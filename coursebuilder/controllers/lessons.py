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

import logging, json

from google.appengine.api import users, memcache

from utils import StudentHandler
from models.models import Student, Unit, Lesson

"""
Handler for course page
"""
class CourseHandler(StudentHandler):

  def get(self):
    # Check for enrollment status
      student = self.getStudent()
      if student:

        # Get unit data and set template values
        units = memcache.get('units')
        if units is None:
          units = Unit.all().order('id')
          memcache.add('units', units)
        self.templateValue['units'] = units

        # Set template values for nav bar
        navbar = {'course': True}
        self.templateValue['navbar'] = navbar

        # Set template values for user
        user = users.get_current_user()
        if user:
          self.templateValue['email'] = user.email()
          self.templateValue['logoutUrl'] = users.create_logout_url("/")

        # Render course page
        self.render('course.html')
      else:
        self.redirect('/register')

"""
Handler for unit page
"""
class UnitHandler(StudentHandler):

  def get(self):
    # Check for enrollment status
      student = self.getStudent()
      if student:

        # Extract incoming args
        c = self.request.get("unit")
        if not c:
          unit_id = 1
        else:
          unit_id = int(c)
        self.templateValue['unit_id'] = unit_id

        l = self.request.get("lesson")
        if not l:
          lesson_id = 1
        else:
          lesson_id = int(l)
        self.templateValue['lesson_id'] = lesson_id

        # Set template values for a unit and its lesson entities
        units = memcache.get('units')
        if units is None:
          units = Unit.all().order('id')
          memcache.add('units', units)
        for unit in units:
          if unit.unit_id == str(unit_id):
            self.templateValue['units'] = unit

        lessons = memcache.get('lessons' + str(unit_id))
        if lessons is None:
          lessons = Lesson.all().filter('unit_id =', unit_id).order('id')
          memcache.add('lessons' + str(unit_id), lessons)
        self.templateValue['lessons'] = lessons

        # Set template values for nav bar
        navbar = {'course':True}
        self.templateValue['navbar'] = navbar

        # Set template values for back and next nav buttons
        if lesson_id == 1:
          self.templateValue['back_button_url'] = ''
          if lessons[lesson_id - 1].activity:
            self.templateValue['next_button_url'] = '/activity?unit=' + str(unit_id) + '&lesson=' + str(lesson_id)
          else:
            self.templateValue['next_button_url'] = '/unit?unit=' + str(unit_id) + '&lesson=' + str(lesson_id + 1)
        elif lesson_id == lessons.count():
          if lessons[lesson_id - 2].activity:
            self.templateValue['back_button_url'] = '/activity?unit=' + str(unit_id) + '&lesson=' + str(lesson_id - 1)
          else:
            self.templateValue['back_button_url'] = '/unit?unit=' + str(unit_id) + '&lesson=' + str(lesson_id - 1)
          if lessons[lesson_id - 1].activity:
            self.templateValue['next_button_url'] = '/activity?unit=' + str(unit_id) + '&lesson=' + str(lesson_id)
          else:
            self.templateValue['next_button_url'] = ''
        else:
          if lessons[lesson_id - 2].activity:
            self.templateValue['back_button_url'] = '/activity?unit=' + str(unit_id) + '&lesson=' + str(lesson_id - 1)
          else:
            self.templateValue['back_button_url'] = '/unit?unit=' + str(unit_id) + '&lesson=' + str(lesson_id - 1)
          if lessons[lesson_id - 1].activity:
            self.templateValue['next_button_url'] = '/activity?unit=' + str(unit_id) + '&lesson=' + str(lesson_id)
          else:
            self.templateValue['next_button_url'] = '/unit?unit=' + str(unit_id) + '&lesson=' + str(lesson_id + 1)

        # Set template values for user
        user = users.get_current_user()
        if user:
          self.templateValue['email'] = user.email()
          self.templateValue['logoutUrl'] = users.create_logout_url("/")

        # Render unit page with all lessons in tabs
        self.render('unit.html')
      else:
        self.redirect('/register')


"""
Handler for activity page.
"""
class ActivityHandler(StudentHandler):
  def get(self):
    # Check for enrollment status
      student = self.getStudent()
      if student:

        # Extract incoming args
        c = self.request.get("unit")
        if not c:
          unit_id = 1
        else:
          unit_id = int(c)

        self.templateValue['unit_id'] = unit_id
        l = self.request.get('lesson')
        if not l:
          lesson_id = 1
        else:
          lesson_id = int(l)
        self.templateValue['lesson_id'] = lesson_id

        # Set template values for a unit and its lesson entities
        units = memcache.get('units')
        if units is None:
          units = Unit.all().order('id')
          memcache.add('units', units)
        for unit in units:
          if unit.unit_id == unit_id:
            self.templateValue['units'] = unit

        lessons = memcache.get('lessons' + str(unit_id))
        if lessons is None:
          lessons = Lesson.all().filter('unit_id =', unit_id).order('id')
          memcache.add('lessons' + str(unit_id), lessons)
        self.templateValue['lessons'] = lessons

        # Set template values for nav-x bar
        navbar = {'course':True}
        self.templateValue['navbar'] = navbar

        # Set template values for back and next nav buttons
        self.templateValue['back_button_url'] = '/unit?unit=' + str(unit_id) + '&lesson=' + str(lesson_id)
        if lesson_id == lessons.count():
          self.templateValue['next_button_url'] = ''
        else:
          self.templateValue['next_button_url'] = '/unit?unit=' + str(unit_id) + '&lesson=' + str(lesson_id + 1)

        # Set template values for user
        user = users.get_current_user()
        if user:
          self.templateValue['email'] = user.email()
          self.templateValue['logoutUrl'] = users.create_logout_url("/")

        # Render activity page
        self.render('activity.html')
      else:
        self.redirect('/register')


"""
Handler for assessment page
"""
class AssessmentHandler(StudentHandler):

  def get(self):
    # Check for enrollment status
      student = self.getStudent()
      if student:

        # Extract incoming args
        n = self.request.get("name")
        if not n:
          n = 'Pre'
        self.templateValue['name'] = n

        # Set template values for nav-x bar
        navbar = {'course':True}
        self.templateValue['navbar'] = navbar

        # Set template values for user
        user = users.get_current_user()
        if user:
          self.templateValue['email'] = user.email()
          self.templateValue['logoutUrl'] = users.create_logout_url("/")

        # Render assessment page
        self.render('assessment.html')
      else:
        self.redirect('/register')


"""
Handler for saving assessment answers
"""
class AnswerHandler(StudentHandler):

  def post(self):
    # Read in answers
    answer = json.dumps(self.request.POST.items())

    assessment_type = self.request.get('assessment_type')
    num_correct = self.request.get('num_correct')
    num_questions = self.request.get('num_questions')

    # Check for enrollment status
    student = self.getStudent()
    if student:
      logging.info(student.key().name() + ':' + answer)

      # Find student entity and save answers
      student = Student.get_by_key_name(student.key().name().encode('utf8'))

      # FIXME: Currently the demonstration course is hardcoded to have
      # three assessments: 'precourse', 'midcourse', and 'postcourse'.
      # If you would like to have different types of assessments or
      # different score weights/thresholds, edit the code below ...
      if assessment_type == 'precourse':
        score = self.request.get('score')
        student.precourse_answer = answer
        student.precourse_score = int(float(score))
      elif assessment_type == 'midcourse':
        score = self.request.get('score')
        student.midterm_answer = answer
        student.midterm_score = int(float(score))
      elif assessment_type == 'postcourse':
        score = self.request.get('score')
        student.final_answer = answer
        student.final_score = int(float(score))
        if not student.midterm_score:
          student.midterm_score = 0
        student.overall_score = int((0.35 * student.midterm_score) + (0.65 * student.final_score))
        self.templateValue['score'] = student.overall_score
        if student.overall_score >= 70:
          assessment_type = 'postcourse_pass'
        else:
          assessment_type = 'postcourse_fail'
      student.put()

      # Update student entity in memcache
      memcache.set(student.key().name(), student)

      # Set template values for nav-x bar
      navbar = {'course':True}
      self.templateValue['navbar'] = navbar

      # Set template values for user
      user = users.get_current_user()
      if user:
        self.templateValue['email'] = user.email()
        self.templateValue['logoutUrl'] = users.create_logout_url("/")

      # Render confirmation page
      self.templateValue['assessment'] = assessment_type
      self.render('test_confirmation.html')
    else:
      self.redirect('/register')
