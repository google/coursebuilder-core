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

from selenium.common import exceptions

from models import courses
from modules.admin import admin_pageobjects
from tests.integration import integration


class _CoursesListTestBase(integration.TestBase):

    def load_courses_list(self, cls=admin_pageobjects.CoursesListPage):
        return super(_CoursesListTestBase, self).load_courses_list(cls=cls)

    def setUp(self):
        super(_CoursesListTestBase, self).setUp()
        self.load_root_page().click_login().login(self.LOGIN, admin=True)

    def whitelist(self, course_name, avail, emails):
        if avail == 'Private':
            return  # Assume newly-created course is already 'Private'.

        avail_page = self.load_dashboard(
            course_name
        ).click_availability(
        ).set_course_availability(
            avail
        )

        if avail == 'Public - No Registration':
            self.assertEqual(0, len(emails))
        else:
            avail_page.set_whitelisted_students(emails)

        avail_page.click_save()


class CourseAdministrationTests(_CoursesListTestBase):

    def test_course_selection_checkboxes(self):
        """Verify select-all and course-select checkboxes affect one other."""

        # ----------------------------------------------------------------
        # Verify operation with multiple courses.
        course_namespace_one = ''  # Power Searching course w/ blank namespace.
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


class CourseMultiEditTests(_CoursesListTestBase):

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
        multi_edit.assert_status(course_namespace, 'Saved.')
        multi_edit.expect_status_message_to_be(
            'Set availability to public for 1 course.')
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

    def test_multi_edit_multiple_courses(self):
        NUM_COURSES = 3
        course_namespaces = []
        for x in xrange(NUM_COURSES):
            course_namespaces.append(
                'ns_' + self.create_new_course(login=False)[0])

        course_list = self.load_courses_list()
        for course_namespace in course_namespaces:
            course_list.toggle_course_checkbox(course_namespace)

        multi_edit = course_list.click_edit_availability()
        multi_edit.set_availability(
            courses.COURSE_AVAILABILITY_POLICIES[
                courses.COURSE_AVAILABILITY_REGISTRATION_REQUIRED]['title'])

        multi_edit.click_save()
        for course_namespace in course_namespaces:
            multi_edit.assert_status(course_namespace, 'Saved.')
            course_list.verify_availability(
                course_namespace, courses.COURSE_AVAILABILITY_POLICIES[
                courses.COURSE_AVAILABILITY_REGISTRATION_REQUIRED]['title'])

        multi_edit.expect_status_message_to_be(
            'Set availability to registration required for %d courses.' %
            NUM_COURSES)

        # Attempt to set courses to Private, but with an error that
        # will prevent that from actually happening.
        multi_edit.set_availability(
            courses.COURSE_AVAILABILITY_POLICIES[
                courses.COURSE_AVAILABILITY_PRIVATE]['title'])

        multi_edit.set_availability_xsrf_token('not a valid token')
        multi_edit.click_save()
        for course_namespace in course_namespaces:
            multi_edit.assert_status(
                course_namespace,
                'Bad XSRF token. Please reload the page and try again')
            course_list.verify_availability(
                course_namespace, courses.COURSE_AVAILABILITY_POLICIES[
                courses.COURSE_AVAILABILITY_REGISTRATION_REQUIRED]['title'])
        multi_edit.expect_status_message_to_be(
            'Set availability to private for 0 courses and had %d errors.' %
            NUM_COURSES)
