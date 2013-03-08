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

import datetime
import json
import logging
import os
from tools import verify

from models import MemcacheManager
from models import StudentPropertyEntity


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
        self._student_progress_tracker = UnitLessonProgressTracker(self)

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
        self._units, self._lessons = load_csv_course(self._app_context)
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

    def get_progress_tracker(self):
        return self._student_progress_tracker


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
    units = verify.read_objects_from_csv_stream(
        app_context.fs.open(unit_file), verify.UNITS_HEADER, verify.Unit)
    lessons = verify.read_objects_from_csv_stream(
        app_context.fs.open(lesson_file), verify.LESSONS_HEADER, verify.Lesson)
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


class UnitLessonProgressTracker(object):
    """Progress tracker for a unit/lesson-based linear course."""

    PROPERTY_KEY = 'linear-course-progress'

    EVENT_CODE_MAPPING = {'activity': 'a',
                          'assessment': 's',
                          'lesson': 'l',
                          'unit': 'u',
                          'video': 'v'}

    # Dependencies for recording derived events. The key is the current
    # event, and the value is a tuple, each element of which contains:
    # - the name of the derived event
    # - the transformation to apply to the id of the current event to get the
    #       id for the new event
    DERIVED_EVENTS = {
        'activity': (
            {
                'type': 'lesson',
                'generate_new_id': (lambda s: s),
            },
        ),
        'lesson': (
            {
                'type': 'unit',
                'generate_new_id': (lambda s: '.'.join(s.split('.')[:-2])),
            },
        ),
    }

    def __init__(self, course):
        self._course = course

    def get_course(self):
        return self._course

    def update_lesson(self, student, event_key):
        """Update this lesson if its activity has been completed."""
        # TODO(sll): Implement this.
        pass

    def update_unit(self, student, event_key):
        """Updates a unit's progress if all its lessons have been completed."""

        unit_id = event_key.split('.')[1]

        progress = self.get_progress(student)
        if not progress:
            progress = StudentPropertyEntity.create(
                student=student, property_name=self.PROPERTY_KEY)

        # Check that all lessons in this unit have been completed.
        for lesson in self.get_course().get_lessons(unit_id):
            lesson_key = '%s.%s.%s.%s' % (
                self.EVENT_CODE_MAPPING['unit'],
                unit_id,
                self.EVENT_CODE_MAPPING['lesson'],
                lesson.id,
            )
            lesson_progress = progress.get(lesson_key)
            if lesson_progress is None or lesson_progress <= 0:
                return

        self._inc(
            progress,
            '%s.%s' % (self.EVENT_CODE_MAPPING['unit'], unit_id))

    DERIVED_EVENT_UPDATER = {'lesson': update_lesson,
                             'unit': update_unit}

    def _inc(self, student_property, key, value=1):
        """Increments the integer value of a student property.

        Note: this method does not commit the change. The calling method should
        call put() on the StudentPropertyEntity.

        Args:
          student_property: the StudentPropertyEntity
          key: the student property whose value should be incremented
          value: the value to increment this property by
        """

        try:
            progress_dict = json.loads(student_property.value)
        except TypeError:
            progress_dict = {}

        if key not in progress_dict:
            progress_dict[key] = 0

        progress_dict[key] += value
        student_property.value = json.dumps(progress_dict)

    def put_completion_event(self, student, event_type, unit_id=None,
                             event_source_id=None):
        """Records an event when part of a course is completed."""
        if event_type not in ['video', 'activity', 'assessment']:
            return

        if event_type == 'assessment':
            event_key = '%s.%s' % (self.EVENT_CODE_MAPPING['assessment'],
                                   event_source_id)
        elif event_type in ['video', 'activity']:
            event_key = '%s.%s.%s.%s' % (
                self.EVENT_CODE_MAPPING['unit'],
                unit_id,
                self.EVENT_CODE_MAPPING[event_type],
                event_source_id
            )

        student_progress = self.get_progress(student)
        if not student_progress:
            student_progress = StudentPropertyEntity.create(
                student=student, property_name=self.PROPERTY_KEY)

        self._inc(student_progress, event_key)

        if event_type in self.DERIVED_EVENTS:
            for derived_event in self.DERIVED_EVENTS[event_type]:
                self.update_derived_events(
                    student,
                    derived_event['type'],
                    derived_event['generate_new_id'](event_key))

        student_progress.updated_on = datetime.datetime.now()
        student_progress.put()

    def put_assessment_completed(self, student, assessment_type):
        """Records that the given student has completed the given assessment."""
        self.put_completion_event(
            student, 'assessment', None, assessment_type)

    def update_derived_events(self, student, event_type, event_key):
        if event_type in self.DERIVED_EVENT_UPDATER:
            self.DERIVED_EVENT_UPDATER[event_type](
                self, student, event_key)

            if event_type in self.DERIVED_EVENTS:
                for derived_event in self.DERIVED_EVENTS[event_type]:
                    self.update_derived_events(
                        student,
                        derived_event['type'],
                        derived_event['generate_new_id'](event_key))

    def is_assessment_completed(self, progress, assessment_type):
        assessment_event_key = '%s.%s' % (
            self.EVENT_CODE_MAPPING['assessment'], assessment_type)
        value = json.loads(progress.value).get(assessment_event_key)
        return value is not None and value > 0

    @classmethod
    def get_progress(cls, student):
        return StudentPropertyEntity.get(student, cls.PROPERTY_KEY)

    def get_unit_progress(self, student):
        """Returns a dict saying which units are completed."""
        units = self.get_course().get_units()
        progress = self.get_progress(student)
        if progress is None:
            return {}

        result = {}
        for unit in units:
            if (unit.type == 'A' and
                self.is_assessment_completed(progress, unit.unit_id)):
                result[unit.unit_id] = True
        return result
