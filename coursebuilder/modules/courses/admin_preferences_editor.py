# Copyright 2014 Google Inc. All Rights Reserved.
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

"""Classes supporting creation and editing of questions."""

__author__ = 'Mike Gainer (mgainer@google.com)'

from common import schema_fields
from common import users
from models import models
from models import roles
from models import services
from modules.courses import messages
from modules.dashboard import dashboard
from modules.dashboard import dto_editor


class AdminPreferencesEditor(dto_editor.BaseDatastoreAssetEditor):
    """An editor for editing and managing course admin preferences.

    Note that this editor operates on StudentPreferencesDAO instances.
    This is intentional; that type stores per-human, per-course prefs.
    This editor exposes only the admin-specific settings, and is
    available only in contexts where the user is a course admin.
    (I.e, the dashboard.)
    """

    @staticmethod
    def edit_admin_preferences(handler):
        if not roles.Roles.is_course_admin(handler.app_context):
            handler.error(401)
            return

        # Admin's prefs must exist as real DB row for REST handler to operate.
        user_id = users.get_current_user().user_id()
        prefs = models.StudentPreferencesDAO.load(user_id)
        if not prefs:
            prefs = models.StudentPreferencesDAO.load_or_default()
            models.StudentPreferencesDAO.save(prefs)

        return {
            'page_title': handler.format_title('Edit Preferences'),
            'main_content': handler.get_form(
                AdminPreferencesRESTHandler,
                users.get_current_user().user_id(),
                exit_url='', deletable=False)
        }


class AdminPreferencesRESTHandler(dto_editor.BaseDatastoreRestHandler):

    URI = '/rest/admin_prefs'
    EXTRA_JS_FILES = []
    XSRF_TOKEN = 'admin-prefs-edit'
    SCHEMA_VERSIONS = [models.StudentPreferencesDAO.CURRENT_VERSION]
    DAO = models.StudentPreferencesDAO

    @classmethod
    def get_schema(cls):
        ret = schema_fields.FieldRegistry(
            'Admin Prefs', description='Administrator preferences',
            extra_schema_dict_values={
                'className': 'inputEx-Group new-form-layout hidden-header'})
        ret.add_property(schema_fields.SchemaField(
            'version', '', 'string', optional=True, hidden=True))
        ret.add_property(schema_fields.SchemaField(
            'id', '', 'string', optional=True, hidden=True))
        ret.add_property(schema_fields.SchemaField(
            'show_hooks', 'Enable Hook Edits', 'boolean',
            description=services.help_urls.make_learn_more_message(
                messages.ENABLE_HOOK_EDITS, 'settings:debugging:show_hooks'),
            optional=True, hidden=False))
        ret.add_property(schema_fields.SchemaField(
            'show_jinja_context', 'Show Jinja Context', 'boolean',
            description=services.help_urls.make_learn_more_message(
                messages.SHOW_JINJA_CONTEXT,
                'settings:debugging:show_jinja_context'), optional=True,
            hidden=False))
        return ret

    def get_default_content(self):
        return {
            'version': self.SCHEMA_VERSIONS[0],
            'show_hooks': False
        }

    def validate(self, prefs_dict, key, schema_version, errors):
        pass


def get_namespaced_handlers():
    return [
        (AdminPreferencesRESTHandler.URI, AdminPreferencesRESTHandler)
    ]

def on_module_enabled():
    dashboard.DashboardHandler.add_custom_post_action(
        'admin_prefs', AdminPreferencesEditor.edit_admin_preferences)

    dashboard.DashboardHandler.add_sub_nav_mapping(
        'settings', 'admin_prefs', 'Debugging', action='settings_admin_prefs',
        contents=AdminPreferencesEditor.edit_admin_preferences)
