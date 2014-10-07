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

"""Classes supporting unit and lesson editing."""

__author__ = 'John Orr (jorr@google.com)'

import cgi
import logging
import urllib
from label_editor import LabelGroupsHelper
import messages
import yaml

from common import tags
from common import utils as common_utils
from common.schema_fields import FieldArray
from common.schema_fields import FieldRegistry
from common.schema_fields import SchemaField
from controllers import sites
from controllers import utils
from controllers.utils import ApplicationHandler
from controllers.utils import BaseRESTHandler
from controllers.utils import XsrfTokenManager
from models import courses
from models import messages as m_messages
from models import models as m_models
from models import review
from models import roles
from models import transforms
from modules.oeditor import oeditor
from tools import verify


DRAFT_TEXT = 'Private'
PUBLISHED_TEXT = 'Public'


# The editor has severe limitations for editing nested lists of objects. First,
# it does not allow one to move a lesson from one unit to another. We need a way
# of doing that. Second, JSON schema specification does not seem to support a
# type-safe array, which has objects of different types. We also want that
# badly :). All in all - using generic schema-based object editor for editing
# nested arrayable polymorphic attributes is a pain...


STATUS_ANNOTATION = oeditor.create_bool_select_annotation(
    ['properties', 'is_draft'], 'Status', DRAFT_TEXT,
    PUBLISHED_TEXT, class_name='split-from-main-group')


def generate_common_schema(title):
    common = FieldRegistry(title)
    common.add_property(SchemaField(
        'key', 'ID', 'string', editable=False,
        extra_schema_dict_values={'className': 'inputEx-Field keyHolder'}))
    common.add_property(
        SchemaField('type', 'Type', 'string', editable=False))
    common.add_property(
        SchemaField('title', 'Title', 'string', optional=True))
    common.add_property(
        SchemaField('description', 'Description', 'string', optional=True))
    common.add_property(
        FieldArray('label_groups', 'Labels',
                   item_type=LabelGroupsHelper.make_labels_group_schema_field(),
                   extra_schema_dict_values={
                       'className': 'inputEx-Field label-group-list'}))
    common.add_property(SchemaField('is_draft', 'Status', 'boolean',
                                    select_data=[(True, DRAFT_TEXT),
                                                 (False, PUBLISHED_TEXT)],
                                    extra_schema_dict_values={
                                        'className': 'split-from-main-group'}))
    return common


# Allowed matchers. Keys of this dict represent internal keys for the matcher
# type, and the value represents the corresponding string that will appear in
# the dashboard UI.
ALLOWED_MATCHERS_NAMES = {
    review.PEER_MATCHER: m_messages.PEER_MATCHER_NAME}


# Allowed graders. Keys of this dict represent internal keys for the grader
# type, and the value represents the corresponding string that will appear in
# the dashboard UI.
ALLOWED_GRADERS_NAMES = {
    courses.AUTO_GRADER: messages.AUTO_GRADER_NAME,
    courses.HUMAN_GRADER: messages.HUMAN_GRADER_NAME,
    }


class CourseOutlineRights(object):
    """Manages view/edit rights for course outline."""

    @classmethod
    def can_view(cls, handler):
        return cls.can_edit(handler)

    @classmethod
    def can_edit(cls, handler):
        return roles.Roles.is_course_admin(handler.app_context)

    @classmethod
    def can_delete(cls, handler):
        return cls.can_edit(handler)

    @classmethod
    def can_add(cls, handler):
        return cls.can_edit(handler)


class UnitLessonEditor(ApplicationHandler):
    """An editor for the unit and lesson titles."""

    HIDE_ACTIVITY_ANNOTATIONS = [
        (['properties', 'activity_title', '_inputex'], {'_type': 'hidden'}),
        (['properties', 'activity_listed', '_inputex'], {'_type': 'hidden'}),
        (['properties', 'activity', '_inputex'], {'_type': 'hidden'}),
    ]

    def get_import_course(self):
        """Shows setup form for course import."""

        template_values = {}
        template_values['page_title'] = self.format_title('Import Course')
        annotations = ImportCourseRESTHandler.SCHEMA_ANNOTATIONS_DICT()
        if not annotations:
            template_values['main_content'] = 'No courses to import from.'
            self.render_page(template_values)
            return

        exit_url = self.canonicalize_url('/dashboard')
        rest_url = self.canonicalize_url(ImportCourseRESTHandler.URI)
        form_html = oeditor.ObjectEditor.get_html_for(
            self,
            ImportCourseRESTHandler.SCHEMA_JSON,
            annotations,
            None, rest_url, exit_url,
            auto_return=True,
            save_button_caption='Import',
            required_modules=ImportCourseRESTHandler.REQUIRED_MODULES)

        template_values = {}
        template_values['page_title'] = self.format_title('Import Course')
        template_values['page_description'] = messages.IMPORT_COURSE_DESCRIPTION
        template_values['main_content'] = form_html
        self.render_page(template_values)

    def get_edit_unit_lesson(self):
        """Shows editor for the list of unit and lesson titles."""

        key = self.request.get('key')

        exit_url = self.canonicalize_url('/dashboard')
        rest_url = self.canonicalize_url(UnitLessonTitleRESTHandler.URI)
        form_html = oeditor.ObjectEditor.get_html_for(
            self,
            UnitLessonTitleRESTHandler.SCHEMA_JSON,
            UnitLessonTitleRESTHandler.SCHEMA_ANNOTATIONS_DICT,
            key, rest_url, exit_url,
            required_modules=UnitLessonTitleRESTHandler.REQUIRED_MODULES)

        template_values = {}
        template_values['page_title'] = self.format_title('Edit Course Outline')
        template_values[
            'page_description'] = messages.COURSE_OUTLINE_EDITOR_DESCRIPTION
        template_values['main_content'] = form_html
        self.render_page(template_values)

    def post_add_lesson(self):
        """Adds new lesson to a first unit of the course."""
        course = courses.Course(self)
        first_unit = None
        for unit in course.get_units():
            if unit.type == verify.UNIT_TYPE_UNIT:
                first_unit = unit
                break
        if first_unit:
            lesson = course.add_lesson(first_unit)
            course.save()
            # TODO(psimakov): complete 'edit_lesson' view
            self.redirect(self.get_action_url(
                'edit_lesson', key=lesson.lesson_id,
                extra_args={'is_newly_created': 1}))
        else:
            self.redirect('/dashboard')

    def post_add_unit(self):
        """Adds new unit to a course."""
        course = courses.Course(self)
        unit = course.add_unit()
        course.save()
        self.redirect(self.get_action_url(
            'edit_unit', key=unit.unit_id, extra_args={'is_newly_created': 1}))

    def post_add_link(self):
        """Adds new link to a course."""
        course = courses.Course(self)
        link = course.add_link()
        link.href = ''
        course.save()
        self.redirect(self.get_action_url(
            'edit_link', key=link.unit_id, extra_args={'is_newly_created': 1}))

    def post_add_assessment(self):
        """Adds new assessment to a course."""
        course = courses.Course(self)
        assessment = course.add_assessment()
        course.save()
        self.redirect(self.get_action_url(
            'edit_assessment', key=assessment.unit_id,
            extra_args={'is_newly_created': 1}))

    def post_set_draft_status(self):
        """Sets the draft status of a course component.

        Only works with CourseModel13 courses, but the REST handler
        is only called with this type of courses.
        """
        key = self.request.get('key')
        if not CourseOutlineRights.can_edit(self):
            transforms.send_json_response(
                self, 401, 'Access denied.', {'key': key})
            return

        course = courses.Course(self)
        component_type = self.request.get('type')
        if component_type == 'unit':
            course_component = course.find_unit_by_id(key)
        elif component_type == 'lesson':
            course_component = course.find_lesson_by_id(None, key)
        else:
            transforms.send_json_response(
                self, 401, 'Invalid key.', {'key': key})
            return

        set_draft = self.request.get('set_draft')
        if set_draft == '1':
            set_draft = True
        elif set_draft == '0':
            set_draft = False
        else:
            transforms.send_json_response(
                self, 401, 'Invalid set_draft value, expected 0 or 1.',
                {'set_draft': set_draft}
            )
            return

        course_component.now_available = not set_draft
        course.save()

        transforms.send_json_response(
            self,
            200,
            'Draft status set to %s.' % (
                DRAFT_TEXT if set_draft else PUBLISHED_TEXT
            ), {
                'is_draft': set_draft
            }
        )
        return

    def _render_edit_form_for(
        self, rest_handler_cls, title, schema=None, annotations_dict=None,
        delete_xsrf_token='delete-unit', page_description=None,
        extra_js_files=None):
        """Renders an editor form for a given REST handler class."""
        annotations_dict = annotations_dict or []
        if schema:
            schema_json = schema.get_json_schema()
            annotations_dict = schema.get_schema_dict() + annotations_dict
        else:
            schema_json = rest_handler_cls.SCHEMA_JSON
            if not annotations_dict:
                annotations_dict = rest_handler_cls.SCHEMA_ANNOTATIONS_DICT

        key = self.request.get('key')

        extra_args = {}
        if self.request.get('is_newly_created'):
            extra_args['is_newly_created'] = 1

        exit_url = self.canonicalize_url('/dashboard')
        rest_url = self.canonicalize_url(rest_handler_cls.URI)
        delete_url = '%s?%s' % (
            self.canonicalize_url(rest_handler_cls.URI),
            urllib.urlencode({
                'key': key,
                'xsrf_token': cgi.escape(
                    self.create_xsrf_token(delete_xsrf_token))
                }))

        form_html = oeditor.ObjectEditor.get_html_for(
            self,
            schema_json,
            annotations_dict,
            key, rest_url, exit_url,
            extra_args=extra_args,
            delete_url=delete_url, delete_method='delete',
            read_only=not self.app_context.is_editable_fs(),
            required_modules=rest_handler_cls.REQUIRED_MODULES,
            extra_js_files=extra_js_files)

        template_values = {}
        template_values['page_title'] = self.format_title('Edit %s' % title)
        if page_description:
            template_values['page_description'] = page_description
        template_values['main_content'] = form_html
        self.render_page(template_values)

    def get_edit_unit(self):
        """Shows unit editor."""
        self._render_edit_form_for(
            UnitRESTHandler, 'Unit',
            page_description=messages.UNIT_EDITOR_DESCRIPTION,
            annotations_dict=UnitRESTHandler.get_annotations_dict(
                courses.Course(self), int(self.request.get('key'))))

    def get_edit_link(self):
        """Shows link editor."""
        self._render_edit_form_for(
            LinkRESTHandler, 'Link',
            page_description=messages.LINK_EDITOR_DESCRIPTION)

    def get_edit_assessment(self):
        """Shows assessment editor."""
        self._render_edit_form_for(
            AssessmentRESTHandler, 'Assessment',
            page_description=messages.ASSESSMENT_EDITOR_DESCRIPTION,
            extra_js_files=['assessment_editor_lib.js', 'assessment_editor.js'])

    def get_edit_lesson(self):
        """Shows the lesson/activity editor."""
        key = self.request.get('key')
        course = courses.Course(self)
        lesson = course.find_lesson_by_id(None, key)
        annotations_dict = (
            None if lesson.has_activity
            else UnitLessonEditor.HIDE_ACTIVITY_ANNOTATIONS)
        schema = LessonRESTHandler.get_schema(course.get_units())
        if courses.has_only_new_style_activities(self.get_course()):
            schema.get_property('objectives').extra_schema_dict_values[
              'excludedCustomTags'] = set(['gcb-activity'])
        self._render_edit_form_for(
            LessonRESTHandler, 'Lessons and Activities',
            schema=schema,
            annotations_dict=annotations_dict,
            delete_xsrf_token='delete-lesson',
            extra_js_files=None)


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

        labels = LabelGroupsHelper.decode_labels_group(
            updated_unit_dict['label_groups'])

        if self._course.get_parent_unit(unit.unit_id):
            track_label_ids = m_models.LabelDAO.get_set_of_ids_of_type(
                m_models.LabelDTO.LABEL_TYPE_COURSE_TRACK)
            if track_label_ids.intersection(labels):
                errors.append('Cannot set track labels on entities which '
                              'are used within other units.')

        unit.labels = common_utils.list_to_text(labels)

    def _apply_updates_to_assessment(self, unit, updated_unit_dict, errors):
        """Store the updated assessment."""

        entity_dict = {}
        AssessmentRESTHandler.SCHEMA.convert_json_to_entity(
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
        if len(ALLOWED_MATCHERS_NAMES) == 1:
            workflow_dict[courses.MATCHER_KEY] = (
                ALLOWED_MATCHERS_NAMES.keys()[0])
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


class CommonUnitRESTHandler(BaseRESTHandler):
    """A common super class for all unit REST handlers."""

    # These functions are called with an updated unit object whenever a
    # change is saved.
    POST_SAVE_HOOKS = []

    def unit_to_dict(self, unit):
        """Converts a unit to a dictionary representation."""
        return UnitTools(self.get_course()).unit_to_dict(unit)

    def apply_updates(self, unit, updated_unit_dict, errors):
        """Applies changes to a unit; modifies unit input argument."""
        UnitTools(courses.Course(self)).apply_updates(
            unit, updated_unit_dict, errors)

    def get(self):
        """A GET REST method shared by all unit types."""
        key = self.request.get('key')

        if not CourseOutlineRights.can_view(self):
            transforms.send_json_response(
                self, 401, 'Access denied.', {'key': key})
            return

        unit = courses.Course(self).find_unit_by_id(key)
        if not unit:
            transforms.send_json_response(
                self, 404, 'Object not found.', {'key': key})
            return

        message = ['Success.']
        if self.request.get('is_newly_created'):
            unit_type = verify.UNIT_TYPE_NAMES[unit.type].lower()
            message.append(
                'New %s has been created and saved.' % unit_type)

        transforms.send_json_response(
            self, 200, '\n'.join(message),
            payload_dict=self.unit_to_dict(unit),
            xsrf_token=XsrfTokenManager.create_xsrf_token('put-unit'))

    def put(self):
        """A PUT REST method shared by all unit types."""
        request = transforms.loads(self.request.get('request'))
        key = request.get('key')

        if not self.assert_xsrf_token_or_fail(
                request, 'put-unit', {'key': key}):
            return

        if not CourseOutlineRights.can_edit(self):
            transforms.send_json_response(
                self, 401, 'Access denied.', {'key': key})
            return

        unit = courses.Course(self).find_unit_by_id(key)
        if not unit:
            transforms.send_json_response(
                self, 404, 'Object not found.', {'key': key})
            return

        payload = request.get('payload')
        updated_unit_dict = transforms.json_to_dict(
            transforms.loads(payload), self.SCHEMA_DICT)

        errors = []
        self.apply_updates(unit, updated_unit_dict, errors)
        if not errors:
            course = courses.Course(self)
            assert course.update_unit(unit)
            course.save()
            common_utils.run_hooks(self.POST_SAVE_HOOKS, unit)
            transforms.send_json_response(self, 200, 'Saved.')
        else:
            transforms.send_json_response(self, 412, '\n'.join(errors))

    def delete(self):
        """Handles REST DELETE verb with JSON payload."""
        key = self.request.get('key')

        if not self.assert_xsrf_token_or_fail(
                self.request, 'delete-unit', {'key': key}):
            return

        if not CourseOutlineRights.can_delete(self):
            transforms.send_json_response(
                self, 401, 'Access denied.', {'key': key})
            return

        course = courses.Course(self)
        unit = course.find_unit_by_id(key)
        if not unit:
            transforms.send_json_response(
                self, 404, 'Object not found.', {'key': key})
            return

        course.delete_unit(unit)
        course.save()

        transforms.send_json_response(self, 200, 'Deleted.')


def generate_unit_schema():
    schema = generate_common_schema('Unit')
    schema.add_property(SchemaField(
        'unit_header', 'Unit Header', 'html', optional=True,
        extra_schema_dict_values={
            'supportCustomTags': tags.CAN_USE_DYNAMIC_TAGS.value,
            'excludedCustomTags': tags.EditorBlacklists.DESCRIPTIVE_SCOPE,
            'className': 'inputEx-Field html-content'}))
    schema.add_property(SchemaField(
        'pre_assessment', 'Pre Assessment', 'integer', optional=True))
    schema.add_property(SchemaField(
        'post_assessment', 'Post Assessment', 'integer', optional=True))
    schema.add_property(SchemaField(
        'show_contents_on_one_page', 'Show Contents on One Page', 'boolean',
        optional=True,
        description='Whether to show all assessments, lessons, and activities '
        'in a Unit on one page, or to show each on its own page.'))
    schema.add_property(SchemaField(
        'manual_progress', 'Manual Progress', 'boolean', optional=True,
        description='When set, the manual progress REST API permits '
        'users to manually mark a unit or lesson as complete, '
        'overriding the automatic progress tracking.'))
    schema.add_property(SchemaField(
        'unit_footer', 'Unit Footer', 'html', optional=True,
        extra_schema_dict_values={
            'supportCustomTags': tags.CAN_USE_DYNAMIC_TAGS.value,
            'excludedCustomTags': tags.EditorBlacklists.DESCRIPTIVE_SCOPE,
            'className': 'inputEx-Field html-content'}))

    return schema


class UnitRESTHandler(CommonUnitRESTHandler):
    """Provides REST API to unit."""

    URI = '/rest/course/unit'
    SCHEMA = generate_unit_schema()
    SCHEMA_JSON = SCHEMA.get_json_schema()
    SCHEMA_DICT = SCHEMA.get_json_schema_dict()
    REQUIRED_MODULES = [
        'inputex-string', 'inputex-select', 'inputex-uneditable',
        'inputex-list', 'inputex-hidden', 'inputex-number', 'inputex-integer',
        'inputex-checkbox', 'gcb-rte']

    @classmethod
    def get_annotations_dict(cls, course, this_unit_id):
        # The set of available assesments needs to be dynamically
        # generated and set as selection choices on the form.
        # We want to only show assessments that are not already
        # selected by other units.
        available_assessments = {}
        referenced_assessments = {}
        for unit in course.get_units():
            if unit.type == verify.UNIT_TYPE_ASSESSMENT:
                model_version = course.get_assessment_model_version(unit)
                track_labels = course.get_unit_track_labels(unit)
                # Don't allow selecting old-style assessments, which we
                # can't display within Unit page.
                # Don't allow selection of assessments with parents
                if (model_version != courses.ASSESSMENT_MODEL_VERSION_1_4 and
                    not track_labels):
                    available_assessments[unit.unit_id] = unit
            elif (unit.type == verify.UNIT_TYPE_UNIT and
                  this_unit_id != unit.unit_id):
                if unit.pre_assessment:
                    referenced_assessments[unit.pre_assessment] = True
                if unit.post_assessment:
                    referenced_assessments[unit.post_assessment] = True
        for referenced in referenced_assessments:
            if referenced in available_assessments:
                del available_assessments[referenced]

        schema = generate_unit_schema()
        choices = [(-1, '-- None --')]
        for assessment_id in sorted(available_assessments):
            choices.append(
                (assessment_id, available_assessments[assessment_id].title))
        schema.get_property('pre_assessment').set_select_data(choices)
        schema.get_property('post_assessment').set_select_data(choices)

        return schema.get_schema_dict()


def generate_link_schema():
    schema = generate_common_schema('Link')
    schema.add_property(SchemaField(
        'url', 'URL', 'string', optional=True,
        description=messages.LINK_EDITOR_URL_DESCRIPTION))
    return schema


class LinkRESTHandler(CommonUnitRESTHandler):
    """Provides REST API to link."""

    URI = '/rest/course/link'
    SCHEMA = generate_link_schema()
    SCHEMA_JSON = SCHEMA.get_json_schema()
    SCHEMA_DICT = SCHEMA.get_json_schema_dict()
    SCHEMA_ANNOTATIONS_DICT = SCHEMA.get_schema_dict()
    REQUIRED_MODULES = [
        'inputex-string', 'inputex-select', 'inputex-uneditable',
        'inputex-list', 'inputex-hidden', 'inputex-number', 'inputex-checkbox']


class ImportCourseRESTHandler(CommonUnitRESTHandler):
    """Provides REST API to course import."""

    URI = '/rest/course/import'

    SCHEMA_JSON = """
    {
        "id": "Import Course Entity",
        "type": "object",
        "description": "Import Course",
        "properties": {
            "course" : {"type": "string"}
            }
    }
    """

    SCHEMA_DICT = transforms.loads(SCHEMA_JSON)

    REQUIRED_MODULES = [
        'inputex-string', 'inputex-select', 'inputex-uneditable']

    @classmethod
    def _get_course_list(cls):
        # Make a list of courses user has the rights to.
        course_list = []
        for acourse in sites.get_all_courses():
            if not roles.Roles.is_course_admin(acourse):
                continue
            if acourse == sites.get_course_for_current_request():
                continue

            atitle = '%s (%s)' % (acourse.get_title(), acourse.get_slug())

            course_list.append({
                'value': acourse.raw, 'label': cgi.escape(atitle)})
        return course_list

    @classmethod
    def SCHEMA_ANNOTATIONS_DICT(cls):  # pylint: disable-msg=g-bad-name
        """Schema annotations are dynamic and include a list of courses."""
        course_list = cls._get_course_list()
        if not course_list:
            return None

        # Format annotations.
        return [
            (['title'], 'Import Course'),
            (
                ['properties', 'course', '_inputex'],
                {
                    'label': 'Available Courses',
                    '_type': 'select',
                    'choices': course_list})]

    def get(self):
        """Handles REST GET verb and returns an object as JSON payload."""
        if not CourseOutlineRights.can_view(self):
            transforms.send_json_response(self, 401, 'Access denied.', {})
            return

        first_course_in_dropdown = self._get_course_list()[0]['value']

        transforms.send_json_response(
            self, 200, None,
            payload_dict={'course': first_course_in_dropdown},
            xsrf_token=XsrfTokenManager.create_xsrf_token(
                'import-course'))

    def put(self):
        """Handles REST PUT verb with JSON payload."""
        request = transforms.loads(self.request.get('request'))

        if not self.assert_xsrf_token_or_fail(
                request, 'import-course', {'key': None}):
            return

        if not CourseOutlineRights.can_edit(self):
            transforms.send_json_response(self, 401, 'Access denied.', {})
            return

        payload = request.get('payload')
        course_raw = transforms.json_to_dict(
            transforms.loads(payload), self.SCHEMA_DICT)['course']

        source = None
        for acourse in sites.get_all_courses():
            if acourse.raw == course_raw:
                source = acourse
                break

        if not source:
            transforms.send_json_response(
                self, 404, 'Object not found.', {'raw': course_raw})
            return

        course = courses.Course(self)
        errors = []
        try:
            course.import_from(source, errors)
        except Exception as e:  # pylint: disable-msg=broad-except
            logging.exception(e)
            errors.append('Import failed: %s' % e)

        if errors:
            transforms.send_json_response(self, 412, '\n'.join(errors))
            return

        course.save()
        transforms.send_json_response(self, 200, 'Imported.')


def workflow_key(key):
    return 'workflow:%s' % key


def create_assessment_registry():
    """Create the registry for course properties."""

    reg = FieldRegistry('Assessment Entity', description='Assessment')

    # Course level settings.
    course_opts = generate_common_schema('Assessment Config')
    course_opts.add_property(
        SchemaField('weight', 'Weight', 'string', optional=True, i18n=False))
    course_opts.add_property(SchemaField(
        'content', 'Assessment Content', 'text', optional=True,
        description=str(messages.ASSESSMENT_CONTENT_DESCRIPTION),
        extra_schema_dict_values={'className': 'inputEx-Field content'}))
    course_opts.add_property(SchemaField(
        'html_content', 'Assessment Content (HTML)', 'html', optional=True,
        extra_schema_dict_values={
            'supportCustomTags': tags.CAN_USE_DYNAMIC_TAGS.value,
            'excludedCustomTags': tags.EditorBlacklists.ASSESSMENT_SCOPE,
            'className': 'inputEx-Field html-content'}))
    course_opts.add_property(SchemaField(
        'html_check_answers', '"Check Answers" Buttons', 'boolean',
        optional=True,
        extra_schema_dict_values={
            'className': 'inputEx-Field assessment-editor-check-answers'}))
    course_opts.add_property(
        SchemaField(workflow_key(courses.SUBMISSION_DUE_DATE_KEY),
                    'Submission Due Date', 'string', optional=True,
                    description=str(messages.DUE_DATE_FORMAT_DESCRIPTION)))
    course_opts.add_property(
        SchemaField(workflow_key(courses.GRADER_KEY), 'Grading Method',
                    'string',
                    select_data=ALLOWED_GRADERS_NAMES.items()))
    reg.add_sub_registry('assessment', 'Assessment Config',
                         registry=course_opts)

    review_opts = reg.add_sub_registry(
        'review_opts', 'Review Config',
        description=str(messages.ASSESSMENT_DETAILS_DESCRIPTION))
    if len(ALLOWED_MATCHERS_NAMES) > 1:
        review_opts.add_property(
            SchemaField(workflow_key(courses.MATCHER_KEY), 'Review Matcher',
                        'string', optional=True,
                        select_data=ALLOWED_MATCHERS_NAMES.items()))

    review_opts.add_property(
        SchemaField(
            'review_form', 'Reviewer Feedback Form', 'text', optional=True,
            description=str(messages.REVIEWER_FEEDBACK_FORM_DESCRIPTION),
            extra_schema_dict_values={
                'className': 'inputEx-Field review-form'}))
    review_opts.add_property(SchemaField(
        'html_review_form', 'Reviewer Feedback Form (HTML)', 'html',
        optional=True,
        extra_schema_dict_values={
            'supportCustomTags': tags.CAN_USE_DYNAMIC_TAGS.value,
            'excludedCustomTags': tags.EditorBlacklists.ASSESSMENT_SCOPE,
            'className': 'inputEx-Field html-review-form'}))
    review_opts.add_property(
        SchemaField(
            workflow_key(courses.REVIEW_DUE_DATE_KEY),
            'Review Due Date', 'string', optional=True,
            description=str(messages.REVIEW_DUE_DATE_FORMAT_DESCRIPTION)))
    review_opts.add_property(
        SchemaField(workflow_key(courses.REVIEW_MIN_COUNT_KEY),
                    'Review Min Count', 'integer', optional=True,
                    description=str(messages.REVIEW_MIN_COUNT_DESCRIPTION)))
    review_opts.add_property(
        SchemaField(workflow_key(courses.REVIEW_WINDOW_MINS_KEY),
                    'Review Window Timeout', 'integer', optional=True,
                    description=str(messages.REVIEW_TIMEOUT_IN_MINUTES)))
    return reg


class AssessmentRESTHandler(CommonUnitRESTHandler):
    """Provides REST API to assessment."""

    URI = '/rest/course/assessment'

    SCHEMA = create_assessment_registry()

    SCHEMA_JSON = SCHEMA.get_json_schema()

    SCHEMA_DICT = SCHEMA.get_json_schema_dict()

    SCHEMA_ANNOTATIONS_DICT = SCHEMA.get_schema_dict()

    REQUIRED_MODULES = [
        'gcb-rte', 'inputex-select', 'inputex-string', 'inputex-textarea',
        'inputex-uneditable', 'inputex-integer', 'inputex-hidden',
        'inputex-checkbox', 'inputex-list']


class UnitLessonTitleRESTHandler(BaseRESTHandler):
    """Provides REST API to unit and lesson titles."""

    URI = '/rest/course/outline'

    SCHEMA_JSON = """
        {
            "type": "object",
            "description": "Course Outline",
            "properties": {
                "outline": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "title": {"type": "string"},
                            "lessons": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "id": {"type": "string"},
                                        "title": {"type": "string"}
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        """

    SCHEMA_DICT = transforms.loads(SCHEMA_JSON)

    SCHEMA_ANNOTATIONS_DICT = [
        (['title'], 'Course Outline'),
        (['_inputex'], {'className': 'organizer'}),
        (['properties', 'outline', '_inputex'], {
            'sortable': 'true',
            'label': ''}),
        ([
            'properties', 'outline', 'items',
            'properties', 'title', '_inputex'], {
                '_type': 'uneditable',
                'label': ''}),
        (['properties', 'outline', 'items', 'properties', 'id', '_inputex'], {
            '_type': 'hidden'}),
        (['properties', 'outline', 'items', 'properties', 'lessons',
          '_inputex'], {
              'sortable': 'true',
              'label': '',
              'listAddLabel': 'Add  a new lesson',
              'listRemoveLabel': 'Delete'}),
        (['properties', 'outline', 'items', 'properties', 'lessons', 'items',
          'properties', 'title', '_inputex'], {
              '_type': 'uneditable',
              'label': ''}),
        (['properties', 'outline', 'items', 'properties', 'lessons', 'items',
          'properties', 'id', '_inputex'], {
              '_type': 'hidden'})
        ]

    REQUIRED_MODULES = [
        'inputex-hidden', 'inputex-list', 'inputex-string',
        'inputex-uneditable']

    def get(self):
        """Handles REST GET verb and returns an object as JSON payload."""

        if not CourseOutlineRights.can_view(self):
            transforms.send_json_response(self, 401, 'Access denied.', {})
            return

        course = courses.Course(self)
        outline_data = []
        for unit in course.get_units():
            lesson_data = []
            for lesson in course.get_lessons(unit.unit_id):
                lesson_data.append({
                    'title': lesson.title,
                    'id': lesson.lesson_id})
            unit_title = unit.title
            if verify.UNIT_TYPE_UNIT == unit.type:
                unit_title = 'Unit: %s' % unit.title
            outline_data.append({
                'title': unit_title,
                'id': unit.unit_id,
                'lessons': lesson_data})
        transforms.send_json_response(
            self, 200, None,
            payload_dict={'outline': outline_data},
            xsrf_token=XsrfTokenManager.create_xsrf_token(
                'unit-lesson-reorder'))

    def put(self):
        """Handles REST PUT verb with JSON payload."""
        request = transforms.loads(self.request.get('request'))

        if not self.assert_xsrf_token_or_fail(
                request, 'unit-lesson-reorder', {'key': None}):
            return

        if not CourseOutlineRights.can_edit(self):
            transforms.send_json_response(self, 401, 'Access denied.', {})
            return

        payload = request.get('payload')
        payload_dict = transforms.json_to_dict(
            transforms.loads(payload), self.SCHEMA_DICT)
        course = courses.Course(self)
        course.reorder_units(payload_dict['outline'])
        course.save()

        transforms.send_json_response(self, 200, 'Saved.')


class LessonRESTHandler(BaseRESTHandler):
    """Provides REST API to handle lessons and activities."""

    URI = '/rest/course/lesson'

    REQUIRED_MODULES = [
        'inputex-string', 'gcb-rte', 'inputex-select', 'inputex-textarea',
        'inputex-uneditable', 'inputex-checkbox', 'inputex-hidden']

    # These functions are called with an updated lesson object whenever a
    # change is saved.
    POST_SAVE_HOOKS = []

    @classmethod
    def get_schema(cls, units):
        # Note GcbRte relies on the structure of this schema. Do not change
        # without checking the dependency.
        unit_list = []
        for unit in units:
            if unit.type == 'U':
                unit_list.append(
                    (unit.unit_id, cgi.escape(utils.display_unit_title(unit))))

        lesson = FieldRegistry('Lesson', description='Lesson')
        lesson.add_property(SchemaField(
            'key', 'ID', 'string', editable=False,
             extra_schema_dict_values={'className': 'inputEx-Field keyHolder'}))
        lesson.add_property(SchemaField(
            'title', 'Title', 'string'))
        lesson.add_property(SchemaField(
            'unit_id', 'Parent Unit', 'string', i18n=False,
            select_data=unit_list))
        lesson.add_property(SchemaField(
            'video', 'Video ID', 'string', optional=True,
            description=messages.LESSON_VIDEO_ID_DESCRIPTION))
        lesson.add_property(SchemaField(
            'scored', 'Scored', 'string', optional=True, i18n=False,
            description=messages.LESSON_SCORED_DESCRIPTION,
            select_data=[
                ('scored', 'Questions are scored'),
                ('not_scored', 'Questions only give feedback')]))
        lesson.add_property(SchemaField(
            'objectives', 'Lesson Body', 'html', optional=True,
            description=messages.LESSON_OBJECTIVES_DESCRIPTION,
            extra_schema_dict_values={
                'supportCustomTags': tags.CAN_USE_DYNAMIC_TAGS.value}))
        lesson.add_property(SchemaField(
            'notes', 'Notes', 'string', optional=True,
            description=messages.LESSON_NOTES_DESCRIPTION))
        lesson.add_property(SchemaField(
            'auto_index', 'Auto Number', 'boolean',
            description=messages.LESSON_AUTO_INDEX_DESCRIPTION))
        lesson.add_property(SchemaField(
            'activity_title', 'Activity Title', 'string', optional=True,
            description=messages.LESSON_ACTIVITY_TITLE_DESCRIPTION))
        lesson.add_property(SchemaField(
            'activity_listed', 'Activity Listed', 'boolean', optional=True,
            description=messages.LESSON_ACTIVITY_LISTED_DESCRIPTION))
        lesson.add_property(SchemaField(
            'activity', 'Activity', 'text', optional=True,
            description=str(messages.LESSON_ACTIVITY_DESCRIPTION),
            extra_schema_dict_values={
                'className': 'inputEx-Field activityHolder'}))
        lesson.add_property(SchemaField(
            'manual_progress', 'Manual Progress', 'boolean', optional=True,
            description=messages.LESSON_MANUAL_PROGRESS_DESCRIPTION))
        lesson.add_property(SchemaField(
            'is_draft', 'Status', 'boolean',
            select_data=[(True, DRAFT_TEXT), (False, PUBLISHED_TEXT)],
            extra_schema_dict_values={
                'className': 'split-from-main-group'}))
        return lesson

    @classmethod
    def get_lesson_dict(cls, app_context, lesson):
        return cls.get_lesson_dict_for(
            courses.Course(None, app_context=app_context), lesson)

    @classmethod
    def get_lesson_dict_for(cls, course, lesson):
        fs = course.app_context.fs
        path = fs.impl.physical_to_logical(course.get_activity_filename(
            lesson.unit_id, lesson.lesson_id))
        if lesson.has_activity and fs.isfile(path):
            activity = fs.get(path)
        else:
            activity = ''

        return {
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

    def get(self):
        """Handles GET REST verb and returns lesson object as JSON payload."""

        if not CourseOutlineRights.can_view(self):
            transforms.send_json_response(self, 401, 'Access denied.', {})
            return

        key = self.request.get('key')
        course = courses.Course(self)
        lesson = course.find_lesson_by_id(None, key)
        assert lesson
        payload_dict = self.get_lesson_dict(self.app_context, lesson)

        message = ['Success.']
        if self.request.get('is_newly_created'):
            message.append('New lesson has been created and saved.')

        transforms.send_json_response(
            self, 200, '\n'.join(message),
            payload_dict=payload_dict,
            xsrf_token=XsrfTokenManager.create_xsrf_token('lesson-edit'))

    def put(self):
        """Handles PUT REST verb to save lesson and associated activity."""
        request = transforms.loads(self.request.get('request'))
        key = request.get('key')

        if not self.assert_xsrf_token_or_fail(
                request, 'lesson-edit', {'key': key}):
            return

        if not CourseOutlineRights.can_edit(self):
            transforms.send_json_response(
                self, 401, 'Access denied.', {'key': key})
            return

        course = courses.Course(self)
        lesson = course.find_lesson_by_id(None, key)
        if not lesson:
            transforms.send_json_response(
                self, 404, 'Object not found.', {'key': key})
            return

        payload = request.get('payload')
        updates_dict = transforms.json_to_dict(
            transforms.loads(payload),
            self.get_schema(course.get_units()).get_json_schema_dict())

        lesson.title = updates_dict['title']
        lesson.unit_id = updates_dict['unit_id']
        lesson.scored = (updates_dict['scored'] == 'scored')
        lesson.objectives = updates_dict['objectives']
        lesson.video = updates_dict['video']
        lesson.notes = updates_dict['notes']
        lesson.auto_index = updates_dict['auto_index']
        lesson.activity_title = updates_dict['activity_title']
        lesson.activity_listed = updates_dict['activity_listed']
        lesson.manual_progress = updates_dict['manual_progress']
        lesson.now_available = not updates_dict['is_draft']

        activity = updates_dict.get('activity', '').strip()
        errors = []
        if activity:
            if lesson.has_activity:
                course.set_activity_content(lesson, activity, errors=errors)
            else:
                errors.append('Old-style activities are not supported.')
        else:
            lesson.has_activity = False
            fs = self.app_context.fs
            path = fs.impl.physical_to_logical(course.get_activity_filename(
                lesson.unit_id, lesson.lesson_id))
            if fs.isfile(path):
                fs.delete(path)

        if not errors:
            assert course.update_lesson(lesson)
            course.save()
            common_utils.run_hooks(self.POST_SAVE_HOOKS, lesson)
            transforms.send_json_response(self, 200, 'Saved.')
        else:
            transforms.send_json_response(self, 412, '\n'.join(errors))

    def delete(self):
        """Handles REST DELETE verb with JSON payload."""
        key = self.request.get('key')

        if not self.assert_xsrf_token_or_fail(
                self.request, 'delete-lesson', {'key': key}):
            return

        if not CourseOutlineRights.can_delete(self):
            transforms.send_json_response(
                self, 401, 'Access denied.', {'key': key})
            return

        course = courses.Course(self)
        lesson = course.find_lesson_by_id(None, key)
        if not lesson:
            transforms.send_json_response(
                self, 404, 'Object not found.', {'key': key})
            return

        assert course.delete_lesson(lesson)
        course.save()

        transforms.send_json_response(self, 200, 'Deleted.')
