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

"""Implementation of the review subsystem."""

__author__ = [
    'johncox@google.com (John Cox)',
]


from models import review
from modules.review import peer
from google.appengine.ext import db


class _DomainObject(object):
    """Domain object for review-related classes."""

    # db.Model. The model definition associated with this domain object class.
    _model = None

    @classmethod
    def make_key(cls, id_or_name, namespace):
        """Makes a db.Key for a domain object."""
        assert cls._model is not None
        return db.Key.from_path(
            cls._model.kind(), id_or_name, namespace=namespace)


class Review(_DomainObject):
    """Domain object for a student work submission."""

    _model = review.Review

    def __init__(self, contents=None, key=None):
        self._contents = contents
        self._key = key

    @property
    def contents(self):
        return self._contents

    @property
    def key(self):
        return self._key


class ReviewStep(_DomainObject):
    """Domain object for the status of a single review at a point in time."""

    _model = peer.ReviewStep

    def __init__(
        self, assigner_kind=None, change_date=None, create_date=None, key=None,
        removed=None, review_key=None, review_summary_key=None,
        reviewee_key=None, reviewer_key=None, state=None, submission_key=None,
        unit_id=None):
        self._assigner_kind = assigner_kind
        self._change_date = change_date
        self._create_date = create_date
        self._key = key
        self._removed = removed
        self._review_key = review_key
        self._review_summary_key = review_summary_key
        self._reviewee_key = reviewee_key
        self._reviewer_key = reviewer_key
        self._state = state
        self._submission_key = submission_key
        self._unit_id = unit_id

    @property
    def assigner_kind(self):
        return self._assigner_kind

    @property
    def change_date(self):
        return self._change_date

    @property
    def create_date(self):
        return self._create_date

    @property
    def key(self):
        return self._key

    @property
    def removed(self):
        return self._removed

    @property
    def review_key(self):
        return self._review_key

    @property
    def review_summary_key(self):
        return self._review_summary_key

    @property
    def reviewee_key(self):
        return self._reviewee_key

    @property
    def reviewer_key(self):
        return self._reviewer_key

    @property
    def state(self):
        return self._state

    @property
    def submission_key(self):
        return self._submission_key

    @property
    def unit_id(self):
        return self._unit_id


class ReviewSummary(_DomainObject):
    """Domain object for review state aggregate entities."""

    _model = peer.ReviewSummary

    def __init__(
        self, assigned_count=None, completed_count=None, change_date=None,
        create_date=None, key=None, submission_key=None, unit_id=None):
        self._assigned_count = assigned_count
        self._completed_count = completed_count
        self._change_date = change_date
        self._create_date = create_date
        self._key = key
        self._submission_key = submission_key
        self._unit_id = unit_id

    @property
    def assigned_count(self):
        return self._assigned_count

    @property
    def completed_count(self):
        return self._completed_count

    @property
    def change_date(self):
        return self._change_date

    @property
    def create_date(self):
        return self._create_date

    @property
    def key(self):
        return self._key

    @property
    def submission_key(self):
        return self._submission_key

    @property
    def unit_id(self):
        return self._unit_id


class Submission(_DomainObject):
    """Domain object for a student work submission."""

    _model = review.Submission

    def __init__(self, contents=None, key=None):
        self._contents = contents
        self._key = key

    @property
    def contents(self):
        return self._contents

    @property
    def key(self):
        return self._key
