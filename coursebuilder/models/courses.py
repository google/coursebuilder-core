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


COURSE_MODEL_VERSION_1_2 = '1.2'
COURSE_MODEL_VERSION_1_3 = '1.3'


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


class ImportExport(object):
    """All migration routines are here."""

    @classmethod
    def upgrade_1_2_to_1_3(cls, course):
        """Upgrades 1.2 course structure into 1.3."""

        # This upgrade has no steps.

        # pylint: disable-msg=protected-access
        course._version = COURSE_MODEL_VERSION_1_3

    @classmethod
    def copy_activities(cls, src_course, dst_course):
        """Copies activities from one course to another."""
        next_id = 1
        for aunit in src_course.get_units():
            if verify.UNIT_TYPE_UNIT != aunit.type:
                continue
            for alesson in src_course.get_lessons(aunit.id):
                if not alesson.activity:
                    continue
                src_filename = os.path.join(
                    src_course.app_context.get_asset_home(),
                    'js/activity-%s.%s.js' % (aunit.id, alesson.id))
                if not src_course.app_context.fs.isfile(src_filename):
                    continue
                assessment_stream = src_course.app_context.fs.open(src_filename)
                if assessment_stream:
                    dst_filename = os.path.join(
                        dst_course.app_context.get_asset_home(),
                        'js/activity-%s.js' % next_id)
                    dst_course.app_context.fs.put(
                        dst_filename, assessment_stream)
                    alesson.activity_resource_id = next_id
                    next_id += 1

    @classmethod
    def copy_assessments(cls, src_course, dst_course):
        """Copies assessments from one course to another."""
        for aunit in src_course.get_units():
            if verify.UNIT_TYPE_ASSESSMENT != aunit.type:
                continue
            src_filename = os.path.join(
                src_course.app_context.get_asset_home(),
                'js/assessment-%s.js' % aunit.unit_id)
            if not src_course.app_context.fs.isfile(src_filename):
                continue
            assessment_stream = src_course.app_context.fs.open(src_filename)
            if assessment_stream:
                dst_filename = os.path.join(
                    dst_course.app_context.get_asset_home(),
                    'js/assessment-%s.js' % aunit.id)
                dst_course.app_context.fs.put(
                    dst_filename, assessment_stream)
                aunit.assessment_resource_id = aunit.id

    @classmethod
    def copy_linked_assets(cls, src_course, dst_course):
        """Copies linked assets from one course to another."""
        cls.copy_assessments(src_course, dst_course)
        cls.copy_activities(src_course, dst_course)

    @classmethod
    def import_course(cls, src, dst, errors):
        """Import course from one application context into another."""

        src_course = Course(None, app_context=src)
        dst_course = Course(None, app_context=dst)

        if not is_editable_fs(dst):
            errors.append(
                'Target course %s must be on read-write media.' % dst.raw)
            return

        if dst_course.get_units():
            errors.append('Target course %s must be empty.' % dst.raw)
            return

        # pylint: disable-msg=protected-access
        src_course._materialize()
        # pylint: disable-msg=protected-access
        dst_course._deserialize(src_course._serialize())
        cls.copy_linked_assets(src_course, dst_course)
        # pylint: disable-msg=protected-access
        dst_course._save()


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

    def __init__(self, handler, app_context=None):
        self._app_context = app_context if app_context else handler.app_context
        self._loaded = False
        self._student_progress_tracker = (
            progress.UnitLessonProgressTracker(self))
        self._namespace = self._app_context.get_namespace_name()
        self._version = COURSE_MODEL_VERSION_1_3

        self._units = []
        self._lessons = []
        self._unit_id_to_lessons = {}

    @property
    def app_context(self):
        return self._app_context

    @property
    def version(self):
        return self._version

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
        if COURSE_MODEL_VERSION_1_3 != self._version:
            raise Exception('Unsupported course version %s, expected %s.' % (
                self._version, COURSE_MODEL_VERSION_1_3))
        envelope = SerializableCourseEnvelope()
        envelope.version = self._version
        envelope.units = self._units
        envelope.lessons = self._lessons
        return pickle.dumps(envelope)

    def _deserialize(self, binary_data):
        """Populates this instance with a serialized representation data."""
        envelope = pickle.loads(binary_data)
        if COURSE_MODEL_VERSION_1_3 != envelope.version:
            raise Exception('Unsupported course version %s, expected %s.' % (
                envelope.version, COURSE_MODEL_VERSION_1_3))
        self._units = envelope.units
        self._lessons = envelope.lessons
        self._reindex()

    def _rebuild_from_source(self):
        """Loads course data from persistence storage into this instance."""
        units, lessons = load_csv_course(self._app_context)
        if units and lessons:
            self._version = COURSE_MODEL_VERSION_1_2
            self._units = units
            self._lessons = lessons
            self._reindex()
            ImportExport.upgrade_1_2_to_1_3(self)
            return

        if is_editable_fs(self._app_context):
            fs = self._app_context.fs.impl
            filename = fs.physical_to_logical(self.COURSES_FILENAME)
            if self._app_context.fs.isfile(filename):
                self._deserialize(self._app_context.fs.get(filename))
                return

        # Init new empty instance.
        self._units = []
        self._lessons = []
        self._reindex()

    def _load_from_memcache(self):
        """Loads course representation from memcache."""
        try:
            binary_data = MemcacheManager.get(
                self.memcache_key, namespace=self._namespace)
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
                MemcacheManager.set(
                    self.memcache_key, self._serialize(),
                    namespace=self._namespace)
                self._loaded = True

    def _save(self):
        """Save data from this instance into persistence."""
        binary_data = self._serialize()
        fs = self._app_context.fs.impl
        filename = fs.physical_to_logical(self.COURSES_FILENAME)
        self._app_context.fs.put(
            filename, vfs.FileStreamWrapped(None, binary_data))
        MemcacheManager.delete(self.memcache_key, namespace=self._namespace)

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

    def get_assessment_url(self, unit_id):
        """Returns assessment URL for direct fetching."""
        unit = self.find_unit_by_id(unit_id)
        assert verify.UNIT_TYPE_ASSESSMENT == unit.type
        if unit.assessment_resource_id:
            resource_id = unit.assessment_resource_id
        else:
            resource_id = unit.unit_id
        return 'assets/js/assessment-%s.js' % resource_id

    def get_activity_url(self, unit_id, lesson_id):
        """Returns activity URL for direct fetching."""
        lesson = self.find_lesson_by_id(unit_id, lesson_id)
        if lesson.activity_resource_id:
            return 'assets/js/activity-%s.js' % lesson.activity_resource_id
        else:
            return 'assets/js/activity-%s.%s.js' % (
                unit_id, lesson_id)


class SerializableCourseEnvelope(object):
    """A serializable, data-only representation of a Course."""

    def __init__(self):
        self.version = None
        self.units = []
        self.lessons = []


class Unit(object):
    """An object to represent a Unit, Assessment or Link."""

    def __init__(self):
        self.id = 0
        self.type = ''
        self.unit_id = ''
        self.title = ''
        self.release_date = ''
        self.now_available = False
        self.assessment_resource_id = None


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
        self.activity_resource_id = None


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
