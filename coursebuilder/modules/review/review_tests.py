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

"""Functional tests for modules/review/review.py."""

__author__ = [
    'johncox@google.com (John Cox)',
]

import datetime
import types
import urllib

from common import crypto
from common import schema_transforms
from common import utils as common_utils
from controllers import sites
from models import data_sources
from models import models
from models import student_work
from models import transforms
from modules.review import domain
from modules.review import peer
from modules.review import review as review_module
from modules.upload import upload
from tests.functional import actions
from google.appengine.ext import db


class ManagerTest(actions.TestBase):
    """Tests for review.Manager."""

    def setUp(self):
        super(ManagerTest, self).setUp()
        self.reviewee = models.Student(key_name='reviewee@example.com')
        self.reviewee_key = self.reviewee.put()
        self.reviewer = models.Student(key_name='reviewer@example.com')
        self.reviewer_key = self.reviewer.put()
        self.unit_id = '1'
        self.submission_key = db.Key.from_path(
            student_work.Submission.kind(),
            student_work.Submission.key_name(
                reviewee_key=self.reviewee_key, unit_id=self.unit_id))

    def test_add_reviewer_adds_new_step_and_summary(self):
        step_key = review_module.Manager.add_reviewer(
            self.unit_id, self.submission_key, self.reviewee_key,
            self.reviewer_key)
        step = db.get(step_key)
        summary = db.get(step.review_summary_key)

        self.assertEqual(domain.ASSIGNER_KIND_HUMAN, step.assigner_kind)
        self.assertEqual(self.reviewee_key, step.reviewee_key)
        self.assertEqual(self.reviewer_key, step.reviewer_key)
        self.assertEqual(domain.REVIEW_STATE_ASSIGNED, step.state)
        self.assertEqual(self.submission_key, step.submission_key)
        self.assertEqual(self.unit_id, step.unit_id)

        self.assertEqual(1, summary.assigned_count)
        self.assertEqual(0, summary.completed_count)
        self.assertEqual(0, summary.expired_count)
        self.assertEqual(self.reviewee_key, summary.reviewee_key)
        self.assertEqual(self.submission_key, summary.submission_key)
        self.assertEqual(self.unit_id, summary.unit_id)

    def test_add_reviewer_existing_raises_assertion_when_summary_missing(self):
        missing_key = db.Key.from_path(
            peer.ReviewSummary.kind(), 'no_summary_found_for_key')
        peer.ReviewStep(
            assigner_kind=domain.ASSIGNER_KIND_AUTO,
            review_key=db.Key.from_path(student_work.Review.kind(), 'review'),
            review_summary_key=missing_key, reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            state=domain.REVIEW_STATE_ASSIGNED, unit_id=self.unit_id
        ).put()

        self.assertRaises(
            AssertionError, review_module.Manager.add_reviewer, self.unit_id,
            self.submission_key, self.reviewee_key, self.reviewer_key)

    def test_add_reviewer_existing_raises_transition_error_when_assigned(self):
        summary_key = peer.ReviewSummary(
            assigned_count=1, reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            unit_id=self.unit_id
        ).put()
        peer.ReviewStep(
            assigner_kind=domain.ASSIGNER_KIND_AUTO,
            review_key=db.Key.from_path(student_work.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            state=domain.REVIEW_STATE_ASSIGNED, unit_id=self.unit_id
        ).put()

        self.assertRaises(
            domain.TransitionError, review_module.Manager.add_reviewer,
            self.unit_id, self.submission_key, self.reviewee_key,
            self.reviewer_key)

    def test_add_reviewer_existing_raises_transition_error_when_completed(self):
        summary_key = peer.ReviewSummary(
            completed_count=1, reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            unit_id=self.unit_id
        ).put()
        peer.ReviewStep(
            assigner_kind=domain.ASSIGNER_KIND_AUTO,
            review_key=db.Key.from_path(student_work.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            state=domain.REVIEW_STATE_COMPLETED, unit_id=self.unit_id
        ).put()

        self.assertRaises(
            domain.TransitionError, review_module.Manager.add_reviewer,
            self.unit_id, self.submission_key, self.reviewee_key,
            self.reviewer_key)

    def test_add_reviewer_unremoved_existing_changes_expired_to_assigned(self):
        summary_key = peer.ReviewSummary(
            expired_count=1, reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            unit_id=self.unit_id
        ).put()
        step_key = peer.ReviewStep(
            assigner_kind=domain.ASSIGNER_KIND_AUTO,
            review_key=db.Key.from_path(student_work.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            state=domain.REVIEW_STATE_EXPIRED, unit_id=self.unit_id
        ).put()
        review_module.Manager.add_reviewer(
            self.unit_id, self.submission_key, self.reviewee_key,
            self.reviewer_key)
        step, summary = db.get([step_key, summary_key])

        self.assertEqual(domain.ASSIGNER_KIND_HUMAN, step.assigner_kind)
        self.assertEqual(domain.REVIEW_STATE_ASSIGNED, step.state)
        self.assertFalse(step.removed)

        self.assertEqual(1, summary.assigned_count)
        self.assertEqual(0, summary.expired_count)

    def test_add_reviewer_removed_unremoves_assigned_step(self):
        summary_key = peer.ReviewSummary(
            reviewee_key=self.reviewee_key, reviewer_key=self.reviewer_key,
            submission_key=self.submission_key, unit_id=self.unit_id
        ).put()
        step_key = peer.ReviewStep(
            assigner_kind=domain.ASSIGNER_KIND_AUTO, removed=True,
            review_key=db.Key.from_path(student_work.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            state=domain.REVIEW_STATE_ASSIGNED, unit_id=self.unit_id
        ).put()
        review_module.Manager.add_reviewer(
            self.unit_id, self.submission_key, self.reviewee_key,
            self.reviewer_key)
        step, summary = db.get([step_key, summary_key])

        self.assertEqual(domain.ASSIGNER_KIND_HUMAN, step.assigner_kind)
        self.assertEqual(domain.REVIEW_STATE_ASSIGNED, step.state)
        self.assertFalse(step.removed)

        self.assertEqual(1, summary.assigned_count)

    def test_add_reviewer_removed_unremoves_completed_step(self):
        summary_key = peer.ReviewSummary(
            reviewee_key=self.reviewee_key, reviewer_key=self.reviewer_key,
            submission_key=self.submission_key, unit_id=self.unit_id
        ).put()
        step_key = peer.ReviewStep(
            assigner_kind=domain.ASSIGNER_KIND_AUTO, removed=True,
            review_key=db.Key.from_path(student_work.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            state=domain.REVIEW_STATE_COMPLETED, unit_id=self.unit_id
        ).put()
        review_module.Manager.add_reviewer(
            self.unit_id, self.submission_key, self.reviewee_key,
            self.reviewer_key)
        step, summary = db.get([step_key, summary_key])

        self.assertEqual(domain.ASSIGNER_KIND_HUMAN, step.assigner_kind)
        self.assertEqual(domain.REVIEW_STATE_COMPLETED, step.state)
        self.assertFalse(step.removed)

        self.assertEqual(1, summary.completed_count)

    def test_add_reviewer_removed_unremoves_and_assigns_expired_step(self):
        summary_key = peer.ReviewSummary(
            expired_count=1, reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            unit_id=self.unit_id
        ).put()
        step_key = peer.ReviewStep(
            assigner_kind=domain.ASSIGNER_KIND_AUTO, removed=True,
            review_key=db.Key.from_path(student_work.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            state=domain.REVIEW_STATE_EXPIRED, unit_id=self.unit_id
        ).put()
        review_module.Manager.add_reviewer(
            self.unit_id, self.submission_key, self.reviewee_key,
            self.reviewer_key)
        step, summary = db.get([step_key, summary_key])

        self.assertEqual(domain.ASSIGNER_KIND_HUMAN, step.assigner_kind)
        self.assertEqual(domain.REVIEW_STATE_ASSIGNED, step.state)
        self.assertFalse(step.removed)

        self.assertEqual(1, summary.assigned_count)
        self.assertEqual(0, summary.expired_count)

    def test_delete_reviewer_marks_step_removed_and_decrements_summary(self):
        summary_key = peer.ReviewSummary(
            assigned_count=1, reviewee_key=self.reviewee_key,
            submission_key=self.submission_key, unit_id=self.unit_id
        ).put()
        step_key = peer.ReviewStep(
            assigner_kind=domain.ASSIGNER_KIND_AUTO,
            review_key=db.Key.from_path(student_work.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            state=domain.REVIEW_STATE_ASSIGNED, unit_id=self.unit_id
        ).put()
        step, summary = db.get([step_key, summary_key])

        self.assertFalse(step.removed)
        self.assertEqual(1, summary.assigned_count)

        deleted_key = review_module.Manager.delete_reviewer(step_key)
        step, summary = db.get([step_key, summary_key])

        self.assertEqual(step_key, deleted_key)
        self.assertTrue(step.removed)
        self.assertEqual(0, summary.assigned_count)

    def test_delete_reviewer_raises_key_error_when_step_missing(self):
        self.assertRaises(
            KeyError, review_module.Manager.delete_reviewer,
            db.Key.from_path(peer.ReviewStep.kind(), 'missing_step_key'))

    def test_delete_reviewer_raises_key_error_when_summary_missing(self):
        missing_key = db.Key.from_path(
            peer.ReviewSummary.kind(), 'missing_review_summary_key')
        step_key = peer.ReviewStep(
            assigner_kind=domain.ASSIGNER_KIND_AUTO,
            review_key=db.Key.from_path(student_work.Review.kind(), 'review'),
            review_summary_key=missing_key, reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            state=domain.REVIEW_STATE_ASSIGNED, unit_id=self.unit_id
        ).put()

        self.assertRaises(
            KeyError, review_module.Manager.delete_reviewer, step_key)

    def test_delete_reviewer_raises_removed_error_if_already_removed(self):
        summary_key = peer.ReviewSummary(
            assigned_count=1, reviewee_key=self.reviewee_key,
            submission_key=self.submission_key, unit_id=self.unit_id
        ).put()
        step_key = peer.ReviewStep(
            assigner_kind=domain.ASSIGNER_KIND_AUTO, removed=True,
            review_key=db.Key.from_path(student_work.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            state=domain.REVIEW_STATE_ASSIGNED, unit_id=self.unit_id
        ).put()

        self.assertRaises(
            domain.RemovedError, review_module.Manager.delete_reviewer,
            step_key)

    def test_expire_review_raises_key_error_when_step_missing(self):
        self.assertRaises(
            KeyError, review_module.Manager.expire_review,
            db.Key.from_path(peer.ReviewStep.kind(), 'missing_step_key'))

    def test_expire_review_raises_key_error_when_summary_missing(self):
        missing_key = db.Key.from_path(
            peer.ReviewSummary.kind(), 'missing_review_summary_key')
        step_key = peer.ReviewStep(
            assigner_kind=domain.ASSIGNER_KIND_AUTO,
            review_key=db.Key.from_path(student_work.Review.kind(), 'review'),
            review_summary_key=missing_key, reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            state=domain.REVIEW_STATE_ASSIGNED, unit_id=self.unit_id
        ).put()

        self.assertRaises(
            KeyError, review_module.Manager.expire_review, step_key)

    def test_expire_review_raises_transition_error_when_state_completed(self):
        summary_key = peer.ReviewSummary(
            completed=1, reviewee_key=self.reviewee_key,
            submission_key=self.submission_key, unit_id=self.unit_id
        ).put()
        step_key = peer.ReviewStep(
            assigner_kind=domain.ASSIGNER_KIND_AUTO,
            review_key=db.Key.from_path(student_work.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            state=domain.REVIEW_STATE_COMPLETED, unit_id=self.unit_id
        ).put()

        self.assertRaises(
            domain.TransitionError, review_module.Manager.expire_review,
            step_key)

    def test_expire_review_raises_transition_error_when_state_expired(self):
        summary_key = peer.ReviewSummary(
            expired_count=1, reviewee_key=self.reviewee_key,
            submission_key=self.submission_key, unit_id=self.unit_id
        ).put()
        step_key = peer.ReviewStep(
            assigner_kind=domain.ASSIGNER_KIND_AUTO,
            review_key=db.Key.from_path(student_work.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            state=domain.REVIEW_STATE_EXPIRED, unit_id=self.unit_id
        ).put()

        self.assertRaises(
            domain.TransitionError, review_module.Manager.expire_review,
            step_key)

    def test_expire_review_raises_removed_error_when_step_removed(self):
        summary_key = peer.ReviewSummary(
            reviewee_key=self.reviewee_key, submission_key=self.submission_key,
            unit_id=self.unit_id
        ).put()
        step_key = peer.ReviewStep(
            assigner_kind=domain.ASSIGNER_KIND_AUTO, removed=True,
            review_key=db.Key.from_path(student_work.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            state=domain.REVIEW_STATE_ASSIGNED, unit_id=self.unit_id
        ).put()

        self.assertRaises(
            domain.RemovedError, review_module.Manager.expire_review, step_key)

    def test_expire_review_transitions_state_and_updates_summary(self):
        summary_key = peer.ReviewSummary(
            assigned_count=1, reviewee_key=self.reviewee_key,
            submission_key=self.submission_key, unit_id=self.unit_id
        ).put()
        step_key = peer.ReviewStep(
            assigner_kind=domain.ASSIGNER_KIND_AUTO,
            review_key=db.Key.from_path(student_work.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            state=domain.REVIEW_STATE_ASSIGNED, unit_id=self.unit_id
        ).put()

        step, summary = db.get([step_key, summary_key])

        self.assertEqual(1, summary.assigned_count)
        self.assertEqual(0, summary.expired_count)
        self.assertEqual(domain.REVIEW_STATE_ASSIGNED, step.state)

        expired_key = review_module.Manager.expire_review(step_key)
        step, summary = db.get([expired_key, summary_key])

        self.assertEqual(0, summary.assigned_count)
        self.assertEqual(1, summary.expired_count)
        self.assertEqual(domain.REVIEW_STATE_EXPIRED, step.state)

    def test_expire_old_reviews_for_unit_expires_found_reviews(self):
        summary_key = peer.ReviewSummary(
            assigned_count=2, completed_count=1, reviewee_key=self.reviewee_key,
            submission_key=self.submission_key, unit_id=self.unit_id
        ).put()
        first_step_key = peer.ReviewStep(
            assigner_kind=domain.ASSIGNER_KIND_AUTO,
            review_key=db.Key.from_path(student_work.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            state=domain.REVIEW_STATE_ASSIGNED, unit_id=self.unit_id
        ).put()
        second_reviewee_key = models.Student(
            key_name='reviewee2@example.com').put()
        second_submission_key = student_work.Submission(
            reviewee_key=second_reviewee_key, unit_id=self.unit_id).put()
        second_step_key = peer.ReviewStep(
            assigner_kind=domain.ASSIGNER_KIND_AUTO,
            review_key=db.Key.from_path(student_work.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=second_reviewee_key,
            reviewer_key=self.reviewer_key,
            submission_key=second_submission_key,
            state=domain.REVIEW_STATE_ASSIGNED, unit_id=self.unit_id
        ).put()
        review_module.Manager.expire_old_reviews_for_unit(0, self.unit_id)
        first_step, second_step, summary = db.get(
            [first_step_key, second_step_key, summary_key])

        self.assertEqual(
            [domain.REVIEW_STATE_EXPIRED, domain.REVIEW_STATE_EXPIRED],
            [step.state for step in [first_step, second_step]])
        self.assertEqual(0, summary.assigned_count)
        self.assertEqual(2, summary.expired_count)

    def test_expire_old_reviews_skips_errors_and_continues_processing(self):
        # Create and bind a function that we can swap in to generate a query
        # that will pick up bad results so we can tell that we skip them.
        query_containing_unprocessable_entities = peer.ReviewStep.all(
            keys_only=True)
        query_fn = types.MethodType(
            lambda x, y, z: query_containing_unprocessable_entities,
            review_module.Manager(), review_module.Manager)
        self.swap(
            review_module.Manager, 'get_expiry_query', query_fn)

        summary_key = peer.ReviewSummary(
            assigned_count=1, completed_count=1, reviewee_key=self.reviewee_key,
            submission_key=self.submission_key, unit_id=self.unit_id
        ).put()
        processable_step_key = peer.ReviewStep(
            assigner_kind=domain.ASSIGNER_KIND_AUTO,
            review_key=db.Key.from_path(student_work.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            state=domain.REVIEW_STATE_ASSIGNED, unit_id=self.unit_id
        ).put()
        second_reviewee_key = models.Student(
            key_name='reviewee2@example.com').put()
        second_submission_key = student_work.Submission(
            reviewee_key=second_reviewee_key, unit_id=self.unit_id).put()
        error_step_key = peer.ReviewStep(
            assigner_kind=domain.ASSIGNER_KIND_AUTO,
            review_key=db.Key.from_path(student_work.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=second_reviewee_key,
            reviewer_key=self.reviewer_key,
            submission_key=second_submission_key,
            state=domain.REVIEW_STATE_COMPLETED, unit_id=self.unit_id
        ).put()
        review_module.Manager.expire_old_reviews_for_unit(0, self.unit_id)
        processed_step, error_step, summary = db.get(
            [processable_step_key, error_step_key, summary_key])

        self.assertEqual(domain.REVIEW_STATE_COMPLETED, error_step.state)
        self.assertEqual(domain.REVIEW_STATE_EXPIRED, processed_step.state)
        self.assertEqual(0, summary.assigned_count)
        self.assertEqual(1, summary.completed_count)
        self.assertEqual(1, summary.expired_count)

    def test_get_assignment_candidates_query_filters_and_orders_correctly(self):
        unused_wrong_unit_key = peer.ReviewSummary(
            reviewee_key=self.reviewee_key, submission_key=self.submission_key,
            unit_id=str(int(self.unit_id) + 1)
        ).put()
        second_reviewee_key = models.Student(
            key_name='reviewee2@example.com').put()
        second_submission_key = student_work.Submission(
            reviewee_key=second_reviewee_key, unit_id=self.unit_id).put()
        older_assigned_and_completed_key = peer.ReviewSummary(
            assigned_count=1, completed_count=1,
            reviewee_key=second_reviewee_key,
            submission_key=second_submission_key, unit_id=self.unit_id
        ).put()
        third_reviewee_key = models.Student(
            key_name='reviewee3@example.com').put()
        third_submission_key = student_work.Submission(
            reviewee_key=third_reviewee_key, unit_id=self.unit_id).put()
        younger_assigned_and_completed_key = peer.ReviewSummary(
            assigned_count=1, completed_count=1,
            reviewee_key=third_reviewee_key,
            submission_key=third_submission_key, unit_id=self.unit_id
        ).put()
        fourth_reviewee_key = models.Student(
            key_name='reviewee4@example.com').put()
        fourth_submission_key = student_work.Submission(
            reviewee_key=fourth_reviewee_key, unit_id=self.unit_id).put()
        completed_but_not_assigned_key = peer.ReviewSummary(
            assigned_count=0, completed_count=1,
            reviewee_key=fourth_reviewee_key,
            submission_key=fourth_submission_key, unit_id=self.unit_id
        ).put()
        fifth_reviewee_key = models.Student(
            key_name='reviewee5@example.com').put()
        fifth_submission_key = student_work.Submission(
            reviewee_key=fifth_reviewee_key, unit_id=self.unit_id).put()
        assigned_but_not_completed_key = peer.ReviewSummary(
            assigned_count=1, completed_count=0,
            reviewee_key=fifth_reviewee_key,
            submission_key=fifth_submission_key, unit_id=self.unit_id
        ).put()

        results = review_module.Manager.get_assignment_candidates_query(
            self.unit_id).fetch(5)
        self.assertEqual([
            assigned_but_not_completed_key,
            completed_but_not_assigned_key,
            older_assigned_and_completed_key,
            younger_assigned_and_completed_key
        ], [r.key() for r in results])

    def test_get_expiry_query_filters_and_orders_correctly(self):
        summary_key = peer.ReviewSummary(
            assigned_count=2, completed_count=1, reviewee_key=self.reviewee_key,
            submission_key=self.submission_key, unit_id=self.unit_id
        ).put()
        unused_completed_step_key = peer.ReviewStep(
            assigner_kind=domain.ASSIGNER_KIND_AUTO,
            review_key=db.Key.from_path(student_work.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            state=domain.REVIEW_STATE_COMPLETED, unit_id=self.unit_id
        ).put()
        second_reviewee_key = models.Student(
            key_name='reviewee2@example.com').put()
        second_submission_key = student_work.Submission(
            reviewee_key=second_reviewee_key, unit_id=self.unit_id).put()
        unused_removed_step_key = peer.ReviewStep(
            assigner_kind=domain.ASSIGNER_KIND_AUTO, removed=True,
            review_key=db.Key.from_path(student_work.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=second_reviewee_key,
            reviewer_key=self.reviewer_key,
            submission_key=second_submission_key,
            state=domain.REVIEW_STATE_ASSIGNED, unit_id=self.unit_id
        ).put()
        third_reviewee_key = models.Student(
            key_name='reviewee3@example.com').put()
        third_submission_key = student_work.Submission(
            reviewee_key=third_reviewee_key, unit_id=self.unit_id).put()
        unused_other_unit_step_key = peer.ReviewStep(
            assigner_kind=domain.ASSIGNER_KIND_AUTO,
            review_key=db.Key.from_path(student_work.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=third_reviewee_key,
            reviewer_key=self.reviewer_key,
            submission_key=third_submission_key,
            state=domain.REVIEW_STATE_ASSIGNED,
            unit_id=str(int(self.unit_id) + 1)
        ).put()
        fourth_reviewee_key = models.Student(
            key_name='reviewee4@example.com').put()
        fourth_submission_key = student_work.Submission(
            reviewee_key=fourth_reviewee_key, unit_id=self.unit_id).put()
        first_assigned_step_key = peer.ReviewStep(
            assigner_kind=domain.ASSIGNER_KIND_AUTO,
            review_key=db.Key.from_path(student_work.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=fourth_reviewee_key,
            reviewer_key=self.reviewer_key,
            submission_key=fourth_submission_key,
            state=domain.REVIEW_STATE_ASSIGNED, unit_id=self.unit_id
        ).put()
        fifth_reviewee_key = models.Student(
            key_name='reviewee5@example.com').put()
        fifth_submission_key = student_work.Submission(
            reviewee_key=fifth_reviewee_key, unit_id=self.unit_id).put()
        second_assigned_step_key = peer.ReviewStep(
            assigner_kind=domain.ASSIGNER_KIND_AUTO,
            review_key=db.Key.from_path(student_work.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=fifth_reviewee_key,
            reviewer_key=self.reviewer_key,
            submission_key=fifth_submission_key,
            state=domain.REVIEW_STATE_ASSIGNED, unit_id=self.unit_id
        ).put()
        zero_review_window_query = review_module.Manager.get_expiry_query(
            0, self.unit_id)
        future_review_window_query = review_module.Manager.get_expiry_query(
            1, self.unit_id)

        self.assertEqual(
            [first_assigned_step_key, second_assigned_step_key],
            zero_review_window_query.fetch(3))
        # No items are > 1 minute old, so we expect an empty result set.
        self.assertEqual(None, future_review_window_query.get())

    def test_get_new_review_creates_step_and_updates_summary(self):
        summary_key = peer.ReviewSummary(
            reviewee_key=self.reviewee_key, submission_key=self.submission_key,
            unit_id=self.unit_id
        ).put()
        summary = db.get(summary_key)

        self.assertEqual(0, summary.assigned_count)

        step_key = review_module.Manager.get_new_review(
            self.unit_id, self.reviewer_key)
        step, summary = db.get([step_key, summary_key])

        self.assertEqual(domain.ASSIGNER_KIND_AUTO, step.assigner_kind)
        self.assertEqual(summary.key(), step.review_summary_key)
        self.assertEqual(self.reviewee_key, step.reviewee_key)
        self.assertEqual(self.reviewer_key, step.reviewer_key)
        self.assertEqual(domain.REVIEW_STATE_ASSIGNED, step.state)
        self.assertEqual(self.submission_key, step.submission_key)
        self.assertEqual(self.unit_id, step.unit_id)

        self.assertEqual(1, summary.assigned_count)

    def test_get_new_review_raises_key_error_when_summary_missing(self):
        summary_key = peer.ReviewSummary(
            reviewee_key=self.reviewee_key, submission_key=self.submission_key,
            unit_id=self.unit_id
        ).put()

        # Create and bind a function that we can swap in to pick the review
        # candidate but as a side effect delete the review summary, causing a
        # the lookup by key to fail.
        def pick_and_remove(unused_cls, candidates):
            db.delete(summary_key)
            return candidates[0]

        fn = types.MethodType(
            pick_and_remove, review_module.Manager(), review_module.Manager)
        self.swap(
            review_module.Manager, '_choose_assignment_candidate', fn)

        self.assertRaises(
            KeyError, review_module.Manager.get_new_review, self.unit_id,
            self.reviewer_key)

    def test_get_new_review_raises_not_assignable_when_already_assigned(self):
        summary_key = peer.ReviewSummary(
            assigned_count=1, reviewee_key=self.reviewee_key,
            submission_key=self.submission_key, unit_id=self.unit_id
        ).put()
        unused_already_assigned_step_key = peer.ReviewStep(
            assigner_kind=domain.ASSIGNER_KIND_AUTO,
            review_key=db.Key.from_path(student_work.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            state=domain.REVIEW_STATE_ASSIGNED, unit_id=self.unit_id
        ).put()

        self.assertRaises(
            domain.NotAssignableError, review_module.Manager.get_new_review,
            self.unit_id, self.reviewer_key)

    def test_get_new_review_raises_not_assignable_when_already_completed(self):
        summary_key = peer.ReviewSummary(
            completed=1, reviewee_key=self.reviewee_key,
            submission_key=self.submission_key, unit_id=self.unit_id
        ).put()
        already_completed_unremoved_step_key = peer.ReviewStep(
            assigner_kind=domain.ASSIGNER_KIND_AUTO,
            review_key=db.Key.from_path(student_work.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            state=domain.REVIEW_STATE_COMPLETED, unit_id=self.unit_id
        ).put()

        self.assertRaises(
            domain.NotAssignableError, review_module.Manager.get_new_review,
            self.unit_id, self.reviewer_key)

        db.delete(already_completed_unremoved_step_key)
        unused_already_completed_removed_step_key = peer.ReviewStep(
            assigner_kind=domain.ASSIGNER_KIND_AUTO, removed=True,
            review_key=db.Key.from_path(student_work.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            state=domain.REVIEW_STATE_COMPLETED, unit_id=self.unit_id
        ).put()

        self.assertRaises(
            domain.NotAssignableError, review_module.Manager.get_new_review,
            self.unit_id, self.reviewer_key)

    def test_get_new_review_raises_not_assignable_when_review_is_for_self(self):
        peer.ReviewSummary(
            assigned_count=1, reviewee_key=self.reviewer_key,
            submission_key=self.submission_key, unit_id=self.unit_id
        ).put()

        self.assertRaises(
            domain.NotAssignableError, review_module.Manager.get_new_review,
            self.unit_id,
            self.reviewer_key)

    def test_get_new_review_raises_not_assignable_when_no_candidates(self):
        self.assertRaises(
            domain.NotAssignableError, review_module.Manager.get_new_review,
            self.unit_id, self.reviewer_key)

    def test_get_new_review_raises_not_assignable_when_retry_limit_hit(self):
        higher_priority_summary = peer.ReviewSummary(
            reviewee_key=self.reviewee_key, submission_key=self.submission_key,
            unit_id=self.unit_id)
        higher_priority_summary_key = higher_priority_summary.put()
        second_reviewee_key = models.Student(
            key_name='reviewee2@example.com').put()
        second_submission_key = student_work.Submission(
            reviewee_key=second_reviewee_key, unit_id=self.unit_id).put()
        lower_priority_summary_key = peer.ReviewSummary(
            completed_count=1, reviewee_key=second_reviewee_key,
            submission_key=second_submission_key, unit_id=self.unit_id
        ).put()

        self.assertEqual(  # Ensure we'll process higher priority first.
            [higher_priority_summary_key, lower_priority_summary_key],
            [c.key() for c in
             review_module.Manager.get_assignment_candidates_query(
                 self.unit_id).fetch(2)])

        # Create and bind a function that we can swap in to pick the review
        # candidate but as a side-effect updates the highest priority candidate
        # so we'll skip it and retry.
        def pick_and_update(unused_cls, candidates):
            db.put(higher_priority_summary)
            return candidates[0]

        fn = types.MethodType(
            pick_and_update, review_module.Manager(), review_module.Manager)
        self.swap(
            review_module.Manager, '_choose_assignment_candidate', fn)

        self.assertRaises(
            domain.NotAssignableError, review_module.Manager.get_new_review,
            self.unit_id, self.reviewer_key, max_retries=0)

    def test_get_new_review_raises_not_assignable_when_summary_updated(self):
        summary = peer.ReviewSummary(
            reviewee_key=self.reviewee_key, submission_key=self.submission_key,
            unit_id=self.unit_id)
        summary.put()

        # Create and bind a function that we can swap in to pick the review
        # candidate but as a side-effect updates the summary so we'll reject it
        # as a candidate.
        def pick_and_update(unused_cls, candidates):
            db.put(summary)
            return candidates[0]

        fn = types.MethodType(
            pick_and_update, review_module.Manager(), review_module.Manager)
        self.swap(
            review_module.Manager, '_choose_assignment_candidate', fn)

        self.assertRaises(
            domain.NotAssignableError, review_module.Manager.get_new_review,
            self.unit_id, self.reviewer_key)

    def test_get_new_review_reassigns_removed_assigned_step(self):
        summary_key = peer.ReviewSummary(
            reviewee_key=self.reviewee_key, submission_key=self.submission_key,
            unit_id=self.unit_id
        ).put()
        unused_already_assigned_removed_step_key = peer.ReviewStep(
            assigner_kind=domain.ASSIGNER_KIND_HUMAN, removed=True,
            review_key=db.Key.from_path(student_work.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            state=domain.REVIEW_STATE_ASSIGNED, unit_id=self.unit_id
        ).put()

        step_key = review_module.Manager.get_new_review(
            self.unit_id, self.reviewer_key)
        step, summary = db.get([step_key, summary_key])

        self.assertEqual(domain.ASSIGNER_KIND_AUTO, step.assigner_kind)
        self.assertFalse(step.removed)
        self.assertEqual(domain.REVIEW_STATE_ASSIGNED, step.state)

        self.assertEqual(1, summary.assigned_count)

    def test_get_new_review_reassigns_removed_expired_step(self):
        summary_key = peer.ReviewSummary(
            reviewee_key=self.reviewee_key, submission_key=self.submission_key,
            unit_id=self.unit_id
        ).put()
        unused_already_expired_removed_step_key = peer.ReviewStep(
            assigner_kind=domain.ASSIGNER_KIND_HUMAN, removed=True,
            review_key=db.Key.from_path(student_work.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            state=domain.REVIEW_STATE_EXPIRED, unit_id=self.unit_id
        ).put()

        step_key = review_module.Manager.get_new_review(
            self.unit_id, self.reviewer_key)
        step, summary = db.get([step_key, summary_key])

        self.assertEqual(domain.ASSIGNER_KIND_AUTO, step.assigner_kind)
        self.assertFalse(step.removed)
        self.assertEqual(domain.REVIEW_STATE_ASSIGNED, step.state)

        self.assertEqual(1, summary.assigned_count)
        self.assertEqual(0, summary.expired_count)

    def test_get_new_review_retries_successfully(self):
        higher_priority_summary = peer.ReviewSummary(
            reviewee_key=self.reviewee_key, submission_key=self.submission_key,
            unit_id=self.unit_id)
        higher_priority_summary_key = higher_priority_summary.put()
        second_reviewee_key = models.Student(
            key_name='reviewee2@example.com').put()
        second_submission_key = student_work.Submission(
            reviewee_key=second_reviewee_key, unit_id=self.unit_id).put()
        lower_priority_summary_key = peer.ReviewSummary(
            completed_count=1, reviewee_key=second_reviewee_key,
            submission_key=second_submission_key, unit_id=self.unit_id
        ).put()

        self.assertEqual(  # Ensure we'll process higher priority first.
            [higher_priority_summary_key, lower_priority_summary_key],
            [c.key() for c in
             review_module.Manager.get_assignment_candidates_query(
                 self.unit_id).fetch(2)])

        # Create and bind a function that we can swap in to pick the review
        # candidate but as a side-effect updates the highest priority candidate
        # so we'll skip it and retry.
        def pick_and_update(unused_cls, candidates):
            db.put(higher_priority_summary)
            return candidates[0]

        fn = types.MethodType(
            pick_and_update, review_module.Manager(), review_module.Manager)
        self.swap(
            review_module.Manager, '_choose_assignment_candidate', fn)

        step_key = review_module.Manager.get_new_review(
            self.unit_id, self.reviewer_key)
        step = db.get(step_key)

        self.assertEqual(lower_priority_summary_key, step.review_summary_key)

    def test_get_review_step_keys_by_returns_list_of_keys(self):
        summary_key = peer.ReviewSummary(
            reviewee_key=self.reviewee_key, submission_key=self.submission_key,
            unit_id=self.unit_id
        ).put()
        matching_step_key = peer.ReviewStep(
            assigner_kind=domain.ASSIGNER_KIND_AUTO, removed=True,
            review_key=db.Key.from_path(student_work.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            state=domain.REVIEW_STATE_EXPIRED, unit_id=self.unit_id
        ).put()
        non_matching_reviewer = models.Student(key_name='reviewer2@example.com')
        non_matching_reviewer_key = non_matching_reviewer.put()
        unused_non_matching_step_key = peer.ReviewStep(
            assigner_kind=domain.ASSIGNER_KIND_AUTO, removed=True,
            review_key=db.Key.from_path(student_work.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=self.reviewee_key,
            reviewer_key=non_matching_reviewer_key,
            submission_key=self.submission_key,
            state=domain.REVIEW_STATE_EXPIRED,
            unit_id=self.unit_id
        ).put()

        self.assertEqual(
            [matching_step_key],
            review_module.Manager.get_review_step_keys_by(
                self.unit_id, self.reviewer_key))

    def test_get_review_step_keys_by_returns_keys_in_sorted_order(self):
        summary_key = peer.ReviewSummary(
            reviewee_key=self.reviewee_key, submission_key=self.submission_key,
            unit_id=self.unit_id
        ).put()
        first_step_key = peer.ReviewStep(
            assigner_kind=domain.ASSIGNER_KIND_AUTO, removed=True,
            review_key=db.Key.from_path(student_work.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            state=domain.REVIEW_STATE_EXPIRED, unit_id=self.unit_id
        ).put()

        second_reviewee_key = models.Student(
            key_name='reviewee2@example.com').put()
        second_submission_key = student_work.Submission(
            reviewee_key=second_reviewee_key, unit_id=self.unit_id).put()
        second_step_key = peer.ReviewStep(
            assigner_kind=domain.ASSIGNER_KIND_AUTO, removed=True,
            review_key=db.Key.from_path(student_work.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=second_reviewee_key,
            reviewer_key=self.reviewer_key,
            submission_key=second_submission_key,
            state=domain.REVIEW_STATE_EXPIRED, unit_id=self.unit_id
        ).put()

        self.assertEqual(
            [first_step_key, second_step_key],
            review_module.Manager.get_review_step_keys_by(
                self.unit_id, self.reviewer_key))

    def test_get_review_step_keys_by_returns_empty_list_when_no_matches(self):
        summary_key = peer.ReviewSummary(
            reviewee_key=self.reviewee_key, submission_key=self.submission_key,
            unit_id=self.unit_id
        ).put()
        non_matching_reviewer = models.Student(key_name='reviewer2@example.com')
        non_matching_reviewer_key = non_matching_reviewer.put()
        unused_non_matching_step_different_reviewer_key = peer.ReviewStep(
            assigner_kind=domain.ASSIGNER_KIND_AUTO, removed=True,
            review_key=db.Key.from_path(student_work.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=self.reviewee_key,
            reviewer_key=non_matching_reviewer_key,
            submission_key=self.submission_key,
            state=domain.REVIEW_STATE_EXPIRED,
            unit_id=self.unit_id,
        ).put()
        unused_non_matching_step_different_unit_id_key = peer.ReviewStep(
            assigner_kind=domain.ASSIGNER_KIND_AUTO, removed=True,
            review_key=db.Key.from_path(student_work.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            state=domain.REVIEW_STATE_EXPIRED,
            unit_id=str(int(self.unit_id) + 1),
        ).put()

        self.assertEqual(
            [], review_module.Manager.get_review_step_keys_by(
                self.unit_id, self.reviewer_key))

    def test_get_review_steps_by_keys(self):
        summary_key = peer.ReviewSummary(
            reviewee_key=self.reviewee_key, submission_key=self.submission_key,
            unit_id=self.unit_id
        ).put()
        step_key = peer.ReviewStep(
            assigner_kind=domain.ASSIGNER_KIND_HUMAN, removed=True,
            review_key=db.Key.from_path(student_work.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            state=domain.REVIEW_STATE_EXPIRED, unit_id=self.unit_id
        ).put()
        second_reviewer_key = models.Student(
            key_name='reviewer2@example.com').put()
        missing_step_key = db.Key.from_path(
            peer.ReviewStep.kind(),
            peer.ReviewStep.key_name(
                self.submission_key, second_reviewer_key))
        model_objects = db.get([step_key, missing_step_key])
        domain_objects = review_module.Manager.get_review_steps_by_keys(
            [step_key, missing_step_key])
        model_step, model_miss = model_objects
        domain_step, domain_miss = domain_objects

        self.assertEqual(2, len(model_objects))
        self.assertEqual(2, len(domain_objects))

        self.assertIsNone(model_miss)
        self.assertIsNone(domain_miss)

        self.assertEqual(model_step.assigner_kind, domain_step.assigner_kind)
        self.assertEqual(model_step.change_date, domain_step.change_date)
        self.assertEqual(model_step.create_date, domain_step.create_date)
        self.assertEqual(model_step.key(), domain_step.key)
        self.assertEqual(model_step.removed, domain_step.removed)
        self.assertEqual(model_step.review_key, domain_step.review_key)
        self.assertEqual(
            model_step.review_summary_key, domain_step.review_summary_key)
        self.assertEqual(model_step.reviewee_key, domain_step.reviewee_key)
        self.assertEqual(model_step.reviewer_key, domain_step.reviewer_key)
        self.assertEqual(model_step.state, domain_step.state)
        self.assertEqual(model_step.submission_key, domain_step.submission_key)
        self.assertEqual(model_step.unit_id, domain_step.unit_id)

    def test_get_reviews_by_keys(self):
        review_key = student_work.Review(
            contents='contents', reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, unit_id=self.unit_id
        ).put()
        missing_review_key = db.Key.from_path(
            student_work.Review.kind(),
            student_work.Review.key_name(
                str(int(self.unit_id) + 1), self.reviewee_key,
                self.reviewer_key))
        model_objects = db.get([review_key, missing_review_key])
        domain_objects = review_module.Manager.get_reviews_by_keys(
            [review_key, missing_review_key])
        model_review, model_miss = model_objects
        domain_review, domain_miss = domain_objects

        self.assertEqual(2, len(model_objects))
        self.assertEqual(2, len(domain_objects))

        self.assertIsNone(model_miss)
        self.assertIsNone(domain_miss)

        self.assertEqual(model_review.contents, domain_review.contents)
        self.assertEqual(model_review.key(), domain_review.key)

    def test_get_submission_and_review_step_keys_no_steps(self):
        student_work.Submission(
            reviewee_key=self.reviewee_key, unit_id=self.unit_id).put()
        peer.ReviewSummary(
            reviewee_key=self.reviewee_key, submission_key=self.submission_key,
            unit_id=self.unit_id
        ).put()

        self.assertEqual(
            (self.submission_key, []),
            review_module.Manager.get_submission_and_review_step_keys(
                self.unit_id, self.reviewee_key))

    def test_get_submission_and_review_step_keys_with_steps(self):
        student_work.Submission(
            reviewee_key=self.reviewee_key, unit_id=self.unit_id).put()
        summary_key = peer.ReviewSummary(
            reviewee_key=self.reviewee_key, submission_key=self.submission_key,
            unit_id=self.unit_id
        ).put()
        matching_step_key = peer.ReviewStep(
            assigner_kind=domain.ASSIGNER_KIND_AUTO, removed=True,
            review_key=db.Key.from_path(student_work.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            state=domain.REVIEW_STATE_EXPIRED, unit_id=self.unit_id
        ).put()
        non_matching_reviewee_key = models.Student(
            key_name='reviewee2@example.com').put()
        non_matching_submission_key = student_work.Submission(
            contents='contents2', reviewee_key=non_matching_reviewee_key,
            unit_id=self.unit_id).put()
        unused_non_matching_step_different_submission_key = peer.ReviewStep(
            assigner_kind=domain.ASSIGNER_KIND_AUTO, removed=True,
            review_key=db.Key.from_path(student_work.Review.kind(), 'review'),
            review_summary_key=summary_key,
            reviewee_key=non_matching_reviewee_key,
            reviewer_key=self.reviewer_key,
            submission_key=non_matching_submission_key,
            state=domain.REVIEW_STATE_EXPIRED, unit_id=self.unit_id
        ).put()

        self.assertEqual(
            (self.submission_key, [matching_step_key]),
            review_module.Manager.get_submission_and_review_step_keys(
                self.unit_id, self.reviewee_key))

    def test_get_submission_and_review_step_keys_returns_none_on_miss(self):
        self.assertIsNone(
            review_module.Manager.get_submission_and_review_step_keys(
                self.unit_id, self.reviewee_key))

    def test_get_submissions_by_keys(self):
        submission_key = student_work.Submission(
            contents='contents', reviewee_key=self.reviewee_key,
            unit_id=self.unit_id).put()
        missing_submission_key = db.Key.from_path(
            student_work.Submission.kind(),
            student_work.Submission.key_name(
                str(int(self.unit_id) + 1), self.reviewee_key))
        domain_models = db.get([submission_key, missing_submission_key])
        domain_objects = review_module.Manager.get_submissions_by_keys(
            [submission_key, missing_submission_key])
        model_submission, model_miss = domain_models
        domain_submission, domain_miss = domain_objects

        self.assertEqual(2, len(domain_models))
        self.assertEqual(2, len(domain_objects))

        self.assertIsNone(model_miss)
        self.assertIsNone(domain_miss)

        self.assertEqual(model_submission.contents, domain_submission.contents)
        self.assertEqual(model_submission.key(), domain_submission.key)

    def test_start_review_process_for_succeeds(self):
        key = review_module.Manager.start_review_process_for(
            self.unit_id, self.submission_key, self.reviewee_key)
        summary = db.get(key)

        self.assertEqual(self.reviewee_key, summary.reviewee_key)
        self.assertEqual(self.submission_key, summary.submission_key)
        self.assertEqual(self.unit_id, summary.unit_id)

    def test_start_review_process_for_throws_if_already_started(self):
        collision = peer.ReviewSummary(
            reviewee_key=self.reviewee_key, submission_key=self.submission_key,
            unit_id=self.unit_id)
        collision.put()

        self.assertRaises(
            domain.ReviewProcessAlreadyStartedError,
            review_module.Manager.start_review_process_for,
            self.unit_id, self.submission_key, self.reviewee_key)

    def test_write_review_raises_constraint_error_if_key_but_no_review(self):
        summary_key = peer.ReviewSummary(
            assigned_count=1, reviewee_key=self.reviewee_key,
            submission_key=self.submission_key, unit_id=self.unit_id
        ).put()
        step_key = peer.ReviewStep(
            assigner_kind=domain.ASSIGNER_KIND_HUMAN,
            review_key=db.Key.from_path(student_work.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            state=domain.REVIEW_STATE_EXPIRED, unit_id=self.unit_id
        ).put()

        self.assertRaises(
            domain.ConstraintError, review_module.Manager.write_review,
            step_key, 'payload')

    def test_write_review_raises_constraint_error_if_no_summary(self):
        missing_summary_key = db.Key.from_path(
            peer.ReviewSummary.kind(),
            peer.ReviewSummary.key_name(self.submission_key))
        review_key = student_work.Review(
            contents='contents', reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key,
            unit_id=self.unit_id).put()
        step_key = peer.ReviewStep(
            assigner_kind=domain.ASSIGNER_KIND_HUMAN,
            review_key=review_key, review_summary_key=missing_summary_key,
            reviewee_key=self.reviewee_key, reviewer_key=self.reviewer_key,
            submission_key=self.submission_key,
            state=domain.REVIEW_STATE_EXPIRED,
            unit_id=self.unit_id
        ).put()

        self.assertRaises(
            domain.ConstraintError, review_module.Manager.write_review,
            step_key, 'payload')

    def test_write_review_raises_key_error_if_no_step(self):
        bad_step_key = db.Key.from_path(peer.ReviewStep.kind(), 'missing')

        self.assertRaises(
            KeyError, review_module.Manager.write_review, bad_step_key,
            'payload')

    def test_write_review_raises_removed_error_if_step_removed(self):
        summary_key = peer.ReviewSummary(
            assigned_count=1, reviewee_key=self.reviewee_key,
            submission_key=self.submission_key, unit_id=self.unit_id
        ).put()
        step_key = peer.ReviewStep(
            assigner_kind=domain.ASSIGNER_KIND_HUMAN, removed=True,
            review_key=db.Key.from_path(student_work.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            state=domain.REVIEW_STATE_EXPIRED, unit_id=self.unit_id
        ).put()

        self.assertRaises(
            domain.RemovedError, review_module.Manager.write_review, step_key,
            'payload')

    def test_write_review_raises_transition_error_if_step_completed(self):
        summary_key = peer.ReviewSummary(
            assigned_count=1, reviewee_key=self.reviewee_key,
            submission_key=self.submission_key, unit_id=self.unit_id
        ).put()
        step_key = peer.ReviewStep(
            assigner_kind=domain.ASSIGNER_KIND_HUMAN,
            review_key=db.Key.from_path(student_work.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            state=domain.REVIEW_STATE_COMPLETED, unit_id=self.unit_id
        ).put()

        self.assertRaises(
            domain.TransitionError, review_module.Manager.write_review,
            step_key, 'payload')

    def test_write_review_with_mark_completed_false(self):
        summary_key = peer.ReviewSummary(
            assigned_count=1, reviewee_key=self.reviewee_key,
            submission_key=self.submission_key, unit_id=self.unit_id
        ).put()
        review_key = student_work.Review(
            contents='old_contents', reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, unit_id=self.unit_id).put()
        step_key = peer.ReviewStep(
            assigner_kind=domain.ASSIGNER_KIND_HUMAN,
            review_key=review_key, review_summary_key=summary_key,
            reviewee_key=self.reviewee_key, reviewer_key=self.reviewer_key,
            submission_key=self.submission_key,
            state=domain.REVIEW_STATE_ASSIGNED, unit_id=self.unit_id
        ).put()
        updated_step_key = review_module.Manager.write_review(
            step_key, 'new_contents', mark_completed=False)

        self.assertEqual(step_key, updated_step_key)

        step, summary = db.get([updated_step_key, summary_key])
        updated_review = db.get(step.review_key)

        self.assertEqual(1, summary.assigned_count)
        self.assertEqual(0, summary.completed_count)
        self.assertEqual(domain.REVIEW_STATE_ASSIGNED, step.state)
        self.assertEqual('new_contents', updated_review.contents)

    def test_write_review_with_no_review_mark_completed_false(self):
        summary_key = peer.ReviewSummary(
            assigned_count=1, reviewee_key=self.reviewee_key,
            submission_key=self.submission_key, unit_id=self.unit_id
        ).put()
        step_key = peer.ReviewStep(
            assigner_kind=domain.ASSIGNER_KIND_HUMAN,
            review_summary_key=summary_key, reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            state=domain.REVIEW_STATE_ASSIGNED, unit_id=self.unit_id
        ).put()
        self.assertIsNone(db.get(step_key).review_key)
        updated_step_key = review_module.Manager.write_review(
            step_key, 'contents', mark_completed=False)

        self.assertEqual(step_key, updated_step_key)

        step, summary = db.get([updated_step_key, summary_key])
        updated_review = db.get(step.review_key)

        self.assertEqual(1, summary.assigned_count)
        self.assertEqual(0, summary.completed_count)
        self.assertEqual(domain.REVIEW_STATE_ASSIGNED, step.state)
        self.assertEqual(step.review_key, updated_review.key())
        self.assertEqual('contents', updated_review.contents)

    def test_write_review_with_no_review_mark_completed_true(self):
        summary_key = peer.ReviewSummary(
            assigned_count=1, reviewee_key=self.reviewee_key,
            submission_key=self.submission_key, unit_id=self.unit_id
        ).put()
        step_key = peer.ReviewStep(
            assigner_kind=domain.ASSIGNER_KIND_HUMAN,
            review_summary_key=summary_key, reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            state=domain.REVIEW_STATE_ASSIGNED, unit_id=self.unit_id
        ).put()
        self.assertIsNone(db.get(step_key).review_key)
        updated_step_key = review_module.Manager.write_review(
            step_key, 'contents')

        self.assertEqual(step_key, updated_step_key)

        step, summary = db.get([updated_step_key, summary_key])
        updated_review = db.get(step.review_key)

        self.assertEqual(0, summary.assigned_count)
        self.assertEqual(1, summary.completed_count)
        self.assertEqual(domain.REVIEW_STATE_COMPLETED, step.state)
        self.assertEqual(step.review_key, updated_review.key())
        self.assertEqual('contents', updated_review.contents)

    def test_write_review_with_state_assigned_and_mark_completed_true(self):
        summary_key = peer.ReviewSummary(
            assigned_count=1, reviewee_key=self.reviewee_key,
            submission_key=self.submission_key, unit_id=self.unit_id
        ).put()
        review_key = student_work.Review(
            contents='old_contents', reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, unit_id=self.unit_id).put()
        step_key = peer.ReviewStep(
            assigner_kind=domain.ASSIGNER_KIND_HUMAN,
            review_key=review_key, review_summary_key=summary_key,
            reviewee_key=self.reviewee_key, reviewer_key=self.reviewer_key,
            submission_key=self.submission_key,
            state=domain.REVIEW_STATE_ASSIGNED, unit_id=self.unit_id
        ).put()
        updated_step_key = review_module.Manager.write_review(
            step_key, 'new_contents')

        self.assertEqual(step_key, updated_step_key)

        step, summary = db.get([updated_step_key, summary_key])
        updated_review = db.get(step.review_key)

        self.assertEqual(0, summary.assigned_count)
        self.assertEqual(1, summary.completed_count)
        self.assertEqual(domain.REVIEW_STATE_COMPLETED, step.state)
        self.assertEqual('new_contents', updated_review.contents)

    def test_write_review_with_state_expired_and_mark_completed_true(self):
        summary_key = peer.ReviewSummary(
            expired_count=1, reviewee_key=self.reviewee_key,
            submission_key=self.submission_key, unit_id=self.unit_id
        ).put()
        review_key = student_work.Review(
            contents='old_contents', reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, unit_id=self.unit_id).put()
        step_key = peer.ReviewStep(
            assigner_kind=domain.ASSIGNER_KIND_HUMAN,
            review_key=review_key, review_summary_key=summary_key,
            reviewee_key=self.reviewee_key, reviewer_key=self.reviewer_key,
            submission_key=self.submission_key,
            state=domain.REVIEW_STATE_EXPIRED, unit_id=self.unit_id
        ).put()
        updated_step_key = review_module.Manager.write_review(
            step_key, 'new_contents')

        self.assertEqual(step_key, updated_step_key)

        step, summary = db.get([updated_step_key, summary_key])
        updated_review = db.get(step.review_key)

        self.assertEqual(1, summary.completed_count)
        self.assertEqual(0, summary.expired_count)
        self.assertEqual(domain.REVIEW_STATE_COMPLETED, step.state)
        self.assertEqual('new_contents', updated_review.contents)

    def test_write_review_with_two_students_creates_different_reviews(self):
        reviewee1 = models.Student(key_name='reviewee1@example.com')
        reviewee1_key = reviewee1.put()
        reviewee2 = models.Student(key_name='reviewee2@example.com')
        reviewee2_key = reviewee2.put()

        submission1_key = db.Key.from_path(
            student_work.Submission.kind(),
            student_work.Submission.key_name(
                reviewee_key=reviewee1_key, unit_id=self.unit_id))
        submission2_key = db.Key.from_path(
            student_work.Submission.kind(),
            student_work.Submission.key_name(
                reviewee_key=reviewee2_key, unit_id=self.unit_id))

        summary1_key = peer.ReviewSummary(
            assigned_count=1, reviewee_key=reviewee1_key,
            submission_key=submission1_key, unit_id=self.unit_id
        ).put()
        step1_key = peer.ReviewStep(
            assigner_kind=domain.ASSIGNER_KIND_HUMAN,
            review_summary_key=summary1_key, reviewee_key=reviewee1_key,
            reviewer_key=self.reviewer_key, submission_key=submission1_key,
            state=domain.REVIEW_STATE_ASSIGNED, unit_id=self.unit_id
        ).put()
        self.assertIsNone(db.get(step1_key).review_key)
        updated_step1_key = review_module.Manager.write_review(
            step1_key, 'contents1', mark_completed=False)

        self.assertEqual(step1_key, updated_step1_key)

        summary2_key = peer.ReviewSummary(
            assigned_count=1, reviewee_key=reviewee2_key,
            submission_key=submission2_key, unit_id=self.unit_id
        ).put()
        step2_key = peer.ReviewStep(
            assigner_kind=domain.ASSIGNER_KIND_HUMAN,
            review_summary_key=summary2_key, reviewee_key=reviewee2_key,
            reviewer_key=self.reviewer_key, submission_key=submission2_key,
            state=domain.REVIEW_STATE_ASSIGNED, unit_id=self.unit_id
        ).put()
        self.assertIsNone(db.get(step2_key).review_key)
        updated_step2_key = review_module.Manager.write_review(
            step2_key, 'contents2', mark_completed=False)

        self.assertEqual(step2_key, updated_step2_key)

        step1, summary1 = db.get([updated_step1_key, summary1_key])
        updated_review = db.get(step1.review_key)

        self.assertEqual(1, summary1.assigned_count)
        self.assertEqual(0, summary1.completed_count)
        self.assertEqual(domain.REVIEW_STATE_ASSIGNED, step1.state)
        self.assertEqual(step1.review_key, updated_review.key())
        self.assertEqual('contents1', updated_review.contents)

        step2, summary2 = db.get([updated_step2_key, summary2_key])
        updated_review = db.get(step2.review_key)

        self.assertEqual(1, summary2.assigned_count)
        self.assertEqual(0, summary2.completed_count)
        self.assertEqual(domain.REVIEW_STATE_ASSIGNED, step2.state)
        self.assertEqual(step2.review_key, updated_review.key())
        self.assertEqual('contents2', updated_review.contents)


class SubmissionDataSourceTest(actions.TestBase):

    ADMIN_EMAIL = 'admin@foo.com'
    COURSE_NAME = 'test_course'
    NAMESPACE = 'ns_%s' % COURSE_NAME
    STUDENT_EMAIL = 'student@foo.com'

    def setUp(self):
        super(SubmissionDataSourceTest, self).setUp()

        self.app_context = actions.simple_add_course(
            self.COURSE_NAME, self.ADMIN_EMAIL, 'Test Course')
        self.base = '/' + self.COURSE_NAME

        actions.login(self.STUDENT_EMAIL)
        actions.register(self, 'John Smith')
        with common_utils.Namespace(self.NAMESPACE):
            student, _ = models.Student.get_first_by_email(self.STUDENT_EMAIL)
            self.student_user_id = student.user_id

        actions.login(self.ADMIN_EMAIL)

    def tearDown(self):
        sites.reset_courses()
        super(SubmissionDataSourceTest, self).tearDown()

    def _post_submission(self, unit_id, contents):
        actions.login(self.STUDENT_EMAIL)
        response = self.post(
            upload._POST_ACTION_SUFFIX.lstrip('/'),
            {'unit_id': unit_id,
             'contents': contents,
             'form_xsrf_token': crypto.XsrfTokenManager.create_xsrf_token(
                 upload._XSRF_TOKEN_NAME),
             },
            # webtest mangles UTF-8 parameter conversion w/o this present.
            content_type='application/x-www-form-urlencoded;charset=utf8')
        self.assertEquals(response.status_int, 200)
        actions.login(self.ADMIN_EMAIL)

    def _get_data(self, source_context=None):
        params = {
            'chunk_size':
                review_module.SubmissionDataSource.get_default_chunk_size()
        }
        if source_context:
            params['source_context'] = source_context
        response = self.get('rest/data/submissions/items?%s' %
                            urllib.urlencode(params))
        content = transforms.loads(response.body)
        return content['data']

    def test_no_content(self):
        data = self._get_data()
        self.assertEquals([], data)

    def test_non_pii_request(self):
        self._post_submission('123', 'the content')
        data = self._get_data()
        self.assertEquals(1, len(data))
        datum = data[0]
        self.assertEquals(datum['user_id'], 'None')
        self.assertEquals(datum['contents'], 'the content')
        self.assertEquals(datum['unit_id'], '123')
        updated_on = datetime.datetime.strptime(
            datum['updated_on'], schema_transforms.ISO_8601_DATETIME_FORMAT)
        diff = (datetime.datetime.utcnow() - updated_on).total_seconds()
        self.assertLess(diff, 5)

    def test_pii_request(self):
        self._post_submission(456, u'音読み')

        # Extra hoop-jumping to get a request context parameter blessed which
        # allows non-PII-suppressed results.
        params = {'data_source_token': 'fake token'}
        source_context = data_sources.DbTableContext.build_blank_default(
            params, review_module.SubmissionDataSource.get_default_chunk_size())
        source_context.send_uncensored_pii_data = True
        handler_class = data_sources._generate_rest_handler(
            review_module.SubmissionDataSource)
        handler_instance = handler_class()
        context_param = handler_instance._encode_context(source_context)
        data = self._get_data(context_param)

        self.assertEquals(1, len(data))
        datum = data[0]
        self.assertEquals(datum['user_id'], self.student_user_id)
        self.assertEquals(datum['contents'], u'音読み')
        self.assertEquals(datum['unit_id'], '456')
        updated_on = datetime.datetime.strptime(
            datum['updated_on'], schema_transforms.ISO_8601_DATETIME_FORMAT)
        diff = (datetime.datetime.utcnow() - updated_on).total_seconds()
        self.assertLess(diff, 5)
