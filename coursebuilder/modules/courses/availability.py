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

"""Display course availability settings page."""

__author__ = 'Mike Gainer (mgainer@google.com)'

import os

import appengine_config
from common import crypto
from common import schema_fields
from controllers import utils
from models import courses
from models import roles
from models import services
from models import transforms
from modules.courses import constants
from modules.courses import messages
from modules.dashboard import dashboard
from modules.oeditor import oeditor

custom_module = None

_TEMPLATES_DIR = os.path.join(
    appengine_config.BUNDLE_ROOT, 'modules', 'courses', 'templates')


class AvailabilityRESTHandler(utils.BaseRESTHandler):

    ACTION = 'availability'
    URL = 'rest/availability'

    @classmethod
    def get_form(cls, handler):
        schema = cls.get_schema()
        return oeditor.ObjectEditor.get_html_for(
            handler, schema.get_json_schema(), schema.get_schema_dict(),
            'dummy_key', cls.URL, additional_dirs=[_TEMPLATES_DIR], exit_url='',
            exit_button_caption='', extra_css_files=['availability.css'],
            extra_js_files=['availability.js'])

    @classmethod
    def get_schema(cls):
        ret = schema_fields.FieldRegistry(
            'Availability', 'Course Availability Settings',
            extra_schema_dict_values={
                'className': (
                    'inputEx-Group new-form-layout hidden-header '
                    'availability-manager')})
        ret.add_property(schema_fields.SchemaField(
            'course_availability', 'Course Availability', 'string',
            description='This sets the availability of the course for '
            'registered and unregistered students.',
            i18n=False, optional=True,
            select_data=[
                (p, p.replace('_', ' ').title())
                for p in courses.COURSE_AVAILABILITY_POLICIES]))
        element_settings = schema_fields.FieldRegistry(
            'Element Settings', 'Availability settings for course elements',
            extra_schema_dict_values={'className': 'content-element'})
        element_settings.add_property(schema_fields.SchemaField(
            'type', 'Element Kind', 'string',
            i18n=False, optional=True, editable=False, hidden=True))
        element_settings.add_property(schema_fields.SchemaField(
            'id', 'Element Key', 'string',
            i18n=False, optional=True, editable=False, hidden=True))
        element_settings.add_property(schema_fields.SchemaField(
            'indent', 'Indent', 'boolean',
            i18n=False, optional=True, editable=False, hidden=True))
        element_settings.add_property(schema_fields.SchemaField(
            'name', 'Course Outline', 'string',
            i18n=False, optional=True, editable=False,
            extra_schema_dict_values={'className': 'title'}))
        element_settings.add_property(schema_fields.SchemaField(
            'shown_when_unavailable', 'Shown When Private', 'boolean',
            description=services.help_urls.make_learn_more_message(
                messages.AVAILABILITY_SHOWN_WHEN_UNAVAILABLE_DESCRIPTION,
                'course:availability:shown_when_unavailable'), i18n=False,
            optional=True,
            extra_schema_dict_values={'className': 'shown'}))
        element_settings.add_property(schema_fields.SchemaField(
            'availability', 'Availability', 'string',
            description=services.help_urls.make_learn_more_message(
                messages.AVAILABILITY_AVAILABILITY_DESCRIPTION,
                'course:availability:availability'), i18n=False, optional=True,
            select_data=[(a, a.title()) for a in courses.AVAILABILITY_VALUES],
            extra_schema_dict_values={'className': 'availability'}))
        ret.add_property(schema_fields.FieldArray(
            'element_settings', 'Content Availability',
            item_type=element_settings, optional=True,
            extra_schema_dict_values={'className': 'content-availability'}))
        ret.add_property(schema_fields.SchemaField(
            'whitelist', 'Students Allowed to Register', 'text',
            description='Only students with email addresses in this list may '
            'register for the course.  Separate addresses with any combination '
            'of commas, spaces, or separate lines.',
            i18n=False, optional=True))
        return ret

    @classmethod
    def add_unit(cls, unit, elements, indent=False):
        elements.append({
            'type': 'unit',
            'id': unit.unit_id,
            'indent': indent,
            'name': unit.title,
            'availability': unit.availability,
            'shown_when_unavailable': unit.shown_when_unavailable,
            })

    @classmethod
    def add_lesson(cls, lesson, elements):
        elements.append({
            'type': 'lesson',
            'id': lesson.lesson_id,
            'indent': True,
            'name': lesson.title,
            'availability': lesson.availability,
            'shown_when_unavailable': lesson.shown_when_unavailable,
            })

    @classmethod
    def traverse_course(cls, course):
        elements = []
        for unit in course.get_units():
            if unit.is_assessment() and course.get_parent_unit(unit.unit_id):
                continue
            cls.add_unit(unit, elements, indent=False)
            if unit.is_unit():
                if unit.pre_assessment:
                    cls.add_unit(course.find_unit_by_id(unit.pre_assessment),
                                 elements, indent=True)
                for lesson in course.get_lessons(unit.unit_id):
                    cls.add_lesson(lesson, elements)
                if unit.post_assessment:
                    cls.add_unit(course.find_unit_by_id(unit.post_assessment),
                                 elements, indent=True)
        return elements

    def get(self):
        if not roles.Roles.is_user_allowed(
            self.app_context, custom_module,
            constants.MODIFY_AVAILABILITY_PERMISSION):
            transforms.send_json_response(self, 401, 'Access denied.')
            return

        course = self.get_course()
        course_availability = course.get_course_availability()
        settings = course.get_environ(self.app_context)
        entity = {
            'course_availability': course_availability,
            'whitelist': settings['reg_form']['whitelist'],
            'element_settings': self.traverse_course(self.get_course()),
        }
        transforms.send_json_response(
            self, 200, 'OK.', payload_dict=entity,
            xsrf_token=crypto.XsrfTokenManager.create_xsrf_token(self.ACTION))

    def put(self):
        request = transforms.loads(self.request.get('request'))

        # Check access permissions.  Not coming through dashboard, so must
        # do these for ourselves.
        if not self.assert_xsrf_token_or_fail(request, self.ACTION,
                                              {'key':'a'}):
            return
        if not roles.Roles.is_user_allowed(
            self.app_context, custom_module,
            constants.MODIFY_AVAILABILITY_PERMISSION):
            transforms.send_json_response(self, 401, 'Access denied.')
            return

        course = self.get_course()
        settings = self.app_context.get_environ()
        payload = transforms.loads(request.get('payload', '{}'))

        # Course-level changes: user whitelist, available/browsable/registerable
        whitelist = payload.get('whitelist')
        if whitelist is not None:
            settings['reg_form']['whitelist'] = whitelist

        course.save_settings(settings)

        course_availability = payload.get('course_availability')
        if course_availability:
            course.set_course_availability(course_availability)

        # Unit and lesson availability, visibility from syllabus list
        for item in payload.get('element_settings', []):
            if item['type'] == 'unit':
                element = course.find_unit_by_id(item['id'])
            elif item['type'] == 'lesson':
                element = course.find_lesson_by_id(None, item['id'])
            else:
                raise ValueError('Unexpected item type "%s"' % item['type'])
            if element:
                if 'availability' in item:
                    element.availability = item['availability']
                if 'shown_when_unavailable' in item:
                    element.shown_when_unavailable = (
                        item['shown_when_unavailable'])
        course.save()
        transforms.send_json_response(self, 200, 'Saved.')


def get_namespaced_handlers():
    return [('/' + AvailabilityRESTHandler.URL, AvailabilityRESTHandler)]


def on_module_enabled(courses_custom_module, module_permissions):
    global custom_module  # pylint: disable=global-statement
    custom_module = courses_custom_module
    module_permissions.extend([
        roles.Permission(
            constants.MODIFY_AVAILABILITY_PERMISSION,
            'Can set course, unit, or lesson availability and visibility'),
        ])
    dashboard.DashboardHandler.add_sub_nav_mapping(
        'publish', 'availability', 'Availability',
        AvailabilityRESTHandler.ACTION, placement=1000)

    dashboard.DashboardHandler.add_custom_get_action(
        AvailabilityRESTHandler.ACTION, AvailabilityRESTHandler.get_form)
    dashboard.DashboardHandler.map_get_action_to_permission(
        AvailabilityRESTHandler.ACTION, courses_custom_module,
        constants.MODIFY_AVAILABILITY_PERMISSION)
