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

    def setUp(self):  # Name set by parent. pylint: disable-msg=g-bad-name
        super(ManagerTest, self).setUp()
        self.student = models.Student(key_name='test@example.com')
        self.student_key = self.student.put()
        self.submission = review.Submission(contents='contents')
        self.submission_key = self.submission.put()
        self.unit_id = '1'

    def test_delete_reviewer_marks_step_removed_and_decrements_summary(self):
        """Ensures delete_reviewer does correct bookkeeping."""
        summary_key = peer.ReviewSummary(
            assigned_count=1,
            reviewee_key=db.Key.from_path(
                models.Student.kind(), 'reviewee@example.com'),
            submission_key=db.Key.from_path(
                review.Submission.kind(), 'submission'),
            unit_id='1'
        ).put()
        step_key = peer.ReviewStep(
            assigner_kind=peer.ASSIGNER_KIND_AUTO,
            review_key=db.Key.from_path(review.Review.kind(), 'review'),
            review_summary_key=summary_key,
            reviewee_key=db.Key.from_path(
                models.Student.kind(), 'reviewee@example.com'),
            reviewer_key=db.Key.from_path(
                models.Student.kind(), 'reviewer@example.com'),
            submission_key=db.Key.from_path(
                review.Submission.kind(), 'submission'),
            state=peer.REVIEW_STATE_ASSIGNED, unit_id='1',
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
            db.Key.from_path(peer.ReviewStep.kind(), 'missing_key'))

    def test_delete_reviewer_raises_key_error_when_summary_missing(self):
        """Ensures we raise KeyError if step references a missing summary."""
        missing_key = db.Key.from_path(
            peer.ReviewSummary.kind(), 'missing_review_summary_key')
        step_key = peer.ReviewStep(
            assigner_kind=peer.ASSIGNER_KIND_AUTO,
            review_key=db.Key.from_path(review.Review.kind(), 'review'),
            review_summary_key=missing_key,
            reviewee_key=db.Key.from_path(
                models.Student.kind(), 'reviewee@example.com'),
            reviewer_key=db.Key.from_path(
                models.Student.kind(), 'reviewer@example.com'),
            submission_key=db.Key.from_path(
                review.Submission.kind(), 'submission'),
            state=peer.REVIEW_STATE_ASSIGNED, unit_id='1',
        ).put()
        self.assertRaises(
            KeyError, review_module.Manager.delete_reviewer, step_key)

    def test_delete_reviewer_raises_value_error_if_already_removed(self):
        """Ensures we raise ValueError when deleting removed review step."""
        summary_key = peer.ReviewSummary(
            assigned_count=1,
            reviewee_key=db.Key.from_path(
                models.Student.kind(), 'reviewee@example.com'),
            submission_key=db.Key.from_path(
                review.Submission.kind(), 'submission'),
            unit_id='1'
        ).put()
        step_key = peer.ReviewStep(
            assigner_kind=peer.ASSIGNER_KIND_AUTO, removed=True,
            review_key=db.Key.from_path(review.Review.kind(), 'review'),
            review_summary_key=summary_key,
            reviewee_key=db.Key.from_path(
                models.Student.kind(), 'reviewee@example.com'),
            reviewer_key=db.Key.from_path(
                models.Student.kind(), 'reviewer@example.com'),
            submission_key=db.Key.from_path(
                review.Submission.kind(), 'submission'),
            state=peer.REVIEW_STATE_ASSIGNED, unit_id='1',
        ).put()
        self.assertRaises(
            ValueError, review_module.Manager.delete_reviewer, step_key)

    def test_start_review_process_for_succeeds(self):
        key = review_module.Manager.start_review_process_for(
            self.unit_id, self.submission_key, self.student_key)
        summary = db.get(key)
        self.assertEqual(self.student_key, summary.reviewee_key)
        self.assertEqual(self.submission_key, summary.submission_key)
        self.assertEqual(self.unit_id, summary.unit_id)

    def test_start_review_process_for_throws_if_already_started(self):
        collision = peer.ReviewSummary(
            reviewee_key=self.student_key, submission_key=self.submission_key,
            unit_id=self.unit_id)
        collision.put()
        self.assertRaises(
            review_module.ReviewProcessAlreadyStartedError,
            review_module.Manager.start_review_process_for,
            self.unit_id, self.submission_key, self.student_key)


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
