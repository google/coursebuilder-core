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

from models import transforms
import actions
from actions import assert_contains
from actions import assert_does_not_contain
from actions import assert_equals


# The unit id for the peer review assignment in the default course.
LEGACY_REVIEW_UNIT_ID = 'ReviewAssessmentExample'


class PeerReviewControllerTest(actions.TestBase):
    """Test peer review from the Student perspective."""

    def test_submit_assignment(self):
        """Test submission of peer-reviewed assignments."""

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

        # Check that the sample peer-review assignment shows up in the preview
        # page.
        response = actions.view_preview(self)
        assert_contains('Sample peer review assignment', response.body)
        assert_does_not_contain('Review peer assignments', response.body)

        actions.login(email)
        actions.register(self, name)

        # Check that the sample peer-review assignment shows up in the course
        # page and that it can be visited.
        response = actions.view_course(self)
        assert_contains('Sample peer review assignment', response.body)
        assert_contains('Review peer assignments', response.body)
        assert_contains(
            '<a href="assessment?name=%s">' % LEGACY_REVIEW_UNIT_ID,
            response.body)
        assert_contains('<span> Review peer assignments </span>', response.body,
                        collapse_whitespace=True)
        assert_does_not_contain('<a href="reviewdashboard', response.body,
                                collapse_whitespace=True)

        # Check that the progress circle for this assignment is unfilled.
        assert_contains(
            'progress-notstarted-%s' % LEGACY_REVIEW_UNIT_ID, response.body)
        assert_does_not_contain(
            'progress-completed-%s' % LEGACY_REVIEW_UNIT_ID, response.body)

        # Try to access an invalid assignment.
        response = self.get(
            'assessment?name=FakeAssessment', expect_errors=True)
        assert_equals(response.status_int, 404)

        # The student should not be able to see others' reviews because he/she
        # has not submitted an assignment yet.
        response = self.get('assessment?name=%s' % LEGACY_REVIEW_UNIT_ID)
        assert_contains('Due date for this assignment', response.body)
        assert_does_not_contain('Reviews received', response.body)

        # The student submits the assignment.
        response = actions.submit_assessment(
            self,
            LEGACY_REVIEW_UNIT_ID,
            {'answers': submission, 'assessment_type': LEGACY_REVIEW_UNIT_ID}
        )
        assert_contains(
            'Thank you for completing this assignment', response.body)
        assert_contains('Review peer assignments', response.body)

        # The student views the submitted assignment.
        response = self.get('assessment?name=%s' % LEGACY_REVIEW_UNIT_ID)
        assert_contains('First answer to Q1', response.body)

        # The student tries to re-submit the same assignment. This should fail.
        response = actions.submit_assessment(
            self,
            LEGACY_REVIEW_UNIT_ID,
            {'answers': second_submission,
             'assessment_type': LEGACY_REVIEW_UNIT_ID},
            presubmit_checks=False
        )
        assert_contains(
            'You have already submitted this assignment.', response.body)
        assert_contains('Review peer assignments', response.body)

        # The student views the submitted assignment. The new answers have not
        # been saved.
        response = self.get('assessment?name=%s' % LEGACY_REVIEW_UNIT_ID)
        assert_contains('First answer to Q1', response.body)
        assert_does_not_contain('Second answer to Q1', response.body)

        # The student checks the course page and sees that the progress
        # circle for this assignment has been filled, and that the 'Review
        # peer assignments' link is now available.
        response = actions.view_course(self)
        assert_contains(
            'progress-completed-%s' % LEGACY_REVIEW_UNIT_ID, response.body)
        assert_does_not_contain(
            '<span> Review peer assignments </span>', response.body,
            collapse_whitespace=True)
        assert_contains(
            '<a href="reviewdashboard?unit=%s">' % LEGACY_REVIEW_UNIT_ID,
            response.body, collapse_whitespace=True)
