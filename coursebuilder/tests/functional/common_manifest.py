# Copyright 2016 Google Inc. All Rights Reserved.
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

"""Tests for parsing and convenience functions for module manifest files."""

__author__ = [
    'Pavel Simakov (psimakov@google.com)',
    'Michael Gainer (mgainer@google.com)'
]

import unittest

from common import manifests


class ModuleManifestTests(unittest.TestCase):

    def test_module_manifest_is_parsed(self):
        manifest_data = '''
            registration:
                main_module: modules.sample.sample
                enabled: False
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
        manifest = manifests.ModuleManifest('sample',
                                            manifest_data=manifest_data)

        assert manifest.data['tests']['unit'][0] == 'modules.sample.foo = 5'
        assert manifest.data[
            'tests']['functional'][0] == 'modules.sample.baz = 6'
        assert manifest.data[
            'tests']['integration'][0] == 'modules.sample.bar = 7'
        assert manifest.data['files'] == ['foo', 'bar', 'baz', 'manifest.yaml']

        integration, non_integration = manifest.get_tests()
        assert 1 == len(integration)
        assert 2 == len(non_integration)
        self.assertEquals('modules.sample.sample',
                          manifest.get_registration().main_module)
        self.assertFalse(manifest.get_registration().enabled)

    def test_registration_section_not_mandatory(self):
        manifest_data = '''
            files:
                - manifest.yaml
            '''
        manifest = manifests.ModuleManifest('sample',
                                            manifest_data=manifest_data)

        # Verify default settings.
        self.assertIsNone(manifest.get_registration().main_module)
        self.assertTrue(manifest.get_registration().enabled)


    def test_module_manifest_is_validated_1(self):
        manifest_data = '''
            tests:
                unknown:
                    - foo = 7
            files:
                - manifest.yaml
            '''
        with self.assertRaises(Exception):
            manifests.ModuleManifest('sample', manifest_data=manifest_data)

    def test_module_manifest_is_validated_2(self):
        manifest_data = '''
            tests:
                unit:
                    - foo : bar
            files:
                - manifest.yaml
            '''
        with self.assertRaises(Exception):
            manifests.ModuleManifest('sample', manifest_data=manifest_data)

    def test_registration_section_is_validated(self):
        # Unexpected member in registration section
        manifest_data = '''
            registration:
                foozle: blat
            files:
                - manifest.yaml
        '''
        with self.assertRaisesRegexp(Exception, 'Unexpected member "foozle"'):
            manifests.ModuleManifest('sample', manifest_data=manifest_data)

        # Bad type for 'main_module'
        manifest_data = '''
            registration:
                main_module: 123
            files:
                - manifest.yaml
        '''
        with self.assertRaisesRegexp(Exception,
                                     'Expected <type \'basestring\'>'):
            manifests.ModuleManifest('sample', manifest_data=manifest_data)

        # Bad type for 'enabled'
        manifest_data = '''
            registration:
                enabled: 123
            files:
                - manifest.yaml
        '''
        with self.assertRaisesRegexp(Exception,
                                     'Expected <type \'bool\'>'):
            manifests.ModuleManifest('sample', manifest_data=manifest_data)

        # main_module does not start with 'modules.sample.'
        manifest_data = '''
            registration:
                main_module: modules.foo.foo
            files:
                - manifest.yaml
        '''
        manifest = manifests.ModuleManifest(
            'sample', manifest_data=manifest_data)
        with self.assertRaisesRegexp(
            ValueError,
            'Expected main module name to start with modules.sample., '):
            manifest.get_registration()

    def test_module_can_not_declare_tests_for_another_module(self):
        manifest_data = '''
            tests:
                unit:
                    - modules.module_name_a.tests.tests.Main = 25
            files:
                - manifest.yaml
            '''
        manifests.ModuleManifest(
            'module_name_a', manifest_data=manifest_data).get_tests()

        with self.assertRaises(Exception):
            manifests.ModuleManifest(
                'module_name_b', manifest_data=manifest_data).get_tests()

    def test_manifest_must_include_manifest_yaml(self):
        manifest_data = '''
            files:
                - foo
        '''
        with self.assertRaises(Exception):
            manifests.ModuleManifest('module_name', manifest_data=manifest_data)
