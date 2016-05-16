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

import re

from modules.admin import admin
from selenium.common import exceptions
from selenium.webdriver.common import action_chains
from selenium.webdriver.support import select

from tests.integration import pageobjects


class CoursesListPage(pageobjects.CoursesListPage):
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

    def _match_enrolled_count_and_tooltip(self, namespace, count, tooltip):
        count_div_selector = '#enrolled_{}'.format(namespace)
        tooltip_selector = '#activity_{}'.format(namespace)

        def count_div_equals_count(driver):
            count_div = self.find_element_by_css_selector(count_div_selector)
            match = (count == count_div.text.strip())
            if not match:
                self.load(None) # Just use last-seen base_url value.
            return match

        # Verification will fail by timeout if expected count never appears.
        self.wait().until(count_div_equals_count)

        def tooltip_match_pops_up(driver):
            count_div = self.find_element_by_css_selector(count_div_selector)
            action_chains.ActionChains(self._tester.driver).move_to_element(
                count_div).perform()
            tooltip_div = self.find_element_by_css_selector(tooltip_selector)
            match = re.match(tooltip, tooltip_div.text.strip())
            if not match:
                self.load(None) # Just use last-seen base_url value.
            return match

        # Verification will fail by timeout if expected count never appears.
        self.wait().until(tooltip_match_pops_up)
        return self

    def verify_no_enrollments(self, namespace, title):
        text = admin.BaseAdminHandler.NONE_ENROLLED
        regexp = re.escape(
            '(registration activity for %s is being computed)' % title)
        return self._match_enrolled_count_and_tooltip(namespace, text, regexp)

    DATETIME_REGEXP = "[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}"

    def verify_total_enrollments(self, namespace, title, count):
        text = "%d" % count
        regexp = ('Most recent activity at %s UTC for %s' %
                  (self.DATETIME_REGEXP, re.escape(title + '.')))
        return self._match_enrolled_count_and_tooltip(namespace, text, regexp)

    def verify_availability(self, namespace, expected):
        a_href = self.find_element_by_id('availability_' + namespace)
        self._tester.assertEqual(expected, a_href.text.strip())
        return self

    def click_edit_availability(self):
        self.find_element_by_id('edit_multi_course_availability').click()
        return MultiEditModalDialog(self._tester)


class MultiEditModalDialog(pageobjects.CoursesListPage):

    def __init__(self, tester):
        super(MultiEditModalDialog, self).__init__(tester)
        # Wait for main div of modal dialog to be visible.
        self._dialog = self.find_element_by_id('multi-course-edit-panel')

    def _dialog_not_visible(self, unused_driver):
        try:
            return not self._dialog.is_displayed()
        except exceptions.StaleElementReferenceException:
            return True

    def click_cancel(self):
        self.find_element_by_id('multi-course-cancel').click()
        self.wait().until(self._dialog_not_visible)
        return CoursesListPage(self._tester)

    def click_save(self):
        self.find_element_by_id('multi-course-save').click()
        spinner = self.find_element_by_id('multi-course-spinner')
        def spinner_not_visible(driver):
            try:
                return not spinner.is_displayed()
            except exceptions.StaleElementReferenceException:
                return True
        self.wait().until(spinner_not_visible)
        return self

    def set_availability(self, value):
        select_elt = self.find_element_by_id('multi-course-select-availability')
        select.Select(select_elt).select_by_visible_text(value)
        return self

    def assert_status(self, namespace, text):
        td = self.find_element_by_id('course_status_' + namespace)
        self._tester.assertEqual(text, td.text.strip())
        return self

    def set_availability_xsrf_token(self, new_value):
        self._tester.driver.execute_script(
            'gcb_multi_edit_dialog._xsrfToken = "%s";' % new_value)
        return self
