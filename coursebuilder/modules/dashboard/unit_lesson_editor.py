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
from common import tags
from controllers import sites
from controllers.utils import ApplicationHandler
from controllers.utils import BaseRESTHandler
from controllers.utils import XsrfTokenManager
from models import courses
from models import roles
from models import transforms
from modules.oeditor import oeditor
from tools import verify
import filer
import messages


DRAFT_TEXT = 'Private'
PUBLISHED_TEXT = 'Public'


# The editor has severe limitations for editing nested lists of objects. First,
# it does not allow one to move a lesson from one unit to another. We need a way
# of doing that. Second, JSON schema specification does not seem to support a
# type-safe array, which has objects of different types. We also want that
# badly :). All in all - using generic schema-based object editor for editing
# nested arrayable polymorphic attributes is a pain...


STATUS_ANNOTATION = oeditor.create_bool_select_annotation(
    ['properties', 'is_draft'], 'Status', DRAFT_TEXT,
    PUBLISHED_TEXT, class_name='split-from-main-group')


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
        template_values['page_description'] = messages.IMPORT_COURSE_DESCRIPTION
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
        template_values[
            'page_description'] = messages.COURSE_OUTLINE_EDITOR_DESCRIPTION
        template_values['main_content'] = form_html
        self.render_page(template_values)

    def post_add_lesson(self):
        """Adds new lesson to a first unit of the course."""
        course = courses.Course(self)
        first_unit = None
        for unit in course.get_units():
            if unit.type == verify.UNIT_TYPE_UNIT:
                first_unit = unit
                break
        if first_unit:
            lesson = course.add_lesson(first_unit)
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

    def _render_edit_form_for(
        self, rest_handler_cls, title, annotations_dict=None,
        delete_xsrf_token='delete-unit', page_description=None):
        """Renders an editor form for a given REST handler class."""
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

        form_html = oeditor.ObjectEditor.get_html_for(
            self,
            rest_handler_cls.SCHEMA_JSON,
            annotations_dict,
            key, rest_url, exit_url,
            extra_args=extra_args,
            delete_url=delete_url, delete_method='delete',
            read_only=not filer.is_editable_fs(self.app_context),
            required_modules=rest_handler_cls.REQUIRED_MODULES)

        template_values = {}
        template_values['page_title'] = self.format_title('Edit %s' % title)
        if page_description:
            template_values['page_description'] = page_description
        template_values['main_content'] = form_html
        self.render_page(template_values)

    def get_edit_unit(self):
        """Shows unit editor."""
        self._render_edit_form_for(
            UnitRESTHandler, 'Unit',
            page_description=messages.UNIT_EDITOR_DESCRIPTION)

    def get_edit_link(self):
        """Shows link editor."""
        self._render_edit_form_for(
            LinkRESTHandler, 'Link',
            page_description=messages.LINK_EDITOR_DESCRIPTION)

    def get_edit_assessment(self):
        """Shows assessment editor."""
        self._render_edit_form_for(
            AssessmentRESTHandler, 'Assessment',
            page_description=messages.ASSESSMENT_EDITOR_DESCRIPTION)

    def get_edit_lesson(self):
        """Shows the lesson/activity editor."""
        self._render_edit_form_for(
            LessonRESTHandler, 'Lessons and Activities',
            annotations_dict=LessonRESTHandler.get_schema_annotations_dict(
                courses.Course(self).get_units()),
            delete_xsrf_token='delete-lesson')


class CommonUnitRESTHandler(BaseRESTHandler):
    """A common super class for all unit REST handlers."""

    def unit_to_dict(self, unused_unit):
        """Converts a unit to a dictionary representation."""
        raise Exception('Not implemented')

    def apply_updates(
        self, unused_unit, unused_updated_unit_dict, unused_errors):
        """Applies changes to a unit; modifies unit input argument."""
        raise Exception('Not implemented')

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
        updated_unit_dict = transforms.json_to_dict(
            transforms.loads(payload), self.SCHEMA_DICT)

        errors = []
        self.apply_updates(unit, updated_unit_dict, errors)
        if not errors:
            course = courses.Course(self)
            assert course.update_unit(unit)
            course.save()
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
        STATUS_ANNOTATION]

    REQUIRED_MODULES = [
        'inputex-string', 'inputex-select', 'inputex-uneditable']

    def unit_to_dict(self, unit):
        assert unit.type == 'U'
        return {
            'key': unit.unit_id,
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
        (['properties', 'url', '_inputex'], {
            'label': 'URL',
            'description': messages.LINK_EDITOR_URL_DESCRIPTION}),
        STATUS_ANNOTATION]

    REQUIRED_MODULES = [
        'inputex-string', 'inputex-select', 'inputex-uneditable']

    def unit_to_dict(self, unit):
        assert unit.type == 'O'
        return {
            'key': unit.unit_id,
            'type': verify.UNIT_TYPE_NAMES[unit.type],
            'title': unit.title,
            'url': unit.href,
            'is_draft': not unit.now_available}

    def apply_updates(self, unit, updated_unit_dict, unused_errors):
        unit.title = updated_unit_dict.get('title')
        unit.href = updated_unit_dict.get('url')
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
    def _get_course_list(cls):
        # Make a list of courses user has the rights to.
        course_list = []
        for acourse in sites.get_all_courses():
            if not roles.Roles.is_course_admin(acourse):
                continue
            if acourse == sites.get_course_for_current_request():
                continue
            course_list.append({
                'value': acourse.raw,
                'label': cgi.escape(acourse.get_title())})
        return course_list

    @classmethod
    def SCHEMA_ANNOTATIONS_DICT(cls):  # pylint: disable-msg=g-bad-name
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
        except Exception as e:  # pylint: disable-msg=broad-except
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

    SCHEMA_JSON = """
    {
        "id": "Assessment Entity",
        "type": "object",
        "description": "Assessment",
        "properties": {
            "key" : {"type": "string"},
            "type": {"type": "string"},
            "title": {"optional": true, "type": "string"},
            "weight": {"optional": true, "type": "string"},
            "content": {"optional": true, "type": "text"},
            "workflow_yaml": {"optional": true, "type": "text"},
            "review_form": {"optional": true, "type": "text"},
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
        (['properties', 'weight', '_inputex'], {'label': 'Weight'}),
        (['properties', 'content', '_inputex'], {
            'label': 'Assessment Content',
            'description': str(messages.ASSESSMENT_CONTENT_DESCRIPTION)}),
        (['properties', 'workflow_yaml', '_inputex'], {
            'label': 'Assessment Details',
            'description': str(messages.ASSESSMENT_DETAILS_DESCRIPTION)}),
        (['properties', 'review_form', '_inputex'], {
            'label': 'Reviewer Feedback Form',
            'description': str(messages.REVIEWER_FEEDBACK_FORM_DESCRIPTION)}),
        STATUS_ANNOTATION]

    REQUIRED_MODULES = [
        'inputex-select', 'inputex-string', 'inputex-textarea',
        'inputex-uneditable']

    def _get_assessment_path(self, unit):
        return self.app_context.fs.impl.physical_to_logical(
            courses.Course(self).get_assessment_filename(unit.unit_id))

    def _get_review_form_path(self, unit):
        return self.app_context.fs.impl.physical_to_logical(
            courses.Course(self).get_review_form_filename(unit.unit_id))

    def unit_to_dict(self, unit):
        """Assemble a dict with the unit data fields."""
        assert unit.type == 'A'

        path = self._get_assessment_path(unit)
        fs = self.app_context.fs
        if fs.isfile(path):
            content = fs.get(path)
        else:
            content = ''

        review_form_path = self._get_review_form_path(unit)
        if review_form_path and fs.isfile(review_form_path):
            review_form = fs.get(review_form_path)
        else:
            review_form = ''

        return {
            'key': unit.unit_id,
            'type': verify.UNIT_TYPE_NAMES[unit.type],
            'title': unit.title,
            'weight': str(unit.weight if hasattr(unit, 'weight') else 0),
            'content': content,
            'workflow_yaml': unit.workflow_yaml,
            'review_form': review_form,
            'is_draft': not unit.now_available,
        }

    def apply_updates(self, unit, updated_unit_dict, errors):
        """Store the updated assessment."""
        unit.title = updated_unit_dict.get('title')

        try:
            unit.weight = int(updated_unit_dict.get('weight'))
            if unit.weight < 0:
                errors.append('The weight must be a non-negative integer.')
        except ValueError:
            errors.append('The weight must be an integer.')

        unit.now_available = not updated_unit_dict.get('is_draft')
        course = courses.Course(self)
        course.set_assessment_content(
            unit, updated_unit_dict.get('content'), errors=errors)

        unit.workflow_yaml = updated_unit_dict.get('workflow_yaml')
        unit.workflow.validate(errors=errors)

        # Only save the review form if the assessment needs human grading.
        if not errors:
            if course.needs_human_grader(unit):
                course.set_review_form(
                    unit, updated_unit_dict.get('review_form'), errors=errors)
            elif updated_unit_dict.get('review_form'):
                errors.append(
                    'Review forms for auto-graded assessments should be empty.')


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
                'label': ''}),
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
        for unit in course.get_units():
            lesson_data = []
            for lesson in course.get_lessons(unit.unit_id):
                lesson_data.append({
                    'title': lesson.title,
                    'id': lesson.lesson_id})
            unit_title = unit.title
            if verify.UNIT_TYPE_UNIT == unit.type:
                unit_title = 'Unit %s - %s' % (unit.index, unit.title)
            outline_data.append({
                'title': unit_title,
                'id': unit.unit_id,
                'lessons': lesson_data})

        transforms.send_json_response(
            self, 200, None,
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
        course = courses.Course(self)
        course.reorder_units(payload_dict['outline'])
        course.save()

        transforms.send_json_response(self, 200, 'Saved.')


class LessonRESTHandler(BaseRESTHandler):
    """Provides REST API to handle lessons and activities."""

    URI = '/rest/course/lesson'

    # Note GcbRte relies on the structure of this schema. Do not change without
    # checking the dependency.
    SCHEMA_JSON = """
    {
        "id": "Lesson Entity",
        "type": "object",
        "description": "Lesson",
        "properties": {
            "key" : {"type": "string"},
            "title" : {"type": "string"},
            "unit_id": {"type": "string"},
            "video" : {"type": "string", "optional": true},
            "objectives" : {
                "type": "string", "format": "html", "optional": true},
            "notes" : {"type": "string", "optional": true},
            "activity_title" : {"type": "string", "optional": true},
            "activity_listed" : {"type": "boolean", "optional": true},
            "activity": {"type": "string", "format": "text", "optional": true},
            "is_draft": {"type": "boolean"}
            }
    }
    """

    SCHEMA_DICT = transforms.loads(SCHEMA_JSON)

    REQUIRED_MODULES = [
        'inputex-string', 'gcb-rte', 'inputex-select', 'inputex-textarea',
        'inputex-uneditable', 'inputex-checkbox']

    @classmethod
    def get_schema_annotations_dict(cls, units):
        unit_list = []
        for unit in units:
            if unit.type == 'U':
                unit_list.append({
                    'label': cgi.escape(
                        'Unit %s - %s' % (unit.index, unit.title)),
                    'value': unit.unit_id})

        return [
            (['title'], 'Lesson'),
            (['properties', 'key', '_inputex'], {
                'label': 'ID', '_type': 'uneditable'}),
            (['properties', 'title', '_inputex'], {'label': 'Title'}),
            (['properties', 'unit_id', '_inputex'], {
                'label': 'Parent Unit', '_type': 'select',
                'choices': unit_list}),
            # TODO(sll): The internal 'objectives' property should also be
            # renamed.
            (['properties', 'objectives', '_inputex'], {
                'label': 'Lesson Body',
                'supportCustomTags': tags.CAN_USE_DYNAMIC_TAGS.value,
                'description': messages.LESSON_OBJECTIVES_DESCRIPTION}),
            (['properties', 'video', '_inputex'], {
                'label': 'Video ID',
                'description': messages.LESSON_VIDEO_ID_DESCRIPTION}),
            (['properties', 'notes', '_inputex'], {
                'label': 'Notes',
                'description': messages.LESSON_NOTES_DESCRIPTION}),
            (['properties', 'activity_title', '_inputex'], {
                'label': 'Activity Title',
                'description': messages.LESSON_ACTIVITY_TITLE_DESCRIPTION}),
            (['properties', 'activity_listed', '_inputex'], {
                'label': 'Activity Listed',
                'description': messages.LESSON_ACTIVITY_LISTED_DESCRIPTION}),
            (['properties', 'activity', '_inputex'], {
                'label': 'Activity',
                'description': str(messages.LESSON_ACTIVITY_DESCRIPTION)}),
            STATUS_ANNOTATION]

    def get(self):
        """Handles GET REST verb and returns lesson object as JSON payload."""

        if not CourseOutlineRights.can_view(self):
            transforms.send_json_response(self, 401, 'Access denied.', {})
            return

        key = self.request.get('key')
        course = courses.Course(self)
        lesson = course.find_lesson_by_id(None, key)
        assert lesson

        fs = self.app_context.fs
        path = fs.impl.physical_to_logical(course.get_activity_filename(
            lesson.unit_id, lesson.lesson_id))
        if lesson.has_activity and fs.isfile(path):
            activity = fs.get(path)
        else:
            activity = ''

        payload_dict = {
            'key': key,
            'title': lesson.title,
            'unit_id': lesson.unit_id,
            'objectives': lesson.objectives,
            'video': lesson.video,
            'notes': lesson.notes,
            'activity_title': lesson.activity_title,
            'activity_listed': lesson.activity_listed,
            'activity': activity,
            'is_draft': not lesson.now_available
            }

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
            transforms.loads(payload), self.SCHEMA_DICT)

        lesson.title = updates_dict['title']
        lesson.unit_id = updates_dict['unit_id']
        lesson.objectives = updates_dict['objectives']
        lesson.video = updates_dict['video']
        lesson.notes = updates_dict['notes']
        lesson.activity_title = updates_dict['activity_title']
        lesson.activity_listed = updates_dict['activity_listed']
        lesson.now_available = not updates_dict['is_draft']

        activity = updates_dict.get('activity', '').strip()
        errors = []
        if activity:
            lesson.has_activity = True
            course.set_activity_content(lesson, activity, errors=errors)
        else:
            lesson.has_activity = False
            fs = self.app_context.fs
            path = fs.impl.physical_to_logical(course.get_activity_filename(
                lesson.unit_id, lesson.lesson_id))
            if fs.isfile(path):
                fs.delete(path)

        if not errors:
            assert course.update_lesson(lesson)
            course.save()
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
