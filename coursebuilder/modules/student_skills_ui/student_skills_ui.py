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

"""Displays the graph of prerequisites for the course."""

__author__ = 'Timothy Johnson (tujohnson@google.com)'

import os

import jinja2

import appengine_config
from common import jinja_utils
from controllers import utils
from models import custom_modules
from models import transforms

TEMPLATE_DIR = os.path.join(
    appengine_config.BUNDLE_ROOT, 'modules', 'student_skills_ui', 'templates')


MODULE_NAME = 'student_skills_ui'
MODULE_TITLE = 'Student Skills UI'


class StudentSkillsUIHandler(utils.BaseHandler):
    """Handles the visualization of the course map."""

    COURSE_MAP_PATH = 'course_map'
    USE_FAKE_DATA_IN_COURSE_MAP = True
    FAKE_NODES = [{'id': 'Skill_1'}, {'id': 'Skill_2'}]
    FAKE_LINKS = [{'source': 0, 'target': 1}]
    X_NAME = 'x'
    Y_NAME = 'y'
    SCALE_NAME = 'scale'
    DEFAULT_PARAMS = {X_NAME: 0, Y_NAME: 0, SCALE_NAME: 1}

    def get(self):
        try:
            self._parse_params()
        except ValueError:
            self.error(400)
            return

        self.personalize_page_and_get_user()
        self._set_required_template_values()
        self._load_graph_data()
        self.render('course_map.html', [TEMPLATE_DIR])

    def _load_graph_data(self):
        if self.USE_FAKE_DATA_IN_COURSE_MAP:
            self.template_value['nodes'] = transforms.dumps(self.FAKE_NODES)
            self.template_value['links'] = transforms.dumps(self.FAKE_LINKS)
        else:
            # TODO(tujohnson): Acquire actual course skill map
            pass

    def _parse_params(self):
        """Parses the URL parameters for x, y, and scale values.

        Raises:
          ValueError: if one of the parameters is not of the correct type.
        """

        # First set our default values for each parameter we look for
        raw_x = self.request.get(self.X_NAME, self.DEFAULT_PARAMS[self.X_NAME])
        raw_y = self.request.get(self.Y_NAME, self.DEFAULT_PARAMS[self.Y_NAME])
        raw_scale = self.request.get(self.SCALE_NAME,
                                     self.DEFAULT_PARAMS[self.SCALE_NAME])

        self.template_value[self.X_NAME] = int(raw_x)
        self.template_value[self.Y_NAME] = int(raw_y)
        self.template_value[self.SCALE_NAME] = float(raw_scale)

    def _set_required_template_values(self):
        """Set values required to extend base_course.html."""
        self.template_value['navbar'] = {'course_map': True}


def course_page_navbar_callback(app_context):
    """Loads the link for the navbar."""
    template = jinja_utils.get_template('course_map_navbar.html',
                                        [TEMPLATE_DIR])
    return [jinja2.utils.Markup(template.render())]


custom_module = None

def register_module():
    """Registers this module in the registry."""
    def on_module_enabled():
        # Register "Skill map" element on navbar.
        utils.CourseHandler.LEFT_LINKS.append(course_page_navbar_callback)

    global custom_module   # pylint: disable=global-statement

    namespaced_routes = [('/' + StudentSkillsUIHandler.COURSE_MAP_PATH,
                          StudentSkillsUIHandler)]

    custom_module = custom_modules.Module(
        MODULE_TITLE,
        'A page to show student progress through the course skills map.',
        global_routes=[],
        namespaced_routes=namespaced_routes,
        notify_module_enabled=on_module_enabled
    )
    return custom_module
