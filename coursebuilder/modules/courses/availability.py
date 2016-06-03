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

import collections
import logging
import os

import appengine_config
from common import crypto
from common import resource
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

TEMPLATES_DIR = os.path.join(
    appengine_config.BUNDLE_ROOT, 'modules', 'courses', 'templates')


class AvailabilityRESTHandler(utils.BaseRESTHandler):

    ACTION = 'availability'
    URL = 'rest/availability'
    ADD_TRIGGER_BUTTON_TEXT = 'Add date/time availability change'

    MISSING_CONTENT_FMT = 'MISSING content with resource Key "%s".'

    # On the Publish > Availability form (in the element_settings course
    # outline and the <option> values in the availability_triggers 'content'
    # <select>), there are only two content types: 'unit', and 'lesson'.
    # All types other than 'lesson' (e.g. 'unit', 'link', 'assessment') are
    # represented by 'unit' instead.
    OUTLINE_CONTENT_TYPES = ['unit', 'lesson']

    UNEXPECTED_CONTENT_FMT = 'Unexpected content type "%%s" not in %s.' % (
        OUTLINE_CONTENT_TYPES)

    UNEXPECTED_AVAIL_FMT = 'Unexpected availability "%%s" not in %s.' % (
        courses.AVAILABILITY_VALUES)

    @classmethod
    def get_form(cls, handler):
        course = handler.get_course()
        schema = cls.get_schema(course)
        return oeditor.ObjectEditor.get_html_for(
            handler, schema.get_json_schema(), schema.get_schema_dict(),
            'dummy_key', cls.URL, additional_dirs=[TEMPLATES_DIR], exit_url='',
            exit_button_caption='', extra_css_files=['availability.css'],
            extra_js_files=['availability.js'])

    @classmethod
    def get_schema(cls, course):
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
                (k, v['title'])
                for k, v in courses.COURSE_AVAILABILITY_POLICIES.iteritems()]))

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
            select_data=courses.AVAILABILITY_SELECT_DATA,
            extra_schema_dict_values={'className': 'availability'}))
        ret.add_property(schema_fields.FieldArray(
            'element_settings', 'Content Availability',
            item_type=element_settings, optional=True,
            extra_schema_dict_values={'className': 'content-availability'}))

        ret.add_property(schema_fields.SchemaField(
            'whitelist', 'Students Allowed to Access', 'text',
            description='Only students with email addresses in this list may '
            'access course content.  Separate addresses with any combination '
            'of commas, spaces, or separate lines.  Course, site, and App '
            'Engine administrators always have access and need not be '
            'listed explicitly.',
            i18n=False, optional=True))

        availability_trigger = schema_fields.FieldRegistry(
            'Trigger', 'Date/Time Triggered Availability Change',
            extra_schema_dict_values={'className': 'availability-trigger'})
        availability_trigger.add_property(schema_fields.SchemaField(
            'content', 'For course content:', 'string',
            description='The course content, such as unit or lesson, '
            'for which to change the availability to students.',
            i18n=False, select_data=cls.content_select(course).items(),
            extra_schema_dict_values={'className': 'trigger-content'}))
        availability_trigger.add_property(schema_fields.SchemaField(
            'availability', 'Change availability to:', 'string',
            description='The availability of the course resource will '
            'change to this value after the trigger date and time.',
            i18n=False, select_data=courses.AVAILABILITY_SELECT_DATA,
            extra_schema_dict_values={'className': 'trigger-availability'}))
        availability_trigger.add_property(schema_fields.SchemaField(
            'when', 'At this date & UTC hour:', 'datetime',
            i18n=False,
            description='The date and hour (UTC) when the availability of the '
            'resource will be changed.',
            extra_schema_dict_values={
                'className': 'trigger-when inputEx-required'}))
        ret.add_property(schema_fields.FieldArray(
            'availability_triggers',
            'Change Course Content Availability at Date/Time',
            item_type=availability_trigger, optional=True,
            description=services.help_urls.make_learn_more_message(
                messages.AVAILABILITY_TRIGGERS_DESCRIPTION,
                'course:availability:triggers'),
            extra_schema_dict_values={
                'className': 'availability-triggers',
                'listAddLabel': cls.ADD_TRIGGER_BUTTON_TEXT,
                'listRemoveLabel': 'Delete'}))
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

    @classmethod
    def add_content_option(cls, content_id, content_type, title, select,
                           note='', indent=0):
        value = str(resource.Key(content_type, content_id))
        text = title
        if note:
            text = '{} ({})'.format(text, note)
        if indent:
            text = ('&emsp;' * indent) + text
        select[value] = text

    @classmethod
    def content_select(cls, course):
        select = collections.OrderedDict()
        for unit in course.get_units():
            if unit.is_assessment():
                if course.get_parent_unit(unit.unit_id):
                    continue
                note = 'assessment'
            elif unit.is_link():
                note = 'link'
            else:
                note = 'unit'
            cls.add_content_option(unit.unit_id, 'unit', unit.title, select,
                                   note=note)
            if unit.is_unit():
                if unit.pre_assessment:
                    pre = course.find_unit_by_id(unit.pre_assessment)
                    cls.add_content_option(
                        pre.unit_id, 'unit', pre.title, select,
                        note='pre-assessment', indent=2)
                for lesson in course.get_lessons(unit.unit_id):
                    cls.add_content_option(
                        lesson.lesson_id, 'lesson', lesson.title, select,
                        indent=1)
                if unit.post_assessment:
                    post = course.find_unit_by_id(unit.post_assessment)
                    cls.add_content_option(
                        post.unit_id, 'unit', post.title, select,
                        note='post-assessment', indent=2)
        return select

    @classmethod
    def construct_entity(cls, course):
        """Expose as function for convenience in wrapping this handler."""

        course_availability = course.get_course_availability()
        app_context = course.app_context
        settings = app_context.get_environ()
        reg_form = settings.setdefault('reg_form', {})
        publish = settings.setdefault('publish', {})

        # Course content associated with existing availability triggers could
        # have been deleted since the trigger itself was created. If the
        # content whose availability was meant to be updated by the trigger
        # has been deleted, also discard the obsolete trigger and do not
        # display it in the Publish > Availability form. (It displays
        # incorrectly anyway, using the first <option> since the trigger
        # content key value is non longer present in the <select>.
        #
        # Saving the resulting form will then omit the obsolete triggers.
        # The UpdateCourseAvailability cron job also detects these obsolete
        # triggers and discards them as well.
        triggers = publish.get('triggers', [])
        selectable_content = cls.content_select(course)
        triggers_with_content = []
        for trigger in triggers:
            content_key = trigger.get('content')
            if content_key in selectable_content:
                triggers_with_content.append(trigger)
            else:
                cls.log_trigger_error(
                    trigger, what='OBSOLETE',
                    ns=app_context.get_namespace_name(),
                    cause=cls.MISSING_CONTENT_FMT % content_key)

        entity = {
            'course_availability': course_availability,
            'whitelist': reg_form.get('whitelist', ''),
            'element_settings': cls.traverse_course(course),
            'availability_triggers': triggers_with_content,
        }
        return entity

    def get(self):
        if not roles.Roles.is_user_allowed(
            self.app_context, custom_module,
            constants.MODIFY_AVAILABILITY_PERMISSION):
            transforms.send_json_response(self, 401, 'Access denied.')
            return

        entity = self.construct_entity(self.get_course())
        transforms.send_json_response(
            self, 200, 'OK.', payload_dict=entity,
            xsrf_token=crypto.XsrfTokenManager.create_xsrf_token(self.ACTION))

    def put(self):
        self.classmethod_put(self)

    @classmethod
    def classmethod_put(cls, handler):
        """Expose as function for convenience in wrapping this hander."""

        request = transforms.loads(handler.request.get('request'))
        response_payload = {
            'key': handler.app_context.get_namespace_name()
        }

        # Check access permissions.  Not coming through dashboard, so must
        # do these for ourselves.
        if not handler.assert_xsrf_token_or_fail(request, handler.ACTION,
                                                 response_payload):
            return
        if not roles.Roles.is_user_allowed(
            handler.app_context, custom_module,
            constants.MODIFY_AVAILABILITY_PERMISSION):
            transforms.send_json_response(handler, 401, 'Access denied.',
                                          payload_dict=response_payload)
            return

        course = handler.get_course()
        settings = handler.app_context.get_environ()
        payload = transforms.loads(request.get('payload', '{}'))

        # Course-level changes: user whitelist, available/browsable/registerable
        whitelist = payload.get('whitelist')
        if whitelist is not None:
            settings['reg_form']['whitelist'] = whitelist

        triggers = payload.get('availability_triggers')
        if triggers is not None:
            settings.setdefault('publish', {})['triggers'] = triggers

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
                raise ValueError(cls.UNEXPECTED_CONTENT_FMT % item['type'])
            if element:
                if 'availability' in item:
                    element.availability = item['availability']
                if 'shown_when_unavailable' in item:
                    element.shown_when_unavailable = (
                        item['shown_when_unavailable'])
        course.save()
        transforms.send_json_response(
            handler, 200, 'Saved.', payload_dict=response_payload)

    @classmethod
    def log_trigger_error(cls, trigger,
                          what='INVALID', why='content', ns='', cause=''):
        """Assemble a trigger error message from optional parts and log it."""
        # "INVALID content in...
        parts = ["%s '%s' in" % (what, why)]
        if ns:
            # "INVALID content in ns_foo...
            parts.append('"%s"' % ns)
        # "INVALID content in... trigger: {avail...} ...
        parts.append('trigger: %s' % trigger)
        # "INVALID content in... trigger: {avail...} cause: ValueError: ...
        if cause:
            parts.append('cause: "%s"' % cause)
        logging.error(' '.join(parts))


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
