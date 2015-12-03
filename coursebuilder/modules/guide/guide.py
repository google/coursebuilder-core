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

"""A Guide: new, non-linear learning experience module."""

__author__ = 'Pavel Simakov (psimakov@google.com)'


import os

import appengine_config
from common import jinja_utils
from common import safe_dom
from common import schema_fields
from common import utils as common_utils
from controllers import sites
from controllers import utils
from models import courses
from models import custom_modules
from models import resources_display
from models import roles
from models import services
from modules.courses import settings
from modules.courses import unit_outline
from tools import verify


guide_module = None

TEMPLATE_DIRS = [
    os.path.join(
        appengine_config.BUNDLE_ROOT, 'modules', 'guide', 'templates'),
    os.path.join(
        appengine_config.BUNDLE_ROOT, 'views'),
]

GUIDE_SETTINGS_SCHEMA_SECTION = 'modules:guide'
GUIDE_URL = 'url'
GUIDE_ENABLED_FOR_THIS_COURSE = 'enabled'
GUIDE_COLOR = 'color'
GUIDE_COLOR_DEFAULT = '#00838F'
GUIDE_DURATION = 'duration'
GUIDE_AVAILABILITY = 'availability'

AVAILABILITY_SELECT_DATA = [
    (courses.AVAILABILITY_UNAVAILABLE, 'Private'),
    (courses.AVAILABILITY_COURSE, 'Course')]


def unit_title(unit, app_context):
    return resources_display.display_unit_title(unit, app_context)


def get_config(app_context):
    config = app_context.get_environ(
        ).get('modules', {}).get('guide', {})
    if not config:
        config = {}
    return config


class GuideDisplayableElement(object):

    def __init__(self, availability):
        self.availability = availability
        self.shown_when_unavailable = False


def can_display_guide_to_current_user(course, config):
    user, student = (
        utils.CourseHandler.get_user_and_student_or_transient())
    course_avail = course.get_course_availability()
    self_avail = config.get(GUIDE_AVAILABILITY)
    displayability = courses.Course.get_element_displayability(
        course_avail, student.is_transient,
        custom_modules.can_see_drafts(course.app_context),
        GuideDisplayableElement(self_avail))
    return student, displayability.is_link_displayed, displayability


class GuideApplicationHandler(utils.ApplicationHandler):

    def get_duration(self, config, course, unit):
        lesson_duration_min = config.get(GUIDE_DURATION)
        total_duration_secs = (lesson_duration_min * 60 * len(
            course.get_lessons(
                unit.unit_id))) if lesson_duration_min else 0
        return total_duration_secs

    def format_availability(self, text):
        return text.capitalize().replace('_', ' ')

    def format_title(self, app_context, course, displayability, config):
        title = app_context.get_title()
        if config.get(GUIDE_AVAILABILITY) == courses.AVAILABILITY_UNAVAILABLE:
            title += ' (Private)'
        else:
            if not displayability.is_available_to_visitors and (
                    roles.Roles.is_course_admin(app_context)):
                title += ' (%s)' % self.format_availability(
                    course.get_course_availability())
        return title

    def get_courses(self):
        all_courses = []
        for app_context in sorted(sites.get_all_courses()):
            with common_utils.Namespace(app_context.namespace):
                course = courses.Course(None, app_context)

                # check rights
                config = get_config(app_context)
                if not config.get(GUIDE_ENABLED_FOR_THIS_COURSE):
                    continue
                student, can_display, displayability = (
                    can_display_guide_to_current_user(course, config))
                if not can_display:
                    continue

                # prepare values to render
                title = self.format_title(
                    app_context, course, displayability, config)
                slug = app_context.get_slug()
                if slug == '/':
                    slug = ''
                category_color = config.get(GUIDE_COLOR)
                if not category_color:
                    category_color = GUIDE_COLOR_DEFAULT

                # iterate units
                units = []
                for unit in unit_outline.StudentCourseView(
                        course, student=student).get_units():
                    if unit.type != verify.UNIT_TYPE_UNIT:
                        continue
                    units.append((
                        unit.unit_id, unit.title,
                        unit.description if unit.description else '',
                        self.get_duration(config, course, unit)
                    ))

                if units:
                    all_courses.append((slug, title, category_color, units,))

        sorted(all_courses, key=lambda x: x[1])
        return all_courses

    def get(self):
        template_data = {}

        all_courses = self.get_courses()
        if not all_courses:
            self.error(404, 'No courses to display')
            return

        template_data['courses'] = sorted(all_courses, key=lambda x: x[1])

        template = jinja_utils.get_template('guides.html', TEMPLATE_DIRS)
        self.response.write(template.render(template_data))


class GuideUnitHandler(utils.BaseHandler):

    def add_duration_to(self, config, lessons):
        lesson_duration_min = config.get(GUIDE_DURATION)
        for lesson in lessons:
            lesson.duration = '%s' % (
                lesson_duration_min if lesson_duration_min else 0)

    def prepare(self, config, view, student, unit, lessons, template_data):
        self.add_duration_to(config, lessons)

        category_color = config.get(GUIDE_COLOR)
        if not category_color:
            category_color = GUIDE_COLOR_DEFAULT

        template_data['course_base_href'] = self.get_base_href(self)
        template_data['course_title'] = self.app_context.get_title()
        template_data['category_color'] = category_color
        template_data['unit_id'] = unit.unit_id
        template_data['unit_title'] = unit.title
        template_data['lessons'] = lessons
        template_data['feedback_link'] = (
            self.app_context.get_environ()['course'].get('forum_url', ''))

    def guide_get(self, config):
        student, can_display, displayability = (
            can_display_guide_to_current_user(self.get_course(), config))
        if not can_display:
            self.error(
                404, 'Negative displayability: %s' % str(displayability))
            return

        unit_id = self.request.get('unit_id')
        if not unit_id:
            self.error(404, 'Bad unit_id')
            return

        view = unit_outline.StudentCourseView(
            self.get_course(), student=student)
        unit = self.get_course().find_unit_by_id(unit_id)
        if not unit in view.get_units():
            self.error(404, 'Unit not visible')
            return

        self.prepare(config, view, student, unit,
            view.get_lessons(unit.unit_id), self.template_value)

        template = jinja_utils.get_template(
            'steps.html', TEMPLATE_DIRS, handler=self)
        self.response.write(template.render(self.template_value))

    def get(self):
        config = get_config(self.app_context)
        if config.get(GUIDE_ENABLED_FOR_THIS_COURSE):
            self.guide_get(config)
        else:
            self.error(404, 'Guide is disabled: %s' % config)
            return


def get_schema_fields():
    enabled_name = (
        GUIDE_SETTINGS_SCHEMA_SECTION + ':' + GUIDE_ENABLED_FOR_THIS_COURSE)
    enabled = schema_fields.SchemaField(
        enabled_name, 'Enable Guides', 'boolean',
        optional=True, i18n=False, editable=True,
        description=str(safe_dom.NodeList(
        ).append(safe_dom.Text(
            'If checked, this course will be included in the guides '
            'experience accessible at ')
        ).append(safe_dom.assemble_link(
            '/modules/guides', '/modules/guides', target="_blank")
        ).append(safe_dom.Text('. Course must not be Private. ')
        ).append(safe_dom.assemble_link(
            services.help_urls.get(enabled_name), 'Learn more...',
            target="_blank"))))
    color = schema_fields.SchemaField(
        GUIDE_SETTINGS_SCHEMA_SECTION + ':' + GUIDE_COLOR,
        'Color', 'string',
        optional=True, i18n=False, editable=True,
        description='The color scheme for this course\'s guides must '
            'be expressed as a web color hex triplet, beginning with '
            'a "#". If blank, #00838F will be used.')
    duration = schema_fields.SchemaField(
        GUIDE_SETTINGS_SCHEMA_SECTION + ':' + GUIDE_DURATION,
        'Duration', 'integer',
        optional=True, i18n=False, editable=True, default_value=0,
        description=(
            'Specify the average length of each lesson in the course in '
            'minutes and it will be used to estimate the duration of each '
            'guide. If blank or set to 0, duration will not be shown.'))
    availabiliy_name = GUIDE_SETTINGS_SCHEMA_SECTION + ':' + GUIDE_AVAILABILITY
    availability = schema_fields.SchemaField(
        availabiliy_name, 'Availability', 'boolean', optional=True, i18n=False,
        select_data=AVAILABILITY_SELECT_DATA,
        default_value=courses.AVAILABILITY_COURSE,
        description=str(safe_dom.NodeList(
        ).append(safe_dom.Text(
            'Guides default to the availability of the course, '
            'but may also be restricted to admins (Private). ')
        ).append(safe_dom.assemble_link(
            services.help_urls.get(availabiliy_name), 'Learn more...',
            target="_blank"))))

    return (lambda _: enabled, lambda _: color, lambda _: duration,
            lambda _: availability)


def register_module():
    """Registers this module in the registry."""

    def notify_module_enabled():
        courses.Course.OPTIONS_SCHEMA_PROVIDERS[
            GUIDE_SETTINGS_SCHEMA_SECTION] += get_schema_fields()
        settings.CourseSettingsHandler.register_settings_section(
            GUIDE_SETTINGS_SCHEMA_SECTION, title='Guides')

    # we now register ZIP handler; here is a test URL:
    #   /modules/guide/resources/polymer/bower_components/bower.json
    polymer_js_handler = sites.make_zip_handler(os.path.join(
        appengine_config.BUNDLE_ROOT, 'lib', 'polymer-guide-1.2.0.zip'))

    global_routes = [
        ('/modules/guide/resources' + '/polymer/(.*)', polymer_js_handler),
        ('/modules/guides', GuideApplicationHandler),]
    namespaced_routes = [('/guide', GuideUnitHandler),]

    global guide_module  # pylint: disable=global-statement
    guide_module = custom_modules.Module(
        'Guide, a new learning experience module.',
        'An alternative to the default course explorer and course experience.',
        global_routes, namespaced_routes,
        notify_module_enabled=notify_module_enabled)

    return guide_module
