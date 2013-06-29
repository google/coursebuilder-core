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

"""Classes supporting creation and editing of quizzes."""

__author__ = 'John Orr (jorr@google.com)'


from common import schema_fields
from controllers.utils import BaseRESTHandler
from controllers.utils import XsrfTokenManager
from models import transforms
from models.models import QuestionDAO
from models.models import QuizDAO
from models.models import QuizDTO
import question_editor
from unit_lesson_editor import CourseOutlineRights


class QuizManagerAndEditor(question_editor.BaseDatastoreAssetEditor):
    """An editor for editing and managing quizzes."""

    def get_template_values(self, key):
        template_values = {}
        template_values['page_title'] = self.format_title('Edit Question')
        template_values['main_content'] = self.get_form(QuizRESTHandler, key)

        return template_values

    def get_add_quiz(self):
        self.render_page(self.get_template_values(''))

    def get_edit_quiz(self):
        self.render_page(self.get_template_values(self.request.get('key')))


class QuizRESTHandler(BaseRESTHandler):
    """REST handler for editing quizzes."""

    URI = '/rest/quiz'

    REQUIRED_MODULES = [
        'gcb-rte', 'inputex-hidden', 'inputex-select', 'inputex-string',
        'inputex-list']

    XSRF_TOKEN = 'quiz-edit'

    SCHEMA_VERSION = '1.5'

    @classmethod
    def get_schema(cls):
        """Return the InputEx schema for the quiz editor."""
        quiz = schema_fields.FieldRegistry(
            'Quiz', description='quiz')

        quiz.add_property(schema_fields.SchemaField(
            'version', '', 'string', optional=True, hidden=True))
        quiz.add_property(schema_fields.SchemaField(
            'name', 'Name', 'string', optional=True))
        quiz.add_property(schema_fields.SchemaField(
            'introduction', 'Introduction', 'html', optional=True))

        item_type = schema_fields.FieldRegistry(
            'Item', extra_schema_dict_values={'className': 'quiz-item'})
        item_type.add_property(schema_fields.SchemaField(
            'weight', 'Weight', 'string', optional=True,
            extra_schema_dict_values={'className': 'quiz-weight'}))

        question_select_data = [
            (q.id, q.description) for q in QuestionDAO.get_all()]

        item_type.add_property(schema_fields.SchemaField(
            'question', 'Question', 'string', optional=True,
            select_data=question_select_data,
            extra_schema_dict_values={'className': 'quiz-question'}))

        item_array = schema_fields.FieldArray(
            'items', '', item_type=item_type,
            extra_schema_dict_values={
                'className': 'quiz-items',
                'sortable': 'true',
                'listAddLabel': 'Add an item',
                'listRemoveLabel': 'Delete item'})

        quiz.add_property(item_array)

        return quiz

    def get(self):
        """Respond to the REST GET verb with the contents of the quiz."""
        key = self.request.get('key')

        if not CourseOutlineRights.can_view(self):
            transforms.send_json_response(
                self, 401, 'Access denied.', {'key': key})
            return

        if key:
            quiz = QuizDAO.load(key)
            version = quiz.dict.get('version')
            if self.SCHEMA_VERSION != version:
                transforms.send_json_response(
                    self, 403, 'Cannot edit a Version %s quiz.' % version,
                    {'key': key})
                return
            payload_dict = quiz.dict
        else:
            payload_dict = {'version': self.SCHEMA_VERSION}

        transforms.send_json_response(
            self, 200, 'Success',
            payload_dict=payload_dict,
            xsrf_token=XsrfTokenManager.create_xsrf_token(self.XSRF_TOKEN))

    def validate(self, quiz_dict):
        """Validate the quiz data sent from the form."""
        errors = []

        assert quiz_dict['version'] == self.SCHEMA_VERSION

        if not quiz_dict['name'].strip():
            errors.append('The quiz must have a non-empty name.')

        if not quiz_dict['items']:
            errors.append('The question must contain at least one question.')

        items = quiz_dict['items']
        for index in range(0, len(items)):
            item = items[index]
            try:
                float(item['weight'])
            except ValueError:
                errors.append(
                    'Item %s must have a numeric weight.' % (index + 1))

        return errors

    def put(self):
        """Store a quiz in the datastore in response to a PUT."""
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
        quiz_dict = transforms.json_to_dict(
            transforms.loads(payload),
            self.get_schema().get_json_schema_dict())

        validation_errors = self.validate(quiz_dict)
        if validation_errors:
            self.validation_error('\n'.join(validation_errors), key=key)
            return

        assert self.SCHEMA_VERSION == quiz_dict.get('version')

        if key:
            quiz = QuizDTO(key, quiz_dict)
        else:
            quiz = QuizDTO(None, quiz_dict)

        QuizDAO.save(quiz)
        transforms.send_json_response(self, 200, 'Saved.')

    def delete(self):
        """Delete the quiz in response to REST request."""
        key = self.request.get('key')

        if not self.assert_xsrf_token_or_fail(
                self.request, self.XSRF_TOKEN, {'key': key}):
            return

        if not CourseOutlineRights.can_delete(self):
            transforms.send_json_response(
                self, 401, 'Access denied.', {'key': key})
            return

        quiz = QuizDAO.load(key)
        if not quiz:
            transforms.send_json_response(
                self, 404, 'Quiz not found.', {'key': key})
            return
        QuizDAO.delete(quiz)
        transforms.send_json_response(self, 200, 'Deleted.')

