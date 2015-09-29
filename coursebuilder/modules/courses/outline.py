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
from models import permissions
from models import roles
from modules.dashboard import dashboard
from modules.courses import constants
from modules.courses import unit_lesson_editor
from modules.dashboard import utils as dashboard_utils
from tools import verify

# Reference to custom_module registered in modules/courses/courses.py
custom_module = None

# A list of functions which are used to generate extra info about a lesson
# or unit in the course outline view. Modules which can provide extra info
# should add a function to this list which accepts a course and a lesson or
# unit as argument and returns a safe_dom NodeList or Node.
COURSE_OUTLINE_EXTRA_INFO_ANNOTATORS = []

# Modules adding extra info annotators (above) may also add a string to this
# list which will be displayed at a heading in the course outline table.
COURSE_OUTLINE_EXTRA_INFO_TITLES = []

# Action name for dashboard to use for our tab.
ACTION_GET_OUTLINE = 'outline'


def _render_status_icon(handler, resource, key, component_type, editable):
    if not hasattr(resource, 'now_available'):
        return
    icon = safe_dom.Element(
        'div', data_key=str(key), data_component_type=component_type)
    common_classes = 'row-hover icon icon-draft-status md'
    if not editable:
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

    course_writable = handler.app_context.is_editable_fs()
    can_edit_status = course_writable and permissions.can_edit_property(
        handler.app_context, constants.SCOPE_ASSESSMENT, 'assessment/is_draft')
    can_view_props = course_writable and permissions.can_edit(
        handler.app_context, constants.SCOPE_ASSESSMENT)

    actions.append(_render_status_icon(
        handler, unit, unit.unit_id, 'assessment', can_edit_status))
    url = handler.canonicalize_url(
        '/dashboard?%s') % urllib.urlencode({
            'action': 'edit_assessment',
            'key': unit.unit_id})
    actions.append(dashboard_utils.create_edit_button(url, can_view_props))
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

    course_writable = handler.app_context.is_editable_fs()
    can_edit_status = course_writable and permissions.can_edit_property(
        handler.app_context, constants.SCOPE_LINK, 'is_draft')
    can_view_props = course_writable and permissions.can_edit(
        handler.app_context, constants.SCOPE_LINK)

    actions.append(_render_status_icon(
        handler, unit, unit.unit_id, 'link', can_edit_status))
    url = handler.canonicalize_url(
        '/dashboard?%s') % urllib.urlencode({
            'action': 'edit_link',
            'key': unit.unit_id})
    actions.append(dashboard_utils.create_edit_button(url, can_view_props))
    return unit_data

def _render_custom_unit_outline(handler, course, unit):
    actions = []
    unit_data = {
        'title': unit.title,
        'class': 'custom-unit',
        'href': unit.custom_unit_url,
        'unit_id': unit.unit_id,
        'actions': actions
    }

    course_writable = handler.app_context.is_editable_fs()
    can_edit_status = course_writable and permissions.can_edit_property(
        handler.app_context, constants.SCOPE_UNIT, 'is_draft')
    can_view_props = course_writable and permissions.can_edit(
        handler.app_context, constants.SCOPE_UNIT)

    actions.append(_render_status_icon(
        handler, unit, unit.unit_id, 'unit', can_edit_status))
    url = handler.canonicalize_url(
        '/dashboard?%s') % urllib.urlencode({
            'action': 'edit_custom_unit',
            'key': unit.unit_id,
            'unit_type': unit.custom_unit_type})
    actions.append(dashboard_utils.create_edit_button(url, can_view_props))
    return unit_data

def _render_unit_outline(handler, course, unit):

    actions = []
    unit_data = {
        'title': unit.title,
        'class': 'unit',
        'href': 'unit?unit=%s' % unit.unit_id,
        'unit_id': unit.unit_id,
        'actions': actions
    }

    course_writable = handler.app_context.is_editable_fs()
    can_edit_status = course_writable and permissions.can_edit_property(
        handler.app_context, constants.SCOPE_UNIT, 'is_draft')
    can_view_props = course_writable and permissions.can_edit(
        handler.app_context, constants.SCOPE_UNIT)

    actions.append(_render_status_icon(
        handler, unit, unit.unit_id, 'unit', can_edit_status))
    url = handler.canonicalize_url(
        '/dashboard?%s') % urllib.urlencode({
            'action': 'edit_unit',
            'key': unit.unit_id})
    actions.append(dashboard_utils.create_edit_button(url, can_view_props))

    if unit.pre_assessment:
        assessment = course.find_unit_by_id(unit.pre_assessment)
        if assessment:
            assessment_outline = _render_assessment_outline(handler, assessment)
            assessment_outline['class'] = 'pre-assessment'
            unit_data['pre_assessment'] = assessment_outline

    # Here, just check whether user is course admin to see if lesson contents
    # are editable.  Eventually, can add specific sub-permissions to lessons,
    # if we like.
    lessons_editable = (handler.app_context.is_editable_fs() and
                        roles.Roles.is_course_admin(handler.app_context))
    lessons = []
    for lesson in course.get_lessons(unit.unit_id):
        actions = []
        actions.append(_render_status_icon(
            handler, lesson, lesson.lesson_id, 'lesson', lessons_editable))
        url = handler.get_action_url(
            'edit_lesson', key=lesson.lesson_id)
        actions.append(dashboard_utils.create_edit_button(
            url, lessons_editable))

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

    is_course_availability_editable = permissions.can_edit_property(
        handler.app_context, constants.SCOPE_COURSE_SETTINGS,
        'course/course:now_available')
    any_course_setting_viewable = permissions.can_view(
        handler.app_context, constants.SCOPE_COURSE_SETTINGS)
    template_values = {
        'course': {
            'title': course.title,
            'can_add_or_remove': roles.Roles.is_course_admin(
                handler.app_context),
            'can_reorder': roles.Roles.is_user_allowed(
                handler.app_context, custom_module,
                constants.COURSE_OUTLINE_REORDER_PERMISSION),
            'settings_viewable': any_course_setting_viewable,
            'availability': {
                'url': handler.get_action_url('course_availability'),
                'xsrf_token': handler.create_xsrf_token('course_availability'),
                'param': not handler.app_context.now_available,
                'class': (
                    'row-hover icon md md-lock-open'
                    if handler.app_context.now_available else
                    'row-hover icon md md-lock'),
                'is_editable': is_course_availability_editable,
            }
        },
        'units': units,
        'add_lesson_xsrf_token': handler.create_xsrf_token('add_lesson'),
        'unit_lesson_title_xsrf_token': handler.create_xsrf_token(
            unit_lesson_editor.UnitLessonTitleRESTHandler.XSRF_TOKEN),
        'unit_title_template': resources_display.get_unit_title_template(
            course.app_context),
        'extra_info_title': ', '.join(COURSE_OUTLINE_EXTRA_INFO_TITLES)
    }
    for item_type in unit_lesson_editor.UnitLessonEditor.CAN_EDIT_DRAFT:
        action_name = '%s_%s' % (
            unit_lesson_editor.UnitLessonEditor.ACTION_POST_SET_DRAFT_STATUS,
            item_type)
        token_name = 'status_xsrf_token_%s' % item_type
        template_values[token_name] = handler.create_xsrf_token(action_name)

    return jinja2.Markup(
        handler.get_template(
            'course_outline.html', [os.path.dirname(__file__)]
            ).render(template_values))

def _get_outline(handler):
    """Renders course outline view."""

    currentCourse = courses.Course(handler)
    can_add_to_course = (roles.Roles.is_course_admin(handler.app_context) and
                         handler.app_context.is_editable_fs())
    outline_actions = []
    if can_add_to_course:
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


def can_view_course_outline(app_context):
    return (
        roles.Roles.is_user_allowed(
            app_context, custom_module,
            constants.COURSE_OUTLINE_VIEW_PERMISSION) or
        roles.Roles.is_user_allowed(
            app_context, custom_module,
            constants.COURSE_OUTLINE_REORDER_PERMISSION) or
        permissions.can_edit(app_context, constants.SCOPE_UNIT) or
        permissions.can_edit(app_context, constants.SCOPE_ASSESSMENT) or
        permissions.can_edit(app_context, constants.SCOPE_LINK)
        )


def on_module_enabled(courses_custom_module, module_permissions):
    global custom_module  # pylint: disable=global-statement
    custom_module = courses_custom_module
    module_permissions.extend([
        roles.Permission(
            constants.COURSE_OUTLINE_VIEW_PERMISSION,
            'Can view course structure'),
        ])

    dashboard.DashboardHandler.add_sub_nav_mapping(
        'edit', 'outline', 'Outline', action=ACTION_GET_OUTLINE,
        contents=_get_outline, placement=1000, sub_group_name='pinned')
    dashboard.DashboardHandler.map_get_action_to_permission_checker(
        ACTION_GET_OUTLINE, can_view_course_outline)
