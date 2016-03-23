# Copyright 2014 Google Inc. All Rights Reserved.
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

"""Module allowing manual marking of unit/lesson progress."""

__author__ = 'Mike Gainer (mgainer@google.com)'

import os

import jinja2

import appengine_config
from common import crypto
from common import tags
from common import utils as common_utils
from controllers import utils
from models import custom_modules
from models import progress
from models import transforms
from modules.courses import lessons

custom_module = None
MODULE_NAME = 'Manual Progress'
XSRF_ACTION = 'manual_progress'
TEMPLATES_DIR = os.path.join(
    appengine_config.BUNDLE_ROOT, 'modules', 'manual_progress', 'templates')
RESOURCES_PATH = '/modules/manual_progress/resources'

# pylint: disable=unbalanced-tuple-unpacking


class ProgressRESTBase(utils.BaseRESTHandler):

    def _perform_checks(self):
        success = False
        key = self.request.params.get('key')
        student = self.get_student()
        course = self.get_course()
        if not self.assert_xsrf_token_or_fail(
            self.request.params, XSRF_ACTION, {'key': key}):
            pass
        elif not key:
            transforms.send_json_response(
                self, 400, 'Bad Request.', {})
        elif not student or student.is_transient or not student.is_enrolled:
            transforms.send_json_response(
                self, 401, 'Access Denied.', {'key': key})
        elif not course:
            transforms.send_json_response(
                self, 400, 'Bad Request.', {'key': key})
        elif not self.app_context.is_editable_fs():
            transforms.send_json_response(
                self, 401, 'Access Denied.', {'key': key})
        else:
            success = True
        return success, key, student, course

    def _send_success_response(self, key, status):
        transforms.send_json_response(
            self, 200, 'OK.', {'key': key,
                               'status': status})


class CourseProgressRESTHandler(ProgressRESTBase):
    URI = '/rest/student/progress/course'

    def _perform_checks(self):
        _progress = None
        success, key, student, course = (
            super(CourseProgressRESTHandler, self)._perform_checks())
        if success:
            _progress = course.get_progress_tracker()

        return success, key, student, _progress

    def _send_success_response(self, key, student, _progress):
        super(CourseProgressRESTHandler, self)._send_success_response(
            key,
            _progress.get_course_status(
                _progress.get_or_create_progress(student)))

    def get(self):
        success, key, student, _progress = self._perform_checks()
        if success:
            self._send_success_response(key, student, _progress)

    def post(self):
        success, key, student, _progress = self._perform_checks()
        if success:
            _progress.force_course_completed(student)
            self._send_success_response(key, student, _progress)


class UnitProgressRESTHandler(ProgressRESTBase):
    URI = '/rest/student/progress/unit'

    def _perform_checks(self):
        unit = None
        _progress = None
        success, key, student, course = (
            super(UnitProgressRESTHandler, self)._perform_checks())
        if success:
            _progress = course.get_progress_tracker()
            unit = course.find_unit_by_id(key)
            if not unit:
                success = False
                transforms.send_json_response(
                    self, 400, 'Bad Request.', {'key': key})
        return success, key, student, unit, _progress

    def _send_success_response(self, key, student, unit, _progress):
        super(UnitProgressRESTHandler, self)._send_success_response(
            key,
            _progress.get_unit_status(
                _progress.get_or_create_progress(student),
                unit.unit_id))

    def get(self):
        success, key, student, unit, _progress = self._perform_checks()
        if success:
            self._send_success_response(key, student, unit, _progress)

    def post(self):
        success, key, student, unit, _progress = self._perform_checks()
        if success:
            if not unit.manual_progress:
                success = False
                transforms.send_json_response(
                    self, 401, 'Access Denied.', {'key': key})
            else:
                _progress.force_unit_completed(student, unit.unit_id)
                self._send_success_response(key, student, unit, _progress)


class LessonProgressRESTHandler(ProgressRESTBase):
    URI = '/rest/student/progress/lesson'

    def _perform_checks(self):
        lesson = None
        _progress = None
        success, key, student, course = (
            super(LessonProgressRESTHandler, self)._perform_checks())
        if success:
            _progress = course.get_progress_tracker()
            lesson = common_utils.find(lambda l: str(l.lesson_id) == key,
                                       course.get_lessons_for_all_units())
            if not lesson:
                success = False
                transforms.send_json_response(
                    self, 400, 'Bad Request.', {'key': key})
        return success, key, student, lesson, _progress

    def _send_success_response(self, key, student, lesson, _progress):
        super(LessonProgressRESTHandler, self)._send_success_response(
            key,
            _progress.get_lesson_status(
                _progress.get_or_create_progress(student),
                lesson.unit_id,
                lesson.lesson_id))

    def get(self):
        success, key, student, lesson, _progress = self._perform_checks()
        if success:
            self._send_success_response(key, student, lesson, _progress)

    def post(self):
        success, key, student, lesson, _progress = self._perform_checks()
        if success:
            if not lesson.manual_progress:
                success = False
                transforms.send_json_response(
                    self, 401, 'Access Denied.', {'key': key})
            else:
                _progress.put_html_completed(
                    student, lesson.unit_id, lesson.lesson_id)
                self._send_success_response(key, student, lesson, _progress)


def _build_completion_button_for_unit_lesson_page(
        app_context, course, unit, lesson, assessment, student_view, student):
    return _build_completion_button(app_context, course, student, unit, lesson)


def _build_completion_button_for_course_page(
        app_context, course, student_view, student):
    return _build_completion_button(app_context, course, student, None, None)


def _build_completion_button(app_context, course, student, unit, lesson):
    """Add manual-completion buttons to footer of syllabus/unit/lesson pages."""

    if not student or student.is_transient:
        return None

    xsrf_token = crypto.XsrfTokenManager.create_xsrf_token(XSRF_ACTION)
    template_data = {}

    # Course force-completion is coded and working, but there's no
    # UI/UX that cares about it in the base code.  This is left here as
    # a convenience, in case some particular course needs to have manual
    # course completion.  The general course won't, so we suppress this
    # button from appearing on all course content pages.
    #
    #template_data['course'] = {
    #    'url': CourseProgressRESTHandler.URI.lstrip('/'),
    #    'key': None,
    #    'xsrf_token': xsrf_token,
    #}
    tracker = None
    _progress = None
    COMPLETED_STATE = progress.UnitLessonCompletionTracker.COMPLETED_STATE
    if (unit and unit.manual_progress) or (lesson and lesson.manual_progress):
        tracker = course.get_progress_tracker()
        _progress = tracker.get_or_create_progress(student)

    if unit and unit.manual_progress:
        if tracker.get_unit_status(
            _progress, unit.unit_id) != COMPLETED_STATE:
            template_data['unit'] = {
                'url': UnitProgressRESTHandler.URI.lstrip('/'),
                'key': str(unit.unit_id),
                'xsrf_token': xsrf_token,
            }

    if lesson and lesson.manual_progress:
        if tracker.get_lesson_status(
            _progress, lesson.unit_id, lesson.lesson_id) != COMPLETED_STATE:
            template_data['lesson'] = {
                'url': LessonProgressRESTHandler.URI.lstrip('/'),
                'key': str(lesson.lesson_id),
                'xsrf_token': xsrf_token,
            }

    if template_data:
        template_environ = app_context.get_template_environ(
            app_context.get_current_locale(), [TEMPLATES_DIR])
        return jinja2.Markup(
            template_environ.get_template('manual_progress.html').render(
                template_data))

    return None


def register_module():

    def notify_module_enabled():
        lessons.UnitHandler.EXTRA_CONTENT.append(
            _build_completion_button_for_unit_lesson_page)
        lessons.CourseHandler.EXTRA_CONTENT.append(
            _build_completion_button_for_course_page)

    global_routes = [
        (os.path.join(RESOURCES_PATH, 'js', '.*'), tags.JQueryHandler),
        (os.path.join(RESOURCES_PATH, '.*'), tags.ResourcesHandler)]
    namespaced_handlers = [
        (CourseProgressRESTHandler.URI, CourseProgressRESTHandler),
        (UnitProgressRESTHandler.URI, UnitProgressRESTHandler),
        (LessonProgressRESTHandler.URI, LessonProgressRESTHandler),
        ]

    global custom_module  # pylint: disable=global-statement
    custom_module = custom_modules.Module(
        MODULE_NAME,
        'Manual marking of unit/lesson progress',
        global_routes, namespaced_handlers,
        notify_module_enabled=notify_module_enabled)
    return custom_module
