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
from tools import verify

DRAFT_TEXT = 'Private'
PUBLISHED_TEXT = 'Public'

SHOWN_WHEN_UNAVAILABLE_TEXT = 'Shown When Private'
HIDDEN_WHEN_UNAVAILABLE_TEXT = 'Hidden When Private'

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


class ResourceSAQuestion(ResourceQuestionBase):

    TYPE = ResourceQuestionBase.TYPE_SA_QUESTION

    GRADER_TYPES = [
        ('case_insensitive', 'Case insensitive string match'),
        ('regex', 'Regular expression'),
        ('numeric', 'Numeric')]

    @classmethod
    def get_schema(cls, course, key):
        """Get the InputEx schema for the short answer question editor."""
        sa_question = schema_fields.FieldRegistry(
            'Short Answer Question',
            description='short answer question',
            extra_schema_dict_values={'className': 'sa-container'})

        sa_question.add_property(schema_fields.SchemaField(
            'version', '', 'string', optional=True, hidden=True))
        sa_question.add_property(schema_fields.SchemaField(
            'description', 'Description', 'string', optional=True,
            extra_schema_dict_values={'className': 'sa-description'},
            description=messages.QUESTION_DESCRIPTION))
        sa_question.add_property(schema_fields.SchemaField(
            'question', 'Question', 'html', optional=True,
            extra_schema_dict_values={
                'supportCustomTags': tags.CAN_USE_DYNAMIC_TAGS.value,
                'excludedCustomTags': TAGS_EXCLUDED_FROM_QUESTIONS,
                'className': 'sa-question'}))
        sa_question.add_property(schema_fields.SchemaField(
            'hint', 'Hint', 'html', optional=True,
            extra_schema_dict_values={'className': 'sa-hint'}))
        sa_question.add_property(schema_fields.SchemaField(
            'defaultFeedback', 'Feedback', 'html', optional=True,
            extra_schema_dict_values={
                'supportCustomTags': tags.CAN_USE_DYNAMIC_TAGS.value,
                'excludedCustomTags': TAGS_EXCLUDED_FROM_QUESTIONS,
                'className': 'sa-feedback'},
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
            'score', 'Score', 'string',
            description=messages.SHORT_ANSWER_SCORE_DESCRIPTION,
            extra_schema_dict_values={
                'className': 'sa-grader-score',
                'value': '1.0',
            }, i18n=False, optional=True))
        grader_type.add_property(schema_fields.SchemaField(
            'matcher', 'Grading', 'string', optional=True, i18n=False,
            select_data=cls.GRADER_TYPES,
            extra_schema_dict_values={'className': 'sa-grader-score'}))
        grader_type.add_property(schema_fields.SchemaField(
            'response', 'Response', 'string', optional=True,
            extra_schema_dict_values={'className': 'sa-grader-text'}))
        grader_type.add_property(schema_fields.SchemaField(
            'feedback', 'Feedback', 'html', optional=True,
            extra_schema_dict_values={
                'supportCustomTags': tags.CAN_USE_DYNAMIC_TAGS.value,
                'excludedCustomTags': TAGS_EXCLUDED_FROM_QUESTIONS,
                'className': 'sa-grader-feedback'}))

        graders_array = schema_fields.FieldArray(
            'graders', '', item_type=grader_type,
            extra_schema_dict_values={
                'className': 'sa-grader-container',
                'listAddLabel': 'Add an answer',
                'listRemoveLabel': 'Delete this answer'})

        sa_question.add_property(graders_array)

        return sa_question


class ResourceMCQuestion(ResourceQuestionBase):

    TYPE = ResourceQuestionBase.TYPE_MC_QUESTION

    @classmethod
    def get_schema(cls, course, key):
        """Get the InputEx schema for the multiple choice question editor."""
        mc_question = schema_fields.FieldRegistry(
            'Multiple Choice Question',
            description='multiple choice question',
            extra_schema_dict_values={'className': 'mc-container'})

        mc_question.add_property(schema_fields.SchemaField(
            'description', 'Description', 'string', optional=True,
            extra_schema_dict_values={'className': 'mc-description'},
            description=messages.QUESTION_DESCRIPTION))
        mc_question.add_property(schema_fields.SchemaField(
            'version', '', 'string', optional=True, hidden=True))
        mc_question.add_property(schema_fields.SchemaField(
            'question', 'Question', 'html', optional=True,
            extra_schema_dict_values={
                'supportCustomTags': tags.CAN_USE_DYNAMIC_TAGS.value,
                'excludedCustomTags': TAGS_EXCLUDED_FROM_QUESTIONS,
                'className': 'mc-question'}))
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
            extra_schema_dict_values={
                'supportCustomTags': tags.CAN_USE_DYNAMIC_TAGS.value,
                'excludedCustomTags': TAGS_EXCLUDED_FROM_QUESTIONS,
                'className': 'mc-choice-text'}))
        choice_type.add_property(schema_fields.SchemaField(
            'feedback', 'Feedback', 'html', optional=True,
            extra_schema_dict_values={
                'supportCustomTags': tags.CAN_USE_DYNAMIC_TAGS.value,
                'excludedCustomTags': TAGS_EXCLUDED_FROM_QUESTIONS,
                'className': 'mc-choice-feedback'}))

        choices_array = schema_fields.FieldArray(
            'choices', '', item_type=choice_type,
            extra_schema_dict_values={
                'className': 'mc-choice-container',
                'listAddLabel': 'Add a choice',
                'listRemoveLabel': 'Delete choice'})

        mc_question.add_property(choices_array)

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
            'items', '', item_type=item_type,
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

    SETTING_TO_ACTION = {
        'assessment': 'settings_unit',
        'invitation': 'settings_registration',
    }

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
        action = cls.SETTING_TO_ACTION.get(key, 'settings_{}'.format(key))
        return 'dashboard?action={}'.format(action)


def workflow_key(key):
    return 'workflow:%s' % key


class LabelGroupsHelper(object):
    """Various methods that make it easier to attach labels to objects."""

    @classmethod
    def make_labels_group_schema_field(cls):
        label = schema_fields.FieldRegistry(None, description='label')
        label.add_property(schema_fields.SchemaField(
            'id', 'ID', 'integer',
            hidden=True,
            editable=False))
        label.add_property(schema_fields.SchemaField(
            'checked', None, 'boolean'))
        label.add_property(schema_fields.SchemaField(
            'title', None, 'string',
            optional=True,
            editable=False))
        label.add_property(schema_fields.SchemaField(
            'description', None, 'string',
            optional=True,
            editable=False,
            extra_schema_dict_values={
                'className': 'label-description'}))
        label.add_property(schema_fields.SchemaField(
            'no_labels', None, 'string',
            optional=True,
            editable=False,
            extra_schema_dict_values={
                'className': 'label-none-in-group'}))

        label_group = schema_fields.FieldRegistry(
            '', description='label groups')
        label_group.add_property(schema_fields.SchemaField(
            'title', None, 'string',
            editable=False))
        label_group.add_property(schema_fields.FieldArray(
            'labels', None,
            item_type=label,
            extra_schema_dict_values={
                'className': 'label-group'}))
        return label_group

    @classmethod
    def decode_labels_group(cls, label_groups):
        """Decodes label_group JSON."""
        labels = set()
        for label_group in label_groups:
            for label in label_group['labels']:
                if label['checked'] and label['id'] > 0:
                    labels.add(label['id'])
        return labels

    @classmethod
    def announcement_labels_to_dict(cls, announcement):
        return cls._all_labels_to_dict(
            common_utils.text_to_list(announcement.labels))

    @classmethod
    def unit_labels_to_dict(cls, course, unit):
        parent_unit = course.get_parent_unit(unit.unit_id)
        labels = common_utils.text_to_list(unit.labels)

        def should_skip(label_type):
            return (
                parent_unit and
                label_type.type == models.LabelDTO.LABEL_TYPE_COURSE_TRACK)

        return cls._all_labels_to_dict(labels, should_skip=should_skip)

    @classmethod
    def _all_labels_to_dict(cls, labels, should_skip=None):
        all_labels = models.LabelDAO.get_all()
        label_groups = []
        for label_type in sorted(models.LabelDTO.LABEL_TYPES,
                                 lambda a, b: cmp(a.menu_order, b.menu_order)):
            if should_skip is not None and should_skip(label_type):
                continue
            label_group = []
            for label in sorted(all_labels, lambda a, b: cmp(a.title, b.title)):
                if label.type == label_type.type:
                    label_group.append({
                        'id': label.id,
                        'title': label.title,
                        'description': label.description,
                        'checked': str(label.id) in labels,
                        'no_labels': '',
                        })
            if not label_group:
                label_group.append({
                    'id': -1,
                    'title': '',
                    'description': '',
                    'checked': False,
                    'no_labels': '-- No labels of this type --',
                    })
            label_groups.append({
                'title': label_type.title,
                'labels': label_group,
                })
        return label_groups


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
        unit.title = updated_unit_dict.get('title')
        unit.description = updated_unit_dict.get('description')
        unit.now_available = not updated_unit_dict.get('is_draft')
        unit.shown_when_unavailable = updated_unit_dict.get(
            'shown_when_unavailable')

        labels = LabelGroupsHelper.decode_labels_group(
            updated_unit_dict['label_groups'])

        if self._course.get_parent_unit(unit.unit_id):
            track_label_ids = models.LabelDAO.get_set_of_ids_of_type(
                models.LabelDTO.LABEL_TYPE_COURSE_TRACK)
            if track_label_ids.intersection(labels):
                errors.append('Cannot set track labels on entities which '
                              'are used within other units.')

        unit.labels = common_utils.list_to_text(labels)

    def _apply_updates_to_assessment(self, unit, updated_unit_dict, errors):
        """Store the updated assessment."""

        entity_dict = {}
        ResourceAssessment.get_schema(None, None).convert_json_to_entity(
            updated_unit_dict, entity_dict)

        self._apply_updates_common(unit, entity_dict, errors)
        try:
            unit.weight = float(entity_dict.get('weight'))
            if unit.weight < 0:
                errors.append('The weight must be a non-negative integer.')
        except ValueError:
            errors.append('The weight must be an integer.')
        content = entity_dict.get('content')
        if content:
            self._course.set_assessment_content(
                unit, entity_dict.get('content'), errors=errors)

        unit.html_content = entity_dict.get('html_content')
        unit.html_check_answers = entity_dict.get('html_check_answers')

        workflow_dict = entity_dict.get('workflow')
        if len(courses.ALLOWED_MATCHERS_NAMES) == 1:
            workflow_dict[courses.MATCHER_KEY] = (
                courses.ALLOWED_MATCHERS_NAMES.keys()[0])
        unit.workflow_yaml = yaml.safe_dump(workflow_dict)
        unit.workflow.validate(errors=errors)

        # Only save the review form if the assessment needs human grading.
        if not errors:
            if self._course.needs_human_grader(unit):
                review_form = entity_dict.get('review_form')
                if review_form:
                    self._course.set_review_form(
                        unit, review_form, errors=errors)
                unit.html_review_form = entity_dict.get('html_review_form')
            elif entity_dict.get('review_form'):
                errors.append(
                    'Review forms for auto-graded assessments should be empty.')

    def _apply_updates_to_link(self, unit, updated_unit_dict, errors):
        self._apply_updates_common(unit, updated_unit_dict, errors)
        unit.href = updated_unit_dict.get('url')

    def _is_assessment_unused(self, unit, assessment, errors):
        parent_unit = self._course.get_parent_unit(assessment.unit_id)
        if parent_unit and parent_unit.unit_id != unit.unit_id:
            errors.append(
                'Assessment "%s" is already asssociated to unit "%s"' % (
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
        unit.unit_header = updated_unit_dict['unit_header']
        unit.unit_footer = updated_unit_dict['unit_footer']
        unit.pre_assessment = None
        unit.post_assessment = None
        unit.manual_progress = updated_unit_dict['manual_progress']
        pre_assessment_id = updated_unit_dict['pre_assessment']
        if pre_assessment_id >= 0:
            assessment = self._course.find_unit_by_id(pre_assessment_id)
            if (self._is_assessment_unused(unit, assessment, errors) and
                self._is_assessment_version_ok(assessment, errors) and
                not self._is_assessment_on_track(assessment, errors)):
                unit.pre_assessment = pre_assessment_id

        post_assessment_id = updated_unit_dict['post_assessment']
        if post_assessment_id >= 0 and pre_assessment_id == post_assessment_id:
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
        return {
            'key': unit.unit_id,
            'type': verify.UNIT_TYPE_NAMES[unit.type],
            'title': unit.title,
            'description': unit.description or '',
            'is_draft': not unit.now_available,
            'shown_when_unavailable': unit.shown_when_unavailable,
            'label_groups': LabelGroupsHelper.unit_labels_to_dict(
                self._course, unit)}

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
            submission_due_date = workflow.get_submission_due_date().strftime(
                courses.ISO_8601_DATE_FORMAT)
        else:
            submission_due_date = ''

        if workflow.get_review_due_date():
            review_due_date = workflow.get_review_due_date().strftime(
                courses.ISO_8601_DATE_FORMAT)
        else:
            review_due_date = ''

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
            workflow_key(courses.SUBMISSION_DUE_DATE_KEY): (
                submission_due_date),
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
    def _generate_common_schema(cls, title, hidden_header=False):
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
            'title', 'Title', 'string', optional=True))
        ret.add_property(schema_fields.SchemaField(
            'description', 'Description', 'string',
            description=str(messages.UNIT_DESCRIPTION_DESCRIPTION),
            optional=True))
        ret.add_property(schema_fields.FieldArray(
            'label_groups', 'Labels',
            item_type=LabelGroupsHelper.make_labels_group_schema_field(),
            extra_schema_dict_values={
                'className': 'inputEx-Field label-group-list'}))
        ret.add_property(schema_fields.SchemaField(
            'is_draft', 'Status', 'boolean',
            select_data=[(True, DRAFT_TEXT),
                         (False, PUBLISHED_TEXT)],
            extra_schema_dict_values={
                'className': 'split-from-main-group'}))
        ret.add_property(schema_fields.SchemaField(
            'shown_when_unavailable', 'Syllabus Visibility', 'boolean',
            optional=True,
            select_data=[(True, SHOWN_WHEN_UNAVAILABLE_TEXT),
                         (False, HIDDEN_WHEN_UNAVAILABLE_TEXT)],
            description='When a unit is marked as %s, ' % DRAFT_TEXT +
            'this setting controls whether the title is still shown '
            'to students on the syllabus overview page when this item '
            'is marked as private.',
            extra_schema_dict_values={
                'className': 'split-from-main-group'}))
        return ret


class ResourceUnit(ResourceUnitBase):

    TYPE = ResourceUnitBase.UNIT_TYPE

    @classmethod
    def get_schema(cls, course, key):
        schema = cls._generate_common_schema('Unit')
        schema.add_property(schema_fields.SchemaField(
            'pre_assessment', 'Pre Assessment', 'integer', optional=True))
        schema.add_property(schema_fields.SchemaField(
            'post_assessment', 'Post Assessment', 'integer', optional=True))
        schema.add_property(schema_fields.SchemaField(
            'show_contents_on_one_page', 'Show Contents on One Page', 'boolean',
            optional=True,
            description='Whether to show all assessments, lessons, '
            'and activities in a Unit on one page, or to show each on '
            'its own page.'))
        schema.add_property(schema_fields.SchemaField(
            'manual_progress', 'Manual Progress', 'boolean', optional=True,
            description='When set, the manual progress REST API permits '
            'users to manually mark a unit or lesson as complete, '
            'overriding the automatic progress tracking.'))
        schema.add_property(schema_fields.SchemaField(
            'unit_header', 'Unit Header', 'html', optional=True,
            extra_schema_dict_values={
                'supportCustomTags': tags.CAN_USE_DYNAMIC_TAGS.value,
                'excludedCustomTags': tags.EditorBlacklists.DESCRIPTIVE_SCOPE,
                'className': 'inputEx-Field html-content cb-editor-small'}))
        schema.add_property(schema_fields.SchemaField(
            'unit_footer', 'Unit Footer', 'html', optional=True,
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

    @classmethod
    def get_schema(cls, course, key):
        reg = schema_fields.FieldRegistry('Assessment',
            extra_schema_dict_values={
                'className': 'inputEx-Group new-form-layout'})

        # Course level settings.
        course_opts = cls._generate_common_schema(
            'Assessment Config', hidden_header=True)
        course_opts.add_property(schema_fields.SchemaField(
            'weight', 'Weight', 'number',
            description=str(messages.ASSESSMENT_WEIGHT_DESCRIPTION),
            i18n=False, optional=True))
        course_opts.add_property(schema_fields.SchemaField(
            'content', 'Assessment Content (JavaScript)', 'text', optional=True,
            description=str(messages.ASSESSMENT_CONTENT_DESCRIPTION),
            extra_schema_dict_values={'className': 'inputEx-Field content'}))
        course_opts.add_property(schema_fields.SchemaField(
            'html_content', 'Assessment Content', 'html', optional=True,
            extra_schema_dict_values={
                'supportCustomTags': tags.CAN_USE_DYNAMIC_TAGS.value,
                'excludedCustomTags': tags.EditorBlacklists.ASSESSMENT_SCOPE,
                'className': 'inputEx-Field html-content'}))
        course_opts.add_property(schema_fields.SchemaField(
            'html_check_answers', '"Check Answers" Buttons', 'boolean',
            description=str(messages.CHECK_ANSWERS_DESCRIPTION),
            extra_schema_dict_values={
                'className': 'inputEx-Field assessment-editor-check-answers'},
            optional=True))
        course_opts.add_property(schema_fields.SchemaField(
            workflow_key(courses.SUBMISSION_DUE_DATE_KEY),
            'Submission Due Date', 'string', optional=True,
            description=str(messages.DUE_DATE_FORMAT_DESCRIPTION)))
        course_opts.add_property(schema_fields.SchemaField(
            workflow_key(courses.GRADER_KEY), 'Grading Method', 'string',
            select_data=ALLOWED_GRADERS_NAMES.items()))
        reg.add_sub_registry('assessment', 'Assessment Config',
                             registry=course_opts)

        review_opts = reg.add_sub_registry('review_opts', 'Peer review',
            description=str(messages.ASSESSMENT_DETAILS_DESCRIPTION),
            extra_schema_dict_values={'id': 'peer-review-group'})

        if len(courses.ALLOWED_MATCHERS_NAMES) > 1:
            review_opts.add_property(schema_fields.SchemaField(
                workflow_key(courses.MATCHER_KEY), 'Review Matcher', 'string',
                optional=True,
                select_data=courses.ALLOWED_MATCHERS_NAMES.items()))

        review_opts.add_property(schema_fields.SchemaField(
            'review_form', 'Reviewer Feedback Form (JavaScript)', 'text',
            optional=True,
            description=str(messages.REVIEWER_FEEDBACK_FORM_DESCRIPTION),
            extra_schema_dict_values={
                'className': 'inputEx-Field review-form'}))
        review_opts.add_property(schema_fields.SchemaField(
            'html_review_form', 'Reviewer Feedback Form', 'html',
            optional=True,
            description=str(messages.REVIEWER_FEEDBACK_FORM_HTML_DESCRIPTION),
            extra_schema_dict_values={
                'supportCustomTags': tags.CAN_USE_DYNAMIC_TAGS.value,
                'excludedCustomTags': tags.EditorBlacklists.ASSESSMENT_SCOPE,
                'className': 'inputEx-Field html-review-form'}))
        review_opts.add_property(schema_fields.SchemaField(
            workflow_key(courses.REVIEW_DUE_DATE_KEY),
            'Review Due Date', 'string', optional=True,
            description=str(messages.REVIEW_DUE_DATE_FORMAT_DESCRIPTION)))
        review_opts.add_property(schema_fields.SchemaField(
            workflow_key(courses.REVIEW_MIN_COUNT_KEY),
            'Review Min Count', 'integer', optional=True,
            description=str(messages.REVIEW_MIN_COUNT_DESCRIPTION)))
        review_opts.add_property(schema_fields.SchemaField(
            workflow_key(courses.REVIEW_WINDOW_MINS_KEY),
            'Review Window Timeout', 'integer', optional=True,
            description=str(messages.REVIEW_TIMEOUT_IN_MINUTES)))
        return reg


    @classmethod
    def get_view_url(cls, rsrc):
        return 'assessment?name=%s' % rsrc.unit_id

    @classmethod
    def get_edit_url(cls, key):
        return 'dashboard?action=edit_assessment&key=%s' % key


class ResourceLink(ResourceUnitBase):

    TYPE = ResourceUnitBase.LINK_TYPE

    @classmethod
    def get_schema(cls, course, key):
        schema = cls._generate_common_schema('Link')
        schema.add_property(schema_fields.SchemaField(
            'url', 'URL', 'string', optional=True,
            description=messages.LINK_EDITOR_URL_DESCRIPTION))
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
        unit_list = []
        for unit in units:
            if unit.type == 'U':
                unit_list.append(
                    (unit.unit_id,
                     cgi.escape(display_unit_title(unit, course.app_context))))

        lesson_data = cls.get_data_dict(course, key)
        has_video_id = bool(lesson_data.get('video'))

        lesson = schema_fields.FieldRegistry(
            'Lesson', description='Lesson', extra_schema_dict_values={
                'className': 'inputEx-Group new-form-layout'})
        lesson.add_property(schema_fields.SchemaField(
            'key', 'ID', 'string', editable=False,
            extra_schema_dict_values={'className': 'inputEx-Field keyHolder'},
            hidden=True))
        lesson.add_property(schema_fields.SchemaField(
            'title', 'Title', 'string', extra_schema_dict_values={
                'className': 'inputEx-Field title-holder'}))
        lesson.add_property(schema_fields.SchemaField(
            'unit_id', 'Parent Unit', 'string', i18n=False,
            select_data=unit_list))
        lesson.add_property(schema_fields.SchemaField(
            'video', 'Video ID', 'string', hidden=not has_video_id,
            optional=True, description=messages.LESSON_VIDEO_ID_DESCRIPTION))
        lesson.add_property(schema_fields.SchemaField(
            'scored', 'Scored', 'string', optional=True, i18n=False,
            description=messages.LESSON_SCORED_DESCRIPTION,
            select_data=[
                ('scored', 'Questions are scored'),
                ('not_scored', 'Questions only give feedback')]))
        lesson.add_property(schema_fields.SchemaField(
            'objectives', 'Lesson Body', 'html', optional=True,
            description=messages.LESSON_OBJECTIVES_DESCRIPTION,
            extra_schema_dict_values={
                'supportCustomTags': tags.CAN_USE_DYNAMIC_TAGS.value}))
        lesson.add_property(schema_fields.SchemaField(
            'notes', 'Notes', 'string', optional=True,
            description=messages.LESSON_NOTES_DESCRIPTION))
        lesson.add_property(schema_fields.SchemaField(
            'auto_index', 'Auto Number', 'boolean',
            description=messages.LESSON_AUTO_INDEX_DESCRIPTION))
        lesson.add_property(schema_fields.SchemaField(
            'activity_title', 'Activity Title', 'string', optional=True,
            description=messages.LESSON_ACTIVITY_TITLE_DESCRIPTION))
        lesson.add_property(schema_fields.SchemaField(
            'activity_listed', 'Activity Listed', 'boolean', optional=True,
            description=messages.LESSON_ACTIVITY_LISTED_DESCRIPTION))
        lesson.add_property(schema_fields.SchemaField(
            'activity', 'Activity', 'text', optional=True,
            description=str(messages.LESSON_ACTIVITY_DESCRIPTION),
            extra_schema_dict_values={
                'className': 'inputEx-Field activityHolder'}))
        lesson.add_property(schema_fields.SchemaField(
            'manual_progress', 'Manual Progress', 'boolean', optional=True,
            description=messages.LESSON_MANUAL_PROGRESS_DESCRIPTION))
        lesson.add_property(schema_fields.SchemaField(
            'is_draft', 'Status', 'boolean',
            select_data=[(True, DRAFT_TEXT), (False, PUBLISHED_TEXT)],
            extra_schema_dict_values={
                'className': 'split-from-main-group'}))
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

        lesson_dict = {
            'key': lesson.lesson_id,
            'title': lesson.title,
            'unit_id': lesson.unit_id,
            'scored': 'scored' if lesson.scored else 'not_scored',
            'objectives': lesson.objectives,
            'video': lesson.video,
            'notes': lesson.notes,
            'auto_index': lesson.auto_index,
            'activity_title': lesson.activity_title,
            'activity_listed': lesson.activity_listed,
            'activity': activity,
            'manual_progress': lesson.manual_progress or False,
            'is_draft': not lesson.now_available
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
        return app_context.gettext('Unit %(index)s - %(title)s')


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
    unit_title = app_context.gettext('Unit %s')
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
