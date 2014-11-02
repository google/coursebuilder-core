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
from models import models
from models import transforms

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
        if user and models.Student.get_enrolled_student_by_email(user.email()):
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
                'form-id', 'Form ID', 'string', optional=True, i18n=False,
                description=(
                    'Enter a unique ID for this form. Note this must be '
                    'unique across your whole course. Then use this ID '
                    'as the ID attribute of your form element.')))
        reg.add_property(
            schema_fields.SchemaField(
                'button-label', 'Button Label', 'string', optional=True,
                i18n=True, description=(
                    'Text to be shown on submit button.')))
        reg.add_property(
            schema_fields.SchemaField(
                'disabled', 'Disabled', 'boolean', optional=True,
                description=(
                    'Use this option to render the form with data but leave '
                    'all the fields disabled. This is used to display the '
                    'results of a questionnaire on a different page.')))
        reg.add_property(
            schema_fields.SchemaField(
                'post-message', 'Post Message', 'text', optional=True,
                i18n=True, description=(
                    'Text shown to the student after they submit their '
                    'responses.')))
        return reg

    def rollup_header_footer(self, context):
        header = cElementTree.Comment('Empty header')
        footer = cElementTree.Element('script')
        footer.attrib['src'] = (
            '/modules/questionnaire/resources/js/questionnaire.js')
        return (header, footer)


class StudentFormEntity(models.StudentPropertyEntity):

    @classmethod
    def load_or_create(cls, student, form_id):
        entity = cls.get(student, form_id)
        if entity is None:
            entity = cls.create(student, form_id)
            entity.value = '{}'
            entity.put()
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

        student = models.Student.get_enrolled_student_by_email(user.email())
        if student is None:
            return

        entity = StudentFormEntity.load_or_create(student, key)
        if entity.value is None:
            return

        form_dict = transforms.loads(entity.value)

        transforms.send_json_response(
            self, 200, None,
            payload_dict=transforms.dict_to_json(form_dict, self.SCHEMA))

    def post(self):
        """POST method called when the student submits answers."""

        request = transforms.loads(self.request.get('request'))

        key = request.get('key')

        if not self.assert_xsrf_token_or_fail(
                request, QUESTIONNAIRE_XSRF_TOKEN_NAME, {}):
            return

        user = self.get_user()
        if user is None:
            transforms.send_json_response(self, 401, 'Access Denied.', {})
            return

        student = models.Student.get_enrolled_student_by_email(user.email())
        if student is None:
            transforms.send_json_response(self, 401, 'Access Denied.', {})
            return

        payload_json = request.get('payload')
        payload_dict = transforms.json_to_dict(payload_json, self.SCHEMA)

        form_data = StudentFormEntity.load_or_create(student, key)
        form_data.value = transforms.dumps(payload_dict)
        form_data.put()

        transforms.send_json_response(self, 200, 'Response submitted.')


questionnaire_module = None


def register_module():

    def on_module_enabled():
        tags.Registry.add_tag_binding(
            QuestionnaireTag.binding_name, QuestionnaireTag)

    def on_module_disabled():
        tags.Registry.remove_tag_binding(QuestionnaireTag.binding_name)

    global_routes = [
        (os.path.join(RESOURCES_PATH, 'js', '.*'), tags.JQueryHandler),
        (os.path.join(RESOURCES_PATH, '.*'), tags.ResourcesHandler)]

    namespaced_routes = [(QuestionnaireHandler.URL, QuestionnaireHandler)]

    global questionnaire_module
    questionnaire_module = custom_modules.Module(
        'Questionnaire',
        'Can create a questionnaire for students to answer.'
        'The responses submitted by students will be saved as a form which can'
        'be reviewed at a later date.',
        global_routes, namespaced_routes,
        notify_module_enabled=on_module_enabled,
        notify_module_disabled=on_module_disabled)

    return questionnaire_module
