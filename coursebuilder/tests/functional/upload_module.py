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

import os

from controllers import utils
from models import models
from models import student_work
from modules.upload import upload
from tests.functional import actions
from google.appengine.ext import db


class TextFileUploadHandlerTestCase(actions.TestBase):
    """Tests for TextFileUploadHandler."""

    # Name inherited from parent.
    # pylint: disable-msg=g-bad-name
    # Treating code under test as module-protected.
    # pylint: disable-msg=protected-access
    # Don't write repetative docstrings for well-named tests.
    # pylint: disable-msg=g-missing-docstring
    def setUp(self):
        super(TextFileUploadHandlerTestCase, self).setUp()
        self.contents = 'contents'
        self.email = 'user@example.com'
        self.headers = {'referer': 'http://localhost/path?query=value#fragment'}
        self.unit_id = '1'
        self.user_id = '2'
        self.student = models.Student(
            is_enrolled=True, key_name=self.email, user_id=self.user_id)
        self.student.put()
        self.xsrf_token = utils.XsrfTokenManager.create_xsrf_token(
            upload._XSRF_TOKEN_NAME)

    def tearDown(self):
        upload.custom_module.disable()
        super(TextFileUploadHandlerTestCase, self).tearDown()

    def configure_environ_for_current_user(self):
        os.environ['USER_EMAIL'] = self.email
        os.environ['USER_ID'] = self.user_id

    def get_submission(self, student_key, unit_id):
        return db.get(student_work.Submission.get_key(unit_id, student_key))

    def test_bad_xsrf_token_returns_400(self):
        response = self.testapp.post(
            upload._POST_ACTION_SUFFIX,
            {'form_xsrf_token': 'bad'}, self.headers, expect_errors=True)
        self.assertEqual(400, response.status_int)

    def test_creates_new_submission(self):
        self.configure_environ_for_current_user()
        user_xsrf_token = utils.XsrfTokenManager.create_xsrf_token(
            upload._XSRF_TOKEN_NAME)
        params = {
            'contents': self.contents,
            'form_xsrf_token': user_xsrf_token,
            'unit_id': self.unit_id,
        }
        self.assertIsNone(self.get_submission(self.student.key(), self.user_id))

        response = self.testapp.post(
            upload._POST_ACTION_SUFFIX, params, self.headers)
        self.assertEqual(200, response.status_int)
        submissions = student_work.Submission.all().fetch(2)
        self.assertEqual(1, len(submissions))
        self.assertEqual(u'"%s"' % self.contents, submissions[0].contents)

    def test_empty_contents_returns_400(self):
        self.configure_environ_for_current_user()
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

    def test_missing_contents_returns_400(self):
        self.configure_environ_for_current_user()
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
        response = self.testapp.post(
            upload._POST_ACTION_SUFFIX,
            {'form_xsrf_token': self.xsrf_token}, self.headers,
            expect_errors=True)
        self.assertEqual(403, response.status_int)

    def test_missing_xsrf_token_returns_400(self):
        response = self.testapp.post(
            upload._POST_ACTION_SUFFIX, {}, self.headers, expect_errors=True)
        self.assertEqual(400, response.status_int)

    def test_updates_existing_submission(self):
        self.configure_environ_for_current_user()
        user_xsrf_token = utils.XsrfTokenManager.create_xsrf_token(
            upload._XSRF_TOKEN_NAME)
        params = {
            'contents': 'old',
            'form_xsrf_token': user_xsrf_token,
            'unit_id': self.unit_id,
        }

        self.assertIsNone(self.get_submission(self.student.key(), self.user_id))
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

    def test_unsavable_contents_returns_400(self):
        self.configure_environ_for_current_user()
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
