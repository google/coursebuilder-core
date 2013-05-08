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

"""Models and helper utilities for the review workflow."""

__author__ = [
    'johncox@google.com (John Cox)',
    'sll@google.com (Sean Lip)',
]

import calendar
import datetime

import entities
import transforms
from google.appengine.ext import db


# For many classes we define both a _DomainObject subclass and a db.Model.
# When possible it is best to use the domain object, since db.Model carries with
# it the datastore API and allows clients to bypass business logic by making
# direct datastore calls.


class Review(entities.BaseEntity):
    """Datastore model for a student review of a Submission."""

    # Contents of the student's review. Max size is 1MB.
    contents = db.TextProperty()


class Submission(entities.BaseEntity):
    """Datastore model for a student work submission."""

    # Contents of the student submission. Max size is 1MB.
    contents = db.TextProperty()


class ReviewUtils(object):
    """A utility class for processing data relating to assessment reviews."""
    # TODO(sll): Update all docs and attribute references in this class once
    # the underlying models in review.py have been properly baked.

    @classmethod
    def has_unstarted_reviews(cls, reviews):
        """Returns whether the student has any unstarted reviews."""
        for review in reviews:
            if 'review' not in review or not review['review']:
                return True
        return False

    @classmethod
    def get_answer_list(cls, submission):
        """Compiles a list of the student's answers from a submission."""
        answer_list = []
        for item in submission:
            # Check that the indices within the submission are valid.
            assert item['index'] == len(answer_list)
            answer_list.append(item['value'])
        return answer_list

    @classmethod
    def count_completed_reviews(cls, reviews):
        """Counts the number of completed reviews in the given set."""
        count = 0
        for review in reviews:
            if 'is_draft' in review and not review['is_draft']:
                count += 1
        return count

    @classmethod
    def has_completed_all_assigned_reviews(cls, reviews):
        """Returns whether the student has completed all assigned reviews."""
        for review in reviews:
            if 'is_draft' in review and review['is_draft']:
                return False
            if 'review' not in review or not review['review']:
                return False
        return True

    @classmethod
    def has_completed_enough_reviews(cls, reviews, review_min_count):
        """Checks whether the review count is at least the minimum required."""
        return cls.count_completed_reviews(reviews) >= review_min_count

    @classmethod
    def get_review_progress(cls, reviews, review_min_count, progress_tracker):
        """Gets the progress value based on the number of reviews done.

        Args:
          reviews: a list of review objects.
          review_min_count: the minimum number of reviews that the student is
              required to complete for this assessment.
          progress_tracker: the course progress tracker.

        Returns:
          the corresponding progress value: 0 (not started), 1 (in progress) or
          2 (completed).
        """
        completed_reviews = cls.count_completed_reviews(reviews)

        if cls.has_completed_enough_reviews(reviews, review_min_count):
            return progress_tracker.COMPLETED_STATE
        elif completed_reviews > 0:
            return progress_tracker.IN_PROGRESS_STATE
        else:
            return progress_tracker.NOT_STARTED_STATE


class ReviewsProcessor(object):
    """A class that processes review arrangements."""

    def __init__(self, course):
        self._course = course

    def _get_course(self):
        return self._course

    def get_new_submission_for_review(self, reviewer, unit):
        """Returns a new submission that this reviewer can review.

        This can be overwritten by other functions that pair reviewers with
        submissions.

        Args:
          reviewer: the reviewer that needs to be assigned a new submission.
          unit: the corresponding assessment.

        Returns:
          the student to assign to this reviewer, or None if no valid
          assignments are possible.
        """
        # This implementation returns a submission with the fewest reviewers
        # assigned so far. It is not optimized.
        chosen_student_key = None
        min_reviewers_so_far = 99999

        for work_entity in StudentWorkEntity.all():
            key = work_entity.key_string
            work = transforms.loads(work_entity.data)

            student_key = key[:key.find(':')]
            unit_id = key[key.find(':') + 1:]
            if unit_id != str(unit.unit_id):
                continue
            if reviewer.key().name() in work['reviewers']:
                continue
            # Do not allow review of the reviewer's own work.
            if student_key == reviewer.key().name():
                continue

            # This piece of work is a candidate submission for this reviewer to
            # review.
            if len(work['reviewers']) < min_reviewers_so_far:
                min_reviewers_so_far = len(work['reviewers'])
                chosen_student_key = student_key

        return chosen_student_key

    def get_student_work(self, student, unit):
        """Returns a student's submission and associated reviews, or None."""
        return self._get_student_work(student, unit)

    def submit_student_work(self, student, unit, answers):
        """Puts a new student work product into the review pool."""
        self._put_student_work(student, unit, {
            'submission': answers,
            # This dict is keyed by reviewer email, with value {'review': ...}.
            'reviewers': {},
        })

    def submit_review(self, student, unit, reviewer, review_data, is_draft):
        """Handles a review submission."""
        work = self._get_student_work(student, unit)
        # Check if the reviewer has indeed been assigned to this submission.
        if work['reviewers'][reviewer.key().name()]:
            work['reviewers'][reviewer.key().name()]['review'] = review_data
            work['reviewers'][reviewer.key().name()]['is_draft'] = is_draft
        self._put_student_work(student, unit, work)

    def get_reviewer_reviews(self, reviewer, unit):
        """Gets the reviews for a given reviewer and unit."""
        reviews = []
        for work_entity in StudentWorkEntity.all():
            key = work_entity.key_string
            work = transforms.loads(work_entity.data)

            student_key = key[:key.find(':')]
            unit_id = key[key.find(':') + 1:]
            if unit_id != str(unit.unit_id):
                continue
            if reviewer.key().name() in work['reviewers']:
                reviews.append({
                    'student': student_key,
                    'submission': work['submission'],
                    'review': work['reviewers'][reviewer.key().name()].get(
                        'review'),
                    'is_draft': work['reviewers'][
                        reviewer.key().name()]['is_draft'],
                    'date_added': work['reviewers'][
                        reviewer.key().name()]['date_added'],
                })
        # Order the reviews by the time they were assigned.
        return sorted(reviews, key=lambda r: r['date_added'])

    def add_reviewer(self, student, unit, new_reviewer):
        """Adds a reviewer to a student submission."""
        work = self.get_student_work(student, unit)
        work['reviewers'][new_reviewer.key().name()] = {
            'review': None, 'is_draft': True,
            'date_added': calendar.timegm(
                datetime.datetime.utcnow().timetuple())}
        self._put_student_work(student, unit, work)

    def delete_reviewer(self, student, unit, reviewer_to_delete):
        """Removes a reviewer from a student submission."""
        work = self.get_student_work(student, unit)
        del work['reviewers'][reviewer_to_delete.key().name()]
        self._put_student_work(student, unit, work)

    def _get_student_work(self, student, unit):
        key = ':'.join([student.key().name(), str(unit.unit_id)])
        work_entity = StudentWorkEntity.get_by_key_name(key)
        return transforms.loads(work_entity.data) if work_entity else None

    def _put_student_work(self, student, unit, work):
        key = ':'.join([student.key().name(), str(unit.unit_id)])
        answers = StudentWorkEntity.get_by_key_name(key)
        if not answers:
            answers = StudentWorkEntity(key_name=key, key_string=key)
        answers.updated_on = datetime.datetime.now()
        answers.data = transforms.dumps(work)
        answers.put()


class StudentWorkEntity(entities.BaseEntity):
    """Student work for human-reviewed assignments."""

    updated_on = db.DateTimeProperty(indexed=True)

    key_string = db.StringProperty(required=True)
    # Each of the following is a string representation of a JSON dict.
    data = db.TextProperty(indexed=False)
