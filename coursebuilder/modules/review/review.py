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

import datetime
import random

from common import schema_fields
from models import counters
from models import custom_modules
from models import data_removal
from models import data_sources
from models import entities
from models import entity_transforms
from models import student_work
from models import transforms
from models import utils
import models.review
from modules.dashboard import dashboard
from modules.review import dashboard as review_dashboard
from modules.review import domain
from modules.review import peer
from modules.review import stats
from google.appengine.ext import db


# In-process increment-only performance counters.
COUNTER_ADD_REVIEWER_BAD_SUMMARY_KEY = counters.PerfCounter(
    'gcb-pr-add-reviewer-bad-summary-key',
    'number of times add_reviewer() failed due to a bad review summary key')
COUNTER_ADD_REVIEWER_SET_ASSIGNER_KIND_HUMAN = counters.PerfCounter(
    'gcb-pr-add-reviewer-set-assigner-kind-human',
    ("number of times add_reviewer() changed an existing step's assigner_kind "
     'to ASSIGNER_KIND_HUMAN'))
COUNTER_ADD_REVIEWER_CREATE_REVIEW_STEP = counters.PerfCounter(
    'gcb-pr-add-reviewer-create-review-step',
    'number of times add_reviewer() created a new review step')
COUNTER_ADD_REVIEWER_EXPIRED_STEP_REASSIGNED = counters.PerfCounter(
    'gcb-pr-add-reviewer-expired-step-reassigned',
    'number of times add_reviewer() reassigned an expired step')
COUNTER_ADD_REVIEWER_FAILED = counters.PerfCounter(
    'gcb-pr-add-reviewer-failed',
    'number of times add_reviewer() had a fatal error')
COUNTER_ADD_REVIEWER_REMOVED_STEP_UNREMOVED = counters.PerfCounter(
    'gcb-pr-add-reviewer-removed-step-unremoved',
    'number of times add_reviewer() unremoved a removed review step')
COUNTER_ADD_REVIEWER_START = counters.PerfCounter(
    'gcb-pr-add-reviewer-start',
    'number of times add_reviewer() has started processing')
COUNTER_ADD_REVIEWER_SUCCESS = counters.PerfCounter(
    'gcb-pr-add-reviewer-success',
    'number of times add_reviewer() completed successfully')
COUNTER_ADD_REVIEWER_UNREMOVED_STEP_FAILED = counters.PerfCounter(
    'gcb-pr-add-reviewer-unremoved-step-failed',
    ('number of times add_reviewer() failed on an unremoved step with a fatal '
     'error'))

COUNTER_ASSIGNMENT_CANDIDATES_QUERY_RESULTS_RETURNED = counters.PerfCounter(
    'gcb-pr-assignment-candidates-query-results-returned',
    ('number of results returned by the query returned by '
     'get_assignment_candidates_query()'))

COUNTER_DELETE_REVIEWER_ALREADY_REMOVED = counters.PerfCounter(
    'gcb-pr-review-delete-reviewer-already-removed',
    ('number of times delete_reviewer() called on review step with removed '
     'already True'))
COUNTER_DELETE_REVIEWER_FAILED = counters.PerfCounter(
    'gcb-pr-review-delete-reviewer-failed',
    'number of times delete_reviewer() had a fatal error')
COUNTER_DELETE_REVIEWER_START = counters.PerfCounter(
    'gcb-pr-review-delete-reviewer-start',
    'number of times delete_reviewer() has started processing')
COUNTER_DELETE_REVIEWER_STEP_MISS = counters.PerfCounter(
    'gcb-pr-review-delete-reviewer-step-miss',
    'number of times delete_reviewer() found a missing review step')
COUNTER_DELETE_REVIEWER_SUCCESS = counters.PerfCounter(
    'gcb-pr-review-delete-reviewer-success',
    'number of times delete_reviewer() completed successfully')
COUNTER_DELETE_REVIEWER_SUMMARY_MISS = counters.PerfCounter(
    'gcb-pr-review-delete-reviewer-summary-miss',
    'number of times delete_reviewer() found a missing review summary')

COUNTER_EXPIRE_REVIEW_CANNOT_TRANSITION = counters.PerfCounter(
    'gcb-pr-expire-review-cannot-transition',
    ('number of times expire_review() was called on a review step that could '
     'not be transitioned to REVIEW_STATE_EXPIRED'))
COUNTER_EXPIRE_REVIEW_FAILED = counters.PerfCounter(
    'gcb-pr-expire-review-failed',
    'number of times expire_review() had a fatal error')
COUNTER_EXPIRE_REVIEW_START = counters.PerfCounter(
    'gcb-pr-expire-review-start',
    'number of times expire_review() has started processing')
COUNTER_EXPIRE_REVIEW_STEP_MISS = counters.PerfCounter(
    'gcb-pr-expire-review-step-miss',
    'number of times expire_review() found a missing review step')
COUNTER_EXPIRE_REVIEW_SUCCESS = counters.PerfCounter(
    'gcb-pr-expire-review-success',
    'number of times expire_review() completed successfully')
COUNTER_EXPIRE_REVIEW_SUMMARY_MISS = counters.PerfCounter(
    'gcb-pr-expire-review-summary-miss',
    'number of times expire_review() found a missing review summary')

COUNTER_EXPIRE_OLD_REVIEWS_FOR_UNIT_EXPIRE = counters.PerfCounter(
    'gcb-pr-expire-old-reviews-for-unit-expire',
    'number of records expire_old_reviews_for_unit() has expired')
COUNTER_EXPIRE_OLD_REVIEWS_FOR_UNIT_SKIP = counters.PerfCounter(
    'gcb-pr-expire-old-reviews-for-unit-skip',
    ('number of times expire_old_reviews_for_unit() skipped a record due to an '
     'error'))
COUNTER_EXPIRE_OLD_REVIEWS_FOR_UNIT_START = counters.PerfCounter(
    'gcb-pr-expire-old-reviews-for-unit-start',
    'number of times expire_old_reviews_for_unit() has started processing')
COUNTER_EXPIRE_OLD_REVIEWS_FOR_UNIT_SUCCESS = counters.PerfCounter(
    'gcb-pr-expire-old-reviews-for-unit-success',
    'number of times expire_old_reviews_for_unit() completed successfully')

COUNTER_EXPIRY_QUERY_KEYS_RETURNED = counters.PerfCounter(
    'gcb-pr-expiry-query-keys-returned',
    'number of keys returned by the query returned by get_expiry_query()')

COUNTER_GET_NEW_REVIEW_ALREADY_ASSIGNED = counters.PerfCounter(
    'gcb-pr-get-new-review-already-assigned',
    ('number of times get_new_review() rejected a candidate because the '
     'reviewer is already assigned to or has already completed it'))
COUNTER_GET_NEW_REVIEW_ASSIGNMENT_ATTEMPTED = counters.PerfCounter(
    'gcb-pr-get-new-review-assignment-attempted',
    'number of times get_new_review() attempted to assign a candidate')
COUNTER_GET_NEW_REVIEW_CANNOT_UNREMOVE_COMPLETED = counters.PerfCounter(
    'gcb-pr-get-new-review-cannot-unremove-completed',
    ('number of times get_new_review() failed because the reviewer already had '
     'a completed, removed review step'))
COUNTER_GET_NEW_REVIEW_FAILED = counters.PerfCounter(
    'gcb-pr-get-new-review-failed',
    'number of times get_new_review() had a fatal error')
COUNTER_GET_NEW_REVIEW_NOT_ASSIGNABLE = counters.PerfCounter(
    'gcb-pr-get-new-review-none-assignable',
    'number of times get_new_review() failed to find an assignable review')
COUNTER_GET_NEW_REVIEW_REASSIGN_EXISTING = counters.PerfCounter(
    'gcb-pr-get-new-review-reassign-existing',
    ('number of times get_new_review() unremoved and reassigned an existing '
     'review step'))
COUNTER_GET_NEW_REVIEW_START = counters.PerfCounter(
    'gcb-pr-get-new-review-start',
    'number of times get_new_review() has started processing')
COUNTER_GET_NEW_REVIEW_SUCCESS = counters.PerfCounter(
    'gcb-pr-get-new-review-success',
    'number of times get_new_review() found and assigned a new review')
COUNTER_GET_NEW_REVIEW_SUMMARY_CHANGED = counters.PerfCounter(
    'gcb-pr-get-new-review-summary-changed',
    ('number of times get_new_review() rejected a candidate because the review '
     'summary changed during processing'))

COUNTER_GET_REVIEW_STEP_KEYS_BY_KEYS_RETURNED = counters.PerfCounter(
    'gcb-pr-get-review-step-keys-by-keys-returned',
    'number of keys get_review_step_keys_by() returned')
COUNTER_GET_REVIEW_STEP_KEYS_BY_FAILED = counters.PerfCounter(
    'gcb-pr-get-review-step-keys-by-failed',
    'number of times get_review_step_keys_by() had a fatal error')
COUNTER_GET_REVIEW_STEP_KEYS_BY_START = counters.PerfCounter(
    'gcb-pr-get-review-step-keys-by-start',
    'number of times get_review_step_keys_by() started processing')
COUNTER_GET_REVIEW_STEP_KEYS_BY_SUCCESS = counters.PerfCounter(
    'gcb-pr-get-review-step-keys-by-success',
    'number of times get_review_step_keys_by() completed successfully')

COUNTER_GET_SUBMISSION_AND_REVIEW_STEP_KEYS_FAILED = counters.PerfCounter(
    'gcb-pr-get-submission-and-review-step-keys-failed',
    'number of times get_submission_and_review_step_keys() had a fatal error')
COUNTER_GET_SUBMISSION_AND_REVIEW_STEP_KEYS_RETURNED = counters.PerfCounter(
    'gcb-pr-get-submission-and-review-step-keys-keys-returned',
    'number of keys get_submission_and_review_step_keys() returned')
COUNTER_GET_SUBMISSION_AND_REVIEW_STEP_KEYS_START = counters.PerfCounter(
    'gcb-pr-get-submission-and-review-step-keys-start',
    ('number of times get_submission_and_review_step_keys() has begun '
     'processing'))
COUNTER_GET_SUBMISSION_AND_REVIEW_STEP_KEYS_SUBMISSION_MISS = (
    counters.PerfCounter(
        'gcb-pr-get-submission-and-review-step-keys-submission-miss',
        ('number of times get_submission_and_review_step_keys() failed to find '
         'a submission_key')))
COUNTER_GET_SUBMISSION_AND_REVIEW_STEP_KEYS_SUCCESS = counters.PerfCounter(
    'gcb-pr-get-submission-and-review-step_keys-success',
    ('number of times get_submission-and-review-step-keys() completed '
     'successfully'))

COUNTER_START_REVIEW_PROCESS_FOR_ALREADY_STARTED = counters.PerfCounter(
    'gcb-pr-start-review-process-for-already-started',
    ('number of times start_review_process_for() called when review already '
     'started'))
COUNTER_START_REVIEW_PROCESS_FOR_FAILED = counters.PerfCounter(
    'gcb-pr-start-review-process-for-failed',
    'number of times start_review_process_for() had a fatal error')
COUNTER_START_REVIEW_PROCESS_FOR_START = counters.PerfCounter(
    'gcb-pr-start-review-process-for-start',
    'number of times start_review_process_for() has started processing')
COUNTER_START_REVIEW_PROCESS_FOR_SUCCESS = counters.PerfCounter(
    'gcb-pr-start-review-process-for-success',
    'number of times start_review_process_for() completed successfully')

COUNTER_WRITE_REVIEW_COMPLETED_ASSIGNED_STEP = counters.PerfCounter(
    'gcb-pr-write-review-completed-assigned-step',
    'number of times write_review() transitioned an assigned step to completed')
COUNTER_WRITE_REVIEW_COMPLETED_EXPIRED_STEP = counters.PerfCounter(
    'gcb-pr-write-review-completed-expired-step',
    'number of times write_review() transitioned an expired step to completed')
COUNTER_WRITE_REVIEW_CREATED_NEW_REVIEW = counters.PerfCounter(
    'gcb-pr-write-review-created-new-review',
    'number of times write_review() created a new review')
COUNTER_WRITE_REVIEW_FAILED = counters.PerfCounter(
    'gcb-pr-write-review-failed',
    'number of times write_review() had a fatal error')
COUNTER_WRITE_REVIEW_REVIEW_MISS = counters.PerfCounter(
    'gcb-pr-write-review-review-miss',
    'number of times write_review() found a missing review')
COUNTER_WRITE_REVIEW_START = counters.PerfCounter(
    'gcb-pr-write-review-start',
    'number of times write_review() started processing')
COUNTER_WRITE_REVIEW_STEP_MISS = counters.PerfCounter(
    'gcb-pr-write-review-step-miss',
    'number of times write_review() found a missing review step')
COUNTER_WRITE_REVIEW_SUMMARY_MISS = counters.PerfCounter(
    'gcb-pr-write-review-summary-miss',
    'number of times write_review() found a missing review summary')
COUNTER_WRITE_REVIEW_SUCCESS = counters.PerfCounter(
    'gcb-pr-write-review-success',
    'number of times write_review() completed successfully')
COUNTER_WRITE_REVIEW_UPDATED_EXISTING_REVIEW = counters.PerfCounter(
    'gcb-pr-write-review-updated-existing-review',
    'number of times write_review() updated an existing review')


# Number of entities to fetch when querying for all review steps that meet
# given criteria. Ideally we'd cursor through results rather than setting a
# ceiling, but for now let's allow as many removed results as unremoved.
_REVIEW_STEP_QUERY_LIMIT = 2 * domain.MAX_UNREMOVED_REVIEW_STEPS


class Manager(object):
    """Object that manages the review subsystem."""

    @classmethod
    def add_reviewer(cls, unit_id, submission_key, reviewee_key, reviewer_key):
        """Adds a reviewer for a submission.

        If there is no pre-existing review step, one will be created.

        Attempting to add an existing unremoved step in REVIEW_STATE_ASSIGNED or
        REVIEW_STATE_COMPLETED is an error.

        If there is an existing unremoved review in REVIEW_STATE_EXPIRED, it
        will be put in REVIEW_STATE_ASSIGNED. If there is a removed review in
        REVIEW_STATE_ASSIGNED or REVIEW_STATE_EXPIRED, it will be put in
        REVIEW_STATE_ASSIGNED and unremoved. If it is in REVIEW_STATE_COMPLETED,
        it will be unremoved but its state will not change. In all these cases
        the assigner kind will be set to ASSIGNER_KIND_HUMAN.

        Args:
            unit_id: string. Unique identifier for a unit.
            submission_key: db.Key of models.student_work.Submission. The
                submission being registered.
            reviewee_key: db.Key of models.models.Student. The student who
                authored the submission.
            reviewer_key: db.Key of models.models.Student. The student to add as
                a reviewer.

        Raises:
            domain.TransitionError: if there is a pre-existing review step found
                in domain.REVIEW_STATE_ASSIGNED|COMPLETED.

        Returns:
            db.Key of written review step.
        """
        try:
            COUNTER_ADD_REVIEWER_START.inc()
            key = cls._add_reviewer(
                unit_id, submission_key, reviewee_key, reviewer_key)
            COUNTER_ADD_REVIEWER_SUCCESS.inc()
            return key
        except Exception as e:
            COUNTER_ADD_REVIEWER_FAILED.inc()
            raise e

    @classmethod
    @db.transactional(xg=True)
    def _add_reviewer(cls, unit_id, submission_key, reviewee_key, reviewer_key):
        found = peer.ReviewStep.get_by_key_name(
            peer.ReviewStep.key_name(submission_key, reviewer_key))
        if not found:
            return cls._add_new_reviewer(
                unit_id, submission_key, reviewee_key, reviewer_key)
        else:
            return cls._add_reviewer_update_step(found)

    @classmethod
    def _add_new_reviewer(
        cls, unit_id, submission_key, reviewee_key, reviewer_key):
        summary = peer.ReviewSummary(
            assigned_count=1, reviewee_key=reviewee_key,
            submission_key=submission_key, unit_id=unit_id)
        # Synthesize summary key to avoid a second synchronous put op.
        summary_key = db.Key.from_path(
            peer.ReviewSummary.kind(),
            peer.ReviewSummary.key_name(submission_key))
        step = peer.ReviewStep(
            assigner_kind=domain.ASSIGNER_KIND_HUMAN,
            review_summary_key=summary_key, reviewee_key=reviewee_key,
            reviewer_key=reviewer_key, state=domain.REVIEW_STATE_ASSIGNED,
            submission_key=submission_key, unit_id=unit_id)
        # pylint: disable=unbalanced-tuple-unpacking,unpacking-non-sequence
        step_key, written_summary_key = entities.put([step, summary])

        if summary_key != written_summary_key:
            COUNTER_ADD_REVIEWER_BAD_SUMMARY_KEY.inc()
            raise AssertionError(
                'Synthesized invalid review summary key %s' % repr(summary_key))

        COUNTER_ADD_REVIEWER_CREATE_REVIEW_STEP.inc()
        return step_key

    @classmethod
    def _add_reviewer_update_step(cls, step):
        should_increment_human = False
        should_increment_reassigned = False
        should_increment_unremoved = False
        summary = entities.get(step.review_summary_key)

        if not summary:
            COUNTER_ADD_REVIEWER_BAD_SUMMARY_KEY.inc()
            raise AssertionError(
                'Found invalid review summary key %s' % repr(
                    step.review_summary_key))

        if not step.removed:

            if step.state == domain.REVIEW_STATE_EXPIRED:
                should_increment_reassigned = True
                step.state = domain.REVIEW_STATE_ASSIGNED
                summary.decrement_count(domain.REVIEW_STATE_EXPIRED)
                summary.increment_count(domain.REVIEW_STATE_ASSIGNED)
            elif (step.state == domain.REVIEW_STATE_ASSIGNED or
                  step.state == domain.REVIEW_STATE_COMPLETED):
                COUNTER_ADD_REVIEWER_UNREMOVED_STEP_FAILED.inc()
                raise domain.TransitionError(
                    'Unable to add new reviewer to step %s' % (
                        repr(step.key())),
                    step.state, domain.REVIEW_STATE_ASSIGNED)
        else:
            should_increment_unremoved = True
            step.removed = False

            if step.state != domain.REVIEW_STATE_EXPIRED:
                summary.increment_count(step.state)
            else:
                should_increment_reassigned = True
                step.state = domain.REVIEW_STATE_ASSIGNED
                summary.decrement_count(domain.REVIEW_STATE_EXPIRED)
                summary.increment_count(domain.REVIEW_STATE_ASSIGNED)

        if step.assigner_kind != domain.ASSIGNER_KIND_HUMAN:
            should_increment_human = True
            step.assigner_kind = domain.ASSIGNER_KIND_HUMAN

        step_key = entities.put([step, summary])[0]

        if should_increment_human:
            COUNTER_ADD_REVIEWER_SET_ASSIGNER_KIND_HUMAN.inc()
        if should_increment_reassigned:
            COUNTER_ADD_REVIEWER_EXPIRED_STEP_REASSIGNED.inc()
        if should_increment_unremoved:
            COUNTER_ADD_REVIEWER_REMOVED_STEP_UNREMOVED.inc()

        return step_key

    @classmethod
    def delete_reviewer(cls, review_step_key):
        """Deletes the given review step.

        We do not physically delete the review step; we mark it as removed,
        meaning it will be ignored from most queries and the associated review
        summary will have its corresponding state count decremented. Calling
        this method on a removed review step is an error.

        Args:
            review_step_key: db.Key of models.student_work.ReviewStep. The
                review step to delete.

        Raises:
            domain.RemovedError: if called on a review step that has already
                been marked removed.
            KeyError: if there is no review step with the given key, or if the
                step references a review summary that does not exist.

        Returns:
            db.Key of deleted review step.
        """
        try:
            COUNTER_DELETE_REVIEWER_START.inc()
            key = cls._mark_review_step_removed(review_step_key)
            COUNTER_DELETE_REVIEWER_SUCCESS.inc()
            return key
        except Exception as e:
            COUNTER_DELETE_REVIEWER_FAILED.inc()
            raise e

    @classmethod
    @db.transactional(xg=True)
    def _mark_review_step_removed(cls, review_step_key):
        step = entities.get(review_step_key)
        if not step:
            COUNTER_DELETE_REVIEWER_STEP_MISS.inc()
            raise KeyError(
                'No review step found with key %s' % repr(review_step_key))
        if step.removed:
            COUNTER_DELETE_REVIEWER_ALREADY_REMOVED.inc()
            raise domain.RemovedError(
                'Cannot remove step %s' % repr(review_step_key), step.removed)
        summary = entities.get(step.review_summary_key)

        if not summary:
            COUNTER_DELETE_REVIEWER_SUMMARY_MISS.inc()
            raise KeyError(
                'No review summary found with key %s' % repr(
                    step.review_summary_key))

        step.removed = True
        summary.decrement_count(step.state)
        return entities.put([step, summary])[0]

    @classmethod
    def expire_review(cls, review_step_key):
        """Puts a review step in state REVIEW_STATE_EXPIRED.

        Args:
            review_step_key: db.Key of models.student_work.ReviewStep. The
                review step to expire.

        Raises:
            domain.RemovedError: if called on a step that is removed.
            domain.TransitionError: if called on a review step that cannot be
                transitioned to REVIEW_STATE_EXPIRED (that is, it is already in
                REVIEW_STATE_COMPLETED or REVIEW_STATE_EXPIRED).
            KeyError: if there is no review with the given key, or the step
                references a review summary that does not exist.

        Returns:
            db.Key of the expired review step.
        """
        try:
            COUNTER_EXPIRE_REVIEW_START.inc()
            key = cls._transition_state_to_expired(review_step_key)
            COUNTER_EXPIRE_REVIEW_SUCCESS.inc()
            return key
        except Exception as e:
            COUNTER_EXPIRE_REVIEW_FAILED.inc()
            raise e

    @classmethod
    @db.transactional(xg=True)
    def _transition_state_to_expired(cls, review_step_key):
        step = entities.get(review_step_key)

        if not step:
            COUNTER_EXPIRE_REVIEW_STEP_MISS.inc()
            raise KeyError(
                'No review step found with key %s' % repr(review_step_key))

        if step.removed:
            COUNTER_EXPIRE_REVIEW_CANNOT_TRANSITION.inc()
            raise domain.RemovedError(
                'Cannot transition step %s' % repr(review_step_key),
                step.removed)

        if step.state in (
                domain.REVIEW_STATE_COMPLETED, domain.REVIEW_STATE_EXPIRED):
            COUNTER_EXPIRE_REVIEW_CANNOT_TRANSITION.inc()
            raise domain.TransitionError(
                'Cannot transition step %s' % repr(review_step_key),
                step.state, domain.REVIEW_STATE_EXPIRED)

        summary = entities.get(step.review_summary_key)

        if not summary:
            COUNTER_EXPIRE_REVIEW_SUMMARY_MISS.inc()
            raise KeyError(
                'No review summary found with key %s' % repr(
                    step.review_summary_key))

        summary.decrement_count(step.state)
        step.state = domain.REVIEW_STATE_EXPIRED
        summary.increment_count(step.state)
        return entities.put([step, summary])[0]

    @classmethod
    def expire_old_reviews_for_unit(cls, review_window_mins, unit_id):
        """Finds and expires all old review steps for a single unit.

        Args:
            review_window_mins: int. Number of minutes before we expire reviews
                assigned by domain.ASSIGNER_KIND_AUTO.
            unit_id: string. Id of the unit to restrict the query to.

        Returns:
            2-tuple of list of db.Key of peer.ReviewStep. 0th element is keys
            that were written successfully; 1st element is keys that we failed
            to update.
        """
        query = cls.get_expiry_query(review_window_mins, unit_id)
        mapper = utils.QueryMapper(
            query, counter=COUNTER_EXPIRY_QUERY_KEYS_RETURNED, report_every=100)
        expired_keys = []
        exception_keys = []

        def map_fn(review_step_key, expired_keys, exception_keys):
            try:
                expired_keys.append(cls.expire_review(review_step_key))
            except:  # All errors are the same. pylint: disable=bare-except
                # Skip. Either the entity was updated between the query and
                # the update, meaning we don't need to expire it; or we ran into
                # a transient datastore error, meaning we'll expire it next
                # time.
                COUNTER_EXPIRE_OLD_REVIEWS_FOR_UNIT_SKIP.inc()
                exception_keys.append(review_step_key)

        COUNTER_EXPIRE_OLD_REVIEWS_FOR_UNIT_START.inc()

        mapper.run(map_fn, expired_keys, exception_keys)
        COUNTER_EXPIRE_OLD_REVIEWS_FOR_UNIT_EXPIRE.inc(
            increment=len(expired_keys))
        COUNTER_EXPIRE_OLD_REVIEWS_FOR_UNIT_SUCCESS.inc()
        return expired_keys, exception_keys

    @classmethod
    def get_assignment_candidates_query(cls, unit_id):
        """Gets query that returns candidates for new review assignment.

        New assignment candidates are scoped to a unit. We prefer first items
        that have the smallest number of completed reviews, then those that have
        the smallest number of assigned reviews, then those that were created
        most recently.

        The results of the query are user-independent.

        Args:
            unit_id: string. Id of the unit to restrict the query to.

        Returns:
            db.Query that will return [peer.ReviewSummary].
        """
        return peer.ReviewSummary.all(
        ).filter(
            peer.ReviewSummary.unit_id.name, unit_id
        ).order(
            peer.ReviewSummary.completed_count.name
        ).order(
            peer.ReviewSummary.assigned_count.name
        ).order(
            peer.ReviewSummary.create_date.name)

    @classmethod
    def get_expiry_query(
        cls, review_window_mins, unit_id, now_fn=datetime.datetime.utcnow):
        """Gets a db.Query that returns review steps to mark expired.

        Results are items that were assigned by machine, are currently assigned,
        are not removed, were last updated more than review_window_mins ago,
        and are ordered by change date ascending.

        Args:
            review_window_mins: int. Number of minutes before we expire reviews
                assigned by domain.ASSIGNER_KIND_AUTO.
            unit_id: string. Id of the unit to restrict the query to.
            now_fn: function that returns the current UTC datetime. Injectable
                for tests only.

        Returns:
            db.Query.
        """
        get_before = now_fn() - datetime.timedelta(
            minutes=review_window_mins)
        return peer.ReviewStep.all(keys_only=True).filter(
            peer.ReviewStep.unit_id.name, unit_id,
        ).filter(
            peer.ReviewStep.assigner_kind.name, domain.ASSIGNER_KIND_AUTO
        ).filter(
            peer.ReviewStep.state.name, domain.REVIEW_STATE_ASSIGNED
        ).filter(
            peer.ReviewStep.removed.name, False
        ).filter(
            '%s <=' % peer.ReviewStep.change_date.name, get_before
        ).order(
            peer.ReviewStep.change_date.name)

    @classmethod
    def get_new_review(
        cls, unit_id, reviewer_key, candidate_count=20, max_retries=5):
        """Attempts to assign a review to a reviewer.

        We prioritize possible reviews by querying review summary objects,
        finding those that best satisfy cls.get_assignment_candidates_query.

        To minimize write contention, we nontransactionally grab candidate_count
        candidates from the head of the query results. Post-query we filter out
        any candidates that are for the prospective reviewer's own work.

        Then we randomly select one. We transactionally attempt to assign that
        review. If assignment fails because the candidate is updated between
        selection and assignment or the assignment is for a submission the
        reviewer already has or has already done, we remove the candidate from
        the list. We then retry assignment up to max_retries times. If we run
        out of retries or candidates, we raise domain.NotAssignableError.

        This is a naive implementation because it scales only to relatively low
        new review assignments per second and because it can raise
        domain.NotAssignableError when there are in fact assignable reviews.

        Args:
            unit_id: string. The unit to assign work from.
            reviewer_key: db.Key of models.models.Student. The reviewer to
                attempt to assign the review to.
            candidate_count: int. The number of candidate keys to fetch and
                attempt to assign from. Increasing this decreases the chance
                that we will have write contention on reviews, but it costs 1 +
                num_results datastore reads and can get expensive for large
                courses.
            max_retries: int. Number of times to retry failed assignment
                attempts. Careful not to set this too high as a) datastore
                throughput is slow and latency from this method is user-facing,
                and b) if you encounter a few failures it is likely that all
                candidates are now failures, so each retry past the first few is
                of questionable value.

        Raises:
            domain.NotAssignableError: if no review can currently be assigned
                for the given unit_id.

        Returns:
            db.Key of peer.ReviewStep. The newly created assigned review step.
        """
        try:
            COUNTER_GET_NEW_REVIEW_START.inc()
            # Filter out candidates that are for submissions by the reviewer.
            raw_candidates = cls.get_assignment_candidates_query(unit_id).fetch(
                candidate_count)
            COUNTER_ASSIGNMENT_CANDIDATES_QUERY_RESULTS_RETURNED.inc(
                increment=len(raw_candidates))
            candidates = [
                candidate for candidate in raw_candidates
                if candidate.reviewee_key != reviewer_key]

            retries = 0
            while True:
                if not candidates or retries >= max_retries:
                    COUNTER_GET_NEW_REVIEW_NOT_ASSIGNABLE.inc()
                    raise domain.NotAssignableError(
                        'No reviews assignable for unit %s and reviewer %s' % (
                            unit_id, repr(reviewer_key)))
                candidate = cls._choose_assignment_candidate(candidates)
                candidates.remove(candidate)
                assigned_key = cls._attempt_review_assignment(
                    candidate.key(), reviewer_key, candidate.change_date)

                if not assigned_key:
                    retries += 1
                else:
                    COUNTER_GET_NEW_REVIEW_SUCCESS.inc()
                    return assigned_key

        except Exception, e:
            COUNTER_GET_NEW_REVIEW_FAILED.inc()
            raise e

    @classmethod
    def _choose_assignment_candidate(cls, candidates):
        """Seam that allows different choice functions in tests."""
        return random.choice(candidates)

    @classmethod
    @db.transactional(xg=True)
    def _attempt_review_assignment(
        cls, review_summary_key, reviewer_key, last_change_date):
        COUNTER_GET_NEW_REVIEW_ASSIGNMENT_ATTEMPTED.inc()
        summary = entities.get(review_summary_key)
        if not summary:
            raise KeyError('No review summary found with key %s' % repr(
                review_summary_key))
        if summary.change_date != last_change_date:
            # The summary has changed since we queried it. We cannot know for
            # sure what the edit was, but let's skip to the next one because it
            # was probably a review assignment.
            COUNTER_GET_NEW_REVIEW_SUMMARY_CHANGED.inc()
            return

        step = peer.ReviewStep.get_by_key_name(
            peer.ReviewStep.key_name(summary.submission_key, reviewer_key))

        if not step:
            step = peer.ReviewStep(
                assigner_kind=domain.ASSIGNER_KIND_AUTO,
                review_summary_key=summary.key(),
                reviewee_key=summary.reviewee_key, reviewer_key=reviewer_key,
                state=domain.REVIEW_STATE_ASSIGNED,
                submission_key=summary.submission_key, unit_id=summary.unit_id)
        else:
            if step.state == domain.REVIEW_STATE_COMPLETED:
                # Reviewer has previously done this review and the review
                # has been deleted. Skip to the next one.
                COUNTER_GET_NEW_REVIEW_CANNOT_UNREMOVE_COMPLETED.inc()
                return

            if step.removed:
                # We can reassign the existing review step.
                COUNTER_GET_NEW_REVIEW_REASSIGN_EXISTING.inc()
                step.removed = False
                step.assigner_kind = domain.ASSIGNER_KIND_AUTO
                step.state = domain.REVIEW_STATE_ASSIGNED
            else:
                # Reviewee has already reviewed or is already assigned to review
                # this submission, so we cannot reassign the step.
                COUNTER_GET_NEW_REVIEW_ALREADY_ASSIGNED.inc()
                return

        summary.increment_count(domain.REVIEW_STATE_ASSIGNED)
        return entities.put([step, summary])[0]

    @classmethod
    def get_review_step_keys_by(cls, unit_id, reviewer_key):
        """Gets the keys of all review steps in a unit for a reviewer.

        Note that keys for review steps marked removed are included in the
        result set.

        Args:
            unit_id: string. Id of the unit to restrict the query to.
            reviewer_key: db.Key of models.models.Student. The author of the
                requested reviews.

        Returns:
            [db.Key of peer.ReviewStep].
        """
        COUNTER_GET_REVIEW_STEP_KEYS_BY_START.inc()

        try:
            query = peer.ReviewStep.all(keys_only=True).filter(
                peer.ReviewStep.reviewer_key.name, reviewer_key
            ).filter(
                peer.ReviewStep.unit_id.name, unit_id
            ).order(
                peer.ReviewStep.create_date.name,
            )

            keys = [key for key in query.fetch(_REVIEW_STEP_QUERY_LIMIT)]

        except Exception as e:
            COUNTER_GET_REVIEW_STEP_KEYS_BY_FAILED.inc()
            raise e

        COUNTER_GET_REVIEW_STEP_KEYS_BY_SUCCESS.inc()
        COUNTER_GET_REVIEW_STEP_KEYS_BY_KEYS_RETURNED.inc(increment=len(keys))
        return keys

    @classmethod
    def get_review_steps_by_keys(cls, keys):
        """Gets review steps by their keys.

        Args:
            keys: [db.Key of peer.ReviewStep]. Keys to fetch.

        Returns:
            [domain.ReviewStep or None]. Missed keys return None in place in
            result list.
        """
        return [
            cls._make_domain_review_step(model) for model in entities.get(keys)]

    @classmethod
    def _make_domain_review_step(cls, model):
        if model is None:
            return

        return domain.ReviewStep(
            assigner_kind=model.assigner_kind, change_date=model.change_date,
            create_date=model.create_date, key=model.key(),
            removed=model.removed, review_key=model.review_key,
            review_summary_key=model.review_summary_key,
            reviewee_key=model.reviewee_key, reviewer_key=model.reviewer_key,
            state=model.state, submission_key=model.submission_key,
            unit_id=model.unit_id
        )

    @classmethod
    def get_reviews_by_keys(cls, keys):
        """Gets reviews by their keys.

        Args:
            keys: [db.Key of review.Review]. Keys to fetch.

        Returns:
            [domain.Review or None]. Missed keys return None in place in result
            list.
        """
        return [cls._make_domain_review(model) for model in entities.get(keys)]

    @classmethod
    def _make_domain_review(cls, model):
        if model is None:
            return

        return domain.Review(contents=model.contents, key=model.key())

    @classmethod
    def get_submission_and_review_step_keys(cls, unit_id, reviewee_key):
        """Gets the submission key/review step keys for the given pair.

        Note that keys for review steps marked removed are included in the
        result set.

        Args:
            unit_id: string. Id of the unit to restrict the query to.
            reviewee_key: db.Key of models.models.Student. The student who
                authored the submission.

        Raises:
            domain.ConstraintError: if multiple review summary keys were found
                for the given unit_id, reviewee_key pair.
            KeyError: if there is no review summary for the given unit_id,
                reviewee pair.

        Returns:
            (db.Key of Submission, [db.Key of peer.ReviewStep]) if submission
            found for given unit_id, reviewee_key pair; None otherwise.
        """
        COUNTER_GET_SUBMISSION_AND_REVIEW_STEP_KEYS_START.inc()

        try:
            submission_key = db.Key.from_path(
                student_work.Submission.kind(),
                student_work.Submission.key_name(unit_id, reviewee_key))
            submission = entities.get(submission_key)
            if not submission:
                COUNTER_GET_SUBMISSION_AND_REVIEW_STEP_KEYS_SUBMISSION_MISS.inc(
                    )
                return

            step_keys_query = peer.ReviewStep.all(
                keys_only=True
            ).filter(
                peer.ReviewStep.submission_key.name, submission_key
            )

            step_keys = step_keys_query.fetch(_REVIEW_STEP_QUERY_LIMIT)
            results = (submission_key, step_keys)

        except Exception as e:
            COUNTER_GET_SUBMISSION_AND_REVIEW_STEP_KEYS_FAILED.inc()
            raise e

        COUNTER_GET_SUBMISSION_AND_REVIEW_STEP_KEYS_SUCCESS.inc()
        COUNTER_GET_SUBMISSION_AND_REVIEW_STEP_KEYS_RETURNED.inc(
            increment=len(step_keys))
        return results

    @classmethod
    def get_submissions_by_keys(cls, keys):
        """Gets submissions by their keys.

        Args:
            keys: [db.Key of review.Submission]. Keys to fetch.

        Returns:
            [domain.Submission or None]. Missed keys return None in place in
            result list.
        """
        return [
            cls._make_domain_submission(model) for model in entities.get(keys)]

    @classmethod
    def _make_domain_submission(cls, model):
        if model is None:
            return

        return domain.Submission(contents=model.contents, key=model.key())

    @classmethod
    def start_review_process_for(cls, unit_id, submission_key, reviewee_key):
        """Registers a new submission with the review subsystem.

        Once registered, reviews can be assigned against a given submission,
        either by humans or by machine. No reviews are assigned during
        registration -- this method merely makes them assignable.

        Args:
            unit_id: string. Unique identifier for a unit.
            submission_key: db.Key of models.student_work.Submission. The
                submission being registered.
            reviewee_key: db.Key of models.models.Student. The student who
                authored the submission.

        Raises:
            db.BadValueError: if passed args are invalid.
            domain.ReviewProcessAlreadyStartedError: if the review process has
                already been started for this student's submission.

        Returns:
            db.Key of created ReviewSummary.
        """
        try:
            COUNTER_START_REVIEW_PROCESS_FOR_START.inc()
            key = cls._create_review_summary(
                reviewee_key, submission_key, unit_id)
            COUNTER_START_REVIEW_PROCESS_FOR_SUCCESS.inc()
            return key
        except Exception as e:
            COUNTER_START_REVIEW_PROCESS_FOR_FAILED.inc()
            raise e

    @classmethod
    @db.transactional(xg=True)
    def _create_review_summary(cls, reviewee_key, submission_key, unit_id):
        collision = peer.ReviewSummary.get_by_key_name(
            peer.ReviewSummary.key_name(submission_key))

        if collision:
            COUNTER_START_REVIEW_PROCESS_FOR_ALREADY_STARTED.inc()
            raise domain.ReviewProcessAlreadyStartedError()

        return peer.ReviewSummary(
            reviewee_key=reviewee_key, submission_key=submission_key,
            unit_id=unit_id,
        ).put()

    @classmethod
    def write_review(
        cls, review_step_key, review_payload, mark_completed=True):
        """Writes a review, updating associated internal state.

        If the passed step already has a review, that review will be updated. If
        it does not have a review, a new one will be created with the passed
        payload.

        Args:
            review_step_key: db.Key of peer.ReviewStep. The key of the review
                step to update.
            review_payload: string. New contents of the review.
            mark_completed: boolean. If True, set the state of the review to
                domain.REVIEW_STATE_COMPLETED. If False, leave the state as it
                was.

        Raises:
            domain.ConstraintError: if no review found for the review step.
            domain.RemovedError: if the step for the review is removed.
            domain.TransitionError: if mark_completed was True but the step was
                already in domain.REVIEW_STATE_COMPLETED.
            KeyError: if no review step was found with review_step_key.

        Returns:
            db.Key of peer.ReviewStep: key of the written review step.
        """
        COUNTER_WRITE_REVIEW_START.inc()
        try:
            step_key = cls._update_review_contents_and_change_state(
                review_step_key, review_payload, mark_completed)
        except Exception as e:
            COUNTER_WRITE_REVIEW_FAILED.inc()
            raise e

        COUNTER_WRITE_REVIEW_SUCCESS.inc()
        return step_key

    @classmethod
    @db.transactional(xg=True)
    def _update_review_contents_and_change_state(
        cls, review_step_key, review_payload, mark_completed):
        should_increment_created_new_review = False
        should_increment_updated_existing_review = False
        should_increment_assigned_to_completed = False
        should_increment_expired_to_completed = False

        step = entities.get(review_step_key)
        if not step:
            COUNTER_WRITE_REVIEW_STEP_MISS.inc()
            raise KeyError(
                'No review step found with key %s' % repr(review_step_key))
        elif step.removed:
            raise domain.RemovedError(
                'Unable to process step %s' % repr(step.key()), step.removed)
        elif mark_completed and step.state == domain.REVIEW_STATE_COMPLETED:
            raise domain.TransitionError(
                'Unable to transition step %s' % repr(step.key()),
                step.state, domain.REVIEW_STATE_COMPLETED)

        if step.review_key:
            review_to_update = entities.get(step.review_key)
            if review_to_update:
                should_increment_updated_existing_review = True
        else:
            review_to_update = student_work.Review(
                contents=review_payload, reviewee_key=step.reviewee_key,
                reviewer_key=step.reviewer_key, unit_id=step.unit_id)
            step.review_key = db.Key.from_path(
                student_work.Review.kind(),
                student_work.Review.key_name(
                    step.unit_id, step.reviewee_key, step.reviewer_key))
            should_increment_created_new_review = True

        if not review_to_update:
            COUNTER_WRITE_REVIEW_REVIEW_MISS.inc()
            raise domain.ConstraintError(
                'No review found with key %s' % repr(step.review_key))

        summary = entities.get(step.review_summary_key)
        if not summary:
            COUNTER_WRITE_REVIEW_SUMMARY_MISS.inc()
            raise domain.ConstraintError(
                'No review summary found with key %s' % repr(
                    step.review_summary_key))

        review_to_update.contents = review_payload
        updated_step_key = None
        if not mark_completed:
            # pylint: disable=unbalanced-tuple-unpacking,unpacking-non-sequence
            _, updated_step_key = entities.put([review_to_update, step])
        else:
            if step.state == domain.REVIEW_STATE_ASSIGNED:
                should_increment_assigned_to_completed = True
            elif step.state == domain.REVIEW_STATE_EXPIRED:
                should_increment_expired_to_completed = True

            summary.decrement_count(step.state)
            step.state = domain.REVIEW_STATE_COMPLETED
            summary.increment_count(step.state)

            # pylint: disable=unbalanced-tuple-unpacking,unpacking-non-sequence
            _, updated_step_key, _ = entities.put(
                [review_to_update, step, summary])

        if should_increment_created_new_review:
            COUNTER_WRITE_REVIEW_CREATED_NEW_REVIEW.inc()
        elif should_increment_updated_existing_review:
            COUNTER_WRITE_REVIEW_UPDATED_EXISTING_REVIEW.inc()

        if should_increment_assigned_to_completed:
            COUNTER_WRITE_REVIEW_COMPLETED_ASSIGNED_STEP.inc()
        elif should_increment_expired_to_completed:
            COUNTER_WRITE_REVIEW_COMPLETED_EXPIRED_STEP.inc()

        return updated_step_key


class SubmissionDataSource(data_sources.AbstractDbTableRestDataSource):

    @classmethod
    def get_name(cls):
        return 'submissions'

    @classmethod
    def get_title(cls):
        return 'Submissions'

    @classmethod
    def get_default_chunk_size(cls):
        return 100

    @classmethod
    def get_context_class(cls):
        return data_sources.DbTableContext

    @classmethod
    def exportable(cls):
        return True

    @classmethod
    def get_schema(cls, app_context, log, source_context):
        clazz = cls.get_entity_class()
        registry = entity_transforms.get_schema_for_entity(clazz)

        # User ID is not directly available in the submission; it's encoded
        # in a Key, which needs to be unpacked.
        registry.add_property(schema_fields.SchemaField(
            'user_id', 'User ID', 'string'))
        ret = registry.get_json_schema_dict()['properties']
        del ret['reviewee_key']
        return ret

    @classmethod
    def get_entity_class(cls):
        return student_work.Submission

    @classmethod
    def _postprocess_rows(cls, app_context, source_context, schema,
                          log, page_number, submissions):
        ret = super(SubmissionDataSource, cls)._postprocess_rows(
            app_context, source_context, schema, log, page_number, submissions)
        for item in ret:
            # Submission's write() method does a transforms.dumps() on
            # the inbound contents, so undo that.
            item['contents'] = transforms.loads(item['contents'])

            # Convert reviewee_key to user ID.
            item['user_id'] = db.Key(encoded=item['reviewee_key']).name()
            del item['reviewee_key']

            # Suppress item key.  It contains PII (the student ID) among other
            # things, and it's not useful for joins since it's an amalgamation.
            del item['key']
        return ret


custom_module = None


def register_module():
    """Registers this module in the registry."""

    # Avert circular dependency
    from modules.review import cron

    stats.register_analytic()

    # register this peer review implementation
    models.review.ReviewsProcessor.set_peer_matcher(Manager)

    # register cron handler
    cron_handlers = [(
        '/cron/expire_old_assigned_reviews',
        cron.ExpireOldAssignedReviewsHandler)]

    def notify_module_enabled():
        dashboard.DashboardHandler.add_sub_nav_mapping(
            'settings', 'edit_assignment', 'Peer review',
            action='edit_assignment',
            contents=review_dashboard.get_edit_assignment)

        dashboard.DashboardHandler.add_custom_post_action(
            'add_reviewer', review_dashboard.post_add_reviewer)
        dashboard.DashboardHandler.add_custom_post_action(
            'delete_reviewer', review_dashboard.post_delete_reviewer)
        data_removal.Registry.register_indexed_by_user_id_remover(
            peer.ReviewSummary.delete_by_reviewee_id)
        data_removal.Registry.register_indexed_by_user_id_remover(
            peer.ReviewStep.delete_by_reviewee_id)
        data_sources.Registry.register(SubmissionDataSource)


    global custom_module  # pylint: disable=global-statement
    custom_module = custom_modules.Module(
        'Peer Review Engine',
        'A set of classes for managing peer review process.',
        cron_handlers, [], notify_module_enabled=notify_module_enabled)
    return custom_module
