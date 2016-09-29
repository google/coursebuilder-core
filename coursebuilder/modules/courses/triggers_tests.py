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

"""Unit tests for modules/courses/triggers."""

__author__ = 'Todd Larsen (tlarsen@google.com)'

import datetime
import logging
import random
import re
import time
import unittest

from common import resource
from common import utc
from controllers import sites
from models import courses

from models import resources_display
from modules.courses import availability_cron
from modules.courses import availability_options
from modules.courses import constants
from modules.courses import triggers
from tests.functional import actions


class FunctionsTests(unittest.TestCase):
    """Unit tests for module-scope functions in modules.courses.triggers."""

    def test_qualified_typename(self):
        """Tests _fully_qualified_typename and _qualified_typename."""
        self.assertEquals(
            'modules.courses.triggers_tests.FunctionsTests',
            triggers._fully_qualified_typename(self.__class__))

        self.assertEquals(
            'triggers_tests.FunctionsTests',
            triggers._qualified_typename(self.__class__))


class TriggerTestsMixin(object):
    """Common functionality mixed into all triggers classes tests."""

    TDTT = triggers.DateTimeTrigger
    TAT = triggers.AvailabilityTrigger
    TCT = triggers.ContentTrigger
    TMT = triggers.MilestoneTrigger

    NOT_DATE_AND_TIME = 'Not a valid ISO-8601 date and time.'

    CHARS_IN_ISO_8601_DATETIME = '[0-9T:.Z-]+'
    ENCODED_TRIGGER_RE = '{.+}'
    UNEMPLEMENTED_ACT_RE = '.*UNIMPLEMENTED .+\\.act\\(.+, .+\\): .+'

    LAST_CENTURY = utc.to_text(dt=datetime.datetime(1900, 1, 1, 0))
    FAR_FUTURE = utc.to_text(dt=datetime.datetime(9999, 12, 31, 23))

    NOW_DELTA = datetime.timedelta(seconds=1)

    BAD_AVAIL = 'not a valid availability value'
    BAD_WHEN = 'not a valid UTC date/time'

    LOG_LEVEL = logging.DEBUG

    def setUp(self):
        self.dt_when = utc.now_as_datetime()
        self.now = utc.to_timestamp(dt=self.dt_when)
        self.txt_when = utc.to_text(dt=self.dt_when)
        self.maxDiff = None

        self.past_hour_text = utc.to_text(
            seconds=utc.hour_start(self.now - (60 * 60)))
        self.next_hour_text = utc.to_text(
            seconds=utc.hour_end(self.now + (60 * 60)) + 1)

    @classmethod
    def utc_past_text(cls, now):
        return utc.to_text(seconds=utc.hour_start(now - (60 * 60)))

    @classmethod
    def utc_future_text(cls, now):
        return utc.to_text(seconds=utc.hour_end(now + (60 * 60)) + 1)

    def default_availabilities(self, cls, availabilities):
        cls = cls if cls is not None else self.TAT
        return (availabilities if availabilities is not None
                else cls.AVAILABILITY_VALUES)

    @classmethod
    def place_triggers_in_expected_order(cls, triggers_list,
                                         unused_trigger_cls, **unused_kwargs):
        return triggers_list

    def check_validate(self, encoded, props, validator):
        """Used by trigger test classes to test validate methods."""
        expected_unused = dict(
            [(k, v) for k, v in encoded.iteritems() if k not in props])
        expected_valid_or_not = triggers.DateTimeTrigger.ValidOrNot(
            props, {}, set(), expected_unused)
        valid_or_not = validator(encoded)
        self.assertEquals(expected_valid_or_not, valid_or_not)

    def check_invalid_is(self, invalid):
        self.assertFalse(invalid.is_valid)
        self.assertFalse(invalid.is_future())
        self.assertFalse(invalid.is_ready())

    def check_valid_is(self, valid):
        self.assertTrue(valid.is_valid)

        now_in_past = self.dt_when - self.NOW_DELTA
        self.assertTrue(valid.is_future(now=now_in_past))
        self.assertFalse(valid.is_ready(now=now_in_past))

        now_in_future = self.dt_when + self.NOW_DELTA
        self.assertFalse(valid.is_future(now=now_in_future))
        self.assertTrue(valid.is_ready(now=now_in_future))

    def separating_logged(self, logs, count, trigger_cls):
        self.assertIn('SEPARATING %d encoded %s(s) in %s.' % (
            count, trigger_cls.typename(), self.NAMESPACE), logs)

    def awaiting_logged(self, logs, count, trigger_cls):
        self.assertIn('AWAITING %d future %s(s) in %s.' % (
            count, trigger_cls.typename(), self.NAMESPACE), logs)

    def untouched_logged(self, logs, trigger_classes):
        for trigger_cls in trigger_classes:
            self.assertIn('UNTOUCHED {} {}.'.format(
                self.NAMESPACE, trigger_cls.kind()), logs)

    def kept_logged(self, logs, count, trigger_cls):
        self.assertIn('KEPT %d future %s(s) in %s.' % (
            count, trigger_cls.typename(), self.NAMESPACE), logs)

    def saved_logged(self, logs, count, trigger_cls):
        self.assertIn('SAVED %d change(s) to %s %s.' % (
                count, self.NAMESPACE, trigger_cls.kind()), logs)

    def retrieve_logged(self, milestone, setting, when, trigger_cls, logs,
                        where='env'):
        milestone = '' if not milestone else milestone + ' '
        self.assertIn('RETRIEVED {} {} for {}{} trigger: {}'.format(
            where, setting, milestone, trigger_cls.kind(), when), logs)

    def set_named_logged(self, milestone, setting, when, trigger_cls, logs,
                         action='SET'):
        milestone = '' if not milestone else milestone + ' '
        self.assertIn('{} {} obtained from {}{} trigger to: {}'.format(
            action, setting, milestone, trigger_cls.kind(), when), logs)

    def cleared_logged(self, milestone, setting, trigger_cls, logs,
                        action='CLEARED'):
        milestone = '' if not milestone else milestone + ' '
        self.assertIn('{} {} due to {}{} trigger missing value.'.format(
            action, setting, milestone, trigger_cls.kind()), logs)

    def error_logged(self, logs, trigger, what, why, cause):
        self.assertRegexpMatches(logs,
            '.*%s %s in namespace %s encoded: "%s" cause: "%s".*' % (
                what, why, self.NAMESPACE, trigger, cause))

    def error_not_logged(self, logs, trigger, what, why, cause):
        self.assertNotRegexpMatches(logs,
            '.*%s %s in namespace %s encoded: "%s" cause: "%s".*' % (
                what, why, self.NAMESPACE, trigger, cause))

    def unimplemented_act_logged(self, logs):
        self.assertRegexpMatches(logs, self.UNEMPLEMENTED_ACT_RE)

    def unimplemented_act_not_logged(self, logs):
        self.assertNotRegexpMatches(logs, self.UNEMPLEMENTED_ACT_RE)

    def unchanged_logged(self, logs, current, trigger, course, trigger_cls):
        decoded = trigger_cls.decode(trigger, course=course)
        self.assertIn('UNCHANGED %s %s: %s' % (
            self.NAMESPACE, trigger_cls.kind(), decoded.logged), logs)

    def content_act_logged(self, logs, ct, ns_name, old_avail, new_avail):
        escaped = re.escape(
            'APPLIED {} from "{}" to "{}" for {} in {}: {}('.format(
                triggers.ContentTrigger.kind(), old_avail, new_avail,
                ct['content'], ns_name, triggers.ContentTrigger.typename()))
        applied_re = '.*' + escaped + '.+\\).*'
        self.assertRegexpMatches(logs, applied_re)

    def milestone_act_logged(self, logs, mt, ns_name, old_avail, new_avail):
        escaped = re.escape(
            'APPLIED {} from "{}" to "{}" at {} in {}: {}('.format(
                triggers.MilestoneTrigger.kind(), old_avail, new_avail,
                availability_options.option_to_title(mt['milestone']),
                ns_name, triggers.MilestoneTrigger.typename()))
        applied_re = '.*' + escaped + '.+\\).*'
        self.assertRegexpMatches(logs, applied_re)

    def triggers_logged(self, logs, logged, previous_avail, course,
                         trigger_cls):
        for lt in logged:
            decoded = trigger_cls.decode(lt, course=course)
            avail = lt.get('availability')
            if avail != previous_avail:
                self.assertIn('TRIGGERED %s %s from "%s" to "%s": %s' % (
                    self.NAMESPACE, trigger_cls.kind(), previous_avail,
                    avail, decoded.logged), logs)
            else:
                self.assertIn('UNCHANGED %s %s "%s": %s' % (
                    self.NAMESPACE, trigger_cls.kind(), previous_avail,
                    decoded.logged), logs)

    def find_trigger_content(self, course, trigger):
        content = resource.Key.fromstring(trigger['content'])
        if content.type == 'lesson':
            return course.find_lesson_by_id(None, content.key)
        return course.find_unit_by_id(content.key)

    def check_content_triggers_applied(self, logs, course, applied, old_avail):
        for at in applied:
            found = self.find_trigger_content(course, at)
            new_avail = at['availability']
            self.assertEquals(found.availability, new_avail)
            if old_avail != new_avail:
                # APPLIED message logged *only* if availability *changes*.
                self.content_act_logged(
                    logs, at, self.NAMESPACE, old_avail, new_avail)

    def check_content_triggers_unapplied(self, course, old_avail, unapplied):
        for ut in unapplied:
            found = self.find_trigger_content(course, ut)
            self.assertEquals(old_avail, found.availability)
            # Assumes no "UNCHANGED" future test cases.
            self.assertNotEquals(ut['availability'], found.availability)

    def check_course_trigger_applied(self, logs, course, mt, old_avail):
        course_avail = course.get_course_availability()
        new_avail = mt['availability']
        self.assertEquals(course_avail, new_avail)
        if old_avail != new_avail:
            # APPLIED message logged *only* if availability *changes*.
            self.milestone_act_logged(
                logs, mt, self.NAMESPACE, old_avail, new_avail)

    def check_course_trigger_unapplied(self, course, mt, old_avail):
        course_avail = course.get_course_availability()
        self.assertEquals(course_avail, old_avail)
        self.assertNotEquals(course_avail, mt['availability'])

    def when_value_error_regexp(self, when):
        with_when = "ValueError(\"time data '{}' does not match".format(when)
        return re.escape(with_when + " format '%Y-%m-%dT%H:%M:%S.%fZ'\",)")


class UnitTestBase(TriggerTestsMixin, unittest.TestCase):
    pass


class DateTimeTriggerTests(UnitTestBase):

    def test_name(self):
        """Tests the name @property, logged @property, and __str__."""
        dtt = self.TDTT(when=self.txt_when)
        expected_name = self.txt_when
        self.assertEquals(expected_name, dtt.name)
        self.assertEquals(expected_name, '{}'.format(dtt))
        expected_logged = '{}({})'.format(dtt.typename(), self.txt_when)
        self.assertEquals(expected_logged, dtt.logged)

    def test_when_css(self):
        self.assertEquals(
            'when gcb-datetime inputEx-fieldWrapper',
            self.TDTT.when_css())

    def test_validate(self):
        """Tests validate_when and validate."""
        # Instances of datetime.datetime simply pass through as-is.
        self.assertEquals(self.dt_when,
            self.TDTT.validate_when(self.dt_when))

        # Date/time in string form should be in ISO-8601 format.
        self.assertEquals(self.dt_when,
            self.TDTT.validate_when(self.txt_when))

        self.assertEquals(None,
            self.TDTT.validate_when(self.NOT_DATE_AND_TIME))

        encoded = {'when': self.txt_when, 'unused': 'ignored'}
        decoded_props = {'when': self.dt_when}
        self.check_validate(encoded, decoded_props, self.TDTT.validate)

    def test_encode_decode(self):
        """Tests encode_when, encode, encoded, decode, and decoded."""
        self.assertEquals(self.txt_when,
            self.TDTT.encode_when(self.dt_when))
        self.assertEquals(None,
            self.TDTT.encode_when(self.NOT_DATE_AND_TIME))

        expected = {'when': self.txt_when}
        encoded_dict = self.TDTT.encode(when=self.dt_when)
        self.assertEquals(expected, encoded_dict)

        decoded_dtt = self.TDTT.decode(expected)
        self.assertEquals(self.dt_when, decoded_dtt.when)
        self.assertEquals(expected, decoded_dtt.encoded)

        constructed_dtt = self.TDTT(when=self.txt_when)
        self.assertEquals(expected, constructed_dtt.encoded)
        decoded_dict = constructed_dtt.decoded
        self.assertEquals(self.dt_when, decoded_dict.get('when'))

    def test_is(self):
        """Tests is_valid, is_future, and is_ready."""
        invalid = self.TDTT()
        self.check_invalid_is(invalid)

        valid = self.TDTT(when=self.txt_when)
        self.check_valid_is(valid)

    SORT_DELTA = datetime.timedelta(seconds=1)

    def is_sorted_ascending_by_when(self, dts):
        is_ascending = True
        current = dts[0]
        for dt in dts:
            is_ascending = is_ascending and (dt.when >= current.when)
            current = dt
        return is_ascending

    def test_sort(self):
        """Tests in-place sorting of DateTimeTriggers by ascending `when`."""
        expected = [
            self.TDTT(when=self.dt_when - (3*self.SORT_DELTA)),
            self.TDTT(when=self.dt_when - self.SORT_DELTA),
            self.TDTT(when=self.dt_when),
            self.TDTT(when=self.dt_when + self.SORT_DELTA),
            self.TDTT(when=self.dt_when + (2*self.SORT_DELTA)),
        ]
        self.assertTrue(self.is_sorted_ascending_by_when(expected))

        unsorted = [
            expected[3], expected[2], expected[4], expected[1], expected[0],
        ]
        self.assertFalse(self.is_sorted_ascending_by_when(unsorted))
        self.assertNotEquals(
            [str(dt) for dt in expected],
            [str(dt) for dt in unsorted])

        now_sorted = self.TDTT.sort(unsorted)
        self.assertTrue(self.is_sorted_ascending_by_when(now_sorted))
        self.assertEquals(
            [str(dt) for dt in expected],
            [str(dt) for dt in now_sorted])

    def test_typename(self):
        self.assertEquals('triggers.DateTimeTrigger', self.TDTT.typename())


class AvailabilityTriggerTests(UnitTestBase):
    """Tests standalone parts of the abstract AvailabilityTrigger class."""

    def test_availability_css(self):
        self.assertEquals('availability gcb-select inputEx-Field',
            self.TAT.availability_css())

    def test_typename(self):
        self.assertEquals('triggers.AvailabilityTrigger', self.TAT.typename())


class FunctionalTestBase(TriggerTestsMixin, actions.TestBase):
    """Base class of unit tests that require a Course to be created.

    The functional tests actions.TestBase is used, even though the triggers
    tests are meant to be unit tests, to permit access to Course creation.
    """

    ADMIN_EMAIL = 'admin@example.com'

    def setUp(self):
        actions.TestBase.setUp(self)
        TriggerTestsMixin.setUp(self)

        self.base = '/' + self.COURSE_NAME
        self.app_context = actions.simple_add_course(
            self.COURSE_NAME, self.ADMIN_EMAIL,
            availability_options.option_to_title(self.COURSE_NAME))
        self.course = courses.Course(None, self.app_context)

    def check_copy_from_settings(self, cls, settings_name):
        self.assertEquals([], cls.copy_from_settings(None))

        # copy_from_settings() has no side-effects on the supplied settings.
        settings = {}
        self.assertEquals([], cls.copy_from_settings(settings))
        expected_settings = {}
        self.assertEquals(expected_settings, settings)

        expected_triggers = self.create_triggers()

        # Copy each encoded trigger in the expected_triggers into the
        # settings, so that they are distinct dict objects.
        settings['publish'] = {}
        settings['publish'][settings_name] = []
        for et in expected_triggers:
            settings['publish'][settings_name].append(et.copy())

        self.assertItemsEqual(
            expected_triggers, cls.copy_from_settings(settings))

    def check_in_settings(self, cls, settings_name):
        # in_settings() has side-effects on the supplied settings if empty.
        settings = {}
        self.assertEquals([], cls.in_settings(settings))
        expected_settings = {'publish': {settings_name: []}}
        self.assertEquals(expected_settings, settings)

        expected_triggers = self.create_triggers()

        # Copy each encoded trigger in the expected_triggers into the
        # settings, so that they are distinct dict objects.
        for et in expected_triggers:
            settings['publish'][settings_name].append(et.copy())

        self.assertItemsEqual(expected_triggers, cls.in_settings(settings))

    def check_payload_into_settings(self, cls, settings_name):
        """Checks payload_into_settings, from_payload, set_into_settings."""
        payload, expected_triggers, expected = self.create_payload_triggers()
        expected.update({'publish': {settings_name: expected_triggers}})
        settings = {}
        cls.payload_into_settings(payload, self.course, settings)
        self.assertItemsEqual(expected, settings)

        # Absent from payload should remove from settings. Use settings dict
        # from above, since it will have settings needing removal (start_date
        # and end_date).
        empty_settings = {'publish': {}}
        if 'course' in settings:
            # Some trigger types (e.g. 'course_start') also store values
            # (e.g. 'start_date') in the 'course' settings in the Course
            # get_environ() dict. Those same triggers remove corresponding
            # settings when the triggers themselves are cleared, but an
            # empty 'course' dict should remain, in tests at least.
            empty_settings['course'] = {}

        cls.payload_into_settings(self.empty_form, self.course, settings)
        self.assertEquals(empty_settings, settings)
        self.assertFalse(settings['publish'].get(settings_name))


class DateTimeTriggerFunctionalTests(FunctionalTestBase):

    COURSE_NAME = 'date_time_trigger_tests'
    NAMESPACE = 'ns_%s' % COURSE_NAME

    def test_unimplemented_act_regexp(self):
        app_context = sites.get_app_context_for_namespace(self.NAMESPACE)
        any_course = courses.Course(None, app_context=app_context)
        settings = {}

        unimplemented_trigger = self.TDTT(when=self.dt_when)
        trigger_type = unimplemented_trigger.typename()

        unimplemented_trigger.act(any_course, settings)
        unimplemented_trigger.act(None, settings)  # Default '' namespace.

        logs = self.get_log()
        self.unimplemented_act_logged(logs)

        with_ns = re.escape('UNIMPLEMENTED {}.act({}, {}): {}('.format(
            trigger_type, self.NAMESPACE, settings, trigger_type))
        ns_re = '{}{}\\)'.format(with_ns, self.CHARS_IN_ISO_8601_DATETIME)
        self.assertRegexpMatches(logs, ns_re)

        no_ns = re.escape('UNIMPLEMENTED {}.act({}, {}): {}('.format(
            trigger_type, "''", settings, trigger_type))
        no_ns_re = '{}{}\\)'.format(no_ns, self.CHARS_IN_ISO_8601_DATETIME)
        self.assertRegexpMatches(logs, no_ns_re)


class ContentTriggerTestsMixin(TriggerTestsMixin):

    BAD_CONTENT_KEY = 'not a valid resource Key'
    BAD_CONTENT_TRIGGER_SUFFIX = ' for a content trigger'

    TTMIX = TriggerTestsMixin

    BAD_CONTENT_WHEN = TTMIX.BAD_WHEN + BAD_CONTENT_TRIGGER_SUFFIX
    BAD_CONTENT_AVAIL = TTMIX.BAD_AVAIL + BAD_CONTENT_TRIGGER_SUFFIX

    # A valid resource.Key type
    VALID_BUT_NOT_OUTLINE = resources_display.ResourceUnitBase.ASSESSMENT_TYPE

    CONTENT_INITIAL_AVAIL = courses.AVAILABILITY_COURSE

    CONTENT_TYPES = [
        resources_display.ResourceUnit.TYPE,
        resources_display.ResourceLesson.TYPE,
    ]

    def setUp(self):
        super(ContentTriggerTestsMixin, self).setUp()
        self.empty_form = {}

    def some_past_content_triggers(self, now, unit_id, lesson_id):
        when = self.utc_past_text(now)

        # Define a unit trigger and a lesson trigger somewhat in the past, to
        # insure that a cron job will act on them at test time.
        return [{
            'content': str(resource.Key('unit', unit_id)),
            'availability': courses.AVAILABILITY_AVAILABLE,
            'when': when,
        }, {
            'content': str(resource.Key('lesson', lesson_id)),
            'availability': courses.AVAILABILITY_UNAVAILABLE,
            'when': when,
        }]

    def some_future_content_triggers(self, now, unit_id, lesson_id):
        when = self.utc_future_text(now)

        # Define a unit trigger and a lesson trigger somewhat into the future,
        # so there is no chance that a cron task will act on them and remove
        # them from the course settings prematurely.
        return [{
            'content': str(resource.Key('unit', unit_id)),
            'availability': courses.AVAILABILITY_AVAILABLE,
            'when': when,
        }, {
            'content': str(resource.Key('lesson', lesson_id)),
            'availability': courses.AVAILABILITY_UNAVAILABLE,
            'when': when,
        }]

    def specific_bad_content_triggers(self, now, assessment_id, unit_id):
        past = self.utc_past_text(now)
        future = self.utc_future_text(now)

        # An empty content trigger, missing all of the required fields.
        empty = {}

        # A content trigger with completely bogus required field values.
        bad = {
            'content': self.BAD_CONTENT_KEY,
            'availability': self.BAD_CONTENT_AVAIL,
            'when': self.BAD_CONTENT_WHEN,
        }

        # Make sure believed-to-be-invalid type still is.
        self.assertNotIn(
            self.VALID_BUT_NOT_OUTLINE, self.TCT.ALLOWED_CONTENT_TYPES)

        # A content trigger with a valid, but not course outline, content type.
        unexpected = {
            'content': str(resource.Key(
                self.VALID_BUT_NOT_OUTLINE, assessment_id)),
            'availability': courses.AVAILABILITY_AVAILABLE,
            'when': past,
        }

        # A valid content trigger missing its associated course content. Also
        # checks that even a content trigger that is in the future is discarded
        # if faulty.
        missing = {
            'content': str(resource.Key('unit', "9999")),
            'availability': courses.AVAILABILITY_AVAILABLE,
            'when': future,
        }
        # Not really a bad content trigger, per se, but simply a no-op trigger,
        # because the result of acting on this trigger is no change in the
        # existing content availability.
        unchanged = {
            'content': str(resource.Key('unit', unit_id)),
            'availability': courses.AVAILABILITY_COURSE,
            'when': past,
        }
        return (empty, bad, unexpected, missing, unchanged)

    def default_availabilities(self, cls, availabilities):
        cls = cls if cls is not None else self.TCT
        availabilities = super(ContentTriggerTestsMixin,
            self).default_availabilities(cls, availabilities)
        return (availabilities if availabilities is not None
                else courses.AVAILABILITY_VALUES)  # Last resort.

    def default_content_types(self, cls, content_types):
        cls = cls if cls is not None else self.TCT

        if content_types is None:
            content_types = cls.ALLOWED_CONTENT_TYPES

        if content_types is None:
            content_types = self.CONTENT_TYPES

        return content_types

    def default_test_args(self, cls, availabilities, content_types):
        """Common default values for modules/courses ContentTriggerTests."""
        cls = cls if cls is not None else self.TCT
        availabilities = self.default_availabilities(cls, availabilities)
        content_types = self.default_content_types(cls, content_types)
        return cls, availabilities, content_types


class ContentTriggerTestBase(ContentTriggerTestsMixin, FunctionalTestBase):
    """Parameterized "test" methods with check_ names, used by subclasses.

    Many of the ContentTriggerTests test_ methods are delegated to the
    equivalent check_ methods in this ContentTriggerTestBase base class.
    This makes re-use of the test code by test_ methods in the
    student_groups.triggers_tests.ContentOverrideTriggerTests subclass
    possible. The check_ methods are parameterized for the differences between
    the modules/courses and modules/student_groups trigger implementations.
    """

    def setUp(self):
        FunctionalTestBase.setUp(self)
        ContentTriggerTestsMixin.setUp(self)

    def check_names(self, cls=None, availabilities=None, content_types=None):
        """Checks the name @property, logged @property, and __str__."""
        cls, availabilities, content_types = self.default_test_args(
            cls, availabilities, content_types)

        rsrc_id = 1
        for rsrc_type in content_types:
            found = resource.Key(rsrc_type, rsrc_id)
            self.assertTrue(found)
            content = str(found)

            for avail in availabilities:
                t = cls(when=self.txt_when, availability=avail,
                        content=content, found=found)
                expected_name = '{}~{}~{}'.format(
                    self.txt_when, avail, content)
                self.assertEquals(expected_name, t.name)
                self.assertEquals(expected_name, '{}'.format(t))
                expected_logged = '{}({}, {}, {})'.format(
                    t.typename(), self.txt_when, avail, content)
                self.assertEquals(expected_logged, t.logged)
                rsrc_id += 1

    NOT_IN_CONTENT_AVAILABILITY = [
        'registration_required', 'registration_optional',
    ]

    def check_availability(self, cls=None, availabilities=None):
        """Checks validate and encode with content availability values."""
        cls, availabilities, _ = self.default_test_args(
            cls, availabilities, None)

        for avail in availabilities:
            self.assertEquals(avail, cls.validate_availability(avail))
            self.assertEquals(avail, cls.encode_availability(avail))

        for avail in self.NOT_IN_CONTENT_AVAILABILITY:
            self.assertEquals(None, cls.validate_availability(avail))
            self.assertEquals(None, cls.encode_availability(avail))

    def check_is(self, cls=None, availabilities=None, content_types=None):
        """Checks is_valid, is_future, and is_ready."""
        cls, availabilities, content_types = self.default_test_args(
            cls, availabilities, content_types)

        invalid = cls()
        self.check_invalid_is(invalid)

        for avail in availabilities:
            valid = cls(when=self.txt_when, availability=avail)
            # TODO(tlarsen): need a course and some content.
            # self.check_valid_is(valid)

    def create_triggers(self, cls=None, availabilities=None,
                        content_types=None):
        cls, availabilities, content_types = self.default_test_args(
            cls, availabilities, content_types)

        expected_triggers = []
        content_id = 1

        for avail in availabilities:
            content_type = cls.validate_content_type(
                random.choice(content_types))
            self.assertTrue(content_type)
            content = cls.encode_content_type_and_id(content_type, content_id)
            self.assertTrue(content)

            expected_triggers.append({
                'when': self.txt_when,
                'availability': avail,
                'content': content,
            })
            content_id += 1

        return expected_triggers

    def create_payload_triggers(self, cls=None, availabilities=None,
                                content_types=None, payload=None):
        cls, availabilities, content_types = self.default_test_args(
            cls, availabilities, content_types)

        if payload is None:
            payload = {}

        payload_triggers = payload.setdefault('content_triggers', [])

        expected_triggers = self.create_triggers(
            cls=cls, availabilities=availabilities, content_types=content_types)

        # Copy each encoded trigger in the expected_triggers into the
        # payload, so that they are distinct dict objects.
        for et in expected_triggers:
            payload_triggers.append(et.copy())

        # No additional 'course:' settings expected for content triggers.
        expected_settings = {}

        return payload, expected_triggers, expected_settings


class ContentTriggerTests(ContentTriggerTestBase):
    """Tests the ContentTrigger class.

    The functional tests actions.TestBase is used, even though these tests
    are meant to be unit tests, to permit access to Course creation.
    """

    COURSE_NAME = 'content_trigger_test'

    def test_name_logged_str(self):
        self.check_names()

    def test_kind(self):
        self.assertEquals('content availability', self.TCT.kind())

    def settings_css(self):
        self.assertEquals('content-triggers', self.TCT.settings_css())

    def test_registry_css(self):
        self.assertEquals('content-trigger inputEx-Group inputEx-valid ' +
                          'inputEx-ListField-subFieldEl',
            self.TCT.registry_css())

    def test_array_css(self):
        self.assertEquals(
            'content-triggers inputEx-Field inputEx-ListField',
            self.TCT.array_css())

    def test_array_wrapper_css(self):
        self.assertEquals(
            'content-triggers section-with-heading inputEx-fieldWrapper',
            self.TCT.array_wrapper_css())

    def test_when_css(self):
        self.assertEquals(
            'when inputEx-required gcb-datetime inputEx-fieldWrapper',
            self.TCT.when_css())

    def test_content_css(self):
        self.assertEquals('content gcb-select inputEx-Field',
            self.TCT.content_css())

    def test_availability(self):
        self.check_availability()

    def test_validate(self):
        """Tests validate, validate_content, ..._type, ..._type_and_id."""
        content_id = 1

        for ct in self.CONTENT_TYPES:
            self.assertEquals(ct, self.TCT.validate_content_type(ct))
            content = self.TCT.validate_content_type_and_id(ct, content_id)
            self.assertTrue(content)
            content_id += 1

    def test_encode_content(self):
        """Tests encode_content, ..._type_and_id."""
        pass  # TODO(tlarsen)

    def test_encode(self):
        """Tests encode and encoded."""
        pass  # TODO(tlarsen)

    def test_decode(self):
        """Tests decode, decoded, type, id."""
        pass  # TODO(tlarsen)

    def test_is(self):
        self.check_is()

    def test_encoded_defaults(self):
        """Tests encoded_defaults for default content availability."""
        self.assertEquals(
            {'availability': courses.AVAILABILITY_UNAVAILABLE},
            self.TCT.encoded_defaults())

    def test_copy_from_settings(self):
        self.check_copy_from_settings(self.TCT, 'content_triggers')

    def test_in_settings(self):
        self.check_in_settings(self.TCT, 'content_triggers')

    def test_for_form(self):
        pass  # TODO(tlarsen)

    def test_payload_into_settings(self):
        self.check_payload_into_settings(self.TCT, 'content_triggers')

    def test_find(self):
        """Tests get_content_finder, find_content_in_course."""
        pass  # TODO(tlarsen)

    def test_act_on_settings(self):
        """Tests act_on_settings, act_on_triggers, log_acted_on, separate."""
        pass  # TODO(tlarsen)

    def test_typename(self):
        self.assertEquals('triggers.ContentTrigger', self.TCT.typename())


class MilestoneTriggerTestsMixin(TriggerTestsMixin):

    COURSE_INITIAL_AVAIL = courses.COURSE_AVAILABILITY_PRIVATE
    COURSE_START_AVAIL = courses.COURSE_AVAILABILITY_REGISTRATION_REQUIRED
    COURSE_END_AVAIL = courses.COURSE_AVAILABILITY_PUBLIC
    COURSE_UNUSED_AVAIL = courses.COURSE_AVAILABILITY_REGISTRATION_OPTIONAL

    TTMIX = TriggerTestsMixin

    BAD_MILESTONE_TRIGGER_SUFFIX = ' for a course start/end trigger'

    BAD_COURSE_WHEN = TTMIX.BAD_WHEN + BAD_MILESTONE_TRIGGER_SUFFIX
    BAD_COURSE_AVAIL = TTMIX.BAD_AVAIL + BAD_MILESTONE_TRIGGER_SUFFIX

    def setUp(self):
        super(MilestoneTriggerTestsMixin, self).setUp()
        self.past_start_text = self.utc_past_text(self.now)
        self.future_end_text = self.utc_future_text(self.now)

        self.defaults_start = self.TMT.encoded_defaults(
            availability=self.TMT.NONE_SELECTED,
            milestone=constants.START_DATE_MILESTONE)
        self.defaults_end = self.TMT.encoded_defaults(
            availability=self.TMT.NONE_SELECTED,
            milestone=constants.END_DATE_MILESTONE)

        self.course_start = self.past_course_start_trigger(self.now)
        self.course_end = self.future_course_end_trigger(self.now)

        # Some common expected course start/end pairs.
        self.course_start_and_end = {
            constants.START_DATE_MILESTONE: [self.course_start],
            constants.END_DATE_MILESTONE: [self.course_end],
        }
        self.only_course_start = {
            constants.START_DATE_MILESTONE: [self.course_start],
            # No course_end specified, so use default placeholder.
            constants.END_DATE_MILESTONE: [self.defaults_end],
        }
        self.only_course_end = {
            # No course_start specified, so use default placeholder.
            constants.START_DATE_MILESTONE: [self.defaults_start],
            constants.END_DATE_MILESTONE: [self.course_end],
        }
        self.defaults_only = {
            # Neither course_start nor course_end specified (placeholders).
            constants.START_DATE_MILESTONE: [self.defaults_start],
            constants.END_DATE_MILESTONE: [self.defaults_end],
        }

        # Course start/end availability triggers with cleared 'when' dates.
        self.empty_form = {
            constants.START_DATE_MILESTONE: [{
                self.TMT.FIELD_NAME: constants.START_DATE_MILESTONE,
                self.TAT.FIELD_NAME: self.TMT.NONE_SELECTED,
            }],
            constants.END_DATE_MILESTONE: [{
                self.TMT.FIELD_NAME: constants.END_DATE_MILESTONE,
                self.TAT.FIELD_NAME: self.TMT.NONE_SELECTED,
            }],
        }

        # Multiple test_act_hooks tests use these "two hours earlier" course
        # end POST parameters.
        self.an_earlier_end_hour_text = utc.to_text(
            seconds=utc.hour_start(self.now - (2 * 60 * 60)))
        self.an_earlier_course_end = {
            'availability': self.course_start['availability'],
            'milestone': constants.END_DATE_MILESTONE,
            'when': self.an_earlier_end_hour_text,
        }
        self.only_early_end = self.only_course_end.copy()
        self.only_early_end[
            constants.END_DATE_MILESTONE] = [self.an_earlier_course_end]

    @classmethod
    def past_course_start_trigger(cls, now):
        when = cls.utc_past_text(now)

        # Define a "course start" milestone trigger somewhat in the past, to
        # insure that that a cron job will apply it at test time.
        return {
            'milestone': constants.START_DATE_MILESTONE,
            'availability': cls.COURSE_START_AVAIL,
            'when': when,
        }

    @classmethod
    def future_course_end_trigger(cls, now):
        when = cls.utc_future_text(now)

        # Define a "course end" milestone trigger somewhat into the future, so
        # there is no chance that a cron task will act on it and remove it from
        # the course settings prematurely.
        return {
            'milestone': constants.END_DATE_MILESTONE,
            'availability': cls.COURSE_END_AVAIL,
            'when': when,
        }

    @classmethod
    def specific_bad_milestone_triggers(cls, now):
        past = cls.utc_past_text(now)
        when = {
            constants.START_DATE_MILESTONE: past,
            constants.END_DATE_MILESTONE: cls.utc_future_text(now),
        }

        bad_triggers = {}

        for milestone in cls.TMT.KNOWN_MILESTONES:
            # An empty milestone trigger, missing all of the required fields.
            empty = {}
            bad_triggers.setdefault(milestone, []).append(empty)

            # A milestone trigger with completely bogus required field values.
            bad = {
                'milestone': milestone,
                'availability': cls.BAD_COURSE_AVAIL,
                'when': cls.BAD_COURSE_WHEN,
            }
            bad_triggers[milestone].append(bad)

            # A milestone trigger with a valid 'availability' but no 'when',
            # indicating that this milestone trigger is cleared by the user.
            no_when = {
                'milestone': milestone,
                'availability': cls.COURSE_UNUSED_AVAIL,
            }
            bad_triggers[milestone].append(no_when)

            # A milestone trigger with a valid 'when' but no 'availability',
            # indicating that this milestone trigger is cleared by the user.
            no_avail = {
                'milestone': milestone,
                'when': when[milestone],
            }
            bad_triggers[milestone].append(no_avail)

            # A milestone trigger that results from selecting the 'none'
            # <option> in the availability <select>
            # ('--- change availability to ---').
            none_selected = {
                'milestone': milestone,
                'availability': triggers.MilestoneTrigger.NONE_SELECTED,
                'when': when[milestone],
            }
            bad_triggers[milestone].append(none_selected)

        return bad_triggers

    def check_course_start_end_dates(self, start_date, end_date, env):
        """Check start/end date settings are initially not present *at all*."""
        self.assertEquals(
            start_date, courses.Course.get_named_course_setting_from_environ(
                constants.START_DATE_SETTING, env))
        self.assertEquals(
            end_date, courses.Course.get_named_course_setting_from_environ(
                constants.END_DATE_SETTING, env))

    @classmethod
    def set_course_start_end_dates(cls, start_date, end_date, env, course):
        """Sets start/end dates in the env dict and save Course settings."""
        courses.Course.set_named_course_setting_in_environ(
            constants.START_DATE_SETTING, env, start_date)
        courses.Course.set_named_course_setting_in_environ(
            constants.END_DATE_SETTING, env, end_date)
        course.save_settings(env)

    @classmethod
    def clear_course_start_end_dates(cls, env, course):
        """Clears start/end dates in the env dict and save Course settings."""
        courses.Course.clear_named_course_setting_in_environ(
            constants.START_DATE_SETTING, env)
        courses.Course.clear_named_course_setting_in_environ(
            constants.END_DATE_SETTING, env)
        course.save_settings(env)

    def check_and_clear_milestone_course_setting(self, milestone, when,
                                                 settings, cls):
        setting_name = cls.MILESTONE_TO_SETTING.get(milestone)

        # Confirm corresponding setting or property is now the POST 'when'.
        self.assertEquals(
            cls.retrieve_named_setting(setting_name, settings), when)

        # Now remove that 'course:' setting, so the side-effects from act()
        # invoked by run_availability_jobs below can be confirmed.
        cls.clear_named_setting(setting_name, settings)
        self.assertNotEquals(
            cls.retrieve_named_setting(setting_name, settings), when)
        self.assertEquals(
            cls.retrieve_named_setting(setting_name, settings), None)

        # Confirm log activity for SET and corresponding CLEARED.
        logs = self.get_log()
        self.set_named_logged(milestone, setting_name, when, cls, logs)
        self.cleared_logged(milestone, setting_name, cls, logs)

    def run_availability_jobs(self, app_context):
        cron_job = availability_cron.UpdateAvailability(app_context)
        self.assertFalse(cron_job.is_active())
        cron_job.submit()
        self.execute_all_deferred_tasks()

    def default_availabilities(self, cls, availabilities):
        cls = cls if cls is not None else self.TMT
        availabilities = super(MilestoneTriggerTestsMixin,
            self).default_availabilities(cls, availabilities)
        return (availabilities if availabilities is not None
                else courses.COURSE_AVAILABILITY_VALUES)  # Last resort.

    def default_milestones(self, cls, milestones):
        cls = cls if cls is not None else self.TMT

        if milestones is None:
            milestones = cls.KNOWN_MILESTONES

        if milestones is None:
            milestones = constants.COURSE_MILESTONES  # Last resort.

        return milestones

    def default_test_args(self, cls, availabilities, milestones):
        """Common default values for modules/courses MilestoneTriggerTests."""
        cls = cls if cls is not None else self.TMT
        availabilities = self.default_availabilities(cls, availabilities)
        milestones = self.default_milestones(cls, milestones)
        return cls, availabilities, milestones

    def place_triggers_in_expected_order(self, triggers_list, cls,
                                         milestones=None):
        cls = cls if cls is not None else self.TMT
        field_name = cls.FIELD_NAME
        milestones = self.default_milestones(cls, milestones)
        in_order = []
        to_reorder = triggers_list  # Initially, no triggers are in order yet.

        for m in milestones:
            remaining = []
            for t in to_reorder:
                if t.get(field_name) == m:
                    # Found a known milestone, so add it in milestones order.
                    in_order.append(t)
                    # Keep looking, though, to gather all duplicate triggers
                    # matching the current milestone.
                else:
                    # This trigger does not match the current milestone.
                    remaining.append(t)

            to_reorder = remaining

        # Append any unknown milestones in original triggers_list order.
        in_order.extend(to_reorder)
        return in_order


class MilestoneTriggerTestBase(MilestoneTriggerTestsMixin, FunctionalTestBase):
    """Parameterized "test" methods with check_ names, used by subclasses.

    Many of the MilestoneTriggerTests test_ methods are delegated to the
    equivalent check_ methods in this MilestoneTriggerTestBase base class.
    This makes re-use of the test code by test_ methods in the
    student_groups.triggers_tests.CourseOverrideTriggerTests subclass
    possible. The check_ methods are parameterized for the differences between
    the modules/courses and modules/student_groups trigger implementations.
    """

    def setUp(self):
        FunctionalTestBase.setUp(self)
        MilestoneTriggerTestsMixin.setUp(self)

    def check_names(self, cls=None, availabilities=None, milestones=None):
        """Checks the name @property, logged @property, and __str__."""
        cls, availabilities, milestones = self.default_test_args(
            cls, availabilities, milestones)

        for m in milestones:
            for avail in availabilities:
                t = cls(when=self.txt_when, availability=avail, milestone=m)
                expected_name = '{}~{}~{}'.format(self.txt_when, avail, m)
                self.assertEquals(expected_name, t.name)
                self.assertEquals(expected_name, '{}'.format(t))
                expected_logged = '{}({}, {}, {})'.format(
                    t.typename(), self.txt_when, avail, m)
                self.assertEquals(expected_logged, t.logged)

    NOT_IN_COURSE_AVAILABILITY = [
        'course', 'none',
    ]

    def check_availability(self, cls=None, availabilities=None):
        """Checks validate and encode with course availability values."""
        cls, availabilities, _ = self.default_test_args(
            cls, availabilities, None)

        for avail in availabilities:
            self.assertEquals(avail, cls.validate_availability(avail))
            self.assertEquals(avail, cls.encode_availability(avail))

        for avail in self.NOT_IN_COURSE_AVAILABILITY:
            self.assertEquals(None, cls.validate_availability(avail))
            self.assertEquals(None, cls.encode_availability(avail))

    def check_milestone_validate(self, cls=None, availabilities=None,
                                 milestones=None):
        """Checks validate_milestone and validate."""
        cls, availabilities, milestones = self.default_test_args(
            cls, availabilities, milestones)

        self.assertEquals(None, cls.validate_milestone('invalid'))

        for m in milestones:
            self.assertEquals(m, cls.validate_milestone(m))

            for avail in availabilities:
                encoded = {
                    'milestone': m,
                    'availability': avail,
                    'when': self.txt_when,
                    'unused': 'ignored',
                }
                decoded_props = {
                    'milestone': m,
                    'availability': avail,
                    'when': self.dt_when,
                }
                self.check_validate(encoded, decoded_props, cls.validate)

    def check_encode_decode(self, cls=None, availabilities=None,
                            milestones=None):
        "ChecksTests encode_milestone, encode, encoded, decode, and decoded."""
        cls, availabilities, milestones = self.default_test_args(
            cls, availabilities, milestones)

        for m in milestones:
            self.assertEquals(m, cls.encode_milestone(m))

            for avail in availabilities:
                expected = {
                    'milestone': m,
                    'availability': avail,
                    'when': self.txt_when,
                }
                encoded_dict = cls.encode(
                    milestone=m, availability=avail, when=self.dt_when)
                self.assertEquals(encoded_dict, expected)

                decoded_mt = cls.decode(expected)
                self.assertEquals(decoded_mt.milestone, m)
                self.assertEquals(decoded_mt.availability, avail)
                self.assertEquals(decoded_mt.encoded, expected)

                constructed_mt = cls(
                    milestone=m, availability=avail, when=self.txt_when)
                self.assertEquals(constructed_mt.encoded, expected)
                decoded_dict = constructed_mt.decoded
                self.assertEquals(decoded_dict.get('milestone'), m)
                self.assertEquals(decoded_dict.get('availability'), avail)

    def check_is(self, cls=None, availabilities=None, milestones=None):
        """Checks is_valid, is_future, and is_ready."""
        cls, availabilities, milestones = self.default_test_args(
            cls, availabilities, milestones)

        invalid = cls()
        self.check_invalid_is(invalid)

        for m in milestones:
            for avail in availabilities:
                valid = cls(
                    milestone=m, when=self.txt_when, availability=avail)
                self.check_valid_is(valid)

    def create_triggers(self, cls=None, availabilities=None, milestones=None):
        cls, availabilities, milestones = self.default_test_args(
            cls, availabilities, milestones)

        expected_triggers = []

        # Create a randomly-shuffled copy that will be destructively altered.
        shuffled = list(availabilities)
        random.shuffle(shuffled)

        for m in milestones:
            avail = cls.validate_availability(shuffled.pop())
            self.assertTrue(avail)

            expected_triggers.append({
                'when': self.txt_when,
                'availability': avail,
                'milestone': m,
            })

        return expected_triggers

    def create_payload_triggers(self, cls=None, availabilities=None,
                                milestones=None, payload=None):
        cls, availabilities, milestones = self.default_test_args(
            cls, availabilities, milestones)

        if payload is None:
            payload = {}

        expected_triggers = self.create_triggers(
            cls=cls, availabilities=availabilities, milestones=milestones)

        expected_settings = {}

        # Copy each encoded trigger in the expected_triggers into the
        # payload, so that they are distinct dict objects.
        for et in expected_triggers:
            m = et['milestone']
            payload[m] = [et.copy()]

            # Some milestone triggers have a coresponding setting in the
            # Course get_environ() 'course' dict. If such a mapping from
            # trigger to setting exists, copy the 'when' date/time from the
            # trigger into the Course setting.
            setting = cls.MILESTONE_TO_SETTING.get(m)
            when = et.get('when')
            if setting and when:
                expected_settings.setdefault('course', {})[setting] = when

        return payload, expected_triggers, expected_settings


class MilestoneTriggerTests(MilestoneTriggerTestBase):
    """Tests the MilestoneTrigger class."""

    COURSE_NAME = 'milestone_trigger_test'

    def test_name_logged_str(self):
        self.check_names()

    def test_kind(self):
        self.assertEquals('course availability', self.TMT.kind())

    def settings_css(self):
        self.assertEquals('course-triggers', self.TMT.settings_css())

    def test_registry_css(self):
        self.assertEquals('course-trigger inputEx-Group inputEx-valid ' +
                          'inputEx-ListField-subFieldEl',
            self.TMT.registry_css())

    def test_array_css(self):
        self.assertEquals(
            'course-triggers inputEx-Field inputEx-ListField',
            self.TMT.array_css())

    def test_array_wrapper_css(self):
        self.assertEquals(
            'course-triggers inputEx-fieldWrapper',
            self.TMT.array_wrapper_css())

    def test_when_css(self):
        self.assertEquals(
            'when inputEx-Field gcb-datetime inputEx-fieldWrapper',
            self.TMT.when_css())

    def test_milestone_css(self):
        self.assertEquals('milestone', self.TMT.milestone_css())

    def test_availability(self):
        self.check_availability()

    def test_validate(self):
        self.check_milestone_validate()

    def test_encode_decode(self):
        self.check_encode_decode()

    def test_is(self):
        self.check_is()

    def test_encoded_defaults(self):
        """Tests encoded_defaults for default course availability."""
        # Some milestone value *must* be supplied as a keyword argument.
        self.assertEquals(None, self.TMT.encoded_defaults())

        expected = {
            'availability': availability_options.AVAILABILITY_NONE_SELECTED,
        }

        for km in self.TMT.KNOWN_MILESTONES:
            expected['milestone'] = km
            self.assertEquals(
                expected, self.TMT.encoded_defaults(milestone=km))

    def test_copy_from_settings(self):
        self.check_copy_from_settings(self.TMT, 'course_triggers')

    def test_in_settings(self):
        self.check_in_settings(self.TMT, 'course_triggers')

    def test_for_form(self):
        pass  # TODO(tlarsen)

    def test_payload_into_settings(self):
        self.check_payload_into_settings(self.TMT, 'course_triggers')

    def test_act_on_settings(self):
        """Tests act_on_settings, act_on_triggers, log_acted_on, separate."""
        pass  # TODO(tlarsen)

    def test_typename(self):
        self.assertEquals('triggers.MilestoneTrigger', self.TMT.typename())


class CronHackTests(actions.TestBase):

    COURSE_NAME = 'cron_hack_test'
    ADMIN_EMAIL = 'admin@example.com'

    def setUp(self):
        super(CronHackTests, self).setUp()
        self.app_context = actions.simple_add_course(
            self.COURSE_NAME, self.ADMIN_EMAIL, 'Cron Hack Test')
        self.save_seconds_per_hour = utc._SECONDS_PER_HOUR
        utc._SECONDS_PER_HOUR = 10

        # Avoid test flakes: If we are in a second that is at the end of
        # an hour, walk time forward until we are cleanly in the next
        # hour, so that we do not accidentally slip across the hour
        # boundary during the run of the test.  This is particularly
        # important, since we are redefining "hours" to be 10 seconds
        # so tests finish in reasonable amounts of time.
        now_ts = utc.now_as_timestamp()
        hour_end_ts = utc.hour_end(now_ts)
        if now_ts == hour_end_ts:
            time.sleep(1)

    def tearDown(self):
        sites.reset_courses()
        utc._SECONDS_PER_HOUR = self.save_seconds_per_hour
        super(CronHackTests, self).tearDown()

    def _assert_job_state(self, is_active):
        job = availability_cron.UpdateAvailability(self.app_context)
        self.assertEquals(is_active, job.is_active())

    def _assert_status_time_is_top_of_current_hour(self):
        now_ts = utc.hour_start(utc.now_as_timestamp())
        status = availability_cron.StartAvailabilityJobsStatus.get_singleton()
        last_run_ts = utc.datetime_to_timestamp(status.last_run)
        self.assertEqual(now_ts, last_run_ts)

    def test_start_jobs_with_no_existing_status_row(self):
        availability_cron.StartAvailabilityJobs.maybe_start_jobs()
        self._assert_job_state(is_active=True)
        self._assert_status_time_is_top_of_current_hour()

    def test_start_jobs_with_existing_status_in_past(self):
        status = availability_cron.StartAvailabilityJobsStatus.get_singleton()
        old_timestamp = utc.now_as_timestamp() - utc._SECONDS_PER_HOUR
        status.last_run = utc.timestamp_to_datetime(old_timestamp)
        availability_cron.StartAvailabilityJobsStatus.update_singleton(status)

        availability_cron.StartAvailabilityJobs.maybe_start_jobs()
        self._assert_job_state(is_active=True)
        self._assert_status_time_is_top_of_current_hour()

    def test_start_jobs_with_existing_status_current(self):
        status = availability_cron.StartAvailabilityJobsStatus.get_singleton()
        old_timestamp = utc.now_as_timestamp()
        status.last_run = utc.timestamp_to_datetime(old_timestamp)
        availability_cron.StartAvailabilityJobsStatus.update_singleton(status)

        availability_cron.StartAvailabilityJobs.maybe_start_jobs()
        self._assert_job_state(is_active=None)  # None => never run.

    def test_get_of_cron_url_starts_deferred_job(self):
        self.get(availability_cron.StartAvailabilityJobs.URL)

        # Execute only one step, so only the StartAvailabilityJobs callback
        # runs; we don't want UpdateAvailability to also run.
        self.execute_all_deferred_tasks(iteration_limit=1)

        # Verify we requested job start and updated status.
        self._assert_job_state(is_active=True)
        self._assert_status_time_is_top_of_current_hour()

    def test_many_gets_to_cron_url_are_harmless(self):
        self.get(availability_cron.StartAvailabilityJobs.URL)
        self.get(availability_cron.StartAvailabilityJobs.URL)
        self.get(availability_cron.StartAvailabilityJobs.URL)
        self.get(availability_cron.StartAvailabilityJobs.URL)
        self.get(availability_cron.StartAvailabilityJobs.URL)

        # We should really have five items on the deferred queue; one for
        # each GET.
        tasks = self.taskq.GetTasks('default')
        self.assertEquals(5, len(tasks))

        # Start 1st availability job; it should enqueue the UpdateAvailability.
        self.execute_all_deferred_tasks(iteration_limit=1)
        self._assert_job_state(is_active=True)
        self._assert_status_time_is_top_of_current_hour()

        # Run one more task; we now expect to see is_active=False, meaning
        # done.
        self.execute_all_deferred_tasks(iteration_limit=1)
        self._assert_job_state(is_active=False)

        # This is weird; looks like deferred queue is smart enough to
        # deduplicate our extra items - we now have _no_ items pending.
        tasks = self.taskq.GetTasks('default')
        self.assertEquals(0, len(tasks))

        # Let's throw some more wood on that fire - pretend cron goes nuts
        # and drops many more to-do items in.
        self.get(availability_cron.StartAvailabilityJobs.URL)
        self.get(availability_cron.StartAvailabilityJobs.URL)
        self.get(availability_cron.StartAvailabilityJobs.URL)
        self.get(availability_cron.StartAvailabilityJobs.URL)
        self.get(availability_cron.StartAvailabilityJobs.URL)

        # Since we have already run the UpdateAvailability job once this
        # hour, we expect that calling maybe_start_jobs from the deferred
        # handler will not start UpdateAvailability again.
        self.execute_all_deferred_tasks(iteration_limit=1)
        self._assert_job_state(is_active=False)

        # And again, we're deduped.
        tasks = self.taskq.GetTasks('default')
        self.assertEquals(0, len(tasks))
