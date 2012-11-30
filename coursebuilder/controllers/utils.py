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
import webapp2, jinja2

from models.models import Student, Unit, PageCache, Email
from google.appengine.api import users, mail, memcache, taskqueue
from google.appengine.ext import db, deferred

template_dir = os.path.join(os.path.dirname(__file__), '../views')
jinja_environment = jinja2.Environment(
    loader=jinja2.FileSystemLoader(template_dir))

USER_EMAIL_PLACE_HOLDER = "{{ email }}"


def sendWelcomeEmail(email):
  # FIXME: To automatically send welcome emails, edit this welcome message
  # and see the welcome email FIXME in RegisterHandler
  message = mail.EmailMessage(sender="COURSE STAFF NAME <COURSE_EMAIL_ADDRESS@YOURDOMAIN>",
    subject="Welcome to COURSE NAME!")
  message.to = email
  message.body = """
    Thank you for registering for COURSE NAME.
    YOUR WELCOME MESSAGE HERE
  """
  message.html = """
    <p>Thank you for registering for COURSE NAME.</p>
    <p>YOUR WELCOME MESSAGE HERE</p>
  """
  message.send()


"""
Base handler
"""
class BaseHandler(webapp2.RequestHandler):
  templateValue = {}
  user = users.get_current_user()
  logging.info(user)

  def getUser(self):
    """Validate user exists."""
    user = users.get_current_user()
    if not user:
      self.redirect(users.create_login_url(self.request.uri))
    else:
      return user

  def render(self, templateFile):
    template = jinja_environment.get_template(templateFile)
    self.response.out.write(template.render(self.templateValue))

  # Evaluate page template, store result in datastore, and update memcache
  def renderToDatastore(self, name, templateFile):
    template = jinja_environment.get_template(templateFile)
    page_cache = PageCache.get_by_key_name(name)
    if page_cache:
      page_cache.content = template.render(self.templateValue)
    else:
      page_cache = PageCache(key_name=name, content=template.render(self.templateValue))
    page_cache.put()
    logging.info('pagecache put: ' + name)
    memcache.set(name, page_cache.content)
    logging.info('cache set: ' + name)
    self.response.out.write(page_cache.content)


"""
Student Handler
"""
class StudentHandler(webapp2.RequestHandler):
  def delegateTo(self, handler):
    """"Run another handler using system identity.


    This method is called when a dynamic page template can't be found neither in
    the cache nor the database. We now need to create this page using a handler
    passed to this method. The handler must run with the exact same request
    parameters as self, but we need to replace current user and the response."""

    # create custom function for replacing the current user
    def get_current_user_ex():
      return users.User(email = USER_EMAIL_PLACE_HOLDER)

    # create custom response.out to intercept output
    class StringWriter:
      def __init__(self):
        self.buffer = []

      def write(self, text):
        self.buffer.append(text)

      def getText(self):
        return "".join(self.buffer)

    class BufferedResponse:
      def __init__(self):
        self.out = StringWriter()

    # configure handler request and response
    handler.request = self.request
    handler.response = BufferedResponse()

    # substitute current user with the system account and run the handler
    get_current_user_old = users.get_current_user
    try:
      users.get_current_user = get_current_user_ex
      handler.get()
    finally:
      users.get_current_user = get_current_user_old

    return handler.response.out.getText()


  def getEnrolledStudent(self):
    user = users.get_current_user()

    if user:
      email = user.email()
      student = memcache.get(email)
      if not student:
        student = Student.get_enrolled_student_by_email(email)
        if student:
          memcache.set(email, student)
      return student
    else:
      self.redirect(users.create_login_url(self.request.uri))

  def serve(self, page, email, overall_score):
    # Search and substitute placeholders for current user email and
    # overall_score (if applicable) in the cached page before serving them to
    # users.
    if overall_score:
      html = page.replace(USER_EMAIL_PLACE_HOLDER, email).replace('XX', overall_score)
      self.response.out.write(html)
    else:
      self.response.out.write(page.replace(USER_EMAIL_PLACE_HOLDER, email))


"""
Handler for course registration closed
"""
class RegisterClosedHandler(BaseHandler):

  def get(self):
    user = users.get_current_user()
    if user:
      self.templateValue['email'] = user.email()
      self.templateValue['logoutUrl'] = users.create_logout_url("/")

    self.templateValue['navbar'] = {'registration': True}
    page = jinja_environment.get_template('registration_close.html').render(self.templateValue)
    self.response.out.write(page.replace(USER_EMAIL_PLACE_HOLDER, user.email()))


"""
Handler for course registration
"""
class RegisterHandler(BaseHandler):
  def get(self):
    user = users.get_current_user()
    if user:
      self.templateValue['email'] = user.email()
      self.templateValue['logoutUrl'] = users.create_logout_url("/")

    navbar = {'registration': True}
    self.templateValue['navbar'] = navbar
    # Check for existing registration -> redirect to course page
    student = Student.get_enrolled_student_by_email(user.email())
    if student:
      self.redirect('/course')
    else:
      self.render('register.html')

  def post(self):
    user = users.get_current_user()
    if user:
      email = user.email()
      self.templateValue['email'] = email
      self.templateValue['logoutUrl'] = users.create_logout_url('/')

    # Restrict the maximum course size to 250000 people
    # FIXME: you can change this number if you wish.
    # Uncomment the following 3 lines if you want to restrict the course size.
    # Note, though, that counting the students in this way uses a lot of database
    # calls that may cost you quota and money.

    # students = Student.all(keys_only=True)
    # if (students.count() > 249999):
    #   self.templateValue['course_status'] = 'full'

    # Create student record
    name = self.request.get('form01')

    # If a student un-enrolls and then tries to re-enroll, then DELETE the
    # old entry first or else the system gets confused ...
    existing_student = Student.get_by_key_name(user.email())
    if existing_student:
      db.delete(existing_student)
      memcache.delete(user.email())

    student = Student(key_name=user.email(), name=name, is_enrolled=True)
    student.put()

    # FIXME: Uncomment the following 2 lines, edit the message in the sendWelcomeEmail
    # function and create a queue.yaml file if you want to automatically send a
    # welcome email message.

    # # Send welcome email
    # deferred.defer(sendWelcomeEmail, email)

    # Render registration confirmation page
    self.templateValue['navbar'] = {'registration': True}
    self.render('confirmation.html')


"""
Handler for forum page
"""
class ForumHandler(BaseHandler):

  def get(self):
    self.templateValue['navbar'] = {'forum': True}
    user = users.get_current_user()
    if user:
      self.templateValue['email'] = user.email()
      self.templateValue['logoutUrl'] = users.create_logout_url('/')
    self.renderToDatastore('forum_page', 'forum.html')


"""
Handler for saving assessment answers
"""
class AnswerHandler(BaseHandler):
  def __init__(self, type):
    self.type = type

  def get(self):
    user = users.get_current_user()
    if user:

      # Set template values
      self.templateValue['email'] = user.email()
      self.templateValue['logoutUrl'] = users.create_logout_url("/")
      self.templateValue['navbar'] = {'course': True}
      self.templateValue['assessment'] = self.type

      # Render confirmation page
      self.renderToDatastore(self.type + 'confirmation_page', 'test_confirmation.html')


class AddTaskHandler(webapp2.RequestHandler):
  def get(self):
    log = ''
    emails = EmailList.all().fetch(1000)
    if emails:
      for email in emails:
        log = log + email.email + "\n"
        taskqueue.add(url='/admin/reminderemail', params={'to': email.email})
      db.delete(emails)
      self.response.out.write(log)


"""
This function handles the click to 'My Profile' link in the nav bar
"""
class StudentProfileHandler(BaseHandler):
  def get(self):
    user = users.get_current_user()
    if user:
      self.templateValue['email'] = user.email()
      self.templateValue['logoutUrl'] = users.create_logout_url("/")
      self.templateValue['navbar'] = {}
    #check for existing registration -> redirect to course page
    e = user.email()
    student = Student.get_by_key_name(e)
    if student == None:
      self.templateValue['student'] = None
      self.templateValue['errormsg'] = 'Error: Student with email ' + e + ' can not be found on the roster.'
      page = jinja_environment.get_template('register.html').render(self.templateValue)
      self.response.out.write(page.replace(USER_EMAIL_PLACE_HOLDER, user.email()))
    else:
      logging.info(student)
      self.templateValue['student'] = student
      page = jinja_environment.get_template('student_profile.html').render(self.templateValue)
      self.response.out.write(page.replace(USER_EMAIL_PLACE_HOLDER, user.email()))


"""
This function handles edits to student records by students
"""
class StudentEditStudentHandler(BaseHandler):
  def get(self):
    e = self.request.get('email')
    user = users.get_current_user()
    if user:
      self.templateValue['email'] = user.email()
      self.templateValue['logoutUrl'] = users.create_logout_url("/")

    self.templateValue['navbar'] = {}
    # Check for existing registration -> redirect to course page
    student = Student.get_by_key_name(e)
    if student == None:
      self.templateValue['student'] = None
      self.templateValue['errormsg'] = 'Error: Student with email ' + e + ' can not be found on the roster.'
      page = jinja_environment.get_template('student_profile.html').render(self.templateValue)
      self.response.out.write(page.replace(USER_EMAIL_PLACE_HOLDER, user.email()))
    else:
      logging.info(student)
      self.templateValue['student'] = student
      page = jinja_environment.get_template('student_profile.html').render(self.templateValue)
      self.response.out.write(page.replace(USER_EMAIL_PLACE_HOLDER, user.email()))

  def post(self):
    user = users.get_current_user()
    if user:
      email = user.email()
      self.templateValue['email'] = email
      self.templateValue['logoutUrl'] = users.create_logout_url("/")

    # Update student record
    e = self.request.get('email')
    n = self.request.get('name')

    student = Student.get_by_key_name(e)
    if student:
      if (n != ''):
        student.name = n
      student.put()
    self.redirect('/student/editstudent?email='+e)


"""
Handler for Announcements
"""
class AnnouncementsHandler(BaseHandler):
  def get(self):
    user = users.get_current_user()
    if user:
      self.templateValue['email'] = user.email()
      self.templateValue['logoutUrl'] = users.create_logout_url("/")

    self.templateValue['navbar'] = {'announcements': True}
    page = jinja_environment.get_template('announcements.html').render(self.templateValue)
    self.response.out.write(page.replace(USER_EMAIL_PLACE_HOLDER, user.email()))


"""
Handler for students to unenroll themselves
"""
class StudentUnenrollHandler(BaseHandler):
  def get(self):
    user = users.get_current_user()
    if user:
      self.templateValue['email'] = user.email()
      self.templateValue['logoutUrl'] = users.create_logout_url("/")

    self.templateValue['navbar'] = {'registration': True}
    page = jinja_environment.get_template('unenroll_confirmation_check.html').render(self.templateValue)
    self.response.out.write(page.replace(USER_EMAIL_PLACE_HOLDER, user.email()))

  def post(self):
    user = users.get_current_user()
    if user:
      email = user.email()
      self.templateValue['email'] = email
      self.templateValue['logoutUrl'] = users.create_logout_url("/")

    # Update student record
    student = Student.get_enrolled_student_by_email(email)
    if student:
      student.is_enrolled = False
      student.put()
      memcache.delete(email)
    page = jinja_environment.get_template('unenroll_confirmation.html').render(self.templateValue)
    self.response.out.write(page)
