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

"""Classes supporting dynamically registering custom modules."""

__author__ = 'Pavel Simakov (psimakov@google.com)'

MODULE_NAME = 'Core REST services'
ALL_LOCALES_PERMISSION = 'can_pick_all_locales'
SEE_DRAFTS_PERMISSION = 'can_see_draft_content'

import collections
import messages
import roles

class Module(object):
    """A class that holds module information."""

    def __init__(
        self, name, desc, global_routes, namespaced_routes,
        notify_module_enabled=None, notify_module_disabled=None):
        self._name = name
        self._desc = desc
        self._global_routes = global_routes
        self._namespaced_routes = namespaced_routes
        self._notify_module_enabled = notify_module_enabled
        self._notify_module_disabled = (
            notify_module_disabled or Module.module_disabling_is_deprecated)

        Registry.registered_modules[self._name] = self

    def disable(self):
        raise NotImplementedError('Disabling modules is not supported.')

    @staticmethod
    def module_disabling_is_deprecated():
        raise NotImplementedError('Disabling modules is not supported.')

    def enable(self):
        Registry.enabled_module_names.add(self.name)
        if self._notify_module_enabled:
            self._notify_module_enabled()

    @property
    def enabled(self):
        return self.name in Registry.enabled_module_names

    @property
    def name(self):
        return self._name

    @property
    def desc(self):
        return self._desc

    @property
    def global_routes(self):
        if self.name in Registry.enabled_module_names:
            return self._global_routes
        else:
            return []

    @property
    def namespaced_routes(self):
        if self.name in Registry.enabled_module_names:
            return self._namespaced_routes
        else:
            return []


class Registry(object):
    """A registry that holds all custom modules."""

    registered_modules = collections.OrderedDict()
    enabled_module_names = set()

    @classmethod
    def get_all_routes(cls):
        global_routes = []
        namespaced_routes = []
        for registered_module in cls.registered_modules.values():
            if registered_module.enabled:
                # Only populate the routing table with enabled modules.
                global_routes += registered_module.global_routes
                namespaced_routes += registered_module.namespaced_routes
        return global_routes, namespaced_routes


core_module = None

def register_core_module(global_handlers, namespaced_handlers):
    """Creates module containing core functionality.

    This is not really a module, in the sense that it's not optional.
    However, the items present are much more conveniently implemented
    by using the Module logic.  Thus, rather than putting something
    in coursebuilder/modules/core, we have this here, so as to indicate
    that it's not really a module in the broader sense.
    """

    global core_module  # pylint: disable=global-statement

    def permissions_callback(unused_app_context):
        return [
            roles.Permission(
                ALL_LOCALES_PERMISSION,
                messages.ROLES_PERMISSION_ALL_LOCALES_DESCRIPTION),
            roles.Permission(
                SEE_DRAFTS_PERMISSION,
                messages.ROLES_PERMISSION_SEE_DRAFTS_DESCRIPTION)
        ]

    def notify_module_enabled():
        roles.Roles.register_permissions(core_module, permissions_callback)

    core_module = Module(
        MODULE_NAME, 'A module to host core REST services',
        global_handlers, namespaced_handlers,
        notify_module_enabled=notify_module_enabled)
    core_module.enable()


def can_pick_all_locales(app_context):
    return roles.Roles.is_user_allowed(
        app_context, core_module, ALL_LOCALES_PERMISSION)


def can_see_drafts(app_context):
    return roles.Roles.is_user_allowed(
        app_context, core_module, SEE_DRAFTS_PERMISSION)
