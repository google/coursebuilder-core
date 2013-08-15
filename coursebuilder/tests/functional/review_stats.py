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

"""Tests for modules/review/stats.py."""

__author__ = 'Sean Lip'

import actions
from actions import assert_contains
from actions import assert_equals
from controllers_review import get_review_payload
from controllers_review import get_review_step_key
from controllers_review import LEGACY_REVIEW_UNIT_ID


class PeerReviewAnalyticsTest(actions.TestBase):
    """Tests the peer review analytics page on the Course Author dashboard."""

    def test_peer_review_analytics(self):
        """Test analytics page on course dashboard."""

        student1 = 'student1@google.com'
        name1 = 'Test Student 1'
        student2 = 'student2@google.com'
        name2 = 'Test Student 2'

        peer = {'assessment_type': 'ReviewAssessmentExample'}

        # Student 1 submits a peer review assessment.
        actions.login(student1)
        actions.register(self, name1)
        actions.submit_assessment(self, 'ReviewAssessmentExample', peer)
        actions.logout()

        # Student 2 submits the same peer review assessment.
        actions.login(student2)
        actions.register(self, name2)
        actions.submit_assessment(self, 'ReviewAssessmentExample', peer)
        actions.logout()

        email = 'admin@google.com'

        # The admin looks at the analytics page on the dashboard.
        actions.login(email, is_admin=True)
        response = self.get('dashboard?action=analytics')
        assert_contains(
            'Google &gt; Dashboard &gt; Analytics', response.body)
        assert_contains('have not been calculated yet', response.body)

        compute_form = response.forms['gcb-compute-student-stats']
        response = self.submit(compute_form)
        assert_equals(response.status_int, 302)
        assert len(self.taskq.GetTasks('default')) == 4

        response = self.get('dashboard?action=analytics')
        assert_contains('is running', response.body)

        self.execute_all_deferred_tasks()

        response = self.get('dashboard?action=analytics')
        assert_contains('were last updated at', response.body)
        assert_contains('currently enrolled: 2', response.body)
        assert_contains('total: 2', response.body)

        assert_contains('Peer Review Statistics', response.body)
        assert_contains('Sample peer review assignment', response.body)
        # JSON code for the completion statistics.
        assert_contains('"[{\\"stats\\": [2]', response.body)
        actions.logout()

        # Student2 requests a review.
        actions.login(student2)
        response = actions.request_new_review(self, LEGACY_REVIEW_UNIT_ID)
        review_step_key_2_for_1 = get_review_step_key(response)
        assert_contains('Assignment to review', response.body)

        # Student2 submits the review.
        response = actions.submit_review(
            self, LEGACY_REVIEW_UNIT_ID, review_step_key_2_for_1,
            get_review_payload('R2for1'))
        assert_contains(
            'Your review has been submitted successfully', response.body)
        actions.logout()

        actions.login(email, is_admin=True)
        response = self.get('dashboard?action=analytics')
        assert_contains(
            'Google &gt; Dashboard &gt; Analytics', response.body)

        compute_form = response.forms['gcb-compute-student-stats']
        response = self.submit(compute_form)
        self.execute_all_deferred_tasks()

        response = self.get('dashboard?action=analytics')
        assert_contains('Peer Review Statistics', response.body)
        # JSON code for the completion statistics.
        assert_contains('"[{\\"stats\\": [1, 1]', response.body)
        actions.logout()
