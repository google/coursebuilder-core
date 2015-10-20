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

from common import tags
from models import transforms
from models import models
from models import resources_display
from modules.dashboard import dto_editor
from modules.dashboard import utils as dashboard_utils


class QuestionGroupManagerAndEditor(dto_editor.BaseDatastoreAssetEditor):
    """An editor for editing and managing question_groups."""

    def qgmae_prepare_template(self, key):
        template_values = {}
        template_values['page_title'] = self.format_title('Edit Question Group')
        template_values['main_content'] = self.get_form(
            QuestionGroupRESTHandler, key,
            dashboard_utils.build_assets_url('edit_question_groups'))
        return template_values

    def get_add_question_group(self):
        self.render_page(
            self.qgmae_prepare_template(''), in_action='edit_question_groups')

    def get_edit_question_group(self):
        self.render_page(
            self.qgmae_prepare_template(self.request.get('key')),
            in_action='edit_question_groups')

    def post_add_to_question_group(self):
        try:
            question_id = long(self.request.get('question_id'))
            question_dto = models.QuestionDAO.load(question_id)
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
            group_dto = models.QuestionGroupDAO.load(group_id)
            if group_dto is None:
                raise ValueError()
        except ValueError:
            transforms.send_json_response(
                self, 500, 'Invalid question group id.',
                {'group-id': self.request.get('group_id')}
            )
            return

        weight = self.request.get('weight', '1')
        try:
            float(weight)
        except ValueError:
            transforms.send_json_response(
                self, 500, 'Invalid weight. Must be a numeric value.', {
                    'weight': weight})
            return

        group_dto.add_question(question_id, weight)
        models.QuestionGroupDAO.save(group_dto)

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

    def get_question_group_preview(self):
        template_values = {}
        template_values['gcb_course_base'] = self.get_base_href(self)
        template_values['question'] = tags.html_to_safe_dom(
            '<question-group qgid="{}">'.format(self.request.get('qgid')), self)
        self.response.write(self.get_template(
            'question_preview.html').render(template_values))


class QuestionGroupRESTHandler(dto_editor.BaseDatastoreRestHandler):
    """REST handler for editing question_groups."""

    URI = '/rest/question_group'

    EXTRA_CSS_FILES = ['question_group_editor.css']
    EXTRA_JS_FILES = ['question_group_editor.js']

    XSRF_TOKEN = 'question-group-edit'

    SCHEMA_VERSIONS = ['1.5']

    DAO = models.QuestionGroupDAO

    @classmethod
    def get_schema(cls):
        return resources_display.ResourceQuestionGroup.get_schema(
            course=None, key=None)

    def get_default_content(self):
        return {'version': self.SCHEMA_VERSIONS[0]}

    def sanitize_input_dict(self, json_dict):
        for item in json_dict['items']:
            if len(str(item['weight']).strip()) == 0:
                item['weight'] = '1'

    def validate(self, question_group_dict, key, schema_version, errors):
        """Validate the question group data sent from the form."""

        if not question_group_dict['description'].strip():
            errors.append('The question group must have a description.')

        descriptions = {question_group.description for question_group
                        in models.QuestionGroupDAO.get_all()
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
