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
        self._notify_module_disabled = notify_module_disabled

        Registry.registered_modules[self._name] = self

    def disable(self):
        if self.name in Registry.enabled_module_names:
            Registry.enabled_module_names.remove(self.name)
            if self._notify_module_disabled:
                self._notify_module_disabled()

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

    registered_modules = {}
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
