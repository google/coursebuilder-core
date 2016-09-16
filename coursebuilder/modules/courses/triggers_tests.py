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
import random
import unittest

from common import resource
from common import utc
from models import courses
from models import resources_display
from modules.courses import availability_options
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

    def setUp(self):
        self.dt_when = utc.now_as_datetime()
        self.txt_when = utc.to_text(dt=self.dt_when)
        self.maxDiff = None

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

    NOW_DELTA = datetime.timedelta(seconds=1)

    def check_valid_is(self, valid):
        self.assertTrue(valid.is_valid)

        now_in_past = self.dt_when - self.NOW_DELTA
        self.assertTrue(valid.is_future(now=now_in_past))
        self.assertFalse(valid.is_ready(now=now_in_past))

        now_in_future = self.dt_when + self.NOW_DELTA
        self.assertFalse(valid.is_future(now=now_in_future))
        self.assertTrue(valid.is_ready(now=now_in_future))


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
        payload, expected = self.create_payload_triggers()
        expected_settings = {'publish': {settings_name: expected}}
        settings = {}
        cls.payload_into_settings(payload, self.course, settings)
        self.assertItemsEqual(expected_settings, settings)

        # Absent from payload should remove from settings. Use settings dict
        # from above, since it will have contents to remove.
        cls.payload_into_settings({}, self.course, settings)
        empty_settings = {'publish': {}}
        self.assertEquals(empty_settings, settings)
        self.assertFalse(settings['publish'].get(settings_name))


class ContentTriggerTestBase(FunctionalTestBase):
    """Parameterized "test" methods with check_ names, used by subclasses.

    Many of the ContentTriggerTests test_ methods are delegated to the
    equivalent check_ methods in this ContentTriggerTestBase base class.
    This makes re-use of the test code by test_ methods in the
    student_groups.triggers_tests.ContentOverrideTriggerTests subclass
    possible. The check_ methods are parameterized for the differences between
    the modules/courses and modules/student_groups trigger implementations.
    """

    CONTENT_TYPES = [
        resources_display.ResourceUnit.TYPE,
        resources_display.ResourceLesson.TYPE,
    ]

    def default_test_args(self, cls, availabilities, content_types):
        """Common default values for modules/courses ContentTriggerTests."""
        if cls is None:
            cls = self.TCT

        if availabilities is None:
            availabilities = courses.AVAILABILITY_VALUES

        if content_types is None:
            content_types = self.CONTENT_TYPES

        return cls, availabilities, content_types

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

        return payload, expected_triggers


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


class MilestoneTriggerTestBase(FunctionalTestBase):
    """Parameterized "test" methods with check_ names, used by subclasses.

    Many of the MilestoneTriggerTests test_ methods are delegated to the
    equivalent check_ methods in this MilestoneTriggerTestBase base class.
    This makes re-use of the test code by test_ methods in the
    student_groups.triggers_tests.CourseOverrideTriggerTests subclass
    possible. The check_ methods are parameterized for the differences between
    the modules/courses and modules/student_groups trigger implementations.
    """

    def default_test_args(self, cls, availabilities, milestones):
        """Common default values for modules/courses MilestoneTriggerTests."""
        if cls is None:
            cls = self.TMT

        if availabilities is None:
            availabilities = courses.COURSE_AVAILABILITY_VALUES

        if milestones is None:
            milestones = self.TMT.KNOWN_MILESTONES

        return cls, availabilities, milestones

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

        # Copy each encoded trigger in the expected_triggers into the
        # payload, so that they are distinct dict objects.
        for et in expected_triggers:
            payload[et['milestone']] = [et.copy()]

        return payload, expected_triggers


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
