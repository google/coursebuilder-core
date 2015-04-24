# Copyright 2015 Google Inc. All Rights Reserved.
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

"""Classes to provide framework for competency measures of student skills."""

__author__ = 'John Orr (jorr@google.com)'

from models import models

from google.appengine.ext import db


class BaseCompetencyMeasure(object):
    """Base class to model the behavior of a competency measure algorithm."""

    # Default value to distinuish between scores which are judged correct vs
    # incorrect. Specifically, if x >= CORRECT_INCORRECT_CUTOFF, it is correct
    # and otherwise incorrect. Implementors are of course free to use different
    # criteria, at their own risk.
    CORRECT_INCORRECT_CUTOFF = 0.5

    def __init__(self, student):
        self.dto = None
        self.student = student

    def load(self, skill_id):
        assert self.dto is None
        resource_key = CompetencyMeasureEntity.create_key_name(
            self.student.user_id, skill_id, self.__class__.__name__)
        self.dto = CompetencyMeasureDao.load(resource_key)
        if not self.dto:
            self.dto = CompetencyMeasureDto(resource_key, {})

    def save(self):
        assert self.dto is not None
        CompetencyMeasureDao.save(self.dto)
        self.dto = None

    def update(
            self, normalized_score, unit_id=None, lesson_id=None, block_id=None,
            timestamp=None):
        """Update competency scores for the student. The base implementation
        only records the score in the event log; subclasses should override this
        method to calculate the summative score, but should also chain a call to
        this method to record the event.

        Args:
            skill_id: the id for the skill for which the result is reported
            normalized_score: a float in the range 0.0 .. 1.0."""
        assert self.dto is not None
        self.dto.append_event({
            'normalized_score': normalized_score,
            'unit_id': unit_id,
            'lesson_id': lesson_id,
            'block_id': block_id,
            'timestamp': timestamp})

    def get_skill_score(self):
        raise NotImplementedError()

    def get_events_list(self):
        assert self.dto is not None
        return self.dto.get_events_list()


class CompetencyMeasureDto(object):
    """DTO to represent a competency measure."""

    def __init__(self, dto_id, dto_dict):
        self._id = dto_id
        self.dict = dto_dict

    @property
    def id(self):
        return self._id

    def get_data(self, property_name):
        return self.dict.get('data', {}).get(property_name)

    def set_data(self, property_name, property_value):
        self.dict.setdefault('data', {})[property_name] = property_value

    def append_event(self, event):
        self.dict.setdefault('events', []).append(event)

    def get_events_list(self):
        return self.dict.get('events', [])


class CompetencyMeasureEntity(models.BaseEntity):
    """Holds all the competency scores for a given student and measure."""
    # The key is a colon-separated triple student_id:skill_id:measure_type
    # The data is a JSON obejct of the following form:
    #     {
    #       "data": { ... }
    #       "events": [ { ... }, { ... }, ...]
    #     }
    # The "data" field holds data which the specific algorithm uses to update
    # the summary from n to n+1. The "events" consists of a list of event
    # objects which include the location (unit_id, lesson_id, block_id) of the
    # data, as well as the score and timestamp.
    data = db.TextProperty(indexed=False)

    @classmethod
    def create_key_name(cls, user_id, skill_id, class_name):
        assert ':' not in '%s%s%s' % (user_id, skill_id, class_name)
        return '%s:%s:%s' % (user_id, skill_id, class_name)

    @classmethod
    def safe_key(cls, db_key, transform_fn):
        user_id, skill_id, class_name = db_key.name().split(':', 2)
        return db.Key.from_path(
            cls.kind(),
            cls.create_key_name(transform_fn(user_id), skill_id, class_name))


class CompetencyMeasureDao(models.BaseJsonDao):
    DTO = CompetencyMeasureDto
    ENTITY = CompetencyMeasureEntity
    ENTITY_KEY_TYPE = models.BaseJsonDao.EntityKeyTypeName


class SuccessRateCompetencyMeasure(BaseCompetencyMeasure):
    """Measure of competency based on the cumulative percentage correct."""

    CORRECT_KEY = 'correct'
    COUNT_KEY = 'count'

    def update(self, normalized_score, **kwargs):
        super(SuccessRateCompetencyMeasure, self).update(
            normalized_score, **kwargs)

        count = self.dto.get_data(self.COUNT_KEY) or 0
        self.dto.set_data(self.COUNT_KEY, count + 1)
        if normalized_score >= self.CORRECT_INCORRECT_CUTOFF:
            correct = self.dto.get_data(self.CORRECT_KEY) or 0
            self.dto.set_data(self.CORRECT_KEY, correct + 1)

    def get_skill_score(self):
        correct = self.dto.get_data(self.CORRECT_KEY) or 0
        count = self.dto.get_data(self.COUNT_KEY) or 0
        return float(correct) / count if count else 0.0

class Registry(object):

    _registry = []

    class _Updater(object):
        def __init__(self, competency_measures):
            self._competency_measures = competency_measures

        def update(self, normalized_score):
            for competency_measure in self._competency_measures:
                competency_measure.update(normalized_score)

        def save(self):
            for competency_measure in self._competency_measures:
                competency_measure.save()

    @classmethod
    def register(cls, competency_measure_class):
        assert issubclass(competency_measure_class, BaseCompetencyMeasure)
        cls._registry.append(competency_measure_class)

    @classmethod
    def get_updater(cls, student, skill_id):
        competency_measures = []
        for competency_measure_class in cls._registry:
            measure = competency_measure_class(student)
            measure.load(skill_id)
            competency_measures.append(measure)
        return cls._Updater(competency_measures)


def notify_module_enabled():
    Registry.register(SuccessRateCompetencyMeasure)
