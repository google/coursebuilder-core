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
import urllib

from common import crypto
from common import utils as common_utils
from controllers import sites
from controllers import utils
from models import courses
from models import models
from models import transforms
from modules.courses import settings
from modules.dashboard import filer
from modules.i18n_dashboard import i18n_dashboard
from tests.functional import actions
from tests.functional.actions import assert_contains

COURSE_NAME = 'admin_settings'
COURSE_TITLE = 'Admin Settings'
ADMIN_EMAIL = 'admin@foo.com'
NAMESPACE = 'ns_%s' % COURSE_NAME
BASE_URL = '/' + COURSE_NAME
ADMIN_SETTINGS_URL = '/%s%s' % (
    COURSE_NAME, settings.HtmlHookRESTHandler.URI)
TEXT_ASSET_URL = '/%s%s' % (
    COURSE_NAME, filer.TextAssetRESTHandler.URI)
STUDENT_EMAIL = 'student@foo.com'
SETTINGS_URL = '/%s/dashboard?action=settings_admin_prefs' % COURSE_NAME


class AdminSettingsTests(actions.TestBase):

    def setUp(self):
        super(AdminSettingsTests, self).setUp()
        actions.simple_add_course(COURSE_NAME, ADMIN_EMAIL, COURSE_TITLE)
        actions.login(ADMIN_EMAIL)

    def test_defaults(self):
        prefs = models.StudentPreferencesDAO.load_or_default()
        self.assertEquals(False, prefs.show_hooks)


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
            'http://localhost/admin/welcome')
        response = self.get('/admin/welcome?action=welcome')
        assert_contains('Welcome to Course Builder', response.body)
        assert_contains('action="/admin/welcome"', response.body)
        assert_contains('Start Using Course Builder', response.body)

    def test_welcome_page_button(self):
        actions.login(ADMIN_EMAIL, is_admin=True)
        response = self.post('/admin/welcome', {})
        self.assertEqual(response.status_int, 302)
        self.assertEqual(
            response.headers['location'],
            'http://localhost/modules/admin')


class HtmlHookTest(actions.TestBase):

    def setUp(self):
        super(HtmlHookTest, self).setUp()

        self.app_context = actions.simple_add_course(COURSE_NAME, ADMIN_EMAIL,
                                            COURSE_TITLE)
        self.course = courses.Course(None, self.app_context)
        actions.login(ADMIN_EMAIL, is_admin=True)
        self.xsrf_token = crypto.XsrfTokenManager.create_xsrf_token(
            settings.HtmlHookRESTHandler.XSRF_ACTION)

    def tearDown(self):
        the_settings = self.course.get_environ(self.app_context)
        the_settings.pop('foo', None)
        the_settings['html_hooks'].pop('foo', None)
        self.course.save_settings(the_settings)
        super(HtmlHookTest, self).tearDown()

    def test_hook_edit_button_presence(self):

        # Turn preference on; expect to see hook editor button
        with common_utils.Namespace(NAMESPACE):
            prefs = models.StudentPreferencesDAO.load_or_default()
            prefs.show_hooks = True
            models.StudentPreferencesDAO.save(prefs)
        response = self.get(BASE_URL)
        self.assertIn('gcb-html-hook-edit', response.body)

        # Turn preference off; expect editor button not present.
        with common_utils.Namespace(NAMESPACE):
            prefs = models.StudentPreferencesDAO.load_or_default()
            prefs.show_hooks = False
            models.StudentPreferencesDAO.save(prefs)

        response = self.get(BASE_URL)
        self.assertNotIn('gcb-html-hook-edit', response.body)

    def test_non_admin_permissions_failures(self):
        actions.login(STUDENT_EMAIL)
        student_xsrf_token = crypto.XsrfTokenManager.create_xsrf_token(
            settings.HtmlHookRESTHandler.XSRF_ACTION)

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
            ADMIN_SETTINGS_URL, cgi.escape('base.after_body_tag_begins'))
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
                'key': 'base.after_body_tag_begins',
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
            ADMIN_SETTINGS_URL, cgi.escape('base.after_body_tag_begins'),
            cgi.escape(self.xsrf_token))
        response = transforms.loads(self.delete(url).body)
        self.assertEquals(200, response['status'])
        self.assertEquals('Deleted.', response['message'])

        response = self.get(BASE_URL)
        self.assertIn('<!-- base.after_body_tag_begins -->', response.body)

    def test_manipulate_non_default_item(self):
        html_text = '<table><tbody><tr><th>;&lt;&gt;</th></tr></tbody></table>'
        new_hook_name = 'html.some_new_hook'

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
        hook_name = 'html.my_new_hook'
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
        with common_utils.Namespace(NAMESPACE):
            prefs = models.StudentPreferencesDAO.load_or_default()
            prefs.show_hooks = True
            models.StudentPreferencesDAO.save(prefs)

        response = self.get(BASE_URL)
        self.assertNotIn('gcb-html-hook-edit', response.body)

        actions.login(ADMIN_EMAIL, is_admin=True)
        with common_utils.Namespace(NAMESPACE):
            prefs = models.StudentPreferencesDAO.load_or_default()
            prefs.show_hooks = True
            models.StudentPreferencesDAO.save(prefs)
        response = self.get(BASE_URL)
        self.assertIn('gcb-html-hook-edit', response.body)

    def test_hook_i18n(self):
        actions.update_course_config(
            COURSE_NAME,
            {
                'html_hooks': {'base': {'after_body_tag_begins': 'foozle'}},
                'extra_locales': [
                    {'locale': 'de', 'availability': 'available'},
                ]
            })

        hook_bundle = {
            'content': {
                'type': 'html',
                'source_value': '',
                'data': [{
                    'source_value': 'foozle',
                    'target_value': 'FUZEL',
                }],
            }
        }
        hook_key = i18n_dashboard.ResourceBundleKey(
            utils.ResourceHtmlHook.TYPE, 'base.after_body_tag_begins', 'de')
        with common_utils.Namespace(NAMESPACE):
            i18n_dashboard.ResourceBundleDAO.save(
                i18n_dashboard.ResourceBundleDTO(str(hook_key), hook_bundle))

        # Verify non-translated version.
        response = self.get(BASE_URL)
        dom = self.parse_html_string(response.body)
        html_hook = dom.find('.//div[@id="base-after-body-tag-begins"]')
        self.assertEquals('foozle', html_hook.text)

        # Set preference to translated language, and check that that's there.
        with common_utils.Namespace(NAMESPACE):
            prefs = models.StudentPreferencesDAO.load_or_default()
            prefs.locale = 'de'
            models.StudentPreferencesDAO.save(prefs)

        response = self.get(BASE_URL)
        dom = self.parse_html_string(response.body)
        html_hook = dom.find('.//div[@id="base-after-body-tag-begins"]')
        self.assertEquals('FUZEL', html_hook.text)

        # With no translation present, but preference set to foreign language,
        # verify that we fall back to the original language.

        # Remove translation bundle, and clear cache.
        with common_utils.Namespace(NAMESPACE):
            i18n_dashboard.ResourceBundleDAO.delete(
                i18n_dashboard.ResourceBundleDTO(str(hook_key), hook_bundle))
        i18n_dashboard.ProcessScopedResourceBundleCache.instance().clear()

        response = self.get(BASE_URL)
        dom = self.parse_html_string(response.body)
        html_hook = dom.find('.//div[@id="base-after-body-tag-begins"]')
        self.assertEquals('foozle', html_hook.text)

    def test_hook_content_found_in_old_location(self):
        actions.update_course_config(COURSE_NAME, {'foo': {'bar': 'baz'}})
        self.assertEquals(
            'baz', utils.HtmlHooks.get_content(self.course, 'foo.bar'))

    def test_insert_on_page_and_hook_content_found_using_old_separator(self):
        the_settings = self.course.get_environ(self.app_context)
        the_settings['html_hooks']['foo'] = {'bar': 'baz'}
        self.course.save_settings(the_settings)
        hooks = utils.HtmlHooks(self.course)
        content = hooks.insert('foo:bar')
        self.assertEquals('<div class="gcb-html-hook" id="foo-bar">baz</div>',
                          str(content))

    def test_hook_content_new_location_overrides_old_location(self):
        actions.update_course_config(COURSE_NAME,
                                     {'html_hooks': {'foo': {'bar': 'zab'}}})
        actions.update_course_config(COURSE_NAME,
                                     {'foo': {'bar': 'baz'}})
        self.assertEquals(
            'zab', utils.HtmlHooks.get_content(self.course, 'foo.bar'))

    def test_hook_rest_edit_removes_from_old_location(self):
        actions.update_course_config(COURSE_NAME,
                                     {'html_hooks': {'foo': {'bar': 'zab'}}})
        actions.update_course_config(COURSE_NAME,
                                     {'foo': {'bar': 'baz'}})
        response = self.put(ADMIN_SETTINGS_URL, {'request': transforms.dumps({
                'xsrf_token': cgi.escape(self.xsrf_token),
                'key': 'foo.bar',
                'payload': transforms.dumps({'hook_content': 'BAZ'})})})
        env = self.course.get_environ(self.app_context)
        self.assertNotIn('bar', env['foo'])
        self.assertEquals('BAZ', env['html_hooks']['foo']['bar'])


    def test_hook_rest_delete_removes_from_old_and_new_location(self):
        actions.update_course_config(COURSE_NAME,
                                     {'html_hooks': {'foo': {'bar': 'zab'}}})
        actions.update_course_config(COURSE_NAME,
                                     {'foo': {'bar': 'baz'}})
        url = '%s?key=%s&xsrf_token=%s' % (
            ADMIN_SETTINGS_URL, cgi.escape('foo.bar'),
            cgi.escape(self.xsrf_token))
        self.delete(url)

        env = self.course.get_environ(self.app_context)
        self.assertNotIn('bar', env['foo'])
        self.assertNotIn('bar', env['html_hooks']['foo'])


class JinjaContextTest(actions.TestBase):

    def setUp(self):
        super(JinjaContextTest, self).setUp()
        actions.simple_add_course(COURSE_NAME, ADMIN_EMAIL, COURSE_TITLE)
        actions.login(ADMIN_EMAIL, is_admin=True)

    def _get_jinja_context_text(self, response):
        root = self.parse_html_string(response.text)
        div = root.find('body/div[last()-1]')
        return ''.join(div.itertext())

    def test_show_jinja_context_presence(self):

        # Turn preference on; expect to see context dump.
        with common_utils.Namespace(NAMESPACE):
            prefs = models.StudentPreferencesDAO.load_or_default()
            prefs.show_jinja_context = True
            models.StudentPreferencesDAO.save(prefs)
        self.assertIn('is_read_write_course:',
                      self._get_jinja_context_text(self.get(BASE_URL)))

        # Turn preference off; expect context dump not present.
        with common_utils.Namespace(NAMESPACE):
            prefs = models.StudentPreferencesDAO.load_or_default()
            prefs.show_jinja_context = False
            models.StudentPreferencesDAO.save(prefs)
        self.assertNotIn('is_read_write_course:',
                         self._get_jinja_context_text(self.get(BASE_URL)))

    def test_student_jinja_context_visibility(self):

        actions.login(STUDENT_EMAIL, is_admin=False)
        with common_utils.Namespace(NAMESPACE):
            prefs = models.StudentPreferencesDAO.load_or_default()
            prefs.show_jinja_context = True
            models.StudentPreferencesDAO.save(prefs)
        self.assertNotIn('is_read_write_course:',
                         self._get_jinja_context_text(self.get(BASE_URL)))


class ExitUrlTest(actions.TestBase):

    def setUp(self):
        super(ExitUrlTest, self).setUp()
        actions.simple_add_course(COURSE_NAME, ADMIN_EMAIL, COURSE_TITLE)
        actions.login(ADMIN_EMAIL, is_admin=True)

    def test_exit_url(self):
        base_url = '/%s/dashboard?action=settings_data_pump' % COURSE_NAME
        url = base_url + '&' + urllib.urlencode({
            'exit_url': 'dashboard?%s' % urllib.urlencode({
                'action': 'data_pump'})})
        response = self.get(url)
        self.assertIn(
            'cb_global.exit_url = \'dashboard?action=data_pump',
            response.body)
