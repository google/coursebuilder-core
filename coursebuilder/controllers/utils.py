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
from models.utils import get_all_scores
import webapp2
from webapp2_extras import i18n
import yaml

from google.appengine.api import users


# FIXME: Set MAX_CLASS_SIZE to a positive integer if you want to restrict the
# course size to a maximum of N students. Note, though, that counting the
# students in this way uses a lot of database calls that may cost you quota
# and money.
# TODO(psimakov): we must use sharded counter and not Student.all().count()
MAX_CLASS_SIZE = None

# A template place holder for the student email.
USER_EMAIL_PLACE_HOLDER = '{{ email }}'

# The name of the template dict key that stores a course's base location.
COURSE_BASE_KEY = 'gcb_course_base'

# The name of the template dict key that stores data from course.yaml.
COURSE_INFO_KEY = 'course_info'


class ApplicationHandler(webapp2.RequestHandler):
    """A handler that is aware of the application context."""

    def __init__(self):
        super(ApplicationHandler, self).__init__()
        self.template_value = {}

    def append_base(self):
        """Append current course <base> to template variables."""
        slug = self.app_context.get_slug()
        if not slug.endswith('/'):
            slug = '%s/' % slug
        self.template_value[COURSE_BASE_KEY] = slug

    def append_parameters_from_yaml_file(self):
        """Append parameters from the relevant course.yaml file."""
        course_data_filename = self.app_context.get_config_filename()

        try:
            with open(course_data_filename) as course_data_file:
                course_info = yaml.load(course_data_file)
                self.template_value[COURSE_INFO_KEY] = course_info
        except IOError():
            logging.info('Error: course.yaml file at %s not accessible',
                         course_data_filename)
            raise

    def get_template(self, template_file, additional_dir=None):
        """Computes location of template files for the current namespace."""
        self.append_base()
        self.append_parameters_from_yaml_file()
        template_dir = self.app_context.get_template_home()

        dirs = [template_dir]
        if additional_dir:
            dirs += additional_dir

        jinja_environment = jinja2.Environment(
            extensions=['jinja2.ext.i18n'],
            loader=jinja2.FileSystemLoader(dirs))
        jinja_environment.install_gettext_translations(i18n)

        locale = self.template_value[COURSE_INFO_KEY]['course']['locale']
        i18n.get_i18n().set_locale(locale)

        return jinja_environment.get_template(template_file)

    def is_absolute(self, url):
        return bool(urlparse.urlparse(url).scheme)

    def canonicalize_url(self, location):
        """Adds the current namespace URL prefix to the relative 'location'."""
        if not self.is_absolute(location):
            if (self.app_context.get_slug() and
                self.app_context.get_slug() != '/'):
                location = '%s%s' % (self.app_context.get_slug(), location)
        return location

    def redirect(self, location):
        super(ApplicationHandler, self).redirect(
            self.canonicalize_url(location))


class BaseHandler(ApplicationHandler):
    """Base handler."""

    def get_user(self):
        """Validate user exists."""
        user = users.get_current_user()
        if not user:
            self.redirect(users.create_login_url(self.request.uri))
        else:
            return user

    def personalize_page_and_get_user(self):
        """If the user exists, add personalized fields to the navbar."""
        user = self.get_user()
        if user:
            self.template_value['email'] = user.email()
            self.template_value['logoutUrl'] = users.create_logout_url('/')
        return user

    def render(self, template_file):
        template = self.get_template(template_file)
        self.response.out.write(template.render(self.template_value))


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

    def get_or_create_page(self, page_name, handler):
        def content_lambda():
            return self.delegate_to(handler)
        return self.get_page(page_name, content_lambda)

    def delegate_to(self, handler):
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

            def get_text(self):
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

        return handler.response.out.get_text()

    def get_enrolled_student(self):
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
            self.template_value['loginUrl'] = users.create_login_url('/')
        else:
            self.template_value['email'] = user.email()
            self.template_value['logoutUrl'] = users.create_logout_url('/')

        self.template_value['navbar'] = {'course': True}
        self.template_value['units'] = Unit.get_units()
        if user and Student.get_enrolled_student_by_email(user.email()):
            self.redirect('/course')
        else:
            self.render('preview.html')


class RegisterHandler(BaseHandler):
    """Handler for course registration."""

    def get(self):
        user = self.personalize_page_and_get_user()
        if not user:
            self.redirect(users.create_login_url(self.request.uri))
            return

        self.template_value['navbar'] = {'registration': True}
        # Check for existing registration -> redirect to course page
        student = Student.get_enrolled_student_by_email(user.email())
        if student:
            self.redirect('/course')
        else:
            self.render('register.html')

    def post(self):
        """Handles POST requests."""
        user = self.personalize_page_and_get_user()
        if not user:
            self.redirect(users.create_login_url(self.request.uri))
            return

        if (MAX_CLASS_SIZE and
            Student.all(keys_only=True).count() >= MAX_CLASS_SIZE):
            self.template_value['course_status'] = 'full'
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
        self.template_value['navbar'] = {'registration': True}
        self.render('confirmation.html')


class ForumHandler(BaseHandler):
    """Handler for forum page."""

    def get(self):
        user = self.personalize_page_and_get_user()
        if not user:
            self.redirect(users.create_login_url(self.request.uri))
            return

        self.template_value['navbar'] = {'forum': True}
        self.render('forum.html')


class AnswerConfirmationHandler(BaseHandler):
    """Handler for rendering answer submission confirmation page."""

    def __init__(self, assessment_type):
        super(AnswerConfirmationHandler, self).__init__()
        self.type = assessment_type

    def get(self):
        user = self.personalize_page_and_get_user()
        if not user:
            self.redirect(users.create_login_url(self.request.uri))
            return

        self.template_value['navbar'] = {'course': True}
        self.template_value['assessment'] = self.type
        self.render('test_confirmation.html')


class StudentProfileHandler(BaseHandler):
    """Handles the click to 'My Profile' link in the nav bar."""

    def get(self):
        """Handles GET requests."""
        user = self.personalize_page_and_get_user()
        if not user:
            self.redirect(users.create_login_url(self.request.uri))
            return

        # Check for existing registration -> redirect to registration page.
        student = Student.get_enrolled_student_by_email(user.email())
        if not student:
            self.redirect('/preview')
            return

        self.template_value['navbar'] = {}
        self.template_value['student'] = student
        self.template_value['scores'] = get_all_scores(student)
        self.render('student_profile.html')


class StudentEditStudentHandler(BaseHandler):
    """Handles edits to student records by students."""

    def get(self):
        """Handles GET requests."""
        user = self.personalize_page_and_get_user()
        if not user:
            self.redirect(users.create_login_url(self.request.uri))
            return

        self.template_value['navbar'] = {}
        e = self.request.get('email')
        # Check for existing registration -> redirect to course page
        student = Student.get_by_email(e)
        if not student:
            self.template_value['student'] = None
            self.template_value['errormsg'] = (
                'Error: Student with email %s cannot be found on the '
                'roster.' % e)
        else:
            self.template_value['student'] = student
            self.template_value['scores'] = get_all_scores(student)
        self.render('student_profile.html')

    def post(self):
        """Handles POST requests."""
        user = self.personalize_page_and_get_user()
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


class StudentUnenrollHandler(BaseHandler):
    """Handler for students to unenroll themselves."""

    def get(self):
        """Handles GET requests."""
        user = self.personalize_page_and_get_user()
        if not user:
            self.redirect(users.create_login_url(self.request.uri))
            return

        student = Student.get_enrolled_student_by_email(user.email())
        if student:
            self.template_value['student'] = student
        self.template_value['navbar'] = {'registration': True}
        self.render('unenroll_confirmation_check.html')

    def post(self):
        """Handles POST requests."""
        user = self.personalize_page_and_get_user()
        if not user:
            self.redirect(users.create_login_url(self.request.uri))
            return

        # Update student record
        student = Student.get_by_email(user.email())
        if student and student.is_enrolled:
            student.is_enrolled = False
            student.put()
        self.template_value['navbar'] = {'registration': True}
        self.render('unenroll_confirmation.html')
