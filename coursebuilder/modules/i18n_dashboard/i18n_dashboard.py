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

"""Module to support users unsubscribing from notifications."""

__author__ = 'John Orr (jorr@google.com)'

import os

import jinja2

import appengine_config
from common import crypto
from common import tags
from controllers import utils
from models import custom_modules
from models import models
from models import transforms
from modules.dashboard import dashboard
from tools import verify

from google.appengine.ext import db


RESOURCES_PATH = '/modules/i18n_dashboard/resources'

TEMPLATES_DIR = os.path.join(
    appengine_config.BUNDLE_ROOT, 'modules', 'i18n_dashboard', 'templates')

custom_module = None


class ResourceKey(object):
    """Manages key for Course Builder resource.

    Every Course Builder resource can be identified by a type name and a
    type-contextual key. This class holds data related to this keying, and
    manages serialization/deserialization as strings.
    """

    ASSESSMENT_TYPE = 'assessment'
    ASSET_IMG_TYPE = 'asset_img'
    LESSON_TYPE = 'lesson'
    LINK_TYPE = 'link'
    QUESTION_GROUP_TYPE = 'question_group'
    QUESTION_TYPE = 'question'
    UNIT_TYPE = 'unit'

    RESOURCE_TYPES = [
        ASSESSMENT_TYPE, ASSET_IMG_TYPE, LESSON_TYPE, LINK_TYPE,
        QUESTION_GROUP_TYPE, QUESTION_TYPE, UNIT_TYPE]

    def __init__(self, type_str, key):
        self._type = type_str
        self._key = key
        assert type_str in self.RESOURCE_TYPES, (
            'Unknown resource type: %s' % type_str)

    def __str__(self):
        return '%s:%s' % (self._type, self._key)

    @classmethod
    def fromstring(cls, key_str):
        index = key_str.index('s')
        return ResourceKey(key_str[:index], key_str[index + 1:])


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

    def __init__(self, course, resource, type_str, key, is_translatable=True):
        self._course = course
        self._resource = resource
        self._type = type_str
        self._key = key
        self._is_translatable = is_translatable

    @property
    def name(self):
        if self._type == ResourceKey.UNIT_TYPE:
            return utils.display_unit_title(self._resource)
        elif self._type == ResourceKey.LESSON_TYPE:
            return utils.display_lesson_title(
                self._course.find_unit_by_id(self._resource.unit_id),
                self._resource)
        elif self._type in [
                ResourceKey.ASSESSMENT_TYPE, ResourceKey.LESSON_TYPE,
                ResourceKey.LINK_TYPE]:
            return self._resource.title
        elif self._type == ResourceKey.ASSET_IMG_TYPE:
            return self._key
        elif self._type in [
                ResourceKey.QUESTION_GROUP_TYPE, ResourceKey.QUESTION_TYPE]:
            return self._resource.description

        return 'none'

    @property
    def class_name(self):
        return '' if self._is_translatable else 'not-translatable'

    @property
    def resource_key(self):
        return ResourceKey(self._type, self._key)

    @property
    def is_translatable(self):
        return self._is_translatable

    def _mock_status_data(self, locale):
        #######################################################################
        # DEMO CODE ONLY
        #
        if locale == 'ru' and self._type in [
                ResourceKey.LESSON_TYPE, ResourceKey.UNIT_TYPE,
                ResourceKey.QUESTION_TYPE]:
            return (self.DONE_STRING, self.DONE_CLASS)
        elif locale == 'el' and self._type == ResourceKey.LESSON_TYPE:
            return (self.IN_PROGRESS_STRING, self.IN_PROGRESS_CLASS)
        else:
            return (self.NOT_STARTED_STRING, self.NOT_STARTED_CLASS)
        #
        #######################################################################

    def status(self, locale):
        return self._mock_status_data(locale)[0]

    def status_class(self, locale):
        return self._mock_status_data(locale)[1]


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


class I18nProgressEntity(models.BaseEntity):
    """The base entity for storing i18n workflow information.

    Each entity represents one resource in the course.
    """

    data = db.TextProperty(indexed=False)


class I18nProgressDTO(object):
    """The lightweight data object for the i18n workflow data."""

    IS_TRANSLATABLE_KEY = 'is_translatable'

    def __init__(self, the_id, the_dict):
        self.id = the_id
        self.dict = the_dict

    def is_translatable(self, default):
        return self.dict.get(self.IS_TRANSLATABLE_KEY, default)

    def set_translatable(self, value):
        self.dict[self.IS_TRANSLATABLE_KEY] = value


class I18nProgressDAO(models.BaseJsonDao):
    """Access object for the i18n workflow data."""

    DTO = I18nProgressDTO
    ENTITY = I18nProgressEntity
    ENTITY_KEY_TYPE = models.BaseJsonDao.EntityKeyTypeName

    @classmethod
    def load_or_create(cls, resource_key):
        i18n_progress_dto = cls.load(str(resource_key))
        if not i18n_progress_dto:
            i18n_progress_dto = I18nProgressDTO(str(resource_key), {})
            cls.save(i18n_progress_dto)
        return i18n_progress_dto


class IsTranslatableRestHandler(utils.BaseRESTHandler):
    """REST handler to respond to setting a resource as (non-)translatable."""

    URL = '/rest/modules/i18n_dashboard/is_translatable'
    XSRF_TOKEN_NAME = 'is-translatable'

    def post(self):
        request = transforms.loads(self.request.get('request'))
        if not self.assert_xsrf_token_or_fail(
                request, self.XSRF_TOKEN_NAME, {}):
            return

        payload = request.get('payload')
        i18n_progress_dto = I18nProgressDAO.load_or_create(
            payload['resource_key'])
        i18n_progress_dto.set_translatable(payload['value'])
        I18nProgressDAO.save(i18n_progress_dto)

        transforms.send_json_response(self, 200, 'OK', {}, None)


class I18nDashboardHandler(object):
    """Provides the logic for rendering the i18n workflow dashboard."""

    def __init__(self, handler):
        """Initialize the class with a request handler.

        Args:
            handler: modules.dashboard.DashboardHandler. This is the handler
                which will do the rendering.
        """
        self.handler = handler
        self.course = handler.get_course()
        self.environ = self.handler.app_context.get_environ()
        self.main_locale = self.environ['course']['locale']
        self.extra_locales = [
            loc['locale'] for loc in self.environ.get('extra_locales', [])]

    def get_resource_row(self, resource, type_str, key):
        i18n_progress_dto = I18nProgressDAO.load_or_create(
            ResourceKey(type_str, key))
        is_translatable = i18n_progress_dto.is_translatable(True)
        return ResourceRow(
            self.course, resource, type_str, key,
            is_translatable=is_translatable)

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

        # Run over units and lessons
        data_rows = []
        for unit in self.course.get_units():
            if unit.type == verify.UNIT_TYPE_ASSESSMENT:
                data_rows.append(self.get_resource_row(
                    unit, ResourceKey.ASSESSMENT_TYPE, unit.unit_id))
            elif unit.type == verify.UNIT_TYPE_LINK:
                data_rows.append(self.get_resource_row(
                    unit, ResourceKey.LINK_TYPE, unit.unit_id))
            elif unit.type == verify.UNIT_TYPE_UNIT:
                data_rows.append(self.get_resource_row(
                    unit, ResourceKey.UNIT_TYPE, unit.unit_id))
                for lesson in self.course.get_lessons(unit.unit_id):
                    data_rows.append(self.get_resource_row(
                        lesson, ResourceKey.LESSON_TYPE, lesson.lesson_id))
            else:
                raise Exception('Unknown unit type: %s.' % unit.type)
        rows += self._make_table_section(data_rows, 'Course Outline')

        # Run over file assets
        data_rows = [
            self.get_resource_row(None, ResourceKey.ASSET_IMG_TYPE, path)
            for path in self.handler.list_files('/assets/img')]
        rows += self._make_table_section(data_rows, 'Images and Documents')

        # Run over questions and question groups
        data_rows = [
            self.get_resource_row(qu, ResourceKey.QUESTION_TYPE, qu.id)
            for qu in models.QuestionDAO.get_all()]
        rows += self._make_table_section(data_rows, 'Questions')

        data_rows = [
            self.get_resource_row(qg, ResourceKey.QUESTION_GROUP_TYPE, qg.id)
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

        self.handler.render_page({
            'page_title': 'I18n Workflow',
            'main_content': jinja2.utils.Markup(main_content)})


def get_i18n_dashboard(handler):
    """A request handler method which will be bound toDashboardHandler."""

    I18nDashboardHandler(handler).render()


def notify_module_enabled():
    dashboard.DashboardHandler.nav_mappings.append(['i18n_dashboard', 'i18n'])
    dashboard.DashboardHandler.get_actions.append('i18n_dashboard')
    dashboard.DashboardHandler.get_i18n_dashboard = get_i18n_dashboard


def notify_module_disabled():
    dashboard.DashboardHandler.nav_mappings.remove(['i18n_dashboard', 'i18n'])
    dashboard.DashboardHandler.get_actions.remove('i18n_dashboard')
    dashboard.DashboardHandler.get_i18n_dashboard = None


def register_module():
    """Registers this module in the registry."""

    global_routes = []

    global_routes = [
        (os.path.join(RESOURCES_PATH, 'js', '.*'), tags.JQueryHandler),
        (os.path.join(RESOURCES_PATH, '.*'), tags.ResourcesHandler)]
    namespaced_routes = [
        (IsTranslatableRestHandler.URL, IsTranslatableRestHandler)]

    global custom_module
    custom_module = custom_modules.Module(
        'I18N Dashboard Module',
        'A module provide i18n workflow.',
        global_routes, namespaced_routes,
        notify_module_enabled=notify_module_enabled,
        notify_module_disabled=notify_module_disabled)

    return custom_module
