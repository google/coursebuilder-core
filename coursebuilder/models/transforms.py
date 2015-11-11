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


import json
from StringIO import StringIO
from xml.etree import ElementTree

import yaml

from common import schema_transforms
import entity_transforms

# Leave tombstones pointing to moved functions
# pylint: disable=unused-import,g-bad-import-order
from entity_transforms import dict_to_entity
from entity_transforms import entity_to_dict
from entity_transforms import get_schema_for_entity

from google.appengine.api import datastore_types
from google.appengine.ext import db


# Leave tombstones pointing to moved functions from 'schema_transforms'
dict_to_instance = schema_transforms.dict_to_instance
json_to_dict = schema_transforms.json_to_dict
string_to_value = schema_transforms.string_to_value
validate_object_matches_json_schema = (
    schema_transforms.validate_object_matches_json_schema)
value_to_string = schema_transforms.value_to_string
ISO_8601_DATE_FORMAT = schema_transforms.ISO_8601_DATE_FORMAT
ISO_8601_DATETIME_FORMAT = schema_transforms.ISO_8601_DATETIME_FORMAT
JSON_TYPES = schema_transforms.JSON_TYPES

# Leave tombstones pointing to moved functions from 'entity_transforms'
dict_to_entity = entity_transforms.dict_to_entity
entity_to_dict = entity_transforms.entity_to_dict
get_schema_for_entity = entity_transforms.get_schema_for_entity

# Prefix to add to all JSON responses to guard against XSSI. Must be kept in
# sync with modules/oeditor/oeditor.html.
JSON_XSSI_PREFIX = ")]}'\n"

# Modules can extends the range of objects which can be JSON serialized by
# adding custom JSON encoder functions to this list. The function will be called
# with a single argument which is an object to be encoded. If the encoding
# function wants to encode this object, it should return a serializable
# representation of the object, or return None otherwise. The first function
# that can encode the object wins, so modules should not override the encodings
# of standard type (list, string, number, etc.
CUSTOM_JSON_ENCODERS = []


def _geo_pt_tostring(value):
    return {'lat': value.lat, 'lon': value.lon}


def _db_key_tostring(value):
    return str(value)


_custom_type_serializer = {
    db.GeoPt: _geo_pt_tostring,
    datastore_types.Key: _db_key_tostring}


def dict_to_json(source_dict, schema=None, recurse=False):
    return schema_transforms.dict_to_json(
        source_dict,
        custom_type_serializer=_custom_type_serializer, schema=schema,
        recurse=recurse)


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

    def set_encoder(obj):
        if isinstance(obj, set):
            return list(obj)
        return None

    def string_escape(in_str):
        # Defend against XSS by escaping <, > and non-ASCII chars
        out = StringIO()
        for c in in_str.decode('utf8'):
            char_val = ord(c)
            if char_val > 0x7f or c == '<' or c == '>':
                out.write('\\u%04X' % char_val)
            else:
                out.write(c)
        return out.getvalue()

    class CustomJSONEncoder(json.JSONEncoder):

        def default(self, obj):
            for f in CUSTOM_JSON_ENCODERS + [set_encoder]:
                value = f(obj)
                if value is not None:
                    return value
            return super(CustomJSONEncoder, self).default(obj)

    if 'cls' not in kwargs:
        kwargs['cls'] = CustomJSONEncoder

    return string_escape(json.dumps(*args, **kwargs))


def loads(s, prefix=JSON_XSSI_PREFIX, strict=True, **kwargs):
    """Wrapper around json.loads that handles XSSI-protected responses.

    To prevent XSSI we insert a prefix before our JSON responses during server-
    side rendering. This loads() removes the prefix and should always be used in
    place of json.loads. See usage docs at
    http://docs.python.org/2/library/json.html.

    Args:
        s: str or unicode. JSON contents to convert.
        prefix: string. The XSSI prefix we remove before conversion.
        strict: boolean. If True use JSON parser, if False - YAML. YAML parser
            allows parsing of malformed JSON text, which has trailing commas and
            can't be parsed by the normal JSON parser.
        **kwargs: keyword arguments delegated to json.loads.

    Returns:
        object. Python object reconstituted from the given JSON string.
    """
    if s.startswith(prefix):
        s = s.lstrip(prefix)
    if strict:
        return json.loads(s, **kwargs)
    else:
        return yaml.safe_load(s, **kwargs)


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
    handler.response.write(JSON_XSSI_PREFIX + dumps(response))


def send_file_upload_response(
        handler, status_code, message, payload_dict=None):
    """Formats and sends out a response to a file upload request.

    Args:
        handler: the request handler.
        status_code: int. The HTTP status code for the response.
        message: str. The text of the message.
        payload_dict: dict. A optional dict of extra data.
    """

    handler.response.headers['Content-Type'] = 'text/xml'
    handler.response.headers['X-Content-Type-Options'] = 'nosniff'

    response_elt = ElementTree.Element('response')

    status_elt = ElementTree.Element('status')
    status_elt.text = str(status_code)
    response_elt.append(status_elt)

    message_elt = ElementTree.Element('message')
    message_elt.text = message
    response_elt.append(message_elt)

    if payload_dict:
        payload_elt = ElementTree.Element('payload')
        payload_elt.text = dumps(payload_dict)
        response_elt.append(payload_elt)

    handler.response.write(ElementTree.tostring(response_elt, encoding='utf-8'))


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
    _SUFFIX = ']}\n'  # make sure output is new-line terminated

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
        except:  # pylint: disable=bare-except
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


def nested_lists_as_string_to_dict(stringified_list_of_lists):
    """Convert list of 2-item name/value lists to dict.

    This is for converting Student.additional_fields.  When creating a
    Student, the raw HTML form content is just added to additional_fields
    without first converting into a dict.  Thus we have a very dict-like
    thing which is actually expressed as a stringified list-of-lists.
    E.g., '[["age", "27"], ["gender", "female"], ["course_goal", "dabble"]]

    Args:
      stringified_list_of_lists: String as example above
    Returns:
      dict version of the list-of-key/value 2-tuples
    """

    if not isinstance(stringified_list_of_lists, basestring):
        return None
    try:
        items = json.loads(stringified_list_of_lists)
        if not isinstance(items, list):
            return None
        for item in items:
            if not isinstance(item, list):
                return False
            if len(item) != 2:
                return False
            if not isinstance(item[0], basestring):
                return False
        return {item[0]: item[1] for item in items}
    except ValueError:
        return None


def dict_to_nested_lists_as_string(d):
    """Convert a dict to stringified list-of-2-tuples format."""
    return json.dumps([[a, b] for a, b in d.items()])
