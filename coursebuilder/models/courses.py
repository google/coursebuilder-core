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
    unit_stream = app_context.fs.open(unit_file)
    lesson_stream = app_context.fs.open(lesson_file)
    if not unit_stream and not lesson_stream:
        return [], []

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


class UnitLessonProgressTracker(object):
    """Progress tracker for a unit/lesson-based linear course."""

    PROPERTY_KEY = 'linear-course-progress'

    # Here are representative examples of the keys for the various entities
    # used in this class:
    #   Unit 1: u.1
    #   Unit 1, Lesson 1: u.1.l.1
    #   Unit 1, Lesson 1, Video 1: u.1.l.1.v.1
    #   Unit 1, Lesson 1, Activity 2: u.1.l.1.a.2
    #   Unit 1, Lesson 1, Activity 2, Block 4: u.1.l.1.a.2.b.4
    #   Assessment 'Pre': s.Pre
    # At the moment, we do not divide assessments into blocks.
    EVENT_CODE_MAPPING = {
        'unit': 'u',
        'lesson': 'l',
        'video': 'v',
        'activity': 'a',
        'block': 'b',
        'assessment': 's',
    }

    def __init__(self, course):
        self._course = course

    def _get_course(self):
        return self._course

    def _get_unit_key(self, unit_id):
        return '%s.%s' % (self.EVENT_CODE_MAPPING['unit'], unit_id)

    def _get_lesson_key(self, unit_id, lesson_id):
        return '%s.%s.%s.%s' % (
            self.EVENT_CODE_MAPPING['unit'], unit_id,
            self.EVENT_CODE_MAPPING['lesson'], lesson_id
        )

    def _get_video_key(self, unit_id, lesson_id, video_id):
        return '%s.%s.%s.%s.%s.%s' % (
            self.EVENT_CODE_MAPPING['unit'], unit_id,
            self.EVENT_CODE_MAPPING['lesson'], lesson_id,
            self.EVENT_CODE_MAPPING['video'], video_id
        )

    def _get_activity_key(self, unit_id, lesson_id, activity_id):
        return '%s.%s.%s.%s.%s.%s' % (
            self.EVENT_CODE_MAPPING['unit'], unit_id,
            self.EVENT_CODE_MAPPING['lesson'], lesson_id,
            self.EVENT_CODE_MAPPING['activity'], activity_id
        )

    def _get_block_key(self, unit_id, lesson_id, activity_id, block_id):
        return '%s.%s.%s.%s.%s.%s.%s.%s' % (
            self.EVENT_CODE_MAPPING['unit'], unit_id,
            self.EVENT_CODE_MAPPING['lesson'], lesson_id,
            self.EVENT_CODE_MAPPING['activity'], activity_id,
            self.EVENT_CODE_MAPPING['block'], block_id
        )

    def _get_assessment_key(self, assessment_id):
        return '%s.%s' % (self.EVENT_CODE_MAPPING['assessment'], assessment_id)

    def update_unit(self, progress, event_key):
        """Updates a unit's progress if all its lessons have been completed."""
        split_event_key = event_key.split('.')
        assert len(split_event_key) == 2
        unit_id = split_event_key[1]

        # Check that all lessons in this unit have been completed.
        lessons = self._get_course().get_lessons(unit_id)
        for lesson in lessons:
            # Skip lessons that do not have activities associated with them.
            if lesson.activity != 'yes':
                continue
            if not self.is_lesson_completed(progress, unit_id, lesson.id):
                return

        self._inc(progress, self._get_unit_key(unit_id))

    def update_lesson(self, progress, event_key):
        """Updates a lesson's progress if its activities have been completed."""
        split_event_key = event_key.split('.')
        assert len(split_event_key) == 4
        unit_id = split_event_key[1]
        lesson_id = int(split_event_key[3])

        lessons = self._get_course().get_lessons(unit_id)
        for lesson in lessons:
            if lesson.id == lesson_id and lesson.activity == 'yes':
                if not self.is_activity_completed(progress, unit_id, lesson_id):
                    return

        self._inc(progress, self._get_lesson_key(unit_id, lesson_id))

    def update_activity(self, progress, event_key):
        """Updates activity's progress when all interactive blocks are done."""
        split_event_key = event_key.split('.')
        assert len(split_event_key) == 6
        unit_id = split_event_key[1]
        lesson_id = split_event_key[3]
        activity_id = 0

        # Get the activity corresponding to this unit/lesson combination.
        activity = verify.Verifier().get_activity_as_python(unit_id, lesson_id)
        for block_id in range(len(activity['activity'])):
            block = activity['activity'][block_id]
            if isinstance(block, dict):
                if not self.is_block_completed(
                        progress, unit_id, lesson_id, block_id):
                    return
        self._inc(progress, self._get_activity_key(
            unit_id, lesson_id, activity_id))

    UPDATER_MAPPING = {
        'activity': update_activity,
        'lesson': update_lesson,
        'unit': update_unit
    }

    # Dependencies for recording derived events. The key is the current
    # event, and the value is a tuple, each element of which contains:
    # - the type of the derived event to be updated
    # - the event updating function to be called
    # - the transformation to apply to the id of the current event to get the
    #       id for the new event
    DERIVED_EVENTS = {
        'block': (
            {
                'type': 'activity',
                'generate_new_id': (lambda s: '.'.join(s.split('.')[:-2])),
            },
        ),
        'activity': (
            {
                'type': 'lesson',
                'generate_new_id': (lambda s: '.'.join(s.split('.')[:-2])),
            },
        ),
        'lesson': (
            {
                'type': 'unit',
                'generate_new_id': (lambda s: '.'.join(s.split('.')[:-2])),
            },
        ),
    }

    def _put_completion_event(self, student, event_type, event_key):
        """Records an event when part of a course is completed."""
        if event_type not in self.EVENT_CODE_MAPPING:
            return

        progress = self.get_or_create_progress(student)

        self.update_event(student, progress, event_type, event_key, True)

        progress.updated_on = datetime.datetime.now()
        progress.put()

    def put_video_completed(self, student, unit_id, lesson_id):
        """Records that the given student has completed a video."""
        self._put_completion_event(
            student, 'video', self._get_video_key(unit_id, lesson_id, 0))

    def put_activity_completed(self, student, unit_id, lesson_id):
        """Records that the given student has completed an activity."""
        self._put_completion_event(
            student, 'activity', self._get_activity_key(unit_id, lesson_id, 0))

    def put_block_completed(self, student, unit_id, lesson_id, block_id):
        """Records that the given student has completed an activity block."""
        self._put_completion_event(
            student, 'block', self._get_block_key(
                unit_id, lesson_id, 0, block_id))

    def put_assessment_completed(self, student, assessment_type):
        """Records that the given student has completed the given assessment."""
        self._put_completion_event(
            student, 'assessment', self._get_assessment_key(assessment_type))

    def put_activity_accessed(self, student, unit_id, lesson_id):
        """Records that the given student has accessed this activity."""
        # TODO(sll): This method currently exists because (in the two-state
        # completed-or-not model) we need to mark activities without
        # interactive blocks as 'completed' when they are accessed. Change this
        # to also mark activities as accessed.

        # Get the activity corresponding to this unit/lesson combination.
        activity = verify.Verifier().get_activity_as_python(unit_id, lesson_id)
        interactive = False
        for block_id in range(len(activity['activity'])):
            block = activity['activity'][block_id]
            if isinstance(block, dict):
                interactive = True
                break
        if not interactive:
            self.put_activity_completed(student, unit_id, lesson_id)

    def update_event(self, student, progress, event_type, event_key,
                     direct_update=False):
        """Updates statistics for the given event, and for derived events.

        Args:
          student: the student
          progress: the StudentProgressEntity for the student
          event_type: the name of the recorded event
          event_key: the key for the recorded event
          direct_update: True if this event is being updated explicitly; False
              if it is being auto-updated.
        """
        if direct_update or event_type not in self.UPDATER_MAPPING:
            self._inc(progress, event_key)
        else:
            self.UPDATER_MAPPING[event_type](self, progress, event_key)

        if event_type in self.DERIVED_EVENTS:
            for derived_event in self.DERIVED_EVENTS[event_type]:
                self.update_event(
                    student,
                    progress,
                    derived_event['type'],
                    derived_event['generate_new_id'](event_key),
                )

    def _is_entity_completed(self, progress, event_key):
        if not progress.value:
            return None
        value = json.loads(progress.value).get(event_key)
        return value is not None and value > 0

    def is_unit_completed(self, progress, unit_id):
        return self._is_entity_completed(progress, self._get_unit_key(unit_id))

    def is_lesson_completed(self, progress, unit_id, lesson_id):
        return self._is_entity_completed(
            progress, self._get_lesson_key(unit_id, lesson_id))

    def is_video_completed(self, progress, unit_id, lesson_id):
        return self._is_entity_completed(
            progress, self._get_video_key(unit_id, lesson_id, 0))

    def is_activity_completed(self, progress, unit_id, lesson_id):
        return self._is_entity_completed(
            progress, self._get_activity_key(unit_id, lesson_id, 0))

    def is_block_completed(self, progress, unit_id, lesson_id, block_id):
        return self._is_entity_completed(
            progress, self._get_block_key(unit_id, lesson_id, 0, block_id))

    def is_assessment_completed(self, progress, assessment_type):
        return self._is_entity_completed(
            progress, self._get_assessment_key(assessment_type))

    @classmethod
    def get_or_create_progress(cls, student):
        progress = StudentPropertyEntity.get(student, cls.PROPERTY_KEY)
        if not progress:
            progress = StudentPropertyEntity.create(
                student=student, property_name=cls.PROPERTY_KEY)
            progress.put()
        return progress

    def get_unit_progress(self, student):
        """Returns a dict saying which units are completed."""
        units = self._get_course().get_units()
        progress = self.get_or_create_progress(student)

        result = {}
        for unit in units:
            if (unit.type == 'A' and
                self.is_assessment_completed(progress, unit.unit_id)):
                result[unit.unit_id] = True
            elif (unit.type == 'U' and
                  self.is_unit_completed(progress, unit.unit_id)):
                result[unit.unit_id] = True

        return result

    def get_lesson_progress(self, unused_student, unused_unit_id):
        """Returns a dict saying which lessons in this unit are completed."""
        raise Exception('Not implemented yet.')

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
