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

import copy
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


class StructureRecursionTests(unittest.TestCase):

    def setUp(self):
        super(StructureRecursionTests, self).setUp()
        parent = schema_fields.FieldRegistry('parent_dict_title')
        child = parent.add_sub_registry('child_dict_name', 'child_dict_title')

        simple_array_type = schema_fields.SchemaField(
            'simple_array_type_name', 'simple_array_type_title', 'type1')
        parent.add_property(schema_fields.FieldArray(
            'simple_array_prop_name', 'simple_array_prop_label',
            item_type=simple_array_type))

        complex_array_type = schema_fields.FieldRegistry(
            'complex_array_type_title')
        array_child = complex_array_type.add_sub_registry(
            'complex_array_child_name', 'array_child_title')

        parent.add_property(schema_fields.FieldArray(
            'complex_array_prop_name', 'complex_array_prop_label',
            item_type=complex_array_type))
        parent.add_property(schema_fields.SchemaField(
            'parent_prop', 'X', 'type2'))
        child.add_property(schema_fields.SchemaField(
            'child_prop', 'X', 'type3'))
        complex_array_type.add_property(schema_fields.SchemaField(
            'complex_array_type_prop', 'X', 'type4'))
        array_child.add_property(schema_fields.SchemaField(
            'array_child_p1', 'X', 'type5'))
        array_child.add_property(schema_fields.SchemaField(
            'array_child_p2', 'X', 'type6'))
        self.schema = parent

        self.entity = {
            "parent_prop": "parent_prop_value",
            "child_dict_name": {
                "child_prop": "child_prop_value"
            },
            "simple_array_prop_name": [
                "simple_array_prop_value_000",
                "simple_array_prop_value_001",
                "simple_array_prop_value_002"
            ],
            "complex_array_prop_name": [
                {
                    "complex_array_type_prop": "complex_array_prop_value_000",
                    "complex_array_child_name": {
                        "array_child_p1": "array_child_p1_value_000",
                        "array_child_p2": "array_child_p2_value_000"
                    }
                },
                {
                    "complex_array_type_prop": "complex_array_prop_value_001",
                    "complex_array_child_name": {
                        "array_child_p1": "array_child_p1_value_001",
                        "array_child_p2": "array_child_p2_value_001"
                    }
                },
                {
                    "complex_array_type_prop": "complex_array_prop_value_002",
                    "complex_array_child_name": {
                        "array_child_p1": "array_child_p1_value_002",
                        "array_child_p2": "array_child_p2_value_002"
                    }
                }
            ]
        }


class ComplexDisplayTypeTests(StructureRecursionTests):
    def test_complex_recursion(self):
        self.assertEquals(
            set(self.schema.get_display_types()),
            set([
                'array', 'type1', 'type2', 'type3', 'type4', 'type5', 'type6',
                'group']))


class DisplayTypeTests(unittest.TestCase):
    def test_simple_field(self):
        self.assertEquals(
            set(schema_fields.SchemaField(
                'x', 'x', 'string').get_display_types()),
            set(['string']))

    def test_automatically_overridden_type(self):
        self.assertEquals(
            set(schema_fields.SchemaField(
                'x', 'x', 'int', select_data={'a':'b'}).get_display_types()),
            set(['select']))

    def test_manually_overridden_types_are_stronger(self):
        self.assertEquals(
            set(schema_fields.SchemaField(
                'x', 'x', 'int', select_data={'a':'b'},
                extra_schema_dict_values={"_type": "special-select"}
                ).get_display_types()),
            set(['special-select']))

    def test_field_registry(self):
        registry = schema_fields.FieldRegistry(None, '')
        registry.add_property(schema_fields.SchemaField('x', 'x', 'string'))
        registry.add_property(schema_fields.SchemaField('y', 'y', 'datetime'))

        sub_registry = registry.add_sub_registry('sub')
        sub_registry.add_property(schema_fields.SchemaField(
            'z', 'z', 'integer'))

        self.assertEquals(
            set(registry.get_display_types()),
            set(['string', 'datetime', 'integer', 'group']))

    def test_simple_field_array(self):
        self.assertEquals(
            set(schema_fields.FieldArray(
                'x', 'x', item_type=schema_fields.SchemaField(
                    None, None, 'string')).get_display_types()),
            set(['array', 'string']))

    def test_complex_field_array(self):
        item_type = schema_fields.FieldRegistry(None, '')
        item_type.add_property(schema_fields.SchemaField('x', 'x', 'string'))
        item_type.add_property(schema_fields.SchemaField('y', 'y', 'datetime'))

        self.assertEquals(
            set(schema_fields.FieldArray(
                'x', 'x', item_type=item_type).get_display_types()),
            set(['array', 'string', 'datetime', 'group']))


class CloneItemsNamedTests(StructureRecursionTests):

    def test_clone_no_paths(self):
        ret = self.schema.clone_only_items_named([])
        self.assertEquals([], ret._properties)
        self.assertEquals({}, ret._sub_registries)

    def test_clone_toplevel_prop(self):
        ret = self.schema.clone_only_items_named(['parent_prop'])
        self.assertEquals(1, len(ret._properties))
        self.assertEquals('parent_prop', ret._properties[0]._name)
        self.assertEquals({}, ret._sub_registries)

    def test_clone_toplevel_struct(self):
        ret = self.schema.clone_only_items_named(['child_dict_name'])
        self.assertEquals([], ret._properties)
        self.assertEquals(1, len(ret._sub_registries))
        self.assertEquals(
            'child_dict_title', ret._sub_registries['child_dict_name']._title)
        # Verify that child dict has not lost any substructure.
        self.assertEquals(
            1, len(ret._sub_registries['child_dict_name']._properties))

    def test_clone_child_prop(self):
        ret = self.schema.clone_only_items_named(['child_dict_name/child_prop'])
        self.assertEquals([], ret._properties)
        self.assertEquals(1, len(ret._sub_registries))
        self.assertEquals(
            1, len(ret._sub_registries['child_dict_name']._properties))
        self.assertEquals(
            'child_prop',
            ret._sub_registries['child_dict_name']._properties[0]._name)

    def test_clone_simple_child_array(self):
        ret = self.schema.clone_only_items_named(['simple_array_prop_name'])
        self.assertEquals(1, len(ret._properties))
        self.assertEquals({}, ret._sub_registries)
        self.assertEquals(
            'simple_array_prop_name', ret._properties[0]._name)
        self.assertEquals(
            'simple_array_type_name', ret._properties[0]._item_type._name)

    def test_clone_simple_array_can_name_simple_childs_type(self):
        ret = self.schema.clone_only_items_named(
            ['simple_array_prop_name/simple_array_type_name'])
        self.assertEquals(1, len(ret._properties))
        self.assertEquals({}, ret._sub_registries)
        self.assertEquals(
            'simple_array_prop_name', ret._properties[0]._name)
        self.assertEquals(
            'simple_array_type_name', ret._properties[0]._item_type._name)

    def test_clone_complex_child_array(self):
        ret = self.schema.clone_only_items_named(['complex_array_prop_name'])
        self.assertEquals(1, len(ret._properties))
        self.assertEquals({}, ret._sub_registries)
        self.assertEquals('complex_array_prop_name', ret._properties[0]._name)

        # Also verify that array hasn't had any substructure removed.
        self.assertEquals(1, len(ret._properties[0]._item_type._properties))
        self.assertEquals(1, len(ret._properties[0]._item_type._sub_registries))

    def test_clone_array_simple_subprop(self):
        ret = self.schema.clone_only_items_named(
            ['complex_array_prop_name/complex_array_type_prop'])
        self.assertEquals(1, len(ret._properties))
        self.assertEquals({}, ret._sub_registries)
        self.assertEquals('complex_array_prop_name', ret._properties[0]._name)

        # verify that array hasn't had any substructure removed.
        self.assertEquals({}, ret._properties[0]._item_type._sub_registries)
        self.assertEquals(1, len(ret._properties[0]._item_type._properties))
        self.assertEquals(
            'complex_array_type_prop',
            ret._properties[0]._item_type._properties[0]._name)

    def test_clone_array_complex_subprop(self):
        ret = self.schema.clone_only_items_named(
            ['complex_array_prop_name/complex_array_child_name'])
        self.assertEquals(1, len(ret._properties))
        self.assertEquals({}, ret._sub_registries)
        self.assertEquals('complex_array_prop_name', ret._properties[0]._name)
        self.assertEquals([], ret._properties[0]._item_type._properties)
        self.assertEquals(1, len(ret._properties[0]._item_type._sub_registries))
        self.assertIn('complex_array_child_name',
                      ret._properties[0]._item_type._sub_registries)

    def test_clone_array_substructure_property(self):
        ret = self.schema.clone_only_items_named(
            ['complex_array_prop_name/complex_array_child_name/array_child_p1'])
        self.assertEquals(1, len(ret._properties))
        self.assertEquals({}, ret._sub_registries)
        self.assertEquals('complex_array_prop_name', ret._properties[0]._name)
        self.assertEquals([], ret._properties[0]._item_type._properties)
        self.assertEquals(1, len(ret._properties[0]._item_type._sub_registries))

        leaf_reg = ret._properties[0]._item_type._sub_registries[
            'complex_array_child_name']
        self.assertEquals(1, len(leaf_reg._properties))
        self.assertEquals('array_child_p1', leaf_reg._properties[0].name)
        self.assertEquals({}, leaf_reg._sub_registries)


class RedactEntityTests(StructureRecursionTests):

    def test_redact_no_paths(self):
        schema = self.schema.clone_only_items_named([])
        schema.redact_entity_to_schema(self.entity)
        self.assertEquals({}, self.entity)

    def test_redact_toplevel_prop(self):
        schema = self.schema.clone_only_items_named(['parent_prop'])
        schema.redact_entity_to_schema(self.entity)
        self.assertEquals({
            "parent_prop": "parent_prop_value",
        }, self.entity)

    def test_redact_toplevel_struct(self):
        schema = self.schema.clone_only_items_named(['child_dict_name'])
        schema.redact_entity_to_schema(self.entity)
        self.assertEquals({
            "child_dict_name": {
                "child_prop": "child_prop_value"
            },
        }, self.entity)

    def test_redact_child_prop(self):
        schema = self.schema.clone_only_items_named(
            ['child_dict_name/child_prop'])
        schema.redact_entity_to_schema(self.entity)
        self.assertEquals({
            "child_dict_name": {
                "child_prop": "child_prop_value"
            },
        }, self.entity)

    def test_redact_simple_child_array(self):
        schema = self.schema.clone_only_items_named(['simple_array_prop_name'])
        schema.redact_entity_to_schema(self.entity)
        self.assertEquals({
            "simple_array_prop_name": [
                "simple_array_prop_value_000",
                "simple_array_prop_value_001",
                "simple_array_prop_value_002"
            ]
        }, self.entity)

    def test_redact_simple_array_can_name_simple_childs_type(self):
        schema = self.schema.clone_only_items_named(
            ['simple_array_prop_name/simple_array_type_name'])
        schema.redact_entity_to_schema(self.entity)
        self.assertEquals({
            "simple_array_prop_name": [
                "simple_array_prop_value_000",
                "simple_array_prop_value_001",
                "simple_array_prop_value_002"
            ]
        }, self.entity)

    def test_redact_complex_child_array(self):
        schema = self.schema.clone_only_items_named(['complex_array_prop_name'])
        schema.redact_entity_to_schema(self.entity)
        self.assertEquals({
            "complex_array_prop_name": [
                {
                    "complex_array_type_prop": "complex_array_prop_value_000",
                    "complex_array_child_name": {
                        "array_child_p1": "array_child_p1_value_000",
                        "array_child_p2": "array_child_p2_value_000"
                    }
                },
                {
                    "complex_array_type_prop": "complex_array_prop_value_001",
                    "complex_array_child_name": {
                        "array_child_p1": "array_child_p1_value_001",
                        "array_child_p2": "array_child_p2_value_001"
                    }
                },
                {
                    "complex_array_type_prop": "complex_array_prop_value_002",
                    "complex_array_child_name": {
                        "array_child_p1": "array_child_p1_value_002",
                        "array_child_p2": "array_child_p2_value_002"
                    }
                }
            ]
        }, self.entity)

    def test_redact_array_simple_subprop(self):
        schema = self.schema.clone_only_items_named(
            ['complex_array_prop_name/complex_array_type_prop'])
        schema.redact_entity_to_schema(self.entity)
        self.assertEquals({
            "complex_array_prop_name": [
                {
                    "complex_array_type_prop": "complex_array_prop_value_000",
                },
                {
                    "complex_array_type_prop": "complex_array_prop_value_001",
                },
                {
                    "complex_array_type_prop": "complex_array_prop_value_002",
                }
            ]
        }, self.entity)

    def test_redact_array_complex_subprop(self):
        schema = self.schema.clone_only_items_named(
            ['complex_array_prop_name/complex_array_child_name'])
        schema.redact_entity_to_schema(self.entity)
        self.assertEquals({
            "complex_array_prop_name": [
                {
                    "complex_array_child_name": {
                        "array_child_p1": "array_child_p1_value_000",
                        "array_child_p2": "array_child_p2_value_000"
                    }
                },
                {
                    "complex_array_child_name": {
                        "array_child_p1": "array_child_p1_value_001",
                        "array_child_p2": "array_child_p2_value_001"
                    }
                },
                {
                    "complex_array_child_name": {
                        "array_child_p1": "array_child_p1_value_002",
                        "array_child_p2": "array_child_p2_value_002"
                    }
                }
            ]
        }, self.entity)

    def test_redact_array_substructure_property(self):
        schema = self.schema.clone_only_items_named(
            ['complex_array_prop_name/complex_array_child_name/array_child_p1'])
        schema.redact_entity_to_schema(self.entity)
        self.assertEquals({
            "complex_array_prop_name": [
                {
                    "complex_array_child_name": {
                        "array_child_p1": "array_child_p1_value_000",
                    }
                },
                {
                    "complex_array_child_name": {
                        "array_child_p1": "array_child_p1_value_001",
                    }
                },
                {
                    "complex_array_child_name": {
                        "array_child_p1": "array_child_p1_value_002",
                    }
                }
            ]
        }, self.entity)

    def test_redact_only_readable(self):
        def make_readonly(schema):
            for prop in schema._properties:
                prop._editable = False
                if (isinstance(prop, schema_fields.FieldArray) and
                    isinstance(prop.item_type, schema_fields.Registry)):
                    make_readonly(prop.item_type)
            for sub_schema in schema._sub_registries.itervalues():
                make_readonly(sub_schema)
        make_readonly(self.schema)

        readable = copy.deepcopy(self.entity)
        self.schema.redact_entity_to_schema(readable, only_writable=False)
        self.assertEquals(readable, self.entity)

        writable = copy.deepcopy(self.entity)
        self.schema.redact_entity_to_schema(writable, only_writable=True)
        self.assertEquals(writable, {})
