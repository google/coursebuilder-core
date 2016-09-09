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
from common import schema_fields
from common import jinja_utils
from controllers import utils
from models import courses
from models import custom_modules
from models import transforms
from modules.skill_map import skill_map

TEMPLATE_DIR = os.path.join(
    appengine_config.BUNDLE_ROOT, 'modules', 'student_skills_ui', 'templates')


MODULE_NAME = 'student_skills_ui'
MODULE_TITLE = 'Student Skills UI'
SETTINGS_SCHEMA_SECTION_NAME = 'student_skills_ui'
SETTING_LOCAL_GRAPH_ENABLED = 'local_graph'

class StudentSkillsUIHandler(utils.BaseHandler):
    """Handles the visualization of the course map."""

    COURSE_MAP_PATH = 'course_map'
    X_NAME = 'x'
    Y_NAME = 'y'
    SCALE_NAME = 'scale'
    # We pass -1 as the default scale value so that the renderer knows to scale
    # the graph to fit in the window.
    DEFAULT_PARAMS = {X_NAME: 0, Y_NAME: 0, SCALE_NAME: -1}
    DEFAULT_COLOR = 'default_color'
    GREEN = '#00cc00'
    YELLOW = '#cccc00'
    GRAY = '#ccc'

    def get(self):
        try:
            self._parse_params()
        except ValueError:
            self.error(400)
            return

        self.personalize_page_and_get_user()
        self._set_required_template_values()

        nodes, links = self._load_graph_data(self.get_course())
        # If there are no nodes, we choose not to set these values, so that the
        # HTML page will display an error message instead of the usual graph.
        if len(nodes) > 0:
            self.template_value['nodes'] = transforms.dumps(nodes)
            self.template_value['links'] = transforms.dumps(links)

        self.render('course_map.html', [TEMPLATE_DIR])

    @classmethod
    def _load_graph_data(cls, course):
        nodes, links = skill_map.SkillMap.get_nodes_and_links(course)
        cls._set_node_colors(nodes, course)
        return nodes, links

    @classmethod
    def _set_node_colors(cls, nodes, course):
        student = cls.get_student()
        if not student:
            for n in nodes:
                n[cls.DEFAULT_COLOR] = cls.GRAY
        else:
            tracker = skill_map.SkillCompletionTracker(course)
            skill_progress_list = tracker.get_skills_progress(
                student, [node['id_num'] for node in nodes])
            for node in nodes:
                # skill_progress_list is a dictionary in which the keys are
                # skill id's, and the values are tuples containing the progress
                # status and the timestamp of the most recent update
                progress = skill_progress_list[node['id_num']][0]
                if progress == skill_map.SkillCompletionTracker.COMPLETED:
                    node[cls.DEFAULT_COLOR] = cls.GREEN
                elif progress == skill_map.SkillCompletionTracker.IN_PROGRESS:
                    node[cls.DEFAULT_COLOR] = cls.YELLOW
                else:
                    node[cls.DEFAULT_COLOR] = cls.GRAY

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
      enable_graph_setting = schema_fields.SchemaField(
          SETTINGS_SCHEMA_SECTION_NAME + ':' + SETTING_LOCAL_GRAPH_ENABLED,
          'Skill Graph in Course Content', 'boolean', optional=True,
          i18n=None)
      course_settings_fields = (
          lambda c: enable_graph_setting,
      )
      courses.Course.OPTIONS_SCHEMA_PROVIDERS[
          skill_map.MODULE_NAME] += course_settings_fields

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
