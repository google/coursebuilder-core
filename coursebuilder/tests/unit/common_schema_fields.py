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

"""Unit tests for common/schema_fields.py."""

__author__ = 'John Orr (jorr@google.com)'

import json
import unittest
from common import schema_fields


def remove_whitespace(s):
    return ''.join(s.split())


class BaseFieldTests(unittest.TestCase):
    """Base class for the tests on a schema field."""

    def assert_json_schema_value(self, expected, registry):
        self.assertEquals(
            remove_whitespace(expected),
            remove_whitespace(json.dumps(registry.get_json_schema())))

    def assert_schema_dict_value(self, expected, registry):
        self.assertEquals(
            remove_whitespace(expected),
            remove_whitespace(json.dumps(registry.get_schema_dict_entry())))


class SchemaFieldTests(BaseFieldTests):
    """Unit tests for common.schema_fields.SchemaField."""

    def test_simple_field(self):
        field = schema_fields.SchemaField('aName', 'aLabel', 'aType')
        expected = '{"type":"aType"}'
        self.assert_json_schema_value(expected, field)
        expected = '{"label":"aLabel"}'
        self.assert_schema_dict_value(expected, field)
        self.assertEquals('aName', field.name)

    def test_extra_schema_dict(self):
        field = schema_fields.SchemaField(
            'aName', 'aLabel', 'aType',
            extra_schema_dict_values={'a': 'A', 'b': 'B'})
        expected = '{"a": "A", "b": "B", "label": "aLabel"}'
        self.assert_schema_dict_value(expected, field)


class FieldArrayTests(BaseFieldTests):
    """Unit tests for common.schema_fields.FieldArray."""

    def test_field_array_with_simple_members(self):
        array = schema_fields.FieldArray(
            'aName', 'aLabel',
            item_type=schema_fields.SchemaField(
                'unusedName', 'unusedLabel', 'aType'))
        expected = '{"items": {"type": "aType"}, "type": "array"}'
        self.assert_json_schema_value(expected, array)
        expected = '{"label": "aLabel"}'
        self.assert_schema_dict_value(expected, array)

    def test_field_array_with_object_members(self):
        object_type = schema_fields.FieldRegistry('object_title')
        object_type.add_property(schema_fields.SchemaField(
            'prop_name', 'prop_label', 'prop_type'))
        field = schema_fields.FieldArray(
            'aName', 'aLabel', item_type=object_type)

        expected = """
{
  "items": {
    "type": "object",
    "id": "object_title",
    "properties": {
      "prop_name": {"type":"prop_type"}
    }
  },
  "type":"array"}
"""
        self.assert_json_schema_value(expected, field)
        expected = '{"label": "aLabel"}'
        self.assert_schema_dict_value(expected, field)

    def test_extra_schema_dict(self):
        array = schema_fields.FieldArray(
            'aName', 'aLabel',
            item_type=schema_fields.SchemaField(
                'unusedName', 'unusedLabel', 'aType'),
            extra_schema_dict_values={'a': 'A', 'b': 'B'})
        expected = '{"a": "A", "b": "B", "label": "aLabel"}'
        self.assert_schema_dict_value(expected, array)


class FieldRegistryTests(unittest.TestCase):
    """Unit tests for common.schema_fields.FieldRegistry."""

    def assert_json_schema_value(self, expected, registry):
        self.assertEquals(
            remove_whitespace(expected),
            remove_whitespace(registry.get_json_schema()))

    def assert_schema_dict_value(self, expected, registry):
        self.assertEquals(
            remove_whitespace(expected),
            remove_whitespace(json.dumps(registry.get_schema_dict())))

    def test_single_property(self):
        reg = schema_fields.FieldRegistry(
            'registry_name', 'registry_description')
        reg.add_property(schema_fields.SchemaField(
            'field_name', 'field_label', 'property_type',
            description='property_description'))
        expected = """
{
  "properties": {
    "field_name": {
      "type": "property_type",
      "description": "property_description"
    }
  },
  "type": "object",
  "id": "registry_name",
  "description": "registry_description"
}"""
        self.assert_json_schema_value(expected, reg)
        expected = """
[
  [["title"], "registry_name"],
  [["properties","field_name","_inputex"], {
    "description": "property_description",
    "label":"field_label"
  }]
]
"""
        self.assert_schema_dict_value(expected, reg)

    def test_single_property_with_select_data(self):
        reg = schema_fields.FieldRegistry(
            'registry_name', 'registry_description')
        reg.add_property(schema_fields.SchemaField(
            'field_name', 'field_label', 'select',
            select_data=[('a', 'A'), ('b', 'B')]))
        expected = """
{
  "properties": {
    "field_name": {
      "type": "select"
    }
  },
  "type": "object",
  "id": "registry_name",
  "description": "registry_description"
}"""
        self.assert_json_schema_value(expected, reg)
        expected = """
[
  [["title"],"registry_name"],
  [["properties","field_name","_inputex"],{
    "choices":[
      {"value": "a", "label": "A"},
      {"value": "b","label": "B"}],
    "label":"field_label"
  }]
]
"""
        self.assert_schema_dict_value(expected, reg)

    def test_object_with_array_property(self):
        reg = schema_fields.FieldRegistry(
            'registry_name', 'registry_description')
        reg.add_property(schema_fields.SchemaField(
            'field_name', 'field_label', 'field_type',
            description='field_description'))
        reg.add_property(schema_fields.FieldArray(
            'array_name', 'array_label',
            item_type=schema_fields.SchemaField(
                'unusedName', 'unusedLabel', 'aType')))

        expected = """
{
  "properties": {
    "field_name": {
      "type": "field_type",
      "description": "field_description"
    },
    "array_name": {
      "items": {"type": "aType"},
      "type":"array"
    }
  },
  "type": "object",
  "id": "registry_name",
  "description": "registry_description"
}
"""
        self.assert_json_schema_value(expected, reg)

    def test_extra_schema_dict(self):
        reg = schema_fields.FieldRegistry(
            'aName', 'aLabel',
            extra_schema_dict_values={'a': 'A', 'b': 'B'})
        expected = """
[
  [["title"], "aName"],
  [["_inputex"], {"a": "A", "b": "B"}]]
"""
        self.assert_schema_dict_value(expected, reg)
