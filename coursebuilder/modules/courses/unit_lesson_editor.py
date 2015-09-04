# Copyright 2013 Google Inc. All Rights Reserved.
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

"""Classes supporting unit and lesson editing."""

__author__ = 'John Orr (jorr@google.com)'

import cgi
import logging
import urllib

from common import utils as common_utils
from controllers import sites
from controllers.utils import ApplicationHandler
from controllers.utils import BaseRESTHandler
from controllers.utils import XsrfTokenManager
from models import courses
from models import resources_display
from models import custom_units
from models import roles
from models import transforms
from modules.oeditor import oeditor
from tools import verify


class CourseOutlineRights(object):
    """Manages view/edit rights for course outline."""

    @classmethod
    def can_view(cls, handler):
        return cls.can_edit(handler)

    @classmethod
    def can_edit(cls, handler):
        return roles.Roles.is_course_admin(handler.app_context)

    @classmethod
    def can_delete(cls, handler):
        return cls.can_edit(handler)

    @classmethod
    def can_add(cls, handler):
        return cls.can_edit(handler)


class UnitLessonEditor(ApplicationHandler):
    """An editor for the unit and lesson titles."""

    HIDE_ACTIVITY_ANNOTATIONS = [
        (['properties', 'activity_title', '_inputex'], {'_type': 'hidden'}),
        (['properties', 'activity_listed', '_inputex'], {'_type': 'hidden'}),
        (['properties', 'activity', '_inputex'], {'_type': 'hidden'}),
    ]

    def get_import_course(self):
        """Shows setup form for course import."""

        template_values = {}
        template_values['page_title'] = self.format_title('Import Course')
        annotations = ImportCourseRESTHandler.SCHEMA_ANNOTATIONS_DICT()
        if not annotations:
            template_values['main_content'] = 'No courses to import from.'
            self.render_page(template_values)
            return

        exit_url = self.canonicalize_url('/dashboard')
        rest_url = self.canonicalize_url(ImportCourseRESTHandler.URI)
        form_html = oeditor.ObjectEditor.get_html_for(
            self,
            ImportCourseRESTHandler.SCHEMA_JSON,
            annotations,
            None, rest_url, exit_url,
            auto_return=True,
            save_button_caption='Import',
            required_modules=ImportCourseRESTHandler.REQUIRED_MODULES)

        template_values = {}
        template_values['page_title'] = self.format_title('Import Course')
        template_values['main_content'] = form_html
        self.render_page(template_values)

    def post_add_lesson(self):
        """Adds new lesson to a first unit of the course."""
        course = courses.Course(self)
        target_unit = None
        if self.request.get('unit_id'):
            target_unit = course.find_unit_by_id(self.request.get('unit_id'))
        else:
            for unit in course.get_units():
                if unit.type == verify.UNIT_TYPE_UNIT:
                    target_unit = unit
                    break
        if target_unit:
            lesson = course.add_lesson(target_unit)
            course.save()
            # TODO(psimakov): complete 'edit_lesson' view
            self.redirect(self.get_action_url(
                'edit_lesson', key=lesson.lesson_id,
                extra_args={'is_newly_created': 1}))
        else:
            self.redirect('/dashboard')

    def post_add_unit(self):
        """Adds new unit to a course."""
        course = courses.Course(self)
        unit = course.add_unit()
        course.save()
        self.redirect(self.get_action_url(
            'edit_unit', key=unit.unit_id, extra_args={'is_newly_created': 1}))

    def post_add_link(self):
        """Adds new link to a course."""
        course = courses.Course(self)
        link = course.add_link()
        link.href = ''
        course.save()
        self.redirect(self.get_action_url(
            'edit_link', key=link.unit_id, extra_args={'is_newly_created': 1}))

    def post_add_assessment(self):
        """Adds new assessment to a course."""
        course = courses.Course(self)
        assessment = course.add_assessment()
        course.save()
        self.redirect(self.get_action_url(
            'edit_assessment', key=assessment.unit_id,
            extra_args={'is_newly_created': 1}))

    def post_add_custom_unit(self):
        """Adds a custom unit to a course."""
        course = courses.Course(self)
        custom_unit_type = self.request.get('unit_type')
        custom_unit = course.add_custom_unit(custom_unit_type)
        course.save()
        self.redirect(self.get_action_url(
            'edit_custom_unit', key=custom_unit.unit_id,
            extra_args={'is_newly_created': 1,
                        'unit_type': custom_unit_type}))

    def post_set_draft_status(self):
        """Sets the draft status of a course component.

        Only works with CourseModel13 courses, but the REST handler
        is only called with this type of courses.
        """
        key = self.request.get('key')
        if not CourseOutlineRights.can_edit(self):
            transforms.send_json_response(
                self, 401, 'Access denied.', {'key': key})
            return

        course = courses.Course(self)
        component_type = self.request.get('type')
        if component_type == 'unit':
            course_component = course.find_unit_by_id(key)
        elif component_type == 'lesson':
            course_component = course.find_lesson_by_id(None, key)
        else:
            transforms.send_json_response(
                self, 401, 'Invalid key.', {'key': key})
            return

        set_draft = self.request.get('set_draft')
        if set_draft == '1':
            set_draft = True
        elif set_draft == '0':
            set_draft = False
        else:
            transforms.send_json_response(
                self, 401, 'Invalid set_draft value, expected 0 or 1.',
                {'set_draft': set_draft}
            )
            return

        course_component.now_available = not set_draft
        course.save()

        transforms.send_json_response(
            self,
            200,
            'Draft status set to %s.' % (
                resources_display.DRAFT_TEXT if set_draft else
                resources_display.PUBLISHED_TEXT
            ), {
                'is_draft': set_draft
            }
        )
        return

    def _render_edit_form_for(
        self, rest_handler_cls, title, additional_dirs=None,
        annotations_dict=None, delete_xsrf_token='delete-unit',
        extra_js_files=None, extra_css_files=None, schema=None):
        """Renders an editor form for a given REST handler class."""
        annotations_dict = annotations_dict or []
        if schema:
            schema_json = schema.get_json_schema()
            annotations_dict = schema.get_schema_dict() + annotations_dict
        else:
            schema_json = rest_handler_cls.SCHEMA_JSON
            if not annotations_dict:
                annotations_dict = rest_handler_cls.SCHEMA_ANNOTATIONS_DICT

        key = self.request.get('key')

        extra_args = {}
        if self.request.get('is_newly_created'):
            extra_args['is_newly_created'] = 1

        exit_url = self.canonicalize_url('/dashboard')
        rest_url = self.canonicalize_url(rest_handler_cls.URI)
        delete_url = '%s?%s' % (
            self.canonicalize_url(rest_handler_cls.URI),
            urllib.urlencode({
                'key': key,
                'xsrf_token': cgi.escape(
                    self.create_xsrf_token(delete_xsrf_token))
                }))

        def extend_list(target_list, ext_name):
            # Extend the optional arg lists such as extra_js_files by an
            # optional list field on the REST handler class. Used to provide
            # seams for modules to add js files, etc. See LessonRESTHandler
            if hasattr(rest_handler_cls, ext_name):
                target_list = target_list or []
                return (target_list or []) + getattr(rest_handler_cls, ext_name)
            return target_list

        form_html = oeditor.ObjectEditor.get_html_for(
            self,
            schema_json,
            annotations_dict,
            key, rest_url, exit_url,
            extra_args=extra_args,
            delete_url=delete_url, delete_method='delete',
            read_only=not self.app_context.is_editable_fs(),
            required_modules=rest_handler_cls.REQUIRED_MODULES,
            additional_dirs=extend_list(additional_dirs, 'ADDITIONAL_DIRS'),
            extra_css_files=extend_list(extra_css_files, 'EXTRA_CSS_FILES'),
            extra_js_files=extend_list(extra_js_files, 'EXTRA_JS_FILES'))

        template_values = {}
        template_values['page_title'] = self.format_title('Edit %s' % title)
        template_values['main_content'] = form_html
        self.render_page(template_values, in_action='outline')

    def get_edit_unit(self):
        """Shows unit editor."""
        self._render_edit_form_for(
            UnitRESTHandler, 'Unit',
            annotations_dict=UnitRESTHandler.get_annotations_dict(
                courses.Course(self), int(self.request.get('key'))))

    def get_edit_custom_unit(self):
        """Shows custom_unit_editor."""
        custom_unit_type = self.request.get('unit_type')
        custom_unit = custom_units.UnitTypeRegistry.get(custom_unit_type)
        rest_handler = custom_unit.rest_handler
        self._render_edit_form_for(
            rest_handler,
            custom_unit.name,
            annotations_dict=rest_handler.get_schema_annotations_dict(
                courses.Course(self)))

    def get_edit_link(self):
        """Shows link editor."""
        self._render_edit_form_for(LinkRESTHandler, 'Link')

    def get_edit_assessment(self):
        """Shows assessment editor."""
        self._render_edit_form_for(
            AssessmentRESTHandler, 'Assessment',
            extra_js_files=['assessment_editor_lib.js', 'assessment_editor.js'])

    def get_edit_lesson(self):
        """Shows the lesson/activity editor."""
        key = self.request.get('key')
        course = courses.Course(self)
        lesson = course.find_lesson_by_id(None, key)
        annotations_dict = (
            None if lesson.has_activity
            else UnitLessonEditor.HIDE_ACTIVITY_ANNOTATIONS)
        schema = LessonRESTHandler.get_schema(course, key)
        if courses.has_only_new_style_activities(course):
            schema.get_property('objectives').extra_schema_dict_values[
              'excludedCustomTags'] = set(['gcb-activity'])
        self._render_edit_form_for(
            LessonRESTHandler, 'Lessons and Activities',
            schema=schema,
            annotations_dict=annotations_dict,
            delete_xsrf_token='delete-lesson',
            extra_js_files=['lesson_editor.js'])

    def get_in_place_lesson_editor(self):
        """Shows the lesson editor iframed inside a lesson page."""
        if not self.app_context.is_editable_fs():
            return

        key = self.request.get('key')

        course = courses.Course(self)
        lesson = course.find_lesson_by_id(None, key)
        annotations_dict = (
            None if lesson.has_activity
            else UnitLessonEditor.HIDE_ACTIVITY_ANNOTATIONS)
        schema = LessonRESTHandler.get_schema(course, key)
        annotations_dict = schema.get_schema_dict() + annotations_dict

        if courses.has_only_new_style_activities(course):
            schema.get_property('objectives').extra_schema_dict_values[
              'excludedCustomTags'] = set(['gcb-activity'])

        extra_js_files = [
            'lesson_editor.js', 'in_place_lesson_editor_iframe.js'
        ] + LessonRESTHandler.EXTRA_JS_FILES

        form_html = oeditor.ObjectEditor.get_html_for(
            self,
            schema.get_json_schema(),
            annotations_dict,
            key, self.canonicalize_url(LessonRESTHandler.URI), None,
            required_modules=LessonRESTHandler.REQUIRED_MODULES,
            additional_dirs=LessonRESTHandler.ADDITIONAL_DIRS,
            extra_css_files=LessonRESTHandler.EXTRA_CSS_FILES,
            extra_js_files=extra_js_files)
        template = self.get_template('in_place_lesson_editor.html', [])
        template_values = {
            'form_html': form_html,
            'extra_css_href_list': self.EXTRA_CSS_HREF_LIST,
            'extra_js_href_list': self.EXTRA_JS_HREF_LIST
        }
        self.response.write(template.render(template_values))


class CommonUnitRESTHandler(BaseRESTHandler):
    """A common super class for all unit REST handlers."""

    # These functions are called with an updated unit object whenever a
    # change is saved.
    POST_SAVE_HOOKS = []

    def unit_to_dict(self, unit):
        """Converts a unit to a dictionary representation."""
        return resources_display.UnitTools(self.get_course()).unit_to_dict(unit)

    def apply_updates(self, unit, updated_unit_dict, errors):
        """Applies changes to a unit; modifies unit input argument."""
        resources_display.UnitTools(courses.Course(self)).apply_updates(
            unit, updated_unit_dict, errors)

    def get(self):
        """A GET REST method shared by all unit types."""
        key = self.request.get('key')

        if not CourseOutlineRights.can_view(self):
            transforms.send_json_response(
                self, 401, 'Access denied.', {'key': key})
            return

        unit = courses.Course(self).find_unit_by_id(key)
        if not unit:
            transforms.send_json_response(
                self, 404, 'Object not found.', {'key': key})
            return

        message = ['Success.']
        if self.request.get('is_newly_created'):
            unit_type = verify.UNIT_TYPE_NAMES[unit.type].lower()
            message.append(
                'New %s has been created and saved.' % unit_type)

        transforms.send_json_response(
            self, 200, '\n'.join(message),
            payload_dict=self.unit_to_dict(unit),
            xsrf_token=XsrfTokenManager.create_xsrf_token('put-unit'))

    def put(self):
        """A PUT REST method shared by all unit types."""
        request = transforms.loads(self.request.get('request'))
        key = request.get('key')

        if not self.assert_xsrf_token_or_fail(
                request, 'put-unit', {'key': key}):
            return

        if not CourseOutlineRights.can_edit(self):
            transforms.send_json_response(
                self, 401, 'Access denied.', {'key': key})
            return

        unit = courses.Course(self).find_unit_by_id(key)
        if not unit:
            transforms.send_json_response(
                self, 404, 'Object not found.', {'key': key})
            return

        payload = request.get('payload')
        errors = []

        try:
            updated_unit_dict = transforms.json_to_dict(
                transforms.loads(payload), self.SCHEMA_DICT)
            self.apply_updates(unit, updated_unit_dict, errors)
        except (TypeError, ValueError), ex:
            errors.append(str(ex))

        if not errors:
            course = courses.Course(self)
            assert course.update_unit(unit)
            course.save()
            common_utils.run_hooks(self.POST_SAVE_HOOKS, unit)
            transforms.send_json_response(self, 200, 'Saved.')
        else:
            transforms.send_json_response(self, 412, '\n'.join(errors))

    def delete(self):
        """Handles REST DELETE verb with JSON payload."""
        key = self.request.get('key')

        if not self.assert_xsrf_token_or_fail(
                self.request, 'delete-unit', {'key': key}):
            return

        if not CourseOutlineRights.can_delete(self):
            transforms.send_json_response(
                self, 401, 'Access denied.', {'key': key})
            return

        course = courses.Course(self)
        unit = course.find_unit_by_id(key)
        if not unit:
            transforms.send_json_response(
                self, 404, 'Object not found.', {'key': key})
            return

        course.delete_unit(unit)
        course.save()

        transforms.send_json_response(self, 200, 'Deleted.')


class UnitRESTHandler(CommonUnitRESTHandler):
    """Provides REST API to unit."""

    URI = '/rest/course/unit'
    SCHEMA = resources_display.ResourceUnit.get_schema(course=None, key=None)
    SCHEMA_JSON = SCHEMA.get_json_schema()
    SCHEMA_DICT = SCHEMA.get_json_schema_dict()
    REQUIRED_MODULES = [
        'inputex-string', 'inputex-select', 'gcb-uneditable',
        'inputex-list', 'inputex-hidden', 'inputex-number', 'inputex-integer',
        'inputex-checkbox', 'gcb-rte']

    @classmethod
    def get_annotations_dict(cls, course, this_unit_id):
        # The set of available assesments needs to be dynamically
        # generated and set as selection choices on the form.
        # We want to only show assessments that are not already
        # selected by other units.
        available_assessments = {}
        referenced_assessments = {}
        for unit in course.get_units():
            if unit.type == verify.UNIT_TYPE_ASSESSMENT:
                model_version = course.get_assessment_model_version(unit)
                track_labels = course.get_unit_track_labels(unit)
                # Don't allow selecting old-style assessments, which we
                # can't display within Unit page.
                # Don't allow selection of assessments with parents
                if (model_version != courses.ASSESSMENT_MODEL_VERSION_1_4 and
                    not track_labels):
                    available_assessments[unit.unit_id] = unit
            elif (unit.type == verify.UNIT_TYPE_UNIT and
                  this_unit_id != unit.unit_id):
                if unit.pre_assessment:
                    referenced_assessments[unit.pre_assessment] = True
                if unit.post_assessment:
                    referenced_assessments[unit.post_assessment] = True
        for referenced in referenced_assessments:
            if referenced in available_assessments:
                del available_assessments[referenced]

        schema = resources_display.ResourceUnit.get_schema(course, this_unit_id)
        choices = [(-1, '-- None --')]
        for assessment_id in sorted(available_assessments):
            choices.append(
                (assessment_id, available_assessments[assessment_id].title))
        schema.get_property('pre_assessment').set_select_data(choices)
        schema.get_property('post_assessment').set_select_data(choices)

        return schema.get_schema_dict()


class LinkRESTHandler(CommonUnitRESTHandler):
    """Provides REST API to link."""

    URI = '/rest/course/link'
    SCHEMA = resources_display.ResourceLink.get_schema(course=None, key=None)
    SCHEMA_JSON = SCHEMA.get_json_schema()
    SCHEMA_DICT = SCHEMA.get_json_schema_dict()
    SCHEMA_ANNOTATIONS_DICT = SCHEMA.get_schema_dict()
    REQUIRED_MODULES = [
        'inputex-string', 'inputex-select', 'gcb-uneditable',
        'inputex-list', 'inputex-hidden', 'inputex-number', 'inputex-checkbox']


class ImportCourseRESTHandler(CommonUnitRESTHandler):
    """Provides REST API to course import."""

    URI = '/rest/course/import'

    SCHEMA_JSON = """
    {
        "id": "Import Course Entity",
        "type": "object",
        "description": "Import Course",
        "properties": {
            "course" : {"type": "string"}
            }
    }
    """

    SCHEMA_DICT = transforms.loads(SCHEMA_JSON)

    REQUIRED_MODULES = [
        'inputex-string', 'inputex-select', 'gcb-uneditable']

    @classmethod
    def _get_course_list(cls):
        # Make a list of courses user has the rights to.
        course_list = []
        for acourse in sites.get_all_courses():
            if not roles.Roles.is_course_admin(acourse):
                continue
            if acourse == sites.get_course_for_current_request():
                continue

            atitle = '%s (%s)' % (acourse.get_title(), acourse.get_slug())

            course_list.append({
                'value': acourse.raw, 'label': cgi.escape(atitle)})
        return course_list

    @classmethod
    def SCHEMA_ANNOTATIONS_DICT(cls):
        """Schema annotations are dynamic and include a list of courses."""
        course_list = cls._get_course_list()
        if not course_list:
            return None

        # Format annotations.
        return [
            (['title'], 'Import Course'),
            (
                ['properties', 'course', '_inputex'],
                {
                    'label': 'Available Courses',
                    '_type': 'select',
                    'choices': course_list})]

    def get(self):
        """Handles REST GET verb and returns an object as JSON payload."""
        if not CourseOutlineRights.can_view(self):
            transforms.send_json_response(self, 401, 'Access denied.', {})
            return

        first_course_in_dropdown = self._get_course_list()[0]['value']

        transforms.send_json_response(
            self, 200, None,
            payload_dict={'course': first_course_in_dropdown},
            xsrf_token=XsrfTokenManager.create_xsrf_token(
                'import-course'))

    def put(self):
        """Handles REST PUT verb with JSON payload."""
        request = transforms.loads(self.request.get('request'))

        if not self.assert_xsrf_token_or_fail(
                request, 'import-course', {'key': None}):
            return

        if not CourseOutlineRights.can_edit(self):
            transforms.send_json_response(self, 401, 'Access denied.', {})
            return

        payload = request.get('payload')
        course_raw = transforms.json_to_dict(
            transforms.loads(payload), self.SCHEMA_DICT)['course']

        source = None
        for acourse in sites.get_all_courses():
            if acourse.raw == course_raw:
                source = acourse
                break

        if not source:
            transforms.send_json_response(
                self, 404, 'Object not found.', {'raw': course_raw})
            return

        course = courses.Course(self)
        errors = []
        try:
            course.import_from(source, errors)
        except Exception as e:  # pylint: disable=broad-except
            logging.exception(e)
            errors.append('Import failed: %s' % e)

        if errors:
            transforms.send_json_response(self, 412, '\n'.join(errors))
            return

        course.save()
        transforms.send_json_response(self, 200, 'Imported.')


class AssessmentRESTHandler(CommonUnitRESTHandler):
    """Provides REST API to assessment."""

    URI = '/rest/course/assessment'

    SCHEMA = resources_display.ResourceAssessment.get_schema(
        course=None, key=None)

    SCHEMA_JSON = SCHEMA.get_json_schema()

    SCHEMA_DICT = SCHEMA.get_json_schema_dict()

    SCHEMA_ANNOTATIONS_DICT = SCHEMA.get_schema_dict()

    REQUIRED_MODULES = [
        'gcb-rte', 'inputex-select', 'inputex-string', 'inputex-textarea',
        'gcb-uneditable', 'inputex-integer', 'inputex-number', 'inputex-hidden',
        'inputex-checkbox', 'inputex-list']


class UnitLessonTitleRESTHandler(BaseRESTHandler):
    """Provides REST API to reorder unit and lesson titles."""

    URI = '/rest/course/outline'
    XSRF_TOKEN = 'unit-lesson-reorder'

    SCHEMA_JSON = """
        {
            "type": "object",
            "description": "Course Outline",
            "properties": {
                "outline": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "title": {"type": "string"},
                            "lessons": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "id": {"type": "string"},
                                        "title": {"type": "string"}
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        """

    SCHEMA_DICT = transforms.loads(SCHEMA_JSON)

    def put(self):
        """Handles REST PUT verb with JSON payload."""
        request = transforms.loads(self.request.get('request'))

        if not self.assert_xsrf_token_or_fail(
                request, self.XSRF_TOKEN, {'key': None}):
            return

        if not CourseOutlineRights.can_edit(self):
            transforms.send_json_response(self, 401, 'Access denied.', {})
            return

        payload = request.get('payload')
        payload_dict = transforms.json_to_dict(
            transforms.loads(payload), self.SCHEMA_DICT)
        course = courses.Course(self)
        course.reorder_units(payload_dict['outline'])
        course.save()

        transforms.send_json_response(self, 200, 'Saved.')


class LessonRESTHandler(BaseRESTHandler):
    """Provides REST API to handle lessons and activities."""

    URI = '/rest/course/lesson'

    REQUIRED_MODULES = [
        'inputex-string', 'gcb-rte', 'inputex-select', 'inputex-textarea',
        'gcb-uneditable', 'inputex-checkbox', 'inputex-hidden']

    # Enable modules to specify locations to load JS and CSS files
    ADDITIONAL_DIRS = []
    # Enable modules to add css files to be shown in the editor page.
    EXTRA_CSS_FILES = []
    # Enable modules to add js files to be shown in the editor page.
    EXTRA_JS_FILES = []

    # Enable other modules to add transformations to the schema.Each member must
    # be a function of the form:
    #     callback(lesson_field_registry)
    # where the argument is the root FieldRegistry for the schema
    SCHEMA_LOAD_HOOKS = []

    # Enable other modules to add transformations to the load. Each member must
    # be a function of the form:
    #     callback(lesson, lesson_dict)
    # and the callback should update fields of the lesson_dict, which will be
    # returned to the caller of a GET request.
    PRE_LOAD_HOOKS = []

    # Enable other modules to add transformations to the save. Each member must
    # be a function of the form:
    #     callback(lesson, lesson_dict)
    # and the callback should update fields of the lesson with values read from
    # the dict which was the payload of a PUT request.
    PRE_SAVE_HOOKS = []

    # These functions are called with an updated lesson object whenever a
    # change is saved.
    POST_SAVE_HOOKS = []

    @classmethod
    def get_schema(cls, course, key):
        lesson_schema = resources_display.ResourceLesson.get_schema(course, key)
        common_utils.run_hooks(cls.SCHEMA_LOAD_HOOKS, lesson_schema)
        return lesson_schema

    @classmethod
    def get_lesson_dict(cls, course, lesson):
        return cls.get_lesson_dict_for(course, lesson)

    @classmethod
    def get_lesson_dict_for(cls, course, lesson):
        lesson_dict = resources_display.ResourceLesson.get_data_dict(
            course, lesson.lesson_id)
        common_utils.run_hooks(cls.PRE_LOAD_HOOKS, lesson, lesson_dict)
        return lesson_dict

    def get(self):
        """Handles GET REST verb and returns lesson object as JSON payload."""

        if not CourseOutlineRights.can_view(self):
            transforms.send_json_response(self, 401, 'Access denied.', {})
            return

        key = self.request.get('key')
        course = courses.Course(self)
        lesson = course.find_lesson_by_id(None, key)
        assert lesson
        payload_dict = self.get_lesson_dict(course, lesson)

        message = ['Success.']
        if self.request.get('is_newly_created'):
            message.append('New lesson has been created and saved.')

        transforms.send_json_response(
            self, 200, '\n'.join(message),
            payload_dict=payload_dict,
            xsrf_token=XsrfTokenManager.create_xsrf_token('lesson-edit'))

    def put(self):
        """Handles PUT REST verb to save lesson and associated activity."""
        request = transforms.loads(self.request.get('request'))
        key = request.get('key')

        if not self.assert_xsrf_token_or_fail(
                request, 'lesson-edit', {'key': key}):
            return

        if not CourseOutlineRights.can_edit(self):
            transforms.send_json_response(
                self, 401, 'Access denied.', {'key': key})
            return

        course = courses.Course(self)
        lesson = course.find_lesson_by_id(None, key)
        if not lesson:
            transforms.send_json_response(
                self, 404, 'Object not found.', {'key': key})
            return

        payload = request.get('payload')
        updates_dict = transforms.json_to_dict(
            transforms.loads(payload),
            self.get_schema(course, key).get_json_schema_dict())

        lesson.title = updates_dict['title']
        lesson.unit_id = updates_dict['unit_id']
        lesson.scored = (updates_dict['scored'] == 'scored')
        lesson.objectives = updates_dict['objectives']
        lesson.video = updates_dict['video']
        lesson.notes = updates_dict['notes']
        lesson.auto_index = updates_dict['auto_index']
        lesson.activity_title = updates_dict['activity_title']
        lesson.activity_listed = updates_dict['activity_listed']
        lesson.manual_progress = updates_dict['manual_progress']
        lesson.now_available = not updates_dict['is_draft']

        activity = updates_dict.get('activity', '').strip()
        errors = []
        if activity:
            if lesson.has_activity:
                course.set_activity_content(lesson, activity, errors=errors)
            else:
                errors.append('Old-style activities are not supported.')
        else:
            lesson.has_activity = False
            fs = self.app_context.fs
            path = fs.impl.physical_to_logical(course.get_activity_filename(
                lesson.unit_id, lesson.lesson_id))
            if fs.isfile(path):
                fs.delete(path)

        if not errors:
            common_utils.run_hooks(self.PRE_SAVE_HOOKS, lesson, updates_dict)
            assert course.update_lesson(lesson)
            course.save()
            common_utils.run_hooks(self.POST_SAVE_HOOKS, lesson)
            transforms.send_json_response(self, 200, 'Saved.')
        else:
            transforms.send_json_response(self, 412, '\n'.join(errors))

    def delete(self):
        """Handles REST DELETE verb with JSON payload."""
        key = self.request.get('key')

        if not self.assert_xsrf_token_or_fail(
                self.request, 'delete-lesson', {'key': key}):
            return

        if not CourseOutlineRights.can_delete(self):
            transforms.send_json_response(
                self, 401, 'Access denied.', {'key': key})
            return

        course = courses.Course(self)
        lesson = course.find_lesson_by_id(None, key)
        if not lesson:
            transforms.send_json_response(
                self, 404, 'Object not found.', {'key': key})
            return

        assert course.delete_lesson(lesson)
        course.save()

        transforms.send_json_response(self, 200, 'Deleted.')
