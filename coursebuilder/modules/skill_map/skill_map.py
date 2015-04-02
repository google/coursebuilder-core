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
import time

from collections import defaultdict

import appengine_config
from common import caching
from common import crypto
from common import resource
from common import safe_dom
from common import schema_fields
from common import tags
from controllers import lessons
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
from modules.admin.admin import WelcomeHandler
from modules import courses as courses_module
from modules.dashboard import dashboard
from modules.dashboard import tabs
from modules.dashboard.unit_lesson_editor import LessonRESTHandler
from modules.i18n_dashboard import i18n_dashboard
from modules.skill_map import skill_map_metrics

from google.appengine.ext import db
from google.appengine.api import namespace_manager

skill_mapping_module = None

# Folder where Jinja template files are stored
TEMPLATES_DIR = os.path.join(
    appengine_config.BUNDLE_ROOT, 'modules', 'skill_map', 'templates')

# URI for skill map css, js, amd img assets.
RESOURCES_URI = '/modules/skill_map/resources'

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

        location_type = schema_fields.FieldRegistry('Location')
        location_type.add_property(schema_fields.SchemaField(
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
            'locations', 'Locations', item_type=location_type,
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
        SkillMap.clear_all()

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
        _assert(skill.id is None, 'Skill has already been added', errors)

        for prerequisite_id in skill.prerequisite_ids:
            _assert(
                prerequisite_id in self._skills,
                'Skill has non-existent prerequisite', errors)

        self._validate_unique_skill_name(skill.id, skill.name, errors)

        skill_id = _SkillDao.save(skill)
        new_skill = Skill(skill_id, skill.dict)
        self._skills[skill_id] = new_skill
        self._rebuild()

        return new_skill

    def update(self, sid, attributes, errors):
        _assert(self.get(sid), 'Skill does not exist', errors)

        # pylint: disable=protected-access
        prerequisite_ids = [
            x['id'] for x in attributes.get('prerequisites', [])]
        for pid in prerequisite_ids:
            self._validate_prerequisite(sid, pid, errors)

        # No duplicate prerequisites
        _assert(
            len(set(prerequisite_ids)) == len(prerequisite_ids),
            'Prerequisites must be unique', errors)

        self._validate_unique_skill_name(sid, attributes.get('name'), errors)

        if errors:
            return sid

        skill_id = _SkillDao.save(Skill(sid, attributes))
        self._skills[skill_id] = Skill(skill_id, attributes)
        self._rebuild()

        return skill_id

    def delete(self, skill_id, errors=None):
        """Remove a skill from the skill map."""
        _assert(
            skill_id in self._skills,
            'Skill is not present in the skill map', errors)

        successors = self.successors(skill_id)
        for successor in successors:
            prerequisite_ids = successor.prerequisite_ids
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
            for prerequisite_id in skill.prerequisite_ids]

    def _validate_prerequisite(self, sid, pid, errors=None):
        _assert(
            sid in self._skills, 'Skill does not exist', errors)
        _assert(
            pid in self._skills,
            'Prerequisite does not exist', errors)

        # No length-1 cycles (ie skill which is its own prerequisite)  allowed
        _assert(
            sid != pid,
            'A skill cannot be its own prerequisite', errors)

    def _validate_unique_skill_name(self, skill_id, name, errors):
        for other_skill in self.skills:
            if other_skill.id == skill_id:
                continue
            _assert(
                name != other_skill.name, 'Name must be unique', errors)

    def add_prerequisite(self, skill_id, prerequisite_skill_id, errors=None):
        self._validate_prerequisite(skill_id, prerequisite_skill_id, errors)

        skill = self._skills.get(skill_id)
        prerequisite_skills = skill.prerequisite_ids
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
        prerequisite_skills = skill.prerequisite_ids
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


class LocationInfo(object):
    """Info object for mapping skills to content locations."""

    def __init__(self, unit, lesson):
        assert lesson.unit_id == unit.unit_id
        self._unit = unit
        self._lesson = lesson

    @property
    def key(self):
        return resources_display.ResourceLesson.get_key(self._lesson)

    @property
    def label(self):
        if self._lesson.index is None:
            return '%s.' % self._unit.index
        return '%s.%s' % (self._unit.index, self._lesson.index)

    @property
    def href(self):
        return 'unit?unit=%s&lesson=%s' % (
            self._unit.unit_id, self._lesson.lesson_id)

    @property
    def edit_href(self):
        return 'dashboard?action=edit_lesson&key=%s' % self._lesson.lesson_id

    @property
    def lesson(self):
        return self._lesson

    @property
    def unit(self):
        return self._unit

    @property
    def sort_key(self):
        return self._unit.unit_id, self._lesson.lesson_id

    @classmethod
    def json_encoder(cls, obj):
        if isinstance(obj, cls):
            return {
                'key': str(obj.key),
                'label': obj.label,
                'href': obj.href,
                'edit_href': obj.edit_href,
                'lesson': obj.lesson.title,
                'unit': obj.unit.title,
                'sort_key': obj.sort_key
            }
        return None


class SkillInfo(object):
    """Skill info object for skills with lesson and unit ids."""

    def __init__(self, skill, locations=None, topo_sort_index=None):
        assert skill
        self._skill = skill
        self._locations = locations or []
        self._prerequisites = []
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
    def locations(self):
        return self._locations

    def set_topo_sort_index(self, topo_sort_index):
        self._topo_sort_index = topo_sort_index

    def sort_key(self):
        if self._locations:
            loc = min(sorted(self._locations, key=lambda x: x.sort_key))
            return loc.unit.unit_id, loc.lesson.lesson_id
        return None, None

    def topo_sort_key(self):
        return self.sort_key() + (self._topo_sort_index, )

    @classmethod
    def json_encoder(cls, obj):
        if isinstance(obj, cls):
            return {
                'id': obj.id,
                'name': obj.name,
                'description': obj.description,
                'prerequisite_ids': [s.id for s in obj.prerequisites],
                'locations': obj.locations,
                'sort_key': obj.sort_key(),
                'topo_sort_key': obj.topo_sort_key()
            }
        return None


class SkillMapError(Exception):
    pass


class SkillMap(caching.RequestScopedSingleton):
    """Provides API to access the course skill map."""

    def __init__(self, skill_graph, course):
        self._rebuild(skill_graph, course)

    def _rebuild(self, skill_graph, course):
        self._skill_graph = skill_graph
        self._course = course

        self._units = dict([(u.unit_id, u) for u in self._course.get_units()])

        self._lessons_by_skill = {}
        for lesson in self._course.get_lessons_for_all_units():
            skill_list = lesson.properties.get(LESSON_SKILL_LIST_KEY, [])
            for skill_id in skill_list:
                self._lessons_by_skill.setdefault(skill_id, []).append(lesson)

        self._skill_infos = {}
        for skill in self._skill_graph.skills:
            locations = []
            for lesson in self._lessons_by_skill.get(skill.id, []):
                unit = self._units[lesson.unit_id]
                locations.append(LocationInfo(unit, lesson))
            self._skill_infos[skill.id] = SkillInfo(skill, locations)
        for skill in self._skill_graph.skills:
            prerequisites = []
            for pid in skill.prerequisite_ids:
                prerequisites.append(self._skill_infos[pid])
            self._skill_infos[skill.id].prerequisites = prerequisites

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

    @classmethod
    def load(cls, course):
        skill_graph = SkillGraph.load()
        return cls.instance(skill_graph, course)

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
        skill_list = lesson.properties.get(LESSON_SKILL_LIST_KEY, [])
        return [self._skill_infos[skill_id] for skill_id in skill_list]

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

    def get_skill(self, skill_id):
        return self._skill_infos[skill_id]

    def add_skill_to_lessons(self, skill, locations):
        """Add the skill to the given lessons.

        Args:
            skill: SkillInfo. The skill to be added
            locations: Iterable of LocationInfo. The locations to add the skill.
        """        # Add back references to the skill from the request payload
        for loc in locations:
            unit, lesson = resource.Key.fromstring(loc['key']).get_resource(
                self._course)
            lesson.properties.setdefault(LESSON_SKILL_LIST_KEY, []).append(
                skill.id)
            assert self._course.update_lesson(lesson)
            # pylint: disable=protected-access
            skill._locations.append(LocationInfo(unit, lesson))
        self._course.save()
        self._lessons_by_skill.setdefault(skill.id, []).extend(locations)

    def delete_skill_from_lessons(self, skill):
        #TODO(broussev): check, and if need be, refactor pre-save lesson hooks
        if not self._lessons_by_skill.get(skill.id):
            return
        for lesson in self._lessons_by_skill[skill.id]:
            lesson.properties[LESSON_SKILL_LIST_KEY].remove(skill.id)
            assert self._course.update_lesson(lesson)
        self._course.save()
        del self._lessons_by_skill[skill.id]
        # pylint: disable=protected-access
        skill._locations = []


class LocationListRestHandler(utils.BaseRESTHandler):
    """REST handler to list all locations."""

    URL = '/rest/modules/skill_map/location_list'

    def get(self):
        if not roles.Roles.is_course_admin(self.app_context):
            transforms.send_json_response(self, 401, 'Access denied.', {})
            return

        location_list = []
        for lesson in self.get_course().get_lessons_for_all_units():
            unit = self.get_course().find_unit_by_id(lesson.unit_id)
            location_list.append(LocationInfo(unit, lesson))

        payload_dict = {'location_list': location_list}
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
            'skill_list': skill_map.skills(),
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

        # Note, first delete from lessons and then from the skill graph
        skill_map.delete_skill_from_lessons(skill)
        skill_graph.delete(key, errors)

        skill_map = SkillMap.load(self.get_course())

        if errors:
            self.validation_error('\n'.join(errors), key=key)
            return

        payload_dict = {
            'skill_list': skill_map.skills(),
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

        errors = []

        course = self.get_course()
        skill_graph = SkillGraph.load()

        if key:
            key_after_save = skill_graph.update(key, python_dict, errors)
        else:
            skill = Skill.build(
                python_dict.get('name'), python_dict.get('description'),
                python_dict.get('prerequisites'))
            key_after_save = skill_graph.add(skill, errors=errors).id

        skill_map = SkillMap.load(course)
        skill = skill_map.get_skill(key_after_save)

        locations = python_dict.get('locations', [])
        skill_map.delete_skill_from_lessons(skill)
        skill_map.add_skill_to_lessons(skill, locations)

        if errors:
            self.validation_error('\n'.join(errors), key=key)
            return

        payload_dict = {
            'key': key_after_save,
            'skill': skill,
            'skill_list': skill_map.skills(),
            'diagnosis': skill_map_metrics.SkillMapMetrics(skill_map).diagnose()
        }

        transforms.send_json_response(
            self, 200, 'Saved.', payload_dict=payload_dict)


class SkillMapHandler(dashboard.DashboardHandler):

    ACTION = 'skill_map'

    URL = '/modules/skill_map'

    NAV_BAR_TAB = 'Skill Map'

    def get_skill_map(self):
        self.course = courses.Course(self)
        if not self.course.app_context.is_editable_fs():
            self.render_page({
                'page_title': self.format_title('Skills Map'),
                'main_content': jinja2.utils.Markup(
                    '<h1>Read-only course.</h1>')
            })
            return

        tab = self.request.get('tab')

        if tab == 'skills_table':
            self.get_skills_table()
        elif tab == 'dependency_graph':
            self.get_dependency_graph()

    def get_skills_table(self):
        skill_map = SkillMap.load(self.course)
        skills = skill_map.skills() or []

        template_values = {
            'skills_autocomplete': json.dumps(
                [{'id': s.id, 'label': s.name} for s in skills])}

        main_content = self.get_template(
            'skills_table.html', [TEMPLATES_DIR]).render(template_values)

        self.render_page({
            'page_title': self.format_title('Skills Table'),
            'main_content': jinja2.utils.Markup(main_content)})

    def get_dependency_graph(self):
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
            'main_content': jinja2.utils.Markup(main_content)
        })


class SkillCompletionAggregate(models.BaseEntity):
    """Representation for the count of skill completions during time.

    Each entity of this class must be created using the skill_id as a
    key name.

    The aggregate field is a json string representing a dictionary. It
    maps dates in skill_map.skill_map.CountSkillCompletion.DATE_FORMAT
    with the number of students that completed that skill before the given
    date.
    """
    name = db.StringProperty()
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
        result = {}
        for skill in skill_map.skills():
            packed_name = self.pack_name(skill.id, skill.name)
            if not packed_name:
                logging.warning('Skill not processed: the id can\'t be packed.'
                                ' Id %s', skill.id)
                continue
            result[skill.id] = packed_name
        return {'skills': result}

    @staticmethod
    def pack_name(skill_id, skill_name):
        join_str = '--'
        if join_str not in str(skill_id):
            return '{}{}{}'.format(skill_id, join_str, skill_name)
        return None

    @staticmethod
    def unpack_name(packed_name):
        return packed_name.split('--', 1)

    @staticmethod
    def map(item):
        """Extracts the skill progress of the student.

        Yields:
            A tuple. The first element is the packed id of the skill (item)
            and the second is a json tuple (state, date_str). If the skill
            is not completed, then the date is None.
        """
        mapper_params = context.get().mapreduce_spec.mapper.params
        skills = mapper_params.get('skills', {})
        sprogress = SkillCompletionTracker().get_skills_progress(
            item, skills.keys())

        for skill_id, skill_progress in sprogress.iteritems():
            state, timestamp = skill_progress
            date_str = time.strftime(CountSkillCompletion.DATE_FORMAT,
                                     time.localtime(timestamp))
            packed_name = skills[skill_id]
            if state == SkillCompletionTracker.COMPLETED:
                yield packed_name, transforms.dumps((state, date_str))
            else:
                yield packed_name, transforms.dumps((state, None))

    @staticmethod
    def reduce(item_id, values):
        """Aggregates the number of students that completed or are in progress.

        Saves the dates of completion in a SkillCompletionAggregate entity.
        The name of the key of this entity is the skill id.

        Args:
            item_id: the packed_name of the skill
            values: a list of json tuples (state, date_str). If the skill
            is not completed, then the date is None.

        Yields:
            A 4-uple with the following schema:
                id, name, complete_count, in_progress_count
        """
        skill_id, name = CountSkillCompletion.unpack_name(item_id)
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
        SkillCompletionAggregate(key_name=str(skill_id), name=name,
                                 aggregate=transforms.dumps(aggregate)).put()
        yield (skill_id, name, completed_count, in_progress_count)


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
        result = jobs.MapReduceJob.get_results(counts_generator)
        # remove the id of the skill
        result = [i[1:] for i in result]
        template_values['counts'] = transforms.dumps(sorted(result))


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
    tabs.Registry.register(
        'skill_map', 'skills_table', 'Skills Table',
        href='modules/skill_map?action=skill_map&tab=skills_table')
    tabs.Registry.register(
        'skill_map', 'dependency_graph', 'Skills Graph',
        href='modules/skill_map?action=skill_map&tab=dependency_graph')

    skill_map_visualization = analytics.Visualization(
        'skill_map',
        'Skill Map Analytics',
        'templates/skill_map_analytics.html',
        data_source_classes=[SkillMapDataSource])
    tabs.Registry.register('analytics', 'skill_map', 'Skill Map',
                           [skill_map_visualization])


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
        skill_map = SkillMap.load(course)
        # TODO(jorr): Should this list be being created by the JS library?
        skill_list = safe_dom.Element('ol', className='skill-display-root')
        for skill in skill_map.get_skills_for_lesson(lesson.lesson_id):
            skill_list.add_child(
                safe_dom.Element('li', className='skill').add_text(skill.name))
        return skill_list
    return None


def welcome_handler_import_skills_callback(app_ctx, unused_errors):
    """Loads, parses and verifies all content for a course."""

    old_namespace = namespace_manager.get_namespace()
    try:
        namespace_manager.set_namespace(app_ctx.get_namespace_name())
        import_skill_map(app_ctx)
    finally:
        namespace_manager.set_namespace(old_namespace)


def lesson_title_provider(handler, app_context, unit, lesson, student):
    if not isinstance(lesson, courses.Lesson13):
        return None

    env = courses.Course.get_environ(app_context)
    if env['course'].get('display_skill_widget') is False:
        return None

    skill_map = SkillMap.load(handler.get_course())
    skill_list = skill_map.get_skills_for_lesson(lesson.lesson_id)

    def filter_visible_locations(skill):
        """Filter out references to lessons which are not visible."""
        locations = []
        for location in skill.locations:
            if not (
                location.unit.now_available
                and location.unit in handler.get_track_matching_student(student)
                and location.lesson.now_available
            ):
                continue
            locations.append(location)

        # pylint: disable=protected-access
        clone = SkillInfo(skill._skill, locations=locations,
            topo_sort_index=skill._topo_sort_index)
        clone._prerequisites = skill._prerequisites
        # pylint: enable=protected-access

        return clone

    def not_in_this_lesson(skill_list):
        """Filter out skills which are taught in the current lesson."""
        return [
            filter_visible_locations(skill) for skill in skill_list
            if lesson not in [loc.lesson for loc in skill.locations]]

    depends_on_skills = set()
    leads_to_skills = set()
    dependency_map = {}
    for skill in skill_list:
        skill = filter_visible_locations(skill)
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
      'unit': unit,
      'can_see_drafts': courses_module.courses.can_see_drafts(app_context),
      'skill_list': skill_list,
      'depends_on_skills': not_in_this_lesson(depends_on_skills),
      'leads_to_skills': not_in_this_lesson(leads_to_skills),
      'dependency_map': transforms.dumps(dependency_map)
    }
    return jinja2.Markup(
        handler.get_template('lesson_header.html', [TEMPLATES_DIR]
    ).render(template_values))


def widget_display_flag_schema_provider(unused_course):
    return schema_fields.SchemaField(
        'course:display_skill_widget', 'Student Skill Widget',
        'boolean', optional=True, description='Display the skills taught in '
        'each lesson.')


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
                LESSON_SKILL_LIST_KEY, []).append(skill.id)
            assert course.update_lesson(lesson)
    course.save()


def notify_module_enabled():
    def get_action(handler):
        handler.redirect('/modules/skill_map?action=skill_map&tab=skills_table')

    dashboard.DashboardHandler.COURSE_OUTLINE_EXTRA_INFO_ANNOTATORS.append(
        course_outline_extra_info_decorator)
    dashboard.DashboardHandler.COURSE_OUTLINE_EXTRA_INFO_TITLES.append('Skills')
    dashboard.DashboardHandler.add_nav_mapping(
        SkillMapHandler.ACTION, SkillMapHandler.NAV_BAR_TAB)
    dashboard.DashboardHandler.get_actions.append('skill_map')
    setattr(dashboard.DashboardHandler, 'get_skill_map', get_action)
    dashboard.DashboardHandler.EXTRA_CSS_HREF_LIST.append(
        '/modules/skill_map/resources/css/common.css')
    dashboard.DashboardHandler.EXTRA_CSS_HREF_LIST.append(
        '/modules/skill_map/resources/css/course_outline.css')
    dashboard.DashboardHandler.EXTRA_CSS_HREF_LIST.append(
        '/modules/skill_map/resources/css/skill_tagging.css')
    dashboard.DashboardHandler.EXTRA_JS_HREF_LIST.append(
        '/modules/skill_map/resources/js/course_outline.js')
    dashboard.DashboardHandler.EXTRA_JS_HREF_LIST.append(
        '/modules/skill_map/resources/js/skill_tagging_lib.js')

    lessons.UnitHandler.set_lesson_title_provider(lesson_title_provider)

    LessonRESTHandler.SCHEMA_LOAD_HOOKS.append(
        lesson_rest_handler_schema_load_hook)
    LessonRESTHandler.PRE_LOAD_HOOKS.append(
        lesson_rest_handler_pre_load_hook)
    LessonRESTHandler.PRE_SAVE_HOOKS.append(
        lesson_rest_handler_pre_save_hook)
    LessonRESTHandler.REQUIRED_MODULES.append('inputex-list')
    LessonRESTHandler.REQUIRED_MODULES.append('inputex-number')

    # TODO(jorr): Use HTTP GET rather than including them as templates
    LessonRESTHandler.ADDITIONAL_DIRS.append(os.path.join(TEMPLATES_DIR))
    LessonRESTHandler.EXTRA_JS_FILES.append('skill_tagging.js')

    transforms.CUSTOM_JSON_ENCODERS.append(LocationInfo.json_encoder)
    transforms.CUSTOM_JSON_ENCODERS.append(SkillInfo.json_encoder)

    WelcomeHandler.COPY_SAMPLE_COURSE_HOOKS.append(
        welcome_handler_import_skills_callback)
    courses.ADDITIONAL_ENTITIES_FOR_COURSE_IMPORT.add(_SkillEntity)

    courses.Course.OPTIONS_SCHEMA_PROVIDERS.setdefault(
        courses.Course.SCHEMA_SECTION_COURSE, []).append(
            widget_display_flag_schema_provider)

    progress.UnitLessonCompletionTracker.POST_UPDATE_PROGRESS_HOOK.append(
        post_update_progress)

    data_sources.Registry.register(SkillMapDataSource)

    resource.Registry.register(ResourceSkill)
    i18n_dashboard.TranslatableResourceRegistry.register(
        TranslatableResourceSkill)

    register_tabs()


def register_module():
    """Registers this module in the registry."""

    underscore_js_handler = sites.make_zip_handler(os.path.join(
        appengine_config.BUNDLE_ROOT, 'lib', 'underscore-1.4.3.zip'))

    d3_js_handler = sites.make_zip_handler(os.path.join(
        appengine_config.BUNDLE_ROOT, 'lib', 'd3-3.4.3.zip'))

    dep_graph_handler = sites.make_zip_handler(os.path.join(
        appengine_config.BUNDLE_ROOT, 'lib', 'dependo-0.1.4.zip'))

    global_routes = [
        (RESOURCES_URI + '/css/.*', tags.ResourcesHandler),
        (RESOURCES_URI + '/js/course_outline.js', tags.JQueryHandler),
        (RESOURCES_URI + '/js/lesson_header.js', tags.JQueryHandler),
        (RESOURCES_URI + '/js/skill_tagging_lib.js', tags.IifeHandler),
        (RESOURCES_URI + '/d3-3.4.3/(d3.min.js)', d3_js_handler),
        (RESOURCES_URI + '/underscore-1.4.3/(underscore.min.js)',
         underscore_js_handler),
        (RESOURCES_URI + '/dependo-0.1.4/(.*)', dep_graph_handler)
    ]

    namespaced_routes = [
        (LocationListRestHandler.URL, LocationListRestHandler),
        (SkillRestHandler.URL, SkillRestHandler),
        (SkillMapHandler.URL, SkillMapHandler),
        (SkillAggregateRestHandler.URL, SkillAggregateRestHandler)
    ]

    global skill_mapping_module  # pylint: disable=global-statement
    skill_mapping_module = custom_modules.Module(
        'Skill Mapping Module',
        'Provide skill mapping of course content',
        global_routes,
        namespaced_routes,
        notify_module_enabled=notify_module_enabled)

    return skill_mapping_module
