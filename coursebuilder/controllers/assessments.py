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
import json
from models import models
from models import utils
from models.models import Student
from models.models import StudentAnswersEntity
from utils import BaseHandler
from google.appengine.ext import db


def store_score(student, assessment_type, score):
    """Stores a student's score on a particular assessment.

    Args:
        student: the student whose data is stored.
        assessment_type: the type of the assessment.
        score: the student's score on this assessment.

    Returns:
        the (possibly modified) assessment_type, which the caller can
        use to render an appropriate response page.
    """
    # FIXME: Course creators can edit this code to implement custom
    # assessment scoring and storage behavior
    # TODO(pgbovine): Note that the latest version of answers are always saved,
    # but scores are only saved if they're higher than the previous attempt.
    # This can lead to unexpected analytics behavior. Resolve this.
    existing_score = utils.get_score(student, assessment_type)
    # remember to cast to int for comparison
    if (existing_score is None) or (score > int(existing_score)):
        utils.set_score(student, assessment_type, score)

    # special handling for computing final score:
    if assessment_type == 'postcourse':
        midcourse_score = utils.get_score(student, 'midcourse')
        if midcourse_score is None:
            midcourse_score = 0
        else:
            midcourse_score = int(midcourse_score)

        if existing_score is None:
            postcourse_score = score
        else:
            postcourse_score = int(existing_score)
            if score > postcourse_score:
                postcourse_score = score

        # Calculate overall score based on a formula
        overall_score = int((0.3 * midcourse_score) + (0.7 * postcourse_score))

        # TODO(pgbovine): this changing of assessment_type is ugly ...
        if overall_score >= 70:
            assessment_type = 'postcourse_pass'
        else:
            assessment_type = 'postcourse_fail'
        utils.set_score(student, 'overall_score', overall_score)

    return assessment_type


class AnswerHandler(BaseHandler):
    """Handler for saving assessment answers."""

    # Find student entity and save answers
    @db.transactional(xg=True)
    def update_assessment_transaction(
        self, email, assessment_type, new_answers, score):
        """Stores answer and updates user scores."""
        student = Student.get_by_email(email)

        # It may be that old Student entities don't have user_id set; fix it.
        if not student.user_id:
            student.user_id = self.get_user().user_id()

        answers = StudentAnswersEntity.get_by_key_name(student.user_id)
        if not answers:
            answers = StudentAnswersEntity(key_name=student.user_id)
        answers.updated_on = datetime.datetime.now()

        utils.set_answer(answers, assessment_type, new_answers)

        assessment_type = store_score(student, assessment_type, score)

        student.put()
        answers.put()

        # Also record the event, which is useful for tracking multiple
        # submissions and history.
        models.EventEntity.record(
            'submit-assessment', self.get_user(), json.dumps({
                'type': 'assessment-%s' % assessment_type,
                'values': new_answers, 'location': 'AnswerHandler'}))

        return (student, assessment_type)

    def post(self):
        """Handles POST requests."""
        student = self.personalize_page_and_get_enrolled()
        if not student:
            return

        if not self.assert_xsrf_token_or_fail(self.request, 'assessment-post'):
            return

        assessment_type = self.request.get('assessment_type')

        # Convert answers from JSON to dict.
        answers = self.request.get('answers')
        if answers:
            answers = json.loads(answers)
        else:
            answers = []

        # TODO(pgbovine): consider storing as float for better precision
        score = int(round(float(self.request.get('score'))))

        # Record score.
        (student, assessment_type) = self.update_assessment_transaction(
            student.key().name(), assessment_type, answers, score)

        self.template_value['navbar'] = {'course': True}
        self.template_value['assessment'] = assessment_type
        self.template_value['student_score'] = utils.get_score(
            student, 'overall_score')
        self.render('test_confirmation.html')
