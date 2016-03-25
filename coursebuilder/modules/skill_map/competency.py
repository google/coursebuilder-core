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

import collections

from models import jobs
from models import models
from models import transforms
from models import data_removal
from modules.skill_map import constants

from google.appengine.ext import db


class BaseCompetencyMeasure(object):
    """Base class to model the behavior of a competency measure algorithm."""

    # Default value to distinguish between scores which are judged correct vs
    # incorrect. Specifically, if x >= CORRECT_INCORRECT_CUTOFF, it is correct
    # and otherwise incorrect. Course implementers are free to use
    # different criteria.
    CORRECT_INCORRECT_CUTOFF = 0.5

    NOT_STARTED = 'not-started'
    LOW_PROFICIENCY = 'low-competency'
    MED_PROFICIENCY = 'med-competency'
    HIGH_PROFICIENCY = 'high-competency'
    UNKNOWN = 'unknown'

    def __init__(self, user_id, skill_id, competency_dto):
        self.user_id = user_id
        self.skill_id = skill_id
        self.competency_dto = competency_dto

    @classmethod
    def load(cls, user_id, skill_id):
        key = CompetencyMeasureEntity.create_key_name(
            user_id, skill_id, cls.__name__)
        competency_dto = CompetencyMeasureDao.load(key)
        if not competency_dto:
            return cls(user_id, skill_id, CompetencyMeasureDto(key, {}))
        return cls(user_id, skill_id, competency_dto)

    @classmethod
    def bulk_load(cls, user_id, skill_ids):
        """Competency measures bulk load."""

        keys = []
        for skill_id in skill_ids:
            keys.append(CompetencyMeasureEntity.create_key_name(
                user_id, skill_id, cls.__name__))
        competency_dtos = CompetencyMeasureDao.bulk_load(keys)
        ret = []
        for key, skill_id, dto in zip(keys, skill_ids, competency_dtos):
            if dto:
                ret.append(cls(user_id, skill_id, dto))
            else:
                ret.append(
                    cls(user_id, skill_id, CompetencyMeasureDto(key, {})))
        return ret

    def save(self):
        CompetencyMeasureDao.save(self.competency_dto)

    def add_score(
            self, normalized_score, unit_id=None, lesson_id=None, block_id=None,
            timestamp=None):
        """Update competency scores for the student. The base implementation
        only records the score in the event log; subclasses should override this
        method to calculate the summative score, but should also chain a call to
        this method to record the event.

        Args:
            skill_id: the id for the skill for which the result is reported
            normalized_score: a float in the range 0.0 .. 1.0."""
        assert self.competency_dto is not None
        self.competency_dto.add_score({
            'normalized_score': normalized_score,
            'unit_id': unit_id,
            'lesson_id': lesson_id,
            'block_id': block_id,
            'timestamp': timestamp})

    @property
    def score(self):
        raise NotImplementedError()

    @property
    def score_level(self):
        raise NotImplementedError()

    @property
    def scores(self):
        return self.competency_dto.get_scores()

    @property
    def last_modified(self):
        return self.competency_dto.last_modified

    @property
    def proficient(self):
        raise NotImplementedError()

    @property
    def attempted(self):
        raise NotImplementedError()


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

    def add_score(self, event):
        self.dict.setdefault('events', []).append(event)

    def get_scores(self):
        return self.dict.get('events', [])

    @property
    def last_modified(self):
        return self.dict.get('last_modified') or ''

    @last_modified.setter
    def last_modified(self, value):
        self.dict['last_modified'] = value


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

    def get_user_id_skill_id_and_class_name(self):
        return self.key().name().split(':')


class CompetencyMeasureDao(models.LastModifiedJsonDao):
    DTO = CompetencyMeasureDto
    ENTITY = CompetencyMeasureEntity
    ENTITY_KEY_TYPE = models.BaseJsonDao.EntityKeyTypeName


class SuccessRateCompetencyMeasure(BaseCompetencyMeasure):
    """Measure of competency based on the cumulative percentage correct."""

    CORRECT_KEY = 'correct'
    COUNT_KEY = 'count'

    def add_score(self, normalized_score, **kwargs):
        super(SuccessRateCompetencyMeasure, self).add_score(
            normalized_score, **kwargs)

        count = self.competency_dto.get_data(self.COUNT_KEY) or 0
        self.competency_dto.set_data(self.COUNT_KEY, count + 1)
        if normalized_score >= self.CORRECT_INCORRECT_CUTOFF:
            correct = self.competency_dto.get_data(self.CORRECT_KEY) or 0
            self.competency_dto.set_data(self.CORRECT_KEY, correct + 1)

    @property
    def score(self):
        correct = self.competency_dto.get_data(self.CORRECT_KEY) or 0
        count = self.competency_dto.get_data(self.COUNT_KEY) or 0
        return float(correct) / count if count else 0.0

    @classmethod
    def calc_score_level(cls, score):
        if score < 0.0 or score > 1.0:
            raise ValueError('Unexpected skill score: %s.' % score)
        if score <= 0.33:
            return cls.LOW_PROFICIENCY
        if score <= 0.66:
            return cls.MED_PROFICIENCY
        if score <= 1.0:
            return cls.HIGH_PROFICIENCY

    @property
    def score_level(self):
        """Returns encoded competency labels used as css classes."""

        if not self.competency_dto.get_data(self.COUNT_KEY):
            return self.NOT_STARTED
        return self.calc_score_level(self.score)

    @property
    def proficient(self):
        return self.score >= 0.66

    @property
    def attempted(self):
        return self.competency_dto.get_data(self.COUNT_KEY) is not None


class CompetencyMeasureRegistry(object):

    _registry = []

    class _Updater(object):
        def __init__(self, competency_measures):
            self._competency_measures = competency_measures

        def add_score(self, normalized_score):
            for competency_measure in self._competency_measures:
                competency_measure.add_score(normalized_score)

        def save(self):
            for competency_measure in self._competency_measures:
                competency_measure.save()

    @classmethod
    def register(cls, competency_measure_class):
        assert issubclass(competency_measure_class, BaseCompetencyMeasure)
        cls._registry.append(competency_measure_class)

    @classmethod
    def get_updater(cls, user_id, skill_id):
        competency_measures = []
        for competency_measure_class in cls._registry:
            measure = competency_measure_class.load(user_id, skill_id)
            competency_measures.append(measure)
        return cls._Updater(competency_measures)


QuestionScore = collections.namedtuple('QuestionScore', ['quid', 'score'])


def _get_questions_scores_from_single_item(data):
    if data['type'] == 'QuestionGroup':
        question_scores = [
            QuestionScore(quid, score)
            for quid, score in zip(data['quids'], data['individualScores'])]
    else:
        question_scores = [QuestionScore(data['quid'], data['score'])]
    return question_scores


def _get_questions_scores_from_many_items(data):
    if isinstance(data, list):
        # It's a pre-1.5 assessment, so ignore it
        return []

    quids = data['quids']
    scores = data['individualScores']
    question_scores = []
    for instanceid in quids:
        quid = quids[instanceid]
        score = scores[instanceid]
        if isinstance(quid, basestring):
            # It wasn't a question group
            question_scores.append(QuestionScore(quid, score))
        else:
            # It's a question group and both quid and score are lists
            question_scores += [
                QuestionScore(q, s) for q, s in zip(quid, score)]
    return question_scores


def record_event_listener(source, user, data):
    # Note the code in this method has similarities to methods in
    # models.event_transforms, but is (a) more limited in scope, and (b) needs
    # less background information marshalled about the structure of the course

    if source == 'tag-assessment':
        # Sent when the "Check Answer" button is presson in a lesson
        question_scores = _get_questions_scores_from_single_item(data)

    elif source == 'attempt-lesson':
        # Sent when the "Grade Questions" button is pressed in a lesson
        # or when the "Check Answers" button is pressed in an assessment
        question_scores = _get_questions_scores_from_many_items(data)

    elif source == 'submit-assessment':
        # Sent when an assignment is submitted.
        data = data['values']
        question_scores = _get_questions_scores_from_many_items(data)

    else:
        return

    scores_by_skill = collections.defaultdict(list)
    for question_score in question_scores:
        question = models.QuestionDAO.load(question_score.quid)
        for skill_id in question.dict.get(constants.SKILLS_KEY, []):
            scores_by_skill[skill_id].append(question_score.score)

    for skill_id, scores in scores_by_skill.iteritems():
        updater = CompetencyMeasureRegistry.get_updater(
            user.user_id(), skill_id)
        for score in scores:
            updater.add_score(score)
        updater.save()


class GenerateSkillCompetencyHistograms(jobs.MapReduceJob):
    """Aggregates student competencies for each skill."""

    @classmethod
    def entity_class(cls):
        return CompetencyMeasureEntity

    @staticmethod
    def get_description():
        return 'skill competency distributions'

    @staticmethod
    def map(entity):
        """Gets the score level from the skill competency measure.

        Yields:
            A tuple of (skill_id, competency_level).
        """
        key = entity.key().name()
        user_id, skill_id, type_name = (
            entity.get_user_id_skill_id_and_class_name())
        if type_name == 'SuccessRateCompetencyMeasure':
            data = transforms.loads(entity.data)
            skill_dto = CompetencyMeasureDao.DTO(key, data)
            measure = SuccessRateCompetencyMeasure(
                user_id, skill_id, skill_dto)
            yield skill_id, measure.score

    @staticmethod
    def reduce(skill_id, scores):
        """Creates a histogram of competencies for each skill.

        Args:
            skill_id: skill id
            levels: list of competency levels

        Yields:
            A tuple (id, competency_histogram):
                (2, {'high-competency': 0, 'low-competency': 0,
                     'med-competency': 1, 'avg': 0.12})
        """
        hist = {
            BaseCompetencyMeasure.LOW_PROFICIENCY: 0,
            BaseCompetencyMeasure.MED_PROFICIENCY: 0,
            BaseCompetencyMeasure.HIGH_PROFICIENCY: 0
        }

        # aggregate values per competency level
        total = 0
        for x in scores:
            score = float(x)
            level = (
                SuccessRateCompetencyMeasure.calc_score_level(score))
            hist[level] += 1
            total += score
        hist['avg'] = total / len(scores) if scores else 0
        yield int(skill_id), hist


def notify_module_enabled():
    CompetencyMeasureRegistry.register(SuccessRateCompetencyMeasure)
    models.EventEntity.EVENT_LISTENERS.append(record_event_listener)
    data_removal.Registry.register_indexed_by_user_id_remover(
        CompetencyMeasureEntity.delete_by_user_id_prefix)
