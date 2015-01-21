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

"""Classes supporting dynamically registering custom unit types."""

__author__ = 'Abhinav Khandelwal (abhinavk@google.com)'

import logging


class UnitTypeRegistry(object):
    """A registry that holds all custom modules."""

    registered_unit_types = {}

    @classmethod
    def register_type(cls, custom_type):
        identifier = custom_type.identifier
        if identifier in cls.registered_unit_types.keys():
            logging.fatal(custom_type.identifier + ' already registered')
            return
        cls.registered_unit_types[identifier] = custom_type

    @classmethod
    def get(cls, identifier):
        return cls.registered_unit_types.get(identifier, None)

    @classmethod
    def has_type(cls, identifier):
        return identifier in cls.registered_unit_types

    @classmethod
    def list(cls):
        return cls.registered_unit_types.values()

    @classmethod
    def i18n_resource_key(cls, course, unit):
        assert unit.is_custom_unit()
        cu = cls.get(unit.custom_unit_type)
        if not cu:
            return None
        return cu.i18n_resource_key(course, unit)


class CustomUnit(object):
    """A class that holds unit information."""

    def __init__(self, identifier, name, rest_handler_cls, visible_url_fn,
                 extra_js_files=None, create_helper=None, cleanup_helper=None,
                 is_graded=False, i18n_resource_key_fn=None):
        self.name = name
        self.identifier = identifier
        self.rest_handler = rest_handler_cls

        # Visible url function should take Unit object as parameter and return
        # the visible url for the unit page. Look at the example usage below
        self.visible_url_fn = visible_url_fn
        self.extra_js_files = extra_js_files

        # Create helper function should take Course and Unit object as parameter
        self.create_helper = create_helper

        # Delete helper function should take Course and Unit object as parameter
        self.cleanup_helper = cleanup_helper

        # Is this custom unit graded.
        self.is_graded = is_graded

        # Function to generate i18n resource keys
        self._i18n_resource_key_fn = i18n_resource_key_fn

        UnitTypeRegistry.register_type(self)

    def visible_url(self, unit):
        return self.visible_url_fn(unit)

    def add_unit(self, course, unit):
        if self.create_helper:
            self.create_helper(course, unit)

    def delete_unit(self, course, unit):
        if self.cleanup_helper:
            self.cleanup_helper(course, unit)

    def i18n_resource_key(self, course, unit):
        if self._i18n_resource_key_fn is not None:
            return self._i18n_resource_key_fn(course, unit)
        return None
