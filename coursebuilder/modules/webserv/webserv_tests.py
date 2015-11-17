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

"""Tests for webserv module."""

__author__ = 'Pavel Simakov (psimakov@google.com)'


from controllers import sites
from models import courses
from tests.functional import actions


class WebservTests(actions.TestBase):

    def setUp(self):
        super(WebservTests, self).setUp()
        sites.setup_courses('')

        # make sure we know of all course availability values; if these change,
        # we will need to revise how to apply rights to webserv content
        self.assertEquals([
            'private', 'public',
            'registration_optional', 'registration_required'], (
                sorted(courses.COURSE_AVAILABILITY_POLICIES.keys())))
        self.assertEquals(
            ['course', 'public', 'unavailable'],
            sorted(courses.AVAILABILITY_VALUES))

    def disabled(self):
        return {
            'course': courses.COURSE_AVAILABILITY_POLICIES[
                  courses.COURSE_AVAILABILITY_PUBLIC],
            'modules': {'webserv': {'enabled': False}}}

    def enabled(
            self, slug='foo', jinja_enabled=False, md_enabled=False,
            availability=courses.AVAILABILITY_COURSE):
        return {
            'course':  courses.COURSE_AVAILABILITY_POLICIES[
                  courses.COURSE_AVAILABILITY_PUBLIC],
            'modules': {'webserv': {
                'enabled': True, 'doc_root': 'sample',
                'jinja_enabled': jinja_enabled, 'md_enabled': md_enabled,
                'slug': slug, 'availability': availability}}}

    def _import_sample_course(self):
        dst_app_context = actions.simple_add_course(
            'webserv', 'webserv_tests@google.com',
            'Power Searching with Google')
        dst_course = courses.Course(None, dst_app_context)
        src_app_context = sites.get_all_courses('course:/:/:')[0]
        errors = []
        dst_course.import_from(src_app_context, errors)
        dst_course.save()
        self.assertEquals(0, len(errors))

    def _init_course(self, slug):
        self._import_sample_course()
        sites.setup_courses('course:/%s::ns_webserv' % slug)
        self.base = '/%s' % slug

    def assertNoPage(self, url):
        response = self.get(url, expect_errors=True)
        self.assertEquals(404, response.status_int)

    def assertPage(self, url, text):
        response = self.get(url)
        self.assertEquals(200, response.status_int, response)
        self.assertIn(text, response.body)

    def test_no_course_no_webserver(self):
        actions.login('guest@example.com', is_admin=True)
        with actions.OverriddenEnvironment(self.disabled()):
            self.assertNoPage('/test')
            self.assertNoPage('/test/course')
            self.assertNoPage('/test/anything-here/anything.html')

            self.assertNoPage('/foo/index.html')
            self.assertNoPage('/foo/')
            self.assertNoPage('/foo')

    def test_course_no_webserver(self):
        self._init_course('test')
        actions.login('guest@example.com', is_admin=True)
        with actions.OverriddenEnvironment(self.disabled()):
            self.assertPage('/test', 'Searching')
            self.assertPage('/test/', 'Searching')
            self.assertPage('/test/course', 'Searching')
            self.assertNoPage('/test/anything-here/anything.html')

            self.assertNoPage('/test/foo/index.html')
            self.assertNoPage('/test/foo/')

    def test_course_and_webserver(self):
        self._init_course('test')
        actions.login('guest@example.com', is_admin=True)
        with actions.OverriddenEnvironment(self.enabled()):
            self.assertPage('/test/course', 'Power Searching')
            self.assertNoPage('/test/anything-here/anything.html')

            self.assertPage('/test/foo/index.html', 'Web Server')
            self.assertPage('/test/foo/', 'Web Server')
            self.assertPage('/test/foo', 'Web Server')
            self.assertPage('/test/', 'Web Server')
            self.assertPage('/test', 'Web Server')
            self.assertNoPage('/test/badPage.html')

    def test_course_slug_webserver_no_slug(self):
        self._init_course('test')
        actions.login('guest@example.com', is_admin=True)
        with actions.OverriddenEnvironment(self.enabled(slug='')):
            self.assertPage('/test/course', 'Power Searching')
            self.assertNoPage('/test/anything-here/anything.html')

            response = self.get('/')
            self.assertEquals(302, response.status_int, response)
            self.assertIn('http://localhost/test/index.html', response.location)

            self.assertPage('/test/index.html', 'Web Server')
            self.assertPage('/test/', 'Web Server')
            self.assertPage('/test', 'Web Server')
            self.assertNoPage('/test/badPage.html')

    def test_course_no_slug_webserver_slug(self):
        self._init_course('')
        actions.login('guest@example.com', is_admin=True)
        with actions.OverriddenEnvironment(self.enabled()):
            self.assertPage('/course', 'Power Searching')
            self.assertNoPage('/anything-here/anything.html')

            response = self.get('/')
            self.assertEquals(302, response.status_int, response)
            self.assertIn('http://localhost/index.html', response.location)

            self.assertPage('/foo/index.html', 'Web Server')
            self.assertPage('/foo/', 'Web Server')
            self.assertPage('/foo', 'Web Server')
            self.assertNoPage('/foo/badPage.html')

    def test_course_no_slug_webserver_no_slug(self):
        self._init_course('')
        actions.login('guest@example.com', is_admin=True)
        with actions.OverriddenEnvironment(self.enabled(slug='')):
            # note how /course is still available; enabling web server
            # on '/' does not shadow any existing namespaced routes!!!
            self.assertPage('/course', 'Power Searching')
            self.assertNoPage('/anything-here/anything.html')

            response = self.get('/')
            self.assertEquals(302, response.status_int, response)
            self.assertIn('http://localhost/index.html', response.location)

            self.assertPage('/index.html', 'Web Server')

            self.assertNoPage('/foo/index.html')
            self.assertNoPage('/foo/')
            self.assertNoPage('/foo')
            self.assertNoPage('/foo/')

    def test_html_with_and_without_jinja(self):
        self._init_course('test')
        actions.login('guest@example.com', is_admin=True)
        with actions.OverriddenEnvironment(self.enabled(jinja_enabled=False)):
            response = self.get('/test/foo/index.html')
            self.assertIn('{{ course_info.course.title }}', response.body)
            self.assertNotIn('Power Searching with Google', response.body)

            response = self.get('/test/foo/main.css')
            self.assertIn('{{ course_info.course.title }}', response.body)

        with actions.OverriddenEnvironment(self.enabled(jinja_enabled=True)):
            response = self.get('/test/foo/index.html')
            self.assertNotIn('{{ course_info.course.title }}', response.body)
            self.assertIn('Power Searching with Google', response.body)
            self.assertIn(
                'https://www.youtube.com/embed/1ppwmxidyIE', response.body)
            self.assertIn('title="YouTube Video Player"', response.body)

            response = self.get('/test/foo/main.css')
            self.assertIn('{{ course_info.course.title }}', response.body)

            response = self.get('/test/foo/jinja.html')
            self.assertNotIn('gcb_webserv_metadata', response.body)
            self.assertIn(
                '<li><b>is_super_admin</b>: True</li>', response.body)
            self.assertIn('Pre-course assessment', response.body)
            self.assertIn('guest@example.com', response.body)

        actions.login('student@example.com')
        with actions.OverriddenEnvironment(self.enabled(jinja_enabled=True)):
            response = self.get('/test/foo/jinja.html')
            self.assertNotIn('gcb_webserv_metadata', response.body)
            self.assertNotIn(
                '<li><b>is_super_admin</b>: True</li>', response.body)
            self.assertNotIn('Pre-course assessment', response.body)
            self.assertNotIn('guest@example.com', response.body)
            self.assertIn('can only be seen by the by admin', response.body)

    def test_html_with_and_without_markdown(self):
        self._init_course('test')
        actions.login('guest@example.com', is_admin=True)
        with actions.OverriddenEnvironment(self.enabled(md_enabled=False)):
            response = self.get('/test/foo/index.md')
            self.assertNotIn('<h1>A First Level Header</h1>', response.body)
            self.assertIn('{{ course_info.course.title }}', response.body)
            self.assertNotIn('Power Searching with Google', response.body)

        with actions.OverriddenEnvironment(self.enabled(md_enabled=True)):
            response = self.get('/test/foo/index.md')
            self.assertIn('<h1>A First Level Header</h1>', response.body)
            self.assertIn('{{ course_info.course.title }}', response.body)
            self.assertNotIn('Power Searching with Google', response.body)

        with actions.OverriddenEnvironment(self.enabled(
                md_enabled=True, jinja_enabled=True)):
            response = self.get('/test/foo/index.md')
            self.assertIn('<h1>A First Level Header</h1>', response.body)
            self.assertNotIn('{{ course_info.course.title }}', response.body)
            self.assertIn('<em>Power Searching with Google</em>', response.body)

    def test_markdown_with_and_without_jinja(self):
        self._init_course('test')
        actions.login('guest@example.com', is_admin=True)
        with actions.OverriddenEnvironment(self.enabled(
                md_enabled=False, jinja_enabled=False)):
            response = self.get('/test/foo/index.md')
            self.assertNotIn('<h1>A First Level Header</h1>', response.body)
            self.assertIn('{{ course_info.course.title }}', response.body)
            self.assertNotIn('Power Searching with Google', response.body)

        with actions.OverriddenEnvironment(self.enabled(
                md_enabled=True, jinja_enabled=False)):
            response = self.get('/test/foo/index.md')
            self.assertIn('<h1>A First Level Header</h1>', response.body)
            self.assertIn('{{ course_info.course.title }}', response.body)
            self.assertNotIn('Power Searching with Google', response.body)

        with actions.OverriddenEnvironment(self.enabled(
                md_enabled=False, jinja_enabled=True)):
            response = self.get('/test/foo/index.md')
            self.assertNotIn('<h1>A First Level Header</h1>', response.body)
            self.assertIn('{{ course_info.course.title }}', response.body)
            self.assertNotIn('Power Searching with Google', response.body)

        with actions.OverriddenEnvironment(self.enabled(
                md_enabled=True, jinja_enabled=True)):
            response = self.get('/test/foo/index.md')
            self.assertIn('<h1>A First Level Header</h1>', response.body)
            self.assertNotIn('{{ course_info.course.title }}', response.body)
            self.assertIn('Power Searching with Google', response.body)

    def test_availability_unavailable(self):
        self._init_course('test')
        for availability in [
                courses.COURSE_AVAILABILITY_PRIVATE,
                courses.COURSE_AVAILABILITY_PUBLIC,
                courses.COURSE_AVAILABILITY_REGISTRATION_REQUIRED,
                courses.COURSE_AVAILABILITY_REGISTRATION_OPTIONAL]:
            env = self.enabled(availability=courses.AVAILABILITY_UNAVAILABLE)
            env.update({
                'course': courses.COURSE_AVAILABILITY_POLICIES[availability]})
            with actions.OverriddenEnvironment(env):
                actions.login('student@example.com', is_admin=True)
                self.assertPage('/test/foo/index.html', ' Web Server')
                self.assertPage('/test/foo/index.md', ' Web Server')
                self.assertPage('/test/foo/main.css', ' Web Server')

                actions.login('student@example.com')
                self.assertNoPage('/test/foo/index.html')
                self.assertNoPage('/test/foo/index.md')
                self.assertNoPage('/test/foo/main.css')

    def test_availability_course(self):
        self._init_course('test')
        actions.login('student@example.com')

        env = self.enabled(availability=courses.AVAILABILITY_COURSE)
        env.update({'course': courses.COURSE_AVAILABILITY_POLICIES[
            courses.COURSE_AVAILABILITY_PRIVATE]})
        with actions.OverriddenEnvironment(env):
            self.assertNoPage('/test/foo/index.html')
            self.assertNoPage('/test/foo/index.md')
            self.assertNoPage('/test/foo/main.css')

        for availability in [
                courses.COURSE_AVAILABILITY_PUBLIC,
                courses.COURSE_AVAILABILITY_REGISTRATION_REQUIRED,
                courses.COURSE_AVAILABILITY_REGISTRATION_OPTIONAL]:
            env = self.enabled(availability=courses.AVAILABILITY_COURSE)
            env.update({'course': courses.COURSE_AVAILABILITY_POLICIES[
                availability]})
            with actions.OverriddenEnvironment(env):
                self.assertPage('/test/foo/index.html', 'Web Server')
                self.assertPage('/test/foo/index.md', 'Web Server')
                self.assertPage('/test/foo/main.css', 'Web Server')
