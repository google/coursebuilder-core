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

"""Page objects for per-course admin integration tests for Course Builder."""

__author__ = [
    'Todd larsen (tlarsen@google.com)'
]

from modules.courses import availability

from tests import suite
from tests.integration import pageobjects


class CourseAvailabilityPage(pageobjects.CourseAvailabilityPage):

    CONTENT_LIST_CSS_SEL = (
        '.availability-manager .content-availability' +
        ' > .inputEx-ListField-childContainer')
    EMPTY_CONTENT_CSS_SEL = CONTENT_LIST_CSS_SEL + ' .no-course-content'

    TRIGGER_LIST_CSS_SEL = (
        '.availability-manager .content-triggers' +
        ' > .inputEx-ListField-childContainer')
    EMPTY_TRIGGER_CSS_SEL = TRIGGER_LIST_CSS_SEL + ' .no-course-content'

    EMPTY_CONTENT_MSG = 'No course content available.'

    EMPTY_TRIGGERS_MSG = (
        'Create course content (units, lessons, assessments) before defining' +
        ' any date/time availability change triggers.')

    def load(self, name):
        def load_page():
            super(CourseAvailabilityPage, self).load(
                suite.TestBase.INTEGRATION_SERVER_BASE_URL,
                suffix='/%s/dashboard?action=availability' % name)
        self.wait_for_page_load_after(load_page)
        return self

    def get_settings(self):
        course_avail = self.get_selected_value_by_css(
            'select[name="course_availability"]')

        start_avail = self.get_selected_value_by_css(
            'select[name="course_start[0]availability"]')
        start_date = self.get_text_field_by_name(
            'course_start[0]group-1[0]')
        start_hour = self.get_selected_value_by_css(
            'select[name="course_start[0]group-1[1][0]"]')

        end_avail = self.get_selected_value_by_css(
            'select[name="course_end[0]availability"]')
        end_date = self.get_text_field_by_name(
            'course_end[0]group-1[0]')
        end_hour = self.get_selected_value_by_css(
            'select[name="course_end[0]group-1[1][0]"]')

        # TODO(mgainer): Could also grab other settings for
        # course-level contents on this page.  Do as necessary.

        # Returning as a plain dict instead of namedtuple; this substantially
        # decreases the amount of repetetive creation of expected results in
        # tests that do incremental changes to settings.
        return {
            'availability': str(course_avail),
            'start_trigger': {
                'availability': str(start_avail),
                'date': str(start_date),
                'hour': str(start_hour),
            },
            'end_trigger': {
                'availability': str(end_avail),
                'date': str(end_date),
                'hour': str(end_hour),
            },
        }

    def verify_empty_content_msgs(self):
        """Verifies that two sections on the Publish > Availability page
        display text placeholders put there by availability.js when there is
        no course content.
        """
        empty_content_div = self.find_element_by_css_selector(
            self.EMPTY_CONTENT_CSS_SEL)
        self._tester.assertEquals(
            self.EMPTY_CONTENT_MSG,
            empty_content_div.text.strip())

        empty_triggers_div = self.find_element_by_css_selector(
            self.EMPTY_TRIGGER_CSS_SEL)
        self._tester.assertEquals(
            self.EMPTY_TRIGGERS_MSG,
            empty_triggers_div.text.strip())
        return self

    CONTAINS_EMPTY_CONTENT_MSG_RE = '^.*' + EMPTY_CONTENT_MSG + '.*$'
    CONTAINS_EMPTY_TRIGGERS_MSG_RE = '^.*' + EMPTY_TRIGGERS_MSG + '.*$'

    def verify_content_present_no_msgs(self, has_triggers=True):
        """Verifies that two sections on the Publish > Availability page do
        *not* display text placeholders put there by availability.js when
        there course content *is* present.
        """
        content_div = self.find_element_by_css_selector(
            self.CONTENT_LIST_CSS_SEL)
        self._tester.assertNotRegexpMatches(
            content_div.text.strip(), self.CONTAINS_EMPTY_CONTENT_MSG_RE)

        triggers_div = self.find_element_by_css_selector(
            self.TRIGGER_LIST_CSS_SEL, pre_wait=False)
        self._tester.assertNotRegexpMatches(
            triggers_div.text.strip(), self.CONTAINS_EMPTY_TRIGGERS_MSG_RE)
        if not has_triggers:
            # With no triggers created yet,
            self._tester.assertEquals('', triggers_div.text.strip())
        # else:
        # TODO(tlarsen): Examine a created availability trigger.
        return self

    NO_TRIGGER_BUTTON_CSS_SEL = (
        '.availability-manager .content-triggers > a.inputEx-List-link')

    def verify_no_trigger_button(self):
        """Verifies the 'Add date/time availability change' button is not
        visible if there is no course content.
        """
        # .inputEx-List-link 'Add' button should not be visible (no pre_wait).
        add_button = self.find_element_by_css_selector(
            self.NO_TRIGGER_BUTTON_CSS_SEL, pre_wait=False)
        # .inputEx-List-link 'Add' button should not be visible (no text).
        self._tester.assertEquals('', add_button.text.strip())
        return self

    # 'Add...' button is re-parented out of div.content-triggers.
    ADD_TRIGGER_BUTTON_CSS_SEL = ' '.join([
        '.availability-manager', '.content-triggers',
        '+ div.add-content-trigger', '> a.gcb-button'])

    def verify_add_trigger_button(self):
        """Verifies if course content is present, that the
        'Add date/time availability change' button text is visible, and that
        the <a> button has been re-parented outside the .content-triggers
        list div, to appear below that section.
        """
        # .gcb-button 'Add' button should be visible; wait for it to appear.
        add_button = self.find_element_by_css_selector(
            self.ADD_TRIGGER_BUTTON_CSS_SEL, pre_wait=True)
        # Visible .gcb-button 'Add' button should contain the button text.
        self._tester.assertEquals(
            availability.AvailabilityRESTHandler.ADD_TRIGGER_BUTTON_TEXT,
            add_button.text.strip())
        return self
