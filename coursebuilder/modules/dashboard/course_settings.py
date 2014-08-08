# Copyright 2012 Google Inc. All Rights Reserved.
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

"""Classes supporting updates to basic course settings."""

__author__ = 'Abhinav Khandelwal (abhinavk@google.com)'

import cgi
import urllib
import yaml

from common import schema_fields
from controllers.utils import ApplicationHandler
from controllers.utils import BaseHandler
from controllers.utils import BaseRESTHandler
from controllers.utils import XsrfTokenManager
from models import courses
from models import roles
from models import transforms
from models import vfs
from modules.dashboard import filer
from modules.dashboard import messages
from modules.oeditor import oeditor


class CourseSettingsRights(object):
    """Manages view/edit rights for files."""

    @classmethod
    def can_view(cls, handler):
        return roles.Roles.is_course_admin(handler.app_context)

    @classmethod
    def can_edit(cls, handler):
        return roles.Roles.is_course_admin(handler.app_context)

    @classmethod
    def can_delete(cls, handler):
        return cls.can_edit(handler)

    @classmethod
    def can_add(cls, handler):
        return cls.can_edit(handler)


class CourseSettingsHandler(BaseHandler):
    """Course settings handler."""

    EXTRA_CSS_FILES = []
    EXTRA_JS_FILES = []
    ADDITIONAL_DIRS = []

    def post_edit_basic_course_settings(self):
        """Handles editing of course.yaml."""
        filer.create_course_file_if_not_exists(self)
        extra_args = {}
        section_names = self.request.get('section_names')
        if section_names:
            extra_args['section_names'] = section_names
        self.redirect(self.get_action_url(
            'edit_basic_settings', key='/course.yaml', extra_args=extra_args))

    def get_edit_basic_settings(self):
        """Shows editor for course.yaml."""

        key = self.request.get('key')

        # The editor for all course settings is getting rather large.  Here,
        # prune out all sections except the one named.  Names can name either
        # entire sub-registries, or a single item.  E.g., "course" selects all
        # items under the 'course' sub-registry, while
        # "base:before_head_tag_ends" selects just that one field.
        registry = courses.Course.create_settings_schema(self.get_course())

        section_names = self.request.get('section_names')
        if section_names:
            registry = registry.clone_only_items_named(section_names.split(':'))

        exit_url = self.canonicalize_url('/dashboard?action=settings')
        rest_url = self.canonicalize_url(CourseSettingsRESTHandler.URI)
        form_html = oeditor.ObjectEditor.get_html_for(
            self, registry.get_json_schema(), registry.get_schema_dict(),
            key, rest_url, exit_url, extra_css_files=self.EXTRA_CSS_FILES,
            extra_js_files=self.EXTRA_JS_FILES,
            additional_dirs=self.ADDITIONAL_DIRS,
            required_modules=CourseSettingsRESTHandler.REQUIRED_MODULES)

        template_values = {}
        template_values['page_title'] = self.format_title('Edit Settings')
        template_values['page_description'] = messages.EDIT_SETTINGS_DESCRIPTION
        template_values['main_content'] = form_html
        self.render_page(template_values)


class CourseYamlRESTHandler(BaseRESTHandler):
    """Common base for REST handlers in this file."""

    def validate_content(self, content):
        yaml.safe_load(content)

    def get_course_dict(self):
        return self.get_course().get_environ(self.app_context)

    def get(self):
        """Handles REST GET verb and returns an object as JSON payload."""
        assert self.app_context.is_editable_fs()

        key = self.request.get('key')

        if not CourseSettingsRights.can_view(self):
            transforms.send_json_response(
                self, 401, 'Access denied.', {'key': key})
            return

        # Load data if possible.
        fs = self.app_context.fs.impl
        filename = fs.physical_to_logical('/course.yaml')
        try:
            stream = fs.get(filename)
        except:  # pylint: disable=bare-except
            stream = None
        if not stream:
            transforms.send_json_response(
                self, 404, 'Object not found.', {'key': key})
            return

        # Prepare data.
        json_payload = self.process_get()
        transforms.send_json_response(
            self, 200, 'Success.',
            payload_dict=json_payload,
            xsrf_token=XsrfTokenManager.create_xsrf_token(self.XSRF_ACTION))

    def _save_content(self, content):
        try:
            self.validate_content(content)
            content_stream = vfs.string_to_stream(unicode(content))
        except Exception as e:  # pylint: disable=W0703
            transforms.send_json_response(self, 412, 'Validation error: %s' % e)
            return False

        # Store new file content.
        fs = self.app_context.fs.impl
        filename = fs.physical_to_logical('/course.yaml')
        fs.put(filename, content_stream)

        return True

    def put(self):
        """Handles REST PUT verb with JSON payload."""
        assert self.app_context.is_editable_fs()

        request_param = self.request.get('request')
        if not request_param:
            transforms.send_json_response(
                self, 400, 'Missing "request" parameter.')
            return
        try:
            request = transforms.loads(request_param)
        except ValueError:
            transforms.send_json_response(
                self, 400, 'Malformed "request" parameter.')
            return
        key = request.get('key')
        if not key:
            transforms.send_json_response(
                self, 400, 'Request missing "key" parameter.')
            return
        payload_param = request.get('payload')
        if not payload_param:
            transforms.send_json_response(
                self, 400, 'Request missing "payload" parameter.')
            return
        try:
            payload = transforms.loads(payload_param)
        except ValueError:
            transforms.send_json_response(
                self, 400, 'Malformed "payload" parameter.')
            return
        if not self.assert_xsrf_token_or_fail(
                request, self.XSRF_ACTION, {'key': key}):
            return
        if not CourseSettingsRights.can_edit(self):
            transforms.send_json_response(
                self, 401, 'Access denied.', {'key': key})
            return

        request_data = self.process_put(request, payload)
        if request_data:
            entity = courses.deep_dict_merge(
                request_data, self.get_course_dict())
            content = yaml.safe_dump(entity)
            if self._save_content(content):
                transforms.send_json_response(self, 200, 'Saved.')

    def delete(self):
        """Handles REST DELETE verb with JSON payload."""

        key = self.request.get('key')

        if not self.assert_xsrf_token_or_fail(
                self.request, self.XSRF_ACTION, {'key': key}):
            return

        if (not CourseSettingsRights.can_delete(self) or
            not self.is_deletion_allowed()):
            transforms.send_json_response(
                self, 401, 'Access denied.', {'key': key})
            return

        entity = self.process_delete()
        content = yaml.safe_dump(entity)
        if self._save_content(content):
            transforms.send_json_response(self, 200, 'Deleted.')


class CourseSettingsRESTHandler(CourseYamlRESTHandler):
    """Provides REST API for a file."""

    REQUIRED_MODULES = [
        'inputex-date', 'inputex-string', 'inputex-textarea', 'inputex-url',
        'inputex-checkbox', 'inputex-select', 'inputex-uneditable', 'gcb-rte']

    URI = '/rest/course/settings'

    XSRF_ACTION = 'basic-course-settings-put'

    def get_group_id(self, email):
        if not email or '@googlegroups.com' not in email:
            return None
        return email.split('@')[0]

    def get_groups_web_url(self, email):
        group_id = self.get_group_id(email)
        if not group_id:
            return None
        return 'https://groups.google.com/group/' + group_id

    def get_groups_embed_url(self, email):
        group_id = self.get_group_id(email)
        if not group_id:
            return None
        return 'https://groups.google.com/forum/embed/?place=forum/' + group_id

    def process_get(self):
        entity = {}
        schema = courses.Course.create_settings_schema(self.get_course())
        schema.convert_entity_to_json_entity(
            self.get_course_dict(), entity)

        json_payload = transforms.dict_to_json(
            entity, schema.get_json_schema_dict())

        return json_payload

    def process_put(self, request, payload):
        errors = []
        request_data = {}
        schema = courses.Course.create_settings_schema(self.get_course())
        schema.convert_json_to_entity(payload, request_data)
        schema.validate(request_data, errors)

        if errors:
            transforms.send_json_response(
                self, 400, 'Invalid data: \n' + '\n'.join(errors))
            return

        if 'course' in request_data:
            course_data = request_data['course']
            if 'forum_email' in course_data:
                forum_email = course_data['forum_email']
                forum_web_url = self.get_groups_web_url(forum_email)
                if forum_web_url:
                    course_data['forum_url'] = forum_web_url
                forum_web_url = self.get_groups_embed_url(forum_email)
                if forum_web_url:
                    course_data['forum_embed_url'] = forum_web_url

            if 'announcement_list_email' in course_data:
                announcement_email = course_data['announcement_list_email']
                announcement_web_url = self.get_groups_web_url(
                    announcement_email)
                if announcement_web_url:
                    course_data['announcement_list_url'] = announcement_web_url
        return request_data

    def is_deletion_allowed(self):
        return False


class HtmlHookHandler(ApplicationHandler):
    """Set up for OEditor manipulation of HTML hook contents.

    A separate handler and REST handler is required for hook contents,
    since the set of hooks is not statically known.  Users are free to add
    whatever hooks they want where-ever they want with fairly arbitrary
    names.  This class and its companion REST class deal with persisting the
    hook values into the course.yaml settings.
    """

    def post_edit_html_hook(self):
        filer.create_course_file_if_not_exists(self)
        self.redirect(self.get_action_url(
            'edit_html_hook', key=self.request.get('html_hook')))

    def get_edit_html_hook(self):
        key = self.request.get('key')

        registry = HtmlHookRESTHandler.REGISTRY
        exit_url = self.canonicalize_url(self.request.referer)
        rest_url = self.canonicalize_url(HtmlHookRESTHandler.URI)
        delete_url = '%s?%s' % (
            self.canonicalize_url(HtmlHookRESTHandler.URI),
            urllib.urlencode({
                'key': key,
                'xsrf_token': cgi.escape(
                        self.create_xsrf_token(HtmlHookRESTHandler.XSRF_ACTION))
            }))
        form_html = oeditor.ObjectEditor.get_html_for(
            self, registry.get_json_schema(), registry.get_schema_dict(),
            key, rest_url, exit_url,
            delete_url=delete_url, delete_method='delete',
            required_modules=HtmlHookRESTHandler.REQUIRED_MODULES)

        template_values = {}
        template_values['page_title'] = self.format_title('Edit Hook HTML')
        template_values['page_description'] = (
            messages.EDIT_HTML_HOOK_DESCRIPTION)
        template_values['main_content'] = form_html
        self.render_page(template_values)


def _create_hook_registry():
    reg = schema_fields.FieldRegistry('Html Hook', description='Html Hook')
    reg.add_property(schema_fields.SchemaField(
        'hook_content', 'HTML Hook Content', 'html',
        optional=True))
    return reg


class HtmlHookRESTHandler(CourseYamlRESTHandler):
    """REST API for individual HTML hook entries in course.yaml."""

    REGISTRY = _create_hook_registry()
    REQUIRED_MODULES = [
        'inputex-textarea', 'inputex-uneditable', 'gcb-rte', 'inputex-hidden']
    URI = '/rest/course/html_hook'
    XSRF_ACTION = 'html-hook-put'

    def process_get(self):
        course_dict = self.get_course_dict()
        html_hook = self.request.get('key')
        path = html_hook.split(':')
        for element in path:
            item = course_dict.get(element)
            if type(item) == dict:
                course_dict = item
        return {'hook_content': item}

    def process_put(self, request, payload):
        request_data = {}
        HtmlHookRESTHandler.REGISTRY.convert_json_to_entity(
            payload, request_data)
        if 'hook_content' not in request_data:
            transforms.send_json_response(
                self, 400, 'Payload missing "hook_content" parameter.')
            return None

        # Walk from bottom to top of hook element name building up
        # dict-in-dict until we are at outermost level, which is
        # the course_dict we will return.
        course_dict = request_data['hook_content']
        for element in reversed(request['key'].split(':')):
            course_dict = {element: course_dict}
        return course_dict

    def is_deletion_allowed(self):
        return True

    def process_delete(self):
        html_hook = self.request.get('key')
        course_dict = self.get_course_dict()
        pruned_dict = course_dict
        for element in html_hook.split(':'):
            if element in pruned_dict:
                if type(pruned_dict[element]) == dict:
                    pruned_dict = pruned_dict[element]
                else:
                    del pruned_dict[element]
        return course_dict
