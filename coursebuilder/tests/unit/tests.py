# Copyright 2012 Google Inc. All Rights Reserved.
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

"""Runs all unit tests."""

__author__ = 'Pavel Simakov (psimakov@google.com)'

import os
import time
import unittest
from controllers import sites
from controllers import utils
from models import config
from models import transforms
from tools import verify


class InvokeExistingUnitTest(unittest.TestCase):
    """Run all units tests declared elsewhere."""

    def test_existing_unit_tests(self):
        """Run all units tests declared elsewhere."""
        sites.run_all_unit_tests()
        config.run_all_unit_tests()
        verify.run_all_unit_tests()
        transforms.run_all_unit_tests()

    def test_xsrf_token_manager(self):
        """Test XSRF token operations."""

        os.environ['AUTH_DOMAIN'] = 'test_domain'

        # Issues and verify anonymous user token.
        action = 'test-action'
        token = utils.XsrfTokenManager.create_xsrf_token(action)
        assert '/' in token
        assert utils.XsrfTokenManager.is_xsrf_token_valid(token, action)

        # Impersonate real user.
        os.environ['USER_EMAIL'] = 'test_email'
        os.environ['USER_ID'] = 'test_id'

        # Issues and verify real user token.
        action = 'test-action'
        token = utils.XsrfTokenManager.create_xsrf_token(action)
        assert '/' in token
        assert utils.XsrfTokenManager.is_xsrf_token_valid(token, action)

        # Check forged time stamp invalidates token.
        parts = token.split('/')
        assert len(parts) == 2
        forgery = '%s/%s' % (long(parts[0]) + 1000, parts[1])
        assert not forgery == token
        assert not utils.XsrfTokenManager.is_xsrf_token_valid(forgery, action)

        # Check token properly expires.
        action = 'test-action'
        time_in_the_past = long(
            time.time() - utils.XsrfTokenManager.XSRF_TOKEN_AGE_SECS)
        old_token = utils.XsrfTokenManager._create_token(
            action, time_in_the_past)
        assert not utils.XsrfTokenManager.is_xsrf_token_valid(old_token, action)

        # Clean up.
        del os.environ['AUTH_DOMAIN']
        del os.environ['USER_EMAIL']
        del os.environ['USER_ID']


if __name__ == '__main__':
    unittest.TextTestRunner().run(
        unittest.TestLoader().loadTestsFromTestCase(InvokeExistingUnitTest))
