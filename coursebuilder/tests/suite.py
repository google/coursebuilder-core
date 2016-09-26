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

"""Course Builder test suite.

This script runs all functional and units test in the Course Builder project.

Here is how to use the script:
    - if you don't have pip, install it using 'sudo apt-get install python-pip'
    - install WebTest using: 'sudo pip install WebTest'
    - make sure your PYTHONPATH contains: google_appengine,
      google_appengine/lib/jinja2-2.6, google_appengine/lib/webapp2-2.5.1 and
      the 'coursebuilder' directory itself
    - invoke this test suite from the command line:
          # Run test method baz in unittest.TestCase Bar found in tests/foo.py.
          python tests/suite.py --test_class_name tests.foo.Bar.baz
    - review the output to make sure there are no errors or warnings

Good luck!
"""

__author__ = 'Sean Lip'

import argparse
import cStringIO
import logging
import os
import pdb
import shutil
import sys
import unittest

import task_queue

import webtest

import appengine_config
from tools.etl import etl

from google.appengine.api.search import simple_search_stub
from google.appengine.datastore import datastore_stub_util
from google.appengine.ext import testbed

_PARSER = argparse.ArgumentParser()
_PARSER.add_argument(
    '--test_class_name',
    help='optional dotted module name of the test(s) to run', type=str)
_PARSER.add_argument(
    '--pdb',
    action='store_true',
    help='Automatically enter a debugger when an error occurs.')

# Direct key access so we'll throw if os.environ is misconfigured.
TEST_DATA_BASE = os.path.join(
    os.environ['COURSEBUILDER_RESOURCES'], 'test-data')


def empty_environ():
    os.environ['AUTH_DOMAIN'] = 'example.com'
    os.environ['SERVER_NAME'] = 'localhost'
    os.environ['HTTP_HOST'] = 'localhost'
    os.environ['SERVER_PORT'] = '8080'
    os.environ['USER_EMAIL'] = ''
    os.environ['USER_ID'] = ''
    os.environ['DEFAULT_VERSION_HOSTNAME'] = (
        os.environ['HTTP_HOST'] + ':' + os.environ['SERVER_PORT'])


def iterate_tests(test_suite_or_case):
    """Iterate through all of the test cases in 'test_suite_or_case'."""
    try:
        suite = iter(test_suite_or_case)
    except TypeError:
        yield test_suite_or_case
    else:
        for test in suite:
            for subtest in iterate_tests(test):
                yield subtest


class TestBase(unittest.TestCase):
    """Base class for all Course Builder tests."""

    INTEGRATION_SERVER_BASE_URL = 'http://localhost:8081'
    ADMIN_SERVER_BASE_URL = 'http://localhost:8000'

    STOP_AFTER_FIRST_FAILURE = False
    HAS_PENDING_FAILURE = False

    # Log level for all tests in this test case. Override if you need to test
    # against different logging levels. Be very careful when setting this to
    # logging.DEBUG: downstream code is sometimes very chatty at logging.DEBUG,
    # and can generate enough logging data that tests run out of memory.
    LOG_LEVEL = logging.ERROR

    def setUp(self):
        if TestBase.STOP_AFTER_FIRST_FAILURE:
            assert not TestBase.HAS_PENDING_FAILURE
        super(TestBase, self).setUp()
        self._set_up_logging()
        # e.g. TEST_DATA_BASE/tests/functional/tests/MyTestCase.
        self.test_tempdir = os.path.join(
            TEST_DATA_BASE, self.__class__.__module__.replace('.', os.sep),
            self.__class__.__name__)
        self.reset_filesystem()
        self._originals = {}  # Map of object -> {symbol_string: original_value}

    def _set_up_logging(self):
        self._log = cStringIO.StringIO()
        self._stream_handler = logging.StreamHandler(self._log)
        self._stream_handler.setFormatter(
            logging.Formatter(fmt='%(levelname)s: %(message)s'))
        self._logger = logging.getLogger()
        self._logger.addHandler(self._stream_handler)
        self._logger.setLevel(self.LOG_LEVEL)

    def tearDown(self):
        self._unswap_all()
        self.reset_filesystem(remove_only=True)
        self._tear_down_logging()
        super(TestBase, self).tearDown()

    def _tear_down_logging(self):
        self._logger.removeHandler(self._stream_handler)
        self._log.close()

    def get_log(self):
        self._log.flush()
        return self._log.getvalue()

    def assertLogContains(self, message):
        self.assertIn(message, self.get_log())

    def assertLogDoesNotContain(self, message):
        self.assertNotIn(message, self.get_log())

    def reset_filesystem(self, remove_only=False):
        if os.path.exists(self.test_tempdir):
            shutil.rmtree(self.test_tempdir)
        if not remove_only:
            os.makedirs(self.test_tempdir)

    def run(self, result=None):
        if not result:
            result = self.defaultTestResult()
        super(TestBase, self).run(result)
        if not result.wasSuccessful():
            TestBase.HAS_PENDING_FAILURE = True

    def shortDescription(self):
        """Additional information logged during unittest invocation."""
        # Suppress default logging of docstrings. Instead log name/status only.
        return None

    def swap(self, source, symbol, new):  # pylint: disable=invalid-name
        """Swaps out source.symbol for a new value.

        Allows swapping of members and methods:

            myobject.foo = 'original_foo'
            self.swap(myobject, 'foo', 'bar')
            self.assertEqual('bar', myobject.foo)
            myobject.baz()  # -> 'original_baz'
            self.swap(myobject, 'baz', lambda: 'quux')
            self.assertEqual('quux', myobject.bar())

        Swaps are automatically undone in tearDown().

        Args:
            source: object. The source object to swap from.
            symbol: string. The name of the symbol to swap.
            new: object. The new value to swap in.
        """
        if source not in self._originals:
            self._originals[source] = {}
        if not self._originals[source].get(symbol, None):
            self._originals[source][symbol] = getattr(source, symbol)
        setattr(source, symbol, new)

    def _unswap_all(self):
        for source, symbol_to_value in self._originals.iteritems():
            for symbol, value in symbol_to_value.iteritems():
                setattr(source, symbol, value)


class FunctionalTestBase(TestBase):
    """Base class for functional tests."""


class AppEngineTestBase(FunctionalTestBase):
    """Base class for tests that require App Engine services."""

    def getApp(self):
        """Returns the main application to be tested."""
        raise Exception('Not implemented.')

    def setUp(self):
        super(AppEngineTestBase, self).setUp()
        empty_environ()

        # setup an app to be tested
        self.testapp = webtest.TestApp(self.getApp())
        self.testbed = testbed.Testbed()
        self.testbed.activate()

        # configure datastore policy to emulate instantaneously and globally
        # consistent HRD; we also patch dev_appserver in main.py to run under
        # the same policy
        policy = datastore_stub_util.PseudoRandomHRConsistencyPolicy(
            probability=1)

        # declare any relevant App Engine service stubs here
        self.testbed.init_user_stub()
        self.testbed.init_memcache_stub()
        self.testbed.init_datastore_v3_stub(consistency_policy=policy)
        self.testbed.init_taskqueue_stub(root_path=os.environ['SOURCE_DIR'])
        self.taskq = self.testbed.get_stub(testbed.TASKQUEUE_SERVICE_NAME)
        self.testbed.init_urlfetch_stub()
        self.testbed.init_files_stub()
        self.testbed.init_blobstore_stub()
        self.testbed.init_mail_stub()
        self.testbed.init_app_identity_stub()
        # TODO(emichael): Fix this when an official stub is created
        self.testbed._register_stub(
            'search', simple_search_stub.SearchServiceStub())
        self.task_dispatcher = task_queue.TaskQueueHandlerDispatcher(
            self.testapp, self.taskq)

        # Handle for testing sent mail.
        self.mail_stub = self.testbed.get_stub(testbed.MAIL_SERVICE_NAME)

    def tearDown(self):
        self.testbed.deactivate()
        super(AppEngineTestBase, self).tearDown()

    def get_mail_stub(self):
        return self.testbed.get_stub(testbed.MAIL_SERVICE_NAME)


def create_test_suite(parsed_args):
    """Loads all requested test suites.

    By default, loads all unittest.TestCases found under the project root's
    tests/ directory.

    Args:
        parsed_args: argparse.Namespace. Processed command-line arguments.

    Returns:
        unittest.TestSuite. The test suite populated with all tests to run.
    """
    loader = unittest.TestLoader()
    if not parsed_args.test_class_name:
        raise Exception('Expected --test_class_name to be specified.')
    os.environ['GCB_TEST_MODE'] = 'true'
    return loader.loadTestsFromName(parsed_args.test_class_name)


def fix_sys_path():
    """Fix the sys.path to include GAE extra paths."""
    import dev_appserver  # pylint: disable=C6204

    # dev_appserver.fix_sys_path() prepends GAE paths to sys.path and hides
    # our classes like 'tests' behind other modules that have 'tests'.
    # Here, unlike dev_appserver, we append the path instead of prepending it,
    # so that our classes come first.
    sys.path += dev_appserver.EXTRA_PATHS[:]

    # This is to work around an issue with the __import__ builtin.  The
    # problem seems to be that if the sys.path list contains an item that
    # partially matches a package name to import, __import__ will get
    # confused, and report an error message (which removes the first path
    # element from the module it's complaining about, which does not help
    # efforts to diagnose the problem at all).
    #
    # The specific case where this causes an issue is between
    # $COURSEBUILDER_HOME/tests/internal and $COURSEBUILDER_HOME/internal
    # Since the former exists, __import__ will ignore the second, and so
    # things like .../internal/experimental/autoregister/autoregister
    # cannot be loaded.
    #
    # To address this issue, we ensure that COURSEBUILDER_HOME is on sys.path
    # before anything else, and do it before appengine_config's module
    # importation starts running.  (And we have to do it here, because if we
    # try to do this within appengine_config, AppEngine will throw an error)
    if appengine_config.BUNDLE_ROOT in sys.path:
        sys.path.remove(appengine_config.BUNDLE_ROOT)
    sys.path.insert(0, appengine_config.BUNDLE_ROOT)


class DebugTestResult(unittest.TextTestResult):

    def addError(self, test, err):
        pdb.post_mortem(err[2])
        super(DebugTestResult, self).addError(test, err)

    def addFailure(self, test, err):
        pdb.post_mortem(err[2])
        super(DebugTestResult, self).addFailure(test, err)


def main():
    """Starts in-process server and runs all test cases in this module."""
    fix_sys_path()

    etl._set_env_vars_from_app_yaml()
    parsed_args = _PARSER.parse_args()
    test_suite = create_test_suite(parsed_args)

    kwargs = {
        'verbosity': 2,
    }

    if parsed_args.pdb:
        kwargs['resultclass'] = DebugTestResult

    result = unittest.TextTestRunner(**kwargs).run(test_suite)
    if result.errors or result.failures:
        raise Exception(
            'Test suite failed: %s errors, %s failures of '
            ' %s tests run.' % (
                len(result.errors), len(result.failures), result.testsRun))

    import tests.functional.actions as actions

    count = len(actions.UNIQUE_URLS_FOUND.keys())
    result.stream.writeln('INFO: Unique URLs found: %s' % count)
    result.stream.writeln('INFO: All %s tests PASSED!' % result.testsRun)


if __name__ == '__main__':
    appengine_config.gcb_force_default_encoding('ascii')
    main()
