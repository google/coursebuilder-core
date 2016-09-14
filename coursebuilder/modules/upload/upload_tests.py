# Copyright 2013 Google Inc. All Rights Reserved.
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

"""Functional tests for modules/upload/upload.py."""

__author__ = [
    'johncox@google.com (John Cox)',
]

from common import crypto
from common import users
from common import utils as common_utils
from controllers import sites
from controllers import utils
from models import models
from models import courses
from models import student_work
from modules.upload import upload
from tests.functional import actions
from google.appengine.ext import db


class TextFileUploadHandlerTestCase(actions.TestBase):
    """Tests for TextFileUploadHandler."""

    def setUp(self):
        super(TextFileUploadHandlerTestCase, self).setUp()
        self.contents = 'contents'
        self.email = 'user@example.com'
        self.headers = {'referer': 'http://localhost/path?query=value#fragment'}
        self.unit_id = '1'
        actions.login(self.email)
        user = users.get_current_user()
        actions.logout()
        self.user_id = user.user_id()
        self.student = models.Student(
            is_enrolled=True, key_name=self.email, user_id=self.user_id)
        self.student.put()
        # Allow protected access for tests. pylint: disable=protected-access
        self.xsrf_token = utils.XsrfTokenManager.create_xsrf_token(
            upload._XSRF_TOKEN_NAME)

    def configure_environ_for_current_user(self):
        actions.login(self.email)

    def get_submission(self, student_key, unit_id):
        return db.get(student_work.Submission.get_key(unit_id, student_key))

    def test_bad_xsrf_token_returns_400(self):
        # Allow protected access for tests. pylint: disable=protected-access
        response = self.testapp.post(
            upload._POST_ACTION_SUFFIX,
            {'form_xsrf_token': 'bad'}, self.headers, expect_errors=True)
        self.assertEqual(400, response.status_int)

    def test_creates_new_submission(self):
        self.configure_environ_for_current_user()
        # Allow protected access for tests. pylint: disable=protected-access
        user_xsrf_token = utils.XsrfTokenManager.create_xsrf_token(
            upload._XSRF_TOKEN_NAME)
        params = {
            'contents': self.contents,
            'form_xsrf_token': user_xsrf_token,
            'unit_id': self.unit_id,
        }
        self.assertIsNone(self.get_submission(
            self.student.get_key(), self.unit_id))

        response = self.testapp.post(
            upload._POST_ACTION_SUFFIX, params, self.headers)
        self.assertEqual(200, response.status_int)
        submissions = student_work.Submission.all().fetch(2)
        self.assertEqual(1, len(submissions))
        self.assertEqual(u'"%s"' % self.contents, submissions[0].contents)

    def test_missing_contents_returns_400(self):
        self.configure_environ_for_current_user()
        # Allow protected access for tests. pylint: disable=protected-access
        user_xsrf_token = utils.XsrfTokenManager.create_xsrf_token(
            upload._XSRF_TOKEN_NAME)
        params = {
            'form_xsrf_token': user_xsrf_token,
            'unit_id': self.unit_id,
        }

        response = self.testapp.post(
            upload._POST_ACTION_SUFFIX, params, self.headers,
            expect_errors=True)
        self.assertEqual(400, response.status_int)

    def test_missing_student_returns_403(self):
        # Allow protected access for tests. pylint: disable=protected-access
        response = self.testapp.post(
            upload._POST_ACTION_SUFFIX,
            {'form_xsrf_token': self.xsrf_token}, self.headers,
            expect_errors=True)
        self.assertEqual(403, response.status_int)

    def test_missing_xsrf_token_returns_400(self):
        # Allow protected access for tests. pylint: disable=protected-access
        response = self.testapp.post(
            upload._POST_ACTION_SUFFIX, {}, self.headers, expect_errors=True)
        self.assertEqual(400, response.status_int)

    def test_updates_existing_submission(self):
        self.configure_environ_for_current_user()
        # Allow protected access for tests. pylint: disable=protected-access
        user_xsrf_token = utils.XsrfTokenManager.create_xsrf_token(
            upload._XSRF_TOKEN_NAME)
        params = {
            'contents': 'old',
            'form_xsrf_token': user_xsrf_token,
            'unit_id': self.unit_id,
        }

        self.assertIsNone(self.get_submission(
            self.student.get_key(), self.unit_id))
        response = self.testapp.post(
            upload._POST_ACTION_SUFFIX, params, self.headers)
        self.assertEqual(200, response.status_int)

        params['contents'] = self.contents
        response = self.testapp.post(
            upload._POST_ACTION_SUFFIX, params, self.headers)
        self.assertEqual(200, response.status_int)
        submissions = student_work.Submission.all().fetch(2)
        self.assertEqual(1, len(submissions))
        self.assertEqual(u'"%s"' % self.contents, submissions[0].contents)

    def test_uploads_in_same_unit_with_distinct_instances_are_distinct(self):
        self.configure_environ_for_current_user()
        # Allow protected access for tests. pylint: disable=protected-access
        user_xsrf_token = utils.XsrfTokenManager.create_xsrf_token(
            upload._XSRF_TOKEN_NAME)
        params = {
            'form_xsrf_token': user_xsrf_token,
            'unit_id': self.unit_id
        }

        # Upload with one instance_id
        params['contents'] = 'a'
        params['instance_id'] = 'instance_a'
        response = self.testapp.post(
            upload._POST_ACTION_SUFFIX, params, self.headers)
        self.assertEqual(200, response.status_int)

        # Upload with a different instance_id (but same unit_id)
        params['contents'] = 'b'
        params['instance_id'] = 'instance_b'
        response = self.testapp.post(
            upload._POST_ACTION_SUFFIX, params, self.headers)
        self.assertEqual(200, response.status_int)

        self.assertEquals('a', student_work.Submission.get_contents(
            self.unit_id, self.student.get_key(), instance_id='instance_a'))

        self.assertEquals('b', student_work.Submission.get_contents(
            self.unit_id, self.student.get_key(), instance_id='instance_b'))

    def test_contents_too_large_returns_400(self):
        self.configure_environ_for_current_user()
        # Allow protected access for tests. pylint: disable=protected-access
        user_xsrf_token = utils.XsrfTokenManager.create_xsrf_token(
            upload._XSRF_TOKEN_NAME)
        params = {
            # Entity size = contents + other data, so 1MB here will overlfow.
            'contents': 'a' * 1024 * 1024,
            'form_xsrf_token': user_xsrf_token,
            'unit_id': self.unit_id,
        }

        response = self.testapp.post(
            upload._POST_ACTION_SUFFIX, params, self.headers,
            expect_errors=True)
        self.assertEqual(400, response.status_int)
        self.assertIn('File too large', response)

    def test_empty_contents_returns_400(self):
        self.configure_environ_for_current_user()
        # Allow protected access for tests. pylint: disable=protected-access
        user_xsrf_token = utils.XsrfTokenManager.create_xsrf_token(
            upload._XSRF_TOKEN_NAME)
        params = {
            'contents': '',
            'form_xsrf_token': user_xsrf_token,
            'unit_id': self.unit_id,
        }

        response = self.testapp.post(
            upload._POST_ACTION_SUFFIX, params, self.headers,
            expect_errors=True)
        self.assertEqual(400, response.status_int)
        self.assertIn('File is empty', response)

    def test_invalid_contents_returns_400(self):
        self.configure_environ_for_current_user()
        # Allow protected access for tests. pylint: disable=protected-access
        user_xsrf_token = utils.XsrfTokenManager.create_xsrf_token(
            upload._XSRF_TOKEN_NAME)
        params = {
            # Contents will be replaced by invalid unicode below.
            'contents': 'not_empty',
            'form_xsrf_token': user_xsrf_token,
            'unit_id': self.unit_id,
        }

        # We use a mock validate_contents() method to inject invalid unicode.
        validate_contents = upload.TextFileUploadHandler.validate_contents
        def mock_validate_contents(self, contents):
            # Force raise UnicodeDecodeException.
            return chr(128)
        upload.TextFileUploadHandler.validate_contents = mock_validate_contents

        try:
            response = self.post(
                upload._POST_ACTION_SUFFIX, params, self.headers)
        finally:
            upload.TextFileUploadHandler.validate_contents = validate_contents

        self.assertEqual(400, response.status_int)
        self.assertIn('Wrong file format', response)


class TextFileUploadTagTestCase(actions.TestBase):
    _ADMIN_EMAIL = 'admin@foo.com'
    _COURSE_NAME = 'upload_test'
    _STUDENT_EMAIL = 'student@foo.com'

    def setUp(self):
        super(TextFileUploadTagTestCase, self).setUp()

        self.base = '/' + self._COURSE_NAME
        self.app_context = actions.simple_add_course(
            self._COURSE_NAME, self._ADMIN_EMAIL, 'Upload File Tag Test')

        self.course = courses.Course(None, self.app_context)

        actions.login(self._STUDENT_EMAIL, is_admin=True)
        actions.register(self, 'S. Tudent')

    def tearDown(self):
        sites.reset_courses()
        super(TextFileUploadTagTestCase, self).tearDown()

    def test_tag_in_assessment(self):
        assessment = self.course.add_assessment()
        assessment.html_content = (
            '<text-file-upload-tag '
            '    display_length="100" instanceid="this-tag-id">'
            '</text-file-upload-tag>')
        self.course.save()
        response = self.get('assessment?name=%s' % assessment.unit_id)
        dom = self.parse_html_string(response.body)
        form = dom.find('.//div[@class="user-upload-form"]')
        file_input = form.find('.//input[@type="file"]')
        submit = form.find('.//input[@type="submit"]')
        self.assertIsNotNone(file_input)
        self.assertIsNotNone(submit)
        self.assertEquals('100', file_input.attrib['size'])
        # The tag is not disabled
        self.assertNotIn('disabled', file_input.attrib)
        self.assertNotIn('disabled', submit.attrib)

    def test_tag_before_and_after_submission(self):
        assessment = self.course.add_assessment()
        assessment.html_content = (
            '<text-file-upload-tag '
            '    display_length="100" instanceid="this-tag-id">'
            '</text-file-upload-tag>')
        self.course.save()

        response = self.get('assessment?name=%s' % assessment.unit_id)
        dom = self.parse_html_string(response.body)
        warning = dom.find(
            './/*[@class="user-upload-form-warning"]').text.strip()
        self.assertEquals('Maximum file size is 1MB.', warning)

        with common_utils.Namespace('ns_' + self._COURSE_NAME):
            student, _ = models.Student.get_first_by_email(self._STUDENT_EMAIL)
            student_work.Submission.write(
                    assessment.unit_id, student.get_key(), 'contents',
                    instance_id='this-tag-id')

        response = self.get('assessment?name=%s' % assessment.unit_id)
        dom = self.parse_html_string(response.body)
        warning = dom.find(
            './/*[@class="user-upload-form-warning"]').text.strip()
        self.assertEquals(
            'You have already submitted; submit again to replace your previous '
            'entry.', warning)

    def test_tag_in_oeditor_preview_is_visible_but_disabled(self):
        response = self.post('oeditor/preview', {
            'xsrf_token': crypto.XsrfTokenManager.create_xsrf_token(
                'oeditor-preview-handler'),
            'value': (
                '<text-file-upload-tag '
                '    display_length="100" instanceid="this-tag-id">'
                '</text-file-upload-tag>')
        })
        dom = self.parse_html_string(response.body)
        form = dom.find('.//div[@class="user-upload-form"]')
        file_input = form.find('.//input[@type="file"]')
        submit = form.find('.//input[@type="submit"]')
        self.assertIsNotNone(file_input)
        self.assertIsNotNone(submit)
        self.assertEquals('100', file_input.attrib['size'])
        # The tag is disabled
        self.assertEquals('disabled', file_input.attrib['disabled'])
        self.assertEquals('disabled', submit.attrib['disabled'])
