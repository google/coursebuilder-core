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

"""Parsing and convenience functions for module manifest files."""

__author__ = [
    'Pavel Simakov (psimakov@google.com)',
    'Michael Gainer (mgainer@google.com)'
]

import collections
import os
import yaml

from common import schema_fields
from common import schema_transforms


class ModuleManifest(object):
    """Provides parsing and access to modules/*/manifest.yaml."""

    def __init__(self, module_name, manifest_fn=None, manifest_data=None):
        self.name = module_name
        self.registration = None
        self.files = None
        self.tests = None
        self.unit = None
        self.functional = None
        self.integration = None
        self.data = self._parse(manifest_fn, manifest_data)

    def get_schema(self):
        registration = schema_fields.FieldRegistry('registration')
        registration.add_property(schema_fields.SchemaField(
            'main_module', 'Main Module', 'string', optional=True))
        registration.add_property(schema_fields.SchemaField(
            'enabled', 'Is Enabled', 'bool', optional=True, default_value=True))
        registration.add_property(schema_fields.SchemaField(
            'enabled_for_tests', 'Is Enabled When Running Tests', 'bool',
            optional=True, default_value=False))

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
        self.registration = manifest.add_sub_registry(
            'registration', title='Registration', registry=registration)

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

    def get_registration(self):
        registration = self.data.get(self.registration.name)
        names = []
        values = []
        for prop in self.registration.properties:
            names.append(prop.name)
            values.append(schema_fields.FieldRegistry.get_field_value(
                prop, registration))
        ret = collections.namedtuple(self.registration.title, names)(*values)
        expected_prefix = 'modules.{name}.'.format(name=self.name)
        if ret.main_module and not ret.main_module.startswith(expected_prefix):
            raise ValueError(
                'Expected main module name to start with {expected_prefix}, '
                'but had {ret.main_module} instead.'.format(
                    expected_prefix=expected_prefix, ret=ret))
        return ret


class ModulesRepo(object):
    """Provides access to all extension modules and their metadata."""

    def __init__(self, bundle_root):
        self.modules_dir = os.path.join(bundle_root, 'modules')
        self.modules = self._get_modules()
        self.module_to_manifest = self._get_manifests()

    def _get_modules(self):
        modules = []
        for (dirpath, dirnames, _) in os.walk(self.modules_dir,
                                              followlinks=True):
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
