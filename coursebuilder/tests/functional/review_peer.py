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

from models import entities
from models import models
from models import review
from modules.review import peer
from tests.functional import actions
from google.appengine.ext import db


class ReferencedModel(entities.BaseEntity):
    pass


class UnvalidatedReference(entities.BaseEntity):
    referenced_model_key = peer.KeyProperty()


class ValidatedReference(entities.BaseEntity):
    referenced_model_key = peer.KeyProperty(kind=ReferencedModel.kind())


class KeyPropertyTest(actions.TestBase):
    """Tests KeyProperty."""

    def setUp(self):  # From superclass. pylint: disable-msg=g-bad-name
        super(KeyPropertyTest, self).setUp()
        self.referenced_model_key = ReferencedModel().put()

    def test_validation_and_datastore_round_trip_of_keys_succeeds(self):
        """Tests happy path for both validation and (de)serialization."""
        model_with_reference = ValidatedReference(
            referenced_model_key=self.referenced_model_key)
        model_with_reference_key = model_with_reference.put()
        model_with_reference_from_datastore = db.get(model_with_reference_key)
        self.assertEqual(
            self.referenced_model_key,
            model_with_reference_from_datastore.referenced_model_key)
        custom_model_from_datastore = db.get(
            model_with_reference_from_datastore.referenced_model_key)
        self.assertEqual(
            self.referenced_model_key, custom_model_from_datastore.key())
        self.assertTrue(isinstance(
            model_with_reference_from_datastore.referenced_model_key,
            db.Key))

    def test_type_not_validated_if_kind_not_passed(self):
        model_key = db.Model().put()
        unvalidated = UnvalidatedReference(referenced_model_key=model_key)
        self.assertEqual(model_key, unvalidated.referenced_model_key)

    def test_validation_fails(self):
        model_key = db.Model().put()
        self.assertRaises(
            db.BadValueError, ValidatedReference,
            referenced_model_key='not_a_key')
        self.assertRaises(
            db.BadValueError, ValidatedReference,
            referenced_model_key=model_key)


class ReviewStepTest(actions.TestBase):

    def test_constructor_sets_key_name(self):
        """Tests construction of key_name, put of entity with key_name set."""
        unit_id = 'unit_id'
        reviewee_key = models.Student(key_name='reviewee@example.com').put()
        reviewer_key = models.Student(key_name='reviewer@example.com').put()
        submission_key = review.Submission().put()
        step_key = peer.ReviewStep(
            assigner_kind=peer.ASSIGNER_KIND_AUTO,
            reviewee_key=reviewee_key, reviewer_key=reviewer_key,
            state=peer.REVIEW_STATE_ASSIGNED,
            submission_key=submission_key, unit_id=unit_id).put()
        self.assertEqual(
            peer.ReviewStep.key_name(
                unit_id, submission_key, reviewee_key, reviewer_key),
            step_key.name())


class ReviewSummaryTest(actions.TestBase):
    """Tests for ReviewSummary."""

    def test_constructor_sets_key_name(self):
        unit_id = 'unit_id'
        reviewee_key = models.Student(key_name='reviewee@example.com').put()
        submission_key = review.Submission().put()
        summary_key = peer.ReviewSummary(
            reviewee_key=reviewee_key, submission_key=submission_key,
            unit_id=unit_id).put()
        self.assertEqual(
            peer.ReviewSummary.key_name(unit_id, submission_key, reviewee_key),
            summary_key.name())

    def test_decrement_count(self):
        """Tests decrement_count."""
        summary = peer.ReviewSummary(
            assigned_count=1, completed_count=1, expired_count=1,
            reviewee_key=db.Key.from_path(
                models.Student.kind(), 'reviewee@example.com'),
            submission_key=db.Key.from_path(
                review.Submission.kind(), 'submission'), unit_id='1')

        self.assertEqual(1, summary.assigned_count)
        summary.decrement_count(peer.REVIEW_STATE_ASSIGNED)
        self.assertEqual(0, summary.assigned_count)
        self.assertEqual(1, summary.completed_count)
        summary.decrement_count(peer.REVIEW_STATE_COMPLETED)
        self.assertEqual(0, summary.completed_count)
        self.assertEqual(1, summary.expired_count)
        summary.decrement_count(peer.REVIEW_STATE_EXPIRED)
        self.assertEqual(0, summary.expired_count)
        self.assertRaises(ValueError, summary.decrement_count, 'bad_state')

    def test_increment_count(self):
        """Tests increment_count."""
        summary = peer.ReviewSummary(
            reviewee_key=db.Key.from_path(
                models.Student.kind(), 'reviewee@example.com'),
            submission_key=db.Key.from_path(
                review.Submission.kind(), 'submission'), unit_id='1')

        self.assertEqual(0, summary.assigned_count)
        summary.increment_count(peer.REVIEW_STATE_ASSIGNED)
        self.assertEqual(1, summary.assigned_count)
        self.assertEqual(0, summary.completed_count)
        summary.increment_count(peer.REVIEW_STATE_COMPLETED)
        self.assertEqual(1, summary.completed_count)
        self.assertEqual(0, summary.expired_count)
        summary.increment_count(peer.REVIEW_STATE_EXPIRED)
        self.assertEqual(1, summary.expired_count)
        self.assertRaises(ValueError, summary.increment_count, 'bad_state')
