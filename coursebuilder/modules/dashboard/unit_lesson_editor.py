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
import random
import urllib
from common import safe_dom
from common import tags
from common.schema_fields import FieldRegistry
from common.schema_fields import SchemaField
from controllers import sites
from controllers.utils import ApplicationHandler
from controllers.utils import BaseRESTHandler
from controllers.utils import XsrfTokenManager
from models import courses
from models import models as m_models
from models import review
from models import roles
from models import transforms
from modules.oeditor import oeditor
from tools import verify
import yaml
import filer
import messages


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


# Allowed matchers. Keys of this dict represent internal keys for the matcher
# type, and the value represents the corresponding string that will appear in
# the dashboard UI.
ALLOWED_MATCHERS_NAMES = {review.PEER_MATCHER: messages.PEER_MATCHER_NAME}


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

    def _render_edit_form_for(
        self, rest_handler_cls, title, annotations_dict=None,
        delete_xsrf_token='delete-unit', page_description=None,
        extra_js_files=None):
        """Renders an editor form for a given REST handler class."""
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
            rest_handler_cls.SCHEMA_JSON,
            annotations_dict,
            key, rest_url, exit_url,
            extra_args=extra_args,
            delete_url=delete_url, delete_method='delete',
            read_only=not filer.is_editable_fs(self.app_context),
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
            page_description=messages.UNIT_EDITOR_DESCRIPTION)

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
        self._render_edit_form_for(
            LessonRESTHandler, 'Lessons and Activities',
            annotations_dict=LessonRESTHandler.get_schema_annotations_dict(
                courses.Course(self).get_units()),
            delete_xsrf_token='delete-lesson',
            extra_js_files=LessonRESTHandler.EXTRA_JS_FILES)


class CommonUnitRESTHandler(BaseRESTHandler):
    """A common super class for all unit REST handlers."""

    def unit_to_dict(self, unused_unit):
        """Converts a unit to a dictionary representation."""
        raise Exception('Not implemented')

    def apply_updates(
        self, unused_unit, unused_updated_unit_dict, unused_errors):
        """Applies changes to a unit; modifies unit input argument."""
        raise Exception('Not implemented')

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


class UnitRESTHandler(CommonUnitRESTHandler):
    """Provides REST API to unit."""

    URI = '/rest/course/unit'

    SCHEMA_JSON = """
    {
        "id": "Unit Entity",
        "type": "object",
        "description": "Unit",
        "properties": {
            "key" : {"type": "string"},
            "type": {"type": "string"},
            "title": {"optional": true, "type": "string"},
            "is_draft": {"type": "boolean"}
            }
    }
    """

    SCHEMA_DICT = transforms.loads(SCHEMA_JSON)

    SCHEMA_ANNOTATIONS_DICT = [
        (['title'], 'Unit'),
        (['properties', 'key', '_inputex'], {
            'label': 'ID', '_type': 'uneditable'}),
        (['properties', 'type', '_inputex'], {
            'label': 'Type', '_type': 'uneditable'}),
        (['properties', 'title', '_inputex'], {'label': 'Title'}),
        STATUS_ANNOTATION]

    REQUIRED_MODULES = [
        'inputex-string', 'inputex-select', 'inputex-uneditable']

    def unit_to_dict(self, unit):
        assert unit.type == 'U'
        return {
            'key': unit.unit_id,
            'type': verify.UNIT_TYPE_NAMES[unit.type],
            'title': unit.title,
            'is_draft': not unit.now_available}

    def apply_updates(self, unit, updated_unit_dict, unused_errors):
        unit.title = updated_unit_dict.get('title')
        unit.now_available = not updated_unit_dict.get('is_draft')


class LinkRESTHandler(CommonUnitRESTHandler):
    """Provides REST API to link."""

    URI = '/rest/course/link'

    SCHEMA_JSON = """
    {
        "id": "Link Entity",
        "type": "object",
        "description": "Link",
        "properties": {
            "key" : {"type": "string"},
            "type": {"type": "string"},
            "title": {"optional": true, "type": "string"},
            "url": {"optional": true, "type": "string"},
            "is_draft": {"type": "boolean"}
            }
    }
    """

    SCHEMA_DICT = transforms.loads(SCHEMA_JSON)

    SCHEMA_ANNOTATIONS_DICT = [
        (['title'], 'Link'),
        (['properties', 'key', '_inputex'], {
            'label': 'ID', '_type': 'uneditable'}),
        (['properties', 'type', '_inputex'], {
            'label': 'Type', '_type': 'uneditable'}),
        (['properties', 'title', '_inputex'], {'label': 'Title'}),
        (['properties', 'url', '_inputex'], {
            'label': 'URL',
            'description': messages.LINK_EDITOR_URL_DESCRIPTION}),
        STATUS_ANNOTATION]

    REQUIRED_MODULES = [
        'inputex-string', 'inputex-select', 'inputex-uneditable']

    def unit_to_dict(self, unit):
        assert unit.type == 'O'
        return {
            'key': unit.unit_id,
            'type': verify.UNIT_TYPE_NAMES[unit.type],
            'title': unit.title,
            'url': unit.href,
            'is_draft': not unit.now_available}

    def apply_updates(self, unit, updated_unit_dict, unused_errors):
        unit.title = updated_unit_dict.get('title')
        unit.href = updated_unit_dict.get('url')
        unit.now_available = not updated_unit_dict.get('is_draft')


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
            course_list.append({
                'value': acourse.raw,
                'label': cgi.escape(acourse.get_title())})
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
    course_opts = reg.add_sub_registry('assessment', 'Assessment Config')
    course_opts.add_property(SchemaField(
        'key', 'ID', 'string', editable=False,
        extra_schema_dict_values={'className': 'inputEx-Field keyHolder'}))
    course_opts.add_property(
        SchemaField('type', 'Type', 'string', editable=False))
    course_opts.add_property(
        SchemaField('title', 'Title', 'string', optional=True))
    course_opts.add_property(
        SchemaField('weight', 'Weight', 'string', optional=True))
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
    course_opts.add_property(
        SchemaField('is_draft', 'Status', 'boolean',
                    select_data=[(True, DRAFT_TEXT), (False, PUBLISHED_TEXT)],
                    extra_schema_dict_values={
                        'className': 'split-from-main-group'}))

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

    REG = create_assessment_registry()

    SCHEMA_JSON = REG.get_json_schema()

    SCHEMA_DICT = REG.get_json_schema_dict()

    SCHEMA_ANNOTATIONS_DICT = REG.get_schema_dict()

    REQUIRED_MODULES = [
        'gcb-rte', 'inputex-select', 'inputex-string', 'inputex-textarea',
        'inputex-uneditable', 'inputex-integer', 'inputex-hidden',
        'inputex-checkbox']

    def _get_assessment_path(self, unit):
        return self.app_context.fs.impl.physical_to_logical(
            courses.Course(self).get_assessment_filename(unit.unit_id))

    def _get_review_form_path(self, unit):
        return self.app_context.fs.impl.physical_to_logical(
            courses.Course(self).get_review_form_filename(unit.unit_id))

    def unit_to_dict(self, unit):
        """Assemble a dict with the unit data fields."""
        assert unit.type == 'A'

        path = self._get_assessment_path(unit)
        fs = self.app_context.fs
        if fs.isfile(path):
            content = fs.get(path)
        else:
            content = ''

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

        return {
            'assessment': {
                'key': unit.unit_id,
                'type': verify.UNIT_TYPE_NAMES[unit.type],
                'title': unit.title,
                'weight': str(unit.weight if hasattr(unit, 'weight') else 0),
                'content': content,
                'html_content': unit.html_content or '',
                'html_check_answers': unit.html_check_answers,
                'is_draft': not unit.now_available,
                workflow_key(courses.SUBMISSION_DUE_DATE_KEY): (
                    submission_due_date),
                workflow_key(courses.GRADER_KEY): workflow.get_grader(),
                },
            'review_opts': {
                workflow_key(courses.MATCHER_KEY): workflow.get_matcher(),
                workflow_key(courses.REVIEW_DUE_DATE_KEY): review_due_date,
                workflow_key(courses.REVIEW_MIN_COUNT_KEY): (
                    workflow.get_review_min_count()),
                workflow_key(courses.REVIEW_WINDOW_MINS_KEY): (
                    workflow.get_review_window_mins()),
                'review_form': review_form,
                'html_review_form': unit.html_review_form or ''
                }
            }

    def apply_updates(self, unit, updated_unit_dict, errors):
        """Store the updated assessment."""

        entity_dict = {}
        AssessmentRESTHandler.REG.convert_json_to_entity(
            updated_unit_dict, entity_dict)
        unit.title = entity_dict.get('title')

        try:
            unit.weight = int(entity_dict.get('weight'))
            if unit.weight < 0:
                errors.append('The weight must be a non-negative integer.')
        except ValueError:
            errors.append('The weight must be an integer.')

        unit.now_available = not entity_dict.get('is_draft')
        course = courses.Course(self)
        content = entity_dict.get('content')
        if content:
            course.set_assessment_content(
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
            if course.needs_human_grader(unit):
                review_form = entity_dict.get('review_form')
                if review_form:
                    course.set_review_form(
                        unit, review_form, errors=errors)
                unit.html_review_form = entity_dict.get('html_review_form')
            elif entity_dict.get('review_form'):
                errors.append(
                    'Review forms for auto-graded assessments should be empty.')


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

    # Note GcbRte relies on the structure of this schema. Do not change without
    # checking the dependency.
    SCHEMA_JSON = """
    {
        "id": "Lesson Entity",
        "type": "object",
        "description": "Lesson",
        "properties": {
            "key" : {"type": "string"},
            "title" : {"type": "string"},
            "unit_id": {"type": "string"},
            "video" : {"type": "string", "optional": true},
            "scored": {"type": "string"},
            "objectives" : {
                "type": "string", "format": "html", "optional": true},
            "notes" : {"type": "string", "optional": true},
            "activity_title" : {"type": "string", "optional": true},
            "activity_listed" : {"type": "boolean", "optional": true},
            "activity": {"type": "string", "format": "text", "optional": true},
            "is_draft": {"type": "boolean"}
            }
    }
    """

    SCHEMA_DICT = transforms.loads(SCHEMA_JSON)

    REQUIRED_MODULES = [
        'inputex-string', 'gcb-rte', 'inputex-select', 'inputex-textarea',
        'inputex-uneditable', 'inputex-checkbox']
    EXTRA_JS_FILES = ['lesson_editor_lib.js', 'lesson_editor.js']

    @classmethod
    def get_schema_annotations_dict(cls, units):
        unit_list = []
        for unit in units:
            if unit.type == 'U':
                unit_list.append({
                    'label': cgi.escape(
                        'Unit %s - %s' % (unit.index, unit.title)),
                    'value': unit.unit_id})

        return [
            (['title'], 'Lesson'),
            (['properties', 'key', '_inputex'], {
                'label': 'ID', '_type': 'uneditable',
                'className': 'inputEx-Field keyHolder'}),
            (['properties', 'title', '_inputex'], {'label': 'Title'}),
            (['properties', 'unit_id', '_inputex'], {
                'label': 'Parent Unit', '_type': 'select',
                'choices': unit_list}),
            (['properties', 'scored', '_inputex'], {
                '_type': 'select',
                'choices': [
                    {'label': 'Questions are scored', 'value': 'scored'},
                    {
                        'label': 'Questions only give feedback',
                        'value': 'not_scored'}],
                'label': 'Scored',
                'description': messages.LESSON_SCORED_DESCRIPTION}),
            # TODO(sll): The internal 'objectives' property should also be
            # renamed.
            (['properties', 'objectives', '_inputex'], {
                'label': 'Lesson Body',
                'supportCustomTags': tags.CAN_USE_DYNAMIC_TAGS.value,
                'description': messages.LESSON_OBJECTIVES_DESCRIPTION}),
            (['properties', 'video', '_inputex'], {
                'label': 'Video ID',
                'description': messages.LESSON_VIDEO_ID_DESCRIPTION}),
            (['properties', 'notes', '_inputex'], {
                'label': 'Notes',
                'description': messages.LESSON_NOTES_DESCRIPTION}),
            (['properties', 'activity_title', '_inputex'], {
                'label': 'Activity Title',
                'description': messages.LESSON_ACTIVITY_TITLE_DESCRIPTION}),
            (['properties', 'activity_listed', '_inputex'], {
                'label': 'Activity Listed',
                'description': messages.LESSON_ACTIVITY_LISTED_DESCRIPTION}),
            (['properties', 'activity', '_inputex'], {
                'label': 'Activity',
                'description': str(messages.LESSON_ACTIVITY_DESCRIPTION),
                'className': 'inputEx-Field activityHolder'}),
            STATUS_ANNOTATION]

    def get(self):
        """Handles GET REST verb and returns lesson object as JSON payload."""

        if not CourseOutlineRights.can_view(self):
            transforms.send_json_response(self, 401, 'Access denied.', {})
            return

        key = self.request.get('key')
        course = courses.Course(self)
        lesson = course.find_lesson_by_id(None, key)
        assert lesson

        fs = self.app_context.fs
        path = fs.impl.physical_to_logical(course.get_activity_filename(
            lesson.unit_id, lesson.lesson_id))
        if lesson.has_activity and fs.isfile(path):
            activity = fs.get(path)
        else:
            activity = ''

        payload_dict = {
            'key': key,
            'title': lesson.title,
            'unit_id': lesson.unit_id,
            'scored': 'scored' if lesson.scored else 'not_scored',
            'objectives': lesson.objectives,
            'video': lesson.video,
            'notes': lesson.notes,
            'activity_title': lesson.activity_title,
            'activity_listed': lesson.activity_listed,
            'activity': activity,
            'is_draft': not lesson.now_available
            }

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
            transforms.loads(payload), self.SCHEMA_DICT)

        lesson.title = updates_dict['title']
        lesson.unit_id = updates_dict['unit_id']
        lesson.scored = (updates_dict['scored'] == 'scored')
        lesson.objectives = updates_dict['objectives']
        lesson.video = updates_dict['video']
        lesson.notes = updates_dict['notes']
        lesson.activity_title = updates_dict['activity_title']
        lesson.activity_listed = updates_dict['activity_listed']
        lesson.now_available = not updates_dict['is_draft']

        activity = updates_dict.get('activity', '').strip()
        errors = []
        if activity:
            lesson.has_activity = True
            course.set_activity_content(lesson, activity, errors=errors)
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


def generate_instanceid():
    chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
    length = 12
    return ''.join([random.choice(chars) for unused_i in xrange(length)])


class CollisionError(Exception):
    """Exception raised to show that a collision in a namespace has occurred."""


class ImportActivityRESTHandler(BaseRESTHandler):
    """REST handler for requests to import an activity into the lesson body."""

    URI = '/rest/course/lesson/activity'

    VERSION = '1.5'

    def put(self):
        """Handle REST PUT instruction to import an assignment."""
        request = transforms.loads(self.request.get('request'))
        key = request.get('key')

        if not self.assert_xsrf_token_or_fail(request, 'lesson-edit', {}):
            return

        if not CourseOutlineRights.can_edit(self):
            transforms.send_json_response(
                self, 401, 'Access denied.', {'key': key})
            return

        text = request.get('text')

        try:
            content, noverify_text = verify.convert_javascript_to_python(
                text, 'activity')
            activity = verify.evaluate_python_expression_from_text(
                content, 'activity', verify.Activity().scope, noverify_text)
        except Exception:  # pylint: disable-msg=broad-except
            transforms.send_json_response(
                self, 412, 'Unable to parse activity.')
            return

        try:
            verify.Verifier().verify_activity_instance(activity, 'none')
        except verify.SchemaException:
            transforms.send_json_response(
                self, 412, 'Unable to validate activity.')
            return

        self.course = courses.Course(self)
        self.lesson = self.course.find_lesson_by_id(None, key)
        self.unit = self.course.find_unit_by_id(self.lesson.unit_id)
        self.question_number = 0
        self.question_descriptions = set(
            [q.description for q in m_models.QuestionDAO.get_all()])
        self.question_group_descriptions = set(
            [qg.description for qg in m_models.QuestionGroupDAO.get_all()])

        lesson_content = []
        try:
            for item in activity['activity']:
                if isinstance(item, basestring):
                    lesson_content.append(item)
                else:
                    question_tag = self.import_question(item)
                    lesson_content.append(question_tag)
                    self.question_number += 1
        except CollisionError:
            transforms.send_json_response(
                self, 412, (
                    'This activity has already been imported. Remove duplicate '
                    'imported questions from the question bank in order to '
                    're-import.'))
            return
        except Exception as ex:
            transforms.send_json_response(
                self, 412, 'Unable to convert: %s' % ex)
            return

        transforms.send_json_response(self, 200, 'OK.', payload_dict={
            'content': '\n'.join(lesson_content)
        })

    def _get_question_description(self):
        return (
            'Imported from unit "%s", lesson "%s" (question #%s)' % (
                self.unit.title, self.lesson.title, self.question_number + 1))

    def _insert_question(self, question_dict, question_type):
        question = m_models.QuestionDTO(None, question_dict)
        question.type = question_type
        return m_models.QuestionDAO.save(question)

    def _insert_question_group(self, question_group_dict):
        question_group = m_models.QuestionGroupDTO(None, question_group_dict)
        return m_models.QuestionGroupDAO.save(question_group)

    def import_question(self, item):
        question_type = item['questionType']
        if question_type == 'multiple choice':
            question_dict = self.import_multiple_choice(item)
            quid = self._insert_question(
                question_dict, m_models.QuestionDTO.MULTIPLE_CHOICE)
            return '<question quid="%s" instanceid="%s"></question>' % (
                quid, generate_instanceid())
        elif question_type == 'multiple choice group':
            question_group_dict = self.import_multiple_choice_group(item)
            qgid = self._insert_question_group(question_group_dict)
            return (
                '<question-group qgid="%s" instanceid="%s">'
                '</question-group>') % (
                    qgid, generate_instanceid())
        elif question_type == 'freetext':
            question_dict = self.import_freetext(item)
            quid = self._insert_question(
                question_dict, m_models.QuestionDTO.SHORT_ANSWER)
            return '<question quid="%s" instanceid="%s"></question>' % (
                quid, generate_instanceid())
        else:
            raise ValueError('Unknown question type: %s' % question_type)

    def import_multiple_choice(self, orig_question):
        description = self._get_question_description()
        if description in self.question_descriptions:
            raise CollisionError()

        return {
            'version': self.VERSION,
            'description': description,
            'question': '',
            'multiple_selections': False,
            'choices': [
                {
                    'text': choice[0],
                    'score': 1.0 if choice[1].value else 0.0,
                    'feedback': choice[2]
                } for choice in orig_question['choices']]}

    def import_multiple_choice_group(self, mc_choice_group):
        """Import a 'multiple choice group' as a question group."""
        description = self._get_question_description()
        if description in self.question_group_descriptions:
            raise CollisionError()

        question_group_dict = {
            'version': self.VERSION,
            'description': description}

        question_list = []
        for index, question in enumerate(mc_choice_group['questionsList']):
            question_dict = self.import_multiple_choice_group_question(
                question, index)
            question = m_models.QuestionDTO(None, question_dict)
            question.type = m_models.QuestionDTO.MULTIPLE_CHOICE
            question_list.append(question)

        quid_list = m_models.QuestionDAO.save_all(question_list)
        question_group_dict['items'] = [{
            'question': str(quid),
            'weight': 1.0} for quid in quid_list]

        return question_group_dict

    def import_multiple_choice_group_question(self, orig_question, index):
        """Import the questions from a group as individual questions."""
        # TODO(jorr): Handle allCorrectOutput and someCorrectOutput
        description = (
            'Imported from unit "%s", lesson "%s" (question #%s, part #%s)' % (
                self.unit.title, self.lesson.title, self.question_number + 1,
                index + 1))
        if description in self.question_descriptions:
            raise CollisionError()

        correct_index = orig_question['correctIndex']
        multiple_selections = not isinstance(correct_index, int)
        if multiple_selections:
            partial = 1.0 / len(correct_index)
            choices = [{
                'text': text,
                'score': partial if i in correct_index else -1.0
            } for i, text in enumerate(orig_question['choices'])]
        else:
            choices = [{
                'text': text,
                'score': 1.0 if i == correct_index else 0.0
            } for i, text in enumerate(orig_question['choices'])]

        return {
            'version': self.VERSION,
            'description': description,
            'question': orig_question.get('questionHTML') or '',
            'multiple_selections': multiple_selections,
            'choices': choices}

    def import_freetext(self, orig_question):
        description = self._get_question_description()
        if description in self.question_descriptions:
            raise CollisionError()

        return {
            'version': self.VERSION,
            'description': description,
            'question': '',
            'hint': orig_question['showAnswerOutput'],
            'graders': [{
                'score': 1.0,
                'matcher': 'regex',
                'response': orig_question['correctAnswerRegex'].value,
                'feedback': orig_question.get('correctAnswerOutput')
            }],
            'defaultFeedback': orig_question.get('incorrectAnswerOutput')}


class ExportAssessmentRESTHandler(BaseRESTHandler):
    """REST handler for requests to export an activity into new format."""

    URI = '/rest/course/asessment/export'

    VERSION = '1.5'

    def put(self):
        """Handle the PUT verb to export an assessment."""
        request = transforms.loads(self.request.get('request'))
        key = request.get('key')

        if not CourseOutlineRights.can_edit(self):
            transforms.send_json_response(
                self, 401, 'Access denied.', {'key': key})
            return

        if not self.assert_xsrf_token_or_fail(
                request, 'put-unit', {'key': key}):
            return

        raw_assessment_dict = transforms.json_to_dict(
            request.get('payload'), AssessmentRESTHandler.SCHEMA_DICT)

        entity_dict = {}
        AssessmentRESTHandler.REG.convert_json_to_entity(
            raw_assessment_dict, entity_dict)

        course = courses.Course(self)
        self.unit = course.find_unit_by_id(key)
        self.question_descriptions = set(
            [q.description for q in m_models.QuestionDAO.get_all()])

        # Import all the assessment context except the questions
        new_unit = course.add_assessment()
        errors = []
        new_unit.title = 'Exported from %s ' % entity_dict.get('title')
        try:
            new_unit.weight = int(entity_dict.get('weight'))
            if new_unit.weight < 0:
                errors.append('The weight must be a non-negative integer.')
        except ValueError:
            errors.append('The weight must be an integer.')
        new_unit.now_available = not entity_dict.get('is_draft')

        workflow_dict = entity_dict.get('workflow')
        if len(ALLOWED_MATCHERS_NAMES) == 1:
            workflow_dict[courses.MATCHER_KEY] = (
                ALLOWED_MATCHERS_NAMES.keys()[0])
        new_unit.workflow_yaml = yaml.safe_dump(workflow_dict)
        new_unit.workflow.validate(errors=errors)

        if errors:
            transforms.send_json_response(self, 412, '\n'.join(errors))
            return

        assessment_dict = self.get_assessment_dict(entity_dict.get('content'))
        if assessment_dict is None:
            return

        if assessment_dict.get('checkAnswers'):
            new_unit.html_check_answers = assessment_dict['checkAnswers'].value

        # Import the questions in the assessment and the review questionnaire

        html_content = []
        html_review_form = []

        if assessment_dict.get('preamble'):
            html_content.append(assessment_dict['preamble'])

        # prepare all the dtos for the questions in the assigment content
        question_dtos = self.get_question_dtos(
            assessment_dict,
            'Imported from assessment "%s" (question #%s)')
        if question_dtos is None:
            return

        # prepare the questions for the review questionnaire, if necessary
        review_dtos = []
        if course.needs_human_grader(new_unit):
            review_str = entity_dict.get('review_form')
            review_dict = self.get_assessment_dict(review_str)
            if review_dict is None:
                return
            if review_dict.get('preamble'):
                html_review_form.append(review_dict['preamble'])

            review_dtos = self.get_question_dtos(
                review_dict,
                'Imported from assessment "%s" (review question #%s)')
            if review_dtos is None:
                return

        # batch submit the questions and split out their resulting id's
        all_dtos = question_dtos + review_dtos
        all_ids = m_models.QuestionDAO.save_all(all_dtos)
        question_ids = all_ids[:len(question_dtos)]
        review_ids = all_ids[len(question_dtos):]

        # insert question tags for the assessment content
        for quid in question_ids:
            html_content.append(
                str(safe_dom.Element(
                    'question',
                    quid=str(quid), instanceid=generate_instanceid())))
        new_unit.html_content = '\n'.join(html_content)

        # insert question tags for the review questionnaire
        for quid in review_ids:
            html_review_form.append(
                str(safe_dom.Element(
                    'question',
                    quid=str(quid), instanceid=generate_instanceid())))
        new_unit.html_review_form = '\n'.join(html_review_form)

        course.save()
        transforms.send_json_response(
            self, 200, (
                'The assessment has been exported to "%s".' % new_unit.title),
            payload_dict={'key': key})

    def get_assessment_dict(self, assessment_content):
        """Validate the assessment scipt and return as a python dict."""
        try:
            content, noverify_text = verify.convert_javascript_to_python(
                assessment_content, 'assessment')
            assessment = verify.evaluate_python_expression_from_text(
                content, 'assessment', verify.Assessment().scope, noverify_text)
        except Exception:  # pylint: disable-msg=broad-except
            transforms.send_json_response(
                self, 412, 'Unable to parse asessment.')
            return None

        try:
            verify.Verifier().verify_assessment_instance(assessment, 'none')
        except verify.SchemaException:
            transforms.send_json_response(
                self, 412, 'Unable to validate assessment')
            return None

        return assessment['assessment']

    def get_question_dtos(self, assessment_dict, description_template):
        """Convert the assessment into a list of QuestionDTO's."""
        question_dtos = []
        try:
            for i, question in enumerate(assessment_dict['questionsList']):
                description = description_template % (self.unit.title, (i + 1))
                if description in self.question_descriptions:
                    raise CollisionError()
                question_dto = self.import_question(question)
                question_dto.dict['description'] = description
                question_dtos.append(question_dto)
        except CollisionError:
            transforms.send_json_response(
                self, 412, (
                    'This assessment has already been imported. Remove '
                    'duplicate imported questions from the question bank in '
                    'order to re-import.'))
            return None
        except Exception as ex:
            transforms.send_json_response(
                self, 412, 'Unable to convert: %s' % ex)
            return None
        return question_dtos

    def import_question(self, question):
        """Convert a single question into a QuestioDTO."""
        if 'choices' in question:
            question_dict = self.import_multiple_choice_question(question)
            question_type = m_models.QuestionDTO.MULTIPLE_CHOICE
        elif 'correctAnswerNumeric' in question:
            question_dict = self.import_short_answer_question(
                question.get('questionHTML'),
                'numeric',
                question.get('correctAnswerNumeric'))
            question_type = m_models.QuestionDTO.SHORT_ANSWER
        elif 'correctAnswerString' in question:
            question_dict = self.import_short_answer_question(
                question.get('questionHTML'),
                'case_insensitive',
                question.get('correctAnswerString'))
            question_type = m_models.QuestionDTO.SHORT_ANSWER
        elif 'correctAnswerRegex' in question:
            question_dict = self.import_short_answer_question(
                question.get('questionHTML'),
                'regex',
                question.get('correctAnswerRegex').value)
            question_type = m_models.QuestionDTO.SHORT_ANSWER
        else:
            raise ValueError('Unknown question type')

        question_dto = m_models.QuestionDTO(None, question_dict)
        question_dto.type = question_type

        return question_dto

    def import_multiple_choice_question(self, question):
        """Assemble the dict for a multiple choice question."""
        question_dict = {
            'version': self.VERSION,
            'question': question.get('questionHTML') or '',
            'multiple_selections': False
        }
        choices = []
        for choice in question.get('choices'):
            if isinstance(choice, basestring):
                text = choice
                score = 0.0
            else:
                text = choice.value
                score = 1.0
            choices.append({
                'text': text,
                'score': score
            })
        question_dict['choices'] = choices
        return question_dict

    def import_short_answer_question(self, question_html, matcher, response):
        return {
            'version': self.VERSION,
            'question': question_html or '',
            'graders': [{
                'score': 1.0,
                'matcher': matcher,
                'response': response,
            }]
        }
