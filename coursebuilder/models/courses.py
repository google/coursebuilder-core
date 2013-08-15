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

"""Common classes and methods for managing Courses."""

__author__ = 'Pavel Simakov (psimakov@google.com)'

import copy
from datetime import datetime
import logging
import os
import pickle
import sys

import appengine_config
from common.schema_fields import FieldRegistry
from common.schema_fields import SchemaField
import common.tags
from tools import verify
import yaml

import models
from models import MemcacheManager
import progress
import review
import transforms
import vfs


COURSE_MODEL_VERSION_1_2 = '1.2'
COURSE_MODEL_VERSION_1_3 = '1.3'

# 1.4 assessments are JavaScript files
ASSESSMENT_MODEL_VERSION_1_4 = '1.4'
# 1.5 assessments are HTML text, with embedded question tags
ASSESSMENT_MODEL_VERSION_1_5 = '1.5'
SUPPORTED_ASSESSMENT_MODEL_VERSIONS = frozenset(
    [ASSESSMENT_MODEL_VERSION_1_4, ASSESSMENT_MODEL_VERSION_1_5])


# Date format string for validating input in ISO 8601 format without a
# timezone. All such strings are assumed to refer to UTC datetimes.
# Example: '2013-03-21 13:00'
ISO_8601_DATE_FORMAT = '%Y-%m-%d %H:%M'


def deep_dict_merge(real_values_dict, default_values_dict):
    """Merges default and real value dictionaries recursively."""

    def _deep_merge(real_values, default_values):
        """Updates real with default values recursively."""

        # Recursively merge dictionaries.
        for key, value in real_values.items():
            default_value = default_values.get(key)
            if (default_value and isinstance(
                    value, dict) and isinstance(default_value, dict)):
                _deep_merge(value, default_value)

        # Copy over other values.
        for key, value in default_values.items():
            if key not in real_values:
                real_values[key] = value

    result = {}
    if real_values_dict:
        result = copy.deepcopy(real_values_dict)
    _deep_merge(result, default_values_dict)
    return result

# The template dict for all courses
course_template_yaml = open(os.path.join(os.path.dirname(
    __file__), '../course_template.yaml'), 'r')

COURSE_TEMPLATE_DICT = yaml.safe_load(
    course_template_yaml.read().decode('utf-8'))

# Here are the defaults for a new course.
DEFAULT_COURSE_YAML_DICT = {
    'course': {
        'title': 'UNTITLED COURSE',
        'locale': 'en_US',
        'main_image': {},
        'browsable': True,
        'now_available': False},
    'preview': {},
    'unit': {},
    'reg_form': {
        'can_register': True,
        'additional_registration_fields': ''
        }
}

# Here are the defaults for an existing course.
DEFAULT_EXISTING_COURSE_YAML_DICT = deep_dict_merge(
    {'course': {
        'now_available': True}},
    DEFAULT_COURSE_YAML_DICT)

# Here is the default course.yaml for a new course.
EMPTY_COURSE_YAML = u"""# my new course.yaml
course:
  title: 'New Course by %s'
  now_available: False
"""

# Here are the default assessment weights corresponding to the sample course.
DEFAULT_LEGACY_ASSESSMENT_WEIGHTS = {'Pre': 0, 'Mid': 30, 'Fin': 70}


# Indicates that an assessment is graded automatically.
AUTO_GRADER = 'auto'
# Indicates that an assessment is graded by a human.
HUMAN_GRADER = 'human'

# Allowed graders.
ALLOWED_GRADERS = [AUTO_GRADER, HUMAN_GRADER]

# Keys in unit.workflow (when it is converted to a dict).
GRADER_KEY = 'grader'
MATCHER_KEY = 'matcher'
SUBMISSION_DUE_DATE_KEY = 'submission_due_date'
REVIEW_DUE_DATE_KEY = 'review_due_date'
REVIEW_MIN_COUNT_KEY = 'review_min_count'
REVIEW_WINDOW_MINS_KEY = 'review_window_mins'

DEFAULT_REVIEW_MIN_COUNT = 2
DEFAULT_REVIEW_WINDOW_MINS = 60

# Keys specific to human-graded assessments.
HUMAN_GRADED_ASSESSMENT_KEY_LIST = [
    MATCHER_KEY, REVIEW_MIN_COUNT_KEY, REVIEW_WINDOW_MINS_KEY,
    SUBMISSION_DUE_DATE_KEY, REVIEW_DUE_DATE_KEY
]

# The name for the peer review assessment used in the sample v1.2 CSV file.
# This is here so that a peer review assessment example is available when
# Course Builder loads with the sample course. However, in general, peer
# review assessments should only be specified in Course Builder v1.4 or
# later (via the web interface).
LEGACY_REVIEW_ASSESSMENT = 'ReviewAssessmentExample'

# This value is the default workflow for assessment grading,
DEFAULT_AUTO_GRADER_WORKFLOW = yaml.safe_dump({
    GRADER_KEY: AUTO_GRADER
}, default_flow_style=False)

# This value is meant to be used only for the human-reviewed assessments in the
# sample v1.2 Power Searching course.
LEGACY_HUMAN_GRADER_WORKFLOW = yaml.safe_dump({
    GRADER_KEY: HUMAN_GRADER,
    MATCHER_KEY: review.PEER_MATCHER,
    SUBMISSION_DUE_DATE_KEY: '2014-03-14 12:00',
    REVIEW_DUE_DATE_KEY: '2014-03-21 12:00',
    REVIEW_MIN_COUNT_KEY: DEFAULT_REVIEW_MIN_COUNT,
    REVIEW_WINDOW_MINS_KEY: DEFAULT_REVIEW_WINDOW_MINS,
}, default_flow_style=False)


def is_editable_fs(app_context):
    return isinstance(app_context.fs.impl, vfs.DatastoreBackedFileSystem)


def copy_attributes(source, target, converter):
    """Copies source object attributes into a target using a converter."""
    for source_name, value in converter.items():
        if value:
            target_name = value[0]
            target_type = value[1]
            setattr(
                target, target_name, target_type(getattr(source, source_name)))


def load_csv_course(app_context):
    """Loads course data from the CSV files."""
    logging.info('Initializing datastore from CSV files.')

    unit_file = os.path.join(app_context.get_data_home(), 'unit.csv')
    lesson_file = os.path.join(app_context.get_data_home(), 'lesson.csv')

    # Check files exist.
    if (not app_context.fs.isfile(unit_file) or
        not app_context.fs.isfile(lesson_file)):
        return None, None

    unit_stream = app_context.fs.open(unit_file)
    lesson_stream = app_context.fs.open(lesson_file)

    # Verify CSV file integrity.
    units = verify.read_objects_from_csv_stream(
        unit_stream, verify.UNITS_HEADER, verify.Unit)
    lessons = verify.read_objects_from_csv_stream(
        lesson_stream, verify.LESSONS_HEADER, verify.Lesson)
    verifier = verify.Verifier()
    verifier.verify_unit_fields(units)
    verifier.verify_lesson_fields(lessons)
    verifier.verify_unit_lesson_relationships(units, lessons)
    assert verifier.errors == 0
    assert verifier.warnings == 0

    # Load data from CSV files into a datastore.
    units = verify.read_objects_from_csv_stream(
        app_context.fs.open(unit_file), verify.UNITS_HEADER, Unit12,
        converter=verify.UNIT_CSV_TO_DB_CONVERTER)
    lessons = verify.read_objects_from_csv_stream(
        app_context.fs.open(lesson_file), verify.LESSONS_HEADER, Lesson12,
        converter=verify.LESSON_CSV_TO_DB_CONVERTER)
    return units, lessons


def index_units_and_lessons(course):
    """Index all 'U' type units and their lessons. Indexes are 1-based."""
    unit_index = 1
    for unit in course.get_units():
        if verify.UNIT_TYPE_UNIT == unit.type:
            unit._index = unit_index  # pylint: disable-msg=protected-access
            unit_index += 1

            lesson_index = 1
            for lesson in course.get_lessons(unit.unit_id):
                lesson._index = (  # pylint: disable-msg=protected-access
                    lesson_index)
                lesson_index += 1


def create_course_registry():
    """Create the registry for course properties."""

    reg = FieldRegistry('Basic Course Settings', description='Course Settings')

    # Course level settings.
    course_opts = reg.add_sub_registry('course', 'Course Config')
    course_opts.add_property(
        SchemaField('course:title', 'Course Name', 'string'))
    course_opts.add_property(
        SchemaField(
            'course:admin_user_emails', 'Course Admin Emails', 'string',
            description='A space-separated list of email addresses of course '
            'administrators. Each email address must be placed between \'[\' '
            'and \']\'.'))
    course_opts.add_property(
        SchemaField(
            'course:forum_email', 'Forum Email', 'string', optional=True,
            description='Email for the forum, e.g. '
            '\'My-Course@googlegroups.com\'.'))
    course_opts.add_property(SchemaField(
        'course:announcement_list_email', 'Announcement List Email', 'string',
        optional=True, description='Email for the mailing list where students '
        'can register to receive course announcements, e.g. '
        '\'My-Course-Announce@googlegroups.com\''))
    course_opts.add_property(SchemaField('course:locale', 'Locale', 'string'))
    course_opts.add_property(SchemaField(
        'course:start_date', 'Course Start Date', 'string', optional=True))
    course_opts.add_property(SchemaField(
        'course:now_available', 'Make Course Available', 'boolean'))
    course_opts.add_property(SchemaField(
        'course:browsable', 'Make Course Browsable', 'boolean',
        description='Allow non-registered users to view course content.'))

    # Course registration settings.
    reg_opts = reg.add_sub_registry('reg_form', 'Student Registration Options')
    reg_opts.add_property(SchemaField(
        'reg_form:can_register', 'Enable Registrations', 'boolean',
        description='Checking this box allows new students to register for '
        'the course.'))
    reg_opts.add_property(SchemaField(
        'reg_form:additional_registration_fields', 'Additional Fields', 'html',
        description='Additional registration text or questions.'))

    # Course homepage settings.
    homepage_opts = reg.add_sub_registry('homepage', 'Homepage Settings')
    homepage_opts.add_property(SchemaField(
        'course:instructor_details', 'Instructor Details', 'html',
        optional=True))
    homepage_opts.add_property(SchemaField(
        'course:blurb', 'Course Abstract', 'html', optional=True,
        description='Text, shown on the course homepage, that explains what '
        'the course is about.',
        extra_schema_dict_values={
            'supportCustomTags': common.tags.CAN_USE_DYNAMIC_TAGS.value,
            'excludedCustomTags':
            common.tags.EditorBlacklists.COURSE_SCOPE}))
    homepage_opts.add_property(SchemaField(
        'course:main_video:url', 'Course Video', 'url', optional=True,
        description='URL for the preview video shown on the course homepage '
        '(e.g. http://www.youtube.com/embed/Kdg2drcUjYI ).'))
    homepage_opts.add_property(SchemaField(
        'course:main_image:url', 'Course Image', 'string', optional=True,
        description='URL for the preview image shown on the course homepage. '
        'This will only be shown if no course video is specified.'))
    homepage_opts.add_property(SchemaField(
        'course:main_image:alt_text', 'Alternate Text', 'string',
        optional=True,
        description='Alt text for the preview image on the course homepage.'))
    return reg


class AbstractCachedObject(object):
    """Abstract serializable versioned object that can stored in memcache."""

    @classmethod
    def _make_key(cls):
        # The course content files may change between deployment. To avoid
        # reading old cached values by the new version of the application we
        # add deployment version to the key. Now each version of the
        # application can put/get its own version of the course and the
        # deployment.
        return 'course:model:pickle:%s:%s' % (
            cls.VERSION, os.environ.get('CURRENT_VERSION_ID'))

    @classmethod
    def new_memento(cls):
        """Creates new empty memento instance; must be pickle serializable."""
        raise Exception('Not implemented')

    @classmethod
    def instance_from_memento(cls, unused_app_context, unused_memento):
        """Creates instance from serializable memento."""
        raise Exception('Not implemented')

    @classmethod
    def memento_from_instance(cls, unused_instance):
        """Creates serializable memento from instance."""
        raise Exception('Not implemented')

    @classmethod
    def load(cls, app_context):
        """Loads instance from memcache; does not fail on errors."""
        try:
            binary_data = MemcacheManager.get(
                cls._make_key(),
                namespace=app_context.get_namespace_name())
            if binary_data:
                memento = cls.new_memento()
                memento.deserialize(binary_data)
                return cls.instance_from_memento(app_context, memento)
        except Exception as e:  # pylint: disable-msg=broad-except
            logging.error(
                'Failed to load object \'%s\' from memcache. %s',
                cls._make_key(), e)
            return None

    @classmethod
    def save(cls, app_context, instance):
        """Saves instance to memcache."""
        MemcacheManager.set(
            cls._make_key(),
            cls.memento_from_instance(instance).serialize(),
            namespace=app_context.get_namespace_name())

    @classmethod
    def delete(cls, app_context):
        """Deletes instance from memcache."""
        MemcacheManager.delete(
            cls._make_key(),
            namespace=app_context.get_namespace_name())

    def serialize(self):
        """Saves instance to a pickle representation."""
        return pickle.dumps(self.__dict__)

    def deserialize(self, binary_data):
        """Loads instance from a pickle representation."""
        adict = pickle.loads(binary_data)
        if self.version != adict.get('version'):
            raise Exception('Expected version %s, found %s.' % (
                self.version, adict.get('version')))
        self.__dict__.update(adict)


class Unit12(object):
    """An object to represent a Unit, Assessment or Link (version 1.2)."""

    def __init__(self):
        self.unit_id = ''  # primary key
        self.type = ''
        self.title = ''
        self.release_date = ''
        self.now_available = False

        # Units of 'U' types have 1-based index. An index is automatically
        # computed.
        self._index = None

    @property
    def href(self):
        assert verify.UNIT_TYPE_LINK == self.type
        return self.unit_id

    @property
    def index(self):
        assert verify.UNIT_TYPE_UNIT == self.type
        return self._index

    @property
    def workflow_yaml(self):
        """Returns the workflow as a YAML text string."""
        assert verify.UNIT_TYPE_ASSESSMENT == self.type
        if self.unit_id == LEGACY_REVIEW_ASSESSMENT:
            return LEGACY_HUMAN_GRADER_WORKFLOW
        else:
            return DEFAULT_AUTO_GRADER_WORKFLOW

    @property
    def workflow(self):
        """Returns the workflow as an object."""
        return Workflow(self.workflow_yaml)


class Lesson12(object):
    """An object to represent a Lesson (version 1.2)."""

    def __init__(self):
        self.lesson_id = 0  # primary key
        self.unit_id = 0  # unit.unit_id of parent
        self.title = ''
        self.scored = False
        self.objectives = ''
        self.video = ''
        self.notes = ''
        self.duration = ''
        self.activity = ''
        self.activity_title = ''
        self.activity_listed = True

        # Lessons have 1-based index inside the unit they belong to. An index
        # is automatically computed.
        self._index = None

    @property
    def now_available(self):
        return True

    @property
    def index(self):
        return self._index


class CachedCourse12(AbstractCachedObject):
    """A representation of a Course12 optimized for storing in memcache."""

    VERSION = COURSE_MODEL_VERSION_1_2

    def __init__(self, units=None, lessons=None, unit_id_to_lessons=None):
        self.version = self.VERSION
        self.units = units
        self.lessons = lessons
        self.unit_id_to_lessons = unit_id_to_lessons

    @classmethod
    def new_memento(cls):
        return CachedCourse12()

    @classmethod
    def instance_from_memento(cls, app_context, memento):
        return CourseModel12(
            app_context, units=memento.units, lessons=memento.lessons,
            unit_id_to_lessons=memento.unit_id_to_lessons)

    @classmethod
    def memento_from_instance(cls, course):
        return CachedCourse12(
            units=course.units, lessons=course.lessons,
            unit_id_to_lessons=course.unit_id_to_lessons)


class CourseModel12(object):
    """A course defined in terms of CSV files (version 1.2)."""

    VERSION = COURSE_MODEL_VERSION_1_2

    @classmethod
    def load(cls, app_context):
        """Loads course data into a model."""
        course = CachedCourse12.load(app_context)
        if not course:
            units, lessons = load_csv_course(app_context)
            if units and lessons:
                course = CourseModel12(app_context, units, lessons)
        if course:
            CachedCourse12.save(app_context, course)
        return course

    @classmethod
    def _make_unit_id_to_lessons_lookup_dict(cls, lessons):
        """Creates an index of unit.unit_id to unit.lessons."""
        unit_id_to_lessons = {}
        for lesson in lessons:
            key = str(lesson.unit_id)
            if key not in unit_id_to_lessons:
                unit_id_to_lessons[key] = []
            unit_id_to_lessons[key].append(lesson)
        return unit_id_to_lessons

    def __init__(
        self, app_context,
        units=None, lessons=None, unit_id_to_lessons=None):

        self._app_context = app_context
        self._units = []
        self._lessons = []
        self._unit_id_to_lessons = {}

        if units:
            self._units = units
        if lessons:
            self._lessons = lessons
        if unit_id_to_lessons:
            self._unit_id_to_lessons = unit_id_to_lessons
        else:
            self._unit_id_to_lessons = (
                self._make_unit_id_to_lessons_lookup_dict(self._lessons))
            index_units_and_lessons(self)

    @property
    def app_context(self):
        return self._app_context

    @property
    def units(self):
        return self._units

    @property
    def lessons(self):
        return self._lessons

    @property
    def unit_id_to_lessons(self):
        return self._unit_id_to_lessons

    def get_units(self):
        return self._units[:]

    def get_lessons(self, unit_id):
        return self._unit_id_to_lessons.get(str(unit_id), [])

    def find_unit_by_id(self, unit_id):
        """Finds a unit given its id."""
        for unit in self._units:
            if str(unit.unit_id) == str(unit_id):
                return unit
        return None

    def get_review_form_filename(self, unit_id):
        """Returns the corresponding review form filename."""
        return 'assets/js/review-%s.js' % unit_id

    def get_assessment_filename(self, unit_id):
        """Returns assessment base filename."""
        unit = self.find_unit_by_id(unit_id)
        assert unit and verify.UNIT_TYPE_ASSESSMENT == unit.type
        return 'assets/js/assessment-%s.js' % unit.unit_id

    def _get_assessment_as_dict(self, filename):
        """Returns the Python dict representation of an assessment file."""
        root_name = 'assessment'
        context = self._app_context
        assessment_content = context.fs.impl.get(os.path.join(
            context.get_home(), filename)).read()

        content, noverify_text = verify.convert_javascript_to_python(
            assessment_content, root_name)
        assessment = verify.evaluate_python_expression_from_text(
            content, root_name, verify.Assessment().scope, noverify_text)

        return assessment

    def get_assessment_content(self, unit):
        """Returns the schema for an assessment as a Python dict."""
        return self._get_assessment_as_dict(
            self.get_assessment_filename(unit.unit_id))

    def get_assessment_model_version(self, unused_unit):
        return ASSESSMENT_MODEL_VERSION_1_4

    def get_review_form_content(self, unit):
        """Returns the schema for a review form as a Python dict."""
        return self._get_assessment_as_dict(
            self.get_review_form_filename(unit.unit_id))

    def get_activity_filename(self, unit_id, lesson_id):
        """Returns activity base filename."""
        return 'assets/js/activity-%s.%s.js' % (unit_id, lesson_id)

    def find_lesson_by_id(self, unit, lesson_id):
        """Finds a lesson given its id (or 1-based index in this model)."""
        index = int(lesson_id) - 1
        return self.get_lessons(unit.unit_id)[index]

    def to_json(self):
        """Creates JSON representation of this instance."""
        adict = copy.deepcopy(self)
        del adict._app_context
        return transforms.dumps(
            adict,
            indent=4, sort_keys=True,
            default=lambda o: o.__dict__)


class Unit13(object):
    """An object to represent a Unit, Assessment or Link (version 1.3)."""

    def __init__(self):
        self.unit_id = 0  # primary key
        self.type = ''
        self.title = ''
        self.release_date = ''
        self.now_available = False

        # Units of 'U' types have 1-based index. An index is automatically
        # computed.
        self._index = None

        # Only valid for the unit.type == verify.UNIT_TYPE_LINK.
        self.href = None

        # Only valid for the unit.type == verify.UNIT_TYPE_ASSESSMENT.
        self.weight = 1

        # Only valid for the unit.type == verify.UNIT_TYPE_ASSESSMENT.
        self.html_content = None
        self.html_check_answers = False
        self.html_review_form = None

        # Only valid for the unit.type == verify.UNIT_TYPE_ASSESSMENT.
        self.workflow_yaml = DEFAULT_AUTO_GRADER_WORKFLOW

    @property
    def index(self):
        assert verify.UNIT_TYPE_UNIT == self.type
        return self._index

    @property
    def workflow(self):
        """Returns the workflow as an object."""
        assert verify.UNIT_TYPE_ASSESSMENT == self.type
        workflow = Workflow(self.workflow_yaml)
        return workflow


class Lesson13(object):
    """An object to represent a Lesson (version 1.3)."""

    def __init__(self):
        self.lesson_id = 0  # primary key
        self.unit_id = 0  # unit.unit_id of parent
        self.title = ''
        self.scored = False
        self.objectives = ''
        self.video = ''
        self.notes = ''
        self.duration = ''
        self.now_available = False
        self.has_activity = False
        self.activity_title = ''
        self.activity_listed = True

        # Lessons have 1-based index inside the unit they belong to. An index
        # is automatically computed.
        self._index = None

    @property
    def index(self):
        return self._index

    @property
    def activity(self):
        """A symbolic name to old attribute."""
        return self.has_activity


class PersistentCourse13(object):
    """A representation of a Course13 optimized for persistence."""

    COURSES_FILENAME = 'data/course.json'

    def __init__(self, next_id=None, units=None, lessons=None):
        self.version = CourseModel13.VERSION
        self.next_id = next_id
        self.units = units
        self.lessons = lessons

    def to_dict(self):
        """Saves object attributes into a dict."""
        result = {}
        result['version'] = str(self.version)
        result['next_id'] = int(self.next_id)

        units = []
        for unit in self.units:
            units.append(transforms.instance_to_dict(unit))
        result['units'] = units

        lessons = []
        for lesson in self.lessons:
            lessons.append(transforms.instance_to_dict(lesson))
        result['lessons'] = lessons

        return result

    def _from_dict(self, adict):
        """Loads instance attributes from the dict."""
        self.next_id = int(adict.get('next_id'))

        self.units = []
        unit_dicts = adict.get('units')
        if unit_dicts:
            for unit_dict in unit_dicts:
                unit = Unit13()
                defaults = {
                    'workflow_yaml': DEFAULT_AUTO_GRADER_WORKFLOW,
                    'html_content': '',
                    'html_check_answers': False,
                    'html_review_form': ''}
                transforms.dict_to_instance(unit_dict, unit, defaults=defaults)
                self.units.append(unit)

        self.lessons = []
        lesson_dicts = adict.get('lessons')
        if lesson_dicts:
            for lesson_dict in lesson_dicts:
                lesson = Lesson13()
                defaults = {
                    'activity_listed': True,
                    'scored': False}
                transforms.dict_to_instance(
                    lesson_dict, lesson, defaults=defaults)
                self.lessons.append(lesson)

    @classmethod
    def save(cls, app_context, course):
        """Saves course to datastore."""
        persistent = PersistentCourse13(
            next_id=course.next_id,
            units=course.units, lessons=course.lessons)

        fs = app_context.fs.impl
        filename = fs.physical_to_logical(cls.COURSES_FILENAME)
        app_context.fs.put(filename, vfs.FileStreamWrapped(
            None, persistent.serialize()))

    @classmethod
    def load(cls, app_context):
        """Loads course from datastore."""
        fs = app_context.fs.impl
        filename = fs.physical_to_logical(cls.COURSES_FILENAME)
        if app_context.fs.isfile(filename):
            persistent = PersistentCourse13()
            persistent.deserialize(app_context.fs.get(filename))
            return CourseModel13(
                app_context, next_id=persistent.next_id,
                units=persistent.units, lessons=persistent.lessons)
        return None

    def serialize(self):
        """Saves instance to a JSON representation."""
        adict = self.to_dict()
        json_text = transforms.dumps(adict)
        return json_text.encode('utf-8')

    def deserialize(self, binary_data):
        """Loads instance from a JSON representation."""
        json_text = binary_data.decode('utf-8')
        adict = transforms.loads(json_text)
        if self.version != adict.get('version'):
            raise Exception('Expected version %s, found %s.' % (
                self.version, adict.get('version')))
        self._from_dict(adict)


class CachedCourse13(AbstractCachedObject):
    """A representation of a Course13 optimized for storing in memcache."""

    VERSION = COURSE_MODEL_VERSION_1_3

    def __init__(
        self, next_id=None, units=None, lessons=None,
        unit_id_to_lesson_ids=None):

        self.version = self.VERSION
        self.next_id = next_id
        self.units = units
        self.lessons = lessons

        # This is almost the same as PersistentCourse13 above, but it also
        # stores additional indexes used for performance optimizations. There
        # is no need to persist these indexes in durable storage, but it is
        # nice to have them in memcache.
        self.unit_id_to_lesson_ids = unit_id_to_lesson_ids

    @classmethod
    def new_memento(cls):
        return CachedCourse13()

    @classmethod
    def instance_from_memento(cls, app_context, memento):
        return CourseModel13(
            app_context, next_id=memento.next_id,
            units=memento.units, lessons=memento.lessons,
            unit_id_to_lesson_ids=memento.unit_id_to_lesson_ids)

    @classmethod
    def memento_from_instance(cls, course):
        return CachedCourse13(
            next_id=course.next_id,
            units=course.units, lessons=course.lessons,
            unit_id_to_lesson_ids=course.unit_id_to_lesson_ids)


class CourseModel13(object):
    """A course defined in terms of objects (version 1.3)."""

    VERSION = COURSE_MODEL_VERSION_1_3

    @classmethod
    def load(cls, app_context):
        """Loads course from memcache or persistence."""
        course = CachedCourse13.load(app_context)
        if not course:
            course = PersistentCourse13.load(app_context)
        if course:
            CachedCourse13.save(app_context, course)
        return course

    @classmethod
    def _make_unit_id_to_lessons_lookup_dict(cls, lessons):
        """Creates an index of unit.unit_id to unit.lessons."""
        unit_id_to_lesson_ids = {}
        for lesson in lessons:
            key = str(lesson.unit_id)
            if key not in unit_id_to_lesson_ids:
                unit_id_to_lesson_ids[key] = []
            unit_id_to_lesson_ids[key].append(str(lesson.lesson_id))
        return unit_id_to_lesson_ids

    def __init__(
        self, app_context, next_id=None, units=None, lessons=None,
        unit_id_to_lesson_ids=None):

        # Init default values.
        self._app_context = app_context
        self._next_id = 1  # a counter for creating sequential entity ids
        self._units = []
        self._lessons = []
        self._unit_id_to_lesson_ids = {}

        # These array keep dirty object in current transaction.
        self._dirty_units = []
        self._dirty_lessons = []
        self._deleted_units = []
        self._deleted_lessons = []

        # Set provided values.
        if next_id:
            self._next_id = next_id
        if units:
            self._units = units
        if lessons:
            self._lessons = lessons
        if unit_id_to_lesson_ids:
            self._unit_id_to_lesson_ids = unit_id_to_lesson_ids
        else:
            self._index()

    @property
    def app_context(self):
        return self._app_context

    @property
    def next_id(self):
        return self._next_id

    @property
    def units(self):
        return self._units

    @property
    def lessons(self):
        return self._lessons

    @property
    def unit_id_to_lesson_ids(self):
        return self._unit_id_to_lesson_ids

    def _get_next_id(self):
        """Allocates next id in sequence."""
        next_id = self._next_id
        self._next_id += 1
        return next_id

    def _index(self):
        """Indexes units and lessons."""
        self._unit_id_to_lesson_ids = self._make_unit_id_to_lessons_lookup_dict(
            self._lessons)
        index_units_and_lessons(self)

    def is_dirty(self):
        """Checks if course object has been modified and needs to be saved."""
        return self._dirty_units or self._dirty_lessons

    def _flush_deleted_objects(self):
        """Delete files owned by deleted objects."""

        # TODO(psimakov): handle similarly add_unit() and set_assessment()

        # To delete an activity/assessment one must look up its filename. This
        # requires a valid unit/lesson. If unit was deleted it's no longer
        # found in _units, same for lesson. So we temporarily install deleted
        # unit/lesson array instead of actual. We also temporarily empty
        # so _unit_id_to_lesson_ids is not accidentally used. This is a hack,
        # and we will improve it as object model gets more complex, but for
        # now it works fine.

        units = self._units
        lessons = self._lessons
        unit_id_to_lesson_ids = self._unit_id_to_lesson_ids
        try:
            self._units = self._deleted_units
            self._lessons = self._deleted_lessons
            self._unit_id_to_lesson_ids = None

            # Delete owned assessments.
            for unit in self._deleted_units:
                if verify.UNIT_TYPE_ASSESSMENT == unit.type:
                    self._delete_assessment(unit)

            # Delete owned activities.
            for lesson in self._deleted_lessons:
                if lesson.has_activity:
                    self._delete_activity(lesson)
        finally:
            self._units = units
            self._lessons = lessons
            self._unit_id_to_lesson_ids = unit_id_to_lesson_ids

    def _update_dirty_objects(self):
        """Update files owned by course."""

        fs = self.app_context.fs

        # Update state of owned assessments.
        for unit in self._dirty_units:
            unit = self.find_unit_by_id(unit.unit_id)
            if not unit or verify.UNIT_TYPE_ASSESSMENT != unit.type:
                continue
            path = fs.impl.physical_to_logical(
                self.get_assessment_filename(unit.unit_id))
            if fs.isfile(path):
                fs.put(
                    path, None, metadata_only=True,
                    is_draft=not unit.now_available)

        # Update state of owned activities.
        for lesson in self._dirty_lessons:
            lesson = self.find_lesson_by_id(None, lesson.lesson_id)
            if not lesson or not lesson.has_activity:
                continue
            path = fs.impl.physical_to_logical(
                self.get_activity_filename(None, lesson.lesson_id))
            if fs.isfile(path):
                fs.put(
                    path, None, metadata_only=True,
                    is_draft=not lesson.now_available)

    def save(self):
        """Saves course to datastore and memcache."""
        self._flush_deleted_objects()
        self._update_dirty_objects()

        self._dirty_units = []
        self._dirty_lessons = []
        self._deleted_units = []
        self._deleted_lessons = []

        self._index()
        PersistentCourse13.save(self._app_context, self)
        CachedCourse13.delete(self._app_context)

    def get_units(self):
        return self._units[:]

    def get_lessons(self, unit_id):
        lesson_ids = self._unit_id_to_lesson_ids.get(str(unit_id))
        lessons = []
        if lesson_ids:
            for lesson_id in lesson_ids:
                lessons.append(self.find_lesson_by_id(None, lesson_id))
        return lessons

    def get_assessment_filename(self, unit_id):
        """Returns assessment base filename."""
        unit = self.find_unit_by_id(unit_id)
        assert unit
        assert verify.UNIT_TYPE_ASSESSMENT == unit.type
        return 'assets/js/assessment-%s.js' % unit.unit_id

    def get_review_form_filename(self, unit_id):
        """Returns review form filename."""
        unit = self.find_unit_by_id(unit_id)
        assert unit
        assert verify.UNIT_TYPE_ASSESSMENT == unit.type
        return 'assets/js/review-%s.js' % unit.unit_id

    def get_activity_filename(self, unused_unit_id, lesson_id):
        """Returns activity base filename."""
        lesson = self.find_lesson_by_id(None, lesson_id)
        assert lesson
        if lesson.has_activity:
            return 'assets/js/activity-%s.js' % lesson_id
        return None

    def find_unit_by_id(self, unit_id):
        """Finds a unit given its id."""
        for unit in self._units:
            if str(unit.unit_id) == str(unit_id):
                return unit
        return None

    def find_lesson_by_id(self, unused_unit, lesson_id):
        """Finds a lesson given its id."""
        for lesson in self._lessons:
            if str(lesson.lesson_id) == str(lesson_id):
                return lesson
        return None

    def add_unit(self, unit_type, title):
        """Adds a brand new unit."""
        assert unit_type in verify.UNIT_TYPES

        unit = Unit13()
        unit.type = unit_type
        unit.unit_id = self._get_next_id()
        unit.title = title
        unit.now_available = False

        self._units.append(unit)
        self._index()

        self._dirty_units.append(unit)
        return unit

    def add_lesson(self, unit, title):
        """Adds brand new lesson to a unit."""
        unit = self.find_unit_by_id(unit.unit_id)
        assert unit

        lesson = Lesson13()
        lesson.lesson_id = self._get_next_id()
        lesson.unit_id = unit.unit_id
        lesson.title = title
        lesson.now_available = False

        self._lessons.append(lesson)
        self._index()

        self._dirty_lessons.append(lesson)
        return lesson

    def move_lesson_to(self, lesson, unit):
        """Moves a lesson to another unit."""
        unit = self.find_unit_by_id(unit.unit_id)
        assert unit
        assert verify.UNIT_TYPE_UNIT == unit.type

        lesson = self.find_lesson_by_id(None, lesson.lesson_id)
        assert lesson
        lesson.unit_id = unit.unit_id

        self._index()

        return lesson

    def _delete_activity(self, lesson):
        """Deletes activity."""
        filename = self._app_context.fs.impl.physical_to_logical(
            self.get_activity_filename(None, lesson.lesson_id))
        if self.app_context.fs.isfile(filename):
            self.app_context.fs.delete(filename)
            return True
        return False

    def _delete_assessment(self, unit):
        """Deletes assessment."""
        files_deleted_count = 0

        filenames = [
            self._app_context.fs.impl.physical_to_logical(
                self.get_assessment_filename(unit.unit_id)),
            self._app_context.fs.impl.physical_to_logical(
                self.get_review_form_filename(unit.unit_id))]

        for filename in filenames:
            if self.app_context.fs.isfile(filename):
                self.app_context.fs.delete(filename)
                files_deleted_count += 1

        return bool(files_deleted_count)

    def delete_all(self):
        """Deletes all course files."""
        for entity in self._app_context.fs.impl.list(
                appengine_config.BUNDLE_ROOT):
            self._app_context.fs.impl.delete(entity)
        assert not self._app_context.fs.impl.list(appengine_config.BUNDLE_ROOT)
        CachedCourse13.delete(self._app_context)

    def delete_lesson(self, lesson):
        """Delete a lesson."""
        lesson = self.find_lesson_by_id(None, lesson.lesson_id)
        if not lesson:
            return False
        self._lessons.remove(lesson)
        self._index()
        self._deleted_lessons.append(lesson)
        self._dirty_lessons.append(lesson)
        return True

    def delete_unit(self, unit):
        """Deletes a unit."""
        unit = self.find_unit_by_id(unit.unit_id)
        if not unit:
            return False
        for lesson in self.get_lessons(unit.unit_id):
            self.delete_lesson(lesson)
        self._units.remove(unit)
        self._index()
        self._deleted_units.append(unit)
        self._dirty_units.append(unit)
        return True

    def update_unit(self, unit):
        """Updates an existing unit."""
        existing_unit = self.find_unit_by_id(unit.unit_id)
        if not existing_unit:
            return False
        existing_unit.title = unit.title
        existing_unit.release_date = unit.release_date
        existing_unit.now_available = unit.now_available

        if verify.UNIT_TYPE_LINK == existing_unit.type:
            existing_unit.href = unit.href

        if verify.UNIT_TYPE_ASSESSMENT == existing_unit.type:
            existing_unit.weight = unit.weight
            existing_unit.html_content = unit.html_content
            existing_unit.html_check_answers = unit.html_check_answers
            existing_unit.html_review_form = unit.html_review_form
            existing_unit.workflow_yaml = unit.workflow_yaml

        self._dirty_units.append(existing_unit)
        return existing_unit

    def update_lesson(self, lesson):
        """Updates an existing lesson."""
        existing_lesson = self.find_lesson_by_id(
            lesson.unit_id, lesson.lesson_id)
        if not existing_lesson:
            return False
        existing_lesson.title = lesson.title
        existing_lesson.unit_id = lesson.unit_id
        existing_lesson.objectives = lesson.objectives
        existing_lesson.video = lesson.video
        existing_lesson.notes = lesson.notes
        existing_lesson.activity_title = lesson.activity_title

        self._index()

        self._dirty_lessons.append(existing_lesson)
        return existing_lesson

    def reorder_units(self, order_data):
        """Reorder the units and lessons based on the order data given.

        Args:
            order_data: list of dict. Format is
                The order_data is in the following format:
                [
                    {'id': 0, 'lessons': [{'id': 0}, {'id': 1}, {'id': 2}]},
                    {'id': 1},
                    {'id': 2, 'lessons': [{'id': 0}, {'id': 1}]}
                    ...
                ]
        """
        reordered_units = []
        unit_ids = set()
        for unit_data in order_data:
            unit_id = unit_data['id']
            unit = self.find_unit_by_id(unit_id)
            assert unit
            reordered_units.append(self.find_unit_by_id(unit_id))
            unit_ids.add(unit_id)
        assert len(unit_ids) == len(self._units)
        self._units = reordered_units

        reordered_lessons = []
        lesson_ids = set()
        for unit_data in order_data:
            unit_id = unit_data['id']
            unit = self.find_unit_by_id(unit_id)
            assert unit
            if verify.UNIT_TYPE_UNIT != unit.type:
                continue
            for lesson_data in unit_data['lessons']:
                lesson_id = lesson_data['id']
                reordered_lessons.append(
                    self.find_lesson_by_id(None, lesson_id))
                lesson_ids.add((unit_id, lesson_id))
        assert len(lesson_ids) == len(self._lessons)
        self._lessons = reordered_lessons

        self._index()

    def _get_assessment_as_dict(self, filename):
        """Gets the content of an assessment file as a Python dict."""
        path = self._app_context.fs.impl.physical_to_logical(filename)
        root_name = 'assessment'
        assessment_content = self.app_context.fs.get(path)

        content, noverify_text = verify.convert_javascript_to_python(
            assessment_content, root_name)
        assessment = verify.evaluate_python_expression_from_text(
            content, root_name, verify.Assessment().scope, noverify_text)
        return assessment

    def get_assessment_content(self, unit):
        """Returns the schema for an assessment as a Python dict."""
        return self._get_assessment_as_dict(
            self.get_assessment_filename(unit.unit_id))

    def get_assessment_model_version(self, unit):
        filename = self.get_assessment_filename(unit.unit_id)
        path = self._app_context.fs.impl.physical_to_logical(filename)
        if self.app_context.fs.isfile(path):
            return ASSESSMENT_MODEL_VERSION_1_4
        else:
            return ASSESSMENT_MODEL_VERSION_1_5

    def get_review_form_content(self, unit):
        """Returns the schema for a review form as a Python dict."""
        return self._get_assessment_as_dict(
            self.get_review_form_filename(unit.unit_id))

    def set_assessment_file_content(
        self, unit, assessment_content, dest_filename, errors=None):
        """Updates the content of an assessment file on the file system."""
        if errors is None:
            errors = []

        path = self._app_context.fs.impl.physical_to_logical(dest_filename)
        root_name = 'assessment'

        try:
            content, noverify_text = verify.convert_javascript_to_python(
                assessment_content, root_name)
            assessment = verify.evaluate_python_expression_from_text(
                content, root_name, verify.Assessment().scope, noverify_text)
        except Exception:  # pylint: disable-msg=broad-except
            errors.append('Unable to parse %s:\n%s' % (
                root_name,
                str(sys.exc_info()[1])))
            return

        verifier = verify.Verifier()
        try:
            verifier.verify_assessment_instance(assessment, path)
        except verify.SchemaException:
            errors.append('Error validating %s\n' % root_name)
            return

        fs = self.app_context.fs
        fs.put(
            path, vfs.string_to_stream(assessment_content),
            is_draft=not unit.now_available)

    def set_assessment_content(self, unit, assessment_content, errors=None):
        """Updates the content of an assessment."""
        self.set_assessment_file_content(
            unit,
            assessment_content,
            self.get_assessment_filename(unit.unit_id),
            errors=errors
        )

    def set_review_form(self, unit, review_form, errors=None):
        """Sets the content of a review form."""
        self.set_assessment_file_content(
            unit,
            review_form,
            self.get_review_form_filename(unit.unit_id),
            errors=errors
        )

    def set_activity_content(self, lesson, activity_content, errors=None):
        """Updates the content of an activity."""
        if errors is None:
            errors = []

        path = self._app_context.fs.impl.physical_to_logical(
            self.get_activity_filename(lesson.unit_id, lesson.lesson_id))
        root_name = 'activity'

        try:
            content, noverify_text = verify.convert_javascript_to_python(
                activity_content, root_name)
            activity = verify.evaluate_python_expression_from_text(
                content, root_name, verify.Activity().scope, noverify_text)
        except Exception:  # pylint: disable-msg=broad-except
            errors.append('Unable to parse %s:\n%s' % (
                root_name,
                str(sys.exc_info()[1])))
            return

        verifier = verify.Verifier()
        try:
            verifier.verify_activity_instance(activity, path)
        except verify.SchemaException:
            errors.append('Error validating %s\n' % root_name)
            return

        fs = self.app_context.fs
        fs.put(
            path, vfs.string_to_stream(activity_content),
            is_draft=not lesson.now_available)

    def import_from(self, src_course, errors):
        """Imports a content of another course into this course."""

        def copy_unit12_into_unit13(src_unit, dst_unit):
            """Copies unit object attributes between versions."""
            assert dst_unit.type == src_unit.type

            dst_unit.title = src_unit.title
            dst_unit.release_date = src_unit.release_date
            dst_unit.now_available = src_unit.now_available

            if verify.UNIT_TYPE_LINK == dst_unit.type:
                dst_unit.href = src_unit.href

            # Copy over the assessment. Note that we copy files directly and
            # avoid all logical validations of their content. This is done for
            # a purpose - at this layer we don't care what is in those files.
            if verify.UNIT_TYPE_ASSESSMENT == dst_unit.type:
                if src_unit.unit_id in DEFAULT_LEGACY_ASSESSMENT_WEIGHTS:
                    dst_unit.weight = (
                        DEFAULT_LEGACY_ASSESSMENT_WEIGHTS[src_unit.unit_id])

                filepath_mappings = [{
                    'src': src_course.get_assessment_filename(src_unit.unit_id),
                    'dst': self.get_assessment_filename(dst_unit.unit_id)
                }, {
                    'src': src_course.get_review_form_filename(
                        src_unit.unit_id),
                    'dst': self.get_review_form_filename(dst_unit.unit_id)
                }]

                for mapping in filepath_mappings:
                    src_filename = os.path.join(
                        src_course.app_context.get_home(), mapping['src'])

                    if src_course.app_context.fs.isfile(src_filename):
                        astream = src_course.app_context.fs.open(src_filename)
                        if astream:
                            dst_filename = os.path.join(
                                self.app_context.get_home(), mapping['dst'])
                            self.app_context.fs.put(dst_filename, astream)

                dst_unit.workflow_yaml = src_unit.workflow_yaml

        def copy_unit13_into_unit13(src_unit, dst_unit):
            """Copies unit13 attributes to a new unit."""
            copy_unit12_into_unit13(src_unit, dst_unit)

            if verify.UNIT_TYPE_ASSESSMENT == dst_unit.type:
                dst_unit.weight = src_unit.weight

        def copy_lesson12_into_lesson13(
            src_unit, src_lesson, unused_dst_unit, dst_lesson):
            """Copies lessons object attributes between versions."""
            dst_lesson.objectives = src_lesson.objectives
            dst_lesson.video = src_lesson.video
            dst_lesson.notes = src_lesson.notes
            dst_lesson.duration = src_lesson.duration
            dst_lesson.has_activity = src_lesson.activity
            dst_lesson.activity_title = src_lesson.activity_title

            # Old model does not have this flag, but all lessons are available.
            dst_lesson.now_available = True

            # Copy over the activity. Note that we copy files directly and
            # avoid all logical validations of their content. This is done for a
            # purpose - at this layer we don't care what is in those files.
            if src_lesson.activity:
                src_filename = os.path.join(
                    src_course.app_context.get_home(),
                    src_course.get_activity_filename(
                        src_unit.unit_id, src_lesson.lesson_id))
                if src_course.app_context.fs.isfile(src_filename):
                    astream = src_course.app_context.fs.open(src_filename)
                    if astream:
                        dst_filename = os.path.join(
                            self.app_context.get_home(),
                            self.get_activity_filename(
                                None, dst_lesson.lesson_id))
                        self.app_context.fs.put(dst_filename, astream)

        if not is_editable_fs(self._app_context):
            errors.append(
                'Target course %s must be '
                'on read-write media.' % self.app_context.raw)
            return None, None

        if self.get_units():
            errors.append(
                'Target course %s must be '
                'empty.' % self.app_context.raw)
            return None, None

        # Iterate over course structure and assets and import each item.
        for unit in src_course.get_units():
            new_unit = self.add_unit(unit.type, unit.title)
            # TODO(johncox): Create a full flow for importing a
            # Course13 into a Course13
            if src_course.version == self.VERSION:
                copy_unit13_into_unit13(unit, new_unit)
            else:
                copy_unit12_into_unit13(unit, new_unit)
            for lesson in src_course.get_lessons(unit.unit_id):
                new_lesson = self.add_lesson(new_unit, lesson.title)
                copy_lesson12_into_lesson13(unit, lesson, new_unit, new_lesson)

        return src_course, self

    def to_json(self):
        """Creates JSON representation of this instance."""
        persistent = PersistentCourse13(
            next_id=self._next_id, units=self._units, lessons=self._lessons)
        return transforms.dumps(
            persistent.to_dict(),
            indent=4, sort_keys=True,
            default=lambda o: o.__dict__)


class Workflow(object):
    """Stores workflow specifications for assessments."""

    def __init__(self, yaml_str):
        """Sets yaml_str (the workflow spec), without doing any validation."""
        self._yaml_str = yaml_str

    def to_yaml(self):
        return self._yaml_str

    def to_dict(self):
        if not self._yaml_str:
            return {}
        obj = yaml.safe_load(self._yaml_str)
        assert isinstance(obj, dict)
        return obj

    def _convert_date_string_to_datetime(self, date_str):
        """Returns a datetime object."""
        if not date_str:
            return None
        return datetime.strptime(date_str, ISO_8601_DATE_FORMAT)

    def get_grader(self):
        """Returns the associated grader."""
        return self.to_dict().get(GRADER_KEY)

    def get_matcher(self):
        return self.to_dict().get(MATCHER_KEY)

    def get_submission_due_date(self):
        date_str = self.to_dict().get(SUBMISSION_DUE_DATE_KEY)
        if date_str is None:
            return None
        return self._convert_date_string_to_datetime(date_str)

    def get_review_due_date(self):
        date_str = self.to_dict().get(REVIEW_DUE_DATE_KEY)
        if date_str is None:
            return None
        return self._convert_date_string_to_datetime(date_str)

    def get_review_min_count(self):
        return self.to_dict().get(REVIEW_MIN_COUNT_KEY)

    def get_review_window_mins(self):
        return self.to_dict().get(REVIEW_WINDOW_MINS_KEY)

    def _ensure_value_is_nonnegative_int(self, workflow_dict, key, errors):
        """Checks that workflow_dict[key] is a non-negative integer."""
        value = workflow_dict[key]
        if not isinstance(value, int):
            errors.append('%s should be an integer' % key)
        elif value < 0:
            errors.append('%s should be a non-negative integer' % key)

    def validate(self, errors=None):
        """Tests whether the current Workflow object is valid."""
        if errors is None:
            errors = []

        try:
            # Validate the workflow specification (in YAML format).
            assert self._yaml_str, 'missing key: %s.' % GRADER_KEY
            workflow_dict = yaml.safe_load(self._yaml_str)

            assert isinstance(workflow_dict, dict), (
                'expected the YAML representation of a dict')

            assert GRADER_KEY in workflow_dict, 'missing key: %s.' % GRADER_KEY
            assert workflow_dict[GRADER_KEY] in ALLOWED_GRADERS, (
                'invalid grader, should be one of: %s' %
                ', '.join(ALLOWED_GRADERS))

            workflow_errors = []
            submission_due_date = None
            if SUBMISSION_DUE_DATE_KEY in workflow_dict.keys():
                try:
                    submission_due_date = self._convert_date_string_to_datetime(
                        workflow_dict[SUBMISSION_DUE_DATE_KEY])
                except Exception as e:  # pylint: disable-msg=broad-except
                    workflow_errors.append(
                        'dates should be formatted as YYYY-MM-DD hh:mm '
                        '(e.g. 1997-07-16 19:20) and be specified in the UTC '
                        'timezone')

            if workflow_errors:
                raise Exception('%s.' % '; '.join(workflow_errors))

            if workflow_dict[GRADER_KEY] == HUMAN_GRADER:

                missing_keys = []
                for key in HUMAN_GRADED_ASSESSMENT_KEY_LIST:
                    if key not in workflow_dict:
                        missing_keys.append(key)
                    elif (isinstance(workflow_dict[key], basestring) and not
                          workflow_dict[key]):
                        missing_keys.append(key)

                assert not missing_keys, (
                    'missing key(s) for a human-reviewed assessment: %s.' %
                    ', '.join(missing_keys))

                if (workflow_dict[MATCHER_KEY] not in
                    review.ALLOWED_MATCHERS):
                    workflow_errors.append(
                        'invalid matcher, should be one of: %s' %
                        ', '.join(review.ALLOWED_MATCHERS))

                self._ensure_value_is_nonnegative_int(
                    workflow_dict, REVIEW_MIN_COUNT_KEY, workflow_errors)
                self._ensure_value_is_nonnegative_int(
                    workflow_dict, REVIEW_WINDOW_MINS_KEY, workflow_errors)

                try:
                    review_due_date = self._convert_date_string_to_datetime(
                        workflow_dict[REVIEW_DUE_DATE_KEY])

                    if submission_due_date > review_due_date:
                        workflow_errors.append(
                            'submission due date should be earlier than '
                            'review due date')
                except Exception as e:  # pylint: disable-msg=broad-except
                    workflow_errors.append(
                        'dates should be formatted as YYYY-MM-DD hh:mm '
                        '(e.g. 1997-07-16 19:20) and be specified in the UTC '
                        'timezone')

                if workflow_errors:
                    raise Exception('%s.' % '; '.join(workflow_errors))

            return True
        except Exception as e:  # pylint: disable-msg=broad-except
            errors.append('Error validating workflow specification: %s' % e)
            return False


class Course(object):
    """Manages a course and all of its components."""

    @classmethod
    def get_environ(cls, app_context):
        """Returns currently defined course settings as a dictionary."""
        course_yaml = None
        course_yaml_dict = None
        course_data_filename = app_context.get_config_filename()
        if app_context.fs.isfile(course_data_filename):
            course_yaml = app_context.fs.open(course_data_filename)
        if not course_yaml:
            return deep_dict_merge(DEFAULT_COURSE_YAML_DICT,
                                   COURSE_TEMPLATE_DICT)
        try:
            course_yaml_dict = yaml.safe_load(
                course_yaml.read().decode('utf-8'))
        except Exception as e:  # pylint: disable-msg=broad-except
            logging.info(
                'Error: course.yaml file at %s not accessible, '
                'loading defaults. %s', course_data_filename, e)

        if not course_yaml_dict:
            return deep_dict_merge(DEFAULT_COURSE_YAML_DICT,
                                   COURSE_TEMPLATE_DICT)
        return deep_dict_merge(deep_dict_merge(
            course_yaml_dict, DEFAULT_EXISTING_COURSE_YAML_DICT),
                               COURSE_TEMPLATE_DICT)

    @property
    def version(self):
        return self._model.VERSION

    @classmethod
    def create_new_default_course(cls, app_context):
        return CourseModel13(app_context)

    @classmethod
    def custom_new_default_course_for_test(cls, app_context):
        # There is an expectation in our tests of automatic import
        # of data/*.csv files. This method can be used in tests to achieve
        # exactly that.
        model = CourseModel12.load(app_context)
        if model:
            return model
        return CourseModel13(app_context)

    @classmethod
    def _load(cls, app_context):
        """Loads course data from persistence storage into this instance."""
        if not is_editable_fs(app_context):
            model = CourseModel12.load(app_context)
            if model:
                return model
        else:
            model = CourseModel13.load(app_context)
            if model:
                return model
        return cls.create_new_default_course(app_context)

    def __init__(self, handler, app_context=None):
        self._app_context = app_context if app_context else handler.app_context
        self._namespace = self._app_context.get_namespace_name()
        self._model = self._load(self._app_context)
        self._tracker = None
        self._reviews_processor = None

    @property
    def app_context(self):
        return self._app_context

    def to_json(self):
        return self._model.to_json()

    def get_progress_tracker(self):
        if not self._tracker:
            self._tracker = progress.UnitLessonCompletionTracker(self)
        return self._tracker

    def get_reviews_processor(self):
        if not self._reviews_processor:
            self._reviews_processor = review.ReviewsProcessor(self)
        return self._reviews_processor

    def get_units(self):
        return self._model.get_units()

    def get_units_of_type(self, unit_type):
        return [unit for unit in self.get_units() if unit_type == unit.type]

    def get_lessons(self, unit_id):
        return self._model.get_lessons(unit_id)

    def get_lessons_for_all_units(self):
        lessons = []
        for unit in self.get_units():
            for lesson in self.get_lessons(unit.unit_id):
                lessons.append(lesson)
        return lessons

    def save(self):
        return self._model.save()

    def find_unit_by_id(self, unit_id):
        return self._model.find_unit_by_id(unit_id)

    def find_lesson_by_id(self, unit, lesson_id):
        return self._model.find_lesson_by_id(unit, lesson_id)

    def is_last_assessment(self, unit):
        """Checks whether the given unit is the last of all the assessments."""
        for current_unit in reversed(self.get_units()):
            if current_unit.type == verify.UNIT_TYPE_ASSESSMENT:
                return current_unit.unit_id == unit.unit_id
        return False

    def add_unit(self):
        """Adds new unit to a course."""
        return self._model.add_unit('U', 'New Unit')

    def add_link(self):
        """Adds new link (other) to a course."""
        return self._model.add_unit('O', 'New Link')

    def add_assessment(self):
        """Adds new assessment to a course."""
        return self._model.add_unit('A', 'New Assessment')

    def add_lesson(self, unit):
        return self._model.add_lesson(unit, 'New Lesson')

    def update_unit(self, unit):
        return self._model.update_unit(unit)

    def update_lesson(self, lesson):
        return self._model.update_lesson(lesson)

    def move_lesson_to(self, lesson, unit):
        return self._model.move_lesson_to(lesson, unit)

    def delete_all(self):
        return self._model.delete_all()

    def delete_unit(self, unit):
        return self._model.delete_unit(unit)

    def delete_lesson(self, lesson):
        return self._model.delete_lesson(lesson)

    def get_score(self, student, assessment_id):
        """Gets a student's score for a particular assessment."""
        assert self.is_valid_assessment_id(assessment_id)
        scores = transforms.loads(student.scores) if student.scores else {}
        return scores.get(assessment_id) if scores else None

    def get_overall_score(self, student):
        """Gets the overall course score for a student."""
        score_list = self.get_all_scores(student)
        overall_score = 0
        total_weight = 0
        for unit in score_list:
            if not unit['human_graded']:
                total_weight += unit['weight']
                overall_score += unit['weight'] * unit['score']

        if total_weight == 0:
            return None

        return int(float(overall_score) / total_weight)

    def is_course_complete(self, student):
        """Returns true if the student has completed the course."""
        score_list = self.get_all_scores(student)
        for unit in score_list:
            if not unit['completed']:
                return False
        return True

    def update_final_grades(self, student):
        """Updates the final grades of the student."""
        if (models.CAN_SHARE_STUDENT_PROFILE.value and
            self.is_course_complete(student)):
            overall_score = self.get_overall_score(student)
            models.StudentProfileDAO.update(
                student.user_id, student.email, final_grade=overall_score)

    def get_overall_result(self, student):
        """Gets the overall result based on a student's score profile."""
        score = self.get_overall_score(student)
        if score is None:
            return None

        # This can be replaced with a custom definition for an overall result
        # string.
        return 'pass' if self.get_overall_score(student) >= 70 else 'fail'

    def get_all_scores(self, student):
        """Gets all score data for a student.

        Args:
            student: the student whose scores should be retrieved.

        Returns:
            an array of dicts, each representing an assessment. Each dict has
            the keys 'id', 'title', 'weight' and 'score' (if available),
            representing the unit id, the assessment title, the weight
            contributed by the assessment to the final score, and the
            assessment score.
        """
        assessment_list = self.get_assessment_list()
        scores = transforms.loads(student.scores) if student.scores else {}

        unit_progress = self.get_progress_tracker().get_unit_progress(student)

        assessment_score_list = []
        for unit in assessment_list:
            # Compute the weight for this assessment.
            weight = 0
            if hasattr(unit, 'weight'):
                weight = unit.weight
            elif unit.unit_id in DEFAULT_LEGACY_ASSESSMENT_WEIGHTS:
                weight = DEFAULT_LEGACY_ASSESSMENT_WEIGHTS[unit.unit_id]

            completed = unit_progress[unit.unit_id]

            # If a human-reviewed assessment is completed, ensure that the
            # required reviews have also been completed.
            if completed and self.needs_human_grader(unit):
                reviews = self.get_reviews_processor().get_review_steps_by(
                    unit.unit_id, student.get_key())
                review_min_count = unit.workflow.get_review_min_count()
                if not review.ReviewUtils.has_completed_enough_reviews(
                        reviews, review_min_count):
                    completed = False

            assessment_score_list.append({
                'id': str(unit.unit_id),
                'title': unit.title,
                'weight': weight,
                'completed': completed,
                'human_graded': self.needs_human_grader(unit),
                'score': (scores[str(unit.unit_id)]
                          if str(unit.unit_id) in scores else 0),
            })

        return assessment_score_list

    def get_assessment_list(self):
        """Returns a list of units that are assessments."""
        # TODO(psimakov): Streamline this so that it does not require a full
        # iteration on each request, probably by modifying the index() method.
        assessment_list = []
        for unit in self.get_units():
            if verify.UNIT_TYPE_ASSESSMENT == unit.type:
                assessment_list.append(unit)
        return copy.deepcopy(assessment_list)

    def get_peer_reviewed_units(self):
        """Returns a list of units that are peer-reviewed assessments.

        Returns:
            A list of units that are peer-reviewed assessments. Each unit
            in the list has a unit_id of type string.
        """
        assessment_list = self.get_assessment_list()
        units = copy.deepcopy([unit for unit in assessment_list if (
            unit.workflow.get_grader() == HUMAN_GRADER and
            unit.workflow.get_matcher() == review.PEER_MATCHER)])
        for unit in units:
            unit.unit_id = str(unit.unit_id)
        return units

    def get_assessment_filename(self, unit_id):
        return self._model.get_assessment_filename(unit_id)

    def get_review_form_filename(self, unit_id):
        return self._model.get_review_form_filename(unit_id)

    def get_activity_filename(self, unit_id, lesson_id):
        return self._model.get_activity_filename(unit_id, lesson_id)

    def get_components(self, unit_id, lesson_id):
        """Returns a list of dicts representing the components in a lesson.

        Args:
            unit_id: the id of the unit containing the lesson
            lesson_id: the id of the lesson

        Returns:
            A list of dicts. Each dict represents one component and has two
            keys:
            - instanceid: the instance id of the component
            - cpt_name: the name of the component tag (e.g. gcb-googlegroup)
        """
        unit = self.find_unit_by_id(unit_id)
        lesson = self.find_lesson_by_id(unit, lesson_id)
        if not lesson.objectives:
            return []

        return common.tags.get_components_from_html(lesson.objectives)

    def get_assessment_components(self, unit_id):
        """Returns a list of dicts representing components in an assessment.

        Args:
            unit_id: the id of the assessment unit

        Returns:
            A list of dicts. Each dict represents one component and has two
            keys:
            - instanceid: the instance id of the component
            - cpt_name: the name of the component tag (e.g. gcb-googlegroup)
        """
        unit = self.find_unit_by_id(unit_id)
        if not getattr(unit, 'html_content', None):
            return []

        return common.tags.get_components_from_html(unit.html_content)

    def get_question_components(self, unit_id, lesson_id):
        """Returns a list of dicts representing the questions in a lesson."""
        components = self.get_components(unit_id, lesson_id)
        question_components = []
        for component in components:
            if component.get('cpt_name') == 'question':
                question_components.append(component)
        return question_components

    def get_question_group_components(self, unit_id, lesson_id):
        """Returns a list of dicts representing the q_groups in a lesson."""
        components = self.get_components(unit_id, lesson_id)
        question_group_components = []
        for component in components:
            if component.get('cpt_name') == 'question-group':
                question_group_components.append(component)
        return question_group_components

    def needs_human_grader(self, unit):
        return unit.workflow.get_grader() == HUMAN_GRADER

    def reorder_units(self, order_data):
        return self._model.reorder_units(order_data)

    def get_assessment_content(self, unit):
        """Returns the schema for an assessment as a Python dict."""
        return self._model.get_assessment_content(unit)

    def get_assessment_model_version(self, unit):
        return self._model.get_assessment_model_version(unit)

    def get_review_form_content(self, unit):
        """Returns the schema for a review form as a Python dict."""
        return self._model.get_review_form_content(unit)

    def set_assessment_content(self, unit, assessment_content, errors=None):
        return self._model.set_assessment_content(
            unit, assessment_content, errors=errors)

    def set_review_form(self, unit, review_form, errors=None):
        return self._model.set_review_form(unit, review_form, errors=errors)

    def set_activity_content(self, lesson, activity_content, errors=None):
        return self._model.set_activity_content(
            lesson, activity_content, errors=errors)

    def is_valid_assessment_id(self, assessment_id):
        """Tests whether the given assessment id is valid."""
        for unit in self.get_units():
            if (verify.UNIT_TYPE_ASSESSMENT == unit.type and
                str(assessment_id) == str(unit.unit_id)):
                return True
        return False

    def is_valid_unit_lesson_id(self, unit_id, lesson_id):
        """Tests whether the given unit id and lesson id are valid."""
        for unit in self.get_units():
            if str(unit.unit_id) == str(unit_id):
                for lesson in self.get_lessons(unit_id):
                    if str(lesson.lesson_id) == str(lesson_id):
                        return True
        return False

    def import_from(self, app_context, errors=None):
        """Import course structure and assets from another courses."""
        src_course = Course(None, app_context=app_context)
        if errors is None:
            errors = []

        # Import 1.2 -> 1.3
        if (src_course.version == CourseModel12.VERSION and
            self.version == CourseModel13.VERSION):
            return self._model.import_from(src_course, errors)

        # import 1.3 -> 1.3
        if (src_course.version == CourseModel13.VERSION and
            self.version == CourseModel13.VERSION):
            return self._model.import_from(src_course, errors)

        errors.append(
            'Import of '
            'course %s (version %s) into '
            'course %s (version %s) '
            'is not supported.' % (
                app_context.raw, src_course.version,
                self.app_context.raw, self.version))

        return None, None

    def get_course_announcement_list_email(self):
        """Get Announcement email address for the course."""
        course_env = self.get_environ(self._app_context)
        if not course_env:
            return None
        if 'course' not in course_env:
            return None
        course_dict = course_env['course']
        if 'announcement_list_email' not in course_dict:
            return None
        announcement_list_email = course_dict['announcement_list_email']
        if announcement_list_email:
            return announcement_list_email
        return None

    def init_new_course_settings(self, title, admin_email):
        """Initializes new course.yaml file if it does not yet exists."""
        fs = self.app_context.fs.impl
        course_yaml = fs.physical_to_logical('/course.yaml')
        if fs.isfile(course_yaml):
            return False

        title = title.replace('\'', '\'\'')
        course_yaml_text = u"""# my new course.yaml
course:
  title: '%s'
  admin_user_emails: '[%s]'
  now_available: False
""" % (title, admin_email)

        fs.put(course_yaml, vfs.string_to_stream(course_yaml_text))
        return True
