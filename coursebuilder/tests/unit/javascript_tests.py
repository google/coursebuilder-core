# Copyright 2015 Google Inc. All Rights Reserved.
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

"""Unit tests for the javascript code."""

__author__ = 'John Orr (jorr@google.com)'

import os

import unittest

import appengine_config
from scripts import project  # TODO(jorr): factor out run() into common/


class TestBase(unittest.TestCase):

    def karma_test(self, test_directory_path):
        karma_conf = os.path.join(
            appengine_config.BUNDLE_ROOT, test_directory_path, 'karma.conf.js')
        result, out = project.run([
            'karma', 'start', karma_conf], verbose=False)
        if result != 0:
            raise Exception('Test failed: %s', out)


class AllJavaScriptTests(TestBase):

    def test_activity_generic(self):
        self.karma_test(
            'tests/unit/javascript_tests/assets_lib_activity_generic')

    def test_butterbar(self):
        self.karma_test('tests/unit/javascript_tests/assets_lib_butterbar')
