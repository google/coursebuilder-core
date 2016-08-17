# Copyright 2016 Google Inc. All Rights Reserved.
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

"""Tests for modules/student_skills_ui/."""

__author__ = 'Timothy Johnson (tujohnson@google.com)'

import urllib
import time

from controllers import sites
from models import courses
from models import models
from models import transforms
from modules.student_skills_ui import student_skills_ui
from modules.skill_map import skill_map
from tests.functional import actions

from google.appengine.api import namespace_manager


ADMIN_EMAIL = 'admin@foo.com'
COURSE_NAME = 'course_map_test'


def _create_url(base='', x_value=None, y_value=None, scale_value=None):
    handler_class = student_skills_ui.StudentSkillsUIHandler
    course_map_url = handler_class.COURSE_MAP_PATH
    x_name = handler_class.X_NAME
    y_name = handler_class.Y_NAME
    scale_name = handler_class.SCALE_NAME

    args = {}
    if x_value is not None:
        args[x_name] = x_value
    if y_value is not None:
        args[y_name] = y_value
    if scale_value is not None:
        args[scale_name] = scale_value

    arg_str = '' if not args else '?%s' % urllib.urlencode(args)
    url = '%s/%s%s' % (base, course_map_url, arg_str)
    return url


class CourseMapArgsTestCase(actions.TestBase):
    """Tests that URL parameters for our course map are validated."""

    def setUp(self):
        super(CourseMapArgsTestCase, self).setUp()

        if not student_skills_ui.custom_module.enabled:
            self.skipTest('Module not enabled')

        self.base = '/' + COURSE_NAME
        self.app_context = actions.simple_add_course(
            COURSE_NAME, ADMIN_EMAIL, 'Title')
        self.old_namespace = namespace_manager.get_namespace()
        namespace_manager.set_namespace('ns_%s' % COURSE_NAME)
        self.course = courses.Course(None, self.app_context)

    def tearDown(self):
        del sites.Registry.test_overrides[sites.GCB_COURSES_CONFIG.name]
        namespace_manager.set_namespace(self.old_namespace)
        super(CourseMapArgsTestCase, self).tearDown()

    def test_valid_args_returns_200(self):
        """Pass valid arguments and check for a 200 response."""
        actions.login(ADMIN_EMAIL)
        url = _create_url(base=self.base)
        response = self.get(url)
        self.assertEqual(200, response.status_int)

        url = _create_url(base=self.base, x_value=100, y_value=100,
                          scale_value=2.0)
        response = self.get(url)
        self.assertEqual(200, response.status_int)

    def test_invalid_args_returns_400_error(self):
        """Check for a 400 response for invalid arguments for each parameter."""
        actions.login(ADMIN_EMAIL)
        url1 = _create_url(base=self.base, x_value=-400.0)
        response = self.get(url1, expect_errors=True)
        self.assertEqual(400, response.status_int)

        url2 = _create_url(base=self.base, y_value=200.0)
        response = self.get(url2, expect_errors=True)
        self.assertEqual(400, response.status_int)

        url3 = _create_url(base=self.base, scale_value='a')
        response = self.get(url3, expect_errors=True)
        self.assertEqual(400, response.status_int)

class CourseMapColorsTestCase(actions.TestBase):
    """Tests the colors that appear in our HTML."""

    STUDENT_EMAIL = 'student@example.com'
    STUDENT_NAME = 'John Smith'

    def setUp(self):
        super(CourseMapColorsTestCase, self).setUp()

        if not student_skills_ui.custom_module.enabled:
            self.skipTest('Module not enabled')

        self.base = '/' + COURSE_NAME
        self.app_context = actions.simple_add_course(
            COURSE_NAME, ADMIN_EMAIL, 'Title')
        self.old_namespace = namespace_manager.get_namespace()
        namespace_manager.set_namespace('ns_%s' % COURSE_NAME)
        self.course = courses.Course(None, self.app_context)
        self.course.set_course_availability(
            courses.COURSE_AVAILABILITY_REGISTRATION_REQUIRED)

        self._add_graph()
        self._get_colors()

    def tearDown(self):
        del sites.Registry.test_overrides[sites.GCB_COURSES_CONFIG.name]
        namespace_manager.set_namespace(self.old_namespace)
        super(CourseMapColorsTestCase, self).tearDown()

    def _add_graph(self):
        skill_graph = skill_map.SkillGraph.load()
        self.skill_node = skill_graph.add(skill_map.Skill.build('a', ''))

    def _get_colors(self):
        self.gray = student_skills_ui.StudentSkillsUIHandler.GRAY
        self.yellow = student_skills_ui.StudentSkillsUIHandler.YELLOW
        self.green = student_skills_ui.StudentSkillsUIHandler.GREEN

    def _login_and_register(self):
        user = actions.login(self.STUDENT_EMAIL)
        actions.register(self, self.STUDENT_NAME)
        self.student = models.Student.get_enrolled_student_by_user(user)

    def _mark_skill_in_progress(self):
        progress = models.StudentPropertyEntity.create(
            student=self.student,
            property_name=skill_map.SkillCompletionTracker.PROPERTY_KEY)
        skill_in_progress = {self.skill_node.id: {
            skill_map.SkillCompletionTracker.IN_PROGRESS: time.time() - 100}}
        progress.value = transforms.dumps(skill_in_progress)
        progress.put()

    def _mark_skill_completed(self):
        progress = models.StudentPropertyEntity.create(
            student=self.student,
            property_name=skill_map.SkillCompletionTracker.PROPERTY_KEY)
        skill_completed = {self.skill_node.id: {
            skill_map.SkillCompletionTracker.COMPLETED: time.time() - 100}}
        progress.value = transforms.dumps(skill_completed)
        progress.put()

    def test_gray_appears_for_transient_student(self):
        url = _create_url(base=self.base)
        response = self.get(url)
        self._check_div_color(response, self.skill_node, self.gray)

    def test_gray_appears_for_skill_not_started(self):
        self._login_and_register()
        url = _create_url(base=self.base)
        response = self.get(url)
        self._check_div_color(response, self.skill_node, self.gray)

    def test_yellow_appears_for_skill_in_progress(self):
        self._login_and_register()
        self._mark_skill_in_progress()
        url = _create_url(base=self.base)
        response = self.get(url)
        self._check_div_color(response, self.skill_node, self.yellow)

    def test_green_appears_for_completed_skill(self):
        self._login_and_register()
        self._mark_skill_completed()
        url = _create_url(base=self.base)
        response = self.get(url)
        self._check_div_color(response, self.skill_node, self.green)

    def _check_div_color(self, response, skill_node, color):
        html_soup = self.parse_html_string_to_soup(str(response.html))
        node_div = html_soup.find('div', {'class': 'graph'})
        node_attrs = transforms.loads(node_div.attrs['data-nodes'])
        color_field = student_skills_ui.StudentSkillsUIHandler.DEFAULT_COLOR
        self.assertEquals(1, len(node_attrs))
        self.assertEquals(skill_node.name, node_attrs[0]['id'])
        self.assertEquals(color, node_attrs[0][color_field])
