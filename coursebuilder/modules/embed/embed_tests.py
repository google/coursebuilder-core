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

"""Functional tests for modules.embed."""

__author__ = [
    'johncox@google.com (John Cox)',
]

from common import users
from common import utils
from controllers import sites
from models import courses
from models import models
from modules.embed import embed

from tests.functional import actions


class FakeHandler(object):

    def __init__(self, app_context, request):
        self.app_context = app_context
        self.request = request


class FakeRequest(object):
    def __init__(self, method, host_url):
        self.method = method
        self.host_url = host_url


class DemoHandlerTestBase(actions.TestBase):

    _HANDLER = None
    _URL = None

    def assert_get_returns_200_with_contents_in_dev(self):
        response = self.testapp.get(self._URL)

        self.assertEquals(200, response.status_code)
        self.assertTrue(response.body)

    def assert_get_returns_404_in_prod(self):
        self.swap(self._HANDLER, '_active', lambda _: False)
        response = self.testapp.get(self._URL, expect_errors=True)

        self.assertEquals(404, response.status_code)


class DemoHandlerTest(DemoHandlerTestBase):

    # Allow access to code under test. pylint: disable=protected-access
    _HANDLER = embed._DemoHandler
    _URL = embed._DEMO_URL

    def test_get_returns_200_with_contents_in_dev(self):
        self.assert_get_returns_200_with_contents_in_dev()

    def test_get_returns_404_in_prod(self):
        self.assert_get_returns_404_in_prod()


class GlobalErrorsDemoHandlerTest(DemoHandlerTestBase):

    # Allow access to code under test. pylint: disable=protected-access
    _HANDLER = embed._GlobalErrorsDemoHandler
    _URL = embed._GLOBAL_ERRORS_DEMO_URL

    def test_get_returns_200_with_contents_in_dev(self):
        self.assert_get_returns_200_with_contents_in_dev()

    def test_get_returns_404_in_prod(self):
        self.assert_get_returns_404_in_prod()


class LocalErrorsDemoHandlerTest(DemoHandlerTestBase):

    # Allow access to code under test. pylint: disable=protected-access
    _HANDLER = embed._LocalErrorsDemoHandler
    _URL = embed._LOCAL_ERRORS_DEMO_URL

    def test_get_returns_200_with_contents_in_dev(self):
        self.assert_get_returns_200_with_contents_in_dev()

    def test_get_returns_404_in_prod(self):
        self.assert_get_returns_404_in_prod()


class ExampleEmbedTestBase(actions.TestBase):

    def setUp(self):
        super(ExampleEmbedTestBase, self).setUp()
        self.admin_email = 'admin@example.com'

    def assert_child_course_namespaces_malformed(self, response):
        self.assertEquals(500, response.status_code)
        self.assertLogContains('child_courses invalid')

    def assert_current_user_enrolled(self, namespace):
        self.assertTrue(bool(self.get_student_for_current_user(namespace)))

    def assert_current_user_not_enrolled(self, namespace):
        self.assertFalse(bool(self.get_student_for_current_user(namespace)))

    def assert_embed_rendered(self, response, email, course_title):
        self.assert_expected_headers_present(response.headers)
        self.assertEquals(200, response.status_code)
        # Frame resizing JS present. Allow access to code under test.
        # pylint: disable=protected-access
        self.assertIn(embed._EMBED_CHILD_JS_URL, response.body)
        # The desired user is authenticated.
        self.assertIn(email, response.body)
        # The id and type of the embedded resource are correct.
        self.assertIn('<strong>example</strong>', response.body)
        self.assertIn('<strong>1</strong>', response.body)
        # We're in the correct target course, verified by its title.
        self.assertIn('<strong>%s</strong>' % course_title, response.body)

    def assert_enrollment_error(self, response, email, num_matches):
        self.assert_expected_headers_present(response.headers)
        self.assertEquals(200, response.status_code)
        self.assertIn('Enrollment error', response.body)
        self.assertIn(email, response.body)
        self.assertLogContains(
            'Must have exactly 1 enrollment target; got %s' % num_matches)

    def assert_expected_headers_present(self, headers):
        self.assertEquals(headers.get('X-Frame-Options'), 'ALLOWALL')

    def get_env(self, child_courses=None):
        env = {'course': {}}
        if child_courses:
            env['course']['child_courses'] = child_courses

        return env

    def get_student_for_current_user(self, namespace):
        user = users.get_current_user()
        assert user

        with utils.Namespace(namespace):
            return models.Student.get_enrolled_student_by_user(user)

    def set_course_setting(self, namespace, name, value):
        app_context = sites.get_app_context_for_namespace(namespace)
        course = courses.Course.get(app_context)
        settings = course.app_context.get_environ()
        settings['course'][name] = value
        course.save_settings(settings)

    def set_now_available(self, namespace, value):
        self.set_course_setting(namespace, 'now_available', value)

    def set_whitelist(self, namespace, value):
        self.set_course_setting(namespace, 'whitelist', value)


class ExampleEmbedAndHandlerV1ChildCoursesTest(ExampleEmbedTestBase):
    """Tests example embed with child courses."""

    def setUp(self):
        super(ExampleEmbedAndHandlerV1ChildCoursesTest, self).setUp()
        self.student_email = 'student@example.com'
        actions.login(self.student_email)
        actions.simple_add_course('parent', self.admin_email, 'Parent')
        actions.simple_add_course('child1', self.admin_email, 'Child1')
        actions.simple_add_course('child2', self.admin_email, 'Child2')

    def assert_user_only_enrolled_in(self, enrolled_namespace):
        not_enrolled = ['ns_parent', 'ns_child1', 'ns_child2']
        not_enrolled.remove(enrolled_namespace)

        for namespace in not_enrolled:
            self.assert_current_user_not_enrolled(namespace)

        self.assert_current_user_enrolled(enrolled_namespace)

    def assert_user_not_enrolled_in_any_course(self):
        self.assert_current_user_not_enrolled('ns_parent')
        self.assert_current_user_not_enrolled('ns_child1')
        self.assert_current_user_not_enrolled('ns_child2')

    def test_get_renders_error_when_no_available_child_courses(self):
        self.set_now_available('ns_child1', False)
        self.set_now_available('ns_child2', False)

        self.assert_user_not_enrolled_in_any_course()

        with actions.OverriddenEnvironment(self.get_env(
                ['ns_child1', 'ns_child2'])):
            redirect = self.testapp.get(
                '/parent/modules/embed/v1/resource/example/1',
                expect_errors=True)
            redirect_url = redirect.headers.get('Location')

            self.assertEquals(302, redirect.status_code)
            self.assertTrue(redirect_url)

            response = self.testapp.get(redirect_url)

            self.assert_enrollment_error(response, self.student_email, 0)
            self.assert_user_not_enrolled_in_any_course()

    def test_get_renders_error_when_whitelists_empty(self):
        self.set_now_available('ns_child1', True)
        self.set_now_available('ns_child2', True)

        self.assert_user_not_enrolled_in_any_course()

        # Both whitelists are empty, so the user may be enrolled in either.
        with actions.OverriddenEnvironment(self.get_env(
                ['ns_child1', 'ns_child2'])):
            redirect = self.testapp.get(
                '/parent/modules/embed/v1/resource/example/1',
                expect_errors=True)
            redirect_url = redirect.headers.get('Location')

            self.assertEquals(302, redirect.status_code)
            self.assertTrue(redirect_url)

            response = self.testapp.get(redirect_url)

            self.assert_enrollment_error(response, self.student_email, 2)
            self.assert_user_not_enrolled_in_any_course()

    def test_get_renders_error_when_user_on_multiple_whitelists(self):
        self.set_now_available('ns_child1', True)
        self.set_now_available('ns_child2', True)
        self.set_whitelist('ns_child1', self.student_email)
        self.set_whitelist('ns_child2', self.student_email)

        self.assert_user_not_enrolled_in_any_course()

        with actions.OverriddenEnvironment(self.get_env(
                ['ns_child1', 'ns_child2'])):
            redirect = self.testapp.get(
                '/parent/modules/embed/v1/resource/example/1',
                expect_errors=True)
            redirect_url = redirect.headers.get('Location')

            self.assertEquals(302, redirect.status_code)
            self.assertTrue(redirect_url)

            response = self.testapp.get(redirect_url)

            self.assert_enrollment_error(response, self.student_email, 2)
            self.assert_user_not_enrolled_in_any_course()

    def test_get_succeeds_when_exactly_one_enrollment_target(self):
        self.set_now_available('ns_child1', True)
        self.set_now_available('ns_child2', True)
        self.set_whitelist('ns_child1', 'not_' + self.student_email)
        self.set_whitelist('ns_child2', self.student_email)

        self.assert_user_not_enrolled_in_any_course()

        with actions.OverriddenEnvironment(self.get_env(
                ['ns_child1', 'ns_child2'])):
            redirect = self.testapp.get(
                '/parent/modules/embed/v1/resource/example/1',
                expect_errors=True)
            redirect_url = redirect.headers.get('Location')

            self.assertEquals(302, redirect.status_code)
            self.assertTrue(redirect_url)

            response = self.testapp.get(redirect_url)

            self.assert_embed_rendered(response, self.student_email, 'Child2')
            self.assert_user_only_enrolled_in('ns_child2')

    def test_get_returns_500_when_child_courses_malformed(self):
        self.assert_user_not_enrolled_in_any_course()

        with actions.OverriddenEnvironment(self.get_env('bad')):
            response = self.testapp.get(
                '/parent/modules/embed/v1/resource/example/1',
                expect_errors=True)

        self.assert_child_course_namespaces_malformed(response)
        self.assert_user_not_enrolled_in_any_course()


class ExampleEmbedAndHandlerV1SingleCourseTest(ExampleEmbedTestBase):
    """Tests example embed with no child courses."""

    def setUp(self):
        super(ExampleEmbedAndHandlerV1SingleCourseTest, self).setUp()
        actions.login(self.admin_email, is_admin=True)
        actions.simple_add_course('course', self.admin_email, 'Course')
        self.user = users.get_current_user()

    def test_get_returns_302_to_200_with_good_payload_and_enrolls_student(self):
        self.assert_current_user_not_enrolled('ns_course')

        redirect = self.testapp.get(
            '/course/modules/embed/v1/resource/example/1')
        redirect_url = redirect.headers.get('Location')

        self.assertEquals(302, redirect.status_code)
        self.assertTrue(redirect_url)
        self.assert_current_user_enrolled('ns_course')

        response = self.testapp.get(redirect_url)

        self.assert_embed_rendered(response, self.admin_email, 'Course')

    def test_get_returns_404_if_kind_not_in_registry(self):
        response = self.testapp.get(
            '/course/modules/embed/v1/resource/not_in_registry/1',
            expect_errors=True)

        self.assertEquals(404, response.status_code)
        self.assertLogContains('No embed found for kind: not_in_registry')

    def test_get_returns_404_if_kind_or_id_or_name_missing(self):
        response = self.testapp.get(
            '/course/modules/embed/v1/resource/malformed',
            expect_errors=True)

        self.assertEquals(404, response.status_code)
        self.assertLogContains(
            'Request malformed; kind: None, id_or_name: None')


class EmbedSnippetTest(actions.TestBase):

    def tearDown(self):
        embed.Registry._bindings = {}
        super(EmbedSnippetTest, self).tearDown()

    def _get_fake_handler(self, slug='/the_course'):
        app_context = sites.ApplicationContext(
            'course', slug, None, None, None)
        request = FakeRequest('GET', 'https://www.example.com')
        return FakeHandler(app_context, request)

    def test_snippet_for_registered_embed(self):
        embed.Registry.bind('fragment', embed.AbstractEmbed)
        handler = self._get_fake_handler()
        key = 'fake_key'
        self.assertEquals(
            '<script src="https://www.example.com/modules/embed/v1/embed.js">'
            '</script>\n'
            '<cb-embed src="https://www.example.com/the_course/modules/embed'
            '/v1/resource/fragment/fake_key"></cb-embed>',
            embed.AbstractEmbed.get_embed_snippet(handler, key))

    def test_snippet_for_registered_embed_and_empty_namespace(self):
        embed.Registry.bind('fragment', embed.AbstractEmbed)
        handler = self._get_fake_handler(slug='/')
        key = 'fake_key'
        self.assertEquals(
            '<script src="https://www.example.com/modules/embed/v1/embed.js">'
            '</script>\n'
            '<cb-embed src="https://www.example.com/modules/embed'
            '/v1/resource/fragment/fake_key"></cb-embed>',
            embed.AbstractEmbed.get_embed_snippet(handler, key))

    def test_snippet_for_non_registered_embed(self):
        handler = self._get_fake_handler()
        key = 'fake_key'
        with self.assertRaises(AssertionError):
            embed.AbstractEmbed.get_embed_snippet(handler, key)


class FinishAuthHandlerTest(actions.TestBase):

    def test_get_returns_200_with_contents(self):
        # Allow access to code under test. pylint: disable=protected-access
        response = self.testapp.get(embed._FINISH_AUTH_URL)

        self.assertEquals(200, response.status_code)
        self.assertTrue(len(response.body))


class JsHandlersTest(actions.TestBase):

    def assert_caching_disabled(self, response):
        self.assertEquals(
            'no-cache, no-store, must-revalidate',
            response.headers['Cache-Control'])
        self.assertEquals('0', response.headers['Expires'])
        self.assertEquals('no-cache', response.headers['Pragma'])

    def assert_javascript_content_type(self, response):
        self.assertEquals(
            'text/javascript; charset=utf-8', response.headers['Content-Type'])

    def assert_successful_response(self, response):
        self.assertEquals(200, response.status_code)
        self.assertTrue(len(response.body))

    def assert_successful_js_response_with_caching_disabled(self, response):
        self.assert_successful_response(response)
        self.assert_caching_disabled(response)
        self.assert_javascript_content_type(response)

    def test_embed_child_js_returns_js_with_caching_disabled(self):
        # Allow access to code under test. pylint: disable=protected-access
        self.assert_successful_js_response_with_caching_disabled(
            self.testapp.get(embed._EMBED_CHILD_JS_URL))

    def test_embed_js_returns_js_with_caching_disabled(self):
        # Allow access to code under test. pylint: disable=protected-access
        self.assert_successful_js_response_with_caching_disabled(
            self.testapp.get(embed._EMBED_JS_URL))

    def test_embed_lib_js_returns_js_with_caching_disabled(self):
        # Allow access to code under test. pylint: disable=protected-access
        self.assert_successful_js_response_with_caching_disabled(
            self.testapp.get(embed._EMBED_LIB_JS_URL))


class RegistryTest(actions.TestBase):

    def setUp(self):
        super(RegistryTest, self).setUp()
        # Allow access to code under test. pylint: disable=protected-access
        self.old_bindings = dict(embed.Registry._bindings)

    def tearDown(self):
        # Allow access to code under test. pylint: disable=protected-access
        embed.Registry._bindings = self.old_bindings
        super(RegistryTest, self).tearDown()

    def test_bind_raises_value_error_if_fragment_already_bound(self):
        embed.Registry.bind('fragment', embed.AbstractEmbed)

        with self.assertRaisesRegexp(
                ValueError,
                'Kind fragment is already bound to .*AbstractEmbed'):
            embed.Registry.bind('fragment', embed.AbstractEmbed)

    def test_get_returns_embed_class_if_match(self):
        embed.Registry.bind('fragment', embed.AbstractEmbed)

        self.assertIs(embed.AbstractEmbed, embed.Registry.get('fragment'))

    def test_get_returns_none_if_no_match(self):
        self.assertIsNone(embed.Registry.get('no_match'))

    def test_get_kind_returns_kind_of_registered_embed(self):
        embed.Registry.bind('fragment', embed.AbstractEmbed)
        self.assertEquals(
            'fragment', embed.Registry.get_kind(embed.AbstractEmbed))

    def test_get_kind_returns_none_if_no_match(self):
        self.assertIsNone(embed.Registry.get_kind(embed.AbstractEmbed))


class StaticResourcesTest(actions.TestBase):

    def test_get_returns_successful_response_with_correct_headers(self):
        # Allow access to code under test. pylint: disable=protected-access
        response = self.testapp.get(embed._EMBED_CSS_URL)

        self.assertEquals(200, response.status_code)
        self.assertEquals('text/css', response.headers['Content-Type'])
        self.assertTrue(len(response.body))


class UrlParserTest(actions.TestBase):

    def test_get_kind_returns_none_if_no_suffix(self):
        no_suffix = 'http://example.com/namespace/modules/embed/v1/resource'
        self.assertIsNone(embed.UrlParser.get_kind(no_suffix))

        no_suffix = 'http://example.com/namespace/modules/embed/v1/resource/'
        self.assertIsNone(embed.UrlParser.get_kind(no_suffix))

    def test_get_kind_returns_none_if_suffix_malformed(self):
        one_arg = (
            'http://example.com/namespace/modules/embed/v1/resource/malformed')
        self.assertIsNone(embed.UrlParser.get_kind(one_arg))

        one_arg_with_spaces = (
            'http://example.com/namespace/modules/embed/v1/'
            'resource/ malformed ')
        self.assertIsNone(embed.UrlParser.get_kind(one_arg_with_spaces))

    def test_get_kind_returns_value_if_url_missing_namespace(self):
        global_url = 'http://example.com/modules/embed/v1/resource/kind/id'
        self.assertEquals('kind', embed.UrlParser.get_kind(global_url))

    def test_get_kind_returns_none_if_url_missing_parts(self):
        no_protocol = 'example.com/namespace/modules/embed/v1/resource/kind/id'
        self.assertIsNone(embed.UrlParser.get_kind(no_protocol))

    def test_get_kind_returns_none_if_url_relative(self):
        relative = '/namespace/modules/embed/v1/resource/kind/id'
        self.assertIsNone(embed.UrlParser.get_kind(relative))

    def test_get_kind_returns_value_and_strips_spaces(self):
        url = (
            'http://example.com/namespace/modules/embed/v1/resource/ kind /'
            'id_or_name')
        self.assertEquals('kind', embed.UrlParser.get_kind(url))

    def test_get_id_or_name_returns_none_if_no_suffix(self):
        no_suffix = 'http://example.com/namespace/modules/embed/v1/resource'
        self.assertIsNone(embed.UrlParser.get_id_or_name(no_suffix))

        no_suffix = 'http://example.com/namespace/modules/embed/v1/resource/'
        self.assertIsNone(embed.UrlParser.get_id_or_name(no_suffix))

    def test_get_id_or_name_returns_none_if_suffix_malformed(self):
        one_arg = (
            'http://example.com/namespace/modules/embed/v1/resource/malformed')
        self.assertIsNone(embed.UrlParser.get_id_or_name(one_arg))

        one_arg_with_spaces = (
            'http://example.com/namespace/modules/embed/v1/'
            'resource/ malformed ')
        self.assertIsNone(embed.UrlParser.get_id_or_name(one_arg_with_spaces))

    def test_get_id_or_name_returns_value_if_url_missing_namespace(self):
        global_url = 'http://example.com/modules/embed/v1/resource/kind/id'
        self.assertEquals('id', embed.UrlParser.get_id_or_name(global_url))

    def test_get_id_or_name_returns_none_if_url_missing_parts(self):
        no_protocol = 'example.com/namespace/modules/embed/v1/resource/kind/id'
        self.assertIsNone(embed.UrlParser.get_id_or_name(no_protocol))

    def test_get_id_or_name_returns_none_if_url_relative(self):
        relative = '/namespace/modules/embed/v1/resource/kind/id'
        self.assertIsNone(embed.UrlParser.get_id_or_name(relative))

    def test_get_id_or_name_returns_value_and_strips_spaces(self):
        url = (
            'http://example.com/namespace/modules/embed/v1/resource/kind/'
            ' id_or_name ')
        self.assertEquals('id_or_name', embed.UrlParser.get_id_or_name(url))


class EnsureSessionTests(actions.TestBase):

    def test_ensure_session_requires_continue_parameter(self):
        response = self.get(
            '/modules/embed/v1/ensure_session', expect_errors=True)
        self.assertEquals(400, response.status_int)

        response = self.get(
            '/modules/embed/v1/ensure_session'
            '?continue=http%3A%2F%2Fx20example.com/foo/html')
        self.assertEquals(302, response.status_int)
