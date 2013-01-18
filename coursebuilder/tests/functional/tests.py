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
from controllers import utils
from controllers.sites import assert_fails
from models import models
from models.utils import get_all_scores
from models.utils import get_score

import actions


class StudentAspectTest(actions.TestBase):
    """Tests the site from the Student perspective."""

    def test_registration(self):
        """Test student registration."""
        email = 'test_registration@example.com'
        name1 = 'Test Student'
        name2 = 'John Smith'
        name3 = 'Pavel Simakov'

        actions.login(email)

        actions.register(self, name1)
        actions.check_profile(self, name1)

        actions.change_name(self, name2)
        actions.unregister(self)

        actions.register(self, name3)
        actions.check_profile(self, name3)

    def test_limited_class_size_registration(self):
        """Test student registration with MAX_CLASS_SIZE."""
        utils.MAX_CLASS_SIZE = 2

        email1 = '111@example.com'
        name1 = 'student1'
        email2 = '222@example.com'
        name2 = 'student2'
        email3 = '333@example.com'
        name3 = 'student3'

        actions.login(email1)
        actions.register(self, name1)
        actions.logout()

        actions.login(email2)
        actions.register(self, name2)
        actions.logout()

        actions.login(email3)
        assert_fails(lambda: actions.register(self, name3))
        actions.logout()

        # Now unset the limit, and registration should succeed
        utils.MAX_CLASS_SIZE = None
        actions.login(email3)
        actions.register(self, name3)
        actions.logout()

    def test_permissions(self):
        """Test student permissions, and which pages they can view."""
        email = 'test_permissions@example.com'
        name = 'Test Permissions'

        actions.login(email)

        actions.register(self, name)
        actions.Permissions.assert_enrolled(self)

        actions.unregister(self)
        actions.Permissions.assert_unenrolled(self)

        actions.register(self, name)
        actions.Permissions.assert_enrolled(self)

    def test_login_and_logout(self):
        """Test if login and logout behave as expected."""
        email = 'test_login_logout@example.com'

        actions.Permissions.assert_logged_out(self)
        actions.login(email)

        actions.Permissions.assert_unenrolled(self)

        actions.logout()
        actions.Permissions.assert_logged_out(self)


class PageCacheTest(actions.TestBase):
    """Checks if pages cached for one user are properly render for another."""

    def test_page_cache(self):
        """Test a user can't see other user pages."""
        email1 = 'user1@foo.com'
        name1 = 'User 1'
        email2 = 'user2@foo.com'
        name2 = 'User 2'

        # Login as one user and view 'unit' and other pages, which are not
        # cached.
        actions.login(email1)
        actions.register(self, name1)
        actions.Permissions.assert_enrolled(self)
        response = actions.view_unit(self)
        actions.assert_contains(email1, response.body)
        actions.logout()

        # Login as another user and check that 'unit' and other pages show
        # the correct new email.
        actions.login(email2)
        actions.register(self, name2)
        actions.Permissions.assert_enrolled(self)
        response = actions.view_unit(self)
        actions.assert_contains(email2, response.body)
        actions.logout()


class AssessmentTest(actions.TestBase):
    """Tests for assessments."""

    def submit_assessment(self, name, args):
        response = self.get('assessment?name=%s' % name)
        actions.assert_contains(
            '<script src="assets/js/assessment-%s.js"></script>' % name,
            response.body)
        response = self.post('answer', args)
        actions.assert_equals(response.status_int, 200)
        return response

    def test_course_pass(self):
        """Tests student passing final exam."""
        email = 'test_pass@google.com'
        name = 'Test Pass'

        post = {'assessment_type': 'postcourse',
                'num_correct': '0', 'num_questions': '4',
                'score': '100.00'}

        # Register.
        actions.login(email)
        actions.register(self, name)

        # Submit answer.
        response = self.submit_assessment('Post', post)
        actions.assert_equals(response.status_int, 200)
        actions.assert_contains('Your score is 70%', response.body)
        actions.assert_contains('you have passed the course', response.body)

        # Check that the result shows up on the profile page.
        response = actions.check_profile(self, name)
        actions.assert_contains('70', response.body)
        actions.assert_contains('100', response.body)

    def test_assessments(self):
        """Tests assessment scores are properly submitted and summarized."""
        email = 'test_assessments@google.com'
        name = 'Test Assessments'

        pre = {'assessment_type': 'precourse',
               '0': 'false', '1': 'false', '2': 'false', '3': 'false',
               'num_correct': '0', 'num_questions': '4',
               'score': '1.00'}

        mid = {'assessment_type': 'midcourse',
               '0': 'false', '1': 'false', '2': 'false', '3': 'false',
               'num_correct': '0', 'num_questions': '4',
               'score': '2.00'}

        post = {'assessment_type': 'postcourse',
                '0': 'false', '1': 'false', '2': 'false', '3': 'false',
                'num_correct': '0', 'num_questions': '4',
                'score': '3.00'}

        second_mid = {'assessment_type': 'midcourse',
                      '0': 'false', '1': 'false', '2': 'false', '3': 'false',
                      'num_correct': '0', 'num_questions': '4',
                      'score': '1.00'}

        second_post = {'assessment_type': 'postcourse',
                       '0': 'false', '1': 'false', '2': 'false', '3': 'false',
                       'num_correct': '0', 'num_questions': '4',
                       'score': '100000'}

        # Register.
        actions.login(email)
        actions.register(self, name)

        # Check that no scores exist right now.
        student = models.Student.get_enrolled_student_by_email(email)
        assert len(get_all_scores(student)) == 0  # pylint: disable=C6411

        # Submit assessments and check the numbers of scores recorded.
        self.submit_assessment('Pre', pre)
        student = models.Student.get_enrolled_student_by_email(email)
        assert len(get_all_scores(student)) == 1

        self.submit_assessment('Mid', mid)
        student = models.Student.get_enrolled_student_by_email(email)
        assert len(get_all_scores(student)) == 2

        self.submit_assessment('Post', post)
        student = models.Student.get_enrolled_student_by_email(email)
        assert len(get_all_scores(student)) == 4  # also includes overall_score

        # Check that scores are recorded properly.
        student = models.Student.get_enrolled_student_by_email(email)
        assert int(get_score(student, 'precourse')) == 1
        assert int(get_score(student, 'midcourse')) == 2
        assert int(get_score(student, 'postcourse')) == 3
        assert (int(get_score(student, 'overall_score')) ==
                int((0.30 * 2) + (0.70 * 3)))

        # Try posting a new midcourse exam with a lower score; nothing should
        # change.
        self.submit_assessment('Mid', second_mid)
        student = models.Student.get_enrolled_student_by_email(email)
        assert int(get_score(student, 'precourse')) == 1
        assert int(get_score(student, 'midcourse')) == 2
        assert int(get_score(student, 'postcourse')) == 3
        assert (int(get_score(student, 'overall_score')) ==
                int((0.30 * 2) + (0.70 * 3)))

        # Now try posting a postcourse exam with a higher score and note
        # the changes.
        self.submit_assessment('Post', second_post)
        student = models.Student.get_enrolled_student_by_email(email)
        assert int(get_score(student, 'precourse')) == 1
        assert int(get_score(student, 'midcourse')) == 2
        assert int(get_score(student, 'postcourse')) == 100000
        assert (int(get_score(student, 'overall_score')) ==
                int((0.30 * 2) + (0.70 * 100000)))


class CourseUrlRewritingTest(StudentAspectTest, PageCacheTest, AssessmentTest):
    """Runs existing tests using rewrite rules for '/courses/pswg' base URL."""

    def setUp(self):
        self.base = '/courses/pswg'
        self.namespace = 'gcb-courses-pswg-tests-ns'

        config = 'course:%s:/:%s' % (self.base, self.namespace)
        os.environ[sites.GCB_COURSES_CONFIG_ENV_VAR_NAME] = config

        super(CourseUrlRewritingTest, self).setUp()

    def tearDown(self):
        super(CourseUrlRewritingTest, self).tearDown()
        del os.environ[sites.GCB_COURSES_CONFIG_ENV_VAR_NAME]

    def canonicalize(self, href, response=None):
        """Canonicalize URL's using either <base> or self.base."""
        if response:
            # Look for <base> tag in the response to compute the canonical URL.
            return super(CourseUrlRewritingTest, self).canonicalize(
                href, response)
        else:
            # Prepend self.base to compute the canonical URL.
            if not href.startswith('/'):
                href = '/%s' % href
            href = '%s%s' % (self.base, href)
            return href
