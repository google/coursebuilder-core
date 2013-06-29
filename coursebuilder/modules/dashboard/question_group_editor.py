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

"""Classes supporting creation and editing of question_groups."""

__author__ = 'John Orr (jorr@google.com)'


from common import schema_fields
from controllers.utils import BaseRESTHandler
from controllers.utils import XsrfTokenManager
from models import transforms
from models.models import QuestionDAO
from models.models import QuestionGroupDAO
from models.models import QuestionGroupDTO
import question_editor
from unit_lesson_editor import CourseOutlineRights


class QuestionGroupManagerAndEditor(question_editor.BaseDatastoreAssetEditor):
    """An editor for editing and managing question_groups."""

    def get_template_values(self, key):
        template_values = {}
        template_values['page_title'] = self.format_title('Edit Question Group')
        template_values['main_content'] = self.get_form(
            QuestionGroupRESTHandler, key)

        return template_values

    def get_add_question_group(self):
        self.render_page(self.get_template_values(''))

    def get_edit_question_group(self):
        self.render_page(self.get_template_values(self.request.get('key')))


class QuestionGroupRESTHandler(BaseRESTHandler):
    """REST handler for editing question_groups."""

    URI = '/rest/question_group'

    REQUIRED_MODULES = [
        'gcb-rte', 'inputex-hidden', 'inputex-select', 'inputex-string',
        'inputex-list']
    EXTRA_JS_FILES = []

    XSRF_TOKEN = 'question-group-edit'

    SCHEMA_VERSION = '1.5'

    @classmethod
    def get_schema(cls):
        """Return the InputEx schema for the question group editor."""
        question_group = schema_fields.FieldRegistry(
            'Question Group', description='question_group')

        question_group.add_property(schema_fields.SchemaField(
            'version', '', 'string', optional=True, hidden=True))
        question_group.add_property(schema_fields.SchemaField(
            'description', 'Description', 'string', optional=True))
        question_group.add_property(schema_fields.SchemaField(
            'introduction', 'Introduction', 'html', optional=True))

        item_type = schema_fields.FieldRegistry(
            'Item',
            extra_schema_dict_values={'className': 'question-group-item'})
        item_type.add_property(schema_fields.SchemaField(
            'weight', 'Weight', 'string', optional=True,
            extra_schema_dict_values={'className': 'question-group-weight'}))

        question_select_data = [
            (q.id, q.description) for q in QuestionDAO.get_all()]

        item_type.add_property(schema_fields.SchemaField(
            'question', 'Question', 'string', optional=True,
            select_data=question_select_data,
            extra_schema_dict_values={'className': 'question-group-question'}))

        item_array = schema_fields.FieldArray(
            'items', '', item_type=item_type,
            extra_schema_dict_values={
                'className': 'question-group-items',
                'sortable': 'true',
                'listAddLabel': 'Add an item',
                'listRemoveLabel': 'Delete item'})

        question_group.add_property(item_array)

        return question_group

    def get(self):
        """Respond to the REST GET verb with the contents of the group."""
        key = self.request.get('key')

        if not CourseOutlineRights.can_view(self):
            transforms.send_json_response(
                self, 401, 'Access denied.', {'key': key})
            return

        if key:
            question_group = QuestionGroupDAO.load(key)
            version = question_group.dict.get('version')
            if self.SCHEMA_VERSION != version:
                transforms.send_json_response(
                    self, 403, 'Cannot edit a Version %s group.' % version,
                    {'key': key})
                return
            payload_dict = question_group.dict
        else:
            payload_dict = {
                'version': self.SCHEMA_VERSION,
                'items': [{'weight': ''}, {'weight': ''}, {'weight': ''}]}

        transforms.send_json_response(
            self, 200, 'Success',
            payload_dict=payload_dict,
            xsrf_token=XsrfTokenManager.create_xsrf_token(self.XSRF_TOKEN))

    def validate(self, question_group_dict, key):
        """Validate the question group data sent from the form."""
        errors = []

        assert question_group_dict['version'] == self.SCHEMA_VERSION

        if not question_group_dict['description'].strip():
            errors.append('The question group must have a description.')

        descriptions = {question_group.description for question_group
                        in QuestionGroupDAO.get_all()
                        if not key or question_group.id != long(key)}
        if question_group_dict['description'] in descriptions:
            errors.append('The description must be different '
                          'from existing question groups.')

        if not question_group_dict['items']:
            errors.append(
                'The question group must contain at least one question.')

        items = question_group_dict['items']
        for index in range(0, len(items)):
            item = items[index]
            try:
                float(item['weight'])
            except ValueError:
                errors.append(
                    'Item %s must have a numeric weight.' % (index + 1))

        return errors

    def put(self):
        """Store a question group in the datastore in response to a PUT."""
        request = transforms.loads(self.request.get('request'))
        key = request.get('key')

        if not self.assert_xsrf_token_or_fail(
                request, self.XSRF_TOKEN, {'key': key}):
            return

        if not CourseOutlineRights.can_edit(self):
            transforms.send_json_response(
                self, 401, 'Access denied.', {'key': key})
            return

        payload = request.get('payload')
        question_group_dict = transforms.json_to_dict(
            transforms.loads(payload),
            self.get_schema().get_json_schema_dict())

        validation_errors = self.validate(question_group_dict, key)
        if validation_errors:
            self.validation_error('\n'.join(validation_errors), key=key)
            return

        assert self.SCHEMA_VERSION == question_group_dict.get('version')

        if key:
            question_group = QuestionGroupDTO(key, question_group_dict)
        else:
            question_group = QuestionGroupDTO(None, question_group_dict)

        key_after_save = QuestionGroupDAO.save(question_group)
        transforms.send_json_response(
            self, 200, 'Saved.', payload_dict={'key': key_after_save})

    def delete(self):
        """Delete the question_group in response to REST request."""
        key = self.request.get('key')

        if not self.assert_xsrf_token_or_fail(
                self.request, self.XSRF_TOKEN, {'key': key}):
            return

        if not CourseOutlineRights.can_delete(self):
            transforms.send_json_response(
                self, 401, 'Access denied.', {'key': key})
            return

        question_group = QuestionGroupDAO.load(key)
        if not question_group:
            transforms.send_json_response(
                self, 404, 'Question Group not found.', {'key': key})
            return
        QuestionGroupDAO.delete(question_group)
        transforms.send_json_response(self, 200, 'Deleted.')

