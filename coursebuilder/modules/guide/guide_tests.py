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

"""Tests for the Guide module."""

__author__ = 'Pavel Simakov (psimakov@google.com)'


from controllers import sites
from models import courses
from tests.functional import actions
from tools import verify

ADMIN_EMAIL = 'GuideTests@test.com'
COURSE_NAME = 'GuideTests'


class GuideTests(actions.TestBase):

    PUBLIC = {
      'course': {'now_available': True, 'browsable': True},
      'reg_form': {'can_register': False}}

    PRIVATE = {'course': {'now_available': False}}

    GUIDE_UNAVAILABLE = {'modules': {'guide': {
        'availability': 'unavailable'}}}

    GUIDE_DISABLED = {'modules': {'guide': {'enabled': False}}}

    GUIDE_ENABLED = {'modules': {'guide': {
        'enabled': True, 'availability': 'public'}}}

    def setUp(self):
        super(GuideTests, self).setUp()
        self._import_sample_course(ns='guide')
        self._import_sample_course(ns='other')
        sites.setup_courses('course:/test::ns_guide\ncourse:/other::ns_other')
        self.base = '/test'

    def _import_sample_course(self, ns='guide'):
        dst_app_context = actions.simple_add_course(
            ns, '%s_tests@google.com' % ns,
            'Power Searching with Google (%s)' % ns)
        dst_course = courses.Course(None, dst_app_context)
        all_courses = sites.get_all_courses('course:/:/:')
        src_app_context = all_courses[len(all_courses) - 1]
        errors = []
        dst_course.import_from(src_app_context, errors)
        dst_course.save()
        self.assertEquals(0, len(errors))

    def test_polymer_components_zip_handler(self):
        response = self.get(
            '/modules/guide/resources/polymer/bower_components/bower.json')
        self.assertEquals(200, response.status_int)

    def test_guide_disabled(self):
        with actions.OverriddenEnvironment(self.GUIDE_DISABLED):
            actions.login(ADMIN_EMAIL, is_admin=True)
            response = self.get('/modules/guide', expect_errors=True)
            self.assertEquals(404, response.status_int)

            actions.login('guest@sample.com')
            response = self.get('/modules/guide', expect_errors=True)
            self.assertEquals(404, response.status_int)

    def test_guide_enabled_but_course_is_private(self):
        environ = self.PRIVATE.copy()
        environ.update(self.GUIDE_ENABLED)
        with actions.OverriddenEnvironment(environ):
            # admin can see it
            actions.login('guest@sample.com', is_admin=True)
            response = self.get('/modules/guide')
            self.assertEquals(200, response.status_int)
            self.assertIn(
                'category="Power Searching with Google (guide) (private)"',
                response.body)

            # student still can't
            actions.login('guest@sample.com')
            response = self.get('/modules/guide', expect_errors=True)
            self.assertEquals(404, response.status_int)

    def _test_guide_app(self, login):
        environ = self.PUBLIC.copy()
        environ.update(self.GUIDE_ENABLED)
        with actions.OverriddenEnvironment(environ):
            if login:
                actions.login('test@example.com')
            response = self.get('/modules/guide')
            self.assertIn('<gcb-guide-container>', response.body)
            self.assertIn(
                'category="Power Searching with Google (guide)"',
                response.body)
            self.assertIn('<gcb-guide-card', response.body)
            self.assertIn(  # note that we intentionally don't show "Unit 1 - "
                'label="Introduction"', response.body)

    def test_guide_app_with_login(self):
        self._test_guide_app(True)

    def test_guide_app_no_login(self):
        self._test_guide_app(False)

    def test_guide_shows_all_unit_lessons(self):
        environ = self.PUBLIC.copy()
        environ.update(self.GUIDE_ENABLED)
        with actions.OverriddenEnvironment(environ):
            actions.login('test@example.com', is_admin=True)

            app_ctx = sites.get_all_courses()[0]
            course = courses.Course(None, app_context=app_ctx)
            for unit in course.get_units():
                if unit.type != verify.UNIT_TYPE_UNIT:
                    continue
                response = self.get('guide?unit_id=%s' % unit.unit_id)

                # check unit details
                self.assertIn(unit.title, response.body.decode('utf-8'))
                self.assertIn(
                    'unit_id="%s"' % unit.unit_id,
                    response.body.decode('utf-8'))

                # check polymer components
                self.assertIn('<gcb-step-container', response.body)
                self.assertIn('<gcb-step-container-data', response.body)
                self.assertIn('<gcb-step-card', response.body)
                self.assertIn('<gcb-step-card-data', response.body)

                # check all lesson titles
                for lesson in course.get_lessons(unit.unit_id):
                    self.assertIn(
                        'lesson_id="%s"' % lesson.lesson_id,
                        response.body.decode('utf-8'))
                    self.assertIn(lesson.title, response.body.decode('utf-8'))

                # check for specific lesson content and custom tags
                self.assertIn('Check Answer', response.body)
                self.assertIn('title="YouTube Video Player"', response.body)
                self.assertIn(
                    '<script src="/modules/'
                    'assessment_tags/resources/grading.js">', response.body)

    def test_public_guide_does_not_need_login(self):
        actions.logout()
        environ = self.PUBLIC.copy()
        environ.update(self.GUIDE_ENABLED)
        with actions.OverriddenEnvironment(environ):
            response = self.get('/modules/guide')
            self.assertEquals(200, response.status_int)
            self.assertIn(
                'category="Power Searching with Google (guide)"',
                response.body)
            app_ctx = sites.get_all_courses()[0]
            course = courses.Course(None, app_context=app_ctx)
            for unit in course.get_units():
                if unit.type != verify.UNIT_TYPE_UNIT:
                    continue
                response = self.get('guide?unit_id=%s' % unit.unit_id)
                self.assertIn(unit.title, response.body.decode('utf-8'))


        environ.update(self.GUIDE_UNAVAILABLE)
        with actions.OverriddenEnvironment(environ):
            response = self.get('/modules/guide', expect_errors=True)
            self.assertEquals(404, response.status_int)
            for unit in course.get_units():
                if unit.type != verify.UNIT_TYPE_UNIT:
                    continue
                response = self.get(
                    'guide?unit_id=%s' % unit.unit_id, expect_errors=True)
                self.assertEquals(404, response.status_int)

    def test_guide_private_course_public(self):
        actions.logout()
        environ = self.PUBLIC.copy()
        environ.update(self.GUIDE_ENABLED)
        environ.update(self.GUIDE_UNAVAILABLE)
        with actions.OverriddenEnvironment(environ):
            response = self.get('/modules/guide', expect_errors=True)
            self.assertEquals(404, response.status_int)

    def test_courses_with_different_availabilities(self):
        app_context_1 = sites.get_course_for_path('/test')
        course_1 = courses.Course(None, app_context_1)
        course_1.set_course_availability(courses.COURSE_AVAILABILITY_PUBLIC)

        app_context_2 = sites.get_course_for_path('/other')
        course_2 = courses.Course(None, app_context_2)
        course_2.set_course_availability(courses.COURSE_AVAILABILITY_PRIVATE)

        actions.logout()
        with actions.OverriddenEnvironment(self.GUIDE_ENABLED):
            response = self.get('/modules/guide')
            self.assertEquals(200, response.status_int)
            self.assertIn('category="Power Searching with Google (guide)"',
                          response.body)
            self.assertNotIn('category="Power Searching with Google (other)"',
                          response.body)
