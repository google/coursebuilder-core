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
from models import config
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
        self.assertIsNone(dom.find('.//a[@href="admin?action=settings"]'))
        self.assertIsNone(dom.find('.//a[@href="admin?action=courses"]'))

    def test_admin_tab_is_present_for_admin(self):
        actions.login(self.ADMIN_EMAIL, is_admin=True)
        dom = self.parse_html_string(self.get('/dashboard').body)
        self.assertIsNotNone(dom.find('.//a[@href="admin?action=settings"]'))
        self.assertIsNotNone(dom.find('.//a[@href="admin?action=courses"]'))

    def test_admin_actions_unavailable_for_non_admin(self):
        actions.login(self.ADMIN_EMAIL, is_admin=False)

        response = self.get('admin?action=settings')
        self.assertEqual(302, response.status_int)

        response = self.get('admin?action=courses')
        self.assertEqual(302, response.status_int)

        response = self.post(
            'admin?action=config_reset&name=gcb_admin_user_emails', {})
        self.assertEqual(302, response.status_int)

    def test_admin_actions_available_for_admin(self):
        actions.login(self.ADMIN_EMAIL, is_admin=True)

        dom = self.parse_html_string(self.get('admin').body)
        site_settings_item = dom.find(
            './/*[@id="menu-item__settings__site"]')
        self.assertIsNotNone(site_settings_item)

        courses_item = dom.find('.//*[@id="menu-item__courses"]')
        self.assertIsNotNone(courses_item)

    def test_debug_info_not_present_for_non_admin(self):
        # NOTE: the is_admin=True version of this test is
        # functional.test_classes.AdminAspectTest.test_access_to_admin_pages

        # create another course which you shouldn't see
        actions.simple_add_course(
            'other-course', 'other-admin@example.com', 'Other Course')

        actions.login(self.ADMIN_EMAIL, is_admin=False)

        response = self.get('admin?action=deployment')
        dom = self.parse_html_string(response.body)

        # we should see our own course
        self.assertIn(self.COURSE_NAME, response.body)

        # we should not see other courses
        self.assertNotIn('Other Course', response.body)

        # we should not see admin features
        self.assertNotIn('application_id', response.body)
        self.assertNotIn('Modules', response.body)

    def test_deprecated_setting_hidden(self):

        def add_setting(deprecated):
            return config.ConfigProperty(
                'gcb_test_property', bool, 'doc string',
                label='Test Property Label', deprecated=deprecated)

        def delete_setting(setting):
            del config.Registry.registered[setting.name]

        actions.login(self.ADMIN_EMAIL, is_admin=True)

        # Setting should be visible when not deprecated.
        setting = add_setting(deprecated=False)
        response = self.get('admin?action=settings')
        self.assertIn(setting.label, response.body)
        delete_setting(setting)

        # Setting should not be shown when deprecated.
        setting = add_setting(deprecated=True)
        response = self.get('admin?action=settings')
        self.assertNotIn(setting.label, response.body)
        delete_setting(setting)
