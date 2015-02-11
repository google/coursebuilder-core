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

"""Test the autoregister module."""

import os
os.environ['GCB_REGISTERED_MODULES_CUSTOM'] = (
    'internal.experimental.autoregister.autoregister')

from common import crypto
from models import courses
from tests.functional import actions
from internal.experimental.autoregister import autoregister

class AutoregisterTests(actions.TestBase):

    COURSE_NAME = 'autoregister_course'
    ADMIN_EMAIL = 'admin@foo.com'
    STUDENT_EMAIL = 'student@foo.com'
    REDIRECT_URL = 'http://disney.com'
    COURSE_URL = '/%s/course' % COURSE_NAME
    PREVIEW_URL = '/%s/preview' % COURSE_NAME
    REGISTER_URL = '/%s/register' % COURSE_NAME
    AUTOREGISTER_URL = '/%s/autoregister' % COURSE_NAME
    UNENROLL_URL = '/%s/student/unenroll' % COURSE_NAME

    def setUp(self):
        super(AutoregisterTests, self).setUp()

        self.context = actions.simple_add_course(
            self.COURSE_NAME, self.ADMIN_EMAIL, 'Autoregister Course')
        course = courses.Course(None, app_context=self.context)
        self.unit = course.add_unit()
        self.unit.now_available = True
        self.lesson = course.add_lesson(self.unit)
        self.lesson.now_available = True
        course.save()

        actions.login(self.ADMIN_EMAIL)
        actions.update_course_config(
            self.COURSE_NAME,
            {
                'course': {
                    'now_available': True,
                    'browsable': False,
                },
                autoregister.AUTOREGISTER_SETTINGS_SCHEMA_SECTION: {
                    autoregister.REDIRECT_URL: self.REDIRECT_URL,
                    autoregister.AUTOREGISTER_ENABLED: True,
                }
            })
        actions.login(self.STUDENT_EMAIL)

    def test_redirect(self):
        # Partly, we're testing that the redirect does, in fact, redirect.  We
        # are also demonstrating that unless some other circumstances change,
        # loading the default course URL will cause a redirect.  We want to
        # have this property so as to be able to not have to re-verify this
        # for all of the test cases for the non-redirect exceptions.
        response = self.get(self.COURSE_URL)
        self.assertEqual(301, response.status_int)
        self.assertEqual(self.REDIRECT_URL, response.location)

    def test_redirect_mid_course_url(self):
        lesson_url = '/%s/unit?unit=%s&lesson=%s' % (
            self.COURSE_NAME, self.unit.unit_id, self.lesson.lesson_id)
        response = self.get(lesson_url)
        self.assertEqual(301, response.status_int)
        self.assertEqual(self.REDIRECT_URL, response.location)

    def test_direct_registration_redirects(self):
        # We also want attempts to directly register to fail; this pushes
        # students to register with GLearn first and then get redirected to
        # the autoregister URL.
        response = self.get(self.REGISTER_URL)
        self.assertEqual(301, response.status_int)
        self.assertEqual(self.REDIRECT_URL, response.location)

    def test_page_unavailable_when_course_not_public(self):
        actions.update_course_config(self.COURSE_NAME,
                                     {'course': {'now_available': False}})

        response = self.get(self.COURSE_URL, expect_errors=True)
        self.assertEqual(404, response.status_int)

    def test_no_redirect_when_course_is_browsable(self):
        actions.update_course_config(self.COURSE_NAME,
                                     {'course': {'browsable': True}})
        response = self.get(self.COURSE_URL)
        self.assertEqual(200, response.status_int)

    def test_no_redirect_when_admin(self):
        # Here, we do a GET for the /preview url.  (If instead we had hit the
        # /course url, we'd have been redirected to /preview because the
        # course is only browseable, and that would look like a bug)
        actions.login(self.ADMIN_EMAIL)
        response = self.get(self.PREVIEW_URL)
        self.assertEqual(200, response.status_int)

    def test_no_redirect_when_autoregister_disabled(self):
        actions.update_course_config(
            self.COURSE_NAME,
            {
                autoregister.AUTOREGISTER_SETTINGS_SCHEMA_SECTION: {
                    autoregister.AUTOREGISTER_ENABLED: False,
                }
            })
        response = self.get(self.PREVIEW_URL)
        self.assertEqual(200, response.status_int)

    def test_autoregister_and_unenroll(self):
        # Unregistered student gets redirected.
        response = self.get(self.COURSE_URL)
        self.assertEqual(301, response.status_int)
        self.assertEqual(self.REDIRECT_URL, response.location)

        response = self.get(self.AUTOREGISTER_URL)
        self.assertEqual(302, response.status_int)
        self.assertEqual('http://localhost' + self.COURSE_URL,
                          response.location)

        response = self.get(self.COURSE_URL)
        self.assertEqual(200, response.status_int)


        self.post(self.UNENROLL_URL,
                  {
                      'xsrf_token': crypto.XsrfTokenManager.create_xsrf_token(
                          'student-unenroll')
                  })
        response = self.get(self.COURSE_URL)
        self.assertEqual(301, response.status_int)
        self.assertEqual(self.REDIRECT_URL, response.location)
