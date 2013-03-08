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
import os
import sys
import urllib
from controllers import sites
from controllers.utils import ApplicationHandler
from controllers.utils import BaseRESTHandler
from controllers.utils import XsrfTokenManager
from models import courses
from models import roles
from models import transforms
from models import vfs
from modules.oeditor import oeditor
from tools import verify
import filer


# The editor has severe limitations for editing nested lists of objects. First,
# it does not allow one to move a lesson from one unit to another. We need a way
# of doing that. Second, JSON schema specification does not seem to support a
# type-safe array, which has objects of different types. We also want that
# badly :). All in all - using generic schema-based object editor for editing
# nested arrayable polymorphic attributes is a pain...


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

    def get_import_course(self):
        """Shows setup form for course import."""

        template_values = {}
        template_values['page_title'] = self.format_title('Import Course')

        annotations = ImportCourseRESTHandler.SCHEMA_ANNOTATIONS_DICT
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

    def get_edit_unit_lesson(self):
        """Shows editor for the list of unit and lesson titles."""

        key = self.request.get('key')

        exit_url = self.canonicalize_url('/dashboard')
        rest_url = self.canonicalize_url(UnitLessonTitleRESTHandler.URI)
        form_html = oeditor.ObjectEditor.get_html_for(
            self,
            UnitLessonTitleRESTHandler.SCHEMA_JSON,
            UnitLessonTitleRESTHandler.SCHEMA_ANNOTATIONS_DICT,
            key, rest_url, exit_url,
            required_modules=UnitLessonTitleRESTHandler.REQUIRED_MODULES)

        template_values = {}
        template_values['page_title'] = self.format_title('Edit Course Outline')
        template_values['main_content'] = form_html
        self.render_page(template_values)

    def post_add_unit(self):
        """Adds new unit to a course."""
        self.redirect(self.get_action_url(
            'edit_unit',
            key=courses.Course(self).add_unit().id))

    def post_add_link(self):
        """Adds new link to a course."""
        self.redirect(self.get_action_url(
            'edit_link',
            key=courses.Course(self).add_link().id))

    def post_add_assessment(self):
        """Adds new assessment to a course."""
        self.redirect(self.get_action_url(
            'edit_assessment',
            key=courses.Course(self).add_assessment().id))

    def _render_edit_form_for(self, rest_handler_cls, title):
        """Renders an editor form for a given REST handler class."""
        key = self.request.get('key')

        exit_url = self.canonicalize_url('/dashboard')
        rest_url = self.canonicalize_url(rest_handler_cls.URI)
        delete_url = '%s?%s' % (
            self.canonicalize_url(rest_handler_cls.URI),
            urllib.urlencode({
                'key': key,
                'xsrf_token': cgi.escape(self.create_xsrf_token('delete-unit'))
                }))

        form_html = oeditor.ObjectEditor.get_html_for(
            self,
            rest_handler_cls.SCHEMA_JSON,
            rest_handler_cls.SCHEMA_ANNOTATIONS_DICT,
            key, rest_url, exit_url,
            delete_url=delete_url, delete_method='delete',
            read_only=not filer.is_editable_fs(self.app_context),
            required_modules=rest_handler_cls.REQUIRED_MODULES)

        template_values = {}
        template_values['page_title'] = self.format_title(
            'Edit %s' % title)
        template_values['main_content'] = form_html
        self.render_page(template_values)

    def get_edit_unit(self):
        """Shows unit editor."""
        self._render_edit_form_for(UnitRESTHandler, 'Unit')

    def get_edit_link(self):
        """Shows link editor."""
        self._render_edit_form_for(LinkRESTHandler, 'Link')

    def get_edit_assessment(self):
        """Shows assessment editor."""
        self._render_edit_form_for(AssessmentRESTHandler, 'Assessment')


class CommonUnitRESTHandler(BaseRESTHandler):
    """A common super class for all unit REST handlers."""

    def unit_to_dict(self, unused_unit):
        """Converts a unit to a dictionary representation."""
        raise Exception('Not implemented')

    def apply_updates(
        self, unused_unit, unused_updated_unit_dict, unused_errors):
        """Applies changes to a unit; modifies unit input argument."""
        raise Exception('Not implemented')

    def pre_delete(self, unused_unit):
        """Override to perform actions required before deletion."""
        pass

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

        transforms.send_json_response(
            self, 200, 'Success.',
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
        updated_unit_dict = transforms.json_to_dict(
            transforms.loads(payload), self.SCHEMA_DICT)

        errors = []
        self.apply_updates(unit, updated_unit_dict, errors)
        if not errors:
            assert courses.Course(self).put_unit(unit)
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

        unit = courses.Course(self).find_unit_by_id(key)
        if not unit:
            transforms.send_json_response(
                self, 404, 'Object not found.', {'key': key})
            return

        self.pre_delete(unit)
        assert courses.Course(self).delete_unit(unit)
        transforms.send_json_response(self, 200, 'Deleted.')


class UnitRESTHandler(CommonUnitRESTHandler):
    """Provides REST API to unit."""

    URI = '/rest/course/unit'

    SCHEMA_JSON = """
    {
        "id": "Unit Entity",
        "type": "object",
        "description": "Unit",
        "properties": {
            "key" : {"type": "string"},
            "type": {"type": "string"},
            "title": {"optional": true, "type": "string"},
            "is_draft": {"type": "boolean"}
            }
    }
    """

    SCHEMA_DICT = transforms.loads(SCHEMA_JSON)

    SCHEMA_ANNOTATIONS_DICT = [
        (['title'], 'Unit'),
        (['properties', 'key', '_inputex'], {
            'label': 'ID', '_type': 'uneditable'}),
        (['properties', 'type', '_inputex'], {
            'label': 'Type', '_type': 'uneditable'}),
        (['properties', 'title', '_inputex'], {'label': 'Title'}),
        oeditor.create_bool_select_annotation(
            ['properties', 'is_draft'], 'Status', 'Draft', 'Published')]

    REQUIRED_MODULES = [
        'inputex-string', 'inputex-select', 'inputex-uneditable']

    def unit_to_dict(self, unit):
        assert unit.type == 'U'
        return {
            'key': unit.id,
            'type': verify.UNIT_TYPE_NAMES[unit.type],
            'title': unit.title,
            'is_draft': not unit.now_available}

    def apply_updates(self, unit, updated_unit_dict, unused_errors):
        unit.title = updated_unit_dict.get('title')
        unit.now_available = not updated_unit_dict.get('is_draft')


class LinkRESTHandler(CommonUnitRESTHandler):
    """Provides REST API to link."""

    URI = '/rest/course/link'

    SCHEMA_JSON = """
    {
        "id": "Link Entity",
        "type": "object",
        "description": "Link",
        "properties": {
            "key" : {"type": "string"},
            "type": {"type": "string"},
            "title": {"optional": true, "type": "string"},
            "url": {"optional": true, "type": "string"},
            "is_draft": {"type": "boolean"}
            }
    }
    """

    SCHEMA_DICT = transforms.loads(SCHEMA_JSON)

    SCHEMA_ANNOTATIONS_DICT = [
        (['title'], 'Link'),
        (['properties', 'key', '_inputex'], {
            'label': 'ID', '_type': 'uneditable'}),
        (['properties', 'type', '_inputex'], {
            'label': 'Type', '_type': 'uneditable'}),
        (['properties', 'title', '_inputex'], {'label': 'Title'}),
        (['properties', 'url', '_inputex'], {'label': 'URL'}),
        oeditor.create_bool_select_annotation(
            ['properties', 'is_draft'], 'Status', 'Draft', 'Published')]

    REQUIRED_MODULES = [
        'inputex-string', 'inputex-select', 'inputex-uneditable']

    def unit_to_dict(self, unit):
        assert unit.type == 'O'
        return {
            'key': unit.id,
            'type': verify.UNIT_TYPE_NAMES[unit.type],
            'title': unit.title,
            'url': unit.unit_id,
            'is_draft': not unit.now_available}

    def apply_updates(self, unit, updated_unit_dict, unused_errors):
        unit.title = updated_unit_dict.get('title')
        unit.unit_id = updated_unit_dict.get('url')
        unit.now_available = not updated_unit_dict.get('is_draft')


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
        'inputex-string', 'inputex-select', 'inputex-uneditable']

    @classmethod
    def SCHEMA_ANNOTATIONS_DICT(cls):  # pylint: disable-msg=g-bad-name
        """Schema annotations are dynamic and include a list of courses."""

        # Make a list of courses user has the rights to.
        course_list = []
        for acourse in sites.get_all_courses():
            if not roles.Roles.is_course_admin(acourse):
                continue
            if acourse == sites.get_course_for_current_request():
                continue
            course_list.append({
                'value': acourse.raw,
                'label': acourse.get_title()})

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

        transforms.send_json_response(
            self, 200, 'Success.',
            payload_dict={'course': None},
            xsrf_token=XsrfTokenManager.create_xsrf_token(
                'unit-lesson-reorder'))

    def put(self):
        """Handles REST PUT verb with JSON payload."""
        if not CourseOutlineRights.can_edit(self):
            transforms.send_json_response(self, 401, 'Access denied.', {})
            return

        request = transforms.loads(self.request.get('request'))
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

        errors = []
        try:
            courses.ImportExport.import_course(
                source, sites.get_course_for_current_request(), errors)
        except Exception as e:  # pylint: disable-msg=broad-except
            logging.exception(e)
            errors.append('Import failed: %s' % e)

        if errors:
            transforms.send_json_response(self, 412, '\n'.join(errors))
            return

        transforms.send_json_response(self, 200, 'Imported.')


class AssessmentRESTHandler(CommonUnitRESTHandler):
    """Provides REST API to assessment."""

    URI = '/rest/course/assessment'

    SCHEMA_JSON = """
    {
        "id": "Assessment Entity",
        "type": "object",
        "description": "Assessment",
        "properties": {
            "key" : {"type": "string"},
            "type": {"type": "string"},
            "title": {"optional": true, "type": "string"},
            "content": {"optional": true, "type": "text"},
            "is_draft": {"type": "boolean"}
            }
    }
    """

    SCHEMA_DICT = transforms.loads(SCHEMA_JSON)

    SCHEMA_ANNOTATIONS_DICT = [
        (['title'], 'Assessment'),
        (['properties', 'key', '_inputex'], {
            'label': 'ID', '_type': 'uneditable'}),
        (['properties', 'type', '_inputex'], {
            'label': 'Type', '_type': 'uneditable'}),
        (['properties', 'title', '_inputex'], {'label': 'Title'}),
        (['properties', 'content', '_inputex'], {'label': 'Content'}),
        oeditor.create_bool_select_annotation(
            ['properties', 'is_draft'], 'Status', 'Draft', 'Published')]

    REQUIRED_MODULES = [
        'inputex-select', 'inputex-string', 'inputex-textarea',
        'inputex-uneditable']

    def _get_assessment_path(self, unit):
        return self.app_context.fs.impl.physical_to_logical(
            os.path.join(
                'assets/js',
                courses.Course.get_assessment_filename(unit)))

    def unit_to_dict(self, unit):
        """Assemble a dict with the unit data fields."""
        assert unit.type == 'A'

        path = self._get_assessment_path(unit)
        fs = self.app_context.fs
        if fs.isfile(path):
            content = fs.get(path)
        else:
            content = ''

        return {
            'key': unit.id,
            'type': verify.UNIT_TYPE_NAMES[unit.type],
            'title': unit.title,
            'content': content,
            'is_draft': not unit.now_available}

    def apply_updates(self, unit, updated_unit_dict, errors):
        """Store the updated assignment."""
        root_name = 'assessment'
        unit.title = updated_unit_dict.get('title')
        unit.now_available = not updated_unit_dict.get('is_draft')

        path = self._get_assessment_path(unit)

        try:
            (content, noverify_text) = verify.convert_javascript_to_python(
                updated_unit_dict.get('content'), root_name)
            assessment = verify.evaluate_python_expression_from_text(
                content, root_name, verify.Assessment().scope, noverify_text)
        except Exception:  # pylint: disable-msg=broad-except
            errors.append('Unable to parse %s:\n%s' % (
                root_name,
                str(sys.exc_info()[1])))
            return

        verifier = verify.Verifier()
        try:
            verifier.verify_assessment_instance(assessment, path)
        except verify.SchemaException:
            errors.append('Error validating %s\n' % root_name)
            return

        fs = self.app_context.fs
        fs.put(
            path, vfs.string_to_stream(content),
            is_draft=not unit.now_available)

    def pre_delete(self, unit):
        path = self._get_assessment_path(unit)
        self.app_context.fs.delete(path)


class UnitLessonTitleRESTHandler(BaseRESTHandler):
    """Provides REST API to unit and lesson titles."""

    URI = '/rest/course/outline'

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

    SCHEMA_ANNOTATIONS_DICT = [
        (['title'], 'Course Outline'),
        (['properties', 'outline', '_inputex'], {
            'sortable': 'true',
            'label': ''}),
        ([
            'properties', 'outline', 'items',
            'properties', 'title', '_inputex'], {
                '_type': 'uneditable',
                'label': 'Unit'}),
        (['properties', 'outline', 'items', 'properties', 'id', '_inputex'], {
            '_type': 'hidden'}),
        (['properties', 'outline', 'items', 'properties', 'lessons',
          '_inputex'], {
              'sortable': 'true',
              'label': '',
              'listAddLabel': 'Add  a new lesson',
              'listRemoveLabel': 'Delete'}),
        (['properties', 'outline', 'items', 'properties', 'lessons', 'items',
          'properties', 'title', '_inputex'], {
              '_type': 'uneditable',
              'label': ''}),
        (['properties', 'outline', 'items', 'properties', 'lessons', 'items',
          'properties', 'id', '_inputex'], {
              '_type': 'hidden'})
        ]

    REQUIRED_MODULES = [
        'inputex-hidden', 'inputex-list', 'inputex-string',
        'inputex-uneditable']

    def get(self):
        """Handles REST GET verb and returns an object as JSON payload."""

        if not CourseOutlineRights.can_view(self):
            transforms.send_json_response(self, 401, 'Access denied.', {})
            return

        course = courses.Course(self)
        outline_data = []
        unit_index = 1
        for unit in course.get_units():
            lesson_data = []
            for lesson in course.get_lessons(unit.id):
                lesson_data.append({
                    'title': lesson.title,
                    'id': lesson.id})
            outline_data.append({
                'title': '%s - %s' % (unit_index, unit.title),
                'id': unit.id,
                'lessons': lesson_data})
            unit_index += 1

        transforms.send_json_response(
            self, 200, 'Success.',
            payload_dict={'outline': outline_data},
            xsrf_token=XsrfTokenManager.create_xsrf_token(
                'unit-lesson-reorder'))

    def put(self):
        """Handles REST PUT verb with JSON payload."""
        request = transforms.loads(self.request.get('request'))

        if not self.assert_xsrf_token_or_fail(
                request, 'unit-lesson-reorder', {'key': None}):
            return

        if not CourseOutlineRights.can_edit(self):
            transforms.send_json_response(self, 401, 'Access denied.', {})
            return

        payload = request.get('payload')
        payload_dict = transforms.json_to_dict(
            transforms.loads(payload), self.SCHEMA_DICT)
        courses.Course(self).reorder_units(payload_dict['outline'])

        transforms.send_json_response(self, 200, 'Saved.')
