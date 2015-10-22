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

"""Manages mapping of users to roles and roles to privileges."""

__author__ = 'Pavel Simakov (psimakov@google.com)'

import collections
import config
import messages

from common import utils
from common import users
from models import MemcacheManager
from models import RoleDAO

GCB_ADMIN_LIST = config.ConfigProperty(
    'gcb_admin_user_emails', str, messages.SITE_SETTINGS_SITE_ADMIN_EMAILS, '',
    label='Site Admin Emails', multiline=True)

KEY_COURSE = 'course'
KEY_ADMIN_USER_EMAILS = 'admin_user_emails'

GCB_WHITELISTED_USERS = config.ConfigProperty(
    'gcb_user_whitelist', str, messages.SITE_SETTINGS_WHITELIST, '',
    label='Whitelist', multiline=True)

Permission = collections.namedtuple('Permission', ['name', 'description'])


class Roles(object):
    """A class that provides information about user roles."""

    # Maps module names to callbacks which generate permissions.
    # See register_permissions for the structure of the callbacks.
    _REGISTERED_PERMISSIONS = collections.OrderedDict()

    memcache_key = 'roles.Roles.users_to_permissions_map'

    @classmethod
    def is_direct_super_admin(cls):
        """Checks if current user is a super admin, without delegation."""
        return users.get_current_user() and users.is_current_user_admin()

    @classmethod
    def is_super_admin(cls):
        """Checks if current user is a super admin, possibly via delegation."""
        if cls.is_direct_super_admin():
            return True
        return cls._user_email_in(users.get_current_user(),
                                  GCB_ADMIN_LIST.value)

    @classmethod
    def is_course_admin(cls, app_context):
        """Checks if a user is a course admin, possibly via delegation."""
        if cls.is_super_admin():
            return True

        if KEY_COURSE in app_context.get_environ():
            environ = app_context.get_environ()[KEY_COURSE]
            if KEY_ADMIN_USER_EMAILS in environ:
                allowed = environ[KEY_ADMIN_USER_EMAILS]
                user = users.get_current_user()
                if allowed and cls._user_email_in(user, allowed):
                    return True
        return False

    @classmethod
    def is_user_whitelisted(cls, app_context):
        user = users.get_current_user()
        global_whitelist = GCB_WHITELISTED_USERS.value.strip()
        course_whitelist = app_context.whitelist.strip()

        # Most-specific whitelist used if present.
        if course_whitelist:
            return cls._user_email_in(user, course_whitelist)

        # Global whitelist if no course whitelist
        elif global_whitelist:
            return cls._user_email_in(user, global_whitelist)

        # Lastly, no whitelist = no restrictions
        else:
            return True

    @classmethod
    def _user_email_in(cls, user, text):
        email_list = [email.lower() for email in utils.text_to_list(
            text, utils.BACKWARD_COMPATIBLE_SPLITTER)]
        return bool(user and user.email().lower() in email_list)

    @classmethod
    def update_permissions_map(cls):
        """Puts a dictionary mapping users to permissions in memcache.

        A dictionary is constructed, using roles information from the datastore,
        mapping user emails to dictionaries that map module names to
        sets of permissions.

        Returns:
            The created dictionary.
        """
        permissions_map = {}
        for role in RoleDAO.get_all():
            for user in role.users:
                user_permissions = permissions_map.setdefault(user, {})
                for (module_name, permissions) in role.permissions.iteritems():
                    module_permissions = user_permissions.setdefault(
                        module_name, set())
                    module_permissions.update(permissions)

        MemcacheManager.set(cls.memcache_key, permissions_map)
        return permissions_map

    @classmethod
    def _load_permissions_map(cls):
        """Loads the permissions map from Memcache or creates it if needed."""
        permissions_map = MemcacheManager.get(cls.memcache_key)
        if permissions_map is None:  # As opposed to {}, which is valid.
            permissions_map = cls.update_permissions_map()
        return permissions_map

    @classmethod
    def is_user_allowed(cls, app_context, module, permission):
        """Check whether the current user is assigned a certain permission.

        Args:
            app_context: sites.ApplicationContext of the relevant course
            module: module object that registered the permission.
            permission: string specifying the permission.

        Returns:
            boolean indicating whether the current user is allowed to perform
                the action associated with the permission.
        """
        if cls.is_course_admin(app_context):
            return True
        if not module or not permission or not users.get_current_user():
            return False
        permissions_map = cls._load_permissions_map()
        user_permissions = permissions_map.get(
            users.get_current_user().email(), {})
        return permission in user_permissions.get(module.name, set())

    @classmethod
    def in_any_role(cls, app_context):
        user = users.get_current_user()
        if not user:
            return False
        permissions_map = cls._load_permissions_map()
        user_permissions = permissions_map.get(user.email(), {})
        return bool(user_permissions)

    @classmethod
    def register_permissions(cls, module, callback_function):
        """Registers a callback function that generates permissions.

        A callback should return an iteratable of permissions of the type
            Permission(permission_name, permission_description)

        Example:
            Module 'module-werewolf' registers permissions 'can_howl' and
            'can_hunt' by defining a function callback_werewolf returning:
            [
                Permission('can_howl', 'Can howl to the moon'),
                Permission('can_hunt', 'Can hunt for sheep')
            ]
            In order to register these permissions the module calls
                register_permissions(module, callback_werewolf) with the module
                whose module.name is 'module-werewolf'.

        Args:
            module: module object that registers the permissions.
            callback_function: a function accepting ApplicationContext as sole
                argument and returning a list of permissions.
        """
        assert module is not None
        assert module.name
        assert module not in cls._REGISTERED_PERMISSIONS
        cls._REGISTERED_PERMISSIONS[module] = callback_function

    @classmethod
    def unregister_permissions(cls, module):
        del cls._REGISTERED_PERMISSIONS[module]

    @classmethod
    def get_modules(cls):
        return cls._REGISTERED_PERMISSIONS.iterkeys()

    @classmethod
    def get_permissions(cls):
        return cls._REGISTERED_PERMISSIONS.iteritems()
