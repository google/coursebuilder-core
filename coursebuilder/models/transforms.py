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

"""Set of converters between db models, Python and JSON dictionaries, etc."""

__author__ = 'Pavel Simakov (psimakov@google.com)'


import datetime
import json
from google.appengine.ext import db


SIMPLE_TYPES = (int, long, float, bool, dict, basestring, list)

SUPPORTED_TYPES = (db.GeoPt, datetime.date)

JSON_TYPES = ['string', 'date', 'text', 'boolean', 'integer']

JSON_DATE_FORMAT = '%Y/%m/%d'


def dict_to_json(source_dict, unused_schema):
    """Converts Python dictionary into JSON dictionary using schema."""
    output = {}
    for key, value in source_dict.items():
        if value is None or isinstance(value, SIMPLE_TYPES):
            output[key] = value
        elif isinstance(value, datetime.date):
            output[key] = value.strftime(JSON_DATE_FORMAT)
        elif isinstance(value, db.GeoPt):
            output[key] = {'lat': value.lat, 'lon': value.lon}
        else:
            raise ValueError(
                'Failed to encode key \'%s\' with value \'%s\'.' % (key, value))
    return output


def json_to_dict(source_dict, schema):
    """Converts JSON dictionary into Python dictionary using schema."""
    output = {}
    for key, attr in schema['properties'].items():
        # Skip schema elements that don't exist in source.
        if not key in source_dict:
            continue

        attr_type = attr['type']
        if not attr_type in JSON_TYPES:
            raise ValueError('Unsupported JSON type: %s' % attr_type)
        if attr_type == 'date':
            output[key] = datetime.datetime.strptime(
                source_dict[key], JSON_DATE_FORMAT).date()
        else:
            output[key] = source_dict[key]
    return output


def entity_to_dict(entity):
    """Puts model object attributes into a Python dictionary."""
    output = {}
    for key, prop in entity.properties().iteritems():
        value = getattr(entity, key)
        if value is None or isinstance(value, SIMPLE_TYPES) or isinstance(
                value, SUPPORTED_TYPES):
            output[key] = value
        else:
            raise ValueError('Failed to encode: %s' % prop)

    # explicitly add entity key as a 'string' attribute
    output['key'] = str(entity.key())

    return output


def dict_to_entity(entity, source_dict):
    """Sets model object attributes from a Python dictionary."""
    for key, value in source_dict.items():
        if value is None or isinstance(value, SIMPLE_TYPES) or isinstance(
                value, SUPPORTED_TYPES):
            setattr(entity, key, value)
        else:
            raise ValueError('Failed to encode: %s' % value)
    return entity


def string_to_value(string, value_type):
    """Converts string representation to a value."""
    if value_type == str:
        if not string:
            return ''
        else:
            return string
    elif value_type == bool:
        if string == '1' or string == 'True' or string == 1:
            return True
        else:
            return False
    elif value_type == int or value_type == long:
        if not string:
            return 0
        else:
            return long(string)
    else:
        raise ValueError('Unknown type: %s' % value_type)


def value_to_string(value, value_type):
    """Converts value to a string representation."""
    if value_type == str:
        return value
    elif value_type == bool:
        if value:
            return 'True'
        else:
            return 'False'
    elif value_type == int or value_type == long:
        return str(value)
    else:
        raise ValueError('Unknown type: %s' % value_type)


def send_json_response(
    handler, status_code, message, payload_dict=None, xsrf_token=None):
    """Formats and sends out a JSON REST response envelope and body."""
    response = {}
    response['status'] = status_code
    response['message'] = message
    if payload_dict:
        response['payload'] = json.dumps(payload_dict)
    if xsrf_token:
        response['xsrf_token'] = xsrf_token
    handler.response.write(json.dumps(response))


def run_all_unit_tests():
    """Runs all unit tests."""
    assert value_to_string(True, bool) == 'True'
    assert value_to_string(False, bool) == 'False'
    assert value_to_string(None, bool) == 'False'

    assert string_to_value('True', bool)
    assert string_to_value('1', bool)
    assert string_to_value(1, bool)

    assert not string_to_value('False', bool)
    assert not string_to_value('0', bool)
    assert not string_to_value('5', bool)
    assert not string_to_value(0, bool)
    assert not string_to_value(5, bool)
    assert not string_to_value(None, bool)

    assert string_to_value('15', int) == 15
    assert string_to_value(15, int) == 15
    assert string_to_value(None, int) == 0

    assert string_to_value('foo', str) == 'foo'
    assert string_to_value(None, str) == str('')


if __name__ == '__main__':
    run_all_unit_tests()
