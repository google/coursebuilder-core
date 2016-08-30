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
import os

import appengine_config
from common import crypto
from common import schema_fields
from controllers import utils
from models import roles
from models import services
from models import transforms
from modules.courses import availability_options
from modules.courses import constants
from modules.courses import messages
from modules.courses import triggers
from modules.dashboard import dashboard
from modules.oeditor import oeditor

custom_module = None

TEMPLATES_DIR = os.path.join(
    appengine_config.BUNDLE_ROOT, 'modules', 'courses', 'templates')


def _authorize_put(handler):
    """Common function for handlers.  Verifies user, gets common settings."""

    request = transforms.loads(handler.request.get('request'))
    response_payload = {
        'key': handler.app_context.get_namespace_name(),
    }
    if not handler.assert_xsrf_token_or_fail(request, handler.ACTION,
                                             response_payload):
        return None, None, None, None
    if not roles.Roles.is_user_allowed(
        handler.app_context, custom_module,
        constants.MODIFY_AVAILABILITY_PERMISSION):
        transforms.send_json_response(handler, 401, 'Access denied.',
                                      payload_dict=response_payload)
        return None, None, None, None

    course = handler.get_course()
    settings = handler.app_context.get_environ()
    payload = transforms.loads(request.get('payload', '{}'))
    return course, settings, payload, response_payload


class AvailabilityRESTHandler(utils.BaseRESTHandler):

    ACTION = 'availability'
    URL = 'rest/availability'

    # Besides their use in AvailabilityRESTHandler, these values exist as
    # public contents for use by (at least): courses_pageobjects.py (and thus
    # indirectly courses_integration_tests.py) and student_groups.py.
    ADD_TRIGGER_BUTTON_TEXT = 'Add date/time availability change'

    # Used by both this REST handler and the one in modules/student_groups
    # to style the course-wide and per-student-group schemas of the
    # "Publish > Availability" form.
    AVAILABILITY_MANAGER_CSS = (
        'inputEx-Group new-form-layout hidden-header availability-manager')

    # Common schema field names shared by both the course-wide and
    # per-student-group "Publish > Availability" forms.
    COURSE_AVAILABILITY_SETTING = 'course_availability'
    ELEMENT_SETTINGS = 'element_settings'
    WHITELIST_SETTING = 'whitelist'

    AVAILABILITY_FIELD = triggers.AvailabilityTrigger.FIELD_NAME
    DATETIME_FIELD = triggers.DateTimeTrigger.FIELD_NAME
    CONTENT_FIELD = triggers.ContentTrigger.FIELD_NAME

    # Match the "Content Availability" element <select> to that of triggers.
    AVAILABILITY_CSS = triggers.AvailabilityTrigger.availability_css()
    SELECT_WRAPPER_CSS = 'gcb-select inputEx-fieldWrapper'
    AVAILABILITY_WRAPPER_CSS = SELECT_WRAPPER_CSS
    ELEM_AVAILABILITY_CSS = AVAILABILITY_CSS

    # Used by both the course-wide student whitelist <textarea> and the
    # student group members <textarea> to style the outer wrapper <div>.
    WHITELIST_WRAPPER_CSS = 'gcb-textarea inputEx-fieldWrapper'

    # modules/student_groups "patches" the "Publish > Availability" form
    # in order to add support for per-student-group availability settings.
    # student_group_availability.js in that module toggles between showing the
    # course-wide and per-student-group settings via two CSS classes. This
    # CSS class needs to be applied to every top-level property in the
    # "Publish > Availability" form schema.
    _COURSE_WIDE_SCOPE_CSS = 'course-wide-scope'
    _COURSE_WIDE_WRAPPER_CSS = 'inputEx-fieldWrapper ' + _COURSE_WIDE_SCOPE_CSS

    _COURSE_AVAILABILITY_CSS = (AVAILABILITY_CSS + ' ' +
        availability_options.option_to_css(COURSE_AVAILABILITY_SETTING))
    _COURSE_AVAILABILITY_WRAPPER_CSS = (
        SELECT_WRAPPER_CSS + ' ' + _COURSE_WIDE_SCOPE_CSS)

    _WHITELIST_WRAPPER_CSS = (
        _COURSE_WIDE_SCOPE_CSS + ' ' + WHITELIST_WRAPPER_CSS)

    # className for "Content Availability" FieldArray.
    _ELEM_ARRAY_CSS = 'content-availability inputEx-Field inputEx-ListField'

    # wrapperClassName for "Content Availability" FieldArray.
    _ELEM_WRAPPER_CSS = 'section-with-heading inputEx-fieldWrapper'

    # className for the FieldRegistry of a complex element array item within
    # the "Content Availability" FieldArray.
    _ELEM_SUB_REG_CSS = (
        'content-element inputEx-Group inputEx-ListField-subFieldEl')

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
    def get_milestone_trigger_schema(cls, milestone,
                                     avail_select, trigger_cls):
        title = '{} Availability'.format(
            availability_options.option_to_title(milestone))
        desc = messages.MILESTONE_TRIGGER_DESCRIPTION_FMT.format(milestone)
        milestone_trigger = schema_fields.FieldRegistry(title,
            description=services.help_urls.make_learn_more_message(
                desc, messages.MILESTONE_TRIGGERS_LEARN_MORE),
            extra_schema_dict_values={
                'className': trigger_cls.registry_css()})
        milestone_trigger.add_property(schema_fields.SchemaField(
            'milestone', None, 'string', i18n=False, hidden=True,
            extra_schema_dict_values={
                'className': trigger_cls.milestone_css()}))
        milestone_trigger.add_property(schema_fields.SchemaField(
            cls.DATETIME_FIELD, None, 'datetime',
            i18n=False, optional=True, extra_schema_dict_values={
                'className': trigger_cls.when_css()}))
        milestone_trigger.add_property(schema_fields.SchemaField(
            cls.AVAILABILITY_FIELD, None, 'string',
            i18n=False, optional=True,
            select_data=avail_select, extra_schema_dict_values={
                'className': trigger_cls.availability_css()}))
        return milestone_trigger

    @classmethod
    def get_milestone_array_schema(cls, milestone, desc_fmt, trigger_cls=None,
                                   scope_css=None, avail_select=None):
        title = availability_options.option_to_title(milestone)

        if trigger_cls is None:
            trigger_cls = triggers.MilestoneTrigger
        if avail_select is None:
            avail_select = availability_options.COURSE_WITH_NONE_SELECT_DATA
        item_type = cls.get_milestone_trigger_schema(
            milestone, avail_select, trigger_cls)

        if scope_css is None:
            scope_css = cls._COURSE_WIDE_SCOPE_CSS
        extra_css = (scope_css + ' ' +
                     availability_options.option_to_css(milestone))
        classname = trigger_cls.array_css(extra_css=extra_css)
        wrapper_classname = trigger_cls.array_wrapper_css(
            extra_css=extra_css)
        ms_text = availability_options.option_to_text(milestone)
        desc = desc_fmt.format(milestone=ms_text)
        return schema_fields.FieldArray(
            milestone, title, desc, item_type=item_type, optional=True,
            extra_schema_dict_values={
                'className': classname,
                'wrapperClassName': wrapper_classname})

    @classmethod
    def get_common_element_schema(cls):
        element_settings = schema_fields.FieldRegistry('Element Settings',
            description='Availability settings for course elements',
            extra_schema_dict_values={
                'className': cls._ELEM_SUB_REG_CSS})
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
            extra_schema_dict_values={
                'className': 'title inputEx-Field'}))
        return element_settings

    @classmethod
    def get_course_wide_element_schema(cls):
        element_settings = cls.get_common_element_schema()
        element_settings.add_property(schema_fields.SchemaField(
            'shown_when_unavailable', 'Shown When Private', 'boolean',
            description=services.help_urls.make_learn_more_message(
                messages.AVAILABILITY_SHOWN_WHEN_UNAVAILABLE_DESCRIPTION,
                'course:availability:shown_when_unavailable'),
            i18n=False, optional=True, extra_schema_dict_values={
                'className': 'shown inputEx-Field inputEx-CheckBox'}))
        element_settings.add_property(schema_fields.SchemaField(
            cls.AVAILABILITY_FIELD, 'Availability', 'string',
            description=services.help_urls.make_learn_more_message(
                messages.AVAILABILITY_AVAILABILITY_DESCRIPTION,
                'course:availability:availability'),
            select_data=availability_options.ELEMENT_SELECT_DATA,
            i18n=False, optional=True, extra_schema_dict_values={
                'className': cls.ELEM_AVAILABILITY_CSS}))
        return element_settings

    @classmethod
    def get_element_array_schema(cls, item_type, scope_css=None):
        if scope_css is None:
            scope_css = cls._COURSE_WIDE_SCOPE_CSS
        wrapper_classname = ' '.join([scope_css, cls._ELEM_WRAPPER_CSS])
        return schema_fields.FieldArray(
            cls.ELEMENT_SETTINGS, 'Content Availability', item_type=item_type,
            optional=True, extra_schema_dict_values={
                'className': cls._ELEM_ARRAY_CSS,
                'wrapperClassName': wrapper_classname})

    @classmethod
    def get_content_trigger_schema(
        cls, course,
        content_trigger_resource_description,
        content_trigger_when_description,
        content_trigger_avail_description,
        avail_select=None):

        tct = triggers.ContentTrigger
        content_trigger = schema_fields.FieldRegistry('Trigger',
            description='Date/Time Triggered Availability Change',
            extra_schema_dict_values={
                'className': tct.registry_css()})
        content_trigger.add_property(schema_fields.SchemaField(
            cls.CONTENT_FIELD, 'For course content:', 'string',
            description=content_trigger_resource_description,
            i18n=False, select_data=cls.content_select(course).items(),
            extra_schema_dict_values={
                'className': tct.content_css()}))
        content_trigger.add_property(schema_fields.SchemaField(
            cls.DATETIME_FIELD, 'At this date & UTC hour:', 'datetime',
            description=content_trigger_when_description,
            i18n=False, extra_schema_dict_values={
                'className': tct.when_css()}))
        if avail_select is None:
            avail_select = availability_options.ELEMENT_SELECT_DATA
        title = 'Change {} to:'.format(tct.kind())
        content_trigger.add_property(schema_fields.SchemaField(
            cls.AVAILABILITY_FIELD, title, 'string',
            description=content_trigger_avail_description,
            i18n=False, select_data=avail_select,
            extra_schema_dict_values={
                'className': tct.availability_css()}))
        return content_trigger

    @classmethod
    def get_content_trigger_array_schema(cls, trigger_cls, item_type,
                                         content_triggers_description,
                                         scope_css=None):
        if scope_css is None:
            scope_css = cls._COURSE_WIDE_SCOPE_CSS
        wrapper_classname = trigger_cls.array_wrapper_css(extra_css=scope_css)
        return schema_fields.FieldArray(
            trigger_cls.SETTINGS_NAME,
            'Change Course Content Availability at Date/Time',
            item_type=item_type, optional=True,
            description=services.help_urls.make_learn_more_message(
                content_triggers_description,
                messages.CONTENT_TRIGGERS_LEARN_MORE),
            extra_schema_dict_values={
                'className': trigger_cls.array_css(),
                'wrapperClassName': wrapper_classname,
                'listAddLabel': cls.ADD_TRIGGER_BUTTON_TEXT,
                'listRemoveLabel': 'Delete'})

    @classmethod
    def get_schema(cls, course):
        course_wide_settings = schema_fields.FieldRegistry('Availability',
            description='Course Availability Settings',
            extra_schema_dict_values={
                'className': cls.AVAILABILITY_MANAGER_CSS})

        course_wide_settings.add_property(schema_fields.SchemaField(
            cls.COURSE_AVAILABILITY_SETTING, 'Course Availability', 'string',
            description=messages.COURSE_WIDE_AVAILABILITY_DESCRIPTION,
            select_data=availability_options.COURSE_SELECT_DATA,
            i18n=False, optional=True, extra_schema_dict_values={
                'className': cls._COURSE_AVAILABILITY_CSS,
                'wrapperClassName': cls._COURSE_AVAILABILITY_WRAPPER_CSS}))

        for milestone in constants.COURSE_MILESTONES:
            course_wide_settings.add_property(cls.get_milestone_array_schema(
                milestone, messages.MILESTONE_TRIGGER_DESC_FMT))

        element_settings = cls.get_course_wide_element_schema()
        course_wide_settings.add_property(
            cls.get_element_array_schema(element_settings))

        course_wide_settings.add_property(schema_fields.SchemaField(
            cls.WHITELIST_SETTING, 'Students Allowed to Access', 'text',
            description=messages.COURSE_WIDE_STUDENTS_ALLOWED_DESCRIPTION,
            i18n=False, optional=True, extra_schema_dict_values={
                'wrapperClassName': cls._WHITELIST_WRAPPER_CSS}))

        content_trigger = cls.get_content_trigger_schema(
            course,
            messages.CONTENT_TRIGGER_RESOURCE_DESCRIPTION,
            messages.CONTENT_TRIGGER_WHEN_DESCRIPTION,
            messages.CONTENT_TRIGGER_AVAIL_DESCRIPTION)
        course_wide_settings.add_property(
            cls.get_content_trigger_array_schema(
                triggers.ContentTrigger, content_trigger,
                messages.CONTENT_TRIGGERS_DESCRIPTION))
        return course_wide_settings

    @classmethod
    def add_unit(cls, unit, elements, indent=False):
        elements.append({
            'type': 'unit',
            'id': unit.unit_id,
            'indent': indent,
            'name': unit.title,
            cls.AVAILABILITY_FIELD: unit.availability,
            'shown_when_unavailable': unit.shown_when_unavailable,
            })

    @classmethod
    def add_lesson(cls, lesson, elements):
        elements.append({
            'type': 'lesson',
            'id': lesson.lesson_id,
            'indent': True,
            'name': lesson.title,
            cls.AVAILABILITY_FIELD: lesson.availability,
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
        value = triggers.ContentTrigger.encode_content_type_and_id(
            content_type, content_id)
        text = title
        if note:
            text = u'{} ({})'.format(text, note)
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
        env = course.app_context.get_environ()
        entity = {
            cls.COURSE_AVAILABILITY_SETTING:
                course.get_course_availability_from_environ(env),
            cls.WHITELIST_SETTING:
                course.get_whitelist_from_environ(env),
            cls.ELEMENT_SETTINGS:
                cls.traverse_course(course),
        }

        course_triggers = triggers.MilestoneTrigger.for_form(
            env, course=course)
        entity.update(course_triggers)

        content_triggers = triggers.ContentTrigger.for_form(
            env, selectable_content=cls.content_select(course))
        entity.update(content_triggers)
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

        course, env, payload, response_payload = _authorize_put(handler)
        if not course:
            return

        # Date/Time triggers:
        #   unit and lesson availability, course-wide availability
        triggers.MilestoneTrigger.payload_into_settings(payload, course, env)
        triggers.ContentTrigger.payload_into_settings(payload, course, env)

        # Course-level settings: user whitelist
        course.set_whitelist_into_environ(payload.get('whitelist'), env)

        # Course-level changes:
        #   course-wide availability (available/browsable/registerable)
        course.set_course_availability_into_environ(
            payload.get('course_availability'), env)

        course.save_settings(env)

        # Unit and lesson availability, visibility from syllabus list
        for item in payload.get(cls.ELEMENT_SETTINGS, []):
            if item['type'] == 'unit':
                element = course.find_unit_by_id(item['id'])
            elif item['type'] == 'lesson':
                element = course.find_lesson_by_id(None, item['id'])
            else:
                tct = triggers.ContentTrigger
                raise ValueError(
                    tct.UNEXPECTED_CONTENT_FMT.format(
                        item['type'], tct.ALLOWED_CONTENT_TYPES))
            if element:
                if cls.AVAILABILITY_FIELD in item:
                    element.availability = item[cls.AVAILABILITY_FIELD]
                if 'shown_when_unavailable' in item:
                    element.shown_when_unavailable = (
                        item['shown_when_unavailable'])
        course.save()
        transforms.send_json_response(
            handler, 200, 'Saved.', payload_dict=response_payload)


class MultiCourseAvailabilityRESTHandler(utils.BaseRESTHandler):
    """Support multi-course for availability.

    MultiCourseAvailabilityRESTHandler is responsible for coping with the
    entire availability page submissions.  It's not a good fit for one-off
    changes to single fields, so we add a separate handler for the UX
    controls for changing one item across multiple courses.
    """

    URL = 'rest/multi_availability'
    ACTION = AvailabilityRESTHandler.ACTION

    def put(self):
        course, settings, payload, response_payload = _authorize_put(self)
        if not course:
            return

        course_availability = payload.get('course_availability')
        if course_availability:
            course.set_course_availability(course_availability)
        transforms.send_json_response(
            self, 200, 'Saved.', payload_dict=response_payload)


class MultiCourseSetStartEndRESTHandler(utils.BaseRESTHandler):
    """Support multi-course for availability.

    MultiCourseAvailabilityRESTHandler is responsible for coping with the
    entire availability page submissions.  It's not a good fit for one-off
    changes to single fields, so we add a separate handler for the UX
    controls for changing one item across multiple courses.
    """

    URL = 'rest/multi_set_start_end'
    ACTION = AvailabilityRESTHandler.ACTION

    def put(self):
        course, settings, payload, response_payload = _authorize_put(self)
        if not course:
            return

        triggers.MilestoneTrigger.payload_into_settings(
            payload, course, settings,
            semantics=triggers.DateTimeTrigger.SET_WILL_MERGE)
        course.save_settings(settings)
        transforms.send_json_response(
            self, 200, 'Saved.', payload_dict=response_payload)


class MultiCourseClearStartEndRESTHandler(utils.BaseRESTHandler):
    """Support multi-course for availability.

    MultiCourseAvailabilityRESTHandler is responsible for coping with the
    entire availability page submissions.  It's not a good fit for one-off
    changes to single fields, so we add a separate handler for the UX
    controls for changing one item across multiple courses.
    """

    URL = 'rest/multi_clear_start_end'
    ACTION = AvailabilityRESTHandler.ACTION

    def put(self):
        course, settings, payload, response_payload = _authorize_put(self)
        if not course:
            return

        milestone = payload.get('milestone')
        triggers.MilestoneTrigger.clear_from_settings(
            settings, milestone=milestone, course=course)
        course.save_settings(settings)
        transforms.send_json_response(
            self, 200, 'Saved.', payload_dict=response_payload)


def get_namespaced_handlers():
    return [
        ('/' + AvailabilityRESTHandler.URL, AvailabilityRESTHandler),
        ('/' + MultiCourseAvailabilityRESTHandler.URL,
         MultiCourseAvailabilityRESTHandler),
        ('/' + MultiCourseSetStartEndRESTHandler.URL,
         MultiCourseSetStartEndRESTHandler),
        ('/' + MultiCourseClearStartEndRESTHandler.URL,
         MultiCourseClearStartEndRESTHandler),
    ]


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
