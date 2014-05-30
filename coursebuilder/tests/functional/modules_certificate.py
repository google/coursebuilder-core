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

"""Tests for modules/certificate/."""

__author__ = 'John Orr (jorr@google.com)'


import actions
from controllers import sites
from models import courses
from models import custom_modules
from models import models
from modules.certificate import certificate


class CertificateHandlerTestCase(actions.TestBase):
    """Tests for the handler which presents the certificate."""

    def setUp(self):
        super(CertificateHandlerTestCase, self).setUp()

        # Enable the certificate module, which is disabled by default
        self.assertFalse(certificate.custom_module.enabled)
        certificate.custom_module.enable()
        _, namespaced_routes = custom_modules.Registry.get_all_routes()
        sites.ApplicationRequestHandler.bind(namespaced_routes)

        # Mock the module's student_is_qualified method
        self.is_qualified = True
        self.original_student_is_qualified = certificate.student_is_qualified
        certificate.student_is_qualified = (
            lambda student, course: self.is_qualified)

    def tearDown(self):
        certificate.student_is_qualified = self.original_student_is_qualified
        certificate.custom_module.disable()
        _, namespaced_routes = custom_modules.Registry.get_all_routes()
        sites.ApplicationRequestHandler.bind(namespaced_routes)

        super(CertificateHandlerTestCase, self).tearDown()

    def test_student_must_be_enrolled(self):
        # If student not in session, expect redirect
        response = self.get('/certificate')
        self.assertEquals(302, response.status_code)

        # If student is not enrolled, expect redirect
        actions.login('test@example.com')
        response = self.get('/certificate')
        self.assertEquals(302, response.status_code)
        self.assertEquals(
            'http://localhost/preview', response.headers['Location'])

        # If the student is enrolled, expect certificate
        models.Student.add_new_student_for_current_user('Test User', None, self)
        response = self.get('/certificate')
        self.assertEquals(200, response.status_code)

    def test_student_must_be_qualified(self):
        actions.login('test@example.com')
        models.Student.add_new_student_for_current_user('Test User', None, self)

        # If student is not qualified, expect redirect to home page
        self.is_qualified = False
        response = self.get('/certificate')
        self.assertEquals(302, response.status_code)
        self.assertEquals('http://localhost/', response.headers['Location'])

        # If student is qualified, expect certificate
        self.is_qualified = True
        response = self.get('/certificate')
        self.assertEquals(200, response.status_code)

    def test_certificate_should_have_student_nickname(self):
        actions.login('test@example.com')
        models.Student.add_new_student_for_current_user('Jane Doe', None, self)

        response = self.get('/certificate')
        self.assertEquals(200, response.status_code)
        self.assertIn('Jane Doe', response.body)

    def test_certificate_table_entry(self):
        actions.login('test@example.com')
        models.Student.add_new_student_for_current_user('Test User', None, self)
        student = models.Student.get_by_email('test@example.com')

        all_courses = sites.get_all_courses()
        app_context = all_courses[0]
        course = courses.Course(None, app_context=app_context)

        # If the student is qualified, a link is shown
        self.is_qualified = True
        table_entry = certificate.get_certificate_table_entry(student, course)
        link = str(table_entry['Certificate'])
        self.assertEquals(
            '<a href="certificate">Click for certificate</a>', link)

        # If the student is not qualified, a message is shown
        self.is_qualified = False
        table_entry = certificate.get_certificate_table_entry(student, course)
        self.assertIn(
            'You have not yet met the course requirements',
            table_entry['Certificate'])

