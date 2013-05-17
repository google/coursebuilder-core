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

from controllers.utils import ApplicationHandler
from controllers.utils import BaseRESTHandler
from controllers.utils import XsrfTokenManager
from models import courses
from models import roles
from models import transforms
from models import vfs
from modules.oeditor import oeditor
import yaml
import messages
from google.appengine.api import users


def is_editable_fs(app_context):
    return app_context.fs.impl.__class__ == vfs.DatastoreBackedFileSystem


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


class CourseSettingsHandler(ApplicationHandler):
    """Course settings handler."""

    def post_edit_basic_course_settings(self):
        """Handles editing of course.yaml."""
        assert is_editable_fs(self.app_context)

        # Check if course.yaml exists; create if not.
        fs = self.app_context.fs.impl
        course_yaml = fs.physical_to_logical('/course.yaml')
        if not fs.isfile(course_yaml):
            fs.put(course_yaml, vfs.string_to_stream(
                courses.EMPTY_COURSE_YAML % users.get_current_user().email()))

        self.redirect(self.get_action_url(
            'edit_basic_settings', key='/course.yaml'))

    def get_edit_basic_settings(self):
        """Shows editor for course.yaml."""

        key = self.request.get('key')

        exit_url = self.canonicalize_url('/dashboard?action=settings')
        rest_url = self.canonicalize_url('/rest/course/settings')
        form_html = oeditor.ObjectEditor.get_html_for(
            self,
            CourseSettingsRESTHandler.REGISTORY.get_json_schema(),
            CourseSettingsRESTHandler.REGISTORY.get_schema_dict(),
            key, rest_url, exit_url,
            required_modules=CourseSettingsRESTHandler.REQUIRED_MODULES)

        template_values = {}
        template_values['page_title'] = self.format_title('Edit Settings')
        template_values['page_description'] = messages.EDIT_SETTINGS_DESCRIPTION
        template_values['main_content'] = form_html
        self.render_page(template_values)


class CourseSettingsRESTHandler(BaseRESTHandler):
    """Provides REST API for a file."""

    REGISTORY = courses.create_course_registry()

    REQUIRED_MODULES = [
        'inputex-date', 'inputex-string', 'inputex-textarea', 'inputex-url',
        'inputex-checkbox', 'inputex-select', 'inputex-uneditable', 'gcb-rte']

    URI = '/rest/course/settings'

    @classmethod
    def validate_content(cls, content):
        yaml.safe_load(content)

    def get_course_dict(self):
        return self.get_course().get_environ(self.app_context)

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

    def get(self):
        """Handles REST GET verb and returns an object as JSON payload."""
        assert is_editable_fs(self.app_context)

        key = self.request.get('key')

        if not CourseSettingsRights.can_view(self):
            transforms.send_json_response(
                self, 401, 'Access denied.', {'key': key})
            return

        # Load data if possible.
        fs = self.app_context.fs.impl
        filename = fs.physical_to_logical(key)
        try:
            stream = fs.get(filename)
        except:  # pylint: disable=bare-except
            stream = None
        if not stream:
            transforms.send_json_response(
                self, 404, 'Object not found.', {'key': key})
            return

        # Prepare data.
        entity = {}
        CourseSettingsRESTHandler.REGISTORY.convert_entity_to_json_entity(
            self.get_course_dict(), entity)

        # Render JSON response.
        json_payload = transforms.dict_to_json(
            entity,
            CourseSettingsRESTHandler.REGISTORY.get_json_schema_dict())
        transforms.send_json_response(
            self, 200, 'Success.',
            payload_dict=json_payload,
            xsrf_token=XsrfTokenManager.create_xsrf_token(
                'basic-course-settings-put'))

    def put(self):
        """Handles REST PUT verb with JSON payload."""
        assert is_editable_fs(self.app_context)

        request = transforms.loads(self.request.get('request'))
        key = request.get('key')

        if not self.assert_xsrf_token_or_fail(
                request, 'basic-course-settings-put', {'key': key}):
            return

        if not CourseSettingsRights.can_edit(self):
            transforms.send_json_response(
                self, 401, 'Access denied.', {'key': key})
            return

        payload = request.get('payload')
        request_data = {}
        CourseSettingsRESTHandler.REGISTORY.convert_json_to_entity(
            transforms.loads(payload), request_data)

        course_data = request_data['course']
        if 'forum_email' in course_data.keys():
            forum_email = course_data['forum_email']
            forum_web_url = self.get_groups_web_url(forum_email)
            if forum_web_url:
                course_data['forum_url'] = forum_web_url
            forum_web_url = self.get_groups_embed_url(forum_email)
            if forum_web_url:
                course_data['forum_embed_url'] = forum_web_url

        if 'announcement_list_email' in course_data.keys():
            announcement_email = course_data['announcement_list_email']
            announcement_web_url = self.get_groups_web_url(announcement_email)
            if announcement_web_url:
                course_data['announcement_list_url'] = announcement_web_url

        entity = courses.deep_dict_merge(request_data, self.get_course_dict())
        content = yaml.safe_dump(entity)

        try:
            self.validate_content(content)
            content_stream = vfs.string_to_stream(unicode(content))
        except Exception as e:  # pylint: disable=W0703
            transforms.send_json_response(self, 412, 'Validation error: %s' % e)
            return

        # Store new file content.
        fs = self.app_context.fs.impl
        filename = fs.physical_to_logical(key)
        fs.put(filename, content_stream)

        # Send reply.
        transforms.send_json_response(self, 200, 'Saved.')

    def delete(self):
        """Handles REST DELETE verb."""

        request = transforms.loads(self.request.get('request'))
        key = request.get('key')
        transforms.send_json_response(
            self, 401, 'Access denied.', {'key': key})
