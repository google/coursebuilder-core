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

from common import schema_fields
from common.crypto import XsrfTokenManager
from common import tags
from common import utils as common_utils
from models import roles
from models import transforms
from models import models
from models import resources_display
from models import services
from modules.assessment_tags import gift
from modules.dashboard import dto_editor
from modules.dashboard import utils as dashboard_utils
from modules.dashboard import messages


class QuestionManagerAndEditor(dto_editor.BaseDatastoreAssetEditor):
    """An editor for editing and managing questions."""

    def qmae_prepare_template(self, rest_handler, key='', auto_return=False):
        """Build the Jinja template for adding a question."""
        template_values = {}
        template_values['page_title'] = self.format_title('Edit Question')
        template_values['main_content'] = self.get_form(
            rest_handler, key,
            dashboard_utils.build_assets_url('edit_questions'),
            auto_return=auto_return)

        return template_values

    def get_add_mc_question(self):
        self.render_page(self.qmae_prepare_template(McQuestionRESTHandler),
                         in_action='edit_questions')

    def get_add_sa_question(self):
        self.render_page(self.qmae_prepare_template(SaQuestionRESTHandler),
                         in_action='edit_questions')

    def get_import_gift_questions(self):
        self.render_page(
            self.qmae_prepare_template(
                GiftQuestionRESTHandler, auto_return=True),
            in_action='edit_questions')

    def get_edit_question(self):
        key = self.request.get('key')
        question = models.QuestionDAO.load(key)

        if not question:
            raise Exception('No question found')

        if question.type == models.QuestionDTO.MULTIPLE_CHOICE:
            self.render_page(
                self.qmae_prepare_template(McQuestionRESTHandler, key=key),
                in_action='edit_questions')
        elif question.type == models.QuestionDTO.SHORT_ANSWER:
            self.render_page(
                self.qmae_prepare_template(SaQuestionRESTHandler, key=key),
                in_action='edit_questions')
        else:
            raise Exception('Unknown question type: %s' % question.type)

    def post_clone_question(self):
        original_question = models.QuestionDAO.load(self.request.get('key'))
        cloned_question = models.QuestionDAO.clone(original_question)
        cloned_question.description += ' (clone)'
        models.QuestionDAO.save(cloned_question)

    def get_question_preview(self):
        template_values = {}
        template_values['gcb_course_base'] = self.get_base_href(self)
        template_values['question'] = tags.html_to_safe_dom(
            '<question quid="{}">'.format(self.request.get('quid')), self)
        self.response.write(self.get_template(
            'question_preview.html').render(template_values))


class BaseQuestionRESTHandler(dto_editor.BaseDatastoreRestHandler):
    """Common methods for handling REST end points with questions."""

    SCHEMA_LOAD_HOOKS = []

    PRE_LOAD_HOOKS = []

    PRE_SAVE_HOOKS = []

    def sanitize_input_dict(self, json_dict):
        json_dict['description'] = json_dict['description'].strip()

    def is_deletion_allowed(self, question):

        used_by = models.QuestionDAO.used_by(question.id)
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
        descriptions = {q.description for q in models.QuestionDAO.get_all()
                        if not key or q.id != long(key)}
        if description in descriptions:
            errors.append(
                'The description must be different from existing questions.')


class McQuestionRESTHandler(BaseQuestionRESTHandler):
    """REST handler for editing multiple choice questions."""

    URI = '/rest/question/mc'

    EXTRA_REQUIRED_MODULES = ['array-extras']
    EXTRA_JS_FILES = [
        'question_editor_lib.js', 'mc_question_editor_lib.js',
        'mc_question_editor.js']

    ADDITIONAL_DIRS = []

    XSRF_TOKEN = 'mc-question-edit'

    SCHEMA_VERSIONS = ['1.5']

    DAO = models.QuestionDAO

    @classmethod
    def get_schema(cls):
        question_schema = resources_display.ResourceMCQuestion.get_schema(
            course=None, key=None)
        common_utils.run_hooks(cls.SCHEMA_LOAD_HOOKS, question_schema)
        return question_schema

    def pre_save_hook(self, question):
        question.type = models.QuestionDTO.MULTIPLE_CHOICE

    def get_default_content(self):
        return {
            'version': self.SCHEMA_VERSIONS[0],
            'question': '',
            'description': '',
            'multiple_selections': False,
            'choices': [
                {'score': '1', 'text': '', 'feedback': ''}
            ]}

    def validate(self, question_dict, key, version, errors):
        # Currently only one version supported; version validity has already
        # been checked.
        self._validate15(question_dict, key, errors)

    def _validate15(self, question_dict, key, errors):
        if not question_dict['question'].strip():
            errors.append('The question can\'t be blank.')

        if not question_dict['description']:
            errors.append('The description can\'t be blank.')

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

    EXTRA_JS_FILES = [
        'question_editor_lib.js', 'sa_question_editor.js',
        'sa_question_editor_lib.js']

    ADDITIONAL_DIRS = []

    XSRF_TOKEN = 'sa-question-edit'

    SCHEMA_VERSIONS = ['1.5']

    DAO = models.QuestionDAO

    @classmethod
    def get_schema(cls):
        question_schema = resources_display.ResourceSAQuestion.get_schema(
            course=None, key=None)
        common_utils.run_hooks(cls.SCHEMA_LOAD_HOOKS, question_schema)
        return question_schema

    def pre_save_hook(self, question):
        question.type = models.QuestionDTO.SHORT_ANSWER

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
            errors.append('The question can\'t be blank.')

        if not question_dict['description']:
            errors.append('The description can\'t be blank.')

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
                matcher for (matcher, unused_text)
                in resources_display.ResourceSAQuestion.GRADER_TYPES]
            if not grader['response'].strip():
                errors.append('Answer %s has no response text.' % (index + 1))
            try:
                float(grader['score'])
            except ValueError:
                errors.append(
                    'Answer %s must have a numeric score.' % (index + 1))


class GiftQuestionRESTHandler(dto_editor.BaseDatastoreRestHandler):
    """REST handler for importing gift questions."""

    URI = '/rest/question/gift'

    EXTRA_JS_FILES = []

    XSRF_TOKEN = 'import-gift-questions'

    @classmethod
    def get_schema(cls):
        """Get the InputEx schema for the short answer question editor."""
        gift_questions = schema_fields.FieldRegistry(
            'GIFT Questions',
            description='One or more GIFT-formatted questions',
            extra_schema_dict_values={'className': 'gift-container'})

        gift_questions.add_property(schema_fields.SchemaField(
            'version', '', 'string', optional=True, hidden=True))
        gift_questions.add_property(schema_fields.SchemaField(
            'description', 'Group Description', 'string', optional=True,
            description=messages.GIFT_GROUP_DESCRIPTION_DESCRIPTION,
            extra_schema_dict_values={'className': 'gift-description'}))
        gift_questions.add_property(schema_fields.SchemaField(
            'questions', 'Questions', 'text',
            description=services.help_urls.make_learn_more_message(
                messages.GIFT_QUESTIONS_DESCRIPTION,
                'dashboard:gift_questions:questions'),
            extra_schema_dict_values={'className': 'gift-questions'}))
        return gift_questions

    def validate_question_descriptions(self, questions, errors):
        descriptions = [q.description for q in models.QuestionDAO.get_all()]
        for question in questions:
            if question['description'] in descriptions:
                errors.append(
                    ('The description must be different '
                     'from existing questions.'))

    def validate_group_description(self, group_description, errors):
        descriptions = [gr.description
                        for gr in models.QuestionGroupDAO.get_all()]
        if group_description in descriptions:
            errors.append('Non-unique group description.')

    def get_default_content(self):
        return {
            'questions': '',
            'description': ''}

    def convert_to_dtos(self, questions):
        dtos = []
        for question in questions:
            question['version'] = models.QuestionDAO.VERSION
            dto = models.QuestionDTO(None, question)
            if dto.type == 'multi_choice':
                dto.type = models.QuestionDTO.MULTIPLE_CHOICE
            else:
                dto.type = models.QuestionDTO.SHORT_ANSWER
            dtos.append(dto)
        return dtos

    def create_group(self, description, question_ids):
        group = {
            'version': models.QuestionDAO.VERSION,
            'description': description,
            'introduction': '',
            'items': [{
                'question': str(x),
                'weight': 1.0} for x in question_ids]}
        return models.QuestionGroupDAO.create_question_group(group)

    def put(self):
        """Store a QuestionGroupDTO and QuestionDTO in the datastore."""
        request = transforms.loads(self.request.get('request'))

        if not self.assert_xsrf_token_or_fail(
                request, self.XSRF_TOKEN, {'key': None}):
            return

        if not roles.Roles.is_course_admin(self.app_context):
            transforms.send_json_response(self, 401, 'Access denied.')
            return

        payload = request.get('payload')
        json_dict = transforms.loads(payload)

        errors = []
        try:
            python_dict = transforms.json_to_dict(
                json_dict, self.get_schema().get_json_schema_dict())
            questions = gift.GiftParser.parse_questions(
                python_dict['questions'])
            self.validate_question_descriptions(questions, errors)
            self.validate_group_description(
                python_dict['description'], errors)
            if not errors:
                dtos = self.convert_to_dtos(questions)
                question_ids = models.QuestionDAO.save_all(dtos)
                self.create_group(python_dict['description'], question_ids)
        except ValueError as e:
            errors.append(str(e))
        except gift.ParseError as e:
            errors.append(str(e))
        except models.CollisionError as e:
            errors.append(str(e))
        if errors:
            self.validation_error('\n'.join(errors))
            return

        msg = 'Saved: %s.' % python_dict['description']
        transforms.send_json_response(self, 200, msg)
        return


class GeneralQuestionRESTHandler(BaseQuestionRESTHandler):
    """REST handler for editing questions of any type."""

    URI = '/rest/question/all'

    def get(self):
        key = self.request.get('key')
        if not roles.Roles.is_course_admin(self.app_context):
            transforms.send_json_response(
                self, 401, 'Access denied.', {'key': key})
            return

        if key:
            question_dto = models.QuestionDAO.load(key)
            if question_dto.type == models.QuestionDTO.MULTIPLE_CHOICE:
                mc_dict = question_dto.dict
                sa_dict = SaQuestionRESTHandler().get_default_content()
                qu_type = 'mc'
            elif question_dto.type == models.QuestionDTO.SHORT_ANSWER:
                mc_dict = McQuestionRESTHandler().get_default_content()
                sa_dict = question_dto.dict
                qu_type = 'sa'
            else:
                raise ValueError(
                    'Unrecognized question type ' + question_dto.type)
        else:
            mc_dict = McQuestionRESTHandler().get_default_content()
            sa_dict = SaQuestionRESTHandler().get_default_content()
            qu_type = None

        question_dict = {
            'quid': key,
            'qu_type': qu_type,
            'mc_tab': mc_dict,
            'sa_tab': sa_dict,
            'select_tab': {
                'quid': key
            }
        }

        xsrf_token_dict = {
            'mc_tab': XsrfTokenManager.create_xsrf_token(
                McQuestionRESTHandler.XSRF_TOKEN),
            'sa_tab': XsrfTokenManager.create_xsrf_token(
                SaQuestionRESTHandler.XSRF_TOKEN)
        }

        transforms.send_json_response(
            self, 200, 'Success',
            payload_dict=question_dict,
            xsrf_token=transforms.dumps(xsrf_token_dict))
