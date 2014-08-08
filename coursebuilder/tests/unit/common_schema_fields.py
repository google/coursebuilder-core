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

    def assert_json_schema_value(self, expected, field):
        self.assertEquals(
            remove_whitespace(expected),
            remove_whitespace(json.dumps(field.get_json_schema_dict())))

    def assert_schema_dict_value(self, expected, field):
        self.assertEquals(
            remove_whitespace(expected),
            remove_whitespace(json.dumps(field._get_schema_dict([]))))


class SchemaFieldTests(BaseFieldTests):
    """Unit tests for common.schema_fields.SchemaField."""

    def test_simple_field(self):
        field = schema_fields.SchemaField('aName', 'aLabel', 'aType')
        expected = '{"type":"aType"}'
        self.assert_json_schema_value(expected, field)
        expected = '[[["_inputex"], {"label": "aLabel"}]]'
        self.assert_schema_dict_value(expected, field)
        self.assertEquals('aName', field.name)

    def test_extra_schema_dict(self):
        field = schema_fields.SchemaField(
            'aName', 'aLabel', 'aType',
            extra_schema_dict_values={'a': 'A', 'b': 'B'})
        expected = '[[["_inputex"], {"a": "A", "b": "B", "label": "aLabel"}]]'
        self.assert_schema_dict_value(expected, field)

    def test_uneditable_field(self):
        field = schema_fields.SchemaField(
            'aName', 'aLabel', 'aType', editable=False)
        expected = '{"type":"aType"}'
        self.assert_json_schema_value(expected, field)
        expected = ('[[["_inputex"], {"_type": "uneditable", '
                    '"label": "aLabel"}]]')
        self.assert_schema_dict_value(expected, field)
        self.assertEquals('aName', field.name)

    def test_hidden_field(self):
        field = schema_fields.SchemaField('aName', 'aLabel', 'aType',
                                          hidden=True)
        expected = '{"type":"aType"}'
        self.assert_json_schema_value(expected, field)
        expected = '[[["_inputex"], {"_type": "hidden", "label": "aLabel"}]]'
        self.assert_schema_dict_value(expected, field)
        self.assertEquals('aName', field.name)


class FieldArrayTests(BaseFieldTests):
    """Unit tests for common.schema_fields.FieldArray."""

    def test_field_array_with_simple_members(self):
        array = schema_fields.FieldArray(
            'aName', 'aLabel',
            item_type=schema_fields.SchemaField(
                'unusedName', 'field_label', 'aType'))
        expected = """
{
  "items": {"type": "aType"},
  "type": "array"
}"""
        self.assert_json_schema_value(expected, array)
        expected = """
[
  [["_inputex"],{"label":"aLabel"}],
  [["items","_inputex"],{"label":"field_label"}]
]
"""
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
        expected = """
[
  [["_inputex"],{"label":"aLabel"}],
  [["items","title"],"object_title"],
  [["items","properties","prop_name","_inputex"],{"label":"prop_label"}]
]
"""
        self.assert_schema_dict_value(expected, field)

    def test_extra_schema_dict(self):
        array = schema_fields.FieldArray(
            'aName', 'aLabel',
            item_type=schema_fields.SchemaField(
                'unusedName', 'field_label', 'aType'),
            extra_schema_dict_values={'a': 'A', 'b': 'B'})
        expected = """
[
  [["_inputex"],{"a":"A","b":"B","label":"aLabel"}],
  [["items","_inputex"],{"label":"field_label"}]]
"""
        self.assert_schema_dict_value(expected, array)


class FieldRegistryTests(BaseFieldTests):
    """Unit tests for common.schema_fields.FieldRegistry."""

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
            'field_name', 'field_label', 'string',
            select_data=[('a', 'A'), ('b', 'B')]))
        expected = """
{
  "properties": {
    "field_name": {
      "type": "string"
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
    "_type": "select",
    "choices":[
      {"value": "a", "label": "A"},
      {"value": "b","label": "B"}],
    "label":"field_label"
  }]
]
"""
        self.assert_schema_dict_value(expected, reg)

    def test_select_data_values_retain_boolean_and_numeric_type_in_json(self):
        reg = schema_fields.FieldRegistry(
            'registry_name', 'registry_description')
        reg.add_property(schema_fields.SchemaField(
            'field_name', 'field_label', 'string',
            select_data=[(True, 'A'), (12, 'B'), ('c', 'C')]))
        expected = """
[
  [["title"],"registry_name"],
  [["properties","field_name","_inputex"],{
    "_type": "select",
    "choices":[
      {"value": true, "label": "A"},
      {"value": 12,"label": "B"},
      {"value": "c","label": "C"}],
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

    def test_mc_question_schema(self):
        """The multiple choice question schema is a good end-to-end example."""
        mc_question = schema_fields.FieldRegistry(
            'MC Question',
            extra_schema_dict_values={'className': 'mc-question'})

        mc_question.add_property(
            schema_fields.SchemaField('question', 'Question', 'string'))

        choice_type = schema_fields.FieldRegistry(
            'choice', extra_schema_dict_values={'className': 'mc-choice'})
        choice_type.add_property(
            schema_fields.SchemaField('text', 'Text', 'string'))
        choice_type.add_property(
            schema_fields.SchemaField('score', 'Score', 'string'))
        choice_type.add_property(
            schema_fields.SchemaField('feedback', 'Feedback', 'string'))

        choices_array = schema_fields.FieldArray(
            'choices', 'Choices', item_type=choice_type)

        mc_question.add_property(choices_array)

        expected = """
{
  "type":"object",
  "id":"MCQuestion",
  "properties":{
    "question":{"type":"string"},
    "choices":{
      "items":{
        "type":"object",
        "id":"choice",
        "properties":{
          "text":{"type":"string"},
          "score":{"type":"string"},
          "feedback":{"type":"string"}
        }
      },
      "type":"array"
    }
  }
}
"""
        self.assert_json_schema_value(expected, mc_question)

        expected = """
[
  [["title"],"MCQuestion"],
  [["_inputex"],{"className":"mc-question"}],
  [["properties","question","_inputex"],{"label":"Question"}],
  [["properties","choices","_inputex"],{"label":"Choices"}],
  [["properties","choices","items","title"],"choice"],
  [["properties","choices","items","_inputex"],{"className":"mc-choice"}],
  [["properties","choices","items","properties","text","_inputex"],{
    "label":"Text"
  }],
  [["properties","choices","items","properties","score","_inputex"],{
    "label":"Score"
  }],
  [["properties","choices","items","properties","feedback","_inputex"],{
    "label":"Feedback"
  }]
 ]
"""
        self.assert_schema_dict_value(expected, mc_question)

    def test_validate(self):

      def fail(value, errors):
        errors.append(value)

      registry = schema_fields.FieldRegistry('Test Registry')
      registry.add_property(schema_fields.SchemaField(
          'top_level_bad', 'Top Level Bad Item', 'string', optional=True,
          validator=fail))
      registry.add_property(schema_fields.SchemaField(
          'top_level_good', 'Top Level Good Item', 'string', optional=True))
      sub_registry = registry.add_sub_registry('child', 'Child Registry')
      sub_registry.add_property(schema_fields.SchemaField(
          'child:bad', 'Top Level Bad Item', 'string', optional=True,
          validator=fail))
      sub_registry.add_property(schema_fields.SchemaField(
          'child:good', 'Top Level Good Item', 'string', optional=True))

      child_bad_value = 'child_bad_value'
      top_level_bad_value = 'top_level_bad_value'
      errors = []
      payload = {
          'top_level_bad': top_level_bad_value,
          'top_level_good': 'top_level_good_value',
          'child': {
              'bad': child_bad_value,
              'good': 'child_good_value',
          }
      }
      registry.validate(payload, errors)

      self.assertEqual([top_level_bad_value, child_bad_value], errors)
