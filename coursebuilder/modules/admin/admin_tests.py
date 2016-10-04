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

import re

from common import safe_dom
from controllers import sites
from models import config
from models import courses
from modules.admin import admin
from tests.functional import actions

from google.appengine.api import namespace_manager


class AdminDashboardTabTests(actions.TestBase):

    ADMIN_EMAIL = 'adin@foo.com'
    COURSE_NAME = 'admin_tab_test_course'
    NAMESPACE = 'ns_' + COURSE_NAME

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

    def test_admin_welcome_shows_redirects_for_non_admin(self):
        actions.login(self.ADMIN_EMAIL, is_admin=False)

        response = self.get('/admin/welcome', expect_errors=True)

        self.assertEqual(response.status_int, 403)
        self.assertIsNotNone(
            re.search('<a.*>Login page</a>', response.text))
        self.assertIsNotNone(
            re.search('<a href="/">Home page</a>', response.text))

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

    def test_availability_link_on_page(self):
        # Find availability link on admin page for our course.
        actions.login(self.ADMIN_EMAIL, is_admin=True)
        response = self.get('/modules/admin')
        dom = self.parse_html_string_to_soup(response.body)
        link = dom.select('#availability_ns_' + self.COURSE_NAME)[0]

        # Follow the link; verify that we're on the per-course availability page
        response = self.get(link.get('href'))
        dom = self.parse_html_string_to_soup(response.body)
        titles = dom.select('.mdl-layout-title')
        title_texts = [re.sub(r'\s+', ' ', t.text).strip() for t in titles]
        self.assertIn('Publish > Availability', title_texts)

    def test_availability_title(self):
        def get_availability_text():
            response = self.get('/modules/admin')
            dom = self.parse_html_string_to_soup(response.body)
            link = dom.select('#availability_ns_' + self.COURSE_NAME)[0]
            return re.sub(r'\s+', ' ', link.text).strip()

        actions.login(self.ADMIN_EMAIL, is_admin=True)
        for policy, settings in courses.COURSE_AVAILABILITY_POLICIES.items():
            # Fetch the instance of the app_context from the per-process
            # cache so that that's the instance that clears its internal
            # cache of settings when we modify the course availability.
            app_context = sites.get_app_context_for_namespace(self.NAMESPACE)
            courses.Course.get(app_context).set_course_availability(policy)
            self.assertEqual(settings['title'], get_availability_text())


class TestAdditionalAllCoursesColumn(object):

    def __init__(self):
        self._num_courses = 0

    def produce_table_header(self):
        return safe_dom.Element(
            'th', className='additional_header'
        ).add_text(
            'Test Column'
        )

    def produce_table_row(self, app_context):
        self._num_courses += 1
        return safe_dom.Element(
            'td', className='additional_column'
        ).add_text(
            'Course %d' % self._num_courses
        )

    def produce_table_footer(self):
        return safe_dom.Element(
            'td', className='additional_footer'
        ).add_text(
            '%d Total Courses' % self._num_courses
        )


class AdminCourseListTests(actions.TestBase):

    ADMIN_EMAIL = 'admin@example.com'
    NUM_COURSES = 3

    def setUp(self):
        super(AdminCourseListTests, self).setUp()
        self.app_contexts = []
        course_configs = []
        for i in xrange(self.NUM_COURSES):
            self.app_contexts.append(actions.simple_add_course(
                'course_%d' % i, self.ADMIN_EMAIL, 'Course %d' % i))
            course_configs.append('course:/course_%d::ns_course_%d' % (i, i))

        # Suppress default course from admin all-courses list.
        config.Registry.test_overrides[sites.GCB_COURSES_CONFIG.name] = (
            ','.join(course_configs))

        admin.BaseAdminHandler.ADDITIONAL_COLUMN_HOOKS[
            self.__class__.__name__] = TestAdditionalAllCoursesColumn()
        actions.login(self.ADMIN_EMAIL, is_admin=True)

    def tearDown(self):
        del admin.BaseAdminHandler.ADDITIONAL_COLUMN_HOOKS[
            self.__class__.__name__]
        del config.Registry.test_overrides[sites.GCB_COURSES_CONFIG.name]
        sites.reset_courses()
        super(AdminCourseListTests, self).tearDown()

    def test_additional_columns(self):
        response = self.get('/modules/admin')
        soup = self.parse_html_string_to_soup(response.body)

        headers = soup.select('.additional_header')
        self.assertEquals(['th'], [h.name for h in headers])
        self.assertEquals(['Test Column'], [h.text for h in headers])

        rows = soup.select('.additional_column')
        self.assertEquals(['td'] * self.NUM_COURSES, [r.name for r in rows])
        expected = ['Course %d' % (i + 1) for i in xrange(self.NUM_COURSES)]
        self.assertEquals(expected, [r.text for r in rows])

        footers = soup.select('.additional_footer')
        self.assertEquals(['td'], [f.name for f in footers])
        self.assertEquals(['%d Total Courses' % self.NUM_COURSES],
                          [f.text for f in footers])
