# Copyright 2012 Google Inc. All Rights Reserved.
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

"""Review processor that is used for managing peer-reviewed assessments."""

__author__ = [
    'sll@google.com (Sean Lip)',
]

import entities
import progress
import student_work
import transforms

from modules.review import domain

# Indicates that a human-graded assessment is peer-graded.
PEER_MATCHER = 'peer'

# Allowed matchers.
ALLOWED_MATCHERS = [PEER_MATCHER]


class ReviewsProcessor(object):
    """A class that processes review arrangements."""

    TYPE_IMPL_MAPPING = {
        PEER_MATCHER: None,
    }

    @classmethod
    def set_peer_matcher(cls, matcher):
        cls.TYPE_IMPL_MAPPING[PEER_MATCHER] = matcher

    def __init__(self, course):
        self._course = course

    def _get_course(self):
        return self._course

    def _get_impl(self, unit_id):
        unit = self._get_course().find_unit_by_id(unit_id)
        return self.TYPE_IMPL_MAPPING[unit.workflow.get_matcher()]

    def _get_review_step_keys_by(self, unit_id, reviewer_key):
        impl = self._get_impl(unit_id)
        return impl.get_review_step_keys_by(str(unit_id), reviewer_key)

    def _get_submission_and_review_step_keys(self, unit_id, reviewee_key):
        impl = self._get_impl(unit_id)
        return impl.get_submission_and_review_step_keys(
            str(unit_id), reviewee_key)

    def add_reviewer(self, unit_id, reviewee_key, reviewer_key):
        submission_key = student_work.Submission.get_key(unit_id, reviewee_key)
        impl = self._get_impl(unit_id)
        return impl.add_reviewer(
            str(unit_id), submission_key, reviewee_key, reviewer_key)

    def delete_reviewer(self, unit_id, review_step_key):
        impl = self._get_impl(unit_id)
        return impl.delete_reviewer(review_step_key)

    def get_new_review(self, unit_id, reviewer_key):
        impl = self._get_impl(unit_id)
        return impl.get_new_review(str(unit_id), reviewer_key)

    def get_review_steps_by(self, unit_id, reviewer_key):
        review_step_keys = self._get_review_step_keys_by(unit_id, reviewer_key)
        return self.get_review_steps_by_keys(unit_id, review_step_keys)

    def get_reviews_by_keys(
        self, unit_id, review_keys, handle_empty_keys=False):
        """Gets a list of reviews, given their review keys.

        If handle_empty_keys is True, then no error is thrown on supplied keys
        that are None; the elements in the result list corresponding to those
        keys simply return None. This usually arises when this method is called
        immediately after get_review_steps_by_keys().

        Args:
            unit_id: string. Id of the unit to get the reviews for.
            review_keys: [db.Key of peer.ReviewStep]. May include None, if
                handle_empty_keys is True.
            handle_empty_keys: if True, the return value contains None for keys
                that are None. If False, the method throws if empty keys are
                supplied.

        Returns:
            List with the same number of elements as review_keys. It contains:
            - the JSON-decoded contents of the review corresponding to that
                review_key, or
            - None if either:
              - no review has been submitted for that review key, or
              - handle_empty_keys == True and the review_key is None.
        """
        impl = self._get_impl(unit_id)
        reviews = []
        if not handle_empty_keys:
            reviews = impl.get_reviews_by_keys(review_keys)
        else:
            nonempty_review_indices = []
            nonempty_review_keys = []
            for idx, review_key in enumerate(review_keys):
                if review_key is not None:
                    nonempty_review_indices.append(idx)
                    nonempty_review_keys.append(review_key)

            tmp_reviews = impl.get_reviews_by_keys(nonempty_review_keys)
            reviews = [None] * len(review_keys)
            for (i, idx) in enumerate(nonempty_review_indices):
                reviews[idx] = tmp_reviews[i]

        return [(transforms.loads(rev.contents) if rev else None)
                for rev in reviews]

    def get_review_steps_by_keys(self, unit_id, review_step_keys):
        impl = self._get_impl(unit_id)
        return impl.get_review_steps_by_keys(review_step_keys)

    def get_submission_and_review_steps(self, unit_id, reviewee_key):
        """Gets the submission and a list of review steps for a unit/reviewee.

        Note that review steps marked removed are included in the result set.

        Args:
            unit_id: string. Id of the unit to get the data for.
            reviewee_key: db.Key of models.models.Student. The student to get
                the data for.

        Returns:
            - None if no submission was found for the given unit_id,
                reviewee_key pair.
            - (Object, [peer.ReviewStep]) otherwise. The first element is the
                de-JSONified content of the reviewee's submission. The second
                element is a list of review steps for this submission, sorted
                by creation date.
        """

        submission_and_review_step_keys = (
            self._get_submission_and_review_step_keys(unit_id, reviewee_key))
        if submission_and_review_step_keys is None:
            return None

        submission_contents = student_work.Submission.get_contents_by_key(
            submission_and_review_step_keys[0])
        review_step_keys = submission_and_review_step_keys[1]
        sorted_review_steps = sorted(
            self.get_review_steps_by_keys(unit_id, review_step_keys),
            key=lambda r: r.create_date)
        return [submission_contents, sorted_review_steps]

    def does_submission_exist(self, unit_id, reviewee_key):
        submission_key = student_work.Submission.get_key(unit_id, reviewee_key)
        return bool(entities.get(submission_key))

    def start_review_process_for(self, unit_id, submission_key, reviewee_key):
        impl = self._get_impl(unit_id)
        return impl.start_review_process_for(
            str(unit_id), submission_key, reviewee_key)

    def write_review(
        self, unit_id, review_step_key, review_payload, mark_completed):
        impl = self._get_impl(unit_id)
        return impl.write_review(
            review_step_key, transforms.dumps(review_payload),
            mark_completed=mark_completed)


class ReviewUtils(object):
    """A utility class for processing data relating to assessment reviews."""

    @classmethod
    def count_completed_reviews(cls, review_steps):
        """Counts the number of completed reviews in the given set."""
        count = 0
        for review_step in review_steps:
            if review_step.state == domain.REVIEW_STATE_COMPLETED:
                count += 1
        return count

    @classmethod
    def has_completed_all_assigned_reviews(cls, review_steps):
        """Returns whether the student has completed all assigned reviews."""
        for review_step in review_steps:
            if review_step.state != domain.REVIEW_STATE_COMPLETED:
                return False
        return True

    @classmethod
    def has_completed_enough_reviews(cls, reviews, review_min_count):
        """Checks whether the review count is at least the minimum required."""
        return cls.count_completed_reviews(reviews) >= review_min_count

    @classmethod
    def get_review_progress(
        cls, review_steps, review_min_count):
        """Gets the progress value based on the number of reviews done.

        Args:
          review_steps: a list of ReviewStep objects.
          review_min_count: the minimum number of reviews that the student is
              required to complete for this assessment.
          progress_tracker: the course progress tracker.

        Returns:
          the corresponding progress value: 0 (not started), 1 (in progress) or
          2 (completed).
        """
        completed_reviews = cls.count_completed_reviews(review_steps)

        if cls.has_completed_enough_reviews(review_steps, review_min_count):
            return progress.UnitLessonCompletionTracker.COMPLETED_STATE
        elif len(review_steps) > 0:
            return progress.UnitLessonCompletionTracker.IN_PROGRESS_STATE
        else:
            return progress.UnitLessonCompletionTracker.NOT_STARTED_STATE
