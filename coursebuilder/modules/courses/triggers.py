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

"""Triggers to change course and content availability."""

__author__ = 'Todd Larsen (tlarsen@google.com)'


import collections
import datetime
import logging

from google.appengine.api import namespace_manager

from common import resource
from common import utc
from controllers import sites
from models import courses
from modules.courses import availability_options


def _fully_qualified_typename(cls):
    """Returns a 'package...module.ClassName' string for the supplied class."""
    return '{}.{}'.format(cls.__module__, cls.__name__)


def _qualified_typename(cls, num_package_path_parts_to_keep=1):
    """Returns a 'module.ClassName' string of the supplied class."""
    num_parts_plus_trailing_class = num_package_path_parts_to_keep + 1
    package_modules_class_parts = _fully_qualified_typename(cls).split('.')
    kept_parts = package_modules_class_parts[-num_parts_plus_trailing_class:]
    return '.'.join(kept_parts)


class DateTimeTrigger(object):
    """Trigger some side-effect at a specified date and time."""

    MISSING_TRIGGER_FMT = "'{}' trigger is missing."
    UNEXPECTED_TRIGGER_FMT = 'is_valid ({}) is_future ({}) is_ready ({})'

    def __init__(self, when=None, **unused):
        """Validates and sets a `when` datetime property."""
        self._when = self.validate_when(when)

    NAME_PART_SEP = '~'

    @property
    def name(self):
        """Returns a "name" string that can be compared, sorted, etc."""
        return self.encoded_when

    def __str__(self):
        """Simply returns the `name` property string."""
        return self.name

    @property
    def when(self):
        """Returns a UTC datetime.datetime or None if `when` is invalid."""
        return self._when

    @classmethod
    def validate_when(cls, when):
        """Validates when (encoded or decoded); returns datetime or None."""
        if isinstance(when, datetime.datetime):
            return when

        try:
            return utc.text_to_datetime(when)
        except (ValueError, TypeError) as err:
            cls.log_issue({'when': when}, 'INVALID',
                          datetime.datetime.__name__, cause=repr(err))
            return None

    @classmethod
    def encode_when(cls, when):
        """Encodes datetime into form payload (stored settings) form."""
        if not isinstance(when, datetime.datetime):
            return None  # Can only encode a datetime.datetime.
        return utc.to_text(dt=when)

    @property
    def encoded_when(self):
        """Encodes `when` into form payload (stored settings) form."""
        return self.encode_when(self.when)

    ValidOrNot = collections.namedtuple('ValidOrNot',
        ['valid', 'invalid', 'missing', 'unused'])

    @classmethod
    def validate_property(cls, prop_name, validator, encoded, valid_or_not):
        """Updates ValidOrNot in-place for a specified property.

        Args:
            prop_name: name string of the property of interest
            validator: function that accepts single encoded value and returns
                either the valid decoded value or None.
            encoded: a dict of property names to their encoded values.
            valid_or_not: updated in-place ValidOrNot namedtuple containing:
                valid, dict of valid property names and decoded values
                invalid, dict of invalid property names and bad encoded values
                missing, set of names of expected but missing properties
                unused, dict of encoded property names and values not in any
                    of `valid`, `invalid`, or `missing`
        """
        if prop_name in encoded:
            raw = encoded[prop_name]
            validated = validator(raw)
            if validated:
                valid_or_not.valid[prop_name] = validated
            else:
                valid_or_not.invalid[prop_name] = raw
        else:
            valid_or_not.missing.add(prop_name)

        valid_or_not.unused.pop(prop_name, None)  # No KeyError if missing.

    VALIDATES = ['when']

    @classmethod
    def validate(cls, encoded):
        """Extracts, validates, and decodes properties from an encoded dict.

        Args:
            encoded: a dict of property names to their encoded values.

        Returns:
          A ValidOrNot namedtuple updated by one or more calls to
          validate_property().
        """
        valid_or_not = cls.ValidOrNot({}, {}, set(), encoded.copy())
        cls.validate_property('when',
            cls.validate_when, encoded, valid_or_not)
        return valid_or_not

    @classmethod
    def decode(cls, encoded, **kwargs):
        """Decodes form payload (or stored settings) into a trigger."""
        # Ctor will complain about any missing properties not present in
        # encoded or kwargs overrides.
        valid_or_not = cls.validate(encoded)
        ctor_kwargs = valid_or_not.valid
        ctor_kwargs.update(cls.only_explicit_overrides(kwargs))
        return cls(**ctor_kwargs)

    @property
    def decoded(self):
        """Returns the DateTimeTrigger as a dict of *decoded* properties."""
        present = {}
        if self.when:
            present['when'] = self.when
        return present

    @classmethod
    def encode(cls, when=None, **unused):
        """Returns encoded dict containing only encode-able properties."""
        encoded = {}
        encoded_when = cls.encode_when(when)
        if encoded_when:
            encoded['when'] = encoded_when
        return encoded

    @property
    def encoded(self):
        """Encodes DateTimeTrigger as form payload (or stored settings)."""
        return self.encode(**self.decoded)

    @property
    def is_valid(self):
        """Returns True if DateTimeTrigger properties are currently valid."""
        return self.when

    def is_future(self, now=None):
        """Returns True if `when` is valid and in the future from `now`."""
        if now is None:
            now = utc.now_as_datetime()
        return self.when and (now < self.when)

    def is_ready(self, now=None):
        """Returns True if valid, current (not future), and can be applied."""
        return self.is_valid and (now > self.when)

    @classmethod
    def get_from_settings(cls, settings):
        """Returns the encoded triggers from the supplied settings."""
        publish = cls._get_publish_settings(settings)
        return publish.get(cls.ENCODED_TRIGGERS, [])

    @classmethod
    def set_into_settings(cls, triggers, settings):
        """Sets the encoded triggers into the supplied settings."""
        publish = cls._get_publish_settings(settings)
        if triggers:
            publish[cls.ENCODED_TRIGGERS] = triggers
        elif cls.ENCODED_TRIGGERS in publish:
            del publish[cls.ENCODED_TRIGGERS]

    @classmethod
    def payload_triggers_into_settings(cls, payload, settings):
        """Places triggers from form payload into the supplied settings."""
        cls.set_into_settings(
            payload.get(cls.ENCODED_TRIGGERS), settings)

    @classmethod
    def sort(cls, triggers):
        """In-place sorts a list of DateTimeTriggers, by increasing `when`."""
        triggers.sort(key=lambda t: t.when)
        # As a convenience, also return the original sorted in-place list.
        return triggers

    @classmethod
    def separate_valid_triggers(cls, encoded_triggers,
                                now=None, course=None, namespace=None):
        """Separates triggers into ready and future, discarding invalid ones.

        Args:
            encoded_triggers: a list of encoded (e.g. form payload or marshaled
                for storing with course settings) triggers.
            now: UTC time as a datetime; default is None, indicating that
                utc.now_as_datetime() should be called.
            course: optional Course used by some triggers for additional
                decoding, initialization, and validation; default is None,
                which causes it to be determined from namespace.
            namespace: namespace name; default is None, indicating that it
                should be obtained from course or the namespace_manager.

        Returns:
            Two lists:
            The first list contains still-encoded future triggers, in same
            order in which they appeared in encoded_triggers.

            The second list the valid, decoded, is_ready (based on the `now`
            time) DateTimeTriggers available to be applied. These triggers
            occur in the second list in "application order", sorted by
            increasing `when` values.

            Any triggers in encoded_triggers that were invalid in some way
            have their defects logged and are then discarded ("dropped on the
            floor").
        """
        if not encoded_triggers:
            return [], []  # Nothing to do, so don't waste time logging, etc.

        if now is None:
            now = utc.now_as_datetime()

        if (namespace is None) or (course is None):
            course, namespace, _ = _get_course_namespace_app_context(
                course=course, namespace=namespace)

        logging.info(
            'SEPARATING %d encoded %s(s) in %s.',
            len(encoded_triggers), cls.typename(), namespace)

        future_encoded, ready_decoded = [], []
        for et in encoded_triggers:
            if et is None:
                cls.log_issue(et, 'MISSING', cls.typename(),
                    cause=cls.MISSING_TRIGGER_FMT.format(None))
                continue
            dt = cls.decode(et, course=course)
            if (not dt) or (not dt.is_valid):
                # decode() will have already logged various error messages.
                continue
            if dt.is_future(now=now):
                # Valid, but future, trigger, so leave encoded for later.
                future_encoded.append(et)
                continue
            if dt.is_ready(now=now):
                # Valid trigger whose time has passed, ready to apply.
                ready_decoded.append(dt)
                continue
            cls.log_issue(et, 'UNEXPECTED', cls.typename(),
                cause=cls.UNEXPECTED_TRIGGER_FMT.format(
                    dt.is_valid, dt.is_future(now=now), dt.is_ready(now=now)))

        return future_encoded, cls.sort(ready_decoded)

    @classmethod
    def only_explicit_overrides(cls, overrides):
        """Returns dict of only override items that have non-None values.

        Args:
            overrides: an iterator of 2-tuples containing property name and
                override values, or a dict, in which case it is converted to
                the required 2-tuple iterator by calling iteritems().
        """
        if isinstance(overrides, dict):
            overrides = overrides.iteritems()
        return dict([(k, v) for k, v in overrides if v is not None])

    @classmethod
    def typename(cls):
        """Returns a 'module.ClassName' string used in logging."""
        return _qualified_typename(cls)

    @property
    def logged(self):
        """Returns a verbose string of the trigger intended for logging."""
        return '{}({})'.format(self.__class__.typename(),
                               self.name.replace(self.NAME_PART_SEP, ', '))

    @classmethod
    def log_issue(cls, encoded, what, why,
                  namespace=None, cause='', log_level=logging.error):
        """Assemble a trigger error message from optional parts and log it."""
        # "INVALID content in...
        parts = ["{} '{}' in".format(what, why)]
        if namespace is None:  # Note: Blank namespace is permitted and valid.
            namespace = namespace_manager.get_namespace()
        parts.append('namespace {}'.format(namespace))
        # "INVALID content in... encoded: {avail...} ...
        parts.append('encoded: "{}"'.format(encoded))
        # "INVALID content in... encoded: {avail...} cause: ValueError: ...
        if cause:
            parts.append('cause: "{}"'.format(cause))
        log_level(' '.join(parts))

    @classmethod
    def _get_publish_settings(cls, settings):
        return settings.setdefault('publish', {})


class AvailabilityTrigger(DateTimeTrigger):
    """Availability change to be applied at the specified date/time."""

    UNEXPECTED_AVAIL_FMT = "Availability '{}' not in {}."

    def __init__(self, availability=None, **super_kwargs):
        """Validates and sets `availability` and super class properties."""
        super(AvailabilityTrigger, self).__init__(**super_kwargs)
        self._availability = self.validate_availability(availability)

    @property
    def name(self):
        """Returns a "name" string that can be compared, sorted, etc."""
        return '{}{}{}'.format(super(AvailabilityTrigger, self).name,
            self.NAME_PART_SEP, self.encoded_availability)

    @property
    def availability(self):
        """Returns a subclass-specific AVAILABILITY_VALUES string or None."""
        return self._availability

    @classmethod
    def validate_availability(cls, availability):
        """Returns availability if in AVAILABILITY_VALUES, otherwise None."""
        if availability in cls.AVAILABILITY_VALUES:
            return availability

        encoded = {'availability': availability}
        cls.log_issue(encoded, 'INVALID', 'availability',
            cause=cls.UNEXPECTED_AVAIL_FMT.format(
                availability, cls.AVAILABILITY_VALUES))
        return None


    @classmethod
    def encode_availability(cls, availability):
        """Returns validated availability (encode and decode are identical)."""
        return cls.validate_availability(availability)

    @property
    def encoded_availability(self):
        return self.encode_availability(self.availability)

    VALIDATES = ['availability']

    @classmethod
    def validate(cls, encoded):
        valid_or_not = super(AvailabilityTrigger, cls).validate(encoded)
        cls.validate_property('availability',
            cls.validate_availability, encoded, valid_or_not)
        return valid_or_not

    @property
    def decoded(self):
        """Returns the AvailabilityTrigger as dict of *decoded* properties."""
        present = super(AvailabilityTrigger, self).decoded
        if self.availability:
            present['availability'] = self.availability
        return present

    @classmethod
    def encode(cls, availability=None, **super_kwargs):
        """Returns encoded dict containing only encode-able properties."""
        encoded = super(AvailabilityTrigger, cls).encode(**super_kwargs)
        encoded_availability = cls.encode_availability(availability)
        if encoded_availability:
            encoded['availability'] = encoded_availability
        return encoded

    @property
    def is_valid(self):
        """Returns True if the Trigger properties are *all* currently valid."""
        return self.availability and super(AvailabilityTrigger, self).is_valid


class ContentTrigger(AvailabilityTrigger):
    """A course content availability change applied at specified date/time."""

    ENCODED_TRIGGERS = 'content_triggers'
    TRIGGERS_CSS = ENCODED_TRIGGERS.replace('_', '-')
    TRIGGER_CSS = TRIGGERS_CSS[:-1]

    AVAILABILITY_VALUES = availability_options.ELEMENT_VALUES

    # On the Publish > Availability form (in the element_settings course
    # outline and the <option> values in the content_triggers 'content'
    # <select>), there are only two content types: 'unit', and 'lesson'.
    # All types other than 'lesson' (e.g. 'unit', 'link', 'assessment') are
    # represented by 'unit' instead.
    CONTENT_TYPE_FINDERS = {
        'unit': lambda course, id: course.find_unit_by_id(id),
        'lesson': lambda course, id: course.find_lesson_by_id(None, id),
    }

    ALLOWED_CONTENT_TYPES = CONTENT_TYPE_FINDERS.keys()

    UNEXPECTED_CONTENT_FMT = 'Content type "{}" not in {}.'
    MISSING_CONTENT_FMT = 'No content matches resource Key "{}".'

    KEY_TYPENAME = _qualified_typename(resource.Key)

    def __init__(self, content=None, content_type=None, content_id=None,
                 found=None, course=None, **super_kwargs):
        """Validates the content type and id and then initializes `content`."""
        super(ContentTrigger, self).__init__(**super_kwargs)

        self._content = self.validate_content(content=content,
            content_type=content_type, content_id=content_id)

        if (not found) and course and self._content:
            found = self.find_content_in_course(self._content, course)

        self._found = found

    @property
    def name(self):
        return '{}{}{}'.format(super(ContentTrigger, self).name,
            self.NAME_PART_SEP, self.encoded_content)

    @property
    def content(self):
        return self._content

    @classmethod
    def validate_content_type(cls, content_type):
        """Returns content_type if in ALLOWED_CONTENT_TYPES, otherwise None."""
        if content_type in cls.ALLOWED_CONTENT_TYPES:
            return content_type

        cls.log_issue({'content_type': content_type}, 'INVALID',
            cls.KEY_TYPENAME, cause=cls.UNEXPECTED_CONTENT_FMT.format(
                content_type, cls.ALLOWED_CONTENT_TYPES))
        return None


    @classmethod
    def validate_content_type_and_id(cls, content_type, content_id):
        """Returns a content resource.Key if content type and ID are valid."""
        if not cls.validate_content_type(content_type):
            return None

        # Both content_type and content_id were provided, and content_type
        # is one of the ALLOWED_CONTENT_TYPES, so now attempt to produce a
        # resource.Key from the two.
        try:
            return resource.Key(content_type, content_id)
        except (AssertionError, AttributeError, ValueError) as err:
            encoded = {'content_type': content_type, 'content_id': content_id}
            cls.log_issue(encoded, 'INVALID', cls.KEY_TYPENAME,
                          cause=repr(err))
            return None

    @classmethod
    def validate_content(cls, content=None,
                         content_type=None, content_id=None):
        """Validates content key; returns it decoded or None if invalid.

        Args:
            content: a resource.Key, or a string resource.Key.fromstring()
                can use to create one.
            content_type: an optional course content type, used only if
                `content` was not supplied, that validate_content_type()
                must be able to validate.
            content_id: an optional course content ID, used only if `content`
                was not supplied.

        Returns:
            Either a valid content resource.Key obtained from one or more of
            the supplied keyword arguments, or None.
        """
        # If `content` was not provided, validate content type and ID instead.
        if not content:
            return cls.validate_content_type_and_id(content_type, content_id)

        if not isinstance(content, resource.Key):
            # If `content` is a valid string encoding of a resource.Key, it
            # needs to actually be a resource.Key before its content.type can
            # be checked, so attempt a conversion.
            try:
                content = resource.Key.fromstring(content)
            except (AssertionError, AttributeError, ValueError) as err:
                cls.log_issue({'content': content}, 'INVALID',
                              cls.KEY_TYPENAME, cause=repr(err))
                return None
        # else:
        # `content` is already a resource.Key (such as when the ContentTrigger
        # class itself calls encode_content()), just skip straight to the
        # validate_content_type() check.

        if cls.validate_content_type(content.type):
            return content

        # `content` is now a valid resource.Key, but resource.Key.type is not
        # one of the ALLOWED_CONTENT_TYPES.
        cls.log_issue({'content': str(content)}, 'INVALID', cls.KEY_TYPENAME,
            cause=cls.UNEXPECTED_CONTENT_FMT.format(
                content.type, cls.ALLOWED_CONTENT_TYPES))
        return None

    @classmethod
    def encode_content_type_and_id(cls, content_type, content_id):
        content = cls.validate_content_type_and_id(content_type, content_id)
        return str(content) if content else None

    @classmethod
    def encode_content(cls, content=None, content_type=None, content_id=None):
        """Encodes content into form payload (stored settings) form."""
        # validate_content() takes care of all possible cases, and in the
        # most common case where `content` is already a resource.Key, it skips
        # all the way to the validate_content_type() check.
        content = cls.validate_content(content=content,
            content_type=content_type, content_id=content_id)

        # Either validate_content() found a way to return a resource.Key with
        # a Key.type in the ALLOWED_CONTENT_TYPES, so str(content) is the
        # desired encoded content key, or it failed.
        #
        # Reasons encoding can fail:
        # 1) resource.Key.fromstring(content) in decode_content() failed
        #    to make a resource.Key.
        # 2) resource.Key(content_type, content_id) in decode_content()
        #    failed to make a resource.Key.
        # 3) validate_content_type(content.type) in decode_content()
        #    failed for the existing or created content key because
        #    content.type was not in ALLOWED_CONTENT_TYPES.
        return str(content) if content else None

    @property
    def encoded_content(self):
        """Encodes `content` into form payload (stored settings) form."""
        return self.encode_content(content=self.content)

    VALIDATES = ['content', 'content_type', 'content_id']

    @classmethod
    def validate(cls, encoded):
        valid_or_not = super(ContentTrigger, cls).validate(encoded)

        validate_content_kwargs = dict(
            [(k, encoded[k]) for k in cls.VALIDATES if k in encoded])
        valid_content = cls.validate_content(**validate_content_kwargs)

        if valid_content:
            valid_or_not.valid['content'] = valid_content
            valid_or_not.valid['content_type'] = valid_content.type
            valid_or_not.valid['content_id'] = valid_content.key
        else:
            # Only set in invalid the encoded values actually present.
            for k in cls.VALIDATES:
                if k in encoded:
                    valid_or_not.invalid[k] = encoded[k]
                else:
                    valid_or_not.missing.add(k)

        for k in ContentTrigger.VALIDATES:
            valid_or_not.unused.pop(k, None)  # No KeyError if no k.

        return valid_or_not

    @property
    def decoded(self):
        """Returns the Trigger as a dict of present, *decoded* properties."""
        present = super(ContentTrigger, self).decoded
        if self.content:
            present['content'] = self.content
        return present

    @classmethod
    def encode(cls, content=None, content_type=None, content_id=None,
               **super_kwargs):
        encoded = super(ContentTrigger, cls).encode(**super_kwargs)
        valid_content = cls.validate_content(content=content,
            content_type=content_type, content_id=content_id)
        encoded_content = cls.encode_content(content=valid_content)
        if encoded_content:
            encoded['content'] = encoded_content
        return encoded

    @property
    def found(self):
        """Returns the unit, lesson, etc., if one was found, or None."""
        return self._found

    @property
    def type(self):
        """Returns associated course content type if one exists, or None."""
        return self.content.type if self.content else None

    @property
    def id(self):
        """Returns an associated course content ID if one exists, or None."""
        return self.content.key if self.content else None

    @property
    def is_valid(self):
        """Returns True if id, type, found, when, etc. are *all* valid."""
        return (self.content and self.found and
                super(ContentTrigger, self).is_valid)

    @classmethod
    def get_content_finder(cls, content):
        if not content:
            cls.log_issue({'content': content}, 'UNSPECIFIED',
                cls.KEY_TYPENAME,
                cause='"{}" has no content finder function.'.format(content))
            return None

        find_func = cls.CONTENT_TYPE_FINDERS.get(content.type)
        if find_func:
            return find_func

        cls.log_issue({'content': str(content)}, 'UNEXPECTED',
            cls.KEY_TYPENAME,
            cause=cls.UNEXPECTED_CONTENT_FMT.format(
                content.type, cls.ALLOWED_CONTENT_TYPES))
        return None

    @classmethod
    def find_content_in_course(cls, content, course, find_func=None):
        if not course:
            cls.log_issue({'content': str(content)}, 'ABSENT', 'course',
                cause='CANNOT find content in "{}" course.'.format(course))
            return None

        if not find_func:
            find_func = cls.get_content_finder(content)

        if not find_func:
            return None  # get_content_finder() already logged the issue.

        found = find_func(course, content.key)

        if found:
            return found

        cls.log_issue({'content': str(content)}, 'OBSOLETE', cls.KEY_TYPENAME,
                      cause=cls.MISSING_CONTENT_FMT.format(content))
        return None

    @classmethod
    def triggers_with_content(cls, settings, selectable_content):
        """Removes obsolete content triggers from the course settings.

        Args:
            settings: the course settings, from app_context.get_environ().
            selectable_content: a dict of <select> <option> option/text pairs;
                the option dict keys are treated as a set of the valid
                course content resource.Keys, in encoded string form.

        Returns:
            A list of the remaining content triggers (encoded in form payload
            and stored settings form) whose associated content still exist.
        """
        encoded_triggers = cls.get_from_settings(settings)

        # Course content associated with existing availability triggers could
        # have been deleted since the trigger itself was created. If the
        # content whose availability was meant to be updated by the trigger
        # has been deleted, also discard the obsolete trigger and do not
        # display it in the Publish > Availability form. (It displays
        # incorrectly anyway, using the first <option> since the trigger
        # content key value is non longer present in the <select>.
        #
        # Saving the resulting form will then omit the obsolete triggers.
        # The UpdateCourseAvailability cron job also detects these obsolete
        # triggers and discards them as well.
        triggers_with_content = []
        for encoded in encoded_triggers:
            encoded_content = encoded.get('content')
            if encoded_content in selectable_content:
                triggers_with_content.append(encoded)
            else:
                cls.log_issue(encoded, 'OBSOLETE', cls.KEY_TYPENAME,
                    cause=cls.MISSING_CONTENT_FMT.format(encoded_content))

        return triggers_with_content

    @classmethod
    def apply_triggers(cls, triggers, namespace=None):
        """Updates course content availability from a list of triggers.

        Applies the supplied list of "ready" course content triggers in order.
        All of the triggers should be valid and should already be sorted by
        increasing values of `when`. The second list returned by
        separate_valid_triggers() statisfies these preconditions.

        "Valid" means the trigger is not malformed and still has associated
        course content that exists. "Ready" means `when` specifies a date and
        time that is now in the past.

        Sorting is required so that, in the case of multiple valid, ready
        triggers associated with the same course content, the chronologically
        last trigger is the one whose availability change persists for that
        content.

        Once applied, a trigger is considered consumed and is not added back
        to the future triggers stored in the course settings.

        Args:
            triggers: a list of ContentTriggers, assumed to all be valid and
                to have been sorted in order of increasing `when` values.
            namespace: optional namespace name string, used in log messages.
        """
        if not triggers:
            return 0  # Nothing to do, so don't waste time logging, etc.

        if namespace is None:  # Note: Blank namespace is permitted and valid.
            namespace = namespace_manager.get_namespace()

        changes = 0
        for t in triggers:
            current = t.found.availability
            if current != t.availability:
                changes += 1
                t.found.availability = t.availability
                logging.info(
                    'TRIGGERED %s content availability "%s" to "%s": %s',
                    namespace, current, t.availability, t.logged)
            else:
                logging.info(
                    'UNCHANGED %s content availability "%s": %s',
                    namespace, current, t.logged)

        return changes


def _get_course_namespace_app_context(
    course=None, namespace=None, app_context=None):
    # Make calling this when all values are known as cheap as possible.
    if course and namespace and app_context:
        return (course, namespace, app_context)

    if course and not app_context:
        app_context = course.app_context
    if app_context and not namespace:
        namespace = app_context.get_namespace_name()
    if not namespace:
        namespace = namespace_manager.get_namespace()
    if not app_context:
        app_context = sites.get_app_context_for_namespace(namespace)
    if not course:
        course = courses.Course(app_context)
    return (course, namespace, app_context)
