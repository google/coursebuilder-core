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

"""Tests that walk through Course Builder pages."""

__author__ = 'Sean Lip'

import os
from controllers import sites
from controllers.sites import AssertFails
from actions import *


class StudentAspectTest(TestBase):
  """Tests the site from the Student perspective."""

  def testRegistration(self):
    """Test student registration."""
    email = 'test_registration@example.com'
    name1 = 'Test Student'
    name2 = 'John Smith'
    name3 = 'Pavel Simakov'

    login(email)

    register(self, name1)
    check_profile(self, name1)

    change_name(self, name2)
    un_register(self)

    register(self, name3)
    check_profile(self, name3)

  def testPermissions(self):
    """Test student permissions to pages."""
    email = 'test_permissions@example.com'
    name = 'Test Permissions'

    login(email)

    register(self, name)
    Permissions.assert_enrolled(self)

    un_register(self)
    Permissions.assert_unenrolled(self)

    register(self, name)
    Permissions.assert_enrolled(self)


class PageCacheTest(TestBase):
  """Checks if pages cached for one user are properly render for another."""

  def testPageCache(self):
    """Test a user can't see other user pages."""
    email1 = 'user1@foo.com'
    name1 = 'User 1'
    email2 = 'user2@foo.com'
    name2 = 'User 2'

    # login as one user and view 'unit' and other pages, which are not cached
    login(email1)
    register(self, name1)
    Permissions.assert_enrolled(self)
    response = view_unit(self)
    AssertContains(email1, response.body)
    logout()

    # login as another user and check 'unit' and other pages show correct new email
    login(email2)
    register(self, name2)
    Permissions.assert_enrolled(self)
    response = view_unit(self)
    AssertContains(email2, response.body)
    logout()


class CourseUrlRewritingTest(StudentAspectTest):
  """Runs existing tests using rewrite rules for '/courses/pswg' base URL."""

  def setUp(self):
    self.base = '/courses/pswg'
    self.namespace = 'gcb-courses-pswg-tests-ns'

    config  ='course:%s:/:%s' % (self.base, self.namespace)
    os.environ[sites.GCB_COURSES_CONFIG_ENV_VAR_NAME] = config

    super(CourseUrlRewritingTest, self).setUp()

  def tearDown(self):
    super(CourseUrlRewritingTest, self).tearDown()
    del os.environ[sites.GCB_COURSES_CONFIG_ENV_VAR_NAME]

  def canonicalize(self, href, response=None):
    """Force self.base on to all URL's, but only if no current response exists."""
    if response:
      # look for <base> tag in the response to compute the canonical URL
      return super(CourseUrlRewritingTest, self).canonicalize(href, response)
    else:
      # prepend self.base to compute the canonical URL
      if not href.startswith('/'):
        href = '/%s' % href
      href = '%s%s' % (self.base, href)
      return href
      