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
import os
import re
import sys


BOOLEAN = object()
STRING = object()
FLOAT = object()
INTEGER = object()
CORRECT = object()
REGEX = object()

SCHEMA = {
    "assessment": {
        "assessmentName": STRING,
        "preamble": STRING,
        "checkAnswers": BOOLEAN,
        "questionsList": [{
            "questionHTML": STRING,
            "lesson": STRING,
            "choices": [STRING, CORRECT],
            "correctAnswerNumeric": FLOAT,
            "correctAnswerString": STRING,
            "correctAnswerRegex": REGEX}]
    }, "activity": [
        STRING,
        {
            "questionType": "multiple choice",
            "choices": [[STRING, BOOLEAN, STRING]]
        }, {
            "questionType": "multiple choice group",
            "questionsList": [{
                "questionHTML": STRING,
                "choices": [STRING],
                "correctIndex": INTEGER}],
            "allCorrectOutput": STRING,
            "someIncorrectOutput": STRING
        }, {
            "questionType": "freetext",
            "correctAnswerRegex": REGEX,
            "correctAnswerOutput": STRING,
            "incorrectAnswerOutput": STRING,
            "showAnswerOutput": STRING,
            "showAnswerPrompt": STRING,
            "outputHeight": STRING
        }]}

UNITS_HEADER = (
    "id,type,unit_id,title,release_date,now_available")
LESSONS_HEADER = (
    "unit_id,unit_title,lesson_id,lesson_title,lesson_activity,"
    "lesson_activity_name,lesson_notes,lesson_video_id,lesson_objectives")

NO_VERIFY_TAG_NAME_OPEN = "<gcb-no-verify>"
NO_VERIFY_TAG_NAME_CLOSE = "</gcb-no-verify>"

OUTPUT_FINE_LOG = False
OUTPUT_DEBUG_LOG = False


class SchemaException(Exception):
  """A class to represent a schema error."""

  def FormatPrimitiveValueName(self, name):
    if name == REGEX: return "REGEX(...)"
    if name == CORRECT: return "CORRECT(...)"
    if name == BOOLEAN: return "BOOLEAN"
    return name

  def FormatPrimitiveTypeName(self, name):
    if name == BOOLEAN: return "BOOLEAN"
    if name == REGEX: return "REGEX(...)"
    if name == CORRECT: return "CORRECT(...)"
    if name == STRING or isinstance(name, str): return "STRING"
    if name == FLOAT: return "FLOAT"
    if name == INTEGER: return "INTEGER"
    if isinstance(name, dict): return "{...}"
    if isinstance(name, list): return "[...]"
    return "Unknown type name '%s'" % name.__class__.__name__

  def FormatTypeNames(self, names):
    if isinstance(names, list):
      captions = []
      for name in names:
        captions.append(self.FormatPrimitiveTypeName(name))
      return captions
    else:
      return self.FormatPrimitiveTypeName(names)

  def FormatTypeName(self, types):
    if isinstance(types, dict):
      return self.FormatTypeNames(types.keys())
    if isinstance(types, list):
      return self.FormatTypeNames(types)
    return self.FormatTypeNames([types])

  def __init__(self, message, value=None, types=None, path=None):
    prefix = ""
    if path: prefix = "Error at %s\n" % path

    if types:
      if value:
        message = prefix + message % (
            self.FormatPrimitiveValueName(value), self.FormatTypeNames(types))
      else:
        message = prefix + message % self.FormatTypeNames(types)
    else:
      if value:
        message = prefix + message % self.FormatPrimitiveValueName(value)
      else:
        message = prefix + message

    super(SchemaException, self).__init__(message)


class Context(object):
  """"A class that manages a stack of traversal contexts."""

  def __init__(self):
    self.parent = None
    self.path = ["/"]

  def New(self, names):
    """"Derives a new context from the current one."""

    context = Context()
    context.parent = self
    context.path = list(self.path)
    if names:
      if isinstance(names, list):
        for name in names:
          if name:
            context.path.append("/" + "%s" % name)
      else:
        context.path.append("/" + "%s" % names)
    return context

  def FormatPath(self):
    """"Formats the canonical name of this context."""

    return "".join(self.path)


class SchemaHelper(object):
  """A class that knows how to apply the schema."""

  def __init__(self):
    self.type_stats = {}

  def VisitElement(self, atype, value, context, is_terminal=True):
    """"This method is called once for each schema element being traversed."""

    if self.type_stats.has_key(atype):
      count = self.type_stats[atype]
    else:
      count = 0
    self.type_stats[atype] = count + 1

    if is_terminal:
      self.parse_log.append("  TERMINAL: %s %s = %s" % (
          atype, context.FormatPath(), value))
    else:
      self.parse_log.append("  NON-TERMINAL: %s %s" % (
          atype, context.FormatPath()))

  def ExtractAllTermsToDepth(self, key, values, type_map):
    """Walks schema recursively and creates a list of all known terms."""

    """Walks schema type map recursively to depth and creates a list of all
    possible {key: value} pairs. The latter is the list of all non-terminal
    and terminal terms allowed in the schema. The list of terms from this
    method can be bound to an execution context for evaluating whether a given
    instance's map complies with the schema."""

    if key: type_map.update({key: key})

    if values == REGEX:
      type_map.update({"regex": lambda x: REGEX})
      return

    if values == CORRECT:
      type_map.update({"correct": lambda x: CORRECT})
      return

    if values == BOOLEAN:
      type_map.update({"true": BOOLEAN, "false": BOOLEAN})
      return

    if values == STRING or values == INTEGER:
      return

    if isinstance(values, dict):
      for new_key, new_value in values.items():
        self.ExtractAllTermsToDepth(new_key, new_value, type_map)
      return

    if isinstance(values, list):
      for new_value in values:
        self.ExtractAllTermsToDepth(None, new_value, type_map)
      return

  def FindSelectors(self, type_map):
    """Finds all type selectors."""

    """Finds all elements in the type map where both a key and a value are
    strings. These elements are used to find one specific type map among
    several alternative type maps."""

    selector = {}
    for akey, avalue in type_map.items():
      if isinstance(akey, str) and isinstance(avalue, str):
        selector.update({akey: avalue})
    return selector

  def FindCompatibleDict(self, value_map, type_map, context):
    """Find the type map most compatible with the value map."""

    """"A value map is considered compatible with a type map when former
    contains the same key names and the value types as the type map."""

    # special case when we have just one type; check name and type are the same
    if len(type_map) == 1:
      for value_key in value_map.keys():
        for key in type_map[0].keys():
          if value_key == key: return key, type_map[0]
      raise SchemaException(
          "Expected: '%s'\nfound: %s", type_map[0].keys()[0], value_map)

    # case when we have several types to choose from
    for adict in type_map:
      dict_selector = self.FindSelectors(adict)
      for akey, avalue in dict_selector.items():
        if value_map[akey] == avalue: return akey, adict
    return None, None

  def CheckSingleValueMatchesType(self, value, atype, context):
    """Checks if a single value matches a specific (primitive) type."""

    if atype == BOOLEAN:
      if (value == "True") or (value == "False") or (value == "true") or (
          value == "false") or (isinstance(value, bool)) or value == BOOLEAN:
        self.VisitElement("BOOLEAN", value, context)
        return True
      else:
        raise SchemaException("Expected: 'true' or 'false'\nfound: %s", value)
    if isinstance(atype, str):
      if isinstance(value, str):
        self.VisitElement("str", value, context)
        return True
      else:
        raise SchemaException("Expected: 'string'\nfound: %s", value)
    if atype == STRING:
      if isinstance(value, str):
        self.VisitElement("STRING", value, context)
        return True
      else:
        raise SchemaException("Expected: 'string'\nfound: %s", value)
    if atype == REGEX and value == REGEX:
      self.VisitElement("REGEX", value, context)
      return True
    if atype == CORRECT and value == CORRECT:
      self.VisitElement("CORRECT", value, context)
      return True
    if atype == FLOAT:
      if IsNumber(value):
        self.VisitElement("NUMBER", value, context)
        return True
      else:
        raise SchemaException("Expected: 'number'\nfound: %s", value)
    if atype == INTEGER:
      if IsInteger(value):
        self.VisitElement("INTEGER", value, context)
        return True
      else:
        raise SchemaException(
            "Expected: 'integer'\nfound: %s", value, path=context.FormatPath())
    raise SchemaException(
        "Unexpected value '%s'\n"
        "for type %s", value, atype, path=context.FormatPath())

  def CheckValueListMatchesType(self, value, atype, context):
    """Checks if all items in value list match a specific type."""

    for value_item in value:
      found = False
      for atype_item in atype:
        if isinstance(atype_item, list):
          for atype_item_item in atype_item:
            if self.DoesValueMatchType(value_item, atype_item_item, context):
              found = True
              break
        else:
          if self.DoesValueMatchType(value_item, atype_item, context):
            found = True
            break
      if not found:
        raise SchemaException("Expected: '%s'\nfound: %s", atype, value)
    return True

  def CheckValueMatchesType(self, value, atype, context):
    """Checks if single value or a list of values match a specific type."""

    if isinstance(atype, list) and isinstance(value, list):
      return self.CheckValueListMatchesType(value, atype, context)
    else:
      return self.CheckSingleValueMatchesType(value, atype, context)

  def DoesValueMatchType(self, value, atype, context):
    """Same as other method, but does not throw an exception."""

    try:
      return self.CheckValueMatchesType(value, atype, context)
    except SchemaException:
      return False

  def DoesValueMatchesOneOfTypes(self, value, types, context):
    """Checks if a value matches to one of the types in the list."""

    type_names = None
    if isinstance(types, list):
      type_names = types
    if type_names:
      for i in range(0, len(type_names)):
        if self.DoesValueMatchType(value, type_names[i], context):
          return True

    return False

  def DoesValueMatchMapOfType(self, value, types, context):
    """Checks if value matches any variation of {...} type."""

    # find all possible map types
    maps = []
    for atype in types:
      if isinstance(atype, dict): maps.append(atype)
    if len(maps) == 0 and isinstance(types, dict):
      maps.append(types)

    # check if the structure of value matches one of the maps
    if isinstance(value, dict):
      aname, adict = self.FindCompatibleDict(value, maps, context)
      if adict:
        self.VisitElement("dict", value, context.New(aname), False)
        for akey, avalue in value.items():
          if not adict.has_key(akey):
            raise SchemaException(
                "Unknown term '%s'", akey, path=context.FormatPath())
          self.CheckValueOfValidType(
              avalue, adict[akey], context.New([aname, akey]))
        return True
      raise SchemaException(
          "The value:\n  %s\n"
          "is incompatible with expected type(s):\n  %s",
          value, types, path=context.FormatPath())

    return False

  def FormatNameWithIndex(self, alist, aindex):
    """custom function to format a context name with an array element index."""

    if len(alist) == 1:
      return ""
    else:
      return "[%s]" % aindex

  def DoesValueMatchListOfTypesInOrder(self, value, types, context, target):
    """Iterates the value and the types in given order and checks for match."""

    all_values_are_lists = True
    for avalue in value:
      if not isinstance(avalue, list):
        all_values_are_lists = False

    if all_values_are_lists:
      for i in range(0, len(value)):
        self.CheckValueOfValidType(value[i], types, context.New(
            self.FormatNameWithIndex(value, i)), True)
    else:
      if len(target) != len(value):
        raise SchemaException(
            "Expected: '%s' values\n" + "found: %s." % value,
            len(target), path=context.FormatPath())
      for i in range(0, len(value)):
        self.CheckValueOfValidType(value[i], target[i], context.New(
            self.FormatNameWithIndex(value, i)))

    return True

  def DoesValueMatchListOfTypesAnyOrder(self, value, types, context, lists):
    """Iterates the value and types and checks if they match in any order."""

    target = lists
    if len(target) == 0:
      if not isinstance(types, list):
        raise SchemaException(
            "Unsupported type %s",
            None, types, path=context.FormatPath())
      target = types

    for i in range(0, len(value)):
      found = False
      for atarget in target:
        try:
          self.CheckValueOfValidType(value[i], atarget, context.New(
              self.FormatNameWithIndex(value, i)))
          found = True
          break
        except:
          continue

      if not found:
        raise SchemaException(
            "The value:\n  %s\n"
            "is incompatible with expected type(s):\n  %s",
            value, types, path=context.FormatPath())
    return True

  def DoesValueMatchListOfType(self, value, types, context, in_order):
    """Checks if a value matches a variation of [...] type."""

    """Extra argument controls whether matching must be done in a specific or
    in any order. A specific  order is demanded by [[...]]] construct,
    i.e. [[STRING, INTEGER, BOOLEAN]], while sub elements inside {...} and
    [...] can be matched in any order."""

    # prepare a list of list types
    lists = []
    for atype in types:
      if isinstance(atype, list): lists.append(atype)
    if len(lists) > 1:
      raise SchemaException(
          "Unable to validate types with multiple alternative "
          "lists %s", None, types, path=context.FormatPath())

    if isinstance(value, list):
      if len(lists) > 1:
        raise SchemaException(
            "Allowed at most one list\nfound: %s.",
            None, types, path=context.FormatPath())

      # determine if list is in order or not as hinted by double array [[..]];
      # [STRING, NUMBER] is in any order, but [[STRING, NUMBER]] demands order
      ordered = len(lists) == 1 and isinstance(types, list)
      if in_order or ordered:
        return self.DoesValueMatchListOfTypesInOrder(
            value, types, context, lists[0])
      else:
        return self.DoesValueMatchListOfTypesAnyOrder(
            value, types, context, lists)

    return False

  def CheckValueOfValidType(self, value, types, context, in_order=None):
    """Check if a value matches any of the given types."""

    if not (isinstance(types, list) or isinstance(types, dict)):
      self.CheckValueMatchesType(value, types, context)
      return
    if self.DoesValueMatchListOfType(value, types, context, in_order): return
    if self.DoesValueMatchMapOfType(value, types, context): return
    if self.DoesValueMatchesOneOfTypes(value, types, context): return

    raise SchemaException("Unknown type %s", value, path=context.FormatPath())

  def CheckInstancesMatchSchema(self, values, types, name):
    """Recursively decomposes 'values' to see if they match schema (types)."""

    self.parse_log = []
    context = Context().New(name)
    self.parse_log.append("  ROOT %s" % context.FormatPath())

    # handle {..} containers
    if isinstance(types, dict):
      if not isinstance(values, dict):
        raise SchemaException("Error at '/': expected {...}, found %s" % (
            values.__class_.__name__))
      self.CheckValueOfValidType(values, types, context.New([]))
      return

    # handle [...] containers
    if isinstance(types, list):
      if not isinstance(values, list):
        raise SchemaException("Error at '/': expected [...], found %s" % (
            values.__class_.__name__))
      for i in range(0, len(values)):
        self.CheckValueOfValidType(
            values[i], types, context.New("[%s]" % i))
      return

    raise SchemaException(
        "Expected an array or a dictionary.", None, path=context.FormatPath())


class Unit(object):
  """A class to represent a Unit."""

  id = 0
  type = ""
  unit_id = ""
  title = ""
  release_date = ""
  now_available = False


class Lesson(object):
  """A class to represent a Lesson."""

  unit_id = 0
  unit_title = ""
  lesson_id = 0
  lesson_title = ""
  lesson_activity = ""
  lesson_activity_name = ""
  lesson_notes = ""
  lesson_video_id = ""
  lesson_objectives = ""

  def ToIdString(self):
    return "%s.%s.%s" % (self.unit_id, self.lesson_id, self.lesson_title)


class Assessment(object):
  """A class to represent a Assessment."""

  def __init__(self):
    self.scope = {}
    SchemaHelper().ExtractAllTermsToDepth(
        "assessment", SCHEMA["assessment"], self.scope)


class Activity(object):
  """A class to represent a Activity."""

  def __init__(self):
    self.scope = {}
    SchemaHelper().ExtractAllTermsToDepth(
        "activity", SCHEMA["activity"], self.scope)


def Echo(x):
  print x


def IsInteger(s):
  try:
    return int(s) == float(s)
  except ValueError:
    return False


def IsBoolean(s):
  try:
    return s == "True" or s == "False"
  except ValueError:
    return False


def IsNumber(s):
  try:
    float(s)
    return True
  except ValueError:
    return False


def IsOneOf(value, values):
  for current in values:
    if value == current:
      return True
  return False


def TextToLineNumberedText(text):
  """Adds line numbers to the provided text."""

  lines = text.split("\n")
  results = []
  i = 1
  for line in lines:
    results.append(str(i) + ": " + line)
    i += 1
  return "\n  ".join(results)


def SetObjectAttributes(target_object, names, values):
  """Sets object attributes from provided values."""

  if len(names) != len(values):
    raise SchemaException(
        "The number of elements must match: %s and %s" % (names, values))
  for i in range(0, len(names)):
    if IsInteger(values[i]):
      setattr(target_object, names[i], int(values[i]))
      continue
    if IsBoolean(values[i]):
      setattr(target_object, names[i], bool(values[i]))
      continue
    setattr(target_object, names[i], values[i])


def ReadObjectsFromCsvFile(fname, header, new_object):
  return ReadObjectsFromCsv(csv.reader(open(fname)), header, new_object)


def ReadObjectsFromCsv(value_rows, header, new_object):
  values = []
  for row in value_rows:
    if len(row) == 0:
      continue
    values.append(row)
  names = header.split(",")

  if names != values[0]:
    raise SchemaException(
        "Error reading CSV header.\n  "
        "Header row had %s element(s): %s\n  "
        "Expected header row with %s element(s): %s" % (
            len(values[0]), values[0], len(names), names))

  items = []
  for i in range (1, len(values)):
    if len(names) != len(values[i]):
      raise SchemaException(
          "Error reading CSV data row.\n  "
          "Row #%s had %s element(s): %s\n  "
          "Expected %s element(s): %s" % (
              i, len(values[i]), values[i], len(names), names))

    item = new_object()
    SetObjectAttributes(item, names, values[i])
    items.append(item)
  return items


def EscapeJavascriptRegex(text):
  return re.sub(r"([:][ ]*)([/])(.*)([/][ismx]*)", r': regex("\2\3\4")', text)


def RemoveJavaScriptSingleLineComment(text):
  text = re.sub(re.compile("^(.*?)[ ]+//(.*)$", re.MULTILINE), r"\1", text)
  text = re.sub(re.compile("^//(.*)$", re.MULTILINE), r"", text)
  return text


def RemoveJavaScriptMultiLineComment(text):
  return re.sub(re.compile("/\*(.*)\*/", re.MULTILINE + re.DOTALL), r"", text)


def RemoveContentMarkedNoVerify(content):
  """Removes content that should not be verified."""

  """If you have any free-form JavaScript in the activity file, you need
  to place it between //<gcb-no-verify> ... //</gcb-no-verify> tags
  so that the verifier can selectively ignore it."""

  pattern = re.compile("(%s)(.*)(%s)" % (
      NO_VERIFY_TAG_NAME_OPEN, NO_VERIFY_TAG_NAME_CLOSE), re.DOTALL)
  return re.sub(pattern, "", content)


def ConvertJavaScriptToPython(content, root_name):
  """Removes JavaScript specific syntactic constructs."""

  """Reads the content and removes JavaScript comments, var's, and escapes
  regular expressions."""

  content = RemoveContentMarkedNoVerify(content)
  content = RemoveJavaScriptMultiLineComment(content)
  content = RemoveJavaScriptSingleLineComment(content)
  content = content.replace("var %s = " % root_name, "%s = " % root_name)
  content = EscapeJavascriptRegex(content)
  return content


def ConvertJavaScriptFileToPython(fname, root_name):
  return ConvertJavaScriptToPython(
      "".join(open(fname, "r").readlines()), root_name)


def EvaluatePythonExpressionFromText(content, root_name, scope):
  """Compiles and evaluates a Python script in a restricted environment."""

  """First compiles and then evaluates a Python script text in a restricted
  environment using provided bindings. Returns the resulting bindings if
  evaluation completed."""

  # create a new execution scope that has only the schema terms defined;
  # remove all other languages constructs including __builtins__
  restricted_scope = {}
  restricted_scope.update(scope)
  restricted_scope.update({"__builtins__": {}})
  code = compile(content, "<string>", "exec")
  exec code in restricted_scope
  if not restricted_scope[root_name]:
    raise Exception("Unable to find '%s'" % root_name)
  return restricted_scope


def EvaluateJavaScriptExpressionFromFile(fname, root_name, scope, error):
  content = ConvertJavaScriptFileToPython(fname, root_name)
  try:
    return EvaluatePythonExpressionFromText(content, root_name, scope)
  except:
    error("Unable to parse %s in file %s\n  %s" % (
        root_name, fname, TextToLineNumberedText(content)))
    for message in sys.exc_info():
      error(str(message))


class Verifier(object):
  """A class that verifies all course content."""

  """A class that knows how to verify Units, Lessons, Assessment and Activities,
  and understands their relationships."""

  def __init__(self):
    self.schema_helper = SchemaHelper()
    self.errors = 0
    self.warnings = 0

  def VerifyUnitFields(self, units):
    for unit in units:
      if not IsOneOf(unit.now_available, [True, False]):
        self.error("Bad now_available '%s' for unit id %s; expected 'True' or 'False'" % (
            unit.now_available, unit.id))

      if not IsOneOf(unit.type, ["U", "A", "O"]):
        self.error("Bad type '%s' for unit id %s; expected 'U', 'A', or 'O'" % (
            unit.type, unit.id))

      if unit.type == "A":
        if not IsOneOf(unit.unit_id, ("Pre", "Mid", "Fin")):
          self.error(
              "Bad unit_id '%s'; expected 'Pre', 'Mid' or 'Fin' for unit id %s"
              % (unit.unit_id, unit.id))

      if unit.type == "U":
        if not IsInteger(unit.unit_id):
          self.error("Expected integer unit_id, found %s in unit id %s" % (
              unit.unit_id, unit.id))

  def VerifyLessonFields(self, lessons):
    for lesson in lessons:
      if not IsOneOf(lesson.lesson_activity, ["yes", ""]):
        self.error("Bad lesson_activity '%s' for lesson_id %s" %
                   (lesson.lesson_activity, lesson.lesson_id))

  def VerifyUnitLessonRelationships(self, units, lessons):
    """Checks how units relate to lessons and otherwise."""

    """Checks that each lesson points to a valid unit and all lessons are used
    by one of the units."""

    used_lessons = []
    units.sort(key=lambda x: x.id)
    #for unit in units:
    for i in range(0, len(units)):
      unit = units[i]

      # check that unit ids are 1-based and sequential
      if unit.id != i + 1:
        self.error("Unit out of order: %s" % (unit.id))

      # get the list of lessons for each unit
      self.fine("Unit %s: %s" % (unit.id, unit.title))
      unit_lessons = []
      for lesson in lessons:
        if lesson.unit_id == unit.unit_id:
          unit_lessons.append(lesson)
          used_lessons.append(lesson)

      # inspect all lessons for the current unit
      unit_lessons.sort(key=lambda x: x.lesson_id)
      for j in range(0, len(unit_lessons)):
        lesson = unit_lessons[j]

        # check that lesson_ids are 1-based and sequential
        if lesson.lesson_id != j + 1:
          self.warn(
              "Lesson lesson_id is out of order: expected %s, found %s (%s)"
              % (j + 1, lesson.lesson_id, lesson.ToIdString()))

        self.fine("  Lesson %s: %s" % (lesson.lesson_id, lesson.lesson_title))

    # find lessons not used by any of the units
    unused_lessons = list(lessons)
    for lesson in used_lessons:
      unused_lessons.remove(lesson)
    for lesson in unused_lessons:
      self.warn("Unused lesson_id %s (%s)" % (
          lesson.lesson_id, lesson.ToIdString()))

    # check all lessons point to known units
    for lesson in lessons:
      has = False
      for unit in units:
        if lesson.unit_id == unit.unit_id:
          has = True
          break
      if not has:
        self.error("Lesson has unknown unit_id %s (%s)" %
                   (lesson.unit_id, lesson.ToIdString()))

  def VerifyActivities(self, lessons):
    """Loads and verifies all activities."""

    self.info("Loading activities:")
    count = 0
    for lesson in lessons:
      if lesson.lesson_activity == "yes":
        count += 1
        fname = os.path.join(
            os.path.dirname(__file__),
            "../assets/js/activity-" + str(lesson.unit_id) + "." +
            str(lesson.lesson_id) + ".js")
        if not os.path.exists(fname):
          self.error("  Missing activity: %s" % fname)
        else:
          activity = EvaluateJavaScriptExpressionFromFile(
              fname, "activity", Activity().scope, self.error)
          self.VerifyActivityInstance(activity, fname)

    self.info("Read %s activities" % count)

  def VerifyAssessment(self, units):
    """Loads and verifies all assessments."""

    self.info("Loading assessment:")
    count = 0
    for unit in units:
      if unit.type == "A":
        count += 1
        fname = os.path.join(
            os.path.dirname(__file__),
            "../assets/js/assessment-" + str(unit.unit_id) + ".js")
        if not os.path.exists(fname):
          self.error("  Missing assessment: %s" % fname)
        else:
          assessment = EvaluateJavaScriptExpressionFromFile(
              fname, "assessment", Assessment().scope, self.error)
          self.VerifyAssessmentInstance(assessment, fname)

    self.info("Read %s assessments" % count)

  def FormatParseLog(self):
    return "Parse log:\n%s" % "\n".join(self.schema_helper.parse_log)

  def VerifyAssessmentInstance(self, scope, fname):
    """Verifies compliance of assessment with schema."""

    if scope:
      try:
        self.schema_helper.CheckInstancesMatchSchema(
            scope["assessment"], SCHEMA["assessment"], "assessment")
        self.info("  Verified assessment %s" % fname)
        if OUTPUT_DEBUG_LOG: self.info(self.FormatParseLog())
      except SchemaException as e:
        self.error("  Error in assessment %s\n%s" % (
            fname, self.FormatParseLog()))
        raise e
    else:
      self.error("  Unable to evaluate 'assessment =' in %s" % fname)

  def VerifyActivityInstance(self, scope, fname):
    """Verifies compliance of activity with schema."""

    if scope:
      try:
        self.schema_helper.CheckInstancesMatchSchema(
            scope["activity"], SCHEMA["activity"], "activity")
        self.info("  Verified activity %s" % fname)
        if OUTPUT_DEBUG_LOG: self.info(self.FormatParseLog())
      except SchemaException as e:
        self.error("  Error in activity %s\n%s" % (
            fname, self.FormatParseLog()))
        raise e
    else:
      self.error("  Unable to evaluate 'activity =' in %s" % fname)

  def fine(self, x):
    if OUTPUT_FINE_LOG:
      self.echo_func("FINE: " + x)

  def info(self, x):
    self.echo_func("INFO: " + x)

  def warn(self, x):
    self.warnings += 1
    self.echo_func("WARNING: " + x)

  def error(self, x):
    self.errors += 1
    self.echo_func("ERROR: " + x)

  def LoadAndVerifyModel(self, echo_func):
    """Loads, parses and verifies all content for a course."""

    self.echo_func = echo_func

    self.info("Started verification in: %s" % __file__)

    unit_file = os.path.join(os.path.dirname(__file__), "../data/unit.csv")
    lesson_file = os.path.join(os.path.dirname(__file__), "../data/lesson.csv")

    self.info("Loading units from: %s" % unit_file)
    units = ReadObjectsFromCsvFile(unit_file, UNITS_HEADER, lambda: Unit())
    self.info("Read %s units" % len(units))

    self.info("Loading lessons from: %s" % lesson_file)
    lessons = ReadObjectsFromCsvFile(lesson_file, LESSONS_HEADER, lambda: Lesson())
    self.info("Read %s lessons" % len(lessons))

    self.VerifyUnitFields(units)
    self.VerifyLessonFields(lessons)
    self.VerifyUnitLessonRelationships(units, lessons)

    try:
      self.VerifyActivities(lessons)
      self.VerifyAssessment(units)
    except SchemaException as e:
      self.error(str(e))

    self.info("Schema usage statistics: %s" % self.schema_helper.type_stats)
    self.info("Completed verification: %s warnings, %s errors." %
              (self.warnings, self.errors))

    return self.errors


def RunAllRegexUnitTests():
  assert EscapeJavascriptRegex(
      "blah regex: /site:bls.gov?/i, blah") == (
          "blah regex: regex(\"/site:bls.gov?/i\"), blah")
  assert EscapeJavascriptRegex(
      "blah regex: /site:http:\/\/www.google.com?q=abc/i, blah") == (
          "blah regex: regex(\"/site:http:\/\/www.google.com?q=abc/i\"), blah")
  assert RemoveJavaScriptMultiLineComment(
      "blah\n/*\ncomment\n*/\nblah") == "blah\n\nblah"
  assert RemoveJavaScriptMultiLineComment(
      "blah\nblah /*\ncomment\nblah */\nblah") == (
          "blah\nblah \nblah")
  assert RemoveJavaScriptSingleLineComment(
      "blah\n// comment\nblah") == "blah\n\nblah"
  assert RemoveJavaScriptSingleLineComment(
      "blah\nblah http://www.foo.com\nblah") == (
          "blah\nblah http://www.foo.com\nblah")
  assert RemoveJavaScriptSingleLineComment(
      "blah\nblah  // comment\nblah") == "blah\nblah\nblah"
  assert RemoveJavaScriptSingleLineComment(
      "blah\nblah  // comment http://www.foo.com\nblah") == "blah\nblah\nblah"
  assert RemoveContentMarkedNoVerify(
      "blah1\n// <gcb-no-verify>/blah2\n// </gcb-no-verify>\nblah3") == (
          "blah1\n// \nblah3")


def RunAllSchemaHelperUnitTests():
  def AssertSame(a, b):
    if a != b:
      raise Exception("Expected:\n  %s\nFound:\n  %s" % (a, b))

  def AssertPass(instances, types, expected_result=None):
    try:
      schema_helper = SchemaHelper()
      result = schema_helper.CheckInstancesMatchSchema(instances, types, "test")
      if OUTPUT_DEBUG_LOG: print "\n".join(schema_helper.parse_log)
      if expected_result: AssertSame(expected_result, result)
    except SchemaException as e:
      if OUTPUT_DEBUG_LOG:
        print str(e)
        print "\n".join(schema_helper.parse_log)
      raise

  def AssertFails(func):
    try:
      func()
      raise Exception("Expected to fail")
    except SchemaException as e:
      if OUTPUT_DEBUG_LOG:
        print str(e)
      pass

  def AssertFail(instances, types):
    AssertFails(lambda: AssertPass(instances, types))

  # CSV tests
  ReadObjectsFromCsv([["id", "type"], [1, "none"]], "id,type", lambda: Unit())
  AssertFails(lambda: ReadObjectsFromCsv(
      [["id", "type"], [1, "none"]], "id,type,title", lambda: Unit()))
  AssertFails(lambda: ReadObjectsFromCsv(
      [["id", "type", "title"], [1, "none"]], "id,type,title", lambda: Unit()))

  # context tests
  AssertSame(
      Context().New([]).New(["a"]).New(["b", "c"]).FormatPath(), ("//a/b/c"))

  # simple map tests
  AssertPass({"name": "Bob"}, {"name": STRING}, None)
  AssertFail("foo", "bar")
  AssertFail({"name": "Bob"}, {"name": INTEGER})
  AssertFail({"name": 12345}, {"name": STRING})
  AssertFail({"amount": 12345}, {"name": INTEGER})
  AssertFail({"regex": CORRECT}, {"regex": REGEX})
  AssertPass({"name": "Bob"}, {"name": STRING, "phone": STRING})
  AssertPass({"name": "Bob"}, {"phone": STRING, "name": STRING})
  AssertPass({"name": "Bob"},
             {"phone": STRING, "name": STRING, "age": INTEGER})

  # mixed attributes tests
  AssertPass({"colors": ["red", "blue"]}, {"colors": [STRING]})
  AssertPass({"colors": []}, {"colors": [STRING]})
  AssertFail({"colors": {"red": "blue"}}, {"colors": [STRING]})
  AssertFail({"colors": {"red": "blue"}}, {"colors": [FLOAT]})
  AssertFail({"colors": ["red", "blue", 5.5]}, {"colors": [STRING]})

  AssertFail({"colors": ["red", "blue", {"foo": "bar"}]}, {"colors": [STRING]})
  AssertFail({"colors": ["red", "blue"], "foo": "bar"}, {"colors": [STRING]})

  AssertPass({"colors": ["red", 1]}, {"colors": [[STRING, INTEGER]]})
  AssertFail({"colors": ["red", "blue"]}, {"colors": [[STRING, INTEGER]]})
  AssertFail({"colors": [1, 2, 3]}, {"colors": [[STRING, INTEGER]]})
  AssertFail({"colors": ["red", 1, 5.3]}, {"colors": [[STRING, INTEGER]]})

  AssertPass({"colors": ["red", "blue"]}, {"colors": [STRING]})
  AssertFail({"colors": ["red", "blue"]}, {"colors": [[STRING]]})
  AssertFail({"colors": ["red", ["blue"]]}, {"colors": [STRING]})
  AssertFail({"colors": ["red", ["blue", "green"]]}, {"colors": [STRING]})

  # required attribute tests
  AssertPass({"colors": ["red", 5]}, {"colors": [[STRING, INTEGER]]})
  AssertFail({"colors": ["red", 5]}, {"colors": [[INTEGER, STRING]]})
  AssertPass({"colors": ["red", 5]}, {"colors": [STRING, INTEGER]})
  AssertPass({"colors": ["red", 5]}, {"colors": [INTEGER, STRING]})
  AssertFail({"colors": ["red", 5, "FF0000"]}, {"colors": [[STRING, INTEGER]]})

  # an array and a map of primitive type tests
  AssertPass({"color": {"name": "red", "rgb": "FF0000"}},
             {"color": {"name": STRING, "rgb": STRING}})
  AssertFail({"color": {"name": "red", "rgb": ["FF0000"]}},
             {"color": {"name": STRING, "rgb": STRING}})
  AssertFail({"color": {"name": "red", "rgb": "FF0000"}},
             {"color": {"name": STRING, "rgb": INTEGER}})
  AssertFail({"color": {"name": "red", "rgb": "FF0000"}},
             {"color": {"name": STRING, "rgb": {"hex": STRING}}})
  AssertPass({"color": {"name": "red", "rgb": "FF0000"}},
             {"color": {"name": STRING, "rgb": STRING}})
  AssertPass({"colors":
              [{"name": "red", "rgb": "FF0000"},
               {"name": "blue", "rgb": "0000FF"}]},
             {"colors": [{"name": STRING, "rgb": STRING}]})
  AssertFail({"colors":
              [{"name": "red", "rgb": "FF0000"},
               {"phone": "blue", "rgb": "0000FF"}]},
             {"colors": [{"name": STRING, "rgb": STRING}]})

  # boolean type tests
  AssertPass({"name": "Bob", "active": "true"},
             {"name": STRING, "active": BOOLEAN})
  AssertPass({"name": "Bob", "active": True},
             {"name": STRING, "active": BOOLEAN})
  AssertPass({"name": "Bob", "active": [5, True, "False"]},
             {"name": STRING, "active": [INTEGER, BOOLEAN]})
  AssertPass({"name": "Bob", "active": [5, True, "false"]},
             {"name": STRING, "active": [STRING, INTEGER, BOOLEAN]})
  AssertFail({"name": "Bob", "active": [5, True, "False"]},
             {"name": STRING, "active": [[INTEGER, BOOLEAN]]})

  # optional attribute tests
  AssertPass({"points":
              [{"x": 1, "y": 2, "z": 3}, {"x": 3, "y": 2, "z": 1},
               {"x": 2, "y": 3, "z": 1}]},
             {"points": [{"x": INTEGER, "y": INTEGER, "z": INTEGER}]})
  AssertPass({"points":
              [{"x": 1, "z": 3}, {"x": 3, "y": 2}, {"y": 3, "z": 1}]},
             {"points": [{"x": INTEGER, "y": INTEGER, "z": INTEGER}]})
  AssertPass({"account":
              [{"name": "Bob", "age": 25, "active": True}]},
             {"account": [{"age": INTEGER, "name": STRING, "active": BOOLEAN}]})

  AssertPass({"account":
              [{"name": "Bob", "active": True}]},
             {"account": [{"age": INTEGER, "name": STRING, "active": BOOLEAN}]})

  # nested array tests
  AssertFail({"name": "Bob", "active": [5, True, "false"]},
             {"name": STRING, "active": [[BOOLEAN]]})
  AssertFail({"name": "Bob", "active": [True]},
             {"name": STRING, "active": [[STRING]]})
  AssertPass({"name": "Bob", "active": ["true"]},
             {"name": STRING, "active": [[STRING]]})
  AssertPass({"name": "flowers", "price": ["USD", 9.99]},
             {"name": STRING, "price": [[STRING, FLOAT]]})
  AssertPass({"name": "flowers", "price":
              [["USD", 9.99], ["CAD", 11.79], ["RUB", 250.23]]},
             {"name": STRING, "price": [[STRING, FLOAT]]})

  # selector tests
  AssertPass({"likes": [{"state": "CA", "food": "cheese"},
                        {"state": "NY", "drink": "wine"}]},
             {"likes": [{"state": "CA", "food": STRING},
                        {"state": "NY", "drink": STRING}]})

  AssertPass({"likes": [{"state": "CA", "food": "cheese"},
                        {"state": "CA", "food": "nuts"}]},
             {"likes": [{"state": "CA", "food": STRING},
                        {"state": "NY", "drink": STRING}]})

  AssertFail({"likes": {"state": "CA", "drink": "cheese"}},
             {"likes": [{"state": "CA", "food": STRING},
                        {"state": "NY", "drink": STRING}]})


def RunAllUnitTests():
  RunAllRegexUnitTests()
  RunAllSchemaHelperUnitTests()


RunAllUnitTests()
Verifier().LoadAndVerifyModel(Echo)

