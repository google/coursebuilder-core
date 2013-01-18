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

import logging
import os
from tools import verify
from models import MemcacheManager


class Course(object):
    """Manages a course and all of its components."""

    # The course content files may change between deployment. To avoid reading
    # old cached values by the new version of the application we add deployment
    # version to the key. Now each version of the application can put/get its
    # own version of the course.
    memcache_key = 'course-%s' % os.environ.get('CURRENT_VERSION_ID')

    def __init__(self, handler):
        self._app_context = handler.app_context
        self._loaded = False
        self._units = []
        self._lessons = []
        self._unit_id_to_lessons = {}

    def _reindex(self):
        """Groups all lessons by unit_id."""
        for lesson in self._lessons:
            key = str(lesson.unit_id)
            if not key in self._unit_id_to_lessons:
                self._unit_id_to_lessons[key] = []
            self._unit_id_to_lessons[key].append(lesson)

    def _load_from_memcache(self):
        """Loads course representation from memcache."""
        try:
            envelope = MemcacheManager.get(self.memcache_key)
            if envelope:
                self._units = envelope.units
                self._lessons = envelope.lessons
                self._reindex()

                self._loaded = True
        except Exception as e:  # pylint: disable-msg=broad-except
            logging.error(
                'Failed to load course \'%s\' from memcache. %s',
                self.memcache_key, e)

    def _save_to_memcache(self):
        """Saves course representation into memcache."""
        envelope = SerializableCourseEnvelope()
        envelope.units = self._units
        envelope.lessons = self._lessons
        MemcacheManager.set(self.memcache_key, envelope)

    def _rebuild_from_source(self):
        """Loads course data from persistence storage into this instance."""
        self._units, self._lessons = load_csv_course(
            self._app_context.get_data_home())
        self._reindex()
        self._loaded = True

    def _materialize(self):
        """Loads data from persistence into this instance."""
        if not self._loaded:
            self._load_from_memcache()
            if not self._loaded:
                self._rebuild_from_source()
                self._save_to_memcache()
                # TODO(psimakov): and if loading fails, then what?

    def get_units(self):
        self._materialize()
        return self._units

    def get_lessons(self, unit_id):
        self._materialize()
        return self._unit_id_to_lessons[str(unit_id)]


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


def load_csv_course(data_folder):
    """Loads course data from the CSV files."""
    logging.info('Initializing datastore from CSV files')

    unit_file = os.path.join(data_folder, 'unit.csv')
    lesson_file = os.path.join(data_folder, 'lesson.csv')

    # Load and validate data from CSV files.
    units = verify.read_objects_from_csv_file(
        unit_file, verify.UNITS_HEADER, verify.Unit)
    lessons = verify.read_objects_from_csv_file(
        lesson_file, verify.LESSONS_HEADER, verify.Lesson)
    verifier = verify.Verifier()
    verifier.verify_unit_fields(units)
    verifier.verify_lesson_fields(lessons)
    verifier.verify_unit_lesson_relationships(units, lessons)
    assert verifier.errors == 0
    assert verifier.warnings == 0

    # Load data from CSV files into a datastore.
    new_units = []
    new_lessons = []
    units = verify.read_objects_from_csv_file(
        unit_file, verify.UNITS_HEADER, Unit)
    lessons = verify.read_objects_from_csv_file(
        lesson_file, verify.LESSONS_HEADER, Lesson)
    for unit in units:
        entity = Unit()
        copy_attributes(unit, entity, verify.UNIT_CSV_TO_DB_CONVERTER)
        new_units.append(entity)
    for lesson in lessons:
        entity = Lesson()
        copy_attributes(lesson, entity, verify.LESSON_CSV_TO_DB_CONVERTER)
        new_lessons.append(entity)

    return new_units, new_lessons
