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
"""

__author__ = 'Todd Larsen (tlarsen@google.com)'


import copy

import appengine_config
from google.appengine.api import namespace_manager
from google.appengine.ext import db

from common import schema_fields
from common import utc
from common import utils
from models import analytics
from models import data_sources
from models import entities
from models import models
from models import transforms
from modules.admin import config
from modules.dashboard import dashboard


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

    LAST_MODIFIED_PROPERTY = '_last_modified'

    def __init__(self, namespace_name, props_dict):
        self.namespace_name = namespace_name
        self.properties = props_dict

    @property
    def last_modified(self):
        return self.properties.get(self.LAST_MODIFIED_PROPERTY) or 0

    def marshal(self, properties=None):
        if properties is None:
            properties = self.properties
        return transforms.dumps(properties)

    @classmethod
    def unmarshal(cls, json):
        return transforms.loads(json)


class TotalEnrollmentDTO(EnrollmentsDTO):
    """Data transfer object for a single, per-course enrollment count."""

    TOTAL_PROPERTY = 'count'

    def get(self):
        """Returns the value of an enrollment counter (or 0 if not yet set)."""
        return self.properties.get(self.TOTAL_PROPERTY, 0)

    def set(self, count):
        """Overwrite the enrollment counter with a new count value."""
        self.properties[self.TOTAL_PROPERTY] = count
        self.properties[self.LAST_MODIFIED_PROPERTY] = utc.now_as_timestamp()

    def inc(self, offset=1):
        """Increment an enrollment counter by a signed offset; default is 1."""
        self.set(self.get() + offset)

    @property
    def is_empty(self):
        return self.TOTAL_PROPERTY not in self.properties


class BinnedEnrollmentsDTO(EnrollmentsDTO):
    """Data transfer object for per-course, binned enrollment event counts."""

    BINNED_PROPERTY = 'binned'

    @property
    def binned(self):
        """Returns the binned counters dict (possibly empty).

        Returns:
            Returns a dict containing a bin for each day with at least one
            counted event. The keys of the returned dict are the 00:00:00 UTC
            time of each non-zero daily bin, as seconds since epoch. The values
            are the total number of counted events in the day starting at that
            time key.
        """
        return self.properties.setdefault(self.BINNED_PROPERTY, {})

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

    @property
    def is_empty(self):
        return not self.binned

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
        self.properties[self.LAST_MODIFIED_PROPERTY] = utc.now_as_timestamp()

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
        self.properties[self.LAST_MODIFIED_PROPERTY] = utc.now_as_timestamp()

    BIN_FORMAT = '%Y%m%d'

    def marshal(self, properties=None):
        if properties is None:
            properties = copy.copy(self.properties)

        binned = properties.get(self.BINNED_PROPERTY)
        if binned:
            properties[self.BINNED_PROPERTY] = dict(
                [(utc.to_text(seconds=seconds, fmt=self.BIN_FORMAT), count)
                 for seconds, count in binned.iteritems()])

        return super(BinnedEnrollmentsDTO, self).marshal(properties=properties)

    @classmethod
    def unmarshal(cls, json):
        properties = super(BinnedEnrollmentsDTO, cls).unmarshal(json)
        binned = properties.get(cls.BINNED_PROPERTY)
        if binned:
            properties[cls.BINNED_PROPERTY] = dict(
                [(utc.text_to_timestamp(text, fmt=cls.BIN_FORMAT), count)
                 for text, count in binned.iteritems()])
        return properties


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
    def _key_name(cls, namespace_name):
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
    def _namespace_name(cls, key_name):
        """Returns the namespace_name extracted from the supplied key_name."""
        # string.split() always returns a list of at least length 1, even for
        # an empty string or string that does not contain the separator, so
        # this simple expression should not raise exceptions.
        return key_name.split(cls.KEY_SEP, 1)[0]

    @classmethod
    def new_dto(cls, namespace_name, properties=None, entity=None):
        """Returns a DTO initialized from entity or namespace_name."""
        if entity is not None:
            # Prefer namespace_name derived from the entity key name if present.
            name = entity.key().name()
            if name is not None:
                namespace_name = cls._namespace_name(name)

            # Prefer properties JSON-decoded from the entity if present.
            if entity.json:
                properties = cls.DTO.unmarshal(entity.json)

        if properties is None:
            properties = {}

        return cls.DTO(namespace_name, properties)

    @classmethod
    def load_or_default(cls, namespace_name):
        """Returns DTO of the namespace_name entity, or a DTO.is_empty one."""
        with utils.Namespace(appengine_config.DEFAULT_NAMESPACE_NAME):
            entity = cls.ENTITY.get_by_key_name(cls._key_name(namespace_name))
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
        with utils.Namespace(appengine_config.DEFAULT_NAMESPACE_NAME):
            many_entities = cls.ENTITY.get_by_key_name(
                [cls._key_name(ns_name) for ns_name in namespace_names])
            return [cls.new_dto(ns_name, entity=entity)
                    for ns_name, entity in zip(namespace_names, many_entities)]

    @classmethod
    def load_many_mapped(cls, namespace_names):
        """Returns a dict with namespace name keys and DTO values."""
        return dict([(dto.namespace_name, dto)
                     for dto in cls.load_many(namespace_names)])

    @classmethod
    def delete(cls, namespace_name):
        """Deletes from the Datastore the namespace_name counter entity."""
        with utils.Namespace(appengine_config.DEFAULT_NAMESPACE_NAME):
            entity = cls.ENTITY.get_by_key_name(cls._key_name(namespace_name))
            if entity is not None:
                entity.delete()

    @classmethod
    def _save(cls, dto):
        # The "save" operation is not public because clients of the enrollments
        # module should cause Datastore mutations only via set() and inc().
        with utils.Namespace(appengine_config.DEFAULT_NAMESPACE_NAME):
            entity = cls.ENTITY(key_name=cls._key_name(dto.namespace_name))
            entity.json = dto.marshal()
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
        dto = cls.new_dto(namespace_name, properties={})
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


def delete_counters(namespace_name):
    """Called by admin.config.DeleteCourseHandler.delete_course()."""
    TotalEnrollmentDAO.delete(namespace_name)
    EnrollmentsAddedDAO.delete(namespace_name)
    EnrollmentsDroppedDAO.delete(namespace_name)


def _count_add(unused_id, utc_date_time):
    """Called back from student lifecycle queue when student (re-)enrolls."""
    namespace_name = namespace_manager.get_namespace()
    TotalEnrollmentDAO.inc(namespace_name)
    EnrollmentsAddedDAO.inc(namespace_name, utc_date_time)


def _count_drop(unused_id, utc_date_time):
    """Called back from StudentLifecycleObserver when user is unenrolled."""
    namespace_name = namespace_manager.get_namespace()
    TotalEnrollmentDAO.inc(namespace_name, offset=-1)
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


MODULE_NAME = 'site_admin_enrollments'


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
