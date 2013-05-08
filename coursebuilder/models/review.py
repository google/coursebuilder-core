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

"""Review processor that is used for managing human-reviewed assessments."""

__author__ = [
    'sll@google.com (Sean Lip)',
]

from modules.review import domain
from modules.review import review

import student_work
import transforms

from google.appengine.ext import db

# Indicates that a human-graded assessment is self-graded.
SELF_MATCHER = 'self'
# Indicates that a human-graded assessment is peer-graded.
PEER_MATCHER = 'peer'

# Allowed matchers.
ALLOWED_MATCHERS = [SELF_MATCHER, PEER_MATCHER]


class ReviewsProcessor(object):
    """A class that processes review arrangements."""

    TYPE_IMPL_MAPPING = {
        PEER_MATCHER: review.Manager,
        SELF_MATCHER: None,
    }

    def __init__(self, course):
        self._course = course

    def _get_course(self):
        return self._course

    def _get_impl(self, unit_id):
        unit = self._get_course().find_unit_by_id(unit_id)
        return self.TYPE_IMPL_MAPPING[unit.workflow.get_matcher()]

    def _get_review_step_keys_by(self, unit_id, reviewer_key):
        impl = self._get_impl(unit_id)
        return impl.get_review_keys_by(str(unit_id), reviewer_key)

    def _get_submission_by_key(self, unit_id, submission_key):
        impl = self._get_impl(unit_id)
        return impl.get_submissions_by_keys([submission_key])[0]

    def add_reviewer(self, unit_id, submission_key, reviewee_key, reviewer_key):
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

    def get_reviews_by_keys(self, unit_id, review_keys):
        impl = self._get_impl(unit_id)
        reviews = impl.get_reviews_by_keys(review_keys)
        return [(transforms.loads(rev.contents) if rev else None)
                for rev in reviews]

    def get_review_steps_by_keys(self, unit_id, review_step_keys):
        impl = self._get_impl(unit_id)
        return impl.get_review_steps_by_keys(review_step_keys)

    def get_submission_and_review_step_keys(self, unit_id, reviewee_key):
        impl = self._get_impl(unit_id)
        return impl.get_submission_and_review_keys(str(unit_id), reviewee_key)

    def get_submission_contents_by_key(self, unit_id, submission_key):
        submission = self._get_submission_by_key(unit_id, submission_key)
        return transforms.loads(submission.contents) if submission else None

    def get_submission_contents(self, unit_id, reviewee_key):
        submission_key = self.get_submission_key(unit_id, reviewee_key)
        return self.get_submission_contents_by_key(unit_id, submission_key)

    def get_submission_key(self, unit_id, reviewee_key):
        return db.Key.from_path(
            student_work.Submission.kind(),
            student_work.Submission.key_name(str(unit_id), reviewee_key))

    def create_submission(self, unit_id, reviewee_key, submission_payload):
        # TODO(sll): Add error handling.
        return student_work.Submission(
            unit_id=str(unit_id), reviewee_key=reviewee_key,
            contents=transforms.dumps(submission_payload)).put()

    def does_submission_exist(self, unit_id, reviewee_key):
        submission_key = self.get_submission_key(unit_id, reviewee_key)
        return bool(db.get(submission_key))

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
    # TODO(sll): Update all docs and attribute references in this class once
    # the underlying models in review.py have been properly baked.

    @classmethod
    def get_answer_list(cls, submission):
        """Compiles a list of the student's answers from a submission."""
        if not submission:
            return []

        answer_list = []
        for item in submission:
            # Check that the indices within the submission are valid.
            assert item['index'] == len(answer_list)
            answer_list.append(item['value'])
        return answer_list

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
        cls, review_steps, review_min_count, progress_tracker):
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
            return progress_tracker.COMPLETED_STATE
        elif completed_reviews > 0:
            return progress_tracker.IN_PROGRESS_STATE
        else:
            return progress_tracker.NOT_STARTED_STATE
