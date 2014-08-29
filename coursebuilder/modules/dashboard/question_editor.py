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

"""Classes supporting creation and editing of questions."""

__author__ = 'John Orr (jorr@google.com)'

import copy

import messages

from common import schema_fields
from models import transforms
from models.models import QuestionDAO
from models.models import QuestionDTO
from models.models import SaQuestionConstants
from modules.dashboard import dto_editor
from modules.dashboard import utils as dashboard_utils


class QuestionManagerAndEditor(dto_editor.BaseDatastoreAssetEditor):
    """An editor for editing and managing questions."""

    def qmae_prepare_template(self, rest_handler, key=''):
        """Build the Jinja template for adding a question."""
        template_values = {}
        template_values['page_title'] = self.format_title('Edit Question')
        template_values['main_content'] = self.get_form(
            rest_handler, key,
            dashboard_utils.build_assets_url('questions'))

        return template_values

    def get_add_mc_question(self):
        self.render_page(self.qmae_prepare_template(McQuestionRESTHandler),
                         'assets', 'questions')

    def get_add_sa_question(self):
        self.render_page(self.qmae_prepare_template(SaQuestionRESTHandler),
                         'assets', 'questions')

    def get_edit_question(self):
        key = self.request.get('key')
        question = QuestionDAO.load(key)

        if not question:
            raise Exception('No question found')

        if question.type == QuestionDTO.MULTIPLE_CHOICE:
            self.render_page(
                self.qmae_prepare_template(McQuestionRESTHandler, key=key),
                'assets', 'questions')
        elif question.type == QuestionDTO.SHORT_ANSWER:
            self.render_page(
                self.qmae_prepare_template(SaQuestionRESTHandler, key=key),
                'assets', 'questions')
        else:
            raise Exception('Unknown question type: %s' % question.type)

    def get_clone_question(self):
        original_question = QuestionDAO.load(self.request.get('key'))
        cloned_question = QuestionDAO.clone(original_question)
        cloned_question.description += ' (clone)'
        QuestionDAO.save(cloned_question)
        self.redirect(self.get_action_url('assets', {'tab': 'questions'}))


class BaseQuestionRESTHandler(dto_editor.BaseDatastoreRestHandler):
    """Common methods for handling REST end points with questions."""

    def sanitize_input_dict(self, json_dict):
        json_dict['description'] = json_dict['description'].strip()

    def is_deletion_allowed(self, question):

        used_by = QuestionDAO.used_by(question.id)
        if used_by:
            group_names = sorted(['"%s"' % x.description for x in used_by])
            transforms.send_json_response(
                self, 403,
                ('Question in use by question groups:\n%s.\nPlease delete it '
                 'from those groups and try again.') % ',\n'.join(group_names),
                {'key': question.id})
            return False
        else:
            return True

    def validate_no_description_collision(self, description, key, errors):
        descriptions = {q.description for q in QuestionDAO.get_all()
                        if not key or q.id != long(key)}
        if description in descriptions:
            errors.append(
                'The description must be different from existing questions.')


class McQuestionRESTHandler(BaseQuestionRESTHandler):
    """REST handler for editing multiple choice questions."""

    URI = '/rest/question/mc'

    REQUIRED_MODULES = [
        'array-extras', 'gcb-rte', 'inputex-radio', 'inputex-select',
        'inputex-string', 'inputex-list', 'inputex-number', 'inputex-hidden']
    EXTRA_JS_FILES = ['mc_question_editor_lib.js', 'mc_question_editor.js']

    XSRF_TOKEN = 'mc-question-edit'

    SCHEMA_VERSIONS = ['1.5']

    DAO = QuestionDAO

    @classmethod
    def get_schema(cls):
        """Get the InputEx schema for the multiple choice question editor."""
        mc_question = schema_fields.FieldRegistry(
            'Multiple Choice Question',
            description='multiple choice question',
            extra_schema_dict_values={'className': 'mc-container'})

        mc_question.add_property(schema_fields.SchemaField(
            'version', '', 'string', optional=True, hidden=True))
        mc_question.add_property(schema_fields.SchemaField(
            'question', 'Question', 'html', optional=True,
            extra_schema_dict_values={'className': 'mc-question'}))
        mc_question.add_property(schema_fields.SchemaField(
            'description', 'Description', 'string', optional=True,
            extra_schema_dict_values={'className': 'mc-description'},
            description=messages.QUESTION_DESCRIPTION))
        mc_question.add_property(schema_fields.SchemaField(
            'multiple_selections', 'Selection', 'boolean',
            optional=True,
            select_data=[
                ('false', 'Allow only one selection'),
                ('true', 'Allow multiple selections')],
            extra_schema_dict_values={
                '_type': 'radio',
                'className': 'mc-selection'}))

        choice_type = schema_fields.FieldRegistry(
            'Choice',
            extra_schema_dict_values={'className': 'mc-choice'})
        choice_type.add_property(schema_fields.SchemaField(
            'score', 'Score', 'string', optional=True, i18n=False,
            extra_schema_dict_values={
                'className': 'mc-choice-score', 'value': '0'}))
        choice_type.add_property(schema_fields.SchemaField(
            'text', 'Text', 'html', optional=True,
            extra_schema_dict_values={'className': 'mc-choice-text'}))
        choice_type.add_property(schema_fields.SchemaField(
            'feedback', 'Feedback', 'html', optional=True,
            extra_schema_dict_values={'className': 'mc-choice-feedback'}))

        choices_array = schema_fields.FieldArray(
            'choices', '', item_type=choice_type,
            extra_schema_dict_values={
                'className': 'mc-choice-container',
                'listAddLabel': 'Add a choice',
                'listRemoveLabel': 'Delete choice'})

        mc_question.add_property(choices_array)

        return mc_question

    def pre_save_hook(self, question):
        question.type = QuestionDTO.MULTIPLE_CHOICE

    def transform_for_editor_hook(self, q_dict):
        p_dict = copy.deepcopy(q_dict)
        # InputEx does not correctly roundtrip booleans, so pass strings
        p_dict['multiple_selections'] = (
            'true' if q_dict.get('multiple_selections') else 'false')
        return p_dict

    def get_default_content(self):
        return {
            'version': self.SCHEMA_VERSIONS[0],
            'question': '',
            'description': '',
            'multiple_selections': 'false',
            'choices': [
                {'score': '1', 'text': '', 'feedback': ''},
                {'score': '0', 'text': '', 'feedback': ''},
                {'score': '0', 'text': '', 'feedback': ''},
                {'score': '0', 'text': '', 'feedback': ''}
            ]}

    def validate(self, question_dict, key, version, errors):
        # Currently only one version supported; version validity has already
        # been checked.
        self._validate15(question_dict, key, errors)

    def _validate15(self, question_dict, key, errors):
        if not question_dict['question'].strip():
            errors.append('The question must have a non-empty body.')

        if not question_dict['description']:
            errors.append('The description must be non-empty.')

        self.validate_no_description_collision(
            question_dict['description'], key, errors)

        if not question_dict['choices']:
            errors.append('The question must have at least one choice.')

        choices = question_dict['choices']
        for index in range(0, len(choices)):
            choice = choices[index]
            if not choice['text'].strip():
                errors.append('Choice %s has no response text.' % (index + 1))
            try:
                # Coefrce the score attrib into a python float
                choice['score'] = float(choice['score'])
            except ValueError:
                errors.append(
                    'Choice %s must have a numeric score.' % (index + 1))


class SaQuestionRESTHandler(BaseQuestionRESTHandler):
    """REST handler for editing short answer questions."""

    URI = '/rest/question/sa'

    REQUIRED_MODULES = [
        'gcb-rte', 'inputex-select', 'inputex-string', 'inputex-list',
        'inputex-hidden', 'inputex-integer']
    EXTRA_JS_FILES = []

    XSRF_TOKEN = 'sa-question-edit'

    GRADER_TYPES = [
        ('case_insensitive', 'Case insensitive string match'),
        ('regex', 'Regular expression'),
        ('numeric', 'Numeric')]

    SCHEMA_VERSIONS = ['1.5']

    DAO = QuestionDAO

    @classmethod
    def get_schema(cls):
        """Get the InputEx schema for the short answer question editor."""
        sa_question = schema_fields.FieldRegistry(
            'Short Answer Question',
            description='short answer question',
            extra_schema_dict_values={'className': 'sa-container'})

        sa_question.add_property(schema_fields.SchemaField(
            'version', '', 'string', optional=True, hidden=True))
        sa_question.add_property(schema_fields.SchemaField(
            'question', 'Question', 'html', optional=True,
            extra_schema_dict_values={'className': 'sa-question'}))
        sa_question.add_property(schema_fields.SchemaField(
            'description', 'Description', 'string', optional=True,
            extra_schema_dict_values={'className': 'sa-description'},
            description=messages.QUESTION_DESCRIPTION))
        sa_question.add_property(schema_fields.SchemaField(
            'hint', 'Hint', 'html', optional=True,
            extra_schema_dict_values={'className': 'sa-hint'}))
        sa_question.add_property(schema_fields.SchemaField(
            'defaultFeedback', 'Feedback', 'html', optional=True,
            extra_schema_dict_values={'className': 'sa-feedback'},
            description=messages.INCORRECT_ANSWER_FEEDBACK))

        sa_question.add_property(schema_fields.SchemaField(
            'rows', 'Rows', 'string', optional=True, i18n=False,
            extra_schema_dict_values={
                'className': 'sa-rows',
                'value': SaQuestionConstants.DEFAULT_HEIGHT_ROWS
            },
            description=messages.INPUT_FIELD_HEIGHT_DESCRIPTION))
        sa_question.add_property(schema_fields.SchemaField(
            'columns', 'Columns', 'string', optional=True, i18n=False,
            extra_schema_dict_values={
                'className': 'sa-columns',
                'value': SaQuestionConstants.DEFAULT_WIDTH_COLUMNS
            },
            description=messages.INPUT_FIELD_WIDTH_DESCRIPTION))

        grader_type = schema_fields.FieldRegistry(
            'Answer',
            extra_schema_dict_values={'className': 'sa-grader'})
        grader_type.add_property(schema_fields.SchemaField(
            'score', 'Score', 'string', optional=True, i18n=False,
            extra_schema_dict_values={'className': 'sa-grader-score'}))
        grader_type.add_property(schema_fields.SchemaField(
            'matcher', 'Grading', 'string', optional=True, i18n=False,
            select_data=cls.GRADER_TYPES,
            extra_schema_dict_values={'className': 'sa-grader-score'}))
        grader_type.add_property(schema_fields.SchemaField(
            'response', 'Response', 'string', optional=True,
            extra_schema_dict_values={'className': 'sa-grader-text'}))
        grader_type.add_property(schema_fields.SchemaField(
            'feedback', 'Feedback', 'html', optional=True,
            extra_schema_dict_values={'className': 'sa-grader-feedback'}))

        graders_array = schema_fields.FieldArray(
            'graders', '', item_type=grader_type,
            extra_schema_dict_values={
                'className': 'sa-grader-container',
                'listAddLabel': 'Add an answer',
                'listRemoveLabel': 'Delete this answer'})

        sa_question.add_property(graders_array)

        return sa_question

    def pre_save_hook(self, question):
        question.type = QuestionDTO.SHORT_ANSWER

    def get_default_content(self):
        return {
            'version': self.SCHEMA_VERSIONS[0],
            'question': '',
            'description': '',
            'graders': [{
                'score': '1.0',
                'matcher': 'case_insensitive',
                'response': '',
                'feedback': ''}]}

    def validate(self, question_dict, key, version, errors):
        # Currently only one version supported; version validity has already
        # been checked.
        self._validate15(question_dict, key, errors)

    def _validate15(self, question_dict, key, errors):
        if not question_dict['question'].strip():
            errors.append('The question must have a non-empty body.')

        if not question_dict['description']:
            errors.append('The description must be non-empty.')

        self.validate_no_description_collision(
            question_dict['description'], key, errors)

        try:
            # Coerce the rows attrib into a python int
            question_dict['rows'] = int(question_dict['rows'])
            if question_dict['rows'] <= 0:
                errors.append('Rows must be a positive whole number')
        except ValueError:
            errors.append('Rows must be a whole number')

        try:
            # Coerce the cols attrib into a python int
            question_dict['columns'] = int(question_dict['columns'])
            if question_dict['columns'] <= 0:
                errors.append('Columns must be a positive whole number')
        except ValueError:
            errors.append('Columns must be a whole number')

        if not question_dict['graders']:
            errors.append('The question must have at least one answer.')

        graders = question_dict['graders']
        for index in range(0, len(graders)):
            grader = graders[index]
            assert grader['matcher'] in [
                matcher for (matcher, unused_text) in self.GRADER_TYPES]
            if not grader['response'].strip():
                errors.append('Answer %s has no response text.' % (index + 1))
            try:
                float(grader['score'])
            except ValueError:
                errors.append(
                    'Answer %s must have a numeric score.' % (index + 1))
