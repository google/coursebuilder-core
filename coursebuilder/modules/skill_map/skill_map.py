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

"""Module to provide skill mapping of Course Builder content."""

__author__ = 'John Orr (jorr@google.com)'

import json
import jinja2
import logging
import os
import random
import time

from collections import defaultdict

import appengine_config
from common import caching
from common import crypto
from common import resource
from common import safe_dom
from common import schema_fields
from common import tags
from controllers import sites
from controllers import utils
from mapreduce import context
from models import analytics
from models import courses
from models import custom_modules
from models import data_sources
from models import jobs
from models import models
from models import progress
from models import resources_display
from models import roles
from models import transforms
from modules.admin.config import CoursesItemRESTHandler
from modules.courses import lessons as lessons_controller
from modules.courses import outline
from modules.courses import settings
from modules.courses.unit_lesson_editor import LessonRESTHandler
from modules.dashboard import dashboard
from modules.dashboard.question_editor import BaseQuestionRESTHandler
from modules.dashboard.question_editor import McQuestionRESTHandler
from modules.dashboard.question_editor import SaQuestionRESTHandler
from modules.i18n_dashboard import i18n_dashboard
from modules.skill_map import competency
from modules.skill_map import constants
from modules.skill_map import skill_map_metrics
from modules.skill_map import recommender
from modules.skill_map import messages
from modules.skill_map.rdf import RdfBuilder

from google.appengine.ext import db
from google.appengine.api import namespace_manager

skill_mapping_module = None

# Folder where Jinja template files are stored
TEMPLATES_DIR = os.path.join(
    appengine_config.BUNDLE_ROOT, 'modules', 'skill_map', 'templates')

# URI for skill map css, js, amd img assets.
RESOURCES_URI = '/modules/skill_map/resources'
MODULE_NAME = 'skill_map'
MODULE_TITLE = 'Skills'

# Flag turning faker on
_USE_FAKE_DATA_IN_SKILL_COMPETENCY_ANALYTICS = False

def _assert(condition, message, errors, target_field):
    """Assert a condition and either log exceptions or raise AssertionError."""
    if not condition:
        if errors is not None:
            errors.append((target_field, message))
        else:
            raise AssertionError('%s:%s' % (target_field, message))

def _error_message(errors):
    return '\n'.join([x[1] for x in errors])


class _SkillEntity(models.BaseEntity):
    """Entity to represent a single skill."""

    # A JSON blob which holds the data for a single skill. It fits the
    # following schema:
    #     {
    #         "name": "string name of skill",
    #         "description": "string description of skill",
    #         "prerequisites": [
    #             {
    #                 "id": the id for the prerequisite SkillEntity
    #             },
    #             { ... }, ...
    #         ],
    #         "last_modified": epoch_time_sec
    #     }
    data = db.TextProperty(indexed=False)


class Skill(object):
    """DTO to represent a single skill."""

    def __init__(self, skill_id, data_dict):
        self._id = skill_id
        self.dict = data_dict

    @classmethod
    def build(cls, name, description, prerequisite_ids=None):
        return Skill(None, {
            'name': name,
            'description': description,
            'prerequisites': prerequisite_ids or []
        })

    @property
    def id(self):
        return self._id

    @property
    def name(self):
        return self.dict.get('name')

    @property
    def description(self):
        return self.dict.get('description')

    @property
    def last_modified(self):
        return self.dict.get('last_modified')

    @last_modified.setter
    def last_modified(self, value):
        self.dict['last_modified'] = value

    @property
    def prerequisite_ids(self):
        """Returns the id's of the prerequisites."""
        return {
            item.get("id") for item in self.dict.get('prerequisites', [])}

    def _set_prerequisite_ids(self, prerequisite_ids):
        """Sets the id's of the prerequisites."""
        self.dict['prerequisites'] = [
            {'id': prerequisite_id} for prerequisite_id in prerequisite_ids]


def _on_skills_changed(skills):
    if not i18n_dashboard.I18nProgressDeferredUpdater.is_translatable_course():
        return
    key_list = [resource.Key(ResourceSkill.TYPE, skill.id) for skill in skills]
    i18n_dashboard.I18nProgressDeferredUpdater.update_resource_list(key_list)


def _translate_skill(skills_generator):
    if not i18n_dashboard.is_translation_required():
        return
    app_context = sites.get_course_for_current_request()
    course = courses.Course.get(app_context)
    skills = []
    key_list = []
    first = True
    for skill in skills_generator:
        skills.append(skill)
        key_list.append(resource.Key(ResourceSkill.TYPE, skill.id))
    i18n_dashboard.translate_dto_list(course, skills, key_list)


class _SkillDao(models.LastModfiedJsonDao):
    DTO = Skill
    ENTITY = _SkillEntity
    ENTITY_KEY_TYPE = models.BaseJsonDao.EntityKeyTypeId
    # Using hooks that are in the same file looks awkward, but it's cleaner
    # than overriding all the load/store methods, and is also proof against
    # future changes that extend the DAO API.
    POST_LOAD_HOOKS = [_translate_skill]
    POST_SAVE_HOOKS = [_on_skills_changed]


class ResourceSkill(resource.AbstractResourceHandler):

    TYPE = 'skill'

    @classmethod
    def get_resource(cls, course, key):
        return _SkillDao.load(key)

    @classmethod
    def get_resource_title(cls, rsrc):
        return rsrc.name

    @classmethod
    def get_schema(cls, course, key):
        prerequisite_type = schema_fields.FieldRegistry('Prerequisite')
        prerequisite_type.add_property(schema_fields.SchemaField(
            'id', '', 'integer', optional=True, i18n=False))

        lesson_type = schema_fields.FieldRegistry('Lesson')
        lesson_type.add_property(schema_fields.SchemaField(
            'key', '', 'string', optional=True, i18n=False))

        question_type = schema_fields.FieldRegistry('Question')
        question_type.add_property(schema_fields.SchemaField(
            'key', '', 'string', optional=True, i18n=False))

        schema = schema_fields.FieldRegistry(
            'Skill', description='skill')
        schema.add_property(schema_fields.SchemaField(
            'version', '', 'string', optional=True, hidden=True))
        schema.add_property(schema_fields.SchemaField(
            'name', 'Name', 'string', optional=True))
        schema.add_property(schema_fields.SchemaField(
            'description', 'Description', 'text', optional=True))
        schema.add_property(schema_fields.FieldArray(
            'prerequisites', 'Prerequisites', item_type=prerequisite_type,
            optional=True))
        schema.add_property(schema_fields.FieldArray(
            'lessons', 'Lessons', item_type=lesson_type,
            optional=True))
        schema.add_property(schema_fields.FieldArray(
            'questions', 'Questions', item_type=question_type,
            optional=True))
        return schema

    @classmethod
    def get_data_dict(cls, course, key):
        return cls.get_resource(course, key).dict

    @classmethod
    def get_view_url(cls, rsrc):
        return None

    @classmethod
    def get_edit_url(cls, key):
        return None


class TranslatableResourceSkill(
    i18n_dashboard.AbstractTranslatableResourceType):

    @classmethod
    def get_ordering(cls):
        return i18n_dashboard.TranslatableResourceRegistry.ORDERING_LATE

    @classmethod
    def get_title(cls):
        return 'Skills'

    @classmethod
    def get_resources_and_keys(cls, course):
        ret = []
        for skill in _SkillDao.get_all():
            ret.append(
                (skill,
                 resource.Key(ResourceSkill.TYPE, skill.id, course)))
        ret.sort(key=lambda x: x[0].name)
        return ret


class SkillGraph(caching.RequestScopedSingleton):
    """Facade to handle the CRUD lifecycle of the skill dependency graph."""

    def __init__(self):
        # dict mapping skill id to skill
        self._skills = _SkillDao.get_all_mapped()
        # dict mapping skill id to list of successor SkillDTO's
        self._successors = None
        self._rebuild()

    def _rebuild(self):
        self.build_successors()
        SkillMap.clear_instance()

    def build_successors(self):
        self._successors = {}
        for other in self._skills.values():
            for pid in other.prerequisite_ids:
                self._successors.setdefault(pid, []).append(other)

    @classmethod
    def load(cls):
        return cls.instance()

    @property
    def skills(self):
        """Get a list of all the skills in this course.

        Returns:
            list of Skill objects.
        """
        return self._skills.values()

    def get(self, skill_id):
        """Get skill by ID."""
        return self._skills[skill_id]

    def add(self, skill, errors=None):
        """Add a skill to the skill map."""
        _assert(skill.id is None, 'Skill has already been added', errors,
                'skill-id')

        for prerequisite_id in skill.prerequisite_ids:
            _assert(prerequisite_id in self._skills,
                    'Skill has non-existent prerequisite', errors,
                    'skill-prerequisites')

        self.validate_unique_skill_name(skill.id, skill.name, errors)

        if errors:
            return skill

        skill_id = _SkillDao.save(skill)
        new_skill = Skill(skill_id, skill.dict)
        self._skills[skill_id] = new_skill
        self._rebuild()

        return new_skill

    def update(self, sid, attributes, errors):
        skill = Skill(sid, attributes)

        _assert(self.get(sid), 'Skill does not exist', errors, 'skill-id')
        prerequisite_ids = [
            x['id'] for x in attributes.get('prerequisites', [])]
        for pid in prerequisite_ids:
            self.validate_distinct(sid, pid, errors)
        self.validate_no_duplicate_prerequisites(prerequisite_ids, errors)
        self.validate_unique_skill_name(sid, attributes.get('name'), errors)

        if errors:
            return skill

        skill_id = _SkillDao.save(skill)

        # pylint: disable=protected-access
        skill = Skill(skill_id, attributes)
        self._skills[skill_id] = skill
        self._rebuild()
        # pylint: enable=protected-access

        return skill

    def delete(self, skill_id, errors=None):
        """Remove a skill from the skill map."""
        _assert(
            skill_id in self._skills,
            'Skill is not present in the skill map', errors,
            'skill-prerequisites')

        successors = self.successors(skill_id)
        # pylint: disable=protected-access
        for successor in successors:
            prerequisite_ids = successor.prerequisite_ids
            prerequisite_ids.remove(skill_id)
            successor._set_prerequisite_ids(prerequisite_ids)

        _SkillDao.delete(self._skills[skill_id])
        _SkillDao.save_all(successors)

        del self._skills[skill_id]
        self._rebuild()
        # pylint: enable=protected-access

    def prerequisites(self, skill_id):
        """Get the immediate prerequisites of the given skill.

        Args:
            skill_id. The id of the skill to find prerequisites of.

        Returns:
            list of Skill.
        """
        skill = self._skills[skill_id]
        return [
            self._skills[prerequisite_id]
            for prerequisite_id in skill.prerequisite_ids]

    def validate_distinct(self, sid, pid, errors=None):
        """Check that the skill and the prerequisite exist and that they
        are distinct."""

        _assert(
            sid in self._skills, 'Skill does not exist', errors, 'skill-id')
        _assert(pid in self._skills,
            'Prerequisite does not exist', errors, 'skill-prerequisites')
        # No length-1 cycles (ie skill which is its own prerequisite)  allowed
        _assert(
            sid != pid,
            'A skill cannot be its own prerequisite', errors,
            'skill-prerequisites')

    def validate_unique_skill_name(self, skill_id, name, errors):
        for other_skill in self.skills:
            if other_skill.id == skill_id:
                continue
            _assert(
                name != other_skill.name, 'Name must be unique', errors,
                'skill-name')

    def validate_prerequisite_not_set(
            self, skill, prerequisite_skill_id, errors):
        _assert(
            prerequisite_skill_id not in skill.prerequisite_ids,
            'This prerequisite has already been set', errors,
            'skill-prerequisites')

    @classmethod
    def validate_no_duplicate_prerequisites(cls, prerequisite_ids, errors):
        _assert(
            len(set(prerequisite_ids)) == len(prerequisite_ids),
            'Prerequisites must be unique', errors, 'skill-prerequisites')

    def add_prerequisite(self, skill_id, prerequisite_skill_id, errors=None):
        self.validate_distinct(skill_id, prerequisite_skill_id, errors)
        skill = self._skills.get(skill_id)
        self.validate_prerequisite_not_set(skill, prerequisite_skill_id, errors)
        prerequisite_skills = skill.prerequisite_ids
        prerequisite_skills.add(prerequisite_skill_id)
        # pylint: disable=protected-access
        skill._set_prerequisite_ids(prerequisite_skills)
        _SkillDao.save(skill)
        self._rebuild()
        # pylint: enable=protected-access

    def delete_prerequisite(self, skill_id, prerequisite_skill_id, errors=None):
        self.validate_distinct(skill_id, prerequisite_skill_id)
        skill = self._skills[skill_id]
        prerequisite_skills = skill.prerequisite_ids
        _assert(
            prerequisite_skill_id in prerequisite_skills,
            'Cannot delete an unset prerequisite.', errors,
            'skill-prerequisites')
        prerequisite_skills.remove(prerequisite_skill_id)
        # pylint: disable=protected-access
        skill._set_prerequisite_ids(prerequisite_skills)

        _SkillDao.save(skill)
        self._rebuild()
        # pylint: enable=protected-access

    def successors(self, skill_id):
        """Get the immediate successors of the given skill.

        Args:
            skill_id. The id of the skill to find successors of.

        Returns:
            list of Skill.
        """
        return self._successors.get(skill_id, [])


class LocationInfo(object):
    """Info object for mapping skills to locations."""

    def __init__(self, course, res):
        self._course = course
        self._resource = res
        self._key = None
        self._label = None
        self._description = None
        self._href = None
        self._edit_href = None
        self._sort_key = None
        self._lesson_title = None
        self._lesson_index = None
        self._unit_id = None
        self._unit_title = None
        self._unit_index = None

        if isinstance(res, courses.Lesson13):
            self.build_lesson_location()
        elif isinstance(res, models.QuestionDTO):
            self.build_question_location()

    def _get_formatted_type(self, question):
        """Question type formatter."""
        if question.type == models.QuestionDTO.MULTIPLE_CHOICE:
            return '(mc)'
        elif question.type == models.QuestionDTO.SHORT_ANSWER:
            return '(sa)'
        return ''

    def build_question_location(self):
        question = self._resource
        qtype = resources_display.ResourceQuestionBase.get_question_key_type(
            question)
        self._key = resource.Key(qtype, question.id)
        self._id = question.id
        self._description = '%s %s' % (
            self._get_formatted_type(question), question.description)
        self._edit_href = resources_display.ResourceQuestionBase.get_edit_url(
            self._key)

    def build_lesson_location(self):
        lesson = self._resource
        self._key = resources_display.ResourceLesson.get_key(lesson)
        self._id = lesson.lesson_id
        self._lesson_index = lesson.index
        self._lesson_title = lesson.title
        unit = self._course.find_unit_by_id(lesson.unit_id)
        self._unit_title = unit.title
        self._unit_id = unit.unit_id
        # pylint: disable=protected-access
        self._unit_index = unit._index
        # pylint: enable=protected-access
        if lesson.index is None:
            self._label = '%s.' % unit.index
        else:
            self._label = '%s.%s' % (unit.index, lesson.index)
        self._description = lesson.title
        self._href = 'unit?unit=%s&lesson=%s' % (
            lesson.unit_id, lesson.lesson_id)
        self._edit_href = 'dashboard?action=edit_lesson&key=%s' % self._id
        self._sort_key = (lesson.unit_id, lesson.lesson_id)

    @property
    def key(self):
        return self._key

    @property
    def id(self):
        return self._id

    @property
    def label(self):
        return self._label

    @property
    def description(self):
        # '(' + this.type + ') ' + this.description)
        return self._description

    @property
    def href(self):
        return self._href

    @property
    def edit_href(self):
        return self._edit_href

    @property
    def resource(self):
        return self._resource

    @property
    def sort_key(self):
        return self._sort_key

    @property
    def lesson_index(self):
        return self._lesson_index

    @property
    def lesson_title(self):
        return self._lesson_title

    @property
    def unit_id(self):
        return self._unit_id

    @property
    def unit_index(self):
        return self._unit_index

    @property
    def unit_title(self):
        return self._unit_title

    @classmethod
    def json_encoder(cls, obj):
        if isinstance(obj, cls):
            return {
                'key': str(obj.key),
                'label': obj.label,
                'description': obj.description,
                'href': obj.href,
                'edit_href': obj.edit_href,
                'sort_key': obj.sort_key,
                'lesson_index': obj.lesson_index,
                'lesson_title': obj.lesson_title,
                'unit_id': obj.unit_id,
                'unit_title': obj.unit_title,
                'unit_index': obj.unit_index
            }
        return None


class SkillInfo(object):
    """Skill info object for skills with lesson and unit ids."""

    def __init__(
            self, skill, lessons=None, questions=None, measure=None,
            topo_sort_index=None):
        assert skill
        self._skill = skill
        self._lessons = lessons or []
        self._questions = questions or []
        self._prerequisites = []
        self._successors = []
        self._competency_measure = measure
        self._topo_sort_index = topo_sort_index

    @property
    def id(self):
        return self._skill.id

    @property
    def name(self):
        return self._skill.name

    @property
    def description(self):
        return self._skill.description

    @property
    def prerequisites(self):
        return self._prerequisites

    @prerequisites.setter
    def prerequisites(self, skills):
        """Sets prerequisite skills."""
        self._prerequisites = skills

    @property
    def successors(self):
        return self._successors

    @successors.setter
    def successors(self, skills):
        """Sets successors skills."""
        self._successors = skills

    @property
    def lessons(self):
        return self._lessons

    @property
    def questions(self):
        return self._questions

    @property
    def competency_measure(self):
        return self._competency_measure

    @competency_measure.setter
    def competency_measure(self, measure):
        """Sets skill score."""
        self._competency_measure = measure

    @property
    def score(self):
        if self._competency_measure:
            return self._competency_measure.score
        else:
            return None

    @property
    def score_level(self):
        if self._competency_measure:
            return self._competency_measure.score_level
        else:
            return competency.BaseCompetencyMeasure.UNKNOWN

    def set_topo_sort_index(self, topo_sort_index):
        self._topo_sort_index = topo_sort_index

    def sort_key(self):
        if self._lessons:
            loc = min(sorted(self._lessons, key=lambda x: x.sort_key))
            return loc.sort_key
        return None, None

    def topo_sort_key(self):
        return self.sort_key() + (self._topo_sort_index, )

    @property
    def proficient(self):
        if self.competency_measure:
            return self.competency_measure.proficient
        else:
            return None

    @classmethod
    def json_encoder(cls, obj):
        if isinstance(obj, cls):
            return {
                'id': obj.id,
                'name': obj.name,
                'description': obj.description,
                'prerequisite_ids': [s.id for s in obj.prerequisites],
                'successor_ids': [s.id for s in obj.successors],
                'lessons': obj.lessons,
                'questions': obj.questions,
                'sort_key': obj.sort_key(),
                'topo_sort_key': obj.topo_sort_key(),
                'score': obj.score,
                'score_level': obj.score_level
            }
        return None


class SkillMapError(Exception):
    pass


class SkillMap(caching.RequestScopedSingleton):
    """Provides API to access the course skill map."""

    def __init__(self, skill_graph, course):
        self._rebuild(skill_graph, course)

    def _rebuild(self, skill_graph, course):
        self._user_id = None
        self._skill_graph = skill_graph
        self._course = course

        self._units = dict([(u.unit_id, u) for u in self._course.get_units()])

        self._lessons_by_skill = {}
        for lesson in self._course.get_lessons_for_all_units():
            skill_ids = lesson.properties.get(constants.SKILLS_KEY, [])
            for skill_id in skill_ids:
                self._lessons_by_skill.setdefault(skill_id, []).append(lesson)

        self._questions_by_skill = {}
        for question in models.QuestionDAO.get_all():
            skill_ids = question.dict.get(constants.SKILLS_KEY, [])
            for skill_id in skill_ids:
                self._questions_by_skill.setdefault(skill_id, []).append(
                    question)

        self._skill_infos = {}

        # add locations and questions
        for skill in self._skill_graph.skills:
            locations = []
            for lesson in self._lessons_by_skill.get(skill.id, []):
                locations.append(LocationInfo(self._course, lesson))
            questions = []
            for question in self._questions_by_skill.get(skill.id, []):
                questions.append(LocationInfo(self._course, question))
            self._skill_infos[skill.id] = SkillInfo(skill, locations, questions)

        # add prerequisites
        for skill in self._skill_graph.skills:
            prerequisites = []
            for pid in skill.prerequisite_ids:
                prerequisites.append(self._skill_infos[pid])
            self._skill_infos[skill.id].prerequisites = prerequisites

        # add successors
        for skill in self._skill_graph.skills:
            successors = []
            for skill_dto in self._skill_graph.successors(skill.id):
                successors.append(self._skill_infos[skill_dto.id])
            self._skill_infos[skill.id].successors = successors

    def build_successors(self):
        """Returns a dictionary keyed by skills' ids.

        The values are sets of successors' ids."""
        successors = {}
        for si in self._skill_infos.values():
            for p in si.prerequisites:
                successors.setdefault(p.id, set()).add(si.id)
            if si.id not in successors:
                successors[si.id] = set()
        return successors

    def _topo_sort(self):
        """Returns topologically sorted co-sets."""
        successors = self.build_successors()
        ret = []
        if not successors:
            return ret
        co_set = set(
            successors.keys()) - reduce(
            set.union, successors.values())  # Skills with no prerequisites.
        while True:
            if not co_set:
                break
            ret.append(co_set)
            for x in co_set:
                del successors[x]
            for src, dst in successors.items():
                successors[src] = dst - co_set
            co_set = set(successors.keys()) - reduce(
                set.union, successors.values(), set())
        if successors:  # There is unvisited nodes -> there is a cycle.
            return None
        else:
            return ret

    def _set_topological_sort_index(self):
        chain = []
        for x in self._topo_sort():
            chain.extend(list(x))
        for skill in self._skill_graph.skills:
            self._skill_infos[skill.id].set_topo_sort_index(
                chain.index(skill.id))

    def personalized(self):
        return self._user_id is not None

    @classmethod
    def load(cls, course, user_id=None):
        skill_graph = SkillGraph.load()
        skill_map = cls.instance(skill_graph, course)
        if user_id:
            skill_map.add_competency_measures(user_id)
        return skill_map

    def get_lessons_for_skill(self, skill):
        return self._lessons_by_skill.get(skill.id, [])

    def get_skills_for_lesson(self, lesson_id):
        """Get the skills assigned to the given lesson.

        Args:
            lesson_id. The id of the lesson.

        Returns:
            A list of SkillInfo objects.
        """

        # TODO(jorr): Can we stop relying on the unit and just use lesson id?
        lesson = self._course.find_lesson_by_id(None, lesson_id)
        sids = lesson.properties.get(constants.SKILLS_KEY, [])
        return [self._skill_infos[skill_id] for skill_id in sids]

    def get_questions_for_skill(self, skill):
        return self._questions_by_skill.get(skill.id, [])

    def successors(self, skill_info):
        """Get the successors to the given skill.

        Args:
            skill_info. A SkillInfo object.

        Returns:
            A list of SkillInfo objects.
        """
        return {
            self._skill_infos[s.id]
            for s in self._skill_graph.successors(skill_info.id)}

    def add_competency_measures(self, user_id):
        """Personalize skill map with user's competency measures."""

        sids = self._skill_infos.keys()
        measures = competency.SuccessRateCompetencyMeasure.bulk_load(
            user_id, sids)
        for measure in measures:
            self._skill_infos[measure.skill_id].competency_measure = measure
        self._user_id = user_id

    def skills(self, sort_by='name'):
        if sort_by == 'name':
            return sorted(self._skill_infos.values(), key=lambda x: x.name)
        elif sort_by == 'lesson':
            return sorted(
                self._skill_infos.values(), key=lambda x: x.sort_key())
        elif sort_by == 'prerequisites':
            self._set_topological_sort_index()
            return sorted(
                self._skill_infos.values(), key=lambda x: x.topo_sort_key())
        else:
            raise ValueError('Invalid sort option.')

    def is_empty(self):
        return len(self._skill_infos) == 0

    @classmethod
    def create_hist_buckets(cls, hist):
        """Transforms a competency histogram into crossfilter buckets."""

        buckets = [
            {'c': 0, 'l': 'low', 'v': 0},
            {'c': 1, 'l': 'med', 'v': 0},
            {'c': 2, 'l': 'high', 'v': 0}]
        if not hist:
            return buckets, 0.0
        buckets[0]['v'] = hist.get(
            competency.BaseCompetencyMeasure.LOW_PROFICIENCY, 0.0)
        buckets[1]['v'] = hist.get(
                competency.BaseCompetencyMeasure.MED_PROFICIENCY, 0.0)
        buckets[2]['v'] = hist.get(
                competency.BaseCompetencyMeasure.HIGH_PROFICIENCY, 0.0)
        return buckets, hist.get('avg', 0.0)

    @classmethod
    def gen_fake_competency_histogram(cls):
        """Faker for crossfilter table data."""

        histogram = [
            {'c': 0, 'v': random.randint(0, 25), 'l': 'low'},
            {'c': 1, 'v': random.randint(0, 10), 'l': 'med'},
            {'c': 2, 'v': random.randint(0, 10), 'l': 'high'}
        ]
        count = (
            histogram[0]['v'] +
            histogram[1]['v'] +
            histogram[2]['v'])
        if count:
            avg = (
                histogram[0]['v'] * 0.33 +
                histogram[1]['v'] * 0.66 +
                histogram[2]['v'] * 1.0) / count
        else:
            avg = 0.0
        return histogram, avg

    def gen_skills_xf_data(self, competencies):
        """Generate cross-filter table for skills competencies dashboard.

        Args:
            competencies: a list of (id, dict) pairs emitted by
            competency.GenerateSkillCompetencyHistograms.reduce.
        """

        competencies = dict(competencies)
        rows = []
        for skill in self._skill_infos.values():
            hist = competencies.get(skill.id)
            if _USE_FAKE_DATA_IN_SKILL_COMPETENCY_ANALYTICS:
                hist, avg = self.gen_fake_competency_histogram()
            else:
                hist, avg = self.create_hist_buckets(hist)

            row = {
                'skill_id': skill.id,
                'skill_name': skill.name,
                'skill_description': skill.description,
                'lesson_id': None,
                'lesson_index': None,
                'lesson_title': None,
                'unit_id': None,
                'unit_index': None,
                'unit_title': None,
                'final': True if skill.successors else False,
                'initial': True if skill.prerequisites else False,
                'histogram': hist,
                'avg': avg
            }

            if skill.lessons:
                # use one location per unit
                unit_ids = set()
                for loc in skill.lessons:
                    if loc.unit_id in unit_ids:
                        continue
                    unit_ids.add(loc.unit_id)

                    next_row = row.copy()
                    next_row['lesson_id'] = loc.id
                    next_row['lesson_index'] = loc.lesson_index
                    next_row['lesson_title'] = loc.lesson_title
                    next_row['unit_id'] = loc.unit_id
                    next_row['unit_index'] = loc.unit_index
                    next_row['unit_title'] = loc.unit_title
                    rows.append(next_row)
            else:
                rows.append(row)
        return rows

    def get_skill(self, skill_id):
        return self._skill_infos[skill_id]

    def add_skill_to_lessons(self, skill, location_keys):
        """Add the skill to the given lessons."""

        for loc in location_keys:
            _, lesson = resource.Key.fromstring(loc['key']).get_resource(
                self._course)
            lesson.properties.setdefault(constants.SKILLS_KEY, []).append(
                skill.id)
            assert self._course.update_lesson(lesson)
            # pylint: disable=protected-access
            skill._lessons.append(LocationInfo(self._course, lesson))
        self._course.save()
        self._lessons_by_skill.setdefault(skill.id, []).extend(location_keys)
        # pylint: enable=protected-access

    def delete_skill_from_lessons(self, skill):
        if not self._lessons_by_skill.get(skill.id):
            return
        # pylint: disable=protected-access
        for lesson in self._lessons_by_skill[skill.id]:
            lesson.properties[constants.SKILLS_KEY].remove(skill.id)
            assert self._course.update_lesson(lesson)
        self._course.save()
        del self._lessons_by_skill[skill.id]
        skill._lessons = []
        # pylint: enable=protected-access

    def add_skill_to_questions(self, skill, question_keys):
        """Add the skill to the given questions.

        Args:
            skill: SkillInfo. The skill to be added
            questions: List of {'id': str}.
        """
        if not question_keys:
            return
        keys = [resource.Key.fromstring(x['key']) for x in question_keys]
        questions = [key.get_resource(self._course) for key in keys]

        for question in questions:
            question.dict.setdefault(
                constants.SKILLS_KEY, []).append(skill.id)
        assert models.QuestionDAO.save_all(questions)
        # pylint: disable=protected-access
        skill._questions.extend(
            [LocationInfo(self._course, question) for question in questions])
        self._questions_by_skill.setdefault(skill.id, []).extend(questions)
        # pylint: enable=protected-access

    def delete_skill_from_questions(self, skill):
        """Delete the skill from all questions."""

        # pylint: disable=protected-access
        if not self._questions_by_skill.get(skill.id):
            return
        for question in self._questions_by_skill[skill.id]:
            question.dict[constants.SKILLS_KEY].remove(skill.id)
        assert models.QuestionDAO.save_all(self._questions_by_skill[skill.id])
        del self._questions_by_skill[skill.id]
        skill._questions = []
        # pylint: enable=protected-access


class LocationListRestHandler(utils.BaseRESTHandler):
    """REST handler to list all locations and questions."""

    URL = '/rest/modules/skill_map/locations'

    def get(self):
        if not roles.Roles.is_course_admin(self.app_context):
            transforms.send_json_response(self, 401, 'Access denied.', {})
            return

        payload_dict = {
            'lessons': [
                LocationInfo(self.get_course(), x)
                for x in self.get_course().get_lessons_for_all_units()],
            'questions': [
                LocationInfo(self.get_course(), x)
                for x in models.QuestionDAO.get_all()]}
        transforms.send_json_response(self, 200, '', payload_dict)


class SkillRestHandler(utils.BaseRESTHandler):
    """REST handler to manage skills."""

    XSRF_TOKEN = 'skill-handler'
    SCHEMA_VERSIONS = ['1']

    URL = '/rest/modules/skill_map/skill'

    @classmethod
    def get_schema(cls):
        """Return the schema for the skill editor."""
        return ResourceSkill.get_schema(course=None, key=None)

    def get(self):
        """Get a skill."""

        if not roles.Roles.is_course_admin(self.app_context):
            transforms.send_json_response(self, 401, 'Access denied.', {})
            return

        key = self.request.get('key')

        skill_map = SkillMap.load(self.get_course())
        payload_dict = {
            'skills': skill_map.skills(),
            'diagnosis': skill_map_metrics.SkillMapMetrics(skill_map).diagnose()
        }

        if key:
            payload_dict['skill'] = skill_map.get_skill(int(key))

        transforms.send_json_response(
            self, 200, '', payload_dict=payload_dict,
            xsrf_token=crypto.XsrfTokenManager.create_xsrf_token(
                self.XSRF_TOKEN))

    def delete(self):
        """Deletes a skill."""

        key = int(self.request.get('key'))

        if not self.assert_xsrf_token_or_fail(
                self.request, self.XSRF_TOKEN, {'key': key}):
            return

        if not roles.Roles.is_course_admin(self.app_context):
            transforms.send_json_response(
                self, 401, 'Access denied.', {'key': key})
            return

        errors = []

        skill_graph = SkillGraph.load()

        skill_map = SkillMap.load(self.get_course())
        skill = skill_map.get_skill(key)

        # Note, first delete from lessons and questions and
        # then from the skill graph
        skill_map.delete_skill_from_lessons(skill)
        skill_map.delete_skill_from_questions(skill)
        skill_graph.delete(key, errors)

        skill_map = SkillMap.load(self.get_course())

        if errors:
            self.validation_error(
                _error_message(errors), key=key, errors=errors)
            return

        payload_dict = {
            'skills': skill_map.skills(),
            'diagnosis': skill_map_metrics.SkillMapMetrics(skill_map).diagnose()
        }

        transforms.send_json_response(self, 200, 'Skill deleted.',
            payload_dict=payload_dict)

    def put(self):
        request = transforms.loads(self.request.get('request'))
        key = request.get('key')

        if not self.assert_xsrf_token_or_fail(
                request, self.XSRF_TOKEN, {}):
            return

        if not roles.Roles.is_course_admin(self.app_context):
            transforms.send_json_response(
                self, 401, 'Access denied.', {'key': key})
            return

        payload = request.get('payload')
        json_dict = transforms.loads(payload)
        python_dict = transforms.json_to_dict(
            json_dict, self.get_schema().get_json_schema_dict(),
            permit_none_values=True)

        version = python_dict.get('version')
        if version not in self.SCHEMA_VERSIONS:
            self.validation_error('Version %s not supported.' % version)
            return

        lesson_locations = python_dict.pop('lessons', [])
        question_locations = python_dict.pop('questions', [])

        errors = []

        course = self.get_course()
        skill_graph = SkillGraph.load()

        if key:
            skill = skill_graph.update(key, python_dict, errors)
        else:
            skill = Skill.build(
                python_dict.get('name'),
                python_dict.get('description'),
                python_dict.get('prerequisites'))
            skill = skill_graph.add(skill, errors=errors)

        if errors:
            self.validation_error(
                _error_message(errors), key=skill.id, errors=errors)
            return

        key_after_save = skill.id
        skill_map = SkillMap.load(course)
        skill = skill_map.get_skill(key_after_save)

        skill_map.delete_skill_from_lessons(skill)
        skill_map.add_skill_to_lessons(skill, lesson_locations)

        skill_map.delete_skill_from_questions(skill)
        skill_map.add_skill_to_questions(skill, question_locations)

        payload_dict = {
            'key': key_after_save,
            'skill': skill,
            'skills': skill_map.skills(),
            'diagnosis': skill_map_metrics.SkillMapMetrics(skill_map).diagnose()
        }

        transforms.send_json_response(
            self, 200, 'Saved.', payload_dict=payload_dict)


class SkillMapHandler(dashboard.DashboardHandler):

    URL = '/modules/skill_map'

    get_actions = ['edit_skills_table', 'edit_dependency_graph']

    def render_read_only(self):
        self.render_page({
            'page_title': self.format_title('Skills Map'),
            'main_content': jinja2.utils.Markup(
                '<h1>Read-only course.</h1>')
        })

    def get_edit_skills_table(self):
        self.course = courses.Course(self)
        if not self.app_context.is_editable_fs():
            self.render_read_only()
            return

        skill_map = SkillMap.load(self.course)
        skills = skill_map.skills() or []

        template_values = {
            'skills_autocomplete': json.dumps(
                [{'id': s.id, 'label': s.name} for s in skills])}

        main_content = self.get_template(
            'skills_table.html', [TEMPLATES_DIR]).render(template_values)

        self.render_page({
            'page_title': self.format_title('Skills table'),
            'main_content': jinja2.utils.Markup(main_content)})

    def get_edit_dependency_graph(self):
        self.course = courses.Course(self)
        if not self.app_context.is_editable_fs():
            self.render_read_only()
            return

        skill_map = SkillMap.load(self.course)

        nodes = []
        n2i = {}
        for ind, skill in enumerate(skill_map.skills()):
            nodes.append({'id': skill.name})
            n2i[skill.name] = ind

        links = []
        for tgt in skill_map.skills():
            for src in tgt.prerequisites:
                links.append({'source': n2i[src.name], 'target': n2i[tgt.name]})

        template_values = {
            'nodes': json.dumps(nodes), 'links': json.dumps(links)}

        main_content = self.get_template(
            'dependency_graph.html', [TEMPLATES_DIR]).render(template_values)
        self.render_page({
            'page_title': self.format_title('Dependencies Graph'),
            'main_content': jinja2.utils.Markup(main_content)},
            in_action='edit_skills_table')


class SkillMapRdfSchemaHandler(utils.ApplicationHandler):
    """A handler to output skill map RDF schema."""

    def get(self):
        self.response.headers['Content-Type'] = 'application/rdf+xml'
        self.response.write(RdfBuilder().schema_toxml())


class SkillMapRdfHandler(utils.BaseHandler):
    """A handler to output skill map in RDF."""

    def can_view(self):
        if roles.Roles.is_course_admin(self.app_context):
            return True, 200

        browsable = self.app_context.get_environ()['course']['browsable']
        if browsable:
            return True, True

        user = self.personalize_page_and_get_user()
        if user is None:
            return False, 401
        else:
            return False, 403

    def get(self):
        can_view, error = self.can_view()
        if not can_view:
            self.error(error)
            return

        self.response.headers['Content-Type'] = 'application/rdf+xml'
        self.response.write(RdfBuilder().skills_toxml(
            SkillMap.load(self.get_course()).skills()))


class SkillCompetencyDataSource(data_sources.SynchronousQuery):

    @staticmethod
    def required_generators():
        return [competency.GenerateSkillCompetencyHistograms]

    @classmethod
    def get_name(cls):
        return 'skills_competency_histograms'

    @staticmethod
    def fill_values(
            app_context, template_values, competency_histograms_generator):
        """Provides template values from the map-reduce job.

        Works with the skills_competencies_analytics.html jinja template.

        Stores in the key 'counts' of template_values a table with the
        following format:
            skill name, count of completions, counts of 'in progress'
        Adds a row for each skill in the output of CountSkillCompletion job.
        """
        job_result = jobs.MapReduceJob.get_results(
            competency_histograms_generator)
        course = courses.Course.get(app_context)
        skill_map = SkillMap.load(course)
        xf_data = skill_map.gen_skills_xf_data(job_result)
        template_values['skill_map_is_empty'] = skill_map.is_empty()
        template_values['xf_data'] = transforms.dumps(xf_data)


class SkillCompletionAggregate(models.BaseEntity):
    """Representation for the count of skill completions during time.

    Each entity of this class must be created using the skill_id as a
    key name.

    The aggregate field is a json string representing a dictionary. It
    maps dates in skill_map.skill_map.CountSkillCompletion.DATE_FORMAT
    with the number of students that completed that skill before the given
    date.
    """
    aggregate = db.TextProperty(indexed=False)


class CountSkillCompletion(jobs.MapReduceJob):
    """Aggregates the progress of students for each skill."""

    DATE_FORMAT = '%Y-%m-%d'

    @classmethod
    def entity_class(cls):
        return models.Student

    @staticmethod
    def get_description():
        return 'counting students that completed or attempted a skill'

    def build_additional_mapper_params(self, app_context):
        """Creates a map from skill ids to skill names."""
        course = courses.Course.get(app_context)
        skill_map = SkillMap.load(course)
        return {'skill_ids': [skill.id for skill in skill_map.skills()]}

    @staticmethod
    def map(item):
        """Extracts the skill progress of the student.

        Yields:
            A tuple. The first element is the packed id of the skill (item)
            and the second is a json tuple (state, date_str). If the skill
            is not completed, then the date is None.
        """
        mapper_params = context.get().mapreduce_spec.mapper.params
        skill_ids = mapper_params.get('skill_ids', [])
        sprogress = SkillCompletionTracker().get_skills_progress(
            item, skill_ids)

        for skill_id, skill_progress in sprogress.iteritems():
            state, timestamp = skill_progress
            date_str = time.strftime(CountSkillCompletion.DATE_FORMAT,
                                     time.localtime(timestamp))
            if state == SkillCompletionTracker.COMPLETED:
                yield skill_id, transforms.dumps((state, date_str))
            else:
                yield skill_id, transforms.dumps((state, None))

    @staticmethod
    def reduce(skill_id, values):
        """Aggregates the number of students that completed or are in progress.

        Saves the dates of completion in a SkillCompletionAggregate entity.
        The name of the key of this entity is the skill id.

        Args:
            item_id: the packed_name of the skill
            values: a list of json tuples (state, date_str). If the skill
            is not completed, then the date is None.

        Yields:
            A 3-uple with the following schema:
                id, complete_count, in_progress_count
        """
        in_progress_count = 0
        aggregate = defaultdict(lambda: 0)
        completed_count = 0
        for value in values:  # Aggregate the value per date
            state, date = tuple(transforms.loads(value))
            if date:
                aggregate[date] += 1
                completed_count += 1
            elif state == SkillCompletionTracker.IN_PROGRESS:
                in_progress_count += 1

        # Make partial sums
        partial_sum = 0
        for date in sorted(aggregate.keys()):
            partial_sum += aggregate[date]
            aggregate[date] = partial_sum
        # Store the entity
        SkillCompletionAggregate(
            key_name=skill_id, aggregate=transforms.dumps(aggregate)).put()
        yield (skill_id, completed_count, in_progress_count)


class SkillAggregateRestHandler(utils.BaseRESTHandler):
    """REST handler to manage the aggregate count of skill completions."""

    SCHEMA_VERSIONS = ['1']

    URL = '/rest/modules/skill_map/skill_aggregate_count'
    MAX_REQUEST_SIZE = 10

    def get(self):
        """Get a the aggregate information for a set of skills.

        In the request, expects a field ids with a json list of skill ids. If
        more than SkillAggregateRestHandler.MAX_REQUEST_SIZE are sent
        an error response will be returned.

        In the field 'payload' of the response returns a json dictionary:
            {'column_headers': ['Date', 'id1', 'id2', ... ]
             'data': [
                ['date', 'count skill with id1', 'count skill with id2', ...]
            }
        The dates returned are in format CountSkillCompletion.DATE_FORMAT
        """
        if not roles.Roles.is_course_admin(self.app_context):
            transforms.send_json_response(self, 401, 'Access denied.', {})
            return

        ids = self.request.get_all('ids')
        data = []
        headers = ['Date']
        if ids:
            if len(ids) >= self.MAX_REQUEST_SIZE:
                # Given the number of possible skills in a course, this
                # method can take a while finish if we don't limit the
                # size of the request.
                self.validation_error('Request with more than'
                    ' {} skills'.format(self.MAX_REQUEST_SIZE))
                return
            aggregates = []
            dates = set()
            # The complexity of the following cycles is
            # O(len(dates)*log(len(date))). Expect len(dates) < 1000 (3 years)
            for skill_id in ids:
                aggregate = SkillCompletionAggregate.get_by_key_name(
                    str(skill_id))
                if aggregate:
                    headers.append(skill_id)
                    aggregate = transforms.loads(aggregate.aggregate)
                    aggregates.append(aggregate)
                    dates.update(aggregate.keys())
            dates = sorted(list(dates))
            last_row = [0] * len(ids)
            for date in dates:
                for index, count in enumerate(last_row):
                    last_row[index] = max(last_row[index],
                                          aggregates[index].get(date, 0))
                data.append([date] + last_row)  # no aliasing

        payload_dict = {'column_headers': headers, 'data': data}
        transforms.send_json_response(
            self, 200, '', payload_dict=payload_dict)


class SkillMapDataSource(data_sources.SynchronousQuery):

    @staticmethod
    def required_generators():
        return [CountSkillCompletion]

    @classmethod
    def get_name(cls):
        return 'skill_map_analytics'

    @staticmethod
    def fill_values(app_context, template_values, counts_generator):
        """Fills template_values with counts from CountSkillCompletion output.

        Works with the skill_map_analytics.html jinja template.

        Stores in the key 'counts' of template_values a table with the
        following format:
            skill name, count of completions, counts of 'in progress'
        Adds a row for each skill in the output of CountSkillCompletion job.
        """
        course = courses.Course.get(app_context)
        skill_map = SkillMap.load(course)

        results = {int(result[0]): result[1:]
            for result in jobs.MapReduceJob.get_results(counts_generator)}

        template_values['counts'] = transforms.dumps([
            [skill.name] + results[skill.id]
            for skill in skill_map.skills()
            if skill.id in results])


class SkillCompletionTracker(object):
    """Interface for the student completion the skills.

    This class performs the same functions as the class
    models.progress.UnitLessonCompletionTracker. It saves the progress of
    each skill into a models.models.StudentPropertyEntity instance with key
    STUDENT_ID-SkillCompletionTracker.PROPERTY_KEY.

    The value attibute on the StudentPropertyEntity is a json string with
    the following schema:
    {
        skill_id: {skill_progress: timestamp, ... }
    }

    The progress of the skill can have three values, similar to the state of
    a lesson:
        NOT_ATTEMPTED: any of the lessons mapped with the skill are
            UnitLessonCompletionTracker.IN_PROGRESS_STATE
        IN_PROGRESS: at least one of the lessons mapped with the skill is not
            in UnitLessonCompletionTracker.NOT_ATTEMPTED_STATE.
        COMPLETED: all the lessons mapped with the skill are in
            UnitLessonCompletionTracker.COMPLETED_STATE.

    The timestamp is and integer that registers the last change in the state
    of that skill progress.
    """
    # TODO(milit): add manual progress of the skills

    PROPERTY_KEY = 'skill-completion'

    COMPLETED = str(progress.UnitLessonCompletionTracker.COMPLETED_STATE)
    IN_PROGRESS = str(progress.UnitLessonCompletionTracker.IN_PROGRESS_STATE)
    NOT_ATTEMPTED = str(
        progress.UnitLessonCompletionTracker.NOT_STARTED_STATE)

    # Elements of the course which progress affects the progress of skills
    PROGRESS_DEPENDENCIES = set(['lesson'])

    def __init__(self, course=None):
        """Creates an instance of SkillCompletionTracker.

        Args:
            course: the course to load. If the course is None, the
            only actions that can be performed are get_or_create_progress,
            get_skill_progress and update_skill_progress.
        """
        # The course as an optional parameter allows access to the progress
        # without loading the SkillMap. (Like in a map reduce job)
        self.course = course
        self._skill_map = None
        if course:
            self._skill_map = SkillMap.load(course)

    def _get_or_create_progress(self, student):
        sprogress = models.StudentPropertyEntity.get(
            student, self.PROPERTY_KEY)
        if not sprogress:
            sprogress = models.StudentPropertyEntity.create(
                student=student, property_name=self.PROPERTY_KEY)
        return sprogress

    def get_skills_progress(self, student, skill_bunch):
        """Returns the more advanced state of the skill for the student.

        This function retrieves the recorded progress of the skill, does not
        calculate it again from the linear progress of the course.

        Args:
            student: an instance of models.models.StudentEntity class.
            skill_bunch: an iterable of skill ids.

        Returns:
            A dictionary mapping the skill ids in skill_bunch with tuples
            (progress, timestamp). For the state NOT_ATTEMPTED the timestamp
            is always 0.
        """
        sprogress = self._get_or_create_progress(student)
        if not sprogress.value:
            return {id: (self.NOT_ATTEMPTED, 0) for id in skill_bunch}
        sprogress = transforms.loads(sprogress.value)
        result = {}
        for skill_id in skill_bunch:
            skill_progress = sprogress.get(str(skill_id))  # After transforms
            # the keys of the progress are str, not int.
            if not skill_progress:
                result[skill_id] = (self.NOT_ATTEMPTED, 0)
            elif self.COMPLETED in skill_progress:
                result[skill_id] = (self.COMPLETED,
                                    skill_progress[self.COMPLETED])
            elif self.IN_PROGRESS in skill_progress:
                result[skill_id] = (self.IN_PROGRESS,
                                    skill_progress[self.IN_PROGRESS])
        return result

    @staticmethod
    def update_skill_progress(progress_value, skill_id, state):
        """Assigns state to the skill in the student progress.

        If there is a change on the state of the skill, saves the current
        time (seconds since epoch).

        Args:
            progress_value: an dictiory. Corresponds to the value of an
            models.models.StudentPropertyEntity instance that tracks the
            skill progress.
            skill_id: the id of the skill to modify.
            state: a valid progress state for the skill.
        """
        skill_progress = progress_value.get(str(skill_id))
        if not skill_progress:
            progress_value[str(skill_id)] = {state: time.time()}
        elif not state in skill_progress:
            progress_value[str(skill_id)][state] = time.time()

    def recalculate_progress(self, lprogress_tracker, lprogress, skill):
        """Calculates the progress of the skill from the linear progress.

        Args:
            lprogress_tracker: an instance of UnitLessonCompletionTracker.
            lprogress: an instance of StudentPropertyEntity that holds
            the linear progress of the student in the course.
            skill: an instance of SkillInfo or Skill.

        Returns:
            The calculated progress of the skill. If self does not have
            a valid skill_map instance (was initialized with no arguments)
            then this method returns None.
        """
        # It's horrible to pass redundant arguments but we avoid
        # obtaining the lprogress from the db multiple times.
        if not self._skill_map:
            return
        skill_lessons = self._skill_map.get_lessons_for_skill(skill)
        state_counts = defaultdict(lambda: 0)
        for lesson in skill_lessons:
            status = lprogress_tracker.get_lesson_status(
                lprogress, lesson.unit_id, lesson.lesson_id)
            state_counts[status] += 1

        if (state_counts[lprogress_tracker.COMPLETED_STATE] ==
            len(skill_lessons)):
            return self.COMPLETED
        if (state_counts[lprogress_tracker.IN_PROGRESS_STATE] +
            state_counts[lprogress_tracker.COMPLETED_STATE]):
            # At leat one lesson in progress or completed
            return self.IN_PROGRESS
        return self.NOT_ATTEMPTED

    def update_skills(self, student, lprogress, lesson_id):
        """Recalculates and saves the progress of all skills mapped to lesson.

        If self does not have a valid skill_map instance (was initialized
        with no arguments) then this method does not perform any action.

        Args:
            student: an instance of StudentEntity.
            lprogress: an instance of StudentPropertyEntity with the linear
            progress of student.
            lesson_id: the id of the lesson.
        """
        # TODO(milit): Add process for lesson None.
        if not self._skill_map:
            return
        lprogress_tracker = progress.UnitLessonCompletionTracker(self.course)

        sprogress = self._get_or_create_progress(student)
        progress_value = {}
        if sprogress.value:
            progress_value = transforms.loads(sprogress.value)
        skills = self._skill_map.get_skills_for_lesson(lesson_id)
        for skill in skills:
            new_progress = self.recalculate_progress(
                lprogress_tracker, lprogress, skill)
            self.update_skill_progress(progress_value, skill.id, new_progress)

        sprogress.value = transforms.dumps(progress_value)
        sprogress.put()


def post_update_progress(course, student, lprogress, event_entity, event_key):
    """Updates the skill progress after the update of the linear progress.

    Args:
        course: the current course.
        student: an instance of StudentEntity.
        lprogress: an instance of StudentPropertyEntity with the linear
        progress. This function is called before the put() to the database,
        this instance must have the latest changes.
        event_entity: a string. The kind of event or progress that was
        trigered. Only events in SkillCompletionTracker.PROGRESS_DEPENDENCIES
        will be processed, others will be ignored.
        event_key: the element that triggered the update of the linear
        progress. This key is the same used in the linear progress and
        must be compatible with the method
        progress.UnitLessonCompletionTracker.get_elements_from_key. If,
        for example, event_entity is 'lesson', the event key could be
        the key of the lesson or the key of any subentities of the lesson.
    """
    if event_entity not in SkillCompletionTracker.PROGRESS_DEPENDENCIES:
        return

    key_elements = progress.UnitLessonCompletionTracker.get_elements_from_key(
        event_key)
    lesson_id = key_elements.get('lesson')
    unit_id = key_elements.get('unit')
    if not (lesson_id and unit_id and
            course.version == courses.CourseModel13.VERSION):
        return
    if not isinstance(course.find_lesson_by_id(unit_id, lesson_id),
                      courses.Lesson13):
        return
    SkillCompletionTracker(course).update_skills(
        student, lprogress, lesson_id)


def register_tabs():
    dashboard.DashboardHandler.add_sub_nav_mapping(
        'edit', 'skills_table', 'Skills', action='edit_skills_table',
        href='modules/skill_map?action=edit_skills_table')

    # analytics tab for skill competency histograms grouped by unit
    skill_competencies = analytics.Visualization(
        'skill_competencies',
        'Skill Competencies',
        'templates/skill_competencies_analytics.html',
        data_source_classes=[SkillCompetencyDataSource])

    dashboard.DashboardHandler.add_sub_nav_mapping(
        'analytics', 'skill_competencies', 'Skill competencies',
        action='analytics_skill_competencies',
        contents=analytics.TabRenderer([skill_competencies]))

    skill_map_visualization = analytics.Visualization(
        'skill_map',
        'Skill Map Analytics',
        'templates/skill_map_analytics.html',
        data_source_classes=[SkillMapDataSource])

    dashboard.DashboardHandler.add_sub_nav_mapping(
        'analytics', 'skill_map', 'Skill map', action='analytics_skill_map',
        contents=analytics.TabRenderer([skill_map_visualization]))


def lesson_rest_handler_schema_load_hook(lesson_field_registry):
    skill_type = schema_fields.FieldRegistry('Skill')
    skill_type.add_property(schema_fields.SchemaField(
        'skill', 'Skill', 'integer', optional=True, i18n=False))
    lesson_field_registry.add_property(schema_fields.FieldArray(
        'skills', 'Skills', optional=True, item_type=skill_type,
        description=messages.SKILLS_LESSON_DESCRIPTION,
        extra_schema_dict_values={
            'className': (
                'skill-panel inputEx-Field inputEx-ListField content-holder')}))


def lesson_rest_handler_pre_load_hook(lesson, lesson_dict):
    lesson_dict['skills'] = [
        {'skill': skill} for skill in lesson.properties.get(
            constants.SKILLS_KEY, [])]


def lesson_rest_handler_pre_save_hook(lesson, lesson_dict):
    if 'skills' in lesson_dict:
        lesson.properties[constants.SKILLS_KEY] = [
            item['skill'] for item in lesson_dict['skills']]


def course_outline_extra_info_decorator(course, unit_or_lesson):
    if isinstance(unit_or_lesson, courses.Lesson13):
        lesson = unit_or_lesson
        skill_map = SkillMap.load(course)
        # TODO(jorr): Should this list be being created by the JS library?
        skills = safe_dom.Element('ol', className='skill-display-root')
        for skill in skill_map.get_skills_for_lesson(lesson.lesson_id):
            skills.add_child(
                safe_dom.Element('li', className='skill').add_text(skill.name))
        return skills
    return None


def question_rest_handler_schema_load_hook(question_field_registry):
    skill_type = schema_fields.FieldRegistry('Skill')
    skill_type.add_property(schema_fields.SchemaField(
        'skill', 'Skill', 'integer', optional=True, i18n=False))
    question_field_registry.add_property(schema_fields.FieldArray(
        'skills', 'Skills', optional=True, item_type=skill_type,
        description=messages.SKILLS_QUESTION_DESCRIPTION,
        extra_schema_dict_values={
            'className': 'skill-panel inputEx-Field inputEx-ListField'}))


def question_rest_handler_pre_load_hook(question, question_dict):
    question_dict['skills'] = [
        {'skill': skill} for skill in question.dict.get(
            constants.SKILLS_KEY, [])]


def question_rest_handler_pre_save_hook(question, question_dict):
    if 'skills' in question_dict:
        question.dict[constants.SKILLS_KEY] = [
            x['skill'] for x in question_dict['skills']]


def welcome_handler_import_skills_callback(app_ctx, unused_errors):
    """Loads, parses and verifies all content for a course."""

    old_namespace = namespace_manager.get_namespace()
    try:
        namespace_manager.set_namespace(app_ctx.get_namespace_name())
        import_skill_map(app_ctx)
    finally:
        namespace_manager.set_namespace(old_namespace)


def filter_visible_lessons(handler, student, skill):
    """Filter out references to lessons which are not visible."""
    visible_lessons = []
    course = handler.get_course()
    for lesson_location in skill.lessons:
        unit, lesson = resources_display.ResourceLesson.get_resource(
            handler.get_course(), lesson_location.id)
        if not (
            course.is_unit_available(unit) and
            course.is_lesson_available(unit, lesson) and
            unit in handler.get_track_matching_student(student)
        ):
            continue
        visible_lessons.append(lesson_location)

    # pylint: disable=protected-access
    cloned_skill_info = SkillInfo(skill._skill, lessons=visible_lessons,
        measure=skill.competency_measure,
        topo_sort_index=skill._topo_sort_index)
    cloned_skill_info._prerequisites = skill._prerequisites
    # pylint: enable=protected-access

    return cloned_skill_info


def not_in_this_lesson(handler, lesson, student, skills):
    """Filter out skills which are taught in the current lesson."""
    return [
        filter_visible_lessons(handler, student, skill) for skill in skills
        if lesson.lesson_id not in [x.id for x in skill.lessons]]


def lesson_title_provider(handler, app_context, lesson, student):
    if not isinstance(lesson, courses.Lesson13):
        return None

    env = courses.Course.get_environ(app_context)
    if not env['course'].get('display_skill_widget'):
        return None

    if isinstance(student, models.TransientStudent):
        skill_map = SkillMap.load(handler.get_course())
    else:
        skill_map = SkillMap.load(
            handler.get_course(), user_id=student.user_id)
    skills = skill_map.get_skills_for_lesson(lesson.lesson_id)

    depends_on_skills = set()
    leads_to_skills = set()
    dependency_map = {}
    for skill in skills:
        skill = filter_visible_lessons(handler, student, skill)
        prerequisites = skill.prerequisites
        successors = skill_map.successors(skill)
        depends_on_skills.update(prerequisites)
        leads_to_skills.update(successors)
        dependency_map[skill.id] = {
            'depends_on': [s.id for s in prerequisites],
            'leads_to': [s.id for s in successors]
        }

    template_values = {
        'lesson': lesson,
        'can_see_drafts': custom_modules.can_see_drafts(app_context),
        'is_course_admin': roles.Roles.is_course_admin(app_context),
        'is_read_write_course': app_context.fs.is_read_write(),
        'skills': skills,
        'depends_on_skills': not_in_this_lesson(
            handler, lesson, student, depends_on_skills),
        'leads_to_skills': not_in_this_lesson(
            handler, lesson, student, leads_to_skills),
        'dependency_map': transforms.dumps(dependency_map),
        'display_skill_level_legend': (
            False if isinstance(student, models.TransientStudent) else True)
    }
    return jinja2.Markup(
        handler.get_template('lesson_header.html', [TEMPLATES_DIR]
    ).render(template_values))


def widget_display_flag_schema_provider(unused_course):
    return schema_fields.SchemaField(
        'course:display_skill_widget', 'Show Skills',
        'boolean', optional=True,
        description=messages.SKILLS_SHOW_SKILLS_DESCRIPTION)


def import_skill_map(app_ctx):
    fn = os.path.join(
        appengine_config.BUNDLE_ROOT, 'data', 'skills.json')
    with open(fn, 'r') as fin:
        nodes = json.loads(fin.read())

    # add skills
    id_to_key = {}
    key_to_id = {}
    key_to_nodes = {}
    skill_graph = SkillGraph.load()
    for node in nodes:
        skill = skill_graph.add(Skill.build(node['name'], node['description']))
        id_to_key[node['id']] = skill.id
        key_to_id[skill.id] = node['id']
        key_to_nodes[skill.id] = node

    # add skills prerequisites
    skill_graph = SkillGraph.load()
    for skill in skill_graph.skills:
        key = skill.id
        node = key_to_nodes[key]
        prerequisite_ids = node.get('prerequisites')
        if prerequisite_ids:
            pre_keys = [id_to_key[pid] for pid in prerequisite_ids]
            for pre_key in pre_keys:
                try:
                    skill_graph.add_prerequisite(key, pre_key)
                except AssertionError:
                    logging.exception(
                        'Invalid skill prerequisite: %s, %s', key, pre_key)

    # build mapping from lesson index to lesson id
    course = courses.Course(None, app_context=app_ctx)
    units = {u.unit_id: u for u in course.get_units()}
    lesson_map = {}
    for lesson in course.get_lessons_for_all_units():
        unit = units[lesson.unit_id]
        lesson_map[(unit.index, lesson.index)] = lesson

    # update lessons properties with skill ids
    skill_graph = SkillGraph.load()
    for skill in skill_graph.skills:
        node = key_to_nodes[skill.id]
        for loc in node['locations']:
            ul_tuple = (loc['unit'], loc['lesson'])
            lesson = lesson_map[ul_tuple]
            lesson.properties.setdefault(
                constants.SKILLS_KEY, []).append(skill.id)
            assert course.update_lesson(lesson)
    course.save()


def skills_progress_provider(handler, app_context, student):
    """Displays student progress on the profile page."""

    if not app_context.is_editable_fs():
        return None

    env = courses.Course.get_environ(app_context)
    if not env['course'].get('display_skill_widget'):
        return None

    course = handler.get_course()
    if course.version == courses.COURSE_MODEL_VERSION_1_2:
        return None

    skill_map = SkillMap.load(handler.get_course(), user_id=student.user_id)
    skill_recommender = recommender.SkillRecommender.instance(skill_map)
    recommended, learned = skill_recommender.recommend()

    template_values = {
        'recently_learned_skills': learned[:4],
        'learn_next_skills': recommended[:4],
        'skills_exist': len(skill_map.skills()) > 0
    }
    return jinja2.Markup(
        handler.get_template('skills_progress.html', [TEMPLATES_DIR]
    ).render(template_values))


def notify_module_enabled():
    outline.COURSE_OUTLINE_EXTRA_INFO_ANNOTATORS.append(
        course_outline_extra_info_decorator)
    outline.COURSE_OUTLINE_EXTRA_INFO_TITLES.append('Skills')
    dashboard.DashboardHandler.EXTRA_CSS_HREF_LIST.append(
        '/modules/skill_map/_static/css/common.css')
    dashboard.DashboardHandler.EXTRA_CSS_HREF_LIST.append(
        '/modules/skill_map/_static/css/course_outline.css')
    dashboard.DashboardHandler.EXTRA_CSS_HREF_LIST.append(
        '/modules/skill_map/_static/css/skill_tagging.css')
    dashboard.DashboardHandler.EXTRA_JS_HREF_LIST.append(
        '/modules/skill_map/resources/js/course_outline.js')
    dashboard.DashboardHandler.EXTRA_JS_HREF_LIST.append(
        '/modules/skill_map/resources/js/skill_tagging_lib.js')
    dashboard.DashboardHandler.EXTRA_JS_HREF_LIST.append(
        '/modules/skill_map/resources/js/skills_competencies_analytics.js')
    dashboard.DashboardHandler.ADDITIONAL_DIRS.append(TEMPLATES_DIR)

    lessons_controller.UnitHandler.set_lesson_title_provider(
        lesson_title_provider)
    utils.StudentProfileHandler.EXTRA_PROFILE_SECTION_PROVIDERS.append(
        skills_progress_provider)

    LessonRESTHandler.SCHEMA_LOAD_HOOKS.append(
        lesson_rest_handler_schema_load_hook)
    LessonRESTHandler.PRE_LOAD_HOOKS.append(
        lesson_rest_handler_pre_load_hook)
    LessonRESTHandler.PRE_SAVE_HOOKS.append(
        lesson_rest_handler_pre_save_hook)

    BaseQuestionRESTHandler.SCHEMA_LOAD_HOOKS.append(
        question_rest_handler_schema_load_hook)
    BaseQuestionRESTHandler.PRE_LOAD_HOOKS.append(
        question_rest_handler_pre_load_hook)
    BaseQuestionRESTHandler.PRE_SAVE_HOOKS.append(
        question_rest_handler_pre_save_hook)

    # TODO(jorr): Use HTTP GET rather than including them as templates
    LessonRESTHandler.ADDITIONAL_DIRS.append(os.path.join(TEMPLATES_DIR))
    LessonRESTHandler.EXTRA_JS_FILES.append('skill_tagging.js')

    McQuestionRESTHandler.ADDITIONAL_DIRS.append(TEMPLATES_DIR)
    McQuestionRESTHandler.EXTRA_JS_FILES.append('skill_tagging.js')
    SaQuestionRESTHandler.ADDITIONAL_DIRS.append(TEMPLATES_DIR)
    SaQuestionRESTHandler.EXTRA_JS_FILES.append('skill_tagging.js')

    transforms.CUSTOM_JSON_ENCODERS.append(LocationInfo.json_encoder)
    transforms.CUSTOM_JSON_ENCODERS.append(SkillInfo.json_encoder)

    CoursesItemRESTHandler.COPY_SAMPLE_COURSE_HOOKS.append(
        welcome_handler_import_skills_callback)
    courses.ADDITIONAL_ENTITIES_FOR_COURSE_IMPORT.add(_SkillEntity)

    courses.Course.OPTIONS_SCHEMA_PROVIDERS[MODULE_NAME].append(
        widget_display_flag_schema_provider)
    courses.Course.OPTIONS_SCHEMA_PROVIDER_TITLES[
        MODULE_NAME] = MODULE_TITLE
    settings.CourseSettingsHandler.register_settings_section(
        MODULE_NAME, title=MODULE_TITLE)

    progress.UnitLessonCompletionTracker.POST_UPDATE_PROGRESS_HOOK.append(
        post_update_progress)

    data_sources.Registry.register(SkillMapDataSource)

    data_sources.Registry.register(SkillCompetencyDataSource)

    resource.Registry.register(ResourceSkill)
    i18n_dashboard.TranslatableResourceRegistry.register(
        TranslatableResourceSkill)

    register_tabs()

    competency.notify_module_enabled()


def register_module():
    """Registers this module in the registry."""

    global_routes = [
        (RESOURCES_URI + '/js/course_outline.js', tags.JQueryHandler),
        (RESOURCES_URI + '/js/lesson_header.js', tags.JQueryHandler),
        (RESOURCES_URI + '/js/skills_progress.js', tags.JQueryHandler),
        (RESOURCES_URI + '/js/skill_tagging_lib.js', tags.JQueryHandler),
        (RESOURCES_URI + '/js/skills_competencies_analytics.js',
         tags.JQueryHandler),
        (RdfBuilder.SCHEMA_URL, SkillMapRdfSchemaHandler),
    ]

    namespaced_routes = [
        (LocationListRestHandler.URL, LocationListRestHandler),
        (SkillRestHandler.URL, SkillRestHandler),
        (SkillMapHandler.URL, SkillMapHandler),
        (SkillAggregateRestHandler.URL, SkillAggregateRestHandler),
        (RdfBuilder.DATA_URL, SkillMapRdfHandler),
    ]

    global skill_mapping_module  # pylint: disable=global-statement
    skill_mapping_module = custom_modules.Module(
        MODULE_TITLE,
        'Provide skill mapping of course content',
        global_routes,
        namespaced_routes,
        notify_module_enabled=notify_module_enabled)

    return skill_mapping_module
