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

"""Classes supporting creation and editing of roles."""

__author__ = 'Glenn De Jonghe (gdejonghe@google.com)'

from common import schema_fields
from common import utils
from models.models import RoleDAO
from models.roles import Roles
from modules.dashboard import dto_editor
import messages


class RoleManagerAndEditor(dto_editor.BaseDatastoreAssetEditor):
    """An editor for editing and managing roles."""

    def _prepare_template(self, key):
        template_values = {}
        template_values['page_title'] = self.format_title('Edit Role')
        template_values['main_content'] = self.get_form(
            RoleRESTHandler, key,
            self.get_action_url('edit_roles'))
        return template_values

    def get_add_role(self):
        self.render_page(
            self._prepare_template(''), in_action='edit_roles')

    def get_edit_role(self):
        self.render_page(
            self._prepare_template(self.request.get('key')),
            in_action='edit_roles')


class RoleRESTHandler(dto_editor.BaseDatastoreRestHandler):
    """REST handler for editing roles."""

    URI = '/rest/role'

    EXTRA_JS_FILES = ['role_editor.js']

    XSRF_TOKEN = 'role-edit'

    SCHEMA_VERSIONS = ['1.5']

    DAO = RoleDAO

    INACTIVE_MODULES = 'Inactive Modules'

    @classmethod
    def _add_module_permissions_schema(cls, subschema, module_name):
        item_type = schema_fields.FieldRegistry(
            'Permission',
            extra_schema_dict_values={'className': 'permission-item'})
        item_type.add_property(schema_fields.SchemaField(
            'assigned', 'Assigned', 'boolean', optional=True,
            extra_schema_dict_values={'className': 'permission-assigned'}))
        item_type.add_property(schema_fields.SchemaField(
            'name', 'Name', 'string', editable=False, optional=True,
            extra_schema_dict_values={'className': 'permission-name'}))
        item_type.add_property(schema_fields.SchemaField(
            'description', 'Description', 'string', optional=True,
            editable=False,
            extra_schema_dict_values={'className': 'permission-label'}))

        item_array = schema_fields.FieldArray(
            module_name, module_name, item_type=item_type,
            extra_schema_dict_values={'className': 'permission-module'},
            optional=True)

        subschema.add_property(item_array)

    @classmethod
    def get_schema(cls):
        """Return the InputEx schema for the roles editor."""
        schema = schema_fields.FieldRegistry(
            'Role', description='role')

        schema.add_property(schema_fields.SchemaField(
            'version', '', 'string', optional=True, hidden=True))
        schema.add_property(schema_fields.SchemaField(
            'name', 'Name', 'string', optional=False,
            description=messages.ROLE_NAME_DESCRIPTION))
        schema.add_property(schema_fields.SchemaField(
            'description', 'Description', 'text', optional=True,
            description=messages.ROLE_DESCRIPTION_DESCRIPTION))
        # TODO(gdejonghe) Use user.id instead of user.email
        schema.add_property(schema_fields.SchemaField(
            'users', 'User Emails', 'text',
            description=messages.ROLE_USER_EMAILS_DESCRIPTION))

        subschema = schema.add_sub_registry('modules', 'Permission Modules')

        for module in Roles.get_modules():
            cls._add_module_permissions_schema(subschema, module.name)
        cls._add_module_permissions_schema(subschema, cls.INACTIVE_MODULES)

        return schema

    def _generate_permission(self, name, description, assigned):
        return {
            'name': name,
            'description': description,
            'assigned': assigned
        }

    def _generate_inactive_permission(self, permission, module=None):
        if module is None:
            return self._generate_permission(
                permission, 'This permission is currently not registered.',
                True)
        return self._generate_permission(
            permission, 'This permission was set by the module "%s" which is '
                'currently not registered.' % (module), True)

    def _update_dict_with_permissions(self, dictionary):
        app_context = self.get_course().app_context
        modules = {}
        for (module, callback) in Roles.get_permissions():
            modules[module.name] = []
            for (permission, description) in callback(app_context):
                modules[module.name].append(
                    self._generate_permission(permission, description, False))
        dictionary['modules'] = modules
        return dictionary

    def get_default_content(self):
        return self._update_dict_with_permissions(
            {'version': self.SCHEMA_VERSIONS[0]})

    def validate(self, role_dict, key, unused_schema_version, errors):
        """Validate the role data sent from the form."""
        role_names = {role.name for role in RoleDAO.get_all() if (
            not key or role.id != long(key))}

        if not role_dict['name'] or role_dict['name'] in role_names:
            errors.append('The role must have a unique non-empty name.')

    def transform_after_editor_hook(self, role_dict):
        """Edit the dict generated by the role editor."""
        role_dict['name'] = role_dict['name'].strip()

        role_dict['users'] = utils.text_to_list(
            role_dict['users'], utils.SPLITTER)

        # Create new entry for the dict to store formatted information
        role_dict['permissions'] = {}
        for (module_name, permissions) in role_dict['modules'].iteritems():
            assigned_permissions = []
            for permission in permissions:
                if permission['assigned']:
                    assigned_permissions.append(permission['name'])
            if assigned_permissions:
                role_dict['permissions'][module_name] = assigned_permissions

        # Remove obsolete entry
        del role_dict['modules']
        return role_dict

    def transform_for_editor_hook(self, role_dict):
        """Modify dict from datastore before it goes to the role editor."""
        self._update_dict_with_permissions(role_dict)
        for (module_name, permissions) in role_dict['modules'].iteritems():
            assigned_permissions = role_dict['permissions'].get(
                module_name, [])
            # First set the checkboxes for the active permissions
            for permission in permissions:
                if permission['name'] in assigned_permissions:
                    assigned_permissions.remove(permission['name'])
                    permission['assigned'] = True

            # Now generate fields for the assigned inactive permissions
            permissions.extend([self._generate_inactive_permission(inactive)
                                for inactive in assigned_permissions])
            # Pop active module
            role_dict['permissions'].pop(module_name, None)

        # Iterate over all the modules that are left over
        role_dict['modules'][self.INACTIVE_MODULES] = []
        for (module, permissions) in role_dict['permissions'].iteritems():
            # Add all the permissions to the INACTIVE MODULES section
            role_dict['modules'][self.INACTIVE_MODULES].extend([
                self._generate_inactive_permission(inactive, module)
                for inactive in permissions
            ])

        role_dict['users'] = ', '.join(role_dict['users'])
        del role_dict['permissions']
        return role_dict

    def after_save_hook(self):
        Roles.update_permissions_map()
