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

"""Classes supporting online file editing."""

__author__ = 'Pavel Simakov (psimakov@google.com)'


import base64
import json
from controllers.utils import ApplicationHandler
from controllers.utils import BaseRESTHandler
from controllers.utils import XsrfTokenManager
from models import roles
from models import transforms
from models import vfs
from modules.oeditor import oeditor
import yaml
from google.appengine.api import users


EMPTY_COURSE_YAML = u"""# my new course.yaml
course:
  title: 'New Course by %s'
"""

# general text file object schema
TEXT_FILE_SCHEMA_JSON = """
    {
        "id": "Text File",
        "type": "object",
        "description": "Text File",
        "properties": {
            "key" : {"type": "string"},
            "encoding" : {"type": "string"},
            "content": {"type": "text"},
            "is_draft": {"type": "boolean"}
            }
    }
    """

TEXT_FILE_SCHEMA_DICT = json.loads(TEXT_FILE_SCHEMA_JSON)

# inputex specific schema annotations to control editor look and feel
TEXT_FILE_SCHEMA_ANNOTATIONS_DICT = [
    (['title'], 'Text File'),
    (['properties', 'key', '_inputex'], {
        'label': 'ID', '_type': 'uneditable'}),
    (['properties', 'encoding', '_inputex'], {
        'label': 'Encoding', '_type': 'uneditable'}),
    (['properties', 'content', '_inputex'], {
        'label': 'Content', '_type': 'text'}),
    oeditor.create_bool_select_annotation(
        ['properties', 'is_draft'], 'Status', 'Draft', 'Published')]


def is_editable_fs(app_context):
    return app_context.fs.impl.__class__ == vfs.DatastoreBackedFileSystem


class FilesRights(object):
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


class FileManagerAndEditor(ApplicationHandler):
    """An editor for editing and managing files."""

    def post_create_or_edit_settings(self):
        """Handles creation or/and editing of course.yaml."""
        assert is_editable_fs(self.app_context)

        # Check if course.yaml exists; create if not.
        fs = self.app_context.fs.impl
        course_yaml = fs.physical_to_logical('/course.yaml')
        if not fs.isfile(course_yaml):
            fs.put(course_yaml, vfs.string_to_stream(
                EMPTY_COURSE_YAML % users.get_current_user().email()))

        self.redirect(self.get_action_url(
            'edit_settings', key='/course.yaml', canonicalize=False))

    def get_edit_settings(self):
        """Shows editor for course.yaml."""

        key = self.request.get('key')

        exit_url = self.canonicalize_url('/dashboard?action=settings')
        rest_url = self.canonicalize_url('/rest/files/item')
        form_html = oeditor.ObjectEditor.get_html_for(
            self, TEXT_FILE_SCHEMA_JSON, TEXT_FILE_SCHEMA_ANNOTATIONS_DICT,
            key, rest_url, exit_url)

        template_values = {}
        template_values['page_title'] = self.format_title('Edit Settings')
        template_values['main_content'] = form_html
        self.render_page(template_values)


class FilesItemRESTHandler(BaseRESTHandler):
    """Provides REST API for a file."""

    FILE_ENCODING_TEXT = 'text/utf-8'
    FILE_ENCODING_BINARY = 'binary/base64'
    FILE_EXTENTION_TEXT = ['.js', '.css', '.yaml', '.html', '.csv']

    @classmethod
    def is_text_file(cls, filename):
        # TODO(psimakov): this needs to be better and not use linear search
        for extention in cls.FILE_EXTENTION_TEXT:
            if filename.endswith(extention):
                return True
        return False

    @classmethod
    def validate_content(cls, filename, content):
        # TODO(psimakov): handle more file types here
        if filename.endswith('.yaml'):
            yaml.safe_load(content)

    def get(self):
        """Handles REST GET verb and returns an object as JSON payload."""
        assert is_editable_fs(self.app_context)

        key = self.request.get('key')
        if not FilesRights.can_view(self):
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
        entity = {'key': key, 'is_draft': stream.metadata.is_draft}
        if self.is_text_file(key):
            entity['encoding'] = self.FILE_ENCODING_TEXT
            entity['content'] = vfs.stream_to_string(stream)
        else:
            entity['encoding'] = self.FILE_ENCODING_BINARY
            entity['content'] = base64.b64encode(stream.read())

        # Render JSON response.
        json_payload = transforms.dict_to_json(entity, TEXT_FILE_SCHEMA_DICT)
        transforms.send_json_response(
            self, 200, 'Success.',
            payload_dict=json_payload,
            xsrf_token=XsrfTokenManager.create_xsrf_token(
                'file-put'))

    def put(self):
        """Handles REST PUT verb with JSON payload."""
        assert is_editable_fs(self.app_context)

        request = json.loads(self.request.get('request'))
        key = request.get('key')

        if not self.assert_xsrf_token_or_fail(
                request, 'file-put', {'key': key}):
            return

        # TODO(psimakov): we don't allow editing of all files; restrict further
        if not FilesRights.can_edit(self):
            transforms.send_json_response(
                self, 401, 'Access denied.', {'key': key})
            return

        payload = request.get('payload')
        entity = json.loads(payload)
        encoding = entity['encoding']
        content = entity['content']

        # Validate the file content.
        errors = []
        try:
            if encoding == self.FILE_ENCODING_TEXT:
                content_stream = vfs.string_to_stream(content)
            elif encoding == self.FILE_ENCODING_BINARY:
                content_stream = base64.b64decode(content)
            else:
                errors.append('Unknown encoding: %s.' % encoding)

            self.validate_content(key, content)
        except Exception as e:  # pylint: disable=W0703
            errors.append('Validation error: %s' % e)
        if errors:
            transforms.send_json_response(self, 412, ''.join(errors))
            return

        # Store new file content.
        fs = self.app_context.fs.impl
        filename = fs.physical_to_logical(key)
        fs.put(filename, content_stream, is_draft=entity['is_draft'])

        # Send reply.
        transforms.send_json_response(self, 200, 'Saved.')
