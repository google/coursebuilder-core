# coding: utf-8
# Copyright 2013 Google Inc. All Rights Reserved.
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

"""Tests for controllers pertaining to peer review assessments."""

__author__ = 'Sean Lip'

from controllers import sites
from models import courses
from models import transforms
from tests.functional import actions


# The unit id for the peer review assignment in the default course.
LEGACY_REVIEW_UNIT_ID = 'ReviewAssessmentExample'


def get_review_step_key(response):
    """Returns the review step key in a request query parameter."""
    request_query_string = response.request.environ['QUERY_STRING']
    return request_query_string[request_query_string.find('key=') + 4:]


def get_review_payload(identifier, is_draft=False):
    """Returns a sample review payload."""
    review = transforms.dumps([
        {'index': 0, 'type': 'choices', 'value': '0', 'correct': False},
        {'index': 1, 'type': 'regex', 'value': identifier, 'correct': True}
    ])
    return {
        'answers': review,
        'is_draft': 'true' if is_draft else 'false',
    }


class PeerReviewControllerTest(actions.TestBase):
    """Test peer review from the Student perspective."""

    def test_submit_assignment(self):
        """Test submission of peer-reviewed assignments."""

        # Override course.yaml settings by patching app_context.
        get_environ_old = sites.ApplicationContext.get_environ

        def get_environ_new(self):
            environ = get_environ_old(self)
            environ['course']['browsable'] = False
            return environ

        sites.ApplicationContext.get_environ = get_environ_new

        email = 'test_peer_reviewed_assignment_submission@google.com'
        name = 'Test Peer Reviewed Assignment Submission'
        submission = transforms.dumps([
            {'index': 0, 'type': 'regex', 'value': 'First answer to Q1',
             'correct': True},
            {'index': 1, 'type': 'choices', 'value': 3, 'correct': False},
            {'index': 2, 'type': 'regex', 'value': 'First answer to Q3',
             'correct': True},
        ])
        second_submission = transforms.dumps([
            {'index': 0, 'type': 'regex', 'value': 'Second answer to Q1',
             'correct': True},
            {'index': 1, 'type': 'choices', 'value': 3, 'correct': False},
            {'index': 2, 'type': 'regex', 'value': 'Second answer to Q3',
             'correct': True},
        ])

        actions.login(email)
        actions.register(self, name)

        # Check that the sample peer-review assignment shows up in the course
        # page and that it can be visited.
        response = actions.view_course(self)
        actions.assert_contains('Sample peer review assignment', response.body)
        actions.assert_contains('Review peer assignments', response.body)
        actions.assert_contains(
            '<a href="assessment?name=%s">' % LEGACY_REVIEW_UNIT_ID,
            response.body)
        actions.assert_contains('Review peer assignments </p>', response.body,
                        collapse_whitespace=True)
        actions.assert_does_not_contain(
            '<a href="reviewdashboard', response.body, collapse_whitespace=True)

        # Check that the progress circle for this assignment is unfilled.
        actions.assert_contains(
            'progress-notstarted-%s' % LEGACY_REVIEW_UNIT_ID, response.body)
        actions.assert_does_not_contain(
            'progress-completed-%s' % LEGACY_REVIEW_UNIT_ID, response.body)

        # Try to access an invalid assignment.
        response = self.get(
            'assessment?name=FakeAssessment', expect_errors=True)
        actions.assert_equals(response.status_int, 404)

        # The student should not be able to see others' reviews because he/she
        # has not submitted an assignment yet.
        response = self.get('assessment?name=%s' % LEGACY_REVIEW_UNIT_ID)
        actions.assert_does_not_contain('Submitted assignment', response.body)
        actions.assert_contains('Due date for this assignment', response.body)
        actions.assert_does_not_contain('Reviews received', response.body)

        # The student should not be able to access the review dashboard because
        # he/she has not submitted the assignment yet.
        response = self.get(
            'reviewdashboard?unit=%s' % LEGACY_REVIEW_UNIT_ID,
            expect_errors=True)
        actions.assert_contains(
            'You must submit the assignment for', response.body)

        # The student submits the assignment.
        response = actions.submit_assessment(
            self,
            LEGACY_REVIEW_UNIT_ID,
            {'answers': submission, 'assessment_type': LEGACY_REVIEW_UNIT_ID}
        )
        actions.assert_contains(
            'Thank you for completing this assignment', response.body)
        actions.assert_contains('Review peer assignments', response.body)

        # The student views the submitted assignment, which has become readonly.
        response = self.get('assessment?name=%s' % LEGACY_REVIEW_UNIT_ID)
        actions.assert_contains('First answer to Q1', response.body)
        actions.assert_contains('Submitted assignment', response.body)

        # The student tries to re-submit the same assignment. This should fail.
        response = actions.submit_assessment(
            self,
            LEGACY_REVIEW_UNIT_ID,
            {'answers': second_submission,
             'assessment_type': LEGACY_REVIEW_UNIT_ID},
            presubmit_checks=False
        )
        actions.assert_contains(
            'You have already submitted this assignment.', response.body)
        actions.assert_contains('Review peer assignments', response.body)

        # The student views the submitted assignment. The new answers have not
        # been saved.
        response = self.get('assessment?name=%s' % LEGACY_REVIEW_UNIT_ID)
        actions.assert_contains('First answer to Q1', response.body)
        actions.assert_does_not_contain('Second answer to Q1', response.body)

        # The student checks the course page and sees that the progress
        # circle for this assignment has been filled, and that the 'Review
        # peer assignments' link is now available.
        response = actions.view_course(self)
        actions.assert_contains(
            'progress-completed-%s' % LEGACY_REVIEW_UNIT_ID, response.body)
        actions.assert_does_not_contain(
            '<span> Review peer assignments </span>', response.body,
            collapse_whitespace=True)
        actions.assert_contains(
            '<a href="reviewdashboard?unit=%s">' % LEGACY_REVIEW_UNIT_ID,
            response.body, collapse_whitespace=True)

        # The student should also be able to now view the review dashboard.
        response = self.get('reviewdashboard?unit=%s' % LEGACY_REVIEW_UNIT_ID)
        actions.assert_contains('Assignments for your review', response.body)
        actions.assert_contains('Review a new assignment', response.body)

        actions.logout()

        # Clean up app_context.
        sites.ApplicationContext.get_environ = get_environ_old

    def test_handling_of_fake_review_step_key(self):
        """Test that bad keys result in the appropriate responses."""

        email = 'student1@google.com'
        name = 'Student 1'
        submission = transforms.dumps([
            {'index': 0, 'type': 'regex', 'value': 'S1-1', 'correct': True},
            {'index': 1, 'type': 'choices', 'value': 3, 'correct': False},
            {'index': 2, 'type': 'regex', 'value': 'is-S1', 'correct': True},
        ])
        payload = {
            'answers': submission, 'assessment_type': LEGACY_REVIEW_UNIT_ID}

        actions.login(email)
        actions.register(self, name)
        actions.submit_assessment(self, LEGACY_REVIEW_UNIT_ID, payload)

        actions.view_review(
            self, LEGACY_REVIEW_UNIT_ID, 'Fake key',
            expected_status_code=404)

        actions.logout()

    def test_not_enough_assignments_to_allocate(self):
        """Test for the case when there are too few assignments in the pool."""

        email = 'student1@google.com'
        name = 'Student 1'
        submission = transforms.dumps([
            {'index': 0, 'type': 'regex', 'value': 'S1-1', 'correct': True},
            {'index': 1, 'type': 'choices', 'value': 3, 'correct': False},
            {'index': 2, 'type': 'regex', 'value': 'is-S1', 'correct': True},
        ])
        payload = {
            'answers': submission, 'assessment_type': LEGACY_REVIEW_UNIT_ID}

        actions.login(email)
        actions.register(self, name)
        response = actions.submit_assessment(
            self, LEGACY_REVIEW_UNIT_ID, payload)

        # The student goes to the review dashboard and requests an assignment
        # to review -- but there is nothing to review.
        response = actions.request_new_review(
            self, LEGACY_REVIEW_UNIT_ID, expected_status_code=200)
        actions.assert_does_not_contain('Assignment to review', response.body)
        actions.assert_contains(
            'Sorry, there are no new submissions ', response.body)
        actions.assert_contains('disabled="true"', response.body)

        actions.logout()

    def test_reviewer_cannot_impersonate_another_reviewer(self):
        """Test that one reviewer cannot use another's review step key."""

        email1 = 'student1@google.com'
        name1 = 'Student 1'
        submission1 = transforms.dumps([
            {'index': 0, 'type': 'regex', 'value': 'S1-1', 'correct': True},
            {'index': 1, 'type': 'choices', 'value': 3, 'correct': False},
            {'index': 2, 'type': 'regex', 'value': 'is-S1', 'correct': True},
        ])
        payload1 = {
            'answers': submission1, 'assessment_type': LEGACY_REVIEW_UNIT_ID}

        email2 = 'student2@google.com'
        name2 = 'Student 2'
        submission2 = transforms.dumps([
            {'index': 0, 'type': 'regex', 'value': 'S2-1', 'correct': True},
            {'index': 1, 'type': 'choices', 'value': 3, 'correct': False},
            {'index': 2, 'type': 'regex', 'value': 'not-S1', 'correct': True},
        ])
        payload2 = {
            'answers': submission2, 'assessment_type': LEGACY_REVIEW_UNIT_ID}

        email3 = 'student3@google.com'
        name3 = 'Student 3'
        submission3 = transforms.dumps([
            {'index': 0, 'type': 'regex', 'value': 'S3-1', 'correct': True},
            {'index': 1, 'type': 'choices', 'value': 3, 'correct': False},
            {'index': 2, 'type': 'regex', 'value': 'not-S1', 'correct': True},
        ])
        payload3 = {
            'answers': submission3, 'assessment_type': LEGACY_REVIEW_UNIT_ID}

        # Student 1 submits the assignment.
        actions.login(email1)
        actions.register(self, name1)
        response = actions.submit_assessment(
            self, LEGACY_REVIEW_UNIT_ID, payload1)
        actions.logout()

        # Student 2 logs in and submits the assignment.
        actions.login(email2)
        actions.register(self, name2)
        response = actions.submit_assessment(
            self, LEGACY_REVIEW_UNIT_ID, payload2)

        # Student 2 requests a review, and is given Student 1's assignment.
        response = actions.request_new_review(self, LEGACY_REVIEW_UNIT_ID)
        review_step_key_2_for_1 = get_review_step_key(response)
        actions.assert_contains('S1-1', response.body)
        actions.logout()

        # Student 3 logs in, and submits the assignment.
        actions.login(email3)
        actions.register(self, name3)
        response = actions.submit_assessment(
            self, LEGACY_REVIEW_UNIT_ID, payload3)

        # Student 3 tries to view Student 1's assignment using Student 2's
        # review step key, but is not allowed to.
        response = actions.view_review(
            self, LEGACY_REVIEW_UNIT_ID, review_step_key_2_for_1,
            expected_status_code=404)

        # Student 3 logs out.
        actions.logout()

    def test_student_cannot_see_reviews_prematurely(self):
        """Test that students cannot see others' reviews prematurely."""

        email = 'student1@google.com'
        name = 'Student 1'
        submission = transforms.dumps([
            {'index': 0, 'type': 'regex', 'value': 'S1-1', 'correct': True},
            {'index': 1, 'type': 'choices', 'value': 3, 'correct': False},
            {'index': 2, 'type': 'regex', 'value': 'is-S1', 'correct': True},
        ])
        payload = {
            'answers': submission, 'assessment_type': LEGACY_REVIEW_UNIT_ID}

        actions.login(email)
        actions.register(self, name)
        response = actions.submit_assessment(
            self, LEGACY_REVIEW_UNIT_ID, payload)

        # Student 1 cannot see the reviews for his assignment yet, because he
        # has not submitted the two required reviews.
        response = self.get('assessment?name=%s' % LEGACY_REVIEW_UNIT_ID)
        actions.assert_equals(response.status_int, 200)
        actions.assert_contains('Due date for this assignment', response.body)
        actions.assert_contains(
            'After you have completed the required number of peer reviews',
            response.body)

        actions.logout()

    # pylint: disable=too-many-statements
    def test_draft_review_behaviour(self):
        """Test correctness of draft review visibility."""

        email1 = 'student1@google.com'
        name1 = 'Student 1'
        submission1 = transforms.dumps([
            {'index': 0, 'type': 'regex', 'value': 'S1-1', 'correct': True},
            {'index': 1, 'type': 'choices', 'value': 3, 'correct': False},
            {'index': 2, 'type': 'regex', 'value': 'is-S1', 'correct': True},
        ])
        payload1 = {
            'answers': submission1, 'assessment_type': LEGACY_REVIEW_UNIT_ID}

        email2 = 'student2@google.com'
        name2 = 'Student 2'
        submission2 = transforms.dumps([
            {'index': 0, 'type': 'regex', 'value': 'S2-1', 'correct': True},
            {'index': 1, 'type': 'choices', 'value': 3, 'correct': False},
            {'index': 2, 'type': 'regex', 'value': 'not-S1', 'correct': True},
        ])
        payload2 = {
            'answers': submission2, 'assessment_type': LEGACY_REVIEW_UNIT_ID}

        email3 = 'student3@google.com'
        name3 = 'Student 3'
        submission3 = transforms.dumps([
            {'index': 0, 'type': 'regex', 'value': 'S3-1', 'correct': True},
            {'index': 1, 'type': 'choices', 'value': 3, 'correct': False},
            {'index': 2, 'type': 'regex', 'value': 'not-S1', 'correct': True},
        ])
        payload3 = {
            'answers': submission3, 'assessment_type': LEGACY_REVIEW_UNIT_ID}

        # Student 1 submits the assignment.
        actions.login(email1)
        actions.register(self, name1)
        response = actions.submit_assessment(
            self, LEGACY_REVIEW_UNIT_ID, payload1)
        actions.logout()

        # Student 2 logs in and submits the assignment.
        actions.login(email2)
        actions.register(self, name2)
        response = actions.submit_assessment(
            self, LEGACY_REVIEW_UNIT_ID, payload2)

        # Student 2 requests a review, and is given Student 1's assignment.
        response = actions.request_new_review(self, LEGACY_REVIEW_UNIT_ID)
        review_step_key_2_for_1 = get_review_step_key(response)
        actions.assert_contains('S1-1', response.body)

        # Student 2 saves her review as a draft.
        review_2_for_1_payload = get_review_payload(
            'R2for1', is_draft=True)

        response = actions.submit_review(
            self, LEGACY_REVIEW_UNIT_ID, review_step_key_2_for_1,
            review_2_for_1_payload)
        actions.assert_contains('Your review has been saved.', response.body)

        response = self.get('reviewdashboard?unit=%s' % LEGACY_REVIEW_UNIT_ID)
        actions.assert_equals(response.status_int, 200)
        actions.assert_contains('(Draft)', response.body)

        # Student 2's draft is still changeable.
        response = actions.view_review(
            self, LEGACY_REVIEW_UNIT_ID, review_step_key_2_for_1)
        actions.assert_contains('Submit Review', response.body)
        response = actions.submit_review(
            self, LEGACY_REVIEW_UNIT_ID, review_step_key_2_for_1,
            review_2_for_1_payload)
        actions.assert_contains('Your review has been saved.', response.body)

        # Student 2 logs out.
        actions.logout()

        # Student 3 submits the assignment.
        actions.login(email3)
        actions.register(self, name3)
        response = actions.submit_assessment(
            self, LEGACY_REVIEW_UNIT_ID, payload3)
        actions.logout()

        # Student 1 logs in and requests two assignments to review.
        actions.login(email1)
        response = self.get('/reviewdashboard?unit=%s' % LEGACY_REVIEW_UNIT_ID)

        response = actions.request_new_review(self, LEGACY_REVIEW_UNIT_ID)
        actions.assert_contains('Assignment to review', response.body)
        actions.assert_contains('not-S1', response.body)

        review_step_key_1_for_someone = get_review_step_key(response)

        response = actions.request_new_review(self, LEGACY_REVIEW_UNIT_ID)
        actions.assert_contains('Assignment to review', response.body)
        actions.assert_contains('not-S1', response.body)

        review_step_key_1_for_someone_else = get_review_step_key(response)

        response = self.get('reviewdashboard?unit=%s' % LEGACY_REVIEW_UNIT_ID)
        actions.assert_equals(response.status_int, 200)
        actions.assert_contains('disabled="true"', response.body)

        # Student 1 submits both reviews, fulfilling his quota.
        review_1_for_other_payload = get_review_payload('R1for')

        response = actions.submit_review(
            self, LEGACY_REVIEW_UNIT_ID, review_step_key_1_for_someone,
            review_1_for_other_payload)
        actions.assert_contains(
            'Your review has been submitted successfully', response.body)

        response = actions.submit_review(
            self, LEGACY_REVIEW_UNIT_ID, review_step_key_1_for_someone_else,
            review_1_for_other_payload)
        actions.assert_contains(
            'Your review has been submitted successfully', response.body)

        response = self.get('/reviewdashboard?unit=%s' % LEGACY_REVIEW_UNIT_ID)
        actions.assert_contains('(Completed)', response.body)
        actions.assert_does_not_contain('(Draft)', response.body)

        # Although Student 1 has submitted 2 reviews, he cannot view Student
        # 2's review because it is still in Draft status.
        response = self.get('assessment?name=%s' % LEGACY_REVIEW_UNIT_ID)
        actions.assert_equals(response.status_int, 200)
        actions.assert_contains(
            'You have not received any peer reviews yet.', response.body)
        actions.assert_does_not_contain('R2for1', response.body)

        # Student 1 logs out.
        actions.logout()

        # Student 2 submits her review for Student 1's assignment.
        actions.login(email2)

        response = self.get('review?unit=%s&key=%s' % (
            LEGACY_REVIEW_UNIT_ID, review_step_key_2_for_1))
        actions.assert_does_not_contain('Submitted review', response.body)

        response = actions.submit_review(
            self, LEGACY_REVIEW_UNIT_ID, review_step_key_2_for_1,
            get_review_payload('R2for1'))
        actions.assert_contains(
            'Your review has been submitted successfully', response.body)

        # Her review is now read-only.
        response = self.get('review?unit=%s&key=%s' % (
            LEGACY_REVIEW_UNIT_ID, review_step_key_2_for_1))
        actions.assert_contains('Submitted review', response.body)
        actions.assert_contains('R2for1', response.body)

        # Student 2 logs out.
        actions.logout()

        # Now Student 1 can see the review he has received from Student 2.
        actions.login(email1)
        response = self.get('assessment?name=%s' % LEGACY_REVIEW_UNIT_ID)
        actions.assert_equals(response.status_int, 200)
        actions.assert_contains('R2for1', response.body)

    def test_independence_of_draft_reviews(self):
        """Test that draft reviews do not interfere with each other."""

        email1 = 'student1@google.com'
        name1 = 'Student 1'
        submission1 = transforms.dumps([
            {'index': 0, 'type': 'regex', 'value': 'S1-1', 'correct': True},
            {'index': 1, 'type': 'choices', 'value': 3, 'correct': False},
            {'index': 2, 'type': 'regex', 'value': 'is-S1', 'correct': True},
        ])
        payload1 = {
            'answers': submission1, 'assessment_type': LEGACY_REVIEW_UNIT_ID}

        email2 = 'student2@google.com'
        name2 = 'Student 2'
        submission2 = transforms.dumps([
            {'index': 0, 'type': 'regex', 'value': 'S2-1', 'correct': True},
            {'index': 1, 'type': 'choices', 'value': 3, 'correct': False},
            {'index': 2, 'type': 'regex', 'value': 'not-S1', 'correct': True},
        ])
        payload2 = {
            'answers': submission2, 'assessment_type': LEGACY_REVIEW_UNIT_ID}

        email3 = 'student3@google.com'
        name3 = 'Student 3'
        submission3 = transforms.dumps([
            {'index': 0, 'type': 'regex', 'value': 'S3-1', 'correct': True},
            {'index': 1, 'type': 'choices', 'value': 3, 'correct': False},
            {'index': 2, 'type': 'regex', 'value': 'not-S1', 'correct': True},
        ])
        payload3 = {
            'answers': submission3, 'assessment_type': LEGACY_REVIEW_UNIT_ID}

        # Student 1 submits the assignment.
        actions.login(email1)
        actions.register(self, name1)
        response = actions.submit_assessment(
            self, LEGACY_REVIEW_UNIT_ID, payload1)
        actions.logout()

        # Student 2 logs in and submits the assignment.
        actions.login(email2)
        actions.register(self, name2)
        response = actions.submit_assessment(
            self, LEGACY_REVIEW_UNIT_ID, payload2)
        actions.logout()

        # Student 3 logs in and submits the assignment.
        actions.login(email3)
        actions.register(self, name3)
        response = actions.submit_assessment(
            self, LEGACY_REVIEW_UNIT_ID, payload3)
        actions.logout()

        # Student 1 logs in and requests two assignments to review.
        actions.login(email1)
        response = self.get('/reviewdashboard?unit=%s' % LEGACY_REVIEW_UNIT_ID)

        response = actions.request_new_review(self, LEGACY_REVIEW_UNIT_ID)
        actions.assert_equals(response.status_int, 200)
        actions.assert_contains('Assignment to review', response.body)
        actions.assert_contains('not-S1', response.body)

        review_step_key_1_for_someone = get_review_step_key(response)

        response = actions.request_new_review(self, LEGACY_REVIEW_UNIT_ID)
        actions.assert_equals(response.status_int, 200)
        actions.assert_contains('Assignment to review', response.body)
        actions.assert_contains('not-S1', response.body)

        review_step_key_1_for_someone_else = get_review_step_key(response)

        self.assertNotEqual(
            review_step_key_1_for_someone, review_step_key_1_for_someone_else)

        # Student 1 submits two draft reviews.
        response = actions.submit_review(
            self, LEGACY_REVIEW_UNIT_ID, review_step_key_1_for_someone,
            get_review_payload('R1forFirst', is_draft=True))
        actions.assert_contains('Your review has been saved.', response.body)

        response = actions.submit_review(
            self, LEGACY_REVIEW_UNIT_ID, review_step_key_1_for_someone_else,
            get_review_payload('R1forSecond', is_draft=True))
        actions.assert_contains('Your review has been saved.', response.body)

        # The two draft reviews should still be different when subsequently
        # accessed.
        response = self.get('review?unit=%s&key=%s' % (
            LEGACY_REVIEW_UNIT_ID, review_step_key_1_for_someone))
        actions.assert_contains('R1forFirst', response.body)

        response = self.get('review?unit=%s&key=%s' % (
            LEGACY_REVIEW_UNIT_ID, review_step_key_1_for_someone_else))
        actions.assert_contains('R1forSecond', response.body)

        # Student 1 logs out.
        actions.logout()


class PeerReviewDashboardAdminTest(actions.TestBase):
    """Test peer review dashboard from the Admin perspective."""

    def test_add_reviewer(self):
        """Test that admin can add a reviewer, and cannot re-add reviewers."""

        email = 'test_add_reviewer@google.com'
        name = 'Test Add Reviewer'
        submission = transforms.dumps([
            {'index': 0, 'type': 'regex', 'value': 'First answer to Q1',
             'correct': True},
            {'index': 1, 'type': 'choices', 'value': 3, 'correct': False},
            {'index': 2, 'type': 'regex', 'value': 'First answer to Q3',
             'correct': True},
        ])
        payload = {
            'answers': submission, 'assessment_type': LEGACY_REVIEW_UNIT_ID}

        actions.login(email)
        actions.register(self, name)
        response = actions.submit_assessment(
            self, LEGACY_REVIEW_UNIT_ID, payload)

        # There is nothing to review on the review dashboard.
        response = actions.request_new_review(
            self, LEGACY_REVIEW_UNIT_ID, expected_status_code=200)
        actions.assert_does_not_contain('Assignment to review', response.body)
        actions.assert_contains(
            'Sorry, there are no new submissions ', response.body)
        actions.logout()

        # The admin assigns the student to review his own work.
        actions.login(email, is_admin=True)
        response = actions.add_reviewer(
            self, LEGACY_REVIEW_UNIT_ID, email, email)
        actions.assert_equals(response.status_int, 302)
        response = self.get(response.location)
        actions.assert_does_not_contain(
            'Error 412: The reviewer is already assigned', response.body)
        actions.assert_contains('First answer to Q1', response.body)
        actions.assert_contains(
            'Review 1 from test_add_reviewer@google.com', response.body)

        # The admin repeats the 'add reviewer' action. This should fail.
        response = actions.add_reviewer(
            self, LEGACY_REVIEW_UNIT_ID, email, email)
        actions.assert_equals(response.status_int, 302)
        response = self.get(response.location)
        actions.assert_contains(
            'Error 412: The reviewer is already assigned', response.body)


class PeerReviewDashboardStudentTest(actions.TestBase):
    """Test peer review dashboard from the Student perspective."""

    COURSE_NAME = 'back_button_top_level'
    STUDENT_EMAIL = 'foo@foo.com'

    def setUp(self):
        super(PeerReviewDashboardStudentTest, self).setUp()
        self.base = '/' + self.COURSE_NAME
        context = actions.simple_add_course(
            self.COURSE_NAME, 'admin@foo.com', 'Peer Back Button Child')
        self.course = courses.Course(None, context)

        self.assessment = self.course.add_assessment()
        self.assessment.title = 'Assessment'
        self.assessment.html_content = 'assessment content'
        self.assessment.workflow_yaml = (
            '{grader: human,'
            'matcher: peer,'
            'review_due_date: \'2034-07-01 12:00\','
            'review_min_count: 1,'
            'review_window_mins: 20,'
            'submission_due_date: \'2034-07-01 12:00\'}')
        self.assessment.availability = courses.AVAILABILITY_AVAILABLE

        self.course.save()
        actions.login(self.STUDENT_EMAIL)
        actions.register(self, self.STUDENT_EMAIL)

        actions.submit_assessment(
            self,
            self.assessment.unit_id,
            {'answers': '', 'score': 0,
             'assessment_type': self.assessment.unit_id},
            presubmit_checks=False
        )

    def test_back_button_top_level_assessment(self):
        response = self.get('reviewdashboard?unit=%s' % str(
            self.assessment.unit_id))

        back_button = self.parse_html_string(response.body).find(
            './/*[@href="assessment?name=%s"]' % self.assessment.unit_id)

        self.assertIsNotNone(back_button)
        self.assertEquals(back_button.text, 'Back to assignment')

    def test_back_button_child_assessment(self):
        parent_unit = self.course.add_unit()
        parent_unit.title = 'No Lessons'
        parent_unit.availability = courses.AVAILABILITY_AVAILABLE
        parent_unit.pre_assessment = self.assessment.unit_id
        self.course.save()

        response = self.get('reviewdashboard?unit=%s' % str(
            self.assessment.unit_id))

        back_button = self.parse_html_string(response.body).find(
            './/*[@href="unit?unit=%s&assessment=%s"]' % (
            parent_unit.unit_id, self.assessment.unit_id))

        self.assertIsNotNone(back_button)
        self.assertEquals(back_button.text, 'Back to assignment')
