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

import logging

from models import utils
from models.models import Student

from utils import BaseHandler

from google.appengine.api import users
from google.appengine.ext import db


def store_assessment_data(student, assessment_type, score, answer):
    """Stores a student's assessment data.

    Args:
        student: the student whose data is stored.
        assessment_type: the type of the assessment.
        score: the student's score on this assessment.
        answer: the list of the student's answers on this assessment.

    Returns:
        the (possibly modified) assessment_type, which the caller can
        use to render an appropriate response page.
    """
    # FIXME: Course creators can edit this code to implement custom
    # assessment scoring and storage behavior
    # TODO(pgbovine): Note that the latest version of answers are always saved,
    # but scores are only saved if they're higher than the previous attempt.
    # This can lead to unexpected analytics behavior. Resolve this.
    utils.set_answer(student, assessment_type, answer)
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
    @db.transactional
    def store_assessment_transaction(self, email, original_type, answer):
        student = Student.get_by_email(email)

        # TODO(pgbovine): consider storing as float for better precision
        score = int(round(float(self.request.get('score'))))
        assessment_type = store_assessment_data(
            student, original_type, score, answer)
        student.put()
        return (student, assessment_type)

    def post(self):
        """Handles POST requests."""
        user = self.personalize_page_and_get_user()
        if not user:
            self.redirect(users.create_login_url(self.request.uri))
            return

        # Read in answers
        # TODO(sll): Add error-handling for when self.request.POST.items() is
        # empty or mis-formatted.
        answer = [[str(item[0]), str(item[1])] for item in
                  self.request.POST.items()]
        original_type = self.request.get('assessment_type')

        # Check for enrollment status
        student = Student.get_by_email(user.email())
        if student and student.is_enrolled:
            # Log answer submission
            logging.info('%s: %s', student.key().name(), answer)

            (student, assessment_type) = self.store_assessment_transaction(
                student.key().name(), original_type, answer)

            # Serve the confirmation page
            self.template_value['navbar'] = {'course': True}
            self.template_value['assessment'] = assessment_type
            self.template_value['student_score'] = utils.get_score(
                student, 'overall_score')
            self.render('test_confirmation.html')
        else:
            self.redirect('/register')
