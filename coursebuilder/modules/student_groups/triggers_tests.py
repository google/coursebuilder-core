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

"""Unit tests for modules/student_groups/triggers."""

__author__ = 'Todd Larsen (tlarsen@google.com)'

import copy

from common import utils
from modules.courses import triggers_tests
from modules.student_groups import student_groups


class OverrideTriggerTestsMixin(object):

    def check_copy_from_student_group(self, cls, settings_name):
        # copy_from_settings() has no side-effects on the supplied settings.
        the_dict = {}
        sg = student_groups.StudentGroupDTO(self.COURSE_NAME, the_dict)
        self.assertEquals([], cls.copy_from_settings(sg))
        self.assertFalse(settings_name in the_dict)

        expected_triggers = self.create_triggers(cls)

        # Copy each encoded trigger in the expected_triggers into the
        # StudentGroupDTO property, so that they are distinct dict objects.
        sg.set_triggers(
            settings_name, [et.copy() for et in expected_triggers])
        self.assertTrue(settings_name in the_dict)
        self.assertItemsEqual(expected_triggers, cls.copy_from_settings(sg))

    def check_in_student_group(self, cls, settings_name):
        # in_settings() has side-effects on the supplied settings if empty.
        the_dict = {}
        sg = student_groups.StudentGroupDTO(self.COURSE_NAME, the_dict)
        self.assertEquals([], cls.in_settings(sg))
        self.assertTrue(settings_name in the_dict)

        expected_triggers = self.create_triggers(cls)

        # Copy each encoded trigger in the expected_triggers into the
        # StudentGroupDTO property, so that they are distinct dict objects.
        sg.set_triggers(
            settings_name, [et.copy() for et in expected_triggers])
        self.assertTrue(settings_name in the_dict)
        self.assertItemsEqual(expected_triggers, cls.in_settings(sg))

    def create_payload_triggers(self, cls, availabilities=None, payload=None):
        payload, expected_triggers, env = self.BASE.create_payload_triggers(
            self, cls, availabilities=availabilities, payload=payload)
        properties = {cls.SETTINGS_NAME: expected_triggers}
        # Course start/end date/time settings in the 'course' dict of the
        # Course settings map to StudentGroupDTO properties of the same name.
        for setting, when in env.get('course', {}).iteritems():
            properties[setting] = when
        expected_group = student_groups.StudentGroupDTO(
            self.COURSE_NAME, properties)
        return payload, expected_triggers, expected_group

    def check_payload_into_student_group(self, cls, settings_name):
        """Checks payload_into_settings, from_payload, set_into_settings."""
        payload, expected_triggers, expected = self.create_payload_triggers(
            cls, availabilities=cls.AVAILABILITY_VALUES)
        the_dict = {}
        sg = student_groups.StudentGroupDTO(self.COURSE_NAME, the_dict)
        cls.payload_into_settings(payload, self.course, sg)

        # Order should not matter, but the way the triggers values are
        # generated, for some trigger test classes, they are in fact in
        # a particular order (e.g. in KNOWN_MILESTONE order).
        self.assertItemsEqual(expected_triggers,
                              sg.get_triggers(settings_name))
        self.assertItemsEqual(expected_triggers,
                              the_dict[settings_name])

        # So, place the potentially non-ordered results in that order before
        # comparing nested structures that contain them.
        not_in_order = sg.get_triggers(settings_name)
        in_order = self.place_triggers_in_expected_order(not_in_order, cls)
        sg.set_triggers(settings_name, in_order)

        self.assertEquals(expected.dict, sg.dict)

        # Absent from payload should remove from settings. Use student_group
        # created above, since it will have properties needing removal
        # (start_date and end_date).
        cls.payload_into_settings(self.empty_form, self.course, sg)
        # Property is always obtained from StudentGroupDTO, but as empty list.
        self.assertEquals([], sg.get_triggers(settings_name))
        # Even when not actually stored as an empty list inside the DTO.
        self.assertEquals({settings_name: []}, sg.dict)
        self.assertEquals([], the_dict.get(settings_name))


class ContentOverrideTriggerTests(OverrideTriggerTestsMixin,
                                  triggers_tests.ContentTriggerTestBase):
    """Tests the ContentOverrideTrigger class."""

    COURSE_NAME = 'content_override_trigger_test'

    sg_content_ot = student_groups.ContentOverrideTrigger
    BASE = triggers_tests.ContentTriggerTestBase

    def test_name_logged_str(self):
        self.check_names(self.sg_content_ot,
            availabilities=self.sg_content_ot.AVAILABILITY_VALUES)

    def test_kind(self):
        self.assertEqual('content availability override',
                         self.sg_content_ot.kind())

    def test_availability(self):
        self.check_availability(self.sg_content_ot,
            availabilities=self.sg_content_ot.AVAILABILITY_VALUES)

    def test_is(self):
        self.check_is(self.sg_content_ot,
            availabilities=self.sg_content_ot.AVAILABILITY_VALUES)

    def test_encoded_defaults(self):
        self.check_encoded_defaults(self.sg_content_ot)

    def test_copy_from_settings(self):
        self.check_copy_from_student_group(
            self.sg_content_ot, 'content_triggers')

    def test_in_settings(self):
        self.check_in_student_group(
            self.sg_content_ot, 'content_triggers')

    def test_for_form(self):
        empty_sg = student_groups.StudentGroupDTO(self.COURSE_NAME, {})
        all_sg = student_groups.StudentGroupDTO(self.COURSE_NAME, {})
        self.check_for_form(self.sg_content_ot, empty_sg, all_sg)

    def test_from_payload(self):
        self.check_from_payload(self.sg_content_ot, 'content_triggers')

    def test_payload_into_settings(self):
        self.check_payload_into_student_group(
            self.sg_content_ot, 'content_triggers')

    def test_act_on_settings(self):
        """Tests act_on_settings, act_on_triggers, log_acted_on, separate."""
        pass # TODO(tlarsen)

    def test_typename(self):
        self.assertEqual('student_groups.ContentOverrideTrigger',
                         self.sg_content_ot.typename())


class CourseOverrideTriggerTests(OverrideTriggerTestsMixin,
                                 triggers_tests.MilestoneTriggerTestBase):
    """Tests the CourseOverrideTrigger class."""

    COURSE_NAME = 'course_override_trigger_test'
    NAMESPACE = 'ns_{}'.format(COURSE_NAME)

    sg_course_ot = student_groups.CourseOverrideTrigger
    BASE = triggers_tests.MilestoneTriggerTestBase

    @property
    def _empty_sg(self):
        return student_groups.StudentGroupDTO(self.COURSE_NAME, {
            'course_triggers': [],
        })

    @property
    def _dates_sg(self):
        return student_groups.StudentGroupDTO(self.COURSE_NAME, {
            'start_date': self.past_hour_text,
            'end_date': self.next_hour_text,
        })

    @property
    def _all_sg(self):
        return student_groups.StudentGroupDTO(self.COURSE_NAME, {
            'course_triggers': [],
            'start_date': self.past_hour_text,
            'end_date': self.next_hour_text,
        })
    def test_name_logged_str(self):
        self.check_names(self.sg_course_ot,
            availabilities=self.sg_course_ot.AVAILABILITY_VALUES)

    def test_kind(self):
        self.assertEqual('course availability override',
                         self.sg_course_ot.kind())

    def test_availability(self):
        self.check_availability(self.sg_course_ot,
            availabilities=self.sg_course_ot.AVAILABILITY_VALUES)

    def test_validate(self):
        self.check_milestone_validate(self.sg_course_ot,
            availabilities=self.sg_course_ot.AVAILABILITY_VALUES)

    def test_encode_decode(self):
        self.check_encode_decode(self.sg_course_ot,
            availabilities=self.sg_course_ot.AVAILABILITY_VALUES)

    def test_is(self):
        self.check_is(self.sg_course_ot,
            availabilities=self.sg_course_ot.AVAILABILITY_VALUES)

    def test_encoded_defaults(self):
        self.check_encoded_defaults(self.sg_course_ot, self._all_sg)

    def test_copy_from_settings(self):
        self.check_copy_from_student_group(
            self.sg_course_ot, 'course_triggers')

    def test_in_settings(self):
        self.check_in_student_group(
            self.sg_course_ot, 'course_triggers')

    def test_for_form(self):
        self.check_for_form(self.sg_course_ot,
            self._empty_sg, self._all_sg, self._dates_sg)

    def expected_updated_settings(self, cls, payload, settings, expected):
        altered = copy.deepcopy(settings)

        with utils.Namespace(self.NAMESPACE):
            cls.payload_into_settings(payload, self.course, altered)

        self.assertEquals(expected.dict, altered.dict)
        return altered

    def test_from_payload(self):
        self.check_from_payload(self.sg_course_ot, 'course_triggers')
                                #empty_triggers=[{}, {}])

    def test_incomplete_payloads_into_settings(self):
        self.check_incomplete_payloads_into_settings(
            self.sg_course_ot, self._all_sg, self._empty_sg, self._dates_sg,
            never_cleared=True)

    def test_payload_into_settings(self):
        self.check_payload_into_student_group(
            self.sg_course_ot, 'course_triggers')

    def test_act_on_settings(self):
        """Tests act_on_settings, act_on_triggers, log_acted_on, separate."""
        pass # TODO(tlarsen)

    def test_typename(self):
        self.assertEqual('student_groups.CourseOverrideTrigger',
                         self.sg_course_ot.typename())
