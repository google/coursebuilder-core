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

"""Functional tests for models/review.py."""

__author__ = [
    'johncox@google.com (John Cox)',
]

from models import entities
from models import models
from models import student_work
from models import transforms
from tests.functional import actions
from google.appengine.ext import db


class ReferencedModel(entities.BaseEntity):
    pass


class UnvalidatedReference(entities.BaseEntity):
    referenced_model_key = student_work.KeyProperty()


class ValidatedReference(entities.BaseEntity):
    referenced_model_key = student_work.KeyProperty(kind=ReferencedModel.kind())


class KeyPropertyTest(actions.TestBase):
    """Tests KeyProperty."""

    def setUp(self):
        super(KeyPropertyTest, self).setUp()
        self.referenced_model_key = ReferencedModel().put()

    def test_bidirectional_transforms_succeed(self):
        """Tests that transforms entity<->dict<->json round trips correctly."""
        referenced_model_key = ReferencedModel().put()
        entity = UnvalidatedReference(referenced_model_key=referenced_model_key)
        entity.put()

        transformed = transforms.entity_to_dict(entity)
        self.assertEqual(referenced_model_key, entity.referenced_model_key)
        self.assertEqual(
            referenced_model_key, transformed['referenced_model_key'])

        new_key = ReferencedModel().put()
        transformed['referenced_model_key'] = new_key
        restored = transforms.dict_to_entity(entity, transformed)
        self.assertEqual(new_key, restored.referenced_model_key)

        json = transforms.dict_to_json(transformed)
        self.assertEqual(str(new_key), json['referenced_model_key'])

        from_json = transforms.json_to_dict(
            json, {'properties': {'referenced_model_key': {'type': 'string'}}})
        self.assertEqual({'referenced_model_key': str(new_key)}, from_json)

    def test_type_not_validated_if_kind_not_passed(self):
        model_key = db.Model().put()
        unvalidated = UnvalidatedReference(referenced_model_key=model_key)
        self.assertEqual(model_key, unvalidated.referenced_model_key)

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

    def test_validation_fails(self):
        model_key = db.Model().put()
        self.assertRaises(
            db.BadValueError, ValidatedReference,
            referenced_model_key='not_a_key')
        self.assertRaises(
            db.BadValueError, ValidatedReference,
            referenced_model_key=model_key)


class ReviewTest(actions.ExportTestBase):

    def setUp(self):
        super(ReviewTest, self).setUp()
        self.reviewee_email = 'reviewee@exmaple.com'
        self.reviewer_email = 'reviewer@example.com'
        self.unit_id = 'unit_id'
        self.reviewee = models.Student(key_name=self.reviewee_email)
        self.reviewee_key = self.reviewee.put()
        self.reviewer = models.Student(key_name=self.reviewer_email)
        self.reviewer_key = self.reviewer.put()
        self.review = student_work.Review(
            reviewee_key=self.reviewee_key, reviewer_key=self.reviewer_key,
            unit_id=self.unit_id)
        self.review_key = self.review.put()

    def test_constructor_sets_key_name(self):
        self.assertEqual(
            student_work.Review.key_name(
                self.unit_id, self.reviewee_key, self.reviewer_key),
            self.review_key.name())

    def test_for_export_transforms_correctly(self):
        exported = self.review.for_export(self.transform)
        self.assert_blacklisted_properties_removed(self.review, exported)
        self.assertEqual(
            'transformed_' + self.reviewer_key.name(),
            exported.reviewer_key.name())

    def test_safe_key_makes_key_names_safe(self):
        safe_review_key = student_work.Review.safe_key(
            self.review_key, self.transform)
        _, safe_unit_id, safe_reviewee_key_str, safe_reviewer_key_str = (
            student_work.Review._split_key(safe_review_key.name()))
        safe_reviewee_key = db.Key(encoded=safe_reviewee_key_str)
        safe_reviewer_key = db.Key(encoded=safe_reviewer_key_str)
        self.assertEqual(
            'transformed_' + self.reviewee_email, safe_reviewee_key.name())
        self.assertEqual(
            'transformed_' + self.reviewer_email, safe_reviewer_key.name())
        self.assertEqual(self.unit_id, safe_unit_id)


class SubmissionTest(actions.ExportTestBase):

    def setUp(self):
        super(SubmissionTest, self).setUp()
        self.reviewee_email = 'reviewee@example.com'
        self.unit_id = 'unit_id'
        self.reviewee = models.Student(key_name=self.reviewee_email)
        self.reviewee_key = self.reviewee.put()
        self.submission = student_work.Submission(
            reviewee_key=self.reviewee_key, unit_id=self.unit_id)
        self.submission_key = self.submission.put()

    def test_constructor_sets_key_name(self):
        self.assertEqual(
            student_work.Submission.key_name(self.unit_id, self.reviewee_key),
            self.submission_key.name())

    def test_for_export_transforms_correctly(self):
        exported = self.submission.for_export(self.transform)
        self.assert_blacklisted_properties_removed(self.submission, exported)
        self.assertEqual(
            'transformed_' + self.reviewee_key.name(),
            exported.reviewee_key.name())

    def test_safe_key_makes_reviewee_key_name_safe(self):
        safe_submission_key = student_work.Submission.safe_key(
            self.submission_key, self.transform)
        _, safe_unit_id, safe_reviewee_key_name = (
            student_work.Submission._split_key(safe_submission_key.name()))
        self.assertEqual(
            'transformed_' + self.reviewee_email, safe_reviewee_key_name)
        self.assertEqual(self.unit_id, safe_unit_id)
