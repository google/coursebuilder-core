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

"""Unit tests for tools/etl/remote.py."""

__author__ = [
    'johncox@google.com (John Cox)',
]


from tests import suite
from tools.etl import remote

from google.appengine.ext.remote_api import remote_api_stub


class EnvironmentTests(suite.TestBase):

    def test_establish_logs_auth_error_and_root_cause_when_oauth_errors(self):
        def throw(unused_server, unused_path, secure=None):
            raise Exception('root cause text')

        self.swap(remote_api_stub, 'ConfigureRemoteApiForOAuth', throw)
        environment = remote.Environment('server')

        with self.assertRaises(SystemExit):
            environment.establish()

        self.assertLogContains('missing OAuth2 credentials')
        self.assertLogContains('root cause text')

    def test_establish_logs_sdk_error_when_oauth_method_missing(self):
        environment = remote.Environment('server')
        oauth2_method_missing = object()

        with self.assertRaises(SystemExit):
            environment.establish(stub=oauth2_method_missing)

        self.assertLogContains('Your Google App Engine SDK is old')

    def test_establish_is_noop_when_testing_true(self):
        # If we actually called the implementation without credentials, we'd
        # crash.
        environment = remote.Environment('server', testing=True)
        environment.establish()
