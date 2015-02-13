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

import os

import appengine_config
from common import crypto
from common import safe_dom
from common import schema_fields
from controllers import utils
from models import courses
from models import custom_modules
from models import transforms
from models import models
from models import roles
from modules.dashboard.dashboard import DashboardHandler
from modules.dashboard.unit_lesson_editor import LessonRESTHandler


from google.appengine.ext import db


skill_mapping_module = None

# Folder where Jinja template files are stored
TEMPLATES_DIR = os.path.join(
    appengine_config.BUNDLE_ROOT, 'modules', 'skill_map', 'templates')

# Key for storing list of skill id's in the properties table of a Lesson
LESSON_SKILL_LIST_KEY = 'modules.skill_map.skill_list'


def _assert(condition, message, errors):
    """Assert a condition and either log exceptions or raise AssertionError."""
    if not condition:
        if errors is not None:
            errors.append(message)
        else:
            raise AssertionError(message)


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
    def build(cls, name, description):
        return Skill(None, {
            'name': name,
            'description': description,
            'prerequisites': []
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

    def _get_prerequisite_ids(self):
        """Returns the id's of the prerequisites."""
        return {
            item.get("id") for item in self.dict.get('prerequisites', [])}

    def _set_prerequisite_ids(self, prerequisite_ids):
        """Sets the id's of the prerequisites."""
        self.dict['prerequisites'] = [
            {'id': prerequisite_id} for prerequisite_id in prerequisite_ids]


class _SkillDao(models.LastModfiedJsonDao):
    DTO = Skill
    ENTITY = _SkillEntity
    ENTITY_KEY_TYPE = models.BaseJsonDao.EntityKeyTypeId


class SkillGraph(object):
    """Facade to handle the CRUD lifecycle of the skill dependency graph."""

    def __init__(self, id_to_skill_dict):
        # dict mapping skill id to skill
        self._skills = id_to_skill_dict
        # dict mapping skill id to list of successor SkillDTO's
        self._successors = None
        self._rebuild()

    def _rebuild(self):
        self._build_successors()

    def _build_successors(self):
        self._successors = {}
        for other in self._skills.values():
            # pylint: disable=protected-access
            for prerequisite_id in other._get_prerequisite_ids():
                self._successors.setdefault(
                    prerequisite_id, []).append(other)

    @classmethod
    def load(cls):
        return cls(_SkillDao.get_all_mapped())

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
        _assert(skill.id is None, 'Skill has already been added', errors)

        # pylint: disable=protected-access
        for prerequisite_id in skill._get_prerequisite_ids():
            _assert(
                prerequisite_id in self._skills,
                'Skill has non-existent prerequisite', errors)

        for other_skill in self.skills:
            _assert(
                skill.name != other_skill.name,
                'Name must be unique', errors)

        skill_id = _SkillDao.save(skill)
        self._skills[skill_id] = Skill(skill_id, skill.dict)
        self._rebuild()

        return skill_id

    def delete(self, skill_id, errors=None):
        """Remove a skill from the skill map."""
        _assert(
            skill_id in self._skills,
            'Skill is not present in the skill map', errors)

        successors = self.successors(skill_id)
        for successor in successors:
            # pylint: disable=protected-access
            prerequisite_ids = successor._get_prerequisite_ids()
            prerequisite_ids.remove(skill_id)
            # pylint: disable=protected-access
            successor._set_prerequisite_ids(prerequisite_ids)

        _SkillDao.delete(self._skills[skill_id])
        _SkillDao.save_all(successors)

        del self._skills[skill_id]
        self._rebuild()

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
            # pylint: disable=protected-access
            for prerequisite_id in skill._get_prerequisite_ids()]

    def add_prerequisite(self, skill_id, prerequisite_skill_id, errors=None):
        _assert(
            skill_id in self._skills, 'Skill does not exist', errors)
        _assert(
            prerequisite_skill_id in self._skills,
            'Prerequisite does not exist', errors)

        # No length-1 cycles (ie skill which is its own prerequisite)  allowed
        _assert(
            skill_id != prerequisite_skill_id,
            'A skill cannot be its own prerequisite', errors)

        skill = self._skills.get(skill_id)
        # pylint: disable=protected-access
        prerequisite_skills = skill._get_prerequisite_ids()
        _assert(
            prerequisite_skill_id not in prerequisite_skills,
            'This prerequisite has already been set', errors)
        prerequisite_skills.add(prerequisite_skill_id)
        # pylint: disable=protected-access
        skill._set_prerequisite_ids(prerequisite_skills)

        _SkillDao.save(skill)
        self._rebuild()

    def delete_prerequisite(self, skill_id, prerequisite_skill_id, errors=None):
        _assert(
            skill_id in self._skills, 'Skill does not exist', errors)
        _assert(
            prerequisite_skill_id in self._skills,
            'Prerequisite does not exist', errors)

        skill = self._skills[skill_id]
        # pylint: disable=protected-access
        prerequisite_skills = skill._get_prerequisite_ids()
        _assert(
            prerequisite_skill_id in prerequisite_skills,
            'Cannot delete an unset prerequisite.', errors)
        prerequisite_skills.remove(prerequisite_skill_id)
        # pylint: disable=protected-access
        skill._set_prerequisite_ids(prerequisite_skills)

        _SkillDao.save(skill)
        self._rebuild()

    def successors(self, skill_id):
        """Get the immediate successors of the given skill.

        Args:
            skill_id. The id of the skill to find successors of.

        Returns:
            list of Skill.
        """
        return self._successors.get(skill_id, [])


class SkillMap(object):
    """Provides API to access the course skill map."""

    def __init__(self, skill_graph, course):
        self._skill_graph = skill_graph
        self._course = course

        self._lessons_by_skill = {}
        for lesson in self._course.get_lessons_for_all_units():
            skill_list = lesson.properties.get(LESSON_SKILL_LIST_KEY, [])
            for skill_id in skill_list:
                self._lessons_by_skill.setdefault(skill_id, []).append(lesson)

    @classmethod
    def load(cls, app_context):
        return cls(SkillGraph.load(), courses.Course.get(app_context))

    def get_lessons_for_skill(self, skill_id):
        return self._lessons_by_skill.get(skill_id, [])

    def get_skills_for_lesson(self, lesson_id):
        # TODO(jorr): Can we stop relying on the unit and just use lesson id?
        lesson = self._course.find_lesson_by_id(None, lesson_id)
        skill_list = lesson.properties.get(LESSON_SKILL_LIST_KEY, [])
        return [self._skill_graph.get(skill_id) for skill_id in skill_list]


class SkillListRestHandler(utils.BaseRESTHandler):
    """REST handler to list skills."""

    URL = '/rest/modules/skill_map/skill_list'
    XSRF_TOKEN = 'skill-handler'

    def get(self):
        if not roles.Roles.is_course_admin(self.app_context):
            transforms.send_json_response(self, 401, 'Access denied.', {})
            return

        payload_dict = {
            'skill_list': [
                {
                    'id': skill.id,
                    'name': skill.name,
                    'description': skill.description
                } for skill in SkillGraph.load().skills
            ]
         }
        transforms.send_json_response(
            self, 200, '', payload_dict,
            xsrf_token=crypto.XsrfTokenManager.create_xsrf_token(
                self.XSRF_TOKEN))


class SkillRestHandler(utils.BaseRESTHandler):
    """REST handler to manage skills."""

    XSRF_TOKEN = SkillListRestHandler.XSRF_TOKEN
    SCHEMA_VERSIONS = ['1']

    URL = '/rest/modules/skill_map/skill'

    @classmethod
    def get_schema(cls):
        """Return the schema for the skill editor."""

        schema = schema_fields.FieldRegistry(
            'Skill', description='skill')

        schema.add_property(schema_fields.SchemaField(
            'version', '', 'string', optional=True, hidden=True))
        schema.add_property(schema_fields.SchemaField(
            'name', 'Name', 'string', optional=True))
        schema.add_property(schema_fields.SchemaField(
            'description', 'Description', 'text', optional=True))

        return schema

    def put(self):
        request = transforms.loads(self.request.get('request'))

        if not self.assert_xsrf_token_or_fail(
                request, self.XSRF_TOKEN, {}):
            return

        if not roles.Roles.is_course_admin(self.app_context):
            transforms.send_json_response(
                self, 401, 'Access denied.', {})
            return

        payload = request.get('payload')
        json_dict = transforms.loads(payload)
        python_dict = transforms.json_to_dict(
            json_dict, self.get_schema().get_json_schema_dict())

        version = python_dict.get('version')
        if version not in self.SCHEMA_VERSIONS:
            self.validation_error('Version %s not supported.' % version)
            return

        errors = []

        skill = Skill.build(
            python_dict.get('name'), python_dict.get('description'))
        key_after_save = SkillGraph.load().add(skill, errors=errors)

        if errors:
            self.validation_error('\n'.join(errors))
            return

        transforms.send_json_response(
            self, 200, 'Saved.', payload_dict={'key': key_after_save})


def lesson_rest_handler_schema_load_hook(lesson_field_registry):
    skill_type = schema_fields.FieldRegistry('Skill')
    skill_type.add_property(schema_fields.SchemaField(
        'skill', 'Skill', 'number', optional=True, i18n=False))
    lesson_field_registry.add_property(schema_fields.FieldArray(
        'skills', 'Skills', optional=True, item_type=skill_type,
        extra_schema_dict_values={
            'className': 'skill-panel inputEx-Field inputEx-ListField'}))


def lesson_rest_handler_pre_load_hook(lesson, lesson_dict):
    lesson_dict['skills'] = [
        {'skill': skill} for skill in lesson.properties.get(
            LESSON_SKILL_LIST_KEY, [])]


def lesson_rest_handler_pre_save_hook(lesson, lesson_dict):
    if 'skills' in lesson_dict:
        lesson.properties[LESSON_SKILL_LIST_KEY] = [
            item['skill'] for item in lesson_dict['skills']]


def course_outline_extra_info_decorator(course, unit_or_lesson):
    if isinstance(unit_or_lesson, courses.Lesson13):
        lesson = unit_or_lesson
        skill_map = SkillMap.load(course.app_context)
        # TODO(jorr): Should this list be being created by the JS library?
        skill_list = safe_dom.Element('ol', className='skill-display-root')
        for skill in skill_map.get_skills_for_lesson(lesson.lesson_id):
            skill_list.add_child(
                safe_dom.Element('li', className='skill').add_text(skill.name))
        return skill_list
    return None


def notify_module_enabled():
    DashboardHandler.COURSE_OUTLINE_EXTRA_INFO_ANNOTATORS.append(
        course_outline_extra_info_decorator)
    LessonRESTHandler.SCHEMA_LOAD_HOOKS.append(
        lesson_rest_handler_schema_load_hook)
    LessonRESTHandler.PRE_LOAD_HOOKS.append(
        lesson_rest_handler_pre_load_hook)
    LessonRESTHandler.PRE_SAVE_HOOKS.append(
        lesson_rest_handler_pre_save_hook)
    LessonRESTHandler.REQUIRED_MODULES.append('inputex-list')
    LessonRESTHandler.REQUIRED_MODULES.append('inputex-number')
    LessonRESTHandler.ADDITIONAL_DIRS.append(TEMPLATES_DIR)
    LessonRESTHandler.EXTRA_JS_FILES.append('skill_tagging_lib.js')
    LessonRESTHandler.EXTRA_JS_FILES.append('skill_tagging.js')
    LessonRESTHandler.EXTRA_CSS_FILES.append('skill_tagging.css')


def register_module():
    """Registers this module in the registry."""

    global_routes = []
    namespaced_routes = [
        (SkillListRestHandler.URL, SkillListRestHandler),
        (SkillRestHandler.URL, SkillRestHandler)]

    global skill_mapping_module  # pylint: disable=global-statement
    skill_mapping_module = custom_modules.Module(
        'Skill Mapping Module',
        'Provide skill mapping of course content',
        global_routes, namespaced_routes,
        notify_module_enabled=notify_module_enabled)

    return skill_mapping_module
