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
#
# @author: pgbovine@google.com (Philip Guo)


"""Classes and methods to manage all aspects of student assessments."""

import json, logging
from models.models import Student
from models.utils import *
from utils import BaseHandler
from google.appengine.api import users
from google.appengine.ext import db


# Stores the assessment data in the student database entry
# and returns the (possibly-modified) assessment type,
# which the caller can use to render an appropriate response page.
#
# (caller must call student.put() to commit)
#
# FIXME: Course creators can edit this code to implement
#        custom assessment scoring and storage behavior
def storeAssessmentData(student, assessment_type, score, answer):
  # TODO: Note that the latest version of answers are always saved,
  # but scores are only saved if they're higher than the previous
  # attempt.  This can lead to unexpected analytics behavior, so we
  # should resolve this somehow.
  setAnswer(student, assessment_type, answer)
  existing_score = getScore(student, assessment_type)
  # remember to cast to int for comparison
  if (existing_score is None) or (score > int(existing_score)):
    setScore(student, assessment_type, score)

  # special handling for computing final score:
  if assessment_type == 'postcourse':
    midcourse_score = getScore(student, 'midcourse')
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
    overall_score = int((0.30*midcourse_score) + (0.70*postcourse_score))

    # TODO: this changing of assessment_type is ugly ...
    if overall_score >= 70:
      assessment_type = 'postcourse_pass'
    else:
      assessment_type = 'postcourse_fail'
    setScore(student, 'overall_score', overall_score)

  return assessment_type


"""
Handler for saving assessment answers
"""
class AnswerHandler(BaseHandler):

  # Find student entity and save answers
  @db.transactional
  def storeAssessmentTransaction(self, email, original_type, answer):
    student = Student.get_by_email(email)

    # TODO: considering storing as float for better precision
    score = int(round(float(self.request.get('score'))))
    assessment_type = storeAssessmentData(student, original_type, score, answer)
    student.put()
    return (student, assessment_type)

  def post(self):
    user = self.personalizePageAndGetUser()
    if not user:
      self.redirect(users.create_login_url(self.request.uri))
      return
    
    # Read in answers
    answer = json.dumps(self.request.POST.items())
    original_type = self.request.get('assessment_type')

    # Check for enrollment status
    student = Student.get_by_email(user.email())
    if student and student.is_enrolled:
      # Log answer submission
      logging.info(student.key().name() + ':' + answer)

      (student, assessment_type) = self.storeAssessmentTransaction(student.key().name(), original_type, answer)

      # Serve the confirmation page
      self.templateValue['navbar'] = {'course': True}
      self.templateValue['assessment'] = assessment_type
      self.templateValue['student_score'] = getScore(student, 'overall_score')
      self.render('test_confirmation.html')
    else:
      self.redirect('/register')

