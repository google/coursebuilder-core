# coding: utf-8
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

"""Integration tests for all-courses integration tests for Course Builder."""

__author__ = [
    'Mike Gainer (mgainer@google.com)'
]

import copy
import re
import time

from selenium.common import exceptions

from models import courses
from modules.admin import admin_pageobjects
from modules.admin import enrollments
from modules.courses import courses_pageobjects
from tests.integration import integration


class _CoursesListTestBase(integration.TestBase):

    SAVED_STATUS = 'Saved.'

    def load_courses_list(self, cls=admin_pageobjects.CoursesListPage):
        return super(_CoursesListTestBase, self).load_courses_list(cls=cls)

    def setUp(self):
        super(_CoursesListTestBase, self).setUp()
        self.login(self.LOGIN, admin=True)


class CourseAdministrationTests(_CoursesListTestBase):

    def test_course_selection_checkboxes(self):
        """Verify select-all and course-select checkboxes affect one other."""

        course_name_one = self.create_new_course(login=False)[0]
        course_namespace_one = 'ns_' + course_name_one

        course_name_two = self.create_new_course(login=False)[0]
        course_namespace_two = 'ns_' + course_name_two

        course_list = self.load_courses_list()

        # On page load, all selections off.
        course_list.verify_all_courses_checkbox_checked(False)
        course_list.verify_all_courses_checkbox_indeterminate(False)
        course_list.verify_course_checkbox_checked(course_namespace_one, False)
        course_list.verify_course_checkbox_checked(course_namespace_two, False)

        # Select course one.  all-courses should now be indeterminate.
        course_list.toggle_course_checkbox(course_namespace_one)
        course_list.verify_all_courses_checkbox_indeterminate(True)
        course_list.verify_course_checkbox_checked(course_namespace_one, True)
        course_list.verify_course_checkbox_checked(course_namespace_two, False)

        # Select course two and unselect course one.
        # All-courses should still be indeterminate.
        course_list.toggle_course_checkbox(course_namespace_two)
        course_list.toggle_course_checkbox(course_namespace_one)
        course_list.verify_all_courses_checkbox_indeterminate(True)
        course_list.verify_course_checkbox_checked(course_namespace_one, False)
        course_list.verify_course_checkbox_checked(course_namespace_two, True)

        # Unselect course two.  all-courses should be determinate and off.
        course_list.toggle_course_checkbox(course_namespace_two)
        course_list.verify_all_courses_checkbox_indeterminate(False)
        course_list.verify_all_courses_checkbox_checked(False)
        course_list.verify_course_checkbox_checked(course_namespace_one, False)
        course_list.verify_course_checkbox_checked(course_namespace_two, False)

        # With none selected, click all-courses checkbox; all should select.
        course_list.toggle_all_courses_checkbox()
        course_list.verify_all_courses_checkbox_indeterminate(False)
        course_list.verify_all_courses_checkbox_checked(True)
        course_list.verify_course_checkbox_checked(course_namespace_one, True)
        course_list.verify_course_checkbox_checked(course_namespace_two, True)

        # With all selected, click all-courses checkbox; all should deselect
        course_list.toggle_all_courses_checkbox()
        course_list.verify_all_courses_checkbox_indeterminate(False)
        course_list.verify_all_courses_checkbox_checked(False)
        course_list.verify_course_checkbox_checked(course_namespace_one, False)
        course_list.verify_course_checkbox_checked(course_namespace_two, False)

        # Select one course so all-courses is indeterminate.
        course_list.toggle_course_checkbox(course_namespace_one)
        course_list.verify_all_courses_checkbox_indeterminate(True)
        course_list.verify_course_checkbox_checked(course_namespace_one, True)
        course_list.verify_course_checkbox_checked(course_namespace_two, False)

        # With all-courses indeterminate, clicking sets all.
        course_list.toggle_all_courses_checkbox()
        course_list.verify_all_courses_checkbox_indeterminate(False)
        course_list.verify_all_courses_checkbox_checked(True)
        course_list.verify_course_checkbox_checked(course_namespace_one, True)
        course_list.verify_course_checkbox_checked(course_namespace_two, True)


class CourseMultiEditSimpleTests(_CoursesListTestBase):
    """Multi-edit tests that don't require multiple courses."""

    def test_multi_edit_cancel(self):
        course_name = self.create_new_course(login=False)[0]
        course_namespace = 'ns_' + course_name
        course_list = self.load_courses_list()
        course_list.toggle_course_checkbox(course_namespace)
        multi_edit = course_list.click_edit_availability()

        multi_edit.find_element_by_id('multi-course-edit-panel')
        multi_edit.click_cancel()
        with self.assertRaises(exceptions.NoSuchElementException):
            multi_edit.find_element_by_id('multi-course-edit-panel',
                                          pre_wait=False)

    def test_multi_edit_single_course(self):
        course_name = self.create_new_course(login=False)[0]
        course_namespace = 'ns_' + course_name
        course_list = self.load_courses_list()

        course_list.toggle_course_checkbox(course_namespace)
        multi_edit = course_list.click_edit_availability()
        multi_edit.set_availability(
            courses.COURSE_AVAILABILITY_POLICIES[
                courses.COURSE_AVAILABILITY_PUBLIC]['title'])
        multi_edit.click_save()
        multi_edit.assert_status(course_namespace, self.SAVED_STATUS)
        multi_edit.expect_status_message_to_be(
            'Updated settings in 1 course.')
        course_list = multi_edit.click_cancel()

        # Course still should be checked on main list.
        course_list.verify_course_checkbox_checked(course_namespace, True)

        # Main list also should have been marked Public
        course_list.verify_availability(
            course_namespace, courses.COURSE_AVAILABILITY_POLICIES[
                courses.COURSE_AVAILABILITY_PUBLIC]['title'])

        # Refresh page and verify that course is still public.
        course_list = self.load_courses_list()
        course_list.verify_availability(
            course_namespace, courses.COURSE_AVAILABILITY_POLICIES[
                courses.COURSE_AVAILABILITY_PUBLIC]['title'])


class CourseMultiEditTests(_CoursesListTestBase):

    NUM_COURSES = 3

    def setUp(self):
        super(CourseMultiEditTests, self).setUp()
        for x in xrange(self.NUM_COURSES):
            self.create_new_course(login=False)
        self.maxDiff = None

    def _get_courses_availability_from_settings(self):
        ret = {}
        page = courses_pageobjects.CourseAvailabilityPage(self)
        for course_namespace in self.course_namespaces:
            stub = re.sub('^ns_', '', course_namespace)
            page.load(stub)
            ret[course_namespace] = page.get_settings()
        return ret

    def _get_course_availability_from_settings(self, course_namespace):
        page = courses_pageobjects.CourseAvailabilityPage(self)
        stub = re.sub('^ns_', '', course_namespace)
        page.load(stub)
        return page.get_settings()

    def test_multi_edit_multiple_courses(self):
        course_list = self.load_courses_list()
        for course_namespace in self.course_namespaces[0:-1]:
            course_list.toggle_course_checkbox(course_namespace)

        multi_edit = course_list.click_edit_availability()

        # Verify that the starting value in the dialog has been copied from
        # the page.
        for course_namespace in self.course_namespaces[0:-1]:
            self.assertEquals(
                'Private',
                multi_edit.get_current_value_for(course_namespace))

        availability = courses.COURSE_AVAILABILITY_POLICIES[
            courses.COURSE_AVAILABILITY_REGISTRATION_REQUIRED]['title']
        multi_edit.set_availability(availability)
        multi_edit.click_save()
        multi_edit.expect_status_message_to_be(
            'Updated settings in %d courses.' %
            (self.NUM_COURSES - 1))

        # Verify that the value has been updated in the dialog.
        for course_namespace in self.course_namespaces[0:-1]:
            multi_edit.assert_status(course_namespace, self.SAVED_STATUS)
            self.assertEquals(
                availability,
                multi_edit.get_current_value_for(course_namespace))

        # Verify content on course list page has changed for altered courses,
        # and has _not_ changed for non-affected ones.
        for course_namespace in self.course_namespaces[0:-1]:
            course_list.verify_availability(course_namespace, availability)
        for course_namespace in self.course_namespaces[-1:]:
            course_list.verify_availability(course_namespace, 'Private')

        # Attempt to set courses to Private, but with an error that
        # will prevent that from actually happening.
        multi_edit.set_availability(
            courses.COURSE_AVAILABILITY_POLICIES[
                courses.COURSE_AVAILABILITY_PRIVATE]['title'])

        multi_edit.set_availability_xsrf_token('not a valid token')
        multi_edit.click_save()
        for course_namespace in self.course_namespaces[0:-1]:
            multi_edit.assert_status(
                course_namespace,
                'Bad XSRF token. Please reload the page and try again')
            course_list.verify_availability(course_namespace, availability)
        multi_edit.expect_status_message_to_be(
            'Updated settings in 0 courses and had %d errors.' %
            (self.NUM_COURSES - 1))

    def _test_multi_edit_date_fails_safe(self, multi_edit):
        # Field should not be marked invalid on open of dialog
        self.assertFalse(multi_edit.is_availability_marked_invalid())
        self.assertFalse(multi_edit.is_date_time_marked_invalid())

        # Save button should be disbled until clear/save radio is selected.
        self.assertFalse(multi_edit.get_save_button_is_enabled())
        multi_edit.click_set_value_radio()
        self.assertTrue(multi_edit.get_save_button_is_enabled())

        # Save with no changes should mark field invalid.
        multi_edit.click_save_expecting_validation_failure()
        self.assertTrue(multi_edit.is_date_time_marked_invalid())

        # Pick a date.  Invalid marker should go away.  Give background
        # triggers up to 5 seconds to unmark field from invalid->valid
        multi_edit.set_date_time('07/12/2100', '22')
        patience = 5
        while patience:
            patience -= 1
            if not multi_edit.is_date_time_marked_invalid():
                break
            time.sleep(1)
        self.assertFalse(multi_edit.is_date_time_marked_invalid())

        # Click save.  Not validating effects; this is done elsewhere.
        # Here, we just want to verify that we are free of errors and
        # Save completes without exceptions.
        multi_edit.click_save()

    def test_multi_edit_start_date_fails_safe(self):
        course_list = self.load_courses_list()
        for course_namespace in self.course_namespaces[:-1]:
            course_list.toggle_course_checkbox(course_namespace)
        multi_edit = course_list.click_edit_start_date()
        self._test_multi_edit_date_fails_safe(multi_edit)

    def test_multi_edit_end_date_fails_safe(self):
        course_list = self.load_courses_list()
        for course_namespace in self.course_namespaces[:-1]:
            course_list.toggle_course_checkbox(course_namespace)
        multi_edit = course_list.click_edit_end_date()
        self._test_multi_edit_date_fails_safe(multi_edit)

    def _multi_edit_set_date(self, multi_edit):
        # Set start(end) date for courses.
        multi_edit.click_set_value_radio()
        multi_edit.set_date_time('07/12/2100', '22')
        multi_edit.set_availability(
            courses.COURSE_AVAILABILITY_POLICIES[
                courses.COURSE_AVAILABILITY_PRIVATE]['title'])
        multi_edit.click_save()
        multi_edit.click_cancel()

    def _test_multi_edit_date_clear(self, multi_edit, course_list):
        # Verify date is present in dialog.
        for course_namespace in self.course_namespaces[0:-1]:
            self.assertEquals(
                'Private on 2100-07-12 22:00:00',
                multi_edit.get_current_value_for(course_namespace))

        # Save button should be disbled until clear/save radio is selected.
        self.assertFalse(multi_edit.get_save_button_is_enabled())
        multi_edit.click_clear_value_radio()
        self.assertTrue(multi_edit.get_save_button_is_enabled())
        multi_edit.click_save()

        # Verify date is cleared in dialog.
        for course_namespace in self.course_namespaces[0:-1]:
            self.assertEquals(
                '', multi_edit.get_current_value_for(course_namespace))
        multi_edit.click_cancel()

        # Verify date is cleared in main page.  (Here, we're verifying both
        # start and end date, which is harmless; whichever of start or end
        # we're not testing will also be blank)
        #
        # Also note: Passing pre_wait=False here is necessary.  Apparently,
        # <a> tags with no text are not considered "visible" by Selenium.
        # Having been on the all-courses page and opened the multi-edit,
        # we are 100% certain that the page is currently up-to-date, so
        # sending pre_wait=False is safe.
        for namespace in self.course_namespaces[0:-1]:
            self.assertEquals('', course_list.get_start_date_for(
                namespace, pre_wait=False))
            self.assertEquals('', course_list.get_end_date_for(
                namespace, pre_wait=False))

    def test_multi_edit_start_date_clear(self):
        course_list = self.load_courses_list()
        for course_namespace in self.course_namespaces[:-1]:
            course_list.toggle_course_checkbox(course_namespace)
        multi_edit = course_list.click_edit_start_date()
        self._multi_edit_set_date(multi_edit)
        multi_edit = course_list.click_edit_start_date()
        self._test_multi_edit_date_clear(multi_edit, course_list)

    def test_multi_edit_end_date_clear(self):
        course_list = self.load_courses_list()
        for course_namespace in self.course_namespaces[:-1]:
            course_list.toggle_course_checkbox(course_namespace)
        multi_edit = course_list.click_edit_end_date()
        self._multi_edit_set_date(multi_edit)
        multi_edit = course_list.click_edit_end_date()
        self._test_multi_edit_date_clear(multi_edit, course_list)

    def test_multi_edit_shown_in_explorer_fails_safe(self):
        course_list = self.load_courses_list()
        for course_namespace in self.course_namespaces[:-1]:
            course_list.toggle_course_checkbox(course_namespace)
        multi_edit = course_list.click_edit_show_in_explorer()

        # Before save attempt, buttons not marked.
        self.assertFalse(multi_edit.are_show_buttons_marked_invalid())

        # Save with no changes should mark field invalid.
        multi_edit.click_save_expecting_validation_failure()
        self.assertTrue(multi_edit.are_show_buttons_marked_invalid())

        # Any change to field should remove the invalid style.
        multi_edit.set_show_in_explorer(True)
        self.assertFalse(multi_edit.are_show_buttons_marked_invalid())

    def _test_multi_edit_dates_trying_to_mess_things_up(self, test_start_date):
        ns = self.course_namespaces[0]
        public = courses.COURSE_AVAILABILITY_POLICIES[
            courses.COURSE_AVAILABILITY_PUBLIC]['title']

        # Set non-blank setting into course so we can verify that subsequent
        # operations really are clearing out values.
        course_list = self.load_courses_list()
        course_list.toggle_course_checkbox(ns)
        if test_start_date:
            multi_edit = course_list.click_edit_start_date()
        else:
            multi_edit = course_list.click_edit_end_date()

        multi_edit.set_availability(public)
        multi_edit.set_date_time('10/13/2016', '15')
        multi_edit.click_set_value_radio()
        multi_edit.click_save()
        self.assertEquals(
            'Public - No Registration on 2016-10-13 15:00:00',
            multi_edit.get_current_value_for(ns))
        if test_start_date:
            actual = course_list.get_start_date_for(ns, pre_wait=False)
        else:
            actual = course_list.get_end_date_for(ns, pre_wait=False)
        self.assertEquals('2016-10-13', actual)
        course_avail = self._get_course_availability_from_settings(ns)
        if test_start_date:
            actual = course_avail['start_trigger']
        else:
            actual = course_avail['end_trigger']
        self.assertEquals(
            {'availability': 'public',
             'date': '10/13/2016',
             'hour': '15'},
            actual)

        # Set date and availability fields, but click 'Clear' radio and save.
        # Verify correct updates onto multi-edit, course list and also actual
        # settings.
        course_list = self.load_courses_list()
        course_list.toggle_course_checkbox(ns)
        if test_start_date:
            multi_edit = course_list.click_edit_start_date()
        else:
            multi_edit = course_list.click_edit_end_date()
        multi_edit.set_availability(public)
        multi_edit.set_date_time('10/13/2016', '15')
        multi_edit.click_clear_value_radio()
        multi_edit.click_save()
        self.assertEquals(
            '',
            multi_edit.get_current_value_for(ns))

        if test_start_date:
            actual = course_list.get_start_date_for(ns, pre_wait=False)
        else:
            actual = course_list.get_end_date_for(ns, pre_wait=False)
        self.assertEquals('', actual)
        course_avail = self._get_course_availability_from_settings(ns)
        if test_start_date:
            actual = course_avail['start_trigger']
        else:
            actual = course_avail['end_trigger']
        self.assertEquals(
            {'availability': 'none',
             'date': '',
             'hour': '00'},
            actual)

        # Set setting, and then using the same dialog, immediately clear
        # setting.  Verify fake values from JS and real setting.
        course_list = self.load_courses_list()
        course_list.toggle_course_checkbox(ns)
        if test_start_date:
            multi_edit = course_list.click_edit_start_date()
        else:
            multi_edit = course_list.click_edit_end_date()
        multi_edit.set_availability(public)
        multi_edit.set_date_time('10/13/2016', '15')
        multi_edit.click_set_value_radio()
        multi_edit.click_save()
        multi_edit.click_clear_value_radio()
        multi_edit.click_save()
        self.assertEquals(
            '',
            multi_edit.get_current_value_for(ns))
        if test_start_date:
            actual = course_list.get_start_date_for(ns, pre_wait=False)
        else:
            actual = course_list.get_end_date_for(ns, pre_wait=False)
        self.assertEquals('', actual)
        course_avail = self._get_course_availability_from_settings(ns)
        if test_start_date:
            actual = course_avail['start_trigger']
        else:
            actual = course_avail['end_trigger']
        self.assertEquals(
            {'availability': 'none',
             'date': '',
             'hour': '00'},
            actual)

    def test_multi_edit_start_trying_to_mess_things_up(self):
        self._test_multi_edit_dates_trying_to_mess_things_up(
            test_start_date=True)

    def test_multi_edit_end_trying_to_mess_things_up(self):
        self._test_multi_edit_dates_trying_to_mess_things_up(
            test_start_date=False)

    def test_multi_edit_course_start_end(self):
        # ----------------------------------------------------------------------
        # Before any changes, course settings for availability are blank.
        expected_c0 = {
            'availability': 'private',
            'start_trigger': {
                'availability': 'none',
                'date': '',
                'hour': '00',
            },
            'end_trigger': {
                'availability': 'none',
                'date': '',
                'hour': '00',
            }
        }
        expected_c1 = copy.deepcopy(expected_c0)
        expected_c2 = copy.deepcopy(expected_c0)
        expected_avail = {
            self.course_namespaces[0]: expected_c0,
            self.course_namespaces[1]: expected_c1,
            self.course_namespaces[2]: expected_c2,
        }

        # ----------------------------------------------------------------------
        # Set start date on two of three courses.
        course_list = self.load_courses_list()
        for course_namespace in self.course_namespaces[:-1]:
            course_list.toggle_course_checkbox(course_namespace)
        multi_edit = course_list.click_edit_start_date()
        multi_edit.click_set_value_radio()
        multi_edit.set_availability(
            courses.COURSE_AVAILABILITY_POLICIES[
                courses.COURSE_AVAILABILITY_REGISTRATION_REQUIRED]['title'])
        multi_edit.set_date_time('07/12/2100', '22')
        multi_edit.click_save()

        expected_c0['start_trigger'] = expected_c1['start_trigger'] = {
            'availability': 'registration_required',
            'date': '07/12/2100',
            'hour': '22'
        }
        actual_avail = self._get_courses_availability_from_settings()
        self.assertEquals(expected_avail, actual_avail)

        # ----------------------------------------------------------------------
        # End date on two of three courses; one course from the set with
        # the start date set, and one with no start date set.
        course_list = self.load_courses_list()
        for course_namespace in self.course_namespaces[1:]:
            course_list.toggle_course_checkbox(course_namespace)
        multi_edit = course_list.click_edit_end_date()
        multi_edit.click_set_value_radio()
        multi_edit.set_availability(
            courses.COURSE_AVAILABILITY_POLICIES[
                courses.COURSE_AVAILABILITY_PUBLIC]['title'])
        multi_edit.set_date_time('07/31/2100', '05')
        multi_edit.click_save()

        expected_c1['end_trigger'] = expected_c2['end_trigger'] = {
            'availability': 'public',
            'date': '07/31/2100',
            'hour': '05',
        }
        actual_avail = self._get_courses_availability_from_settings()
        self.assertEquals(expected_avail, actual_avail)

        # ----------------------------------------------------------------------
        # Set current availability for all courses; verify that this does
        # not clobber start/end triggers.
        course_list = self.load_courses_list()
        for course_namespace in self.course_namespaces:
            course_list.toggle_course_checkbox(course_namespace)
        multi_edit = course_list.click_edit_availability()
        multi_edit.set_availability(
            courses.COURSE_AVAILABILITY_POLICIES[
                courses.COURSE_AVAILABILITY_REGISTRATION_OPTIONAL]['title'])
        multi_edit.click_save()

        expected_c0['availability'] = 'registration_optional'
        expected_c1['availability'] = 'registration_optional'
        expected_c2['availability'] = 'registration_optional'
        actual_avail = self._get_courses_availability_from_settings()
        self.assertEquals(expected_avail, actual_avail)

        # ----------------------------------------------------------------------
        # Clear start dates for all courses; verify change.
        course_list = self.load_courses_list()
        for course_namespace in self.course_namespaces:
            course_list.toggle_course_checkbox(course_namespace)
        multi_edit = course_list.click_edit_start_date()
        multi_edit.click_clear_value_radio()
        multi_edit.click_save()

        expected_c0['start_trigger'] = expected_c1['start_trigger'] = {
            'availability': 'none',
            'date': '',
            'hour': '00'
        }
        actual_avail = self._get_courses_availability_from_settings()
        self.assertEquals(expected_avail, actual_avail)

        # ----------------------------------------------------------------------
        # Clear end dates for all courses; verify change.
        course_list = self.load_courses_list()
        for course_namespace in self.course_namespaces:
            course_list.toggle_course_checkbox(course_namespace)
        multi_edit = course_list.click_edit_end_date()
        multi_edit.click_clear_value_radio()
        multi_edit.click_save()

        expected_c1['end_trigger'] = expected_c2['end_trigger'] = {
            'availability': 'none',
            'date': '',
            'hour': '00'
        }
        actual_avail = self._get_courses_availability_from_settings()
        self.assertEquals(expected_avail, actual_avail)

    def test_multi_edit_course_start_appearance_only(self):
        course_list = self.load_courses_list()
        for course_namespace in self.course_namespaces[0:-1]:
            course_list.toggle_course_checkbox(course_namespace)
        availability = courses.COURSE_AVAILABILITY_POLICIES[
            courses.COURSE_AVAILABILITY_PUBLIC]['title']
        multi_edit = course_list.click_edit_start_date()

        # Verify that the starting value in the dialog has been copied from
        # the page.
        for course_namespace in self.course_namespaces[0:-1]:
            self.assertEquals(
                '',
                multi_edit.get_current_value_for(course_namespace))

        multi_edit.click_set_value_radio()
        multi_edit.set_availability(availability)
        multi_edit.set_date_time('07/31/2100', '05')
        multi_edit.click_save()

        # Verify that value has been updated in the dialog.
        for course_namespace in self.course_namespaces[0:-1]:
            self.assertEquals(
                availability + ' on 2100-07-31 05:00:00',
                multi_edit.get_current_value_for(course_namespace))
        multi_edit.click_cancel()

        # Verify the value has been updated on the course list page.
        for course_namespace in self.course_namespaces[0:-1]:
            self.assertEquals(
                '2100-07-31',
                course_list.get_start_date_for(course_namespace))
        for course_namespace in self.course_namespaces[-1:]:
            self.assertEquals(
                '',
                course_list.get_category_for(course_namespace, pre_wait=False))

        # Re-open multi-edit dialog; verify that the long form of the
        # availability text is present, not just the short form from the
        # list page.
        multi_edit = course_list.click_edit_start_date()
        for course_namespace in self.course_namespaces[0:-1]:
            self.assertEquals(
                availability + ' on 2100-07-31 05:00:00',
                multi_edit.get_current_value_for(course_namespace))

    def _get_category_from_settings(self, namespace):
        return self.load_dashboard(
            re.sub('^ns_', '', namespace)
        ).click_settings(
        ).get_text_field_by_name(
            'course:category_name'
        )

    def test_multi_edit_course_category(self):
        course_list = self.load_courses_list()
        for course_namespace in self.course_namespaces[0:-1]:
            course_list.toggle_course_checkbox(course_namespace)
        multi_edit = course_list.click_edit_category()

        # Verify that the starting value in the dialog has been copied from
        # the page.
        for course_namespace in self.course_namespaces[0:-1]:
            self.assertEquals(
                '',
                multi_edit.get_current_value_for(course_namespace))

        # Try to save with blank value.
        multi_edit.click_set_value_radio()
        self.assertFalse(multi_edit.is_category_marked_invalid())
        multi_edit.click_save_expecting_validation_failure()
        self.assertTrue(multi_edit.is_category_marked_invalid())

        # Setting category to nonblank clears error marker
        multi_edit.set_category('Frumious Bandersnatch')
        self.assertFalse(multi_edit.is_category_marked_invalid())
        multi_edit.click_save()

        # Verify that value has been updated in the dialog.
        for course_namespace in self.course_namespaces[0:-1]:
            self.assertEquals(
                'Frumious Bandersnatch',
                multi_edit.get_current_value_for(course_namespace))
        multi_edit.click_cancel()

        # Verify the value has been updated on the course list page.
        for course_namespace in self.course_namespaces[0:-1]:
            self.assertEquals(
                'Frumious Bandersnatch',
                course_list.get_category_for(course_namespace, pre_wait=False))
        for course_namespace in self.course_namespaces[-1:]:
            self.assertEquals(
                '',
                course_list.get_category_for(course_namespace, pre_wait=False))

        # Verify that settings have actually been changed by loading the
        # setting from individual courses' settings pages.
        for course_namespace in self.course_namespaces[0:-1]:
            self.assertEquals(
                'Frumious Bandersnatch',
                self._get_category_from_settings(course_namespace))
        for course_namespace in self.course_namespaces[-1:]:
            self.assertEquals(
                '',
                self._get_category_from_settings(course_namespace))

        # And now, having set values, clear values.
        course_list = self.load_courses_list()
        for course_namespace in self.course_namespaces[0:-1]:
            course_list.toggle_course_checkbox(course_namespace)
        multi_edit = course_list.click_edit_category()

        # Verify that the starting value in the dialog has been copied from
        # the page.
        for course_namespace in self.course_namespaces[0:-1]:
            self.assertEquals(
                'Frumious Bandersnatch',
                multi_edit.get_current_value_for(course_namespace))

        # Clear values.
        multi_edit.click_clear_value_radio()
        multi_edit.click_save()

        # Verify that value has been updated in the dialog.
        for course_namespace in self.course_namespaces[0:-1]:
            self.assertEquals(
                '',
                multi_edit.get_current_value_for(course_namespace))
        multi_edit.click_cancel()

        # Verify the value has been updated on the course list page.
        for course_namespace in self.course_namespaces:
            self.assertEquals(
                '',
                course_list.get_category_for(course_namespace, pre_wait=False))

        # Verify that settings have actually been changed by loading the
        # setting from individual courses' settings pages.
        for course_namespace in self.course_namespaces:
            self.assertEquals(
                '',
                self._get_category_from_settings(course_namespace))

    def _get_show_in_explorer_from_settings(self, namespace):
        self.load_dashboard(
            re.sub('^ns_', '', namespace)
        ).click_settings(
        )
        element = self.driver.find_element_by_name('course:show_in_explorer')
        return element.get_attribute('value')

    def test_multi_edit_course_show_in_explorer(self):
        course_list = self.load_courses_list()
        for course_namespace in self.course_namespaces[:-1]:
            course_list.toggle_course_checkbox(course_namespace)
        multi_edit = course_list.click_edit_show_in_explorer()
        multi_edit.set_show_in_explorer(False)
        multi_edit.click_save()

        # Verify that value has been updated in the dialog.
        for course_namespace in self.course_namespaces[0:-1]:
            self.assertEquals(
                'No',
                multi_edit.get_current_value_for(course_namespace))
        multi_edit.click_cancel()

        # Verify the value has been updated on the course list page.
        for course_namespace in self.course_namespaces[0:-1]:
            self.assertEquals(
                'No',
                course_list.get_show_in_explorer_for(course_namespace))
        for course_namespace in self.course_namespaces[-1:]:
            self.assertEquals(
                'Yes',
                course_list.get_show_in_explorer_for(course_namespace))

        # Verify that settings have actually been changed by loading the
        # setting from individual courses' settings pages.
        for course_namespace in self.course_namespaces[0:-1]:
            self.assertEquals(
                'false',
                self._get_show_in_explorer_from_settings(course_namespace))
        for course_namespace in self.course_namespaces[-1:]:
            self.assertEquals(
                'true',
                self._get_show_in_explorer_from_settings(course_namespace))


class CoursesEnrollmentsTests(_CoursesListTestBase):

    COURSES_LIST_PAGE_RELOAD_WAIT = 5

    def test_enrollments_mapreduce_zero(self):
        course_name, title = self.create_new_course(login=False)
        course_namespace = 'ns_' + course_name

        # Specifically do *not* load the Courses list just yet, instead,
        # kick off the site_admin_enrollments/total MapReduce first.
        cron_page = self.load_appengine_cron(
        ).run_cron(
            enrollments.StartComputeCounts.URL
        )

        # Now load the Courses list page and confirm that the value in the
        # "Registered Students" column is (eventually) definitely 0 (zero)
        # and not an em dash.
        self.load_courses_list(
        ).verify_total_enrollments(
            course_namespace, title, 0,
            delay_scale_factor=self.COURSES_LIST_PAGE_RELOAD_WAIT
        )

    def test_registered_students_updated(self):
        course_name, title = self.create_new_course(login=False)
        course_namespace = 'ns_' + course_name

        # Newly-created course should have 'Private' availability.
        # "Registered Students" count starts as zero.
        #
        # (A "No count" em dash can only be displayed for legacy courses that
        # existed before the release of Course Builder that added enrollment
        # counts, a state is difficult to create during integration tests.)
        self.load_courses_list(
        ).verify_availability(
            course_namespace, 'Private'
        ).verify_total_enrollments(
            course_namespace, title, 0
        )

        admin1 = self.one_admin()
        admin2 = self.one_admin()
        pupil3 = self.one_pupil()
        emails = [admin1.email, admin2.email, pupil3.email]

        # 'Private' will not let students enroll. 'Public' causes the
        # [Register] button to not be displayed for anyone, even the course
        # creator. Fix both of those by requiring registration, which allows
        # non-admins to register.
        avail = 'Registration Required'
        self.init_availability_and_whitelist(course_name, avail, emails)

        # Double-check that whitelisted students were indeed saved.
        self.load_dashboard(
            course_name
        ).click_availability(
        ).verify_whitelisted_students(
            '\n'.join(emails)
        )

        # Confirm that Courses page no longer indicates newly-created test
        # course as being 'Private'.
        self.load_courses_list(
        ).verify_availability(
            course_namespace, avail,
        )

        # Register an admin user as a student; confirm count is now "1".
        # Log out course creator admin and log in as this new admin.
        self.login(admin1.email, admin=admin1.admin, logout_first=True)
        self.load_course(
            course_name
        ).click_register(
        ).enroll(
            admin1.name
        )
        self.load_courses_list(
        ).verify_total_enrollments(
            course_namespace, title, 1
        )

        # Register another admin user as a student; confirm count is now "2".
        # Log out course creator admin and log in as a second admin.
        self.login(admin2.email, admin=admin2.admin, logout_first=True)
        self.load_course(
            course_name
        ).click_register(
        ).enroll(
            admin2.name
        )
        self.load_courses_list(
        ).verify_total_enrollments(
            course_namespace, title, 2
        )

        # Register non-admin user as a student; confirm count is now "3".
        # Log out 2nd admin and log in as a non-admin student.
        self.login(pupil3.email, admin=pupil3.admin, logout_first=True)
        self.load_course(
            course_name
        ).click_register(
        ).enroll(
            pupil3.name
        ).click_course()

        # Log out and log in as course creator to check enrollment totals.
        self.login(self.LOGIN, admin=True, logout_first=True)
        self.load_courses_list(
        ).verify_total_enrollments(
            course_namespace, title, 3
        )

        # TODO(tlarsen): Implement a DeleteMyDataPage and:
        #   1) Unenroll all students, one by one.
        #   2) Confirm count decrements to 0, not an em dash, and tooltip
        #      still indicates "Most recent activity at...", and not
        #      "(registration activity...is being computed)".


class CoursesListSortingTests(_CoursesListTestBase):

    COLUMNS_ORDER = admin_pageobjects.CoursesListPage.SORTABLE_COLUMNS_ORDER

    # The Courses list page is intiially already sorted by the 'Title' column,
    # in ascending order. Check that state without clicking on the 'Title'
    # column header, then also explicitly click on the 'Title' column header
    # at the end.
    COLUMNS_TO_CHECK = COLUMNS_ORDER + ['title']

    def test_material_design_sorted_by_arrows(self):
        initial = True  # Skip first click on initial sorted-by 'Title' column.
        courses_page = self.load_courses_list()

        for column in self.COLUMNS_TO_CHECK:
            initial = courses_page.click_if_not_initial(column, initial)
            courses_page.verify_sorted_by_arrows(
                column, 'ascending',
            # Clicking ascending-sorted column sorts it again, descending.
            ).click_sortable_column(
                column
            ).verify_sorted_by_arrows(
                column, 'descending',
            )

    COURSES_TO_CREATE = [
        # Always create at least one *Public* course first, and make it have
        # the sorted-first URL as well, to give non-admin pupils somewhere to
        # land other than the 'Log in as another user' 404 page. (This matters
        # if --skip_integration_setup was supplied to scripts/project.py and
        # the public course from the usual setup does not exist.)
        admin_pageobjects.CoursesListPage.Course(
            '     ', 'all_whitespace_title', 'Public - No Registration', 0),
        admin_pageobjects.CoursesListPage.Course(
            'wHITESPACE', 'b_1st_stripped_no_case', 'Private', 0),
        admin_pageobjects.CoursesListPage.Course(
            '  Whitespace', 'c_2nd_stripped_no_case', 'Private', 0),
        admin_pageobjects.CoursesListPage.Course(
            'TITLE DUPE', 'd_1st_title_url', 'Registration Required', 1),
        admin_pageobjects.CoursesListPage.Course(
            'TITLE DUPE', 'e_2nd_title_url', 'Private', 0),
        admin_pageobjects.CoursesListPage.Course(
            '4 ENROLL dupe', 'g_1st_enroll_url', 'Registration Optional', 2),
        admin_pageobjects.CoursesListPage.Course(
            '3 enroll DUPE', 'p_2nd_enroll_url', 'Registration Required', 2),
        admin_pageobjects.CoursesListPage.Course(
            '2 reg dupe', 't_1st_reg_url', 'Registration Optional', 4),
        admin_pageobjects.CoursesListPage.Course(
            '1 REG DUPE', 'v_2nd_reg_url', 'Registration Optional', 3),
        admin_pageobjects.CoursesListPage.Course(
            '0 ṴǸḬҪȪƉỀ', 'zzzz_last_by_url', 'Public - No Registration', 0),
    ]

    def test_sort_courses(self):
        # Create several courses with specific names and titles.
        for c in self.COURSES_TO_CREATE:
            self.create_course(c.title, c.url, login=False)
            persons = [p for p in self.some_persons(c.enroll, avail=c.avail)]
            emails = [p.email for p in persons]
            self.init_availability_and_whitelist(c.url, c.avail, emails)

            # Enroll the selected persons. Someone is expected to be logged
            # in prior to calling enroll_students (and that should be true,
            # as the course-creating admin should still be logged in at this
            # point).
            self.enroll_persons(c.url, persons, avail=c.avail)

            # The last-enrolled student is still logged in, so log that user
            # out and switch to the course-creating admin.
            self.login(self.LOGIN, admin=True, logout_first=True)

        initial = True  # Skip first click on initial sorted-by 'Title' column.
        courses_page = self.load_courses_list()
        for cl in self.COLUMNS_TO_CHECK:
            initial = courses_page.click_if_not_initial(cl, initial)
            courses_page.verify_rows_sorted_by_column(
                cl, 'ascending', self.COURSES_TO_CREATE
            # Clicking ascending-sorted column sorts it again, descending.
            ).click_sortable_column(
                cl
            ).verify_rows_sorted_by_column(
                cl, 'descending', self.COURSES_TO_CREATE
            )
