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

"""Functional tests for models/review.py."""

__author__ = [
    'mgainer@google.com (Mike Gainer)',
]

from common import utils as common_utils
from common import schema_fields
from models import permissions
from models import custom_modules
from models import models
from models import roles
from modules.courses import constants
from tests.functional import actions


class PermissionsTests(actions.TestBase):
    """Tests KeyProperty."""

    ADMIN_EMAIL = 'admin@foo.com'
    IN_ROLE_EMAIL = 'assistant@foo.com'
    NON_ROLE_EMAIL = 'student@foo.com'
    COURSE_NAME = 'permissions_tests'
    NAMESPACE = 'ns_%s' % COURSE_NAME
    MODULE_NAME = 'permissions_tests'
    PERMISSION_NAME = 'test_permission'
    PERMISSION = roles.Permission(PERMISSION_NAME, 'Fake perm. for testing')
    PERMISSION_SCOPE = 'test_scope'
    ROLE_NAME = 'test_user_role'
    custom_module = None

    @classmethod
    def setUpClass(cls):
        super(PermissionsTests, cls).setUpClass()
        cls.custom_module = custom_modules.Module(
            cls.MODULE_NAME, 'Permissions Tests', [], [],
            notify_module_enabled=cls.notify_module_enabled)
        cls.custom_module.enable()

    @classmethod
    def tearDownClass(cls):
        roles.Roles.unregister_permissions(cls.custom_module)
        permissions.SchemaPermissionRegistry.remove(
            cls.PERMISSION_SCOPE, cls.PERMISSION_NAME)
        super(PermissionsTests, cls).tearDownClass()

    @classmethod
    def notify_module_enabled(cls):
        roles.Roles.register_permissions(
            cls.custom_module, cls.permissions_callback)
        permissions.SchemaPermissionRegistry.add(
            cls.PERMISSION_SCOPE,
            permissions.SimpleSchemaPermission(
                cls.custom_module, cls.PERMISSION_NAME,
                readable_list=['a', 'b'],
                editable_list=['a']))
        permissions.SchemaPermissionRegistry.add(
            cls.PERMISSION_SCOPE,
            permissions.CourseAdminSchemaPermission())

    @classmethod
    def permissions_callback(cls, app_context):
        return [cls.PERMISSION]

    def setUp(self):
        super(PermissionsTests, self).setUp()
        self.app_context = actions.simple_add_course(
            self.COURSE_NAME, self.ADMIN_EMAIL, 'Permissions Tests')
        self.schema = schema_fields.FieldRegistry('title')
        self.schema.add_property(schema_fields.SchemaField('a', 'A', 'string'))
        self.schema.add_property(schema_fields.SchemaField('b', 'B', 'string'))
        self.schema.add_property(schema_fields.SchemaField('c', 'C', 'string'))
        self.entity = {'a': 1, 'b': 2, 'c': 3}

        with common_utils.Namespace(self.NAMESPACE):
            role_dto = models.RoleDTO(the_id=None, the_dict={
                'name': self.ROLE_NAME,
                'permissions': {self.MODULE_NAME: [self.PERMISSION_NAME]},
                'description': 'Role allowing limited schema access.',
                'users': [self.IN_ROLE_EMAIL]})
            roles.RoleDAO.save(role_dto)

    def test_admin_has_permissions_with_no_configuration_needed(self):
        actions.login(self.ADMIN_EMAIL, is_admin=True)
        self.assertTrue(permissions.can_view(
            self.app_context, constants.SCOPE_COURSE_SETTINGS))
        self.assertTrue(permissions.can_edit(
            self.app_context, constants.SCOPE_COURSE_SETTINGS))
        self.assertTrue(permissions.can_view_property(
            self.app_context, constants.SCOPE_COURSE_SETTINGS,
            'absolutely/anything'))
        self.assertTrue(permissions.can_edit_property(
            self.app_context, constants.SCOPE_COURSE_SETTINGS,
            'absolutely/anything'))

    def test_non_admin_has_no_permissions_with_no_configuration_needed(self):
        actions.login(self.IN_ROLE_EMAIL)
        self.assertFalse(permissions.can_view(
            self.app_context, constants.SCOPE_COURSE_SETTINGS))
        self.assertFalse(permissions.can_edit(
            self.app_context, constants.SCOPE_COURSE_SETTINGS))
        self.assertFalse(permissions.can_view_property(
            self.app_context, constants.SCOPE_COURSE_SETTINGS,
            'absolutely/anything'))
        self.assertFalse(permissions.can_edit_property(
            self.app_context, constants.SCOPE_COURSE_SETTINGS,
            'absolutely/anything'))

    def test_role_permissions(self):
        with common_utils.Namespace(self.NAMESPACE):

            # Admin and assistant can read 'a', but student cannot.
            checker = permissions.SchemaPermissionRegistry.build_view_checker(
                self.PERMISSION_SCOPE, ['a'])
            actions.login(self.ADMIN_EMAIL)
            self.assertTrue(checker(self.app_context))
            actions.login(self.IN_ROLE_EMAIL)
            self.assertTrue(checker(self.app_context))
            actions.login(self.NON_ROLE_EMAIL)
            self.assertFalse(checker(self.app_context))

            # Admin and assistant can read 'b', but student cannot.
            checker = permissions.SchemaPermissionRegistry.build_view_checker(
                self.PERMISSION_SCOPE, ['b'])
            actions.login(self.ADMIN_EMAIL)
            self.assertTrue(checker(self.app_context))
            actions.login(self.IN_ROLE_EMAIL)
            self.assertTrue(checker(self.app_context))
            actions.login(self.NON_ROLE_EMAIL)
            self.assertFalse(checker(self.app_context))

            # Admin can read 'c', but neither assistant nor student may.
            checker = permissions.SchemaPermissionRegistry.build_view_checker(
                self.PERMISSION_SCOPE, ['c'])
            actions.login(self.ADMIN_EMAIL)
            self.assertTrue(checker(self.app_context))
            actions.login(self.IN_ROLE_EMAIL)
            self.assertFalse(checker(self.app_context))
            actions.login(self.NON_ROLE_EMAIL)
            self.assertFalse(checker(self.app_context))

            # Admin and assistant can write 'a', but student cannot.
            checker = permissions.SchemaPermissionRegistry.build_edit_checker(
                self.PERMISSION_SCOPE, ['a'])
            actions.login(self.ADMIN_EMAIL)
            self.assertTrue(checker(self.app_context))
            actions.login(self.IN_ROLE_EMAIL)
            self.assertTrue(checker(self.app_context))
            actions.login(self.NON_ROLE_EMAIL)
            self.assertFalse(checker(self.app_context))

            # Admin can write 'b', but neither assistant nor student may.
            checker = permissions.SchemaPermissionRegistry.build_edit_checker(
                self.PERMISSION_SCOPE, ['b'])
            actions.login(self.ADMIN_EMAIL)
            self.assertTrue(checker(self.app_context))
            actions.login(self.IN_ROLE_EMAIL)
            self.assertFalse(checker(self.app_context))
            actions.login(self.NON_ROLE_EMAIL)
            self.assertFalse(checker(self.app_context))

            # Admin can write 'c', but neither assistant nor student may.
            checker = permissions.SchemaPermissionRegistry.build_edit_checker(
                self.PERMISSION_SCOPE, ['c'])
            actions.login(self.ADMIN_EMAIL)
            self.assertTrue(checker(self.app_context))
            actions.login(self.IN_ROLE_EMAIL)
            self.assertFalse(checker(self.app_context))
            actions.login(self.NON_ROLE_EMAIL)
            self.assertFalse(checker(self.app_context))

    def test_schema_redaction(self):
        reg = permissions.SchemaPermissionRegistry
        with common_utils.Namespace(self.NAMESPACE):

            # All properties readable/writable for admin
            actions.login(self.ADMIN_EMAIL)
            ret = reg.redact_schema_to_permitted_fields(
                self.app_context, self.PERMISSION_SCOPE, self.schema)
            a = ret.get_property('a')
            self.assertNotIn('disabled', a._extra_schema_dict_values)
            self.assertFalse(a.hidden)
            b = ret.get_property('b')
            self.assertNotIn('disabled', b._extra_schema_dict_values)
            self.assertFalse(b.hidden)
            c = ret.get_property('c')
            self.assertNotIn('disabled', c._extra_schema_dict_values)
            self.assertFalse(c.hidden)

            # 'a', 'b' readable, 'a' writable, and 'c' removed for assistant.
            actions.login(self.IN_ROLE_EMAIL)
            ret = reg.redact_schema_to_permitted_fields(
                self.app_context, self.PERMISSION_SCOPE, self.schema)
            a = ret.get_property('a')
            self.assertNotIn('disabled', a._extra_schema_dict_values)
            self.assertFalse(a.hidden)
            b = ret.get_property('b')
            self.assertTrue(b._extra_schema_dict_values.get('disabled'))
            self.assertFalse(b.hidden)
            self.assertIsNone(ret.get_property('c'))

            # All properties removed for account w/ no access.
            actions.login(self.NON_ROLE_EMAIL)
            ret = reg.redact_schema_to_permitted_fields(
                self.app_context, self.PERMISSION_SCOPE, self.schema)
            self.assertIsNone(ret.get_property('a'))
            self.assertIsNone(ret.get_property('b'))
            self.assertIsNone(ret.get_property('c'))


class SimpleSchemaPermissionTests(actions.TestBase):

    def test_no_args_equals_no_permissions(self):
        p = permissions.SimpleSchemaPermission(None, None)
        self.assertFalse(p.can_view('a'))
        self.assertFalse(p.can_edit('a'))

    def test_read_some_write_none(self):
        p = permissions.SimpleSchemaPermission(None, None, readable_list=['a'])
        self.assertTrue(p.can_view('a'))
        self.assertFalse(p.can_edit('a'))
        self.assertFalse(p.can_view('b'))
        self.assertFalse(p.can_edit('b'))

    def test_read_write_some(self):
        p = permissions.SimpleSchemaPermission(None, None,
                                               readable_list=['a'],
                                               editable_list=['a'])
        self.assertTrue(p.can_view('a'))
        self.assertTrue(p.can_edit('a'))
        self.assertFalse(p.can_view('b'))
        self.assertFalse(p.can_edit('b'))

    def test_writability_implies_readability(self):
        p = permissions.SimpleSchemaPermission(None, None, editable_list=['a'])
        self.assertTrue(p.can_view('a'))
        self.assertTrue(p.can_edit('a'))
        self.assertFalse(p.can_view('b'))
        self.assertFalse(p.can_edit('b'))

    def test_some_readable_some_writable(self):
        p = permissions.SimpleSchemaPermission(None, None,
                                               readable_list=['b'],
                                               editable_list=['a'])
        self.assertTrue(p.can_view('a'))
        self.assertTrue(p.can_edit('a'))
        self.assertTrue(p.can_view('b'))
        self.assertFalse(p.can_edit('b'))
        self.assertFalse(p.can_view('c'))
        self.assertFalse(p.can_edit('c'))

    def test_read_any(self):
        p = permissions.SimpleSchemaPermission(None, None, all_readable=True)
        self.assertTrue(p.can_view('a'))
        self.assertFalse(p.can_edit('a'))
        self.assertTrue(p.can_view('b'))
        self.assertFalse(p.can_edit('b'))

    def test_write_any(self):
        p = permissions.SimpleSchemaPermission(None, None, all_writable=True)
        self.assertTrue(p.can_view('a'))
        self.assertTrue(p.can_edit('a'))
        self.assertTrue(p.can_view('b'))
        self.assertTrue(p.can_edit('b'))

    def test_read_even_one_with_no_readable(self):
        p = permissions.SimpleSchemaPermission(None, None)
        self.assertFalse(p.can_view())

    def test_read_even_one_with_one_readable(self):
        p = permissions.SimpleSchemaPermission(None, None, readable_list=['a'])
        self.assertTrue(p.can_view())

    def test_read_even_one_with_all_readable(self):
        p = permissions.SimpleSchemaPermission(None, None, all_readable=True)
        self.assertTrue(p.can_view())

    def test_read_even_one_with_one_writable(self):
        p = permissions.SimpleSchemaPermission(None, None, editable_list=['a'])
        self.assertTrue(p.can_view())

    def test_read_even_one_with_all_writable(self):
        p = permissions.SimpleSchemaPermission(None, None, all_writable=True)
        self.assertTrue(p.can_view())

    def test_write_even_one_with_no_writable(self):
        p = permissions.SimpleSchemaPermission(None, None, all_readable=True)
        self.assertFalse(p.can_edit())

    def test_write_even_one_with_one_writable(self):
        p = permissions.SimpleSchemaPermission(None, None, editable_list=['a'])
        self.assertTrue(p.can_edit())

    def test_write_even_one_with_all_writable(self):
        p = permissions.SimpleSchemaPermission(None, None, all_writable=True)
        self.assertTrue(p.can_edit())

    def test_containing_schema(self):
        p = permissions.SimpleSchemaPermission(
            None, None, readable_list=['a/b/c'], editable_list=['d/e/f'])
        self.assertTrue(p.can_view('a'))
        self.assertTrue(p.can_view('a/b'))
        self.assertTrue(p.can_view('a/b/c'))
        self.assertFalse(p.can_edit('a'))
        self.assertFalse(p.can_edit('a/b'))
        self.assertFalse(p.can_edit('a/b/c'))

        self.assertTrue(p.can_view('d'))
        self.assertTrue(p.can_view('d/e'))
        self.assertTrue(p.can_view('d/e/f'))
        self.assertTrue(p.can_edit('d'))
        self.assertTrue(p.can_edit('d/e'))
        self.assertTrue(p.can_edit('d/e/f'))

        self.assertFalse(p.can_view('g'))
        self.assertFalse(p.can_view('g/h'))
        self.assertFalse(p.can_view('g/h/i'))
        self.assertFalse(p.can_edit('g'))
        self.assertFalse(p.can_edit('g/h'))
        self.assertFalse(p.can_edit('g/h/i'))
