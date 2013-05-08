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


class Property(object):
    """Property."""

    def __init__(
        self, name, label, property_type, description=None, optional=False):
        self._name = name
        self._label = label
        self._property_type = property_type
        self._description = description
        self._optional = optional

    def name(self):
        return self._name


class Registry(object):
    """Registry is a collection of Property's."""

    def __init__(self, title, description=None):
        self._title = title
        self._registry = {'id': title, 'type': 'object'}
        self._description = description
        if description:
            self._registry['description'] = description
        self._properties = []
        self._sub_registories = {}

    def add_property(self, schema_field):
        """Add a Property to this Registry."""
        self._properties.append(schema_field)

    def add_sub_registry(self, name, title, descirption=None):
        """Add a sub registry to for this Registry."""
        b = Registry(title, descirption)
        self._sub_registories[name] = b
        return b
