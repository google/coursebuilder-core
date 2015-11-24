# Copyright 2014 Google Inc. All Rights Reserved.
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

"""A feature to include questionnaires in lessons.

Usage:
    Include a form in the HTML of a lesson and give the form a unique id.
    E.g.,
        <form id="questionnaire-1">
            <label>Name: <input name="name"></label><br>
            Sex:
            <label>Female <input name="sex" type="radio" value="female"></label>
            <label>Male <input name="sex" type="radio" value="male"></label>
        </form>
    Then add a Questionnaire tag to the page, using the custom component toolbox
    in the rich text editor. Enter the id of the form into the tag. This will
    add a button to your page which the student presses to submit their
    responses. Responses are stored, and are shown and can be edited on
    subsequent visits to the page.
"""

__author__ = 'Neema Kotonya (neemak@google.com)'

import os
from xml.etree import cElementTree

import appengine_config
from common import jinja_utils
from common import schema_fields
from common import tags
from controllers.utils import BaseRESTHandler
from controllers.utils import XsrfTokenManager
from models import custom_modules
from models import data_removal
from models import data_sources
from models import models
from models import services
from models import transforms
from modules.questionnaire import messages

RESOURCES_PATH = '/modules/questionnaire/resources'

QUESTIONNAIRE_XSRF_TOKEN_NAME = 'questionnaire'

TEMPLATES_DIR = os.path.join(
    appengine_config.BUNDLE_ROOT, 'modules', 'questionnaire', 'templates')


class QuestionnaireTag(tags.ContextAwareTag):
    """A custom tag to manage submission and repopulation of questionnaires."""

    binding_name = 'gcb-questionnaire'

    @classmethod
    def name(cls):
        return 'Questionnaire'

    @classmethod
    def vendor(cls):
        return 'gcb'

    def get_icon_url(self):
        return '/modules/questionnaire/resources/img/icon.png'

    def render(self, node, context):
        """Renders the submit button."""

        xsrf_token = XsrfTokenManager.create_xsrf_token(
            QUESTIONNAIRE_XSRF_TOKEN_NAME)
        form_id = node.attrib.get('form-id')
        button_label = node.attrib.get('button-label')
        disabled = (node.attrib.get('disabled') == 'true')
        post_message = node.text

        user = context.handler.get_user()
        registered = False
        if user and models.Student.get_enrolled_student_by_user(user):
            registered = True

        template_vals = {
            'xsrf_token': xsrf_token,
            'form_id': form_id,
            'button_label': button_label,
            'disabled': disabled,
            'registered': registered,
            'post_message': post_message,
        }
        template = jinja_utils.get_template(
            'questionnaire.html', [TEMPLATES_DIR])
        button = template.render(template_vals)
        return tags.html_string_to_element_tree(button)

    def get_schema(self, unused_handler):
        reg = schema_fields.FieldRegistry('Questionnaire')
        reg.add_property(
            schema_fields.SchemaField(
                'form-id', 'Form ID', 'string', i18n=False,
                description=services.help_urls.make_learn_more_message(
                    messages.RTE_QUESTIONNAIRE_FORM_ID,
                    'questionnaire:questionnaire:form_id')))
        reg.add_property(
            schema_fields.SchemaField(
                'button-label', 'Submit Label', 'string', i18n=True,
                description=str(messages.RTE_QUESTIONNAIRE_SUBMIT_LABEL)))
        reg.add_property(
            schema_fields.SchemaField(
                'disabled', 'Disable Fields', 'boolean', optional=True,
                description=services.help_urls.make_learn_more_message(
                    messages.RTE_QUESTIONNAIRE_DISABLE_FIELDS,
                    'questionnaire:questionnaire:disabled')))
        reg.add_property(
            schema_fields.SchemaField(
                'post-message', 'Submission Text', 'text', optional=True,
                i18n=True,
                description=messages.RTE_QUESTIONNAIRE_SUBMISSION_TEXT))
        return reg

    def rollup_header_footer(self, context):
        header = cElementTree.Comment('Empty header')
        footer = cElementTree.Element('script')
        footer.attrib['src'] = (
            '/modules/questionnaire/resources/js/questionnaire.js')
        return (header, footer)


class StudentFormEntity(models.StudentPropertyEntity):

    @classmethod
    def load_or_default(cls, student, form_id):
        entity = cls.get(student, form_id)
        if entity is None:
            entity = cls.create(student, form_id)
            entity.value = '{}'
        return entity


class QuestionnaireHandler(BaseRESTHandler):
    """The REST Handler provides GET and PUT methods for the form data."""

    URL = '/rest/modules/questionnaire'

    SCHEMA = {
        'type': 'object',
        'properties': {
            'form_data': {'type': 'string', 'optional': 'true'}
        }
    }

    def get(self):
        """GET method is called when the page with the questionnaire loads."""

        key = self.request.get('key')

        if not self.assert_xsrf_token_or_fail(
                self.request, QUESTIONNAIRE_XSRF_TOKEN_NAME, {}):
            return

        user = self.get_user()
        if user is None:
            return

        student = models.Student.get_enrolled_student_by_user(user)
        if student is None:
            return

        entity = StudentFormEntity.load_or_default(student, key)
        if entity.value is None:
            return

        form_dict = transforms.loads(entity.value)

        transforms.send_json_response(
            self, 200, None,
            payload_dict=transforms.dict_to_json(form_dict))

    def post(self):
        """POST method called when the student submits answers."""

        # I18N: Message to show the user was not allowed to access to resource
        access_denied = self.gettext('Access denied.')

        # I18N: Message to acknowledge successful submission of the
        # questionnaire
        response_submitted = self.gettext('Response submitted.')

        request = transforms.loads(self.request.get('request'))

        key = request.get('key')

        if not self.assert_xsrf_token_or_fail(
                request, QUESTIONNAIRE_XSRF_TOKEN_NAME, {}):
            return

        user = self.get_user()
        if user is None:
            transforms.send_json_response(self, 401, access_denied, {})
            return

        student = models.Student.get_enrolled_student_by_user(user)
        if student is None:
            transforms.send_json_response(self, 401, access_denied, {})
            return

        payload_json = request.get('payload')
        payload_dict = transforms.json_to_dict(payload_json, self.SCHEMA)

        form_data = StudentFormEntity.load_or_default(student, key)
        form_data.value = transforms.dumps(payload_dict)
        form_data.put()

        transforms.send_json_response(self, 200, response_submitted)


class QuestionnaireDataSource(data_sources.AbstractDbTableRestDataSource):
    """Data source to export all questions responses for all students."""

    @classmethod
    def get_name(cls):
        return 'questionnaire_responses'

    @classmethod
    def get_title(cls):
        return 'Questionnaire Responses'

    @classmethod
    def exportable(cls):
        return True

    @classmethod
    def get_schema(cls, unused_app_context, unused_catch_and_log,
                   unused_source_context):
        reg = schema_fields.FieldRegistry('Questionnaire Response',
                                          description='Course sub-components')
        reg.add_property(schema_fields.SchemaField(
            'user_id', 'User ID', 'string',
            description='Student ID encrypted with a session-specific key'))
        reg.add_property(schema_fields.SchemaField(
            'questionnaire_id', 'Questionnaire ID', 'string',
            description='ID of questionnaire.'))

        form_data = schema_fields.FieldRegistry(None, 'form_data')
        form_data.add_property(schema_fields.SchemaField(
            'name', 'Field Name', 'string', optional=True,
            description='The questionnaire field name.'))
        form_data.add_property(schema_fields.SchemaField(
            'value', 'Field Value', 'string', optional=True,
            description='The student response in the questionnaire field.'))

        reg.add_property(schema_fields.FieldArray(
            'form_data', 'Form Data', item_type=form_data))
        return reg.get_json_schema_dict()['properties']

    @classmethod
    def get_entity_class(cls):
        return StudentFormEntity

    @classmethod
    def _postprocess_rows(cls, unused_app_context, source_context,
            unused_schema, unused_log, unused_page_number, form_entities):

        def to_string(value):
            if value is None or isinstance(value, basestring):
                return value
            else:
                return str(value)

        if source_context.send_uncensored_pii_data:
            transform_fn = lambda x: x
        else:
            transform_fn = cls._build_transform_fn(source_context)

        response_list = []

        for entity in form_entities:
            student_id, questionnaire_id = entity.key().name().split('-', 1)
            form_data = [
                {
                    'name': to_string(item.get('name')),
                    'value': to_string(item.get('value'))
                } for item in (
                    transforms.loads(entity.value).get('form_data', []))]
            response_list.append({
                'user_id': transform_fn(student_id),
                'questionnaire_id': questionnaire_id,
                'form_data': form_data
            })

        return response_list


questionnaire_module = None


def register_module():

    def on_module_enabled():
        tags.Registry.add_tag_binding(
            QuestionnaireTag.binding_name, QuestionnaireTag)
        data_sources.Registry.register(QuestionnaireDataSource)
        data_removal.Registry.register_indexed_by_user_id_remover(
            StudentFormEntity.delete_by_user_id_prefix)

    global_routes = [
        (os.path.join(RESOURCES_PATH, 'js', '.*'), tags.JQueryHandler),
        (os.path.join(RESOURCES_PATH, '.*'), tags.ResourcesHandler)]

    namespaced_routes = [(QuestionnaireHandler.URL, QuestionnaireHandler)]

    global questionnaire_module  # pylint: disable=global-statement
    questionnaire_module = custom_modules.Module(
        'Questionnaire',
        'Can create a questionnaire for students to answer.'
        'The responses submitted by students will be saved as a form which can'
        'be reviewed at a later date.',
        global_routes, namespaced_routes,
        notify_module_enabled=on_module_enabled)

    return questionnaire_module
