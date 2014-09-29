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

"""Tests for modules/courses/."""

__author__ = 'Glenn De Jonghe (gdejonghe@google.com)'

import actions
from models import courses
from models import models
from modules.courses import courses as courses_module

from google.appengine.api import namespace_manager


class AccessDraftsTestCase(actions.TestBase):
    COURSE_NAME = 'draft_access'
    ADMIN_EMAIL = 'admin@foo.com'
    USER_EMAIL = 'user@foo.com'
    ROLE = 'test_role'
    ACTION = 'test_action'

    def setUp(self):
        super(AccessDraftsTestCase, self).setUp()
        actions.login(self.ADMIN_EMAIL, is_admin=True)
        self.base = '/' + self.COURSE_NAME
        self.context = actions.simple_add_course(
            self.COURSE_NAME, self.ADMIN_EMAIL, 'Access Draft Testing')

        self.course = courses.Course(None, self.context)

        self.old_namespace = namespace_manager.get_namespace()
        namespace_manager.set_namespace('ns_%s' % self.COURSE_NAME)

        role_dto = models.RoleDTO(None, {
            'name': self.ROLE,
            'users': [self.USER_EMAIL],
            'permissions': {
                courses_module.custom_module.name: [
                courses_module.SEE_DRAFTS_PERMISSION]
            }
        })
        models.RoleDAO.save(role_dto)
        actions.logout()

    def tearDown(self):
        namespace_manager.set_namespace(self.old_namespace)
        super(AccessDraftsTestCase, self).tearDown()

    def test_access_assessment(self):
        assessment = self.course.add_assessment()
        assessment.is_draft = True
        self.course.save()
        self.assertEquals(
            self.get('assessment?name=%s' % assessment.unit_id).status_int, 302)
        actions.login(self.USER_EMAIL, is_admin=False)
        self.assertEquals(
            self.get('assessment?name=%s' % assessment.unit_id).status_int, 200)
        actions.logout()

    def test_access_lesson(self):
        unit = self.course.add_unit()
        unit.is_draft = True
        lesson = self.course.add_lesson(unit)
        lesson.is_draft = True
        self.course.save()
        self.assertEquals(
            self.get('unit?unit=%s&lesson=%s' % (
            unit.unit_id, lesson.lesson_id)).status_int, 302)
        actions.login(self.USER_EMAIL, is_admin=False)
        self.assertEquals(
            self.get('unit?unit=%s&lesson=%s' % (
            unit.unit_id, lesson.lesson_id)).status_int, 200)
        actions.logout()
