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

from modules.admin import admin_pageobjects
from tests import suite
from tests.integration import integration

class CourseAdministrationTests(integration.TestBase):

    def _load_course_list(self, ):
        return admin_pageobjects.CourseListPage(self).load(
            suite.TestBase.INTEGRATION_SERVER_BASE_URL)

    def test_course_selection_checkboxes(self):
        """Verify select-all and course-select checkboxes affect one other."""

        self.load_root_page(
        ).click_login(
        ).login(
            self.LOGIN, admin=True
        )
        # ----------------------------------------------------------------
        # Verify operation with multiple courses.
        course_namespace_one = ''  # Power Searching course w/ blank namespace.
        course_name_two = self.create_new_course(login=False)[0]
        course_namespace_two = 'ns_' + course_name_two
        course_list = self._load_course_list()

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
