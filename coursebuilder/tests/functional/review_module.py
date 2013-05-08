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
