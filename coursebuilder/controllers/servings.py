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


"""These handlers either serve cached pages or delegate to real handlers."""

from models.models import Student

import lessons
import utils
from utils import StudentHandler
from google.appengine.api import users


class CourseHandler(StudentHandler):
    """Handler for serving course page."""

    def get(self):
        student = self.get_enrolled_student()
        if student:
            page = self.get_or_create_page(
                'course_page', lessons.CourseHandler())
            self.serve(page, student.key().name())
        else:
            self.redirect('/preview')


class UnitHandler(StudentHandler):
    """Handler for serving class page."""

    def get(self):
        """Handles GET requests."""
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
        student = self.get_enrolled_student()
        if student:
            page = self.get_or_create_page(
                'lesson%s%s_page' % (class_id, lesson_id),
                lessons.UnitHandler())
            self.serve(page, student.key().name())
        else:
            self.redirect('/register')


class ActivityHandler(StudentHandler):
    """Handler for serving activity page."""

    def get(self):
        """Handles GET requests."""
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
        student = self.get_enrolled_student()
        if student:
            page = self.get_or_create_page(
                'activity%s%s_page' % (class_id, lesson_id),
                lessons.ActivityHandler())
            self.serve(page, student.key().name())
        else:
            self.redirect('/register')


class AssessmentHandler(StudentHandler):
    """Handler for serving assessment page."""

    def get(self):
        # Extract incoming args
        n = self.request.get('name')
        if not n:
            n = 'Pre'
        name = n

        # Check for enrollment status
        student = self.get_enrolled_student()
        if student:
            page = self.get_or_create_page(
                'assessment%s_page' % name, lessons.AssessmentHandler())
            self.serve(page, student.key().name())
        else:
            self.redirect('/register')


class ForumHandler(StudentHandler):
    """Handler for serving forum page."""

    def get(self):
        # Check for enrollment status
        student = self.get_enrolled_student()
        if student:
            page = self.get_or_create_page('forum_page', utils.ForumHandler())
            self.serve(page, student.key().name())
        else:
            self.redirect('/register')


class PreviewHandler(StudentHandler):
    """Handler for serving preview page."""

    def get(self):
        user = users.get_current_user()
        if user:
            if Student.get_enrolled_student_by_email(user.email()):
                self.redirect('/course')
            else:
                page = self.get_or_create_page(
                    'loggedin_preview_page', utils.CoursePreviewHandler())
                self.serve(page, user.email())
        else:
            page = self.get_or_create_page(
                'anonymous_preview_page', utils.CoursePreviewHandler())
            self.serve(page)
