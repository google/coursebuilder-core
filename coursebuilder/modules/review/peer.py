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

"""Internal implementation details of the peer review subsystem.

Public classes, including domain objects, can be found in domain.py and
models/student_work.py. Entities declared here should not be used by external
clients.
"""

__author__ = [
    'johncox@google.com (John Cox)',
]

from models import counters
from models import models
from models import student_work
from modules.review import domain
from google.appengine.ext import db

COUNTER_INCREMENT_COUNT_COUNT_AGGREGATE_EXCEEDED_MAX = counters.PerfCounter(
    'gcb-pr-increment-count-count-aggregate-exceeded-max',
    ('number of times increment_count() failed because the new aggregate of '
     'the counts would have exceeded domain.MAX_UNREMOVED_REVIEW_STEPS'))


class ReviewSummary(student_work.BaseEntity):
    """Object that tracks the aggregate state of reviews for a submission."""

    # UTC last modification timestamp.
    change_date = db.DateTimeProperty(auto_now=True, required=True)
    # UTC create date.
    create_date = db.DateTimeProperty(auto_now_add=True, required=True)

    # Strong counters. Callers should never manipulate these directly. Instead,
    # use decrement|increment_count.
    # Count of ReviewStep entities for this submission currently in state
    # STATE_ASSIGNED.
    assigned_count = db.IntegerProperty(default=0, required=True)
    # Count of ReviewStep entities for this submission currently in state
    # STATE_COMPLETED.
    completed_count = db.IntegerProperty(default=0, required=True)
    # Count of ReviewStep entities for this submission currently in state
    # STATE_EXPIRED.
    expired_count = db.IntegerProperty(default=0, required=True)

    # Key of the student who wrote the submission being reviewed.
    reviewee_key = student_work.KeyProperty(
        kind=models.Student.kind(), required=True)
    # Key of the submission being reviewed.
    submission_key = student_work.KeyProperty(
        kind=student_work.Submission.kind(), required=True)
    # Identifier of the unit this review is a part of.
    unit_id = db.StringProperty(required=True)

    def __init__(self, *args, **kwargs):
        """Constructs a new ReviewSummary."""
        assert not kwargs.get('key_name'), (
            'Setting key_name manually not supported')
        submission_key = kwargs.get('submission_key')
        assert submission_key, 'Missing required submission_key property'
        reviewee_key = kwargs.get('reviewee_key')
        assert reviewee_key, 'Missing required reviewee_key property'
        kwargs['key_name'] = self.key_name(submission_key)
        super(ReviewSummary, self).__init__(*args, **kwargs)

    @classmethod
    def key_name(cls, submission_key):
        """Creates a key_name string for datastore operations."""
        return '(review_summary:%s)' % submission_key.id_or_name()

    @classmethod
    def safe_key(cls, db_key, transform_fn):
        _, _, unit_id, unsafe_reviewee_key_name = cls._split_key(db_key.name())
        unsafe_reviewee_key = db.Key.from_path(
            models.Student.kind(), unsafe_reviewee_key_name)
        unsafe_submission_key = student_work.Submission.get_key(
            unit_id, unsafe_reviewee_key)
        safe_submission_key = student_work.Submission.safe_key(
            unsafe_submission_key, transform_fn)
        return db.Key.from_path(cls.kind(), cls.key_name(safe_submission_key))

    def _check_count(self):
        count_sum = (
            self.assigned_count + self.completed_count + self.expired_count)
        if count_sum >= domain.MAX_UNREMOVED_REVIEW_STEPS:
            COUNTER_INCREMENT_COUNT_COUNT_AGGREGATE_EXCEEDED_MAX.inc()
            raise db.BadValueError(
                'Unable to increment %s to %s; max is %s' % (
                    self.kind(), count_sum, domain.MAX_UNREMOVED_REVIEW_STEPS))

    def decrement_count(self, state):
        """Decrements the count for the given state enum; does not save.

        Args:
            state: string. State indicating counter to decrement; must be one of
                domain.REVIEW_STATES.

        Raises:
            ValueError: if state not in domain.REVIEW_STATES.
        """
        if state == domain.REVIEW_STATE_ASSIGNED:
            self.assigned_count -= 1
        elif state == domain.REVIEW_STATE_COMPLETED:
            self.completed_count -= 1
        elif state == domain.REVIEW_STATE_EXPIRED:
            self.expired_count -= 1
        else:
            raise ValueError('%s not in %s' % (state, domain.REVIEW_STATES))

    def increment_count(self, state):
        """Increments the count for the given state enum; does not save.

        Args:
            state: string. State indicating counter to increment; must be one of
                domain.REVIEW_STATES.

        Raises:
            db.BadValueError: if incrementing the counter would cause the sum of
               all *_counts to exceed domain.MAX_UNREMOVED_REVIEW_STEPS.
            ValueError: if state not in domain.REVIEW_STATES
        """
        if state not in domain.REVIEW_STATES:
            raise ValueError('%s not in %s' % (state, domain.REVIEW_STATES))

        self._check_count()

        if state == domain.REVIEW_STATE_ASSIGNED:
            self.assigned_count += 1
        elif state == domain.REVIEW_STATE_COMPLETED:
            self.completed_count += 1
        elif state == domain.REVIEW_STATE_EXPIRED:
            self.expired_count += 1

    def for_export(self, transform_fn):
        model = super(ReviewSummary, self).for_export(transform_fn)
        model.reviewee_key = models.Student.safe_key(
            model.reviewee_key, transform_fn)
        model.submission_key = student_work.Submission.safe_key(
            model.submission_key, transform_fn)
        return model

    @classmethod
    def _get_student_key(cls, value):
        return db.Key.from_path(models.Student.kind(), value)

    @classmethod
    def delete_by_reviewee_id(cls, user_id):
        student_key = cls._get_student_key(user_id)
        query = ReviewSummary.all(keys_only=True).filter(
            'reviewee_key =', student_key)
        db.delete(query.run())


class ReviewStep(student_work.BaseEntity):
    """Object that represents a single state of a review."""

    # Audit trail information.

    # Identifier for the kind of thing that did the assignment. Used to
    # distinguish between assignments done by humans and those done by the
    # review subsystem.
    assigner_kind = db.StringProperty(
        choices=domain.ASSIGNER_KINDS, required=True)
    # UTC last modification timestamp.
    change_date = db.DateTimeProperty(auto_now=True, required=True)
    # UTC create date.
    create_date = db.DateTimeProperty(auto_now_add=True, required=True)

    # Repeated data to allow filtering/ordering in queries.

    # Key of the submission being reviewed.
    submission_key = student_work.KeyProperty(
        kind=student_work.Submission.kind(), required=True)
    # Unit this review step is part of.
    unit_id = db.StringProperty(required=True)

    # State information.

    # State of this review step.
    state = db.StringProperty(choices=domain.REVIEW_STATES, required=True)
    # Whether or not the review has been removed. By default removed entities
    # are ignored for most queries.
    removed = db.BooleanProperty(default=False)

    # Pointers that tie the work and people involved together.

    # Key of the Review associated with this step.
    review_key = student_work.KeyProperty(kind=student_work.Review.kind())
    # Key of the associated ReviewSummary.
    review_summary_key = student_work.KeyProperty(kind=ReviewSummary.kind())
    # Key of the Student being reviewed.
    reviewee_key = student_work.KeyProperty(kind=models.Student.kind())
    # Key of the Student doing this review.
    reviewer_key = student_work.KeyProperty(kind=models.Student.kind())

    def __init__(self, *args, **kwargs):
        """Constructs a new ReviewStep."""
        assert not kwargs.get('key_name'), (
            'Setting key_name manually not supported')
        reviewer_key = kwargs.get('reviewer_key')
        reviewee_key = kwargs.get('reviewee_key')
        submission_key = kwargs.get('submission_key')
        assert reviewer_key, 'Missing required reviewer_key property'
        assert reviewee_key, 'Missing required reviewee_key property'
        assert submission_key, 'Missing required submission_key property'
        kwargs['key_name'] = self.key_name(submission_key, reviewer_key)
        super(ReviewStep, self).__init__(*args, **kwargs)

    @classmethod
    def key_name(cls, submission_key, reviewer_key):
        """Creates a key_name string for datastore operations."""
        return '(review_step:%s:%s)' % (
            submission_key.id_or_name(), reviewer_key.id_or_name())

    @classmethod
    def safe_key(cls, db_key, transform_fn):
        """Constructs a version of the entitiy's key that is safe for export."""
        cls._split_key(db_key.name())
        name = db_key.name().strip('()')
        unsafe_submission_key_name, unsafe_reviewer_id_or_name = name.split(
            ':', 1)[1].rsplit(':', 1)
        unsafe_reviewer_key = db.Key.from_path(
            models.Student.kind(), unsafe_reviewer_id_or_name)
        safe_reviewer_key = models.Student.safe_key(
            unsafe_reviewer_key, transform_fn)

        # Treating as module-protected. pylint: disable=protected-access
        _, unit_id, unsafe_reviewee_key_name = (
            student_work.Submission._split_key(unsafe_submission_key_name))
        unsafe_reviewee_key = db.Key.from_path(
            models.Student.kind(), unsafe_reviewee_key_name)
        unsafe_submission_key = student_work.Submission.get_key(
            unit_id, unsafe_reviewee_key)
        safe_submission_key = student_work.Submission.safe_key(
            unsafe_submission_key, transform_fn)

        return db.Key.from_path(
            cls.kind(), cls.key_name(safe_submission_key, safe_reviewer_key))

    def for_export(self, transform_fn):
        """Creates a version of the entity that is safe for export."""
        model = super(ReviewStep, self).for_export(transform_fn)
        model.review_key = student_work.Review.safe_key(
            model.review_key, transform_fn)
        model.review_summary_key = ReviewSummary.safe_key(
            model.review_summary_key, transform_fn)
        model.reviewee_key = models.Student.safe_key(
            model.reviewee_key, transform_fn)
        model.reviewer_key = models.Student.safe_key(
            model.reviewer_key, transform_fn)
        model.submission_key = student_work.Submission.safe_key(
            model.submission_key, transform_fn)
        return model

    @classmethod
    def _get_student_key(cls, value):
        return db.Key.from_path(models.Student.kind(), value)

    @classmethod
    def delete_by_reviewee_id(cls, user_id):
        student_key = cls._get_student_key(user_id)
        query = ReviewStep.all(keys_only=True).filter(
            'reviewee_key =', student_key)
        db.delete(query.run())
