#!/usr/bin/python

# Copyright 2014 Google Inc. All Rights Reserved.
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

"""Runs all of the tests in parallel with or without integration server.

This package doesn't need any setup and can do one of three things:

    execute all unit, functional and integration tests:
        python scripts/project.py --test=*

    execute specific tests packages, classes or methods:
        python scripts/project.py --test tests.unit.test_classes

    execute a complete official Course Builder release verification process:
        python scripts/project.py --release

It's possible to run this package headless, while still fully executing all
of the Selenium integration tests. Several tools are available to get this
done. The one we know works is xvfb -- virtual framebuffer display server.
Here is an example how to use it:

    ssh $my_developer_box
    sudo apt-get install xvfb
    Xvfb :99 -ac & export DISPLAY=:99
    cd /coursebuilder
    python scripts/project.py --release

Good luck!
"""

__author__ = 'Pavel Simakov (psimakov@google.com)'


import os
import sys

import argparse
import datetime
import difflib
import logging
import multiprocessing
import re
import signal
import shutil
import socket
import stat
import subprocess
import threading
import time
import urllib2
import yaml
import zipfile

# defer some imports
schema_fields = None
schema_transforms = None
all_tests = None


INTEGRATION_SERVER_BASE_URL = 'http://localhost:8081'

# List of dot-qualified modules that may not be imported by CB code.
DISALLOWED_IMPORTS = [
    'google.appengine.api.users',
]

# Map of relative cb path -> dot qualified import target of exceptions to
# DISALLOWED_IMPORTS.
DISALLOWED_IMPORTS_EXCEPTIONS = {
    'common/users.py': ['google.appengine.api.users'],
    'tests/functional/common_users.py': ['google.appengine.api.users'],
}
PY_FILE_SUFFIX = '.py'

LOG_LINES = []
LOG_LOCK = threading.Lock()

# exact count of compiled .mo catalog files included in release; change this
# when new files are added. NOTE: common.locales.LOCALES_DISPLAY_NAMES must
# be kept in sync with the locales supported.
EXPECTED_MO_FILE_COUNT = 58

PRODUCT_NAME = 'coursebuilder'

# name of the response header used to transmit handler class name;
# keep in sync with the same value in controllers/sites.py
GCB_HANDLER_CLASS_HEADER_NAME = 'gcb-handler-class'

# a lists of tests URL's that can be served statically or dynamically
STATIC_SERV_URLS = [
    ('/modules/oeditor/_static/js/butterbar.js', None),  # always static
    ('/static/codemirror/lib/codemirror.js', 'CustomZipHandler'),
    ('/static/yui_3.6.0/yui/build/yui/yui.js', 'CustomZipHandler'),
    ('/static/inputex-3.1.0/src/loader.js', 'CustomZipHandler'),
    (
        '/static/2in3/2in3-master/dist/2.9.0/build/yui2-editor/yui2-editor.js',
        'CustomZipHandler'),
    (
        '/modules/guide/resources/polymer/bower_components/bower.json',
        'CustomZipHandler')
    ]

# a lists of tests URL's served by combo zip handler
COMBO_SERV_URLS = [
    (
        '/static/combo/inputex?'
        'src/inputex/assets/skins/sam/inputex.css&'
        'src/inputex-list/assets/skins/sam/inputex-list.css',
        'CustomCssComboZipHandler'),
    ]

# A directory, which all components of this file should treat as project root
BUILD_DIR = None

TEST_CLASS_NAME_ANY = '*'

def build_dir():
    """Convenience function to access BUILD_DIR."""
    return BUILD_DIR


def make_default_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--test',
        help='A dotted module name of the test(s) to run; '
        'use "*" to run all tests',
        type=str, default=None)
    parser.add_argument(
        '--release',
        help='Whether to run an entire release validation process',
        action='store_true')
    parser.add_argument(
        '--skip_integration', help='Whether to skip integration tests',
        action='store_true')
    parser.add_argument(
        '--skip_non_integration',
        help='Whether to skip functional and unit tests',
        action='store_true')
    parser.add_argument(
        '--skip_pylint', help='Whether to skip pylint tests',
        action='store_true')
    parser.add_argument(
        '--ignore_pylint_failures',
        help='Whether to ignore pylint test failures',
        action='store_true')
    parser.add_argument(
        '--deep_clean',
        help='Whether to delete all temporary files, resources and caches '
        'before starting the release process',
        action='store_true')
    parser.add_argument(
        '--verbose',
        help='Print more verbose output to help diagnose problems',
        action='store_true')
    parser.add_argument(
        '--server_log_file',
        help='If present, capture stdout and stderr from integration server '
        'to the named file.  This is helpful when diagnosing a problem with '
        'the server that does not manifest when the server is started outside '
        'tests.')
    return parser


def ensure_port_available(port_number, quiet=False):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind(('localhost', port_number))
    except socket.error, ex:
        if not quiet:
            logging.error('''
                ==========================================================
                Failed to bind to port %d.
                This probably means another CourseBuilder server is
                already running.  Be sure to shut down any manually
                started servers before running tests.

                Kill running server from command line via:
                lsof -i tcp:8081 -Fp | tr -d p | xargs kill -9
                ==========================================================''',
                port_number)
        raise ex
    s.close()


def start_integration_server(server_log_file, env):
    ensure_port_available(8000)
    ensure_port_available(8081)
    ensure_port_available(8082)
    server_cmd = os.path.join(build_dir(), 'scripts', 'start_in_shell.sh')
    return start_integration_server_process(
        server_cmd,
        set(['tests.integration.fake_visualizations']),
        server_log_file, env=env)


def start_integration_server_process(
    integration_server_start_cmd, modules, server_log_file, env):
    if modules:
        _fn = os.path.join(build_dir(), 'custom.yaml')
        _st = os.stat(_fn)
        os.chmod(_fn, _st.st_mode | stat.S_IWUSR)
        fp = open(_fn, 'w')
        fp.writelines([
            'env_variables:\n',
            '  GCB_REGISTERED_MODULES_CUSTOM:\n'])
        fp.writelines(['    %s\n' % module for module in modules])
        fp.close()

    logging.info('Starting external server: %s', integration_server_start_cmd)

    if server_log_file:
        if not server_log_file.startswith('/tmp'):
            raise ValueError(
                'Server log file name should start with /tmp; '
                'if it is in the local directory, the dev_appserver runtime '
                'will notice the file contents change, and attempt to '
                're-parse it, just-in-case.  This will add some log lines, '
                'so the file will change again, and will trigger a '
                're-parse, which....   Just put the file in /tmp/...')
        logfile = open(server_log_file, 'w')
    else:
        logfile = open(os.devnull, 'w')

    server = subprocess.Popen(
        integration_server_start_cmd, preexec_fn=os.setsid, stdout=logfile,
        stderr=logfile, env=env)
    time.sleep(3)  # Wait for server to start up

    return server, logfile


def stop_integration_server(server, logfile, modules):
    server.kill()  # dev_appserver.py itself.
    logfile.close()

    # The new dev appserver starts a _python_runtime.py process that isn't
    # captured by start_integration_server and so doesn't get killed. Until it's
    # done, our tests will never complete so we kill it manually.
    os.killpg(server.pid, signal.SIGTERM)

    # wait process to terminate
    while True:
        try:
            ensure_port_available(8081, quiet=True)
            ensure_port_available(8000, quiet=True)
            break
        except:  # pylint: disable=bare-except
            time.sleep(0.25)

    # clean up
    if modules:
        fp = open(
            os.path.join(build_dir(), 'custom.yaml'), 'w')
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


class WithReleaseConfiguration(object):
    """Class to manage integration server using 'with' statement."""

    def __init__(
        self,
        enable_integration_server, enable_static_serving, config):
        self.enable_integration_server = enable_integration_server
        self.enable_static_serving = enable_static_serving
        self.server_log_file = config.parsed_args.server_log_file

    def __enter__(self):
        if self.enable_integration_server:
            log(
                'Starting integration server '
                '(static serving %s)' % (
                    'enabled' if self.enable_static_serving else 'disabled'))
            env = os.environ.copy()
            env['GCB_ALLOW_STATIC_SERV'] = (
                'true' if self.enable_static_serving else 'false')
            self.server, self.logfile = start_integration_server(
                self.server_log_file, env=env)

    def __exit__(self, unused_type, unused_value, unused_traceback):
        if self.enable_integration_server:
            log('Stopping integration server')
            stop_integration_server(
                self.server, self.logfile,
                set(['tests.integration.fake_visualizations']))


def log(message):
    with LOG_LOCK:
        line = '%s\t%s' % (
            datetime.datetime.now().strftime('%Y/%m/%d %H:%M:%S'), message)
        LOG_LINES.append(line)
        print line


def run(exe, strict=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        verbose=False):
    """Runs a shell command and captures the stdout and stderr output."""
    p = subprocess.Popen(exe, stdout=stdout, stderr=stderr)
    last_stdout, last_stderr = p.communicate()
    result = []
    if last_stdout:
        for line in last_stdout:
            result.append(line)
    if last_stderr:
        for line in last_stderr:
            result.append(line)
    result = ''.join(result)

    if p.returncode != 0 and verbose and 'KeyboardInterrupt' not in result:
        exe_string = ' '.join(exe)
        print '#########vvvvv########### Start of output from >>>%s<<< ' % (
            exe_string)
        print result
        print '#########^^^^^########### End of output from >>>%s<<<' % (
            exe_string)

    if p.returncode != 0 and strict:
        raise Exception('Error %s\n%s' % (p.returncode, result))
    return p.returncode, result


class TaskThread(threading.Thread):
    """Runs a task in a separate thread."""

    def __init__(self, func, name=None):
        super(TaskThread, self).__init__()
        self.func = func
        self.exception = None
        self.name = name

    @classmethod
    def execute_task_list(
        cls, tasks,
        chunk_size=None, runtimes_sec=None, fail_on_first_error=False):

        if chunk_size is None:
            chunk_size = len(tasks)
        assert chunk_size > 0
        assert chunk_size < 256

        if runtimes_sec is None:
            runtimes_sec = []

        errors = []

        todo = [] + tasks
        running = set()
        task_to_runtime_sec = {}

        def on_error(error, task):
            errors.append(error)
            log(Exception(error))
            log('Failed task: %s.' % task.name)
            if fail_on_first_error:
                raise Exception(error)

        def update_progress():
            log(
                'Progress so far: '
                '%s failed, %s completed, %s running, %s pending.' % (
                    len(errors), len(tasks) - len(todo) - len(running),
                    len(running), len(todo)))

        last_update_on = 0
        while todo or running:

            # update progress
            now = time.time()
            update_frequency_sec = 30
            if now - last_update_on > update_frequency_sec:
                last_update_on = now
                update_progress()

            # check status of running jobs
            if running:
                for task in list(running):
                    task.join(1)
                    if task.isAlive():
                        start, end = task_to_runtime_sec[task]
                        now = time.time()
                        if now - end > 60:
                            log('Waiting over %ss for: %s' % (
                                int(now - start), task.name))
                            task_to_runtime_sec[task] = (start, now)
                        continue
                    if task.exception:
                        on_error(task.exception, task)
                    start, _ = task_to_runtime_sec[task]
                    now = time.time()
                    task_to_runtime_sec[task] = (start, now)
                    running.remove(task)

            # submit new work
            while len(running) < chunk_size and todo:
                task = todo.pop(0)
                running.add(task)
                now = time.time()
                task_to_runtime_sec[task] = (now, now)
                task.start()

        update_progress()

        if errors:
            raise Exception('There were %s errors' % len(errors))

        # format runtimes
        for task in tasks:
            start, end = task_to_runtime_sec[task]
            runtimes_sec.append(end - start)

    def run(self):
        try:
            self.func()
        except Exception as e:  # pylint: disable=broad-except
            self.exception = e


class FunctionalTestTask(object):
    """Executes a set of tests given a test class name."""

    def __init__(self, test_class_name, verbose):
        self.test_class_name = test_class_name
        self.verbose = verbose

    def run(self):
        if self.verbose:
            log('Running all tests in: %s.' % (self.test_class_name))
        suite_sh = os.path.join(build_dir(), 'scripts', 'suite.sh')
        result, self.output = run(
            ['sh', suite_sh, self.test_class_name], stdout=None,
            verbose=self.verbose)
        if result != 0:
            raise Exception()


class DeveloperWorkflowTester(object):

    def __init__(self, config):
        self.build_dir = config.build_dir

    def _run(self, cmd):
        result, out = run(cmd, verbose=False)
        if result != 0:
            raise Exception('Test failed:\n%s', out)
        return out

    def assert_contains(self, needle, haystack):
        if haystack.find(needle) == -1:
            raise Exception(
                'Expected to find %s, found:\n%s', (needle, haystack))

    def test_all(self):
        log('Testing developer test workflow')

        self.tests = TestsRepo(None)

        self.test_module_manifest_is_parsed()
        self.test_module_can_not_declare_tests_for_another_module()
        self.test_module_manifest_is_validated_1()
        self.test_module_manifest_is_validated_2()
        self.test_manifest_must_include_manifest_yaml()
        self.test_class_name_expansion()
        self.test_developer_test_workflow_with_test_sh()
        self.test_developer_test_workflow_with_project_py()
        self.test_developer_test_workflow_with_module_manifest()

    def test_module_manifest_is_parsed(self):
        manifest_data = '''
            tests:
                unit:
                    - modules.sample.foo = 5
                functional:
                    - modules.sample.baz = 6
                integration:
                    - modules.sample.bar = 7
            files:
                - foo
                - bar
                - baz
                - manifest.yaml
            '''
        manifest = ModuleManifest('sample', manifest_data=manifest_data)

        assert manifest.data['tests']['unit'][0] == 'modules.sample.foo = 5'
        assert manifest.data[
            'tests']['functional'][0] == 'modules.sample.baz = 6'
        assert manifest.data[
            'tests']['integration'][0] == 'modules.sample.bar = 7'
        assert manifest.data['files'] == ['foo', 'bar', 'baz', 'manifest.yaml']

        integration, non_integration = manifest.get_tests()
        assert 1 == len(integration)
        assert 2 == len(non_integration)

    def test_module_manifest_is_validated_1(self):
        manifest_data = '''
            tests:
                unknown:
                    - foo = 7
            files:
                - manifest.yaml
            '''
        try:
            ModuleManifest('sample', manifest_data=manifest_data)
        except:  # pylint: disable=bare-except
            return
        raise Exception('Expected to fail')

    def test_module_manifest_is_validated_2(self):
        manifest_data = '''
            tests:
                unit:
                    - foo : bar
            files:
                - manifest.yaml
            '''
        try:
            ModuleManifest('sample', manifest_data=manifest_data)
        except:  # pylint: disable=bare-except
            return
        raise Exception('Expected to fail')

    def test_module_can_not_declare_tests_for_another_module(self):
        manifest_data = '''
            tests:
                unit:
                    - modules.module_name_a.tests.tests.Main = 25
            files:
                - manifest.yaml
            '''
        ModuleManifest(
            'module_name_a', manifest_data=manifest_data).get_tests()
        try:
            ModuleManifest(
                'module_name_b', manifest_data=manifest_data).get_tests()
        except:  # pylint: disable=bare-except
            return
        raise Exception('Expected to fail')

    def test_manifest_must_include_manifest_yaml(self):
        manifest_data = '''
            files:
                - foo
        '''
        try:
            ModuleManifest('module_name', manifest_data=manifest_data)
        except:  # pylint: disable=bare-except
            return
        raise Exception('Expected to fail')


    def test_class_name_expansion(self):
        """Developer can test all methods of one class."""
        # package name expands into class names
        tests = self.tests.select_tests_to_run('tests.unit.')
        assert 'tests.unit.test_classes.InvokeExistingUnitTest' in tests
        assert 'tests.unit.test_classes.EtlRetryTest' in tests

        # class name is preserved
        tests = self.tests.select_tests_to_run(
            'tests.unit.test_classes.InvokeExistingUnitTest')
        assert 'tests.unit.test_classes.InvokeExistingUnitTest' in tests

        # method name is preserved
        tests = self.tests.select_tests_to_run(
            'tests.unit.test_classes.InvokeExistingUnitTest.'
            'test_string_encoding')
        assert(
            'tests.unit.test_classes.InvokeExistingUnitTest.'
            'test_string_encoding' in tests)

    def test_developer_test_workflow_with_test_sh(self):
        """Developer can test one method of one class with project.py."""
        cmd = os.path.join(self.build_dir, 'scripts', 'project.py')

        # test "module.module.ClassName.method_name" is supported
        out = self._run([
            'python', cmd, '--test',
            'tests.unit.test_classes.'
            'InvokeExistingUnitTest.test_string_encoding'])
        self.assert_contains(
            'tests.unit.test_classes.InvokeExistingUnitTest', out)

        # test "method_name (module.module.ClassName)" is supported
        out = self._run([
            'python', cmd, '--test',
            'test_same_formula_body (modules.math.math_tests.MathTagTests)'])
        self.assert_contains(
            'modules.math.math_tests.MathTagTests.test_same_formula_body', out)

    def test_developer_test_workflow_with_project_py(self):
        """Developer can test one method of one class with project.py."""
        cmd = os.path.join(self.build_dir, 'scripts',
            'project.py')
        out = self._run([
            'python', cmd,
            '--skip_pylint',
            '--test', 'tests.unit.test_classes'])
        self.assert_contains(
            'tests.unit.test_classes.InvokeExistingUnitTest', out)

    def test_developer_test_workflow_with_module_manifest(self):
        """Developer can seamlessly run a test declared in module manifest."""
        cmd = os.path.join(self.build_dir, 'scripts', 'project.py')
        out = self._run([
            'python', cmd, '--test', 'modules.math.math_tests'])
        self.assert_contains(
            'modules.math.math_tests.MathTagTests', out)


class ModuleManifest(object):
    """Provides parsing and access to modules/*/manifest.yaml."""

    def __init__(self, module_name, manifest_fn=None, manifest_data=None):
        self.name = module_name
        self.files = None
        self.tests = None
        self.unit = None
        self.functional = None
        self.integration = None
        self.data = self._parse(manifest_fn, manifest_data)

    def get_schema(self):
        self.files = schema_fields.FieldArray(
            'files', 'Module files',
            item_type=schema_fields.SchemaField(
                'filename', 'Filename', 'string'))

        self.unit = schema_fields.FieldArray(
            'unit', 'Unit test classes',
            item_type=schema_fields.SchemaField(
                'entry', 'module.module.ClassName = test_count', 'string'))

        self.functional = schema_fields.FieldArray(
          'functional', 'Functional test classes',
          item_type=schema_fields.SchemaField(
              'entry', 'module.module.ClassName = test_count', 'string'))

        self.integration = schema_fields.FieldArray(
            'integration', 'Integration test classes',
            item_type=schema_fields.SchemaField(
                'entry', 'module.module.ClassName = test_count', 'string'))

        tests = schema_fields.FieldRegistry('tests_registry')
        tests.add_property(self.unit)
        tests.add_property(self.functional)
        tests.add_property(self.integration)

        manifest = schema_fields.FieldRegistry('manifest')
        manifest.add_property(self.files)
        self.tests = manifest.add_sub_registry(
            'tests',
            title='Unit, functional and integration tests', registry=tests)

        return manifest

    def _parse(self, manifest_fn=None, manifest_data=None):
        if not (manifest_fn or manifest_data):
            raise Exception('Either manifest_fn or manifest_data is required.')
        if manifest_data:
            data = yaml.load(manifest_data)
        else:
            data = yaml.load(open(manifest_fn))

        complaints = schema_transforms.validate_object_matches_json_schema(
            data, self.get_schema().get_json_schema_dict())
        if complaints:
            raise Exception('Failed to parse manifest file %s: %s' % (
                manifest_fn, complaints))
        if 'manifest.yaml' not in [os.path.basename(f) for f in data['files']]:
            raise Exception('Manifest must name itself in the "files" section.')
        return data

    def _test_line_to_dict(self, line):
        parts = line.split('=')
        if not len(parts) == 2:
            raise Exception(
                'Expected module.package.ClassName = test_count, '
                'found "%s"' % line)
        if not parts[0].strip().startswith('modules.%s' % self.name):
            raise Exception(
                'Test name "%s" must start with the '
                'module name "%s"' % (parts[0].strip(), self.name))
        return {parts[0].strip(): int(parts[1].strip())}

    def get_tests(self):
        integration_tests = {}
        non_integration_tests = {}
        tests = self.data.get(self.tests.name)
        if tests:
            for test_type in [
                    self.unit.name,
                    self.functional.name]:
                tests_for_type = tests.get(test_type)
                if tests_for_type:
                    for test in tests_for_type:
                        non_integration_tests.update(
                            self._test_line_to_dict(test))
            integration = tests.get(self.integration.name)
            if integration:
                for test in integration:
                    integration_tests.update(
                        self._test_line_to_dict(test))
        return integration_tests, non_integration_tests


class ModulesRepo(object):
    """Provides access to all extension modules and their metadata."""

    def __init__(self, config):
        self.config = config
        self.modules_dir = os.path.join(self.config.build_dir, 'modules')
        self.modules = self._get_modules()
        self.module_to_manifest = self._get_manifests()
        log(
            'Found %s modules with %s manifests' % (
                len(self.modules), len(self.module_to_manifest.keys())))

    def _get_modules(self):
        modules = []
        for (dirpath, dirnames, _) in os.walk(self.modules_dir):
            for dirname in dirnames:
                modules.append(dirname)
            del dirnames[:]
        modules.sort()
        return modules

    def _get_manifests(self):
        modules_to_manifest = {}
        for module in self.modules:
            manifest_fn = os.path.join(
                self.modules_dir, module, 'manifest.yaml')
            if os.path.isfile(manifest_fn):
                modules_to_manifest[module] = ModuleManifest(
                    module, manifest_fn=manifest_fn)
        return modules_to_manifest


class FilesRepo(object):
    """Provides access to all files."""

    def __init__(self, config):
        self.config = config

        self.known_files = self._get_known_files()
        self.module_known_files = self._get_module_known_files()
        self.all_known_files = self.known_files + self.module_known_files
        self.all_known_files.sort()
        log('Modules bring %s new files' % (
            len(self.module_known_files)))

    def _get_known_files(self):
        file_list_fn = '%s/scripts/all_files.txt' % self.config.build_dir
        return open(file_list_fn).read().splitlines()

    def _get_module_known_files(self):
        known_files = []
        for manifest in self.config.modules.module_to_manifest.values():
            files = manifest.data.get('files')
            if files:
                known_files += files
        return known_files


class TestsRepo(object):
    """Provides acces to all known tests."""

    def __init__(self, config):
        self.config = config
        self.integration_tests = all_tests.ALL_INTEGRATION_TEST_CLASSES
        self.non_integration_tests = all_tests.ALL_TEST_CLASSES
        if config:
            integration_tests, non_integration_tests = self._get_modules_tests()
            self.integration_tests.update(integration_tests)
            self.non_integration_tests.update(non_integration_tests)
            self.non_integration_tests.update(self._get_all_third_party_tests())

    def _get_all_third_party_tests(self):
        yaml_path = os.path.join(
            self.config.build_dir, 'scripts', 'third_party_tests.yaml')
        if os.path.exists(yaml_path):
            with open(yaml_path) as fp:
                data = yaml.load(fp)
            return data['tests']
        else:
            return {}

    def _get_modules_tests(self):
        integration_tests = {}
        non_integration_tests = {}
        for manifest in self.config.modules.module_to_manifest.values():
            module_integration_tests, module_non_integration_tests = (
                manifest.get_tests())
            integration_tests.update(module_integration_tests)
            non_integration_tests.update(module_non_integration_tests)
        log(
            'Modules bring %s integration and %s non-integration tests' % (
                len(integration_tests), len(non_integration_tests)))
        return integration_tests, non_integration_tests

    def select_tests_to_run(self, test_class_name):
        test_classes = {}
        test_classes.update(self.integration_tests)
        test_classes.update(self.non_integration_tests)

        if test_class_name:
            _test_classes = {}

            for name in test_classes.keys():
                # try matching '*'
                if TEST_CLASS_NAME_ANY == test_class_name:
                    _test_classes.update({name: test_classes[name]})
                    continue

                # try matching on the class name
                if name.find(test_class_name) == 0:
                    _test_classes.update({name: test_classes[name]})
                    continue

                # try matching on the method name
                if test_class_name.find(name) == 0:
                    _test_classes.update({test_class_name: 1})
                    continue

            if not _test_classes:
                raise Exception(
                    'No tests found for "%s".  (Did you remember to add the '
                    'test class to scripts/all_tests.py or your module''s '
                    'manifest.yaml file)?' % test_class_name)

            test_classes = _test_classes
            sorted_names = sorted(
                test_classes, key=lambda key: test_classes[key])

        return test_classes

    def is_a_member_of(self, test_class_name, set_of_tests):
        for name in set_of_tests.keys():

            # try matching on the class name
            if name.find(test_class_name) == 0:
                return True

            # try matching on the method name
            if test_class_name.find(name) == 0:
                return True

        return False

    def _parse_test_name(self, name):
        """Attempts to convert the argument to a dotted test name.

        If the test name is provided in the format output by unittest error
        messages (e.g., "my_test (tests.functional.modules_my.MyModuleTest)")
        then it is converted to a dotted test name
        (e.g., "tests.functional.modules_my.MyModuleTest.my_test"). Otherwise
        it is returned unmodified.
        """

        if not name:
            return name

        match = re.match(
            r"\s*(?P<method_name>\S+)\s+\((?P<class_name>\S+)\)\s*", name)
        if match:
            return "{class_name}.{method_name}".format(
                class_name=match.group('class_name'),
                method_name=match.group('method_name'),
            )
        else:
            return name

    def group_tests(self):
        # get all applicable tests
        test_classes = self.select_tests_to_run(
            self._parse_test_name(self.config.parsed_args.test))

        # separate out integration and non-integration tests
        integration_tests = {}
        non_integration_tests = {}
        for test_class_name in test_classes.keys():
            if self.is_a_member_of(
                test_class_name, self.integration_tests):
                target = integration_tests
            else:
                target = non_integration_tests
            target.update(
                    {test_class_name: test_classes[test_class_name]})

        # filter out according to command line args
        if self.config.parsed_args.skip_non_integration:
            log('Skipping non-integration tests at user request')
            non_integration_tests = {}
        if self.config.parsed_args.skip_integration:
            log('Skipping integration test at user request')
            integration_tests = {}

        _all_tests = {}
        _all_tests.update(non_integration_tests)
        _all_tests.update(integration_tests)

        return _all_tests, integration_tests, non_integration_tests


class ReleaseConfiguration(object):
    """Contains data and methods for a particular release configuration."""

    def __init__(self, parsed_args, _build_dir):
        self.parsed_args = parsed_args
        self.build_dir = os.path.abspath(_build_dir)
        self.modules = ModulesRepo(self)
        self.files = FilesRepo(self)
        self.tests = TestsRepo(self)


def walk_folder_tree(home_dir, skip_rel_dirs=None):
    fileset = set()
    for dir_, _, files in os.walk(home_dir):
        reldir = os.path.relpath(dir_, home_dir)
        if skip_rel_dirs:
            skip = False
            for skip_rel_dir in skip_rel_dirs:
                if reldir.startswith('%s%s' % (skip_rel_dir, os.sep)):
                    skip = True
                    break
            if skip:
                continue
        for filename in files:
            relfile = os.path.join(reldir, filename)
            fileset.add(relfile)
    return sorted(list(fileset))


def write_text_file(file_name, text):
    afile = open(file_name, 'w')
    afile.write(text)
    afile.close()


def _create_manifests(_build_dir, release_label):
    manifest_file = os.path.join(_build_dir, 'VERSION')
    third_party_file = os.path.join(_build_dir, 'lib/README')

    write_text_file(manifest_file, 'Release: %s' % release_label)
    write_text_file(
        third_party_file,
        """
        This folder contains various third party packages that Course Builder
        depends upon. These packages are not developed by Google Inc., but
        provided by the open-source developer community. Please review the
        licensing terms for each individual package before use.""")


def purge(dir_name, pattern):
    """Deletes files matching pattern from a directory tree."""
    for f in os.listdir(dir_name):
        current = os.path.join(dir_name, f)
        if not os.path.isfile(current):
            purge(current, pattern)
        else:
            if re.search(pattern, f):
                os.remove(current)


def remove_dir(dir_name):
    """Deletes a directory."""
    if os.path.exists(dir_name):
        shutil.rmtree(dir_name)
        if os.path.exists(dir_name):
            raise Exception('Failed to delete directory: %s' % dir_name)


def chmod_dir_recursive(folder_name, mode):
    """Removes read-only attribute from all files and folders recursively."""
    for root, unused_dirs, files in os.walk(folder_name):
        for fname in files:
            full_path = os.path.join(root, fname)
            os.chmod(full_path, mode)


def _zip_all_files(target_dir, release_label):
    """Build and test a release zip file."""
    zip_file_name = os.path.join(
        target_dir, '%s_%s.zip' % (PRODUCT_NAME, release_label))

    log('Zipping: %s' % zip_file_name)

    chmod_dir_recursive(build_dir(), 0o777)

    # build it
    _out = zipfile.ZipFile(zip_file_name, 'w')
    for root, unused_dirs, files in os.walk(build_dir()):
        base = '/'.join(root.split('/')[3:])
        base = os.path.join(PRODUCT_NAME, base)
        for afile in files:
            _out.write(os.path.join(root, afile),
                           os.path.join(base, afile))
    _out.close()

    # verify it
    _in = zipfile.ZipFile(zip_file_name, 'r')
    _in.testzip()
    for afile in _in.filelist:
        date = '%d-%02d-%02d %02d:%02d:%02d' % afile.date_time[:6]
    _in.close()


def get_import_target(line):
    """Canonicalize import statements into a reliable form.

    All of

        import foo.bar.baz
        from foo.bar import baz
        from foo.bar import baz as quux

    are canonicalized to

        foo.bar.baz

    Returns None if line does not contain an import statement. Note that we will
    not catch imports done with advanced techniques (__import__, etc.).
    """
    target = None

    match = re.search(r'^import\ (.+)$', line)
    if match:
        target = match.groups()[0]
    else:
        match = re.search(r'^from\ (\S+)\ import\ (\S+)(\ as\ .+)?$', line)
        if match:
            target = '%s.%s' % tuple(match.groups()[0:2])

    return target


def is_disallowed_import_exception(path, target):
    return target in DISALLOWED_IMPORTS_EXCEPTIONS.get(path, [])


def _assert_no_disallowed_imports(root):
    for cb_path in walk_folder_tree(root):
        if not os.path.splitext(cb_path)[1] == PY_FILE_SUFFIX:
            continue

        if cb_path.startswith('./'):
            cb_path = cb_path[2:]

        with open(os.path.join(root, cb_path)) as f:
            for line in f.readlines():
                target = get_import_target(line.strip())

                if (target in DISALLOWED_IMPORTS and not
                    is_disallowed_import_exception(cb_path, target)):
                    raise Exception(
                        'Found disallowed import of "%s" in file: %s' % (
                            target, cb_path))
    log('No banned imports found')


def count_files_in_dir(dir_name, suffix=None):
    """Counts files with a given suffix, or all files if suffix is None."""

    count = 0
    for f in os.listdir(dir_name):
        current = os.path.join(dir_name, f)
        if os.path.isfile(current):
            if not suffix or current.endswith(suffix):
                count += 1
        else:
            count += count_files_in_dir(current, suffix=suffix)
    return count


def _enforce_file_count(config):
    """Check that we have exactly the files we expect; delete extras."""
    skip_rel_dirs = ['_static']
    known_files = config.files.all_known_files

    # verify mo files
    count_mo_files = count_files_in_dir(
        config.build_dir, suffix='.mo')
    if count_mo_files != EXPECTED_MO_FILE_COUNT:
        raise Exception('Expected %s .mo catalogue files, found %s' %
                        (EXPECTED_MO_FILE_COUNT, count_mo_files))

    if known_files:
        # list files
        all_files = walk_folder_tree(
            config.build_dir, skip_rel_dirs=skip_rel_dirs)

        # delete extras
        remove_count = 0
        for afile in all_files:
            if afile not in known_files:
                fn = os.path.join(config.build_dir, afile)
                os.remove(fn)
                remove_count += 1
        if remove_count:
            log('WARNING: removed %s unlisted files' % remove_count)

        # list files again; check no extras
        all_files = walk_folder_tree(
            config.build_dir, skip_rel_dirs=skip_rel_dirs)
        if all_files != known_files:
            diff = difflib.unified_diff(
                all_files, known_files, lineterm='')
            raise Exception(
                'Folder contents differs from expected:\n%s' % (
                      '\n'.join(list(diff))))
    if known_files:
        log('File count enforced: %s *.mo amongst %s other known files' % (
            EXPECTED_MO_FILE_COUNT, len(known_files)))
    else:
        log('File count enforced: %s *.mo files' % EXPECTED_MO_FILE_COUNT)


def _setup_all_dependencies():
    """Setup all third party Python packages."""
    common_sh = os.path.join(build_dir(), 'scripts', 'common.sh')
    log('Installing dependencies by running %s' % common_sh)
    result, output = run(['sh', common_sh], strict=True)
    if result != 0:
        raise Exception()

    for line in output.split('\n'):
        if not line:
            continue
        # ignore garbage produced by the script; it proven impossible to fix the
        # script to avoid garbage from being produced
        if 'grep: write error' in line or 'grep: writing output' in line:
            continue
        log(line)


def assert_handler(url, handler):
    """Verifies (via response headers) that URL is not served by CB handler."""
    last_attempt = 4
    url = INTEGRATION_SERVER_BASE_URL + url

    for attempt in xrange(1, last_attempt):
        try:
            result = urllib2.urlopen(url, timeout=10)
            break
        except urllib2.URLError as e:
            # Sometimes the server has not yet restarted and connections are
            # refused, so the timeout mechanism won't retry. Do it manually.
            log('Unable to open %s on attempt %s' % (url, attempt))
            if attempt != last_attempt - 1:
                time.sleep(5)
    else:
        raise e

    assert result.getcode() == 200

    headers = dict(result.headers)
    specified_handler = headers.get(GCB_HANDLER_CLASS_HEADER_NAME, None)

    if not specified_handler == handler:
        raise Exception(
            'Failed to find header %s with value %s in url %s '
            'having response headers %s' % (
            GCB_HANDLER_CLASS_HEADER_NAME, handler, url, headers))


def assert_gcb_allow_static_serv_is_disabled():
    log('Making sure static serving disabled')
    assert not os.path.exists(os.path.join(build_dir(), 'lib', '_static'))
    for url, handler in STATIC_SERV_URLS:
        assert_handler(url, handler)
    for  url, handler in COMBO_SERV_URLS:
        assert_handler(url, handler)


def assert_gcb_allow_static_serv_is_enabled():
    log('Making sure static serving enabled')
    assert os.path.exists(os.path.join(build_dir(), 'lib', '_static'))
    for url, _ in STATIC_SERV_URLS:
        assert_handler(url, None)


def _run_all_tests(config, setup_deps=True):
    _all_tests, integration_tests, non_integration_tests = (
        config.tests.group_tests())

    with_server = bool(integration_tests)
    test_static_serv = not bool(config.parsed_args.test)

    if test_static_serv and with_server:
        with WithReleaseConfiguration(True, False, config):
            assert_gcb_allow_static_serv_is_disabled()

    with WithReleaseConfiguration(with_server, True, config):
        if with_server:
            if test_static_serv:
                assert_gcb_allow_static_serv_is_enabled()
            _run_tests(
                {
                  'tests.integration.test_classes.'
                  'IntegrationServerInitializationTask': 1},
                False, setup_deps=False, chunk_size=1, hint='setup')
        if _all_tests:
            try:
                chunk_size = 2 * multiprocessing.cpu_count()
            except:  # pylint: disable=bare-except
                chunk_size = 8
            _run_tests(
                _all_tests, config.parsed_args.verbose,
                setup_deps=setup_deps, chunk_size=chunk_size)


def _run_tests(
    test_classes, verbose, setup_deps=True, chunk_size=16, hint='generic'):
    start = time.time()
    task_to_test = {}
    tasks = []
    integration_tasks = []

    # Prepare tasks
    for test_class_name in test_classes:
        test = FunctionalTestTask(test_class_name, verbose)
        task = TaskThread(test.run, name='testing %s' % test_class_name)
        task_to_test[task] = test
        tasks.append(task)

    # order tests by their size largest to smallest
    tasks = sorted(
        tasks,
        key=lambda task: test_classes.get(task_to_test[task].test_class_name),
        reverse=True)

    # setup dependencies
    if setup_deps:
        _setup_all_dependencies()

    # execute all tasks
    log('Executing %s "%s" test suites' % (len(tasks), hint))
    runtimes_sec = []
    TaskThread.execute_task_list(
        tasks, chunk_size=chunk_size, runtimes_sec=runtimes_sec)

    # map durations to names
    name_durations = []
    for index, duration in enumerate(runtimes_sec):
        name_durations.append((
            round(duration, 2), task_to_test[tasks[index]].test_class_name))

    # report all longest first
    if name_durations:
        log('Reporting execution times for upto 10 longest tests')
    for duration, name in sorted(
        name_durations, key=lambda name_duration: name_duration[0],
        reverse=True)[:10]:
        log('Took %ss for %s' % (int(duration), name))

    # Check we ran all tests as expected.
    total_count = 0
    for task in tasks:
        test = task_to_test[task]
        # Check that no unexpected tests were picked up via automatic discovery,
        # and that the number of tests run in a particular suite.py invocation
        # matches the expected number of tests.
        test_count = test_classes.get(test.test_class_name, None)
        expected_text = 'INFO: All %s tests PASSED!' % test_count
        if test_count is None:
            log('%s\n\nERROR: ran unexpected test class %s' % (
                test.output, test.test_class_name))
        if expected_text not in test.output:
            log('%s\n\nERROR: Expected %s tests to be run for the test class '
                '%s, but found some other number.' % (
                    test.output, test_count, test.test_class_name))
            raise Exception()
        total_count += test_count

    log('Ran %s tests in %s test classes; took %ss' % (
        total_count, len(tasks), int(time.time() - start)))


def _run_lint():
    # Wire outputs to our own stdout/stderr so messages appear immediately,
    # rather than batching up and waiting for the end (linting takes a while)
    path = os.path.join(build_dir(), 'scripts', 'pylint.sh')
    status = subprocess.call(path, stdin=None, stdout=sys.stdout,
                             stderr=sys.stderr)
    return status == 0


def _dry_run(parsed_args):
    _run_tests(
        all_tests.INTERNAL_TEST_CLASSES,
        parsed_args.verbose, setup_deps=False, hint="dry run")


def _lint(parsed_args):
    if parsed_args.skip_pylint:
        log('Skipping pylint at user request')
    else:
        if not _run_lint():
            if parsed_args.ignore_pylint_failures:
                log('Ignoring pylint test errors.')
            else:
                raise RuntimeError('Pylint tests failed.')


def _prepare_filesystem(
    source_dir_name, target_dir_name, build_dir_name, deep_clean=False):
    """Prepare various directories used in the release process."""

    log('Working directory: %s' % os.getcwd())
    log('Source directory: %s' % source_dir_name)
    log('Target directory: %s' % target_dir_name)
    log('Build temp directory: %s' % build_dir_name)

    remove_dir(build_dir_name)
    shutil.copytree(source_dir_name, build_dir_name, symlinks=True)
    shell_env = _get_config_sh_shell_env()

    if deep_clean:
        dirs_to_remove = [
            os.path.join(
                os.path.expanduser("~"),
                _get_coursebuilder_resources_path(shell_env)),
            os.path.join(build_dir_name, 'lib')
            ]
        log('Deep cleaning %s' % ', '.join(dirs_to_remove))
        for _dir in dirs_to_remove:
            remove_dir(_dir)

    if not os.path.exists(target_dir_name):
        log('Creating target directory: %s' % target_dir_name)
        os.makedirs(target_dir_name)


def _save_log(target_dir, release_label):
    log_file = os.path.join(target_dir, 'log_%s.txt' % release_label)
    log('Saving log to: %s' % log_file)
    write_text_file(log_file, '%s' % '\n'.join(LOG_LINES))


def _test_developer_workflow(config):
    DeveloperWorkflowTester(config).test_all()


def _set_up_imports():
    global schema_fields
    global schema_transforms
    global all_tests

    # when this runs, the environment is not yet setup; as a minimum,
    # we need access to our own code; provide it here
    sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

    # no third party packages are available or will ever be available in this
    # module including Google App Engine SDK, but we can safely access our own
    # code, IF AND ONLY IF, it does not have any dependencies
    # pylint: disable=redefined-outer-name
    from common import schema_fields
    from common import schema_transforms
    from scripts import all_tests


def _do_a_release(source_dir, target_dir, release_label):
    """Creates/validates an official release of CourseBuilder.

    Args:
        source_dir: a string specifying source folder for the project
        target_dir: a string specifying target folder for output
        build_dir: a string specifying temp folder to do a build in
        release_label: a string with text label for the release

    Here is what this function does:
        - creates a target_dir, build_dir; cleans temp directories
        - copies all files from source_dir to the build_dir
        - deletes all files from build_dir that should not be released
        - adds VERSION and manifest file
        - scans all modules and adds tests/files listed in manifests
        - sets up all third party dependencies
        - brings up and tears down integration server
        - checks banned imports
        - tests developer workflow
        - runs all tests in the build_dir and checks they pass
        - creates a zip file
        - copies a resulting zip file and log file to target_dir
    """
    del LOG_LINES[:]

    parsed_args = make_default_parser().parse_args()

    start = time.time()
    log('Starting Course Builder release: %s' % release_label)

    _prepare_filesystem(
        source_dir, target_dir, build_dir(), deep_clean=parsed_args.deep_clean)
    _setup_all_dependencies()
    _create_manifests(build_dir(), release_label)
    config = ReleaseConfiguration(parsed_args, build_dir())
    _dry_run(parsed_args)
    _lint(parsed_args)
    _assert_no_disallowed_imports(build_dir())
    _test_developer_workflow(config)
    _enforce_file_count(config)
    _run_all_tests(config, setup_deps=False)
    _enforce_file_count(config)
    _zip_all_files(target_dir, release_label)
    remove_dir(build_dir())
    _save_log(target_dir, release_label)

    log('Done release in %ss: find results in %s' % (
        int(time.time() - start), target_dir))

    return 0


def _test_only(parsed_args):
    """Runs a set of tests as specific by command line arguments."""
    global BUILD_DIR  # pylint: disable=global-statement
    BUILD_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

    log('Running task "test": %s' % parsed_args)
    log('Working directory: %s' % os.getcwd())
    log('Source directory: %s' % build_dir())
    if parsed_args.deep_clean:
        raise Exception(
            'Unable to use --deep_clean flag without --do_a_release flag.')
    _setup_all_dependencies()
    if not parsed_args.test:
        _lint(parsed_args)
    return _run_all_tests(ReleaseConfiguration(parsed_args, BUILD_DIR))


def _test_and_release(parsed_args):
    """Runs an entire release process with all tests and configurations."""
    release_label = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')

    global BUILD_DIR  # pylint: disable=global-statement
    BUILD_DIR = '/tmp/%s-build-%s' % (PRODUCT_NAME, release_label)

    log('Running task "release": %s' % parsed_args)
    return _do_a_release(
        os.path.abspath(os.path.join(os.path.dirname(__file__), '..')),
        os.getcwd(), release_label)


def _get_config_sh_shell_env():
    config_sh = os.path.join(os.path.dirname(__file__), 'config.sh')
    output = subprocess.check_output(
        'source %s; env -0' % config_sh, executable='/bin/bash', shell=True)

    env = {}
    for line in output.split('\0'):
        parts = line.split('=')
        env[parts[0]] = parts[-1]

    return env


def _get_coursebuilder_resources_path(shell_env):
    coursebuilder_resources_path = shell_env.get('COURSEBUILDER_RESOURCES')
    assert coursebuilder_resources_path

    return coursebuilder_resources_path


def main():
    parsed_args = make_default_parser().parse_args()
    if parsed_args.release:
        return _test_and_release(parsed_args)
    if parsed_args.test:
        return _test_only(parsed_args)
    return make_default_parser().print_help()


if __name__ == '__main__':
    _set_up_imports()
    main()
