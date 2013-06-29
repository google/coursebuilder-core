# Copyright 2013 Google Inc. All Rights Reserved.
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

"""Classes supporting courses viewed by a student."""

__author__ = 'Rahul Singal (rahulsingal@google.com)'

import mimetypes

import appengine_config
from common import jinja_utils
from controllers import sites
from controllers.utils import PageInitializerService
from controllers.utils import XsrfTokenManager
from models import courses as Courses
from models import transforms
from models.models import StudentProfileDAO
from models.roles import Roles
import webapp2
import course_explorer

from google.appengine.api import users

# We want to use views file in both /views and /modules/course_explorer/views.
DIR = appengine_config.BUNDLE_ROOT
LOCALE = Courses.COURSE_TEMPLATE_DICT['base']['locale']
STUDENT_RENAME_GLOBAL_XSRF_TOKEN_ID = 'rename-student-global'

# Int. Maximum number of bytes App Engine's db.StringProperty can store.
_STRING_PROPERTY_MAX_BYTES = 500


class IndexPageHandler(webapp2.RequestHandler):
    """Handles routing of root url."""

    def get(self):
        """Handles GET requests."""
        if course_explorer.GCB_ENABLE_COURSE_EXPLORER_PAGE.value:
            self.redirect('/explorer')
        else:
            self.redirect('/course')


class BaseStudentHandler(webapp2.RequestHandler):
    """Base Handler for a student's courses."""

    def __init__(self, *args, **kwargs):
        super(BaseStudentHandler, self).__init__(*args, **kwargs)
        self.template_values = {}
        self.initialize_student_state()

    def initialize_student_state(self):
        """Initialize course information related to student."""
        PageInitializerService.get().initialize(self.template_values)
        self.enrolled_courses_dict = {}
        self.courses_progress_dict = {}
        user = users.get_current_user()
        if not user:
            return

        profile = StudentProfileDAO.get_profile_by_user_id(user.user_id())
        if not profile:
            return

        self.template_values['register_xsrf_token'] = (
            XsrfTokenManager.create_xsrf_token('register-post'))

        self.enrolled_courses_dict = transforms.loads(profile.enrollment_info)
        if self.enrolled_courses_dict:
            self.template_values['has_enrolled_courses'] = True

        if profile.course_info:
            self.courses_progress_dict = transforms.loads(profile.course_info)

    def get_public_courses(self):
        """Get all the public courses."""
        public_courses = []
        for course in sites.get_all_courses():
            info = sites.ApplicationContext.get_environ(course)
            if info['course']['now_available']:
                public_courses.append(course)
        return public_courses

    def is_enrolled(self, course):
        """Returns true if student is enrolled else false."""
        return bool(
            self.enrolled_courses_dict.get(course.get_namespace_name()))

    def is_completed(self, course):
        """Returns true if student has completed course else false."""
        info = self.courses_progress_dict.get(course.get_namespace_name())
        if info and 'final_grade' in info:
            return True
        return False

    def get_course_info(self, course):
        """Returns course info required in views."""
        info = sites.ApplicationContext.get_environ(course)
        slug = course.get_slug()
        course_preview_url = slug
        if slug == '/':
            course_preview_url = '/course'
            slug = ''
        info['course']['slug'] = slug
        info['course']['course_preview_url'] = course_preview_url
        info['course']['is_registered'] = self.is_enrolled(course)
        info['course']['is_completed'] = self.is_completed(course)
        return info

    def get_enrolled_courses(self, courses):
        """Returns list of courses registered by student."""
        enrolled_courses = []
        for course in courses:
            if self.is_enrolled(course):
                enrolled_courses.append(self.get_course_info(course))
        return enrolled_courses

    def initialize_page_and_get_user(self):
        """Add basic fields to template and return user."""
        self.template_values['course_info'] = Courses.COURSE_TEMPLATE_DICT
        self.template_values['course_info']['course'] = {'locale': LOCALE}
        user = users.get_current_user()
        if not user:
            self.template_values['loginUrl'] = users.create_login_url('/')
        else:
            self.template_values['email'] = user.email()
            self.template_values['is_super_admin'] = Roles.is_super_admin()
            self.template_values['logoutUrl'] = users.create_logout_url('/')
        return user

    def is_valid_xsrf_token(self, action):
        """Asserts the current request has proper XSRF token or fails."""
        token = self.request.get('xsrf_token')
        return token and XsrfTokenManager.is_xsrf_token_valid(token, action)


class ProfileHandler(BaseStudentHandler):
    """Global profile handler for a student."""

    def _storable_in_string_property(self, value):
        # db.StringProperty can hold 500B. len(1_unicode_char) == 1, so len() is
        # not a good proxy for unicode string size. Instead, cast to utf-8-
        # encoded str first.
        return len(value.encode('utf-8')) <= _STRING_PROPERTY_MAX_BYTES

    def get(self):
        """Handles GET requests."""
        user = self.initialize_page_and_get_user()
        courses = self.get_public_courses()
        self.template_values['student'] = (
            StudentProfileDAO.get_profile_by_user_id(user.user_id()))
        self.template_values['navbar'] = {'profile': True}
        self.template_values['courses'] = self.get_enrolled_courses(courses)
        self.template_values['student_edit_xsrf_token'] = (
            XsrfTokenManager.create_xsrf_token(
                STUDENT_RENAME_GLOBAL_XSRF_TOKEN_ID))

        template = jinja_utils.get_template(
            '/modules/course_explorer/views/profile.html', DIR, LOCALE)
        self.response.write(template.render(self.template_values))

    def post(self):
        """Handles post requests."""
        user = self.initialize_page_and_get_user()
        if not user:
            self.error(403)
            return

        if not self.is_valid_xsrf_token(STUDENT_RENAME_GLOBAL_XSRF_TOKEN_ID):
            self.error(403)
            return

        new_name = self.request.get('name')
        if not (new_name and self._storable_in_string_property(new_name)):
            self.error(400)
            return

        StudentProfileDAO.update(
            user.user_id(), None, nick_name=new_name, profile_only=True)
        self.redirect('/explorer/profile')


class AllCoursesHandler(BaseStudentHandler):
    """Handles list of courses that can be viewed by a student."""

    def get(self):
        """Handles GET requests."""
        self.initialize_page_and_get_user()
        courses = self.get_public_courses()

        self.template_values['courses'] = (
            [self.get_course_info(course) for course in courses])
        self.template_values['navbar'] = {'course_explorer': True}
        template = jinja_utils.get_template(
            '/modules/course_explorer/views/course_explorer.html', DIR, LOCALE)
        self.response.write(template.render(self.template_values))


class RegisteredCoursesHandler(BaseStudentHandler):
    """Handles registered courses view for a student."""

    def get(self):
        """Handles GET request."""
        self.initialize_page_and_get_user()
        courses = self.get_public_courses()
        enrolled_courses = self.get_enrolled_courses(courses)

        self.template_values['courses'] = enrolled_courses
        self.template_values['navbar'] = {'mycourses': True}
        self.template_values['can_enroll_more_courses'] = (
            len(courses) - len(enrolled_courses) > 0)
        template = jinja_utils.get_template(
            '/modules/course_explorer/views/course_explorer.html', DIR, LOCALE)
        self.response.write(template.render(self.template_values))


class AssetsHandler(webapp2.RequestHandler):
    """Handles asset file for the home page."""

    def get_mime_type(self, filename, default='application/octet-stream'):
        guess = mimetypes.guess_type(filename)[0]
        if guess is None:
            return default
        return guess

    def get(self, path):
        """Handles GET requests."""
        filename = '%s/assets/%s' % (appengine_config.BUNDLE_ROOT, path)
        with open(filename, 'r') as f:
            self.response.headers['Content-Type'] = self.get_mime_type(filename)
            self.response.write(f.read())
