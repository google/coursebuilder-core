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

"""Tests that walk through Course Builder pages."""

__author__ = 'Mike Gainer (mgainer@google.com)'

import cgi
import re

from common import crypto
from common import utils as common_utils
from controllers import sites
from models import courses
from models import models
from models import transforms
from modules.dashboard import course_settings
from modules.dashboard import filer
from tests.functional import actions
from tests.functional.actions import assert_contains
from tests.functional.actions import assert_does_not_contain

COURSE_NAME = 'admin_settings'
COURSE_TITLE = 'Admin Settings'
ADMIN_EMAIL = 'admin@foo.com'
NAMESPACE = 'ns_%s' % COURSE_NAME
BASE_URL = '/' + COURSE_NAME
ADMIN_SETTINGS_URL = '/%s%s' % (
    COURSE_NAME, course_settings.HtmlHookRESTHandler.URI)
TEXT_ASSET_URL = '/%s%s' % (
    COURSE_NAME, filer.TextAssetRESTHandler.URI)
STUDENT_EMAIL = 'student@foo.com'
SETTINGS_URL = '/%s/dashboard?action=settings&tab=admin_prefs' % COURSE_NAME


class AdminSettingsTests(actions.TestBase):

    def setUp(self):
        super(AdminSettingsTests, self).setUp()
        actions.simple_add_course(COURSE_NAME, ADMIN_EMAIL, COURSE_TITLE)
        actions.login(ADMIN_EMAIL)

    def test_defaults(self):
        prefs = models.StudentPreferencesDAO.load_or_create()
        self.assertEquals(True, prefs.show_hooks)

    def test_settings_page(self):
        response = self.get(SETTINGS_URL)
        self.assertIn('Show hook edit buttons: True', response.body)

        with common_utils.Namespace(NAMESPACE):
            prefs = models.StudentPreferencesDAO.load_or_create()
            prefs.show_hooks = False
            models.StudentPreferencesDAO.save(prefs)
        response = self.get(SETTINGS_URL)
        self.assertIn('Show hook edit buttons: False', response.body)


class WelcomePageTests(actions.TestBase):

    def setUp(self):
        super(WelcomePageTests, self).setUp()
        self.auto_deploy = sites.ApplicationContext.AUTO_DEPLOY_DEFAULT_COURSE
        sites.ApplicationContext.AUTO_DEPLOY_DEFAULT_COURSE = False

    def tearDown(self):
        sites.ApplicationContext.AUTO_DEPLOY_DEFAULT_COURSE = self.auto_deploy
        super(WelcomePageTests, self).tearDown()

    def test_welcome_page(self):
        actions.login(ADMIN_EMAIL, is_admin=True)
        response = self.get('/')
        self.assertEqual(response.status_int, 302)
        self.assertEqual(
            response.headers['location'],
            'http://localhost/admin?action=welcome')
        response = self.get('/admin?action=welcome')
        assert_contains('Welcome to Course Builder', response.body)
        assert_contains('/admin?action=add_first_course', response.body)
        assert_contains('/admin?action=explore_sample', response.body)

    def test_explore_sample_course(self):
        actions.login(ADMIN_EMAIL, is_admin=True)
        response = self.post(
            '/admin?action=explore_sample',
            params={'xsrf_token': crypto.XsrfTokenManager.create_xsrf_token(
                'explore_sample')})
        self.assertEqual(response.status_int, 302)
        self.assertEqual(
            response.headers['location'],
            'http://localhost/sample/dashboard')
        response = self.get('/sample/dashboard')
        assert_contains('Power Searching with Google', response.body)
        assert_does_not_contain('explore_sample', response.body)

    def test_create_new_course(self):
        actions.login(ADMIN_EMAIL, is_admin=True)
        response = self.post(
            '/admin?action=add_first_course',
            params={'xsrf_token': crypto.XsrfTokenManager.create_xsrf_token(
                'add_first_course')})
        self.assertEqual(response.status_int, 302)
        self.assertEqual(
            response.headers['location'],
            'http://localhost/first/dashboard')
        response = self.get('/first/dashboard')
        assert_contains('My First Course', response.body)
        response = self.get('/admin?action=welcome')
        assert_does_not_contain('add_first_course', response.body)

    def test_explore_sample_course_idempotent(self):
        self.test_explore_sample_course()
        self.test_explore_sample_course()

        self.test_create_new_course()
        response = self.get('/')
        self.assertEqual(response.status_int, 302)
        self.assertEqual(
            response.headers['location'],
            'http://localhost/sample/course?use_last_location=true')

    def test_create_new_course_idempotent(self):
        self.test_create_new_course()
        self.test_create_new_course()

        self.test_explore_sample_course()
        response = self.get('/')
        self.assertEqual(response.status_int, 302)
        self.assertEqual(
            response.headers['location'],
            'http://localhost/first/course?use_last_location=true')


class HtmlHookTest(actions.TestBase):

    def setUp(self):
        super(HtmlHookTest, self).setUp()

        context = actions.simple_add_course(COURSE_NAME, ADMIN_EMAIL,
                                            COURSE_TITLE)
        self.course = courses.Course(None, context)
        actions.login(ADMIN_EMAIL, is_admin=True)
        self.xsrf_token = crypto.XsrfTokenManager.create_xsrf_token(
            course_settings.HtmlHookRESTHandler.XSRF_ACTION)

    def test_hook_edit_button_presence(self):

        # Turn preference on; expect to see hook editor button
        with common_utils.Namespace(NAMESPACE):
            prefs = models.StudentPreferencesDAO.load_or_create()
            prefs.show_hooks = True
            models.StudentPreferencesDAO.save(prefs)
        response = self.get(BASE_URL)
        self.assertIn('gcb-html-hook-edit', response.body)

        # Turn preference off; expect editor button not present.
        with common_utils.Namespace(NAMESPACE):
            prefs = models.StudentPreferencesDAO.load_or_create()
            prefs.show_hooks = False
            models.StudentPreferencesDAO.save(prefs)

        response = self.get(BASE_URL)
        self.assertNotIn('gcb-html-hook-edit', response.body)

    def test_non_admin_permissions_failures(self):
        actions.login(STUDENT_EMAIL)
        student_xsrf_token = crypto.XsrfTokenManager.create_xsrf_token(
            course_settings.HtmlHookRESTHandler.XSRF_ACTION)

        response = self.get(ADMIN_SETTINGS_URL)
        self.assertEquals(200, response.status_int)
        payload = transforms.loads(response.body)
        self.assertEquals(401, payload['status'])
        self.assertEquals('Access denied.', payload['message'])

        response = self.put(ADMIN_SETTINGS_URL, {'request': transforms.dumps({
                'key': 'base:after_body_tag_begins',
                'xsrf_token': cgi.escape(student_xsrf_token),
                'payload': '{}'})})
        payload = transforms.loads(response.body)
        self.assertEquals(401, payload['status'])
        self.assertEquals('Access denied.', payload['message'])

        response = self.delete(ADMIN_SETTINGS_URL + '?xsrf_token=' +
                               cgi.escape(student_xsrf_token))
        self.assertEquals(200, response.status_int)
        payload = transforms.loads(response.body)
        self.assertEquals(401, payload['status'])
        self.assertEquals('Access denied.', payload['message'])

    def test_malformed_requests(self):
        response = self.put(ADMIN_SETTINGS_URL, {})
        payload = transforms.loads(response.body)
        self.assertEquals(400, payload['status'])
        self.assertEquals('Missing "request" parameter.', payload['message'])

        response = self.put(ADMIN_SETTINGS_URL, {'request': 'asdfasdf'})
        payload = transforms.loads(response.body)
        self.assertEquals(400, payload['status'])
        self.assertEquals('Malformed "request" parameter.', payload['message'])

        response = self.put(ADMIN_SETTINGS_URL, {'request': transforms.dumps({
                'xsrf_token': cgi.escape(self.xsrf_token)})})
        payload = transforms.loads(response.body)
        self.assertEquals(400, payload['status'])
        self.assertEquals('Request missing "key" parameter.',
                          payload['message'])

        response = self.put(ADMIN_SETTINGS_URL, {'request': transforms.dumps({
                'xsrf_token': cgi.escape(self.xsrf_token),
                'key': 'base:after_body_tag_begins'})})
        payload = transforms.loads(response.body)
        self.assertEquals(400, payload['status'])
        self.assertEquals('Request missing "payload" parameter.',
                          payload['message'])

        response = self.put(ADMIN_SETTINGS_URL, {'request': transforms.dumps({
                'xsrf_token': cgi.escape(self.xsrf_token),
                'key': 'base:after_body_tag_begins',
                'payload': 'asdfsdfasdf'})})
        payload = transforms.loads(response.body)
        self.assertEquals(400, payload['status'])
        self.assertEquals('Malformed "payload" parameter.',
                          payload['message'])

        response = self.put(ADMIN_SETTINGS_URL, {'request': transforms.dumps({
                'xsrf_token': cgi.escape(self.xsrf_token),
                'key': 'base:after_body_tag_begins',
                'payload': '{}'})})
        payload = transforms.loads(response.body)
        self.assertEquals(400, payload['status'])
        self.assertEquals('Payload missing "hook_content" parameter.',
                          payload['message'])

    def test_get_unknown_hook_content(self):
        # Should be safe (but unhelpful) to ask for no hook.
        response = transforms.loads(self.get(ADMIN_SETTINGS_URL).body)
        payload = transforms.loads(response['payload'])
        self.assertIsNone(payload['hook_content'])

    def test_get_defaulted_hook_content(self):
        url = '%s?key=%s' % (
            ADMIN_SETTINGS_URL, cgi.escape('base:after_body_tag_begins'))
        response = transforms.loads(self.get(url).body)
        self.assertEquals(200, response['status'])
        self.assertEquals('Success.', response['message'])
        payload = transforms.loads(response['payload'])
        self.assertEquals('<!-- base.after_body_tag_begins -->',
                          payload['hook_content'])

    def test_page_has_defaulted_hook_content(self):
        response = self.get(BASE_URL)
        self.assertIn('<!-- base.after_body_tag_begins -->', response.body)

    def test_set_hook_content(self):
        html_text = '<table><tbody><tr><th>;&lt;&gt;</th></tr></tbody></table>'

        response = self.put(ADMIN_SETTINGS_URL, {'request': transforms.dumps({
                'xsrf_token': cgi.escape(self.xsrf_token),
                'key': 'base:after_body_tag_begins',
                'payload': transforms.dumps(
                    {'hook_content': html_text})})})
        self.assertEquals(200, response.status_int)
        response = transforms.loads(response.body)
        self.assertEquals(200, response['status'])
        self.assertEquals('Saved.', response['message'])

        # And verify that the changed text appears on course pages.
        # NOTE that text is as-is; no escaping of special HTML
        # characters should have been done.
        response = self.get(BASE_URL)
        self.assertIn(html_text, response.body)

    def test_delete_default_content_ineffective(self):
        response = self.get(BASE_URL)
        self.assertIn('<!-- base.after_body_tag_begins -->', response.body)

        url = '%s?key=%s&xsrf_token=%s' % (
            ADMIN_SETTINGS_URL, cgi.escape('base:after_body_tag_begins'),
            cgi.escape(self.xsrf_token))
        response = transforms.loads(self.delete(url).body)
        self.assertEquals(200, response['status'])
        self.assertEquals('Deleted.', response['message'])

        response = self.get(BASE_URL)
        self.assertIn('<!-- base.after_body_tag_begins -->', response.body)

    def test_manipulate_non_default_item(self):
        html_text = '<table><tbody><tr><th>;&lt;&gt;</th></tr></tbody></table>'
        new_hook_name = 'html:some_new_hook'

        # Verify that content prior to setting is blank.
        url = '%s?key=%s&xsrf_token=%s' % (
            ADMIN_SETTINGS_URL, cgi.escape(new_hook_name),
            cgi.escape(self.xsrf_token))
        response = transforms.loads(self.get(url).body)
        payload = transforms.loads(response['payload'])
        self.assertIsNone(payload['hook_content'])

        # Set the content.
        response = self.put(ADMIN_SETTINGS_URL, {'request': transforms.dumps({
                'xsrf_token': cgi.escape(self.xsrf_token),
                'key': new_hook_name,
                'payload': transforms.dumps(
                    {'hook_content': html_text})})})
        self.assertEquals(200, response.status_int)
        response = transforms.loads(response.body)
        self.assertEquals(200, response['status'])
        self.assertEquals('Saved.', response['message'])

        # Verify that content after setting is as expected
        url = '%s?key=%s&xsrf_token=%s' % (
            ADMIN_SETTINGS_URL, cgi.escape(new_hook_name),
            cgi.escape(self.xsrf_token))
        response = transforms.loads(self.get(url).body)
        payload = transforms.loads(response['payload'])
        self.assertEquals(html_text, payload['hook_content'])

        # Delete the content.
        response = transforms.loads(self.delete(url).body)
        self.assertEquals(200, response['status'])
        self.assertEquals('Deleted.', response['message'])

        # Verify that content after setting is None.
        url = '%s?key=%s&xsrf_token=%s' % (
            ADMIN_SETTINGS_URL, cgi.escape(new_hook_name),
            cgi.escape(self.xsrf_token))
        response = transforms.loads(self.get(url).body)
        payload = transforms.loads(response['payload'])
        self.assertIsNone(payload['hook_content'])

    def test_add_new_hook_to_page(self):
        hook_name = 'html:my_new_hook'
        html_text = '<table><tbody><tr><th>;&lt;&gt;</th></tr></tbody></table>'
        key = 'views/base.html'
        url = '%s?key=%s' % (
            TEXT_ASSET_URL, cgi.escape(key))

        # Get base page template.
        response = transforms.loads(self.get(url).body)
        xsrf_token = response['xsrf_token']
        payload = transforms.loads(response['payload'])
        contents = payload['contents']

        # Add hook specification to page content.
        contents = contents.replace(
            '<body data-gcb-page-locale="{{ page_locale }}">',
            '<body data-gcb-page-locale="{{ page_locale }}">\n' +
            '{{ html_hooks.insert(\'%s\') | safe }}' % hook_name)
        self.put(TEXT_ASSET_URL, {'request': transforms.dumps({
                'xsrf_token': cgi.escape(xsrf_token),
                'key': key,
                'payload': transforms.dumps({'contents': contents})})})

        # Verify that new hook appears on page.
        response = self.get(BASE_URL)
        self.assertIn('id="%s"' % re.sub('[^a-zA-Z-]', '-', hook_name),
                      response.body)

        # Verify that modified hook content appears on page
        response = self.put(ADMIN_SETTINGS_URL, {'request': transforms.dumps({
                'xsrf_token': cgi.escape(self.xsrf_token),
                'key': hook_name,
                'payload': transforms.dumps(
                    {'hook_content': html_text})})})

        response = self.get(BASE_URL)
        self.assertIn(html_text, response.body)

    def test_student_admin_hook_visibility(self):
        actions.login(STUDENT_EMAIL, is_admin=False)
        response = self.get(BASE_URL)
        self.assertNotIn('gcb-html-hook-edit', response.body)

        actions.login(ADMIN_EMAIL, is_admin=True)
        response = self.get(BASE_URL)
        self.assertIn('gcb-html-hook-edit', response.body)


class JinjaContextTest(actions.TestBase):

    def setUp(self):
        super(JinjaContextTest, self).setUp()
        actions.simple_add_course(COURSE_NAME, ADMIN_EMAIL, COURSE_TITLE)
        actions.login(ADMIN_EMAIL, is_admin=True)

    def _get_jinja_context_text(self, response):
        root = self.parse_html_string(response.text)
        div = root.find('body/div[last()]')
        return ''.join(div.itertext())

    def test_show_jina_context_presence(self):

        # Turn preference on; expect to see context dump.
        with common_utils.Namespace(NAMESPACE):
            prefs = models.StudentPreferencesDAO.load_or_create()
            prefs.show_jinja_context = True
            models.StudentPreferencesDAO.save(prefs)
        self.assertIn('is_read_write_course:',
                      self._get_jinja_context_text(self.get(BASE_URL)))

        # Turn preference off; expect context dump not present.
        with common_utils.Namespace(NAMESPACE):
            prefs = models.StudentPreferencesDAO.load_or_create()
            prefs.show_jinja_context = False
            models.StudentPreferencesDAO.save(prefs)
        self.assertNotIn('is_read_write_course:',
                         self._get_jinja_context_text(self.get(BASE_URL)))

    def test_student_jinja_context_visibility(self):

        actions.login(STUDENT_EMAIL, is_admin=False)
        with common_utils.Namespace(NAMESPACE):
            prefs = models.StudentPreferencesDAO.load_or_create()
            prefs.show_jinja_context = True
            models.StudentPreferencesDAO.save(prefs)
        self.assertNotIn('is_read_write_course:',
                         self._get_jinja_context_text(self.get(BASE_URL)))
