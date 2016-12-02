# Copyright 2016 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS-IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Stored course enrollment statistics.

This module implements three counters that track per-course enrollment activity:
'total', 'adds', and 'drops'. For each course, a per-course instance of these
counters is stored in the default AppEngine namespace.

A course is identified by the corresponding namespace name. To obtain all of
the counters of a given type (e.g. 'total'):
1) Call sites.get_all_courses() to obtain a list of ApplicationContexts.
2) Call get_namespace_name() on each ApplicationContext in the resulting list.
3) Pass this list of namespace names to load_many() of the DAO of the desired
   counter type, e.g. TotalEnrollmentDAO.load_many(list_of_namespace_names).

For example, consider the entity key names of the counters associated with a
course with namespace_name 'sample'. The entities storing the counters for
that course would be found in the default namespace at "ns_sample:total",
"ns_sample:adds", and "ns_sample:drops". Similarly, other courses would have
their own instances of these counters in the default namespace, with key names
similarly derived from their namespace names.

'total' is a simple single-value counter that represents the current total
enrollment a single course. This counter is updated in real time by
registering StudentLifecycleObserver handlers that tally the equivalent of:
  (number of EVENT_ADD + number of EVENT_REENROLL)
    - (number of EVENT_UNENROLL + number of EVENT_UNENROLL_COMMANDED)
A MapReduce will also periodically determine the actual value by iterating over
the Datastore and overwrite the event tally.

'adds' is a collection of counters that bin the EVENT_ADD and EVENT_REENROLL
events that occur in a single day, via StudentLifecycleObserver handlers.

'drops' is the analogue of 'adds' that tracks EVENT_UNENROLL and
EVENT_UNENROLL_COMMANDED.

These counters are stored in the default namespace to reduce the implementation
complexity and to concentrate the data into a fixed number of rows for speed
in loading. The 'total', 'adds', and 'drops' counters are separate entities to
reduce contention between the StudentLifecycleObserver handlers updating them.

A _new_course_counts callback initializes these enrollments counters to zero
upon course creation. Student lifecycle events will update these counters in
near real-time soon after the course is created.

Courses that exist in the Datastore prior to updating an installation to a new
Course Builder version that implements enrollments counters will be missing
those counter entities in the Datastore. These missing counters will be
initialized for the first time by enrollments_mapreduce.ComputeCounts
MapReduceJobs. Student lifecycle events will trigger MapReduceJobs for these
missing counters and then update them in near real-time soon after they are
initialized by the background jobs.
"""

__author__ = 'Todd Larsen (tlarsen@google.com)'


import collections
import copy
import datetime
import logging

import appengine_config
from google.appengine.api import namespace_manager
from google.appengine.ext import db

from common import schema_fields
from common import utc
from common import utils as common_utils
from controllers import sites
from controllers import utils
from models import analytics
from models import data_sources
from models import entities
from models import jobs
from models import models
from models import transforms
from modules.admin import config
from modules.dashboard import dashboard


# The "display" rendition of an uninitialized 'Registered Students' value.
NONE_ENROLLED = u'\u2014'  # em dash


class EnrollmentsEntity(entities.BaseEntity):
    """Portions of the Datastore model shared by all enrollment counters.

    Enrollment counters implemented in this module are per-course singletons.
    The key_name of each counter is derived from what the entity class is
    counting (the cls.COUNTING string) and the name of the course, obtained,
    for example, via sites.ApplicationContext.get_namespace_name().

    Subclasses are expected to override the COUNTING string, e.g. 'total',
    'adds', 'drops', etc.
    """
    COUNTING = "UNDEFINED -- override in entity subclass"

    # JSON-encoded DTO is stored here.
    json = db.TextProperty(indexed=False)


class TotalEnrollmentEntity(EnrollmentsEntity):
    COUNTING = 'total'


class EnrollmentsAddedEntity(EnrollmentsEntity):
    COUNTING = 'adds'


class EnrollmentsDroppedEntity(EnrollmentsEntity):
    COUNTING = 'drops'


class EnrollmentsDTO(object):
    """Features common to all DTO of enrollments counters."""

    def __init__(self, the_id, the_dict):
        self.id = the_id
        self.dict = the_dict

    @property
    def last_modified(self):
        return self.dict.get('_last_modified') or 0

    def _force_last_modified(self, timestamp):
        """Sets last_modified to a POSIX timestamp, seconds since UTC epoch."""
        self.dict['_last_modified'] = timestamp

    def set_last_modified_to_now(self):
        """Sets the last_modified property to the current UTC time."""
        self._force_last_modified(utc.now_as_timestamp())

    def seconds_since_last_modified(self, now=None):
        lm = self.last_modified  # Copy to lessen races with other modifiers.
        if not lm:
            return 0  # Last modified not recorded, so no elapsed time since.

        now = now if now is not None else utc.now_as_timestamp()
        return now - lm

    @property
    def is_empty(self):
        """True if no count is present (but may still be pending)."""
        return not self.binned

    @property
    def is_pending(self):
        """True if some background job is initializing the counter."""
        return self.is_empty and self.last_modified

    MAX_PENDING_SEC = 60 * 60  # 1 hour

    @property
    def is_stalled(self):
        """True if pending but since last modified exceeds MAX_PENDING_SEC."""
        return self.seconds_since_last_modified() > self.MAX_PENDING_SEC

    @property
    def is_missing(self):
        """True for uninitialized counters (empty and not pending)."""
        return self.is_empty and (not self.last_modified)

    @property
    def binned(self):
        """Returns an empty binned counters dict (subclasses should override).

        This method exists to provide a uniform representation of what is
        stored in an enrollments counter. Some counters are binned (e.g.,
        EnrollmentsDroppedDTO), and their get() method requires an extra
        timestamp parameter to select a particular bin. Other counters are
        single, unbinned counts (e.g. TotalEnrollmentDTO), and their get()
        method does not accept the meaningless timestamp parameter.

        Some clients want to treat all of these enrollments counter DTOs the
        same, rather than needing to distinquish between those with get() that
        needs a timestamp and those that do not. So, all of the EnrollmentsDTO
        subclasses implement the binned property. For binned counters, it
        simply returns all of the bins. For single, unbinned counters, a
        single "bin" of the current day is returned, containing the single
        counter value.

        Returns:
          Subclasses should override this method to return a dict whose keys
          are integer 00:00:00 UTC "start of day" dates in seconds since
          epoch, and whose values are the counts corresponding to those keys.
        """
        return {}

    def marshal(self, the_dict):
        return transforms.dumps(the_dict)

    @classmethod
    def unmarshal(cls, json):
        return transforms.loads(json)


class TotalEnrollmentDTO(EnrollmentsDTO):
    """Data transfer object for a single, per-course enrollment count."""

    def get(self):
        """Returns the value of an enrollment counter (or 0 if not yet set)."""
        return self.dict.get('count', 0)

    def set(self, count):
        """Overwrite the enrollment counter with a new count value."""
        self.dict['count'] = count
        self.set_last_modified_to_now()

    def inc(self, offset=1):
        """Increment an enrollment counter by a signed offset; default is 1."""
        self.set(self.get() + offset)

    @property
    def is_empty(self):
        # Faster than base class version that could cause creation of the
        # temporary binned dict.
        return 'count' not in self.dict

    @property
    def binned(self):
        """Returns the binned counters dict (empty if uninitialized counter).

        Returns:
            If the counter is initialized (has been set() at least once), a
            dict containing a single bin containing the total enrollments count
            is constructed and returned.  The single key in the returned dict
            is the 00:00:00 UTC "start of day" time of last_modified, as
            seconds since epoch. The single value is the get() count.

            Otherwise, if the counter is uninitialized, an empty dict is
            returned (just like the EnrollmentsDTO base class).
        """
        if self.is_empty:
            return super(TotalEnrollmentDTO, self).binned

        return {
            utc.day_start(self.last_modified): self.get(),
        }


class BinnedEnrollmentsDTO(EnrollmentsDTO):
    """Data transfer object for per-course, binned enrollment event counts."""

    @property
    def binned(self):
        """Returns the binned counters dict (possibly empty).

        Returns:
            If the counter is initialized (at least one timestamped bin has
            been set()), the dict containing a bin for each day with at least
            one counted event is returned. The keys of the returned dict are
            the 00:00:00 UTC "start of day" time of each non-zero daily bin,
            as seconds since epoch. The values are the total number of
            counted events in the day starting at that time key.

            Otherwise, if the counter is uninitialized, an empty dict is
            returned (just like the EnrollmentsDTO base class).
        """
        return self.dict.setdefault(
            'binned', super(BinnedEnrollmentsDTO, self).binned)

    @classmethod
    def bin(cls, timestamp):
        """Converts POSIX timestamp to daily counter bin in self.binned dict.

        Args:
            timestamp: UTC time, as a POSIX timestamp (seconds since epoch).
        Returns:
            The key of the counter bin (which may or may not actually exist)
            in the self.binned dict associated with the supplied UTC time.
        """
        return utc.day_start(timestamp)

    def _get_bin(self, bin_key):
        return self.binned.get(bin_key, 0)

    def get(self, timestamp):
        """Returns a count of events in for a day (selected via a UTC time).

        Args:
            timestamp: UTC time, as a POSIX timestamp (seconds since epoch).
        Returns:
            The counter value of the daily bin, or 0 if the corresponding
            self.bin() does not exist in the self.binned dict.
        """
        return self._get_bin(self.bin(timestamp))

    def _set_bin(self, bin_key, count):
        self.binned[bin_key] = count
        self.set_last_modified_to_now()

    def set(self, timestamp, count):
        """Overwrites the count of events for a day (selected via a UTC time).

        Args:
            timestamp: UTC time, as a POSIX timestamp (seconds since epoch).
            count: the new integer value of the selected binned counter
        """
        self._set_bin(self.bin(timestamp), count)

    def inc(self, timestamp, offset=1):
        """Increments the count of events for a day (selected via a UTC time).

        Args:
            timestamp: UTC time, as a POSIX timestamp (seconds since epoch).
            offset: optional signed increment offset; defaults to 1.
        Returns:
            The incremented (by offset) existing count in the specified daily
            bin -OR- if the selected bin does not exist, count resulting from
            creating a new bin initialized to 0 and incremented by offset.
        """
        bin_key = self.bin(timestamp)
        self._set_bin(bin_key, self._get_bin(bin_key) + offset)
        self.set_last_modified_to_now()

    _BIN_FORMAT = '%Y%m%d'

    def marshal(self, the_dict):
        binned = the_dict.get('binned')
        if binned:
            # A copy (to avoid mutating the original) is only necessary if
            # there are actually int seconds since epoch bin keys that need
            # to be made compatible with JSON.
            the_dict = copy.copy(the_dict)
            the_dict['binned'] = dict(
                [(utc.to_text(seconds=seconds, fmt=self._BIN_FORMAT), count)
                 for seconds, count in binned.iteritems()])

        return super(BinnedEnrollmentsDTO, self).marshal(the_dict)

    @classmethod
    def unmarshal(cls, json):
        the_dict = super(BinnedEnrollmentsDTO, cls).unmarshal(json)
        binned = the_dict.get('binned')
        if binned:
            the_dict['binned'] = dict(
                [(utc.text_to_timestamp(text, fmt=cls._BIN_FORMAT), count)
                 for text, count in binned.iteritems()])
        return the_dict


class EnrollmentsDAO(object):
    """Operations shared by the DAO of all enrollment counters.

    The API is loosely based on models.BaseJsonDao, but with the memcache
    complexity removed, and appengine_config.DEFAULT_NAMESPACE_NAME always
    used as the namespace.

    EnrollmentsDAO is not a generic, "full-featured" DAO. Only the operations
    likely to be used by the admin Courses pages, StudentLifecycleObserver
    event handlers, and the enrollment total MapReduce are provided.
    """

    KEY_SEP = ':'

    @classmethod
    def key_name(cls, namespace_name):
        """Creates enrollment counter key_name strings for Datastore operations.

        Enrollment counter keys are grouped by namespace_name and then by what
        entity class is counting. The key name string is expected to be a
        KEY_SEP-delimited list of substrings. The first substring must always
        be the namespace_name.

        Args:
            namespace_name: the name of the course (e.g. "ns_my_new_course")
        Returns:
            namespace_name and then cls.ENTITY.COUNTING in a string.
            Some examples:
            "ns_example:totals", "ns_example:adds", "ns_example:drops"
        """
        return "%s%s%s" % (namespace_name, cls.KEY_SEP, cls.ENTITY.COUNTING)

    @classmethod
    def namespace_name(cls, key_name):
        """Returns the namespace_name extracted from the supplied key_name."""
        # string.split() always returns a list of at least length 1, even for
        # an empty string or string that does not contain the separator, so
        # this simple expression should not raise exceptions.
        return key_name.split(cls.KEY_SEP, 1)[0]

    @classmethod
    def new_dto(cls, namespace_name, the_dict=None, entity=None):
        """Returns a DTO initialized from entity or namespace_name."""
        if entity is not None:
            # Prefer namespace_name derived from the entity key name if present.
            name = entity.key().name()
            if name is not None:
                namespace_name = cls.namespace_name(name)

            # Prefer the_dict JSON-decoded from the entity if present.
            if entity.json:
                the_dict = cls.DTO.unmarshal(entity.json)

        if the_dict is None:
            the_dict = {}

        return cls.DTO(cls.key_name(namespace_name), the_dict)

    @classmethod
    def load_or_default(cls, namespace_name):
        """Returns DTO of the namespace_name entity, or a DTO.is_empty one."""
        with common_utils.Namespace(appengine_config.DEFAULT_NAMESPACE_NAME):
            entity = cls.ENTITY.get_by_key_name(cls.key_name(namespace_name))
            return cls.new_dto(namespace_name, entity=entity)

    @classmethod
    def load_many(cls, namespace_names):
        """Loads multiple DTOs in the same order as supplied namespace names.

        Args:
            namespace_names: a list of namespace name strings
        Returns:
            A list of cls.DTOs created from entities fetched from the
            Datastore, in the same order as the supplied namespace_names list.
            When no corresponding entity exists in the Datastore for a given
            namespace name, a DTO where DTO.is_empty is true is placed in that
            slot in the returned list (not None like, say, get_by_key_name()).
        """
        with common_utils.Namespace(appengine_config.DEFAULT_NAMESPACE_NAME):
            many_entities = cls.ENTITY.get_by_key_name(
                [cls.key_name(ns_name) for ns_name in namespace_names])
            return [cls.new_dto(ns_name, entity=entity)
                    for ns_name, entity in zip(namespace_names, many_entities)]

    @classmethod
    def load_many_mapped(cls, namespace_names):
        """Returns a dict with namespace_name keys and DTO values."""
        return dict([(cls.namespace_name(dto.id), dto)
                     for dto in cls.load_many(namespace_names)])

    @classmethod
    def load_all(cls):
        """Loads all DTOs that have valid entities, in no particular order.

        Returns:
            An iterator that produces cls.DTOs created from all the ENTITY
            values in the Datastore, in no particular order.
        """
        with common_utils.Namespace(appengine_config.DEFAULT_NAMESPACE_NAME):
            for e in common_utils.iter_all(cls.ENTITY.all()):
                if e.key().name():
                    yield cls.new_dto('', entity=e)

    @classmethod
    def delete(cls, namespace_name):
        """Deletes from the Datastore the namespace_name counter entity."""
        with common_utils.Namespace(appengine_config.DEFAULT_NAMESPACE_NAME):
            entity = cls.ENTITY.get_by_key_name(cls.key_name(namespace_name))
            if entity is not None:
                entity.delete()

    @classmethod
    def mark_pending(cls, dto=None, namespace_name=''):
        """Indicates that a background job is initializing the counter.

        The last_modified property is set to the current time and stored,
        without any counter value, a state that indicates to others that some
        background job is currently computing the value of the counter.

        Args:
            dto: an existing DTO to be "marked" and stored in the Datastore;
              dto.is_missing must be True.
            namespace_name: used to create a new DTO if dto was not supplied.

        Returns:
            The original dto if one was provided; unchanged if the required
            dto.is_missing precondition was not met.

            Otherwise, the last_modified property will be set to the current
            UTC time, but no counter value will be set, resulting in
            dto.is_empty being True and now dto.is_pending also being True
            (and dto.is_missing changing to False).

            If an existing dto was not supplied, creates a new one using the
            provided namespace_name, setting last_modified only, as above,
            again resulting in dto.is_empty and dto.is_pending being True and
            dto.is_missing being False.
        """
        if not dto:
            dto = cls.new_dto(namespace_name, the_dict={})

        if dto.is_missing:
            dto.set_last_modified_to_now()
            cls._save(dto)

        return dto

    @classmethod
    def _save(cls, dto):
        # The "save" operation is not public because clients of the enrollments
        # module should cause Datastore mutations only via set() and inc().
        with common_utils.Namespace(appengine_config.DEFAULT_NAMESPACE_NAME):
            entity = cls.ENTITY(key_name=dto.id)
            entity.json = dto.marshal(dto.dict)
            entity.put()


class TotalEnrollmentDAO(EnrollmentsDAO):
    """A single total enrollment counter for each course."""

    DTO = TotalEnrollmentDTO
    ENTITY = TotalEnrollmentEntity

    @classmethod
    def get(cls, namespace_name):
        """Returns value of a single enrollment total from the Datastore."""
        return cls.load_or_default(namespace_name).get()

    @classmethod
    def set(cls, namespace_name, count):
        """Forces single enrollment total in the Datastore to a new count."""
        dto = cls.new_dto(namespace_name, the_dict={})
        dto.set(count)
        cls._save(dto)
        return dto

    @classmethod
    @db.transactional(xg=True)
    def inc(cls, namespace_name, offset=1):
        """Loads an enrollment counter from the Datastore and increments it."""
        dto = cls.load_or_default(namespace_name)
        dto.inc(offset=offset)
        cls._save(dto) # Save altered/new DTO as entity.
        return dto


class BinnedEnrollmentsDAO(EnrollmentsDAO):
    """Operations common to all binned enrollments counters."""

    DTO = BinnedEnrollmentsDTO

    @classmethod
    def get(cls, namespace_name, date_time):
        """Returns value of a binned enrollment counter from the Datastore."""
        return cls.load_or_default(namespace_name).get(
            utc.datetime_to_timestamp(date_time))

    @classmethod
    @db.transactional(xg=True)
    def set(cls, namespace_name, date_time, count):
        """Sets the Datastore value of a counter in a specific bin."""
        dto = cls.load_or_default(namespace_name)
        dto.set(utc.datetime_to_timestamp(date_time), count)
        cls._save(dto) # Save altered/new DTO as entity.
        return dto

    @classmethod
    @db.transactional(xg=True)
    def inc(cls, namespace_name, date_time, offset=1):
        """Increments the Datastore value of a counter in a specific bin."""
        dto = cls.load_or_default(namespace_name)
        dto.inc(utc.datetime_to_timestamp(date_time), offset=offset)
        cls._save(dto) # Save altered/new DTO as entity.
        return dto


class EnrollmentsAddedDAO(BinnedEnrollmentsDAO):
    ENTITY = EnrollmentsAddedEntity


class EnrollmentsDroppedDAO(BinnedEnrollmentsDAO):
    ENTITY = EnrollmentsDroppedEntity


class ComputeCounts(jobs.MapReduceJob):
    """MapReduce job to set the student total enrollment count for courses.

    This MapReduce updates two of the course enrollments counters, the simple
    'total' enrollment count and the daily-binned 'adds' counts.

    The 'total' counter is updated by calling TotalEnrollmentDAO.set()
    to force a known value on the 'total' counter for a specified course. The
    purpose of this MapReduce is to "reset" the total enrollment count to an
    absolute starting point, and then allow that count to be incremented and
    decremented in real time, between runs of the MapReduce, by the registered
    StudentLifecycleObserver handlers. Those handlers adjust the MapReduce-
    computed starting point by the equivalent of:

    (number of EVENT_ADD + number of EVENT_REENROLL)
     - (number of EVENT_UNENROLL + number of EVENT_UNENROLL_COMMANDED)

    Counters in the daily bins of the 'adds' counters are updated by calling
    EnrollmentsAddedDAO.set() overwrite the values for each daily bin. The
    bin is determined from the Student.enrolled_on value of each student
    enrolled in the specified course. To avoid race conditions between this
    MapReduce and real time updates being made by the student lifecycle event
    handlers, the bin corresponding to "today" when the MapReduce is run is
    *not* overwritten.
    """

    @classmethod
    def get_description(cls):
        return "Update the 'total' and 'adds' counters for a course."

    @classmethod
    def entity_class(cls):
        return models.Student

    @classmethod
    def map(cls, student):
        if student.is_enrolled:
            yield (TotalEnrollmentEntity.COUNTING, 1)
            bin_seconds_since_epoch = BinnedEnrollmentsDTO.bin(
                utc.datetime_to_timestamp(student.enrolled_on))
            yield (bin_seconds_since_epoch, 1)

    @classmethod
    def combine(cls, unused_key, values, previously_combined_outputs=None):
        total = sum([int(value) for value in values])
        if previously_combined_outputs is not None:
            total += sum([int(value) for value in previously_combined_outputs])
        yield total

    @classmethod
    def reduce(cls, key, values):
        total = sum(int(value) for value in values)
        ns_name = namespace_manager.get_namespace()

        if key == TotalEnrollmentEntity.COUNTING:
            TotalEnrollmentDAO.set(ns_name, total)
            yield key, total
        else:
            # key is actually a daily 'adds' counter bin seconds since epoch.
            bin_seconds_since_epoch = long(key)
            today = utc.day_start(utc.now_as_timestamp())
            # Avoid race conditions by not updating today's daily bin (which
            # is being updated by student lifecycle events).
            if bin_seconds_since_epoch != today:
                date_time = utc.timestamp_to_datetime(bin_seconds_since_epoch)
                EnrollmentsAddedDAO.set(ns_name, date_time, total)

    @classmethod
    def complete(cls, kwargs, results):
        if not results:
            ns_name = namespace_manager.get_namespace()
            # Re-check that value actually is zero; there is a race between
            # this M/R job running and student registration on the user
            # lifecycle queue, so don't overwrite to zero unless it really
            # is zero _now_.
            if TotalEnrollmentDAO.get(ns_name) == 0:
                TotalEnrollmentDAO.set(ns_name, 0)


MODULE_NAME = 'site_admin_enrollments'


class _BaseCronHandler(utils.AbstractAllCoursesCronHandler):

    URL_FMT = '/cron/%s/%%s' % MODULE_NAME

    @classmethod
    def is_globally_enabled(cls):
        return True

    @classmethod
    def is_enabled_for_course(cls, app_context):
        return True


class StartComputeCounts(_BaseCronHandler):
    """Handle callback from cron by launching enrollments counts MapReduce."""

    # /cron/site_admin_enrollments/total
    URL = _BaseCronHandler.URL_FMT % TotalEnrollmentEntity.COUNTING

    def cron_action(self, app_context, global_state):
        job = ComputeCounts(app_context)
        ns = app_context.get_namespace_name()
        dto = TotalEnrollmentDAO.load_or_default(ns)

        if job.is_active():
            # Weekly re-computation of enrollments counters, so forcibly stop
            # any already-running job and start over.
            if not dto.is_empty:
                logging.warning(
                    'CANCELING periodic "%s" enrollments total refresh found'
                    ' unexpectedly still running.', dto.id)
            elif dto.is_pending:
                logging.warning(
                    'INTERRUPTING missing "%s" enrollments total'
                    ' initialization started on %s.', dto.id,
                    utc.to_text(seconds=dto.last_modified))
            job.cancel()
        else:
            when = dto.last_modified
            if not dto.is_empty:
                logging.info(
                    'REFRESHING existing "%s" enrollments total, %d as of %s.',
                    dto.id, dto.get(), utc.to_text(seconds=when))
            elif dto.is_pending:
                since = dto.seconds_since_last_modified()
                logging.warning(
                    'COMPLETING "%s" enrollments total initialization started '
                    'on %s stalled for %s.', dto.id, utc.to_text(seconds=when),
                    datetime.timedelta(seconds=since))

        job.submit()


def init_missing_total(enrolled_total_dto, app_context):
    """Returns True if a ComputeCounts MapReduceJob was submitted."""
    name = enrolled_total_dto.id
    when = enrolled_total_dto.last_modified

    if not enrolled_total_dto.is_empty:
        logging.warning(StartInitMissingCounts.LOG_SKIPPING_FMT,
            name, enrolled_total_dto.get(), utc.to_text(seconds=when))
        return False

    delta = enrolled_total_dto.seconds_since_last_modified()
    if enrolled_total_dto.is_pending:
        if not enrolled_total_dto.is_stalled:
            logging.info(
                'PENDING "%s" enrollments total initialization in progress'
                ' for %s, since %s.', name, datetime.timedelta(seconds=delta),
                utc.to_text(seconds=when))
            return False
        logging.warning(
            'STALLED "%s" enrollments total initialization for %s, since %s.',
            name, datetime.timedelta(seconds=delta), utc.to_text(seconds=when))

    # enrolled_total_dto is either *completely* missing (not *just* lacking its
    # counter property, and thus not indicating initialization of that count
    # is in progress), or pending initialization has stalled (taken more than
    # MAX_PENDING_SEC to complete), so store "now" as a last_modified value to
    # indicate that a MapReduce update has been requested.
    marked_dto = TotalEnrollmentDAO.mark_pending(dto=enrolled_total_dto,
        namespace_name=app_context.get_namespace_name())
    logging.info('SCHEDULING "%s" enrollments total update at %s.',
                 marked_dto.id, utc.to_text(seconds=marked_dto.last_modified))
    ComputeCounts(app_context).submit()
    return True


class StartInitMissingCounts(_BaseCronHandler):
    """Handle callback from cron by checking for missing enrollment totals."""

    # /cron/site_admin_enrollments/missing
    URL = _BaseCronHandler.URL_FMT % 'missing'

    LOG_SKIPPING_FMT = (
        'SKIPPING existing "%s" enrollments total recomputation, %d as of %s.')

    def cron_action(self, app_context, global_state):
        total_dto = TotalEnrollmentDAO.load_or_default(
            app_context.get_namespace_name())
        if total_dto.is_missing or total_dto.is_stalled:
            init_missing_total(total_dto, app_context)
        else:
            # Debug-level log message only for tests examining logs.
            logging.debug(self.LOG_SKIPPING_FMT,
                total_dto.id, total_dto.get(),
                utc.to_text(seconds=total_dto.last_modified))


def delete_counters(namespace_name):
    """Called by admin.config.DeleteCourseHandler.delete_course()."""
    TotalEnrollmentDAO.delete(namespace_name)
    EnrollmentsAddedDAO.delete(namespace_name)
    EnrollmentsDroppedDAO.delete(namespace_name)


def _count_add(unused_id, utc_date_time):
    """Called back from student lifecycle queue when student (re-)enrolls.

    This callback only increments 'total' and 'adds' counters that already
    exist in the Datastore.
    """
    namespace_name = namespace_manager.get_namespace()
    total_dto = TotalEnrollmentDAO.load_or_default(namespace_name)

    if not total_dto.is_empty:
        TotalEnrollmentDAO.inc(namespace_name)
    elif total_dto.is_missing:
        init_missing_total(
            total_dto, sites.get_app_context_for_namespace(namespace_name))

    # Update today's 'adds' no matter what, because the ComputeCounts
    # MapReduceJob avoids the current day bin, specifically to avoid races
    # with this callback.
    EnrollmentsAddedDAO.inc(namespace_name, utc_date_time)


def _count_drop(unused_id, utc_date_time):
    """Called back from StudentLifecycleObserver when user is unenrolled.

    This callback only decrements 'total' and increments 'drops' counters that
    already exist in the Datastore.
    """
    namespace_name = namespace_manager.get_namespace()
    total_dto = TotalEnrollmentDAO.load_or_default(namespace_name)

    if not total_dto.is_empty:
        TotalEnrollmentDAO.inc(namespace_name, offset=-1)
    elif total_dto.is_missing:
        init_missing_total(
            total_dto, sites.get_app_context_for_namespace(namespace_name))

    # Update today's 'drops' no matter what, because the ComputeCounts
    # MapReduceJob avoids the current day bin, specifically to avoid races
    # with this callback. (Also, the ComputeCounts MapReduceJob does
    # not implement collecting drops at this time.)
    EnrollmentsDroppedDAO.inc(namespace_name, utc_date_time)


def _new_course_counts(app_context, unused_errors):
    """Called back from CoursesItemRESTHandler when new course is created."""
    namespace_name = app_context.get_namespace_name()
    TotalEnrollmentDAO.set(namespace_name, 0)
    EnrollmentsAddedDAO.set(namespace_name, utc.now_as_datetime(), 0)
    EnrollmentsDroppedDAO.set(namespace_name, utc.now_as_datetime(), 0)


class EnrollmentsDataSource(data_sources.AbstractSmallRestDataSource,
                            data_sources.SynchronousQuery):
    """Merge adds/drops data to single source for display libraries."""

    @classmethod
    def get_name(cls):
        return 'enrollments'

    @classmethod
    def get_title(cls):
        return 'Enrollments'

    @staticmethod
    def required_generators():
        return []

    @classmethod
    def get_schema(cls, app_context, log, source_context):
        ret = schema_fields.FieldRegistry('enrollments')
        ret.add_property(schema_fields.SchemaField(
            'timestamp_millis', 'Milliseconds Since Epoch', 'integer'))
        ret.add_property(schema_fields.SchemaField(
            'add', 'Add', 'integer',
            description='Number of students added in this time range'))
        ret.add_property(schema_fields.SchemaField(
            'drop', 'Drop', 'integer',
            description='Number of students dropped in this time range'))
        return ret.get_json_schema_dict()['properties']

    @classmethod
    def fetch_values(cls, app_context, source_ctx, schema, log, page_number):
        # Get values as REST to permit simple integration to graph libraries.
        add_counts = EnrollmentsAddedDAO.load_or_default(
            app_context.get_namespace_name()).binned
        drop_counts = EnrollmentsDroppedDAO.load_or_default(
            app_context.get_namespace_name()).binned
        bin_timestamps = set(add_counts.keys()) | set(drop_counts.keys())
        return [
            {'timestamp_millis': bin_timestamp * 1000,
             'add': add_counts.get(bin_timestamp, 0),
             'drop': drop_counts.get(bin_timestamp, 0)}
            for bin_timestamp in bin_timestamps], 0

    @classmethod
    def fill_values(cls, app_context, template_values):
        # Provide a boolean for do-we-have-any-data-at-all at static
        # page-paint time; DC graphs look awful when empty; simpler to
        # suppress than try to make nice.

        dto = EnrollmentsAddedDAO.load_or_default(
            app_context.get_namespace_name())
        template_values['enrollment_data_available'] = not dto.is_empty


CourseEnrolled = collections.namedtuple('CourseEnrolled',
    ['count', 'display', 'most_recent_enroll'])

_NONE_RECENT_FMT = u'(registration activity is being computed for "{}")'
_MOST_RECENT_FMT = u'Most recent activity at {} for "{}".'

def get_course_enrolled(enrolled_dto, course_name):
    if enrolled_dto.is_empty:
        # 'count' property is not present, so exit early.
        return CourseEnrolled(
            0, NONE_ENROLLED, _NONE_RECENT_FMT.format(course_name))

    count = enrolled_dto.get()
    lm_dt = utc.timestamp_to_datetime(enrolled_dto.last_modified)
    lm_text = utc.to_text(dt=lm_dt, fmt=utc.ISO_8601_UTC_HUMAN_FMT)
    most_recent_enroll = _MOST_RECENT_FMT.format(lm_text, course_name)
    return CourseEnrolled(count, count, most_recent_enroll)


def register_callbacks():
    # Update enrollments counters when a student enrolls, unenrolls.
    models.StudentLifecycleObserver.EVENT_CALLBACKS[
        models.StudentLifecycleObserver.EVENT_ADD][
            MODULE_NAME] = _count_add
    models.StudentLifecycleObserver.EVENT_CALLBACKS[
        models.StudentLifecycleObserver.EVENT_REENROLL][
            MODULE_NAME] = _count_add
    models.StudentLifecycleObserver.EVENT_CALLBACKS[
        models.StudentLifecycleObserver.EVENT_UNENROLL][
            MODULE_NAME] = _count_drop
    models.StudentLifecycleObserver.EVENT_CALLBACKS[
        models.StudentLifecycleObserver.EVENT_UNENROLL_COMMANDED][
            MODULE_NAME] = _count_drop

    # Set counters for newly-created courses initially to zero (to avoid
    # extraneous enrollments MapReduce runs).
    config.CoursesItemRESTHandler.NEW_COURSE_ADDED_HOOKS[
        MODULE_NAME] = _new_course_counts

    # Delete the corresponding enrollments counters when a course is deleted.
    config.CourseDeleteHandler.COURSE_DELETED_HOOKS[
        MODULE_NAME] = delete_counters

    # Register analytic to show nice zoomable graph of enroll/unenroll rates.
    data_sources.Registry.register(EnrollmentsDataSource)
    visualization = analytics.Visualization(
        'enrollments', 'Enrollments', 'templates/enrollments.html',
        data_source_classes=[EnrollmentsDataSource])
    dashboard.DashboardHandler.add_sub_nav_mapping(
        'analytics', 'enrollments', 'Enrollments',
        action='analytics_enrollments',
        contents=analytics.TabRenderer([visualization]))
