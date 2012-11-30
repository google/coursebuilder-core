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
from models.models import Student, PageCache
from utils import StudentHandler
from google.appengine.api import memcache


"""
Handler for serving course page
"""
class CourseHandler(StudentHandler):

  def get(self):
    # Check for enrollment status
    student = self.getStudent()
    if student:
      # Serve the course page from memcache if possible, other from datastore
      page_name = 'course_page'
      cached_page = memcache.get(page_name)
      if not cached_page:
        logging.info('cache miss: ' + page_name)
        page = PageCache.get_by_key_name(page_name)
        if page:
          memcache.add(page_name, page.content)
          cached_page = page.content
        else:
          cached_page = self.delegateTo(lessons.CourseHandler())

      self.serve(cached_page, student.key().name(), None)
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
    student = self.getStudent()
    if student:
      # Serve the lesson page from memcache if possible, other from datastore
      page_name = 'lesson%s%s_page' % (class_id, lesson_id)
      cached_page = memcache.get(page_name)
      if not cached_page:
        logging.info('cache miss: ' + page_name)
        page = PageCache.get_by_key_name(page_name)
        if page:
          memcache.add(page_name, page.content)
          cached_page = page.content
        else:
          cached_page = self.delegateTo(lessons.UnitHandler())

      self.serve(cached_page, student.key().name(), None)
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
    student = self.getStudent()
    if student:
      # Serve the activity page from memcache if possible, other from datastore
      page_name = 'activity' + str(class_id) + str(lesson_id) + '_page'
      cached_page = memcache.get(page_name)
      if not cached_page:
        logging.info('cache miss: ' + page_name)
        page = PageCache.get_by_key_name(page_name)
        if page:
          memcache.add(page_name, page.content)
          cached_page = page.content
        else:
          cached_page = self.delegateTo(lessons.ActivityHandler())

      self.serve(cached_page, student.key().name(), None)
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
    student = self.getStudent()
    if student:
      # Serve the assessment page from memcache if possible, other from datastore
      page_name = 'assessment' + name + '_page'
      cached_page = memcache.get(page_name)
      if not cached_page:
        logging.info('cache miss: ' + page_name)
        page = PageCache.get_by_key_name(page_name)
        if page:
          memcache.add(page_name, page.content)
          cached_page = page.content
        else:
          cached_page = self.delegateTo(lessons.AssessmentHandler())

      self.serve(cached_page, student.key().name(), None)
    else:
      self.redirect('/register')


"""
Handler for serving forum page
"""
class ForumHandler(StudentHandler):

  def get(self):
    # Check for enrollment status
    student = self.getStudent()
    if student:
      # Serve the forum page from memcache if possible, other from datastore
      page_name = 'forum_page'
      cached_page = memcache.get(page_name)
      if not cached_page:
        logging.info('cache miss: ' + page_name)
        page = PageCache.get_by_key_name(page_name)
        if page:
          memcache.add(page_name, page.content)
          cached_page = page.content
        else:
          cached_page = self.delegateTo(utils.ForumHandler())

      self.serve(cached_page, student.key().name(), None)
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
    student = self.getStudent()
    if student:
      # Log answer submission
      logging.info(student.key().name() + ':' + answer)

      # Find student entity and save answers
      student = Student.get_by_key_name(student.key().name().encode('utf8'))

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
      memcache.set(student.key().name(), student)

      # Serve the confirmation page from memcache if possible, otherwise
      # from datastore
      page_name = type + 'confirmation_page'
      cached_page = memcache.get(page_name)
      if not cached_page:
        logging.info('cache miss: ' + page_name)
        page = PageCache.get_by_key_name(page_name)
        if page:
          memcache.add(page_name, page.content)
          cached_page = page.content
        else:
          cached_page = self.delegateTo(utils.AnswerHandler(type))

      self.serve(cached_page, student.key().name(), str(student.overall_score))
    else:
      self.redirect('/register')
