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

from selenium.common import exceptions

from models import courses
from modules.admin import admin_pageobjects
from modules.admin import enrollments
from modules.courses import courses_pageobjects
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
        multi_edit.assert_status(course_namespace, 'Saved.')
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
        self.course_namespaces = []
        for x in xrange(self.NUM_COURSES):
            self.course_namespaces.append(
                'ns_' + self.create_new_course(login=False)[0])
        self.course_list = self.load_courses_list()
        self.maxDiff = None

    def _get_courses_availability(self):
        ret = {}
        page = courses_pageobjects.CourseAvailabilityPage(self)
        for course_namespace in self.course_namespaces:
            stub = re.sub('^ns_', '', course_namespace)
            page.load(stub)
            ret[course_namespace] = page.get_settings()
        return ret

    def test_multi_edit_multiple_courses(self):

        for course_namespace in self.course_namespaces:
            self.course_list.toggle_course_checkbox(course_namespace)

        multi_edit = self.course_list.click_edit_availability()
        multi_edit.set_availability(
            courses.COURSE_AVAILABILITY_POLICIES[
                courses.COURSE_AVAILABILITY_REGISTRATION_REQUIRED]['title'])

        multi_edit.click_save()
        for course_namespace in self.course_namespaces:
            multi_edit.assert_status(course_namespace, 'Saved.')
            self.course_list.verify_availability(
                course_namespace, courses.COURSE_AVAILABILITY_POLICIES[
                courses.COURSE_AVAILABILITY_REGISTRATION_REQUIRED]['title'])

        multi_edit.expect_status_message_to_be(
            'Updated settings in %d courses.' %
            self.NUM_COURSES)

        # Attempt to set courses to Private, but with an error that
        # will prevent that from actually happening.
        multi_edit.set_availability(
            courses.COURSE_AVAILABILITY_POLICIES[
                courses.COURSE_AVAILABILITY_PRIVATE]['title'])

        multi_edit.set_availability_xsrf_token('not a valid token')
        multi_edit.click_save()
        for course_namespace in self.course_namespaces:
            multi_edit.assert_status(
                course_namespace,
                'Bad XSRF token. Please reload the page and try again')
            self.course_list.verify_availability(
                course_namespace, courses.COURSE_AVAILABILITY_POLICIES[
                courses.COURSE_AVAILABILITY_REGISTRATION_REQUIRED]['title'])
        multi_edit.expect_status_message_to_be(
            'Updated settings in 0 courses and had %d errors.' %
            self.NUM_COURSES)

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
        actual_avail = self._get_courses_availability()
        self.assertEquals(expected_avail, actual_avail)

        # ----------------------------------------------------------------------
        # End date on two of three courses; one course from the set with
        # the start date set, and one with no start date set.
        course_list = self.load_courses_list()
        for course_namespace in self.course_namespaces[1:]:
            course_list.toggle_course_checkbox(course_namespace)
        multi_edit = course_list.click_edit_end_date()
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
        actual_avail = self._get_courses_availability()
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
        actual_avail = self._get_courses_availability()
        self.assertEquals(expected_avail, actual_avail)

        # ----------------------------------------------------------------------
        # Clear start dates for all courses; verify change.
        course_list = self.load_courses_list()
        for course_namespace in self.course_namespaces:
            course_list.toggle_course_checkbox(course_namespace)
        multi_edit = course_list.click_edit_start_date()
        multi_edit.set_date_time('', '00')
        multi_edit.click_save()

        expected_c0['start_trigger'] = expected_c1['start_trigger'] = {
            'availability': 'none',
            'date': '',
            'hour': '00'
        }
        actual_avail = self._get_courses_availability()
        self.assertEquals(expected_avail, actual_avail)

        # ----------------------------------------------------------------------
        # Clear end dates for all courses; verify change.
        course_list = self.load_courses_list()
        for course_namespace in self.course_namespaces:
            course_list.toggle_course_checkbox(course_namespace)
        multi_edit = course_list.click_edit_end_date()
        multi_edit.set_date_time('', '00')
        multi_edit.click_save()

        expected_c1['end_trigger'] = expected_c2['end_trigger'] = {
            'availability': 'none',
            'date': '',
            'hour': '00'
        }
        actual_avail = self._get_courses_availability()
        self.assertEquals(expected_avail, actual_avail)

    def _get_category(self, namespace):
        return self.load_dashboard(
            re.sub('^ns_', '', namespace)
        ).click_settings(
        ).get_text_field_by_name(
            'course:category_name'
        )

    def test_multi_edit_course_category(self):
        course_list = self.load_courses_list()
        for course_namespace in self.course_namespaces[:-1]:
            course_list.toggle_course_checkbox(course_namespace)
        multi_edit = course_list.click_edit_category()
        multi_edit.set_category('Frumious Bandersnatch')
        multi_edit.click_save()

        self.assertEquals(
            'Frumious Bandersnatch',
            self._get_category(self.course_namespaces[0]))
        self.assertEquals(
            'Frumious Bandersnatch',
            self._get_category(self.course_namespaces[1]))
        self.assertEquals(
            '',
            self._get_category(self.course_namespaces[2]))


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
            '0 Last URL', 'zzzz_last_by_url', 'Public - No Registration', 0),
    ]

    SAMPLE = admin_pageobjects.CoursesListPage.Course(
        'Power Searching with Google', '', 'Registration Optional', 1)

    def test_sort_courses(self):

        # If --skip_integration_setup was supplied to scripts/project.py,
        # the 'Power Searching with Google' sample course will not be present.
        root_page = self.load_root_page()
        base_url = integration.TestBase.INTEGRATION_SERVER_BASE_URL

        if root_page.is_default_course_deployed(base_url):
            all_courses = list(self.COURSES_TO_CREATE)
            all_courses.append(self.SAMPLE)
        else:
            all_courses = self.COURSES_TO_CREATE

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
                cl, 'ascending', all_courses
            # Clicking ascending-sorted column sorts it again, descending.
            ).click_sortable_column(
                cl
            ).verify_rows_sorted_by_column(
                cl, 'descending', all_courses
            )
