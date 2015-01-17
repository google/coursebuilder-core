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

"""Functional tests for modules/review/peer.py."""

__author__ = [
    'johncox@google.com (John Cox)',
]

from models import models
from models import student_work
from modules.review import domain
from modules.review import peer
from tests.functional import actions
from google.appengine.ext import db


class ReviewStepTest(actions.ExportTestBase):

    def setUp(self):
        super(ReviewStepTest, self).setUp()
        self.reviewee_email = 'reviewee@example.com'
        self.reviewee_key = models.Student(key_name=self.reviewee_email).put()
        self.reviewer_email = 'reviewer@example.com'
        self.reviewer_key = models.Student(key_name=self.reviewer_email).put()
        self.unit_id = 'unit_id'
        self.submission_key = student_work.Submission(
            reviewee_key=self.reviewee_key, unit_id=self.unit_id).put()
        self.review_key = student_work.Review(
            reviewee_key=self.reviewee_key, reviewer_key=self.reviewer_key,
            unit_id=self.unit_id).put()
        self.review_summary_key = peer.ReviewSummary(
            reviewee_key=self.reviewee_key, submission_key=self.submission_key,
            unit_id=self.unit_id).put()
        self.step = peer.ReviewStep(
            assigner_kind=domain.ASSIGNER_KIND_AUTO, review_key=self.review_key,
            review_summary_key=self.review_summary_key,
            reviewee_key=self.reviewee_key, reviewer_key=self.reviewer_key,
            state=domain.REVIEW_STATE_ASSIGNED,
            submission_key=self.submission_key, unit_id=self.unit_id)
        self.step_key = self.step.put()

    def test_constructor_sets_key_name(self):
        """Tests construction of key_name, put of entity with key_name set."""
        self.assertEqual(
            peer.ReviewStep.key_name(self.submission_key, self.reviewer_key),
            self.step_key.name())

    def test_for_export_transforms_correctly(self):
        exported = self.step.for_export(self.transform)

        self.assert_blacklisted_properties_removed(self.step, exported)
        self.assertEqual(
            student_work.Review.safe_key(self.review_key, self.transform),
            exported.review_key)
        self.assertEqual(
            peer.ReviewSummary.safe_key(
                self.review_summary_key, self.transform),
            exported.review_summary_key)
        self.assertEqual(
            models.Student.safe_key(self.reviewee_key, self.transform),
            exported.reviewee_key)
        self.assertEqual(
            models.Student.safe_key(self.reviewer_key, self.transform),
            exported.reviewer_key)
        self.assertEqual(
            student_work.Submission.safe_key(
                self.submission_key, self.transform),
            exported.submission_key)

    def test_safe_key_transforms_or_retains_sensitive_data(self):
        original_key = peer.ReviewStep.safe_key(self.step_key, lambda x: x)
        transformed_key = peer.ReviewStep.safe_key(
            self.step_key, self.transform)

        get_reviewee_key_name = (
            lambda x: x.split('%s:' % self.unit_id)[-1].split(')')[0])
        get_reviewer_key_name = lambda x: x.rsplit(':')[-1].strip(')')

        self.assertEqual(
            self.reviewee_email, get_reviewee_key_name(original_key.name()))
        self.assertEqual(
            self.reviewer_email, get_reviewer_key_name(original_key.name()))

        self.assertEqual(
            'transformed_' + self.reviewee_email,
            get_reviewee_key_name(transformed_key.name()))
        self.assertEqual(
            'transformed_' + self.reviewer_email,
            get_reviewer_key_name(transformed_key.name()))


class ReviewSummaryTest(actions.ExportTestBase):

    def setUp(self):
        super(ReviewSummaryTest, self).setUp()
        self.unit_id = 'unit_id'
        self.reviewee_email = 'reviewee@example.com'
        self.reviewee_key = models.Student(
            key_name='reviewee@example.com').put()
        self.submission_key = student_work.Submission(
            reviewee_key=self.reviewee_key, unit_id=self.unit_id).put()
        self.summary = peer.ReviewSummary(
            reviewee_key=self.reviewee_key, submission_key=self.submission_key,
            unit_id=self.unit_id)
        self.summary_key = self.summary.put()

    def test_constructor_sets_key_name(self):
        summary_key = peer.ReviewSummary(
            reviewee_key=self.reviewee_key, submission_key=self.submission_key,
            unit_id=self.unit_id).put()
        self.assertEqual(
            peer.ReviewSummary.key_name(self.submission_key),
            summary_key.name())

    def test_decrement_count(self):
        """Tests decrement_count."""
        summary = peer.ReviewSummary(
            assigned_count=1, completed_count=1, expired_count=1,
            reviewee_key=self.reviewee_key, submission_key=self.submission_key,
            unit_id=self.unit_id)

        self.assertEqual(1, summary.assigned_count)
        summary.decrement_count(domain.REVIEW_STATE_ASSIGNED)
        self.assertEqual(0, summary.assigned_count)
        self.assertEqual(1, summary.completed_count)
        summary.decrement_count(domain.REVIEW_STATE_COMPLETED)
        self.assertEqual(0, summary.completed_count)
        self.assertEqual(1, summary.expired_count)
        summary.decrement_count(domain.REVIEW_STATE_EXPIRED)
        self.assertEqual(0, summary.expired_count)
        self.assertRaises(ValueError, summary.decrement_count, 'bad_state')

    def test_increment_count(self):
        """Tests increment_count."""
        summary = peer.ReviewSummary(
            reviewee_key=self.reviewee_key, submission_key=self.submission_key,
            unit_id=self.unit_id)

        self.assertRaises(ValueError, summary.increment_count, 'bad_state')
        self.assertEqual(0, summary.assigned_count)
        summary.increment_count(domain.REVIEW_STATE_ASSIGNED)
        self.assertEqual(1, summary.assigned_count)
        self.assertEqual(0, summary.completed_count)
        summary.increment_count(domain.REVIEW_STATE_COMPLETED)
        self.assertEqual(1, summary.completed_count)
        self.assertEqual(0, summary.expired_count)
        summary.increment_count(domain.REVIEW_STATE_EXPIRED)
        self.assertEqual(1, summary.expired_count)

        check_overflow = peer.ReviewSummary(
            assigned_count=domain.MAX_UNREMOVED_REVIEW_STEPS - 1,
            reviewee_key=self.reviewee_key, submission_key=self.submission_key,
            unit_id=self.unit_id)
        # Increment to the limit succeeds...
        check_overflow.increment_count(domain.REVIEW_STATE_ASSIGNED)

        # ...but not beyond.
        self.assertRaises(
            db.BadValueError,
            check_overflow.increment_count, domain.REVIEW_STATE_ASSIGNED)

    def test_for_export_transforms_correctly(self):
        exported = self.summary.for_export(self.transform)

        self.assert_blacklisted_properties_removed(self.summary, exported)
        self.assertEqual(
            models.Student.safe_key(self.reviewee_key, self.transform),
            exported.reviewee_key)
        self.assertEqual(
            student_work.Submission.safe_key(
                self.submission_key, self.transform),
            exported.submission_key)

    def test_safe_key_transforms_or_retains_sensitive_data(self):
        original_key = peer.ReviewSummary.safe_key(
            self.summary_key, lambda x: x)
        transformed_key = peer.ReviewSummary.safe_key(
            self.summary_key, self.transform)

        get_reviewee_key_name = lambda x: x.rsplit(':', 1)[-1].strip(')')

        self.assertEqual(
            self.reviewee_email, get_reviewee_key_name(original_key.name()))
        self.assertEqual(
            'transformed_' + self.reviewee_email,
            get_reviewee_key_name(transformed_key.name()))
