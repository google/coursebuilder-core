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
from models import config
from models import models
from modules.embed import embed

from tests.functional import actions


class FakeHandler(object):

    def __init__(self, request):
        self.request = request


class FakeRequest(object):
    def __init__(self, method):
        self.method = method


# TODO(johncox): remove after security audit of embed module.
class TestBase(actions.TestBase):

    def setUp(self):
        super(TestBase, self).setUp()
        self.old_module_handlers_enabled = embed._MODULE_HANDLERS_ENABLED.value
        config.Registry.test_overrides[
            embed._MODULE_HANDLERS_ENABLED.name] = True

    def tearDown(self):
        config.Registry.test_overrides[embed._MODULE_HANDLERS_ENABLED.name] = (
            self.old_module_handlers_enabled)
        super(TestBase, self).tearDown()


class DemoHandlerTestBase(TestBase):

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

    _HANDLER = embed._DemoHandler
    _URL = embed._DEMO_URL

    def test_get_returns_200_with_contents_in_dev(self):
        self.assert_get_returns_200_with_contents_in_dev()

    def test_get_returns_404_in_prod(self):
        self.assert_get_returns_404_in_prod()


class GlobalErrorsDemoHandlerTest(DemoHandlerTestBase):

    _HANDLER = embed._GlobalErrorsDemoHandler
    _URL = embed._GLOBAL_ERRORS_DEMO_URL

    def test_get_returns_200_with_contents_in_dev(self):
        self.assert_get_returns_200_with_contents_in_dev()

    def test_get_returns_404_in_prod(self):
        self.assert_get_returns_404_in_prod()


class LocalErrorsDemoHandlerTest(DemoHandlerTestBase):

    _HANDLER = embed._LocalErrorsDemoHandler
    _URL = embed._LOCAL_ERRORS_DEMO_URL

    def test_get_returns_200_with_contents_in_dev(self):
        self.assert_get_returns_200_with_contents_in_dev()

    def test_get_returns_404_in_prod(self):
        self.assert_get_returns_404_in_prod()


class ExampleEmbedAndHandlerV1Test(TestBase):

    def setUp(self):
        super(ExampleEmbedAndHandlerV1Test, self).setUp()
        self.admin_email = 'admin@example.com'
        actions.login(self.admin_email, is_admin=True)
        actions.simple_add_course('course', self.admin_email, 'Course')
        self.user = users.get_current_user()

    def assert_current_user_enrolled(self):
        self.assertTrue(bool(self.get_student_for_current_user()))

    def assert_current_user_not_enrolled(self):
        self.assertFalse(bool(self.get_student_for_current_user()))

    def get_student_for_current_user(self):
        user = users.get_current_user()
        assert user

        with utils.Namespace('ns_course'):
            return models.Student.get_enrolled_student_by_user(user)

    def test_get_returns_302_to_200_with_good_payload_and_enrolls_student(self):
        self.assert_current_user_not_enrolled()

        redirect = self.testapp.get(
            '/course/modules/embed/v1/resource/example/1')
        redirect_url = redirect.headers.get('Location')

        self.assertEquals(302, redirect.status_code)
        self.assertTrue(redirect_url)
        self.assert_current_user_enrolled()

        response = self.testapp.get(redirect_url)

        self.assertEquals(200, response.status_code)
        # Required for frame resizing.
        self.assertIn(embed._EMBED_CHILD_JS_URL, response.body)
        # An email means the user is in session.
        self.assertIn(self.admin_email, response.body)
        # Data about the type and identifier of the embed instance.
        self.assertIn('<strong>example</strong>', response.body)
        self.assertIn('<strong>1</strong>', response.body)
        # The course title means app context is visible to the embed handler.
        self.assertIn('<strong>Course</strong>', response.body)

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


class FinishAuthHandlerTest(TestBase):

    def test_get_returns_200_with_contents(self):
        response = self.testapp.get(embed._FINISH_AUTH_URL)

        self.assertEquals(200, response.status_code)
        self.assertTrue(len(response.body))


class JsHandlersTest(TestBase):

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
        self.assert_successful_js_response_with_caching_disabled(
            self.testapp.get(embed._EMBED_CHILD_JS_URL))

    def test_embed_js_returns_js_with_caching_disabled(self):
        self.assert_successful_js_response_with_caching_disabled(
            self.testapp.get(embed._EMBED_JS_URL))

    def test_embed_lib_js_returns_js_with_caching_disabled(self):
        self.assert_successful_js_response_with_caching_disabled(
            self.testapp.get(embed._EMBED_LIB_JS_URL))


class RegistryTest(TestBase):

    def setUp(self):
        super(RegistryTest, self).setUp()
        self.old_bindings = dict(embed.Registry._bindings)

    def tearDown(self):
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


class StaticResourcesTest(TestBase):

    def test_get_returns_successful_response_with_correct_headers(self):
        response = self.testapp.get(embed._EMBED_CSS_URL)

        self.assertEquals(200, response.status_code)
        self.assertEquals('text/css', response.headers['Content-Type'])
        self.assertTrue(len(response.body))


class UrlParserTest(TestBase):

    def test_get_kind_returns_none_if_no_suffix(self):
        no_suffix = 'http://example.com/namespace/modules/embed/v1/resource'
        self.assertIsNone(embed.UrlParser.get_kind(no_suffix))

        no_suffix = 'http://example.com/namespace/modules/embed/v1/resource/'
        self.assertIsNone(embed.UrlParser.get_kind(no_suffix))

    def test_get_kind_returns_none_if_suffix_malformed(self):
        one_arg = (
            'http://example.com/namespace/modules/embed/resource/v1/malformed')
        self.assertIsNone(embed.UrlParser.get_kind(one_arg))

        one_arg_with_spaces = (
            'http://example.com/namespace/modules/embed/v1/'
            'resource/ malformed ')
        self.assertIsNone(embed.UrlParser.get_kind(one_arg_with_spaces))

    def test_get_kind_returns_none_if_url_missing_namespace(self):
        global_url = 'http://example.com/modules/embed/resource/v1/kind/id'
        self.assertIsNone(embed.UrlParser.get_kind(global_url))

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

    def test_get_id_or_name_returns_none_if_url_missing_namespace(self):
        global_url = 'http://example.com/modules/embed/resource/v1/kind/id'
        self.assertIsNone(embed.UrlParser.get_id_or_name(global_url))

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


# TODO(johncox): remove after security audit of embed module.
class Handlers404ByDefaultTest(actions.TestBase):

    def assert_handlers_404(self, handlers, prefix=None):
        for url, _ in handlers:
            if prefix:
                url = '/%s%s' % (prefix, url)

            response = self.testapp.get(url, expect_errors=True)

            self.assertEquals(404, response.status_code)
            self.assertIn('HTTP status code: 404.', response.body)
            self.assertLogContains(
                'You must enable %s to fetch %s' % (
                    embed._MODULE_HANDLERS_ENABLED.name, url))

    def test_global_handlers_404(self):
        self.assert_handlers_404(embed._GLOBAL_HANDLERS)

    def test_namespaced_handlers_404(self):
        self.admin_email = 'admin@example.com'
        self.prefix = 'course'
        actions.login(self.admin_email, is_admin=True)
        actions.simple_add_course(self.prefix, self.admin_email, 'Course')

        self.assert_handlers_404(embed._NAMESPACED_HANDLERS, prefix=self.prefix)
