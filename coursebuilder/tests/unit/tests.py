# coding: utf-8
# Copyright 2013 Google Inc. All Rights Reserved.
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
import sys
import time
import unittest
import appengine_config
from controllers import sites
from controllers import utils
from models import config
from models import transforms
from tools import verify


class ShouldHaveFailedByNow(Exception):
    """Special exception raised when a prior method did not raise."""
    pass


def assert_fails(function):
    """Checks that function invocation raises an exception."""
    try:
        function()
        raise ShouldHaveFailedByNow(
            'Expected to fail: %s().' % function.__name__)
    except ShouldHaveFailedByNow as e:
        raise e
    except Exception:
        pass


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

    def test_string_encoding(self):
        """Test our understanding of Python string encoding aspects.

        We were quite naive to believe Python solves all string encoding issues
        automatically. That is not completely true and we have to do a lot of
        manual work to get it right. Here we capture some of the patterns.
        """
        original_encoding = sys.getdefaultencoding()

        # Test with 'ascii' default encoding. Note that GAE runs in 'ascii',
        # and not in 'utf-8'. There is no way to override this currently.
        appengine_config.gcb_force_default_encoding('ascii')

        # Note that Python bravely ignores the file encoding declaration
        # 'coding: utf-8' at the top of this file. The intuitive behavior would
        # be to change the default encoding to 'utf-8' for all the code running
        # in the scope of this file.

        # Initialization.
        test_1 = 'My Test Title Мой заголовок теста'
        test_2 = u'My Test Title Мой заголовок теста'

        # Types.
        assert isinstance(test_1, str)
        assert isinstance(test_2, unicode)
        assert test_1 != test_2

        # Conversions.
        assert_fails(lambda: unicode(test_1))
        assert unicode(test_1, 'utf-8')
        assert isinstance(unicode(test_1, 'utf-8'), unicode)
        assert unicode(test_1, 'utf-8') == test_2

        # Expressions.
        assert_fails(lambda: test_1 + test_2)
        assert_fails(lambda: '%s %s' % (test_1, test_2))
        assert_fails(lambda: u'%s %s' % (test_1, test_2))  # Why does it fail?
        assert_fails(lambda: ''.join([test_1, test_2]))
        assert_fails(lambda: u''.join([test_1, test_2]))  # Why does it fail?
        ''.join([unicode(test_1, 'utf-8'), test_2])

        # Test with 'utf-8' default encoding.
        appengine_config.gcb_force_default_encoding('utf-8')

        # Initialization.
        test_1 = 'My Test Title Мой заголовок теста'
        test_2 = u'My Test Title Мой заголовок теста'

        # Types.
        assert isinstance(test_1, str)  # How can this be true?
        assert isinstance(test_2, unicode)
        assert test_1 == test_2  # Note '!=' above, and '==' here. Who knew!!!

        # Conversions.
        assert unicode(test_1) == test_2
        assert unicode(test_1, 'utf-8') == test_2

        # Expressions.
        assert test_1 + test_2
        assert '%s %s' % (test_1, test_2)
        assert u'%s %s' % (test_1, test_2)

        # Clean up.
        appengine_config.gcb_force_default_encoding(original_encoding)


if __name__ == '__main__':
    unittest.TextTestRunner().run(
        unittest.TestLoader().loadTestsFromTestCase(InvokeExistingUnitTest))
