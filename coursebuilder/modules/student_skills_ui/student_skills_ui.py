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
from models import courses
from models import custom_modules
from models import models
from models import transforms
from modules.skill_map import skill_map

TEMPLATES_DIR = os.path.join(
    appengine_config.BUNDLE_ROOT, 'modules', 'student_skills_ui', 'templates')


MODULE_NAME = 'student_skills_ui'
MODULE_TITLE = 'Student Skills UI'
SETTINGS_SCHEMA_SECTION_NAME = 'student_skills_ui'
SETTING_LOCAL_GRAPH_ENABLED = 'local_graph'
SKILLS_SHOW_SKILL_GRAPH_DESCRIPTION = """
Show graph of related skills on each lesson page
"""

def get_node_data(course, my_skill_map, skill, student):
    node = {'id': skill.name, 'skill': skill}
    node['progress'] = get_student_progress(course,
        my_skill_map, skill, student)
    return node


def get_student_progress(course, my_skill_map, skill, student):
    if isinstance(student, models.TransientStudent):
        return 'no_progress'
    else:
        tracker = skill_map.SkillCompletionTracker(course)
        progress_dict = tracker.get_skills_progress(student, [skill.id])

        # The keys in our dictionary are skill id's, and the values are tuples
        # containing the progress status and the timestamp of the most recent
        # update.
        progress = progress_dict[skill.id][0]
        if progress == skill_map.SkillCompletionTracker.COMPLETED:
            return 'completed'
        elif progress == skill_map.SkillCompletionTracker.IN_PROGRESS:
            return 'in_progress'
        else:
            return 'no_progress'


def add_header_diagrams(handler, app_context, unit, lesson, student):
    # Make sure that checkbox in Skills dashboard section is checked
    env = courses.Course.get_environ(app_context)
    if SETTINGS_SCHEMA_SECTION_NAME not in env:
        return None
    if not env[SETTINGS_SCHEMA_SECTION_NAME].get(SETTING_LOCAL_GRAPH_ENABLED):
        return None

    if isinstance(student, models.TransientStudent):
        my_skill_map = skill_map.SkillMap.load(handler.get_course())
    else:
        my_skill_map = skill_map.SkillMap.load(
            handler.get_course(), user_id=student.user_id)
    skills = my_skill_map.get_skills_for_lesson(lesson.lesson_id)
    skills_set = set(skills) # We convert this to a set for O(1) lookup time.

    course = handler.get_course()
    nodes = [get_node_data(course, my_skill_map, skill, student)
             for skill in skills]
    edges = []
    for node in nodes:
        node['highlight'] = True

    for index in xrange(len(skills)):
        skill = skill_map.filter_visible_lessons(handler, student,
                                                 skills[index])

        prerequisites = skill.prerequisites
        for prereq_skill in prerequisites:
            if prereq_skill not in skills_set:
                # Add 0-based link index. The source is the node that's about to
                # be placed at the end, and the target is the one at the current
                # index.
                edges.append({'source': len(nodes), 'target': index})
                nodes.append(get_node_data(course, my_skill_map, prereq_skill,
                                           student))

        successors = my_skill_map.successors(skill)
        for succ_skill in successors:
            if succ_skill not in skills_set:
                # Add 0-based link index. The source is the node at the current
                # index, and the target is the one that's about to be placed at
                # the end.
                edges.append({'source': index, 'target': len(nodes)})
                nodes.append(get_node_data(course, my_skill_map, succ_skill,
                                           student))

    template_values = {'nodes': transforms.dumps(nodes),
                       'edges': transforms.dumps(edges)}

    title = 'Skill graph'
    content = jinja2.Markup(
    handler.get_template('unit_header.html', [TEMPLATES_DIR]
        ).render(template_values))

    return {'title': title, 'content': content}


custom_module = None

def register_module():
    """Registers this module in the registry."""
    def on_module_enabled():
        enable_graph_setting = schema_fields.SchemaField(
            SETTINGS_SCHEMA_SECTION_NAME + ':' + SETTING_LOCAL_GRAPH_ENABLED,
            'Skill Graph in Course Content', 'boolean',
            optional=True, i18n=None,
            description=SKILLS_SHOW_SKILL_GRAPH_DESCRIPTION)
        course_settings_fields = (
            lambda c: enable_graph_setting,
        )
        courses.Course.OPTIONS_SCHEMA_PROVIDERS[
            skill_map.MODULE_NAME] += course_settings_fields

        # Add to header on unit pages
        skill_map.HEADER_CALLBACKS['skill-diagram'] = add_header_diagrams

    global custom_module   # pylint: disable=global-statement

    custom_module = custom_modules.Module(
        MODULE_TITLE,
        'A page to show student progress through the course skills map.',
        global_routes=[],
        namespaced_routes=[],
        notify_module_enabled=on_module_enabled
    )
    return custom_module

