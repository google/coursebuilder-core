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

"""Properties and its collections."""

__author__ = 'Abhinav Khandelwal (abhinavk@google.com)'

import collections


class Property(object):
    """Property."""

    def __init__(
        self, name, label, property_type, select_data=None, description=None,
        optional=False, extra_schema_dict_values=None):
        self._name = name
        self._label = label
        self._property_type = property_type
        self._select_data = select_data
        self._description = description
        self._optional = optional
        self._extra_schema_dict_values = extra_schema_dict_values

    @property
    def name(self):
        return self._name


class Registry(object):
    """Registry is a collection of Property's."""

    def __init__(self, title, description=None, extra_schema_dict_values=None):
        self._title = title
        self._registry = {'id': title, 'type': 'object'}
        self._description = description
        if description:
            self._registry['description'] = description
        self._extra_schema_dict_values = extra_schema_dict_values
        self._properties = []
        self._sub_registories = collections.OrderedDict()

    @property
    def title(self):
        return self._title

    def add_property(self, schema_field):
        """Add a Property to this Registry."""
        self._properties.append(schema_field)

    def add_sub_registry(
        self, name, title=None, description=None, registry=None):
        """Add a sub registry to for this Registry."""
        if not registry:
            registry = Registry(title, description)
        self._sub_registories[name] = registry
        return registry

    def has_subregistries(self):
        return True if self._sub_registories else False
