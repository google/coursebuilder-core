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

"""Manages mapping of privileges onto schema components."""

__author__ = 'Mike Gainer (mgainer@google.com)'

import collections
import copy
import itertools

from common import schema_fields
import roles


class AbstractSchemaPermission(object):
    """Base class for policy objects governing access to settings.

    Various modules may wish to add permission-based or other kinds of polices
    which permit users to view/edit only certain course settings fields.  This
    can be accomplished by adding a SchemaPermission instance to
    SchemaPermissionRegistry.  These are checked when the settings
    forms are built and submitted.
    """

    def get_name(self):
        """Provide a globally unique name for deduplication."""
        raise NotImplementedError()

    def applies_to_current_user(self, application_context):
        """Indicate whether the current user satisfies this permission."""
        raise NotImplementedError()

    def can_view(self, prop_name=None):
        """Indicate whether users in this permission may view this setting.

        Args:
          prop_name:  A name of the form 'container/subcontainer/property'.
              E.g., 'course/main_image/alt_text'.  Containers themselves
              are also presented for consideration.  In the example,
              both 'course' and 'course/main_image' will also be passed
              to this function.  If this function returns False at a
              container level, it will not be consulted for any of that
              container's contents.

              If prop_name is None, this returns a boolean indicating whether
              this policy permits viewing of any property at all.
        Returns:
          boolean: True if the user may see the field's value.
        """
        raise NotImplementedError()

    def can_edit(self, prop_name=None):
        """Indicate whether users in this permission may edit a property.

        Args:
          prop_name: As above, for can_view.  If None, a boolean indicating
              whether this policy permits editing of at least one item.
              A read-only policy will thus return False, and this allows
              some REST handlers to bail out early with a useful error code.
          Returns:
            boolean: True if the user may modify the field's value.
        """
        raise NotImplementedError()


class SimpleSchemaPermission(AbstractSchemaPermission):
    """Convenience: bind a permission to list of readable/writable settings."""

    def __init__(self, module, permission_name, readable_list=None,
                 editable_list=None, all_readable=False, all_writable=False):
        """Configure settings wich may be read/edited with a given permission.

        Permission names are of the form 'container/subcontainer/property'.
        E.g., 'course/main_image/alt_text'.  Permission names are stored as
        dict-of-dict to simplify partial matching.  (This prevents clients of
        this interface from having to specify all of 'course',
        'course/main_image' and 'course/main_image/alt_text'; the presence of
        'course/main_image/alt_text' implies the read/write-ability of
        containing sub-schemas.

        Args:
          module: The module in which the given permission is registered.
          permission_name: The permission name.
          readable_list: List of properties whose values may be viewed.
          editable_list: List of properties whose values may be edited.
          all_readable: When true, all properties are readable; readable_list
            is ignored.
          all_writable: When true, all properties are readable and writable;
            all other parameters controlling read-/write-ability are ignored.
        """
        self._module = module
        self._permission_name = permission_name
        self._readable = self._build_tree(readable_list or [])
        self._editable = self._build_tree(editable_list or [])
        self._all_readable = all_readable
        self._all_writable = all_writable

    def get_name(self):
        return self._permission_name

    @classmethod
    def _build_tree(cls, paths):
        # Arbitrary depth instantiate-on-reference dict constructor
        treebuilder = lambda: collections.defaultdict(treebuilder)

        # Build a tree of nodes from the given paths.
        root = treebuilder()
        for path in paths:
            parts = path.split(schema_fields.Registry.SCHEMA_PATH_SEPARATOR)
            node = root
            for part in parts:
                node = node[part]
        return root

    @classmethod
    def _tree_matches(cls, tree, path):
        for name in path.split(schema_fields.Registry.SCHEMA_PATH_SEPARATOR):
            if name not in tree:
                return False
            tree = tree[name]
        return True

    def applies_to_current_user(self, application_context):
        return roles.Roles.is_user_allowed(
            application_context, self._module, self._permission_name)

    def can_view(self, prop_name=None):
        if self._all_writable or self._all_readable:
            return True
        if prop_name is None:
            return len(self._readable) > 0 or len(self._editable) > 0
        return (self.can_edit(prop_name) or
                self._tree_matches(self._readable, prop_name))

    def can_edit(self, prop_name=None):
        if self._all_writable:
            return True
        if prop_name is None:
            return len(self._editable) > 0
        return self._tree_matches(self._editable, prop_name)


class CourseAdminSchemaPermission(AbstractSchemaPermission):
    """Grants read/write on all settings fields to full course admin role."""

    NAME = 'course_admin'

    def get_name(self):
        return self.NAME

    def applies_to_current_user(self, application_context):
        return roles.Roles.is_course_admin(application_context)

    def can_view(self, prop_name=None):
        return True

    def can_edit(self, prop_name=None):
        return True


class SchemaPermissionRegistry(object):

    # Dictionary, keyed by scope.  Scopes hold sets of permissions.  E.g.,
    # there is a separate scope for each of: course settings, units, and
    # assessments -- each of these has its own schema, and the permissions
    # relevant to each are kept separately.
    #
    # Within each scope's dict is a sub-dict.  This is keyed by the names
    # supplied from AbstractSchemaPermission.get_name().
    PERMISSIONS = collections.defaultdict(dict)

    @classmethod
    def _validate_scope(cls, scope):
        if scope not in cls.PERMISSIONS:
            raise ValueError('scope must be one of "%s"' %
                             '", "'.join(cls.PERMISSIONS.keys()))
        return cls.PERMISSIONS[scope]

    @classmethod
    def add(cls, scope, item):
        """Register a new permissions policy.

        Args:
          scope: A string indicating which schema scope we are checking.
              (e.g., 'course' for course settings, 'unit' for unit schema,
               'assessment' for assesments, and so on.)

          item: An instance of AbstractSchemaPermission granting access to
              components in schemas of the 'scope' kind.
        """

        scope_permissions = cls.PERMISSIONS[scope]
        name = item.get_name()
        if name in scope_permissions:
            raise ValueError('%s is already registered in scope %s' % (
                (name, scope)))
        scope_permissions[name] = item

    @classmethod
    def remove(cls, scope, item_name):
        """Unregister a permissions policy.

        Args:
          scope: A string indicating which schema scope we are checking.
              (e.g., 'course' for course settings, 'unit' for unit schema,
               'assessment' for assesments, and so on.)

          item_name: The name of a permission item, as given from the item's
              get_name().  Note that this is not symmetric with add, and
              that's on purpose - a module's unregister method thus does
              not have to have access to the permission object that was
              likely created in the register() method.
        Returns:
          Removed item, if any.  Lets caller see if the unregistered name
          was previously registered.
        """
        return cls.PERMISSIONS[scope].pop(item_name, None)

    @classmethod
    def _get_active_permissions(cls, app_context, scope):
        """Get the list of active permissions for the current user.

        Args:
          app_context: Standard Course Builder Application Context object.
          scope: A string indicating which schema scope we are checking.
              (e.g., 'course' for course settings, 'unit' for unit schema,
               'assessment' for assesments, and so on.)

        Returns:
          List (possibly empty) of access policies for the current user.
        """
        scope_permissions = cls._validate_scope(scope)
        return [p for p in scope_permissions.itervalues()
                if p.applies_to_current_user(app_context)]

    @classmethod
    def redact_schema_to_permitted_fields(cls, app_context, scope, schema):
        """Delete and/or mark as read-only fields not permitted to user."""

        perms = cls._get_active_permissions(app_context, scope)
        user_can_view = lambda name: any([p.can_view(name) for p in perms])
        user_can_edit = lambda name: any([p.can_edit(name) for p in perms])

        def build_prop_path(prefix, suffix):
            if not prefix:
                return suffix
            return '%s%s%s' % (
                prefix, schema_fields.Registry.SCHEMA_PATH_SEPARATOR, suffix)

        # Here, we know we are operating on a cloned copy of the schema,
        # so we are legitimately modifying what is nominally an append-only
        # object.
        def visit_schema(schema, prefix, in_editable_container=True):
            # pylint: disable=protected-access
            for prop in copy.copy(schema._properties):
                name = build_prop_path(prefix, prop.name)
                if not user_can_view(name):
                    schema._properties.remove(prop)
                elif not in_editable_container or not user_can_edit(name):
                    prop._extra_schema_dict_values['disabled'] = True
            for sub_name, sub_schema in schema._sub_registries.iteritems():
                name = build_prop_path(prefix, sub_name)
                if not user_can_view(name):
                    del schema._sub_registries[name]
                else:
                    visit_schema(sub_schema, name, user_can_edit(name))
        visit_schema(schema, '')
        return schema

    @classmethod
    def _build_checker(cls, scope, sections, can_operate):
        def check_callback(app_context):
            perms = cls._get_active_permissions(app_context, scope)
            return any([can_operate(p, s)
                        for p, s in itertools.product(perms, sections)])
        return check_callback

    @classmethod
    def build_view_checker(cls, scope, sections):
        """Build checker telling whether the current user may view given items.

        When a user accesses Dashboard pages, we need to build a list of
        settings subsections that the current user has view/edit rights to.
        This function returns a checker function that is called back to
        establish the rights of whatever user is accessing the dashboard.

        Args:
          scope: A string indicating which schema scope we are checking.
              (e.g., 'course' for course settings, 'unit' for unit schema,
               'assessment' for assesments, and so on.)

          sections: A list of strings naming areas of the course settings
            tree.  If the user has read access to any section named, the checker
            function will return True.
        Returns:
          A callback function returning a Boolean indicating user access.
          This is suitable for passing to Dashboard functions which bind
          actions to custom checkers.
        """
        return cls._build_checker(
            scope, sections,
            lambda permission, section: permission.can_view(section))

    @classmethod
    def build_edit_checker(cls, scope, sections):
        """Build checker telling whether the current user may edit given items.

        Args:
          scope: A string indicating which schema scope we are checking.
              (e.g., 'course' for course settings, 'unit' for unit schema,
               'assessment' for assesments, and so on.)
          sections: A list of strings naming areas of the course settings
            tree.  If the user has write access to any section named, the
            checker function will return True.
        Returns:
          A callback function returning a Boolean indicating user access.
          This is suitable for passing to Dashboard functions which bind
          actions to custom checkers.
        """
        return cls._build_checker(
            scope, sections,
            lambda permission, section: permission.can_edit(section))


def can_view(app_context, scope):
    """Boolean: Can current user see even one setting, or none at all?

    This provides a simple, rudimentary sanity check used by REST handlers
    to error out early if the given user has no privileges whatsoever.
    Handlers are expected to also iterate through the active permissions
    to verify user access to specific fields being retrieved.

    Args:
      app_context: Standard Course Builder Application Context object.
      scope: A string indicating which schema scope we are checking.
          (e.g., 'course' for course settings, 'unit' for unit schema,
          'assessment' for assesments, and so on.)

    Returns:
      True iff user has read access to at least one setting.
    """
    # pylint: disable=protected-access
    perms = SchemaPermissionRegistry._get_active_permissions(app_context, scope)
    return any([p.can_view() for p in perms])


def can_edit(app_context, scope):
    """Boolean: Can current user write even one setting, or none at all?

    This provides a simple, rudimentary sanity check used by REST handlers
    to error out early if the given user has no privileges whatsoever.
    Handlers are expected to also iterate through the active permissions
    to verify user access to specific fields being altered.

    Args:
      app_context: Standard Course Builder Application Context object.
      scope: A string indicating which schema scope we are checking.
          (e.g., 'course' for course settings, 'unit' for unit schema,
          'assessment' for assesments, and so on.)

    Returns:
      True iff user has write access to at least one setting.
    """
    # pylint: disable=protected-access
    perms = SchemaPermissionRegistry._get_active_permissions(app_context, scope)
    return any([p.can_edit() for p in perms])


def can_view_property(app_context, scope, property_name):
    """Convenience wrapper to check editability of a single property.

    When only a single property's viewability needs to be checked, this
    function collects and abstracts some rather abstruse syntax.

    Args:
      app_context: Standard Course Builder application context object
      scope: A string indicating which schema scope we are checking.
          (e.g., 'course' for course settings, 'unit' for unit schema,
          'assessment' for assesments, and so on.)

    Returns:
      Boolean indicating whether this user may edit that property.
    """
    return SchemaPermissionRegistry.build_view_checker(
        scope, [property_name])(app_context)


def can_edit_property(app_context, scope, property_name):
    """Convenience wrapper to check editability of a single property.

    When only a single property's editability needs to be checked, this
    function collects and abstracts some rather abstruse syntax.

    Args:
      app_context: Standard Course Builder application context object
      scope: A string indicating which schema scope we are checking.
          (e.g., 'course' for course settings, 'unit' for unit schema,
          'assessment' for assesments, and so on.)

    Returns:
      Boolean indicating whether this user may edit that property.
    """
    return SchemaPermissionRegistry.build_edit_checker(
        scope, [property_name])(app_context)
