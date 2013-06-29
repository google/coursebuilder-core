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

"""Student progress trackers."""

__author__ = 'Sean Lip (sll@google.com)'

import datetime
import os

from tools import verify
from models import StudentPropertyEntity

import transforms


class UnitLessonCompletionTracker(object):
    """Tracks student completion for a unit/lesson-based linear course."""

    PROPERTY_KEY = 'linear-course-completion'

    # Here are representative examples of the keys for the various entities
    # used in this class:
    #   Unit 1: u.1
    #   Unit 1, Lesson 1: u.1.l.1
    #   Unit 1, Lesson 1, Activity 0: u.1.l.1.a.0
    #   Unit 1, Lesson 1, Activity 0, Block 4: u.1.l.1.a.0.b.4
    #   Assessment 'Pre': s.Pre
    # At the moment, we do not divide assessments into blocks.
    #
    # The following keys were added in v1.5:
    #   Unit 1, Lesson 1, HTML: u.1.l.1.h.0
    #   Unit 1, Lesson 1, HTML, Component with instanceid id: u.1.l.1.h.0.c.id
    #
    # The number after the 'h' and 'a' codes is always zero, since a lesson may
    # have at most one HTML body and one activity.
    #
    # IMPORTANT NOTE: The values of the keys mean different things depending on
    # whether the entity is a composite entity or not.
    # If it is a composite entity (unit, lesson, activity), then the value is
    #   - 0 if none of its sub-entities has been completed
    #   - 1 if some, but not all, of its sub-entities have been completed
    #   - 2 if all its sub-entities have been completed.
    # If it is not a composite entity (i.e. block, assessment, component), then
    # the value is just the number of times the event has been triggered.

    # Constants for recording the state of composite entities.
    # TODO(sll): Change these to enums.
    NOT_STARTED_STATE = 0
    IN_PROGRESS_STATE = 1
    COMPLETED_STATE = 2

    EVENT_CODE_MAPPING = {
        'unit': 'u',
        'lesson': 'l',
        'activity': 'a',
        'html': 'h',
        'block': 'b',
        'assessment': 's',
        'component': 'c',
    }

    # Names of component tags that are tracked for progress calculations.
    TRACKABLE_COMPONENTS = frozenset([
        'question',
        'question-group',
    ])

    def __init__(self, course):
        self._course = course

    def _get_course(self):
        return self._course

    def get_activity_as_python(self, unit_id, lesson_id):
        """Gets the corresponding activity as a Python object."""
        root_name = 'activity'
        course = self._get_course()
        activity_text = course.app_context.fs.get(
            os.path.join(course.app_context.get_home(),
                         course.get_activity_filename(unit_id, lesson_id)))

        content, noverify_text = verify.convert_javascript_to_python(
            activity_text, root_name)
        activity = verify.evaluate_python_expression_from_text(
            content, root_name, verify.Activity().scope, noverify_text)
        return activity

    def _get_unit_key(self, unit_id):
        return '%s.%s' % (self.EVENT_CODE_MAPPING['unit'], unit_id)

    def _get_lesson_key(self, unit_id, lesson_id):
        return '%s.%s.%s.%s' % (
            self.EVENT_CODE_MAPPING['unit'], unit_id,
            self.EVENT_CODE_MAPPING['lesson'], lesson_id
        )

    def _get_activity_key(self, unit_id, lesson_id):
        return '%s.%s.%s.%s.%s.%s' % (
            self.EVENT_CODE_MAPPING['unit'], unit_id,
            self.EVENT_CODE_MAPPING['lesson'], lesson_id,
            self.EVENT_CODE_MAPPING['activity'], 0
        )

    def _get_html_key(self, unit_id, lesson_id):
        return '%s.%s.%s.%s.%s.%s' % (
            self.EVENT_CODE_MAPPING['unit'], unit_id,
            self.EVENT_CODE_MAPPING['lesson'], lesson_id,
            self.EVENT_CODE_MAPPING['html'], 0
        )

    def _get_component_key(self, unit_id, lesson_id, component_id):
        return '%s.%s.%s.%s.%s.%s.%s.%s' % (
            self.EVENT_CODE_MAPPING['unit'], unit_id,
            self.EVENT_CODE_MAPPING['lesson'], lesson_id,
            self.EVENT_CODE_MAPPING['html'], 0,
            self.EVENT_CODE_MAPPING['component'], component_id
        )

    def _get_block_key(self, unit_id, lesson_id, block_id):
        return '%s.%s.%s.%s.%s.%s.%s.%s' % (
            self.EVENT_CODE_MAPPING['unit'], unit_id,
            self.EVENT_CODE_MAPPING['lesson'], lesson_id,
            self.EVENT_CODE_MAPPING['activity'], 0,
            self.EVENT_CODE_MAPPING['block'], block_id
        )

    def _get_assessment_key(self, assessment_id):
        return '%s.%s' % (self.EVENT_CODE_MAPPING['assessment'], assessment_id)

    def get_valid_component_ids(self, unit_id, lesson_id):
        """Returns a list of dicts representing trackable components."""
        components = self._get_course().get_components(unit_id, lesson_id)
        return [cpt['instanceid'] for cpt in components if (
            cpt['name'] in self.TRACKABLE_COMPONENTS and
            cpt['instanceid'] is not None)]

    def get_valid_block_ids(self, unit_id, lesson_id):
        """Returns a list of block ids representing interactive activities."""
        valid_block_ids = []

        # Get the activity corresponding to this unit/lesson combination.
        activity = self.get_activity_as_python(unit_id, lesson_id)
        for block_id in range(len(activity['activity'])):
            block = activity['activity'][block_id]
            if isinstance(block, dict):
                valid_block_ids.append(block_id)

        return valid_block_ids

    def _update_unit(self, progress, event_key):
        """Updates a unit's progress if all its lessons have been completed."""
        split_event_key = event_key.split('.')
        assert len(split_event_key) == 2
        unit_id = split_event_key[1]

        if self._get_entity_value(progress, event_key) == self.COMPLETED_STATE:
            return

        # Record that at least one lesson in this unit has been completed.
        self._set_entity_value(progress, event_key, self.IN_PROGRESS_STATE)

        # Check if all lessons in this unit have been completed.
        lessons = self._get_course().get_lessons(unit_id)
        for lesson in lessons:
            if (self.get_lesson_status(
                    progress,
                    unit_id, lesson.lesson_id) != self.COMPLETED_STATE):
                return

        # Record that all lessons in this unit have been completed.
        self._set_entity_value(progress, event_key, self.COMPLETED_STATE)

    def _update_lesson(self, progress, event_key):
        """Updates a lesson's progress based on the progress of its children."""
        split_event_key = event_key.split('.')
        assert len(split_event_key) == 4
        unit_id = split_event_key[1]
        lesson_id = split_event_key[3]

        if self._get_entity_value(progress, event_key) == self.COMPLETED_STATE:
            return

        # Record that at least one part of this lesson has been completed.
        self._set_entity_value(progress, event_key, self.IN_PROGRESS_STATE)

        lessons = self._get_course().get_lessons(unit_id)
        for lesson in lessons:
            if str(lesson.lesson_id) == lesson_id and lesson:
                # Is the activity completed?
                if (lesson.activity and self.get_activity_status(
                        progress, unit_id, lesson_id) != self.COMPLETED_STATE):
                    return

                # Are all components of the lesson completed?
                if (self.get_html_status(
                        progress, unit_id, lesson_id) != self.COMPLETED_STATE):
                    return

        # Record that all activities in this lesson have been completed.
        self._set_entity_value(progress, event_key, self.COMPLETED_STATE)

    def _update_activity(self, progress, event_key):
        """Updates activity's progress when all interactive blocks are done."""
        split_event_key = event_key.split('.')
        assert len(split_event_key) == 6
        unit_id = split_event_key[1]
        lesson_id = split_event_key[3]

        if self._get_entity_value(progress, event_key) == self.COMPLETED_STATE:
            return

        # Record that at least one block in this activity has been completed.
        self._set_entity_value(progress, event_key, self.IN_PROGRESS_STATE)

        valid_block_ids = self.get_valid_block_ids(unit_id, lesson_id)
        for block_id in valid_block_ids:
            if not self.is_block_completed(
                    progress, unit_id, lesson_id, block_id):
                return

        # Record that all blocks in this activity have been completed.
        self._set_entity_value(progress, event_key, self.COMPLETED_STATE)

    def _update_html(self, progress, event_key):
        """Updates html's progress when all interactive blocks are done."""
        split_event_key = event_key.split('.')
        assert len(split_event_key) == 6
        unit_id = split_event_key[1]
        lesson_id = split_event_key[3]

        if self._get_entity_value(progress, event_key) == self.COMPLETED_STATE:
            return

        # Record that at least one block in this activity has been completed.
        self._set_entity_value(progress, event_key, self.IN_PROGRESS_STATE)

        cpt_ids = self.get_valid_component_ids(unit_id, lesson_id)
        for cpt_id in cpt_ids:
            if not self.is_component_completed(
                    progress, unit_id, lesson_id, cpt_id):
                return

        # Record that all blocks in this activity have been completed.
        self._set_entity_value(progress, event_key, self.COMPLETED_STATE)

    UPDATER_MAPPING = {
        'activity': _update_activity,
        'html': _update_html,
        'lesson': _update_lesson,
        'unit': _update_unit
    }

    # Dependencies for recording derived events. The key is the current
    # event, and the value is a tuple, each element of which contains:
    # - the dependent entity to be updated
    # - the transformation to apply to the id of the current event to get the
    #       id for the derived parent event
    DERIVED_EVENTS = {
        'block': (
            {
                'entity': 'activity',
                'generate_parent_id': (lambda s: '.'.join(s.split('.')[:-2])),
            },
        ),
        'activity': (
            {
                'entity': 'lesson',
                'generate_parent_id': (lambda s: '.'.join(s.split('.')[:-2])),
            },
        ),
        'lesson': (
            {
                'entity': 'unit',
                'generate_parent_id': (lambda s: '.'.join(s.split('.')[:-2])),
            },
        ),
        'component': (
            {
                'entity': 'html',
                'generate_parent_id': (lambda s: '.'.join(s.split('.')[:-2])),
            },
        ),
        'html': (
            {
                'entity': 'lesson',
                'generate_parent_id': (lambda s: '.'.join(s.split('.')[:-2])),
            },
        ),
    }

    def put_activity_completed(self, student, unit_id, lesson_id):
        """Records that the given student has completed an activity."""
        if not self._get_course().is_valid_unit_lesson_id(unit_id, lesson_id):
            return
        self._put_event(
            student, 'activity', self._get_activity_key(unit_id, lesson_id))

    def put_html_completed(self, student, unit_id, lesson_id):
        """Records that the given student has completed a lesson page."""
        if not self._get_course().is_valid_unit_lesson_id(unit_id, lesson_id):
            return
        self._put_event(
            student, 'html', self._get_html_key(unit_id, lesson_id))

    def put_block_completed(self, student, unit_id, lesson_id, block_id):
        """Records that the given student has completed an activity block."""
        if not self._get_course().is_valid_unit_lesson_id(unit_id, lesson_id):
            return
        if block_id not in self.get_valid_block_ids(unit_id, lesson_id):
            return
        self._put_event(
            student,
            'block',
            self._get_block_key(unit_id, lesson_id, block_id)
        )

    def put_component_completed(self, student, unit_id, lesson_id, cpt_id):
        """Records completion of a component in a lesson body."""
        if not self._get_course().is_valid_unit_lesson_id(unit_id, lesson_id):
            return
        if cpt_id not in self.get_valid_component_ids(unit_id, lesson_id):
            return
        self._put_event(
            student,
            'component',
            self._get_component_key(unit_id, lesson_id, cpt_id)
        )

    def put_assessment_completed(self, student, assessment_id):
        """Records that the given student has completed the given assessment."""
        if not self._get_course().is_valid_assessment_id(assessment_id):
            return
        self._put_event(
            student, 'assessment', self._get_assessment_key(assessment_id))

    def put_activity_accessed(self, student, unit_id, lesson_id):
        """Records that the given student has accessed this activity."""
        # This method currently exists because we need to mark activities
        # without interactive blocks as 'completed' when they are accessed.
        if not self.get_valid_block_ids(unit_id, lesson_id):
            self.put_activity_completed(student, unit_id, lesson_id)

    def put_html_accessed(self, student, unit_id, lesson_id):
        """Records that the given student has accessed this lesson page."""
        # This method currently exists because we need to mark lesson bodies
        # without interactive blocks as 'completed' when they are accessed.
        if not self.get_valid_component_ids(unit_id, lesson_id):
            self.put_html_completed(student, unit_id, lesson_id)

    def _put_event(self, student, event_entity, event_key):
        """Starts a cascade of updates in response to an event taking place."""
        if student.is_transient or event_entity not in self.EVENT_CODE_MAPPING:
            return

        progress = self.get_or_create_progress(student)

        self._update_event(
            student, progress, event_entity, event_key, direct_update=True)

        progress.updated_on = datetime.datetime.now()
        progress.put()

    def _update_event(self, student, progress, event_entity, event_key,
                      direct_update=False):
        """Updates statistics for the given event, and for derived events.

        Args:
          student: the student
          progress: the StudentProgressEntity for the student
          event_entity: the name of the affected entity (unit, lesson, etc.)
          event_key: the key for the recorded event
          direct_update: True if this event is being updated explicitly; False
              if it is being auto-updated.
        """
        if direct_update or event_entity not in self.UPDATER_MAPPING:
            if event_entity in self.UPDATER_MAPPING:
                # This is a derived event, so directly mark it as completed.
                self._set_entity_value(
                    progress, event_key, self.COMPLETED_STATE)
            else:
                # This is not a derived event, so increment its counter by one.
                self._inc(progress, event_key)
        else:
            self.UPDATER_MAPPING[event_entity](self, progress, event_key)

        if event_entity in self.DERIVED_EVENTS:
            for derived_event in self.DERIVED_EVENTS[event_entity]:
                self._update_event(
                    student=student,
                    progress=progress,
                    event_entity=derived_event['entity'],
                    event_key=derived_event['generate_parent_id'](event_key),
                )

    def get_unit_status(self, progress, unit_id):
        return self._get_entity_value(progress, self._get_unit_key(unit_id))

    def get_lesson_status(self, progress, unit_id, lesson_id):
        return self._get_entity_value(
            progress, self._get_lesson_key(unit_id, lesson_id))

    def get_activity_status(self, progress, unit_id, lesson_id):
        return self._get_entity_value(
            progress, self._get_activity_key(unit_id, lesson_id))

    def get_html_status(self, progress, unit_id, lesson_id):
        return self._get_entity_value(
            progress, self._get_html_key(unit_id, lesson_id))

    def get_block_status(self, progress, unit_id, lesson_id, block_id):
        return self._get_entity_value(
            progress, self._get_block_key(unit_id, lesson_id, block_id))

    def get_assessment_status(self, progress, assessment_id):
        return self._get_entity_value(
            progress, self._get_assessment_key(assessment_id))

    def is_block_completed(self, progress, unit_id, lesson_id, block_id):
        value = self._get_entity_value(
            progress, self._get_block_key(unit_id, lesson_id, block_id))
        return value is not None and value > 0

    def is_component_completed(self, progress, unit_id, lesson_id, cpt_id):
        value = self._get_entity_value(
            progress, self._get_component_key(unit_id, lesson_id, cpt_id))
        return value is not None and value > 0

    def is_assessment_completed(self, progress, assessment_id):
        value = self._get_entity_value(
            progress, self._get_assessment_key(assessment_id))
        return value is not None and value > 0

    @classmethod
    def get_or_create_progress(cls, student):
        progress = StudentPropertyEntity.get(student, cls.PROPERTY_KEY)
        if not progress:
            progress = StudentPropertyEntity.create(
                student=student, property_name=cls.PROPERTY_KEY)
            progress.put()
        return progress

    def get_unit_progress(self, student):
        """Returns a dict with the states of each unit."""
        if student.is_transient:
            return {}

        units = self._get_course().get_units()
        progress = self.get_or_create_progress(student)

        result = {}
        for unit in units:
            if unit.type == 'A':
                result[unit.unit_id] = self.is_assessment_completed(
                    progress, unit.unit_id)
            elif unit.type == 'U':
                value = self.get_unit_status(progress, unit.unit_id)
                result[unit.unit_id] = value or 0

        return result

    def get_lesson_progress(self, student, unit_id):
        """Returns a dict saying which lessons in this unit are completed."""
        if student.is_transient:
            return {}

        lessons = self._get_course().get_lessons(unit_id)
        progress = self.get_or_create_progress(student)

        result = {}
        for lesson in lessons:
            result[lesson.lesson_id] = {
                'html': self.get_html_status(
                    progress, unit_id, lesson.lesson_id) or 0,
                'activity': self.get_activity_status(
                    progress, unit_id, lesson.lesson_id) or 0,
            }
        return result

    def get_component_progress(self, student, unit_id, lesson_id, cpt_id):
        """Returns the progress status of the given component."""
        if student.is_transient:
            return 0

        progress = self.get_or_create_progress(student)
        return self.is_component_completed(
            progress, unit_id, lesson_id, cpt_id) or 0

    def _get_entity_value(self, progress, event_key):
        if not progress.value:
            return None
        return transforms.loads(progress.value).get(event_key)

    def _set_entity_value(self, student_property, key, value):
        """Sets the integer value of a student property.

        Note: this method does not commit the change. The calling method should
        call put() on the StudentPropertyEntity.

        Args:
          student_property: the StudentPropertyEntity
          key: the student property whose value should be incremented
          value: the value to increment this property by
        """
        try:
            progress_dict = transforms.loads(student_property.value)
        except (AttributeError, TypeError):
            progress_dict = {}

        progress_dict[key] = value
        student_property.value = transforms.dumps(progress_dict)

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
            progress_dict = transforms.loads(student_property.value)
        except (AttributeError, TypeError):
            progress_dict = {}

        if key not in progress_dict:
            progress_dict[key] = 0

        progress_dict[key] += value
        student_property.value = transforms.dumps(progress_dict)
