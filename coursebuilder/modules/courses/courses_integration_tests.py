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

"""Per-course integration tests for Course Builder."""

__author__ = [
    'Todd Larsen (tlarsen@google.com)'
]

from modules.courses import courses_pageobjects
from tests.integration import integration


class AvailabilityTests(integration.TestBase):

    def setUp(self):
        super(AvailabilityTests, self).setUp()
        self.login(self.LOGIN, admin=True)

    def test_availability_page_js(self):
        """Checks the parts of the Publish > Availability page contents that
        are dynamically altered by availability.js.
        """
        sample_course_name = ''  # Power Searching course w/ blank namespace.
        sample_availablity_page = self.load_dashboard(
            sample_course_name
        ).click_availability(
            cls=courses_pageobjects.CourseAvailabilityPage
        ).verify_content_present_no_msgs(
            has_triggers=True
        ).verify_add_trigger_button(
        )

        empty_course_name = self.create_new_course(login=False)[0]
        self.load_dashboard(
            empty_course_name
        ).click_availability(
            cls=courses_pageobjects.CourseAvailabilityPage
        ).verify_empty_content_msgs(
        ).verify_no_trigger_button(
        )
