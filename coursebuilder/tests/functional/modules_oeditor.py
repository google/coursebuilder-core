# Copyright 2014 Google Inc. All Rights Reserved.
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

"""Functional tests for the oeditor module."""

__author__ = [
    'John Cox (johncox@google.com)',
]

from models import config
from models import courses
from tests.functional import actions


class ObjectEditorTest(actions.TestBase):

    # Allow access to protected code under test.
    # pylint: disable-msg=protected-access

    def tearDown(self):
        config.Registry.test_overrides = {}
        super(ObjectEditorTest, self).tearDown()

    def get_oeditor_dom(self):
        actions.login('test@example.com', is_admin=True)
        response = self.get(
            '/admin?action=config_edit&name=gcb_admin_user_emails')
        return self.parse_html_string(response.body)

    def get_script_tag_by_src(self, src):
        return self.get_oeditor_dom().find('.//script[@src="%s"]' % src)

    def test_get_drive_tag_parent_frame_script_src_empty_if_apis_disabled(self):
        self.assertIsNone(self.get_script_tag_by_src(
            '/modules/core_tags/resources/drive_tag_parent_frame.js'))

    def test_get_drive_tag_parent_frame_script_src_set_if_apis_enabled(self):
        config.Registry.test_overrides[
            courses.COURSES_CAN_USE_GOOGLE_APIS.name] = True
        self.assertIsNotNone(self.get_script_tag_by_src(
            '/modules/core_tags/resources/drive_tag_parent_frame.js'))

    def test_get_drive_tag_script_manager_script_src_empty_if_apis_disabled(
            self):
        self.assertIsNone(self.get_script_tag_by_src(
            '/modules/core_tags/resources/drive_tag_script_manager.js'))

    def test_get_drive_tag_script_manager_script_src_set_if_apis_enabled(
            self):
        config.Registry.test_overrides[
            courses.COURSES_CAN_USE_GOOGLE_APIS.name] = True
        self.assertIsNotNone(self.get_script_tag_by_src(
            '/modules/core_tags/resources/drive_tag_script_manager.js'))
