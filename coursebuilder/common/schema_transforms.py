# Copyright 2015 Google Inc. All Rights Reserved.
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

"""Set of functions to transforms schemas and objects that map to them."""

__author__ = 'Pavel Simakov (psimakov@google.com)'


import datetime
import itertools
import types
import urlparse


SIMPLE_TYPES = (int, long, float, bool, dict, basestring, list)

ISO_8601_DATE_FORMAT = '%Y-%m-%d'
ISO_8601_DATETIME_FORMAT = '%Y-%m-%dT%H:%M:%S.%fZ'
_LEGACY_DATE_FORMAT = '%Y/%m/%d'

_JSON_DATE_FORMATS = [
    ISO_8601_DATE_FORMAT,
    _LEGACY_DATE_FORMAT,
]
_JSON_DATETIME_FORMATS = [
    ISO_8601_DATETIME_FORMAT
] + [
    ''.join(parts) for parts in itertools.product(
        # Permutations of reasonably-expected permitted variations on ISO-8601.
        # The first item in each tuple indicates the preferred choice.
        _JSON_DATE_FORMATS,
        ('T', ' '),
        ('%H:%M:%S', '%H:%M'),
        ('.%f', ',%f', ''),  # US/Euro decimal separator
        ('Z', ''),  # Be explicit about Zulu timezone.  Blank implies local.
    )
]
JSON_TYPES = ['string', 'date', 'datetime', 'text', 'html',
              'boolean', 'integer', 'number', 'array', 'object', 'timestamp']


def get_custom_serializer_for(value, custom_type_serializer=None):
    if custom_type_serializer:
        for custom_type, serializer in custom_type_serializer.iteritems():
            if isinstance(value, custom_type):
                return serializer
    return None


def dict_to_json(
        source_dict, custom_type_serializer=None, schema=None, recurse=False):
    """Converts Python dictionary into JSON dictionary using schema."""
    output = {}
    for key, value in source_dict.items():
        if isinstance(value, dict) and recurse:
            output[key] = dict_to_json(
                value, custom_type_serializer=custom_type_serializer,
                recurse=recurse)
        elif value is None or isinstance(value, SIMPLE_TYPES):
            output[key] = value
        elif isinstance(value, datetime.datetime):
            output[key] = value.strftime(ISO_8601_DATETIME_FORMAT)
        elif isinstance(value, datetime.date):
            output[key] = value.strftime(ISO_8601_DATE_FORMAT)
        else:
            custom = get_custom_serializer_for(value, custom_type_serializer)
            if custom:
                output[key] = custom(value)
            else:
                raise ValueError(
                    'Failed to encode key \'%s\' with value \'%s\'.' %
                    (key, value))
    return output


def _json_to_datetime(value, date_only=False):
    if value is None:
        return None

    DNMF = 'does not match format'
    if date_only:
        formats = _JSON_DATE_FORMATS
    else:
        formats = _JSON_DATETIME_FORMATS

    exception = None
    for format_str in formats:
        try:
            value = datetime.datetime.strptime(value, format_str)
            if date_only:
                value = value.date()
            return value
        except ValueError as e:
            # Save first exception so as to preserve the error message that
            # describes the most-preferred format, unless the new error
            # message is something other than "does-not-match-format", (and
            # the old one is) in which case save that, because anything other
            # than DNMF is more useful/informative.
            if not exception or (DNMF not in str(e) and DNMF in str(exception)):
                exception = e

    # We cannot get here without an exception.
    # The linter thinks we might still have 'None', but is mistaken.
    # pylint: disable=raising-bad-type
    raise exception


def _convert_bool(value, key):
    if isinstance(value, types.NoneType):
        return False
    elif isinstance(value, bool):
        return value
    elif isinstance(value, basestring):
        value = value.lower()
        if value == 'true':
            return True
        elif value == 'false':
            return False
    raise ValueError('Bad boolean value for %s: %s' % (key, value))


def coerce_json_value(source, schema, debug_key):
    data_type = schema['type']

    if data_type not in JSON_TYPES:
        raise ValueError('Unsupported JSON type: %s' % data_type)
    if data_type == 'object':
        return json_to_dict(source, schema)
    elif data_type == 'datetime' or data_type == 'date':
        return _json_to_datetime(source, data_type == 'date')
    elif data_type == 'number':
        return float(source)
    elif data_type in ('integer', 'timestamp'):
        return int(source) if source else 0
    elif data_type == 'boolean':
        return _convert_bool(source, debug_key)
    elif data_type == 'array':
        subschema = schema['items']
        array = []
        for item in source:
            array.append(coerce_json_value(item, subschema, debug_key))
        return array
    else:
        return source


def json_to_dict(source_dict, schema, permit_none_values=False):
    """Converts JSON dictionary into Python dictionary using schema."""

    output = {}

    for key, attr in schema['properties'].items():
        # Skip schema elements that don't exist in source.

        if key not in source_dict:
            is_optional = _convert_bool(attr.get('optional'), 'optional')
            if not is_optional:
                raise ValueError('Missing required attribute: %s' % key)
            continue

        # TODO(jorr): Make the policy for None values clearer and more
        # consistent. Note that some types (string and datetime) always accept
        # None but others (integer) don't.

        # Reifying from database may provide "null", which translates to
        # None.  As long as the field is optional (checked above), set
        # value to None directly (skipping conversions below).
        if permit_none_values and source_dict[key] is None:
            output[key] = None
            continue

        output[key] = coerce_json_value(source_dict[key], attr, key)
    return output


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


def dict_to_instance(adict, instance, defaults=None):
    """Populates instance attributes using data dictionary."""
    for key, unused_value in instance.__dict__.iteritems():
        if not key.startswith('_'):
            if key in adict:
                setattr(instance, key, adict[key])
            elif defaults and key in defaults:
                setattr(instance, key, defaults[key])
            else:
                raise KeyError(key)


def validate_object_matches_json_schema(obj, schema, path='', complaints=None):
    """Check whether the given object matches a schema.

    When building up a dict of contents which is supposed to match a declared
    schema, human error often creeps in; it is easy to neglect to cast a number
    to a floating point number, or an object ID to a string.  This function
    verifies the presence, type, and format of fields.

    Note that it is not effective to verify sub-components that are scalars
    or arrays, due to the way field names are (or rather, are not) stored
    in the JSON schema layout.

    Args:
      obj: A dict containing contents that should match the given schema
      schema: A dict describing a schema, as obtained from
        FieldRegistry.get_json_schema_dict().  This parameter can also
        be the 'properties' member of a JSON schema dict, as that sub-item
        is commonly used in the REST data source subsystem.
      path: Do not pass a value for this; it is used for internal recursion.
      complaints: Either leave this blank or pass in an empty list.  If
        blank, the list of complaints is available as the return value.
        If nonblank, the list of complaints will be appended to this list.
        Either is fine, depending on your preferred style.
    Returns:
      Array of verbose complaint strings.  If array is blank, object
      validated without error.
    """

    def is_valid_url(obj):
        url = urlparse.urlparse(obj)
        return url.scheme and url.netloc

    def is_valid_date(obj):
        try:
            datetime.datetime.strptime(obj, ISO_8601_DATE_FORMAT)
            return True
        except ValueError:
            return False

    def is_valid_datetime(obj):
        try:
            datetime.datetime.strptime(obj, ISO_8601_DATETIME_FORMAT)
            return True
        except ValueError:
            return False

    if complaints is None:
        complaints = []
    if 'properties' in schema or isinstance(obj, dict):
        if not path:
            if 'id' in schema:
                path = schema['id']
            else:
                path = '(root)'
        if obj is None:
            pass
        elif not isinstance(obj, dict):
            complaints.append('Expected a dict at %s, but had %s' % (
                path, type(obj)))
        else:
            if 'properties' in schema:
                schema = schema['properties']
            for name, sub_schema in schema.iteritems():
                validate_object_matches_json_schema(
                    obj.get(name), sub_schema, path + '.' + name, complaints)
            for name in obj:
                if name not in schema:
                    complaints.append('Unexpected member "%s" in %s' % (
                        name, path))
    elif 'items' in schema:
        if 'items' in schema['items']:
            complaints.append('Unsupported: array-of-array at ' + path)
        if obj is None:
            pass
        elif not isinstance(obj, (list, tuple)):
            complaints.append('Expected a list or tuple at %s, but had %s' % (
                path, type(obj)))
        else:
            for index, item in enumerate(obj):
                item_path = path + '[%d]' % index
                if item is None:
                    complaints.append('Found None at %s' % item_path)
                else:
                    validate_object_matches_json_schema(
                        item, schema['items'], item_path, complaints)
    else:
        if obj is None:
            if not schema.get('optional'):
                complaints.append('Missing mandatory value at ' + path)
        else:
            expected_type = None
            validator = None
            if schema['type'] in ('string', 'text', 'html', 'file'):
                expected_type = basestring
            elif schema['type'] == 'url':
                expected_type = basestring
                validator = is_valid_url
            elif schema['type'] in ('integer', 'timestamp'):
                expected_type = int
            elif schema['type'] in 'number':
                expected_type = float
            elif schema['type'] in 'boolean':
                expected_type = bool
            elif schema['type'] == 'date':
                expected_type = basestring
                validator = is_valid_date
            elif schema['type'] == 'datetime':
                expected_type = basestring
                validator = is_valid_datetime

            if expected_type:
                if not isinstance(obj, expected_type):
                    complaints.append(
                        'Expected %s at %s, but instead had %s' % (
                            expected_type, path, type(obj)))
                elif validator and not validator(obj):
                    complaints.append(
                        'Value "%s" is not well-formed according to %s' % (
                            str(obj), validator.__name__))
            else:
                complaints.append(
                    'Unrecognized schema scalar type "%s" at %s' % (
                        schema['type'], path))
    return complaints

