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
import logging
import os
import pickle
import sys
from tools import verify
import yaml
from models import MemcacheManager
import progress
import transforms
import vfs


COURSE_MODEL_VERSION_1_2 = '1.2'
COURSE_MODEL_VERSION_1_3 = '1.3'


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
            if not key in real_values:
                real_values[key] = value

    result = {}
    if real_values_dict:
        result = copy.deepcopy(real_values_dict)
    _deep_merge(result, default_values_dict)
    return result


# Here are the defaults for a new course.
DEFAULT_COURSE_YAML_DICT = {
    'course': {
        'title': 'UNTITLED COURSE',
        'locale': 'en_US',
        'main_image': {},
        'now_available': False},
    'base': {
        'show_gplus_button': True},
    'institution': {
        'logo': {},
        'url': ''},
    'preview': {},
    'unit': {},
    'reg_form': {
        'can_register': True,
        'additional_registration_fields': (
            '<!-- reg_form.additional_registration_fields -->')}
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


class Unit12(object):
    """An object to represent a Unit, Assessment or Link (version 1.2)."""

    def __init__(self):
        self.unit_id = ''  # primary key
        self.type = ''
        self.title = ''
        self.release_date = ''
        self.now_available = False

    @property
    def href(self):
        assert verify.UNIT_TYPE_LINK == self.type
        return self.unit_id


class Lesson12(object):
    """An object to represent a Lesson (version 1.2)."""

    def __init__(self):
        self.lesson_id = 0  # primary key
        self.unit_id = 0  # unit.unit_id of parent
        self.title = ''
        self.objectives = ''
        self.video = ''
        self.notes = ''
        self.duration = ''
        self.activity = ''
        self.activity_title = ''


class CourseModel12(object):
    """A course defined in terms of CSV files (version 1.2)."""

    VERSION = COURSE_MODEL_VERSION_1_2

    @classmethod
    def load(cls, app_context):
        """Loads course data into a model."""
        units, lessons = load_csv_course(app_context)
        if units and lessons:
            return CourseModel12(app_context, units, lessons)
        return None

    @classmethod
    def index_lessons(cls, lessons):
        """Creates an index of unit.unit_id to unit.lessons."""
        unit_id_to_lessons = {}
        for lesson in lessons:
            key = str(lesson.unit_id)
            if not key in unit_id_to_lessons:
                unit_id_to_lessons[key] = []
            unit_id_to_lessons[key].append(lesson)
        return unit_id_to_lessons

    def __init__(self, app_context, units, lessons):
        self._app_context = app_context
        self._units = units
        self._lessons = lessons
        self._unit_id_to_lessons = self.index_lessons(self._lessons)

    @property
    def app_context(self):
        return self._app_context

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

    def get_assessment_filename(self, unit_id):
        """Returns assessment base filename."""
        unit = self.find_unit_by_id(unit_id)
        assert unit and verify.UNIT_TYPE_ASSESSMENT == unit.type
        return 'assets/js/assessment-%s.js' % unit.unit_id

    def get_activity_filename(self, unit_id, lesson_id):
        """Returns activity base filename."""
        return 'assets/js/activity-%s.%s.js' % (unit_id, lesson_id)

    def find_lesson_by_id(self, unit, lesson_id):
        """Finds a lesson given its id (or 1-based index in this model)."""
        index = int(lesson_id) - 1
        return self.get_lessons(unit.unit_id)[index]


class Unit13(object):
    """An object to represent a Unit, Assessment or Link (version 1.3)."""

    def __init__(self):
        self.unit_id = 0  # primary key
        self.type = ''
        self.title = ''
        self.release_date = ''
        self.now_available = False

        # Only valid for the unit.type == verify.UNIT_TYPE_LINK.
        self.href = None


class Lesson13(object):
    """An object to represent a Lesson (version 1.3)."""

    def __init__(self):
        self.lesson_id = 0  # primary key
        self.unit_id = 0  # unit.unit_id of parent
        self.title = ''
        self.objectives = ''
        self.video = ''
        self.notes = ''
        self.duration = ''
        self.now_available = False
        self.has_activity = False
        self.activity_title = ''

    @property
    def activity(self):
        """A symbolic name to old attribute."""
        return self.has_activity


class SerializableCourseEnvelope(object):
    """A serializable, data-only representation of a Course."""

    def __init__(self):
        self.version = None
        self.next_id = None
        self.units = None
        self.lessons = None
        self.unit_id_to_lesson_ids = None


class CourseModel13(object):
    """A course defined in terms of objects (version 1.3)."""

    VERSION = COURSE_MODEL_VERSION_1_3

    # A logical filename where we persist courses data."""
    COURSES_FILENAME = 'data/course.pickle'

    # The course content files may change between deployment. To avoid reading
    # old cached values by the new version of the application we add deployment
    # version to the key. Now each version of the application can put/get its
    # own version of the course.
    memcache_key = 'course-%s' % os.environ.get('CURRENT_VERSION_ID')

    @classmethod
    def assert_envelope_version(cls, envelope):
        if cls.VERSION != envelope.version:
            raise Exception(
                'Unsupported course version %s, expected %s.' % (
                    envelope.version, cls.VERSION))

    @classmethod
    def load(cls, app_context):
        """Loads course from memcache or the fs."""
        envelope = None
        try:
            binary_data = MemcacheManager.get(
                cls.memcache_key, namespace=app_context.get_namespace_name())
            if binary_data:
                envelope = pickle.loads(binary_data)
                cls.assert_envelope_version(envelope)
        except Exception as e:  # pylint: disable-msg=broad-except
            logging.error(
                'Failed to load course \'%s\' from memcache. %s',
                cls.memcache_key, e)

        if not envelope:
            fs = app_context.fs.impl
            filename = fs.physical_to_logical(cls.COURSES_FILENAME)
            if app_context.fs.isfile(filename):
                envelope = pickle.loads(app_context.fs.get(filename))
                cls.assert_envelope_version(envelope)
                if envelope:
                    return CourseModel13(app_context, envelope)

        return None

    def __init__(self, app_context, envelope=None):
        self._app_context = app_context
        self._units = []
        self._lessons = []
        self._unit_id_to_lesson_ids = {}

        # a counter for creating sequential entity ids
        self._next_id = 1

        if envelope:
            self.assert_envelope_version(envelope)

            self._next_id = envelope.next_id
            self._units = envelope.units
            self._lessons = envelope.lessons
            self._unit_id_to_lesson_ids = envelope.unit_id_to_lesson_ids

    def _get_next_id(self):
        """Allocates next id in sequence."""
        next_id = self._next_id
        self._next_id += 1
        return next_id

    def _index(self, lessons):
        """Creates an index of unit.unit_id to unit.lessons."""
        unit_id_to_lesson_ids = {}
        for lesson in lessons:
            key = str(lesson.unit_id)
            if not key in unit_id_to_lesson_ids:
                unit_id_to_lesson_ids[key] = []
            unit_id_to_lesson_ids[key].append(str(lesson.lesson_id))
        self._unit_id_to_lesson_ids = unit_id_to_lesson_ids

    def save(self):
        """Saves this model to fs."""
        envelope = SerializableCourseEnvelope()
        envelope.version = self.VERSION
        envelope.next_id = self._next_id
        envelope.units = self._units
        envelope.lessons = self._lessons
        envelope.unit_id_to_lesson_ids = self._unit_id_to_lesson_ids

        # TODO(psimakov): we really should use JSON, not binary format
        binary_data = pickle.dumps(envelope)

        fs = self._app_context.fs.impl
        filename = fs.physical_to_logical(self.COURSES_FILENAME)
        self._app_context.fs.put(
            filename, vfs.FileStreamWrapped(None, binary_data))

        MemcacheManager.delete(
            self.memcache_key,
            namespace=self._app_context.get_namespace_name())

    @property
    def app_context(self):
        return self._app_context

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
        self._index(self._lessons)

        return lesson

    def move_lesson_to(self, lesson, unit):
        """Moves a lesson to another unit."""
        unit = self.find_unit_by_id(unit.unit_id)
        assert unit
        assert verify.UNIT_TYPE_UNIT == unit.type

        lesson = self.find_lesson_by_id(None, lesson.lesson_id)
        assert lesson
        lesson.unit_id = unit.unit_id

        self._index(self._lessons)

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
        filename = self._app_context.fs.impl.physical_to_logical(
            self.get_assessment_filename(unit.unit_id))
        if self.app_context.fs.isfile(filename):
            self.app_context.fs.delete(filename)
            return True
        return False

    def delete_lesson(self, lesson):
        """Delete a lesson."""
        lesson = self.find_lesson_by_id(None, lesson.lesson_id)
        if not lesson:
            return False
        if lesson.has_activity:
            self._delete_activity(lesson)
        self._lessons.remove(lesson)
        self._index(self._lessons)
        return True

    def delete_unit(self, unit):
        """Deletes a unit."""
        unit = self.find_unit_by_id(unit.unit_id)
        if not unit:
            return False
        for lesson in self.get_lessons(unit.unit_id):
            self.delete_lesson(lesson)
        if verify.UNIT_TYPE_ASSESSMENT == unit.type:
            self._delete_assessment(unit)
        self._units.remove(unit)
        self._index(self._lessons)
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

        self._index(self._lessons)
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

        self._index(self._lessons)

    def set_assessment_content(self, unit, assessment_content, errors=None):
        """Updates the content of an assessment."""
        if errors is None:
            errors = []

        path = self._app_context.fs.impl.physical_to_logical(
            self.get_assessment_filename(unit.unit_id))
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
            is_draft=False)

    def import_from(self, src_course, errors):
        """Imports a content of another course into this course."""

        def copy_unit12_into_unit13(src_unit, dst_unit):
            """Copies unit object attributes between versions."""
            dst_unit.title = src_unit.title
            dst_unit.release_date = src_unit.release_date
            dst_unit.now_available = src_unit.now_available

            if verify.UNIT_TYPE_LINK == src_unit.type:
                dst_unit.href = src_unit.href

            # Copy over the assessment. Note that we copy files directly and
            # avoid all logical validations of their content. This is done for a
            # purpose - at this layer we don't care what is in those files.
            if verify.UNIT_TYPE_ASSESSMENT == dst_unit.type:
                src_filename = os.path.join(
                    src_course.app_context.get_home(),
                    src_course.get_assessment_filename(src_unit.unit_id))
                if src_course.app_context.fs.isfile(src_filename):
                    astream = src_course.app_context.fs.open(src_filename)
                    if astream:
                        dst_filename = os.path.join(
                            self.app_context.get_home(),
                            self.get_assessment_filename(dst_unit.unit_id))
                        self.app_context.fs.put(dst_filename, astream)

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
            copy_unit12_into_unit13(unit, new_unit)
            for lesson in src_course.get_lessons(unit.unit_id):
                new_lesson = self.add_lesson(new_unit, lesson.title)
                copy_lesson12_into_lesson13(unit, lesson, new_unit, new_lesson)

        return src_course, self


class Course(object):
    """Manages a course and all of its components."""

    @classmethod
    def get_environ(cls, app_context):
        """Returns currently defined course settings as a dictionary."""
        course_data_filename = app_context.get_config_filename()
        try:
            course_yaml = app_context.fs.open(course_data_filename)
            if not course_yaml:
                return DEFAULT_COURSE_YAML_DICT
            course_yaml_dict = yaml.safe_load(
                course_yaml.read().decode('utf-8'))
            if not course_yaml_dict:
                return DEFAULT_COURSE_YAML_DICT
            return deep_dict_merge(
                course_yaml_dict, DEFAULT_EXISTING_COURSE_YAML_DICT)
        except Exception:
            logging.info('Error: course.yaml file at %s not accessible',
                         course_data_filename)
            raise

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

    @property
    def app_context(self):
        return self._app_context

    def to_json(self):
        """Creates JSON representation of this instance."""
        model = copy.deepcopy(self._model)
        del model._app_context
        return transforms.dumps(
            model,
            indent=4, sort_keys=True,
            default=lambda o: o.__dict__)

    def get_progress_tracker(self):
        if not self._tracker:
            self._tracker = progress.UnitLessonCompletionTracker(self)
        return self._tracker

    def get_units(self):
        return self._model.get_units()

    def get_lessons(self, unit_id):
        return self._model.get_lessons(unit_id)

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
        # This can be replaced with a custom definition of an overall score.
        # TODO(sll): If the unit id is not 'Mid' or 'Fin', this is not going to
        # work. Fix this more generically.
        score_list = self.get_all_scores(student)
        overall_score = 0
        for unit in score_list:
            if unit['id'] == 'Mid' and unit['score']:
                overall_score += 0.3 * unit['score']
            if unit['id'] == 'Fin' and unit['score']:
                overall_score += 0.7 * unit['score']
        return int(overall_score)

    def get_overall_result(self, student):
        """Gets the overall result based on a student's score profile."""
        # This can be replaced with a custom definition for an overall result
        # string.
        return 'pass' if self.get_overall_score(student) >= 70 else 'fail'

    def get_all_scores(self, student):
        """Gets all score data for a student.

        Args:
            student: the student whose scores should be retrieved.

        Returns:
            an array of dicts, each representing an assessment. Each dict has
            the keys 'id', 'title' and 'score' (if available), representing the
            unit id, the assessment title, and the assessment score.
        """
        assessment_list = self.get_assessment_list()
        scores = transforms.loads(student.scores) if student.scores else {}

        assessment_score_list = [{
            'id': str(unit.unit_id),
            'title': unit.title,
            'score': (scores[str(unit.unit_id)]
                      if str(unit.unit_id) in scores else 0),
        } for unit in assessment_list]

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

    def get_assessment_filename(self, unit_id):
        return self._model.get_assessment_filename(unit_id)

    def get_activity_filename(self, unit_id, lesson_id):
        return self._model.get_activity_filename(unit_id, lesson_id)

    def reorder_units(self, order_data):
        return self._model.reorder_units(order_data)

    def set_assessment_content(self, unit, assessment_content, errors=None):
        return self._model.set_assessment_content(
            unit, assessment_content, errors)

    def set_activity_content(self, lesson, activity_content, errors=None):
        return self._model.set_activity_content(
            lesson, activity_content, errors)

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
