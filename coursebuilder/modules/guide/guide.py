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

RESOURCES_URI = '/modules/guide/resources'

GUIDE_SETTINGS_SCHEMA_SECTION = 'modules:guide'
GUIDE_URL = 'url'
GUIDE_ENABLED_FOR_THIS_COURSE = 'enabled'
GUIDE_COLOR = 'color'
GUIDE_COLOR_DEFAULT = '#00838F'
GUIDE_DURATION = 'duration'

MAIN_HANDLER_URL = '/modules/guide'


def unit_title(unit, app_context):
    return resources_display.display_unit_title(unit, app_context)


def get_config(app_context):
    return app_context.get_environ(
        ).get('modules', {}).get('guide', {})


class GuideApplicationHandler(utils.ApplicationHandler):

    def get_duration(self, config, course, unit):
        lesson_duration_min = config.get(GUIDE_DURATION)
        total_duration_secs = (lesson_duration_min * 60 * len(
            course.get_lessons(
                unit.unit_id))) if lesson_duration_min else 0
        return total_duration_secs

    def get_courses(self):
        all_courses = []
        for app_context in sorted(sites.get_all_courses()):
            with common_utils.Namespace(app_context.namespace):
                course = courses.Course(None, app_context)

                config = get_config(app_context)
                if not config or not config.get(
                        GUIDE_ENABLED_FOR_THIS_COURSE):
                    continue

                slug = app_context.get_slug()
                if slug == '/':
                    slug = ''
                category_color = config.get(GUIDE_COLOR)
                if not category_color:
                    category_color = GUIDE_COLOR_DEFAULT

                title = app_context.get_title()
                mode = course.get_course_availability()
                if not mode == courses.COURSE_AVAILABILITY_PUBLIC:
                    if roles.Roles.is_course_admin(app_context):
                        title += ' (%s)' % mode
                    else:
                        continue

                units = []
                for unit in unit_outline.StudentCourseView(course).get_units():
                    if unit.type != verify.UNIT_TYPE_UNIT:
                        continue
                    units.append((
                        unit.unit_id, unit.title,
                        unit.description if unit.description else '',
                        self.get_duration(config, course, unit)
                    ))

                all_courses.append((
                    slug, title, category_color, units,))

        sorted(all_courses, key=lambda x: x[1])
        return all_courses

    def get(self):
        template_data = {}

        all_courses = self.get_courses()
        if not all_courses:
            self.error(404)
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

    def prepare(self, student, unit_id, config, template_data):
        course = self.get_course()
        unit = course.find_unit_by_id(unit_id)
        lessons = unit_outline.StudentCourseView(
            course, student=student).get_lessons(unit_id)
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

    def get(self):
        student = self.personalize_page_and_get_enrolled(
            supports_transient_student=True)
        if not student:
            return

        config = get_config(self.app_context)
        if not config or not config.get(GUIDE_ENABLED_FOR_THIS_COURSE):
            self.error(403)
            return

        unit_id = self.request.get('unit_id')
        if not unit_id:
            self.error(404)
            return
        self.prepare(student, unit_id, config, self.template_value)

        template = jinja_utils.get_template(
            'steps.html', TEMPLATE_DIRS, handler=self)
        self.response.write(template.render(self.template_value))


def get_schema_fields():
    enabled = schema_fields.SchemaField(
        GUIDE_SETTINGS_SCHEMA_SECTION + ':' + GUIDE_ENABLED_FOR_THIS_COURSE,
        'Enabled', 'boolean',
        optional=True, i18n=False, editable=True,
        description=str(safe_dom.NodeList().append(safe_dom.Text(
            'Whether to include this course into Guide experience, '
            'which can be accessed at ')
        ).append(safe_dom.assemble_link(
            '/modules/guide', '/modules/guide', target="_blank")
        ).append(safe_dom.Text(
            '. Only courses that have "public" availability and Guide '
            'enabled are included. If no public courses are available, '
            'Guide experience is disabled.'))))
    color = schema_fields.SchemaField(
        GUIDE_SETTINGS_SCHEMA_SECTION + ':' + GUIDE_COLOR,
        'Color', 'string',
        optional=True, i18n=False, editable=True,
        description='Color to use for this course\'s units (#00FF00).')
    duration = schema_fields.SchemaField(
        GUIDE_SETTINGS_SCHEMA_SECTION + ':' + GUIDE_DURATION,
        'Duration', 'integer',
        optional=True, i18n=False, editable=True, default_value=0,
        description=(
            'Average duration in minutes of a lesson in this unit. '
            'Enter "0" to prevent display of lesson and unit durations.'))

    return (lambda c: enabled, lambda c: color, lambda c: duration)


def register_module():
    """Registers this module in the registry."""

    def notify_module_enabled():
        courses.Course.OPTIONS_SCHEMA_PROVIDERS[
            GUIDE_SETTINGS_SCHEMA_SECTION] += get_schema_fields()
        settings.CourseSettingsHandler.register_settings_section(
            GUIDE_SETTINGS_SCHEMA_SECTION, title='Guide')

    # we now register ZIP handler; here is a test URL:
    #   /modules/guide/resources/polymer/bower_components/bower.json
    polymer_js_handler = sites.make_zip_handler(os.path.join(
        appengine_config.BUNDLE_ROOT, 'lib', 'polymer-guide-1.2.0.zip'))

    global_routes = [
        (RESOURCES_URI + '/polymer/(.*)', polymer_js_handler),
        (MAIN_HANDLER_URL, GuideApplicationHandler),]
    namespaced_routes = [('/guide', GuideUnitHandler),]

    global guide_module  # pylint: disable=global-statement
    guide_module = custom_modules.Module(
        'Guide, a new learning experience module.',
        'An alternative to the default course explorer and course experience.',
        global_routes, namespaced_routes,
        notify_module_enabled=notify_module_enabled)

    return guide_module
