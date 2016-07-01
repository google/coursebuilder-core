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

"""Integration tests for student groups."""

__author__ = [
    'Mike Gainer (mgainer@google.com)',
]

from tests.integration import pageobjects

from selenium.common import exceptions
from selenium.webdriver.support import select


class StudentGroupsListPage(pageobjects.DashboardPage):

    def click_add_group(self):
        self.find_element_by_id('edit_student_group').click()
        return StudentGroupEditorPage(self._tester)

    def click_edit_group(self, group_name):
        link = self.find_element_by_link_text(group_name)
        self.wait_for_page_load_after(link.click)
        return StudentGroupEditorPage(self._tester)

    def delete_group(self, group_name):
        delete_control = self.find_element_by_id('delete-' + group_name)
        def delete_and_accept_alert():
            delete_control.click()
            self.switch_to_alert().accept()
        self.wait_for_page_load_after(delete_and_accept_alert)
        return self

    def verify_group_on_page(self, group_name, expect_present):
        self.find_element_by_link_text('Add Group')  # Wait for valid page.
        try:
            self.find_element_by_link_text(group_name, pre_wait=False)
            actually_present = True
        except exceptions.NoSuchElementException:
            actually_present = False
        self._tester.assertEquals(expect_present, actually_present)
        return self


class StudentGroupEditorPage(pageobjects.EditorPageObject):

    def click_close(self):
        return self._close_and_return_to(StudentGroupsListPage)


class CourseAvailabilityPage(pageobjects.CourseAvailabilityPage):

    def verify_student_group_selector_presence(self, expect_present):
        # Force wait until page loaded by looking for an element that
        # should always be there.
        self.find_element_by_name('course_availability')

        # Is the student-group selector on the page?
        try:
            self.find_element_by_name('student_group', pre_wait=False)
            actually_present = True
        except exceptions.NoSuchElementException:
            actually_present = False
        self._tester.assertEquals(expect_present, actually_present)
        return self

    def select_student_group(self, option_text):
        select.Select(self.find_element_by_name(
            'student_group')).select_by_visible_text(option_text)
        return self

    def unsaved_changes_warning(self, option_text):
        if option_text == "Course":
            prefix = 'These course-wide availablity settings'
        else:
            prefix = 'These student group availability settings'
        return (prefix + ' have unsaved changes that will be' +
          ' lost if you switch.\n\nOK to switch anyway?')

    def cancel_unsaved_changes_warning(self, option_text):
        return self._handle_unsaved_changes_warning(option_text, dismiss=True)

    def ignore_unsaved_changes_warning(self, option_text):
        return self._handle_unsaved_changes_warning(option_text, accept=True)

    def _handle_unsaved_changes_warning(self, option_text,
                                        dismiss=False, accept=False):
        # One and only one of `dismiss` or `accept` must be True.
        self._tester.assertNotEqual(dismiss, accept)
        alert = self.switch_to_alert()
        self._tester.assertEqual(
            self.unsaved_changes_warning(option_text),
            alert.text)
        if accept:
            alert.accept()
        if dismiss:
            alert.dismiss()
        self._tester.assertEqual(
            self.where_am_i(),
            'dashboard?action=availability')
        return self
