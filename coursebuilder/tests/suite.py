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
    - download WebTest Python package from a URL below and put
      the files in a folder of your choice, for example: tmp/webtest:
          http://pypi.python.org/packages/source/W/WebTest/WebTest-1.4.2.zip
    - update your Python path:
          PYTHONPATH=$PYTHONPATH:/tmp/webtest
    - invoke this test suite from the command line:
          # Automatically find and run all Python tests in tests/*.
          python tests/suite.py
          # Run only tests matching shell glob *_functional_test.py in tests/*.
          python tests/suite.py --pattern *_functional_test.py
          # Run test method baz in unittest.TestCase Bar found in tests/foo.py.
          python tests/suite.py --test_class_name tests.foo.Bar.baz
    - review the output to make sure there are no errors or warnings

Good luck!
"""

__author__ = 'Sean Lip'

import argparse
import base64
import os
import shutil
import sys
import unittest

# The following import is needed in order to add third-party libraries.
import appengine_config  # pylint: disable-msg=unused-import
import webtest

from google.appengine.datastore import datastore_stub_util
from google.appengine.ext import deferred
from google.appengine.ext import testbed


_PARSER = argparse.ArgumentParser()
_PARSER.add_argument(
    '--pattern', default='*.py',
    help='shell pattern for discovering files containing tests', type=str)
_PARSER.add_argument(
    '--test_class_name',
    help='optional dotted module name of the test(s) to run', type=str)

# Base filesystem location for test data.
TEST_DATA_BASE = '/tmp/experimental/coursebuilder/test-data/'


def empty_environ():
    os.environ['AUTH_DOMAIN'] = 'example.com'
    os.environ['SERVER_NAME'] = 'localhost'
    os.environ['HTTP_HOST'] = 'localhost'
    os.environ['SERVER_PORT'] = '8080'
    os.environ['USER_EMAIL'] = ''
    os.environ['USER_ID'] = ''


class TestBase(unittest.TestCase):
    """Base class for all Course Builder tests."""

    def setUp(self):
        super(TestBase, self).setUp()
        # Map of object -> {symbol_string: original_value}
        self._originals = {}

    def tearDown(self):
        self._unswap_all()
        super(TestBase, self).tearDown()

    def swap(self, source, symbol, new):
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

    # Allow protected method names. pylint: disable-msg=g-bad-name
    def _unswap_all(self):
        for source, symbol_to_value in self._originals.iteritems():
            for symbol, value in symbol_to_value.iteritems():
                setattr(source, symbol, value)

    def shortDescription(self):
        """Additional information logged during unittest invocation."""
        # Suppress default logging of docstrings. Instead log name/status only.
        return None


class FunctionalTestBase(TestBase):
    """Base class for functional tests."""

    def setUp(self):
        super(FunctionalTestBase, self).setUp()
        # e.g. TEST_DATA_BASE/tests/functional/tests/MyTestCase.
        self.test_tempdir = os.path.join(
            TEST_DATA_BASE, self.__class__.__module__.replace('.', os.sep),
            self.__class__.__name__)
        self.reset_filesystem()

    def tearDown(self):
        self.reset_filesystem(remove_only=True)
        super(FunctionalTestBase, self).tearDown()

    def reset_filesystem(self, remove_only=False):
        if os.path.exists(self.test_tempdir):
            shutil.rmtree(self.test_tempdir)
        if not remove_only:
            os.makedirs(self.test_tempdir)


class AppEngineTestBase(FunctionalTestBase):
    """Base class for tests that require App Engine services."""

    def getApp(self):  # pylint: disable-msg=g-bad-name
        """Returns the main application to be tested."""
        raise Exception('Not implemented.')

    def setUp(self):  # pylint: disable-msg=g-bad-name
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
        self.testbed.init_taskqueue_stub()
        self.taskq = self.testbed.get_stub(testbed.TASKQUEUE_SERVICE_NAME)

    def tearDown(self):  # pylint: disable-msg=g-bad-name
        self.testbed.deactivate()
        super(AppEngineTestBase, self).tearDown()

    def execute_all_deferred_tasks(self, queue_name='default'):
        """Executes all pending deferred tasks."""
        for task in self.taskq.GetTasks(queue_name):
            deferred.run(base64.b64decode(task['body']))


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
    if parsed_args.test_class_name:
        return loader.loadTestsFromName(parsed_args.test_class_name)
    else:
        return loader.discover(
            os.path.dirname(__file__), pattern=parsed_args.pattern)


def fix_sys_path():
    """Fix the sys.path to include GAE extra paths."""
    import dev_appserver  # pylint: disable=C6204

    # dev_appserver.fix_sys_path() prepends GAE paths to sys.path and hides
    # our classes like 'tests' behind other modules that have 'tests'.
    # Here, unlike dev_appserver, we append the path instead of prepending it,
    # so that our classes come first.
    sys.path += dev_appserver.EXTRA_PATHS[:]


def main():
    """Starts in-process server and runs all test cases in this module."""
    fix_sys_path()
    parsed_args = _PARSER.parse_args()

    result = unittest.TextTestRunner(verbosity=2).run(
        create_test_suite(parsed_args))

    if result.errors or result.failures:
        raise Exception(
            'Test suite failed: %s errors, %s failures of '
            ' %s tests run.' % (
                len(result.errors), len(result.failures), result.testsRun))

    import tests.functional.actions as actions  # pylint: disable-msg=g-import-not-at-top

    count = len(actions.UNIQUE_URLS_FOUND.keys())
    result.stream.writeln('INFO: Unique URLs found: %s' % count)
    result.stream.writeln('INFO: All %s tests PASSED!' % result.testsRun)


if __name__ == '__main__':
    appengine_config.gcb_force_default_encoding('ascii')
    main()
