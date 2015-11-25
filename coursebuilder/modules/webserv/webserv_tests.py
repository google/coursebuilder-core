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
from modules.webserv import webserv
from tests.functional import actions

class WebservFunctionalTests(actions.TestBase):

    def setUp(self):
        super(WebservFunctionalTests, self).setUp()
        sites.setup_courses('')

        # make sure we know of all course availability values; if these change,
        # we will need to revise how to apply rights to webserv content
        self.assertEquals([
            'private', 'public',
            'registration_optional', 'registration_required'], (
                sorted(courses.COURSE_AVAILABILITY_POLICIES.keys())))
        self.assertEquals(
            ['course', 'private', 'public'],
            sorted(courses.AVAILABILITY_VALUES))

    def disabled(self):
        return {
            'modules': {'webserv': {'enabled': False}}}

    def enabled(
            self, slug='foo', jinja_enabled=False, md_enabled=False,
            availability=courses.AVAILABILITY_COURSE,
            caching=webserv.CACHING_NONE):
        return {
            'modules': {'webserv': {
                'enabled': True, 'doc_root': 'sample',
                'jinja_enabled': jinja_enabled, 'md_enabled': md_enabled,
                'slug': slug, 'availability': availability,
                'caching': caching}}}

    def _import_sample_course(self):
        dst_app_context = actions.simple_add_course(
            'webserv', 'webserv_tests@google.com',
            'Power Searching with Google')
        dst_course = courses.Course(None, dst_app_context)
        src_app_context = sites.get_all_courses('course:/:/:')[0]
        errors = []
        dst_course.import_from(src_app_context, errors)
        dst_course.save()
        self.base = ''
        self.assertEquals(0, len(errors))
        return dst_course

    def _init_course(self, slug):
        course = self._import_sample_course()
        sites.setup_courses('course:/%s::ns_webserv' % slug)
        return course

    def assertNoPage(self, url):
        response = self.get(url, expect_errors=True)
        self.assertEquals(404, response.status_int)

    def assertRedirectPage(self, url, location, partial=False):
        response = self.get(url, expect_errors=True)
        self.assertEquals(302, response.status_int)
        if partial:
            self.assertIn(location, response.location)
        else:
            self.assertEquals('http://localhost' + location, response.location)

    def assertPage(self, url, text):
        response = self.get(url)
        self.assertEquals(200, response.status_int, response)
        if text:
            self.assertIn(text, response.body)

    def register(self):
        self.base = '/test'
        actions.register(self, 'Test Student')
        self.base = ''

    def unregister(self):
        self.base = '/test'
        actions.unregister(self)
        self.base = ''

    def test_no_course_no_webserver(self):
        actions.login('admin@example.com', is_admin=True)
        with actions.OverriddenEnvironment(self.disabled()):
            self.assertRedirectPage('/', '/admin/welcome')
            self.assertNoPage('/test')
            self.assertNoPage('/test/course')
            self.assertNoPage('/test/anything-here/anything.html')
            self.assertNoPage('/foo/index.html')
            self.assertNoPage('/foo/')
            self.assertNoPage('/foo')

    def test_course_no_webserver(self):
        self._init_course('test')
        actions.login('admin@example.com', is_admin=True)
        with actions.OverriddenEnvironment(self.disabled()):
            self.assertRedirectPage('/', '/test/course?use_last_location=true')
            self.assertPage('/test', 'Searching')
            self.assertPage('/test/', 'Searching')
            self.assertPage('/test/course', 'Searching')
            self.assertNoPage('/test/foo/index.html')
            self.assertNoPage('/test/foo/')
            self.assertNoPage('/test/anything-here/anything.html')

    def test_course_and_webserver(self):
        self._init_course('test')
        actions.login('admin@example.com', is_admin=True)
        with actions.OverriddenEnvironment(self.enabled()):
            self.assertRedirectPage('/', '/test/foo/')
            self.assertPage('/test', 'Power Searching')
            self.assertPage('/test/', 'Power Searching')
            self.assertPage('/test/course', 'Power Searching')
            self.assertNoPage('/test/anything-here/anything.html')
            self.assertRedirectPage('/test/foo', '/test/foo/')
            self.assertPage('/test/foo/', 'Web Server')
            self.assertPage('/test/foo/index.html', 'Web Server')
            self.assertNoPage('/test/badPage.html')

            # note how existing URLs still work, including /assets/...
            self.assertPage('/test/course', 'Power Searching')
            self.assertPage('/test/dashboard', 'Advanced site settings')
            self.assertPage('/admin/welcome', 'Welcome to Course Builder')
            self.assertPage('/test/assets/img/Image7.7.png', None)

            # fetch static resource; note it returns 404, because static
            # serving does not work in the test server
            self.assertNoPage('/modules/webserv/_static/book-icon-md.png')

    def test_course_slug_webserver_no_slug(self):
        self._init_course('test')
        actions.login('admin@example.com', is_admin=True)
        with actions.OverriddenEnvironment(self.enabled(slug='')):
            self.assertRedirectPage('/', '/test/')
            self.assertRedirectPage('/test', '/test/')
            self.assertPage('/test/', 'Web Server')
            self.assertPage('/test/course', 'Power Searching')
            self.assertPage('/test/index.html', 'Web Server')
            self.assertNoPage('/test/badPage.html')

    def test_course_no_slug_webserver_slug(self):
        self._init_course('')
        actions.login('admin@example.com', is_admin=True)
        with actions.OverriddenEnvironment(self.enabled()):
            self.assertRedirectPage('/', '/foo/')
            self.assertPage('/course', 'Power Searching')
            self.assertRedirectPage('/foo', '/foo/')
            self.assertPage('/foo/', 'Web Server')
            self.assertPage('/foo/index.html', 'Web Server')
            self.assertNoPage('/anything-here/anything.html')
            self.assertNoPage('/foo/badPage.html')

    def test_course_no_slug_webserver_no_slug(self):
        self._init_course('')
        actions.login('admin@example.com', is_admin=True)
        with actions.OverriddenEnvironment(self.enabled(slug='')):
            self.assertPage('/', 'Web Server')
            self.assertPage('/course', 'Power Searching')
            self.assertNoPage('/anything-here/anything.html')
            self.assertPage('/index.html', 'Web Server')
            self.assertNoPage('/foo/index.html')
            self.assertNoPage('/foo/')
            self.assertNoPage('/foo')

    def test_html_with_and_without_jinja(self):
        self._init_course('test')
        actions.login('admin@example.com', is_admin=True)
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
                '<script>gcbTagYoutubeEnqueueVideo("1ppwmxidyIE", ',
                response.body)

            response = self.get('/test/foo/main.css')
            self.assertIn('{{ course_info.course.title }}', response.body)

            response = self.get('/test/foo/jinja.html')
            self.assertNotIn('gcb_webserv_metadata', response.body)
            self.assertIn(
                '<li><b>is_super_admin</b>: True</li>', response.body)
            self.assertIn('Pre-course assessment', response.body)
            self.assertIn('admin@example.com', response.body)

        actions.login('student@example.com')
        with actions.OverriddenEnvironment(self.enabled(jinja_enabled=True)):
            response = self.get('/test/foo/jinja.html')
            self.assertNotIn('gcb_webserv_metadata', response.body)
            self.assertNotIn(
                '<li><b>is_super_admin</b>: True</li>', response.body)
            self.assertNotIn('Pre-course assessment', response.body)
            self.assertNotIn('student@example.com', response.body)
            self.assertIn('can only be seen by the by admin', response.body)

    def test_html_with_and_without_markdown(self):
        self._init_course('test')
        actions.login('admin@example.com', is_admin=True)

        with actions.OverriddenEnvironment(self.enabled(md_enabled=False)):
            response = self.get('/test/foo/index.md')
            self.assertIn('gcb-md-header: /md_header.html', response.body)
            self.assertNotIn(
                '<title>Course Builder Markdown Page</title>', response.body)
            self.assertIn('gcb-md-footer: /md_footer.html', response.body)
            self.assertNotIn(
                '<p>Powered by Course Builder!</p>', response.body)

            response = self.get('/test/foo/markdown.md')
            self.assertNotIn('<h1>A First Level Header</h1>', response.body)
            self.assertNotIn('<h2 id="my-second-level-header">', response.body)
            self.assertIn('{{ course_info.course.title }}', response.body)
            self.assertNotIn('Power Searching with Google', response.body)

        with actions.OverriddenEnvironment(self.enabled(md_enabled=True)):
            response = self.get('/test/foo/index.md')
            self.assertNotIn('gcb-md-header: /md_header.html', response.body)
            self.assertIn(
                '<title>Course Builder Markdown Page</title>', response.body)
            self.assertNotIn('gcb-md-footer: /md_footer.html', response.body)
            self.assertIn(
                '<p>Powered by Course Builder!</p>', response.body)

            response = self.get('/test/foo/markdown.md')
            self.assertIn('<h1>A First Level Header</h1>', response.body)
            self.assertIn('<h2 id="my-second-level-header">', response.body)
            self.assertIn('{{ course_info.course.title }}', response.body)
            self.assertNotIn('Power Searching with Google', response.body)

    def test_markdown_page_query_string(self):
        self._init_course('test')
        actions.login('admin@example.com', is_admin=True)

        with actions.OverriddenEnvironment(self.enabled(md_enabled=True)):
            response = self.get(
                '/test/foo/markdown.md?default_header_footer=true')
            self.assertIn('<!-- MD_DEFAULT_HEADER -->', response.body)
            self.assertNotIn(
                '<title>Course Builder Markdown Page</title>', response.body)
            self.assertIn('<!-- MD_DEFAULT_FOOTER -->', response.body)
            self.assertNotIn(
                '<p>Powered by Course Builder!</p>', response.body)

            response = self.get('/test/foo/markdown.md')
            self.assertNotIn('<!-- MD_DEFAULT_HEADER -->', response.body)
            self.assertIn(
                '<title>Course Builder Markdown Page</title>', response.body)
            self.assertNotIn('<!-- MD_DEFAULT_FOOTER -->', response.body)
            self.assertIn(
                '<p>Powered by Course Builder!</p>', response.body)

            response = self.get(
                '/test/foo/markdown.md?body_only=true')
            self.assertNotIn('<head>', response.body)
            self.assertIn('<h1>A First Level Header</h1>', response.body)

    def test_markdown_alternative_names(self):
        # when an author creates markdown document foo.md and wants to add
        # a link to a document bar.md he may specify either bar.html or
        # bar.md as link target; here we tests that markdown.html is
        # accessible; it does not really exist in the filesystem; a system
        # will pretend it exists when markdown is enabled and that it does
        # not exist when markdown is disabled
        self._init_course('test')
        actions.login('admin@example.com', is_admin=True)

        with actions.OverriddenEnvironment(self.enabled(md_enabled=True)):
            response = self.get('/test/foo/markdown.html')
            self.assertIn('<h1>A First Level Header</h1>', response.body)
            self.assertIn('{{ course_info.course.title }}', response.body)
            self.assertNotIn('Power Searching with Google', response.body)
            self.assertNoPage('/test/foo/main.html')

        with actions.OverriddenEnvironment(self.enabled(md_enabled=False)):
            self.assertNoPage('/test/foo/markdown.html')
            self.assertNoPage('/test/foo/main.html')

    def test_markdown_jinja_permutations(self):
        self._init_course('test')
        actions.login('admin@example.com', is_admin=True)

        with actions.OverriddenEnvironment(self.enabled(
                md_enabled=False, jinja_enabled=False)):
            response = self.get('/test/foo/markdown.md')
            self.assertNotIn('<h1>A First Level Header</h1>', response.body)
            self.assertIn('{{ course_info.course.title }}', response.body)
            self.assertNotIn('Power Searching with Google', response.body)

        with actions.OverriddenEnvironment(self.enabled(
                md_enabled=True, jinja_enabled=False)):
            response = self.get('/test/foo/markdown.md')
            self.assertIn('<h1>A First Level Header</h1>', response.body)
            self.assertIn('{{ course_info.course.title }}', response.body)
            self.assertNotIn('Power Searching with Google', response.body)

        with actions.OverriddenEnvironment(self.enabled(
                md_enabled=False, jinja_enabled=True)):
            response = self.get('/test/foo/markdown.md')
            self.assertNotIn('<h1>A First Level Header</h1>', response.body)
            self.assertIn('{{ course_info.course.title }}', response.body)
            self.assertNotIn('Power Searching with Google', response.body)

        with actions.OverriddenEnvironment(self.enabled(
                md_enabled=True, jinja_enabled=True)):
            response = self.get('/test/foo/markdown.md')
            self.assertIn('<h1>A First Level Header</h1>', response.body)
            self.assertNotIn('{{ course_info.course.title }}', response.body)
            self.assertIn('Power Searching with Google', response.body)

    def test_availability_unavailable(self):
        course = self._init_course('test')
        env = self.enabled(availability=courses.AVAILABILITY_UNAVAILABLE)

        for availability in [
                courses.COURSE_AVAILABILITY_PRIVATE,
                courses.COURSE_AVAILABILITY_PUBLIC,
                courses.COURSE_AVAILABILITY_REGISTRATION_REQUIRED,
                courses.COURSE_AVAILABILITY_REGISTRATION_OPTIONAL]:
            course.set_course_availability(availability)
            with actions.OverriddenEnvironment(env):
                actions.login('admin@example.com', is_admin=True)
                self.assertPage('/test/foo/index.html', ' Web Server')
                self.assertPage('/test/foo/markdown.md', ' Web Server')
                self.assertPage('/test/foo/main.css', ' Web Server')

                actions.login('student@example.com')
                self.assertNoPage('/test/foo/index.html')
                self.assertNoPage('/test/foo/markdown.md')
                self.assertNoPage('/test/foo/main.css')

    def test_availability_course(self):
        course = self._init_course('test')
        env = self.enabled(availability=courses.AVAILABILITY_COURSE)

        for availability in [
                courses.COURSE_AVAILABILITY_PUBLIC,
                courses.COURSE_AVAILABILITY_REGISTRATION_OPTIONAL]:
            course.set_course_availability(availability)
            with actions.OverriddenEnvironment(env):
                actions.logout()
                self.assertPage('/test/foo/index.html', 'Web Server')
                self.assertPage('/test/foo/markdown.md', 'Web Server')
                self.assertPage('/test/foo/main.css', 'Web Server')

                actions.login('student@example.com')
                self.assertPage('/test/foo/index.html', 'Web Server')
                self.assertPage('/test/foo/markdown.md', 'Web Server')
                self.assertPage('/test/foo/main.css', 'Web Server')

                if availability == (
                        courses.COURSE_AVAILABILITY_REGISTRATION_OPTIONAL):
                    self.register()
                    self.assertPage('/test/foo/index.html', ' Web Server')
                    self.assertPage('/test/foo/markdown.md', ' Web Server')
                    self.assertPage('/test/foo/main.css', ' Web Server')
                    self.unregister()

                actions.login('admin@example.com', is_admin=True)
                self.assertPage('/test/foo/index.html', ' Web Server')
                self.assertPage('/test/foo/markdown.md', ' Web Server')
                self.assertPage('/test/foo/main.css', ' Web Server')

        for availability in [
                courses.COURSE_AVAILABILITY_REGISTRATION_REQUIRED,
                courses.COURSE_AVAILABILITY_PRIVATE]:
            course.set_course_availability(availability)
            with actions.OverriddenEnvironment(env):
                actions.logout()
                self.assertNoPage('/test/foo/index.html')
                self.assertNoPage('/test/foo/markdown.md')
                self.assertNoPage('/test/foo/main.css')

                actions.login('student@example.com')
                self.assertNoPage('/test/foo/index.html')
                self.assertNoPage('/test/foo/markdown.md')
                self.assertNoPage('/test/foo/main.css')

                if availability == (
                        courses.COURSE_AVAILABILITY_REGISTRATION_REQUIRED):
                    self.register()
                    self.assertPage('/test/foo/index.html', ' Web Server')
                    self.assertPage('/test/foo/markdown.md', ' Web Server')
                    self.assertPage('/test/foo/main.css', ' Web Server')
                    self.unregister()

                actions.login('admin@example.com', is_admin=True)
                self.assertPage('/test/foo/index.html', ' Web Server')
                self.assertPage('/test/foo/markdown.md', ' Web Server')
                self.assertPage('/test/foo/main.css', ' Web Server')

    def assert_no_cache(self, response):
        self.assertIn('no-cache', response.headers['Cache-Control'])
        self.assertIn('no-cache', response.headers['Pragma'])
        self.assertNotIn('public', response.headers['Cache-Control'])
        self.assertNotIn('max-age', response.headers['Cache-Control'])
        self.assertIn(
            webserv.EXPIRES_IN_THE_PAST, response.headers['Expires'])

    def assert_cached(self, response, duration_min):
        self.assertNotIn('no-cache', response.headers['Cache-Control'])
        self.assertNotIn('Pragma', response.headers)
        self.assertIn('public', response.headers['Cache-Control'])
        self.assertIn(
            'max-age=%s' % (60 * duration_min),
            response.headers['Cache-Control'])
        self.assertNotIn(
            webserv.EXPIRES_IN_THE_PAST, response.headers['Expires'])

    def test_caching(self):
        course = self._init_course('test')
        actions.login('admin@example.com', is_admin=True)

        with actions.OverriddenEnvironment(self.enabled(
                md_enabled=True, jinja_enabled=True)):
            for url in [
                    '/test/foo/main.css',
                    '/test/foo/index.html',
                    '/test/foo/markdown.md']:
                self.assert_no_cache(self.get(url))

        with actions.OverriddenEnvironment(self.enabled(
                md_enabled=True, jinja_enabled=True,
                caching=webserv.CACHING_5_MIN)):
            response = self.get('/test/foo/main.css')
            self.assert_cached(response, 5)
            for url in [
                    '/test/foo/index.html',
                    '/test/foo/markdown.md']:
                self.assert_no_cache(self.get(url))

        with actions.OverriddenEnvironment(self.enabled(
                md_enabled=True, jinja_enabled=False,
                caching=webserv.CACHING_1_HOUR)):
            for url in [
                    '/test/foo/main.css',
                    '/test/foo/index.html',
                    '/test/foo/markdown.md']:
                self.assert_cached(self.get(url), 60)
