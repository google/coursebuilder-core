# Copyright 2015 Google Inc. All Rights Reserved.
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

"""Settings for the Course Explorer."""

__author__ = 'Nick Retallack (nretallack@google.com)'

import base64
import cgi

import appengine_config
from common import schema_fields
from common import crypto
from common import users
from common import utils as common_utils
from models import config
from models import models
from models import roles
from models import transforms
from models import messages as models_messages
from controllers import utils
from modules.explorer import constants
from modules.explorer import messages
from modules.dashboard import dashboard_handler
from modules.oeditor import oeditor

GCB_ENABLE_COURSE_EXPLORER_PAGE = config.ConfigProperty(
    'gcb_enable_course_explorer_page', bool,
    messages.SITE_SETTINGS_COURSE_EXPLORER, default_value=False,
    label='Course Explorer', multiline=False, validator=None)

COURSE_EXPLORER_SETTINGS = config.ConfigProperty(
    'course_explorer_settings', str, '',
    label='Site settings', show_in_site_settings=False)


def make_logo_url(mime_type, bytes_base64):
    return 'data:{};base64,{}'.format(mime_type, bytes_base64)


def get_course_explorer_settings_data():
    try:
        return transforms.loads(COURSE_EXPLORER_SETTINGS.value)
    except ValueError:
        return {'title': ''}


def schema_provider(unused_course):
    group = schema_fields.FieldRegistry(
        COURSE_EXPLORER_SETTINGS.label, extra_schema_dict_values={
            'className': 'inputEx-Group new-form-layout'})

    group.add_property(schema_fields.SchemaField(
        'title', 'Site Name', 'string',
        description=models_messages.SITE_NAME_DESCRIPTION,
        i18n=False,
        optional=True,
    ))

    group.add_property(schema_fields.SchemaField(
        'logo_url', 'Site Logo', 'string',
        description=messages.SITE_LOGO_DESCRIPTION,
        editable=False,
        extra_schema_dict_values={'visu': {
            'visuType': 'funcName',
            'funcName': 'renderImage',
        }},
        i18n=False,
        optional=True,
    ))


    group.add_property(schema_fields.SchemaField(
        'logo', 'Change Site Logo', 'file',
        i18n=False,
        optional=True,
    ))

    group.add_property(schema_fields.SchemaField(
        'logo_alt_text', 'Site Logo Description', 'string',
        description=models_messages.SITE_LOGO_DESCRIPTION_DESCRIPTION,
        i18n=False,
        optional=True,
    ))

    group.add_property(schema_fields.SchemaField(
        'extra_content', 'Extra Content', 'html',
        description=messages.EXTRA_CONTENT_DESCRIPTION,
        i18n=False,
        optional=True,
    ))

    group.add_property(schema_fields.SchemaField(
        'institution_name', 'Organization Name', 'string',
        description=models_messages.ORGANIZATION_NAME_DESCRIPTION,
        i18n=False,
        optional=True,
    ))
    group.add_property(schema_fields.SchemaField(
        'institution_url', 'Organization URL', 'string',
        description=models_messages.ORGANIZATION_URL_DESCRIPTION,
        extra_schema_dict_values={'_type': 'url', 'showMsg': True},
        i18n=False,
        optional=True,
    ))

    group.add_property(schema_fields.SchemaField(
        'privacy_terms_url', 'Privacy & Terms URL', 'string',
        description=models_messages.HOMEPAGE_PRIVACY_URL_DESCRIPTION,
        extra_schema_dict_values={'_type': 'url', 'showMsg': True},
        i18n=False,
        optional=True,
    ))

    return group


class SettingsEditor(dashboard_handler.AbstractDashboardHandler):
    URL = 'explorer-settings'
    ACTION = 'explorer-settings'
    PAGE_TITLE = COURSE_EXPLORER_SETTINGS.label

    def get(self):
        super(SettingsEditor, self).get()
        schema = schema_provider(None)
        self.render_content(oeditor.ObjectEditor.get_html_for(
            self, schema.get_json_schema(), schema.get_schema_dict(), 'key',
            SettingsEditorRest.URL, None, save_method='upload'))


class SettingsEditorRest(utils.BaseRESTHandler):
    URL = 'rest/explorer-settings'
    ACTION = 'explorer-settings-rest'

    def get(self):
        if not roles.Roles.is_course_admin(self.app_context):
            transforms.send_json_response(
                self, 401, 'Access denied.', {})
            return

        payload_dict = get_course_explorer_settings_data()

        logo_mime_type = payload_dict.pop('logo_mime_type', None)
        logo_bytes_base64 = payload_dict.pop('logo_bytes_base64', None)
        if logo_mime_type and logo_bytes_base64:
            payload_dict['logo_url'] = make_logo_url(
                logo_mime_type, logo_bytes_base64)

        transforms.send_json_response(
            self, 200, 'Success',
            payload_dict=payload_dict,
            xsrf_token=crypto.XsrfTokenManager.create_xsrf_token(self.ACTION))

    def post(self):
        name = COURSE_EXPLORER_SETTINGS.name
        request = transforms.loads(self.request.get('request'))

        if not self.assert_xsrf_token_or_fail(
                request, self.ACTION, {}):
            return

        if not roles.Roles.is_course_admin(self.app_context):
            transforms.send_json_response(
                self, 401, 'Access denied.', {})
            return

        raw_data = transforms.loads(request.get('payload'))
        raw_data.pop('logo', None)
        try:
            data = transforms.json_to_dict(
                raw_data, schema_provider(None).get_json_schema_dict())
        except (TypeError, ValueError) as err:
            self.validation_error(err.replace('\n', ' '))
            return

        logo = self.request.POST.get('logo')
        logo_uploaded = isinstance(logo, cgi.FieldStorage)
        if logo_uploaded:
            data['logo_bytes_base64'] = base64.b64encode(logo.file.read())
            data['logo_mime_type'] = logo.type

        with common_utils.Namespace(appengine_config.DEFAULT_NAMESPACE_NAME):
            entity = config.ConfigPropertyEntity.get_by_key_name(name)

            if entity is None:
                entity = config.ConfigPropertyEntity(key_name=name)
                old_value = None
            else:
                old_value = entity.value

            # Don't delete the logo.
            if not logo_uploaded and old_value:
                old_dict = transforms.loads(old_value)
                if (
                        'logo_bytes_base64' in old_dict and
                        'logo_mime_type' in old_dict):
                    data['logo_bytes_base64'] = old_dict['logo_bytes_base64']
                    data['logo_mime_type'] = old_dict['logo_mime_type']

            entity.value = transforms.dumps(data)
            entity.is_draft = False
            entity.put()

            # is this necessary?
            models.EventEntity.record(
                'put-property', users.get_current_user(), transforms.dumps({
                    'name': name,
                    'before': str(old_value), 'after': str(entity.value)}))

        transforms.send_file_upload_response(self, 200, 'Saved.')


def register():
    SettingsEditor.add_to_menu(
        'settings', constants.MODULE_NAME, COURSE_EXPLORER_SETTINGS.label,
        sub_group_name='advanced')


namespaced_routes = utils.map_handler_urls([
    SettingsEditor,
    SettingsEditorRest,
])
