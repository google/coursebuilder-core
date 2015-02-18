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

import appengine_config
from common import crypto
from common import safe_dom
from common import schema_fields
from common import tags
from controllers import sites
from controllers import utils
from models import courses
from models import custom_modules
from models import transforms
from models import models
from models import roles
from modules.admin.admin import WelcomeHandler
from modules.dashboard import dashboard
from modules.dashboard import tabs
from modules.dashboard.unit_lesson_editor import LessonRESTHandler


from google.appengine.ext import db
from google.appengine.api import namespace_manager

skill_mapping_module = None

# Folder where Jinja template files are stored
TEMPLATES_DIR = os.path.join(
    appengine_config.BUNDLE_ROOT, 'modules', 'skill_map', 'templates')

# Folder where css, js, amd img assets are stored.
RESOURCES_PATH = '/modules/skill_map/resources'

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
            for pid in other.prerequisite_ids:
                self._successors.setdefault(pid, []).append(other)

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

        for prerequisite_id in skill.prerequisite_ids:
            _assert(
                prerequisite_id in self._skills,
                'Skill has non-existent prerequisite', errors)

        for other_skill in self.skills:
            _assert(
                skill.name != other_skill.name,
                'Name must be unique', errors)

        skill_id = _SkillDao.save(skill)
        new_skill = Skill(skill_id, skill.dict)
        self._skills[skill_id] = new_skill
        self._rebuild()

        return new_skill

    def update(self, sid, attributes, errors):
        _assert(self.get(sid), 'Skill does not exist', errors)

        # pylint: disable=protected-access
        for pid in [x['id'] for x in attributes.get('prerequisites', [])]:
            _assert(
                pid in self._skills, 'Skill has non-existent prerequisite',
                errors)

        name = attributes.get('name')
        for other_skill in self.skills:
            if other_skill.id == sid:
                continue
            _assert(
                name != other_skill.name, 'Name must be unique', errors)

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
    def label(self):
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
            loc = min(sorted(self._locations, lambda x: x.sort_key))
            return loc.unit.unit_id, loc.lesson.lesson_id
        return None, None

    def topo_sort_key(self):
        return self.sort_key() + (self._topo_sort_index, )


class SkillMapError(Exception):
    pass


class SkillMap(object):
    """Provides API to access the course skill map."""

    def __init__(self, skill_graph, course):
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

    def _build_successors(self):
        successors = {}
        for si in self._skill_infos.values():
            for p in si.prerequisites:
                successors.setdefault(p.id, set()).add(si.id)
            if si.id not in successors:
                successors[si.id] = set()
        return successors

    def _topo_sort(self):
        """Returns topologically sorted co-sets."""

        successors = self._build_successors()
        ret = []
        co_set = set(
            successors.keys()) - reduce(
            set.union, successors.values())
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
        if successors:
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
        return cls(SkillGraph.load(), course)

    def get_lessons_for_skill(self, skill):
        return self._lessons_by_skill.get(skill.id, [])

    def get_skills_for_lesson(self, lesson_id):
        # TODO(jorr): Can we stop relying on the unit and just use lesson id?
        lesson = self._course.find_lesson_by_id(None, lesson_id)
        skill_list = lesson.properties.get(LESSON_SKILL_LIST_KEY, [])
        return [self._skill_graph.get(skill_id) for skill_id in skill_list]

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

        prerequisite_type = schema_fields.FieldRegistry('Prerequisite')

        prerequisite_type.add_property(schema_fields.SchemaField(
            'id', '', 'integer', optional=True, i18n=False))

        prerequisites = schema_fields.FieldArray(
            'prerequisites', 'Prerequisites', item_type=prerequisite_type,
            optional=True)

        schema.add_property(prerequisites)

        return schema

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

        if key:
            key_after_save = SkillGraph.load().update(key, python_dict, errors)
        else:
            skill = Skill.build(
                python_dict.get('name'), python_dict.get('description'),
                python_dict.get('prerequisites'))
            key_after_save = SkillGraph.load().add(skill, errors=errors).id

        if errors:
            self.validation_error('\n'.join(errors), key=key)
            return

        transforms.send_json_response(
            self, 200, 'Saved.', payload_dict={'key': key_after_save})


class TableRow(object):
    """Class to represent a row in the skills table."""

    @property
    def name(self):
        raise NotImplementedError()

    @property
    def class_name(self):
        return ''

    @property
    def spans_all_columns(self):
        return False


class SectionRow(TableRow):
    """A row in the table which serves as a section heading."""

    def __init__(self, name):
        self._name = name

    @property
    def name(self):
        return self._name

    @property
    def class_name(self):
        return 'section-row'

    @property
    def spans_all_columns(self):
        return True


class EmptyRow(SectionRow):
    """A multi-column row in the table which indicates an empty section."""

    def __init__(self, name='Empty section', class_name='empty_section'):
        super(EmptyRow, self).__init__(name)
        self._class_name = class_name

    @property
    def class_name(self):
        return self._class_name


class SkillRow(TableRow):
    """A row in the skills table showing a skill."""

    CLASS = 'skill'

    def __init__(self, skill_info):
        self._skill_info = skill_info

    @property
    def description(self):
        return self._skill_info.description

    @property
    def name(self):
        return self._skill_info.name

    @property
    def prerequisites(self):
        pre = []
        for x in self._skill_info.prerequisites:
            pre.append(x.name)
        return pre

    @property
    def class_name(self):
        return ''


class SkillMapHandler(dashboard.DashboardHandler):

    ACTION = 'skill_map'

    URL = '/modules/skill_map'

    NAV_BAR_TAB = 'Skill Map'

    def _make_table_section(self, data_rows):
        rows = []
        if data_rows:
            rows += data_rows
        else:
            rows.append(EmptyRow())
        return rows

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
        rows = self._make_table_section(skills)

        template_values = {
            'nodes_count': len([]),
            'rows': rows,
            'skill_count': len(rows),
            'skills_autocomplete': json.dumps(
                [{'id': s.id, 'label': s.name} for s in skills])}

        main_content = self.get_template(
            'skills_table.html', [TEMPLATES_DIR]).render(template_values)

        self.render_page({
            'page_title': self.format_title('Skills Table'),
            'main_content': jinja2.utils.Markup(main_content),
            'sections': [{
                'title': 'Skills Table',
                'actions': [],
                'pre': ' '}]})

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
                links.append({'source': n2i[tgt.name], 'target': n2i[src.name]})

        template_values = {
            'nodes': json.dumps(nodes), 'links': json.dumps(links)}

        main_content = self.get_template(
            'dependency_graph.html', [TEMPLATES_DIR]).render(template_values)
        self.render_page({
            'page_title': self.format_title('Dependencies Graph'),
            'main_content': jinja2.utils.Markup(main_content)
        })


def register_tabs():
    tabs.Registry.register(
        'skill_map', 'skills_table', 'Skills Table',
        href='modules/skill_map?action=skill_map&tab=skills_table')
    tabs.Registry.register(
        'skill_map', 'dependency_graph', 'Skills Graph',
        href='modules/skill_map?action=skill_map&tab=dependency_graph')


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


def import_skill_map(app_ctx):
    fn = os.path.join(
        appengine_config.BUNDLE_ROOT, 'data', 'skills.txt')
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
        ul_tuple = (node['unit'], node['lesson'])
        lesson = lesson_map[ul_tuple]
        lesson.properties.setdefault(LESSON_SKILL_LIST_KEY, []).append(skill.id)
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

    WelcomeHandler.COPY_SAMPLE_COURSE_HOOKS.append(
        welcome_handler_import_skills_callback)
    courses.ADDITIONAL_ENTITIES_FOR_COURSE_IMPORT.add(_SkillEntity)

    register_tabs()


def register_module():
    """Registers this module in the registry."""

    underscore_js_handler = sites.make_zip_handler(os.path.join(
        appengine_config.BUNDLE_ROOT, 'lib', 'underscore-1.7.0.zip'))

    global_routes = [
        (os.path.join(RESOURCES_PATH, 'css', '.*'), tags.ResourcesHandler),
        (os.path.join(RESOURCES_PATH, 'js', '.*'), tags.JQueryHandler),
        ('/static/underscore-1.7.0/(underscore.js)', underscore_js_handler),
        ('/static/underscore-1.7.0/(underscore.min.js)', underscore_js_handler)
    ]

    namespaced_routes = [
        (SkillListRestHandler.URL, SkillListRestHandler),
        (SkillRestHandler.URL, SkillRestHandler),
        (SkillMapHandler.URL, SkillMapHandler)
    ]

    global skill_mapping_module  # pylint: disable=global-statement
    skill_mapping_module = custom_modules.Module(
        'Skill Mapping Module',
        'Provide skill mapping of course content',
        global_routes,
        namespaced_routes,
        notify_module_enabled=notify_module_enabled)

    return skill_mapping_module

