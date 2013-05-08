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
import cgi
import os
import urllib
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


ALLOWED_ASSET_UPLOAD_BASE = 'assets/img'

MAX_ASSET_UPLOAD_SIZE_K = 500


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
                courses.EMPTY_COURSE_YAML % users.get_current_user().email()))

        self.redirect(self.get_action_url('edit_settings', key='/course.yaml'))

    def get_edit_settings(self):
        """Shows editor for course.yaml."""

        key = self.request.get('key')

        exit_url = self.canonicalize_url('/dashboard?action=settings')
        rest_url = self.canonicalize_url('/rest/files/item')
        form_html = oeditor.ObjectEditor.get_html_for(
            self,
            FilesItemRESTHandler.SCHEMA_JSON,
            FilesItemRESTHandler.SCHEMA_ANNOTATIONS_DICT,
            key, rest_url, exit_url,
            required_modules=FilesItemRESTHandler.REQUIRED_MODULES)

        template_values = {}
        template_values['page_title'] = self.format_title('Edit Settings')
        template_values['page_description'] = messages.EDIT_SETTINGS_DESCRIPTION
        template_values['main_content'] = form_html
        self.render_page(template_values)

    def get_add_asset(self):
        """Show an upload dialog for assets."""

        exit_url = self.canonicalize_url('/dashboard?action=assets')
        rest_url = self.canonicalize_url(
            AssetItemRESTHandler.URI)
        form_html = oeditor.ObjectEditor.get_html_for(
            self,
            AssetItemRESTHandler.SCHEMA_JSON,
            AssetItemRESTHandler.SCHEMA_ANNOTATIONS_DICT,
            '', rest_url, exit_url, save_method='upload', auto_return=True,
            required_modules=AssetItemRESTHandler.REQUIRED_MODULES,
            save_button_caption='Upload')

        template_values = {}
        template_values['page_title'] = self.format_title('Upload Asset')
        template_values['page_description'] = messages.UPLOAD_ASSET_DESCRIPTION
        template_values['main_content'] = form_html
        self.render_page(template_values)

    def get_delete_asset(self):
        """Show an review/delete page for assets."""

        uri = self.request.get('uri')

        exit_url = self.canonicalize_url('/dashboard?action=assets')
        rest_url = self.canonicalize_url(
            AssetUriRESTHandler.URI)
        delete_url = '%s?%s' % (
            self.canonicalize_url(FilesItemRESTHandler.URI),
            urllib.urlencode({
                'key': uri,
                'xsrf_token': cgi.escape(self.create_xsrf_token('delete-asset'))
                }))
        form_html = oeditor.ObjectEditor.get_html_for(
            self,
            AssetUriRESTHandler.SCHEMA_JSON,
            AssetUriRESTHandler.SCHEMA_ANNOTATIONS_DICT,
            uri, rest_url, exit_url, save_method='',
            delete_url=delete_url, delete_method='delete')

        template_values = {}
        template_values['page_title'] = self.format_title('View Asset')
        template_values['main_content'] = form_html
        self.render_page(template_values)


class FilesItemRESTHandler(BaseRESTHandler):
    """Provides REST API for a file."""

    SCHEMA_JSON = """
        {
            "id": "Text File",
            "type": "object",
            "description": "Text File",
            "properties": {
                "key" : {"type": "string"},
                "encoding" : {"type": "string"},
                "content": {"type": "text"}
                }
        }
        """

    SCHEMA_DICT = transforms.loads(SCHEMA_JSON)

    SCHEMA_ANNOTATIONS_DICT = [
        (['title'], 'Text File'),
        (['properties', 'key', '_inputex'], {
            'label': 'ID', '_type': 'uneditable'}),
        (['properties', 'encoding', '_inputex'], {
            'label': 'Encoding', '_type': 'uneditable'}),
        (['properties', 'content', '_inputex'], {
            'label': 'Content', '_type': 'text'})]

    REQUIRED_MODULES = [
        'inputex-string', 'inputex-textarea', 'inputex-select',
        'inputex-uneditable']

    URI = '/rest/files/item'
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
        entity = {'key': key}
        if self.is_text_file(key):
            entity['encoding'] = self.FILE_ENCODING_TEXT
            entity['content'] = vfs.stream_to_string(stream)
        else:
            entity['encoding'] = self.FILE_ENCODING_BINARY
            entity['content'] = base64.b64encode(stream.read())

        # Render JSON response.
        json_payload = transforms.dict_to_json(
            entity,
            FilesItemRESTHandler.SCHEMA_DICT)
        transforms.send_json_response(
            self, 200, 'Success.',
            payload_dict=json_payload,
            xsrf_token=XsrfTokenManager.create_xsrf_token(
                'file-put'))

    def put(self):
        """Handles REST PUT verb with JSON payload."""
        assert is_editable_fs(self.app_context)

        request = transforms.loads(self.request.get('request'))
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
        entity = transforms.loads(payload)
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
        fs.put(filename, content_stream)

        # Send reply.
        transforms.send_json_response(self, 200, 'Saved.')

    def delete(self):
        """Handles REST DELETE verb."""

        key = self.request.get('key')

        if not self.assert_xsrf_token_or_fail(
                self.request, 'delete-asset', {'key': key}):
            return

        if not FilesRights.can_delete(self):
            transforms.send_json_response(
                self, 401, 'Access denied.', {'key': key})
            return

        fs = self.app_context.fs.impl
        path = fs.physical_to_logical(key)
        if not fs.isfile(path):
            transforms.send_json_response(
                self, 403, 'File does not exist.', None)
            return

        fs.delete(path)
        transforms.send_json_response(self, 200, 'Deleted.')


class AssetItemRESTHandler(BaseRESTHandler):
    """Provides REST API for managing assets."""

    URI = '/rest/assets/item'

    SCHEMA_JSON = """
        {
            "id": "Asset",
            "type": "object",
            "description": "Asset",
            "properties": {
                "base": {"type": "string"},
                "file": {"type": "string", "optional": true}
                }
        }
        """

    SCHEMA_ANNOTATIONS_DICT = [
        (['title'], 'Upload Asset'),
        (['properties', 'base', '_inputex'], {
            'label': 'Base', '_type': 'uneditable'}),
        (['properties', 'file', '_inputex'], {
            'label': 'File', '_type': 'file'})]

    REQUIRED_MODULES = [
        'inputex-string', 'inputex-uneditable', 'inputex-file',
        'io-upload-iframe']

    def get(self):
        """Provides empty initial content for asset upload editor."""
        # TODO(jorr): Pass base URI through as request param when generalized.
        json_payload = {'file': '', 'base': ALLOWED_ASSET_UPLOAD_BASE}
        transforms.send_json_response(
            self, 200, 'Success.', payload_dict=json_payload,
            xsrf_token=XsrfTokenManager.create_xsrf_token('asset-upload'))

    def post(self):
        """Handles asset uploads."""
        assert is_editable_fs(self.app_context)

        if not FilesRights.can_add(self):
            transforms.send_json_file_upload_response(
                self, 401, 'Access denied.')
            return

        request = transforms.loads(self.request.get('request'))
        if not self.assert_xsrf_token_or_fail(request, 'asset-upload', None):
            return

        payload = transforms.loads(request['payload'])
        base = payload['base']
        assert base == ALLOWED_ASSET_UPLOAD_BASE

        upload = self.request.POST['file']
        filename = os.path.split(upload.filename)[1]
        assert filename
        physical_path = os.path.join(base, filename)

        fs = self.app_context.fs.impl
        path = fs.physical_to_logical(physical_path)
        if fs.isfile(path):
            transforms.send_json_file_upload_response(
                self, 403, 'Cannot overwrite existing file.')
            return

        content = upload.file.read()
        upload.file.seek(0)
        if len(content) > MAX_ASSET_UPLOAD_SIZE_K * 1024:
            transforms.send_json_response(
                self, 403,
                'Max allowed file upload size is %dK' % MAX_ASSET_UPLOAD_SIZE_K,
                None)
            return

        fs.put(path, upload.file)
        transforms.send_json_file_upload_response(self, 200, 'Saved.')


class AssetUriRESTHandler(BaseRESTHandler):
    """Provides REST API for managing asserts by means of their URIs."""

    # TODO(jorr): Refactor the asset management classes to have more meaningful
    # REST URI's and class names
    URI = '/rest/assets/uri'

    SCHEMA_JSON = """
        {
            "id": "Asset",
            "type": "object",
            "description": "Asset",
            "properties": {
                "uri": {"type": "string"}
                }
        }
        """

    SCHEMA_ANNOTATIONS_DICT = [
        (['title'], 'Image or Document'),
        (['properties', 'uri', '_inputex'], {
            'label': 'Asset',
            '_type': 'uneditable',
            'visu': {
                'visuType': 'funcName',
                'funcName': 'renderAsset'}})]

    def get(self):
        """Handles REST GET verb and returns the uri of the asset."""

        uri = self.request.get('key')

        if not FilesRights.can_view(self):
            transforms.send_json_response(
                self, 401, 'Access denied.', {'key': uri})
            return

        transforms.send_json_response(
            self, 200, 'Success.',
            payload_dict={'uri': uri},
            xsrf_token=XsrfTokenManager.create_xsrf_token('asset-delete'))
