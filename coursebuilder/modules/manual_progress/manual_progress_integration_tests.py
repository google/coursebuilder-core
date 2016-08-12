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

__author__ = [
    'Mike Gainer (mgainer@google.com)',
]

from modules.manual_progress import manual_progress_pageobjects
from tests.integration import integration


class ManualProgressTest(integration.TestBase):

    def test_manual_progress(self):
        name = self.create_new_course()[0]
        self.load_dashboard(
            name
        ).click_add_unit(
        ).set_title(
            'Test Unit 1'
        ).set_manual_progress_unit(
            True
        ).click_save(
        ).click_close(
        ).click_add_lesson(
        ).set_title(
            'Test Lesson 1.1'
        ).select_settings(
        ).set_manual_progress_lesson(
            True
        ).click_save(
        ).click_close(
        ).click_add_lesson(
        ).set_title(
            'Test Lesson 1.2'
        ).select_settings(
        ).set_manual_progress_lesson(
            True
        ).click_save(
        ).click_close(
        ).click_add_unit(
        ).set_title(
            'Test Unit 2'
        ).click_save(
        ).click_close(
        ).click_add_lesson(
            1
        ).set_title(
            'Test Lesson 2.1'
        ).click_save(
        ).click_close(
        ).click_add_lesson(
            1
        ).set_title(
            'Test Lesson 2.2'
        ).click_save(
        ).click_close(

        # Should be no manual completion items on lesson page; student is
        # not registered.
        ).click_on_course_outline_components(
            '1. Test Lesson 1.1'
        )
        manual_progress_pageobjects.ManualCompletionPage(
            self
        ).verify_no_manual_completion_unit(
        ).verify_no_manual_completion_lesson(
        ).verify_no_manual_completion_course(
        ).click_link(
            'Course'
        ).verify_no_manual_completion_unit(
        ).verify_no_manual_completion_lesson(
        ).verify_no_manual_completion_course()

        # Now register; manual completion items for unit, lesson should
        # now be present.
        self.load_root_page(
        ).register_for_course(
            name
        )

        manual_progress_pageobjects.ManualCompletionPage(
            self
        ).verify_no_manual_completion_unit(
        ).verify_no_manual_completion_lesson(
        ).click_link(
            'Unit 1 - Test Unit 1'
        ).click_complete_lesson(
        ).click_link(
            'Course'
        ).verify_progress(
            ['In progress', 'Not yet started']
        ).click_link(
            'Unit 1 - Test Unit 1'
        ).verify_no_manual_completion_lesson(

        # Complete unit manually; unit should now show as completed,
        # despite us never having visited lesson 1.2
        ).click_complete_unit(
        ).click_link(
            'Course'
        ).verify_progress(
            ['Completed', 'Not yet started']
        ).click_link(
            'Unit 1 - Test Unit 1'
        ).verify_no_manual_completion_lesson(
        ).verify_no_manual_completion_unit(
        ).click_link(
            'Course'

        # Verify unit 2, which is not marked for manual completion, has
        # no completion controls.
        ).click_link(
            'Unit 2 - Test Unit 2'
        ).verify_no_manual_completion_unit(
        ).verify_no_manual_completion_lesson(
        ).verify_no_manual_completion_course(
        )
