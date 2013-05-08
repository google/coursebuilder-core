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

import types

from models import models
from models import review
from modules.review import peer
from modules.review import review as review_module
from tests.functional import actions
from google.appengine.ext import db


class TestBase(actions.TestBase):

    def assert_make_key_successful(
        self, domain_object_class, db_model_class, id_or_name, namespace):
        key = domain_object_class.make_key(id_or_name, namespace)
        self.assertEqual(db_model_class.__name__, key.kind())
        self.assertEqual(id_or_name, key.id_or_name())
        self.assertEqual(namespace, key.namespace())


class ManagerTest(TestBase):
    """Tests for review.Manager."""

    # Don't require documentation for self-describing test methods.
    # pylint: disable-msg=g-missing-docstring

    def setUp(self):  # Name set by parent. pylint: disable-msg=g-bad-name
        super(ManagerTest, self).setUp()
        self.reviewee = models.Student(key_name='reviewee@example.com')
        self.reviewee_key = self.reviewee.put()
        self.reviewer = models.Student(key_name='reviewer@example.com')
        self.reviewer_key = self.reviewer.put()
        self.submission = review.Submission(contents='contents')
        self.submission_key = self.submission.put()
        self.unit_id = '1'

    def test_add_reviewer_adds_new_step_and_summary(self):
        step_key = review_module.Manager.add_reviewer(
            self.unit_id, self.submission_key, self.reviewee_key,
            self.reviewer_key)
        step = db.get(step_key)
        summary = db.get(step.review_summary_key)

        self.assertEqual(peer.ASSIGNER_KIND_HUMAN, step.assigner_kind)
        self.assertEqual(self.reviewee_key, step.reviewee_key)
        self.assertEqual(self.reviewer_key, step.reviewer_key)
        self.assertEqual(peer.REVIEW_STATE_ASSIGNED, step.state)
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
            assigner_kind=peer.ASSIGNER_KIND_AUTO,
            review_key=db.Key.from_path(review.Review.kind(), 'review'),
            review_summary_key=missing_key, reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            state=peer.REVIEW_STATE_ASSIGNED, unit_id=self.unit_id
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
            assigner_kind=peer.ASSIGNER_KIND_AUTO,
            review_key=db.Key.from_path(review.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            state=peer.REVIEW_STATE_ASSIGNED, unit_id=self.unit_id
        ).put()

        self.assertRaises(
            review_module.TransitionError, review_module.Manager.add_reviewer,
            self.unit_id, self.submission_key, self.reviewee_key,
            self.reviewer_key)

    def test_add_reviewer_existing_raises_transition_error_when_completed(self):
        summary_key = peer.ReviewSummary(
            completed_count=1, reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            unit_id=self.unit_id
        ).put()
        peer.ReviewStep(
            assigner_kind=peer.ASSIGNER_KIND_AUTO,
            review_key=db.Key.from_path(review.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            state=peer.REVIEW_STATE_COMPLETED, unit_id=self.unit_id
        ).put()

        self.assertRaises(
            review_module.TransitionError, review_module.Manager.add_reviewer,
            self.unit_id, self.submission_key, self.reviewee_key,
            self.reviewer_key)

    def test_add_reviewer_unremoved_existing_changes_expired_to_assigned(self):
        summary_key = peer.ReviewSummary(
            expired_count=1, reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            unit_id=self.unit_id
        ).put()
        step_key = peer.ReviewStep(
            assigner_kind=peer.ASSIGNER_KIND_AUTO,
            review_key=db.Key.from_path(review.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            state=peer.REVIEW_STATE_EXPIRED, unit_id=self.unit_id
        ).put()
        review_module.Manager.add_reviewer(
            self.unit_id, self.submission_key, self.reviewee_key,
            self.reviewer_key)
        step, summary = db.get([step_key, summary_key])

        self.assertEqual(peer.ASSIGNER_KIND_HUMAN, step.assigner_kind)
        self.assertEqual(peer.REVIEW_STATE_ASSIGNED, step.state)
        self.assertFalse(step.removed)

        self.assertEqual(1, summary.assigned_count)
        self.assertEqual(0, summary.expired_count)

    def test_add_reviewer_removed_unremoves_assigned_step(self):
        summary_key = peer.ReviewSummary(
            reviewee_key=self.reviewee_key, reviewer_key=self.reviewer_key,
            submission_key=self.submission_key, unit_id=self.unit_id
        ).put()
        step_key = peer.ReviewStep(
            assigner_kind=peer.ASSIGNER_KIND_AUTO, removed=True,
            review_key=db.Key.from_path(review.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            state=peer.REVIEW_STATE_ASSIGNED, unit_id=self.unit_id
        ).put()
        review_module.Manager.add_reviewer(
            self.unit_id, self.submission_key, self.reviewee_key,
            self.reviewer_key)
        step, summary = db.get([step_key, summary_key])

        self.assertEqual(peer.ASSIGNER_KIND_HUMAN, step.assigner_kind)
        self.assertEqual(peer.REVIEW_STATE_ASSIGNED, step.state)
        self.assertFalse(step.removed)

        self.assertEqual(1, summary.assigned_count)

    def test_add_reviewer_removed_unremoves_completed_step(self):
        summary_key = peer.ReviewSummary(
            reviewee_key=self.reviewee_key, reviewer_key=self.reviewer_key,
            submission_key=self.submission_key, unit_id=self.unit_id
        ).put()
        step_key = peer.ReviewStep(
            assigner_kind=peer.ASSIGNER_KIND_AUTO, removed=True,
            review_key=db.Key.from_path(review.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            state=peer.REVIEW_STATE_COMPLETED, unit_id=self.unit_id
        ).put()
        review_module.Manager.add_reviewer(
            self.unit_id, self.submission_key, self.reviewee_key,
            self.reviewer_key)
        step, summary = db.get([step_key, summary_key])

        self.assertEqual(peer.ASSIGNER_KIND_HUMAN, step.assigner_kind)
        self.assertEqual(peer.REVIEW_STATE_COMPLETED, step.state)
        self.assertFalse(step.removed)

        self.assertEqual(1, summary.completed_count)

    def test_add_reviewer_removed_unremoves_and_assigns_expired_step(self):
        summary_key = peer.ReviewSummary(
            expired_count=1, reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            unit_id=self.unit_id
        ).put()
        step_key = peer.ReviewStep(
            assigner_kind=peer.ASSIGNER_KIND_AUTO, removed=True,
            review_key=db.Key.from_path(review.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            state=peer.REVIEW_STATE_EXPIRED, unit_id=self.unit_id
        ).put()
        review_module.Manager.add_reviewer(
            self.unit_id, self.submission_key, self.reviewee_key,
            self.reviewer_key)
        step, summary = db.get([step_key, summary_key])

        self.assertEqual(peer.ASSIGNER_KIND_HUMAN, step.assigner_kind)
        self.assertEqual(peer.REVIEW_STATE_ASSIGNED, step.state)
        self.assertFalse(step.removed)

        self.assertEqual(1, summary.assigned_count)
        self.assertEqual(0, summary.expired_count)

    def test_delete_reviewer_marks_step_removed_and_decrements_summary(self):
        summary_key = peer.ReviewSummary(
            assigned_count=1, reviewee_key=self.reviewee_key,
            submission_key=self.submission_key, unit_id=self.unit_id
        ).put()
        step_key = peer.ReviewStep(
            assigner_kind=peer.ASSIGNER_KIND_AUTO,
            review_key=db.Key.from_path(review.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            state=peer.REVIEW_STATE_ASSIGNED, unit_id=self.unit_id
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
            assigner_kind=peer.ASSIGNER_KIND_AUTO,
            review_key=db.Key.from_path(review.Review.kind(), 'review'),
            review_summary_key=missing_key, reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            state=peer.REVIEW_STATE_ASSIGNED, unit_id=self.unit_id
        ).put()

        self.assertRaises(
            KeyError, review_module.Manager.delete_reviewer, step_key)

    def test_delete_reviewer_raises_removed_error_if_already_removed(self):
        summary_key = peer.ReviewSummary(
            assigned_count=1, reviewee_key=self.reviewee_key,
            submission_key=self.submission_key, unit_id=self.unit_id
        ).put()
        step_key = peer.ReviewStep(
            assigner_kind=peer.ASSIGNER_KIND_AUTO, removed=True,
            review_key=db.Key.from_path(review.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            state=peer.REVIEW_STATE_ASSIGNED, unit_id=self.unit_id
        ).put()

        self.assertRaises(
            review_module.RemovedError, review_module.Manager.delete_reviewer,
            step_key)

    def test_expire_review_raises_key_error_when_step_missing(self):
        self.assertRaises(
            KeyError, review_module.Manager.expire_review,
            db.Key.from_path(peer.ReviewStep.kind(), 'missing_step_key'))

    def test_expire_review_raises_key_error_when_summary_missing(self):
        missing_key = db.Key.from_path(
            peer.ReviewSummary.kind(), 'missing_review_summary_key')
        step_key = peer.ReviewStep(
            assigner_kind=peer.ASSIGNER_KIND_AUTO,
            review_key=db.Key.from_path(review.Review.kind(), 'review'),
            review_summary_key=missing_key, reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            state=peer.REVIEW_STATE_ASSIGNED, unit_id=self.unit_id
        ).put()

        self.assertRaises(
            KeyError, review_module.Manager.expire_review, step_key)

    def test_expire_review_raises_transition_error_when_state_completed(self):
        summary_key = peer.ReviewSummary(
            completed=1, reviewee_key=self.reviewee_key,
            submission_key=self.submission_key, unit_id=self.unit_id
        ).put()
        step_key = peer.ReviewStep(
            assigner_kind=peer.ASSIGNER_KIND_AUTO,
            review_key=db.Key.from_path(review.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            state=peer.REVIEW_STATE_COMPLETED, unit_id=self.unit_id
        ).put()

        self.assertRaises(
            review_module.TransitionError, review_module.Manager.expire_review,
            step_key)

    def test_expire_review_raises_transition_error_when_state_expired(self):
        summary_key = peer.ReviewSummary(
            expired_count=1, reviewee_key=self.reviewee_key,
            submission_key=self.submission_key, unit_id=self.unit_id
        ).put()
        step_key = peer.ReviewStep(
            assigner_kind=peer.ASSIGNER_KIND_AUTO,
            review_key=db.Key.from_path(review.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            state=peer.REVIEW_STATE_EXPIRED, unit_id=self.unit_id
        ).put()

        self.assertRaises(
            review_module.TransitionError, review_module.Manager.expire_review,
            step_key)

    def test_expire_review_raises_removed_error_when_step_removed(self):
        summary_key = peer.ReviewSummary(
            reviewee_key=self.reviewee_key, submission_key=self.submission_key,
            unit_id=self.unit_id
        ).put()
        step_key = peer.ReviewStep(
            assigner_kind=peer.ASSIGNER_KIND_AUTO, removed=True,
            review_key=db.Key.from_path(review.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            state=peer.REVIEW_STATE_ASSIGNED, unit_id=self.unit_id
        ).put()

        self.assertRaises(
            review_module.RemovedError, review_module.Manager.expire_review,
            step_key)

    def test_expire_review_transitions_state_and_updates_summary(self):
        summary_key = peer.ReviewSummary(
            assigned_count=1, reviewee_key=self.reviewee_key,
            submission_key=self.submission_key, unit_id=self.unit_id
        ).put()
        step_key = peer.ReviewStep(
            assigner_kind=peer.ASSIGNER_KIND_AUTO,
            review_key=db.Key.from_path(review.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            state=peer.REVIEW_STATE_ASSIGNED, unit_id=self.unit_id
        ).put()

        step, summary = db.get([step_key, summary_key])

        self.assertEqual(1, summary.assigned_count)
        self.assertEqual(0, summary.expired_count)
        self.assertEqual(peer.REVIEW_STATE_ASSIGNED, step.state)

        expired_key = review_module.Manager.expire_review(step_key)
        step, summary = db.get([expired_key, summary_key])

        self.assertEqual(0, summary.assigned_count)
        self.assertEqual(1, summary.expired_count)
        self.assertEqual(peer.REVIEW_STATE_EXPIRED, step.state)

    def test_expire_old_reviews_for_unit_expires_found_reviews(self):
        summary_key = peer.ReviewSummary(
            assigned_count=2, completed_count=1, reviewee_key=self.reviewee_key,
            submission_key=self.submission_key, unit_id=self.unit_id
        ).put()
        first_step_key = peer.ReviewStep(
            assigner_kind=peer.ASSIGNER_KIND_AUTO,
            review_key=db.Key.from_path(review.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            state=peer.REVIEW_STATE_ASSIGNED, unit_id=self.unit_id
        ).put()
        second_reviewee = models.Student(key_name='reviewee2@example.com')
        second_reviewee_key = second_reviewee.put()
        second_step_key = peer.ReviewStep(
            assigner_kind=peer.ASSIGNER_KIND_AUTO,
            review_key=db.Key.from_path(review.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=second_reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            state=peer.REVIEW_STATE_ASSIGNED, unit_id=self.unit_id
        ).put()
        review_module.Manager.expire_old_reviews_for_unit(0, self.unit_id)
        first_step, second_step, summary = db.get(
            [first_step_key, second_step_key, summary_key])

        self.assertEqual(
            [peer.REVIEW_STATE_EXPIRED, peer.REVIEW_STATE_EXPIRED],
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
            assigner_kind=peer.ASSIGNER_KIND_AUTO,
            review_key=db.Key.from_path(review.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            state=peer.REVIEW_STATE_ASSIGNED, unit_id=self.unit_id
        ).put()
        second_reviewee = models.Student(key_name='reviewee2@example.com')
        second_reviewee_key = second_reviewee.put()
        error_step_key = peer.ReviewStep(
            assigner_kind=peer.ASSIGNER_KIND_AUTO,
            review_key=db.Key.from_path(review.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=second_reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            state=peer.REVIEW_STATE_COMPLETED, unit_id=self.unit_id
        ).put()
        review_module.Manager.expire_old_reviews_for_unit(0, self.unit_id)
        processed_step, error_step, summary = db.get(
            [processable_step_key, error_step_key, summary_key])

        self.assertEqual(peer.REVIEW_STATE_COMPLETED, error_step.state)
        self.assertEqual(peer.REVIEW_STATE_EXPIRED, processed_step.state)
        self.assertEqual(0, summary.assigned_count)
        self.assertEqual(1, summary.completed_count)
        self.assertEqual(1, summary.expired_count)

    def test_get_assignment_candidates_query_filters_and_orders_correctly(self):
        unused_wrong_unit_key = peer.ReviewSummary(
            reviewee_key=self.reviewee_key, submission_key=self.submission_key,
            unit_id=str(int(self.unit_id) + 1)
        ).put()
        second_reviewee = models.Student(key_name='reviewee2@example.com')
        second_reviewee_key = second_reviewee.put()
        older_assigned_and_completed_key = peer.ReviewSummary(
            assigned_count=1, completed_count=1,
            reviewee_key=second_reviewee_key,
            submission_key=self.submission_key, unit_id=self.unit_id
        ).put()
        third_reviewee = models.Student(key_name='reviewee3@example.com')
        third_reviewee_key = third_reviewee.put()
        younger_assigned_and_completed_key = peer.ReviewSummary(
            assigned_count=1, completed_count=1,
            reviewee_key=third_reviewee_key, submission_key=self.submission_key,
            unit_id=self.unit_id
        ).put()
        fourth_reviewee = models.Student(key_name='reviewee4@example.com')
        fourth_reviewee_key = fourth_reviewee.put()
        completed_but_not_assigned_key = peer.ReviewSummary(
            assigned_count=0, completed_count=1,
            reviewee_key=fourth_reviewee_key,
            submission_key=self.submission_key, unit_id=self.unit_id
        ).put()
        fifth_reviewee = models.Student(key_name='reviewee5@example.com')
        fifth_reviewee_key = fifth_reviewee.put()
        assigned_but_not_completed_key = peer.ReviewSummary(
            assigned_count=1, completed_count=0,
            reviewee_key=fifth_reviewee_key, submission_key=self.submission_key,
            unit_id=self.unit_id
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
            assigner_kind=peer.ASSIGNER_KIND_AUTO,
            review_key=db.Key.from_path(review.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            state=peer.REVIEW_STATE_COMPLETED, unit_id=self.unit_id
        ).put()
        second_reviewee = models.Student(key_name='reviewee2@example.com')
        second_reviewee_key = second_reviewee.put()
        unused_removed_step_key = peer.ReviewStep(
            assigner_kind=peer.ASSIGNER_KIND_AUTO, removed=True,
            review_key=db.Key.from_path(review.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=second_reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            state=peer.REVIEW_STATE_ASSIGNED, unit_id=self.unit_id
        ).put()
        third_reviewee = models.Student(key_name='reviewee3@example.com')
        third_reviewee_key = third_reviewee.put()
        unused_other_unit_step_key = peer.ReviewStep(
            assigner_kind=peer.ASSIGNER_KIND_AUTO,
            review_key=db.Key.from_path(review.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=third_reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            state=peer.REVIEW_STATE_ASSIGNED, unit_id=str(int(self.unit_id) + 1)
        ).put()
        fourth_reviewee = models.Student(key_name='reviewee4@example.com')
        fourth_reviewee_key = fourth_reviewee.put()
        first_assigned_step_key = peer.ReviewStep(
            assigner_kind=peer.ASSIGNER_KIND_AUTO,
            review_key=db.Key.from_path(review.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=fourth_reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            state=peer.REVIEW_STATE_ASSIGNED, unit_id=self.unit_id
        ).put()
        fifth_reviewee = models.Student(key_name='reviewee5@example.com')
        fifth_reviewee_key = fifth_reviewee.put()
        second_assigned_step_key = peer.ReviewStep(
            assigner_kind=peer.ASSIGNER_KIND_AUTO,
            review_key=db.Key.from_path(review.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=fifth_reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            state=peer.REVIEW_STATE_ASSIGNED, unit_id=self.unit_id
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

        self.assertEqual(peer.ASSIGNER_KIND_AUTO, step.assigner_kind)
        self.assertEqual(summary.key(), step.review_summary_key)
        self.assertEqual(self.reviewee_key, step.reviewee_key)
        self.assertEqual(self.reviewer_key, step.reviewer_key)
        self.assertEqual(peer.REVIEW_STATE_ASSIGNED, step.state)
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
            assigner_kind=peer.ASSIGNER_KIND_AUTO,
            review_key=db.Key.from_path(review.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            state=peer.REVIEW_STATE_ASSIGNED, unit_id=self.unit_id
        ).put()

        self.assertRaises(
            review_module.NotAssignableError,
            review_module.Manager.get_new_review, self.unit_id,
            self.reviewer_key)

    def test_get_new_review_raises_not_assignable_when_already_completed(self):
        summary_key = peer.ReviewSummary(
            completed=1, reviewee_key=self.reviewee_key,
            submission_key=self.submission_key, unit_id=self.unit_id
        ).put()
        already_completed_unremoved_step_key = peer.ReviewStep(
            assigner_kind=peer.ASSIGNER_KIND_AUTO,
            review_key=db.Key.from_path(review.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            state=peer.REVIEW_STATE_COMPLETED, unit_id=self.unit_id
        ).put()

        self.assertRaises(
            review_module.NotAssignableError,
            review_module.Manager.get_new_review, self.unit_id,
            self.reviewer_key)

        db.delete(already_completed_unremoved_step_key)
        unused_already_completed_removed_step_key = peer.ReviewStep(
            assigner_kind=peer.ASSIGNER_KIND_AUTO, removed=True,
            review_key=db.Key.from_path(review.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            state=peer.REVIEW_STATE_COMPLETED, unit_id=self.unit_id
        ).put()

        self.assertRaises(
            review_module.NotAssignableError,
            review_module.Manager.get_new_review, self.unit_id,
            self.reviewer_key)

    def test_get_new_review_raises_not_assignable_when_no_candidates(self):
        self.assertRaises(
            review_module.NotAssignableError,
            review_module.Manager.get_new_review, self.unit_id,
            self.reviewer_key)

    def test_get_new_review_raises_not_assignable_when_retry_limit_hit(self):
        higher_priority_summary = peer.ReviewSummary(
            reviewee_key=self.reviewee_key, submission_key=self.submission_key,
            unit_id=self.unit_id)
        higher_priority_summary_key = higher_priority_summary.put()
        second_reviewee = models.Student(key_name='reviewee2@example.com')
        second_reviewee_key = second_reviewee.put()
        lower_priority_summary_key = peer.ReviewSummary(
            completed_count=1, reviewee_key=second_reviewee_key,
            submission_key=self.submission_key, unit_id=self.unit_id
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
            review_module.NotAssignableError,
            review_module.Manager.get_new_review, self.unit_id,
            self.reviewer_key, max_retries=0)

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
            review_module.NotAssignableError,
            review_module.Manager.get_new_review, self.unit_id,
            self.reviewer_key)

    def test_get_new_review_reassigns_removed_assigned_step(self):
        summary_key = peer.ReviewSummary(
            reviewee_key=self.reviewee_key, submission_key=self.submission_key,
            unit_id=self.unit_id
        ).put()
        unused_already_assigned_removed_step_key = peer.ReviewStep(
            assigner_kind=peer.ASSIGNER_KIND_HUMAN, removed=True,
            review_key=db.Key.from_path(review.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            state=peer.REVIEW_STATE_ASSIGNED, unit_id=self.unit_id
        ).put()

        step_key = review_module.Manager.get_new_review(
            self.unit_id, self.reviewer_key)
        step, summary = db.get([step_key, summary_key])

        self.assertEqual(peer.ASSIGNER_KIND_AUTO, step.assigner_kind)
        self.assertFalse(step.removed)
        self.assertEqual(peer.REVIEW_STATE_ASSIGNED, step.state)

        self.assertEqual(1, summary.assigned_count)

    def test_get_new_review_reassigns_removed_expired_step(self):
        summary_key = peer.ReviewSummary(
            reviewee_key=self.reviewee_key, submission_key=self.submission_key,
            unit_id=self.unit_id
        ).put()
        unused_already_expired_removed_step_key = peer.ReviewStep(
            assigner_kind=peer.ASSIGNER_KIND_HUMAN, removed=True,
            review_key=db.Key.from_path(review.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            state=peer.REVIEW_STATE_EXPIRED, unit_id=self.unit_id
        ).put()

        step_key = review_module.Manager.get_new_review(
            self.unit_id, self.reviewer_key)
        step, summary = db.get([step_key, summary_key])

        self.assertEqual(peer.ASSIGNER_KIND_AUTO, step.assigner_kind)
        self.assertFalse(step.removed)
        self.assertEqual(peer.REVIEW_STATE_ASSIGNED, step.state)

        self.assertEqual(1, summary.assigned_count)
        self.assertEqual(0, summary.expired_count)

    def test_get_new_review_retries_successfully(self):
        higher_priority_summary = peer.ReviewSummary(
            reviewee_key=self.reviewee_key, submission_key=self.submission_key,
            unit_id=self.unit_id)
        higher_priority_summary_key = higher_priority_summary.put()
        second_reviewee = models.Student(key_name='reviewee2@example.com')
        second_reviewee_key = second_reviewee.put()
        lower_priority_summary_key = peer.ReviewSummary(
            completed_count=1, reviewee_key=second_reviewee_key,
            submission_key=self.submission_key, unit_id=self.unit_id
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

    def test_get_review_keys_by_returns_list_of_keys(self):
        summary_key = peer.ReviewSummary(
            reviewee_key=self.reviewee_key, submission_key=self.submission_key,
            unit_id=self.unit_id
        ).put()
        matching_step_key = peer.ReviewStep(
            assigner_kind=peer.ASSIGNER_KIND_AUTO, removed=True,
            review_key=db.Key.from_path(review.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            state=peer.REVIEW_STATE_EXPIRED, unit_id=self.unit_id
        ).put()
        non_matching_reviewer = models.Student(key_name='reviewer2@example.com')
        non_matching_reviewer_key = non_matching_reviewer.put()
        unused_non_matching_step_key = peer.ReviewStep(
            assigner_kind=peer.ASSIGNER_KIND_AUTO, removed=True,
            review_key=db.Key.from_path(review.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=self.reviewee_key,
            reviewer_key=non_matching_reviewer_key,
            submission_key=self.submission_key, state=peer.REVIEW_STATE_EXPIRED,
            unit_id=self.unit_id
        ).put()

        self.assertEqual(
            [matching_step_key],
            review_module.Manager.get_review_keys_by(
                self.unit_id, self.reviewer_key))

    def test_get_review_keys_by_returns_empty_list_when_no_matches(self):
        summary_key = peer.ReviewSummary(
            reviewee_key=self.reviewee_key, submission_key=self.submission_key,
            unit_id=self.unit_id
        ).put()
        non_matching_reviewer = models.Student(key_name='reviewer2@example.com')
        non_matching_reviewer_key = non_matching_reviewer.put()
        unused_non_matching_step_different_reviewer_key = peer.ReviewStep(
            assigner_kind=peer.ASSIGNER_KIND_AUTO, removed=True,
            review_key=db.Key.from_path(review.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=self.reviewee_key,
            reviewer_key=non_matching_reviewer_key,
            submission_key=self.submission_key, state=peer.REVIEW_STATE_EXPIRED,
            unit_id=self.unit_id,
        ).put()
        unused_non_matching_step_different_unit_id_key = peer.ReviewStep(
            assigner_kind=peer.ASSIGNER_KIND_AUTO, removed=True,
            review_key=db.Key.from_path(review.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            state=peer.REVIEW_STATE_EXPIRED, unit_id=str(int(self.unit_id) + 1),
        ).put()

        self.assertEqual(
            [], review_module.Manager.get_review_keys_by(
                self.unit_id, self.reviewer_key))

    def test_get_submission_and_review_keys_no_steps(self):
        peer.ReviewSummary(
            reviewee_key=self.reviewee_key, submission_key=self.submission_key,
            unit_id=self.unit_id
        ).put()

        self.assertEqual(
            (self.submission_key, []),
            review_module.Manager.get_submission_and_review_keys(
                self.unit_id, self.reviewee_key))

    def test_get_submission_and_review_keys_with_steps(self):
        summary_key = peer.ReviewSummary(
            reviewee_key=self.reviewee_key, submission_key=self.submission_key,
            unit_id=self.unit_id
        ).put()
        matching_step_key = peer.ReviewStep(
            assigner_kind=peer.ASSIGNER_KIND_AUTO, removed=True,
            review_key=db.Key.from_path(review.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            state=peer.REVIEW_STATE_EXPIRED, unit_id=self.unit_id
        ).put()
        non_matching_reviewee = models.Student(key_name='reviewee2@example.com')
        non_matching_reviewee_key = non_matching_reviewee.put()
        unused_non_matching_step_different_reviewee_key = peer.ReviewStep(
            assigner_kind=peer.ASSIGNER_KIND_AUTO, removed=True,
            review_key=db.Key.from_path(review.Review.kind(), 'review'),
            review_summary_key=summary_key,
            reviewee_key=non_matching_reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            state=peer.REVIEW_STATE_EXPIRED, unit_id=self.unit_id
        ).put()
        non_matching_submission_key = review.Submission(
            contents='contents2').put()
        unused_non_matching_step_different_submission_key = peer.ReviewStep(
            assigner_kind=peer.ASSIGNER_KIND_AUTO, removed=True,
            review_key=db.Key.from_path(review.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key,
            submission_key=non_matching_submission_key,
            state=peer.REVIEW_STATE_EXPIRED, unit_id=self.unit_id
        ).put()
        unused_non_matching_step_different_unit_id_key = peer.ReviewStep(
            assigner_kind=peer.ASSIGNER_KIND_AUTO, removed=True,
            review_key=db.Key.from_path(review.Review.kind(), 'review'),
            review_summary_key=summary_key, reviewee_key=self.reviewee_key,
            reviewer_key=self.reviewer_key, submission_key=self.submission_key,
            state=peer.REVIEW_STATE_EXPIRED, unit_id=str(int(self.unit_id) + 1),
        ).put

        self.assertEqual(
            (self.submission_key, [matching_step_key]),
            review_module.Manager.get_submission_and_review_keys(
                self.unit_id, self.reviewee_key))

    def test_get_submission_and_review_keys_returns_none_on_miss(self):
        self.assertIsNone(
            review_module.Manager.get_submission_and_review_keys(
                self.unit_id, self.reviewee_key))

    def test_get_submission_key(self):
        peer.ReviewSummary(
            reviewee_key=self.reviewee_key, submission_key=self.submission_key,
            unit_id=self.unit_id
        ).put()

        self.assertEqual(
            None,
            review_module.Manager.get_submission_key(
                str(int(self.unit_id) + 1), self.reviewee_key))
        self.assertEqual(
            self.submission_key,
            review_module.Manager.get_submission_key(
                self.unit_id, self.reviewee_key))

    def test_get_submission_key_raises_constraint_error(self):
        unused_first_summary_key = peer.ReviewSummary(
            reviewee_key=self.reviewee_key, submission_key=self.submission_key,
            unit_id=self.unit_id
        ).put()
        second_submission_key = review.Submission(contents='contents2').put()
        unused_second_summary_key = peer.ReviewSummary(
            reviewee_key=self.reviewee_key,
            submission_key=second_submission_key, unit_id=self.unit_id
        ).put()

        self.assertRaises(
            review_module.ConstraintError,
            review_module.Manager.get_submission_key, self.unit_id,
            self.reviewee_key)

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
            review_module.ReviewProcessAlreadyStartedError,
            review_module.Manager.start_review_process_for,
            self.unit_id, self.submission_key, self.reviewee_key)


class ReviewTest(TestBase):

    def test_make_key(self):
        self.assert_make_key_successful(
            review_module.Review, review.Review, 'id_or_name',
            'namespace')


class ReviewStepTest(TestBase):

    def test_make_key(self):
        self.assert_make_key_successful(
            review_module.ReviewStep, peer.ReviewStep, 'id_or_name',
            'namespace')


class ReviewSummaryTest(TestBase):

    def test_make_key(self):
        self.assert_make_key_successful(
            review_module.ReviewSummary, peer.ReviewSummary, 'id_or_name',
            'namespace')


class SubmissionTest(TestBase):

    def test_make_key(self):
        self.assert_make_key_successful(
            review_module.Submission, review.Submission, 'id_or_name',
            'namespace')
