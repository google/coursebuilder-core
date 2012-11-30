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
#
# @author: psimakov@google.com (Pavel Simakov)

"""A collection of actions for testing Course Builder pages."""

import logging
import main
import os
import re
import suite
from models.models import Unit, Lesson
from tools import verify
from google.appengine.api import namespace_manager


class TestBase(suite.BaseTestClass):
  def getApp(self):
    main.debug = True
    return main.app

  def setUp(self):
    super(TestBase, self).setUp()

    # set desired namespace and inits data
    namespace = namespace_manager.get_namespace()
    try:
      if hasattr(self, 'namespace'):
        namespace_manager.set_namespace(self.namespace)
      self.initDatastore()
    finally:
      if namespace == '':
        namespace_manager.set_namespace(None)

  def initDatastore(self):
    """Loads course data from the CSV files."""
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

  def canonicalize(self, href, response=None):
    """Create absolute URL using <base> if defined, '/' otherwise."""
    if href.startswith('/'):
      return href
    base = '/'
    if response:
      match = re.search(r'<base href=[\'"]?([^\'" >]+)', response.body)
      if match and not href.startswith('/'):
        base = match.groups()[0]
    return '%s%s' % (base, href)

  def hookResponse(self, response):
    """Modify response.goto() to properly compute URL using <base> if defined."""
    gotox = response.goto
    def newGoto(href, method='get', **args):
      return gotox(self.canonicalize(href), method, **args)

    response.goto = newGoto
    return response

  def get(self, url):
    url = self.canonicalize(url)
    logging.info('Goto: %s' % url)
    response = self.testapp.get(url)
    return self.hookResponse(response)

  def click(self, response, name):
    logging.info('Click: %s' % name)
    response = response.click(name)
    return self.hookResponse(response)

  def submit(self, form):
    logging.info('Submit: %s' % form)
    response = form.submit()
    return self.hookResponse(response)


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


def login(email):
  os.environ['USER_EMAIL'] = email
  os.environ['USER_ID'] = 'user1'


def get_current_user_email():
  email = os.environ['USER_EMAIL']
  if not email:
    raise Exception('No current user.')
  return email


def logout():
  os.environ['USER_EMAIL'] = None
  os.environ['USER_ID'] = None


def register(browser, name):
  response = browser.get('/')
  AssertEquals(response.status_int, 302)

  response = view_registration(browser)

  response.form.set('form01', name)
  response = browser.submit(response.form)

  AssertContains('Thank you for registering for', response.body)
  check_profile(browser, name)


def check_profile(browser, name):
  response = view_my_profile(browser)
  AssertContains('Email:', response.body)
  AssertContains(name, response.body)
  AssertContains(get_current_user_email(), response.body)


def view_registration(browser):
  response = browser.get('register')
  AssertContains('What is your name?', response.body)
  return response


def view_course(browser):
  response = browser.get('course')
  AssertContains(' the stakes are high.', response.body)
  return response


def view_unit(browser):
  response = browser.get('unit?unit=1&lesson=1')
  AssertContains('Unit 1 - Introduction', response.body)
  return response


def view_activity(browser):
  response = browser.get('activity?unit=1&lesson=2')
  AssertContains('<script src="assets/js/activity-1.2.js"></script>', response.body)
  return response


def view_announcements(browser):
  response = browser.get('announcements')
  AssertContains('Example Announcement', response.body)
  return response


def view_my_profile(browser):
  response = browser.get('student/home')
  AssertContains('Certificate Name:', response.body)
  return response


def view_forum(browser):
  response = browser.get('forum')
  AssertContains('document.getElementById("forum_embed").src =', response.body)
  return response


def view_assesements(browser):
  for name in ['Pre', 'Mid', 'Fin']:
    response = browser.get('assessment?name=%s' % name)
    assert 'assets/js/assessment-%s.js' % name in response.body
    AssertEquals(response.status_int, 200)


def change_name(browser, new_name):
  response = browser.get('student/home')

  response.form.set('name', new_name)
  response = browser.submit(response.form)

  AssertEquals(response.status_int, 302)
  check_profile(browser, new_name)


def un_register(browser):
  response = browser.get('student/home')
  response = browser.click(response, 'Unenroll')

  AssertContains('to unenroll from', response.body)
  browser.submit(response.form)


class Permissions():
  """Defines who can see what."""

  @classmethod
  def get_enrolled_student_allowed_pages(cls):
    """Returns all pages that enrolled student can see."""
    return [view_announcements, view_forum, view_course,
        view_assesements, view_unit, view_activity, view_my_profile]

  @classmethod
  def get_enrolled_student_denied_pages(cls):
    """Returns all pages that enrolled student can't see."""
    return [view_registration]

  @classmethod
  def get_unenrolled_student_allowed_pages(cls):
    """Returns all pages that un-enrolled student can see."""
    return [view_registration, view_my_profile, view_announcements]

  @classmethod
  def get_unenrolled_student_denied_pages(cls):
    """Returns all pages that un-enrolled student can't see."""
    all = Permissions.get_enrolled_student_allowed_pages()
    for allowed in Permissions.get_unenrolled_student_allowed_pages():
      if allowed in all:
        all.remove(allowed)
    return all

  @classmethod
  def assert_enrolled(cls, browser):
    """Check that current user can see only what is allowed to enrolled student."""
    AssertNoneFail(browser, Permissions.get_enrolled_student_allowed_pages())
    AssertAllFail(browser, Permissions.get_enrolled_student_denied_pages())

  @classmethod
  def assert_unenrolled(cls, browser):
    """Check that current user can see only what is allowed to un-enrolled student."""
    AssertNoneFail(browser, Permissions.get_unenrolled_student_allowed_pages())
    AssertAllFail(browser, Permissions.get_unenrolled_student_denied_pages())
