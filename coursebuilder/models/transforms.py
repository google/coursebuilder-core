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
from google.appengine.ext import db


SIMPLE_TYPES = (int, long, float, bool, dict, basestring, list)

SUPPORTED_TYPES = (db.GeoPt, datetime.date)

JSON_TYPES = ['string', 'date', 'text', 'boolean']

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
