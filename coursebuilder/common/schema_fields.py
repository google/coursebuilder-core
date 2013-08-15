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

"""Mapping from schema to backend properties."""

__author__ = 'Abhinav Khandelwal (abhinavk@google.com)'

import collections
import json
from models.property import Property
from models.property import Registry


class SchemaField(Property):
    """SchemaField defines a simple field in REST API."""

    def __init__(
        self, name, label, property_type, select_data=None, description=None,
        optional=False, hidden=False, editable=True,
        extra_schema_dict_values=None):
        Property.__init__(
            self, name, label, property_type, select_data=select_data,
            description=description, optional=optional,
            extra_schema_dict_values=extra_schema_dict_values)
        self._hidden = hidden
        self._editable = editable

    def get_json_schema_dict(self):
        """Get the JSON schema for this field."""
        prop = {}
        prop['type'] = self._property_type
        if self._optional:
            prop['optional'] = self._optional
        if self._description:
            prop['description'] = self._description
        return prop

    def _get_schema_dict(self, prefix_key):
        """Get Schema annotation dictionary for this field."""
        if self._extra_schema_dict_values:
            schema = self._extra_schema_dict_values
        else:
            schema = {}
        schema['label'] = self._label
        if self._hidden:
            schema['_type'] = 'hidden'
        elif not self._editable:
            schema['_type'] = 'uneditable'
        elif self._select_data and '_type' not in schema:
            schema['_type'] = 'select'

        if 'date' is self._property_type:
            schema['dateFormat'] = 'Y/m/d'
            schema['valueFormat'] = 'Y/m/d'
        elif self._select_data:
            choices = []
            for value, label in self._select_data:
                choices.append(
                    {'value': value, 'label': unicode(label)})
            schema['choices'] = choices

        if self._description:
            schema['description'] = self._description

        return [(prefix_key + ['_inputex'], schema)]


class FieldArray(SchemaField):
    """FieldArray is an array with object or simple items in the REST API."""

    def __init__(
        self, name, label, description=None, item_type=None,
        extra_schema_dict_values=None):

        super(FieldArray, self).__init__(
            name, label, 'array', description=description,
            extra_schema_dict_values=extra_schema_dict_values)
        self._item_type = item_type

    def get_json_schema_dict(self):
        json_schema = super(FieldArray, self).get_json_schema_dict()
        json_schema['items'] = self._item_type.get_json_schema_dict()
        return json_schema

    def _get_schema_dict(self, prefix_key):
        dict_list = super(FieldArray, self)._get_schema_dict(prefix_key)
        # pylint: disable-msg=protected-access
        dict_list += self._item_type._get_schema_dict(prefix_key + ['items'])
        # pylint: enable-msg=protected-access
        return dict_list


class FieldRegistry(Registry):
    """FieldRegistry is an object with SchemaField properties in REST API."""

    def add_sub_registry(
        self, name, title=None, description=None, registry=None):
        """Add a sub registry to for this Registry."""
        if not registry:
            registry = FieldRegistry(title, description=description)
        self._sub_registories[name] = registry
        return registry

    def get_json_schema_dict(self):
        schema_dict = dict(self._registry)
        schema_dict['properties'] = collections.OrderedDict()
        for schema_field in self._properties:
            schema_dict['properties'][schema_field.name] = (
                schema_field.get_json_schema_dict())
        for key in self._sub_registories.keys():
            schema_dict['properties'][key] = (
                self._sub_registories[key].get_json_schema_dict())
        return schema_dict

    def get_json_schema(self):
        """Get the json schema for this API."""
        return json.dumps(self.get_json_schema_dict())

    def _get_schema_dict(self, prefix_key):
        """Get schema dict for this API."""
        title_key = list(prefix_key)
        title_key.append('title')
        schema_dict = [(title_key, self._title)]

        if self._extra_schema_dict_values:
            key = list(prefix_key)
            key.append('_inputex')
            schema_dict.append([key, self._extra_schema_dict_values])

        base_key = list(prefix_key)
        base_key.append('properties')

        # pylint: disable-msg=protected-access
        for schema_field in self._properties:
            key = base_key + [schema_field.name]
            schema_dict += schema_field._get_schema_dict(key)
        # pylint: enable-msg=protected-access

        for key in self._sub_registories.keys():
            sub_registry_key_prefix = list(base_key)
            sub_registry_key_prefix.append(key)
            sub_registry = self._sub_registories[key]
            # pylint: disable-msg=protected-access
            for entry in sub_registry._get_schema_dict(sub_registry_key_prefix):
                schema_dict.append(entry)
            # pylint: enable-msg=protected-access
        return schema_dict

    def get_schema_dict(self):
        """Get schema dict for this API."""
        return self._get_schema_dict(list())

    def _add_entry(self, key_part_list, value, entity):
        if len(key_part_list) == 1:
            entity[key_part_list[0]] = value
            return
        key = key_part_list.pop()
        if not entity.has_key(key):
            entity[key] = {}
        else:
            assert type(entity[key]) == type(dict())
        self._add_entry(key_part_list, value, entity[key])

    def convert_json_to_entity(self, json_entry, entity):
        assert type(json_entry) == type(dict())
        for key in json_entry.keys():
            if type(json_entry[key]) == type(dict()):
                self.convert_json_to_entity(json_entry[key], entity)
            else:
                key_parts = key.split(':')
                key_parts.reverse()
                self._add_entry(key_parts, json_entry[key], entity)

    def _get_field_value(self, key_part_list, entity):
        if len(key_part_list) == 1:
            if entity.has_key(key_part_list[0]):
                return entity[key_part_list[0]]
            return None
        key = key_part_list.pop()
        if entity.has_key(key):
            return self._get_field_value(key_part_list, entity[key])
        return None

    def convert_entity_to_json_entity(self, entity, json_entry):
        for schema_field in self._properties:
            field_name = schema_field.name
            field_name_parts = field_name.split(':')
            field_name_parts.reverse()
            value = self._get_field_value(field_name_parts, entity)
            if type(value) != type(None):
                json_entry[field_name] = value

        for key in self._sub_registories.keys():
            json_entry[key] = {}
            self._sub_registories[key].convert_entity_to_json_entity(
                entity, json_entry[key])
