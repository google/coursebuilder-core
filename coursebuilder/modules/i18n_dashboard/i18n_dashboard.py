# Copyright 2014 Google Inc. All Rights Reserved.
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

"""Module to support internationalization (i18n) workflow."""

__author__ = 'John Orr (jorr@google.com)'

import logging
import os
import urllib

import jinja2
from webapp2_extras import i18n

import appengine_config
from common import crypto
from common import schema_fields
from common import tags
from common import xcontent
from controllers import sites
from controllers import utils
from models import courses
from models import custom_modules
from models import models
from models import roles
from models import transforms
from modules.dashboard import dashboard
from modules.dashboard import question_editor
from modules.dashboard import question_group_editor
from modules.dashboard import unit_lesson_editor
from modules.oeditor import oeditor
from tools import verify

from google.appengine.ext import db


RESOURCES_PATH = '/modules/i18n_dashboard/resources'

TEMPLATES_DIR = os.path.join(
    appengine_config.BUNDLE_ROOT, 'modules', 'i18n_dashboard', 'templates')

VERB_NEW = xcontent.SourceToTargetDiffMapping.VERB_NEW
VERB_CHANGED = xcontent.SourceToTargetDiffMapping.VERB_CHANGED
VERB_CURRENT = xcontent.SourceToTargetDiffMapping.VERB_CURRENT

TYPE_HTML = 'html'
TYPE_STRING = 'string'
TYPE_TEXT = 'text'
TYPE_URL = 'url'


custom_module = None


class ResourceKey(object):
    """Manages key for Course Builder resource.

    Every Course Builder resource can be identified by a type name and a
    type-contextual key. This class holds data related to this keying, and
    manages serialization/deserialization as strings.
    """

    ASSESSMENT_TYPE = 'assessment'
    ASSET_IMG_TYPE = 'asset_img'
    COURSE_SETTINGS_TYPE = 'course_settings'
    LESSON_TYPE = 'lesson'
    LINK_TYPE = 'link'
    QUESTION_GROUP_TYPE = 'question_group'
    QUESTION_MC_TYPE = 'question_mc'
    QUESTION_SA_TYPE = 'question_sa'
    UNIT_TYPE = 'unit'

    RESOURCE_TYPES = [
        ASSESSMENT_TYPE, ASSET_IMG_TYPE, COURSE_SETTINGS_TYPE, LESSON_TYPE,
        LINK_TYPE, QUESTION_GROUP_TYPE, QUESTION_MC_TYPE, QUESTION_SA_TYPE,
        UNIT_TYPE]

    def __init__(self, type_str, key):
        self._type = type_str
        self._key = key
        assert type_str in self.RESOURCE_TYPES, (
            'Unknown resource type: %s' % type_str)

    def __str__(self):
        return '%s:%s' % (self._type, self._key)

    @property
    def type(self):
        return self._type

    @property
    def key(self):
        return self._key

    @classmethod
    def fromstring(cls, key_str):
        index = key_str.index(':')
        return ResourceKey(key_str[:index], key_str[index + 1:])

    def get_title(self, app_context):
        course = courses.Course(None, app_context=app_context)

        if self._type == ResourceKey.UNIT_TYPE:
            return utils.display_unit_title(course.find_unit_by_id(self._key))
        elif self._type == ResourceKey.LESSON_TYPE:
            lesson = course.find_lesson_by_id(None, self._key)
            return utils.display_lesson_title(
                course.get_unit_for_lesson(lesson), lesson)
        elif self._type in [ResourceKey.ASSESSMENT_TYPE, ResourceKey.LINK_TYPE]:
            return course.find_unit_by_id(self._key).title
        elif self._type == ResourceKey.ASSET_IMG_TYPE:
            return self._key
        elif self._type == ResourceKey.COURSE_SETTINGS_TYPE:
            schema = course.create_settings_schema()
            return schema.sub_registries[self._key].title
        elif self._type in [
                ResourceKey.QUESTION_MC_TYPE, ResourceKey.QUESTION_SA_TYPE]:
            qu = models.QuestionDAO.load(self._key)
            return qu.description
        elif self._type in ResourceKey.QUESTION_GROUP_TYPE:
            qgp = models.QuestionGroupDAO.load(self._key)
            return qgp.description
        else:
            return 'none'

    def get_schema(self, app_context):
        course = courses.Course(None, app_context=app_context)
        if self.type == ResourceKey.ASSESSMENT_TYPE:
            return unit_lesson_editor.AssessmentRESTHandler.SCHEMA
        elif self.type == ResourceKey.LINK_TYPE:
            return unit_lesson_editor.LinkRESTHandler.SCHEMA
        elif self.type == ResourceKey.UNIT_TYPE:
            return unit_lesson_editor.UnitRESTHandler.SCHEMA
        elif self.type == ResourceKey.LESSON_TYPE:
            units = course.get_units()
            return unit_lesson_editor.LessonRESTHandler.get_schema(units)
        elif self.type == ResourceKey.COURSE_SETTINGS_TYPE:
            return course.create_settings_schema().clone_only_items_named(
                [self.key])
        elif self.type == ResourceKey.QUESTION_MC_TYPE:
            return question_editor.McQuestionRESTHandler.get_schema()
        elif self.type == ResourceKey.QUESTION_SA_TYPE:
            return question_editor.SaQuestionRESTHandler.get_schema()
        elif self.type == ResourceKey.QUESTION_GROUP_TYPE:
            return question_group_editor.QuestionGroupRESTHandler.get_schema()
        else:
            raise ValueError('Unknown content type: %s' % self.type)

    def get_data_dict(self, app_context):
        course = courses.Course(None, app_context=app_context)
        if self.type == ResourceKey.ASSESSMENT_TYPE:
            unit = course.find_unit_by_id(self.key)
            unit_dict = unit_lesson_editor.UnitTools(course).unit_to_dict(unit)
            return unit_dict
        elif self.type == ResourceKey.LINK_TYPE:
            unit = course.find_unit_by_id(self.key)
            unit_dict = unit_lesson_editor.UnitTools(course).unit_to_dict(unit)
            return unit_dict
        elif self.type == ResourceKey.UNIT_TYPE:
            unit = course.find_unit_by_id(self.key)
            unit_dict = unit_lesson_editor.UnitTools(course).unit_to_dict(unit)
            return unit_dict
        elif self.type == ResourceKey.LESSON_TYPE:
            lesson = course.find_lesson_by_id(None, self.key)
            return unit_lesson_editor.LessonRESTHandler.get_lesson_dict(
                app_context, lesson)
        elif self.type == ResourceKey.COURSE_SETTINGS_TYPE:
            schema = course.create_settings_schema().clone_only_items_named(
                [self.key])
            json_entity = {}
            schema.convert_entity_to_json_entity(
                course.get_environ(app_context), json_entity)
            return json_entity[self.key]
        elif self.type in [
                ResourceKey.QUESTION_MC_TYPE, ResourceKey.QUESTION_SA_TYPE]:
            return models.QuestionDAO.load(int(self.key)).dict
        elif self.type == ResourceKey.QUESTION_GROUP_TYPE:
            return models.QuestionGroupDAO.load(int(self.key)).dict
        else:
            raise ValueError('Unknown content type: %s' % self.type)

    @classmethod
    def get_question_type(cls, qu):
        """Utility to convert between question type codes."""
        if qu.type == models.QuestionDTO.MULTIPLE_CHOICE:
            return ResourceKey.QUESTION_MC_TYPE
        elif qu.type == models.QuestionDTO.SHORT_ANSWER:
            return ResourceKey.QUESTION_SA_TYPE
        else:
            raise ValueError('Unknown question type: %s' % qu.type)


class ResourceBundleKey(object):
    """Manages a key for a resource bundle."""

    def __init__(self, type_str, key, locale):
        self._locale = locale
        self._type = type_str
        self._key = key

    def __str__(self):
        return '%s:%s:%s' % (self._type, self._key, self._locale)

    @property
    def locale(self):
        return self._locale

    @property
    def resource_key(self):
        return ResourceKey(self._type, self._key)

    @classmethod
    def fromstring(cls, key_str):
        type_str, key, locale = key_str.split(':', 2)
        return ResourceBundleKey(type_str, key, locale)


class NamedJsonDAO(models.BaseJsonDao):
    """Base class for DAOs of entities with named keys."""

    ENTITY_KEY_TYPE = models.BaseJsonDao.EntityKeyTypeName

    @classmethod
    def load_or_create(cls, resource_key):
        dto = cls.load(str(resource_key))
        if not dto:
            dto = cls.DTO(str(resource_key), {})
            cls.save(dto)
        return dto


class I18nProgressEntity(models.BaseEntity):
    """The base entity for storing i18n workflow information.

    Each entity represents one resource in the course.
    """

    data = db.TextProperty(indexed=False)


class I18nProgressDTO(object):
    """The lightweight data object for the i18n workflow data."""

    NOT_STARTED = 0
    IN_PROGRESS = 1
    DONE = 2

    IS_I18N_KEY = 'is_i18n'
    PROGRESS_KEY = 'progress'

    def __init__(self, the_id, the_dict):
        self.id = the_id
        self.dict = the_dict

    @property
    def is_translatable(self):
        return self.dict.get(self.IS_I18N_KEY, True)

    @is_translatable.setter
    def is_translatable(self, value):
        assert type(value) == bool
        self.dict[self.IS_I18N_KEY] = value

    def get_progress(self, locale):
        return self.dict.get(self.PROGRESS_KEY, {}).get(
            locale, self.NOT_STARTED)

    def set_progress(self, locale, value):
        progress_dict = self.dict.setdefault(self.PROGRESS_KEY, {})
        progress_dict[locale] = value


class I18nProgressDAO(NamedJsonDAO):
    """Access object for the i18n workflow data."""

    DTO = I18nProgressDTO
    ENTITY = I18nProgressEntity


class ResourceBundleEntity(models.BaseEntity):
    """The base entity for storing i18n resource bundles."""

    data = db.TextProperty(indexed=False)


class ResourceBundleDTO(object):
    """The lightweight data transfer object for resource bundles.

    Resource bundles are keyed by (resource_type, resource_key, locale). The
    data stored in the dict follows the following pattern:

    {
      field_name_1: {
        type: <the value type for the field>,
        source_value: <only used for html type: the undecomposed source_value>,
        data: [
          # A list of source/target pairs. The list is a singleton for plain
          # string data, and is a list of decomposed chunks for html data
          {
            source_value: <the original untranslated string>,
            target_value: <the translated string>,
          }
        ]
      },
      field_name_2: ...
    }
    """

    def __init__(self, the_id, the_dict):
        self.id = the_id
        self.dict = the_dict


class ResourceBundleDAO(NamedJsonDAO):
    """Data access object for resource bundle information."""

    DTO = ResourceBundleDTO
    ENTITY = ResourceBundleEntity


class TableRow(object):
    """Class to represent a row in the dashboard table."""

    @property
    def name(self):
        raise NotImplementedError()

    @property
    def class_name(self):
        return ''

    @property
    def spans_all_columns(self):
        return False


class ResourceRow(TableRow):
    """A row in the dashboard table which displays status of a CB resource."""

    DONE_CLASS = 'done'
    DONE_STRING = 'Done'
    IN_PROGRESS_CLASS = 'in-progress'
    IN_PROGRESS_STRING = 'In progress'
    NOT_STARTED_CLASS = 'not-started'
    NOT_STARTED_STRING = 'Not started'
    NOT_TRANSLATABLE_CLASS = 'not-translatable'

    def __init__(
            self, course, resource, type_str, key,
            i18n_progress_dto=None):
        self._course = course
        self._resource = resource
        self._type = type_str
        self._key = key
        self._i18n_progress_dto = i18n_progress_dto

    @property
    def name(self):
        return ResourceKey(self._type, self._key).get_title(
            self._course.app_context)

    @property
    def class_name(self):
        if self._i18n_progress_dto.is_translatable:
            return ''
        else:
            return self.NOT_TRANSLATABLE_CLASS

    @property
    def resource_key(self):
        return ResourceKey(self._type, self._key)

    @property
    def is_translatable(self):
        return self._i18n_progress_dto.is_translatable

    def status(self, locale):
        progress = self._i18n_progress_dto.get_progress(locale)
        if progress == I18nProgressDTO.NOT_STARTED:
            return self.NOT_STARTED_STRING
        elif progress == I18nProgressDTO.IN_PROGRESS:
            return self.IN_PROGRESS_STRING
        else:
            return self.DONE_STRING

    def status_class(self, locale):
        progress = self._i18n_progress_dto.get_progress(locale)
        if progress == I18nProgressDTO.NOT_STARTED:
            return self.NOT_STARTED_CLASS
        elif progress == I18nProgressDTO.IN_PROGRESS:
            return self.IN_PROGRESS_CLASS
        else:
            return self.DONE_CLASS

    def view_url(self, unused_locale):
        if self._type == ResourceKey.UNIT_TYPE:
            return 'unit?unit=%s' % self._key
        elif self._type == ResourceKey.LESSON_TYPE:
            return 'unit?unit=%s&lesson=%s' % (
                self._resource.unit_id, self._key)
        elif self._type == ResourceKey.ASSESSMENT_TYPE:
            return 'assessment?name=%s' % self._key
        elif self._type == ResourceKey.ASSET_IMG_TYPE:
            return self._key
        elif self._type in [
                ResourceKey.COURSE_SETTINGS_TYPE, ResourceKey.LINK_TYPE,
                ResourceKey.QUESTION_MC_TYPE, ResourceKey.QUESTION_SA_TYPE,
                ResourceKey.QUESTION_GROUP_TYPE]:
            return 'javascript:void(0)'

        raise ValueError('Unknown type %s' % self._type)

    def edit_url(self, locale):
        return 'dashboard?%s' % urllib.urlencode({
            'action': TranslationConsole.ACTION,
            'key': ResourceBundleKey(self._type, self._key, locale)})


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

    def __init__(self, name='Empty section'):
        super(EmptyRow, self).__init__(name)

    @property
    def class_name(self):
        return 'empty-section'


class IsTranslatableRestHandler(utils.BaseRESTHandler):
    """REST handler to respond to setting a resource as (non-)translatable."""

    URL = '/rest/modules/i18n_dashboard/is_translatable'
    XSRF_TOKEN_NAME = 'is-translatable'

    def post(self):
        request = transforms.loads(self.request.get('request'))
        if not self.assert_xsrf_token_or_fail(
                request, self.XSRF_TOKEN_NAME, {}):
            return

        if not unit_lesson_editor.CourseOutlineRights.can_edit(self):
            transforms.send_json_response(self, 401, 'Access denied.', {})
            return

        payload = request.get('payload')
        i18n_progress_dto = I18nProgressDAO.load_or_create(
            payload['resource_key'])
        i18n_progress_dto.is_translatable = payload['value']
        I18nProgressDAO.save(i18n_progress_dto)

        transforms.send_json_response(self, 200, 'OK', {}, None)


class BaseDashboardExtension(object):
    ACTION = None

    @classmethod
    def register(cls):
        def get_action(handler):
            cls(handler).render()

        dashboard.DashboardHandler.get_actions.append(cls.ACTION)
        setattr(
            dashboard.DashboardHandler, 'get_%s' % cls.ACTION, get_action)

    @classmethod
    def unregister(cls):
        dashboard.DashboardHandler.get_actions.remove(cls.ACTION)
        setattr(dashboard.DashboardHandler, 'get_%s' % cls.ACTION, None)

    def __init__(self, handler):
        """Initialize the class with a request handler.

        Args:
            handler: modules.dashboard.DashboardHandler. This is the handler
                which will do the rendering.
        """
        self.handler = handler


class I18nDashboardHandler(BaseDashboardExtension):
    """Provides the logic for rendering the i18n workflow dashboard."""

    ACTION = 'i18n_dashboard'

    def __init__(self, handler):
        super(I18nDashboardHandler, self).__init__(handler)
        self.course = handler.get_course()
        self.environ = self.handler.app_context.get_environ()
        self.main_locale = self.environ['course']['locale']
        self.extra_locales = [
            loc['locale'] for loc in self.environ.get('extra_locales', [])]

    def _get_resource_row(self, resource, type_str, key):
        i18n_progress_dto = I18nProgressDAO.load_or_create(
            ResourceKey(type_str, key))
        return ResourceRow(
            self.course, resource, type_str, key,
            i18n_progress_dto=i18n_progress_dto)

    def _make_table_section(self, data_rows, section_title):
        rows = []
        rows.append(SectionRow(section_title))
        if data_rows:
            rows += data_rows
        else:
            rows.append(EmptyRow())
        return rows

    def render(self):
        rows = []

        # Course settings
        data_rows = []

        for section in [
                'course', 'registration', 'homepage', 'unit', 'i18n']:
            data_rows.append(self._get_resource_row(
                None, ResourceKey.COURSE_SETTINGS_TYPE, section))
        rows += self._make_table_section(data_rows, 'Course Settings')

        # Run over units and lessons
        data_rows = []
        for unit in self.course.get_units():
            if unit.type == verify.UNIT_TYPE_ASSESSMENT:
                data_rows.append(self._get_resource_row(
                    unit, ResourceKey.ASSESSMENT_TYPE, unit.unit_id))
            elif unit.type == verify.UNIT_TYPE_LINK:
                data_rows.append(self._get_resource_row(
                    unit, ResourceKey.LINK_TYPE, unit.unit_id))
            elif unit.type == verify.UNIT_TYPE_UNIT:
                data_rows.append(self._get_resource_row(
                    unit, ResourceKey.UNIT_TYPE, unit.unit_id))
                for lesson in self.course.get_lessons(unit.unit_id):
                    data_rows.append(self._get_resource_row(
                        lesson, ResourceKey.LESSON_TYPE, lesson.lesson_id))
            else:
                raise Exception('Unknown unit type: %s.' % unit.type)
        rows += self._make_table_section(data_rows, 'Course Outline')

        # Run over file assets
        data_rows = [
            self._get_resource_row(None, ResourceKey.ASSET_IMG_TYPE, path)
            for path in self.handler.list_files('/assets/img')]
        rows += self._make_table_section(data_rows, 'Images & Documents')

        # Run over questions and question groups
        data_rows = []
        for qu in models.QuestionDAO.get_all():
            qu_type = ResourceKey.get_question_type(qu)
            data_rows.append(self._get_resource_row(qu, qu_type, qu.id))

        rows += self._make_table_section(data_rows, 'Questions')

        data_rows = [
            self._get_resource_row(qg, ResourceKey.QUESTION_GROUP_TYPE, qg.id)
            for qg in models.QuestionGroupDAO.get_all()]
        rows += self._make_table_section(data_rows, 'Question Groups')

        if not [row for row in rows if type(row) is ResourceRow]:
            rows = [EmptyRow(name='No course content')]

        template_values = {
            'main_locale': self.main_locale,
            'extra_locales': self.extra_locales,
            'rows': rows,
            'num_columns': len(self.extra_locales) + 2,
            'is_translatable_xsrf_token': (
                crypto.XsrfTokenManager.create_xsrf_token(
                    IsTranslatableRestHandler.XSRF_TOKEN_NAME))}

        main_content = self.handler.get_template(
            'i18n_dashboard.html', [TEMPLATES_DIR]).render(template_values)
        actions = [{
            'id': 'edit_18n_settings',
            'caption': 'Edit I18N Settings',
            'href': self.handler.get_action_url(
                'settings', extra_args={'tab': 'i18n'})
            }]
        self.handler.render_page({
            'page_title': self.handler.format_title('I18n Workflow'),
            'main_content': jinja2.utils.Markup(main_content),
            'sections': [{
                    'title': 'Internationalization',
                    'actions': actions,
                    'pre': ' ',
                    }]
            })


class TranslationConsole(BaseDashboardExtension):
    ACTION = 'i18_console'

    def render(self):
        main_content = oeditor.ObjectEditor.get_html_for(
            self.handler,
            TranslationConsoleRestHandler.SCHEMA.get_json_schema(),
            TranslationConsoleRestHandler.SCHEMA.get_schema_dict(),
            self.handler.request.get('key'),
            self.handler.canonicalize_url(TranslationConsoleRestHandler.URL),
            self.handler.get_action_url(I18nDashboardHandler.ACTION),
            auto_return=False,
            required_modules=TranslationConsoleRestHandler.REQUIRED_MODULES,
            extra_css_files=['translation_console.css'],
            extra_js_files=['translation_console.js'],
            additional_dirs=[TEMPLATES_DIR])

        self.handler.render_page({
            'page_title': self.handler.format_title('I18n Workflow'),
            'main_content': main_content})


def tc_generate_schema():
    schema = schema_fields.FieldRegistry(
        'Translation Console', extra_schema_dict_values={
            'className': 'inputEx-Group translation-console'})

    schema.add_property(schema_fields.SchemaField(
        'title', 'Title', 'string', editable=False))

    schema.add_property(schema_fields.SchemaField(
        'key', 'ID', 'string', hidden=True))
    schema.add_property(schema_fields.SchemaField(
        'source_locale', 'Source Locale', 'string', hidden=True))
    schema.add_property(schema_fields.SchemaField(
        'target_locale', 'Target Locale', 'string', hidden=True))

    section = schema_fields.FieldRegistry(
        None, 'section', extra_schema_dict_values={
            'className': 'inputEx-Group translation-item'})
    section.add_property(schema_fields.SchemaField(
        'name', 'Name', 'string', editable=False))
    section.add_property(schema_fields.SchemaField(
        'type', 'Type', 'string', editable=False, optional=True))
    section.add_property(schema_fields.SchemaField(
        'source_value', 'source_value', 'string', hidden=True, optional=True))

    item = schema_fields.FieldRegistry(None, 'item')
    item.add_property(schema_fields.SchemaField(
        'source_value', 'Original', 'string', optional=True,
        extra_schema_dict_values={'_type': 'text', 'className': 'disabled'}))
    item.add_property(schema_fields.SchemaField(
        'target_value', 'Translated', 'string', optional=True,
        extra_schema_dict_values={'_type': 'text', 'className': 'active'}))
    item.add_property(schema_fields.SchemaField(
        'verb', 'Verb', 'string', hidden=True, optional=True))
    item.add_property(schema_fields.SchemaField(
        'old_source_value', 'Old Source Value', 'string', hidden=True,
        optional=True))
    item.add_property(schema_fields.SchemaField(
        'changed', 'Changed', 'boolean', hidden=True, optional=True))

    section.add_property(schema_fields.FieldArray(
        'data', 'Data', item_type=item,
        extra_schema_dict_values={}))

    schema.add_property(schema_fields.FieldArray(
        'sections', 'Sections', item_type=section))

    return schema


class TranslationConsoleRestHandler(utils.BaseRESTHandler):
    URL = '/rest/modules/i18n_dashboard/translation_console'
    XSRF_TOKEN_NAME = 'translation-console'

    SCHEMA = tc_generate_schema()

    REQUIRED_MODULES = [
        'inputex-hidden', 'inputex-list', 'inputex-string', 'inputex-textarea',
        'inputex-uneditable']

    def _filter_translatable(self, binding):
        """Filter only translatable strings."""
        return schema_fields.ValueToTypeBinding.filter_on_criteria(
            binding,
            type_names=[TYPE_HTML, TYPE_STRING, TYPE_TEXT, TYPE_URL],
            hidden_values=[False],
            i18n_values=[None, True],
            editable_values=[True])

    def _add_known_translations_as_defaults(self, locale, sections):
        translations = i18n.get_store().get_translations(locale)
        for section in sections:
            for item in section['data']:
                if item['verb'] == VERB_NEW:
                    source_value = item['source_value']
                    target_value = translations.gettext(source_value)
                    if source_value and target_value != source_value:
                        item['target_value'] = target_value
                        item['verb'] = VERB_CURRENT

    def get(self):
        key = ResourceBundleKey.fromstring(self.request.get('key'))

        if not roles.Roles.is_course_admin(self.app_context):
            transforms.send_json_response(
                self, 401, 'Access denied.', {'key': str(key)})
            return

        schema = key.resource_key.get_schema(self.app_context)
        values = key.resource_key.get_data_dict(self.app_context)

        binding = schema_fields.ValueToTypeBinding.bind_entity_to_schema(
            values, schema)

        allowed_names = self._filter_translatable(binding)

        existing_mappings = []
        resource_bundle_dto = ResourceBundleDAO.load(str(key))
        if resource_bundle_dto:
            for name, value in resource_bundle_dto.dict.items():
                if value['type'] == TYPE_HTML:
                    source_value = value['source_value']
                    target_value = ''
                else:
                    source_value = value['data'][0]['source_value']
                    target_value = value['data'][0]['target_value']

                existing_mappings.append(xcontent.SourceToTargetMapping(
                    name, value['type'], source_value, target_value))

        mappings = xcontent.SourceToTargetDiffMapping.map_source_to_target(
            binding, allowed_names=allowed_names,
            existing_mappings=existing_mappings)

        map_lists_source_to_target = (
            xcontent.SourceToTargetDiffMapping.map_lists_source_to_target)
        config = xcontent.Configuration(opaque_tag_names=[
            tag_name.upper()
            for tag_name in tags.Registry.get_all_tags().keys()])
        sections = []
        for mapping in mappings:
            if mapping.type == TYPE_HTML:
                existing_mappings = []
                if resource_bundle_dto:
                    field_dict = resource_bundle_dto.dict.get(mapping.name)
                    if field_dict:
                        existing_mappings = field_dict['data']
                transformer = xcontent.ContentTransformer(config=config)
                context = xcontent.Context(
                    xcontent.ContentIO.fromstring(mapping.source_value))
                transformer.decompose(context)

                html_mappings = map_lists_source_to_target(
                    context.resource_bundle,
                    [m['source_value'] for m in existing_mappings])
                source_value = mapping.source_value
                data = []
                for html_mapping in html_mappings:
                    if html_mapping.target_value_index is not None:
                        target_value = existing_mappings[
                            html_mapping.target_value_index]['target_value']
                    else:
                        target_value = ''
                    data.append({
                        'source_value': html_mapping.source_value,
                        'old_source_value': html_mapping.target_value,
                        'target_value': target_value,
                        'verb': html_mapping.verb,
                        'changed': False})
            else:
                source_value = ''
                data = [{
                    'source_value': mapping.source_value,
                    'target_value': mapping.target_value,
                    'verb': mapping.verb,
                    'changed': False}]

            sections.append({
                'name': mapping.name,
                'type': mapping.type,
                'source_value': source_value,
                'data': data
            })

        self._add_known_translations_as_defaults(key.locale, sections)

        def cmp_sections(section1, section2):
            """Comparator to sort the sections in schema order."""
            name1 = section1['name']
            name2 = section2['name']
            path1 = name1.split(':')
            path2 = name2.split(':')
            for part1, part2 in zip(path1, path2):
                if part1[0] == '[' and part1[-1] == ']':
                    assert part2[0] == '[' and part2[-1] == ']'
                    c = cmp(int(part1[1:-1]), int(part2[1:-1]))
                    if c != 0:
                        return c
                    else:
                        continue
                elif part1 != part2:
                    name_no_index1, _ = (
                        schema_fields.FieldRegistry.compute_name(path1))
                    name_no_index2, _ = (
                        schema_fields.FieldRegistry.compute_name(path2))
                    return cmp(
                        binding.index.names_in_order.index(name_no_index1),
                        binding.index.names_in_order.index(name_no_index2))
            return cmp(len(path1), len(path2))

        payload_dict = {
            'key': str(key),
            'title': str(key.resource_key.get_title(self.app_context)),
            'source_locale': self.app_context.get_environ()['course']['locale'],
            'target_locale': key.locale,
            'sections': sorted(sections, cmp=cmp_sections)
        }

        transforms.send_json_response(
            self, 200, 'success',
            payload_dict=payload_dict,
            xsrf_token=utils.XsrfTokenManager.create_xsrf_token(
                self.XSRF_TOKEN_NAME))

    def put(self):
        request = transforms.loads(self.request.get('request'))
        key = request['key']
        resource_bundle_key = ResourceBundleKey.fromstring(key)

        if not self.assert_xsrf_token_or_fail(
                request, self.XSRF_TOKEN_NAME, {'key': key}):
            return

        if not roles.Roles.is_course_admin(self.app_context):
            transforms.send_json_response(
                self, 401, 'Access denied.', {'key': key})
            return

        payload = transforms.loads(request['payload'])
        payload_dict = transforms.json_to_dict(
            payload, self.SCHEMA.get_json_schema_dict())

        # Update the resource bundle
        resource_bundle_dto = ResourceBundleDAO.load(key)
        if not resource_bundle_dto:
            resource_bundle_dto = ResourceBundleDTO(key, {})

        for section in payload_dict['sections']:
            changed = False
            data = []
            for item in section['data']:
                if item['changed']:
                    changed = True
                    data.append({
                        'source_value': item['source_value'],
                        'target_value': item['target_value']})
                elif item['verb'] == VERB_CHANGED:
                    data.append({
                        'source_value': item['old_source_value'],
                        'target_value': item['target_value']})
                elif item['verb'] == VERB_CURRENT:
                    data.append({
                        'source_value': item['source_value'],
                        'target_value': item['target_value']})
                else:  # when it is VERB_NEW
                    pass

            if changed:
                source_value = None
                if section['type'] == TYPE_HTML:
                    source_value = section['source_value']

                resource_bundle_dto.dict[section['name']] = {
                    'type': section['type'],
                    'source_value': source_value,
                    'data': data,
                }
        ResourceBundleDAO.save(resource_bundle_dto)

        # Update the progress
        is_done = True
        for section in payload_dict['sections']:
            for item in section['data']:
                if item['verb'] != VERB_CURRENT and not item['changed']:
                    is_done = False

        i18_progress_dto = I18nProgressDAO.load_or_create(
            resource_bundle_key.resource_key)
        i18_progress_dto.set_progress(
            resource_bundle_key.locale,
            I18nProgressDTO.DONE if is_done else I18nProgressDTO.IN_PROGRESS)
        I18nProgressDAO.save(i18_progress_dto)

        transforms.send_json_response(self, 200, 'Saved.')


class LazyTranslator(object):

    def __init__(self, source_value, translation_dict):
        self.source_value = source_value
        self.target_value = None
        self.translation_dict = translation_dict

    def __str__(self):
        if self.target_value is not None:
            return self.target_value

        if self.translation_dict['type'] == TYPE_HTML:
            self.target_value = self._translate_html()
        else:
            self.target_value = self.translation_dict['data'][0]['target_value']

        return self.target_value

    def __len__(self):
        return len(unicode(self))

    def _translate_html(self):
        if self.translation_dict['source_value'] != self.source_value:
            return self.source_value

        try:
            context = xcontent.Context(xcontent.ContentIO.fromstring(
                self.source_value))
            config = xcontent.Configuration(opaque_tag_names=[
                tag_name.upper()
                for tag_name in tags.Registry.get_all_tags().keys()])
            transformer = xcontent.ContentTransformer(config=config)
            transformer.decompose(context)

            resource_bundle = [
                data['target_value'] for data in self.translation_dict['data']]
            errors = []

            transformer.recompose(context, resource_bundle, errors)
            return xcontent.ContentIO.tostring(context.tree)
        except Exception:  # pylint: disable-msg=broad-except
            logging.exception('Unable to translate: %s', self.source_value)
            return self.source_value


def set_attribute(thing, attribute_name, translation_dict):
    # TODO(jorr): Need to be able to deal with hierarchical names from the
    # schema, not just top-level names.
    assert hasattr(thing, attribute_name)

    source_value = getattr(thing, attribute_name)
    setattr(thing, attribute_name, LazyTranslator(
        source_value, translation_dict))


def translate_list(thing_list, translations):
    for thing, bundle in zip(thing_list, translations):
        if bundle is not None:
            for flattened_name, translation_dict in bundle.dict.items():
                set_attribute(thing, flattened_name, translation_dict)


def translate_course(course):
    if not sites.is_localized_content_allowed():
        return

    locale = sites.get_current_locale(course.app_context)
    units = course.get_units()
    lessons = course.get_lessons_for_all_units()

    keys = [
        str(ResourceBundleKey(ResourceKey.UNIT_TYPE, unit.unit_id, locale))
        for unit in units]
    keys += [
        str(ResourceBundleKey(
            ResourceKey.LESSON_TYPE, lesson.lesson_id, locale))
        for lesson in lessons]

    translate_list(units + lessons, ResourceBundleDAO.bulk_load(keys))


def translate_dto_list(dto_list, key_list):
    if not sites.is_localized_content_allowed():
        return

    app_context = sites.get_course_for_current_request()
    if app_context is None:
        return

    locale = sites.get_current_locale(app_context)

    bundle_list = ResourceBundleDAO.bulk_load(
        [str(ResourceBundleKey(key.type, key.key, locale)) for key in key_list])

    for resource_key, dto, bundle in zip(key_list, dto_list, bundle_list):
        if bundle is None:
            continue
        schema = resource_key.get_schema(app_context)
        binding = schema_fields.ValueToTypeBinding.bind_entity_to_schema(
            dto.dict, schema)
        for name, translation_dict in bundle.dict.items():
            source_value = binding.name_to_value[name].value
            binding.name_to_value[name].value = LazyTranslator(
                source_value, translation_dict)


def translate_question_dto(dto_list):
    key_list = []
    for dto in dto_list:
        qu_type = ResourceKey.get_question_type(dto)
        key_list.append(ResourceKey(qu_type, dto.id))
    translate_dto_list(dto_list, key_list)


def translate_question_group_dto(dto_list):
    key_list = [
        ResourceKey(ResourceKey.QUESTION_GROUP_TYPE, dto.id)
        for dto in dto_list]
    translate_dto_list(dto_list, key_list)


def notify_module_enabled():
    dashboard.DashboardHandler.nav_mappings.append(
        [I18nDashboardHandler.ACTION, 'I18N'])
    I18nDashboardHandler.register()
    TranslationConsole.register()
    courses.Course.POST_LOAD_HOOKS.append(translate_course)
    models.QuestionDAO.POST_LOAD_HOOKS.append(translate_question_dto)
    models.QuestionGroupDAO.POST_LOAD_HOOKS.append(translate_question_group_dto)


def notify_module_disabled():
    dashboard.DashboardHandler.nav_mappings.remove(
        [I18nDashboardHandler.ACTION, 'I18N'])
    I18nDashboardHandler.unregister()
    TranslationConsole.unregister()
    courses.Course.POST_LOAD_HOOKS.remove(translate_course)
    models.QuestionDAO.POST_LOAD_HOOKS.remove(translate_question_dto)
    models.QuestionGroupDAO.POST_LOAD_HOOKS.remove(translate_question_group_dto)


def register_module():
    """Registers this module in the registry."""

    global_routes = [
        (os.path.join(RESOURCES_PATH, 'js', '.*'), tags.JQueryHandler),
        (os.path.join(RESOURCES_PATH, '.*'), tags.ResourcesHandler)]
    namespaced_routes = [
        (TranslationConsoleRestHandler.URL, TranslationConsoleRestHandler),
        (IsTranslatableRestHandler.URL, IsTranslatableRestHandler)]

    global custom_module
    custom_module = custom_modules.Module(
        'I18N Dashboard Module',
        'A module provide i18n workflow.',
        global_routes, namespaced_routes,
        notify_module_enabled=notify_module_enabled,
        notify_module_disabled=notify_module_disabled)

    return custom_module
