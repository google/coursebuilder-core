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

from modules.student_groups import student_groups_pageobjects
from tests.integration import integration


class AvailabilityTests(integration.TestBase):

    def test_availability_settings(self):
        name = self.create_new_course()[0]
        self.load_dashboard(
            name
        ).click_add_unit(
        ).set_title(
            'Test Unit 1'
        ).click_save(
        ).click_close()

        # Verify student-group availability picker not present when there
        # are no student groups added.
        self.load_dashboard(
            name
        ).click_availability(
            cls=student_groups_pageobjects.CourseAvailabilityPage
        ).verify_student_group_selector_presence(
            True
        )

        # Use availability page to set different students for whitelist
        # for course and group.
        self.load_dashboard(
            name
        ).click_leftnav_item_by_id(
            'settings', 'menu-item__settings__student_groups',
            student_groups_pageobjects.StudentGroupsListPage
        ).click_add_group(
        ).set_text_field_by_title(
            'Group Name',
            'My New Group'
        ).set_textarea_field_by_title(
            'Group Description',
            'There are many like it, but this one is mine.'
        ).click_save(
        ).click_close(
        ).click_edit_group(
            'My New Group'
        ).verify_text_field_by_title(
            'Group Name',
            'My New Group'
        ).verify_textarea_field_by_title(
            'Group Description',
            'There are many like it, but this one is mine.'
        ).click_close(
        ).click_availability(
            cls=student_groups_pageobjects.CourseAvailabilityPage
        ).verify_student_group_selector_presence(
            True
        ).select_student_group(
            'Student Group: My New Group'
        ).wait_until_button_enabled(
            'Save'
        ).set_whitelisted_students(
            ['group_student@foo.com'],
            'members'
        ).click_save(
            status_message='Saved'
        ).select_student_group(
            'Course'
        ).wait_until_button_enabled(
            'Save'
        ).set_whitelisted_students(
            ['course_student@foo.com'],
            'whitelist'
        ).click_save(
        )

        # Re-navigate to availability page.  Verify that corrent whitelist
        # contents are still there upon reload.
        self.load_dashboard(
            name
        ).click_availability(
            cls=student_groups_pageobjects.CourseAvailabilityPage
        ).verify_whitelisted_students(
            'course_student@foo.com',
            'whitelist'
        ).select_student_group(
            'Student Group: My New Group'
        ).wait_until_button_enabled(
            'Save'
        ).verify_whitelisted_students(
            'group_student@foo.com',
            'members'
        )

        # Verify deleting via the list view works.
        self.load_dashboard(
            name
        ).click_leftnav_item_by_id(
            'settings', 'menu-item__settings__student_groups',
            student_groups_pageobjects.StudentGroupsListPage
        ).verify_group_on_page(
            'My New Group', True
        ).delete_group(
            'My New Group'
        ).verify_group_on_page(
            'My New Group', False
        )
