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

"""Student HTML file submission upload module."""

__author__ = [
    'johncox@google.com (John Cox)',
]

import logging
import os

import jinja2

from google.appengine.runtime.apiproxy_errors import RequestTooLargeError

from common import jinja_utils
from common import schema_fields
from common import tags
from controllers import utils
from models import custom_modules
from models import models
from models import student_work
from modules.upload import messages

# String. Url fragment after the namespace we POST user payloads to.
_POST_ACTION_SUFFIX = '/upload'
# String. Course Builder root-relative path where resources for this module are.
_RESOURCES_PATH = os.path.join(os.path.sep, 'modules', 'upload', 'resources')
# String. Post form XSRF token name.
_XSRF_TOKEN_NAME = 'user-upload-form-xsrf'


# TODO(tujohnson): This belongs on line 107 instead of here, but I'm trying to
# satisfy the linter.
# pylint: disable=broad-except
class TextFileUploadHandler(utils.BaseHandler):

    def get_template(self, template_file, additional_dirs=None, prefs=None):
        dirs = additional_dirs if additional_dirs else []
        dirs.append(os.path.join(os.path.dirname(__file__), 'templates'))
        return super(TextFileUploadHandler, self).get_template(
            template_file, additional_dirs=dirs, prefs=prefs)

    def validate_contents(self, contents):
        """Checks that contents is unicode or raises UnicodeError."""
        try:
            # TODO(davyrisso): Non-unicode characters are still allowed,
            # this is due to the fact that we want to support non-latin scripts.
            # However it prevents binary files from being submitted.
            assert isinstance(contents, str) or isinstance(contents, unicode)
        except AssertionError:
            raise UnicodeError
        return contents

    def post(self):
        """Creates or updates a student submission."""
        token = self.request.get('form_xsrf_token')
        if not utils.XsrfTokenManager.is_xsrf_token_valid(
                token, _XSRF_TOKEN_NAME):
            self.error(400)
            return

        student = self.personalize_page_and_get_enrolled()
        if not student:
            self.error(403)
            return

        success = False
        error_detail = None
        unit_id = self.request.get('unit_id')
        instance_id = self.request.get('instance_id')

        contents = self.request.get('contents')

        if not contents:
            # I18N: Error message for failed student file upload.
            # The selected file was empty.
            error_detail = self.gettext('File is empty.')
            logging.warn(error_detail)
            self.error(400)
        else:
            try:
                contents = self.validate_contents(contents)
                success = bool(student_work.Submission.write(
                    unit_id, student.get_key(), contents,
                    instance_id=instance_id))
            except UnicodeError:
                # I18N: Error message for failed student file upload.
                # The selected file was not a text file.
                error_detail = self.gettext(
                    'Wrong file format, only text files (.txt) ' +
                    'with unicode contents are allowed.')
                logging.warn(error_detail)
                self.error(400)
            except RequestTooLargeError:
                # I18N: Error message for failed student file upload.
                # The selected file was too large.
                error_detail = self.gettext(
                    'File too large, only files smaller than 1MB are allowed.')
                logging.warn(error_detail)
                self.error(400)
            except Exception as e:
                # I18N: Error message for failed student file upload.
                # Generic upload error.
                error_detail = self.gettext(
                    'Unable to save student submission.') + (
                    'Error was: "{}"'.format(e)) if str(e) else ''
                logging.warn(error_detail)
                self.error(400)
        self.template_value['navbar'] = {'course': True}
        self.template_value['success'] = success
        self.template_value['error_detail'] = error_detail
        self.template_value['unit_id'] = unit_id
        self.render('result.html')


class TextFileUploadTag(tags.BaseTag):
    """Renders a form for uploading a text file."""

    binding_name = 'text-file-upload-tag'

    @classmethod
    def name(cls):
        return 'Student Text File Upload'

    @classmethod
    def vendor(cls):
        return 'gcb'

    def _get_action(self, slug):
        action = slug + _POST_ACTION_SUFFIX
        return action.replace('//', '/')

    def get_icon_url(self):
        return os.path.join(_RESOURCES_PATH, 'script_add.png')

    def get_schema(self, unused_handler):
        """Gets the tag's schema."""
        registry = schema_fields.FieldRegistry(TextFileUploadTag.name())
        registry.add_property(schema_fields.SchemaField(
            'display_length', 'Display Length', 'integer',
            description=messages.RTE_UPLOAD_DISPLAY_LENGTH,
            extra_schema_dict_values={'value': 100},
        ))

        return registry

    def render(self, node, handler):
        """Renders the custom tag."""
        student = handler.personalize_page_and_get_enrolled(
            supports_transient_student=True)
        enabled = (
            not isinstance(student, models.TransientStudent)
            and hasattr(handler, 'unit_id'))

        template_value = {}
        template_value['enabled'] = enabled

        template = jinja_utils.get_template(
            'templates/form.html', os.path.dirname(__file__))

        already_submitted = False
        if enabled:
            instance_id = node.attrib.get('instanceid')
            already_submitted = bool(
                student_work.Submission.get(
                    handler.unit_id, student.get_key(),
                    instance_id=instance_id))
            template_value['unit_id'] = handler.unit_id
            template_value['instance_id'] = instance_id

        template_value['action'] = self._get_action(
            handler.app_context.get_slug())
        template_value['already_submitted'] = already_submitted
        template_value['display_length'] = node.attrib.get(
            'display_length')
        template_value['form_xsrf_token'] = (
            utils.XsrfTokenManager.create_xsrf_token(_XSRF_TOKEN_NAME))

        return tags.html_string_to_element_tree(
            jinja2.utils.Markup(template.render(template_value))
        )


custom_module = None


def register_module():
    """Registers this module for use."""

    def on_module_disable():
        tags.Registry.remove_tag_binding(TextFileUploadTag.binding_name)
        tags.EditorBlacklists.unregister(
            TextFileUploadTag.binding_name,
            tags.EditorBlacklists.COURSE_SCOPE)
        tags.EditorBlacklists.unregister(
            TextFileUploadTag.binding_name,
            tags.EditorBlacklists.DESCRIPTIVE_SCOPE)

    def on_module_enable():
        tags.Registry.add_tag_binding(
            TextFileUploadTag.binding_name, TextFileUploadTag)
        tags.EditorBlacklists.register(
            TextFileUploadTag.binding_name,
            tags.EditorBlacklists.COURSE_SCOPE)
        tags.EditorBlacklists.register(
            TextFileUploadTag.binding_name,
            tags.EditorBlacklists.DESCRIPTIVE_SCOPE)

    global_routes = [
        (os.path.join(_RESOURCES_PATH, '.*'), tags.ResourcesHandler),
    ]
    namespaced_routes = [
        (_POST_ACTION_SUFFIX, TextFileUploadHandler),
    ]

    global custom_module  # pylint: disable=global-statement

    custom_module = custom_modules.Module(
        'Student Text File Submission Upload',
        'Adds a custom tag for students to upload text files <= 1MB in size.',
        global_routes, namespaced_routes,
        notify_module_disabled=on_module_disable,
        notify_module_enabled=on_module_enable,
    )

    return custom_module
