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
import os
import urlparse
import jinja2
from models.models import Lesson
from models.models import Student
from models.models import Unit
from models.roles import Roles
from models.utils import get_all_scores
from tools import verify
import webapp2
from webapp2_extras import i18n
from google.appengine.api import users


# FIXME: Set MAX_CLASS_SIZE to a positive integer if you want to restrict the
# course size to a maximum of N students. Note, though, that counting the
# students in this way uses a lot of database calls that may cost you quota
# and money.
# TODO(psimakov): we must use sharded counter and not Student.all().count()
MAX_CLASS_SIZE = None

# The name of the template dict key that stores a course's base location.
COURSE_BASE_KEY = 'gcb_course_base'

# The name of the template dict key that stores data from course.yaml.
COURSE_INFO_KEY = 'course_info'


class ReflectiveRequestHandler(object):
    """Uses reflection to handle custom get() and post() requests.

    Use this class as a mix-in with any webapp2.RequestHandler to allow request
    dispatching to multiple get() and post() methods based on the 'action'
    parameter.

    Open your existing webapp2.RequestHandler, add this class as a mix-in.
    Define the following class variables:

        default_action = 'list'
        get_actions = ['default_action', 'edit']
        post_actions = ['save']

    Add instance methods named get_list(self), get_edit(self), post_save(self).
    These methods will now be called automatically based on the 'action'
    GET/POST parameter.
    """

    def get(self):
        """Handles GET."""
        action = self.request.get('action')
        if not action:
            action = self.__class__.default_action

        if not action in self.__class__.get_actions:
            self.error(404)
            return

        handler = getattr(self, 'get_%s' % action)
        if not handler:
            self.error(404)
            return

        return handler()

    def post(self):
        """Handles POST."""
        action = self.request.get('action')
        if not action or not action in self.__class__.post_actions:
            self.error(404)
            return

        handler = getattr(self, 'post_%s' % action)
        if not handler:
            self.error(404)
            return

        return handler()


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

    def get_template(self, template_file, additional_dir=None):
        """Computes location of template files for the current namespace."""
        self.template_value[COURSE_INFO_KEY] = self.app_context.get_environ()
        self.template_value['is_super_admin'] = Roles.is_super_admin()
        self.append_base()

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

    def get_units(self):
        """Gets a list of units in a course. Loads data from CSV if None."""
        units = Unit.get_units()
        if not units:
            units = put_course_into_datastore(self.app_context.get_data_home())
        return units

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

    def personalize_page_and_get_enrolled(self):
        """If the user is enrolled, add personalized fields to the navbar."""
        user = self.personalize_page_and_get_user()
        if not user:
            self.redirect(users.create_login_url(self.request.uri))
            return None

        student = Student.get_enrolled_student_by_email(user.email())
        if not student:
            self.redirect('/preview')
            return None

        return student

    def render(self, template_file):
        template = self.get_template(template_file)
        self.response.out.write(template.render(self.template_value))


def copy_attributes(source, target, converter):
    """Copies source object attributes into a target using a converter."""
    for source_name, value in converter.items():
        if value:
            target_name = value[0]
            target_type = value[1]
            setattr(
                target, target_name, target_type(getattr(source, source_name)))


def put_course_into_datastore(data_folder):
    """Loads course data from the CSV files."""
    logging.info('Initializing datastore from CSV files')

    unit_file = os.path.join(data_folder, 'unit.csv')
    lesson_file = os.path.join(data_folder, 'lesson.csv')

    # Load and validate data from CSV files.
    units = verify.read_objects_from_csv_file(
        unit_file, verify.UNITS_HEADER, verify.Unit)
    lessons = verify.read_objects_from_csv_file(
        lesson_file, verify.LESSONS_HEADER, verify.Lesson)
    verifier = verify.Verifier()
    verifier.verify_unit_fields(units)
    verifier.verify_lesson_fields(lessons)
    verifier.verify_unit_lesson_relationships(units, lessons)
    assert verifier.errors == 0
    assert verifier.warnings == 0

    # Load data from CSV files into a datastore.
    units = verify.read_objects_from_csv_file(
        unit_file, verify.UNITS_HEADER, Unit)
    lessons = verify.read_objects_from_csv_file(
        lesson_file, verify.LESSONS_HEADER, Lesson)
    for unit in units:
        entity = Unit()
        copy_attributes(unit, entity, verify.UNIT_CSV_TO_DB_CONVERTER)
        entity.put()
    for lesson in lessons:
        entity = Lesson()
        copy_attributes(lesson, entity, verify.LESSON_CSV_TO_DB_CONVERTER)
        entity.put()

    return Unit.get_units(False)


class PreviewHandler(BaseHandler):
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
        self.template_value['units'] = self.get_units()
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
        """Handles GET requests."""
        if not self.personalize_page_and_get_enrolled():
            return

        self.template_value['navbar'] = {'forum': True}
        self.render('forum.html')


class StudentProfileHandler(BaseHandler):
    """Handles the click to 'My Profile' link in the nav bar."""

    def get(self):
        """Handles GET requests."""
        student = self.personalize_page_and_get_enrolled()
        if not student:
            return

        self.template_value['navbar'] = {}
        self.template_value['student'] = student
        self.template_value['scores'] = get_all_scores(student)
        self.render('student_profile.html')


class StudentEditStudentHandler(BaseHandler):
    """Handles edits to student records by students."""

    def get(self):
        """Handles GET requests."""
        student = self.personalize_page_and_get_enrolled()
        if not student:
            return

        self.template_value['navbar'] = {}
        self.template_value['student'] = student
        self.template_value['scores'] = get_all_scores(student)
        self.render('student_profile.html')

    def post(self):
        """Handles POST requests."""
        student = self.personalize_page_and_get_enrolled()
        if not student:
            return

        Student.rename_current(self.request.get('name'))

        self.redirect('/student/editstudent')


class StudentUnenrollHandler(BaseHandler):
    """Handler for students to unenroll themselves."""

    def get(self):
        """Handles GET requests."""
        student = self.personalize_page_and_get_enrolled()
        if not student:
            return

        self.template_value['student'] = student
        self.template_value['navbar'] = {'registration': True}
        self.render('unenroll_confirmation_check.html')

    def post(self):
        """Handles POST requests."""
        student = self.personalize_page_and_get_enrolled()
        if not student:
            return

        Student.set_enrollment_status_for_current(False)

        self.template_value['navbar'] = {'registration': True}
        self.render('unenroll_confirmation.html')
