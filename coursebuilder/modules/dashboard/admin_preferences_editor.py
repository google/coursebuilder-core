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
from models import models
from models import roles
from modules.dashboard import dto_editor

from google.appengine.api import users


class AdminPreferencesEditor(dto_editor.BaseDatastoreAssetEditor):
    """An editor for editing and managing course admin preferences.

    Note that this editor operates on StudentPreferencesDAO instances.
    This is intentional; that type stores per-human, per-course prefs.
    This editor exposes only the admin-specific settings, and is
    available only in contexts where the user is a course admin.
    (I.e, the dashboard.)
    """

    def post_edit_admin_preferences(self):
        if not roles.Roles.is_course_admin(self.app_context):
            self.error(401)
            return
        template_values = {
            'page_title': self.format_title('Edit Preferences'),
            'main_content': self.get_form(
                AdminPreferencesRESTHandler,
                users.get_current_user().user_id(),
                '/dashboard?action=settings&tab=admin_prefs',
                deletable=False)
        }
        self.render_page(template_values, 'settings')


class AdminPreferencesRESTHandler(dto_editor.BaseDatastoreRestHandler):

    URI = '/rest/admin_prefs'
    REQUIRED_MODULES = ['inputex-hidden', 'inputex-checkbox']
    EXTRA_JS_FILES = []
    XSRF_TOKEN = 'admin-prefs-edit'
    SCHEMA_VERSIONS = [models.StudentPreferencesDAO.CURRENT_VERSION]
    DAO = models.StudentPreferencesDAO

    @classmethod
    def get_schema(cls):
        ret = schema_fields.FieldRegistry(
            'Admin Prefs', description='Administrator preferences')
        ret.add_property(schema_fields.SchemaField(
            'version', '', 'string', optional=True, hidden=True))
        ret.add_property(schema_fields.SchemaField(
            'id', '', 'string', optional=True, hidden=True))
        ret.add_property(schema_fields.SchemaField(
            'show_hooks', 'Show Hook Edit Buttons', 'boolean',
            description='Whether to show controls on course pages to permit'
            'editing of HTML inclusions (hook points) at that location on '
            'the page.  Turn this setting off to see the course as the '
            'student would see it, and on to enable the edit controls.',
            optional=True, hidden=False))
        ret.add_property(schema_fields.SchemaField(
            'show_jinja_context', 'Show Jinja Context', 'boolean',
            description='Whether to show a dump of Jinja context contents '
            'at the bottom of course pages (Only for admins, and only '
            'available on development server.)',
            optional=True, hidden=False))
        return ret

    def get_default_content(self):
        return {
            'version': self.SCHEMA_VERSIONS[0],
            'show_hooks': False
        }

    def validate(self, prefs_dict, key, schema_version, errors):
        pass
