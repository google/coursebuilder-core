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
import collections
import os
import urllib

import yaml

import appengine_config
from common import schema_fields
from common import users
from controllers.utils import ApplicationHandler
from controllers.utils import BaseRESTHandler
from controllers.utils import XsrfTokenManager
from models import courses
from models import roles
from models import transforms
from models import vfs
from modules.dashboard import asset_paths
from modules.dashboard import messages
from modules.dashboard import utils as dashboard_utils
from modules.oeditor import oeditor


MAX_ASSET_UPLOAD_SIZE_K = 500


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

    _ASSET_TYPE_TO_CODEMIRROR_MODE = {
        'js':'javascript',
        'css':'css',
        'templates':'htmlmixed',
        'html':'htmlmixed',
    }

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
        from_action = self.request.get('from_action')
        if from_action:
            extra_args['from_action'] = from_action
        self.redirect(self.get_action_url('edit_settings', key='/course.yaml',
                                          extra_args=extra_args))

    def get_edit_settings(self):
        """Shows editor for course.yaml."""

        key = self.request.get('key')
        from_action = self.request.get('from_action')
        exit_url = self.canonicalize_url(
            '/dashboard?action={}'.format(from_action))
        rest_url = self.canonicalize_url('/rest/files/item')
        form_html = oeditor.ObjectEditor.get_html_for(
            self,
            FilesItemRESTHandler.SCHEMA_JSON,
            FilesItemRESTHandler.SCHEMA_ANNOTATIONS_DICT,
            key, rest_url, exit_url,
            required_modules=FilesItemRESTHandler.REQUIRED_MODULES)

        template_values = {}
        template_values['page_title'] = self.format_title('Edit Settings')
        template_values['main_content'] = form_html
        self.render_page(template_values, in_action=from_action)

    def get_manage_asset(self):
        """Show an upload/delete dialog for assets."""

        path = self.request.get('key')
        key = asset_paths.as_key(path)
        if not asset_paths.AllowedBases.is_path_allowed(path):
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

        details = AssetItemRESTHandler.get_schema_details(path)
        json, ann = details.json, details.annotations
        from_action = self.request.get('from_action')
        exit_url = self.canonicalize_url(
            dashboard_utils.build_assets_url(from_action))
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
        template_values['main_content'] = form_html

        self.render_page(template_values, in_action=from_action)

    def get_manage_text_asset(self):
        """Show an edit/save/delete/revert form for a text asset."""
        assert self.app_context.is_editable_fs()
        uri = self.request.get('uri')
        assert uri
        asset_type = self.request.get('type')
        from_action = self.request.get('from_action')

        mode = self._ASSET_TYPE_TO_CODEMIRROR_MODE.get(asset_type, '')

        asset = self.app_context.fs.impl.get(
            os.path.join(appengine_config.BUNDLE_ROOT, uri))
        assert asset
        asset_in_datastore_fs = not is_readonly_asset(asset)

        try:
            asset_in_local_fs = bool(self.local_fs.get(uri))
        except IOError:
            asset_in_local_fs = False

        exit_url = self.get_action_url(from_action)
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
        schema = TextAssetRESTHandler.get_asset_schema(mode)
        form_html = oeditor.ObjectEditor.get_html_for(
            self,
            schema.get_json_schema(),
            schema.get_schema_dict(),
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
        }, in_action=from_action)


def create_course_file_if_not_exists(handler):
    assert handler.app_context.is_editable_fs()

    # Check if course.yaml exists; create if not.
    fs = handler.app_context.fs.impl
    course_yaml = fs.physical_to_logical('/course.yaml')
    if not fs.isfile(course_yaml):
        fs.put(course_yaml, vfs.string_to_stream(
            courses.Course.EMPTY_COURSE_YAML %
            users.get_current_user().email()))


class TextAssetRESTHandler(BaseRESTHandler):
    """REST endpoints for text assets."""

    ERROR_MESSAGE_UNEDITABLE = (
        'Error: contents are not text and cannot be edited.')
    REQUIRED_MODULES = [
        'inputex-hidden',
        'inputex-textarea',
        'gcb-code',
    ]
    URI = '/rest/assets/text'
    XSRF_TOKEN_NAME = 'manage-text-asset'

    @classmethod
    def get_asset_schema(cls, mode):
        schema = schema_fields.FieldRegistry('Edit asset',
            description='Text Asset',
            extra_schema_dict_values={
                'className':'inputEx-Group new-form-layout hidden-header'
            })
        schema.add_property(schema_fields.SchemaField(
            'contents', 'Contents', 'text',
            extra_schema_dict_values={
                'mode': mode,
                '_type': 'code',
                'large': True,
            },
        ))
        schema.add_property(schema_fields.SchemaField(
            'is_text', 'Is Text', 'boolean', hidden=True,
        ))
        schema.add_property(schema_fields.SchemaField(
            'readonly', 'ReadOnly', 'boolean', hidden=True,
        ))
        return schema

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

        if not asset_paths.AllowedBases.is_path_allowed(filename):
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

        if not asset_paths.AllowedBases.is_path_allowed(filename):
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
        'gcb-uneditable']

    URI = '/rest/files/item'
    FILE_ENCODING_TEXT = 'text/utf-8'
    FILE_ENCODING_BINARY = 'binary/base64'
    FILE_EXTENSION_TEXT = frozenset(['.js', '.css', '.yaml', '.html', '.csv'])

    @classmethod
    def is_text_file(cls, filename):
        for extention in cls.FILE_EXTENSION_TEXT:
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
        json_payload = transforms.dict_to_json(entity)
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


def generate_asset_rest_handler_schema(name, description, displayable=False):
    """Helper function for building schemas of asset-handling OEditor UIs."""

    schema = schema_fields.FieldRegistry('Asset', description='Asset')
    schema.add_property(schema_fields.SchemaField(
        'file', name, 'file', description=description))
    schema.add_property(schema_fields.SchemaField(
        'key', 'Key', 'string', editable=False, hidden=True))
    schema.add_property(schema_fields.SchemaField(
        'base', 'Base', 'string', editable=False, hidden=True))

    location_dict = {}
    if displayable:
        location_dict['visu'] = {
            'visuType': 'funcName',
            'funcName': 'renderAsset'}

    schema.add_property(schema_fields.SchemaField(
        'asset_url', 'Location', 'string', editable=False, optional=True,
        extra_schema_dict_values=location_dict))
    return schema


_SchemaDetails = collections.namedtuple('_SchemaDetails',
                                        ['json', 'annotations'])

def _asset_schema_details(schema):
    return _SchemaDetails(json=schema.get_json_schema(),
                          annotations=schema.get_schema_dict())

class AssetItemRESTHandler(BaseRESTHandler):
    """Provides REST API for managing assets."""

    URI = '/rest/assets/item'
    REQUIRED_MODULES = [
        'inputex-string', 'gcb-uneditable', 'inputex-file',
        'inputex-hidden', 'io-upload-iframe']

    XSRF_TOKEN_NAME = 'asset-upload'

    # Two-tuples of JSON schema (from get_json_schema()) and annotations
    # dict (from get_schema_dict()) from customized schemas corresponding
    # to specific "base" asset path prefixes (see asset_paths.as_base).
    _SCHEMAS = {
        '/assets/css/': _asset_schema_details(
            generate_asset_rest_handler_schema(
                'Upload New CSS',
                messages.IMAGES_DOCS_UPLOAD_NEW_CSS_DESCRIPTION)),
        '/assets/html/': _asset_schema_details(
            generate_asset_rest_handler_schema(
                'Upload New HTML',
                messages.IMAGES_DOCS_UPLOAD_NEW_HTML_DESCRIPTION)),
        '/assets/lib/': _asset_schema_details(
            generate_asset_rest_handler_schema(
                'Upload New JavaScript',
                messages.IMAGES_DOCS_UPLOAD_NEW_JS_DESCRIPTION)),
        '/views/': _asset_schema_details(
            generate_asset_rest_handler_schema(
                'Upload New Template',
                messages.IMAGES_DOCS_UPLOAD_NEW_TEMPLATE_DESCRIPTION)),
        '/assets/img/': _asset_schema_details(
            generate_asset_rest_handler_schema(
                'Upload New Image',
                messages.IMAGES_DOCS_UPLOAD_NEW_IMAGE_DESCRIPTION,
                displayable=True)),
    }

    # Two-tuple like those in _SCHEMAS above, but generic, for use when the
    # asset path prefix is not found in the _SCHEMAS keys.
    _UNKNOWN_SCHEMA = _asset_schema_details(
        generate_asset_rest_handler_schema(
            'Upload New File',
            messages.IMAGES_DOCS_UPLOAD_NEW_FILE_DESCRIPTION))

    @classmethod
    def get_schema_details(cls, path):
        for base in cls._SCHEMAS.keys():
            if asset_paths.does_path_match_base(path, base):
                return cls._SCHEMAS[base]
        return cls._UNKNOWN_SCHEMA

    def _can_write_payload_to_base(self, payload, base):
        """Determine if a given payload type can be put in a base directory."""
        # Binary data can go in images; text data can go anywhere else.
        if asset_paths.AllowedBases.is_path_allowed(
            base, bases=asset_paths.AllowedBases.binary_bases()):
            return True
        else:
            return (is_text_payload(payload) and
                    asset_paths.AllowedBases.is_path_allowed(
                        base, bases=asset_paths.AllowedBases.text_bases()))

    def get(self):
        """Provides empty initial content for asset upload editor."""
        # TODO(jorr): Pass base URI through as request param when generalized.
        key = self.request.get('key')
        base = asset_paths.AllowedBases.match_allowed_bases(key)
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
        else:
            json_payload['asset_url'] = asset_paths.relative_base(base)
        transforms.send_json_response(
            self, 200, 'Success.', payload_dict=json_payload,
            xsrf_token=XsrfTokenManager.create_xsrf_token(self.XSRF_TOKEN_NAME))

    def post(self):
        is_valid, payload, upload = self._validate_post()
        if is_valid:
            key = payload['key']
            base = asset_paths.as_key(payload['base'])
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
        if not asset_paths.AllowedBases.is_path_allowed(base):
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
