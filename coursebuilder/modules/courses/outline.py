# Copyright 2015 Google Inc. All Rights Reserved.
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

"""Display course outline on dashboard page."""

__author__ = 'Pavel Simakov (psimakov@google.com)'

import os
import urllib

import jinja2

from common import safe_dom
from models import courses
from models import custom_units
from models import resources_display
from modules.dashboard import dashboard
from modules.dashboard import unit_lesson_editor
from modules.dashboard import utils as dashboard_utils
from tools import verify

# A list of functions which are used to generate extra info about a lesson
# or unit in the course outline view. Modules which can provide extra info
# should add a function to this list which accepts a course and a lesson or
# unit as argument and returns a safe_dom NodeList or Node.
COURSE_OUTLINE_EXTRA_INFO_ANNOTATORS = []

# Modules adding extra info annotators (above) may also add a string to this
# list which will be displayed at a heading in the course outline table.
COURSE_OUTLINE_EXTRA_INFO_TITLES = []


def _render_status_icon(handler, resource, key, component_type):
    if not hasattr(resource, 'now_available'):
        return
    icon = safe_dom.Element(
        'div', data_key=str(key), data_component_type=component_type)
    common_classes = 'row-hover icon icon-draft-status md'
    if not handler.app_context.is_editable_fs():
        common_classes += ' inactive'
    if resource.now_available:
        icon.add_attribute(
            alt=resources_display.PUBLISHED_TEXT,
            title=resources_display.PUBLISHED_TEXT,
            className=common_classes + ' md-lock-open',
        )
    else:
        icon.add_attribute(
            alt=resources_display.DRAFT_TEXT,
            title=resources_display.DRAFT_TEXT,
            className=common_classes + ' md-lock'
        )
    return icon

def _render_assessment_outline(handler, unit):
    actions = []
    unit_data = {
        'title': unit.title,
        'class': 'assessment',
        'href': 'assessment?name=%s' % unit.unit_id,
        'unit_id': unit.unit_id,
        'actions': actions
    }

    actions.append(_render_status_icon(handler, unit, unit.unit_id, 'unit'))
    if handler.app_context.is_editable_fs():
        url = handler.canonicalize_url(
            '/dashboard?%s') % urllib.urlencode({
                'action': 'edit_assessment',
                'key': unit.unit_id})
        actions.append(dashboard_utils.create_edit_button(url))

    return unit_data

def _render_link_outline(handler, unit):
    actions = []
    unit_data = {
        'title': unit.title,
        'class': 'link',
        'href': unit.href or '',
        'unit_id': unit.unit_id,
        'actions': actions
    }
    actions.append(_render_status_icon(handler, unit, unit.unit_id, 'unit'))
    if handler.app_context.is_editable_fs():
        url = handler.canonicalize_url(
            '/dashboard?%s') % urllib.urlencode({
                'action': 'edit_link',
                'key': unit.unit_id})
        actions.append(dashboard_utils.create_edit_button(url))
    return unit_data

def _render_custom_unit_outline(handler, unit):
    actions = []
    unit_data = {
        'title': unit.title,
        'class': 'custom-unit',
        'href': unit.custom_unit_url,
        'unit_id': unit.unit_id,
        'actions': actions
    }
    actions.append(_render_status_icon(handler, unit, unit.unit_id, 'unit'))
    if handler.app_context.is_editable_fs():
        url = handler.canonicalize_url(
            '/dashboard?%s') % urllib.urlencode({
                'action': 'edit_custom_unit',
                'key': unit.unit_id,
                'unit_type': unit.custom_unit_type})
        actions.append(dashboard_utils.create_edit_button(url))
    return unit_data

def _render_unit_outline(handler, course, unit):
    is_editable = handler.app_context.is_editable_fs()

    actions = []
    unit_data = {
        'title': unit.title,
        'class': 'unit',
        'href': 'unit?unit=%s' % unit.unit_id,
        'unit_id': unit.unit_id,
        'actions': actions
    }

    actions.append(_render_status_icon(handler, unit, unit.unit_id, 'unit'))
    if is_editable:
        url = handler.canonicalize_url(
            '/dashboard?%s') % urllib.urlencode({
                'action': 'edit_unit',
                'key': unit.unit_id})
        actions.append(dashboard_utils.create_edit_button(url))

    if unit.pre_assessment:
        assessment = course.find_unit_by_id(unit.pre_assessment)
        if assessment:
            assessment_outline = _render_assessment_outline(handler, assessment)
            assessment_outline['class'] = 'pre-assessment'
            unit_data['pre_assessment'] = assessment_outline

    lessons = []
    for lesson in course.get_lessons(unit.unit_id):
        actions = []
        actions.append(
            _render_status_icon(handler, lesson, lesson.lesson_id, 'lesson'))
        if is_editable:
            url = handler.get_action_url(
                'edit_lesson', key=lesson.lesson_id)
            actions.append(dashboard_utils.create_edit_button(url))

        extras = []
        for annotator in COURSE_OUTLINE_EXTRA_INFO_ANNOTATORS:
            extra_info = annotator(course, lesson)
            if extra_info:
                extras.append(extra_info)

        lessons.append({
            'title': lesson.title,
            'class': 'lesson',
            'href': 'unit?unit=%s&lesson=%s' % (
                unit.unit_id, lesson.lesson_id),
            'lesson_id': lesson.lesson_id,
            'actions': actions,
            'auto_index': lesson.auto_index,
            'extras': extras})

    unit_data['lessons'] = lessons

    if unit.post_assessment:
        assessment = course.find_unit_by_id(unit.post_assessment)
        if assessment:
            assessment_outline = _render_assessment_outline(handler, assessment)
            assessment_outline['class'] = 'post-assessment'
            unit_data['post_assessment'] = assessment_outline

    return unit_data

def _render_course_outline_to_html(handler, course):
    """Renders course outline to HTML."""

    units = []
    for unit in course.get_units():
        if course.get_parent_unit(unit.unit_id):
            continue  # Will be rendered as part of containing element.
        if unit.type == verify.UNIT_TYPE_ASSESSMENT:
            units.append(_render_assessment_outline(handler, unit))
        elif unit.type == verify.UNIT_TYPE_LINK:
            units.append(_render_link_outline(handler, unit))
        elif unit.type == verify.UNIT_TYPE_UNIT:
            units.append(_render_unit_outline(handler, course, unit))
        elif unit.type == verify.UNIT_TYPE_CUSTOM:
            units.append(_render_custom_unit_outline(handler, course, unit))
        else:
            raise Exception('Unknown unit type: %s.' % unit.type)

    template_values = {
        'course': {
            'title': course.title,
            'is_editable': handler.app_context.is_editable_fs(),
            'availability': {
                'url': handler.get_action_url('course_availability'),
                'xsrf_token': handler.create_xsrf_token('course_availability'),
                'param': not handler.app_context.now_available,
                'class': (
                    'row-hover icon md md-lock-open'
                    if handler.app_context.now_available else
                    'row-hover icon md md-lock')
            }
        },
        'units': units,
        'add_lesson_xsrf_token': handler.create_xsrf_token('add_lesson'),
        'status_xsrf_token': handler.create_xsrf_token('set_draft_status'),
        'unit_lesson_title_xsrf_token': handler.create_xsrf_token(
            unit_lesson_editor.UnitLessonTitleRESTHandler.XSRF_TOKEN),
        'unit_title_template': resources_display.get_unit_title_template(
            course.app_context),
        'extra_info_title': ', '.join(COURSE_OUTLINE_EXTRA_INFO_TITLES)
    }
    return jinja2.Markup(
        handler.get_template(
            'course_outline.html', [os.path.dirname(__file__)]
            ).render(template_values))

def _get_outline(handler):
    """Renders course outline view."""

    currentCourse = courses.Course(handler)

    outline_actions = []
    if handler.app_context.is_editable_fs():
        outline_actions.append({
            'id': 'add_unit',
            'caption': 'Add Unit',
            'action': handler.get_action_url('add_unit'),
            'xsrf_token': handler.create_xsrf_token('add_unit')})
        outline_actions.append({
            'id': 'add_link',
            'caption': 'Add Link',
            'action': handler.get_action_url('add_link'),
            'xsrf_token': handler.create_xsrf_token('add_link')})
        outline_actions.append({
            'id': 'add_assessment',
            'caption': 'Add Assessment',
            'action': handler.get_action_url('add_assessment'),
            'xsrf_token': handler.create_xsrf_token('add_assessment')})

        for custom_type in custom_units.UnitTypeRegistry.list():
            outline_actions.append({
                'id': 'add_custom_unit_%s' % custom_type.identifier,
                'caption': 'Add %s' % custom_type.name,
                'action': handler.get_action_url(
                        'add_custom_unit',
                        extra_args={'unit_type': custom_type.identifier}),
                'xsrf_token': handler.create_xsrf_token('add_custom_unit')})

        if not currentCourse.get_units():
            outline_actions.append({
                'id': 'import_course',
                'caption': 'Import',
                'href': handler.get_action_url('import_course')
                })

    sections = [
        {
            'actions': outline_actions,
            'pre': _render_course_outline_to_html(handler, currentCourse)}]

    template_values = {
        'page_title': handler.format_title('Outline'),
        'alerts': handler.get_alerts(),
        'sections': sections,
        }

    handler.render_page(template_values)


def on_module_enabled():
    dashboard.DashboardHandler.add_sub_nav_mapping(
        'edit', 'outline', 'Outline', action='outline', contents=_get_outline,
        placement=1000)
