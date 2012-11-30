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

import unittest
import dev_appserver
import os
import tests
import webtest
from google.appengine.ext import testbed


def EmptyEnviron():
  os.environ['AUTH_DOMAIN'] = 'example.com'
  os.environ['SERVER_NAME'] = 'localhost'
  os.environ['SERVER_PORT'] = '8080'
  os.environ['USER_EMAIL'] = ''
  os.environ['USER_ID'] = ''


def AssertEquals(expected, actual):
  if not expected == actual:
    raise Exception('Expected \'%s\', does not match actual \'%s\'.' % (expected, actual))


def AssertContains(needle, haystack):
  if not needle in haystack:
    raise Exception('Can\'t find \'%s\' in \'%s\'.' % (needle, haystack))


def AssertNoneFail(browser, callbacks):
  """Invokes all callbacks and expects each one not to fail."""
  for callback in callbacks:
    callback(browser)


def AssertAllFail(browser, callbacks):
  """Invokes all callbacks and expects each one to fail."""
  class MustFail(Exception):
    pass

  for callback in callbacks:
    try:
      callback(browser)
      raise MustFail('Expected to fail: %s().' % callback.__name__)
    except MustFail as e:
      raise e
    except Exception:
      pass


class BaseTestClass(unittest.TestCase):
  """Base class for setting up and tearing down test cases."""

  def setUp(self):
    EmptyEnviron()
    import main
    main.debug = True
    app = main.app
    self.testapp = webtest.TestApp(app)
    self.testbed = testbed.Testbed()
    self.testbed.activate()

    # Declare any relevant App Engine service stubs here.
    self.testbed.init_user_stub()
    self.testbed.init_memcache_stub()
    self.testbed.init_datastore_v3_stub()

  def tearDown(self):
    self.testbed.deactivate()

  def get(self, url):
    return self.testapp.get(url)


def main():
  """Starts in-process server and runs all test cases in this module."""
  dev_appserver.fix_sys_path()
  suite = unittest.TestLoader().loadTestsFromModule(tests)
  unittest.TextTestRunner(verbosity=2).run(suite)


if __name__ == '__main__':
  main()

