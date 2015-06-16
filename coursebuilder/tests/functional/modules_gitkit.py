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

"""Functional tests from the GITKit federated authentication module."""

__author__ = [
    'johncox@google.com (John Cox)',
]

import copy

from common import users
from models import config
from models import models
from models import transforms
from modules.gitkit import gitkit
from tests.functional import actions

import appengine_config

from google.appengine.ext import db
from identitytoolkit import gitkitclient
from webapp2_extras import securecookie

# Allow access to code under test. pylint: disable=protected-access


class _GitkitFake(object):

    def __init__(self, value):
        self.value = value

    def VerifyGitkitToken(self, unused_token):
        if isinstance(self.value, Exception):
            raise self.value
        else:
            return self.value


class _Environment(object):
    """Context for overriding config properties."""

    def __init__(self, config_yaml, props_dict, service=None):
        self.config_yaml = config_yaml
        self.old_config_yaml = copy.deepcopy(gitkit.Runtime._CONFIG_YAML)
        self.old_props = None
        self.old_make_gitkit_service = gitkit._make_gitkit_service
        self.props_dict = props_dict
        self.service = service

    def __enter__(self):
        gitkit.Runtime._CONFIG_YAML = self.config_yaml
        self.old_props = dict(config.Registry.test_overrides)

        for name, value in self.props_dict.iteritems():
            config.Registry.test_overrides[name] = value

        if self.service:
            gitkit._make_gitkit_service = (
                lambda *unused_args, **unused_kwargs: self.service)

        return self

    def __exit__(self, *unused_exception_info):
        gitkit.Runtime._CONFIG_YAML = self.old_config_yaml
        config.Registry.test_overrides = self.old_props
        gitkit._make_gitkit_service = self.old_make_gitkit_service


class _TestBase(actions.TestBase):

    # Because the module system doesn't actually call notify_module_disabled,
    # we enable and disable the users service in our tests. We also create our
    # own WSGIApplication because otherwise our endpoints would not be
    # registered and reachable.

    def getApp(self):
        return users.AuthInterceptorWSGIApplication(
            gitkit.GLOBAL_HANDLERS + gitkit.NAMESPACED_HANDLERS)

    def setUp(self):
        super(_TestBase, self).setUp()
        self.browser_api_key = 'browser_api_key_value'
        self.client_id = 'client_id_value'
        self.email = 'test@example.com'
        self.host = 'localhost:80'
        self.photo_url = 'http://photo'
        self.provider_id = 'provider_id_value'
        self.old_users_service = users.UsersServiceManager.get()
        self.scheme = 'http'
        self.serializer = securecookie.SecureCookieSerializer('notasecret')
        self.server_api_key = 'server_api_key_value'
        self.service_account_email = 'service.account@email.value'
        self.service_account_key = 'service_account_key_value'
        self.title = 'title_value'
        self.user_id = '1234'

        self.gitkit_user = gitkitclient.GitkitUser(
            email=self.email, photo_url=self.photo_url,
            provider_id=self.provider_id, user_id=self.user_id)

        self.admins = ['first@example.com', 'second@example.com']
        self.enabled = False
        self.config_yaml = {
            gitkit._CONFIG_YAML_ADMINS_NAME: self.admins,
            gitkit._CONFIG_YAML_ENABLED_NAME: self.enabled,
        }

        self.properties = self._get_properties(
            self.browser_api_key, self.client_id, self.server_api_key,
            self.service_account_email, self.service_account_key, self.title,
        )
        users.UsersServiceManager.set(gitkit.UsersService)

    def tearDown(self):
        users.UsersServiceManager.set(self.old_users_service)
        super(_TestBase, self).tearDown()

    def assert_redirect_to(self, expected, url, params):
        service = self._get_gitkit_service(self.gitkit_user)
        headers = self._make_token_headers('token')

        with _Environment(self.config_yaml, self.properties, service=service):
            response = self.testapp.get(url, headers=headers, params=params)

            self.assertEquals(302, response.status_code)
            self.assertEquals(expected, response.location)

    def assert_response_contains(self, response, code, text):
        self.assertEquals(code, response.status_code)
        self.assertIn(text, response.body)

    def _get_properties(
            self, browser_api_key, client_id, server_api_key,
            service_account_email, service_account_key, title):
        return {
            gitkit._BROWSER_API_KEY.name: browser_api_key,
            gitkit._CLIENT_ID.name: client_id,
            gitkit._SERVER_API_KEY.name: server_api_key,
            gitkit._SERVICE_ACCOUNT_JSON.name: transforms.dumps({
                gitkit._SERVICE_ACCOUNT_EMAIL_NAME: service_account_email,
                gitkit._SERVICE_ACCOUNT_KEY_NAME: service_account_key,
            }),
            gitkit._TITLE.name: title,
        }

    def _get_gitkit_service(self, value):
        service = gitkit.GitkitService(None, None, None, None, None)
        service._instance = _GitkitFake(value)
        return service

    def _make_token_headers(self, value):
        # The value is garbage, but we can't validate it anyway in tests unless
        # we're issuing wire ops with real keys/secrets.
        return {
            'Cookie': '%s=%s' % (
                gitkit._GITKIT_TOKEN_COOKIE_NAME,
                self.serializer.serialize(
                    gitkit._GITKIT_TOKEN_COOKIE_NAME, value)),
        }


class AccountChooserCustomizationHandlersTest(_TestBase):

    def assert_content_type_equals(self, expected, response):
        self.assertEquals(expected, response.headers['Content-Type'])

    def assert_cors_header_set(self, response):
        self.assertEquals(
            'https://www.accountchooser.com',
            response.headers['Access-Control-Allow-Origin'])

    def test_branding_handler(self):
        response = self.testapp.get(gitkit._BRANDING_URL)

        self.assertEquals(200, response.status_code)
        self.assert_cors_header_set(response)
        self.assertIn('Pick an account to continue', response.body)

    def test_favicon_handler(self):
        response = self.testapp.get(gitkit._FAVICON_URL)

        self.assertEquals(200, response.status_code)
        self.assert_cors_header_set(response)
        self.assert_content_type_equals('image/x-icon', response)
        self.assertTrue(len(response.body) > 0)


class EmailMappingTest(_TestBase):

    def setUp(self):
        super(EmailMappingTest, self).setUp()
        self.new_email = 'new_user@example.tld'

    def assert_key_values_correct(self, key, name):
        self.assertEquals(
            appengine_config.DEFAULT_NAMESPACE_NAME, key.namespace())
        self.assertEquals(gitkit.EmailMapping.kind(), key.kind())
        self.assertEquals(name, key.name())

    def test_create_or_update_creates_new_mapping(self):
        self.assertIsNone(gitkit.EmailMapping.all().get())

        key, caused_write = gitkit.EmailMapping.create_or_update(
            self.email, self.user_id)
        entity = db.get(key)

        self.assertTrue(caused_write)
        self.assertEquals(self.email, entity.email)
        self.assertEquals(self.user_id, entity.key().name())

    def test_create_or_update_with_unchanged_mapping(self):
        gitkit.EmailMapping.create_or_update(self.email, self.user_id)
        key, caused_write = gitkit.EmailMapping.create_or_update(
            self.email, self.user_id)

        entities = gitkit.EmailMapping.all().fetch(2)
        entity = entities[0]

        self.assertFalse(caused_write)
        self.assertEquals(1, len(entities))
        self.assertEquals(self.email, entity.email)
        self.assertEquals(self.user_id, entity.key().name())

    def test_create_or_update_updates_existing_mapping(self):
        gitkit.EmailMapping.create_or_update(self.email, self.user_id)
        key, caused_write = gitkit.EmailMapping.create_or_update(
            self.new_email, self.user_id)

        entities = gitkit.EmailMapping.all().fetch(2)
        entity = entities[0]

        self.assertTrue(caused_write)
        self.assertEquals(1, len(entities))
        self.assertEquals(self.new_email, entity.email)
        self.assertEquals(self.user_id, entity.key().name())

    def test_get_by_user_id(self):
        gitkit.EmailMapping.create_or_update(self.email, self.user_id)
        entity = gitkit.EmailMapping.get_by_user_id(self.user_id)
        self.assertEquals(self.email, entity.email)
        self.assertEquals(self.user_id, entity.key().name())

    def test_key(self):
        key, _ = gitkit.EmailMapping.create_or_update(self.email, self.user_id)

        self.assert_key_values_correct(key, self.user_id)

    def test_safe_key(self):
        key, _ = gitkit.EmailMapping.create_or_update(self.email, self.user_id)
        transform_fn = lambda unsafe_key: 'transformed_%s' % unsafe_key
        safe_key = gitkit.EmailMapping.safe_key(key, transform_fn)

        self.assert_key_values_correct(safe_key, 'transformed_1234')


class GitkitServiceTest(_TestBase):

    def test_get_provider_id_raises_runtime_error_if_misconfigured(self):
        service = self._get_gitkit_service(
            NotImplementedError(gitkit._BAD_CRYPTO_NEEDLE))

        with self.assertRaisesRegexp(
                RuntimeError, 'Please check your configuration values'):
            service.get_provider_id('token')

    def test_get_provider_id_succeeds(self):
        service = self._get_gitkit_service(self.gitkit_user)

        self.assertEquals(self.provider_id, service.get_provider_id('token'))

    def test_get_user_raises_runtime_error_if_misconfigured(self):
        service = self._get_gitkit_service(
            NotImplementedError(gitkit._BAD_CRYPTO_NEEDLE))

        with self.assertRaisesRegexp(
                RuntimeError, 'Please check your configuration values'):
            service.get_user('token')

    def test_get_user_succeeds(self):
        service = self._get_gitkit_service(self.gitkit_user)
        user = service.get_user('token')

        self.assertTrue(isinstance(user, users.User))
        self.assertEquals(self.email, user.email())
        self.assertEquals(self.user_id, user.user_id())

    def test_instances_use_common_cache_by_default(self):
        service1 = gitkit.GitkitService(
            'client_id', 'server_api_key', 'service@account.email',
            'service_account_key', 'widget_url')
        service2 = gitkit.GitkitService(
            'client_id', 'server_api_key', 'service@account.email',
            'service_account_key', 'widget_url')
        self.assertIs(
            service1._instance.rpc_helper.http.cache,
            service2._instance.rpc_helper.http.cache)


class SignInContinueHandlerTest(_TestBase):

    def tests_redirects_to_dest_url(self):
        self.assert_redirect_to(
            'http://localhost/foo',
            gitkit._SIGN_IN_CONTINUE_URL, {gitkit._DEST_URL_NAME: '/foo'})

    def test_redirects_to_slash_if_no_dest_url(self):
        self.assert_redirect_to(
            'http://localhost/', gitkit._SIGN_IN_CONTINUE_URL, {})

    def test_redirects_to_unescaped_absolute_dest_url(self):
        self.assert_redirect_to(
            'http://foo/bar baz', gitkit._SIGN_IN_CONTINUE_URL,
            {gitkit._DEST_URL_NAME: 'http://foo/bar baz'})

    def test_redirects_to_unescaped_dest_url(self):
        self.assert_redirect_to(
            'http://localhost/foo bar',
            gitkit._SIGN_IN_CONTINUE_URL, {gitkit._DEST_URL_NAME: '/foo bar'})


class SignInHandlerTest(_TestBase):

    def test_redirects_to_continue_with_dest_url(self):
        self.assert_redirect_to(
            'http://localhost/modules/gitkit/signin/continue?dest_url=%2Ffoo',
            gitkit._SIGN_IN_URL, {gitkit._GITKIT_DEST_URL_NAME: '/foo'})

    def test_redirects_to_continue_with_escaped_dest_url(self):
        self.assert_redirect_to(
            ('http://localhost/modules/gitkit/signin/continue?'
             'dest_url=%2Ffoo+bar'),
            gitkit._SIGN_IN_URL, {gitkit._GITKIT_DEST_URL_NAME: '/foo bar'})

    def test_redirects_to_continue_with_escaped_absolute_dest_url(self):
        self.assert_redirect_to(
            ('http://localhost/modules/gitkit/signin/continue?'
             'dest_url=http%3A%2F%2Ffoo'),
            gitkit._SIGN_IN_URL, {gitkit._GITKIT_DEST_URL_NAME: 'http://foo'})

    def test_redirects_to_continue_with_no_dest_url(self):
        self.assert_redirect_to(
            'http://localhost/modules/gitkit/signin/continue',
            gitkit._SIGN_IN_URL, {})

    def test_returns_302_and_creates_mapping_if_no_student(self):
        service = self._get_gitkit_service(self.gitkit_user)
        headers = self._make_token_headers('token')

        # When there's no student, the mapping can still be updated, causing an
        # event to fire. Since there was no previous value, the event's 'from'
        # field is empty.
        with _Environment(self.config_yaml, self.properties, service=service):
            response = self.testapp.get(gitkit._SIGN_IN_URL, headers=headers)
            event = models.EventEntity.all().get()
            mapping = gitkit.EmailMapping.all().get()

            self.assertEquals(self.email, mapping.email)
            self.assertEquals(
                transforms.dumps({'from': None, 'to': self.email}), event.data)

            self.assertEquals(302, response.status_code)
            self.assertTrue(
                response.location.endswith(gitkit._SIGN_IN_CONTINUE_URL))

    def tests_returns_302_if_student_with_same_email(self):
        service = self._get_gitkit_service(self.gitkit_user)
        headers = self._make_token_headers('token')
        models.Student(
            key_name=self.user_id, email=self.email, user_id=self.user_id).put()
        gitkit.EmailMapping.create_or_update(self.email, self.user_id)

        # When there's a student but no email change, no event fires. Check to
        # see the mapping still has the same value.
        with _Environment(self.config_yaml, self.properties, service=service):
            response = self.testapp.get(gitkit._SIGN_IN_URL, headers=headers)
            mapping = gitkit.EmailMapping.all().get()

            self.assertIsNone(models.EventEntity.all().get())
            self.assertEquals(self.email, mapping.email)

            self.assertEquals(302, response.status_code)
            self.assertTrue(
                response.location.endswith(gitkit._SIGN_IN_CONTINUE_URL))

    def tests_returns_302_and_updates_if_student_email_changed(self):
        service = self._get_gitkit_service(self.gitkit_user)
        headers = self._make_token_headers('token')
        old_email = 'old_' + self.email
        models.Student(
            key_name=self.user_id, email=old_email, user_id=self.user_id).put()
        gitkit.EmailMapping.create_or_update(old_email, self.user_id)

        # When there's a student with a different email in the mapping, a change
        # event fires with the old and new values.
        with _Environment(self.config_yaml, self.properties, service=service):
            response = self.testapp.get(gitkit._SIGN_IN_URL, headers=headers)
            event = models.EventEntity.all().get()
            mapping = gitkit.EmailMapping.all().get()

            self.assertEquals(self.email, mapping.email)
            self.assertEquals(
                transforms.dumps({
                    'from': 'old_' + self.email,
                    'to': self.email,
                }), event.data)

            self.assertEquals(302, response.status_code)
            self.assertTrue(
                response.location.endswith(gitkit._SIGN_IN_CONTINUE_URL))

    def test_returns_400_if_token_invalid(self):
        service = self._get_gitkit_service(None)
        headers = self._make_token_headers('token_value')

        with _Environment(self.config_yaml, self.properties, service=service):
            response = self.testapp.get(
                gitkit._SIGN_IN_URL, expect_errors=True, headers=headers)

            self.assertEquals(400, response.status_code)
            self.assertLogContains('invalid token')

    def test_returns_400_if_token_missing(self):

        with _Environment(self.config_yaml, self.properties):
            response = self.testapp.get(gitkit._SIGN_IN_URL, expect_errors=True)

            self.assertEquals(400, response.status_code)
            self.assertLogContains(
                gitkit._GITKIT_TOKEN_COOKIE_NAME + ' not found')

    def test_returns_500_if_error_communicating_with_gitkit(self):
        service = self._get_gitkit_service(Exception('details'))
        headers = self._make_token_headers('token_value')

        with _Environment(self.config_yaml, self.properties, service=service):
            response = self.testapp.get(
                gitkit._SIGN_IN_URL, expect_errors=True, headers=headers)

            self.assertEquals(500, response.status_code)
            self.assertLogContains('Error communicating with GITKit: details')

    def test_returns_500_if_runtime_config_invalid(self):
        self.config_yaml.pop(gitkit._CONFIG_YAML_ADMINS_NAME)

        with _Environment(self.config_yaml, self.properties):
            response = self.testapp.get(gitkit._SIGN_IN_URL, expect_errors=True)

            self.assertEquals(500, response.status_code)
            self.assertLogContains('GITKit integration misconfigured')


class RuntimeAndRuntimeConfigTest(_TestBase):

    def setUp(self):
        super(RuntimeAndRuntimeConfigTest, self).setUp()
        self.old_config_yaml_path = gitkit._CONFIG_YAML_PATH

    def tearDown(self):
        gitkit._CONFIG_YAML_PATH = self.old_config_yaml_path
        super(RuntimeAndRuntimeConfigTest, self).tearDown()

    def test_validate_raises_runtime_error_if_admin_invalid(self):
        self.config_yaml[gitkit._CONFIG_YAML_ADMINS_NAME] = 'invalid'

        with self.assertRaisesRegexp(
                RuntimeError,
                '%s missing or invalid' % gitkit._CONFIG_YAML_ADMINS_NAME):
            with _Environment(self.config_yaml, self.properties):
                gitkit.Runtime.get_runtime_config(
                    self.host, self.scheme,
                ).validate()

    def test_validate_raises_runtime_error_if_admin_missing(self):
        self.config_yaml.pop(gitkit._CONFIG_YAML_ADMINS_NAME)

        with self.assertRaisesRegexp(
                RuntimeError,
                '%s missing or invalid' % gitkit._CONFIG_YAML_ADMINS_NAME):
            with _Environment(self.config_yaml, self.properties):
                gitkit.Runtime.get_runtime_config(
                    self.host, self.scheme,
                ).validate()

    def test_validate_raises_runtime_error_if_browser_api_key_not_set(self):
        self.properties.pop(gitkit._BROWSER_API_KEY.name)

        with self.assertRaisesRegexp(
                RuntimeError, gitkit._BROWSER_API_KEY.name + ' not set'):
            with _Environment(self.config_yaml, self.properties):
                gitkit.Runtime.get_runtime_config(
                    self.host, self.scheme,
                ).validate()

    def test_validate_raises_runtime_error_if_client_id_not_set(self):
        self.properties.pop(gitkit._CLIENT_ID.name)

        with self.assertRaisesRegexp(
                RuntimeError, gitkit._CLIENT_ID.name + ' not set'):
            with _Environment(self.config_yaml, self.properties):
                gitkit.Runtime.get_runtime_config(
                    self.host, self.scheme,
                ).validate()

    def test_validate_raises_runtime_error_if_config_yaml_unreadable(self):
        gitkit._CONFIG_YAML_PATH = 'unreadable_' + gitkit._CONFIG_YAML_PATH

        with self.assertRaisesRegexp(
                RuntimeError,
                gitkit._CONFIG_YAML_ADMINS_NAME + ' missing or invalid'):
            with _Environment(None, self.properties):
                runtime_config = gitkit.Runtime.get_runtime_config(
                    self.host, self.scheme)
                runtime_config.validate()

        self.assertLogContains(
            gitkit._CONFIG_YAML_PATH + ' missing or malformed')

    def test_validate_raises_runtime_error_if_enabled_invalid(self):
        self.config_yaml[gitkit._CONFIG_YAML_ENABLED_NAME] = 'invalid'

        with self.assertRaisesRegexp(
                RuntimeError,
                '%s missing or invalid' % gitkit._CONFIG_YAML_ENABLED_NAME):
            with _Environment(self.config_yaml, self.properties):
                gitkit.Runtime.get_runtime_config(
                    self.host, self.scheme,
                ).validate()

    def test_validate_raises_runtime_error_if_enabled_missing(self):
        self.config_yaml.pop(gitkit._CONFIG_YAML_ENABLED_NAME)

        with self.assertRaisesRegexp(
                RuntimeError,
                '%s missing or invalid' % gitkit._CONFIG_YAML_ENABLED_NAME):
            with _Environment(self.config_yaml, self.properties):
                gitkit.Runtime.get_runtime_config(
                    self.host, self.scheme,
                ).validate()

    def test_validate_raises_runtime_error_if_server_api_key_not_set(self):
        self.properties.pop(gitkit._SERVER_API_KEY.name)

        with self.assertRaisesRegexp(
                RuntimeError, gitkit._SERVER_API_KEY.name + ' not set'):
            with _Environment(self.config_yaml, self.properties):
                gitkit.Runtime.get_runtime_config(
                    self.host, self.scheme,
                ).validate()

    def test_validate_raises_runtime_error_if_service_email_not_set(self):
        self.properties[gitkit._SERVICE_ACCOUNT_JSON.name] = transforms.dumps({
            gitkit._SERVICE_ACCOUNT_KEY_NAME: self.service_account_key,
        })

        with self.assertRaisesRegexp(
                RuntimeError,
                '%s not set in %s' % (
                    gitkit._SERVICE_ACCOUNT_EMAIL_NAME,
                    gitkit._SERVICE_ACCOUNT_JSON.name)):
            with _Environment(self.config_yaml, self.properties):
                gitkit.Runtime.get_runtime_config(
                    self.host, self.scheme,
                ).validate()

    def test_validate_raises_runtime_error_if_service_key_not_set(self):
        self.properties[gitkit._SERVICE_ACCOUNT_JSON.name] = transforms.dumps({
            gitkit._SERVICE_ACCOUNT_EMAIL_NAME: self.service_account_email,
        })

        with self.assertRaisesRegexp(
                RuntimeError,
                '%s not set in %s' % (
                    gitkit._SERVICE_ACCOUNT_KEY_NAME,
                    gitkit._SERVICE_ACCOUNT_JSON.name)):
            with _Environment(self.config_yaml, self.properties):
                gitkit.Runtime.get_runtime_config(
                    self.host, self.scheme,
                ).validate()

    def test_validate_raises_runtime_error_if_title_not_set(self):
        self.properties[gitkit._TITLE.name] = ''

        with self.assertRaisesRegexp(
                RuntimeError, '%s missing or invalid' % gitkit._TITLE.name):
            with _Environment(self.config_yaml, self.properties):
                gitkit.Runtime.get_runtime_config(
                    self.host, self.scheme
                ).validate()

    def test_validate_succeeds_and_runtime_config_has_expected_values(self):
        with _Environment(self.config_yaml, self.properties):
            runtime_config = gitkit.Runtime.get_runtime_config(
                self.host, self.scheme)
            runtime_config.validate()

            self.assertEquals(self.admins, runtime_config.admins)
            self.assertEquals(
                self.browser_api_key, runtime_config.browser_api_key)
            self.assertEquals(self.client_id, runtime_config.client_id)
            self.assertEquals(self.enabled, runtime_config.enabled)
            self.assertEquals(
                self.service_account_email,
                runtime_config.service_account_email)
            self.assertEquals(
                self.service_account_key, runtime_config.service_account_key)
            self.assertEquals(
                'http://localhost:80/modules/gitkit/signout',
                runtime_config.sign_out_url)
            self.assertEquals(
                'http://localhost:80/modules/gitkit/widget',
                runtime_config.widget_url)
            self.assertEquals(self.title, runtime_config.title)


class SignOutContinueHandlerTest(_TestBase):

    def tests_redirects_to_dest_url(self):
        self.assert_redirect_to(
            'http://localhost/foo',
            gitkit._SIGN_OUT_CONTINUE_URL, {gitkit._DEST_URL_NAME: '/foo'})

    def test_redirects_to_slash_if_no_dest_url(self):
        self.assert_redirect_to(
            'http://localhost/', gitkit._SIGN_OUT_CONTINUE_URL, {})

    def test_redirects_to_unescaped_absolute_dest_url(self):
        self.assert_redirect_to(
            'http://foo/bar baz', gitkit._SIGN_OUT_CONTINUE_URL,
            {gitkit._DEST_URL_NAME: 'http://foo/bar baz'})

    def test_redirects_to_unescaped_dest_url(self):
        self.assert_redirect_to(
            'http://localhost/foo bar',
            gitkit._SIGN_OUT_CONTINUE_URL, {gitkit._DEST_URL_NAME: '/foo bar'})

    def test_returns_500_if_user_still_authenticated(self):
        self.swap(gitkit.users, 'get_current_user', lambda: True)
        response = self.testapp.get(
            gitkit._SIGN_OUT_CONTINUE_URL, expect_errors=True)

        self.assertEquals(500, response.status_code)
        self.assertLogContains('User still in session after sign out; aborting')


class SignOutHandlerTest(_TestBase):

    def test_get_returns_500_if_runtime_config_validation_fails(self):
        response = self.testapp.get(gitkit._SIGN_OUT_URL, expect_errors=True)

        self.assert_response_contains(response, 500, '')

    def test_get_returns_page_with_expected_config_data(self):
        browser_api_key = 'browser_api_key'

        with _Environment(self.config_yaml, self.properties):
            response = self.testapp.get(gitkit._SIGN_OUT_URL)

            self.assert_response_contains(response, 200, browser_api_key)
            self.assert_response_contains(response, 200, gitkit._DEST_URL_NAME)


class StudentFederatedEmailTest(_TestBase):

    def setUp(self):
        super(StudentFederatedEmailTest, self).setUp()
        self.student = models.Student(user_id=self.user_id)

    def test_federated_resolver_returns_email_if_mapping(self):
        gitkit.EmailMapping.create_or_update(self.email, self.user_id)

        self.assertEquals(self.email, self.student.federated_email)

    def test_federated_resolver_returns_none_if_no_mapping(self):
        self.assertIsNone(self.student.federated_email)


class UsersServiceTest(_TestBase):

    def setUp(self):
        super(UsersServiceTest, self).setUp()
        self.old_runtime_config = gitkit.Runtime.get_current_runtime_config()
        self.old_token = gitkit.Runtime.get_current_token()
        self.runtime_config = gitkit.Runtime.get_runtime_config(
                self.host, self.scheme)

    def tearDown(self):
        gitkit.Runtime.set_current_runtime_config(self.old_runtime_config)
        gitkit.Runtime.set_current_token(self.old_token)
        super(UsersServiceTest, self).tearDown()

    def test_create_login_url_falls_back_to_gae_if_no_runtime_config(self):
        self.assertEquals(
            ('https://www.google.com/accounts/Login?'
             'continue=http%3A//localhost/'),
            users.create_login_url())

    def test_create_login_url_falls_back_to_gae_if_not_enabled(self):
        self.runtime_config.enabled = False
        gitkit.Runtime.set_current_runtime_config(self.runtime_config)
        gitkit.Runtime.set_current_token('token')

        self.assertEquals(
            ('https://www.google.com/accounts/Login?'
             'continue=http%3A//localhost/'),
            users.create_login_url())

    def test_create_login_url_no_dest_url(self):
        self.runtime_config.enabled = True
        gitkit.Runtime.set_current_runtime_config(self.runtime_config)

        self.assertEquals(
            'http://localhost:80/modules/gitkit/widget?mode=select',
            users.create_login_url())

    def test_create_login_url_with_dest_url(self):
        self.runtime_config.enabled = True
        gitkit.Runtime.set_current_runtime_config(self.runtime_config)

        self.assertEquals(
            ('http://localhost:80/modules/gitkit/widget?'
             'signInSuccessUrl=http%3A%2F%2Ffoo%3Fbar%3Db+az&mode=select'),
            users.create_login_url(dest_url='http://foo?bar=b az'))

    def test_create_logout_url_falls_back_to_gae_if_no_runtime_config(self):
        self.assertEquals(
            ('https://www.google.com/accounts/Logout?'
             'continue=http%3A//foo%3Fbar%3Db%20az'),
            users.create_logout_url('http://foo?bar=b az'))

    def test_create_logout_url_falls_back_to_gae_if_not_enabled(self):
        self.runtime_config.enabled = False
        gitkit.Runtime.set_current_runtime_config(self.runtime_config)

        self.assertEquals(
            ('https://www.google.com/accounts/Logout?'
             'continue=http%3A//foo%3Fbar%3Db%20az'),
            users.create_logout_url('http://foo?bar=b az'))

    def test_create_logout_url_with_dest_url(self):
        self.runtime_config.enabled = True
        gitkit.Runtime.set_current_runtime_config(self.runtime_config)

        self.assertEquals(
            ('/modules/gitkit/signout?'
             'dest_url=http%3A%2F%2Ffoo%3Fbar%3Db+az'),
            users.create_logout_url('http://foo?bar=b az'))

    def test_get_current_user_returns_gae_value_if_no_runtime_config(self):
        actions.login('gae_user@example.com')
        user = users.get_current_user()

        self.assertEquals('gae_user@example.com', user.email())

    def test_get_current_user_returns_gae_value_for_admins_when_disabled(self):
        # This tests that we return users who are in config yaml's admins list
        # when disabled is True. This is important because during the bootstrap
        # process (when disabled is True), we only want admin users to be able
        # to sign into the site.
        self.runtime_config.enabled = False
        self.runtime_config.admins = ['in_admin_list@example.com']
        gitkit.Runtime.set_current_runtime_config(self.runtime_config)

        actions.login('in_admin_list@example.com')
        user = users.get_current_user()

        self.assertEquals('in_admin_list@example.com', user.email())

        actions.login('not_in_admin_list@example.com')

        self.assertIsNone(users.get_current_user())
        self.assertLogContains('Disallowing get_current_user() for non-admin')

    def test_get_current_user_returns_gitkit_value_when_enabled(self):
        self.runtime_config.enabled = True
        gitkit.Runtime.set_current_runtime_config(self.runtime_config)
        gitkit.Runtime.set_current_token('token')
        service = self._get_gitkit_service(self.gitkit_user)
        self.swap(
            gitkit, '_make_gitkit_service', lambda *args, **kwargs: service)

        user = users.get_current_user()

        self.assertEquals(self.email, user.email())
        self.assertEquals(self.user_id, user.user_id())

    def test_get_current_user_returns_none_when_enabled_but_no_token(self):
        self.runtime_config.enabled = True
        gitkit.Runtime.set_current_runtime_config(self.runtime_config)
        service = self._get_gitkit_service(self.gitkit_user)
        self.swap(
            gitkit, '_make_gitkit_service', lambda *args, **kwargs: service)

        self.assertIsNone(users.get_current_user())

    def test_get_current_user_returns_none_if_enabled_and_no_user(self):
        self.runtime_config.enabled = True
        gitkit.Runtime.set_current_runtime_config(self.runtime_config)

        self.assertIsNone(users.get_current_user())

    def test_is_current_user_admin_falls_back_to_gae_if_no_runtime_config(self):
        actions.login('gae_user@example.com', is_admin=True)

        self.assertTrue(users.is_current_user_admin())

    def test_is_current_user_admin_falls_back_to_gae_if_not_enabled(self):
        actions.login('gae_user@example.com', is_admin=True)
        self.runtime_config.enabled = False
        gitkit.Runtime.set_current_runtime_config(self.runtime_config)

        self.assertTrue(users.is_current_user_admin())

    def test_is_current_user_admin_returns_false_if_user_not_in_list(self):
        actions.login('not_in_admin_list@example.com')
        self.runtime_config.enabled = True
        self.runtime_config.admins = []
        gitkit.Runtime.set_current_runtime_config(self.runtime_config)
        gitkit.Runtime.set_current_token('token')
        service = self._get_gitkit_service(self.gitkit_user)
        self.swap(
            gitkit, '_make_gitkit_service', lambda *args, **kwargs: service)

        self.assertFalse(users.is_current_user_admin())

    def test_is_current_user_admin_returns_true_if_user_in_list(self):
        actions.login(self.email)
        self.runtime_config.enabled = True
        self.runtime_config.admins = [self.email]
        gitkit.Runtime.set_current_runtime_config(self.runtime_config)
        gitkit.Runtime.set_current_token('token')
        service = self._get_gitkit_service(self.gitkit_user)
        self.swap(
            gitkit, '_make_gitkit_service', lambda *args, **kwargs: service)

        self.assertTrue(users.is_current_user_admin())


class WidgetHandlerTest(_TestBase):

    def test_get_returns_500_if_runtime_config_validation_fails(self):
        response = self.testapp.get(gitkit._WIDGET_URL, expect_errors=True)

        self.assert_response_contains(response, 500, '')

    def test_get_returns_page_with_expected_widget_config_data(self):
        browser_api_key = 'browser_api_key'
        expected_branding_url = 'http://localhost/modules/gitkit/branding'
        expected_favicon_url = 'http://localhost/modules/gitkit/favicon.ico'

        with _Environment(self.config_yaml, self.properties):
            response = self.testapp.get(gitkit._WIDGET_URL)

            self.assert_response_contains(response, 200, browser_api_key)
            self.assert_response_contains(response, 200, expected_branding_url)
            self.assert_response_contains(response, 200, gitkit._EMAIL_URL)
            self.assert_response_contains(response, 200, expected_favicon_url)
            self.assert_response_contains(response, 200, gitkit._SIGN_IN_URL)
            self.assert_response_contains(response, 200, gitkit._TITLE.value)
