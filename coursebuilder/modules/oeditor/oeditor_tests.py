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

import re
import time

from common import crypto
from common import users
from controllers import sites
from models import config
from models import courses
from models import transforms
from modules.oeditor import oeditor
from tests.functional import actions

from google.appengine.api import namespace_manager


class ObjectEditorTest(actions.TestBase):

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
            '/modules/core_tags/_static/js/drive_tag_parent_frame.js'))

    def test_get_drive_tag_parent_frame_script_src_set_if_apis_enabled(self):
        config.Registry.test_overrides[
            courses.COURSES_CAN_USE_GOOGLE_APIS.name] = True
        self.assertIsNotNone(self.get_script_tag_by_src(
            '/modules/core_tags/_static/js/drive_tag_parent_frame.js'))

    def test_get_drive_tag_script_manager_script_src_empty_if_apis_disabled(
            self):
        self.assertIsNone(self.get_script_tag_by_src(
            '/modules/core_tags/_static/js/drive_tag_script_manager.js'))

    def test_get_drive_tag_script_manager_script_src_set_if_apis_enabled(
            self):
        config.Registry.test_overrides[
            courses.COURSES_CAN_USE_GOOGLE_APIS.name] = True
        self.assertIsNotNone(self.get_script_tag_by_src(
            '/modules/core_tags/_static/js/drive_tag_script_manager.js'))


class ButtonbarCssHandlerTests(actions.TestBase):

    def _get(self):
        return self.get('/modules/oeditor/buttonbar.css')

    def test_response_is_cacheable(self):
        self.assertEqual(
            'max-age=600, public', self._get().headers['Cache-Control'])

    def test_content_type_is_css(self):
        self.assertEqual('text/css', self._get().headers['Content-Type'])


class EditorPrefsTests(actions.TestBase):
    COURSE_NAME = 'test_editor_state'
    EDITOR_STATE = {'objectives': {'editorType': 'html'}}

    def setUp(self):
        super(EditorPrefsTests, self).setUp()

        self.base = '/' + self.COURSE_NAME
        app_context = actions.simple_add_course(
            self.COURSE_NAME, 'admin@example.com', 'Test Editor State')
        self.old_namespace = namespace_manager.get_namespace()
        namespace_manager.set_namespace('ns_%s' % self.COURSE_NAME)
        self.course = courses.Course(None, app_context)
        self.unit = self.course.add_unit()
        self.lesson = self.course.add_lesson(self.unit)
        self.course.save()

        self.location = '/%s/rest/course/lesson' % self.COURSE_NAME
        self.key = self.lesson.lesson_id

    def tearDown(self):
        del sites.Registry.test_overrides[sites.GCB_COURSES_CONFIG.name]
        namespace_manager.set_namespace(self.old_namespace)
        super(EditorPrefsTests, self).tearDown()

    def _post(self, xsrf_token=None, payload=None):
        request = {}
        if xsrf_token is None:
            xsrf_token = crypto.XsrfTokenManager.create_xsrf_token(
                oeditor.EditorPrefsRestHandler.XSRF_TOKEN)
        request['xsrf_token'] = xsrf_token

        if payload is None:
            payload = {
                'location': self.location,
                'key': self.key,
                'state': self.EDITOR_STATE
            }
        request['payload'] = transforms.dumps(payload)

        data = {'request': transforms.dumps(request)}
        return self.post('oeditor/rest/editor_prefs', data, expect_errors=True)

    def test_safe_key(self):
        def transform_function(pii_str):
            return 'tr(%s)' % pii_str

        key_name = oeditor.EditorPrefsDao.create_key_name(
            321, self.location, self.key)
        dto = oeditor.EditorPrefsDto(key_name, {})
        oeditor.EditorPrefsDao.save(dto)
        entity = oeditor.EditorPrefsEntity.get_by_key_name(key_name)
        safe_key = oeditor.EditorPrefsEntity.safe_key(
            entity.key(), transform_function)
        self.assertEqual(
            'tr(321):/%s/rest/course/lesson:%s' % (
                self.COURSE_NAME, self.lesson.lesson_id),
            safe_key.name())

    def test_rest_handler_requires_user_in_session(self):
        response = self._post()
        self.assertEquals(401, response.status_int)

    def test_rest_handler_requires_course_admin(self):
        actions.login('user@example.com', is_admin=False)
        response = self._post()
        self.assertEquals(200, response.status_int)
        body = transforms.loads(response.body)
        self.assertEquals(401, body['status'])

    def test_rest_handler_requires_xsrf_token(self):
        response = self._post(xsrf_token='bad_token')
        self.assertEquals(200, response.status_int)
        body = transforms.loads(response.body)
        self.assertEquals(403, body['status'])

    def test_rest_handler_saves_state(self):
        actions.login('user@example.com', is_admin=True)
        response = self._post()
        self.assertEquals(200, response.status_int)
        body = transforms.loads(response.body)
        self.assertEquals(200, body['status'])

        user = users.get_current_user()
        key_name = oeditor.EditorPrefsDao.create_key_name(
            user.user_id(), self.location, self.key)
        dto = oeditor.EditorPrefsDao.load(key_name)
        self.assertEquals(self.EDITOR_STATE, dto.dict)

    def test_oeditor_returns_state(self):
        actions.login('user@example.com', is_admin=True)
        xsrf_timestamp = long(time.time())
        xsrf_token = crypto.XsrfTokenManager.create_xsrf_token(
                oeditor.EditorPrefsRestHandler.XSRF_TOKEN)

        self._post(xsrf_token=xsrf_token)
        response = self.get('dashboard?action=edit_lesson&key=%s' % (
            self.lesson.lesson_id))

        expected = {
          'xsrf_token': xsrf_token,
          'location': self.location,
          'key': str(self.key),
          'prefs': self.EDITOR_STATE
        }
        expected = transforms.loads(transforms.dumps(expected))

        match = re.search(
            r'cb_global.editor_prefs = JSON.parse\((.*)\);', response.body)

        actual = match.group(1)
        actual = transforms.loads('"%s"' % actual)
        actual = transforms.loads(actual[1:-1])

        # If the time moves up to the next second between the moment we
        # generate our expected XSRF token and the response to the GET call is
        # made, the XSRF tokens will mismatch, and the test will fail.  Allow
        # a tolerance of up to 5 sceonds to allow for that (and thus suppress
        # test flakes.
        tolerance = 0
        while actual['xsrf_token'] != expected['xsrf_token'] and tolerance < 5:
            tolerance += 1
            expected['xsrf_token'] = crypto.XsrfTokenManager._create_token(
                oeditor.EditorPrefsRestHandler.XSRF_TOKEN,
                xsrf_timestamp + tolerance)

        self.assertEquals(expected, actual)
