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
import logging
import os
import shutil
import signal
import socket
import stat
import subprocess
import sys
import time
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
    '--pattern', default='*.py',
    help='shell pattern for discovering files containing tests', type=str)
_PARSER.add_argument(
    '--test_class_name',
    help='optional dotted module name of the test(s) to run', type=str)
_PARSER.add_argument(
    '--integration_server_start_cmd',
    help='script to start an external CB server', type=str)

# Base filesystem location for test data.
if 'COURSEBUILDER_RESOURCES' in os.environ:
    TEST_DATA_BASE = os.path.join(
        os.environ['COURSEBUILDER_RESOURCES'], 'test-data/')
else:
    TEST_DATA_BASE = os.path.join(
        os.environ['HOME'], 'coursebuilder_resources/test-data/')


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

    REQUIRES_INTEGRATION_SERVER = 'REQUIRES_INTEGRATION_SERVER'
    REQUIRES_TESTING_MODULES = 'REQUIRES_TESTING_MODULES'
    INTEGRATION_SERVER_BASE_URL = 'http://localhost:8081'
    ADMIN_SERVER_BASE_URL = 'http://localhost:8000'

    STOP_AFTER_FIRST_FAILURE = False
    HAS_PENDING_FAILURE = False

    def setUp(self):
        if TestBase.STOP_AFTER_FIRST_FAILURE:
            assert not TestBase.HAS_PENDING_FAILURE
        super(TestBase, self).setUp()
        # e.g. TEST_DATA_BASE/tests/functional/tests/MyTestCase.
        self.test_tempdir = os.path.join(
            TEST_DATA_BASE, self.__class__.__module__.replace('.', os.sep),
            self.__class__.__name__)
        self.reset_filesystem()
        self._originals = {}  # Map of object -> {symbol_string: original_value}

    def run(self, result=None):
        if not result:
            result = self.defaultTestResult()
        super(TestBase, self).run(result)
        if not result.wasSuccessful():
            TestBase.HAS_PENDING_FAILURE = True

    def tearDown(self):
        self._unswap_all()
        self.reset_filesystem(remove_only=True)
        super(TestBase, self).tearDown()

    def reset_filesystem(self, remove_only=False):
        if os.path.exists(self.test_tempdir):
            shutil.rmtree(self.test_tempdir)
        if not remove_only:
            os.makedirs(self.test_tempdir)

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

    # Allow protected method names. pylint: disable=g-bad-name
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


class AppEngineTestBase(FunctionalTestBase):
    """Base class for tests that require App Engine services."""

    def getApp(self):  # pylint: disable=g-bad-namer
        """Returns the main application to be tested."""
        raise Exception('Not implemented.')

    def setUp(self):  # pylint: disable=g-bad-name
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
        self.testbed.init_urlfetch_stub()
        self.testbed.init_files_stub()
        self.testbed.init_blobstore_stub()
        self.testbed.init_mail_stub()
        # TODO(emichael): Fix this when an official stub is created
        self.testbed._register_stub(
            'search', simple_search_stub.SearchServiceStub())
        self.task_dispatcher = task_queue.TaskQueueHandlerDispatcher(
            self.testapp, self.taskq)

    def tearDown(self):  # pylint: disable=g-bad-name
        self.testbed.deactivate()
        super(AppEngineTestBase, self).tearDown()

    def get_mail_stub(self):
        return self.testbed.get_stub(testbed.MAIL_SERVICE_NAME)

    def execute_all_deferred_tasks(self, queue_name='default',
                                   iteration_limit=None):
        """Executes all pending deferred tasks."""

        # Outer loop here because some tasks (esp. map/reduce) will enqueue
        # more tasks as part of their operation.
        while iteration_limit is None or iteration_limit > 0:
            tasks = self.taskq.GetTasks(queue_name)
            if not tasks:
                break
            for task in tasks:
                self.task_dispatcher.dispatch_task(task)
            if iteration_limit:
                iteration_limit -= 1


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


def ensure_port_available(port_number):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind(('localhost', port_number))
    except socket.error, ex:
        logging.error(
            '''==========================================================
            Failed to bind to port %d.
            This probably means another CourseBuilder server is
            already running.  Be sure to shut down any manually
            started servers before running tests.
            ==========================================================''',
            port_number)
        raise ex
    s.close()


def start_integration_server(integration_server_start_cmd, modules):
    if modules:
        _fn = os.path.join(appengine_config.BUNDLE_ROOT, 'custom.yaml')
        _st = os.stat(_fn)
        os.chmod(_fn, _st.st_mode | stat.S_IWUSR)
        fp = open(_fn, 'w')
        fp.writelines([
            'env_variables:\n',
            '  GCB_REGISTERED_MODULES_CUSTOM:\n'])
        fp.writelines(['    %s\n' % module.__name__ for module in modules])
        fp.close()

    logging.info('Starting external server: %s', integration_server_start_cmd)
    server = subprocess.Popen(integration_server_start_cmd)
    time.sleep(3)  # Wait for server to start up
    return server


def stop_integration_server(server, modules):
    server.kill()  # dev_appserver.py itself.

    # The new dev appserver starts a _python_runtime.py process that isn't
    # captured by start_integration_server and so doesn't get killed. Until it's
    # done, our tests will never complete so we kill it manually.
    (stdout, unused_stderr) = subprocess.Popen(
        ['pgrep', '-f', '_python_runtime.py'], stdout=subprocess.PIPE
    ).communicate()

    # If tests are killed partway through, runtimes can build up; send kill
    # signals to all of them, JIC.
    pids = [int(pid.strip()) for pid in stdout.split('\n') if pid.strip()]
    for pid in pids:
        os.kill(pid, signal.SIGKILL)

    if modules:
        fp = open(
            os.path.join(appengine_config.BUNDLE_ROOT, 'custom.yaml'), 'w')
        fp.writelines([
            '# Add configuration for your application here to avoid\n'
            '# potential merge conflicts with new releases of the main\n'
            '# app.yaml file.  Modules registered here should support the\n'
            '# standard CourseBuilder module config.  (Specifically, the\n'
            '# imported Python module should provide a method\n'
            '# "register_module()", taking no parameters and returning a\n'
            '# models.custom_modules.Module instance.\n'
            '#\n'
            'env_variables:\n'
            '#  GCB_REGISTERED_MODULES_CUSTOM:\n'
            '#    modules.my_extension_module\n'
            '#    my_extension.modules.widgets\n'
            '#    my_extension.modules.blivets\n'
            ])
        fp.close()


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
    etl._set_env_vars_from_app_yaml()
    parsed_args = _PARSER.parse_args()
    test_suite = create_test_suite(parsed_args)

    all_tags = {}
    for test in iterate_tests(test_suite):
        if hasattr(test, 'TAGS'):
            for tag in test.TAGS:
                if isinstance(test.TAGS[tag], set) and tag in all_tags:
                    all_tags[tag].update(test.TAGS[tag])
                else:
                    all_tags[tag] = test.TAGS[tag]

    server = None
    if TestBase.REQUIRES_INTEGRATION_SERVER in all_tags:
        ensure_port_available(8081)
        ensure_port_available(8000)
        server = start_integration_server(
            parsed_args.integration_server_start_cmd,
            all_tags.get(TestBase.REQUIRES_TESTING_MODULES, set()))

    result = unittest.TextTestRunner(verbosity=2).run(test_suite)

    if server:
        stop_integration_server(
            server, all_tags.get(TestBase.REQUIRES_TESTING_MODULES, set()))

    if result.errors or result.failures:
        raise Exception(
            'Test suite failed: %s errors, %s failures of '
            ' %s tests run.' % (
                len(result.errors), len(result.failures), result.testsRun))

    import tests.functional.actions as actions  # pylint: disable=g-import-not-at-top

    count = len(actions.UNIQUE_URLS_FOUND.keys())
    result.stream.writeln('INFO: Unique URLs found: %s' % count)
    result.stream.writeln('INFO: All %s tests PASSED!' % result.testsRun)


if __name__ == '__main__':
    appengine_config.gcb_force_default_encoding('ascii')
    main()
