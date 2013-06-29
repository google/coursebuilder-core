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

"""Functional tests for models/student_work.py."""

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

    def setUp(self):  # From superclass. pylint: disable-msg=g-bad-name
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
        json = transforms.dict_to_json(transformed, None)
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


class ReviewTest(actions.TestBase):

    def test_constructor_sets_key_name(self):
        """Tests construction of key_name, put of entity with key_name set."""
        unit_id = 'unit_id'
        reviewer_key = models.Student(key_name='reviewer@example.com').put()
        review_key = student_work.Review(
            reviewer_key=reviewer_key, unit_id=unit_id).put()
        self.assertEqual(
            student_work.Review.key_name(unit_id, reviewer_key),
            review_key.name())


class SubmissionTest(actions.TestBase):

    def test_constructor_sets_key_name(self):
        """Tests construction of key_name, put of entity with key_name set."""
        unit_id = 'unit_id'
        reviewee_key = models.Student(key_name='reviewee@example.com').put()
        review_key = student_work.Submission(
            reviewee_key=reviewee_key, unit_id=unit_id).put()
        self.assertEqual(
            student_work.Submission.key_name(unit_id, reviewee_key),
            review_key.name())
