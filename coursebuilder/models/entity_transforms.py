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

"""Set of converters between db models, Python and JSON dictionaries, etc."""

__author__ = 'Mike Gainer (mgainer@google.com)'

import base64
import datetime
import entities
import transforms_constants

from common import schema_fields

from google.appengine.api import datastore_types
from google.appengine.ext import db

PYTHON_TYPE_TO_JSON_TYPE = {
    basestring: 'string',
    datetime.date: 'date',
    datetime.datetime: 'datetime',
    int: 'integer',
    float: 'number',
    bool: 'boolean',
    datastore_types.Text: 'text',
}
SUPPORTED_TYPES = (
    datastore_types.Key,
    datetime.date,
    datetime.datetime,
    db.GeoPt,
)


def _get_schema_field(property_type):
    name = property_type.name
    if property_type.data_type == list:
        # Shallow evaluation here is OK; Python DB API does not permit
        # array-of-array; when declaring a ListProperty, the item type
        # must be a Type instance (and thus cannot be a class, and thus
        # cannot be a Property class)
        item_type = schema_fields.SchemaField(
            name=name + ':item', label=name + ':item', optional=True,
            property_type=PYTHON_TYPE_TO_JSON_TYPE[
                property_type.item_type])
        ret = schema_fields.FieldArray(
            name=name, label=name,
            description=property_type.verbose_name,
            item_type=item_type)
    else:
        ret = schema_fields.SchemaField(
            name=name, label=name,
            property_type=PYTHON_TYPE_TO_JSON_TYPE[property_type.data_type],
            description=property_type.verbose_name,
            optional=not property_type.required)
    return ret


def get_schema_for_entity(clazz):
    assert issubclass(clazz, entities.BaseEntity)  # Must have blacklist.
    available_properties = clazz.properties()
    # Treating as module-protected. pylint: disable-msg=protected-access
    suppressed = clazz._get_export_blacklist()
    registry = schema_fields.FieldRegistry(clazz.__name__)
    for property_type in available_properties.values():
        if property_type.name not in suppressed:
            registry.add_property(_get_schema_field(property_type))
    return registry


def entity_to_dict(entity, force_utf_8_encoding=False):
    """Puts model object attributes into a Python dictionary."""
    output = {}
    for_export = isinstance(entity, entities.ExportEntity)
    properties = entity.properties()

    if for_export:
        for name in entity.instance_properties():
            properties[name] = getattr(entity, name)

    for key, prop in properties.iteritems():
        value = getattr(entity, key)
        if (value is None or
            isinstance(value, transforms_constants.SIMPLE_TYPES) or
            isinstance(value, SUPPORTED_TYPES)):
            output[key] = value

            # some values are raw bytes; force utf-8 or base64 encoding
            if force_utf_8_encoding and isinstance(value, basestring):
                try:
                    output[key] = value.encode('utf-8')
                except UnicodeDecodeError:
                    output[key] = {
                        'type': 'binary',
                        'encoding': 'base64',
                        'content': base64.urlsafe_b64encode(value)}

        else:
            raise ValueError('Failed to encode: %s' % prop)

    # explicitly add entity key as a 'string' attribute
    output['key'] = str(entity.safe_key) if for_export else str(entity.key())

    if for_export:
        output.pop('safe_key')

    return output


def dict_to_entity(entity, source_dict):
    """Sets model object attributes from a Python dictionary."""
    for key, value in source_dict.items():
        if (value is None
            or isinstance(value, transforms_constants.SIMPLE_TYPES)
            or isinstance(value, SUPPORTED_TYPES)):
            setattr(entity, key, value)
        else:
            raise ValueError('Failed to encode: %s' % value)
    return entity
