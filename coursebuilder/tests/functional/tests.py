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
from controllers import sites, utils
from models import models
from controllers.sites import AssertFails
from actions import *
from controllers.assessments import getScore, getAllScores


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

  def testLimitedClassSizeRegistration(self):
    """Test student registration with CLASS_SIZE_RESTRICTION."""
    utils.CLASS_SIZE_RESTRICTION = 2

    email1 = '111@example.com'
    name1 = 'student1'
    email2 = '222@example.com'
    name2 = 'student2'
    email3 = '333@example.com'
    name3 = 'student3'

    login(email1)
    register(self, name1)
    logout()

    login(email2)
    register(self, name2)
    logout()

    login(email3)

    # registration should fail for the third user
    class MustFail(Exception):
      pass
    try:
      register(self, name3)
      raise MustFail("Registration should fail for " + name3 + " but didn't")
    except MustFail as e:
      raise e
    except Exception:
      pass
    logout()

    # now unset the limit, and registration should succeed
    utils.CLASS_SIZE_RESTRICTION = None
    login(email3)
    register(self, name3)
    logout()

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

  def testLoginAndLogout(self):
    """Test if login and logout behave as expected."""
    email = 'test_login_logout@example.com'

    Permissions.assert_logged_out(self)
    login(email)

    logout()
    Permissions.assert_logged_out(self)


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


class AssessmentTest(TestBase):

  def submitAssessment(self, name, args):
    response = self.get('assessment?name=%s' % name)
    AssertContains('<script src="assets/js/assessment-%s.js"></script>' % name, response.body)
    response = self.post('answer', args)
    AssertEquals(response.status_int, 200)
    return response

  def testCoursePass(self):
    """Tests student passing final exam."""
    email = 'test_pass@google.com'
    name = 'Test Pass'

    post = {'assessment_type': 'postcourse',
        'num_correct': '0', 'num_questions': '4',
        'score': '100.00'}

    # register
    login(email)
    register(self, name)

    # submit answer
    response = self.submitAssessment('Post', post)
    AssertEquals(response.status_int, 200)
    AssertContains('Your score is 70%', response.body)
    AssertContains('you have passed the course', response.body)

    # scheck pass
    response = check_profile(self, name)
    AssertContains('70', response.body)
    AssertContains('100', response.body)

  def testAssessments(self):
    """Tests assessment scores are properly submitted and summarized."""
    email = 'test_assessments@google.com'
    name = 'Test Assessments'

    pre = {'assessment_type': 'precourse',
        '0': 'false', '1': 'false',
        '2': 'false', '3': 'false',
        'num_correct': '0', 'num_questions': '4',
        'score': '1.00'}

    mid = {'assessment_type': 'midcourse',
        '0': 'false', '1': 'false',
        '2': 'false', '3': 'false',
        'num_correct': '0', 'num_questions': '4',
        'score': '2.00'}

    post = {'assessment_type': 'postcourse',
        '0': 'false', '1': 'false',
        '2': 'false', '3': 'false',
        'num_correct': '0', 'num_questions': '4',
        'score': '3.00'}

    second_mid = {'assessment_type': 'midcourse',
        '0': 'false', '1': 'false',
        '2': 'false', '3': 'false',
        'num_correct': '0', 'num_questions': '4',
        'score': '1.00'}

    second_post = {'assessment_type': 'postcourse',
        '0': 'false', '1': 'false',
        '2': 'false', '3': 'false',
        'num_correct': '0', 'num_questions': '4',
        'score': '100000'}

    # register
    login(email)
    register(self, name)

    # check no scores exist right now
    student = models.Student.get_enrolled_student_by_email(email)
    assert len(getAllScores(student)) == 0

    # submit assessments and check numbers of scores recorded
    self.submitAssessment('Pre', pre)
    student = models.Student.get_enrolled_student_by_email(email)
    assert len(getAllScores(student)) == 1

    self.submitAssessment('Mid', mid)
    student = models.Student.get_enrolled_student_by_email(email)
    assert len(getAllScores(student)) == 2

    self.submitAssessment('Post', post)
    student = models.Student.get_enrolled_student_by_email(email)
    assert len(getAllScores(student)) == 4 # also includes overall_score

    # check scores are recorded properly
    student = models.Student.get_enrolled_student_by_email(email)
    assert int(getScore(student, 'precourse')) == 1
    assert int(getScore(student, 'midcourse')) == 2
    assert int(getScore(student, 'postcourse')) == 3
    assert int(getScore(student, 'overall_score')) == int((0.30*2) + (0.70*3))

    # try posting a new midcourse exam with a lower score; nothing should change
    self.submitAssessment('Mid', second_mid)
    student = models.Student.get_enrolled_student_by_email(email)
    assert int(getScore(student, 'precourse')) == 1
    assert int(getScore(student, 'midcourse')) == 2
    assert int(getScore(student, 'postcourse')) == 3
    assert int(getScore(student, 'overall_score')) == int((0.30*2) + (0.70*3))

    # now try posting a postcourse exam with a higher score and note changes
    self.submitAssessment('Post', second_post)
    student = models.Student.get_enrolled_student_by_email(email)
    assert int(getScore(student, 'precourse')) == 1
    assert int(getScore(student, 'midcourse')) == 2
    assert int(getScore(student, 'postcourse')) == 100000
    assert int(getScore(student, 'overall_score')) == int((0.30*2) + (0.70*100000))


class CourseUrlRewritingTest(StudentAspectTest, PageCacheTest, AssessmentTest):
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

