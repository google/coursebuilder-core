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

# TODO(johncox): Regularize the simple and complex types named both here
# and in transforms.json_to_dict() so that we have a well-defined consistent
# set of types for which we can do conversions and generate schemas.
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
        type_name = PYTHON_TYPE_TO_JSON_TYPE.get(property_type.data_type)
        if not type_name:
            if issubclass(property_type.data_type, entities.BaseEntity):
                type_name = 'string'
            else:
                raise ValueError('Unsupported entity type for schema: %s' %
                                 str(property_type.data_type))
        ret = schema_fields.SchemaField(
            name=name, label=name,
            property_type=type_name,
            description=property_type.verbose_name,
            optional=not property_type.required)
    return ret


def get_schema_for_entity(clazz):
    """Get schema matching entity returned by BaseEntity.for_export()."""

    assert issubclass(clazz, entities.BaseEntity)  # Must have blacklist.
    # Treating as module-protected. pylint: disable=protected-access
    return _get_schema_for_entity(clazz, clazz._get_export_blacklist())


def get_schema_for_entity_unsafe(clazz):
    """Get schema matching entity returned by BaseEntity.for_export_unsafe()."""

    return _get_schema_for_entity(clazz, {})


def _get_schema_for_entity(clazz, suppressed):
    available_properties = clazz.properties()
    registry = schema_fields.FieldRegistry(clazz.__name__)
    for property_type in available_properties.values():
        if property_type.name not in suppressed:
            registry.add_property(_get_schema_field(property_type))
    return registry


def string_to_key(s):
    """Reify key from serialized version, discarding namespace and appid."""
    key_with_namespace_and_appid = db.Key(encoded=s)
    return db.Key.from_path(*key_with_namespace_and_appid.to_path())


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
        elif isinstance(prop, db.ReferenceProperty):
            output[key] = str(value.key())
        else:
            raise ValueError('Failed to encode: %s' % prop)

    # explicitly add entity key as a 'string' attribute
    output['key'] = str(entity.safe_key) if for_export else str(entity.key())

    if for_export:
        output.pop('safe_key')

    return output


def dict_to_entity(entity, source_dict):
    """Sets model object attributes from a Python dictionary."""

    properties = entity.properties()
    for key, value in source_dict.items():
        if (value and key in properties and
            isinstance(properties[key], db.ReferenceProperty)):

            setattr(entity, key, string_to_key(value))
        elif (value is None
              or isinstance(value, transforms_constants.SIMPLE_TYPES)
              or isinstance(value, SUPPORTED_TYPES)):
            setattr(entity, key, value)
        else:
            raise ValueError('Failed to set value "%s" for %s' % (value, key))
    return entity


def json_dict_to_entity_initialization_dict(entity_class, source_dict):
    """Sets model object attributes from a Python dictionary."""

    properties = entity_class.properties()
    ret = {}
    for key, value in source_dict.items():
        if (value and key in properties and
            isinstance(properties[key], db.ReferenceProperty)):
            ret[key] = string_to_key(value)
        elif (value is None
              or isinstance(value, transforms_constants.SIMPLE_TYPES)
              or isinstance(value, SUPPORTED_TYPES)):
            ret[key] = value
        else:
            raise ValueError('Failed to set value "%s" for %s' % (value, key))
    return ret
