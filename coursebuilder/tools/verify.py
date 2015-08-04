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
#
# @author: psimakov@google.com (Pavel Simakov)

"""Enforces schema and verifies course files for referential integrity.

Use this script to verify referential integrity of your course definition files
before you import them into the production instance of Google AppEngine.

Here is how to use the script:
     - prepare your course files
         - edit the data/unit.csv file
         - edit the data/lesson.csv file
         - edit the assets/js/activity-*.*.js files
         - edit the assets/js/assessment-*.js files
     - run the script from a command line by navigating to the root
       directory of the app and then typing "python tools/verify.py"
     - review the report printed to the console for errors and warnings

Good luck!
"""

import csv
import json
import logging
import os
import re
from StringIO import StringIO
import sys


BOOLEAN = object()
STRING = object()
FLOAT = object()
INTEGER = object()
CORRECT = object()
REGEX = object()
INTEGER_OR_INTEGER_LIST = object()

SCHEMA = {
    'assessment': {
        'assessmentName': STRING,
        'preamble': STRING,
        'checkAnswers': BOOLEAN,
        'questionsList': [{
            'questionHTML': STRING,
            'lesson': STRING,
            'choices': [STRING, CORRECT],
            # The fractional score for each choice in this question, if it is
            # multiple-choice. Each of these values should be between 0.0 and
            # 1.0, inclusive.
            'choiceScores': [FLOAT],
            # The weight given to the entire question.
            'weight': INTEGER,
            'multiLine': BOOLEAN,
            'correctAnswerNumeric': FLOAT,
            'correctAnswerString': STRING,
            'correctAnswerRegex': REGEX}]
    }, 'activity': [
        STRING,
        {
            'questionType': 'multiple choice',
            'questionHTML': STRING,
            'choices': [[STRING, BOOLEAN, STRING]]
        }, {
            'questionType': 'multiple choice group',
            'questionGroupHTML': STRING,
            'questionsList': [{
                'questionHTML': STRING,
                'choices': [STRING],
                'correctIndex': INTEGER_OR_INTEGER_LIST,
                'multiSelect': BOOLEAN}],
            'allCorrectMinCount': INTEGER,
            'allCorrectOutput': STRING,
            'someIncorrectOutput': STRING
        }, {
            'questionType': 'freetext',
            'questionHTML': STRING,
            'correctAnswerRegex': REGEX,
            'correctAnswerOutput': STRING,
            'incorrectAnswerOutput': STRING,
            'showAnswerOutput': STRING,
            'showAnswerPrompt': STRING,
            'outputHeight': STRING
        }]}

UNIT_TYPE_UNIT = 'U'
UNIT_TYPE_LINK = 'O'
UNIT_TYPE_ASSESSMENT = 'A'
UNIT_TYPE_CUSTOM = 'X'
UNIT_TYPES = [UNIT_TYPE_UNIT, UNIT_TYPE_LINK, UNIT_TYPE_ASSESSMENT,
              UNIT_TYPE_CUSTOM]

UNIT_TYPE_NAMES = {
    UNIT_TYPE_UNIT: 'Unit',
    UNIT_TYPE_LINK: 'Link',
    UNIT_TYPE_ASSESSMENT: 'Assessment',
    UNIT_TYPE_CUSTOM: 'Custom Unit'}

UNITS_HEADER = (
    'id,type,unit_id,title,release_date,now_available')
LESSONS_HEADER = (
    'unit_id,unit_title,lesson_id,lesson_title,lesson_activity,'
    'lesson_activity_name,lesson_notes,lesson_video_id,lesson_objectives')

UNIT_CSV_TO_DB_CONVERTER = {
    'id': None,
    'type': ('type', unicode),
    'unit_id': ('unit_id', unicode),
    'title': ('title', unicode),
    'release_date': ('release_date', unicode),
    'now_available': ('now_available', lambda value: value == 'True')
}
LESSON_CSV_TO_DB_CONVERTER = {
    'unit_id': ('unit_id', int),

    # Field 'unit_title' is a duplicate of Unit.title. We enforce that both
    # values are the same and ignore this value altogether.
    'unit_title': None,
    'lesson_id': ('lesson_id', int),
    'lesson_title': ('title', unicode),
    'lesson_activity': ('activity', lambda value: value == 'yes'),
    'lesson_activity_name': ('activity_title', unicode),
    'lesson_video_id': ('video', unicode),
    'lesson_objectives': ('objectives', unicode),
    'lesson_notes': ('notes', unicode)
}

# pylint: disable=anomalous-backslash-in-string
NO_VERIFY_TAG_NAME_OPEN = '<gcb-no-verify>\s*\n'
# pylint: enable=anomalous-backslash-in-string
NO_VERIFY_TAG_NAME_CLOSE = '</gcb-no-verify>'

OUTPUT_FINE_LOG = False
OUTPUT_DEBUG_LOG = False


class Term(object):

    def __init__(self, term_type, value=None):
        self.term_type = term_type
        self.value = value

    def __eq__(self, other):
        if type(other) is not Term:
            return False
        else:
            return ((self.term_type == other.term_type) and
                    (self.value == other.value))


class SchemaException(Exception):
    """A class to represent a schema error."""

    def format_primitive_value_name(self, name):
        if name == REGEX:
            return 'REGEX(...)'
        if name == CORRECT:
            return 'CORRECT(...)'
        if name == BOOLEAN:
            return 'BOOLEAN'
        return name

    def format_primitive_type_name(self, name):
        """Formats a name for a primitive type."""

        if name == BOOLEAN:
            return 'BOOLEAN'
        if name == REGEX:
            return 'REGEX(...)'
        if name == CORRECT:
            return 'CORRECT(...)'
        if name == STRING or isinstance(name, basestring):
            return 'STRING'
        if name == FLOAT:
            return 'FLOAT'
        if name == INTEGER_OR_INTEGER_LIST:
            return 'INTEGER_OR_INTEGER_LIST'
        if name == INTEGER:
            return 'INTEGER'
        if isinstance(name, dict):
            return '{...}'
        if isinstance(name, list):
            return '[...]'
        return 'Unknown type name \'%s\'' % name.__class__.__name__

    def format_type_names(self, names):
        if isinstance(names, list):
            captions = []
            for name in names:
                captions.append(self.format_primitive_type_name(name))
            return captions
        else:
            return self.format_primitive_type_name(names)

    def __init__(self, message, value=None, types=None, path=None):
        prefix = ''
        if path:
            prefix = 'Error at %s\n' % path

        if types is not None:
            if value:
                message = prefix + message % (
                    self.format_primitive_value_name(value),
                    self.format_type_names(types))
            else:
                message = prefix + message % self.format_type_names(types)
        else:
            if value:
                message = prefix + (
                    message % self.format_primitive_value_name(value))
            else:
                message = prefix + message

        super(SchemaException, self).__init__(message)


class Context(object):
    """"A class that manages a stack of traversal contexts."""

    def __init__(self):
        self.parent = None
        self.path = ['/']

    def new(self, names):
        """"Derives a new context from the current one."""

        context = Context()
        context.parent = self
        context.path = list(self.path)
        if names:
            if isinstance(names, list):
                for name in names:
                    if name:
                        context.path.append('/' + '%s' % name)
            else:
                context.path.append('/' + '%s' % names)
        return context

    def format_path(self):
        """Formats the canonical name of this context."""

        return ''.join(self.path)


class SchemaHelper(object):
    """A class that knows how to apply the schema."""

    def __init__(self):
        self.type_stats = {}

    def visit_element(self, atype, value, context, is_terminal=True):
        """Callback for each schema element being traversed."""

        if atype in self.type_stats:
            count = self.type_stats[atype]
        else:
            count = 0
        self.type_stats[atype] = count + 1

        if is_terminal:
            self.parse_log.append('  TERMINAL: %s %s = %s' % (
                atype, context.format_path(), value))
        else:
            self.parse_log.append('  NON-TERMINAL: %s %s' % (
                atype, context.format_path()))

    def extract_all_terms_to_depth(self, key, values, type_map):
        """Walks schema type map recursively to depth."""

        # Walks schema type map recursively to depth and creates a list of all
        # possible {key: value} pairs. The latter is a list of all non-terminal
        # and terminal terms allowed in the schema. The list of terms from this
        # method can be bound to an execution context for evaluating whether a
        # given instance's map complies with the schema.

        if key:
            type_map.update({key: key})

        if values == REGEX:
            type_map.update({'regex': lambda x: Term(REGEX, x)})
            return

        if values == CORRECT:
            type_map.update({'correct': lambda x: Term(CORRECT, x)})
            return

        if values == BOOLEAN:
            type_map.update(
                {'true': Term(BOOLEAN, True), 'false': Term(BOOLEAN, False)})
            return

        if values == STRING or values == INTEGER:
            return

        if isinstance(values, dict):
            for new_key, new_value in values.items():
                self.extract_all_terms_to_depth(new_key, new_value, type_map)
            return

        if isinstance(values, list):
            for new_value in values:
                self.extract_all_terms_to_depth(None, new_value, type_map)
            return

    def find_selectors(self, type_map):
        """Finds all type selectors."""

        # Finds all elements in the type map where both a key and a value are
        # strings. These elements are used to find one specific type map among
        # several alternative type maps.

        selector = {}
        for akey, avalue in type_map.items():
            if isinstance(akey, basestring) and isinstance(avalue, basestring):
                selector.update({akey: avalue})
        return selector

    def find_compatible_dict(self, value_map, type_map, unused_context):
        """Find the type map most compatible with the value map."""

        # A value map is considered compatible with a type map when former
        # contains the same key names and the value types as the type map.

        # special case when we have just one type; check name and type are the
        # same
        if len(type_map) == 1:
            for value_key in value_map.keys():
                for key in type_map[0].keys():
                    if value_key == key:
                        return key, type_map[0]
            raise SchemaException(
                "Expected: '%s'\nfound: %s", type_map[0].keys()[0], value_map)

        # case when we have several types to choose from
        for adict in type_map:
            dict_selector = self.find_selectors(adict)
            for akey, avalue in dict_selector.items():
                if value_map[akey] == avalue:
                    return akey, adict
        return None, None

    def check_single_value_matches_type(self, value, atype, context):
        """Checks if a single value matches a specific (primitive) type."""

        if atype == BOOLEAN:
            if isinstance(value, bool) or value.term_type == BOOLEAN:
                self.visit_element('BOOLEAN', value, context)
                return True
            else:
                raise SchemaException(
                    'Expected: \'true\' or \'false\'\nfound: %s', value)
        if isinstance(atype, basestring):
            if isinstance(value, basestring):
                self.visit_element('str', value, context)
                return True
            else:
                raise SchemaException('Expected: \'string\'\nfound: %s', value)
        if atype == STRING:
            if isinstance(value, basestring):
                self.visit_element('STRING', value, context)
                return True
            else:
                raise SchemaException('Expected: \'string\'\nfound: %s', value)
        if atype == REGEX and value.term_type == REGEX:
            self.visit_element('REGEX', value, context)
            return True
        if atype == CORRECT and value.term_type == CORRECT:
            self.visit_element('CORRECT', value, context)
            return True
        if atype == FLOAT:
            if is_number(value):
                self.visit_element('NUMBER', value, context)
                return True
            else:
                raise SchemaException('Expected: \'number\'\nfound: %s', value)
        if atype == INTEGER_OR_INTEGER_LIST:
            if is_integer(value):
                self.visit_element('INTEGER', value, context)
                return True
            if is_integer_list(value):
                self.visit_element('INTEGER_OR_INTEGER_LIST', value, context)
                return True
            raise SchemaException(
                'Expected: \'integer\' or '
                '\'array of integer\'\nfound: %s', value,
                path=context.format_path())
        if atype == INTEGER:
            if is_integer(value):
                self.visit_element('INTEGER', value, context)
                return True
            else:
                raise SchemaException(
                    'Expected: \'integer\'\nfound: %s', value,
                    path=context.format_path())
        raise SchemaException(
            'Unexpected value \'%s\'\n'
            'for type %s', value, atype, path=context.format_path())

    def check_value_list_matches_type(self, value, atype, context):
        """Checks if all items in value list match a specific type."""

        for value_item in value:
            found = False
            for atype_item in atype:
                if isinstance(atype_item, list):
                    for atype_item_item in atype_item:
                        if self.does_value_match_type(
                                value_item, atype_item_item, context):
                            found = True
                            break
                else:
                    if self.does_value_match_type(
                            value_item, atype_item, context):
                        found = True
                        break
            if not found:
                raise SchemaException(
                    'Expected: \'%s\'\nfound: %s', atype, value)
        return True

    def check_value_matches_type(self, value, atype, context):
        """Checks if single value or a list of values match a specific type."""

        if isinstance(atype, list) and isinstance(value, list):
            return self.check_value_list_matches_type(value, atype, context)
        else:
            return self.check_single_value_matches_type(value, atype, context)

    def does_value_match_type(self, value, atype, context):
        """Same as other method, but does not throw an exception."""

        try:
            return self.check_value_matches_type(value, atype, context)
        except SchemaException:
            return False

    def does_value_match_one_of_types(self, value, types, context):
        """Checks if a value matches to one of the types in the list."""

        type_names = None
        if isinstance(types, list):
            type_names = types
        if type_names:
            for i in range(0, len(type_names)):
                if self.does_value_match_type(value, type_names[i], context):
                    return True

        return False

    def does_value_match_map_of_type(self, value, types, context):
        """Checks if value matches any variation of {...} type."""

        # find all possible map types
        maps = []
        for atype in types:
            if isinstance(atype, dict):
                maps.append(atype)
        if not maps and isinstance(types, dict):
            maps.append(types)

        # check if the structure of value matches one of the maps
        if isinstance(value, dict):
            aname, adict = self.find_compatible_dict(value, maps, context)
            if adict:
                self.visit_element(
                    'dict', value, context.new(aname), is_terminal=False)
                for akey, avalue in value.items():
                    if akey not in adict:
                        raise SchemaException(
                            'Unknown term \'%s\'', akey,
                            path=context.format_path())
                    self.check_value_of_valid_type(
                        avalue, adict[akey], context.new([aname, akey]))
                return True
            raise SchemaException(
                'The value:\n  %s\n'
                'is incompatible with expected type(s):\n  %s',
                value, types, path=context.format_path())

        return False

    def format_name_with_index(self, alist, aindex):
        """A function to format a context name with an array element index."""

        if len(alist) == 1:
            return ''
        else:
            return '[%s]' % aindex

    def does_value_match_list_of_types_in_order(
        self, value, types, context, target):
        """Iterates the value and types in given order and checks for match."""

        all_values_are_lists = True
        for avalue in value:
            if not isinstance(avalue, list):
                all_values_are_lists = False

        if all_values_are_lists:
            for i in range(0, len(value)):
                self.check_value_of_valid_type(value[i], types, context.new(
                    self.format_name_with_index(value, i)), in_order=True)
        else:
            if len(target) != len(value):
                raise SchemaException(
                    'Expected: \'%s\' values\n' + 'found: %s.' % value,
                    len(target), path=context.format_path())
            for i in range(0, len(value)):
                self.check_value_of_valid_type(value[i], target[i], context.new(
                    self.format_name_with_index(value, i)))

        return True

    def does_value_match_list_of_types_any_order(self, value, types,
                                                 context, lists):
        """Iterates the value and types, checks if they match in any order."""

        target = lists
        if not target:
            if not isinstance(types, list):
                raise SchemaException(
                    'Unsupported type %s',
                    None, types, path=context.format_path())
            target = types

        for i in range(0, len(value)):
            found = False
            for atarget in target:
                try:
                    self.check_value_of_valid_type(
                        value[i], atarget,
                        context.new(self.format_name_with_index(value, i)))
                    found = True
                    break
                except SchemaException as unused_e:
                    continue

            if not found:
                raise SchemaException(
                    'The value:\n  %s\n'
                    'is incompatible with expected type(s):\n  %s',
                    value, types, path=context.format_path())
        return True

    def does_value_match_list_of_type(self, value, types, context, in_order):
        """Checks if a value matches a variation of [...] type."""

        # Extra argument controls whether matching must be done in a specific
        # or in any order. A specific order is demanded by [[...]]] construct,
        # i.e. [[STRING, INTEGER, BOOLEAN]], while sub elements inside {...} and
        # [...] can be matched in any order.

        # prepare a list of list types
        lists = []
        for atype in types:
            if isinstance(atype, list):
                lists.append(atype)
        if len(lists) > 1:
            raise SchemaException(
                'Unable to validate types with multiple alternative '
                'lists %s', None, types, path=context.format_path())

        if isinstance(value, list):
            if len(lists) > 1:
                raise SchemaException(
                    'Allowed at most one list\nfound: %s.',
                    None, types, path=context.format_path())

            # determine if list is in order or not as hinted by double array
            # [[..]]; [STRING, NUMBER] is in any order, but [[STRING, NUMBER]]
            # demands order
            ordered = len(lists) == 1 and isinstance(types, list)
            if in_order or ordered:
                return self.does_value_match_list_of_types_in_order(
                    value, types, context, lists[0])
            else:
                return self.does_value_match_list_of_types_any_order(
                    value, types, context, lists)

        return False

    def check_value_of_valid_type(self, value, types, context, in_order=None):
        """Check if a value matches any of the given types."""

        if not (isinstance(types, list) or isinstance(types, dict)):
            self.check_value_matches_type(value, types, context)
            return
        if (self.does_value_match_list_of_type(value, types,
                                               context, in_order) or
            self.does_value_match_map_of_type(value, types, context) or
            self.does_value_match_one_of_types(value, types, context)):
            return

        raise SchemaException(
            'Unknown type %s', value, path=context.format_path())

    def check_instances_match_schema(self, values, types, name):
        """Recursively decompose 'values' to see if they match schema types."""

        self.parse_log = []
        context = Context().new(name)
        self.parse_log.append('  ROOT %s' % context.format_path())

        # pylint: disable=protected-access
        values_class = values.__class__
        # pylint: enable=protected-access

        # handle {..} containers
        if isinstance(types, dict):
            if not isinstance(values, dict):
                raise SchemaException(
                    'Error at \'/\': expected {...}, found %s' % (
                        values_class.__name__))
            self.check_value_of_valid_type(values, types, context.new([]))
            return

        # handle [...] containers
        if isinstance(types, list):
            if not isinstance(values, list):
                raise SchemaException(
                    'Error at \'/\': expected [...], found %s' % (
                        values_class.__name__))
            for i in range(0, len(values)):
                self.check_value_of_valid_type(
                    values[i], types, context.new('[%s]' % i))
            return

        raise SchemaException(
            'Expected an array or a dictionary.', None,
            path=context.format_path())


def escape_quote(value):
    return unicode(value).replace('\'', r'\'')


class Unit(object):
    """A class to represent a Unit."""

    def __init__(self):
        self.id = 0
        self.type = ''
        self.unit_id = ''
        self.title = ''
        self.release_date = ''
        self.now_available = False

    def list_properties(self, name, output):
        """Outputs all properties of the unit."""

        output.append('%s[\'id\'] = %s;' % (name, self.id))
        output.append('%s[\'type\'] = \'%s\';' % (
            name, escape_quote(self.type)))
        output.append('%s[\'unit_id\'] = \'%s\';' % (
            name, escape_quote(self.unit_id)))
        output.append('%s[\'title\'] = \'%s\';' % (
            name, escape_quote(self.title)))
        output.append('%s[\'release_date\'] = \'%s\';' % (
            name, escape_quote(self.release_date)))
        output.append('%s[\'now_available\'] = %s;' % (
            name, str(self.now_available).lower()))


class Lesson(object):
    """A class to represent a Lesson."""

    def __init__(self):
        self.unit_id = 0
        self.unit_title = ''
        self.lesson_id = 0
        self.lesson_title = ''
        self.lesson_activity = ''
        self.lesson_activity_name = ''
        self.lesson_notes = ''
        self.lesson_video_id = ''
        self.lesson_objectives = ''

    def list_properties(self, name, output):
        """Outputs all properties of the lesson."""

        activity = 'false'
        if self.lesson_activity == 'yes':
            activity = 'true'

        output.append('%s[\'unit_id\'] = %s;' % (name, self.unit_id))
        output.append('%s[\'unit_title\'] = \'%s\';' % (
            name, escape_quote(self.unit_title)))
        output.append('%s[\'lesson_id\'] = %s;' % (name, self.lesson_id))
        output.append('%s[\'lesson_title\'] = \'%s\';' % (
            name, escape_quote(self.lesson_title)))
        output.append('%s[\'lesson_activity\'] = %s;' % (name, activity))
        output.append('%s[\'lesson_activity_name\'] = \'%s\';' % (
            name, escape_quote(self.lesson_activity_name)))
        output.append('%s[\'lesson_notes\'] = \'%s\';' % (
            name, escape_quote(self.lesson_notes)))
        output.append('%s[\'lesson_video_id\'] = \'%s\';' % (
            name, escape_quote(self.lesson_video_id)))
        output.append('%s[\'lesson_objectives\'] = \'%s\';' % (
            name, escape_quote(self.lesson_objectives)))

    def to_id_string(self):
        return '%s.%s.%s' % (self.unit_id, self.lesson_id, self.lesson_title)


class Assessment(object):
    """A class to represent a Assessment."""

    def __init__(self):
        self.scope = {}
        SchemaHelper().extract_all_terms_to_depth(
            'assessment', SCHEMA['assessment'], self.scope)


class Activity(object):
    """A class to represent a Activity."""

    def __init__(self):
        self.scope = {}
        SchemaHelper().extract_all_terms_to_depth(
            'activity', SCHEMA['activity'], self.scope)


def silent_echo(unused_level, unused_message):
    pass


def echo(level, message):
    logging.log(level, message)


def is_integer_list(s):
    try:
        if not isinstance(s, list):
            return False
        for item in s:
            if not isinstance(item, int):
                return False
        return True
    except ValueError:
        return False


def is_integer(s):
    try:
        return int(s) == float(s)
    except Exception:  # pylint: disable=broad-except
        return False


def is_boolean(s):
    try:
        return s == 'True' or s == 'False'
    except ValueError:
        return False


def is_number(s):
    try:
        float(s)
        return True
    except ValueError:
        return False


def is_one_of(value, values):
    for current in values:
        if value == current:
            return True
    return False


def text_to_line_numbered_text(text):
    """Adds line numbers to the provided text."""

    lines = text.split('\n')
    results = []
    i = 1
    for line in lines:
        results.append(str(i) + ': ' + line)
        i += 1
    return '\n  '.join(results)


def set_object_attributes(target_object, names, values, converter=None):
    """Sets object attributes from provided values."""

    if len(names) != len(values):
        raise SchemaException(
            'The number of elements must match: %s and %s' % (names, values))
    for i in range(len(names)):
        if converter:
            target_def = converter.get(names[i])
            if target_def:
                target_name = target_def[0]
                target_type = target_def[1]
                setattr(target_object, target_name, target_type(values[i]))
                continue
        if is_integer(values[i]):
            # if we are setting an attribute of an object that support
            # metadata, try to infer the target type and convert 'int' into
            # 'str' here
            target_type = None
            if hasattr(target_object.__class__, names[i]):
                attribute = getattr(target_object.__class__, names[i])
                if hasattr(attribute, 'data_type'):
                    target_type = attribute.data_type.__name__

            if target_type and (target_type == 'str' or
                                target_type == 'basestring'):
                setattr(target_object, names[i], str(values[i]))
            else:
                setattr(target_object, names[i], int(values[i]))
            continue
        if is_boolean(values[i]):
            setattr(target_object, names[i], bool(values[i]))
            continue
        setattr(target_object, names[i], values[i])


def read_objects_from_csv_stream(stream, header, new_object, converter=None):
    return read_objects_from_csv(
        csv.reader(StringIO(stream.read())), header, new_object,
        converter=converter)


def read_objects_from_csv_file(fname, header, new_object):
    return read_objects_from_csv_stream(open(fname), header, new_object)


def read_objects_from_csv(value_rows, header, new_object, converter=None):
    """Reads objects from the rows of a CSV file."""

    values = []
    for row in value_rows:
        if not row:
            continue
        values.append(row)
    names = header.split(',')

    if names != values[0]:
        raise SchemaException(
            'Error reading CSV header.\n  '
            'Header row had %s element(s): %s\n  '
            'Expected header row with %s element(s): %s' % (
                len(values[0]), values[0], len(names), names))

    items = []
    for i in range(1, len(values)):
        if len(names) != len(values[i]):
            raise SchemaException(
                'Error reading CSV data row.\n  '
                'Row #%s had %s element(s): %s\n  '
                'Expected %s element(s): %s' % (
                    i, len(values[i]), values[i], len(names), names))

        # Decode string values in case they were encoded in UTF-8. The CSV
        # reader should do this automatically, but it does not. The issue is
        # discussed here: http://docs.python.org/2/library/csv.html
        decoded_values = []
        for value in values[i]:
            if isinstance(value, basestring):
                value = unicode(value.decode('utf-8'))
            decoded_values.append(value)

        item = new_object()
        set_object_attributes(item, names, decoded_values, converter=converter)
        items.append(item)
    return items


def escape_javascript_regex(text):
    return re.sub(
        r'correctAnswerRegex([:][ ]*)([/])(.*)([/][ismx]*)',
        r'correctAnswerRegex: regex("\2\3\4")', text)


def remove_javascript_single_line_comment(text):
    text = re.sub(re.compile('^(.*?)[ ]+//(.*)$', re.MULTILINE), r'\1', text)
    text = re.sub(re.compile('^//(.*)$', re.MULTILINE), r'', text)
    return text


def remove_javascript_multi_line_comment(text):
    # pylint: disable=anomalous-backslash-in-string
    return re.sub(
        re.compile('/\*(.*)\*/', re.MULTILINE + re.DOTALL), r'', text)
    # pylint: enable=anomalous-backslash-in-string


def parse_content_marked_no_verify(content):
    """Parses and returns a tuple of real content and no-verify text."""

    # If you have any free-form JavaScript in the activity file, you need
    # to place it between //<gcb-no-verify> ... //</gcb-no-verify> tags
    # so that the verifier can selectively ignore it.

    pattern = re.compile('%s(.*)%s' % (
        NO_VERIFY_TAG_NAME_OPEN, NO_VERIFY_TAG_NAME_CLOSE), re.DOTALL)
    m = pattern.search(content)
    noverify_text = None
    if m:
        noverify_text = m.group(1)
    return (re.sub(pattern, '', content), noverify_text)


def convert_javascript_to_python(content, root_name):
    """Removes JavaScript specific syntactic constructs and returns a tuple."""

    # Reads the content and removes JavaScript comments, var's, and escapes
    # regular expressions.

    (content, noverify_text) = parse_content_marked_no_verify(content)
    content = remove_javascript_multi_line_comment(content)
    content = remove_javascript_single_line_comment(content)
    content = content.replace('var %s = ' % root_name, '%s = ' % root_name)
    content = escape_javascript_regex(content)
    return (content, noverify_text)


def convert_javascript_file_to_python(fname, root_name):
    return convert_javascript_to_python(
        ''.join(open(fname, 'r').readlines()), root_name)


def legacy_eval_python_expression_for_test(content, scope, unused_root_name):
    """Legacy content parsing function using compile/exec."""

    logging.warning('WARNING! This code is unsafe and uses compile/exec!')

    # First compiles and then evaluates a Python script text in a restricted
    # environment using provided bindings. Returns the resulting bindings if
    # evaluation completed.

    # create a new execution scope that has only the schema terms defined;
    # remove all other languages constructs including __builtins__
    restricted_scope = {}
    restricted_scope.update(scope)
    restricted_scope.update({'__builtins__': {}})
    code = compile(content, '<string>', 'exec')
    exec code in restricted_scope  # pylint: disable=exec-used
    return restricted_scope


def not_implemented_parse_content(
    unused_content, unused_scope, unused_root_name):
    raise Exception('Not implemented.')


# by default no parser method is configured; set custom parser if you have it
parse_content = not_implemented_parse_content


def evaluate_python_expression_from_text(content, root_name, scope,
                                         noverify_text):
    """Compiles and evaluates a Python script in a restricted environment."""

    restricted_scope = parse_content(content, scope, root_name)
    if noverify_text:
        restricted_scope['noverify'] = noverify_text
    if restricted_scope.get(root_name) is None:
        raise Exception('Unable to find \'%s\'' % root_name)
    return restricted_scope


def evaluate_javascript_expression_from_file(fname, root_name, scope, error):
    (content, noverify_text) = convert_javascript_file_to_python(fname,
                                                                 root_name)
    try:
        return evaluate_python_expression_from_text(content, root_name, scope,
                                                    noverify_text)
    except:
        error('Unable to parse %s in file %s\n  %s' % (
            root_name, fname, text_to_line_numbered_text(content)))
        for message in sys.exc_info():
            error(str(message))
        raise


class Verifier(object):
    """Verifies Units, Lessons, Assessments, Activities and their relations."""

    def __init__(self):
        self.echo_func = silent_echo
        self.schema_helper = SchemaHelper()
        self.errors = 0
        self.warnings = 0
        self.export = []

    def verify_unit_fields(self, units):
        self.export.append('units = Array();')
        for unit in units:
            if not is_one_of(unit.now_available, [True, False]):
                self.error(
                    'Bad now_available \'%s\' for unit id %s; expected '
                    '\'True\' or \'False\'' % (unit.now_available, unit.id))

            if not is_one_of(unit.type, UNIT_TYPES):
                self.error(
                    'Bad type \'%s\' for unit id %s; '
                    'expected: %s.' % (unit.type, unit.id, UNIT_TYPES))

            if unit.type == 'U':
                if not is_integer(unit.unit_id):
                    self.error(
                        'Expected integer unit_id, found %s in unit id '
                        ' %s' % (unit.unit_id, unit.id))

            self.export.append('')
            self.export.append('units[%s] = Array();' % unit.id)
            self.export.append('units[%s][\'lessons\'] = Array();' % unit.id)
            unit.list_properties('units[%s]' % unit.id, self.export)

    def verify_lesson_fields(self, lessons):
        for lesson in lessons:
            if not is_one_of(lesson.lesson_activity, ['yes', '']):
                self.error('Bad lesson_activity \'%s\' for lesson_id %s' % (
                    lesson.lesson_activity, lesson.lesson_id))

            self.export.append('')
            self.export.append('units[%s][\'lessons\'][%s] = Array();' % (
                lesson.unit_id, lesson.lesson_id))
            lesson.list_properties('units[%s][\'lessons\'][%s]' % (
                lesson.unit_id, lesson.lesson_id), self.export)

    def verify_unit_lesson_relationships(self, units, lessons):
        """Checks each lesson points to a unit and all lessons are in use."""

        used_lessons = []
        units.sort(key=lambda x: x.id)
        # for unit in units:
        for i in range(0, len(units)):
            unit = units[i]

            # check that unit ids are 1-based and sequential
            if unit.id != i + 1:
                self.error('Unit out of order: %s' % (unit.id))

            # get the list of lessons for each unit
            self.fine('Unit %s: %s' % (unit.id, unit.title))
            unit_lessons = []
            for lesson in lessons:
                if lesson.unit_id == unit.unit_id:
                    if lesson.unit_title != unit.title:
                        raise Exception(''.join([
                            'A unit_title of a lesson (id=%s) must match ',
                            'title of a unit (id=%s) the lesson belongs to.'
                            ]) % (lesson.lesson_id, lesson.unit_id))
                    unit_lessons.append(lesson)
                    used_lessons.append(lesson)

            # inspect all lessons for the current unit
            unit_lessons.sort(key=lambda x: x.lesson_id)
            for j in range(0, len(unit_lessons)):
                lesson = unit_lessons[j]

                # check that lesson_ids are 1-based and sequential
                if lesson.lesson_id != j + 1:
                    self.warn(
                        'Lesson lesson_id is out of order: expected %s, found '
                        ' %s (%s)' % (
                            j + 1, lesson.lesson_id, lesson.to_id_string()))

                self.fine('  Lesson %s: %s' % (
                    lesson.lesson_id, lesson.lesson_title))

        # find lessons not used by any of the units
        unused_lessons = list(lessons)
        for lesson in used_lessons:
            unused_lessons.remove(lesson)
        for lesson in unused_lessons:
            self.warn('Unused lesson_id %s (%s)' % (
                lesson.lesson_id, lesson.to_id_string()))

        # check all lessons point to known units
        for lesson in lessons:
            has = False
            for unit in units:
                if lesson.unit_id == unit.unit_id:
                    has = True
                    break
            if not has:
                self.error('Lesson has unknown unit_id %s (%s)' % (
                    lesson.unit_id, lesson.to_id_string()))

    def get_activity_as_python(self, unit_id, lesson_id):
        fname = os.path.join(
            os.path.dirname(__file__),
            '../assets/js/activity-%s.%s.js' % (unit_id, lesson_id))
        if not os.path.exists(fname):
            self.error('  Missing activity: %s' % fname)
        else:
            activity = evaluate_javascript_expression_from_file(
                fname, 'activity', Activity().scope, self.error)
            self.verify_activity_instance(activity, fname)
            return activity

    def verify_activities(self, lessons):
        """Loads and verifies all activities."""

        self.info('Loading activities:')
        count = 0
        for lesson in lessons:
            if lesson.lesson_activity == 'yes':
                count += 1
                activity = self.get_activity_as_python(
                    lesson.unit_id, lesson.lesson_id)
                self.export.append('')
                self.encode_activity_json(
                    activity, lesson.unit_id, lesson.lesson_id)

        self.info('Read %s activities' % count)

    def verify_assessment(self, units):
        """Loads and verifies all assessments."""

        self.export.append('')
        self.export.append('assessments = Array();')

        self.info('Loading assessment:')
        count = 0
        for unit in units:
            if unit.type == 'A':
                count += 1
                assessment_name = str(unit.unit_id)
                fname = os.path.join(
                    os.path.dirname(__file__),
                    '../assets/js/assessment-%s.js' % assessment_name)
                if not os.path.exists(fname):
                    self.error('  Missing assessment: %s' % fname)
                else:
                    assessment = evaluate_javascript_expression_from_file(
                        fname, 'assessment', Assessment().scope, self.error)
                    self.verify_assessment_instance(assessment, fname)
                    self.export.append('')
                    self.encode_assessment_json(assessment, assessment_name)

        self.info('Read %s assessments' % count)

    # NB: The exported script needs to define a gcb_regex() wrapper function
    @staticmethod
    def encode_regex(regex_str):
        """Encodes a JavaScript-style regex into a Python gcb_regex call."""
        # parse the regex into the base and modifiers. e.g., for /foo/i
        # base is 'foo' and modifiers is 'i'
        assert regex_str[0] == '/'
        # find the LAST '/' in regex_str (because there might be other
        # escaped '/' characters in the middle of regex_str)
        final_slash_index = regex_str.rfind('/')
        assert final_slash_index > 0

        base = regex_str[1:final_slash_index]
        modifiers = regex_str[final_slash_index + 1:]
        func_str = 'gcb_regex(' + repr(base) + ', ' + repr(modifiers) + ')'
        return func_str

    def encode_activity_json(self, activity_dict, unit_id, lesson_id):
        """Encodes an activity dictionary into JSON."""
        output = []
        for elt in activity_dict['activity']:
            t = type(elt)
            encoded_elt = None

            if t is str:
                encoded_elt = {'type': 'string', 'value': elt}
            elif t is dict:
                qt = elt['questionType']
                encoded_elt = {'type': qt}
                if qt == 'multiple choice':
                    choices = elt['choices']
                    encoded_choices = [[x, y.value, z] for x, y, z in choices]
                    encoded_elt['choices'] = encoded_choices
                elif qt == 'multiple choice group':
                    # everything inside are primitive types that can be encoded
                    elt_copy = dict(elt)
                    del elt_copy['questionType']  # redundant
                    encoded_elt['value'] = elt_copy
                elif qt == 'freetext':
                    for k in elt.keys():
                        if k == 'questionType':
                            continue
                        elif k == 'correctAnswerRegex':
                            encoded_elt[k] = Verifier.encode_regex(elt[k].value)
                        else:
                            # ordinary string
                            encoded_elt[k] = elt[k]
                else:
                    assert False
            else:
                assert False

            assert encoded_elt
            output.append(encoded_elt)

        # N.B.: make sure to get the string quoting right!
        code_str = "units[%s]['lessons'][%s]['activity'] = " % (
            unit_id, lesson_id) + repr(json.dumps(output)) + ';'
        self.export.append(code_str)

        if 'noverify' in activity_dict:
            self.export.append('')
            noverify_code_str = "units[%s]['lessons'][%s]['code'] = " % (
                unit_id, lesson_id) + repr(activity_dict['noverify']) + ';'
            self.export.append(noverify_code_str)

    def encode_assessment_json(self, assessment_dict, assessment_name):
        """Encodes an assessment dictionary into JSON."""
        real_dict = assessment_dict['assessment']

        output = {}
        output['assessmentName'] = real_dict['assessmentName']
        if 'preamble' in real_dict:
            output['preamble'] = real_dict['preamble']
        output['checkAnswers'] = real_dict['checkAnswers'].value

        encoded_questions_list = []
        for elt in real_dict['questionsList']:
            encoded_elt = {}
            encoded_elt['questionHTML'] = elt['questionHTML']
            if 'lesson' in elt:
                encoded_elt['lesson'] = elt['lesson']
            if 'correctAnswerNumeric' in elt:
                encoded_elt['correctAnswerNumeric'] = elt[
                    'correctAnswerNumeric']
            if 'correctAnswerString' in elt:
                encoded_elt['correctAnswerString'] = elt['correctAnswerString']
            if 'correctAnswerRegex' in elt:
                encoded_elt['correctAnswerRegex'] = Verifier.encode_regex(
                    elt['correctAnswerRegex'].value)
            if 'choices' in elt:
                encoded_choices = []
                correct_answer_index = None
                for (ind, e) in enumerate(elt['choices']):
                    if type(e) is str:
                        encoded_choices.append(e)
                    elif e.term_type == CORRECT:
                        encoded_choices.append(e.value)
                        correct_answer_index = ind
                    else:
                        raise Exception("Invalid type in 'choices'")
                encoded_elt['choices'] = encoded_choices
                encoded_elt['correctAnswerIndex'] = correct_answer_index
            encoded_questions_list.append(encoded_elt)
        output['questionsList'] = encoded_questions_list

        # N.B.: make sure to get the string quoting right!
        code_str = 'assessments[\'' + assessment_name + '\'] = ' + repr(
            json.dumps(output)) + ';'
        self.export.append(code_str)

        if 'noverify' in assessment_dict:
            self.export.append('')
            noverify_code_str = ('assessments[\'' + assessment_name +
                                 '\'] = ' + repr(assessment_dict['noverify']) +
                                 ';')
            self.export.append(noverify_code_str)

    def format_parse_log(self):
        return 'Parse log:\n%s' % '\n'.join(self.schema_helper.parse_log)

    def verify_assessment_instance(self, scope, fname):
        """Verifies compliance of assessment with schema."""

        if scope:
            try:
                self.schema_helper.check_instances_match_schema(
                    scope['assessment'], SCHEMA['assessment'], 'assessment')
                self.info('  Verified assessment %s' % fname)
                if OUTPUT_DEBUG_LOG:
                    self.info(self.format_parse_log())
            except SchemaException as e:
                self.error('  Error in assessment %s\n%s' % (
                    fname, self.format_parse_log()))
                raise e
        else:
            self.error('  Unable to evaluate \'assessment =\' in %s' % fname)

    def verify_activity_instance(self, scope, fname):
        """Verifies compliance of activity with schema."""

        if scope:
            try:
                self.schema_helper.check_instances_match_schema(
                    scope['activity'], SCHEMA['activity'], 'activity')
                self.info('  Verified activity %s' % fname)
                if OUTPUT_DEBUG_LOG:
                    self.info(self.format_parse_log())
            except SchemaException as e:
                self.error('  Error in activity %s\n%s' % (
                    fname, self.format_parse_log()))
                raise e
        else:
            self.error('  Unable to evaluate \'activity =\' in %s' % fname)

    def fine(self, x):
        if OUTPUT_FINE_LOG:
            self.echo_func(20, 'FINE: ' + x)

    def info(self, x):
        self.echo_func(20, 'INFO: ' + x)

    def warn(self, x):
        self.warnings += 1
        self.echo_func(30, 'WARNING: ' + x)

    def error(self, x):
        self.errors += 1
        self.echo_func(40, 'ERROR: ' + x)

    def load_and_verify_model(self, echo_func):
        """Loads, parses and verifies all content for a course."""

        self.echo_func = echo_func

        self.info('Started verification in: %s' % __file__)

        unit_file = os.path.join(os.path.dirname(__file__), '../data/unit.csv')
        lesson_file = os.path.join(
            os.path.dirname(__file__), '../data/lesson.csv')

        self.info('Loading units from: %s' % unit_file)
        units = read_objects_from_csv_file(unit_file, UNITS_HEADER, Unit)
        self.info('Read %s units' % len(units))

        self.info('Loading lessons from: %s' % lesson_file)
        lessons = read_objects_from_csv_file(
            lesson_file, LESSONS_HEADER, Lesson)
        self.info('Read %s lessons' % len(lessons))

        self.verify_unit_fields(units)
        self.verify_lesson_fields(lessons)
        self.verify_unit_lesson_relationships(units, lessons)

        try:
            self.verify_activities(lessons)
            self.verify_assessment(units)
        except SchemaException as e:
            self.error(str(e))

        info = (
            'Schema usage statistics: %s'
            'Completed verification: %s warnings, %s errors.' % (
                self.schema_helper.type_stats, self.warnings, self.errors))
        self.info(info)

        return self.warnings, self.errors, info


def run_all_regex_unit_tests():
    """Executes all tests related to regular expressions."""

    # pylint: disable=anomalous-backslash-in-string
    assert escape_javascript_regex(
        'correctAnswerRegex: /site:bls.gov?/i, blah') == (
            'correctAnswerRegex: regex(\"/site:bls.gov?/i\"), blah')
    assert escape_javascript_regex(
        'correctAnswerRegex: /site:http:\/\/www.google.com?q=abc/i, blah') == (
            'correctAnswerRegex: '
            'regex(\"/site:http:\/\/www.google.com?q=abc/i\"), blah')
    assert remove_javascript_multi_line_comment(
        'blah\n/*\ncomment\n*/\nblah') == 'blah\n\nblah'
    assert remove_javascript_multi_line_comment(
        'blah\nblah /*\ncomment\nblah */\nblah') == ('blah\nblah \nblah')
    assert remove_javascript_single_line_comment(
        'blah\n// comment\nblah') == 'blah\n\nblah'
    assert remove_javascript_single_line_comment(
        'blah\nblah http://www.foo.com\nblah') == (
            'blah\nblah http://www.foo.com\nblah')
    assert remove_javascript_single_line_comment(
        'blah\nblah  // comment\nblah') == 'blah\nblah\nblah'
    assert remove_javascript_single_line_comment(
        'blah\nblah  // comment http://www.foo.com\nblah') == (
            'blah\nblah\nblah')
    assert parse_content_marked_no_verify(
        'blah1\n// <gcb-no-verify>\n/blah2\n// </gcb-no-verify>\nblah3')[0] == (
            'blah1\n// \nblah3')
    # pylint: enable=anomalous-backslash-in-string

    assert Verifier.encode_regex('/white?/i') == """gcb_regex('white?', 'i')"""
    assert (Verifier.encode_regex('/jane austen (book|books) \\-price/i') ==
            r"""gcb_regex('jane austen (book|books) \\-price', 'i')""")
    assert (Verifier.encode_regex('/Kozanji|Kozan-ji|Kosanji|Kosan-ji/i') ==
            r"""gcb_regex('Kozanji|Kozan-ji|Kosanji|Kosan-ji', 'i')""")
    assert (Verifier.encode_regex('/Big Time College Sport?/i') ==
            "gcb_regex('Big Time College Sport?', 'i')")
    assert (Verifier.encode_regex('/354\\s*[+]\\s*651/') ==
            r"""gcb_regex('354\\s*[+]\\s*651', '')""")


# pylint: disable=too-many-statements
def run_all_schema_helper_unit_tests():
    """Executes all tests related to schema validation."""

    def assert_same(a, b):
        if a != b:
            raise Exception('Expected:\n  %s\nFound:\n  %s' % (a, b))

    def assert_pass(instances, types, expected_result=None):
        try:
            schema_helper = SchemaHelper()
            result = schema_helper.check_instances_match_schema(
                instances, types, 'test')
            if OUTPUT_DEBUG_LOG:
                print '\n'.join(schema_helper.parse_log)
            if expected_result:
                assert_same(expected_result, result)
        except SchemaException as e:
            if OUTPUT_DEBUG_LOG:
                print str(e)
                print '\n'.join(schema_helper.parse_log)
            raise

    def assert_fails(func):
        try:
            func()
            raise Exception('Expected to fail')
        except SchemaException as e:
            if OUTPUT_DEBUG_LOG:
                print str(e)

    def assert_fail(instances, types):
        assert_fails(lambda: assert_pass(instances, types))

    def create_python_dict_from_js_object(js_object):
        python_str, noverify = convert_javascript_to_python(
            'var x = ' + js_object, 'x')
        ret = evaluate_python_expression_from_text(
            python_str, 'x', Assessment().scope, noverify)
        return ret['x']

    # CSV tests
    units = read_objects_from_csv(
        [
            ['id', 'type', 'now_available'],
            [1, 'U', 'True'],
            [1, 'U', 'False']],
        'id,type,now_available', Unit, converter=UNIT_CSV_TO_DB_CONVERTER)
    assert units[0].now_available
    assert not units[1].now_available

    read_objects_from_csv(
        [['id', 'type'], [1, 'none']], 'id,type', Unit)

    def reader_one():
        return read_objects_from_csv(
            [['id', 'type'], [1, 'none']], 'id,type,title', Unit)
    assert_fails(reader_one)

    def reader_two():
        read_objects_from_csv(
            [['id', 'type', 'title'], [1, 'none']], 'id,type,title', Unit)
    assert_fails(reader_two)

    # context tests
    assert_same(Context().new([]).new(['a']).new(['b', 'c']).format_path(),
                ('//a/b/c'))

    # simple map tests
    assert_pass({'name': 'Bob'}, {'name': STRING})
    assert_fail('foo', 'bar')
    assert_fail({'name': 'Bob'}, {'name': INTEGER})
    assert_fail({'name': 12345}, {'name': STRING})
    assert_fail({'amount': 12345}, {'name': INTEGER})
    assert_fail({'regex': Term(CORRECT)}, {'regex': Term(REGEX)})
    assert_pass({'name': 'Bob'}, {'name': STRING, 'phone': STRING})
    assert_pass({'name': 'Bob'}, {'phone': STRING, 'name': STRING})
    assert_pass({'name': 'Bob'},
                {'phone': STRING, 'name': STRING, 'age': INTEGER})

    # mixed attributes tests
    assert_pass({'colors': ['red', 'blue']}, {'colors': [STRING]})
    assert_pass({'colors': []}, {'colors': [STRING]})
    assert_fail({'colors': {'red': 'blue'}}, {'colors': [STRING]})
    assert_fail({'colors': {'red': 'blue'}}, {'colors': [FLOAT]})
    assert_fail({'colors': ['red', 'blue', 5.5]}, {'colors': [STRING]})

    assert_fail({'colors': ['red', 'blue', {'foo': 'bar'}]},
                {'colors': [STRING]})
    assert_fail({'colors': ['red', 'blue'], 'foo': 'bar'},
                {'colors': [STRING]})

    assert_pass({'colors': ['red', 1]}, {'colors': [[STRING, INTEGER]]})
    assert_fail({'colors': ['red', 'blue']}, {'colors': [[STRING, INTEGER]]})
    assert_fail({'colors': [1, 2, 3]}, {'colors': [[STRING, INTEGER]]})
    assert_fail({'colors': ['red', 1, 5.3]}, {'colors': [[STRING, INTEGER]]})

    assert_pass({'colors': ['red', 'blue']}, {'colors': [STRING]})
    assert_fail({'colors': ['red', 'blue']}, {'colors': [[STRING]]})
    assert_fail({'colors': ['red', ['blue']]}, {'colors': [STRING]})
    assert_fail({'colors': ['red', ['blue', 'green']]}, {'colors': [STRING]})

    # required attribute tests
    assert_pass({'colors': ['red', 5]}, {'colors': [[STRING, INTEGER]]})
    assert_fail({'colors': ['red', 5]}, {'colors': [[INTEGER, STRING]]})
    assert_pass({'colors': ['red', 5]}, {'colors': [STRING, INTEGER]})
    assert_pass({'colors': ['red', 5]}, {'colors': [INTEGER, STRING]})
    assert_fail({'colors': ['red', 5, 'FF0000']},
                {'colors': [[STRING, INTEGER]]})

    # an array and a map of primitive type tests
    assert_pass({'color': {'name': 'red', 'rgb': 'FF0000'}},
                {'color': {'name': STRING, 'rgb': STRING}})
    assert_fail({'color': {'name': 'red', 'rgb': ['FF0000']}},
                {'color': {'name': STRING, 'rgb': STRING}})
    assert_fail({'color': {'name': 'red', 'rgb': 'FF0000'}},
                {'color': {'name': STRING, 'rgb': INTEGER}})
    assert_fail({'color': {'name': 'red', 'rgb': 'FF0000'}},
                {'color': {'name': STRING, 'rgb': {'hex': STRING}}})
    assert_pass({'color': {'name': 'red', 'rgb': 'FF0000'}},
                {'color': {'name': STRING, 'rgb': STRING}})
    assert_pass({'colors':
                 [{'name': 'red', 'rgb': 'FF0000'},
                  {'name': 'blue', 'rgb': '0000FF'}]},
                {'colors': [{'name': STRING, 'rgb': STRING}]})
    assert_fail({'colors':
                 [{'name': 'red', 'rgb': 'FF0000'},
                  {'phone': 'blue', 'rgb': '0000FF'}]},
                {'colors': [{'name': STRING, 'rgb': STRING}]})

    # boolean type tests
    assert_pass({'name': 'Bob', 'active': True},
                {'name': STRING, 'active': BOOLEAN})
    assert_pass({'name': 'Bob', 'active': [5, True, False]},
                {'name': STRING, 'active': [INTEGER, BOOLEAN]})
    assert_pass({'name': 'Bob', 'active': [5, True, 'false']},
                {'name': STRING, 'active': [STRING, INTEGER, BOOLEAN]})
    assert_fail({'name': 'Bob', 'active': [5, True, 'False']},
                {'name': STRING, 'active': [[INTEGER, BOOLEAN]]})

    # optional attribute tests
    assert_pass({'points':
                 [{'x': 1, 'y': 2, 'z': 3}, {'x': 3, 'y': 2, 'z': 1},
                  {'x': 2, 'y': 3, 'z': 1}]},
                {'points': [{'x': INTEGER, 'y': INTEGER, 'z': INTEGER}]})
    assert_pass({'points':
                 [{'x': 1, 'z': 3}, {'x': 3, 'y': 2}, {'y': 3, 'z': 1}]},
                {'points': [{'x': INTEGER, 'y': INTEGER, 'z': INTEGER}]})
    assert_pass({'account':
                 [{'name': 'Bob', 'age': 25, 'active': True}]},
                {'account':
                 [{'age': INTEGER, 'name': STRING, 'active': BOOLEAN}]})

    assert_pass({'account':
                 [{'name': 'Bob', 'active': True}]},
                {'account':
                 [{'age': INTEGER, 'name': STRING, 'active': BOOLEAN}]})

    # nested array tests
    assert_fail({'name': 'Bob', 'active': [5, True, 'false']},
                {'name': STRING, 'active': [[BOOLEAN]]})
    assert_fail({'name': 'Bob', 'active': [True]},
                {'name': STRING, 'active': [[STRING]]})
    assert_pass({'name': 'Bob', 'active': ['true']},
                {'name': STRING, 'active': [[STRING]]})
    assert_pass({'name': 'flowers', 'price': ['USD', 9.99]},
                {'name': STRING, 'price': [[STRING, FLOAT]]})
    assert_pass({'name': 'flowers', 'price':
                 [['USD', 9.99], ['CAD', 11.79], ['RUB', 250.23]]},
                {'name': STRING, 'price': [[STRING, FLOAT]]})

    # selector tests
    assert_pass({'likes': [{'state': 'CA', 'food': 'cheese'},
                           {'state': 'NY', 'drink': 'wine'}]},
                {'likes': [{'state': 'CA', 'food': STRING},
                           {'state': 'NY', 'drink': STRING}]})

    assert_pass({'likes': [{'state': 'CA', 'food': 'cheese'},
                           {'state': 'CA', 'food': 'nuts'}]},
                {'likes': [{'state': 'CA', 'food': STRING},
                           {'state': 'NY', 'drink': STRING}]})

    assert_fail({'likes': {'state': 'CA', 'drink': 'cheese'}},
                {'likes': [{'state': 'CA', 'food': STRING},
                           {'state': 'NY', 'drink': STRING}]})

    # creating from dict tests
    assert_same(create_python_dict_from_js_object('{"active": true}'),
                {'active': Term(BOOLEAN, True)})
    assert_same(create_python_dict_from_js_object(
        '{"a": correct("hello world")}'),
                {'a': Term(CORRECT, 'hello world')})
    assert_same(create_python_dict_from_js_object(
        '{correctAnswerRegex: /hello/i}'),
                {'correctAnswerRegex': Term(REGEX, '/hello/i')})


def run_example_activity_tests():
    """Parses and validates example activity file."""
    fname = os.path.join(
        os.path.dirname(__file__), '../assets/js/activity-examples.js')
    if not os.path.exists(fname):
        raise Exception('Missing file: %s', fname)

    verifier = Verifier()
    verifier.echo_func = echo
    activity = evaluate_javascript_expression_from_file(
        fname, 'activity', Activity().scope, verifier.echo_func)
    verifier.verify_activity_instance(activity, fname)


def test_exec():
    """This test shows that exec/compile are explitable, thus not safe."""
    content = """
foo = [
    c for c in ().__class__.__base__.__subclasses__()
    if c.__name__ == 'catch_warnings'
][0]()._module.__builtins__
"""
    restricted_scope = {}
    restricted_scope.update({'__builtins__': {}})
    code = compile(content, '<string>', 'exec')
    exec code in restricted_scope  # pylint: disable=exec-used
    assert 'isinstance' in restricted_scope.get('foo')


def test_sample_assets():
    """Test assets shipped with the sample course."""
    _, _, output = Verifier().load_and_verify_model(echo)
    if (
            'Schema usage statistics: {'
            '\'REGEX\': 19, \'STRING\': 415, \'NUMBER\': 1, '
            '\'BOOLEAN\': 81, \'dict\': 73, \'str\': 41, \'INTEGER\': 9, '
            '\'CORRECT\': 9}' not in output
            or 'Completed verification: 0 warnings, 0 errors.' not in output):
        raise Exception('Sample course verification failed.\n%s' % output)


def run_all_unit_tests():
    """Runs all unit tests in this module."""
    global parse_content  # pylint: disable=global-statement
    original = parse_content
    try:
        parse_content = legacy_eval_python_expression_for_test

        run_all_regex_unit_tests()
        run_all_schema_helper_unit_tests()
        run_example_activity_tests()
        test_exec()
        test_sample_assets()
    finally:
        parse_content = original


if __name__ == '__main__':
    run_all_unit_tests()
