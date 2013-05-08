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

"""Functional tests for modules/review/api.py."""

__author__ = [
    'johncox@google.com (John Cox)',
]

from models import review
from modules.review import peer
from modules.review import review as review_module
from tests.functional import actions


class TestBase(actions.TestBase):

    def assert_make_key_successful(
        self, domain_object_class, db_model_class, id_or_name, namespace):
        key = domain_object_class.make_key(id_or_name, namespace)
        self.assertEqual(db_model_class.__name__, key.kind())
        self.assertEqual(id_or_name, key.id_or_name())
        self.assertEqual(namespace, key.namespace())


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
