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

from common import crypto
from models import courses
from models import custom_units
from models import resources_display
from models import permissions
from models import roles
from modules.dashboard import dashboard
from modules.courses import constants
from modules.courses import unit_lesson_editor
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


def _render_assessment_outline(handler, unit):
    course_writable = handler.app_context.is_editable_fs()
    can_view_props = course_writable and permissions.can_edit(
        handler.app_context, constants.SCOPE_ASSESSMENT)

    return {
        'title': unit.title,
        'id': unit.unit_id,
        'component_type': 'assessment',
        'view_url': 'assessment?name=%s' % unit.unit_id,
        'href': handler.canonicalize_url(
            '/dashboard?%s') % urllib.urlencode({
                'action': 'edit_assessment',
                'key': unit.unit_id}),
        'can_view_props': can_view_props,
    }


def _render_link_outline(handler, unit):
    course_writable = handler.app_context.is_editable_fs()
    can_view_props = course_writable and permissions.can_edit(
        handler.app_context, constants.SCOPE_LINK)

    return {
        'title': unit.title,
        'view_url': unit.href or '',
        'id': unit.unit_id,
        'component_type': 'link',
        'can_view_props': can_view_props,
        'href': handler.canonicalize_url(
            '/dashboard?%s') % urllib.urlencode({
                'action': 'edit_link',
                'key': unit.unit_id}),
    }

def _render_custom_unit_outline(handler, course, unit):
    course_writable = handler.app_context.is_editable_fs()
    can_view_props = course_writable and permissions.can_edit(
        handler.app_context, constants.SCOPE_UNIT)

    return {
        'title': unit.title,
        'component_type': 'custom-unit',
        'view_url': unit.custom_unit_url,
        'id': unit.unit_id,
        'can_view_props': can_view_props,
        'href': handler.canonicalize_url(
            '/dashboard?%s') % urllib.urlencode({
                'action': 'edit_custom_unit',
                'key': unit.unit_id,
                'unit_type': unit.custom_unit_type})
    }

def _render_unit_outline(handler, course, unit):
    course_writable = handler.app_context.is_editable_fs()
    can_view_props = course_writable and permissions.can_edit(
        handler.app_context, constants.SCOPE_UNIT)

    unit_data = {
        'title': unit.title,
        'component_type': 'unit',
        'view_url': 'unit?unit=%s' % unit.unit_id,
        'id': unit.unit_id,
        'can_view_props': can_view_props,
        'href': handler.canonicalize_url(
            '/dashboard?%s') % urllib.urlencode({
                'action': 'edit_unit',
                'key': unit.unit_id}),
    }

    if unit.pre_assessment:
        assessment = course.find_unit_by_id(unit.pre_assessment)
        if assessment:
            assessment_outline = _render_assessment_outline(handler, assessment)
            assessment_outline['component_type'] = 'pre-assessment'
            assessment_outline['not_reorderable'] = True
            unit_data['pre_assessment'] = assessment_outline

    # Here, just check whether user is course admin to see if lesson contents
    # are editable.  Eventually, can add specific sub-permissions to lessons,
    # if we like.
    lessons_editable = (handler.app_context.is_editable_fs() and
                        roles.Roles.is_course_admin(handler.app_context))
    lessons = []
    for lesson in course.get_lessons(unit.unit_id):
        extras = []
        for annotator in COURSE_OUTLINE_EXTRA_INFO_ANNOTATORS:
            extra_info = annotator(course, lesson)
            if extra_info:
                extras.append(extra_info)

        lessons.append({
            'title': lesson.title,
            'component_type': 'lesson',
            'view_url': 'unit?unit=%s&lesson=%s' % (
                unit.unit_id, lesson.lesson_id),
            'id': lesson.lesson_id,
            'href': handler.get_action_url('edit_lesson', key=lesson.lesson_id),
            'can_view_props': lessons_editable,
            'auto_index': lesson.auto_index,
            'extras': extras})

    unit_data['lessons'] = lessons

    if unit.post_assessment:
        assessment = course.find_unit_by_id(unit.post_assessment)
        if assessment:
            assessment_outline = _render_assessment_outline(handler, assessment)
            assessment_outline['component_type'] = 'post-assessment'
            assessment_outline['not_reorderable'] = True
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
        },
        'units': units,
        'add_lesson_xsrf_token': handler.create_xsrf_token('add_lesson'),
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
    import_job = unit_lesson_editor.ImportCourseBackgroundJob(
        handler.app_context, from_namespace=None)
    import_job_running = import_job.is_active()
    can_add_to_course = (roles.Roles.is_course_admin(handler.app_context) and
                         handler.app_context.is_editable_fs() and
                         not import_job_running)
    sections = []
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
    elif import_job_running:
        xsrf_token = crypto.XsrfTokenManager.create_xsrf_token(
            unit_lesson_editor.UnitLessonEditor.ACTION_POST_CANCEL_IMPORT)
        sections.append({
            'pre': jinja2.Markup(
                handler.get_template(
                    'import_running.html', [os.path.dirname(__file__)]
                    ).render({
                        'xsrf_token': xsrf_token,
                        'job_name': import_job.name,
                    }))})

    sections.append({
        'actions': outline_actions,
        'pre': _render_course_outline_to_html(handler, currentCourse)
        })
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
            constants.COURSE_OUTLINE_REORDER_PERMISSION) or
        permissions.can_edit(app_context, constants.SCOPE_UNIT) or
        permissions.can_edit(app_context, constants.SCOPE_ASSESSMENT) or
        permissions.can_edit(app_context, constants.SCOPE_LINK)
        )


def on_module_enabled(courses_custom_module):
    global custom_module  # pylint: disable=global-statement
    custom_module = courses_custom_module
    dashboard.DashboardHandler.add_sub_nav_mapping(
        'edit', 'outline', 'Outline', action=ACTION_GET_OUTLINE,
        contents=_get_outline, placement=1000, sub_group_name='pinned')
    dashboard.DashboardHandler.map_get_action_to_permission_checker(
        ACTION_GET_OUTLINE, can_view_course_outline)
