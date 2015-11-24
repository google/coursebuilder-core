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


class GuideTests(actions.TestBase):

    ALL_COURSES = [
        ('Alpha', courses.COURSE_AVAILABILITY_PUBLIC),
        ('Bravo', courses.COURSE_AVAILABILITY_REGISTRATION_OPTIONAL),
        ('Charlie', courses.COURSE_AVAILABILITY_REGISTRATION_REQUIRED),
        ('Delta', courses.COURSE_AVAILABILITY_PRIVATE)]

    GUIDE_DISABLED = {'modules': {'guide': {'enabled': False}}}

    GUIDE_ENABLED_COURSE = {'modules': {'guide': {
        'enabled': True, 'availability': courses.AVAILABILITY_COURSE}}}

    GUIDE_ENABLED_PRIVATE = {'modules': {'guide': {
        'enabled': True, 'availability': courses.AVAILABILITY_UNAVAILABLE}}}

    def _import_sample_course(self, ns='guide', availability=None):
        dst_app_context = actions.simple_add_course(
            ns, '%s_tests@google.com' % ns,
            'Power Searching with Google [%s]' % ns)
        dst_course = courses.Course(None, dst_app_context)
        all_courses = sites.get_all_courses('course:/:/:')
        src_app_context = all_courses[len(all_courses) - 1]
        errors = []
        dst_course.import_from(src_app_context, errors)
        dst_course.save()
        dst_course.set_course_availability(availability)
        self.assertEquals(0, len(errors))

    def setUp(self):
        super(GuideTests, self).setUp()
        entries = []
        for name, availability in self.ALL_COURSES:
            self._import_sample_course(ns=name, availability=availability)
            entries.append('course:/%s::ns_%s\n' % (name, name))
        sites.setup_courses(''.join(entries))

    def assert_guide_not_accesssible(self, name, is_guides_accessible=False):
        response = self.get('/modules/guides', expect_errors=True)
        if is_guides_accessible:
            self.assertEquals(200, response.status_int)
        else:
            self.assertEquals(404, response.status_int)

        app_ctx = sites.get_course_for_path('/%s' % name)
        course = courses.Course(None, app_context=app_ctx)
        for unit in course.get_units():
            if unit.type != verify.UNIT_TYPE_UNIT:
                continue
            response = self.get(
                '/%s/guide?unit_id=%s' % (name, unit.unit_id),
                expect_errors=True)
            self.assertEquals(404, response.status_int)

    def assert_guide_accesssible(self, name):
        response = self.get('/modules/guides')
        self.assertEquals(200, response.status_int)
        self.assertIn(
            'category="Power Searching with Google [%s]' % name,
            response.body)

        app_ctx = sites.get_course_for_path('/%s' % name)
        course = courses.Course(None, app_context=app_ctx)
        for unit in course.get_units():
            if unit.type != verify.UNIT_TYPE_UNIT:
                continue
            response = self.get('/%s/guide?unit_id=%s' % (name, unit.unit_id))
            self.assertIn(unit.title, response.body.decode('utf-8'))

    def register(self, name):
        self.base = '/%s' % name
        actions.register(self, 'Test User %s' % name)
        self.base = ''

    def test_polymer_components_zip_handler(self):
        response = self.get(
            '/modules/guide/resources/polymer/bower_components/bower.json')
        self.assertEquals(200, response.status_int)

    def test_guide_disabled(self):
        with actions.OverriddenEnvironment(self.GUIDE_DISABLED):
            for name in ['Alpha', 'Bravo', 'Charlie', 'Delta']:
                actions.logout()
                self.assert_guide_not_accesssible(name)

                actions.login('guest@sample.com')
                self.assert_guide_not_accesssible(name)

                if name == 'Bravo' or name == 'Charlie':
                    self.register(name)
                    self.assert_guide_not_accesssible(name)

                actions.login('admin@sample.com', is_admin=True)
                self.assert_guide_not_accesssible(name)

    def test_guide_enabled_private(self):
        with actions.OverriddenEnvironment(self.GUIDE_ENABLED_PRIVATE):
            for name in ['Alpha', 'Bravo', 'Charlie', 'Delta']:
                actions.logout()
                self.assert_guide_not_accesssible(name)

                actions.login('guest@sample.com')
                self.assert_guide_not_accesssible(name)

                if name == 'Bravo' or name == 'Charlie':
                    self.register(name)
                    self.assert_guide_not_accesssible(name)

                actions.login('admin@sample.com', is_admin=True)
                self.assert_guide_accesssible(name)

                # check course labels as admin sees them
                response = self.get('/modules/guides')
                self.assertEquals(200, response.status_int)
                self.assertIn(
                    'category="Power Searching with Google [Alpha] '
                    '(Private)', response.body)
                self.assertIn(
                    'category="Power Searching with Google [Bravo] '
                    '(Private)', response.body)
                self.assertIn(
                    'category="Power Searching with Google [Charlie] '
                    '(Private)', response.body)
                self.assertIn(
                    'category="Power Searching with Google [Delta] '
                    '(Private)', response.body)

    def test_guide_enabled_course(self):
        with actions.OverriddenEnvironment(self.GUIDE_ENABLED_COURSE):
            actions.logout()
            self.assert_guide_accesssible('Alpha')
            self.assert_guide_accesssible('Bravo')
            self.assert_guide_not_accesssible(
                'Charlie', is_guides_accessible=True)
            self.assert_guide_not_accesssible(
                'Delta', is_guides_accessible=True)

            actions.login('guest@sample.com')
            self.assert_guide_accesssible('Alpha')
            self.assert_guide_accesssible('Bravo')
            self.assert_guide_not_accesssible(
                'Charlie', is_guides_accessible=True)
            self.assert_guide_not_accesssible(
                'Delta', is_guides_accessible=True)

            self.register('Charlie')
            self.assert_guide_accesssible('Alpha')
            self.assert_guide_accesssible('Bravo')
            self.assert_guide_accesssible('Charlie')
            self.assert_guide_not_accesssible(
                'Delta', is_guides_accessible=True)

            actions.login('admin@sample.com', is_admin=True)
            for name in ['Alpha', 'Bravo', 'Charlie', 'Delta']:
                self.assert_guide_accesssible(name)

            # check course labels as admin sees them
            response = self.get('/modules/guides')
            self.assertEquals(200, response.status_int)
            self.assertIn(
                'category="Power Searching with Google [Alpha]',
                response.body)
            self.assertIn(
                'category="Power Searching with Google [Bravo]',
                response.body)
            self.assertIn(
                'category="Power Searching with Google [Charlie] '
                '(Registration required)', response.body)
            self.assertIn(
                'category="Power Searching with Google [Delta] (Private)',
                response.body)

    def test_guide_shows_all_unit_lessons(self):
        with actions.OverriddenEnvironment(self.GUIDE_ENABLED_PRIVATE):
            actions.login('test@example.com', is_admin=True)

            # check guides page
            response = self.get('/modules/guides')
            self.assertIn('<gcb-guide-container>', response.body)
            self.assertIn(
                'category="Power Searching with Google [Alpha]',
                response.body)
            self.assertIn('<gcb-guide-card', response.body)
            self.assertIn(  # note that we intentionally don't show "Unit 1 - "
                'label="Introduction"', response.body)

            # check unit and lesson pages
            app_ctx = sites.get_all_courses()[0]
            course = courses.Course(None, app_context=app_ctx)
            for unit in course.get_units():
                if unit.type != verify.UNIT_TYPE_UNIT:
                    continue
                response = self.get('/Alpha/guide?unit_id=%s' % unit.unit_id)

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
                self.assertIn(
                    '<script>gcbTagYoutubeEnqueueVideo("', response.body)
                self.assertIn(
                    '<script src="/modules/'
                    'assessment_tags/resources/grading.js">', response.body)
