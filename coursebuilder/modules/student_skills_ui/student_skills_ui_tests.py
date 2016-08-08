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

import math
import urllib

from controllers import sites
from modules.student_skills_ui import student_skills_ui
from tests.functional import actions
from tests.integration import integration

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions


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

    ADMIN_EMAIL = 'admin@foo.com'
    COURSE_NAME = 'course_map_test'
    NAMESPACE = 'ns_%s' % COURSE_NAME

    def setUp(self):
        super(CourseMapArgsTestCase, self).setUp()

        if not student_skills_ui.custom_module.enabled:
            self.skipTest('Module not enabled')

        self.base = '/' + self.COURSE_NAME
        self.app_context = actions.simple_add_course(
            self.COURSE_NAME, self.ADMIN_EMAIL, 'Title')

    def tearDown(self):
        sites.reset_courses()
        super(CourseMapArgsTestCase, self).tearDown()

    def test_valid_args_returns_200(self):
        """Pass valid arguments and check for a 200 response."""
        url = _create_url()
        response = self.get(url)
        self.assertEqual(200, response.status_int)

        url = _create_url(x_value=100, y_value=100, scale_value=2.0)
        response = self.get(url)
        self.assertEqual(200, response.status_int)

    def test_invalid_args_returns_400_error(self):
        """Check for a 400 response for invalid arguments for each parameter."""
        url1 = _create_url(x_value=-400.0)
        response = self.get(url1, expect_errors=True)
        self.assertEqual(400, response.status_int)

        url2 = _create_url(y_value=200.0)
        response = self.get(url2, expect_errors=True)
        self.assertEqual(400, response.status_int)

        url3 = _create_url(scale_value='a')
        response = self.get(url3, expect_errors=True)
        self.assertEqual(400, response.status_int)


class CourseMapLayoutTestCase(integration.TestBase):
    """Tests for the layout locations of nodes in the course map page."""

    # Since our force-directed drawing is nondeterministic, we set an allowed
    # deviation of 5% between the location at which a graph is drawn and its
    # expected location.
    PERCENT_ERROR = 0.05

    def setUp(self):
        super(CourseMapLayoutTestCase, self).setUp()

        if not student_skills_ui.custom_module.enabled:
            self.skipTest('Module not enabled')

        self.course_name, self.course_title = self.create_new_course()
        self.base = '/' + self.course_name

    def tearDown(self):
        sites.reset_courses()
        super(CourseMapLayoutTestCase, self).tearDown()

    def _render_graph(self, x=0, y=0, scale=1):
        host = self.INTEGRATION_SERVER_BASE_URL
        url = _create_url(base=host+self.base, x_value=x, y_value=y,
                          scale_value=scale)
        self.driver.get(url)
        self._wait_for_graph()

        # Find the center of our graph, i.e., the average location of the nodes
        nodes = student_skills_ui.StudentSkillsUIHandler.FAKE_NODES
        avg_x = 0.0
        avg_y = 0.0
        for node in nodes:
            page_node = self.driver.find_element_by_class_name(
                'circle-%s' % node['id'])
            avg_x += page_node.location['x']
            avg_y += page_node.location['y']
        avg_x /= len(nodes)
        avg_y /= len(nodes)

        # Get window size
        window_size = self.driver.get_window_size()
        width = window_size['width']
        height = window_size['height']

        # Compare the average location of our nodes to the expected location
        expected_x = width / 2 + x
        expected_y = height / 2 + y
        x_diff_frac = math.fabs(expected_x - avg_x) / width
        y_diff_frac = math.fabs(expected_y - avg_y) / height

        self.assertLess(x_diff_frac, self.PERCENT_ERROR)
        self.assertLess(y_diff_frac, self.PERCENT_ERROR)

    def _wait_for_graph(self):
        # Our Javascript inserts a div with
        # id="cb-student-skills-nodule-end-layout" after the D3 layout sends an
        # end event. So we'll look for it until we time out.
        seconds_to_wait = 10
        element = WebDriverWait(self.driver, seconds_to_wait).until(
            expected_conditions.presence_of_element_located(
                (By.ID, 'cb-student-skills-module-end-layout')))

    def test_layout_locations(self):
        # Test that layout is centered when no arguments are given.
        self._render_graph()

        # Test shifting layout to the left and right.
        self._render_graph(x=200)

        # Test shifting layout by both coordinates simultaneously.
        self._render_graph(x=200, y=100)

        # Test that graph is still centered after being scaled.
        self._render_graph(scale=2)

        # Test that graph is shifted by the right distance when also scaled up.
        self._render_graph(x=200, y=-200, scale=3)

        # Test that graph is shifted by the right distance when also scaled
        # down.
        self._render_graph(x=-200, y=200, scale=0.5)
