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

"""Page objects for all-courses admin integration tests for Course Builder."""

__author__ = [
    'Mike Gainer (mgainer@google.com)'
]

from tests.integration import pageobjects


class CourseListPage(pageobjects.DashboardPage):
    _SELECT_ALL_COURSES_CHECKBOX_ID = 'all_courses_select'

    def _click_checkbox_and_wait_for_effects_to_propagate(self, checkbox):
        prev_counter = self._tester.driver.execute_script(
            'return gcbAdminOperationCount;')
        checkbox.click()
        def effects_have_propagated(driver):
            current_counter = driver.execute_script(
                'return gcbAdminOperationCount;')
            return current_counter > prev_counter
        self.wait().until(effects_have_propagated)

    def _toggle_checkbox(self, checkbox_id):
        checkbox = self.find_element_by_id(checkbox_id)
        self._click_checkbox_and_wait_for_effects_to_propagate(checkbox)

    def _set_checkbox(self, checkbox_id, value=True):
        checkbox = self.find_element_by_id(checkbox_id)
        checked = checkbox.get_attribute('checked')
        if (not checked and value) or (checked and not value):
            self._click_checkbox_and_wait_for_effects_to_propagate(checkbox)

    def _get_checkbox_state(self, checkbox_id):
        return self.find_element_by_id(
            checkbox_id).get_attribute('checked') == 'true'

    def toggle_course_checkbox(self, course_namespace):
        self._toggle_checkbox('select_' + course_namespace)
        return self

    def toggle_all_courses_checkbox(self):
        self._toggle_checkbox(self._SELECT_ALL_COURSES_CHECKBOX_ID)
        return self

    def set_all_courses_checkbox(self, value):
        self._set_checkbox(self._SELECT_ALL_COURSES_CHECKBOX_ID)
        return self

    def verify_course_checkbox_checked(self, course_namespace, expected_state):
        actual_state = self._get_checkbox_state('select_' + course_namespace)
        self._tester.assertEqual(expected_state, actual_state)
        return self

    def verify_all_courses_checkbox_checked(self, expected_state):
        actual_state = self._get_checkbox_state(
            self._SELECT_ALL_COURSES_CHECKBOX_ID)
        self._tester.assertEqual(expected_state, actual_state)
        return self

    def verify_all_courses_checkbox_indeterminate(self, expected_state):
        actual_state = self.find_element_by_id(
            self._SELECT_ALL_COURSES_CHECKBOX_ID).get_attribute(
                'indeterminate') == 'true'
        self._tester.assertEqual(expected_state, actual_state)
        return self

    def load(self, base_url):
        self.get(base_url + '/modules/admin')
        return self
