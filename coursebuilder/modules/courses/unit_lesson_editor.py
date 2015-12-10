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

from common import utils as common_utils
from common import crypto
from common import schema_fields
from controllers import sites
from controllers import utils
from models import courses
from models import resources_display
from models import custom_units
from models import jobs
from models import permissions
from models import roles
from models import services
from models import transforms
from modules.courses import constants
from modules.courses import messages
from modules.assessments import assessments
from modules.dashboard import dashboard
from modules.oeditor import oeditor
from tools import verify

from google.appengine.ext import db

custom_module = None  # reference to modules.courses.courses.custom_module


class UnitLessonEditor(object):
    """Namespace for functions handling action callbacks from Dashboard."""

    HIDE_ACTIVITY_ANNOTATIONS = [
        (['properties', 'activity_title', '_inputex'], {'_type': 'hidden'}),
        (['properties', 'activity_listed', '_inputex'], {'_type': 'hidden'}),
        (['properties', 'activity', '_inputex'], {'_type': 'hidden'}),
    ]

    ACTION_GET_IMPORT_COURSE = 'import_course'
    ACTION_POST_CANCEL_IMPORT = 'cancel_import'
    ACTION_POST_ADD_UNIT = 'add_unit'
    ACTION_GET_EDIT_UNIT = 'edit_unit'
    ACTION_POST_ADD_LESSON = 'add_lesson'
    ACTION_GET_EDIT_LESSON = 'edit_lesson'
    ACTION_GET_IN_PLACE_LESSON_EDITOR = 'in_place_lesson_editor'
    ACTION_POST_ADD_LINK = 'add_link'
    ACTION_GET_EDIT_LINK = 'edit_link'
    ACTION_POST_ADD_ASSESSMENT = 'add_assessment'
    ACTION_GET_EDIT_ASSESSMENT = 'edit_assessment'
    ACTION_POST_ADD_CUSTOM_UNIT = 'add_custom_unit'
    ACTION_GET_EDIT_CUSTOM_UNIT = 'edit_custom_unit'

    @classmethod
    def on_module_enabled(cls):
        for action, callback in (
            (cls.ACTION_GET_IMPORT_COURSE, cls.get_import_course),
            (cls.ACTION_POST_CANCEL_IMPORT, cls.post_cancel_import),
            (cls.ACTION_POST_ADD_UNIT, cls.post_add_unit),
            (cls.ACTION_GET_EDIT_UNIT, cls.get_edit_unit),
            (cls.ACTION_POST_ADD_LESSON, cls.post_add_lesson),
            (cls.ACTION_GET_EDIT_LESSON, cls.get_edit_lesson),
            (cls.ACTION_GET_IN_PLACE_LESSON_EDITOR,
             cls.get_in_place_lesson_editor),
            (cls.ACTION_POST_ADD_LINK, cls.post_add_link),
            (cls.ACTION_GET_EDIT_LINK, cls.get_edit_link),
            (cls.ACTION_POST_ADD_ASSESSMENT, cls.post_add_assessment),
            (cls.ACTION_GET_EDIT_ASSESSMENT, cls.get_edit_assessment),
            (cls.ACTION_POST_ADD_CUSTOM_UNIT, cls.post_add_custom_unit),
            (cls.ACTION_GET_EDIT_CUSTOM_UNIT, cls.get_edit_custom_unit),
            ):

            if callback.__name__.startswith('get_'):
                dashboard.DashboardHandler.add_custom_get_action(
                    action, callback, in_action='outline')
            elif callback.__name__.startswith('post_'):
                dashboard.DashboardHandler.add_custom_post_action(
                    action, callback)
            else:
                raise ValueError('Callback names must start with get_ or post_')

        # Tell dashboard we want to handle authorization of viewing of
        # unit/assessment/link editors ourselves, rather than using a single
        # permission name.  (This uses detailed schema permissions authority
        # checks instead.)
        dashboard.DashboardHandler.map_get_action_to_permission_checker(
            cls.ACTION_GET_EDIT_UNIT, UnitRESTHandler.can_view)
        dashboard.DashboardHandler.map_get_action_to_permission_checker(
            cls.ACTION_GET_EDIT_LINK, LinkRESTHandler.can_view)
        dashboard.DashboardHandler.map_get_action_to_permission_checker(
            cls.ACTION_GET_EDIT_ASSESSMENT, AssessmentRESTHandler.can_view)

    @classmethod
    def get_import_course(cls, handler):
        """Shows setup form for course import."""

        template_values = {}
        template_values['page_title'] = handler.format_title('Import Course')
        annotations = ImportCourseRESTHandler.SCHEMA_ANNOTATIONS_DICT()
        if not annotations:
            template_values['main_content'] = 'No courses to import from.'
            handler.render_page(template_values)
            return

        exit_url = handler.canonicalize_url('/dashboard')
        rest_url = handler.canonicalize_url(ImportCourseRESTHandler.URI)
        form_html = oeditor.ObjectEditor.get_html_for(
            handler,
            ImportCourseRESTHandler.SCHEMA_JSON,
            annotations,
            None, rest_url, exit_url,
            auto_return=True,
            save_button_caption='Import',
            required_modules=ImportCourseRESTHandler.REQUIRED_MODULES)

        template_values = {}
        template_values['page_title'] = handler.format_title('Import Course')
        template_values['main_content'] = form_html
        return template_values

    @classmethod
    def post_cancel_import(cls, handler):
        # Dashboard dispatch will have checked XSRF and admin privileges.
        ImportCourseBackgroundJob(handler.app_context, None).cancel()
        handler.redirect('/dashboard?action=outline')

    @classmethod
    def post_add_lesson(cls, handler):
        """Adds new lesson to a first unit of the course."""
        course = courses.Course(handler)
        target_unit = None
        if handler.request.get('unit_id'):
            target_unit = course.find_unit_by_id(handler.request.get('unit_id'))
        else:
            for unit in course.get_units():
                if unit.type == verify.UNIT_TYPE_UNIT:
                    target_unit = unit
                    break
        if target_unit:
            lesson = course.add_lesson(target_unit)
            course.save()
            # TODO(psimakov): complete 'edit_lesson' view
            handler.redirect(handler.get_action_url(
                'edit_lesson', key=lesson.lesson_id,
                extra_args={'is_newly_created': 1}))
        else:
            handler.redirect('/dashboard')

    @classmethod
    def post_add_unit(cls, handler):
        """Adds new unit to a course."""
        course = courses.Course(handler)
        unit = course.add_unit()
        course.save()
        handler.redirect(handler.get_action_url(
            'edit_unit', key=unit.unit_id, extra_args={'is_newly_created': 1}))

    @classmethod
    def post_add_link(cls, handler):
        """Adds new link to a course."""
        course = courses.Course(handler)
        link = course.add_link()
        link.href = ''
        course.save()
        handler.redirect(handler.get_action_url(
            'edit_link', key=link.unit_id, extra_args={'is_newly_created': 1}))

    @classmethod
    def post_add_assessment(cls, handler):
        """Adds new assessment to a course."""
        course = courses.Course(handler)
        assessment = course.add_assessment()
        course.save()
        handler.redirect(handler.get_action_url(
            'edit_assessment', key=assessment.unit_id,
            extra_args={'is_newly_created': 1}))

    @classmethod
    def post_add_custom_unit(cls, handler):
        """Adds a custom unit to a course."""
        course = courses.Course(handler)
        custom_unit_type = handler.request.get('unit_type')
        custom_unit = course.add_custom_unit(custom_unit_type)
        course.save()
        handler.redirect(handler.get_action_url(
            'edit_custom_unit', key=custom_unit.unit_id,
            extra_args={'is_newly_created': 1,
                        'unit_type': custom_unit_type}))

    @classmethod
    def _render_edit_form_for(
        cls, handler, rest_handler_cls, title, schema, additional_dirs=None,
        annotations_dict=None, delete_xsrf_token='delete-unit',
        delete_message=None, extra_js_files=None, extra_css_files=None):
        """Renders an editor form for a given REST handler class."""
        annotations_dict = annotations_dict or []
        schema_json = schema.get_json_schema()
        annotations_dict = schema.get_schema_dict() + annotations_dict

        key = handler.request.get('key')

        extra_args = {}
        if handler.request.get('is_newly_created'):
            extra_args['is_newly_created'] = 1

        exit_url = handler.canonicalize_url('/dashboard')
        rest_url = handler.canonicalize_url(rest_handler_cls.URI)
        delete_method = None
        delete_url = None
        if roles.Roles.is_course_admin(handler.app_context):
            delete_method = 'delete'
            delete_url = '%s?%s' % (
                handler.canonicalize_url(rest_handler_cls.URI),
                urllib.urlencode({
                    'key': key,
                    'xsrf_token': cgi.escape(
                        handler.create_xsrf_token(delete_xsrf_token))
                    }))

        def extend_list(target_list, ext_name):
            # Extend the optional arg lists such as extra_js_files by an
            # optional list field on the REST handler class. Used to provide
            # seams for modules to add js files, etc. See LessonRESTHandler
            if hasattr(rest_handler_cls, ext_name):
                target_list = target_list or []
                return (target_list or []) + getattr(rest_handler_cls, ext_name)
            return target_list

        form_html = oeditor.ObjectEditor.get_html_for(
            handler,
            schema_json,
            annotations_dict,
            key, rest_url, exit_url,
            additional_dirs=extend_list(additional_dirs, 'ADDITIONAL_DIRS'),
            delete_url=delete_url,
            delete_method=delete_method,
            delete_message=delete_message,
            display_types=schema.get_display_types(),
            extra_args=extra_args,
            extra_css_files=extend_list(extra_css_files, 'EXTRA_CSS_FILES'),
            extra_js_files=extend_list(extra_js_files, 'EXTRA_JS_FILES'),
            read_only=not handler.app_context.is_editable_fs())

        template_values = {}
        template_values['page_title'] = handler.format_title('Edit %s' % title)
        template_values['main_content'] = form_html
        return template_values

    @classmethod
    def get_edit_unit(cls, handler):
        """Shows unit editor."""
        return cls._render_edit_form_for(
            handler, UnitRESTHandler, 'Unit', UnitRESTHandler.get_schema(
                courses.Course(handler), int(handler.request.get('key'))),
            delete_message='Are you sure you want to delete this unit? '
            'Deleting the unit will also delete any lessons it contains.')

    @classmethod
    def get_edit_custom_unit(cls, handler):
        """Shows custom_unit_editor."""
        custom_unit_type = handler.request.get('unit_type')
        custom_unit = custom_units.UnitTypeRegistry.get(custom_unit_type)
        rest_handler = custom_unit.rest_handler
        return cls._render_edit_form_for(
            handler, rest_handler, custom_unit.name,
            rest_handler.get_schema(courses.Course(handler)))

    @classmethod
    def get_edit_link(cls, handler):
        """Shows link editor."""
        return cls._render_edit_form_for(
            handler, LinkRESTHandler, 'Link', LinkRESTHandler.get_schema(
                courses.Course(handler), int(handler.request.get('key'))))

    @classmethod
    def get_edit_assessment(cls, handler):
        """Shows assessment editor."""
        return cls._render_edit_form_for(
            handler, AssessmentRESTHandler, 'Assessment',
            AssessmentRESTHandler.get_schema(
                courses.Course(handler), int(handler.request.get('key'))),
            extra_js_files=['assessment_editor_lib.js', 'assessment_editor.js'])

    @classmethod
    def get_edit_lesson(cls, handler):
        """Shows the lesson/activity editor."""
        key = handler.request.get('key')
        course = courses.Course(handler)
        lesson = course.find_lesson_by_id(None, key)
        annotations_dict = (
            None if lesson.has_activity else cls.HIDE_ACTIVITY_ANNOTATIONS)
        schema = LessonRESTHandler.get_schema(course, key)
        if courses.has_only_new_style_activities(course):
            schema.get_property('objectives').extra_schema_dict_values[
              'excludedCustomTags'] = set(['gcb-activity'])
        return cls._render_edit_form_for(
            handler,
            LessonRESTHandler, 'Lessons and Activities', schema,
            annotations_dict=annotations_dict,
            delete_xsrf_token='delete-lesson',
            extra_js_files=['lesson_editor.js'])


    @classmethod
    def get_in_place_lesson_editor(cls, handler):
        """Shows the lesson editor iframed inside a lesson page."""
        if not handler.app_context.is_editable_fs():
            return

        key = handler.request.get('key')

        course = courses.Course(handler)
        lesson = course.find_lesson_by_id(None, key)
        annotations_dict = (
            None if lesson.has_activity else cls.HIDE_ACTIVITY_ANNOTATIONS)
        schema = LessonRESTHandler.get_schema(course, key)
        annotations_dict = schema.get_schema_dict() + annotations_dict

        if courses.has_only_new_style_activities(course):
            schema.get_property('objectives').extra_schema_dict_values[
              'excludedCustomTags'] = set(['gcb-activity'])

        extra_js_files = [
            'lesson_editor.js', 'in_place_lesson_editor_iframe.js'
        ] + LessonRESTHandler.EXTRA_JS_FILES

        form_html = oeditor.ObjectEditor.get_html_for(
            handler,
            schema.get_json_schema(),
            annotations_dict,
            key, handler.canonicalize_url(LessonRESTHandler.URI), None,
            additional_dirs=LessonRESTHandler.ADDITIONAL_DIRS,
            display_types=schema.get_display_types(),
            extra_css_files=LessonRESTHandler.EXTRA_CSS_FILES,
            extra_js_files=extra_js_files)
        template = handler.get_template('in_place_lesson_editor.html', [])
        template_values = {
            'form_html': form_html,
            'extra_css_href_list': handler.EXTRA_CSS_HREF_LIST,
            'extra_js_href_list': handler.EXTRA_JS_HREF_LIST
        }
        handler.response.write(template.render(template_values))


class CommonUnitRESTHandler(utils.BaseRESTHandler):
    """A common super class for all unit REST handlers."""

    # These functions are called with an updated unit object whenever a
    # change is saved.
    POST_SAVE_HOOKS = []

    def unit_to_dict(self, unit):
        """Converts a unit to a dictionary representation."""
        return resources_display.UnitTools(self.get_course()).unit_to_dict(unit)

    def apply_updates(self, unit, updated_unit_dict, errors):
        """Applies changes to a unit; modifies unit input argument."""
        resources_display.UnitTools(courses.Course(self)).apply_updates(
            unit, updated_unit_dict, errors)

    def can_view(self):
        raise NotImplementedError()

    def can_edit(self):
        raise NotImplementedError()

    @classmethod
    def get_schema(cls, course, key):
        raise NotImplementedError()

    def get(self):
        """A GET REST method shared by all unit types."""
        key = self.request.get('key')

        if not self.can_view(self.app_context):
            transforms.send_json_response(
                self, 401, 'Access denied.', {'key': key})
            return

        course = courses.Course(self)
        unit = course.find_unit_by_id(key)
        if not unit:
            transforms.send_json_response(
                self, 404, 'Object not found.', {'key': key})
            return

        message = ['Success.']
        if self.request.get('is_newly_created'):
            unit_type = verify.UNIT_TYPE_NAMES[unit.type].lower()
            message.append(
                'New %s has been created and saved.' % unit_type)

        entity = self.unit_to_dict(unit)
        schema = self.get_schema(course, key)
        schema.redact_entity_to_schema(entity, only_writable=False)

        transforms.send_json_response(
            self, 200, '\n'.join(message),
            payload_dict=transforms.dict_to_json(entity, recurse=True),
            xsrf_token=crypto.XsrfTokenManager.create_xsrf_token('put-unit'))

    def put(self):
        """A PUT REST method shared by all unit types."""
        request = transforms.loads(self.request.get('request'))
        key = request.get('key')

        if not self.assert_xsrf_token_or_fail(
                request, 'put-unit', {'key': key}):
            return

        if not self.can_edit(self.app_context):
            transforms.send_json_response(
                self, 401, 'Access denied.', {'key': key})
            return

        unit = courses.Course(self).find_unit_by_id(key)
        if not unit:
            transforms.send_json_response(
                self, 404, 'Object not found.', {'key': key})
            return

        payload = request.get('payload')
        errors = []

        course = courses.Course(self)
        try:
            schema = self.get_schema(course, key)
            updated_unit_dict = transforms.json_to_dict(
                transforms.loads(payload), schema.get_json_schema_dict())
            schema.redact_entity_to_schema(updated_unit_dict)
            self.apply_updates(unit, updated_unit_dict, errors)
        except (TypeError, ValueError), ex:
            errors.append(str(ex))

        if not errors:
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

        if not roles.Roles.is_course_admin(self.app_context):
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

    @classmethod
    def can_view(cls, app_context):
        return permissions.can_view(app_context, constants.SCOPE_UNIT)

    @classmethod
    def can_edit(cls, app_context):
        return permissions.can_edit(app_context, constants.SCOPE_UNIT)

    @classmethod
    def get_schema(cls, course, this_unit_id):
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

        schema = resources_display.ResourceUnit.get_schema(course, this_unit_id)
        choices = [(-1, '-- None --')]
        for assessment_id in sorted(available_assessments):
            choices.append(
                (assessment_id, available_assessments[assessment_id].title))
        schema.get_property('pre_assessment').set_select_data(choices)
        schema.get_property('post_assessment').set_select_data(choices)

        permissions.SchemaPermissionRegistry.redact_schema_to_permitted_fields(
            course.app_context, constants.SCOPE_UNIT, schema)
        return schema


class LinkRESTHandler(CommonUnitRESTHandler):
    """Provides REST API to link."""

    URI = '/rest/course/link'

    @classmethod
    def can_view(cls, app_context):
        return permissions.can_view(app_context, constants.SCOPE_LINK)

    @classmethod
    def can_edit(cls, app_context):
        return permissions.can_edit(app_context, constants.SCOPE_LINK)

    @classmethod
    def get_schema(cls, course, key):
        schema = resources_display.ResourceLink.get_schema(course, key)
        permissions.SchemaPermissionRegistry.redact_schema_to_permitted_fields(
            course.app_context, constants.SCOPE_LINK, schema)
        return schema


class ImportCourseRESTHandler(utils.BaseRESTHandler):
    """Provides REST API to course import."""

    URI = '/rest/course/import'
    ACTION = 'import-course'

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
        'inputex-string', 'inputex-select', 'gcb-uneditable']

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
    def SCHEMA_ANNOTATIONS_DICT(cls):
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
        if not roles.Roles.is_course_admin(self.app_context):
            transforms.send_json_response(self, 401, 'Access denied.', {})
            return

        first_course_in_dropdown = self._get_course_list()[0]['value']

        transforms.send_json_response(
            self, 200, None,
            payload_dict={'course': first_course_in_dropdown},
            xsrf_token=crypto.XsrfTokenManager.create_xsrf_token(self.ACTION))

    def put(self):
        """Handles REST PUT verb with JSON payload."""
        request = transforms.loads(self.request.get('request'))

        if not self.assert_xsrf_token_or_fail(
                request, self.ACTION, {'key': None}):
            return

        if not roles.Roles.is_course_admin(self.app_context):
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

        import_job = ImportCourseBackgroundJob(
            self.app_context, source.get_namespace_name())
        if import_job.is_active():
            transforms.send_json_response(
                self, 503, 'Import already in progress.', {'raw': course_raw})
            return
        try:
            status = import_job.submit()
            error_starting = (status < 0)
        except Exception:  # pylint: disable=broad-except
            error_starting = True
        if error_starting:
            transforms.send_json_response(
                self, 500, 'Could not start import.', {'raw': course_raw})
            return

        transforms.send_json_response(self, 200, 'Importing.')

class ImportCourseBackgroundJob(jobs.DurableJob):

    def __init__(self, app_context, from_namespace):
        super(ImportCourseBackgroundJob, self).__init__(app_context)
        self._from_namespace = from_namespace

    @db.transactional
    def load_status(self, context):
        return ImportCourseBackgroundJob(context, None).load()

    def run(self):
        to_context = sites.get_app_context_for_namespace(self._namespace)
        course = courses.Course(None, app_context=to_context)
        from_context = sites.get_app_context_for_namespace(self._from_namespace)
        start_status = self.load()
        errors = []
        course.import_from(from_context, errors)
        if errors:
            for error in errors:
                logging.error(error)
            raise RuntimeError(
                'Import course from %s to %s job encountered errors; see '
                'App Engine logs for details.' %
                (self._from_namespace, self._namespace))
        elif self._already_finished(start_status.sequence_num):
            # Importing a course takes a good long time -- over 60s
            # for a large course on an F1 instance.  Entirely concievable
            # that an import may have been canceled while import_from()
            # was working.
            raise RuntimeError(
                'Import course from %s to %s job was canceled or '
                'a subsequent run has already completed; not saving '
                'this work.' % (self._from_namespace, self._namespace))
        else:
            course.save()


class AssessmentRESTHandler(CommonUnitRESTHandler):
    """Provides REST API to assessment."""

    URI = '/rest/course/assessment'

    @classmethod
    def get_schema(cls, course, key):
        schema = resources_display.ResourceAssessment.get_schema(course, key)

        reg = schema_fields.FieldRegistry('')
        reg.add_property(schema_fields.SchemaField(
            'snippet', 'Embed Link', 'text', optional=True,
            extra_schema_dict_values={
                'disabled': True,
                'className': 'inputEx-Field embed-code-snippet-display'},
            description=services.help_urls.make_learn_more_message(
                messages.EMBED_ASSESSMENT_DESCRIPTION,
                'course:assessment:snippet')))
        schema.add_sub_registry('embed', '', registry=reg)

        permissions.SchemaPermissionRegistry.redact_schema_to_permitted_fields(
            course.app_context, constants.SCOPE_ASSESSMENT, schema)
        return schema

    def unit_to_dict(self, unit):
        unit_dict = super(AssessmentRESTHandler, self).unit_to_dict(unit)
        unit_dict['embed'] = {
            'snippet': assessments.AssessmentEmbed.get_embed_snippet(
                self, unit.unit_id)
        }
        return unit_dict

    @classmethod
    def can_view(cls, app_context):
        return permissions.can_view(app_context, constants.SCOPE_ASSESSMENT)

    @classmethod
    def can_edit(cls, app_context):
        return permissions.can_edit(app_context, constants.SCOPE_ASSESSMENT)


class UnitLessonTitleRESTHandler(utils.BaseRESTHandler):
    """Provides REST API to reorder unit and lesson titles."""

    URI = '/rest/course/outline'
    XSRF_TOKEN = 'unit-lesson-reorder'

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

    def put(self):
        """Handles REST PUT verb with JSON payload."""
        request = transforms.loads(self.request.get('request'))

        if not self.assert_xsrf_token_or_fail(
                request, self.XSRF_TOKEN, {'key': None}):
            return

        if not roles.Roles.is_user_allowed(
            self.app_context, custom_module,
            constants.COURSE_OUTLINE_REORDER_PERMISSION):

            transforms.send_json_response(self, 401, 'Access denied.', {})
            return


        payload = request.get('payload')
        payload_dict = transforms.json_to_dict(
            transforms.loads(payload), self.SCHEMA_DICT)
        course = courses.Course(self)
        course.reorder_units(payload_dict['outline'])
        course.save()

        transforms.send_json_response(self, 200, 'Saved.')


class LessonRESTHandler(utils.BaseRESTHandler):
    """Provides REST API to handle lessons and activities."""

    URI = '/rest/course/lesson'

    # Enable modules to specify locations to load JS and CSS files
    ADDITIONAL_DIRS = []
    # Enable modules to add css files to be shown in the editor page.
    EXTRA_CSS_FILES = []
    # Enable modules to add js files to be shown in the editor page.
    EXTRA_JS_FILES = []

    # Enable other modules to add transformations to the schema.Each member must
    # be a function of the form:
    #     callback(lesson_field_registry)
    # where the argument is the root FieldRegistry for the schema
    SCHEMA_LOAD_HOOKS = []

    # Enable other modules to add transformations to the load. Each member must
    # be a function of the form:
    #     callback(lesson, lesson_dict)
    # and the callback should update fields of the lesson_dict, which will be
    # returned to the caller of a GET request.
    PRE_LOAD_HOOKS = []

    # Enable other modules to add transformations to the save. Each member must
    # be a function of the form:
    #     callback(lesson, lesson_dict)
    # and the callback should update fields of the lesson with values read from
    # the dict which was the payload of a PUT request.
    PRE_SAVE_HOOKS = []

    # These functions are called with an updated lesson object whenever a
    # change is saved.
    POST_SAVE_HOOKS = []

    @classmethod
    def get_schema(cls, course, key):
        lesson_schema = resources_display.ResourceLesson.get_schema(course, key)
        common_utils.run_hooks(cls.SCHEMA_LOAD_HOOKS, lesson_schema)
        return lesson_schema

    @classmethod
    def get_lesson_dict(cls, course, lesson):
        return cls.get_lesson_dict_for(course, lesson)

    @classmethod
    def get_lesson_dict_for(cls, course, lesson):
        lesson_dict = resources_display.ResourceLesson.get_data_dict(
            course, lesson.lesson_id)
        common_utils.run_hooks(cls.PRE_LOAD_HOOKS, lesson, lesson_dict)
        return lesson_dict

    def get(self):
        """Handles GET REST verb and returns lesson object as JSON payload."""

        if not roles.Roles.is_course_admin(self.app_context):
            transforms.send_json_response(self, 401, 'Access denied.', {})
            return

        key = self.request.get('key')
        course = courses.Course(self)
        lesson = course.find_lesson_by_id(None, key)
        assert lesson
        payload_dict = self.get_lesson_dict(course, lesson)

        message = ['Success.']
        if self.request.get('is_newly_created'):
            message.append('New lesson has been created and saved.')

        transforms.send_json_response(
            self, 200, '\n'.join(message),
            payload_dict=payload_dict,
            xsrf_token=crypto.XsrfTokenManager.create_xsrf_token('lesson-edit'))

    def put(self):
        """Handles PUT REST verb to save lesson and associated activity."""
        request = transforms.loads(self.request.get('request'))
        key = request.get('key')

        if not self.assert_xsrf_token_or_fail(
                request, 'lesson-edit', {'key': key}):
            return

        if not roles.Roles.is_course_admin(self.app_context):
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
            self.get_schema(course, key).get_json_schema_dict())

        lesson.title = updates_dict['title']
        lesson.unit_id = common_utils.find(
            lambda unit: unit['selected'], updates_dict['unit_id'])['value']
        lesson.scored = (updates_dict['scored'] == 'scored')
        lesson.objectives = updates_dict['objectives']
        lesson.video = updates_dict['video']
        lesson.notes = updates_dict['notes']
        lesson.auto_index = updates_dict['auto_index']
        lesson.activity_title = updates_dict['activity_title']
        lesson.activity_listed = updates_dict['activity_listed']
        lesson.manual_progress = updates_dict['manual_progress']

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
            common_utils.run_hooks(self.PRE_SAVE_HOOKS, lesson, updates_dict)
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

        if not roles.Roles.is_course_admin(self.app_context):
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


def get_namespaced_handlers():
    return [
        (AssessmentRESTHandler.URI, AssessmentRESTHandler),
        (ImportCourseRESTHandler.URI, ImportCourseRESTHandler),
        (LessonRESTHandler.URI, LessonRESTHandler),
        (LinkRESTHandler.URI, LinkRESTHandler),
        (UnitLessonTitleRESTHandler.URI, UnitLessonTitleRESTHandler),
        (UnitRESTHandler.URI, UnitRESTHandler),
    ]


def on_module_enabled(courses_custom_module, module_permissions):
    global custom_module  # pylint: disable=global-statement
    custom_module = courses_custom_module

    UnitLessonEditor.on_module_enabled()

    module_permissions.extend([
        roles.Permission(
            constants.COURSE_OUTLINE_REORDER_PERMISSION,
            'Can re-order units and lessons'),
        ])

    # Course admins can always edit all fields in units/assessments/links
    permissions.SchemaPermissionRegistry.add(
        constants.SCOPE_UNIT, permissions.CourseAdminSchemaPermission())
    permissions.SchemaPermissionRegistry.add(
        constants.SCOPE_ASSESSMENT, permissions.CourseAdminSchemaPermission())
    permissions.SchemaPermissionRegistry.add(
        constants.SCOPE_LINK, permissions.CourseAdminSchemaPermission())
