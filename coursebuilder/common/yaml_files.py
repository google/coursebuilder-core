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

"""Classes for processing various .yaml files in CourseBuilder installations."""

__author__ = 'Mike Gainer (mgainer@google.com)'

import copy
import re
import yaml

NEWLINE_BEFORE_YAML_SECTIONS = set([
    'env_variables',
    'includes',
    'inbound_services',
    'builtins',
    'libraries',
    'handlers',
])


class CourseBuilderYamlFormatter(yaml.Dumper):
    """Custom formatter to generate CourseBuilder style in yaml files."""

    def __init__(self, *args, **kwargs):
        super(CourseBuilderYamlFormatter, self).__init__(*args, **kwargs)
        self.best_width = 0  # Minimize line merging

    # Add newlines before major sections for good visual parsing.
    def emit(self, item):
        if (isinstance(item, yaml.ScalarEvent) and
            str(item.value) in NEWLINE_BEFORE_YAML_SECTIONS):
            self.write_line_break()
            self.write_line_break()
        super(CourseBuilderYamlFormatter, self).emit(item)

    # For very long lines, don't leave 1st item in element on same line
    # as name of element; instead, move to next line so all parts have
    # the same indent.  (E.g., for GCB_REGISTERED_MODULES list)
    def write_plain(self, text, split):
        if len(text) > 80 or ' ' in text:
            self.write_line_break()
            self.write_indent()
        super(CourseBuilderYamlFormatter, self).write_plain(text, split)


class AppYamlFile(object):
    """Parse, modify, and write app.yaml file."""

    def __init__(self, name):
        self._name = name
        self._loaded = False

    def _lazy_load(self):
        if self._loaded:
            return

        with open(self._name) as fp:
            self._root = yaml.compose(fp)

        # Root value is a list of 2-tuples for name/value of top-level
        # items in yaml file.
        for item in self._root.value:
            if item[0].value == 'env_variables':
                self._env_vars = item[1].value
            if item[0].value == 'libraries':
                self._library_list = item[1].value
            if item[0].value == 'application':
                self._application = item[1].value

        # Libraries item is a list of name/value 2-tuples.
        # Extract name and version for each library.
        self._lib_versions = {}
        for lib_spec in self._library_list:
            name = None
            vers = None
            for lib_item in lib_spec.value:
                if lib_item[0].value == 'name':
                    name = lib_item[1].value
                elif lib_item[0].value == 'version':
                    vers = lib_item[1].value
            if name and vers:
                self._lib_versions[name] = vers
        self._loaded = True

    def write(self):
        self._lazy_load()
        content = yaml.serialize(self._root, stream=None,
                                 Dumper=CourseBuilderYamlFormatter)
        with open(self._name, 'w') as fp:
            fp.write(content)

    def require_library(self, library, version):
        """Add tree nodes for new library if it is not already called for."""
        self._lazy_load()
        if library in self._lib_versions:
            if version != self._lib_versions[library]:
                raise ValueError(
                    'Library "%s" is already required ' % library +
                    'at version "%s".  ' % self._lib_versions[library] +
                    'Cannot satisfy request for version "%s".' % version)
            return False

        added_lib = copy.deepcopy(self._library_list[0])
        added_lib.value[0][1].value = library
        added_lib.value[1][1].value = version
        self._library_list.append(added_lib)
        self._library_list.sort(key=lambda x: x.value[0][1].value)
        return True

    def set_env(self, var_name, var_value):
        self._lazy_load()
        var_value = var_value.strip()
        env_var = None
        for member in self._env_vars:
            if member[0].value == var_name:
                env_var = member
                break

        if var_value:
            if not env_var:
                env_var_name = yaml.ScalarNode('tag:yaml.org,2002:str',
                                               var_name)
                env_var_value = yaml.ScalarNode('tag:yaml.org,2002:str',
                                                var_value)
                env_var = (env_var_name, env_var_value)
                self._env_vars.append(env_var)
            else:
                env_var[1].value = var_value
        else:
            if env_var:
                self._env_vars.remove(env_var)

    def get_env(self, var_name):
        self._lazy_load()
        for env_var in self._env_vars:
            if env_var[0].value == var_name:
                return env_var[1].value
        return None

    def get_all_env(self):
        self._lazy_load()
        ret = {}
        for env_var in self._env_vars:
            ret[env_var[0].value] = env_var[1].value
        return ret

    @property
    def application(self):
        self._lazy_load()
        return self._application


class ModuleManifest(object):
    """Parse module.yaml files into object providing convienent properties."""

    def __init__(self, path):
        self._path = path
        self._loaded = False

    def _lazy_load(self):
        if self._loaded:
            return

        with open(self._path) as fp:
            module_spec = yaml.load(fp)

        self._main_module = module_spec['module_name']
        parts = self._main_module.split('.')
        if parts[0] != 'modules' or len(parts) < 2:
            raise ValueError(
                'module_name is expected to name the main python file '
                'under CourseBuilder as: modules.<module>.<filename>')
        self._module_name = parts[1]

        self._required_version = module_spec['container_version']
        self._third_party_libraries = module_spec.get(
            'third_party_libraries', {})
        self._appengine_libraries = module_spec.get(
            'appengine_libraries', {})
        self._tests = module_spec['tests']
        self._loaded = True

    def assert_version_compatibility(self, actual_version):
        self._lazy_load()
        for required, actual in zip(re.split(r'[-.]', self._required_version),
                                    re.split(r'[-.]', actual_version)):
            if int(required) < int(actual):
                break
            if int(required) > int(actual):
                raise ValueError(
                    'Current CourseBuilder version %s ' % actual_version +
                    'is less than the version %s ' % self._required_version +
                    'required by module %s' % self._module_name)

    @property
    def module_name(self):
        self._lazy_load()
        return self._module_name

    @property
    def main_module(self):
        self._lazy_load()
        return self._main_module

    @property
    def third_party_libraries(self):
        self._lazy_load()
        return self._third_party_libraries

    @property
    def appengine_libraries(self):
        self._lazy_load()
        return self._appengine_libraries

    @property
    def tests(self):
        self._lazy_load()
        return self._tests
