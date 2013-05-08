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
        assert len(self.taskq.GetTasks('default')) == 2

        response = self.get('dashboard?action=analytics')
        assert_contains('is running', response.body)

        self.execute_all_deferred_tasks()

        response = self.get('dashboard?action=analytics')
        assert_contains('were last updated on', response.body)
        assert_contains('currently enrolled: 2', response.body)
        assert_contains('total: 2', response.body)

        assert_contains('Peer Review Analytics', response.body)
        assert_contains('Sample peer review assignment', response.body)
        # JSON code for the completion statistics.
        assert_contains('"[{\\"stats\\": [2]', response.body)

        # TODO(sll): Add the following actions here once we have written the
        # actions for request_new_review, submit_review::
        # - Student2 requests a review.
        # - Student2 submits the review.
        # The JSON code should then become [1, 1] after the actions above are
        # completed.
