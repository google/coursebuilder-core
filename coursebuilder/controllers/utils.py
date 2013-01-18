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

"""Handlers that are not directly related to course content."""

__author__ = 'Saifu Angto (saifu@google.com)'

import logging
import urlparse

import jinja2
from models.models import MemcacheManager
from models.models import Student
from models.models import Unit
from models.utils import getAllScores
import webapp2

from google.appengine.api import users


# FIXME: Set MAX_CLASS_SIZE to a positive integer if you want to restrict the
# course size to a maximum of N students. Note, though, that counting the
# students in this way uses a lot of database calls that may cost you quota
# and money.
# TODO(psimakov): we must use sharded counter and not Student.all().count()
MAX_CLASS_SIZE = None

# A template place holder for the student email.
USER_EMAIL_PLACE_HOLDER = '{{ email }}'


class ApplicationHandler(webapp2.RequestHandler):
    """A handler that is aware of the application context."""

    def __init__(self):
        super(ApplicationHandler, self).__init__()
        self.templateValue = {}

    def appendBase(self):
        """Append current course <base> to template variables."""
        slug = self.app_context.getSlug()
        if not slug.endswith('/'):
            slug = '%s/' % slug
        self.templateValue['gcb_course_base'] = slug

    def getTemplate(self, templateFile):
        """Computes location of template files for the current namespace."""
        self.appendBase()
        template_dir = self.app_context.getTemplateHome()
        jinja_environment = jinja2.Environment(
            loader=jinja2.FileSystemLoader(template_dir))
        return jinja_environment.get_template(templateFile)

    def is_absolute(self, url):
        return bool(urlparse.urlparse(url).scheme)

    def redirect(self, location):
        """Adds the current namespace URL prefix to the relative 'location'."""
        if not self.is_absolute(location):
            if (self.app_context.getSlug() and
                self.app_context.getSlug() != '/'):
                location = '%s%s' % (self.app_context.getSlug(), location)
        super(ApplicationHandler, self).redirect(location)


class BaseHandler(ApplicationHandler):
    """Base handler."""

    def getUser(self):
        """Validate user exists."""
        user = users.get_current_user()
        if not user:
            self.redirect(users.create_login_url(self.request.uri))
        else:
            return user

    def personalizePageAndGetUser(self):
        """If the user exists, add personalized fields to the navbar."""
        user = self.getUser()
        if user:
            self.templateValue['email'] = user.email()
            self.templateValue['logoutUrl'] = users.create_logout_url('/')
        return user

    def render(self, templateFile):
        template = self.getTemplate(templateFile)
        self.response.out.write(template.render(self.templateValue))


class StudentHandler(ApplicationHandler):
    """Student handler."""

    def get_page(self, page_name, content_lambda):
        """Get page from cache or create page on demand."""
        content = MemcacheManager.get(page_name)
        if not content:
            logging.info('Cache miss: %s', page_name)
            content = content_lambda()
            MemcacheManager.set(page_name, content)
        return content

    def getOrCreatePage(self, page_name, handler):
        def content_lambda():
            return self.delegateTo(handler)
        return self.get_page(page_name, content_lambda)

    def delegateTo(self, handler):
        """Run another handler using system identity.

        This method is called when a dynamic page template cannot be found in
        either memcache or the datastore. We now need to create this page using
        a handler passed to this method. The handler must run with the exact
        same request parameters as self, but we need to replace current user
        and the response.

        Args:
            handler: The handler to be run using the system identity.

        Returns:
            The text output by the handler.
        """

        # create custom function for replacing the current user
        def get_placeholder_user():
            return users.User(email=USER_EMAIL_PLACE_HOLDER)

        # create custom response.out to intercept output
        class StringWriter(object):
            def __init__(self):
                self.buffer = []

            def write(self, text):
                self.buffer.append(text)

            def getText(self):
                return ''.join(self.buffer)

        class BufferedResponse(object):
            def __init__(self):
                self.out = StringWriter()

        # configure handler request and response
        handler.app_context = self.app_context
        handler.request = self.request
        handler.response = BufferedResponse()

        # substitute current user with the system account and run the handler
        get_current_user_old = users.get_current_user
        try:
            user = users.get_current_user()
            if user:
                users.get_current_user = get_placeholder_user
            handler.get()
        finally:
            users.get_current_user = get_current_user_old

        return handler.response.out.getText()

    def getEnrolledStudent(self):
        user = users.get_current_user()
        if user:
            return Student.get_enrolled_student_by_email(user.email())
        else:
            self.redirect(users.create_login_url(self.request.uri))

    def serve(self, page, email=None):
        """Substitute email placeholders before serving the cached page."""
        html = page
        if email:
            html = html.replace(USER_EMAIL_PLACE_HOLDER, email)
        self.response.out.write(html)


class CoursePreviewHandler(BaseHandler):
    """Handler for viewing course preview."""

    def get(self):
        """Handles GET requests."""
        user = users.get_current_user()
        if not user:
            self.templateValue['loginUrl'] = users.create_login_url('/')
        else:
            self.templateValue['email'] = user.email()
            self.templateValue['logoutUrl'] = users.create_logout_url('/')

        self.templateValue['navbar'] = {'course': True}
        self.templateValue['units'] = Unit.get_units()
        if user and Student.get_enrolled_student_by_email(user.email()):
            self.redirect('/course')
        else:
            self.render('preview.html')


class RegisterHandler(BaseHandler):
    """Handler for course registration."""

    def get(self):
        user = self.personalizePageAndGetUser()
        if not user:
            self.redirect(users.create_login_url(self.request.uri))
            return

        self.templateValue['navbar'] = {'registration': True}
        # Check for existing registration -> redirect to course page
        student = Student.get_enrolled_student_by_email(user.email())
        if student:
            self.redirect('/course')
        else:
            self.render('register.html')

    def post(self):
        """Handles POST requests."""
        user = self.personalizePageAndGetUser()
        if not user:
            self.redirect(users.create_login_url(self.request.uri))
            return

        if (MAX_CLASS_SIZE and
            Student.all(keys_only=True).count() >= MAX_CLASS_SIZE):
            self.templateValue['course_status'] = 'full'
        else:
            # Create student record
            name = self.request.get('form01')

            # create new or re-enroll old student
            student = Student.get_by_email(user.email())
            if student:
                if not student.is_enrolled:
                    student.is_enrolled = True
                    student.name = name
            else:
                student = Student(
                    key_name=user.email(), name=name, is_enrolled=True)
            student.put()

        # Render registration confirmation page
        self.templateValue['navbar'] = {'registration': True}
        self.render('confirmation.html')


class ForumHandler(BaseHandler):
    """Handler for forum page."""

    def get(self):
        user = self.personalizePageAndGetUser()
        if not user:
            self.redirect(users.create_login_url(self.request.uri))
            return

        self.templateValue['navbar'] = {'forum': True}
        self.render('forum.html')


class AnswerConfirmationHandler(BaseHandler):
    """Handler for rendering answer submission confirmation page."""

    def __init__(self, assessment_type):
        super(AnswerConfirmationHandler, self).__init__()
        self.type = assessment_type

    def get(self):
        user = self.personalizePageAndGetUser()
        if not user:
            self.redirect(users.create_login_url(self.request.uri))
            return

        self.templateValue['navbar'] = {'course': True}
        self.templateValue['assessment'] = self.type
        self.render('test_confirmation.html')


class StudentProfileHandler(BaseHandler):
    """Handles the click to 'My Profile' link in the nav bar."""

    def get(self):
        """Handles GET requests."""
        user = self.personalizePageAndGetUser()
        if not user:
            self.redirect(users.create_login_url(self.request.uri))
            return

        # Check for existing registration -> redirect to registration page.
        student = Student.get_enrolled_student_by_email(user.email())
        if not student:
            self.redirect('/preview')
            return

        self.templateValue['navbar'] = {}
        self.templateValue['student'] = student
        self.templateValue['scores'] = getAllScores(student)
        self.render('student_profile.html')


class StudentEditStudentHandler(BaseHandler):
    """Handles edits to student records by students."""

    def get(self):
        """Handles GET requests."""
        user = self.personalizePageAndGetUser()
        if not user:
            self.redirect(users.create_login_url(self.request.uri))
            return

        self.templateValue['navbar'] = {}
        e = self.request.get('email')
        # Check for existing registration -> redirect to course page
        student = Student.get_by_email(e)
        if not student:
            self.templateValue['student'] = None
            self.templateValue['errormsg'] = (
                'Error: Student with email %s cannot be found on the '
                'roster.' % e)
        else:
            self.templateValue['student'] = student
            self.templateValue['scores'] = getAllScores(student)
        self.render('student_profile.html')

    def post(self):
        """Handles POST requests."""
        user = self.personalizePageAndGetUser()
        if not user:
            self.redirect(users.create_login_url(self.request.uri))
            return

        # Update student record
        email = self.request.get('email')
        name = self.request.get('name')

        student = Student.get_by_email(email)
        if student:
            if name:
                student.name = name
            student.put()
        self.redirect('/student/editstudent?email=%s' % email)


class AnnouncementsHandler(BaseHandler):
    """Handler for announcements."""

    def get(self):
        """Handles GET requests."""
        user = self.personalizePageAndGetUser()
        if not user:
            self.redirect(users.create_login_url(self.request.uri))
            return

        student = Student.get_enrolled_student_by_email(user.email())
        if not student:
            self.redirect('/preview')
            return

        self.templateValue['navbar'] = {'announcements': True}
        self.render('announcements.html')


class StudentUnenrollHandler(BaseHandler):
    """Handler for students to unenroll themselves."""

    def get(self):
        """Handles GET requests."""
        user = self.personalizePageAndGetUser()
        if not user:
            self.redirect(users.create_login_url(self.request.uri))
            return

        student = Student.get_enrolled_student_by_email(user.email())
        if student:
            self.templateValue['student'] = student
        self.templateValue['navbar'] = {'registration': True}
        self.render('unenroll_confirmation_check.html')

    def post(self):
        """Handles POST requests."""
        user = self.personalizePageAndGetUser()
        if not user:
            self.redirect(users.create_login_url(self.request.uri))
            return

        # Update student record
        student = Student.get_by_email(user.email())
        if student and student.is_enrolled:
            student.is_enrolled = False
            student.put()
        self.templateValue['navbar'] = {'registration': True}
        self.render('unenroll_confirmation.html')
