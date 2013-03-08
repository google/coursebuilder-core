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

from controllers.utils import ApplicationHandler
from controllers.utils import BaseRESTHandler
from controllers.utils import XsrfTokenManager
from models import courses
from models import transforms
from modules.oeditor import oeditor


UNIT_LESSON_REST_HANDLER_URI = '/rest/unit_lesson/title'

EDIT_UNIT_LESSON_SCHEMA_JSON = """
    {
        "type": "object",
        "description": "Course Outline",
        "properties": {
            "outline": {
                "type": "array",
                "description": "Course Outline",
                "items": {
                    "type": "object",
                    "description": "Unit",
                    "properties": {
                        "title": {"type": "string"},
                        "id": {"type": "string"},
                        "lessons": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "description": "Lesson",
                                "properties": {
                                    "title": {"type": "string"},
                                    "id": {"type": "string"}
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    """

EDIT_UNIT_LESSON_SCHEMA_ANNOTATIONS_DICT = [
    (['properties', 'outline', '_inputex'], {
        'sortable': 'true',
        'label': 'Units'}),
    (['properties', 'outline', 'items', 'properties', 'title', '_inputex'], {
        '_type': 'uneditable',
        'name': 'name',
        'label': ''}),
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
        template_values['main_content'] = form_html
        self.render_page(template_values)


class UnitLessonTitleRESTHandler(BaseRESTHandler):
    """Provides REST API to unit and lesson titles."""

    def get(self):
        """Handles REST GET verb and returns an object as JSON payload."""
        course = courses.Course(self)
        outline_data = []
        for unit in course.get_units():
            # TODO(jorr): Need to handle other course objects than just units
            if unit.type == 'U':
                lesson_data = []
                for lesson in course.get_lessons(unit.unit_id):
                    lesson_data.append({
                        'name': lesson.title,
                        'id': lesson.id})
                outline_data.append({
                    'name': unit.title,
                    'id': unit.unit_id,
                    'lessons': lesson_data})

        transforms.send_json_response(
            self, 200, 'Success.',
            payload_dict={'outline': outline_data},
            xsrf_token=XsrfTokenManager.create_xsrf_token(
                'unit-lesson-reorder'))

    def put(self):
        """Handles REST PUT verb with JSON payload."""

        # TODO(jorr) Need to actually save the stuff we're sent

        # Send reply.
        transforms.send_json_response(self, 200, 'Saved.')
