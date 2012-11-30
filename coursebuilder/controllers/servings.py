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
# @author: psimakov@google.com (Pavel Simakov)


import logging, json
import lessons, utils
from models.models import Student
from utils import StudentHandler


"""
Handler for serving course page
"""
class CourseHandler(StudentHandler):

  def get(self):
    student = self.getEnrolledStudent()
    if student:
      page = self.getOrCreatePage('course_page', lessons.CourseHandler())
      self.serve(page, student.key().name(), None)
    else:
      self.redirect('/register')


"""
Handler for serving class page
"""
class UnitHandler(StudentHandler):

  def get(self):
    # Extract incoming args
    c = self.request.get('unit')
    if not c:
      class_id = 1
    else:
      class_id = int(c)

    l = self.request.get('lesson')
    if not l:
      lesson_id = 1
    else:
      lesson_id = int(l)

    # Check for enrollment status
    student = self.getEnrolledStudent()
    if student:
      page = self.getOrCreatePage(
          'lesson%s%s_page' % (class_id, lesson_id), lessons.UnitHandler())
      self.serve(page, student.key().name(), None)
    else:
      self.redirect('/register')


"""
Handler for serving activity page
"""
class ActivityHandler(StudentHandler):

  def get(self):
    # Extract incoming args
    c = self.request.get('unit')
    if not c:
      class_id = 1
    else:
      class_id = int(c)

    l = self.request.get('lesson')
    if not l:
      lesson_id = 1
    else:
      lesson_id = int(l)

    # Check for enrollment status
    student = self.getEnrolledStudent()
    if student:
      page = self.getOrCreatePage(
          'activity' + str(class_id) + str(lesson_id) + '_page', lessons.ActivityHandler()) 
      self.serve(page, student.key().name(), None)
    else:
      self.redirect('/register')


"""
Handler for serving assessment page
"""
class AssessmentHandler(StudentHandler):

  def get(self):
    # Extract incoming args
    n = self.request.get('name')
    if not n:
      n = 'Pre'
    name = n

    # Check for enrollment status
    student = self.getEnrolledStudent()
    if student:
      page = self.getOrCreatePage(
          'assessment' + name + '_page', lessons.AssessmentHandler())
      self.serve(page, student.key().name(), None)
    else:
      self.redirect('/register')


"""
Handler for serving forum page
"""
class ForumHandler(StudentHandler):

  def get(self):
    # Check for enrollment status
    student = self.getEnrolledStudent()
    if student:
      page = self.getOrCreatePage('forum_page', utils.ForumHandler()) 
      self.serve(page, student.key().name(), None)
    else:
      self.redirect('/register')


"""
Handler for saving assessment answers
"""
class AnswerHandler(StudentHandler):

  def post(self):
    # Read in answers
    answer = json.dumps(self.request.POST.items())
    type = self.request.get('assessment_type')

    # Check for enrollment status
    student = self.getEnrolledStudent()
    if student:
      # Log answer submission
      logging.info(student.key().name() + ':' + answer)

      # Find student entity and save answers
      student = Student.get_by_email(student.key().name())

      score = self.request.get('score')
      score = round(float(score))

      if type == 'precourse':
        # Save precourse_score, if it's higher than existing precourse_score
        if not student.precourse_score or int(score) > student.precourse_score:
          student.precourse_score = int(score)
        student.precourse_answer = answer
      elif type == 'midcourse':
        # Save midterm_score, if it's higher than existing midterm_score
        if not student.midterm_score or int(score) > student.midterm_score:
          student.midterm_score = int(score)
        student.midterm_answer = answer
      elif type == 'postcourse':
        student.final_answer = answer
        # Save final_score, if it's higher than existing final_score
        if not student.final_score or int(score) > student.final_score:
          student.final_score = int(float(score))
          if not student.midterm_score:
            student.midterm_score = 0

          # Calculate overall score based on a formula
          student.overall_score = int((0.30*student.midterm_score) +
                                      (0.70*student.final_score))

        if student.overall_score >= 70:
          type = 'postcourse_pass'
        else:
          type = 'postcourse_fail'
        student.final_answer = answer
      student.put()

      # Serve the confirmation page
      page = self.getOrCreatePage(
          type + 'confirmation_page', utils.AnswerHandler(type)) 
      self.serve(page, student.key().name(), str(student.overall_score))
    else:
      self.redirect('/register')
