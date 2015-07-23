# Copyright 2015 Google Inc. All Rights Reserved.
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

"""Tests for modules/admin. (See also test_classes.AdminAspectTest."""

__author__ = 'John Orr (jorr@google.com)'

from controllers import sites
from models import courses
from tests.functional import actions

from google.appengine.api import namespace_manager


class AdminDashboardTabTests(actions.TestBase):

    ADMIN_EMAIL = 'adin@foo.com'
    COURSE_NAME = 'admin_tab_test_course'

    def setUp(self):
        super(AdminDashboardTabTests, self).setUp()

        self.base = '/' + self.COURSE_NAME
        context = actions.simple_add_course(
            self.COURSE_NAME, self.ADMIN_EMAIL, 'I18N Course')
        self.old_namespace = namespace_manager.get_namespace()
        namespace_manager.set_namespace('ns_%s' % self.COURSE_NAME)

        self.course = courses.Course(None, context)

    def tearDown(self):
        del sites.Registry.test_overrides[sites.GCB_COURSES_CONFIG.name]
        namespace_manager.set_namespace(self.old_namespace)
        super(AdminDashboardTabTests, self).tearDown()

    def test_admin_tab_not_present_for_non_admin(self):
        actions.login(self.ADMIN_EMAIL, is_admin=False)
        dom = self.parse_html_string(self.get('/dashboard').body)
        self.assertIsNone(dom.find('.//a[@href="admin?action=courses"]'))

    def test_admin_tab_is_present_for_admin(self):
        actions.login(self.ADMIN_EMAIL, is_admin=True)
        dom = self.parse_html_string(self.get('/dashboard').body)
        self.assertIsNotNone(dom.find('.//a[@href="admin?action=courses"]'))

    def test_admin_actions_unavailable_for_non_admin(self):
        actions.login(self.ADMIN_EMAIL, is_admin=False)

        response = self.get('admin?action=courses')
        self.assertEqual(302, response.status_int)

        response = self.post(
            'admin?action=config_reset&name=gcb_admin_user_emails', {})
        self.assertEqual(302, response.status_int)

    def test_admin_actions_available_for_admin(self):
        actions.login(self.ADMIN_EMAIL, is_admin=True)

        dom = self.parse_html_string(self.get('admin').body)
        group = dom.find('.//*[@id="menu-group__admin"]')
        self.assertIsNotNone(group)
