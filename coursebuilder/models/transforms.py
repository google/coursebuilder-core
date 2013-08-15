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

import base64
import datetime
import json

from xml.etree import ElementTree

import entities
from google.appengine.api import datastore_types
from google.appengine.ext import db


JSON_DATE_FORMAT = '%Y/%m/%d'
JSON_TYPES = ['string', 'date', 'text', 'html', 'boolean', 'integer', 'number',
              'array', 'object']
# Prefix to add to all JSON responses to guard against XSSI. Must be kept in
# sync with modules/oeditor/oeditor.html.
_JSON_XSSI_PREFIX = ")]}'\n"
SIMPLE_TYPES = (int, long, float, bool, dict, basestring, list)
SUPPORTED_TYPES = (
    datastore_types.Key,
    datetime.date,
    db.GeoPt,
)


def dict_to_json(source_dict, unused_schema):
    """Converts Python dictionary into JSON dictionary using schema."""
    output = {}
    for key, value in source_dict.items():
        if value is None or isinstance(value, SIMPLE_TYPES):
            output[key] = value
        elif isinstance(value, datastore_types.Key):
            output[key] = str(value)
        elif isinstance(value, datetime.date):
            output[key] = value.strftime(JSON_DATE_FORMAT)
        elif isinstance(value, db.GeoPt):
            output[key] = {'lat': value.lat, 'lon': value.lon}
        else:
            raise ValueError(
                'Failed to encode key \'%s\' with value \'%s\'.' % (key, value))
    return output


def dumps(*args, **kwargs):
    """Wrapper around json.dumps.

    No additional behavior; present here so this module is a drop-in replacement
    for json.dumps|loads. Clients should never use json.dumps|loads directly.
    See usage docs at http://docs.python.org/2/library/json.html.

    Args:
        *args: positional arguments delegated to json.dumps.
        **kwargs: keyword arguments delegated to json.dumps.

    Returns:
        string. The converted JSON.
    """

    class SetAsListJSONEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, set):
                return list(obj)
            return super(SetAsListJSONEncoder, self).default(obj)

    if 'cls' not in kwargs:
        kwargs['cls'] = SetAsListJSONEncoder

    return json.dumps(*args, **kwargs)


def loads(s, prefix=_JSON_XSSI_PREFIX, **kwargs):
    """Wrapper around json.loads that handles XSSI-protected responses.

    To prevent XSSI we insert a prefix before our JSON responses during server-
    side rendering. This loads() removes the prefix and should always be used in
    place of json.loads. See usage docs at
    http://docs.python.org/2/library/json.html.

    Args:
        s: str or unicode. JSON contents to convert.
        prefix: string. The XSSI prefix we remove before conversion.
        **kwargs: keyword arguments delegated to json.loads.

    Returns:
        object. Python object reconstituted from the given JSON string.
    """
    if s.startswith(prefix):
        s = s.lstrip(prefix)
    return json.loads(s, **kwargs)


def json_to_dict(source_dict, schema):
    """Converts JSON dictionary into Python dictionary using schema."""

    def convert_bool(value, key):
        if isinstance(value, bool):
            return value
        elif isinstance(value, basestring):
            value = value.lower()
            if value == 'true':
                return True
            elif value == 'false':
                return False
        raise ValueError('Bad boolean value for %s: %s' % (key, value))

    output = {}
    for key, attr in schema['properties'].items():
        # Skip schema elements that don't exist in source.
        if key not in source_dict:
            if 'true' != attr.get('optional'):
                raise ValueError('Missing required attribute: %s' % key)
            continue

        attr_type = attr['type']
        if attr_type not in JSON_TYPES:
            raise ValueError('Unsupported JSON type: %s' % attr_type)
        if attr_type == 'object':
            output[key] = json_to_dict(source_dict[key], attr)
        elif attr_type == 'date':
            output[key] = datetime.datetime.strptime(
                source_dict[key], JSON_DATE_FORMAT).date()
        elif attr_type == 'number':
            output[key] = float(source_dict[key])
        elif attr_type == 'boolean':
            output[key] = convert_bool(source_dict[key], key)
        elif attr_type == 'array':
            subschema = attr['items']
            array = []
            for item in source_dict[key]:
                array.append(json_to_dict(item, subschema))
            output[key] = array
        else:
            output[key] = source_dict[key]
    return output


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
        if value is None or isinstance(value, SIMPLE_TYPES) or isinstance(
                value, SUPPORTED_TYPES):
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


def instance_to_dict(instance):
    """Populates data dictionary from instance attrs."""
    adict = {}
    for key, unused_value in instance.__dict__.iteritems():
        if not key.startswith('_'):
            adict[key] = getattr(instance, key)
    return adict


def send_json_response(
    handler, status_code, message, payload_dict=None, xsrf_token=None):
    """Formats and sends out a JSON REST response envelope and body."""
    handler.response.headers[
        'Content-Type'] = 'application/javascript; charset=utf-8'
    handler.response.headers['X-Content-Type-Options'] = 'nosniff'
    handler.response.headers['Content-Disposition'] = 'attachment'
    response = {}
    response['status'] = status_code
    response['message'] = message
    if payload_dict:
        response['payload'] = dumps(payload_dict)
    if xsrf_token:
        response['xsrf_token'] = xsrf_token
    handler.response.write(_JSON_XSSI_PREFIX + dumps(response))


def send_json_file_upload_response(handler, status_code, message):
    """Formats and sends out a JSON REST response envelope and body.

    NOTE: This method has lowered protections against XSSI (compared to
    send_json_response) and so it MUST NOT be used with dynamic data. Use ONLY
    constant data originating entirely on the server as arguments.

    Args:
        handler: the request handler.
        status_code: the HTTP status code for the response.
        message: the text of the message - must not be dynamic data.
    """

    # The correct MIME type for JSON is application/json but there are issues
    # with our AJAX file uploader in MSIE which require text/plain instead.
    if 'MSIE' in handler.request.headers.get('user-agent'):
        content_type = 'text/plain; charset=utf-8'
    else:
        content_type = 'application/javascript; charset=utf-8'
    handler.response.headers['Content-Type'] = content_type
    handler.response.headers['X-Content-Type-Options'] = 'nosniff'
    response = {}
    response['status'] = status_code
    response['message'] = message
    handler.response.write(_JSON_XSSI_PREFIX + dumps(response))


class JsonFile(object):
    """A streaming file-ish interface for JSON content.

    Usage:

        writer = JsonFile('path')
        writer.open('w')
        writer.write(json_serializable_python_object)  # We serialize for you.
        writer.write(another_json_serializable_python_object)
        writer.close()  # Must close before read.
        reader = JsonFile('path')
        reader.open('r')  # Only 'r' and 'w' are supported.
        for entity in reader:
            do_something_with(entity)  # We deserialize back to Python for you.
        self.reader.reset()  # Reset read pointer to head.
        contents = self.reader.read()  # Returns {'rows': [...]}.
        for entity in contents['rows']:
            do_something_with(entity)  # Again, deserialized back to Python.
        reader.close()

    with syntax is not supported.  Cannot be used inside the App Engine
    container where the filesystem is read-only.

    Internally, each call to write will take a Python object, serialize it, and
    write the contents as one line to the json file. On __iter__ we deserialize
    one line at a time, generator-style, to avoid OOM unless serialization/de-
    serialization of one object exhausts memory.
    """

    # When writing to files use \n instead of os.linesep; see
    # http://docs.python.org/2/library/os.html.
    _LINE_TEMPLATE = ',\n    %s'
    _MODE_READ = 'r'
    _MODE_WRITE = 'w'
    _MODES = frozenset([_MODE_READ, _MODE_WRITE])
    _PREFIX = '{"rows": ['
    _SUFFIX = ']}'

    def __init__(self, path):
        self._first = True
        self._file = None
        self._path = path

    def __iter__(self):
        assert self._file
        return self

    def close(self):
        """Closes the file; must close before read."""
        assert self._file
        if not self._file.closed:  # Like file, allow multiple close calls.
            if self.mode == self._MODE_WRITE:
                self._file.write('\n' + self._SUFFIX)
            self._file.close()

    @property
    def mode(self):
        """Returns the mode the file was opened in."""
        assert self._file
        return self._file.mode

    @property
    def name(self):
        """Returns string name of the file."""
        assert self._file
        return self._file.name

    def next(self):
        """Retrieves the next line and deserializes it into a Python object."""
        assert self._file
        line = self._file.readline()
        if line.startswith(self._PREFIX):
            line = self._file.readline()
        if line.endswith(self._SUFFIX):
            raise StopIteration()
        line = line.strip()
        if line.endswith(','):
            line = line[:-1]
        return loads(line)

    def open(self, mode):
        """Opens the file in the given mode string ('r, 'w' only)."""
        assert not self._file
        assert mode in self._MODES
        self._file = open(self._path, mode)
        if self.mode == self._MODE_WRITE:
            self._file.write(self._PREFIX)

    def read(self):
        """Reads the file into a single Python object; may exhaust memory.

        Returns:
            dict. Format: {'rows': [...]} where the value is a list of de-
            serialized objects passed to write.
        """
        assert self._file
        return loads(self._file.read())

    def reset(self):
        """Resets file's position to head."""
        assert self._file
        self._file.seek(0)

    def write(self, python_object):
        """Writes serialized JSON representation of python_object to file.

        Args:
            python_object: object. Contents to write. Must be JSON-serializable.

        Raises:
            ValueError: if python_object cannot be JSON-serialized.
        """
        assert self._file
        template = self._LINE_TEMPLATE
        if self._first:
            template = template[1:]
            self._first = False
        self._file.write(template % dumps(python_object))


def convert_dict_to_xml(element, python_object):
    if isinstance(python_object, dict):
        for key, value in dict.items(python_object):
            dict_element = ElementTree.Element(key)
            element.append(dict_element)
            convert_dict_to_xml(dict_element, value)
    elif isinstance(python_object, list):
        list_element = ElementTree.Element('list')
        element.append(list_element)
        for item in python_object:
            item_element = ElementTree.Element('item')
            list_element.append(item_element)
            convert_dict_to_xml(item_element, item)
    else:
        try:
            loaded_python_object = loads(python_object)
            convert_dict_to_xml(element, loaded_python_object)
        except:  # pylint: disable-msg=bare-except
            element.text = unicode(python_object)
            return


def convert_json_rows_file_to_xml(json_fn, xml_fn):
    """To XML converter for JSON files created by JsonFile writer.

    Usage:

        convert_json_rows_file_to_xml('Student.json', 'Student.xml')

    Args:
        json_fn: filename of the JSON file (readable with JsonFile) to import.
        xml_fn: filename of the target XML file to export.

    The dict and list objects are unwrapped; all other types are converted to
    Unicode strings.
    """

    json_file = JsonFile(json_fn)
    json_file.open('r')
    xml_file = open(xml_fn, 'w')
    xml_file.write('<rows>')
    for line in json_file:
        root = ElementTree.Element('row')
        convert_dict_to_xml(root, line)
        xml_file.write(ElementTree.tostring(root, encoding='utf-8'))
        xml_file.write('\n')
    xml_file.write('</rows>')
    xml_file.close()
