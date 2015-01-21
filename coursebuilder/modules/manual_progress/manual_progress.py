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

from common import utils as common_utils
from controllers import utils
from models import custom_modules
from models import transforms

custom_module = None
MODULE_NAME = 'Manual Progress'
XSRF_ACTION = 'manual_progress'

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
        progress = None
        success, key, student, course = (
            super(CourseProgressRESTHandler, self)._perform_checks())
        if success:
            progress = course.get_progress_tracker()

        return success, key, student, progress

    def _send_success_response(self, key, student, progress):
        super(CourseProgressRESTHandler, self)._send_success_response(
            key,
            progress.get_course_status(
                progress.get_or_create_progress(student)))

    def get(self):
        success, key, student, progress = self._perform_checks()
        if success:
            self._send_success_response(key, student, progress)

    def post(self):
        success, key, student, progress = self._perform_checks()
        if success:
            progress.force_course_completed(student)
            self._send_success_response(key, student, progress)


class UnitProgressRESTHandler(ProgressRESTBase):
    URI = '/rest/student/progress/unit'

    def _perform_checks(self):
        unit = None
        progress = None
        success, key, student, course = (
            super(UnitProgressRESTHandler, self)._perform_checks())
        if success:
            progress = course.get_progress_tracker()
            unit = course.find_unit_by_id(key)
            if not unit:
                success = False
                transforms.send_json_response(
                    self, 400, 'Bad Request.', {'key': key})
        return success, key, student, unit, progress

    def _send_success_response(self, key, student, unit, progress):
        super(UnitProgressRESTHandler, self)._send_success_response(
            key,
            progress.get_unit_status(
                progress.get_or_create_progress(student),
                unit.unit_id))

    def get(self):
        success, key, student, unit, progress = self._perform_checks()
        if success:
            self._send_success_response(key, student, unit, progress)

    def post(self):
        success, key, student, unit, progress = self._perform_checks()
        if success:
            if not unit.manual_progress:
                success = False
                transforms.send_json_response(
                    self, 401, 'Access Denied.', {'key': key})
            else:
                progress.force_unit_completed(student, unit.unit_id)
                self._send_success_response(key, student, unit, progress)


class LessonProgressRESTHandler(ProgressRESTBase):
    URI = '/rest/student/progress/lesson'

    def _perform_checks(self):
        lesson = None
        progress = None
        success, key, student, course = (
            super(LessonProgressRESTHandler, self)._perform_checks())
        if success:
            progress = course.get_progress_tracker()
            lesson = common_utils.find(lambda l: str(l.lesson_id) == key,
                                       course.get_lessons_for_all_units())
            if not lesson:
                success = False
                transforms.send_json_response(
                    self, 400, 'Bad Request.', {'key': key})
        return success, key, student, lesson, progress

    def _send_success_response(self, key, student, lesson, progress):
        super(LessonProgressRESTHandler, self)._send_success_response(
            key,
            progress.get_lesson_status(
                progress.get_or_create_progress(student),
                lesson.unit_id,
                lesson.lesson_id))

    def get(self):
        success, key, student, lesson, progress = self._perform_checks()
        if success:
            self._send_success_response(key, student, lesson, progress)

    def post(self):
        success, key, student, lesson, progress = self._perform_checks()
        if success:
            if not lesson.manual_progress:
                success = False
                transforms.send_json_response(
                    self, 401, 'Access Denied.', {'key': key})
            else:
                progress.put_html_completed(
                    student, lesson.unit_id, lesson.lesson_id)
                self._send_success_response(key, student, lesson, progress)


def register_module():
    namespaced_handlers = [
        (CourseProgressRESTHandler.URI, CourseProgressRESTHandler),
        (UnitProgressRESTHandler.URI, UnitProgressRESTHandler),
        (LessonProgressRESTHandler.URI, LessonProgressRESTHandler),
        ]

    global custom_module  # pylint: disable=global-statement
    custom_module = custom_modules.Module(
        MODULE_NAME,
        'Manual marking of unit/lesson progress',
        [], namespaced_handlers)
    return custom_module
