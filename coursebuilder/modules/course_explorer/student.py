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
import os
import webapp2

from google.appengine.ext import db

import appengine_config
from common import jinja_utils
from common import users
from controllers import sites
from controllers import utils
from models import courses as models_courses
from models import models
from models import roles
from models import transforms
import course_explorer

# We want to use views file in both /views and /modules/course_explorer/views.
TEMPLATE_DIRS = [
    os.path.join(appengine_config.BUNDLE_ROOT, 'views'),
    os.path.join(
        appengine_config.BUNDLE_ROOT, 'modules', 'course_explorer', 'views'),
]

STUDENT_RENAME_GLOBAL_XSRF_TOKEN_ID = 'rename-student-global'

# Int. Maximum number of bytes App Engine's db.StringProperty can store.
_STRING_PROPERTY_MAX_BYTES = 500


class BaseStudentHandler(webapp2.RequestHandler):
    """Base Handler for a student's courses."""

    def __init__(self, *args, **kwargs):
        super(BaseStudentHandler, self).__init__(*args, **kwargs)
        self.template_values = {}
        self.enrolled_namespaces = []
        self.courses_progress_dict = {}

        utils.PageInitializerService.get().initialize(self.template_values)
        user = users.get_current_user()
        if not user:
            return

        self.enrolled_namespaces = self.get_enrolled_namespaces()
        self.template_values['has_enrolled_courses'] = bool(
            self.enrolled_namespaces)

        profile = models.StudentProfileDAO.get_profile_by_user_id(
            user.user_id())
        if profile and profile.course_info:
            self.courses_progress_dict = transforms.loads(profile.course_info)

    def get_locale_for_user(self):
        """Chooses locale for a user."""
        return 'en_US'  # TODO(psimakov): choose proper locale from profile

    def is_enrolled(self, course):
        """Returns true if student is enrolled else false."""
        return course.get_namespace_name() in self.enrolled_namespaces

    def is_completed(self, course):
        """Returns true if student has completed course else false."""
        info = self.courses_progress_dict.get(course.get_namespace_name())
        return info and 'final_grade' in info

    def can_register(self, course):
        return course.get_environ()['reg_form']['can_register']

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
        info['course']['course_progress_url'] = (
            course_preview_url + '/student/home')
        info['course']['is_registered'] = self.is_enrolled(course)
        info['course']['is_completed'] = self.is_completed(course)
        info['course']['can_register'] = self.can_register(course)
        return info

    def get_enrolled_namespaces(self):
        user_id = users.get_current_user().user_id()
        return [
            student.key().namespace() for student in db.get([
                db.Key.from_path(
                    'Student', user_id, namespace=course.get_namespace_name())
                for course in sites.get_all_courses()])
            if student and student.is_enrolled]

    def get_enrolled_courses(self):
        """Returns a list of courses that the student is enrolled in."""
        return [
            self.get_course_info(course)
            for course in sites.get_visible_courses()
            if course.get_namespace_name() in self.enrolled_namespaces]

    def initialize_page_and_get_user(self):
        """Add basic fields to template and return user."""
        self.template_values['course_info'] = (
            models_courses.COURSE_TEMPLATE_DICT)
        self.template_values['course_info']['course'] = {
            'locale': self.get_locale_for_user()}
        self.template_values['page_locale'] = 'en'
        user = users.get_current_user()
        if not user:
            self.template_values['loginUrl'] = users.create_login_url('/')
        else:
            self.template_values['email'] = user.email()
            self.template_values[
                'is_super_admin'] = roles.Roles.is_super_admin()
            self.template_values['logoutUrl'] = users.create_logout_url('/')
        return user


class NullHtmlHooks(object):
    """Provide a non-null callback object for pages asking for hooks.

    In contexts where we have no single course to use to determine
    hook contents, we simply return blank content.
    """

    def insert(self, unused_name):
        return ''


class AllCoursesHandler(BaseStudentHandler):
    """Handles list of courses that can be viewed by a student."""

    def get(self):
        """Handles GET requests."""
        if not course_explorer.GCB_ENABLE_COURSE_EXPLORER_PAGE.value:
            self.error(404)
            return

        self.initialize_page_and_get_user()
        self.template_values['courses'] = [
            self.get_course_info(course)
            for course in sites.get_visible_courses()]
        self.template_values['navbar'] = {'course_explorer': True}
        self.template_values['html_hooks'] = NullHtmlHooks()
        template = jinja_utils.get_template(
            'course_explorer.html', TEMPLATE_DIRS)
        self.response.write(template.render(self.template_values))


class IndexPageHandler(BaseStudentHandler, utils.QueryableRouteMixin):
    """Handles registered courses view for a student."""

    @classmethod
    def can_handle_route_method_path_now(cls, route, method, path):
        return course_explorer.GCB_ENABLE_COURSE_EXPLORER_PAGE.value

    def get(self):
        """Handles GET request."""

        if not course_explorer.GCB_ENABLE_COURSE_EXPLORER_PAGE.value:
            self.error(404)
            return

        self.initialize_page_and_get_user()
        if not self.enrolled_namespaces:
            self.redirect('/explorer')
            return

        self.template_values['courses'] = self.get_enrolled_courses()
        self.template_values['navbar'] = {'mycourses': True}
        self.template_values['html_hooks'] = NullHtmlHooks()
        template = jinja_utils.get_template(
            'course_explorer.html', TEMPLATE_DIRS)
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
        if not course_explorer.GCB_ENABLE_COURSE_EXPLORER_PAGE.value:
            self.error(404)
            return

        filename = '%s/assets/%s' % (appengine_config.BUNDLE_ROOT, path)
        with open(filename, 'r') as f:
            self.response.headers[
                'Content-Type'] = self.get_mime_type(filename)
            self.response.write(f.read())
