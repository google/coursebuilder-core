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
from tools import verify
import yaml
from models import MemcacheManager
import progress
import vfs


DEFAULT_COURSE_YAML_DICT = {
    'course': {'title': 'UNTITLED COURSE', 'locale': 'en_US', 'main_image': {}},
    'base': {'show_gplus_button': True},
    'institution': {'logo': {}, 'url': ''},
    'preview': {},
    'reg_form': {'can_register': True}
}


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


def is_editable_fs(app_context):
    return isinstance(app_context.fs.impl, vfs.DatastoreBackedFileSystem)


class Course(object):
    """Manages a course and all of its components."""

    # A logical filename where we persist courses data."""
    COURSES_FILENAME = '/data/course.pickle'

    # The course content files may change between deployment. To avoid reading
    # old cached values by the new version of the application we add deployment
    # version to the key. Now each version of the application can put/get its
    # own version of the course.
    memcache_key = 'course-%s' % os.environ.get('CURRENT_VERSION_ID')

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
            return deep_dict_merge(course_yaml_dict, DEFAULT_COURSE_YAML_DICT)
        except Exception:
            logging.info('Error: course.yaml file at %s not accessible',
                         course_data_filename)
            raise

    def __init__(self, handler):
        self._app_context = handler.app_context
        self._loaded = False
        self._units = []
        self._lessons = []
        self._unit_id_to_lessons = {}
        self._student_progress_tracker = (
            progress.UnitLessonProgressTracker(self))

    def _reindex(self):
        """Groups all lessons by unit_id."""
        self._unit_id_to_lessons = {}
        for lesson in self._lessons:
            key = str(lesson.unit_id)
            if not key in self._unit_id_to_lessons:
                self._unit_id_to_lessons[key] = []
            self._unit_id_to_lessons[key].append(lesson)

    def _serialize(self):
        """Creates bytes of a serialized representation of this instance."""
        envelope = SerializableCourseEnvelope()
        envelope.units = self._units
        envelope.lessons = self._lessons
        return pickle.dumps(envelope)

    def _deserialize(self, binary_data):
        """Populates this instance with a serialized representation data."""
        envelope = pickle.loads(binary_data)
        self._units = envelope.units
        self._lessons = envelope.lessons

        self._reindex()

    def _rebuild_from_csv_files(self):
        """Rebuilds this instance from CSV files."""
        self._units, self._lessons = load_csv_course(self._app_context)
        self._reindex()

    def _init_new(self):
        """Units new empty instance."""
        self._units = []
        self._lessons = []
        self._reindex()

    def _rebuild_from_source(self):
        """Loads course data from persistence storage into this instance."""
        units, lessons = load_csv_course(self._app_context)
        if units and lessons:
            self._units = units
            self._lessons = lessons
            self._reindex()
            return

        if is_editable_fs(self._app_context):
            fs = self._app_context.fs.impl
            filename = fs.physical_to_logical(self.COURSES_FILENAME)
            if self._app_context.fs.isfile(filename):
                self._deserialize(self._app_context.fs.get(filename))
                return

        self._init_new()

    def _load_from_memcache(self):
        """Loads course representation from memcache."""
        try:
            binary_data = MemcacheManager.get(self.memcache_key)
            if binary_data:
                self._deserialize(binary_data)
                self._loaded = True
        except Exception as e:  # pylint: disable-msg=broad-except
            logging.error(
                'Failed to load course \'%s\' from memcache. %s',
                self.memcache_key, e)

    def _materialize(self):
        """Loads data from persistence into this instance."""
        if not self._loaded:
            self._load_from_memcache()
            if not self._loaded:
                self._rebuild_from_source()
                MemcacheManager.set(self.memcache_key, self._serialize())
                self._loaded = True

    def _save(self):
        """Save data from this instance into persistence."""
        binary_data = self._serialize()
        fs = self._app_context.fs.impl
        filename = fs.physical_to_logical(self.COURSES_FILENAME)
        self._app_context.fs.put(
            filename, vfs.FileStreamWrapped(None, binary_data))
        MemcacheManager.delete(self.memcache_key)

    def get_units(self):
        self._materialize()
        return self._units

    def get_lessons(self, unit_id):
        self._materialize()
        lessons = self._unit_id_to_lessons.get(str(unit_id))
        if not lessons:
            return []
        return lessons

    def get_progress_tracker(self):
        return self._student_progress_tracker

    def find_unit_by_id(self, uid):
        """Finds a unit given its unique id."""
        for unit in self.get_units():
            if str(unit.id) == str(uid):
                return unit
        return None

    def find_lesson_by_id(self, unit_id, lesson_id):
        """Find a given lesson by its id and the id of its parent unit."""
        for lesson in self.get_lessons(unit_id):
            if str(lesson.id) == str(lesson_id):
                return lesson
        return None

    def _get_max_id_used(self):
        """Finds max id used by a unit of the course."""
        max_id = 0
        for unit in self.get_units():
            if unit.id > max_id:
                max_id = unit.id
        return max_id

    def _add_generic_unit(self, unit_type, title=None):
        assert unit_type in verify.UNIT_TYPES

        unit = Unit()
        unit.type = unit_type
        unit.id = self._get_max_id_used() + 1
        unit.title = title
        unit.now_available = False

        self.get_units().append(unit)
        self._save()

        return unit

    def add_unit(self):
        """Adds new unit to a course."""
        return self._add_generic_unit('U', 'New Unit')

    def add_link(self):
        """Adds new link (other) to a course."""
        return self._add_generic_unit('O', 'New Link')

    def add_assessment(self):
        """Adds new assessment to a course."""
        return self._add_generic_unit('A', 'New Assessment')

    @staticmethod
    def get_assessment_filename(unit):
        """Returns the filename for the assessment JS in the VFS."""
        return 'assessment-%d.js' % unit.id

    def delete_unit(self, unit):
        """Deletes existing unit."""
        unit = self.find_unit_by_id(unit.id)
        if unit:
            self.get_units().remove(unit)
            self._save()
            return True
        return False

    def put_unit(self, unit):
        """Updates existing unit."""
        units = self.get_units()
        for index, current in enumerate(units):
            if str(unit.id) == str(current.id):
                units[index] = unit
                self._save()
                return True
        return False

    def reorder_units(self, order_data):
        """Reorder the units and lessons based on the order data given.

        Args:
            order_data: list of dict. Format is
                The order_data is in the following format:
                [
                    {'id': 0, 'lessons': [{'id': 0}, {'id': 1}, {'id': 2}]},
                    {'id': 0, 'lessons': []},
                    {'id': 0, 'lessons': [{'id': 0}, {'id': 1}]}
                    ...
                ]
        """
        reordered_units = []
        unit_ids = set()
        for unit_data in order_data:
            unit_id = unit_data['id']
            reordered_units.append(self.find_unit_by_id(unit_id))
            unit_ids.add(unit_id)
        assert len(unit_ids) == len(self._units)
        self._units = reordered_units

        reordered_lessons = []
        lesson_ids = set()
        for unit_data in order_data:
            unit_id = unit_data['id']
            for lesson_data in unit_data['lessons']:
                lesson_id = lesson_data['id']
                reordered_lessons.append(
                    self.find_lesson_by_id(unit_id, lesson_id))
                lesson_ids.add((unit_id, lesson_id))
        assert len(lesson_ids) == len(self._lessons)
        self._lessons = reordered_lessons

        self._reindex()
        self._save()


class SerializableCourseEnvelope(object):
    """A serializable, data-only representation of a Course."""

    def __init__(self):
        self.units = []
        self.lessons = []


class Unit(object):
    """An object to represent a Unit."""

    def __init__(self):
        self.id = 0
        self.type = ''
        self.unit_id = ''
        self.title = ''
        self.release_date = ''
        self.now_available = False


class Lesson(object):
    """An object to represent a Lesson."""

    def __init__(self):
        self.unit_id = 0
        self.id = 0
        self.title = ''
        self.objectives = ''
        self.video = ''
        self.notes = ''
        self.duration = ''
        self.activity = ''
        self.activity_title = ''


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
    logging.info('Initializing datastore from CSV files')

    unit_file = os.path.join(app_context.get_data_home(), 'unit.csv')
    lesson_file = os.path.join(app_context.get_data_home(), 'lesson.csv')

    # Load and validate data from CSV files.
    unit_stream = app_context.fs.open(unit_file)
    lesson_stream = app_context.fs.open(lesson_file)
    if not unit_stream and not lesson_stream:
        return None, None

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
    new_units = []
    new_lessons = []
    units = verify.read_objects_from_csv_stream(
        app_context.fs.open(unit_file), verify.UNITS_HEADER, Unit)
    lessons = verify.read_objects_from_csv_stream(
        app_context.fs.open(lesson_file), verify.LESSONS_HEADER, Lesson)
    for unit in units:
        entity = Unit()
        copy_attributes(unit, entity, verify.UNIT_CSV_TO_DB_CONVERTER)
        new_units.append(entity)
    for lesson in lessons:
        entity = Lesson()
        copy_attributes(lesson, entity, verify.LESSON_CSV_TO_DB_CONVERTER)
        new_lessons.append(entity)

    return new_units, new_lessons
