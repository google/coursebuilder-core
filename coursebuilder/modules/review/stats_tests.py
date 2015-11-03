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

from modules.review import controllers_tests
from tests.functional import actions


class PeerReviewAnalyticsTest(actions.TestBase):
    """Tests the peer review analytics page on the Course Author dashboard."""

    # pylint: disable=too-many-statements
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
        response = self.get('dashboard?action=peer_review')
        actions.assert_contains(
            'Google &gt; Dashboard &gt; Manage &gt; Peer review',
            response.body)
        actions.assert_contains('have not been calculated yet', response.body)

        response = response.forms[
            'gcb-generate-analytics-data'].submit().follow()
        assert len(self.taskq.GetTasks('default')) == 1

        actions.assert_contains('is running', response.body)

        self.execute_all_deferred_tasks()

        response = self.get(response.request.url)
        actions.assert_contains('were last updated at', response.body)
        actions.assert_contains('Peer review', response.body)
        actions.assert_contains('Sample peer review assignment', response.body)
        # JSON code for the completion statistics.
        actions.assert_contains('"[{\\"stats\\": [2]', response.body)
        actions.logout()

        # Student2 requests a review.
        actions.login(student2)
        response = actions.request_new_review(
            self, controllers_tests.LEGACY_REVIEW_UNIT_ID)
        review_step_key_2_for_1 = controllers_tests.get_review_step_key(
            response)
        actions.assert_contains('Assignment to review', response.body)

        # Student2 submits the review.
        response = actions.submit_review(
            self, controllers_tests.LEGACY_REVIEW_UNIT_ID,
            review_step_key_2_for_1,
            controllers_tests.get_review_payload('R2for1'))
        actions.assert_contains(
            'Your review has been submitted successfully', response.body)
        actions.logout()

        actions.login(email, is_admin=True)
        response = self.get('dashboard?action=peer_review')
        actions.assert_contains(
            'Google &gt; Dashboard &gt; Manage &gt; Peer review',
            response.body)

        response = response.forms[
            'gcb-generate-analytics-data'].submit().follow()
        self.execute_all_deferred_tasks()

        response = self.get(response.request.url)
        actions.assert_contains('Peer review', response.body)
        # JSON code for the completion statistics.
        actions.assert_contains('"[{\\"stats\\": [1, 1]', response.body)
        actions.logout()
