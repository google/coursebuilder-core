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
from models import transforms
from models.models import QuestionDAO
from models.models import QuestionGroupDAO
from modules.dashboard import dto_editor
from modules.dashboard import utils as dashboard_utils


class QuestionGroupManagerAndEditor(dto_editor.BaseDatastoreAssetEditor):
    """An editor for editing and managing question_groups."""

    def qgmae_prepare_template(self, key):
        template_values = {}
        template_values['page_title'] = self.format_title('Edit Question Group')
        template_values['main_content'] = self.get_form(
            QuestionGroupRESTHandler, key,
            dashboard_utils.build_assets_url('questions'))
        return template_values

    def get_add_question_group(self):
        self.render_page(self.qgmae_prepare_template(''), 'assets', 'questions')

    def get_edit_question_group(self):
        self.render_page(self.qgmae_prepare_template(self.request.get('key')),
                         'assets', 'questions')

    def post_add_to_question_group(self):
        try:
            question_id = long(self.request.get('question_id'))
            question_dto = QuestionDAO.load(question_id)
            if question_dto is None:
                raise ValueError()
        except ValueError:
            transforms.send_json_response(
                self, 500, 'Invalid question id.',
                {'question-id': self.request.get('question_id')}
            )
            return

        try:
            group_id = long(self.request.get('group_id'))
            group_dto = QuestionGroupDAO.load(group_id)
            if group_dto is None:
                raise ValueError()
        except ValueError:
            transforms.send_json_response(
                self, 500, 'Invalid question group id.',
                {'group-id': self.request.get('group_id')}
            )
            return

        weight = self.request.get('weight')
        try:
            float(weight)
        except ValueError:
            transforms.send_json_response(
                self, 500, 'Invalid weight. Must be a numeric value.', {
                    'weight': weight})
            return

        group_dto.add_question(question_id, weight)
        QuestionGroupDAO.save(group_dto)

        transforms.send_json_response(
            self,
            200,
            '%s added to %s.' % (
                question_dto.description, group_dto.description
            ),
            {
                'group-id': group_dto.id,
                'question-id': question_dto.id
            }
        )
        return


class QuestionGroupRESTHandler(dto_editor.BaseDatastoreRestHandler):
    """REST handler for editing question_groups."""

    URI = '/rest/question_group'

    REQUIRED_MODULES = [
        'gcb-rte', 'inputex-hidden', 'inputex-select', 'inputex-string',
        'inputex-list']
    EXTRA_JS_FILES = []

    XSRF_TOKEN = 'question-group-edit'

    SCHEMA_VERSIONS = ['1.5']

    DAO = QuestionGroupDAO

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
            'weight', 'Weight', 'string', optional=True, i18n=False,
            extra_schema_dict_values={'className': 'question-group-weight'}))

        question_select_data = [(q.id, q.description) for q in sorted(
            QuestionDAO.get_all(), key=lambda x: x.description)]

        item_type.add_property(schema_fields.SchemaField(
            'question', 'Question', 'string', optional=True, i18n=False,
            select_data=question_select_data,
            extra_schema_dict_values={'className': 'question-group-question'}))

        item_array = schema_fields.FieldArray(
            'items', '', item_type=item_type,
            extra_schema_dict_values={
                'className': 'question-group-items',
                'sortable': 'true',
                'listAddLabel': 'Add a question',
                'listRemoveLabel': 'Remove'})

        question_group.add_property(item_array)

        return question_group

    def get_default_content(self):
        return {'version': self.SCHEMA_VERSIONS[0]}

    def validate(self, question_group_dict, key, schema_version, errors):
        """Validate the question group data sent from the form."""

        if not question_group_dict['description'].strip():
            errors.append('The question group must have a description.')

        descriptions = {question_group.description for question_group
                        in QuestionGroupDAO.get_all()
                        if not key or question_group.id != long(key)}
        if question_group_dict['description'] in descriptions:
            errors.append('The description must be different '
                          'from existing question groups.')

        items = question_group_dict['items']
        for index in range(0, len(items)):
            item = items[index]
            try:
                float(item['weight'])
            except ValueError:
                errors.append(
                    'Item %s must have a numeric weight.' % (index + 1))
