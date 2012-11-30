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


class StudentRegistrationTest(TestBase):

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


class RewriteRulesTest(TestBase):

  def setUp(self):
    self.base = '/courses/pswg'
    self.namespace = 'gcb-courses-pswg-tests-ns'
    os.environ[sites.GCB_REWRITE_RULES_ENV_VAR_NAME] = 'course:%s:/:%s' % (
        self.base, self.namespace)
    super(RewriteRulesTest, self).setUp()

  def tearDown(self):
    super(RewriteRulesTest, self).tearDown()
    del os.environ[sites.GCB_REWRITE_RULES_ENV_VAR_NAME]

  def get(self, url):
    return super(RewriteRulesTest, self).get('%s%s' % (self.base, url))

  def testAll(self):
    """Test URL rewriting using '/courses/pswg' base URL."""
    email = 'rewrite_rules_test@example.com'
    name = 'Rewrite Rules Test'

    login(email)

    # TODO(psimakov): this fails because of absolute URLs; needs to be fixed
    AssertFails(lambda : register(self, name))
    AssertFails(lambda : Permissions.assert_enrolled(self))
    AssertFails(lambda : un_register(self))
