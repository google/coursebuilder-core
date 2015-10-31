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


"""Unit tests for the transforms functions."""

__author__ = 'John Orr (jorr@google.com)'

import datetime
import unittest

from common import schema_fields
from models import transforms


def wrap_properties(properties):
    return {'properties': properties}


class JsonToDictTests(unittest.TestCase):

    def test_missing_optional_fields_are_allowed(self):
        schema = wrap_properties(
            {'opt_field': {'type': 'boolean', 'optional': 'true'}})
        result = transforms.json_to_dict({}, schema)
        self.assertEqual(len(result), 0)

    def test_missing_required_fields_are_rejected(self):
        schema = wrap_properties(
            {'req_field': {'type': 'boolean', 'optional': 'false'}})
        try:
            transforms.json_to_dict({}, schema)
            self.fail('Expected ValueError')
        except ValueError as e:
            self.assertEqual(str(e), 'Missing required attribute: req_field')

        schema = wrap_properties(
            {'req_field': {'type': 'boolean'}})
        try:
            transforms.json_to_dict({}, schema)
            self.fail('Expected ValueError')
        except ValueError as e:
            self.assertEqual(str(e), 'Missing required attribute: req_field')

    def test_convert_boolean(self):
        schema = wrap_properties({'field': {'type': 'boolean'}})
        source = {'field': True}
        result = transforms.json_to_dict(source, schema)
        self.assertEqual(len(result), 1)
        self.assertEqual(result['field'], True)

    def test_convert_string_to_boolean(self):
        schema = wrap_properties({'field': {'type': 'boolean'}})
        source = {'field': 'true'}
        result = transforms.json_to_dict(source, schema)
        self.assertEqual(len(result), 1)
        self.assertEqual(result['field'], True)

    def test_reject_bad_boolean(self):
        schema = wrap_properties({'field': {'type': 'boolean'}})
        source = {'field': 'cat'}
        try:
            transforms.json_to_dict(source, schema)
            self.fail('Expected ValueException')
        except ValueError as e:
            self.assertEqual(str(e), 'Bad boolean value for field: cat')

    def test_convert_number(self):
        schema = wrap_properties({'field': {'type': 'number'}})
        source = {'field': 3.14}
        result = transforms.json_to_dict(source, schema)
        self.assertEqual(len(result), 1)
        self.assertEqual(result['field'], 3.14)

    def test_convert_string_to_number(self):
        schema = wrap_properties({'field': {'type': 'number'}})
        source = {'field': '3.14'}
        result = transforms.json_to_dict(source, schema)
        self.assertEqual(len(result), 1)
        self.assertEqual(result['field'], 3.14)

    def test_reject_bad_number(self):
        schema = wrap_properties({'field': {'type': 'number'}})
        source = {'field': 'cat'}
        try:
            transforms.json_to_dict(source, schema)
            self.fail('Expected ValueException')
        except ValueError as e:
            self.assertEqual(str(e), 'could not convert string to float: cat')

    def test_convert_date(self):
        schema = wrap_properties({'field': {'type': 'date'}})

        source = {'field': '2005/03/01'}
        result = transforms.json_to_dict(source, schema)
        self.assertEqual(len(result), 1)
        self.assertEqual(result['field'], datetime.date(2005, 3, 1))

        source = {'field': '2005-03-01'}
        result = transforms.json_to_dict(source, schema)
        self.assertEqual(result['field'], datetime.date(2005, 3, 1))

    def test_reject_bad_dates(self):
        schema = wrap_properties({'field': {'type': 'date'}})
        source = {'field': '2005/02/31'}
        try:
            transforms.json_to_dict(source, schema)
            self.fail('Expected ValueException')
        except ValueError as e:
            self.assertEqual(str(e), 'day is out of range for month')

        schema = wrap_properties({'field': {'type': 'date'}})
        source = {'field': 'cat'}
        try:
            transforms.json_to_dict(source, schema)
            self.fail('Expected ValueException')
        except ValueError as e:
            self.assertEqual(
                str(e), 'time data \'cat\' does not match format \'%s\'' %
                transforms.ISO_8601_DATE_FORMAT)

    def test_convert_datetime(self):
        schema = wrap_properties({'field': {'type': 'datetime'}})

        source = {'field': '2005/03/01 20:30'}
        result = transforms.json_to_dict(source, schema)
        self.assertEqual(len(result), 1)
        self.assertEqual(
            result['field'], datetime.datetime(2005, 3, 1, 20, 30, 0))

        source = {'field': '2005-03-01 20:30:19'}
        result = transforms.json_to_dict(source, schema)
        self.assertEqual(
            result['field'], datetime.datetime(2005, 3, 1, 20, 30, 19))

        source = {'field': '2005-03-01 20:30:19Z'}
        result = transforms.json_to_dict(source, schema)
        self.assertEqual(
            result['field'], datetime.datetime(2005, 3, 1, 20, 30, 19))

        source = {'field': '2005-03-01T20:30:19.123456Z'}
        result = transforms.json_to_dict(source, schema)
        self.assertEqual(
            result['field'], datetime.datetime(2005, 3, 1, 20, 30, 19, 123456))

    def test_reject_bad_datetimes(self):
        schema = wrap_properties({'field': {'type': 'datetime'}})
        source = {'field': '2005/02/31 20:30'}
        try:
            transforms.json_to_dict(source, schema)
            self.fail('Expected ValueException')
        except ValueError as e:
            self.assertEqual(str(e), 'day is out of range for month')

        schema = wrap_properties({'field': {'type': 'datetime'}})
        source = {'field': 'cat'}
        try:
            transforms.json_to_dict(source, schema)
            self.fail('Expected ValueException')
        except ValueError as e:
            self.assertEqual(
                str(e),
                'time data \'cat\' does not match format \'%s\'' %
                transforms.ISO_8601_DATETIME_FORMAT)

    def test_nulls(self):
        for type_name in transforms.JSON_TYPES:
            schema = wrap_properties({'field': {'type': type_name}})
            source = {'field': None}
            ret = transforms.json_to_dict(source, schema,
                                          permit_none_values=True)
            self.assertIn('field', ret)
            self.assertIsNone(ret['field'])


class StringValueConversionTests(unittest.TestCase):

    def test_value_to_string(self):
        assert transforms.value_to_string(True, bool) == 'True'
        assert transforms.value_to_string(False, bool) == 'False'
        assert transforms.value_to_string(None, bool) == 'False'

    def test_string_to_value(self):
        assert transforms.string_to_value('True', bool)
        assert transforms.string_to_value('1', bool)
        assert transforms.string_to_value(1, bool)

        assert not transforms.string_to_value('False', bool)
        assert not transforms.string_to_value('0', bool)
        assert not transforms.string_to_value('5', bool)
        assert not transforms.string_to_value(0, bool)
        assert not transforms.string_to_value(5, bool)
        assert not transforms.string_to_value(None, bool)

        assert transforms.string_to_value('15', int) == 15
        assert transforms.string_to_value(15, int) == 15
        assert transforms.string_to_value(None, int) == 0

        assert transforms.string_to_value('foo', str) == 'foo'
        assert transforms.string_to_value(None, str) == str('')


class JsonParsingTests(unittest.TestCase):

    def test_json_trailing_comma_in_dict_fails(self):
        json_text = '{"foo": "bar",}'
        try:
            transforms.loads(json_text)
            raise Exception('Expected to fail')
        except ValueError:
            pass

    def test_json_trailing_comma_in_array_fails(self):
        json_text = '{"foo": ["bar",]}'
        try:
            transforms.loads(json_text)
            raise Exception('Expected to fail')
        except ValueError:
            pass

    def test_non_strict_mode_parses_json(self):
        json_text = '{"foo": "bar", "baz": ["bum",],}'
        _json = transforms.loads(json_text, strict=False)
        assert _json.get('foo') == 'bar'


class SchemaValidationTests(unittest.TestCase):

    def test_mandatory_scalar_missing(self):
        reg = schema_fields.FieldRegistry('Test')
        reg.add_property(schema_fields.SchemaField(
            'a_string', 'A String', 'string'))
        complaints = transforms.validate_object_matches_json_schema(
            {},
            reg.get_json_schema_dict())
        self.assertEqual(
            complaints,
            ['Missing mandatory value at Test.a_string'])

    def test_mandatory_scalar_present(self):
        reg = schema_fields.FieldRegistry('Test')
        reg.add_property(schema_fields.SchemaField(
            'a_string', 'A String', 'string'))
        complaints = transforms.validate_object_matches_json_schema(
            {'a_string': ''},
            reg.get_json_schema_dict())
        self.assertEqual(complaints, [])

    def test_optional_scalar_missing(self):
        reg = schema_fields.FieldRegistry('Test')
        reg.add_property(schema_fields.SchemaField(
            'a_string', 'A String', 'string', optional=True))
        complaints = transforms.validate_object_matches_json_schema(
            {},
            reg.get_json_schema_dict())
        self.assertEqual(complaints, [])

    def test_optional_scalar_present(self):
        reg = schema_fields.FieldRegistry('Test')
        reg.add_property(schema_fields.SchemaField(
            'a_string', 'A String', 'string', optional=True))
        complaints = transforms.validate_object_matches_json_schema(
            {'a_string': ''},
            reg.get_json_schema_dict())
        self.assertEqual(complaints, [])

    def test_non_struct_where_struct_expected(self):
        reg = schema_fields.FieldRegistry('Test')
        reg.add_property(schema_fields.SchemaField(
            'a_string', 'A String', 'string'))
        complaints = transforms.validate_object_matches_json_schema(
            123,
            reg.get_json_schema_dict())
        self.assertEqual(
            complaints,
            ['Expected a dict at Test, but had <type \'int\'>'])

    def test_malformed_url(self):
        reg = schema_fields.FieldRegistry('Test')
        reg.add_property(schema_fields.SchemaField(
            'a_url', 'A URL', 'url'))
        complaints = transforms.validate_object_matches_json_schema(
            {'a_url': 'not really a URL, is it?'},
            reg.get_json_schema_dict())
        self.assertEqual(
            complaints,
            ['Value "not really a URL, is it?" '
             'is not well-formed according to is_valid_url'])

    def test_valid_url(self):
        reg = schema_fields.FieldRegistry('Test')
        reg.add_property(schema_fields.SchemaField(
            'a_url', 'A URL', 'url'))
        complaints = transforms.validate_object_matches_json_schema(
            {'a_url': 'http://x.com'},
            reg.get_json_schema_dict())
        self.assertEqual(complaints, [])

    def test_malformed_date(self):
        reg = schema_fields.FieldRegistry('Test')
        reg.add_property(schema_fields.SchemaField(
            'a_date', 'A Date', 'date'))
        complaints = transforms.validate_object_matches_json_schema(
            {'a_date': 'not really a date string, is it?'},
            reg.get_json_schema_dict())
        self.assertEqual(
            complaints,
            ['Value "not really a date string, is it?" '
             'is not well-formed according to is_valid_date'])

    def test_valid_date(self):
        reg = schema_fields.FieldRegistry('Test')
        reg.add_property(schema_fields.SchemaField(
            'a_date', 'A Date', 'date'))
        complaints = transforms.validate_object_matches_json_schema(
            {'a_date': '2014-12-17'},
            reg.get_json_schema_dict())
        self.assertEqual(complaints, [])

    def test_malformed_datetime(self):
        reg = schema_fields.FieldRegistry('Test')
        reg.add_property(schema_fields.SchemaField(
            'a_datetime', 'A Datetime', 'datetime'))
        complaints = transforms.validate_object_matches_json_schema(
            {'a_datetime': 'not really a datetime string, is it?'},
            reg.get_json_schema_dict())
        self.assertEqual(
            complaints,
            ['Value "not really a datetime string, is it?" '
             'is not well-formed according to is_valid_datetime'])

    def test_valid_datetime(self):
        reg = schema_fields.FieldRegistry('Test')
        reg.add_property(schema_fields.SchemaField(
            'a_datetime', 'A Datetime', 'datetime'))
        complaints = transforms.validate_object_matches_json_schema(
            {'a_datetime': '2014-12-17T14:10:09.222333Z'},
            reg.get_json_schema_dict())
        self.assertEqual(complaints, [])

    def test_unexpected_member(self):
        reg = schema_fields.FieldRegistry('Test')
        reg.add_property(schema_fields.SchemaField(
            'a_string', 'A String', 'string'))
        complaints = transforms.validate_object_matches_json_schema(
            {'a_string': '',
             'a_number': 456},
            reg.get_json_schema_dict())
        self.assertEqual(complaints, ['Unexpected member "a_number" in Test'])

    def test_arrays_are_implicitly_optional(self):
        reg = schema_fields.FieldRegistry('Test')
        reg.add_property(schema_fields.FieldArray(
            'scalar_array', 'Scalar Array',
            item_type=schema_fields.SchemaField(
                'a_string', 'A String', 'string')))
        complaints = transforms.validate_object_matches_json_schema(
            {},
            reg.get_json_schema_dict())
        self.assertEqual(complaints, [])

    def test_empty_array(self):
        reg = schema_fields.FieldRegistry('Test')
        reg.add_property(schema_fields.FieldArray(
            'scalar_array', 'Scalar Array',
            item_type=schema_fields.SchemaField(
                'a_string', 'A String', 'string')))
        complaints = transforms.validate_object_matches_json_schema(
            {'scalar_array': []},
            reg.get_json_schema_dict())
        self.assertEqual(complaints, [])

    def test_array_with_valid_content(self):
        reg = schema_fields.FieldRegistry('Test')
        reg.add_property(schema_fields.FieldArray(
            'scalar_array', 'Scalar Array',
            item_type=schema_fields.SchemaField(
                'a_string', 'A String', 'string')))
        complaints = transforms.validate_object_matches_json_schema(
            {'scalar_array': ['foo', 'bar', 'baz']},
            reg.get_json_schema_dict())
        self.assertEqual(complaints, [])

    def test_array_with_bad_members(self):
        reg = schema_fields.FieldRegistry('Test')
        reg.add_property(schema_fields.FieldArray(
            'scalar_array', 'Scalar Array',
            item_type=schema_fields.SchemaField(
                'a_string', 'A String', 'string')))
        complaints = transforms.validate_object_matches_json_schema(
            {'scalar_array': ['foo', 123, 'bar', 456, 'baz']},
            reg.get_json_schema_dict())
        self.assertEqual(
            complaints,
            ['Expected <type \'basestring\'> at Test.scalar_array[1], '
             'but instead had <type \'int\'>',
             'Expected <type \'basestring\'> at Test.scalar_array[3], '
             'but instead had <type \'int\'>'])

    def test_dicts_implicitly_optional(self):
        reg = schema_fields.FieldRegistry('Test')
        sub_registry = schema_fields.FieldRegistry('subregistry')
        sub_registry.add_property(schema_fields.SchemaField(
            'name', 'Name', 'string', description='user name'))
        sub_registry.add_property(schema_fields.SchemaField(
            'city', 'City', 'string', description='city name'))
        reg.add_sub_registry('sub_registry', title='Sub Registry',
                             description='a sub-registry',
                             registry=sub_registry)
        complaints = transforms.validate_object_matches_json_schema(
            {},
            reg.get_json_schema_dict())
        self.assertEqual(complaints, [])

    def test_nested_dict(self):
        reg = schema_fields.FieldRegistry('Test')
        sub_registry = schema_fields.FieldRegistry('subregistry')
        sub_registry.add_property(schema_fields.SchemaField(
            'name', 'Name', 'string', description='user name'))
        sub_registry.add_property(schema_fields.SchemaField(
            'city', 'City', 'string', description='city name'))
        reg.add_sub_registry('sub_registry', title='Sub Registry',
                             description='a sub-registry',
                             registry=sub_registry)
        complaints = transforms.validate_object_matches_json_schema(
            {'sub_registry': {'name': 'John Smith', 'city': 'Back East'}},
            reg.get_json_schema_dict())
        self.assertEqual(complaints, [])

    def test_nested_dict_missing_items(self):
        reg = schema_fields.FieldRegistry('Test')
        sub_registry = schema_fields.FieldRegistry('subregistry')
        sub_registry.add_property(schema_fields.SchemaField(
            'name', 'Name', 'string', description='user name'))
        sub_registry.add_property(schema_fields.SchemaField(
            'city', 'City', 'string', description='city name'))
        reg.add_sub_registry('sub_registry', title='Sub Registry',
                             description='a sub-registry',
                             registry=sub_registry)
        complaints = transforms.validate_object_matches_json_schema(
            {'sub_registry': {}},
            reg.get_json_schema_dict())
        self.assertEqual(
          complaints,
          ['Missing mandatory value at Test.sub_registry.name',
           'Missing mandatory value at Test.sub_registry.city'])

    def test_array_of_dict(self):
        sub_registry = schema_fields.FieldRegistry('subregistry')
        sub_registry.add_property(schema_fields.SchemaField(
            'name', 'Name', 'string', description='user name'))
        sub_registry.add_property(schema_fields.SchemaField(
            'city', 'City', 'string', description='city name'))

        reg = schema_fields.FieldRegistry('Test')
        reg.add_property(schema_fields.FieldArray(
            'struct_array', 'Struct Array', item_type=sub_registry))
        complaints = transforms.validate_object_matches_json_schema(
            {'struct_array': [
              {'name': 'One', 'city': 'Two'},
              None,
              {'name': 'Three'},
              {'city': 'Four'}
              ]},
            reg.get_json_schema_dict())
        self.assertEqual(
            complaints,
            ['Found None at Test.struct_array[1]',
             'Missing mandatory value at Test.struct_array[2].city',
             'Missing mandatory value at Test.struct_array[3].name'])

    def test_array_of_string(self):
        reg = schema_fields.FieldRegistry('Test')
        reg.add_property(schema_fields.FieldArray(
            'string_array', 'String Array',
            item_type=schema_fields.SchemaField(None, None, 'string'),
            select_data=(('one', 'One'), ('two', 'Two'), ('three', 'Three'))))
        json_schema = reg.get_json_schema_dict()

        source = {'string_array': ['one', 'two']}

        self.assertEqual(transforms.validate_object_matches_json_schema(
            source, json_schema), [])

        self.assertEqual(transforms.json_to_dict(source, json_schema), source)
