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

import os, logging
from models.models import Student, Unit, Lesson
import webapp2, jinja2

from google.appengine.api import users, memcache, taskqueue
from google.appengine.ext import db

template_dir = os.path.join(os.path.dirname(__file__), '../views')
jinja_environment = jinja2.Environment(
    loader=jinja2.FileSystemLoader(template_dir))


"""
Base handler
"""
class BaseHandler(webapp2.RequestHandler):
  templateValue = {}
  user = users.get_current_user()
  logging.info(user)

  def getUser(self):
    """Validate user exists and in early access list."""
    user = users.get_current_user()
    if not user:
      self.redirect(users.create_login_url(self.request.uri))
    else:
      return user

  def render(self, templateFile):
    template = jinja_environment.get_template(templateFile)
    self.response.out.write(template.render(self.templateValue))


"""
Student Handler
"""
class StudentHandler(webapp2.RequestHandler):
  templateValue = {}
  def getStudent(self):
    user = users.get_current_user()
    if user:
      student = memcache.get(user.email())
      if not student:
        student = Student.get_by_key_name(user.email())
        memcache.set(user.email(), student)
      return student
    else:
      self.redirect(users.create_login_url(self.request.uri))

  def render(self, templateFile):
    template = jinja_environment.get_template(templateFile)
    html = template.render(self.templateValue)
    self.response.out.write(html)


"""
Handler for course registration
"""
class RegisterHandler(BaseHandler):

  def get(self):
    user = users.get_current_user()
    if user:
      self.templateValue['email'] = user.email()
      self.templateValue['logoutUrl'] = users.create_logout_url('/')

    navbar = {'registration': True}
    self.templateValue['navbar'] = navbar
    # Check for existing registration -> redirect to course page
    student = Student.get_by_key_name(user.email())
    if student is None:
      self.render('register.html')
    else:
      self.redirect('/course')

  def post(self):
    user = users.get_current_user()
    if user:
      email = user.email()
      self.templateValue['email'] = email
      self.templateValue['logoutUrl'] = users.create_logout_url('/')

    # Restrict the maximum course size to 250000 people
    # FIXME: you can change this number if you wish.
    students = Student.all(keys_only=True)
    if (students.count() > 249999):
      self.templateValue['course_status'] = 'full'

    # Create student record
    name = self.request.get('form01')
    student = Student(key_name=user.email(), name=name)
    student.put()

    # Render registration confirmation page
    navbar = {'registration': True}
    self.templateValue['navbar'] = navbar
    self.render('confirmation.html')


"""
Handler for forum page
"""
class ForumHandler(BaseHandler):

  def get(self):
    navbar = {'forum':True}
    self.templateValue['navbar'] = navbar
    user = users.get_current_user()
    if user:
      self.templateValue['email'] = user.email()
      self.templateValue['logoutUrl'] = users.create_logout_url('/')
    self.render('forum.html')
