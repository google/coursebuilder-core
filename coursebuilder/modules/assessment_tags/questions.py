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

"""Module for implementing question tags."""

__author__ = 'sll@google.com (Sean Lip)'


import os
from xml.etree import cElementTree

from common import jinja_utils
from common import schema_fields
from common import tags
from controllers import utils
import jinja2
from models import custom_modules
from models import models as m_models
from models import transforms


RESOURCES_PATH = '/modules/assessment_tags/resources'


def render_question(quid, instanceid, locale, embedded=False, weight=None):
    """Generates the HTML for a question.

    Args:
      quid: String. The question id.
      instanceid: String. The unique reference id for the question instance
         (different instances of the same question in a page will have
         different instanceids).
      locale: String. The locale for the Jinja environment that is used to
          generate the question HTML.
      embedded: Boolean. Whether this question is embedded within a container
          object.
      weight: float. The weight to be used when grading the question in a
          scored lesson.

    Returns:
      a Jinja markup string that represents the HTML for the question.
    """
    question_dto = m_models.QuestionDAO.load(quid)

    template_values = question_dto.dict
    template_values['embedded'] = embedded
    template_values['instanceid'] = instanceid
    template_values['resources_path'] = RESOURCES_PATH

    template_file = None
    js_data = {}
    if question_dto.type == question_dto.MULTIPLE_CHOICE:
        template_file = 'templates/mc_question.html'

        multi = template_values['multiple_selections']
        template_values['button_type'] = 'checkbox' if multi else 'radio'

        choices = [{
            'score': choice['score'], 'feedback': choice['feedback']
        } for choice in template_values['choices']]
        js_data['choices'] = choices
    elif question_dto.type == question_dto.SHORT_ANSWER:
        template_file = 'templates/sa_question.html'
        js_data['graders'] = template_values['graders']
        js_data['hint'] = template_values.get('hint')
        js_data['defaultFeedback'] = template_values.get('defaultFeedback')

    if not embedded:
        js_data['weight'] = weight
    template_values['js_data'] = transforms.dumps(js_data)

    template = jinja_utils.get_template(
        template_file, [os.path.dirname(__file__)], locale=locale)
    return jinja2.utils.Markup(template.render(template_values))


class QuestionTag(tags.BaseTag):
    """A tag for rendering questions."""

    def get_icon_url(self):
        return '/modules/assessment_tags/resources/question.png'

    @classmethod
    def name(cls):
        return 'Question'

    @classmethod
    def vendor(cls):
        return 'gcb'

    def render(self, node, handler):
        """Renders a question."""
        locale = (
            handler.template_value[utils.COURSE_INFO_KEY]['course']['locale'])

        quid = node.attrib.get('quid')
        try:
            weight = float(node.attrib.get('weight'))
        except TypeError:
            weight = 1.0

        instanceid = node.attrib.get('instanceid')

        div = cElementTree.XML(render_question(
            quid, instanceid, locale, embedded=False, weight=weight))
        return div

    def get_schema(self, unused_handler):
        """Get the schema for specifying the question."""
        questions = m_models.QuestionDAO.get_all()
        question_list = [(q.id, q.description) for q in questions]

        reg = schema_fields.FieldRegistry('Question')
        if question_list:
            reg.add_property(
                schema_fields.SchemaField(
                    'quid', 'Question', 'string', optional=True,
                    select_data=question_list))
            reg.add_property(
                schema_fields.SchemaField(
                    'weight', 'Weight', 'string', optional=True,
                    extra_schema_dict_values={'value': '1'},
                    description='The number of points for a correct answer.'))
        else:
            reg.add_property(
                schema_fields.SchemaField(
                    'quid', '', 'string', optional=True,
                    editable=False, extra_schema_dict_values={
                        'value': 'No questions available',
                        'visu': {
                            'visuType': 'funcName',
                            'funcName': 'disableSave'}}))

        return reg


class QuestionGroupTag(tags.BaseTag):
    """A tag for rendering question groups."""

    def get_icon_url(self):
        return '/modules/assessment_tags/resources/question_group.png'

    @classmethod
    def name(cls):
        return 'Question Group'

    @classmethod
    def vendor(cls):
        return 'gcb'

    def render(self, node, handler):
        """Renders a question."""
        locale = (
            handler.template_value[utils.COURSE_INFO_KEY]['course']['locale'])

        qgid = node.attrib.get('qgid')
        group_instanceid = node.attrib.get('instanceid')
        question_group_dto = m_models.QuestionGroupDAO.load(qgid)

        template_values = question_group_dto.dict
        template_values['instanceid'] = group_instanceid
        template_values['resources_path'] = RESOURCES_PATH

        template_values['question_html_array'] = []
        js_data = {}
        for ind, item in enumerate(question_group_dto.dict['items']):
            quid = item['question']
            question_instanceid = '%s.%s.%s' % (group_instanceid, ind, quid)
            template_values['question_html_array'].append(render_question(
                quid, question_instanceid, locale, embedded=True
            ))
            js_data[question_instanceid] = item
        template_values['js_data'] = transforms.dumps(js_data)

        template_file = 'templates/question_group.html'
        template = jinja_utils.get_template(
            template_file, [os.path.dirname(__file__)], locale=locale)

        div = cElementTree.XML(template.render(template_values))
        return div

    def get_schema(self, unused_handler):
        """Get the schema for specifying the question group."""
        question_groups = m_models.QuestionGroupDAO.get_all()
        question_group_list = [(q.id, q.name) for q in question_groups]

        reg = schema_fields.FieldRegistry('Question Group')
        if question_group_list:
            reg.add_property(
                schema_fields.SchemaField(
                    'qgid', 'Question Group', 'string', optional=True,
                    select_data=question_group_list))
        else:
            reg.add_property(
                schema_fields.SchemaField(
                    'qgid', '', 'string', optional=True,
                    editable=False, extra_schema_dict_values={
                        'value': 'No question groups available',
                        'visu': {
                            'visuType': 'funcName',
                            'funcName': 'disableSave'}}))
        return reg


custom_module = None


def register_module():
    """Registers this module in the registry."""

    def when_module_enabled():
        # Register custom tags.
        tags.Registry.add_tag_binding('question', QuestionTag)
        tags.Registry.add_tag_binding('question-group', QuestionGroupTag)

    def when_module_disabled():
        # Unregister custom tags.
        tags.Registry.remove_tag_binding('question')
        tags.Registry.remove_tag_binding('question-group')

    # Add a static handler for icons shown in the rich text editor.
    global_routes = [(
        os.path.join(RESOURCES_PATH, '.*'), tags.ResourcesHandler)]

    global custom_module
    custom_module = custom_modules.Module(
        'Question tags',
        'A set of tags for rendering questions within a lesson body.',
        global_routes,
        [],
        notify_module_enabled=when_module_enabled,
        notify_module_disabled=when_module_disabled)
    return custom_module
