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

"""Configure a library for inclusion in app.yaml file.  Detects conflicts.

Usage:

cd $COURSEBUILDER_HOME
scripts/require_app_yaml_lib.py <libname> <libversion>

Example:
scripts/require_app_yaml_lib.py pycrypto 2.6


This script is meant for use by CourseBuilder extension modules.  Rather
than applying changes directly to the app.yaml file via patching, this
script can be used to safely specify new AppEngine-supplied libraries.

If libname is not mentioned in the app.yaml file for the CourseBuilder
application, the library is added to the 'libraries' section in app.yaml
in alphabetical order.  If the library is already mentioned, and the
requested version number is already present, no action is taken.
If the library is already mentioned, but the version numbers mismatch,
the script will exit with an error status code of 1.
"""


__author__ = 'Mike Gainer (mgainer@google.com)'

import copy
import sys
import yaml

NEWLINE_BEFORE_SECTIONS = set([
    'env_variables',
    'includes',
    'inbound_services',
    'builtins',
    'libraries',
    'handlers',
])


class CbDumper(yaml.Dumper):
    """Custom tree dumper to generate CourseBuilder preferred formatting."""

    def __init__(self, *args, **kwargs):
        super(CbDumper, self).__init__(*args, **kwargs)
        self.best_width = 0  # Minimize line merging

    # Add newlines before major sections for good visual parsing.
    def emit(self, item):
        if (isinstance(item, yaml.ScalarEvent) and
            str(item.value) in NEWLINE_BEFORE_SECTIONS):
            self.write_line_break()
            self.write_line_break()
        super(CbDumper, self).emit(item)

    # For very long lines, don't leave 1st item in element on same line
    # as name of element; instead, move to next line so all parts have
    # the same indent.  (E.g., for GCB_REGISTERED_MODULES list)
    def write_plain(self, text, split):
        if len(text) > 80:
            self.write_line_break()
            self.write_indent()
        super(CbDumper, self).write_plain(text, split)


def _read_yaml(name):
    with open(name) as fp:
        root = yaml.compose(fp)
    return root


def _parse_libraries(root):
    """Parse and return library versions as well as list to add new lib to."""

    # Root value is a list of 2-tuples for name/value of top-level
    # items in yaml file.
    lib_versions = {}
    library_list = None
    for item in root.value:
        if item[0].value == 'libraries':
            library_list = item[1].value

            # Libraries item is a list of name/value 2-tuples.
            # Extract name and version for each library.
            for lib_spec in library_list:
                name = None
                vers = None
                for lib_item in lib_spec.value:
                    if lib_item[0].value == 'name':
                        name = lib_item[1].value
                    elif lib_item[0].value == 'version':
                        vers = lib_item[1].value
                if name and vers:
                    lib_versions[name] = vers
    return lib_versions, library_list


def _maybe_add_library(library, version, lib_versions, library_list):
    """Add tree nodes for new library if it is not already called for."""

    if library in lib_versions:
        if version != lib_versions[library]:
            raise ValueError(
                'Library "%s" is already required ' % library +
                'at version "%s".  ' % lib_versions[library] +
                'Cannot satisfy request for version "%s".' % version)
        return False

    added_lib = copy.deepcopy(library_list[0])
    added_lib.value[0][1].value = library
    added_lib.value[1][1].value = version
    library_list.append(added_lib)
    library_list.sort(key=lambda x: x.value[0][1].value)
    return True


def _write_yaml(name, root):
    content = yaml.serialize(root, stream=None, Dumper=CbDumper)
    with open(name, 'w') as fp:
        fp.write(content)


def main(filename, library, version):
    root = _read_yaml(filename)
    lib_versions, library_list = _parse_libraries(root)
    if _maybe_add_library(library, version, lib_versions, library_list):
        _write_yaml(filename, root)


if __name__ == '__main__':
    main('app.yaml', sys.argv[1], sys.argv[2])
