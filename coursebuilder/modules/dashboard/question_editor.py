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


import cgi
import copy
import urllib
from common import schema_fields
from controllers.utils import ApplicationHandler
from controllers.utils import BaseRESTHandler
from controllers.utils import XsrfTokenManager
from models import transforms
from models.models import QuestionDAO
from models.models import QuestionDTO
from models.models import SaQuestionConstants
from modules.oeditor import oeditor
import messages
from unit_lesson_editor import CourseOutlineRights


class BaseDatastoreAssetEditor(ApplicationHandler):
    def get_form(self, rest_handler, key=''):
        """Build the Jinja template for adding a question."""
        rest_url = self.canonicalize_url(rest_handler.URI)
        exit_url = self.canonicalize_url('/dashboard?action=assets')
        if key:
            delete_url = '%s?%s' % (
                self.canonicalize_url(rest_handler.URI),
                urllib.urlencode({
                    'key': key,
                    'xsrf_token': cgi.escape(
                        self.create_xsrf_token(rest_handler.XSRF_TOKEN))
                    }))
        else:
            delete_url = None

        schema = rest_handler.get_schema()

        return oeditor.ObjectEditor.get_html_for(
            self,
            schema.get_json_schema(),
            schema.get_schema_dict(),
            key, rest_url, exit_url,
            delete_url=delete_url, delete_method='delete',
            required_modules=rest_handler.REQUIRED_MODULES,
            extra_js_files=rest_handler.EXTRA_JS_FILES)


class QuestionManagerAndEditor(BaseDatastoreAssetEditor):
    """An editor for editing and managing questions."""

    def prepare_template(self, rest_handler, key=''):
        """Build the Jinja template for adding a question."""
        template_values = {}
        template_values['page_title'] = self.format_title('Edit Question')
        template_values['main_content'] = self.get_form(rest_handler, key=key)

        return template_values

    def get_add_mc_question(self):
        self.render_page(self.prepare_template(McQuestionRESTHandler))

    def get_add_sa_question(self):
        self.render_page(self.prepare_template(SaQuestionRESTHandler))

    def get_edit_question(self):
        key = self.request.get('key')
        question = QuestionDAO.load(key)

        if not question:
            raise Exception('No question found')

        if question.type == QuestionDTO.MULTIPLE_CHOICE:
            self.render_page(
                self.prepare_template(McQuestionRESTHandler, key=key))
        elif question.type == QuestionDTO.SHORT_ANSWER:
            self.render_page(
                self.prepare_template(SaQuestionRESTHandler, key=key))
        else:
            raise Exception('Unknown question type: %s' % question.type)


class BaseQuestionRESTHandler(BaseRESTHandler):
    """Common methods for handling REST end points with questions."""

    def put(self):
        """Store a question in the datastore in response to a PUT."""
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
        question_dict = transforms.loads(payload)
        question_dict['description'] = question_dict['description'].strip()

        question_dict, errors = self.import_and_validate(question_dict, key)

        if errors:
            self.validation_error('\n'.join(errors), key=key)
            return

        if key:
            question = QuestionDTO(key, question_dict)
        else:
            question = QuestionDTO(None, question_dict)

        question.type = self.TYPE
        key_after_save = QuestionDAO.save(question)

        transforms.send_json_response(
            self, 200, 'Saved.', payload_dict={'key': key_after_save})

    def delete(self):
        """Remove a question from the datastore in response to DELETE."""
        key = self.request.get('key')

        if not self.assert_xsrf_token_or_fail(
                self.request, self.XSRF_TOKEN, {'key': key}):
            return

        if not CourseOutlineRights.can_delete(self):
            transforms.send_json_response(
                self, 401, 'Access denied.', {'key': key})
            return

        question = QuestionDAO.load(key)
        if not question:
            transforms.send_json_response(
                self, 404, 'Question not found.', {'key': key})
            return

        used_by = QuestionDAO.used_by(question.id)
        if used_by:
            group_names = ['"%s"' % x for x in used_by]
            transforms.send_json_response(
                self, 403,
                ('Question in use by question groups:\n%s.\nPlease delete it '
                 'from those groups and try again.') % ',\n'.join(group_names),
                {'key': key})
            return

        QuestionDAO.delete(question)
        transforms.send_json_response(self, 200, 'Deleted.')

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

    TYPE = QuestionDTO.MULTIPLE_CHOICE
    XSRF_TOKEN = 'mc-question-edit'

    SCHEMA_VERSION = '1.5'

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
            'score', 'Score', 'string', optional=True,
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

    def get(self):
        """Get the data to populate the question editor form."""

        def export(q_dict):
            p_dict = copy.deepcopy(q_dict)
            # InputEx does not correctly roundtrip booleans, so pass strings
            p_dict['multiple_selections'] = (
                'true' if q_dict.get('multiple_selections') else 'false')
            return p_dict

        key = self.request.get('key')

        if not CourseOutlineRights.can_view(self):
            transforms.send_json_response(
                self, 401, 'Access denied.', {'key': key})
            return

        if key:
            question = QuestionDAO.load(key)
            payload_dict = export(question.dict)
        else:
            payload_dict = {
                'version': self.SCHEMA_VERSION,
                'question': '',
                'description': '',
                'multiple_selections': 'false',
                'choices': [
                    {'score': '1', 'text': '', 'feedback': ''},
                    {'score': '0', 'text': '', 'feedback': ''},
                    {'score': '0', 'text': '', 'feedback': ''},
                    {'score': '0', 'text': '', 'feedback': ''}
                ]}

        transforms.send_json_response(
            self, 200, 'Success',
            payload_dict=payload_dict,
            xsrf_token=XsrfTokenManager.create_xsrf_token(self.XSRF_TOKEN))

    def import_and_validate(self, unvalidated_dict, key):
        version = unvalidated_dict.get('version')
        if self.SCHEMA_VERSION != version:
            return (None, ['Version %s question not supported.' % version])
        return self._import_and_validate15(unvalidated_dict, key)

    def _import_and_validate15(self, unvalidated_dict, key):
        errors = []
        try:
            question_dict = transforms.json_to_dict(
                unvalidated_dict, self.get_schema().get_json_schema_dict())
        except ValueError as err:
            errors.append(str(err))
            return (None, errors)

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

        return (question_dict, errors)


class SaQuestionRESTHandler(BaseQuestionRESTHandler):
    """REST handler for editing short answer questions."""

    URI = '/rest/question/sa'

    REQUIRED_MODULES = [
        'gcb-rte', 'inputex-select', 'inputex-string', 'inputex-list',
        'inputex-hidden', 'inputex-integer']
    EXTRA_JS_FILES = []

    TYPE = QuestionDTO.SHORT_ANSWER
    XSRF_TOKEN = 'sa-question-edit'

    GRADER_TYPES = [
        ('case_insensitive', 'Case insensitive string match'),
        ('regex', 'Regular expression'),
        ('numeric', 'Numeric')]

    SCHEMA_VERSION = '1.5'

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
            'rows', 'Rows', 'string', optional=True,
            extra_schema_dict_values={
                'className': 'sa-rows',
                'value': SaQuestionConstants.DEFAULT_HEIGHT_ROWS
            },
            description=messages.INPUT_FIELD_HEIGHT_DESCRIPTION))
        sa_question.add_property(schema_fields.SchemaField(
            'columns', 'Columns', 'string', optional=True,
            extra_schema_dict_values={
                'className': 'sa-columns',
                'value': SaQuestionConstants.DEFAULT_WIDTH_COLUMNS
            },
            description=messages.INPUT_FIELD_WIDTH_DESCRIPTION))

        grader_type = schema_fields.FieldRegistry(
            'Answer',
            extra_schema_dict_values={'className': 'sa-grader'})
        grader_type.add_property(schema_fields.SchemaField(
            'score', 'Score', 'string', optional=True,
            extra_schema_dict_values={'className': 'sa-grader-score'}))
        grader_type.add_property(schema_fields.SchemaField(
            'matcher', 'Grading', 'string', optional=True,
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

    def get(self):
        """Get the data to populate the question editor form."""
        key = self.request.get('key')

        if not CourseOutlineRights.can_view(self):
            transforms.send_json_response(
                self, 401, 'Access denied.', {'key': key})
            return

        if key:
            question = QuestionDAO.load(key)
            payload_dict = question.dict
        else:
            payload_dict = {
                'version': self.SCHEMA_VERSION,
                'question': '',
                'description': '',
                'graders': [
                    {
                        'score': '1.0',
                        'matcher': 'case_insensitive',
                        'response': '',
                        'feedback': ''}]}

        transforms.send_json_response(
            self, 200, 'Success',
            payload_dict=payload_dict,
            xsrf_token=XsrfTokenManager.create_xsrf_token(self.XSRF_TOKEN))

    def import_and_validate(self, unvalidated_dict, key):
        version = unvalidated_dict.get('version')
        if self.SCHEMA_VERSION != version:
            return (None, ['Version %s question not supported.' % version])
        return self._import_and_validate15(unvalidated_dict, key)

    def _import_and_validate15(self, unvalidated_dict, key):
        errors = []
        try:
            question_dict = transforms.json_to_dict(
                unvalidated_dict, self.get_schema().get_json_schema_dict())
        except ValueError as err:
            errors.append(str(err))
            return (None, errors)

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

        return (question_dict, errors)
