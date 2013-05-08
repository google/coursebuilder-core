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

from models import review
from tests.functional import actions


class ReviewTest(actions.TestBase):

    def test_make_key(self):
        key = review.Review.make_key('id_or_name', 'namespace')
        self.assertEqual(review.ReviewModel.__name__, key.kind())
        self.assertEqual('id_or_name', key.id_or_name())
        self.assertEqual('namespace', key.namespace())


class SubmissionTest(actions.TestBase):

    def test_make_key(self):
        key = review.Submission.make_key('id_or_name', 'namespace')
        self.assertEqual(review.SubmissionModel.__name__, key.kind())
        self.assertEqual('id_or_name', key.id_or_name())
        self.assertEqual('namespace', key.namespace())
