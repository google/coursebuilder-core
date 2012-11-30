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
import unittest
import dev_appserver
import os
import tests
import webtest
from tools import verify
from models.models import Unit, Lesson
from google.appengine.ext import testbed


EXPECTED_TEST_COUNT = 2


def EmptyEnviron():
  os.environ['AUTH_DOMAIN'] = 'example.com'
  os.environ['SERVER_NAME'] = 'localhost'
  os.environ['SERVER_PORT'] = '8080'
  os.environ['USER_EMAIL'] = ''
  os.environ['USER_ID'] = ''


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

    self.initDatastore()

  def initDatastore(self):
    """Generate dummy tests data."""
    logging.info('')
    logging.info('Initializing datastore')

    # load and parse data from CSV file
    unit_file = os.path.join(os.path.dirname(__file__), "../../data/unit.csv")
    lesson_file = os.path.join(os.path.dirname(__file__), "../../data/lesson.csv")
    units = verify.ReadObjectsFromCsvFile(unit_file, verify.UNITS_HEADER, Unit)
    lessons = verify.ReadObjectsFromCsvFile(lesson_file, verify.LESSONS_HEADER, Lesson)

    # store all units and lessons
    for unit in units:
      unit.put()
    for lesson in lessons:
      lesson.put()
    assert Unit.all().count() == 11
    assert Lesson.all().count() == 29

  def tearDown(self):
    self.testbed.deactivate()

  def get(self, url):
    logging.info('Visiting: %s' % url)
    return self.testapp.get(url)


def main():
  """Starts in-process server and runs all test cases in this module."""
  dev_appserver.fix_sys_path()
  suite = unittest.TestLoader().loadTestsFromModule(tests)
  result = unittest.TextTestRunner(verbosity=2).run(suite)

  if result.testsRun != EXPECTED_TEST_COUNT:
    raise Exception(
        'Expected %s tests to be run, not %s.' % (EXPECTED_TEST_COUNT, result.testsRun))
  
  if len(result.errors) != 0 or len(result.failures) != 0:
    raise Exception(
        "Functional test suite failed: %s errors, %s failures of %s tests run." % (
            len(result.errors), len(result.failures), result.testsRun))


if __name__ == '__main__':
  main()

