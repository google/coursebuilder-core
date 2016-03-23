# Copyright 2015 Google Inc. All Rights Reserved.
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

"""Implement resource abstraction for Course-level items."""

__author__ = 'Mike Gainer (mgainer@google.com)'

import cgi
import yaml

import models
import courses
import messages

from common import resource
from common import safe_dom
from common import schema_fields
from common import tags
from common import utils as common_utils
from models import services
from tools import verify

DRAFT_TEXT = messages.DRAFT_TEXT
PUBLISHED_TEXT = messages.PUBLISHED_TEXT

# Allowed graders. Keys of this dict represent internal keys for the grader
# type, and the value represents the corresponding string that will appear in
# the dashboard UI.
AUTO_GRADER_NAME = 'Automatic grading'
HUMAN_GRADER_NAME = 'Peer review'
ALLOWED_GRADERS_NAMES = {
    courses.AUTO_GRADER: AUTO_GRADER_NAME,
    courses.HUMAN_GRADER: HUMAN_GRADER_NAME,
}

# When expanding GCB tags within questions, these tags may not be used
# (so as to forestall infinite recursion)
TAGS_EXCLUDED_FROM_QUESTIONS = set(
    ['question', 'question-group', 'gcb-questionnaire', 'text-file-upload-tag'])


class SaQuestionConstants(object):
    DEFAULT_WIDTH_COLUMNS = 100
    DEFAULT_HEIGHT_ROWS = 1


class ResourceQuestionBase(resource.AbstractResourceHandler):

    TYPE_MC_QUESTION = 'question_mc'
    TYPE_SA_QUESTION = 'question_sa'

    @classmethod
    def get_question_key_type(cls, qu):
        """Utility to convert between question type codes."""
        if qu.type == models.QuestionDTO.MULTIPLE_CHOICE:
            return cls.TYPE_MC_QUESTION
        elif qu.type == models.QuestionDTO.SHORT_ANSWER:
            return cls.TYPE_SA_QUESTION
        else:
            raise ValueError('Unknown question type: %s' % qu.type)

    @classmethod
    def get_resource(cls, course, key):
        return models.QuestionDAO.load(key)

    @classmethod
    def get_resource_title(cls, rsrc):
        return rsrc.description

    @classmethod
    def get_data_dict(cls, course, key):
        return cls.get_resource(course, key).dict

    @classmethod
    def get_view_url(cls, rsrc):
        return None

    @classmethod
    def get_edit_url(cls, key):
        return 'dashboard?action=edit_question&key=%s' % key

    @classmethod
    def _add_html_field_to(
            cls, registry, name, label, class_name, supportCustomTags,
            description=None, optional=True):
        registry.add_property(schema_fields.SchemaField(
            name, label, 'html', optional=optional,
            extra_schema_dict_values={
                'supportCustomTags': supportCustomTags,
                'excludedCustomTags': TAGS_EXCLUDED_FROM_QUESTIONS,
                'rteButtonSet': 'reduced',
                'className': class_name},
            description=description))


class ResourceSAQuestion(ResourceQuestionBase):

    TYPE = ResourceQuestionBase.TYPE_SA_QUESTION

    GRADER_TYPES = [
        ('case_insensitive', 'Case insensitive string match'),
        ('regex', 'Regular expression'),
        ('numeric', 'Numeric')]

    @classmethod
    def get_schema(cls, course, key, forbidCustomTags=False):
        """Get the InputEx schema for the short answer question editor."""
        supportCustomTags = (
            not forbidCustomTags and tags.CAN_USE_DYNAMIC_TAGS.value)

        sa_question = schema_fields.FieldRegistry(
            'Short Answer Question',
            description='short answer question',
            extra_schema_dict_values={'className': 'sa-container'})

        sa_question.add_property(schema_fields.SchemaField(
            'version', '', 'string', optional=True, hidden=True))
        cls._add_html_field_to(
            sa_question, 'question', 'Question', 'sa-question',
            supportCustomTags, optional=False)
        cls._add_html_field_to(
            sa_question, 'hint', 'Hint', 'sa-hint', supportCustomTags,
            description=messages.SHORT_ANSWER_HINT_DESCRIPTION)
        cls._add_html_field_to(
            sa_question, 'defaultFeedback', 'Feedback', 'sa-feedback',
            supportCustomTags,
            description=messages.INCORRECT_ANSWER_FEEDBACK)

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
            'score', 'Score', 'string',
            description=messages.SHORT_ANSWER_SCORE_DESCRIPTION,
            extra_schema_dict_values={
                'className': 'sa-grader-score',
                'value': '1.0',
            }, i18n=False))
        grader_type.add_property(schema_fields.SchemaField(
            'matcher', 'Type', 'string',
            description=messages.SHORT_ANSWER_TYPE_DESCRIPTION,
            extra_schema_dict_values={'className': 'sa-grader-score'},
            i18n=False, optional=True, select_data=cls.GRADER_TYPES))
        grader_type.add_property(schema_fields.SchemaField(
            'response', 'Answer', 'string',
            description=messages.SHORT_ANSWER_ANSWER_DESCRIPTION,
            extra_schema_dict_values={
                'className': 'inputEx-Field sa-grader-text'},
            optional=False))
        cls._add_html_field_to(
            grader_type, 'feedback', 'Feedback', 'sa-grader-feedback',
            supportCustomTags,
            description=messages.SHORT_ANSWER_FEEDBACK_DESCRIPTION)

        graders_array = schema_fields.FieldArray(
            'graders', '', item_type=grader_type,
            extra_schema_dict_values={
                'className': 'sa-grader-container',
                'listAddLabel': 'Add an answer',
                'listRemoveLabel': 'Delete this answer'},
            optional=True)

        sa_question.add_property(graders_array)

        sa_question.add_property(schema_fields.SchemaField(
            'description', 'Description', 'string', optional=False,
            extra_schema_dict_values={
                'className': 'inputEx-Field sa-description'},
            description=messages.QUESTION_DESCRIPTION))

        return sa_question


class ResourceMCQuestion(ResourceQuestionBase):

    TYPE = ResourceQuestionBase.TYPE_MC_QUESTION

    @classmethod
    def get_schema(cls, course, key, forbidCustomTags=False):
        """Get the InputEx schema for the multiple choice question editor."""
        supportCustomTags = (
            not forbidCustomTags and tags.CAN_USE_DYNAMIC_TAGS.value)

        mc_question = schema_fields.FieldRegistry(
            'Multiple Choice Question',
            description='multiple choice question',
            extra_schema_dict_values={'className': 'mc-container'})

        mc_question.add_property(schema_fields.SchemaField(
            'version', '', 'string', optional=True, hidden=True))
        cls._add_html_field_to(
            mc_question, 'question', 'Question', 'mc-question',
            supportCustomTags, optional=False)
        cls._add_html_field_to(
            mc_question, 'defaultFeedback', 'Feedback', 'mc-question',
            supportCustomTags,
            description=messages.MULTIPLE_CHOICE_FEEDBACK_DESCRIPTION)

        mc_question.add_property(schema_fields.SchemaField(
            'permute_choices', 'Randomize Choices', 'boolean',
            description=messages.MULTIPLE_CHOICE_RANDOMIZE_CHOICES_DESCRIPTION,
            extra_schema_dict_values={'className': 'mc-bool-option'},
            optional=True))

        mc_question.add_property(schema_fields.SchemaField(
            'all_or_nothing_grading', 'All or Nothing', 'boolean',
            optional=True, description='Disallow partial credit. Assign a '
            'score of 0.0 to a question unless its raw score is 1.0.',
            extra_schema_dict_values={'className': 'mc-bool-option'}))

        mc_question.add_property(schema_fields.SchemaField(
            'show_answer_when_incorrect', 'Display Correct', 'boolean',
            optional=True, description='Display the correct choice if '
            'answer is incorrect.',
            extra_schema_dict_values={'className': 'mc-bool-option'}))

        mc_question.add_property(schema_fields.SchemaField(
            'multiple_selections', 'Selection', 'boolean',
            optional=True,
            select_data=[
                (False, 'Allow only one selection'),
                (True, 'Allow multiple selections')],
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
        cls._add_html_field_to(
            choice_type, 'text', 'Text', 'mc-choice-text', supportCustomTags)
        cls._add_html_field_to(
            choice_type, 'feedback', 'Feedback', 'mc-choice-feedback',
            supportCustomTags,
            description=messages.MULTIPLE_CHOICE_CHOICE_FEEDBACK_DESCRIPTION)

        choices_array = schema_fields.FieldArray(
            'choices', None, item_type=choice_type,
            extra_schema_dict_values={
                'className': 'mc-choice-container',
                'listAddLabel': 'Add a choice',
                'listRemoveLabel': 'Delete choice'})

        mc_question.add_property(choices_array)

        mc_question.add_property(schema_fields.SchemaField(
            'description', 'Description', 'string', optional=False,
            extra_schema_dict_values={
                'className': 'inputEx-Field mc-description'},
            description=messages.QUESTION_DESCRIPTION))

        return mc_question


class ResourceQuestionGroup(resource.AbstractResourceHandler):

    TYPE = 'question_group'

    @classmethod
    def get_resource(cls, course, key):
        return models.QuestionGroupDAO.load(key)

    @classmethod
    def get_resource_title(cls, rsrc):
        return rsrc.description

    @classmethod
    def get_schema(cls, course, key):
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
            'weight', 'Weight', 'number', optional=True, i18n=False,
            extra_schema_dict_values={'className': 'question-group-weight'}))

        question_select_data = [(q.id, q.description) for q in sorted(
            models.QuestionDAO.get_all(), key=lambda x: x.description)]

        item_type.add_property(schema_fields.SchemaField(
            'question', 'Question', 'string', optional=True, i18n=False,
            select_data=question_select_data,
            extra_schema_dict_values={'className': 'question-group-question'}))

        item_array_classes = 'question-group-items'
        if not question_select_data:
            item_array_classes += ' empty-question-list'

        item_array = schema_fields.FieldArray(
            'items', None, item_type=item_type,
            extra_schema_dict_values={
                'className': item_array_classes,
                'sortable': 'true',
                'listAddLabel': 'Add a question',
                'listRemoveLabel': 'Remove'})

        question_group.add_property(item_array)

        return question_group

    @classmethod
    def get_data_dict(cls, course, key):
        return models.QuestionGroupDAO.load(int(key)).dict

    @classmethod
    def get_view_url(cls, rsrc):
        return None

    @classmethod
    def get_edit_url(cls, key):
        return 'dashboard?action=edit_question_group&key=%s' % key


class ResourceCourseSettings(resource.AbstractResourceHandler):

    TYPE = 'course_settings'

    @classmethod
    def get_resource(cls, course, key):
        entire_schema = course.create_settings_schema()
        return entire_schema.clone_only_items_named([key])

    @classmethod
    def get_resource_title(cls, rsrc):
        return ' '.join([sr.title for sr in rsrc.sub_registries.itervalues()])

    @classmethod
    def get_schema(cls, course, key):
        return cls.get_resource(course, key)

    @classmethod
    def get_data_dict(cls, course, key):
        schema = cls.get_schema(course, key)
        json_entity = {}
        schema.convert_entity_to_json_entity(
            course.get_environ(course.app_context), json_entity)
        return json_entity[key]

    @classmethod
    def get_view_url(cls, rsrc):
        return None

    @classmethod
    def get_edit_url(cls, key):
        action = 'settings_{}'.format(key)
        return 'dashboard?action={}'.format(action)


def workflow_key(key):
    return 'workflow:%s' % key


class LabelGroupsHelper(object):
    """Various methods that make it easier to attach labels to objects."""

    LABELS_FIELD_NAME = 'labels'
    TRACKS_FIELD_NAME = 'tracks'
    LOCALES_FIELD_NAME = 'locales'

    FIELDS = [
        {
            'name': LABELS_FIELD_NAME,
            'label': 'Labels',
            'description':
                'The {content} is tagged with these labels for your reference.',
            'type_id': models.LabelDTO.LABEL_TYPE_GENERAL,
        },
        {
            'name': TRACKS_FIELD_NAME,
            'label': 'Tracks',
            'description':
                'The {content} is part of these tracks. If none are selected, '
                'it will be part of all tracks.',
            'type_id': models.LabelDTO.LABEL_TYPE_COURSE_TRACK,
            'topic_id': 'labels:%s' % TRACKS_FIELD_NAME,
        },
        {
            'name': LOCALES_FIELD_NAME,
            'label': 'Languages',
            'description':
                'The {content} is available in these languages, in addition to '
                'the base language.',
            'type_id': models.LabelDTO.LABEL_TYPE_LOCALE,
        },
    ]

    @classmethod
    def add_labels_schema_fields(cls, schema, type_name, exclude_types=None):
        """Creates multiple form fields for choosing labels"""
        if exclude_types is None:
            exclude_types = []

        for field in cls.FIELDS:
            if field['name'] not in exclude_types:
                description = field['description'].format(content=type_name)
                topic_id = field.get('topic_id')
                if topic_id:
                    description = services.help_urls.make_learn_more_message(
                        description, topic_id)

                schema.add_property(schema_fields.FieldArray(
                    field['name'], field['label'], description=str(description),
                    extra_schema_dict_values={
                        '_type': 'checkbox-list',
                        'noItemsHideField': True,
                    },
                    item_type=schema_fields.SchemaField(None, None, 'string',
                        extra_schema_dict_values={'_type': 'boolean'},
                        i18n=False),
                    optional=True,
                    select_data=cls._labels_to_choices(field['type_id'])))

    @classmethod
    def _labels_to_choices(cls, label_type):
        """Produces select_data for a label type"""
        return [(label.id, label.title) for label in sorted(
            models.LabelDAO.get_all_of_type(label_type),
            key=lambda label: label.title)]

    @classmethod
    def remove_label_field_data(cls, data):
        """Deletes label field data from a payload"""
        for field in cls.FIELDS:
            del data[field['name']]

    @classmethod
    def field_data_to_labels(cls, data):
        """Collects chosen labels from all fields into a single set"""
        labels = set()
        for field in cls.FIELDS:
            if field['name'] in data:
                labels |= set(data[field['name']])
        return labels

    @classmethod
    def _filter_labels(cls, labels, label_type):
        """Filters chosen labels by a given type"""
        return [label.id for label in sorted(
            models.LabelDAO.get_all_of_type(label_type),
            key=lambda label: label.title)
        if str(label.id) in labels]

    @classmethod
    def labels_to_field_data(cls, labels, exclude_types=None):
        """Filters chosen labels by type into data for multiple fields"""
        if exclude_types is None:
            exclude_types = []
        return {
            field['name']: cls._filter_labels(labels, field['type_id'])
            for field in cls.FIELDS
            if not field['name'] in exclude_types}


class UnitTools(object):

    def __init__(self, course):
        self._course = course

    def apply_updates(self, unit, updated_unit_dict, errors):
        if unit.type == verify.UNIT_TYPE_ASSESSMENT:
            self._apply_updates_to_assessment(unit, updated_unit_dict, errors)
        elif unit.type == verify.UNIT_TYPE_LINK:
            self._apply_updates_to_link(unit, updated_unit_dict, errors)
        elif unit.type == verify.UNIT_TYPE_UNIT:
            self._apply_updates_to_unit(unit, updated_unit_dict, errors)
        else:
            raise ValueError('Unknown unit type %s' % unit.type)

    def _apply_updates_common(self, unit, updated_unit_dict, errors):
        """Apply changes common to all unit types."""
        if 'title' in updated_unit_dict:
            unit.title = updated_unit_dict['title']
        if 'description' in updated_unit_dict:
            unit.description = updated_unit_dict['description']
        labels = LabelGroupsHelper.field_data_to_labels(updated_unit_dict)

        if labels and self._course.get_parent_unit(unit.unit_id):
            track_label_ids = models.LabelDAO.get_set_of_ids_of_type(
                models.LabelDTO.LABEL_TYPE_COURSE_TRACK)
            if track_label_ids.intersection(labels):
                errors.append('Cannot set track labels on entities which '
                              'are used within other units.')

        unit.labels = common_utils.list_to_text(labels)

    def _apply_updates_to_assessment(self, unit, updated_unit_dict, errors):
        """Store the updated assessment."""

        entity_dict = {}
        ResourceAssessment.get_schema(
            self._course, unit.unit_id).convert_json_to_entity(
                updated_unit_dict, entity_dict)

        self._apply_updates_common(unit, entity_dict, errors)
        if 'weight' in entity_dict:
            try:
                unit.weight = float(entity_dict['weight'])
                if unit.weight < 0:
                    errors.append('The weight must be a non-negative integer.')
            except ValueError:
                errors.append('The weight must be an integer.')
        if 'content' in entity_dict:
            content = entity_dict['content']
            if content:
                self._course.set_assessment_content(
                    unit, content, errors=errors)

        if 'html_content' in entity_dict:
            unit.html_content = entity_dict['html_content']
        if 'html_check_answers' in entity_dict:
            unit.html_check_answers = entity_dict['html_check_answers']

        if 'workflow' in entity_dict:
            workflow_dict = entity_dict['workflow']

            def convert_date(key):
                due_date = workflow_dict.get(key)
                if due_date:
                    workflow_dict[key] = due_date.strftime(
                        courses.ISO_8601_DATE_FORMAT)

            convert_date(courses.SUBMISSION_DUE_DATE_KEY)
            convert_date(courses.REVIEW_DUE_DATE_KEY)

            if len(courses.ALLOWED_MATCHERS_NAMES) == 1:
                workflow_dict[courses.MATCHER_KEY] = (
                    courses.ALLOWED_MATCHERS_NAMES.keys()[0])
            unit.workflow_yaml = yaml.safe_dump(workflow_dict)
            unit.workflow.validate(errors=errors)

        # Only save the review form if the assessment needs human grading.
        if not errors:
            if self._course.needs_human_grader(unit):
                if 'review_form' in entity_dict:
                    review_form = entity_dict['review_form']
                    if review_form:
                        self._course.set_review_form(
                            unit, review_form, errors=errors)
                if 'html_review_form' in entity_dict:
                    unit.html_review_form = entity_dict['html_review_form']
            elif entity_dict.get('review_form'):
                errors.append(
                    'Review forms for auto-graded assessments should be empty.')

    def _apply_updates_to_link(self, unit, updated_unit_dict, errors):
        self._apply_updates_common(unit, updated_unit_dict, errors)
        if 'url' in updated_unit_dict:
            unit.href = updated_unit_dict['url']

    def _is_assessment_unused(self, unit, assessment, errors):
        parent_unit = self._course.get_parent_unit(assessment.unit_id)
        if parent_unit and parent_unit.unit_id != unit.unit_id:
            errors.append(
                'Assessment "%s" is already associated to unit "%s"' % (
                    assessment.title, parent_unit.title))
            return False
        return True

    def _is_assessment_version_ok(self, assessment, errors):
        # Here, we want to establish that the display model for the
        # assessment is compatible with the assessment being used in
        # the context of a Unit.  Model version 1.4 is not, because
        # the way sets up submission is to build an entirely new form
        # from JavaScript (independent of the form used to display the
        # assessment), and the way it learns the ID of the assessment
        # is by looking in the URL (as opposed to taking a parameter).
        # This is incompatible with the URLs for unit display, so we
        # just disallow older assessments here.
        model_version = self._course.get_assessment_model_version(assessment)
        if model_version == courses.ASSESSMENT_MODEL_VERSION_1_4:
            errors.append(
                'The version of assessment "%s" ' % assessment.title +
                'is not compatible with use as a pre/post unit element')
            return False
        return True

    def _is_assessment_on_track(self, assessment, errors):
        if self._course.get_unit_track_labels(assessment):
            errors.append(
                'Assessment "%s" has track labels, ' % assessment.title +
                'so it cannot be used as a pre/post unit element')
            return True
        return False

    def _apply_updates_to_unit(self, unit, updated_unit_dict, errors):
        self._apply_updates_common(unit, updated_unit_dict, errors)
        if 'unit_header' in updated_unit_dict:
            unit.unit_header = updated_unit_dict['unit_header']
        if 'unit_footer' in updated_unit_dict:
            unit.unit_footer = updated_unit_dict['unit_footer']
        if 'manual_progress' in updated_unit_dict:
            unit.manual_progress = updated_unit_dict['manual_progress']
        if 'pre_assessment' in updated_unit_dict:
            unit.pre_assessment = None
            pre_assessment_id = updated_unit_dict['pre_assessment']
            if pre_assessment_id >= 0:
                assessment = self._course.find_unit_by_id(pre_assessment_id)
                if (self._is_assessment_unused(unit, assessment, errors) and
                    self._is_assessment_version_ok(assessment, errors) and
                    not self._is_assessment_on_track(assessment, errors)):
                    unit.pre_assessment = pre_assessment_id
        if 'post_assessment' in updated_unit_dict:
            unit.post_assessment = None
            post_assessment_id = updated_unit_dict['post_assessment']
            if (post_assessment_id >= 0 and
                pre_assessment_id == post_assessment_id):

                errors.append(
                    'The same assessment cannot be used as both the pre '
                    'and post assessment of a unit.')
            elif post_assessment_id >= 0:
                assessment = self._course.find_unit_by_id(post_assessment_id)
                if (assessment and
                    self._is_assessment_unused(unit, assessment, errors) and
                    self._is_assessment_version_ok(assessment, errors) and
                    not self._is_assessment_on_track(assessment, errors)):
                    unit.post_assessment = post_assessment_id
        if 'show_contents_on_one_page' in updated_unit_dict:
            unit.show_contents_on_one_page = (
                updated_unit_dict['show_contents_on_one_page'])

    def unit_to_dict(self, unit, keys=None):
        if unit.type == verify.UNIT_TYPE_ASSESSMENT:
            return self._assessment_to_dict(unit, keys=keys)
        elif unit.type == verify.UNIT_TYPE_LINK:
            return self._link_to_dict(unit)
        elif unit.type == verify.UNIT_TYPE_UNIT:
            return self._unit_to_dict(unit)
        else:
            raise ValueError('Unknown unit type %s' % unit.type)

    def _unit_to_dict_common(self, unit):
        data = {
            'key': unit.unit_id,
            'type': verify.UNIT_TYPE_NAMES[unit.type],
            'title': unit.title,
            'description': unit.description or '',
        }

        exclude_types = []
        if self._course.get_parent_unit(unit.unit_id):
            exclude_types.append(LabelGroupsHelper.TRACKS_FIELD_NAME)

        data.update(LabelGroupsHelper.labels_to_field_data(
            common_utils.text_to_list(unit.labels),
            exclude_types=exclude_types))

        return data

    def _get_assessment_path(self, unit):
        return self._course.app_context.fs.impl.physical_to_logical(
            self._course.get_assessment_filename(unit.unit_id))

    def _get_review_form_path(self, unit):
        return self._course.app_context.fs.impl.physical_to_logical(
            self._course.get_review_filename(unit.unit_id))

    def _assessment_to_dict(self, unit, keys=None):
        """Assemble a dict with the unit data fields."""
        assert unit.type == 'A'

        content = None
        if keys is not None and 'content' in keys:
            path = self._get_assessment_path(unit)
            fs = self._course.app_context.fs
            if fs.isfile(path):
                content = fs.get(path)
            else:
                content = ''

        review_form = None
        if keys is not None and 'review_form' in keys:
            review_form_path = self._get_review_form_path(unit)
            if review_form_path and fs.isfile(review_form_path):
                review_form = fs.get(review_form_path)
            else:
                review_form = ''

        workflow = unit.workflow

        if workflow.get_submission_due_date():
            submission_due_date = workflow.get_submission_due_date()
        else:
            submission_due_date = None

        if workflow.get_review_due_date():
            review_due_date = workflow.get_review_due_date()
        else:
            review_due_date = None

        unit_common = self._unit_to_dict_common(unit)
        unit_common.update({
            'weight': str(unit.weight if hasattr(unit, 'weight') else 0),
            'content': content,
            'html_content': (
                '' if unit.is_old_style_assessment(self._course)
                else unit.html_content),
            'html_check_answers': (
                False if unit.is_old_style_assessment(self._course)
                else unit.html_check_answers),
            workflow_key(courses.SINGLE_SUBMISSION_KEY): (
                workflow.is_single_submission()),
            workflow_key(courses.SUBMISSION_DUE_DATE_KEY): (
                submission_due_date),
            workflow_key(courses.SHOW_FEEDBACK_KEY): (
                workflow.show_feedback()),
            workflow_key(courses.GRADER_KEY): workflow.get_grader(),
            })
        return {
            'assessment': unit_common,
            'review_opts': {
                workflow_key(courses.MATCHER_KEY): workflow.get_matcher(),
                workflow_key(courses.REVIEW_DUE_DATE_KEY): review_due_date,
                workflow_key(courses.REVIEW_MIN_COUNT_KEY): (
                    workflow.get_review_min_count()),
                workflow_key(courses.REVIEW_WINDOW_MINS_KEY): (
                    workflow.get_review_window_mins()),
                'review_form': review_form,
                'html_review_form': (
                    unit.html_review_form or ''
                    if hasattr(unit, 'html_review_form') else ''),
                }
            }

    def _link_to_dict(self, unit):
        assert unit.type == 'O'
        ret = self._unit_to_dict_common(unit)
        ret['url'] = unit.href
        return ret

    def _unit_to_dict(self, unit):
        assert unit.type == 'U'
        ret = self._unit_to_dict_common(unit)
        ret['unit_header'] = unit.unit_header or ''
        ret['unit_footer'] = unit.unit_footer or ''
        ret['pre_assessment'] = unit.pre_assessment or -1
        ret['post_assessment'] = unit.post_assessment or -1
        ret['show_contents_on_one_page'] = (
            unit.show_contents_on_one_page or False)
        ret['manual_progress'] = unit.manual_progress or False
        return ret


class ResourceUnitBase(resource.AbstractResourceHandler):

    ASSESSMENT_TYPE = 'assessment'
    UNIT_TYPE = 'unit'
    LINK_TYPE = 'link'

    # These default values can be overridden by class-scoped constants in
    # specific derived classes.
    TITLE_DESCRIPTION = messages.UNIT_TITLE_DESCRIPTION
    DESCRIPTION_DESCRIPTION = messages.UNIT_DESCRIPTION_DESCRIPTION

    @classmethod
    def key_for_unit(cls, unit, course=None):
        if unit.type == verify.UNIT_TYPE_ASSESSMENT:
            unit_type = cls.ASSESSMENT_TYPE
        elif unit.type == verify.UNIT_TYPE_LINK:
            unit_type = cls.LINK_TYPE
        elif unit.type == verify.UNIT_TYPE_UNIT:
            unit_type = cls.UNIT_TYPE
        else:
            raise ValueError('Unknown unit type: %s' % unit.type)
        return resource.Key(unit_type, unit.unit_id, course=course)

    @classmethod
    def get_resource(cls, course, key):
        return course.find_unit_by_id(key)

    @classmethod
    def get_resource_title(cls, rsrc):
        return rsrc.title

    @classmethod
    def get_data_dict(cls, course, key):
        unit = course.find_unit_by_id(key)
        return UnitTools(course).unit_to_dict(unit)

    @classmethod
    def _generate_common_schema(
            cls, title, hidden_header=False, exclude_fields=None):
        group_class_name = 'inputEx-Group new-form-layout'
        if hidden_header:
            group_class_name += ' hidden-header'

        ret = schema_fields.FieldRegistry(title, extra_schema_dict_values={
            'className': group_class_name})
        ret.add_property(schema_fields.SchemaField(
            'key', 'ID', 'string', editable=False,
            extra_schema_dict_values={'className': 'inputEx-Field keyHolder'},
            hidden=True))
        ret.add_property(schema_fields.SchemaField(
            'type', 'Type', 'string', editable=False, hidden=True))
        ret.add_property(schema_fields.SchemaField(
            'title', 'Title', 'string',
            description=cls.TITLE_DESCRIPTION, optional=False))
        ret.add_property(schema_fields.SchemaField(
            'description', 'Description', 'string',
            description=cls.DESCRIPTION_DESCRIPTION, optional=True))
        return ret


class ResourceUnit(ResourceUnitBase):

    TYPE = ResourceUnitBase.UNIT_TYPE

    @classmethod
    def get_schema(cls, course, key):
        schema = cls._generate_common_schema('Unit')
        LabelGroupsHelper.add_labels_schema_fields(schema, 'unit')
        schema.add_property(schema_fields.SchemaField(
            'pre_assessment', 'Pre-Assessment', 'integer', optional=True,
            description=messages.UNIT_PRE_ASSESSMENT_DESCRIPTION))
        schema.add_property(schema_fields.SchemaField(
            'post_assessment', 'Post-Assessment', 'integer', optional=True,
            description=messages.UNIT_POST_ASSESSMENT_DESCRIPTION))
        schema.add_property(schema_fields.SchemaField(
            'show_contents_on_one_page', 'Show on One Page', 'boolean',
            description=messages.UNIT_SHOW_ON_ONE_PAGE_DESCRIPTION,
            optional=True))
        schema.add_property(schema_fields.SchemaField(
            'manual_progress', 'Allow Manual Completion', 'boolean',
            description=services.help_urls.make_learn_more_message(
                messages.UNIT_ALLOW_MANUAL_COMPLETION_DESCRIPTION,
                'course:%s:manual_progress' % ResourceUnitBase.UNIT_TYPE),
            optional=True))
        schema.add_property(schema_fields.SchemaField(
            'unit_header', 'Header', 'html', optional=True,
            description=messages.UNIT_HEADER_DESCRIPTION,
            extra_schema_dict_values={
                'supportCustomTags': tags.CAN_USE_DYNAMIC_TAGS.value,
                'excludedCustomTags': tags.EditorBlacklists.DESCRIPTIVE_SCOPE,
                'className': 'inputEx-Field html-content cb-editor-small'}))
        schema.add_property(schema_fields.SchemaField(
            'unit_footer', 'Footer', 'html', optional=True,
            description=messages.UNIT_FOOTER_DESCRIPTION,
            extra_schema_dict_values={
                'supportCustomTags': tags.CAN_USE_DYNAMIC_TAGS.value,
                'excludedCustomTags': tags.EditorBlacklists.DESCRIPTIVE_SCOPE,
                'className': 'inputEx-Field html-content cb-editor-small'}))
        return schema

    @classmethod
    def get_view_url(cls, rsrc):
        return 'unit?unit=%s' % rsrc.unit_id

    @classmethod
    def get_edit_url(cls, key):
        return 'dashboard?action=edit_unit&key=%s' % key

class ResourceAssessment(ResourceUnitBase):

    TYPE = ResourceUnitBase.ASSESSMENT_TYPE

    TITLE_DESCRIPTION = messages.ASSESSMENT_TITLE_DESCRIPTION
    DESCRIPTION_DESCRIPTION = messages.ASSESSMENT_DESCRIPTION_DESCRIPTION
    AVAILABILITY_DESCRIPTION = messages.ASSESSMENT_AVAILABILITY_DESCRIPTION
    SYLLABUS_VISIBILITY_DESCRIPTION = (
        messages.ASSESSMENT_SYLLABUS_VISIBILITY_DESCRIPTION)

    @classmethod
    def get_schema(cls, course, key):
        reg = schema_fields.FieldRegistry('Assessment',
            extra_schema_dict_values={
                'className': 'inputEx-Group new-form-layout'})

        # Course level settings.
        course_opts = cls._generate_common_schema(
            'Assessment Config', hidden_header=True)

        unit = cls.get_resource(course, key)
        exclude_types = []
        if course.get_parent_unit(unit.unit_id):
            exclude_types.append(LabelGroupsHelper.TRACKS_FIELD_NAME)

        LabelGroupsHelper.add_labels_schema_fields(
            course_opts, 'assessment', exclude_types=exclude_types)

        course_opts.add_property(schema_fields.SchemaField(
            'weight', 'Points', 'number',
            description=messages.ASSESSMENT_POINTS_DESCRIPTION,
            i18n=False, optional=False))
        course_opts.add_property(schema_fields.SchemaField(
            'content', 'Assessment Content (JavaScript)', 'text', optional=True,
            description=services.help_urls.make_learn_more_message(
                messages.ASSESSMENT_CONTENT_JAVASCRIPT_DESCRIPTION,
                'course:%s:content' % ResourceUnitBase.ASSESSMENT_TYPE),
            extra_schema_dict_values={'className': 'inputEx-Field content'}))
        course_opts.add_property(schema_fields.SchemaField(
            'html_content', 'Assessment Content', 'html', optional=True,
            description=services.help_urls.make_learn_more_message(
                messages.ASSESSMENT_CONTENT_DESCRIPTION,
                'course:%s:html_content' % ResourceUnitBase.ASSESSMENT_TYPE),
            extra_schema_dict_values={
                'supportCustomTags': tags.CAN_USE_DYNAMIC_TAGS.value,
                'excludedCustomTags': tags.EditorBlacklists.ASSESSMENT_SCOPE,
                'className': 'inputEx-Field html-content'}))
        course_opts.add_property(schema_fields.SchemaField(
            'html_check_answers', "Show Correct Answer", 'boolean',
            description=messages.ASSESSMENT_SHOW_CORRECT_ANSWER_DESCRIPTION,
            extra_schema_dict_values={
                'className': ('inputEx-Field inputEx-CheckBox'
                              ' assessment-editor-check-answers')},
            optional=True))
        course_opts.add_property(schema_fields.SchemaField(
            workflow_key(courses.SINGLE_SUBMISSION_KEY), 'Single Submission',
            'boolean', optional=True,
            description=messages.ASSESSMENT_SINGLE_SUBMISSION_DESCRIPTION))
        course_opts.add_property(schema_fields.SchemaField(
            workflow_key(courses.SUBMISSION_DUE_DATE_KEY),
            'Due Date', 'datetime', optional=True,
            description=str(messages.ASSESSMENT_DUE_DATE_FORMAT_DESCRIPTION),
            extra_schema_dict_values={'_type': 'datetime'}))
        course_opts.add_property(schema_fields.SchemaField(
            workflow_key(courses.SHOW_FEEDBACK_KEY), 'Show Feedback',
            'boolean', optional=True,
            description=messages.ASSESSMENT_SHOW_FEEDBACK_DESCRIPTION))
        course_opts.add_property(schema_fields.SchemaField(
            workflow_key(courses.GRADER_KEY), 'Grading Method', 'string',
            select_data=ALLOWED_GRADERS_NAMES.items(), optional=True,
            description=services.help_urls.make_learn_more_message(
                messages.ASSESSMENT_GRADING_METHOD_DESCRIPTION,
                'course:%s:%s' % (
                    ResourceUnitBase.ASSESSMENT_TYPE,
                    workflow_key(courses.GRADER_KEY)))))
        reg.add_sub_registry('assessment', 'Assessment Config',
                             registry=course_opts)

        review_opts = reg.add_sub_registry('review_opts', 'Peer review',
            description=services.help_urls.make_learn_more_message(
                messages.ASSESSMENT_DETAILS_DESCRIPTION,
                'course:%s:review_opts' % ResourceUnitBase.ASSESSMENT_TYPE),
            extra_schema_dict_values={'id': 'peer-review-group'})

        if len(courses.ALLOWED_MATCHERS_NAMES) > 1:
            review_opts.add_property(schema_fields.SchemaField(
                workflow_key(courses.MATCHER_KEY), 'Review Matcher', 'string',
                optional=True,
                select_data=courses.ALLOWED_MATCHERS_NAMES.items()))

        review_opts.add_property(schema_fields.SchemaField(
            'review_form', 'Reviewer Feedback Form (JavaScript)', 'text',
            optional=True,
            description=services.help_urls.make_learn_more_message(
                messages.ASSESSMENT_REVIEWER_FEEDBACK_FORM_DESCRIPTION,
                'course:%s:review_form' % ResourceUnitBase.ASSESSMENT_TYPE),
            extra_schema_dict_values={
                'className': 'inputEx-Field review-form'}))
        review_opts.add_property(schema_fields.SchemaField(
            'html_review_form', 'Reviewer Feedback Form', 'html',
            optional=True,
            description=(
                messages.ASSESSMENT_REVIEWER_FEEDBACK_FORM_HTML_DESCRIPTION),
            extra_schema_dict_values={
                'supportCustomTags': tags.CAN_USE_DYNAMIC_TAGS.value,
                'excludedCustomTags': tags.EditorBlacklists.ASSESSMENT_SCOPE,
                'className': 'inputEx-Field html-review-form'}))
        review_opts.add_property(schema_fields.SchemaField(
            workflow_key(courses.REVIEW_DUE_DATE_KEY),
            'Review Due Date', 'datetime', optional=True,
            description=messages.ASSESSMENT_REVIEW_DUE_DATE_FORMAT_DESCRIPTION,
            extra_schema_dict_values={'_type': 'datetime'}))
        review_opts.add_property(schema_fields.SchemaField(
            workflow_key(courses.REVIEW_MIN_COUNT_KEY),
            'Review Min Count', 'integer', optional=True,
            description=messages.ASSESSMENT_REVIEW_MIN_COUNT_DESCRIPTION))
        review_opts.add_property(schema_fields.SchemaField(
            workflow_key(courses.REVIEW_WINDOW_MINS_KEY),
            'Review Window Timeout', 'integer', optional=True,
            description=services.help_urls.make_learn_more_message(
                messages.ASSESSMENT_REVIEW_TIMEOUT_IN_MINUTES,
                workflow_key(courses.REVIEW_WINDOW_MINS_KEY))))
        return reg


    @classmethod
    def get_view_url(cls, rsrc):
        return 'assessment?name=%s' % rsrc.unit_id

    @classmethod
    def get_edit_url(cls, key):
        return 'dashboard?action=edit_assessment&key=%s' % key


class ResourceLink(ResourceUnitBase):

    TYPE = ResourceUnitBase.LINK_TYPE

    TITLE_DESCRIPTION = messages.LINK_TITLE_DESCRIPTION
    DESCRIPTION_DESCRIPTION = messages.LINK_DESCRIPTION_DESCRIPTION
    AVAILABILITY_DESCRIPTION = messages.LINK_AVAILABILITY_DESCRIPTION
    SYLLABUS_VISIBILITY_DESCRIPTION = (
        messages.LINK_SYLLABUS_VISIBILITY_DESCRIPTION)

    @classmethod
    def get_schema(cls, course, key):
        schema = cls._generate_common_schema('Link')
        LabelGroupsHelper.add_labels_schema_fields(schema, 'link')
        schema.add_property(schema_fields.SchemaField(
            'url', 'URL', 'string', description=messages.LINK_URL_DESCRIPTION,
            extra_schema_dict_values={'_type': 'url', 'showMsg': True}))
        return schema

    @classmethod
    def get_view_url(cls, rsrc):
        return rsrc.href

    @classmethod
    def get_edit_url(cls, key):
        return 'dashboard?action=edit_link&key=%s' % key


class ResourceLesson(resource.AbstractResourceHandler):

    TYPE = 'lesson'

    @classmethod
    def get_key(cls, lesson):
        return resource.Key(cls.TYPE, lesson.lesson_id)

    @classmethod
    def get_resource(cls, course, key):
        lesson = course.find_lesson_by_id(None, key)
        unit = course.get_unit_for_lesson(lesson)
        return (unit, lesson)

    @classmethod
    def get_resource_title(cls, rsrc):
        return rsrc[1].title

    @classmethod
    def get_schema(cls, course, key):
        units = course.get_units()

        # Note GcbRte relies on the structure of this schema. Do not change
        # without checking the dependency.
        lesson_element = course.find_lesson_by_id(None, key)
        has_video_id = bool(lesson_element and lesson_element.video)

        lesson = schema_fields.FieldRegistry(
            'Lesson', description='Lesson', extra_schema_dict_values={
                'className': 'inputEx-Group new-form-layout'})
        lesson.add_property(schema_fields.SchemaField(
            'key', 'ID', 'string', editable=False,
            extra_schema_dict_values={'className': 'inputEx-Field keyHolder'},
            hidden=True))
        lesson.add_property(schema_fields.SchemaField(
            'title', 'Title', 'string', extra_schema_dict_values={
                'className': 'inputEx-Field content-holder'},
            description=messages.LESSON_TITLE_DESCRIPTION))
        lesson.add_property(create_select_array_schema(
            'unit_id', 'Contained in Unit',
            messages.LESSON_PARENT_UNIT_DESCRIPTION))

        lesson.add_property(schema_fields.SchemaField(
            'video', 'Video ID', 'string', hidden=not has_video_id,
            optional=True, description=messages.LESSON_VIDEO_ID_DESCRIPTION))
        lesson.add_property(schema_fields.SchemaField(
            'scored', 'Question Scoring', 'string', optional=True, i18n=False,
            description=messages.LESSON_SCORED_DESCRIPTION,
            select_data=[
                ('scored', 'Questions are scored'),
                ('not_scored', 'Questions only give feedback')]))
        lesson.add_property(schema_fields.SchemaField(
            'objectives', 'Lesson Body', 'html', optional=True,
            extra_schema_dict_values={
                'className': 'content-holder',
                'supportCustomTags': tags.CAN_USE_DYNAMIC_TAGS.value}))
        lesson.add_property(schema_fields.SchemaField(
            'notes', 'Text Version URL', 'string', optional=True,
            description=messages.LESSON_TEXT_VERSION_URL_DESCRIPTION,
            extra_schema_dict_values={'_type': 'url', 'showMsg': True}))
        lesson.add_property(schema_fields.SchemaField(
            'auto_index', 'Auto-Number', 'boolean',
            description=messages.LESSON_AUTO_NUMBER_DESCRIPTION, optional=True))
        lesson.add_property(schema_fields.SchemaField(
            'activity_title', 'Activity Title', 'string', optional=True,
            description=messages.LESSON_ACTIVITY_TITLE_DESCRIPTION))
        lesson.add_property(schema_fields.SchemaField(
            'activity_listed', 'Activity Listed', 'boolean', optional=True,
            description=messages.LESSON_ACTIVITY_LISTED_DESCRIPTION))
        lesson.add_property(schema_fields.SchemaField(
            'activity', 'Activity', 'text', optional=True,
            description=services.help_urls.make_learn_more_message(
                messages.LESSON_ACTIVITY_DESCRIPTION,
                'course:lesson:activity'),
            extra_schema_dict_values={
                'className': 'inputEx-Field activityHolder'}))
        lesson.add_property(schema_fields.SchemaField(
            'manual_progress', 'Require Manual Completion', 'boolean',
            description=services.help_urls.make_learn_more_message(
                messages.LESSON_REQUIRE_MANUAL_COMPLETION_DESCRIPTION,
                'course:lesson:manual_progress'),
            optional=True))
        return lesson

    @classmethod
    def get_data_dict(cls, course, key):
        lesson = course.find_lesson_by_id(None, key)
        fs = course.app_context.fs
        path = fs.impl.physical_to_logical(course.get_activity_filename(
            lesson.unit_id, lesson.lesson_id))
        if lesson.has_activity and fs.isfile(path):
            activity = fs.get(path)
        else:
            activity = ''

        units = course.get_units()
        unit_list = []
        for unit in units:
            if unit.type == 'U':
                unit_list.append({
                    'value': str(unit.unit_id),
                    'label': cgi.escape(
                        display_unit_title(unit, course.app_context)),
                    'selected': str(lesson.unit_id) == str(unit.unit_id),
                    })

        lesson_dict = {
            'key': lesson.lesson_id,
            'title': lesson.title,
            'unit_id': unit_list,
            'scored': 'scored' if lesson.scored else 'not_scored',
            'objectives': lesson.objectives,
            'video': lesson.video,
            'notes': lesson.notes,
            'auto_index': lesson.auto_index,
            'activity_title': lesson.activity_title,
            'activity_listed': lesson.activity_listed,
            'activity': activity,
            'manual_progress': lesson.manual_progress or False,
            }
        return lesson_dict

    @classmethod
    def get_view_url(cls, rsrc):
        return 'unit?unit=%s&lesson=%s' % (rsrc[0].unit_id, rsrc[1].lesson_id)

    @classmethod
    def get_edit_url(cls, key):
        return 'dashboard?action=edit_lesson&key=%s' % key


def get_unit_title_template(app_context):
    """Prepare an internationalized display for the unit title."""
    course_properties = app_context.get_environ()
    if course_properties['course'].get('display_unit_title_without_index'):
        return '%(title)s'
    else:
        # I18N: Message displayed as title for unit within a course.
        # Note that the items %(index) and %(title).  The %(index)
        # will be replaced with a number indicating the unit's
        # sequence I18N: number within the course, and the %(title)
        # with the unit's title.
        return app_context.gettext('Unit %(index)s - %(title)s',
                                   log_exception=False)


def display_unit_title(unit, app_context):
    """Prepare an internationalized display for the unit title."""
    course_properties = app_context.get_environ()
    template = get_unit_title_template(app_context)
    return template % {'index': unit.index, 'title': unit.title}


def display_short_unit_title(unit, app_context):
    """Prepare a short unit title."""
    course_properties = app_context.get_environ()
    if course_properties['course'].get('display_unit_title_without_index'):
        return unit.title
    if unit.type != 'U':
        return unit.title
    # I18N: Message displayed as title for unit within a course.  The
    # "%s" will be replaced with the index number of the unit within
    # the course.  E.g., "Unit 1", "Unit 2" and so on.
    unit_title = app_context.gettext('Unit %s', log_exception=False)
    return unit_title % unit.index


def display_lesson_title(unit, lesson, app_context):
    """Prepare an internationalized display for the unit title."""

    course_properties = app_context.get_environ()
    content = safe_dom.NodeList()
    span = safe_dom.Element('span')
    content.append(span)

    if lesson.auto_index:
        prefix = ''
        if course_properties['course'].get('display_unit_title_without_index'):
            prefix = '%s ' % lesson.index
        else:
            prefix = '%s.%s ' % (unit.index, lesson.index)
        span.add_text(prefix)
        _class = ''
    else:
        _class = 'no-index'

    span.add_text(lesson.title)
    span.set_attribute('className', _class)
    return content


def create_select_array_schema(field_name, field_title, description):
    select_element = schema_fields.FieldRegistry(title=None)
    select_element.add_property(schema_fields.SchemaField(
        'value', 'Value', 'string',
        editable=False, hidden=True, i18n=False))
    select_element.add_property(schema_fields.SchemaField(
        'label', 'Label', 'string',
        i18n=False, editable=False))
    select_element.add_property(schema_fields.SchemaField(
        'selected', 'Selected', 'boolean', default_value=False,
        i18n=False, editable=False))
    return schema_fields.FieldArray(
        field_name, field_title, description=description,
        item_type=select_element, optional=True,
        extra_schema_dict_values={'_type': 'array-select'})
