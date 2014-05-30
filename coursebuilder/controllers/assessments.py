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

"""Classes and methods to manage all aspects of student assessments."""

__author__ = 'pgbovine@google.com (Philip Guo)'

import datetime
import logging

from utils import BaseHandler
from utils import HUMAN_READABLE_DATETIME_FORMAT

from controllers import lessons
from models import courses
from models import models
from models import review
from models import student_work
from models import transforms
from models import utils
from models.models import Student
from models.models import StudentAnswersEntity
from tools import verify

from google.appengine.ext import db


def store_score(course, student, assessment_type, score):
    """Stores a student's score on a particular assessment.

    Args:
        course: the course containing the assessment.
        student: the student whose data is stored.
        assessment_type: the type of the assessment.
        score: the student's score on this assessment.

    Returns:
        the result of the assessment, if appropriate.
    """
    # FIXME: Course creators can edit this code to implement custom
    # assessment scoring and storage behavior
    # TODO(pgbovine): Note that the latest version of answers are always saved,
    # but scores are only saved if they're higher than the previous attempt.
    # This can lead to unexpected analytics behavior. Resolve this.
    existing_score = course.get_score(student, assessment_type)
    # remember to cast to int for comparison
    if (existing_score is None) or (score > int(existing_score)):
        utils.set_score(student, assessment_type, score)


class AnswerHandler(BaseHandler):
    """Handler for saving assessment answers."""

    # Find student entity and save answers
    @db.transactional(xg=True)
    def update_assessment_transaction(
        self, email, assessment_type, new_answers, score):
        """Stores answer and updates user scores.

        Args:
            email: the student's email address.
            assessment_type: the title of the assessment.
            new_answers: the latest set of answers supplied by the student.
            score: the numerical assessment score.

        Returns:
            the student instance.
        """
        student = Student.get_enrolled_student_by_email(email)
        course = self.get_course()

        # It may be that old Student entities don't have user_id set; fix it.
        if not student.user_id:
            student.user_id = self.get_user().user_id()

        answers = StudentAnswersEntity.get_by_key_name(student.user_id)
        if not answers:
            answers = StudentAnswersEntity(key_name=student.user_id)
        answers.updated_on = datetime.datetime.now()

        utils.set_answer(answers, assessment_type, new_answers)

        store_score(course, student, assessment_type, score)

        student.put()
        answers.put()

        # Also record the event, which is useful for tracking multiple
        # submissions and history.
        models.EventEntity.record(
            'submit-assessment', self.get_user(), transforms.dumps({
                'type': 'assessment-%s' % assessment_type,
                'values': new_answers, 'location': 'AnswerHandler'}))

        return student

    def get(self):
        """Handles GET requests.

        This method is here because if a student logs out when on the
        reviewed_assessment_confirmation page, that student is redirected to
        the GET method of the corresponding handler. It might be a good idea to
        merge this class with lessons.AssessmentHandler, which currently only
        has a GET handler.
        """
        self.redirect('/course')

    # pylint: disable-msg=too-many-statements
    def post(self):
        """Handles POST requests."""
        student = self.personalize_page_and_get_enrolled()
        if not student:
            return

        if not self.assert_xsrf_token_or_fail(self.request, 'assessment-post'):
            return

        course = self.get_course()
        assessment_type = self.request.get('assessment_type')
        if not assessment_type:
            self.error(404)
            logging.error('No assessment type supplied.')
            return

        unit = course.find_unit_by_id(assessment_type)
        if unit is None or unit.type != verify.UNIT_TYPE_ASSESSMENT:
            self.error(404)
            logging.error('No assessment named %s exists.', assessment_type)
            return

        self.template_value['navbar'] = {'course': True}
        self.template_value['assessment'] = assessment_type
        self.template_value['assessment_name'] = unit.title
        self.template_value['is_last_assessment'] = (
            course.is_last_assessment(unit))
        self.template_value['unit_id'] = unit.unit_id

        # Convert answers from JSON to dict.
        answers = self.request.get('answers')
        answers = transforms.loads(answers) if answers else []

        grader = unit.workflow.get_grader()

        # Scores are not recorded for human-reviewed assignments.
        score = 0
        if grader == courses.AUTO_GRADER:
            score = int(round(float(self.request.get('score'))))

        # Record assessment transaction.
        student = self.update_assessment_transaction(
            student.key().name(), assessment_type, answers, score)

        if grader == courses.HUMAN_GRADER:
            rp = course.get_reviews_processor()

            # Guard against duplicate submissions of a human-graded assessment.
            previously_submitted = rp.does_submission_exist(
                unit.unit_id, student.get_key())

            if not previously_submitted:
                # Check that the submission due date has not passed.
                time_now = datetime.datetime.now()
                submission_due_date = unit.workflow.get_submission_due_date()
                if time_now > submission_due_date:
                    self.template_value['time_now'] = time_now.strftime(
                        HUMAN_READABLE_DATETIME_FORMAT)
                    self.template_value['submission_due_date'] = (
                        submission_due_date.strftime(
                            HUMAN_READABLE_DATETIME_FORMAT))
                    self.template_value['error_code'] = (
                        'assignment_deadline_exceeded')
                    self.render('error.html')
                    return

                submission_key = student_work.Submission.write(
                    unit.unit_id, student.get_key(), answers)
                rp.start_review_process_for(
                    unit.unit_id, submission_key, student.get_key())
                # Record completion event in progress tracker.
                course.get_progress_tracker().put_assessment_completed(
                    student, assessment_type)

            self.template_value['previously_submitted'] = previously_submitted

            matcher = unit.workflow.get_matcher()
            self.template_value['matcher'] = matcher
            if matcher == review.PEER_MATCHER:
                self.template_value['review_dashboard_url'] = (
                    'reviewdashboard?unit=%s' % unit.unit_id
                )

            self.render('reviewed_assessment_confirmation.html')
            return
        else:
            # Record completion event in progress tracker.
            course.get_progress_tracker().put_assessment_completed(
                student, assessment_type)

            # Save the submission in the datastore, overwriting the earlier
            # version if it exists.
            submission_key = student_work.Submission.write(
                unit.unit_id, student.get_key(), answers)
            course.update_final_grades(student)

            parent_unit = course.get_parent_unit(unit.unit_id)
            if parent_unit:
                unit_contents = lessons.UnitHandler.UnitLeftNavElements(
                    course, parent_unit)
                next_url = unit_contents.get_url_by(
                    'assessment', unit.unit_id, 0) + '&confirmation'
                self.redirect('/' + next_url)
            else:
                self.template_value['result'] = course.get_overall_result(
                    student)
                self.template_value['score'] = score
                self.template_value['overall_score'] = course.get_overall_score(
                    student)
                self.render('test_confirmation.html')
