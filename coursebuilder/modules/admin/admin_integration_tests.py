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
        self.login(self.LOGIN, admin=True)


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


class CoursesEnrollmentsTests(_CoursesListTestBase):

    def test_registered_students_updated(self):
        course_name, title = self.create_new_course(login=False)
        course_namespace = 'ns_' + course_name

        # Newly-created course should have 'Private' availability.
        # "Registered Students" count starts as em dash to indicate
        # "no count", and tooltip contents are different.
        self.load_courses_list(
        ).verify_availability(
            course_namespace, 'Private'
        ).verify_no_enrollments(
            course_namespace, title
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

    COURSES = [
        admin_pageobjects.CoursesListPage.Course(
            '     ', 'all_whitespace_title_test_sort_url', 'Private', 0),
        admin_pageobjects.CoursesListPage.Course(
            'wHITESPACE', 'b_test_sort_url', 'Public - No Registration', 0),
        admin_pageobjects.CoursesListPage.Course(
            '  Whitespace', 'c_test_sort_url', 'Private', 0),
        admin_pageobjects.CoursesListPage.Course(
            'NAME DUPE', 'd_test_sort_url', 'Registration Required', 1),
        admin_pageobjects.CoursesListPage.Course(
            'NAME DUPE', 'e_test_sort_url', 'Private', 0),
        admin_pageobjects.CoursesListPage.Course(
            '4 ENROLL dupe', 'g_test_sort_url', 'Registration Optional', 2),
        admin_pageobjects.CoursesListPage.Course(
            '3 enroll DUPE', 'p_test_sort_url', 'Registration Required', 2),
        admin_pageobjects.CoursesListPage.Course(
            '2 reg dupe', 't_test_sort_url', 'Registration Optional', 4),
        admin_pageobjects.CoursesListPage.Course(
            '1 REG DUPE', 'v_test_sort_url', 'Registration Optional', 3),
        admin_pageobjects.CoursesListPage.Course(
            '0 Last URL', 'zzzz_test_sort_url', 'Public - No Registration', 0),
    ]

    SAMPLE = admin_pageobjects.CoursesListPage.Course(
        'Power Searching with Google', '', 'Registration Optional', 1)

    ALL_COURSES = COURSES + [SAMPLE]

    def test_sort_courses(self):
        # Create several courses with specific names and titles.
        for c in self.COURSES:
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
                cl, 'ascending', self.ALL_COURSES,
            # Clicking ascending-sorted column sorts it again, descending.
            ).click_sortable_column(
                cl
            ).verify_rows_sorted_by_column(
                cl, 'descending', self.ALL_COURSES,
            )
