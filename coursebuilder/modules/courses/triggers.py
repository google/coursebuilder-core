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

"""Trigger changes to course or content availability at given dates and times.

HOW DATE/TIME TRIGGERS RELATE TO "SETTINGS"

Triggers are stored in "settings" until they are acted on and then discarded.
Triggers can also have side-effects *on* these "settings". What constitutes
"settings" depends on the actual trigger class.

For the modules.courses trigger classes (here in triggers.py), "settings" are
an environ dict such as one returned by a get_environ() call on the
app_context of a course.

For the modules.student_groups trigger classes, "settings" are contained in a
StudentGroupDTO object for each student group.

TRIGGERS STORED IN "SETTINGS"

The modules.courses triggers are stored in fields in a 'publish' dict inside
the environ dict. The SETTINGS_NAME (e.g. content_triggers or course_triggers)
of a trigger class corresponds to the key in the 'publish' dict for a given
list of triggers (e.g. "element" content or course start/end "milestone").

The modules.student_groups triggers are stored in StudentGroupDTO properties.
The SETTINGS_NAME (e.g. content_triggers or course_triggers) of a trigger
class corresponds to an identical property name in that DTO object for a
given list of triggers (e.g. content or course start/end).

"SETTINGS" ALTERED BY TRIGGERS

The trigger classes in modules.courses update "settings" values in a supplied
environ dict (availability changes due to course start/end "milestones")
*and* a supplied Course (and the various Unit, Lesson, etc. resources that make
up the Course content, to change content "element" availability). The act()
methods of these trigger classes do *not* call Course.save_settings() or
Course.save(). Persisting the changes made by triggered act() methods is the
responsibility of the caller of the act_on_settings() method, after all such
triggered changes are applied.

the modules.student_groups trigger classes update "settings" values in a
supplied StudentGroupDTO object. Both course-wide and content "element"
availability overrides are stored in the same DTO. The act() methods update
(or remove, for transitions to the 'no_override' state) these overrides from
the DTO, but do *not* call StudentGroupDAO.save(). Like other triggers,
persisting the changes made by the act() methods is the responsibility of the
act_on_settings() caller.
"""

__author__ = 'Todd Larsen (tlarsen@google.com)'


import collections
import datetime
import logging

from common import resource
from common import utc
from common import utils
from models import courses
from models import resources_display
from modules.courses import availability_options
from modules.courses import constants


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
    """Trigger some side-effect at a specified date and time.

    DateTimeTrigger is very much an abstract base class, as many of its
    methods rely on a class-scoped SETTINGS_NAME constant that is only
    defined by concrete subclasses (e.g. ContentTrigger, MilestoneTrigger,
    but *not* AvailabilityTrigger, which is also an abstract base class).
    """
    FIELD_NAME = 'when'
    FIELDS = [FIELD_NAME]

    MISSING_TRIGGER_FMT = "'{}' trigger is missing."
    IMPOSSIBLE_TRIGGER_FMT = 'is_valid ({}) is_future ({}) is_ready ({})'
    LOG_ISSUE_FMT = '%s %s in namespace %s encoded: "%s" cause: "%s"'
    UNSPECIFIED_FMT = '{} not specified.'

    SET_WILL_OVERWRITE = 'overwrite'
    SET_WILL_MERGE = 'merge'
    # By default, most trigger classes only implement 'overwrite' semantics
    # for set_into_settings().
    SET_ONLY_OVERWRITES = frozenset([SET_WILL_OVERWRITE])
    IMPLEMENTED_SET_SEMANTICS = SET_ONLY_OVERWRITES

    def __init__(self, when=None, **unused):
        """Validates and sets a `when` datetime property."""
        # `when` is always either a datetime object or None.
        self._when = self.validate_when(when)

    NAME_PART_SEP = '~'

    @property
    def name(self):
        """Returns a "name" string that can be compared, sorted, etc."""
        return self.encoded_when

    @property
    def name_as_items(self):
        """Returns name @property parts as a comma-separated items string."""
        return self.name.replace(self.NAME_PART_SEP, ', ')

    def __str__(self):
        """Simply returns the `name` property string."""
        return self.name

    @classmethod
    def kind(cls):
        """Human-readable "kind" of trigger, e.g. 'content availability'.

        Returns:
            A human-readable "kind" string created from cls.SETTINGS_NAME
            if it exists (e.g. "content" from 'content_triggers').  Subclasses
            may append or prepend their words (e.g. ContentTrigger.kind()
            returns "content" from this base class kind() method with
            " availability" appended by its other AvailabilityTrigger.kind()
            base class method.

            Otherwise, the type name is returned by abstract base classes.
        """
        return (cls.typename().split('.')[-1]
                if not hasattr(cls, 'SETTINGS_NAME')
                else cls.SETTINGS_NAME.split('_')[0])

    @classmethod
    def settings_css(cls):
        """Returns the base plural CSS class name used to compute values."""
        return availability_options.option_to_css(cls.SETTINGS_NAME)

    REGISTRY_CSS = 'inputEx-Group inputEx-valid inputEx-ListField-subFieldEl'

    @classmethod
    def registry_css(cls, extra_css=None):
        """Returns 'className' value used with a trigger FieldRegistry."""
        plural_css_class = cls.settings_css()
        crop = 2 if plural_css_class.endswith('es') else 1
        singular_css_class = plural_css_class[:-crop]
        extra_css = [] if not extra_css else [extra_css]
        classes = [singular_css_class, cls.REGISTRY_CSS] + extra_css
        return ' '.join(classes)

    ARRAY_CSS = 'inputEx-Field inputEx-ListField'

    @classmethod
    def array_css(cls, extra_css=None):
        """Returns 'className' value used with a FieldArray of triggers."""
        extra_css = [] if not extra_css else [extra_css]
        classes = [cls.settings_css(), cls.ARRAY_CSS] + extra_css
        return ' '.join(classes)

    ARRAY_WRAPPER_CSS = 'section-with-heading inputEx-fieldWrapper'

    @classmethod
    def array_wrapper_css(cls, extra_css=None):
        """Returns 'wrapperClassName' value used with a triggers FieldArray."""
        extra_css = [] if not extra_css else [extra_css]
        classes = [cls.settings_css(), cls.ARRAY_WRAPPER_CSS] + extra_css
        return ' '.join(classes)

    DATETIME_CSS = 'gcb-datetime inputEx-fieldWrapper gcb-utc-datetime'

    @classmethod
    def when_css(cls, extra_css=None):
        """Returns 'className' value for a 'when' SchemaField."""
        extra_css = [] if not extra_css else [extra_css]
        classes = [DateTimeTrigger.FIELD_NAME, cls.DATETIME_CSS] + extra_css
        return ' '.join(classes)

    @property
    def when(self):
        """Returns a UTC datetime.datetime or None if `when` is invalid."""
        return self._when

    WHEN_TYPENAME = datetime.datetime.__name__

    @classmethod
    def validate_when(cls, when):
        """Validates when (encoded or decoded); returns datetime or None."""
        if isinstance(when, datetime.datetime):
            return when  # Skip datetime coercion for existing datetime.

        if when is None:
            logging.debug(cls.LOG_ISSUE_FMT, 'SKIPPED', cls.kind(),
                utils.get_ns_name_for_logging(),
                {DateTimeTrigger.FIELD_NAME: when},
                cls.UNSPECIFIED_FMT.format(cls.WHEN_TYPENAME))
            return when  # Skip datetime coercion for None.

        try:
            return utc.text_to_datetime(when)
        except (ValueError, TypeError) as err:
            logging.warning(cls.LOG_ISSUE_FMT, 'INVALID', cls.WHEN_TYPENAME,
                utils.get_ns_name_for_logging(),
                {DateTimeTrigger.FIELD_NAME: when}, repr(err))
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
    def validation_failed(cls, valid_or_not):
        return valid_or_not.invalid or valid_or_not.missing

    @classmethod
    def validate_property(cls, prop_name, validator, encoded, valid_or_not):
        """Updates ValidOrNot in-place for a specified property.

        Args:
            prop_name: name string of the property of interest.
            validator: function that accepts single encoded value and returns
                either the valid decoded value or None.
            encoded: a dict of property names to their encoded values.
            valid_or_not: updated in-place ValidOrNot namedtuple containing:
                valid, dict of valid property names and decoded values
                invalid, dict of invalid property names and bad encoded values
                missing, set of names of expected but missing properties
                unused, dict of encoded property names and values not in any
                    of `valid`, `invalid`, or `missing`.
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

    VALIDATES = [FIELD_NAME]

    @classmethod
    def validate(cls, encoded, fail_fast=None):
        """Extracts, validates, and decodes properties from an encoded dict.

        Args:
            encoded: a dict of property names to their encoded values.
            fail_fast: if True, stop validating at the first validation failure.

        Returns:
          A ValidOrNot namedtuple updated by one or more calls to
          validate_property().
        """
        valid_or_not = cls.ValidOrNot({}, {}, set(), encoded.copy())
        cls.validate_property(DateTimeTrigger.FIELD_NAME,
            cls.validate_when, encoded, valid_or_not)
        return valid_or_not

    DEFAULT_FAIL_FAST = True

    @classmethod
    def abort_validation(cls, fail_fast, valid_or_not):
        if fail_fast:
            return cls.validation_failed(valid_or_not)

        if (fail_fast is None) and cls.DEFAULT_FAIL_FAST:
            return cls.validation_failed(valid_or_not)

        return False

    @classmethod
    def decode(cls, encoded, **kwargs):
        """Decodes form payload (or stored settings) into a trigger."""
        # Ctor will complain about any missing properties not present in
        # encoded or kwargs overrides.
        valid_or_not = cls.validate(encoded)
        ctor_kwargs = valid_or_not.valid
        for k, v in kwargs.iteritems():
            if v is not None:
                ctor_kwargs[k] = v  # Apply explicit override from kwargs.
        return cls(**ctor_kwargs)

    @property
    def decoded(self):
        """Returns the DateTimeTrigger as a dict of *decoded* properties."""
        present = {}
        if self.when is not None:
            present[DateTimeTrigger.FIELD_NAME] = self.when
        return present

    @classmethod
    def encode(cls, when=None, **unused):
        """Returns encoded dict containing only encode-able properties."""
        encoded = {}
        encoded_when = cls.encode_when(when)
        if encoded_when:
            encoded[DateTimeTrigger.FIELD_NAME] = encoded_when
        return encoded

    @property
    def encoded(self):
        """Encodes DateTimeTrigger as form payload (or stored settings)."""
        return self.encode(**self.decoded)

    @property
    def is_valid(self):
        """Returns True if DateTimeTrigger properties are currently valid."""
        # self._when is set in exactly one place, in __init__(), and is set
        # only to the return value of validate_when(), which is either None
        # or a datetime object.
        return self.when is not None

    @classmethod
    def now(cls, now=None):
        """Returns `now` as datetime or UTC "now" if None."""
        return cls.validate_when(now) or utc.now_as_datetime()

    def is_future(self, now=None):
        """Returns True if `when` is valid and in the future from `now`."""
        # Explicitly check *only* if valid `when` is present for comparison,
        # rather than checking the (potentially sub-class) is_valid property.
        return (self.when is not None) and (self.now(now=now) < self.when)

    def is_ready(self, now=None):
        """Returns True if valid, current (not future), and can be applied."""
        return self.is_valid and (self.now(now=now) >= self.when)

    @classmethod
    def is_complete(cls, encoded_trigger):
        """True if encoded_trigger contains values for all expected FIELDS."""
        for field in cls.FIELDS:
            if not encoded_trigger.get(field):
                return False
        return True

    @classmethod
    def encoded_defaults(cls, when=None):
        """Creates an encoded trigger initialized to any possible defaults.

        Args:
            when: (optional) Typically, there is no  meaningful default
                value for the date/time of a trigger, though some subclasses
                may supply one (e.g. the value of 'course:start_date' for
                the 'when' default of a 'course_end' MilestoneTrigger).

        Returns:
            Returns an encoded trigger initialized with any explicitly
            supplied keyword argument defaults or class defaults, or None if
            it was not possible to encode a default trigger of the class type.
        """
        defaults = {}

        # Ignore *all* False values, not just None.
        if when:
            defaults[DateTimeTrigger.FIELD_NAME] = when

        return defaults

    @classmethod
    def is_defaults(cls, encoded_trigger, defaults=None):
        """True if encoded_trigger contains only encoded_defaults() values.

        Args:
            encoded_trigger: an encoded (e.g. form payload or marshaled
                for storing into settings) trigger dict.
            defaults: (optional) a dict containing the defaults for an
                encoded trigger. Some subclasses (e.g. MilestoneTrigger)
                need to create a defaults dict that in some way depends on
                the encoded_trigger being tested. encoded_defaults() works
                for non-exceptional trigger subclasses.
        """
        if defaults is None:
            defaults = cls.encoded_defaults()

        # There may not be defaults for some otherwise valid encoded trigger
        # fields, so only compare the fields present in the defaults dict,
        # ignoring any additional fields present in encoded_trigger.
        for field, value in defaults.iteritems():
            if encoded_trigger.get(field) != value:
                return False
        return True

    @classmethod
    def triggers_in(cls, settings):
        """Retrieves (or creates empty) triggers list in supplied settings."""
        return settings.setdefault(cls.SETTINGS_NAME, [])

    @classmethod
    def in_settings(cls, settings):
        """Actual encoded availability triggers in course and/or settings.

        Args:
            settings: subclass-specific settings (which may be altered
                *in place*, see the triggers_in() method, called by this
                one), containing the encoded triggers.

        Returns:
            The *mutable* list of the encoded triggers (dicts with JSON
            encode-able values) actually in the supplied settings (including
            possibly a newly-created empty list into which triggers can be
            inserted).
        """
        return cls.triggers_in(courses.Course.publish_in_environ(settings))

    @classmethod
    def copy_triggers_from(cls, settings):
        """Like triggers_in(), but return a copy and no creation if missing."""
        return ([]
                if ((not settings) or (cls.SETTINGS_NAME not in settings))
                else list(settings[cls.SETTINGS_NAME]))

    @classmethod
    def copy_from_settings(cls, settings):
        """Copies encoded availability triggers from course and/or settings.

        Args:
            settings: subclass-specific settings containing the encoded
                triggers, simply copied from and thus not altered by this
                method.

        Returns:
            A *shallow copy* of the list of encoded triggers (dicts with JSON
            encode-able values) present in the supplied settings, or an
            empty list if settings is None or the SETTINGS_NAME values were
            not present.
        """
        return ([] if settings is None
                else cls.copy_triggers_from(
                    courses.Course.get_publish_from_environ(settings)))

    @classmethod
    def for_form(cls, settings, **kwargs):
        """Returns encoded availability triggers from settings as form values.

        Args:
            settings: passed, untouched, through to copy_from_settings(),
                and thus works with all types of settings, e.g. a Course
                get_environ() dict, or StudentGroupDTO for student_groups
                trigger subclasses.
            kwargs: subclass-specific keyword arguments.

        Returns:
          The base class implementation simply returns a dict containing a
          single key/value pair, with SETTINGS_NAME as the key and the
          unaltered results of copy_from_settings() as the value.
        """
        return {
            cls.SETTINGS_NAME: cls.copy_from_settings(settings),
        }

    @classmethod
    def check_set_semantics(cls, semantics):
        if semantics is None:
            return cls.SET_WILL_OVERWRITE

        if semantics in cls.IMPLEMENTED_SET_SEMANTICS:
            return semantics

        raise ValueError(
            'set_into_settings() semantics "{}" must be one of: {}'.format(
                semantics, cls.IMPLEMENTED_SET_SEMANTICS))

    @classmethod
    def set_into_settings(cls, encoded_triggers, settings,
                          semantics=None, **kwargs):
        """Sets encoded availability triggers into the supplied settings.

        If a non-empty encoded_triggers list was supplied, it is set as the
        value of the SETTINGS_NAME key in a dict or property in a DTO.

        Args:
            encoded_triggers: a list of encoded triggers, marshaled for
                storing as settings values.
            settings: subclass-specific settings, updated *in place* by this
                method with new encoded_triggers.
            semantics: one of the IMPLEMENTED_SET_SEMANTICS, defaulting to
                the SET_WILL_OVERWRITE semantics (supported by all triggers)
                if None.
              SET_WILL_OVERWRITE -- When called from the per-course
                  availability settings page, this parameter specifies that
                  overwrite semantics are applied. In this settings page
                  case, all settings are present on that form, and so any
                  existing SETTINGS_NAME values are completely overwritten
                  (by encoded_triggers, when they are provided) or deleted
                  (when encoded_triggers is empty or None).
              SET_WILL_MERGE -- See subclass set_into_settings() methods for
                  discussion of how merge semantics are implemented by that
                  subclass.
            kwargs: subclass-specific keyword arguments passed through to
                clear_from_settings() if it is called.
        """
        # ValueError is raised if an unsupported set semantics value was
        # supplied (but otherwise this base class implementation ignores the
        # actual parameter value, as most triggers classes only implement the
        # default 'overwrite' semantics).
        cls.check_set_semantics(semantics)
        if encoded_triggers:
            publish = courses.Course.publish_in_environ(settings)
            publish[cls.SETTINGS_NAME] = encoded_triggers
        else:
            cls.clear_from_settings(settings, **kwargs)

    @classmethod
    def clear_from_settings(cls, settings, **kwargs):
        """Removes class triggers from the supplied settings.

        The default behavior of this method is to remove the all of the
        subclass triggers (the SETTINGS_NAME list) from the 'publish' part
        of the supplied course settings.

        Args:
            settings: subclass-specific settings, updated *in place* by this
                method removing existing encoded triggers.
            kwargs: subclass-specific keyword arguments.
        """
        publish = courses.Course.publish_in_environ(settings)
        publish.pop(cls.SETTINGS_NAME, None)  # No KeyError if missing.

    @classmethod
    def from_payload(cls, payload):
        """Gets just encoded triggers from the availability form payload."""
        return cls.copy_triggers_from(payload)

    @classmethod
    def payload_into_settings(cls, payload, course, settings, semantics=None):
        """Sets triggers from form payload in settings for a course.

        Args:
            payload: POST form payload dict
            course: a Course passed through to set_into_settings(), used by
                some trigger subclasses.
            settings: subclass-specific settings, updated *in place* by this
                method with new encoded_triggers, via set_into_settings().
            semantics: (optional) see set_into_settings().
        """
        cls.set_into_settings(cls.from_payload(payload), settings,
                              semantics=semantics, course=course)

    @classmethod
    def sort(cls, triggers):
        """In-place sorts a list of DateTimeTriggers, by increasing `when`."""
        triggers.sort(key=lambda t: t.when)
        # As a convenience, also return the original sorted in-place list.
        return triggers

    Separated = collections.namedtuple('Separated',
        ['encoded', 'decoded', 'future', 'ready', 'invalid', 'all'])

    @classmethod
    def separate(cls, encoded_triggers, course, now=None):
        """Separates encoded triggers into various Separated categories.

        Unless otherwise noted, all values in the various Separated lists
        appear in the same order that they occurred in the original supplied
        encoded_triggers list.

        "Decoded" triggers are objects of some DateTimeTrigger subclass.

        "Encoded" triggers result from JSON-decoding by transforms.loads().

        Args:
            encoded_triggers: a list of encoded (e.g. form payload or marshaled
                for storing into settings) triggers.
            course: Course used by some triggers for additional decoding,
                initialization, and validation.
            now: (optional) UTC time as a datetime, used to decide if a trigger
                is ready to be acted on; default is None, indicating that
                `ready` and `future` separating can be skipped.

        Returns:
            A Separated namedtuple where:
            `encoded` is a list of *all* valid triggers, in encoded form.
            `decoded` is a list of *all* valid triggers, in decoded form.
            `future` is a list of valid, future triggers, in encoded form.
            `ready` is a list of valid triggers, in decoded form, ready
                (is_ready(now) is True) to be applied. These triggers appear
                in the `ready` list in "order of application", sorted by
                increasing `when` datetime.
            `invalid` is a list of  invalid triggers, in encoded form.
            `all` is encoded_triggers in its original form.
        """
        if not encoded_triggers:
            # Nothing to do, so don't waste time logging, etc.
            return cls.Separated([], [], [], [], [], encoded_triggers)

        logged_ns = utils.get_ns_name_for_logging(course=course)
        logging.debug(
            'SEPARATING %d encoded %s(s) in %s.', len(encoded_triggers),
            cls.typename(), logged_ns)

        encoded = []
        decoded = []
        future = []
        ready = []
        invalid = []

        # Either (possibly coerced to) a datetime, or (perhaps already) None.
        now = cls.validate_when(now)

        for et in encoded_triggers:
            if et is None:
                logging.warning(cls.LOG_ISSUE_FMT, 'MISSING', cls.typename(),
                    logged_ns, et, cls.MISSING_TRIGGER_FMT.format(None))
                # Nothing at all to do, and do not keep the None values.
                continue

            # decode() will log any detailed validation error messages.
            dt = cls.decode(et, course=course)
            if not dt:
                invalid.append(et)
                continue
            is_valid = dt.is_valid
            if not is_valid:
                invalid.append(et)
                continue

            # Keep both encoded and decoded forms of the known-valid trigger.
            encoded.append(et)
            decoded.append(dt)

            if now is None:
                # `now` datetime not specified, so skip `future` vs. `ready`.
                continue

            is_future = dt.is_future(now=now)
            if is_future:
                # Valid, but future, trigger, so leave encoded for later.
                future.append(et)
                continue

            is_ready = dt.is_ready(now=now)
            if is_ready:
                # Valid trigger whose time has passed, ready to to call act().
                ready.append(dt)
                continue

            logging.warning(cls.LOG_ISSUE_FMT, 'IMPOSSIBLE', cls.typename(),
                logged_ns, et, cls.IMPOSSIBLE_TRIGGER_FMT.format(
                    bool(is_valid), is_future, is_ready))

        cls.sort(ready)
        return cls.Separated(
            encoded, decoded, future, ready, invalid, encoded_triggers)

    ChangedByAct = collections.namedtuple('ChangedByAct',
        ['previous', 'next'])

    def act(self, course, settings):
        """Perform whatever action is associated with the trigger.

        The base class (DateTimeTrigger) implementation of act() is a no-op.
        It simply logs that it was called and returns None. This is all that
        can be reasponably expected, given that it has no specific details
        about what to do or update (unlike more-specific subclasses).

        Args:
            course: a Course that can be used or altered by subclass act()
                methods.
            settings: subclass-specific settings that can be used or altered
                by subclass act() methods (e.g. a Course get_environ() dict,
                or StudentGroupDTO for student_groups trigger subclasses).

        Returns:
            A ChangedByAct namedtuple is returned if acting on the trigger
            caused some state change that might require course or settings to
            be saved.

            None is returned if acting on the trigger produced no actual
            change of any course or settings state.
        """
        logging.warning('UNIMPLEMENTED %s.act(%s, %s): %s',
            self.typename(), utils.get_ns_name_for_logging(course=course),
            settings, self.logged)
        return None

    Acted = collections.namedtuple('Acted', ['trigger', 'changed'])

    TriggeredActs = collections.namedtuple('TriggeredActs',
        ['acted', 'ignored'])

    @classmethod
    def act_on_triggers(cls, decoded_triggers, course, settings):
        """Takes actions for a list of decoded triggers (calls act() for each).

        Calls act() to take action on each trigger in the supplied list of
        "ready" triggers, in order. All of the triggers should be valid and
        should already be sorted in the order of application, such as by
        increasing values of `when`. The `ready` list in the Separated
        namedtuple returned by separate() satisfies these preconditions.

        "Valid" means the trigger is not malformed. "Ready" means `when`
        specifies a date and time that is now in the past.

        Sorting is required so that, in the case of multiple valid, ready
        triggers associated with the action, the most significant trigger
        (typicaly the chronologically last one) is the one whose taken
        action persists.

        Once applied, a trigger is considered consumed and should not be
        added back to the future triggers stored in settings.

        Args:
            decoded_triggers: a list of objects of some DateTimeTrigger
                subclass, assumed to all be valid and to have been sorted in
                order of application.
            course: a Course that can be used or altered by subclass act()
                methods.
            settings: subclass-specific settings that can be read or even
                altered by subclass act() methods.

        Returns:
            An TriggeredActs namedtuple containing:
            acted, a list Acted namedtuples, each containing a decoded
                trigger whose act() method indicated that an action was taken
                that modified the course or settings and the ChangedByAct
                value indicating what was modified by that act().
            ignored, a list of decoded triggers whose act() methods indicate
                that no modification to the course or settings occurred.
        """
        acted = []
        ignored = []

        if not decoded_triggers:
            # Nothing to do, so don't waste time logging, etc.
            return cls.TriggeredActs(acted, ignored)

        logged_ns = utils.get_ns_name_for_logging(course=course)

        for dt in decoded_triggers:
            changed = dt.act(course, settings)
            if changed:
                acted.append(cls.Acted(dt, changed))
                logging.info('TRIGGERED %s %s from "%s" to "%s": %s',
                             logged_ns, dt.kind(), changed.previous,
                             changed.next, dt.logged)
            else:
                ignored.append(dt)
                logging.debug('UNCHANGED %s %s: %s',
                              logged_ns, dt.kind(), dt.logged)

        if acted:
            logging.debug('ACTED on %d %s %s(s).',
                          len(acted), logged_ns, cls.typename())

        if ignored:
            logging.debug('IGNORED %d %s %s(s).',
                          len(ignored), logged_ns, cls.typename())

        return cls.TriggeredActs(acted, ignored)

    SettingsActs = collections.namedtuple('SettingsActs',
        ['num_consumed', 'separated', 'num_changed', 'triggered_acts'])

    @classmethod
    def act_on_settings(cls, course, settings, now):
        """Acts on triggers from settings and keeps future triggers.

        Triggers are retrieved from settings and then separated into ready,
        invalid, and future triggers lists. The "ready" triggers are acted
        on (their act() methods are called), and any future triggers are
        set_into_settings() to retain them for future separating and acting.

        Args:
            course: a Course, passed to copy_from_settings() to obtain
                triggers, that may also be used or altered by subclass
                act() methods.
            settings: subclass-specific settings, passed to
                copy_from_settings() to obtain any encoded triggers, then
                read or even potentially altered by subclass act() methods,
                and finally updated *in place* by set_into_settings().
            now: current UTC time as a datetime, used to decide if a valid
                trigger is ready to be acted on.

        Returns:
            An SettingsActs namedtuple containing:
            num_changed, which is positive if any triggers retrieved
                from settings were either invalid and discarded or ready and
                acted on.
            separated, the Separated namedtuple resulting from separate()
                applied to the triggers retrieved from settings.
            triggered_acts, the TriggeredActs namedtuple resulting from
                act_on_triggers() applied to the "ready" triggers.
        """
        # Extract all cls type triggers from supplied settings.
        encoded_triggers = cls.copy_from_settings(settings)

        # Separate triggers into "ready to apply" and future triggers.
        separated = cls.separate(encoded_triggers, course, now=now)

        future_encoded = separated.future
        ready_decoded = separated.ready

        # Were any of the triggers from settings['publish'] consumed ("ready"
        # and applied) or discarded (invalid)?
        num_consumed = len(encoded_triggers) - len(future_encoded)

        # Apply availability changes for any valid, "ready to apply" triggers.
        acts = cls.act_on_triggers(ready_decoded, course, settings)
        num_changed = len(acts.acted)

        if num_consumed:
            # Update the triggers stored in the settings with the remaining
            # future triggers.  (These settings are not yet saved, as that is
            # the responsibility of the caller.)
            cls.set_into_settings(
                future_encoded, settings, course=course, triggers_only=True)

        return cls.SettingsActs(num_consumed, separated, num_changed, acts)

    @classmethod
    def log_acted_on(cls, logged_ns, settings_acts,
                     course_saved, settings_saved):
        num_invalid = len(settings_acts.separated.invalid)
        if num_invalid:
            logging.warning('DISCARDED %d invalid %s(s) in %s.',
                            num_invalid, cls.typename(), logged_ns)

        num_consumed = settings_acts.num_consumed
        num_remaining = len(settings_acts.separated.future)
        if num_consumed:
            if settings_saved:
                logging.debug('KEPT %d future %s(s) in %s.',
                    num_remaining, cls.typename(), logged_ns)
            else:
                logging.warning('FAILED to keep %d future %s(s) in %s.',
                    num_remaining, cls.typename(), logged_ns)
        elif num_remaining:
            logging.debug('AWAITING %d future %s(s) in %s.',
                num_remaining, cls.typename(), logged_ns)

        num_changed = settings_acts.num_changed
        if num_changed:
            if course_saved:
                logging.debug('SAVED %d change(s) to %s %s.',
                    num_changed, logged_ns, cls.kind())
            else:
                logging.warning('FAILED to save %d change(s) to %s %s.',
                    num_changed, logged_ns, cls.kind())
        else:
            logging.debug('UNTOUCHED %s %s.', logged_ns, cls.kind())

    @classmethod
    def typename(cls):
        """Returns a 'module.ClassName' string used in logging."""
        return _qualified_typename(cls)

    @property
    def logged(self):
        """Returns a verbose string of the trigger intended for logging."""
        return '{}({})'.format(self.__class__.typename(), self.name_as_items)


class AvailabilityTrigger(DateTimeTrigger):
    """Availability change to be applied at the specified date/time.

    AvailabilityTrigger is very much an abstract base class, as many of its
    methods rely on a class-scoped AVAILABILITY_VALUES collection that is only
    defined by concrete subclasses (e.g. ContentTrigger, MilestoneTrigger).

    AvailabilityTrigger also does not define SETTINGS_NAME.
    """

    FIELD_NAME = 'availability'
    FIELDS = DateTimeTrigger.FIELDS + [FIELD_NAME]

    UNEXPECTED_AVAIL_FMT = "Availability '{}' not in {}."

    def __init__(self, availability=None, **super_kwargs):
        """Validates and sets `availability` and super class properties."""
        super(AvailabilityTrigger, self).__init__(**super_kwargs)
        # `availability` is either one of cls.AVAILABILITY_VALUES or None.
        self._availability = self.validate_availability(availability)

    @property
    def name(self):
        """Returns a "name" string that can be compared, sorted, etc."""
        return '{}{}{}'.format(super(AvailabilityTrigger, self).name,
            self.NAME_PART_SEP, self.encoded_availability)

    @classmethod
    def kind(cls):
        """Forms, e.g., 'content availability' from 'content_triggers.'"""
        return (cls.typename().split('.')[-1]
                if not hasattr(cls, 'SETTINGS_NAME')
                else super(AvailabilityTrigger, cls).kind() + ' availability')

    SELECT_CSS = 'gcb-select inputEx-Field'

    @classmethod
    def availability_css(cls, extra_css=None):
        """Returns 'className' value for an 'availability' SchemaField."""
        extra_css = [] if not extra_css else [extra_css]
        classes = [AvailabilityTrigger.FIELD_NAME, cls.SELECT_CSS] + extra_css
        return ' '.join(classes)

    @property
    def availability(self):
        """Returns a subclass-specific AVAILABILITY_VALUES string or None."""
        return self._availability

    # ('none', '--- change availability to ---') is the default form <option>
    # in the course-wide start/end availability <select> fields.
    NONE_SELECTED = availability_options.AVAILABILITY_NONE_SELECTED

    @classmethod
    def validate_availability(cls, availability):
        """Returns availability if in AVAILABILITY_VALUES, otherwise None."""
        if availability in cls.AVAILABILITY_VALUES:
            return availability

        if (not availability) or (availability == cls.NONE_SELECTED):
            logging.debug(cls.LOG_ISSUE_FMT, 'SKIPPED', cls.kind(),
                utils.get_ns_name_for_logging(),
                {AvailabilityTrigger.FIELD_NAME: availability},
                'No availability selected.')
        else:
            logging.warning(cls.LOG_ISSUE_FMT, 'INVALID', cls.kind(),
                utils.get_ns_name_for_logging(),
                {AvailabilityTrigger.FIELD_NAME: availability},
                cls.UNEXPECTED_AVAIL_FMT.format(
                    availability, cls.AVAILABILITY_VALUES))

        return None

    @classmethod
    def encode_availability(cls, availability):
        """Returns validated availability (encode and decode are identical)."""
        return cls.validate_availability(availability)

    @property
    def encoded_availability(self):
        return self.encode_availability(self.availability)

    VALIDATES = [FIELD_NAME]

    @classmethod
    def validate(cls, encoded, fail_fast=None):
        valid_or_not = super(AvailabilityTrigger, cls).validate(
            encoded, fail_fast=fail_fast)
        if cls.abort_validation(fail_fast, valid_or_not):
            return valid_or_not
        cls.validate_property(AvailabilityTrigger.FIELD_NAME,
            cls.validate_availability, encoded, valid_or_not)
        return valid_or_not

    @property
    def decoded(self):
        """Returns the AvailabilityTrigger as dict of *decoded* properties."""
        present = super(AvailabilityTrigger, self).decoded
        if self.availability is not None:
            present[AvailabilityTrigger.FIELD_NAME] = self.availability
        return present

    @classmethod
    def encode(cls, availability=None, **super_kwargs):
        """Returns encoded dict containing only encode-able properties."""
        encoded = super(AvailabilityTrigger, cls).encode(**super_kwargs)
        encoded_availability = cls.encode_availability(availability)
        if encoded_availability:
            encoded[AvailabilityTrigger.FIELD_NAME] = encoded_availability
        return encoded

    @property
    def is_valid(self):
        """Returns True if the Trigger properties are *all* currently valid."""
        # self._availability is set in exactly one place, in __init__(), and
        # is set only to the return value of validate_availability(), which
        # is either None or one of the cls.AVAILABILITY_VALUES.
        return self.availability and super(AvailabilityTrigger, self).is_valid

    @classmethod
    def encoded_defaults(cls, availability=None, **super_kwargs):
        """Returns an encoded trigger initialized to any possible defaults.

        The availability value (either the explicitly supplied keyword
        parameter or the class DEFAULT_AVAILABILITY) is *not* validated.
        This allows for form default values like AVAILABILITY_NONE_SELECTED
        that must be supplied *to* a form via an entity, but must not be stored
        *from* that form if still "change availability to".

        Args:
            availability: an optional explicitly specified availability value;
                default is to use cls.DEFAULT_AVAILABILITY
            super_kwargs: keyword arguments passed on to base class
        """
        defaults = super(AvailabilityTrigger, cls).encoded_defaults(
            **super_kwargs)
        if availability is None:
            availability = cls.DEFAULT_AVAILABILITY

        defaults[AvailabilityTrigger.FIELD_NAME] = availability
        return defaults


class ContentTrigger(AvailabilityTrigger):
    """A course content availability change applied at specified date/time.

    Modules can register to be called back when a content date/time trigger is
    "acted-on", that is, the act() method of a ContentTrigger has been
    invoked (this happens when a valid trigger is now in the past and thus
    "triggered"). Callbacks are registered like this:

        triggers.ContentTrigger.ACT_HOOKS['my_module'] = my_handler

    Trigger callbacks are called a single time for a given acted-on trigger,
    since the act() method for a given trigger is called only once, and then
    that "expended" trigger is, by definition, discarded. The callbacks are
    called in no particular order, via common.utils.run_hooks().

    Acted-on trigger callbacks must accept these paramters:
      trigger - the specific ContentTrigger instance invoking the callbacks.
      changed - a ChangedByAct namedtuple containing 'previous' and 'next'
        content availability changed by act(), or None if no change.
      course - the Course that has been potentially altered by the act()
        method prior to any callbacks being called.
      env - the Course get_environ() dict containing settings changes made by
        the act() method that *have not yet been saved* to the Course.
        Changes to this env dict by the callback *will* affect what is
        eventually saved back into the Course environment and settings.
    """

    ACT_HOOKS = {}

    FIELD_NAME = 'content'
    FIELDS = AvailabilityTrigger.FIELDS + [FIELD_NAME]

    SETTINGS_NAME = 'content_triggers'

    AVAILABILITY_VALUES = availability_options.ELEMENT_VALUES
    DEFAULT_AVAILABILITY = availability_options.ELEMENT_DEFAULT

    # On the Publish > Availability form (in the element_settings course
    # outline and the <option> values in the content_triggers 'content'
    # <select>), there are only two content types: 'unit', and 'lesson'.
    # All types other than 'lesson' (e.g. 'unit', 'link', 'assessment') are
    # represented by 'unit' instead.
    CONTENT_TYPE_FINDERS = {
        resources_display.ResourceUnit.TYPE:
            lambda course, id: course.find_unit_by_id(id),
        resources_display.ResourceLesson.TYPE:
            lambda course, id: course.find_lesson_by_id(None, id),
    }

    ALLOWED_CONTENT_TYPES = CONTENT_TYPE_FINDERS.keys()

    UNEXPECTED_CONTENT_FMT = 'Content type "{}" not in {}.'
    MISSING_CONTENT_FMT = 'No content matches resource Key "{}".'

    KEY_TYPENAME = _qualified_typename(resource.Key)

    def __init__(self, content=None, content_type=None, content_id=None,
                 found=None, course=None, **super_kwargs):
        """Validates the content type and id and then initializes `content`."""
        super(ContentTrigger, self).__init__(**super_kwargs)

        # `content` is always either a resource.Key or None.
        self._content = self.validate_content(content=content,
            content_type=content_type, content_id=content_id)

        if (not found) and course and self.content:
            found = self.find_content_in_course(self.content, course)
        # else:
        # TODO(tlarsen): Confirm that caller-supplied `found` parameter is
        #   actually an acceptable Unit, Lesson, etc., object.

        # `found` is expected to be either a Unit, a Lesson, or None, though
        # a caller of __init__() could (erroneously?) supply something else.
        self._found = found

    @property
    def name(self):
        return '{}{}{}'.format(super(ContentTrigger, self).name,
            self.NAME_PART_SEP, self.encoded_content)

    DATETIME_CSS = 'inputEx-required ' + AvailabilityTrigger.DATETIME_CSS

    @classmethod
    def content_css(cls, extra_css=None):
        """Returns 'className' value for a 'content' SchemaField."""
        extra_css = [] if not extra_css else [extra_css]
        classes = [ContentTrigger.FIELD_NAME, cls.SELECT_CSS] + extra_css
        return ' '.join(classes)

    @property
    def content(self):
        return self._content

    @classmethod
    def validate_content_type(cls, content_type):
        """Returns content_type if in ALLOWED_CONTENT_TYPES, otherwise None."""
        if content_type in cls.ALLOWED_CONTENT_TYPES:
            return content_type

        logging.warning(cls.LOG_ISSUE_FMT, 'INVALID', cls.KEY_TYPENAME,
            utils.get_ns_name_for_logging(), {'content_type': content_type},
            cls.UNEXPECTED_CONTENT_FMT.format(
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
            logging.warning(cls.LOG_ISSUE_FMT, 'INVALID', cls.KEY_TYPENAME,
                utils.get_ns_name_for_logging(), encoded, repr(err))
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
        logged_ns = utils.get_ns_name_for_logging()

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
                logging.warning(cls.LOG_ISSUE_FMT, 'INVALID', cls.KEY_TYPENAME,
                    logged_ns, {ContentTrigger.FIELD_NAME: str(content)},
                    repr(err))
                return None
        # else:
        # `content` is already a resource.Key (such as when the ContentTrigger
        # class itself calls encode_content()), just skip straight to the
        # validate_content_type() check.

        if cls.validate_content_type(content.type):
            return content

        # `content` is now a valid resource.Key, but resource.Key.type is not
        # one of the ALLOWED_CONTENT_TYPES.
        logging.warning(cls.LOG_ISSUE_FMT, 'INVALID', cls.KEY_TYPENAME,
            logged_ns, {ContentTrigger.FIELD_NAME: str(content)},
            cls.UNEXPECTED_CONTENT_FMT.format(
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

    VALIDATES = [FIELD_NAME, 'content_type', 'content_id']

    @classmethod
    def validate(cls, encoded, fail_fast=None):
        valid_or_not = super(ContentTrigger, cls).validate(
            encoded, fail_fast=fail_fast)
        if cls.abort_validation(fail_fast, valid_or_not):
            return valid_or_not

        validate_content_kwargs = dict(
            [(k, encoded[k]) for k in cls.VALIDATES if k in encoded])
        valid_content = cls.validate_content(**validate_content_kwargs)

        if valid_content:
            valid_or_not.valid[ContentTrigger.FIELD_NAME] = valid_content
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
        if self.content is not None:
            present[ContentTrigger.FIELD_NAME] = self.content
        return present

    @classmethod
    def encode(cls, content=None, content_type=None, content_id=None,
               **super_kwargs):
        encoded = super(ContentTrigger, cls).encode(**super_kwargs)
        valid_content = cls.validate_content(content=content,
            content_type=content_type, content_id=content_id)
        encoded_content = cls.encode_content(content=valid_content)
        if encoded_content:
            encoded[ContentTrigger.FIELD_NAME] = encoded_content
        return encoded

    @property
    def found(self):
        """Returns the Unit, Lesson, etc., if one was found, or None."""
        return self._found

    @property
    def type(self):
        """Returns associated course content type if one exists, or None."""
        return None if self.content is None else self.content.type

    @property
    def id(self):
        """Returns an associated course content ID if one exists, or None."""
        return None if self.content is None else str(self.content.key)

    @property
    def is_valid(self):
        """Returns True if id, type, found, when, etc. are *all* valid."""
        # self._content is set in exactly one place, in __init__(), and
        # is set only to the return value of validate_content(), which is
        # either None or a valid content resource.Key.
        # self._found is similarly only set in __init__(), and *should* be
        # only either None or a valid Unit or Lesson, but (currently) the
        # __init__() caller *could* provide an invalid value of some sort.
        return ((self.content is not None) and (self.found is not None) and
                super(ContentTrigger, self).is_valid)

    @classmethod
    def for_form(cls, settings, selectable_content=None):
        """Returns encoded availability triggers from settings as form values.

        Args:
            settings: passed, untouched, through to the base class.
            selectable_content:  a collection (typically a select_data dict)
                containing the encoded 'content' resource.Key strings of
                existing Course units, lessons, etc.

        Returns:
          A list of the ContentTriggers from the encoded copy_from_settings()
          triggers whose associated 'content' exists (that is, the encoded
          key of the unit, lessong, et.c, was found in selectable_content).
        """
        form_fields = super(ContentTrigger, cls).for_form(settings)

        if not selectable_content:
            # Without knowledge of valid content, there is no way to discard
            # obsolete triggers, so just bail out by returning everything.
            return form_fields

        return dict([(field,
                      cls.has_content(encoded_triggers, selectable_content))
                     for field, encoded_triggers in form_fields.iteritems()])

    @classmethod
    def get_content_finder(cls, content):
        logged_ns = utils.get_ns_name_for_logging()
        if not content:
            logging.warning(cls.LOG_ISSUE_FMT, 'UNSPECIFIED', cls.KEY_TYPENAME,
                logged_ns, {ContentTrigger.FIELD_NAME: content},
                '"{}" has no content finder function.'.format(content))
            return None

        find_func = cls.CONTENT_TYPE_FINDERS.get(content.type)
        if find_func:
            return find_func

        logging.warning(cls.LOG_ISSUE_FMT, 'UNEXPECTED', cls.KEY_TYPENAME,
            logged_ns, {ContentTrigger.FIELD_NAME: str(content)},
            cls.UNEXPECTED_CONTENT_FMT.format(
                content.type, cls.ALLOWED_CONTENT_TYPES))
        return None

    @classmethod
    def find_content_in_course(cls, content, course, find_func=None):
        logged_ns = utils.get_ns_name_for_logging(course=course)
        if not course:
            logging.warning(cls.LOG_ISSUE_FMT, 'ABSENT', 'course',
                logged_ns, {ContentTrigger.FIELD_NAME: str(content)},
                'CANNOT find content in "{}" course.'.format(course))
            return None

        if not find_func:
            find_func = cls.get_content_finder(content)

        if not find_func:
            return None  # get_content_finder() already logged the issue.

        found = find_func(course, content.key)
        if found:
            return found

        logging.warning(cls.LOG_ISSUE_FMT, 'OBSOLETE', cls.KEY_TYPENAME,
            logged_ns, {ContentTrigger.FIELD_NAME: str(content)},
            cls.MISSING_CONTENT_FMT.format(content))
        return None

    @classmethod
    def has_content(cls, encoded_triggers, selectable_content):
        """Removes obsolete content triggers from a list of triggers.

        Args:
            encoded_triggers: a list of encoded (e.g. form payload or marshaled
                for storing into settings) triggers.
            selectable_content: a dict of <select> <option> option/text pairs;
                the option dict keys are treated as a set of the valid
                course content resource.Keys, in encoded string form.

        Returns:
            A list of the remaining content triggers (encoded in form payload
            and stored settings form) whose associated content still exist.
        """
        logged_ns = utils.get_ns_name_for_logging()

        # Course content associated with existing availability triggers could
        # have been deleted since the trigger itself was created. If the
        # content whose availability was meant to be updated by the trigger
        # has been deleted, also discard the obsolete trigger and do not
        # display it in the Publish > Availability form. (It displays
        # incorrectly anyway, using the first <option> since the trigger
        # content key value is non longer present in the <select>.
        #
        # Saving the resulting form will then omit the obsolete triggers.
        # The UpdateAvailability cron job also detects these obsolete triggers
        # and discards them as well.
        triggers_with_content = []
        for encoded in encoded_triggers:
            encoded_content = encoded.get(ContentTrigger.FIELD_NAME)
            if encoded_content in selectable_content:
                triggers_with_content.append(encoded)
            else:
                logging.warning(cls.LOG_ISSUE_FMT, 'OBSOLETE',
                    cls.KEY_TYPENAME, logged_ns, encoded,
                    cls.MISSING_CONTENT_FMT.format(encoded_content))

        return triggers_with_content

    def act(self, course, settings):
        """Updates course content availability as indicated by the trigger.

        The supplied parameters are not directly used, but any alteration to
        self.found will not be persistent until the caller (eventually) calls
        save() for the Course of which self.found is a content element.

        Args:
            course: a Course passed through, unaltered, to ACT_HOOKS callbacks.
            settings: a Course get_environ() dict passed through, unaltered, to
                ACT_HOOKS callbacks.
        """
        current = self.found.availability
        new = self.availability

        if current != new:
            self.found.availability = new
            changed = self.ChangedByAct(current, new)
            logging.info('APPLIED %s from "%s" to "%s" for %s in %s: %s',
                self.kind(), current, new, self.encoded_content,
                utils.get_ns_name_for_logging(course=course), self.logged)
        else:
            changed = None

        utils.run_hooks(self.ACT_HOOKS.itervalues(),
                        self, changed, course, settings)
        return changed


class MilestoneTrigger(AvailabilityTrigger):
    """Course availability change at the specified start/end date/times.

    Why for_form(), set_into_settings(), and from_payload() perform the
    manipulations that they do to go back and forth between the way milestone
    triggers are stored in the settings and the way they are defined in the
    "Publish > Availability" form schema? (Rather than, say, just storing
    each milestone trigger keyed by its milestone value into the 'publish'
    dict?) One reason: complex properties in the "Publish > Availability" form
    schema are implemented as FieldRegistry objects.

    Each milestone trigger is one of these complex "form within a form"
    fields, consisting of an availability value (as an AvailabilityTrigger)
    and a "when" datetime (as a DateTimeTrigger). This is no different from
    a ContentTrigger, though, so why the additional complexity?

    Content triggers, being multiple and variable in number, are a natural
    fit for being grouped inside a FieldArray, where a FieldRegistry is
    easily used as an element of the variable-length array.

    Milestone triggers, on the other hand, are singular (e.g. "course start",
    "course end"). Unfortunately, it is not possible to add_property() one
    FieldRegistry (how triggers are represented in the form schema) into
    another FieldRegistry. Instead, add_sub_registry() must be used, but this
    results in a bad layout of the form, because sub-registries are always
    rendered at the very bottom of the form, after all of the properties
    (SchemaFields and FieldArrays).

    To instead allow these milestone triggers to appear in the form at the
    most appropriate vertical location (near the top, beneath the existing
    "Course Availability" <select>, rather than being relegated to the bottom
    of the form), each milestone trigger FieldRegistry is embedded into a
    single-value FieldArray, which *can* add_property() directly into the
    top-level FieldRegistry of the form.

    An added bonus of using a list of encoded triggers as the way all of the
    milestone triggers are stored is that the same super @classmethods that
    operate on lists of content triggers can be used with the milestone
    triggers as well.

    Modules can register to be called back when a course-wide milestone
    date/time trigger is "acted-on", that is, the act() method of a
    MilestoneTrigger has been invoked (this happens when a valid trigger is
    now in the past and thus "triggered"). Callbacks can be registered for
    each of the KNOWN_MILESTONES like this:

        triggers.MilestoneTrigger.ACT_HOOKS[constants.START_DATE_MILESTONE][
            'my_module'] = my_course_start_handler

        triggers.MilestoneTrigger.ACT_HOOKS[constants.END_DATE_MILESTONE][
            'my_module'] = my_course_end_handler

    Trigger callbacks are called a single time for a given acted-on trigger,
    since the act() method for a given trigger is called only once, and then
    that "expended" trigger is, by definition, discarded. The callbacks are
    called in no particular order, via common.utils.run_hooks().

    Acted-on trigger callbacks must accept these paramters:
      trigger - the specific MilestoneTrigger instance invoking the callbacks.
      changed - a ChangedByAct namedtuple containing 'previous' and 'next'
        course-wide availability changed by act(), or None if no change.
        (If there is no change, the current availability is still accessible
        to the callback via trigger.availability.)
      course - the Course that has been potentially altered by the act()
        method prior to any callbacks being called.
      env - the Course get_environ() dict containing settings changes made by
        the act() method that *have not yet been saved* to the Course.
        Changes to this env dict by the callback *will* affect what is
        eventually saved back into the Course environment and settings.
    """

    # Course milestones are currently the only known milestones.
    KNOWN_MILESTONES = list(constants.COURSE_MILESTONES)
    MILESTONE_TO_SETTING = constants.MILESTONE_TO_SETTING
    SETTING_TO_MILESTONE = constants.SETTING_TO_MILESTONE

    ACT_HOOKS = {km: {} for km in KNOWN_MILESTONES}

    FIELD_NAME = 'milestone'
    FIELDS = AvailabilityTrigger.FIELDS + [FIELD_NAME]

    SETTINGS_NAME = 'course_triggers'

    # Explicitly does *not* include the AVAILABILITY_NONE_SELECTED <option>
    # value ('none', '--- change availability to ---') from the form, even
    # though that is the DEFAULT_AVAILABILITY value used in the form <select>.
    AVAILABILITY_VALUES = availability_options.COURSE_VALUES

    # ('none', '--- change availability to ---') is the default form <option>
    # in the course start/end availability <select> fields, but any milestone
    # trigger that did not have an actual (present in COURSE_VALUES)
    # availability selected will be discarded and not saved in the course
    # settings.
    DEFAULT_AVAILABILITY = AvailabilityTrigger.NONE_SELECTED

    UNEXPECTED_MILESTONE_FMT = "Milestone '{}' not in {}."

    IMPLEMENTED_SET_SEMANTICS = frozenset([
        DateTimeTrigger.SET_WILL_OVERWRITE,
        DateTimeTrigger.SET_WILL_MERGE,
    ])

    def __init__(self, milestone=None, **super_kwargs):
        """Validates and sets `milestone` and super class properties."""
        super(MilestoneTrigger, self).__init__(**super_kwargs)
        # `milestone` is always either one of cls.KNOWN_MILESTONES or None.
        self._milestone = self.validate_milestone(milestone)

    @property
    def name(self):
        """Returns a "name" string that can be compared, sorted, etc."""
        return '{}{}{}'.format(super(MilestoneTrigger, self).name,
            self.NAME_PART_SEP, self.encoded_milestone)

    DATETIME_CSS = 'inputEx-Field ' + AvailabilityTrigger.DATETIME_CSS
    ARRAY_WRAPPER_CSS = 'inputEx-fieldWrapper'

    @classmethod
    def milestone_css(cls, extra_css=None):
        """Returns 'className' value for a 'milestone' SchemaField."""
        extra_css = [] if not extra_css else [extra_css]
        classes = [MilestoneTrigger.FIELD_NAME] + extra_css
        return ' '.join(classes)

    @property
    def milestone(self):
        """Returns one of the KNOWN_MILESTONES or None.

        The milestone property is a hidden field in the form schema of each
        milestone trigger on the "Publish > Availability" form. Its sole use
        is to transition a trigger back and forth between form payload
        structured as a dict keyed by the milestone, and an unordered list of
        milestone triggers as they are stored in the settings.
        """
        return self._milestone

    @classmethod
    def validate_milestone(cls, milestone):
        """Returns milestone if in KNOWN_MILESTONES, otherwise None."""
        if milestone in cls.KNOWN_MILESTONES:
            return milestone
        logging.warning(cls.LOG_ISSUE_FMT, 'INVALID',
            MilestoneTrigger.FIELD_NAME, utils.get_ns_name_for_logging(),
            {MilestoneTrigger.FIELD_NAME: milestone},
            cls.UNEXPECTED_MILESTONE_FMT.format(
                milestone, cls.KNOWN_MILESTONES))
        return None

    @classmethod
    def encode_milestone(cls, milestone):
        """Returns validated milestone (encode and decode are identical)."""
        return cls.validate_milestone(milestone)

    @property
    def encoded_milestone(self):
        return self.encode_milestone(self.milestone)

    VALIDATES = [FIELD_NAME]

    @classmethod
    def validate(cls, encoded, fail_fast=None):
        valid_or_not = super(MilestoneTrigger, cls).validate(
            encoded, fail_fast=fail_fast)
        if cls.abort_validation(fail_fast, valid_or_not):
            return valid_or_not
        cls.validate_property(MilestoneTrigger.FIELD_NAME,
            cls.validate_milestone, encoded, valid_or_not)
        return valid_or_not

    @property
    def decoded(self):
        """Returns the MilestoneTrigger as dict of *decoded* properties."""
        present = super(MilestoneTrigger, self).decoded
        if self.milestone is not None:
            present[MilestoneTrigger.FIELD_NAME] = self.milestone
        return present

    @classmethod
    def encode(cls, milestone=None, **super_kwargs):
        """Returns encoded dict containing only encode-able properties."""
        encoded = super(MilestoneTrigger, cls).encode(**super_kwargs)
        encoded_milestone = cls.encode_milestone(milestone)
        if encoded_milestone:
            encoded[MilestoneTrigger.FIELD_NAME] = encoded_milestone
        return encoded

    @property
    def is_valid(self):
        """Returns True if the Trigger properties are *all* currently valid."""
        # self._milestone is set in exactly one place, in __init__(), and
        # is set only to the return value of validate_milestone(), which is
        # either None or one of the cls.KNOWN_MILESTONES.
        return ((self.milestone is not None) and
                super(MilestoneTrigger, self).is_valid)

    @classmethod
    def _get_named_setting_env(cls, env, course=None):
        """Determines which settings to alter when changing a named setting.

        This method checks if an env dict was supplied and prefers it, if
        present, since it may have pending settings changes that have not yet
        been saved to the Course. For similar reasons, the env dict is not
        saved to the course, since it may also be further modified elsewhere
        before later being saved.

        Args:
            env: a Course get_environ() dict, returned if supplied (non-None).
            course: (optional) a Course, whose app_context is passed to
                get_environ() if env is None.

        Returns:
            A two-tuple:
              1) env if it is not None; otherwise, use course (if supplied) to
                 obtain a get_environ() dict.
              2) False unless a get_environ() dict was obtained from course.
        """
        if (env is not None) or (not course):
            return env, False

        env = courses.Course.get_environ(course.app_context)
        return env, (env is not None)

    @classmethod
    def retrieve_named_setting(cls, setting_name, env, course=None):
        """Returns value of a named setting from settings or Course, or None.

        Args:
            setting_name: a Course get_environ() 'course' dict key for a
                setting value to retrieve from env.
            env: a Course get_environ() dict from which to copy a value
                indicated by the setting_name key from the 'course' dict.
            course: (optional) a Course, consulted for the setting_name value
                only if not found in env.
        """

        env, from_course = cls._get_named_setting_env(env, course=course)
        value = courses.Course.get_named_course_setting_from_environ(
            setting_name, env)

        where = 'course' if from_course else 'env'
        milestone = cls.SETTING_TO_MILESTONE.get(setting_name)
        milestone = '' if not milestone else milestone + ' '
        logging.debug('RETRIEVED %s %s for %s%s trigger: %s',
                      where, setting_name, milestone, cls.kind(), value)
        return value

    @classmethod
    def get_default_when_from_settings(cls, milestone, settings, course=None):
        """Returns a default 'when' value for a milestone, from settings.

        Args:
            milestone: one of the KNOWN_MILESTONES, to be mapped to the name
                of a corresponding setting, if there is one.
            settings: subclass-specific settings (e.g. a Course get_environ()
                dict, or StudentGroupDTO for student_groups) potentially
                holding defaults trigger 'when' values.
            course: (optional) a Course, which, if settings does not contain
                a default setting value corresponding to the milestone, is
                used to obtain the 'course' setting (e.g. 'course:start_date')
                corresponding to the milestone (e.g. 'course_start' 'when')
                if there is one.

        Returns:
            An UTC ISO-8601 date/time string, if one can be found (first) in
            settings, and, if not, (second) in the Course. None is returned
            an encoded 'when' string corresponding to milestone is unavailable.
        """
        setting_name = cls.MILESTONE_TO_SETTING.get(milestone)
        if not setting_name:
            # If there is no mapping from milestone (e.g. 'course_start')
            # to settings name (e.g. a 'start_date' Course get_environ()
            # 'course' dict key or StudentGroupDTO property name), then
            # there is no corresponding `when` value in the settings, so
            # exit early.
            return None

        if (not settings) and (not course):
            # If no Course or settings (e.g. a Course get_environ() dict or a
            # StudentGroupDTO) were provided, there is no source for a `when`
            # value derived from settings, so exit early.
            return None

        return cls.retrieve_named_setting(
            setting_name, settings, course=course)

    @classmethod
    def encoded_defaults(cls, milestone=None, settings=None, course=None,
                         **super_kwargs):
        """Returns an encoded trigger initialized to any possible defaults.

        Some milestones (e.g. course_start and course_end) *do* potentially
        have meaningful default date/time values (e.g. obtained from
        'course:start_date' and 'course:end_date, repectively), so 'when'
        may have a value in those cases.

        Args:
            milestone: an explicitly specified milestone "name"; there are
                no "unnamed" MilestoneTriggers, so some valid milestone value
                from the class KNOWN_MILESTONES *must* be supplied.
            settings:  see get_default_when_from_settings().
            course: (optional) see get_default_when_from_settings().
            super_kwargs: keyword arguments passed on to base class.

        Returns:
            Returns the encoded trigger for the specified milestone, or None
            if that milestone is invalid.
        """
        if not cls.validate_milestone(milestone):
            # No specific milestone (e.g. course_start) provided, so no way to
            # return a meaningful "default" MilestoneTrigger, so exit early.
            return None

        when = cls.get_default_when_from_settings(
            milestone, settings, course=course)

        if when and not super_kwargs.get(DateTimeTrigger.FIELD_NAME):
            super_kwargs = super_kwargs.copy()
            super_kwargs[DateTimeTrigger.FIELD_NAME] = when

        defaults = super(MilestoneTrigger, cls).encoded_defaults(
            **super_kwargs)
        defaults[MilestoneTrigger.FIELD_NAME] = milestone
        return defaults

    @classmethod
    def is_defaults(cls, encoded_trigger, defaults=None, **enc_def_kwargs):
        """True if encoded_trigger contains only encoded_defaults() values.

        There is no *default* value for the `milestone` property, but the
        property typically must be present in a MilestoneTrigger. If the
        'milestone' key itself is not present in the supplied encoded_trigger
        dict, this method defers to the base class is_defaults().

        Similarly, since there is no default value for the `milestone`
        property, so whatever value is present in the supplied encoded_trigger
        dict (valid with respect to validate_milestone() or not) is also placed
        into the dict returned by MilestoneTrigger.encoded_defaults(), to
        effectively eliminate that property from the comparison.

        Args:
            encoded_trigger: an encoded (e.g. form payload or marshaled
                for storing into settings) trigger dict.
            defaults: (optional) a dict containing the defaults for an
                encoded trigger. MilestoneTrigger needs to create a defaults
                dict that depends on the 'milestone' value in encoded_trigger,
                so a subclass might have similar needs.
            enc_def_kwargs: additional keywords arguments passed directly to
                encoded_defaults() if defaults is missing.
        """
        milestone = encoded_trigger.get(MilestoneTrigger.FIELD_NAME)

        if milestone in cls.KNOWN_MILESTONES:
            # Deal with *all* False values, not just None.
            if not defaults:
                if MilestoneTrigger.FIELD_NAME not in enc_def_kwargs:
                    enc_def_kwargs = enc_def_kwargs.copy()
                    enc_def_kwargs[MilestoneTrigger.FIELD_NAME] = milestone
                defaults = cls.encoded_defaults(**enc_def_kwargs)
            elif MilestoneTrigger.FIELD_NAME not in defaults:
                defaults[MilestoneTrigger.FIELD_NAME] = milestone

        return super(MilestoneTrigger, cls).is_defaults(
                encoded_trigger, defaults=defaults)

    @classmethod
    def copy_milestone_from_settings(cls, milestone, settings):
        """Copies the specified milestone from a supplied settings.

        Args:
            milestone: one of the KNOWN_MILESTONE strings.
            settings: subclass-specific settings (e.g. a Course get_environ()
                dict, or StudentGroupDTO for student_groups) potentially
                holding the requested milestone trigger.

        Returns:
            The specified milestone trigger in "encoded" form (a dict of
            JSON-encoded string key/value pairs) if that trigger is present in
            the supplied settings. Otherwise, an empty dict is returned.
        """
        # len(KNOWN_MILESTONES) is the upper bound of the length of the list
        # returned by copy_from_settings(). The current length of that list
        # is *2*, so just traverse it, instead of calling for_form() to
        # transform it into a milestone-keyed dict of single value lists.
        for mt in cls.copy_from_settings(settings):
            if mt.get(MilestoneTrigger.FIELD_NAME) == milestone:
                return mt.copy()  # Just string values, so shallow copy OK.
        return {}

    @classmethod
    def for_form(cls, settings, course=None):
        """Groups milestone triggers; provides defaults for absent triggers.

        Milestone triggers are stored as a single list that is the value of
        the SETTINGS_NAME key in a dict or a property in a DTO.

        Args:
            settings: see encoded_defaults() and also base class for_form().
            course: (optional) see encoded_defaults() and also separate().

        Returns:
            A dict with all KNOWN_MILESTONES as keys, and single-value
            lists as values. The single value in each list is one of:
            - An encoded milestone trigger obtained from the course settings,
              for the same milestone as the dict key.
            - An encoded_defaults() placeholder for the same milestone as the
              dict key, if that trigger was missing from the course settings.

            Any trigger in the course settings corresponding to a milestone
            not found in KNOWN_MILESTONES is simply dropped (not included in
            the returned dict).
        """
        lists_of_encoded_triggers = super(MilestoneTrigger, cls).for_form(
            settings).itervalues()
        flattened = [et for ets in lists_of_encoded_triggers for et in ets]
        deduped, _ = cls.dedupe_for_settings(flattened, course=course,
            semantics=cls.SET_WILL_OVERWRITE)
        return dict([(m, [deduped[m]]) if m in deduped else
                     (m, [cls.encoded_defaults(
                             milestone=m, settings=settings, course=course)])
                     for m in cls.KNOWN_MILESTONES])

    @classmethod
    def dedupe_for_settings(cls, encoded_triggers,
                            semantics=None, settings=None, course=None):
        """De-duplicates encoded triggers to prepare for updating settings.

        separate() is used to obtain only the valid milestone triggers from the
        supplied encoded_triggers. The resulting valid, still-encoded triggers
        are then written (in the order they occurred in the supplied
        encoded_triggers list) into a dict, thus retaining only the last valid
        trigger corresponding to each of the KNOWN_MILESTONES.

        Args:
            encoded_triggers: a list of course triggers (typically from encoded
                form payload), in no particular order, and possibly including
                invalid triggers (e.g. '--- change availability to ---'
                availability, no 'when' date/time, etc.); any invalid triggers
                are omitted from the returned dict.
            semantics: (optional) one of
                SET_WILL_OVERWITE -- (default behavior) Only unique, valid
                    course milestone triggers extracted from the supplied
                    encoded_triggers are returned.
                SET_WILL_MERGE -- Unique, valid course milestone triggers
                    extracted from the supplied encoded_triggers are merged
                    with any existing triggers found in the supplied settings.
            settings: (optional) subclass-specific settings containing existing
                encoded triggers, simply copied from and thus not altered by
                this method. Needed only for SET_WILL_MERGE semantics.
            course: (optional) passed, untouched, through to separate().

        Returns:
            Returns a two-tuple of:
            * A dict containing (by definition) *at most* one unique trigger
              for each of the KNOWN_MILESTONES, mapping each milestone to the
              corresponding valid, encoded trigger (if one exists).
            * The Separated namedtuple returned by separate().

        """
        semantics = cls.check_set_semantics(semantics)
        separated = cls.separate(encoded_triggers, course)
        deduped = {et[MilestoneTrigger.FIELD_NAME]: et
                   for et in separated.encoded}

        if settings and (semantics == cls.SET_WILL_MERGE):
            # When calling to set settings for multiple courses all at once,
            # only one item at a time is sent, and other milestone types
            # should not be affected.  In this case, we want to merge with
            # existing settings, rather than drop milestone types that are not
            # explicitly named.
            current = {t[MilestoneTrigger.FIELD_NAME]: t
                       for t in cls.copy_from_settings(settings)}
            current.update(deduped)
            # Any valid, de-duped triggers have now replaced their counterparts
            # in the triggers currently present in the supplied settings (or
            # been added if they were not already present in those settings).
            # This merged dict of course milestone triggers can now actually
            # *overwrite* the existing SETTINGS_NAME list. If no triggers
            # remain after merging (current is an empty dict), the super
            # set_into_settings() will call clear_from_settings() as expected.
            deduped = current

        return deduped, separated

    @classmethod
    def clear_named_setting(cls, setting_name, env, course=None):
        """Removes a named setting from settings or the Course.

        Args:
            setting_name: a Course get_environ() 'course' dict key for a
                setting to remove from env or the Course.
            env: a Course get_environ() dict to update *in place* by removing
                the setting_name key and value from the 'course' dict.
            course: (optional) a Course used to remove the named setting if
                env was not supplied.
        """
        env, from_course = cls._get_named_setting_env(env, course=course)
        if env is not None:
            courses.Course.clear_named_course_setting_in_environ(
                setting_name, env)
            if from_course and course:
                course.save_settings(env)
                action = 'SAVED CLEARED'
            else:
                action = 'CLEARED'

            milestone = cls.SETTING_TO_MILESTONE.get(setting_name)
            milestone = '' if not milestone else milestone + ' '
            logging.debug(
                '%s %s due to %s%s trigger missing value.',
                action, setting_name, milestone, cls.kind())

    @classmethod
    def set_named_setting(cls, setting_name, value, env, course=None):
        """Sets the value of a named setting into settings or the Course.

        Args:
            setting_name: a Course get_environ() 'course' dict key for a
                setting to update in env or the Course.
            value: a value for setting_name; if None, the setting will be
                cleared from env of the Course, if possible.
            env: a Course get_environ() dict to update *in place* the value of
                the setting_name key in the 'course' dict.
            course: (optional) a Course used to set the value of the named
                setting if env was not supplied.
        """
        if value:
            env, from_course = cls._get_named_setting_env(env, course=course)
            if env is not None:
                courses.Course.set_named_course_setting_in_environ(
                    setting_name, env, value)
                if from_course and course:
                    course.save_settings(env)
                    action = 'SAVED SET'
                else:
                    action = 'SET'

                milestone = cls.SETTING_TO_MILESTONE.get(setting_name)
                milestone = '' if not milestone else milestone + ' '
                logging.debug(
                    '%s %s obtained from %s%s trigger to: %s.',
                    action, setting_name, milestone, cls.kind(), value)
        else:
            cls.clear_named_setting(setting_name, env, course=course)

    @classmethod
    def _get_setting_name_for_set_or_clear(cls, milestone, settings,
                                           setting_name, course):
        if not setting_name:
            setting_name = cls.MILESTONE_TO_SETTING.get(milestone)

        if not setting_name:
            # If there is no mapping from milestone (e.g. 'course_start')
            # to settings name (e.g. a 'start_date' Course get_environ()
            # 'course' dict key or StudentGroupDTO property name), then
            # there is no corresponding `when` value in the settings, so
            # exit early.
            return None

        if (not settings) and (not course):
            # If no Course or settings (e.g. a Course get_environ() dict or a
            # StudentGroupDTO) were provided, there is no place to alter a
            # `when` value into the settings, so exit early.
            return None

        return setting_name

    @classmethod
    def set_corresponding_setting(cls, milestone, when, settings,
                                  setting_name=None, course=None):
        setting_name = cls._get_setting_name_for_set_or_clear(
            milestone, settings, setting_name, course)

        if setting_name:
            cls.set_named_setting(setting_name, when, settings, course=course)

    @classmethod
    def clear_corresponding_setting(cls, milestone, settings,
                                    setting_name=None, course=None):
        setting_name = cls._get_setting_name_for_set_or_clear(
            milestone, settings, setting_name, course)

        if setting_name:
            cls.clear_named_setting(setting_name, settings, course=course)

    @classmethod
    def set_multiple_whens_into_settings(cls, encoded_triggers, settings,
                                         remaining=None, course=None):
        """Set valid 'when' values from encoded triggers into settings.

        Args:
            encoded_triggers: a list of encoded course milestone triggers from
                which valid 'when' values corresponding to Course settings or
                student group properties (e.g. start_date for a course_start
                trigger) are extracted.
            settings: subclass-specific settings (e.g. a Course get_environ()
                dict, or StudentGroupDTO for student_groups trigger subclasses)
                containing settings that correspond to milestones (e.g.
                milestone 'course_start' to 'course:start_date') that are
                potentially updated *in-place*.
            remaining: (optional) a milestone to setting mapping that is
                destructively updated *in place*, removing each mapping for
                which a setting value has been successfully set; initialized
                to a copy of MILESTONE_TO_SETTING by default.
            course: (optional) see set_named_setting().

        Returns:
            The updated `remaining` dict, with milestone to setting mappings
            removed for each successful stored setting value. Callers should
            pass this dict from set_multiple_whens_into_settings() calls to
            subsequent calls.
        """
        if remaining is None:
            remaining = cls.MILESTONE_TO_SETTING.copy()

        if not remaining:
            # All known milestones accounted for, so nothing left to do.
            return remaining

        for et in encoded_triggers:
            milestone = et.get(cls.FIELD_NAME)  # 'milestone'
            if not milestone:
                continue  # Malformed MilestoneTrigger?
            setting_name = remaining.get(milestone)
            if not setting_name:
                continue  # No setting name (remaining) for that milestone.
            when = et.get(DateTimeTrigger.FIELD_NAME)  # 'when'
            if when:
                when = cls.validate_when(when)  # datetime if valid, or None.
                if when:
                    when = cls.encode_when(when)  # Re-encode to UTC ISO-8601.
            when = when if when else None  # Collapse False values to None.
            remaining.pop(milestone, None)
            cls.set_corresponding_setting(milestone, when,
                settings, setting_name=setting_name, course=course)

        return remaining

    @classmethod
    def clear_multiple_corresponding_settings(cls, milestones, settings,
                                              remaining=None, course=None):
        """Clears settings values corresponding to encoded triggers.

        Args:
            milestones: a list of milestones corresponding to settings to be
                removed (e.g. remove 'start_date' setting or property for a
                'course_start' milestone).
            settings: subclass-specific settings (e.g. a Course get_environ()
                dict, or StudentGroupDTO for student_groups trigger subclasses)
                containing settings that correspond to milestones (e.g.
                milestone 'course_start' to 'course:start_date') that are
                potentially removed *in-place*.
            remaining: (optional) a milestone to setting mapping that is
                destructively updated *in place*, removing each mapping for
                which a setting value has been successfully cleared;
                initialized to a copy of MILESTONE_TO_SETTING by default.
            course: (optional) see clear_named_setting().

        Returns:
            The updated `remaining` dict, with milestone to setting mappings
            removed for each successful removed setting value. Callers should
            pass this dict from clear_multiple_corresponding_settings() calls
            to subsequent calls.
        """
        if remaining is None:
            remaining = cls.MILESTONE_TO_SETTING.copy()

        if not remaining:
            # All known milestones accounted for, so nothing left to do.
            return remaining

        for milestone in milestones:
            if not milestone:
                continue  # Malformed MilestoneTrigger?
            setting_name = remaining.get(milestone)
            if not setting_name:
                continue  # No setting name (remaining) for that milestone.
            remaining.pop(milestone, None)
            cls.clear_corresponding_setting(milestone,
                settings, setting_name=setting_name, course=course)

        return remaining

    @classmethod
    def set_into_settings(cls, encoded_triggers, settings,
                          semantics=None, course=None, triggers_only=False):
        """Sets encoded course start/end triggers into the supplied settings.

        Sets the value of the SETTINGS_NAME key in the 'publish' dict
        within the settings to a list containing at most *one* trigger for
        each of the KNOWN_MILESTONES, in no particular order.

        dedupe_for_settings() is used to remove any "deactivated" or invalid
        triggers, keeping only *at most* one unique encoded trigger for each of
        the KNOWN_MILESTONES.

        For example, milestone triggers coming from the form payload that have
        no 'when' datetime (because the user pressed the [Clear] button) or
        have 'none' availability (the user selected the
        '--- change availability to ---' value) are discarded and thus omitted
        from the milestone triggers to be stored in the settings. Those two
        user actions are perfectly valid ways to "deactivate" a milestone
        trigger.

        The remaining valid, still-encoded triggers are then de-duped,
        retaining only the last (in the order it occurred in the supplied
        encoded_triggers list) valid trigger corresponding to each of the
        KNOWN_MILESTONES. The result is stored as a single list in no
        particular order.

        Args:
            encoded_triggers: a list of course triggers (typically encoded
                form payload), in no particular order, and possibly including
                invalid triggers (e.g. '--- change availability to ---'
                availability, no 'when' date/time, etc.); any invalid triggers
                are omitted.
            settings: a Course get_environ() dict containing settings that
                correspond to milestones (e.g. milestone 'course_start' to
                'course:start_date', see MILESTONE_TO_SETTING) and are
                potentially updated *in-place*. The base class also updates
                the dict *in place* with new encoded_triggers.
            semantics: one of
                SET_WILL_OVERWITE -- De-duped, valid course milestone triggers
                    extracted from encoded_triggers are supplied to the base
                    class set_into_settings() unchanged.
                SET_WILL_MERGE -- When called to set settings for multiple
                    courses all at once, only one item at a time is sent, so
                    encoded_triggers is instead merged with the existing
                    SETTINGS_NAME values.
            course: (optional) passed, untouched, to dedupe_for_settings(),
                set_multiple_whens_into_settings(), the base class
                set_into_settings(), and through to separate().
            triggers_only: (optional) if True, update only the SETTINGS_NAME
                triggers list, and not any other settings.
        """
        deduped, separated = cls.dedupe_for_settings(encoded_triggers,
            semantics=semantics, settings=settings, course=course)
        super(MilestoneTrigger, cls).set_into_settings(deduped.values(),
            settings, semantics=cls.SET_WILL_OVERWRITE, course=course,
            triggers_only=triggers_only)

        if triggers_only:
            return  # Only update the SETTINGS_NAME triggers list.

        # Any encoded triggers in the deduped dict are valid, so copy
        # their 'when' date/time to the corresponding 'course' setting,
        # if there is one.
        remaining = cls.set_multiple_whens_into_settings(
            deduped.itervalues(), settings, course=course)

        # If not all of the known milestone triggers have been accounted for,
        # next check the encoded "invalid" triggers split out by separate().
        # Some may have a valid 'when' value (triggers with a "default"
        # availability would be separated out as invalid, even if the 'when'
        # field was valid) that needs to be saved into the settings.
        cls.set_multiple_whens_into_settings(
            separated.invalid, settings, remaining=remaining, course=course)

    @classmethod
    def clear_from_settings(cls, env, milestone=None, course=None,
                            triggers_only=False):
        """Removes one or all 'milestone' triggers from a get_environ() dict.

        Also removes any settings values that correspond to any removed
        triggers (e.g. removes 'start_date' setting for a 'course_start'
        milestone).

        Args:
            env: a Course get_environ() dict containing encoded triggers,
                that is updated *in-place* by clear_from_settings().
            milestone: if unspecified, the entire SETTINGS_NAME list
                ('course_triggers') is removed (the base class behavior of this
                method); otherwise only the specified 'milestone' trigger is
                pruned from that list.
            course: (optional) passed to set_into_settings() if called.
            triggers_only: (optional) if True, clear only the SETTINGS_NAME
                triggers list, and not any other settings.
        """
        triggers = cls.copy_from_settings(env)

        if milestone is None:
            # Original "remove entire SETTINGS_NAME list" if not pruning out
            # the trigger(s) for a specific course milestone.
            super(MilestoneTrigger, cls).clear_from_settings(env)
            if triggers_only:
                return
            # Now remove *all* settings values corresponding to the milestones
            # of *all* trigger that were just removed.
            milestones = [t.get(cls.FIELD_NAME) for t in triggers]
            cls.clear_multiple_corresponding_settings(
                milestones, env, course=course)
            return

        kept = [t for t in triggers
                if t.get(cls.FIELD_NAME) != milestone]

        if not triggers_only:
            # Clear only the single setting corresponding to the milestone of
            # the one trigger that was just pruned.
            cls.clear_corresponding_setting(milestone, env, course=course)

        # If any triggers remain after pruning out the milestone ones,
        # the kept list needs to actually *overwrite* the existing
        # SETTINGS_NAME list. If no triggers remain after pruning (kept is an
        # empty list), super set_into_settings() calls clear_from_settings().
        super(MilestoneTrigger, cls).set_into_settings(
            kept, env, course=course)

    @classmethod
    def from_payload(cls, payload):
        """Returns all encoded milestone triggers from form payload.

        Milestone triggers in the "Publish > Availability" form are found in
        single-value FieldArrays with a schema property name corresponding
        cooresponding to one of the KNOWN_MILESTONES. So, they appear in
        the payload dict like:
          {
            'course_start': [{'milestone': 'course_start', 'when': ...}],
            'course_end':  [{'milestone': 'course_end', 'when': ...}],
            ...
          }
        The callers of from_payload() expect the triggers to be returned in
        a single list of all triggers for that SETTINGS_NAME.

        from_payload() iterates through all of the KNOWN_MILESTONES, to get()
        for each of those milestones what is expected to be a single-value
        list containing the milestone trigger (or possibly just an empty list).
        """
        return [et for m in cls.KNOWN_MILESTONES for et in payload.get(m, [])]

    def act(self, course, env):
        """Updates course-wide availability as indicated by the trigger.

        Note: this act() method specifically does *not* deal with receiving
        a student_groups.StudentGroupDTO instead of a Course get_environ()
        dict as its "settings" parameter. Any student_groups subclass of
        MilestoneTrigger is expected to supply its own act() method.

        Args:
            course: a Course passed through, unaltered, to ACT_HOOKS callbacks.
            env: a Course get_environ() dict containing settings that are
                potentially updated *in-place* by act() and then passed to
                ACT_HOOKS callbacks.
        """
        changed = None
        current = courses.Course.get_course_availability_from_environ(env)
        new = self.availability
        hooks_to_run = self.ACT_HOOKS.get(self.milestone, {})

        if current != new:
            courses.Course.set_course_availability_into_environ(new, env)
            changed = self.ChangedByAct(current, new)
            logging.info('APPLIED %s from "%s" to "%s" at %s in %s: %s',
                self.kind(), current, new,
                availability_options.option_to_title(self.milestone),
                utils.get_ns_name_for_logging(course=course), self.logged)
        elif hooks_to_run:
            old_when = self.get_default_when_from_settings(
                self.milestone, env, course=course)
            new_when = self.encoded_when
            if old_when != new_when:
                changed = self.ChangedByAct(old_when, new_when)

        utils.run_hooks(hooks_to_run.itervalues(), self, changed, course, env)
        return changed

    CourseWhen = collections.namedtuple('CourseWhen', [
        'iso8601_z', 'human', 'date_only', 'no_suffix', 'as_tooltip'])

    # First element in the "Start Date" or "End Date" column value tooltip
    # will be either the resulting availability after a course-wide start/end
    # availability trigger, or the corresponding 'start_date' or 'end_date'
    # setting in the 'course' dict of get_environ().
    #
    # For example, with a course-wide start/end availability trigger:
    #   "Registration Required on 2016-10-20 12:00:00 UTC."
    # Or, without a trigger, using the corresponding 'course' setting instead:
    #   "Start on 2016-10-20 12:00:00 UTC."
    # Or, as a last resort, simply the date and time.
    _ON_PREFIX = u'{} on '
    _TITLE_ON_WHEN_FMT = _ON_PREFIX + '{}.'
    _WHEN_FOR_COURSE_FMT = '{} for "{}".'
    _WHEN_TOOLTIP_FMT = _ON_PREFIX + _WHEN_FOR_COURSE_FMT
    _UTC_SUFFIX = ' UTC'

    @classmethod
    def get_course_when(cls, env, milestone, course_name):
        """Returns a CourseWhen named tuple filled out from env settings."""
        title = constants.MILESTONE_TO_TITLE.get(milestone)

        course_triggers = cls.for_form(env)
        trigger = course_triggers.get(milestone, [{}])[0]
        when = trigger.get(DateTimeTrigger.FIELD_NAME)

        if not when:
            # No trigger with 'when', so check 'course' settings for a value.
            setting_name = cls.MILESTONE_TO_SETTING.get(milestone)
            when = courses.Course.get_named_course_setting_from_environ(
                setting_name, env, default='')
        else:
            # Non-empty 'when' trigger was present, so get availability text.
            avail = trigger.get(AvailabilityTrigger.FIELD_NAME)
            policy = courses.COURSE_AVAILABILITY_POLICIES.get(avail, {})
            title = policy.get('title') or title

        if not when:
            # No 'when' in trigger or 'course' settings, so exit early.
            return cls.CourseWhen('', '', '', '', '')

        # Non-empty 'when' will always be an ISO 8601 "UTC Z" string.
        when_dt = utc.text_to_datetime(when)
        human = utc.to_text(dt=when_dt, fmt=utc.ISO_8601_UTC_HUMAN_FMT)
        no_suffix = human
        date = utc.to_text(dt=when_dt, fmt=utc.ISO_8601_DATE_FMT)

        if no_suffix.endswith(cls._UTC_SUFFIX):
            no_suffix = no_suffix[:-len(cls._UTC_SUFFIX)]

        if title:
            tip = cls._WHEN_TOOLTIP_FMT.format(title, human, course_name)
            no_suffix = cls._TITLE_ON_WHEN_FMT.format(title, no_suffix)
        else:
            tip = cls._WHEN_FOR_COURSE_FMT.format(human, course_name)

        return cls.CourseWhen(when, human, date, no_suffix, tip)
