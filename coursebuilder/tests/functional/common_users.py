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

"""Functional tests for common/users.py."""

__author__ = [
    'johncox@google.com (John Cox)',
]

from common import users
from tests.functional import actions

from google.appengine.api import users as gae_users


class AppEnginePassthroughUsersServiceTest(actions.TestBase):

    def setUp(self):
        super(AppEnginePassthroughUsersServiceTest, self).setUp()
        self.destination_url = 'http://destination'
        self.email = 'user@example.com'
        self.old_users_service = users.UsersServiceManager.get()
        users.UsersServiceManager.set(
            users.AppEnginePassthroughUsersService)

    def tearDown(self):
        users.UsersServiceManager.set(self.old_users_service)
        super(AppEnginePassthroughUsersServiceTest, self).tearDown()

    def assert_service_results_equal_and_not_none(
            self, users_result, gae_users_result):
        self.assertIsNotNone(users_result)
        self.assertIsNotNone(gae_users_result)
        self.assertEqual(users_result, gae_users_result)

    def test_create_login_url_delegates_to_gae_users_service(self):
        users_result = users.create_login_url(
            dest_url=self.destination_url, _auth_domain='is_ignored',
            federated_identity='federated_identity')
        gae_users_result = gae_users.create_login_url(
            dest_url=self.destination_url, _auth_domain='is_ignored',
            federated_identity='federated_identity')

        self.assert_service_results_equal_and_not_none(
            users_result, gae_users_result)

    def test_create_logout_url_delegates_to_gae_users_service(self):
        users_result = users.create_logout_url('destination')
        gae_users_result = gae_users.create_logout_url('destination')

        self.assert_service_results_equal_and_not_none(
            users_result, gae_users_result)

    def test_get_current_user_delegates_to_gae_users_service(self):
        actions.login(self.email)
        users_result = users.get_current_user()
        gae_users_result = gae_users.get_current_user()

        self.assert_service_results_equal_and_not_none(
            users_result, gae_users_result)

    def test_get_service_name(self):
        self.assertEqual(
            'common.users.AppEnginePassthroughUsersService',
            users.AppEnginePassthroughUsersService.get_service_name())

    def test_is_current_user_admin_delegates_to_gae_users_service(self):
        actions.login(self.email, is_admin=True)
        users_result = users.is_current_user_admin()
        gae_users_result = users.is_current_user_admin()

        self.assertTrue(users_result)
        self.assertTrue(gae_users_result)


class PublicExceptionsAndClassesIdentityTests(actions.TestBase):

    def assert_all_is(self, expected_list, actual):
        for expected in expected_list:
            self.assertIs(expected, actual)

    def test_users_classes_are_app_engine_users_classes(self):
        self.assert_all_is([users.User, users._User], gae_users.User)

    def test_users_exceptions_are_app_engine_users_exceptions(self):
        self.assert_all_is([users.Error, users._Error], gae_users.Error)
        self.assert_all_is(
            [users.NotAllowedError, users._NotAllowedError],
            gae_users.NotAllowedError)
        self.assert_all_is(
            [users.RedirectTooLongError, users._RedirectTooLongError],
            gae_users.RedirectTooLongError)
        self.assert_all_is(
            [users.UserNotFoundError, users._UserNotFoundError],
            gae_users.UserNotFoundError)
