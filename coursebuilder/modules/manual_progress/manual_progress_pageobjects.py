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

"""Test JS UI for manual marking of course/unit/lesson progress."""

__author__ = 'Mike Gainer (mgainer@google.com)'

from tests.integration import pageobjects

from selenium.common import exceptions


class ManualCompletionPage(pageobjects.RootPage):

    def _verify_no_manual_completion_element(self, name):
        try:
            element = self.find_element_by_css_selector(
                '#manual-progress-completion-%s' % name, pre_wait=False)
            self._tester.fail('Should not find element')
        except exceptions.NoSuchElementException:
            pass
        return self

    def verify_no_manual_completion_course(self):
        return self._verify_no_manual_completion_element('course')

    def verify_no_manual_completion_unit(self):
        return self._verify_no_manual_completion_element('unit')

    def verify_no_manual_completion_lesson(self):
        return self._verify_no_manual_completion_element('lesson')

    def _click_complete(self, element_name):
        self.find_element_by_css_selector(element_name).click()
        self.expect_status_message_to_be('OK.')
        return self

    def click_complete_course(self):
        return self._click_complete('#manual-progress-complete-course')

    def click_complete_unit(self):
        return self._click_complete('#manual-progress-complete-unit')

    def click_complete_lesson(self):
        return self._click_complete('#manual-progress-complete-lesson')

    def verify_progress(self, expected_progress):
        progress_icons = self.find_elements_by_css_selector(
            '.gcb-progress-icon')
        actual_progress = [i.get_attribute('alt') for i in progress_icons]
        self._tester.assertEquals(expected_progress, actual_progress)
        return self
