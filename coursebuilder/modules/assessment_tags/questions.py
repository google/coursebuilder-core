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

import base64
import logging
import os

import jinja2

import appengine_config
from common import jinja_utils
from common import schema_fields
from common import tags
from models import custom_modules
from models import models as m_models
from models import resources_display
from models import transforms

RESOURCES_PATH = '/modules/assessment_tags/resources'


@appengine_config.timeandlog('render_question', duration_only=True)
def render_question(
    quid, instanceid, embedded=False, weight=None, progress=None):
    """Generates the HTML for a question.

    Args:
      quid: String. The question id.
      instanceid: String. The unique reference id for the question instance
         (different instances of the same question in a page will have
         different instanceids).
      embedded: Boolean. Whether this question is embedded within a container
          object.
      weight: number. The weight to be used when grading the question in a
          scored lesson. This value is cast to a float and, if this cast
          fails, defaults to 1.0.
      progress: None, 0 or 1. If None, no progress marker should be shown. If
          0, a 'not-started' progress marker should be shown. If 1, a
          'complete' progress marker should be shown.

    Returns:
      a Jinja markup string that represents the HTML for the question.
    """
    try:
        question_dto = m_models.QuestionDAO.load(quid)
    except Exception:  # pylint: disable=broad-except
        logging.exception('Invalid question: %s', quid)
        return '[Invalid question]'

    if not question_dto:
        return '[Question deleted]'

    if weight is None:
        weight = 1.0
    else:
        try:
            weight = float(weight)
        except ValueError:
            weight = 1.0

    template_values = question_dto.dict
    template_values['embedded'] = embedded
    template_values['instanceid'] = instanceid
    template_values['resources_path'] = RESOURCES_PATH
    if progress is not None:
        template_values['progress'] = progress

    template_file = None
    js_data = {
        'quid': quid
    }
    if question_dto.type == question_dto.MULTIPLE_CHOICE:
        template_file = 'templates/mc_question.html'

        multi = template_values['multiple_selections']
        template_values['button_type'] = 'checkbox' if multi else 'radio'

        choices = [{
            'text': choice['text'], 'score': choice['score'],
            'feedback': choice.get('feedback')
        } for choice in template_values['choices']]
        js_data['choices'] = choices
        js_data['defaultFeedback'] = template_values.get('defaultFeedback')
        js_data['permuteChoices'] = (
            template_values.get('permute_choices', False))
        js_data['showAnswerWhenIncorrect'] = (
            template_values.get('show_answer_when_incorrect', False))
        js_data['allOrNothingGrading'] = (
            template_values.get('all_or_nothing_grading', False))
    elif question_dto.type == question_dto.SHORT_ANSWER:
        template_file = 'templates/sa_question.html'
        js_data['graders'] = template_values['graders']
        js_data['hint'] = template_values.get('hint')
        js_data['defaultFeedback'] = template_values.get('defaultFeedback')

        # The following two lines are included for backwards compatibility with
        # v1.5 questions that do not have the row and column properties set.
        template_values['rows'] = template_values.get(
            'rows',
            resources_display.SaQuestionConstants.DEFAULT_HEIGHT_ROWS)
        template_values['columns'] = template_values.get(
            'columns',
            resources_display.SaQuestionConstants.DEFAULT_WIDTH_COLUMNS)
    else:
        return '[Unsupported question type]'

    # Display the weight as an integer if it is sufficiently close to an
    # integer. Otherwise, round it to 2 decimal places. This ensures that the
    # weights displayed to the student are exactly the same as the weights that
    # are used for grading.
    weight = (int(round(weight)) if abs(weight - round(weight)) < 1e-6
              else round(weight, 2))
    template_values['displayed_weight'] = weight

    if not embedded:
        js_data['weight'] = float(weight)
    template_values['js_data'] = base64.b64encode(transforms.dumps(js_data))

    template = jinja_utils.get_template(
        template_file, [os.path.dirname(__file__)])
    return jinja2.utils.Markup(template.render(template_values))


class QuestionTag(tags.BaseTag):
    """A tag for rendering questions."""

    binding_name = 'question'

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

        quid = node.attrib.get('quid')
        weight = node.attrib.get('weight')

        instanceid = node.attrib.get('instanceid')

        progress = None
        if (hasattr(handler, 'student') and not handler.student.is_transient
            and not handler.lesson_is_scored):
            progress = handler.get_course().get_progress_tracker(
                ).get_component_progress(
                    handler.student, handler.unit_id, handler.lesson_id,
                    instanceid)

        html_string = render_question(
            quid, instanceid, embedded=False, weight=weight,
            progress=progress)
        return tags.html_string_to_element_tree(html_string)

    def get_schema(self, handler):
        """Get the schema for specifying the question."""
        reg = schema_fields.FieldRegistry('Question')

        if handler is None:
            reg.add_property(schema_fields.SchemaField(
                'quid', 'Question', 'string', optional=True, i18n=False))
            reg.add_property(schema_fields.SchemaField(
                'weight', 'Weight', 'number', optional=True, i18n=False))
            return reg

        reg.add_property(schema_fields.SchemaField(
            'quid', None, 'string', hidden=True, optional=True, i18n=False))
        reg.add_property(schema_fields.SchemaField(
            'qu_type', None, 'string', hidden=True, optional=True, i18n=False))
        reg.add_property(schema_fields.SchemaField(
            'weight', None, 'number', hidden=True, optional=True, i18n=False))

        select_schema = schema_fields.FieldRegistry(
            'Select',
            extra_schema_dict_values={'className': 'select-container'})

        question_list = [(
            unicode(q.id),  # q.id is an int; schema requires a string
            q.description) for q in m_models.QuestionDAO.get_all()]

        if question_list:
            select_schema.add_property(
                schema_fields.SchemaField(
                    'quid', 'Question', 'string', optional=True, i18n=False,
                    select_data=[
                        ('', '-- Select Existing Question --')] + question_list
            ))
        else:
            select_schema.add_property(
                schema_fields.SchemaField(
                    'unused_id', '', 'string', optional=True,
                    editable=False, extra_schema_dict_values={
                        'value': 'No questions available'}))

        course = handler.get_course()
        mc_schema = resources_display.ResourceMCQuestion.get_schema(
            course, None, forbidCustomTags=True)
        sa_schema = resources_display.ResourceSAQuestion.get_schema(
            course, None, forbidCustomTags=True)

        reg.add_sub_registry('mc_tab', registry=mc_schema)
        reg.add_sub_registry('sa_tab', registry=sa_schema)
        reg.add_sub_registry('select_tab', registry=select_schema)

        # TODO(jorr): This trick of putting a second weight field in here is
        # needed only because FieldRegistry.get_json_schema_dict() outputs all
        # top-level fields before the subregistries. Fix that and do a thorough
        # audit of its impact on other OEditor forms' layout.
        weight_holder = schema_fields.FieldRegistry('Weight Holder')
        weight_holder.add_property(
            schema_fields.SchemaField(
                'weight', 'Weight', 'number', optional=True, i18n=False,
                extra_schema_dict_values={
                    'value': '1',
                    'className': 'question-weight'},
                description='The number of points for a correct answer. '
                'If it is not set, it will default to one point.'))

        reg.add_sub_registry(
            'weight_holder', registry=weight_holder)

        return reg

    @classmethod
    def extra_js_files(cls):
        return [
            'question_editor_lib.js', 'mc_question_editor_lib.js',
            'sa_question_editor_lib.js', 'questions_popup.js']

    @classmethod
    def extra_css_files(cls):
        return ['questions_popup.css']

    @classmethod
    def additional_dirs(cls):
        return [
            os.path.join(appengine_config.BUNDLE_ROOT, 'modules',
                'assessment_tags', 'templates'),
            os.path.join(appengine_config.BUNDLE_ROOT, 'modules', 'dashboard',
                'templates'),
        ]


class QuestionGroupTag(tags.BaseTag):
    """A tag for rendering question groups."""

    binding_name = 'question-group'

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

        qgid = node.attrib.get('qgid')
        group_instanceid = node.attrib.get('instanceid')
        question_group_dto = m_models.QuestionGroupDAO.load(qgid)
        if not question_group_dto:
            return tags.html_string_to_element_tree('[Deleted question group]')

        template_values = question_group_dto.dict
        template_values['embedded'] = False
        template_values['instanceid'] = group_instanceid
        template_values['resources_path'] = RESOURCES_PATH

        if (hasattr(handler, 'student') and not handler.student.is_transient
            and not handler.lesson_is_scored):
            progress = handler.get_course().get_progress_tracker(
                ).get_component_progress(
                    handler.student, handler.unit_id, handler.lesson_id,
                    group_instanceid)
            template_values['progress'] = progress

        template_values['question_html_array'] = []
        js_data = {}
        for ind, item in enumerate(question_group_dto.dict['items']):
            quid = item['question']
            question_instanceid = '%s.%s.%s' % (group_instanceid, ind, quid)
            template_values['question_html_array'].append(render_question(
                quid, question_instanceid, weight=item['weight'],
                embedded=True
            ))
            js_data[question_instanceid] = item
        template_values['js_data'] = base64.b64encode(transforms.dumps(js_data))

        template_file = 'templates/question_group.html'
        template = jinja_utils.get_template(
            template_file, [os.path.dirname(__file__)])

        html_string = template.render(template_values)
        return tags.html_string_to_element_tree(html_string)

    def get_schema(self, handler):
        """Get the schema for specifying the question group."""
        question_group_list = []
        if handler:
            question_groups = m_models.QuestionGroupDAO.get_all()
            question_group_list = [(
                unicode(q.id),  # q.id is a number; schema requires a string
                q.description) for q in question_groups]

            if not question_group_list:
                return self.unavailable_schema('No question groups available')

        reg = schema_fields.FieldRegistry('Question Group')
        reg.add_property(
            schema_fields.SchemaField(
                'qgid', 'Question Group', 'string', optional=True, i18n=False,
                select_data=question_group_list))
        return reg


custom_module = None


def register_module():
    """Registers this module in the registry."""

    def when_module_enabled():
        # Register custom tags.
        tags.Registry.add_tag_binding(
            QuestionTag.binding_name, QuestionTag)
        tags.Registry.add_tag_binding(
            QuestionGroupTag.binding_name, QuestionGroupTag)
        for binding_name in (QuestionTag.binding_name,
                             QuestionGroupTag.binding_name):
            for scope in (tags.EditorBlacklists.COURSE_SCOPE,
                          tags.EditorBlacklists.DESCRIPTIVE_SCOPE):
                tags.EditorBlacklists.register(binding_name, scope)

    def when_module_disabled():
        # Unregister custom tags.
        tags.Registry.remove_tag_binding(QuestionTag.binding_name)
        tags.Registry.remove_tag_binding(QuestionGroupTag.binding_name)
        for binding_name in (QuestionTag, binding_name,
                             QuestionGroupTag.binding_name):
            for scope in (tags.EditorBlacklists.COURSE_SCOPE,
                          tags.EditorBlacklists.DESCRIPTIVE_SCOPE):
                tags.EditorBlacklists.unregister(binding_name, scope)

    # Add a static handler for icons shown in the rich text editor.
    global_routes = [(
        os.path.join(RESOURCES_PATH, '.*'), tags.ResourcesHandler)]

    global custom_module  # pylint: disable=global-statement
    custom_module = custom_modules.Module(
        'Question tags',
        'A set of tags for rendering questions within a lesson body.',
        global_routes,
        [],
        notify_module_enabled=when_module_enabled,
        notify_module_disabled=when_module_disabled)
    return custom_module
