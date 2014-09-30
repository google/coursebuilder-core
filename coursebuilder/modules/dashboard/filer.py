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

import messages
import yaml

import appengine_config
from common import schema_fields
from controllers.utils import ApplicationHandler
from controllers.utils import BaseRESTHandler
from controllers.utils import XsrfTokenManager
from models import courses
from models import roles
from models import transforms
from models import vfs
from modules.dashboard import utils as dashboard_utils
from modules.oeditor import oeditor

from google.appengine.api import users

# Set of string. The relative, normalized path bases we allow uploading of
# binary data into.
ALLOWED_ASSET_BINARY_BASES = frozenset([
    'assets/img',
])
# Set of string. The relative, normalized path bases we allow uploading of text
# data into.
ALLOWED_ASSET_TEXT_BASES = frozenset([
    'assets/css',
    'assets/html',
    'assets/lib',
    'views'
])

DISPLAYABLE_ASSET_BASES = frozenset([
    'assets/img',
])

MAX_ASSET_UPLOAD_SIZE_K = 500


def allowed_asset_upload_bases():
    """The relative, normalized path bases we allow uploading into.

    Returns:
        Set of string.
    """
    return ALLOWED_ASSET_BINARY_BASES.union(ALLOWED_ASSET_TEXT_BASES)


def is_text_payload(payload):
    try:
        transforms.dumps(payload)
        return True
    except:  # All errors are equivalently bad. pylint: disable=bare-except
        return False


def is_readonly_asset(asset):
    return not getattr(asset, 'metadata', None)


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

    local_fs = vfs.LocalReadOnlyFileSystem(logical_home_folder='/')

    def _get_delete_url(self, base_url, key, xsrf_token_name):
        return '%s?%s' % (
            self.canonicalize_url(base_url),
            urllib.urlencode({
                'key': key,
                'xsrf_token': cgi.escape(
                    self.create_xsrf_token(xsrf_token_name)),
            }))

    def post_create_or_edit_settings(self):
        """Handles creation or/and editing of course.yaml."""
        create_course_file_if_not_exists(self)
        extra_args = {}
        for name in ('tab', 'tab_title'):
            value = self.request.get(name)
            if value:
                extra_args[name] = value
        self.redirect(self.get_action_url('edit_settings', key='/course.yaml',
                                          extra_args=extra_args))

    def get_edit_settings(self):
        """Shows editor for course.yaml."""

        key = self.request.get('key')
        tab = self.request.get('tab')
        exit_url = self.canonicalize_url('/dashboard?action=settings&tab=%s' %
                                         tab)
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
        self.render_page(template_values, in_action='settings')

    def _is_displayable_asset(self, path):
        return any([path.startswith(name) for name in DISPLAYABLE_ASSET_BASES])

    def get_manage_asset(self):
        """Show an upload/delete dialog for assets."""

        key = self.request.get('key').lstrip('/').rstrip('/')
        if not _is_asset_in_allowed_bases(key):
            raise ValueError('Cannot add/edit asset with key "%s" ' % key +
                             'which is not under a valid asset path')
        fs = self.app_context.fs.impl

        delete_url = None
        delete_method = None
        delete_message = None
        auto_return = False
        if fs.isfile(fs.physical_to_logical(key)):
            delete_url = self._get_delete_url(
                FilesItemRESTHandler.URI, key, 'delete-asset')
            delete_method = 'delete'
        else:
            # Sadly, since we don't know the name of the asset when we build
            # the form, the form can't update itself to show the uploaded
            # asset when the upload completes.  Rather than continue to
            # show a blank form, bring the user back to the assets list.
            auto_return = True

        if self._is_displayable_asset(key):
            json = AssetItemRESTHandler.DISPLAYABLE_SCHEMA_JSON
            ann = AssetItemRESTHandler.DISPLAYABLE_SCHEMA_ANNOTATIONS_DICT
        else:
            json = AssetItemRESTHandler.UNDISPLAYABLE_SCHEMA_JSON
            ann = AssetItemRESTHandler.UNDISPLAYABLE_SCHEMA_ANNOTATIONS_DICT

        tab_name = self.request.get('tab')
        exit_url = self.canonicalize_url(
            dashboard_utils.build_assets_url(tab_name))
        rest_url = self.canonicalize_url(AssetItemRESTHandler.URI)

        form_html = oeditor.ObjectEditor.get_html_for(
            self, json, ann, key, rest_url, exit_url, save_method='upload',
            save_button_caption='Upload', auto_return=auto_return,
            delete_url=delete_url, delete_method=delete_method,
            delete_message=delete_message,
            required_modules=AssetItemRESTHandler.REQUIRED_MODULES,
            additional_dirs=[os.path.join(dashboard_utils.RESOURCES_DIR, 'js')])

        template_values = {}
        template_values['page_title'] = self.format_title('Manage Asset')
        template_values['page_description'] = messages.UPLOAD_ASSET_DESCRIPTION
        template_values['main_content'] = form_html
        self.render_page(template_values, 'assets', tab_name)

    def get_manage_text_asset(self):
        """Show an edit/save/delete/revert form for a text asset."""
        assert self.app_context.is_editable_fs()
        uri = self.request.get('uri')
        assert uri
        tab_name = self.request.get('tab')

        asset = self.app_context.fs.impl.get(
            os.path.join(appengine_config.BUNDLE_ROOT, uri))
        assert asset
        asset_in_datastore_fs = not is_readonly_asset(asset)

        try:
            asset_in_local_fs = bool(self.local_fs.get(uri))
        except IOError:
            asset_in_local_fs = False

        exit_url = self.canonicalize_url(
            dashboard_utils.build_assets_url(tab_name))
        rest_url = self.canonicalize_url(TextAssetRESTHandler.URI)

        delete_button_caption = 'Delete'
        delete_message = None
        delete_url = None

        if asset_in_datastore_fs:
            delete_message = 'Are you sure you want to delete %s?' % uri
            delete_url = self._get_delete_url(
                TextAssetRESTHandler.URI, uri,
                TextAssetRESTHandler.XSRF_TOKEN_NAME)

        if asset_in_local_fs:
            delete_message = (
                'Are you sure you want to restore %s to the original version? '
                'All your customizations will be lost.' % uri)
            delete_button_caption = 'Restore original'

        # Disable the save button if the payload is not text by setting method
        # to ''.
        save_method = 'put' if is_text_payload(asset.read()) else ''

        form_html = oeditor.ObjectEditor.get_html_for(
            self,
            TextAssetRESTHandler.SCHEMA.get_json_schema(),
            TextAssetRESTHandler.SCHEMA.get_schema_dict(),
            uri,
            rest_url,
            exit_url,
            delete_button_caption=delete_button_caption,
            delete_method='delete',
            delete_message=delete_message,
            delete_url=delete_url,
            required_modules=TextAssetRESTHandler.REQUIRED_MODULES,
            save_method=save_method,
        )
        self.render_page({
            'page_title': self.format_title('Edit ' + uri),
            'main_content': form_html,
        }, 'assets', tab_name)


def create_course_file_if_not_exists(handler):
    assert handler.app_context.is_editable_fs()

    # Check if course.yaml exists; create if not.
    fs = handler.app_context.fs.impl
    course_yaml = fs.physical_to_logical('/course.yaml')
    if not fs.isfile(course_yaml):
        fs.put(course_yaml, vfs.string_to_stream(
            courses.EMPTY_COURSE_YAML % users.get_current_user().email()))


def _match_allowed_bases(filename,
                         allowed_bases=allowed_asset_upload_bases()):
    for allowed_base in allowed_bases:
        if (filename == allowed_base or
            (filename.startswith(allowed_base) and
             len(filename) > len(allowed_base) and
             filename[len(allowed_base)] == '/')):
            return allowed_base
    return None


def _is_asset_in_allowed_bases(filename,
                               allowed_bases=allowed_asset_upload_bases()):
    matched_base = _match_allowed_bases(filename, allowed_bases)
    return True if matched_base else False


class TextAssetRESTHandler(BaseRESTHandler):
    """REST endpoints for text assets."""

    ERROR_MESSAGE_UNEDITABLE = (
        'Error: contents are not text and cannot be edited.')
    REQUIRED_MODULES = [
        'inputex-hidden',
        'inputex-textarea',
    ]
    SCHEMA = schema_fields.FieldRegistry('Edit asset', description='Text Asset')
    SCHEMA.add_property(schema_fields.SchemaField(
        'contents', 'Contents', 'text',
    ))
    SCHEMA.add_property(schema_fields.SchemaField(
        'is_text', 'Is Text', 'boolean', hidden=True,
    ))
    SCHEMA.add_property(schema_fields.SchemaField(
        'readonly', 'ReadOnly', 'boolean', hidden=True,
    ))
    URI = '/rest/assets/text'
    XSRF_TOKEN_NAME = 'manage-text-asset'

    def delete(self):
        """Handles the delete verb."""
        assert self.app_context.is_editable_fs()
        filename = self.request.get('key')

        if not (filename and self.assert_xsrf_token_or_fail(
                self.request, self.XSRF_TOKEN_NAME, {'key': filename})):
            return

        if not FilesRights.can_delete(self):
            transforms.send_json_response(
                self, 401, 'Access denied.', {'key': filename})
            return

        if not _is_asset_in_allowed_bases(filename):
            transforms.send_json_response(
                self, 400, 'Malformed request.', {'key': filename})
            return

        self.app_context.fs.impl.delete(
            os.path.join(appengine_config.BUNDLE_ROOT, filename))
        transforms.send_json_response(self, 200, 'Done.')

    def get(self):
        """Handles the get verb."""
        assert FilesRights.can_edit(self)
        filename = self.request.get('key')
        assert filename
        asset = self.app_context.fs.impl.get(
            os.path.join(appengine_config.BUNDLE_ROOT, filename))
        assert asset

        contents = asset.read()
        is_text = is_text_payload(contents)
        if not is_text:
            contents = self.ERROR_MESSAGE_UNEDITABLE
        json_message = 'Success.' if is_text else self.ERROR_MESSAGE_UNEDITABLE

        json_payload = {
            'contents': contents,
            'is_text': is_text,
            'readonly': is_readonly_asset(asset),
        }
        transforms.send_json_response(
            self, 200, json_message, payload_dict=json_payload,
            xsrf_token=XsrfTokenManager.create_xsrf_token(self.XSRF_TOKEN_NAME))

    def put(self):
        """Handles the put verb."""
        assert self.app_context.is_editable_fs()
        request = self.request.get('request')
        assert request
        request = transforms.loads(request)
        payload = transforms.loads(request.get('payload'))
        filename = request.get('key')

        if not (filename and self.assert_xsrf_token_or_fail(
                request, self.XSRF_TOKEN_NAME, {'key': filename})):
            return

        if not FilesRights.can_edit(self):
            transforms.send_json_response(
                self, 401, 'Access denied.', {'key': filename})
            return

        if not _is_asset_in_allowed_bases(filename):
            transforms.send_json_response(
                self, 400, 'Malformed request.', {'key': filename})
            return

        self.app_context.fs.impl.put(
            os.path.join(appengine_config.BUNDLE_ROOT, filename),
            vfs.string_to_stream(unicode(payload.get('contents'))))
        transforms.send_json_response(self, 200, 'Saved.')


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

    def validate_content(self, filename, content):
        # TODO(psimakov): handle more file types here
        if filename == '/course.yaml':
            courses.Course.validate_course_yaml(content, self.get_course())
        elif filename.endswith('.yaml'):
            yaml.safe_load(content)

    def get(self):
        """Handles REST GET verb and returns an object as JSON payload."""
        assert self.app_context.is_editable_fs()

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
        assert self.app_context.is_editable_fs()

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


def add_asset_handler_base_fields(schema):
    """Helper function for building schemas of asset-handling OEditor UIs."""

    schema.add_property(schema_fields.SchemaField(
        'file', 'Upload New File', 'file',
        optional=True,
        description='You may upload a file to set or replace the content '
        'of the asset.'))
    schema.add_property(schema_fields.SchemaField(
        'key', 'Key', 'string',
        editable=False,
        hidden=True))
    schema.add_property(schema_fields.SchemaField(
        'base', 'Base', 'string',
        editable=False,
        hidden=True))


def add_asset_handler_display_field(schema):
    """Helper function for building schemas of asset-handling OEditor UIs."""

    schema.add_property(schema_fields.SchemaField(
        'asset_url', 'Asset', 'string',
        editable=False,
        optional=True,
        description='This is the asset for the native language for the course.',
        extra_schema_dict_values={
            'visu': {
                'visuType': 'funcName',
                'funcName': 'renderAsset'
                }
            }))


def generate_asset_rest_handler_schema():
    schema = schema_fields.FieldRegistry('Asset', description='Asset')
    add_asset_handler_base_fields(schema)
    return schema


def generate_displayable_asset_rest_handler_schema():
    schema = schema_fields.FieldRegistry('Asset', description='Asset')
    add_asset_handler_display_field(schema)
    add_asset_handler_base_fields(schema)
    return schema


class AssetItemRESTHandler(BaseRESTHandler):
    """Provides REST API for managing assets."""

    URI = '/rest/assets/item'
    UNDISPLAYABLE_SCHEMA = generate_asset_rest_handler_schema()
    UNDISPLAYABLE_SCHEMA_JSON = UNDISPLAYABLE_SCHEMA.get_json_schema()
    UNDISPLAYABLE_SCHEMA_ANNOTATIONS_DICT = (
        UNDISPLAYABLE_SCHEMA.get_schema_dict())
    DISPLAYABLE_SCHEMA = generate_displayable_asset_rest_handler_schema()
    DISPLAYABLE_SCHEMA_JSON = DISPLAYABLE_SCHEMA.get_json_schema()
    DISPLAYABLE_SCHEMA_ANNOTATIONS_DICT = DISPLAYABLE_SCHEMA.get_schema_dict()
    REQUIRED_MODULES = [
        'inputex-string', 'inputex-uneditable', 'inputex-file',
        'inputex-hidden', 'io-upload-iframe']

    XSRF_TOKEN_NAME = 'asset-upload'

    def _can_write_payload_to_base(self, payload, base):
        """Determine if a given payload type can be put in a base directory."""
        # Binary data can go in images; text data can go anywhere else.
        if _is_asset_in_allowed_bases(base, ALLOWED_ASSET_BINARY_BASES):
            return True
        else:
            return is_text_payload(payload) and _is_asset_in_allowed_bases(
                base, ALLOWED_ASSET_TEXT_BASES)

    def get(self):
        """Provides empty initial content for asset upload editor."""
        # TODO(jorr): Pass base URI through as request param when generalized.
        key = self.request.get('key')
        base = _match_allowed_bases(key)
        if not base:
            transforms.send_json_response(
                self, 400, 'Malformed request.', {'key': key})
            return

        json_payload = {
            'key': key,
            'base': base,
        }
        fs = self.app_context.fs.impl
        if fs.isfile(fs.physical_to_logical(key)):
            json_payload['asset_url'] = key
        transforms.send_json_response(
            self, 200, 'Success.', payload_dict=json_payload,
            xsrf_token=XsrfTokenManager.create_xsrf_token(self.XSRF_TOKEN_NAME))

    def post(self):
        is_valid, payload, upload = self._validate_post()
        if is_valid:
            key = payload['key']
            base = payload['base']
            if key == base:
                # File name not given on setup; we are uploading a new file.
                filename = os.path.split(self.request.POST['file'].filename)[1]
                physical_path = os.path.join(base, filename)
                is_overwrite_allowed = False
            else:
                # File name already established on setup; use existing
                # file's name and uploaded file's data.
                physical_path = key
                is_overwrite_allowed = True
            self._handle_post(physical_path, is_overwrite_allowed, upload)

    def _validate_post(self):
        """Handles asset uploads."""
        assert self.app_context.is_editable_fs()

        if not FilesRights.can_add(self):
            transforms.send_file_upload_response(
                self, 401, 'Access denied.')
            return False, None, None

        request = transforms.loads(self.request.get('request'))
        if not self.assert_xsrf_token_or_fail(request, self.XSRF_TOKEN_NAME,
                                              None):
            return False, None, None

        upload = self.request.POST['file']
        if not isinstance(upload, cgi.FieldStorage):
            transforms.send_file_upload_response(
                self, 403, 'No file specified.')
            return False, None, None

        payload = transforms.loads(request['payload'])
        base = payload['base']
        if not _is_asset_in_allowed_bases(base):
            transforms.send_file_upload_response(
                self, 400, 'Malformed request.', {'key': base})
            return False, None, None

        content = upload.file.read()
        if not self._can_write_payload_to_base(content, base):
            transforms.send_file_upload_response(
                self, 403, 'Cannot write binary data to %s.' % base)
            return False, None, None

        if len(content) > MAX_ASSET_UPLOAD_SIZE_K * 1024:
            transforms.send_file_upload_response(
                self, 403,
                'Max allowed file upload size is %dK' % MAX_ASSET_UPLOAD_SIZE_K)
            return False, None, None

        return True, payload, upload

    def _handle_post(self, physical_path, is_overwrite_allowed, upload):
        fs = self.app_context.fs.impl
        path = fs.physical_to_logical(physical_path)
        if fs.isfile(path):
            if not is_overwrite_allowed:
                transforms.send_file_upload_response(
                    self, 403, 'Cannot overwrite existing file.')
                return
            else:
                fs.delete(path)

        upload.file.seek(0)
        fs.put(path, upload.file)
        transforms.send_file_upload_response(self, 200, 'Saved.')
