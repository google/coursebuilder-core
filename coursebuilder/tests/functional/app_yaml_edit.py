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

"""Functional tests for scripts/require_app_yaml_lib.py."""

__author__ = 'mgainer@google.com (Mike Gainer)'

import os
import tempfile
import unittest

from  scripts import require_app_yaml_lib

APP_YAML = os.path.join(os.environ['COURSEBUILDER_HOME'], 'app.yaml')


class RequireAppYamlLibTest(unittest.TestCase):

    def _read_content(self, filename):
        with open(filename) as fp:
            return fp.read()

    def setUp(self):
        super(RequireAppYamlLibTest, self).setUp()
        fd, self.temp = tempfile.mkstemp()
        os.close(fd)
        self.app_yaml_content = self._read_content(APP_YAML)
        with open(self.temp, 'w') as fp:
            fp.write(self.app_yaml_content)
            fp.close()

    def tearDown(self):
        super(RequireAppYamlLibTest, self).tearDown()
        os.unlink(self.temp)

    def test_add_lib_operation(self):
        require_app_yaml_lib.main(self.temp, 'fred', '1.2.3')
        actual_content = self._read_content(self.temp)
        self.assertIn('- name: fred', actual_content)
        self.assertIn('  version: "1.2.3"', actual_content)

    def test_no_op_operation(self):
        require_app_yaml_lib.main(self.temp, 'fred', '1.2.3')

        # Second addition of same library at same version does not throw.
        require_app_yaml_lib.main(self.temp, 'fred', '1.2.3')

    def test_bad_version_operation(self):
        require_app_yaml_lib.main(self.temp, 'fred', '1.2.3')

        # Second addition of same library w/ different version throws.
        with self.assertRaises(ValueError):
            require_app_yaml_lib.main(self.temp, 'fred', '1.2.2')
