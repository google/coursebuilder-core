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

import json
from controllers.utils import ApplicationHandler
from controllers.utils import BaseRESTHandler
from controllers.utils import XsrfTokenManager
from models import courses
from models import roles
from models import transforms
from modules.oeditor import oeditor


UNIT_LESSON_REST_HANDLER_URI = '/rest/unit_lesson/title'


# The editor has severe limitations for editing nested lists of objects. First,
# it does not allow one to move a lesson from one unit to another. We need a way
# of doing that. Second, JSON schema specification does not seem to support a
# type-safe array, which has objects of different types. We also want that
# badly :). All in all - using generic schema-based object editor for editing
# nested arrayable polymorphic attributes is a pain...

EDIT_UNIT_LESSON_SCHEMA_JSON = """
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

EDIT_UNIT_LESSON_SCHEMA_DICT = json.loads(EDIT_UNIT_LESSON_SCHEMA_JSON)


EDIT_UNIT_LESSON_SCHEMA_ANNOTATIONS_DICT = [
    (['title'], 'Course Outline'),
    (['properties', 'outline', '_inputex'], {
        'sortable': 'true',
        'label': ''}),
    (['properties', 'outline', 'items', 'properties', 'title', '_inputex'], {
        '_type': 'uneditable',
        'name': 'name',
        'label': 'Unit'}),
    (['properties', 'outline', 'items', 'properties', 'id', '_inputex'], {
        '_type': 'hidden',
        'name': 'id'}),
    (['properties', 'outline', 'items', 'properties', 'lessons',
      '_inputex'], {
          'sortable': 'true',
          'label': 'Lessons',
          'listAddLabel': 'Add  a new lesson',
          'listRemoveLabel': 'Delete'}),
    (['properties', 'outline', 'items', 'properties', 'lessons', 'items',
      'properties', 'title', '_inputex'], {
          '_type': 'uneditable',
          'name': 'name',
          'label': ''}),
    (['properties', 'outline', 'items', 'properties', 'lessons', 'items',
      'properties', 'id', '_inputex'], {
          '_type': 'hidden',
          'name': 'id'})
    ]


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

    def get_edit_unit_lesson(self):
        """Shows editor for the list of unit and lesson titles."""

        key = self.request.get('key')

        exit_url = self.canonicalize_url('/dashboard')
        rest_url = self.canonicalize_url(UNIT_LESSON_REST_HANDLER_URI)
        form_html = oeditor.ObjectEditor.get_html_for(
            self,
            EDIT_UNIT_LESSON_SCHEMA_JSON,
            EDIT_UNIT_LESSON_SCHEMA_ANNOTATIONS_DICT,
            key, rest_url, exit_url)

        template_values = {}
        template_values['page_title'] = self.format_title('Edit Course Outline')
        template_values['main_content'] = form_html
        self.render_page(template_values)


class UnitLessonTitleRESTHandler(BaseRESTHandler):
    """Provides REST API to unit and lesson titles."""

    def get(self):
        """Handles REST GET verb and returns an object as JSON payload."""

        if not CourseOutlineRights.can_view(self):
            transforms.send_json_response(self, 401, 'Access denied.', {})
            return

        course = courses.Course(self)
        outline_data = []
        unit_index = 1
        for unit in course.get_units():
            # TODO(jorr): Need to handle other course objects than just units
            if unit.type == 'U':
                lesson_data = []
                for lesson in course.get_lessons(unit.unit_id):
                    lesson_data.append({
                        'name': lesson.title,
                        'id': lesson.id})
                outline_data.append({
                    'name': '%s - %s' % (unit_index, unit.title),
                    'id': unit.unit_id,
                    'lessons': lesson_data})
                unit_index += 1

        transforms.send_json_response(
            self, 200, 'Success.',
            payload_dict={'outline': outline_data},
            xsrf_token=XsrfTokenManager.create_xsrf_token(
                'unit-lesson-reorder'))

    def put(self):
        """Handles REST PUT verb with JSON payload."""

        if not CourseOutlineRights.can_edit(self):
            transforms.send_json_response(self, 401, 'Access denied.', {})
            return

        # TODO(jorr) Need to actually save the stuff we're sent.
        transforms.send_json_response(self, 405, 'Not yet implemented.', {})
