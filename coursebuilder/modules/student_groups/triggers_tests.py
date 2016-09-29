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

from modules.courses import triggers_tests
from modules.student_groups import student_groups


class OverrideTriggerTestsMixin(object):

    def check_copy_from_student_group(self, cls, settings_name):
        # copy_from_settings() has no side-effects on the supplied settings.
        the_dict = {}
        sg = student_groups.StudentGroupDTO(self.COURSE_NAME, the_dict)
        self.assertEquals([], cls.copy_from_settings(sg))
        self.assertFalse(settings_name in the_dict)

        expected_triggers = self.create_triggers()

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

        expected_triggers = self.create_triggers()

        # Copy each encoded trigger in the expected_triggers into the
        # StudentGroupDTO property, so that they are distinct dict objects.
        sg.set_triggers(
            settings_name, [et.copy() for et in expected_triggers])
        self.assertTrue(settings_name in the_dict)
        self.assertItemsEqual(expected_triggers, cls.in_settings(sg))

    def check_payload_into_student_group(self, cls, settings_name):
        """Checks payload_into_settings, from_payload, set_into_settings."""
        payload, triggers, settings = self.create_payload_triggers(cls=cls,
            availabilities=cls.AVAILABILITY_VALUES)
        properties = {settings_name: triggers}
        # Course start/end date/time settings in the 'course' dict of the
        # Course settings map to StudentGroupDTO properties of the same name.
        for setting, when in settings.get('course', {}).iteritems():
            properties[setting] = when
        expected_group = student_groups.StudentGroupDTO(
            self.COURSE_NAME, properties)
        the_dict = {}
        sg = student_groups.StudentGroupDTO(self.COURSE_NAME, the_dict)
        cls.payload_into_settings(payload, self.course, sg)

        # Order should not matter, but the way the triggers values are
        # generated, for some trigger test classes, they are in fact in
        # a particular order (e.g. in KNOWN_MILESTONE order).
        self.assertItemsEqual(triggers, sg.get_triggers(settings_name))
        self.assertItemsEqual(triggers, the_dict[settings_name])

        # So, place the potentially non-ordered results in that order before
        # comparing nested structures that contain them.
        not_in_order = sg.get_triggers(settings_name)
        in_order = self.place_triggers_in_expected_order(not_in_order, cls)
        sg.set_triggers(settings_name, in_order)

        self.assertEquals(expected_group.dict, sg.dict)

        # Absent from payload should remove from settings. Use student_group
        # created above, since it will have properties needing removal
        # (start_date and end_date).
        cls.payload_into_settings(self.empty_form, self.course, sg)
        # Property is always present in StudentGroupDTO, but as empty list.
        self.assertEquals({settings_name: []}, sg.dict)
        self.assertEquals([], sg.get_triggers(settings_name))
        self.assertEquals([], the_dict[settings_name])


class ContentOverrideTriggerTests(OverrideTriggerTestsMixin,
                                  triggers_tests.ContentTriggerTestBase):
    """Tests the ContentOverrideTrigger class."""

    COURSE_NAME = 'content_override_trigger_test'

    sg_content_ot = student_groups.ContentOverrideTrigger

    def test_name_logged_str(self):
        self.check_names(cls=self.sg_content_ot,
            availabilities=self.sg_content_ot.AVAILABILITY_VALUES)

    def test_kind(self):
        self.assertEqual('content availability override',
                         self.sg_content_ot.kind())

    def test_availability(self):
        self.check_availability(cls=self.sg_content_ot,
            availabilities=self.sg_content_ot.AVAILABILITY_VALUES)

    def test_is(self):
        self.check_is(cls=self.sg_content_ot,
            availabilities=self.sg_content_ot.AVAILABILITY_VALUES)

    def test_copy_from_settings(self):
        self.check_copy_from_student_group(
            self.sg_content_ot, 'content_triggers')

    def test_in_settings(self):
        self.check_in_student_group(
            self.sg_content_ot, 'content_triggers')

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

    sg_course_ot = student_groups.CourseOverrideTrigger

    def test_name_logged_str(self):
        self.check_names(cls=self.sg_course_ot,
            availabilities=self.sg_course_ot.AVAILABILITY_VALUES)

    def test_kind(self):
        self.assertEqual('course availability override',
                         self.sg_course_ot.kind())

    def test_availability(self):
        self.check_availability(cls=self.sg_course_ot,
            availabilities=self.sg_course_ot.AVAILABILITY_VALUES)

    def test_validate(self):
        self.check_milestone_validate(cls=self.sg_course_ot,
            availabilities=self.sg_course_ot.AVAILABILITY_VALUES)

    def test_encode_decode(self):
        self.check_encode_decode(cls=self.sg_course_ot,
            availabilities=self.sg_course_ot.AVAILABILITY_VALUES)

    def test_is(self):
        self.check_is(cls=self.sg_course_ot,
            availabilities=self.sg_course_ot.AVAILABILITY_VALUES)

    def test_copy_from_settings(self):
        self.check_copy_from_student_group(
            self.sg_course_ot, 'course_triggers')

    def test_in_settings(self):
        self.check_in_student_group(
            self.sg_course_ot, 'course_triggers')

    def test_payload_into_settings(self):
        self.check_payload_into_student_group(
            self.sg_course_ot, 'course_triggers')

    def test_act_on_settings(self):
        """Tests act_on_settings, act_on_triggers, log_acted_on, separate."""
        pass # TODO(tlarsen)

    def test_typename(self):
        self.assertEqual('student_groups.CourseOverrideTrigger',
                         self.sg_course_ot.typename())
