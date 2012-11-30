# Copyright 2012 Google Inc. All Rights Reserved.
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

"""Functional tests for Course Builder."""

__author__ = 'Sean Lip'


import logging
import os
import sys
import unittest
import webtest
from google.appengine.ext import testbed


EXPECTED_TEST_COUNT = 4


def EmptyEnviron():
  os.environ['AUTH_DOMAIN'] = 'example.com'
  os.environ['SERVER_NAME'] = 'localhost'
  os.environ['SERVER_PORT'] = '8080'
  os.environ['USER_EMAIL'] = ''
  os.environ['USER_ID'] = ''


class BaseTestClass(unittest.TestCase):
  """Base class for setting up and tearing down test cases."""

  def getApp(self):
    """Returns the main application to be tested."""
    raise Exception('Not implemented.')

  def setUp(self):
    EmptyEnviron()

    # setup an app to be tested
    self.testapp = webtest.TestApp(self.getApp())
    self.testbed = testbed.Testbed()
    self.testbed.activate()

    # declare any relevant App Engine service stubs here
    self.testbed.init_user_stub()
    self.testbed.init_memcache_stub()
    self.testbed.init_datastore_v3_stub()

  def tearDown(self):
    self.testbed.deactivate()


def createTestSuite():
  """Loads all tests classes from appropriate modules."""
  import tests
  return unittest.TestLoader().loadTestsFromModule(tests)


def fix_sys_path():
  """Fix the sys.path to include GAE extra paths."""
  import dev_appserver

  # dev_appserver.fix_sys_path() prepends GAE paths to sys.path and hides
  # our classes like 'tests' behind other modules that have 'tests'
  # here, unlike dev_appserver, we append, not prepend path so our classes are first
  sys.path = sys.path + dev_appserver.EXTRA_PATHS[:]


def main():
  """Starts in-process server and runs all test cases in this module."""
  fix_sys_path()
  result = unittest.TextTestRunner(verbosity=2).run(createTestSuite())

  if result.testsRun != EXPECTED_TEST_COUNT:
    raise Exception(
        'Expected %s tests to be run, not %s.' % (EXPECTED_TEST_COUNT, result.testsRun))

  if len(result.errors) != 0 or len(result.failures) != 0:
    raise Exception(
        "Functional test suite failed: %s errors, %s failures of %s tests run." % (
            len(result.errors), len(result.failures), result.testsRun))


if __name__ == '__main__':
  logging.basicConfig(level=3)
  main()
