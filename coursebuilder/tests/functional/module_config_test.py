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

"""Test module configuration script."""

__author__ = 'Mike Gainer (mgainer@google.com)'

import cStringIO
import logging
import os
import shutil
import sys
import tempfile
import traceback
import unittest

import appengine_config
from common import yaml_files
from scripts import modules as module_config


class TestWithTempDir(unittest.TestCase):

    def setUp(self):
        super(TestWithTempDir, self).setUp()
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        super(TestWithTempDir, self).tearDown()
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _dump_dir(self, _, dirname, names):
        for name in names:
            path = os.path.join(dirname, name)
            if not os.path.isdir(path):
                print '-------------------------', path
                with open(path) as fp:
                    print fp.read()

    def _dump_tree(self):
        os.path.walk(self._tmpdir, self._dump_dir, None)

    def _write_content(self, path, content):
        with open(path, 'w') as fp:
            for line in content:
                fp.write(line)

    def _assert_content_equals(self, path, expected_lines):
        with open(path) as fp:
            actual_lines = fp.readlines()
        self.assertEquals(expected_lines, actual_lines)


class ManipulateAppYamlFileTest(TestWithTempDir):

    def setUp(self):
        super(ManipulateAppYamlFileTest, self).setUp()
        self._yaml_path = os.path.join(self._tmpdir, 'app.yaml')
        self._minimal_content = [
            '\n',
            '\n',
            'libraries:\n',
            '- name: jinja2\n',
            '  version: "2.6"\n',
            '\n',
            'env_variables:\n',
            '  FOO: bar\n',
            '  BAR: bleep\n',
            ]

    def test_read_write_unchanged(self):
        parsed_content = (
            '\n'
            '\n'
            'libraries:\n'
            '- name: jinja2\n'
            '  version: "2.6"\n'
            '\n'
            'env_variables:\n'
            '  FOO: bar\n'
            'scalar_str: "string"\n'
            'scalar_int: 123\n'
            'scalar_bool: true\n'
            'dict:\n'
            '  foo1: bar\n'
            '  foo2: 123\n'
            '  foo3: true\n'
            'list:\n'
            '- name: blah\n'
            '  value: 123\n'
            '- name: blahblah\n'
            '- value: 999\n'
            )
        with open(self._yaml_path, 'w') as fp:
            fp.write(parsed_content)
        app_yaml = yaml_files.AppYamlFile(self._yaml_path)
        app_yaml.write()
        with open(self._yaml_path) as fp:
            written_content = fp.read()
        self.assertEquals(parsed_content, written_content)

    def test_get_env_var(self):
        self._write_content(self._yaml_path, self._minimal_content)
        app_yaml = yaml_files.AppYamlFile(self._yaml_path)
        self.assertEquals('bar', app_yaml.get_env('FOO'))
        self.assertEquals('bleep', app_yaml.get_env('BAR'))

    def test_add_env_var(self):
        self._write_content(self._yaml_path, self._minimal_content)
        app_yaml = yaml_files.AppYamlFile(self._yaml_path)
        app_yaml.set_env('BAZ', 'bar')
        self.assertEquals('bar', app_yaml.get_env('BAZ'))
        app_yaml.write()

        expected = self._minimal_content + ['  BAZ: bar\n']
        self._assert_content_equals(self._yaml_path, expected)

    def test_overwrite_env_var(self):
        self._write_content(self._yaml_path, self._minimal_content)
        app_yaml = yaml_files.AppYamlFile(self._yaml_path)
        app_yaml.set_env('FOO', 'foo')
        self.assertEquals('foo', app_yaml.get_env('FOO'))
        app_yaml.write()

        expected = (
            self._minimal_content[:7] +
            ['  FOO: foo\n'] +
            self._minimal_content[8:])
        self._assert_content_equals(self._yaml_path, expected)

    def test_clear_env_var(self):
        self._write_content(self._yaml_path, self._minimal_content)
        app_yaml = yaml_files.AppYamlFile(self._yaml_path)
        app_yaml.set_env('BAR', '')
        self.assertIsNone(app_yaml.get_env('BAR'))
        app_yaml.write()

        expected = self._minimal_content[:-1]
        self._assert_content_equals(self._yaml_path, expected)

    def test_require_existing_library(self):
        self._write_content(self._yaml_path, self._minimal_content)
        app_yaml = yaml_files.AppYamlFile(self._yaml_path)
        app_yaml.require_library('jinja2', '2.6')
        app_yaml.write()

        expected = self._minimal_content
        self._assert_content_equals(self._yaml_path, expected)

    def test_require_new_library(self):
        self._write_content(self._yaml_path, self._minimal_content)
        app_yaml = yaml_files.AppYamlFile(self._yaml_path)
        app_yaml.require_library('frammis', '1.2')
        app_yaml.write()

        expected = (
            self._minimal_content[:3] +
            ['- name: frammis\n',
             '  version: "1.2"\n'] +
            self._minimal_content[3:])
        self._assert_content_equals(self._yaml_path, expected)

    def test_require_different_version_of_library(self):
        self._write_content(self._yaml_path, self._minimal_content)
        app_yaml = yaml_files.AppYamlFile(self._yaml_path)
        with self.assertRaises(ValueError):
            app_yaml.require_library('jinja2', '2.1')


class ModuleManifestTest(TestWithTempDir):

    def setUp(self):
        super(ModuleManifestTest, self).setUp()
        self._manifest_path = os.path.join(self._tmpdir,
                                           module_config._MANIFEST_NAME)

    def test_manifest_must_contain_module(self):
        with open(self._manifest_path, 'w') as fp:
            fp.write('foo: bar\n')
        with self.assertRaises(KeyError):
            # pylint: disable=expression-not-assigned
            yaml_files.ModuleManifest(self._manifest_path).module_name

    def test_module_name_must_name_full_python_module(self):
        with open(self._manifest_path, 'w') as fp:
            fp.write('module_name: bar\n')
        with self.assertRaises(ValueError):
            # pylint: disable=expression-not-assigned
            yaml_files.ModuleManifest(self._manifest_path).module_name

    def test_module_name_must_start_with_modules(self):
        with open(self._manifest_path, 'w') as fp:
            fp.write('module_name: bar.baz\n')
        with self.assertRaises(ValueError):
            # pylint: disable=expression-not-assigned
            yaml_files.ModuleManifest(self._manifest_path).module_name

    def test_manifest_must_have_container_version(self):
        with open(self._manifest_path, 'w') as fp:
            fp.write('module_name: modules.bar.bar_module\n')
        with self.assertRaises(KeyError):
            # pylint: disable=expression-not-assigned
            yaml_files.ModuleManifest(self._manifest_path).module_name

    def test_manifest_must_have_tests(self):
        with open(self._manifest_path, 'w') as fp:
            fp.write(
                'module_name: modules.bar.bar_module\n'
                'container_version: 1.3\n'
                )
        with self.assertRaises(KeyError):
            # pylint: disable=expression-not-assigned
            yaml_files.ModuleManifest(self._manifest_path).module_name

    def test_minimal_manifest(self):
        with open(self._manifest_path, 'w') as fp:
            fp.write(
                'module_name: modules.foo.foo_module\n'
                'container_version: 1.2.3\n'
                'tests:\n'
                '  this: 1\n'
                '  that: 2\n')
        manifest = yaml_files.ModuleManifest(self._manifest_path)
        self.assertEquals(manifest.module_name, 'foo')
        self.assertEquals(manifest.main_module, 'modules.foo.foo_module')
        self.assertEquals(manifest.third_party_libraries, {})
        self.assertEquals(manifest.appengine_libraries, {})
        self.assertEquals(manifest.tests, {'this': 1, 'that': 2})

    def test_version_compatibility(self):
        with open(self._manifest_path, 'w') as fp:
            fp.write(
                'module_name: modules.foo.foo_module\n'
                'container_version: 1.2.3\n'
                'tests:\n'
                '  this: 1\n'
                '  that: 2\n')
        manifest = yaml_files.ModuleManifest(self._manifest_path)
        manifest.assert_version_compatibility('1.2.3')
        manifest.assert_version_compatibility('1.2.4')
        manifest.assert_version_compatibility('1.3.0')
        manifest.assert_version_compatibility('2.0.0')

        with self.assertRaises(ValueError):
            manifest.assert_version_compatibility('1.2.2')
        with self.assertRaises(ValueError):
            manifest.assert_version_compatibility('1.1.9')
        with self.assertRaises(ValueError):
            manifest.assert_version_compatibility('0.9.9')


class ModuleIncorporationTest(TestWithTempDir):

    def _make_module(self, module_dir, module_name):
        with open(os.path.join(module_dir, '__init__.py'), 'w'):
            pass
        with open(os.path.join(module_dir, module_name), 'w') as fp:
            fp.write(
                'from models import custom_modules\n'
                'def register_module():\n'
                '  return custom_modules.Module("x", "x", [], [])'
                )

    def setUp(self):
        super(ModuleIncorporationTest, self).setUp()

        self.foo_dir = os.path.join(self._tmpdir, 'foo')
        self.foo_src_dir = os.path.join(self.foo_dir, 'src')
        self.foo_scripts_dir = os.path.join(self.foo_dir, 'scripts')
        self.bar_dir = os.path.join(self._tmpdir, 'bar')
        self.bar_src_dir = os.path.join(self.bar_dir, 'src')
        self.bar_scripts_dir = os.path.join(self.bar_dir, 'scripts')
        self.cb_dir = os.path.join(self._tmpdir, 'coursebuilder')
        self.cb_modules_dir = os.path.join(self.cb_dir, 'modules')
        self.scripts_dir = os.path.join(self.cb_dir, 'scripts')
        self.lib_dir = os.path.join(self.cb_dir, 'lib')
        self.modules_dir = os.path.join(self._tmpdir,
                                        self._get_resources_path_fragment(),
                                        'modules')
        for dirname in (self.foo_dir, self.foo_src_dir, self.foo_scripts_dir,
                        self.bar_dir, self.bar_src_dir, self.bar_scripts_dir,
                        self.cb_dir, self.scripts_dir, self.lib_dir,
                        self.cb_modules_dir, self.modules_dir):
            os.makedirs(dirname)

        foo_manifest_path = os.path.join(self.foo_dir,
                                         module_config._MANIFEST_NAME)
        with open(foo_manifest_path, 'w') as fp:
            fp.write(
                'module_name: modules.foo.foo_module\n'
                'container_version: 1.6.0\n'
                'tests:\n'
                '  tests.ext.foo.foo_tests.FooTest: 1\n'
                'third_party_libraries:\n'
                '- name: foo_stuff.zip\n')
        self._make_module(self.foo_src_dir, 'foo_module.py')
        foo_installer_path = os.path.join(self.foo_dir, 'scripts', 'setup.sh')
        with open(foo_installer_path, 'w') as fp:
            fp.write(
                '#!/bin/bash\n'
                'ln -s $(pwd)/src $2/modules/foo\n'
                'touch $2/lib/foo_stuff.zip\n'
                )

        bar_manifest_path = os.path.join(self.bar_dir,
                                         module_config._MANIFEST_NAME)
        with open(bar_manifest_path, 'w') as fp:
            fp.write(
                'module_name: modules.bar.bar_module\n'
                'container_version: 1.6.0\n'
                'tests:\n'
                '  tests.ext.bar.bar_tests.BarTest: 1\n'
                'appengine_libraries:\n'
                '- name: endpoints\n'
                '  version: "1.0"\n')
        self._make_module(self.bar_src_dir, 'bar_module.py')
        bar_installer_path = os.path.join(self.bar_dir, 'scripts', 'setup.sh')
        with open(bar_installer_path, 'w') as fp:
            fp.write(
                '#!/bin/bash\n'
                'ln -s $(pwd)/src $2/modules/bar\n'
                )

        self.initial_app_yaml = [
            'application: mycourse\n',
            'runtime: python27\n',
            'api_version: 1\n',
            'threadsafe: false\n',
            '\n',
            'env_variables:\n',
            '  GCB_PRODUCT_VERSION: "1.6.0"\n',
            '\n',
            'libraries:\n',
            '- name: jinja2\n',
            '  version: "2.6"\n',
            ]
        self.app_yaml_path = os.path.join(self.cb_dir, 'app.yaml')
        self._write_content(self.app_yaml_path, self.initial_app_yaml)
        self.third_party_tests_path = os.path.join(
            self.scripts_dir, 'third_party_tests.yaml')
        with open(os.path.join(self.cb_modules_dir, '__init__.py'), 'w'):
            pass

        self.log_stream = cStringIO.StringIO()
        self.old_log_handlers = list(module_config._LOG.handlers)
        module_config._LOG.handlers = [logging.StreamHandler(self.log_stream)]

        self.save_bundle_root = appengine_config.BUNDLE_ROOT
        appengine_config.BUNDLE_ROOT = self.cb_dir
        self.save_sys_path = sys.path
        sys.path.insert(0, self.cb_dir)
        self.save_modules = sys.modules.pop('modules')

    def tearDown(self):
        module_config._LOG.handlers = self.old_log_handlers
        appengine_config.BUNDLE_ROOT = self.save_bundle_root
        sys.path = self.save_sys_path
        sys.modules['modules'] = self.save_modules
        super(ModuleIncorporationTest, self).tearDown()

    def _install(self, modules_arg):
        if modules_arg:
            args = module_config.PARSER.parse_args([modules_arg])
        else:
            args = module_config.PARSER.parse_args([])
        try:
            module_config.main(args, self.cb_dir, self.modules_dir)
        except Exception, ex:
            self._dump_tree()
            traceback.print_exc()
            raise ex

    def _get_log(self):
        self.log_stream.flush()
        ret = self.log_stream.getvalue()
        self.log_stream.reset()
        return ret

    def _get_resources_path_fragment(self):
        return 'coursebuilder_resources_%s' % (
            os.environ['GCB_PRODUCT_VERSION'].replace('.', '_'))

    def _expect_logs(self, expected_lines):
        actual_lines = self._get_log().split('\n')
        for expected, actual in zip(expected_lines, actual_lines):
            self.assertIn(expected, actual)

    def test_install_foo(self):
        self._install('--targets=foo@%s' % self.foo_dir)
        expected = (
            self.initial_app_yaml[:7] +
            ['  GCB_THIRD_PARTY_LIBRARIES: foo_stuff.zip\n',
             '  GCB_THIRD_PARTY_MODULES: modules.foo.foo_module\n'] +
            self.initial_app_yaml[7:]
            )
        self._assert_content_equals(self.app_yaml_path, expected)

        expected = [
            'tests:\n',
            '  tests.ext.foo.foo_tests.FooTest: 1\n',
            ]
        self._assert_content_equals(self.third_party_tests_path, expected)

        expected = [
            'Downloading module foo',
            'Installing module foo',
            'Updating scripts/third_party_tests.yaml',
            'Updating app.yaml',
            'You should change this from its default',
            ]
        self._expect_logs(expected)

    def test_install_with_file_localhost_url(self):
        self._install('--targets=foo@file://localhost%s' %
                      os.path.abspath(self.foo_dir))
        expected = [
            'Downloading module foo',
            'Installing module foo',
            'Updating scripts/third_party_tests.yaml',
            'Updating app.yaml',
            'You should change this from its default',
            ]
        self._expect_logs(expected)

    def test_install_with_file_nohost_url(self):
        self._install('--targets=foo@file://%s' %
                      os.path.abspath(self.foo_dir))
        expected = [
            'Downloading module foo',
            'Installing module foo',
            'Updating scripts/third_party_tests.yaml',
            'Updating app.yaml',
            'You should change this from its default',
            ]
        self._expect_logs(expected)

    def test_install_with_relative_path_url(self):
        self._install('--targets=foo@file://%s' %
                      os.path.relpath(self.foo_dir))
        expected = [
            'Downloading module foo',
            'Installing module foo',
            'Updating scripts/third_party_tests.yaml',
            'Updating app.yaml',
            'You should change this from its default',
            ]
        self._expect_logs(expected)

    def test_install_with_relative_path(self):
        self._install('--targets=foo@%s' % os.path.relpath(self.foo_dir))
        expected = [
            'Downloading module foo',
            'Installing module foo',
            'Updating scripts/third_party_tests.yaml',
            'Updating app.yaml',
            'You should change this from its default',
            ]
        self._expect_logs(expected)

    def test_install_both(self):
        self._install('--targets=foo@%s,bar@%s' % (self.foo_dir, self.bar_dir))
        expected = (
            self.initial_app_yaml[:7] +
            ['  GCB_THIRD_PARTY_LIBRARIES: foo_stuff.zip\n',
             '  GCB_THIRD_PARTY_MODULES:\n',
             '    modules.foo.foo_module\n',
             '    modules.bar.bar_module\n'] +
            self.initial_app_yaml[7:9] +
            ['- name: endpoints\n',
             '  version: "1.0"\n',] +
            self.initial_app_yaml[9:]
            )
        self._assert_content_equals(self.app_yaml_path, expected)

        expected = [
            'tests:\n',
            '  tests.ext.bar.bar_tests.BarTest: 1\n',
            '  tests.ext.foo.foo_tests.FooTest: 1\n',
            ]
        self._assert_content_equals(self.third_party_tests_path, expected)

        expected = [
            'Downloading module foo',
            'Installing module foo',
            'Downloading module bar',
            'Installing module bar',
            'Updating scripts/third_party_tests.yaml',
            'Updating app.yaml',
            'You should change this from its default',
            ]
        self._expect_logs(expected)

    def test_reinstall_both(self):
        self._install('--targets=foo@%s,bar@%s' % (self.foo_dir, self.bar_dir))
        self._get_log()
        self._install('--targets=foo@%s,bar@%s' % (self.foo_dir, self.bar_dir))
        expected = (
            self.initial_app_yaml[:7] +
            ['  GCB_THIRD_PARTY_LIBRARIES: foo_stuff.zip\n',
             '  GCB_THIRD_PARTY_MODULES:\n',
             '    modules.foo.foo_module\n',
             '    modules.bar.bar_module\n'] +
            self.initial_app_yaml[7:9] +
            ['- name: endpoints\n',
             '  version: "1.0"\n',] +
            self.initial_app_yaml[9:]
            )
        self._assert_content_equals(self.app_yaml_path, expected)

        expected = [
            'tests:\n',
            '  tests.ext.bar.bar_tests.BarTest: 1\n',
            '  tests.ext.foo.foo_tests.FooTest: 1\n',
            ]
        self._assert_content_equals(self.third_party_tests_path, expected)

        expected = [
            'Updating scripts/third_party_tests.yaml',
            'Updating app.yaml',
            'You should change this from its default',
            ]
        self._expect_logs(expected)

    def test_reinstall_both_after_manual_removal(self):
        self._install('--targets=foo@%s,bar@%s' % (self.foo_dir, self.bar_dir))
        self._get_log()
        os.unlink(os.path.join(self.cb_dir, 'modules', 'foo'))
        os.unlink(os.path.join(self.cb_dir, 'modules', 'bar'))
        self._install('--targets=foo@%s,bar@%s' % (self.foo_dir, self.bar_dir))
        expected = (
            self.initial_app_yaml[:7] +
            ['  GCB_THIRD_PARTY_LIBRARIES: foo_stuff.zip\n',
             '  GCB_THIRD_PARTY_MODULES:\n',
             '    modules.foo.foo_module\n',
             '    modules.bar.bar_module\n'] +
            self.initial_app_yaml[7:9] +
            ['- name: endpoints\n',
             '  version: "1.0"\n',] +
            self.initial_app_yaml[9:]
            )
        self._assert_content_equals(self.app_yaml_path, expected)

        expected = [
            'tests:\n',
            '  tests.ext.bar.bar_tests.BarTest: 1\n',
            '  tests.ext.foo.foo_tests.FooTest: 1\n',
            ]
        self._assert_content_equals(self.third_party_tests_path, expected)

        expected = [
            'Installing module foo',
            'Installing module bar',
            'Updating scripts/third_party_tests.yaml',
            'Updating app.yaml',
            'You should change this from its default',
            ]
        self._expect_logs(expected)

    def test_install_both_then_reinstall_foo(self):
        self._install('--targets=foo@%s,bar@%s' % (self.foo_dir, self.bar_dir))
        self._get_log()
        self._install('--targets=foo@%s' % self.foo_dir)
        expected = (
            self.initial_app_yaml[:7] +
            ['  GCB_THIRD_PARTY_LIBRARIES: foo_stuff.zip\n',
             '  GCB_THIRD_PARTY_MODULES: modules.foo.foo_module\n'] +
            self.initial_app_yaml[7:9] +
            ['- name: endpoints\n',  # Note that AE lib requirement stays.
             '  version: "1.0"\n',] +
            self.initial_app_yaml[9:]
            )
        self._assert_content_equals(self.app_yaml_path, expected)

        expected = [
            'tests:\n',
            '  tests.ext.foo.foo_tests.FooTest: 1\n',
            ]
        self._assert_content_equals(self.third_party_tests_path, expected)

        expected = [
            'Updating scripts/third_party_tests.yaml',
            'Updating app.yaml',
            'You should change this from its default',
            ]
        self._expect_logs(expected)

    def test_install_both_then_reinstall_bar(self):
        self._install('--targets=foo@%s,bar@%s' % (self.foo_dir, self.bar_dir))
        self._get_log()
        self._install('--targets=bar@%s' % self.bar_dir)
        expected = (
            self.initial_app_yaml[:7] +
            ['  GCB_THIRD_PARTY_MODULES: modules.bar.bar_module\n'] +
            self.initial_app_yaml[7:9] +
            ['- name: endpoints\n',
             '  version: "1.0"\n',] +
            self.initial_app_yaml[9:]
            )
        self._assert_content_equals(self.app_yaml_path, expected)

        expected = [
            'tests:\n',
            '  tests.ext.bar.bar_tests.BarTest: 1\n',
            ]
        self._assert_content_equals(self.third_party_tests_path, expected)

        expected = [
            'Updating scripts/third_party_tests.yaml',
            'Updating app.yaml',
            'You should change this from its default',
            ]
        self._expect_logs(expected)

    def test_install_both_then_reinstall_none(self):
        self._install('--targets=foo@%s,bar@%s' % (self.foo_dir, self.bar_dir))
        self._get_log()
        self._install(None)
        expected = (
            self.initial_app_yaml[:9] +
            ['- name: endpoints\n',  # Note that AE lib requirement stays.
             '  version: "1.0"\n',] +
            self.initial_app_yaml[9:]
            )
        self._assert_content_equals(self.app_yaml_path, expected)
        self.assertFalse(os.path.exists(self.third_party_tests_path))
        expected = [
            'Updating app.yaml',
            'You should change this from its default',
            ]
        self._expect_logs(expected)

    def test_appengine_config(self):
        self._install('--targets=foo@%s,bar@%s' % (self.foo_dir, self.bar_dir))
        yaml = yaml_files.AppYamlFile(self.app_yaml_path)
        os.environ.update(yaml.get_all_env())

        # Touch into place the hard-coded expected set of libs so we don't
        # get spurious errors.
        for lib in appengine_config.ALL_LIBS:
            with open(lib.file_path, 'w'):
                pass

        # Just looking for no crash.
        appengine_config._import_and_enable_modules('GCB_THIRD_PARTY_MODULES',
                                                    reraise=True)
        appengine_config.gcb_init_third_party()
