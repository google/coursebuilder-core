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

"""Tests for extra tabs added to the navbar."""

__author__ = 'John Orr (jorr@google.com)'

from controllers import sites
from models import courses
from models import resources_display
from models import models
from modules.i18n_dashboard.i18n_dashboard import ResourceBundleDAO
from modules.i18n_dashboard.i18n_dashboard import ResourceBundleDTO
from modules.i18n_dashboard.i18n_dashboard import ResourceBundleKey
from tests.functional import actions

from google.appengine.api import namespace_manager

ADMIN_EMAIL = 'admin@foo.com'
COURSE_NAME = 'extra_tabs_course'
SENDER_EMAIL = 'sender@foo.com'
STUDENT_EMAIL = 'student@foo.com'
STUDENT_NAME = 'A. Student'


class ExtraTabsTests(actions.TestBase):

    def setUp(self):
        super(ExtraTabsTests, self).setUp()

        self.base = '/' + COURSE_NAME
        app_context = actions.simple_add_course(
            COURSE_NAME, ADMIN_EMAIL, 'Extra Tabs Course')
        self.old_namespace = namespace_manager.get_namespace()
        namespace_manager.set_namespace('ns_%s' % COURSE_NAME)

        self.course = courses.Course(None, app_context)

        courses.Course.ENVIRON_TEST_OVERRIDES = {
            'course': {
                'extra_tabs': [
                    {
                        'label': 'FAQ',
                        'position': 'left',
                        'visibility': 'all',
                        'url': '',
                        'content': 'Frequently asked questions'},
                    {
                        'label': 'Resources',
                        'position': 'right',
                        'visibility': 'student',
                        'url': 'http://www.example.com',
                        'content': 'Links to resources'}]
            }
        }
        self.faq_url = 'modules/extra_tabs/render?index=0'

        actions.login(STUDENT_EMAIL, is_admin=False)
        actions.register(self, STUDENT_NAME)

    def tearDown(self):
        del sites.Registry.test_overrides[sites.GCB_COURSES_CONFIG.name]
        namespace_manager.set_namespace(self.old_namespace)
        courses.Course.ENVIRON_TEST_OVERRIDES = {}
        super(ExtraTabsTests, self).tearDown()

    def test_extra_tabs_on_navbar_visible_to_students(self):
        body = self.get('course').body
        self.assertIn('FAQ', body)
        self.assertIn('Resources', body)

    def test_extra_tabs_on_navbar_visible_to_everyone(self):
        actions.logout()
        body = self.get('course').body
        self.assertIn('FAQ', body)
        self.assertNotIn('Resources', body)

    def test_extra_tabs_with_url_point_to_target(self):
        dom = self.parse_html_string(self.get('course').body)
        resources_el = dom.find('.//div[@id="gcb-nav-x"]//ul/li[5]/a')
        self.assertEquals('Resources', resources_el.text)
        self.assertEquals('http://www.example.com', resources_el.attrib['href'])

    def test_extra_tabs_with_content_point_to_page(self):
        dom = self.parse_html_string(self.get('course').body)
        faq_el = dom.find('.//div[@id="gcb-nav-x"]//ul/li[4]/a')
        self.assertEquals('FAQ', faq_el.text)
        self.assertEquals(self.faq_url, faq_el.attrib['href'])

    def test_content_handler_delivers_page(self):
        self.assertIn('Frequently asked questions', self.get(self.faq_url))

    def test_tabs_are_aligned_correctly(self):
        dom = self.parse_html_string(self.get('course').body)
        faq_li = dom.find('.//div[@id="gcb-nav-x"]//ul/li[4]')
        self.assertIsNone(faq_li.attrib.get('class'))
        resources_li = dom.find('.//div[@id="gcb-nav-x"]//ul/li[5]')
        self.assertIn('gcb-pull-right', resources_li.attrib['class'])

    def test_tabs_are_translated(self):
        courses.Course.ENVIRON_TEST_OVERRIDES['extra_locales'] = [{
            'availability': 'available', 'locale': 'el'}]

        prefs = models.StudentPreferencesDAO.load_or_default()
        prefs.locale = 'el'
        models.StudentPreferencesDAO.save(prefs)

        bundle = {
            'course:extra_tabs:[0]:label': {
                'type': 'string',
                'source_value': None,
                'data': [
                    {'source_value': 'FAQ', 'target_value': 'faq'}]},
            'course:extra_tabs:[0]:content': {
                'type': 'html',
                'source_value': 'Frequently asked questions',
                'data': [{
                    'source_value': 'Frequently asked questions',
                    'target_value': 'fREQUENTLY aSKED qUESTIONS'}]}}
        key_el = ResourceBundleKey(
            resources_display.ResourceCourseSettings.TYPE, 'homepage', 'el')
        ResourceBundleDAO.save(ResourceBundleDTO(str(key_el), bundle))

        dom = self.parse_html_string(self.get('course').body)
        faq_el = dom.find('.//div[@id="gcb-nav-x"]//ul/li[4]/a')
        self.assertEquals('faq', faq_el.text)
        self.assertEquals(self.faq_url, faq_el.attrib['href'])
        self.assertIn('fREQUENTLY aSKED qUESTIONS', self.get(self.faq_url))
