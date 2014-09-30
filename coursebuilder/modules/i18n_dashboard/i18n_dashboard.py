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

import cgi
import collections
import cStringIO
import logging
import os
import re
import StringIO
import urllib
import zipfile

from babel import localedata
from babel.messages import catalog
from babel.messages import pofile
import jinja2
from webapp2_extras import i18n

import appengine_config
from common import crypto
from common import safe_dom
from common import schema_fields
from common import tags
from common import utils as common_utils
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
from modules.dashboard import utils as dashboard_utils
from modules.oeditor import oeditor
from tools import verify

from google.appengine.ext import db

RESOURCES_PATH = '/modules/i18n_dashboard/resources'

TEMPLATES_DIR = os.path.join(
    appengine_config.BUNDLE_ROOT, 'modules', 'i18n_dashboard', 'templates')

# The path to the CSS file with application-wide i18n-related styling
GLOBAL_CSS = '/modules/i18n_dashboard/resources/css/global_i18n.css'

VERB_NEW = xcontent.SourceToTargetDiffMapping.VERB_NEW
VERB_CHANGED = xcontent.SourceToTargetDiffMapping.VERB_CHANGED
VERB_CURRENT = xcontent.SourceToTargetDiffMapping.VERB_CURRENT

# This permission grants the user access to the i18n dashboard and console.
ACCESS_PERMISSION = 'access_i18n_dashboard'
ACCESS_PERMISSION_DESCRIPTION = 'Can access I18n Dashboard.'

TYPE_HTML = 'html'
TYPE_STRING = 'string'
TYPE_TEXT = 'text'
TYPE_URL = 'url'

# Filter for those schema fields which are translatable
TRANSLATABLE_FIELDS_FILTER = schema_fields.FieldFilter(
    type_names=[TYPE_HTML, TYPE_STRING, TYPE_TEXT, TYPE_URL],
    hidden_values=[False],
    i18n_values=[None, True],
    editable_values=[True])


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

    def __init__(self, type_str, key, course=None):
        self._type = type_str
        self._key = key
        self._course = course
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

    @classmethod
    def for_unit(cls, unit):
        if unit.type == verify.UNIT_TYPE_ASSESSMENT:
            unit_type = ResourceKey.ASSESSMENT_TYPE
        elif unit.type == verify.UNIT_TYPE_LINK:
            unit_type = ResourceKey.LINK_TYPE
        elif unit.type == verify.UNIT_TYPE_UNIT:
            unit_type = ResourceKey.UNIT_TYPE
        else:
            raise ValueError('Unknown unit type: %s' % unit.type)

        return ResourceKey(unit_type, unit.unit_id)

    def _get_course(self, app_context):
        course = self._course
        if not course or course.app_context != app_context:
            course = courses.Course(None, app_context=app_context)
        return course

    def get_title(self, app_context):
        resource = self.get_resource(app_context)
        return self.get_resource_title(resource)

    def get_resource(self, app_context):
        course = self._get_course(app_context)
        if self._type == ResourceKey.UNIT_TYPE:
            return course.find_unit_by_id(self._key)
        elif self._type == ResourceKey.LESSON_TYPE:
            lesson = course.find_lesson_by_id(None, self._key)
            unit = course.get_unit_for_lesson(lesson)
            return (unit, lesson)
        elif self._type in [ResourceKey.ASSESSMENT_TYPE, ResourceKey.LINK_TYPE]:
            return course.find_unit_by_id(self._key)
        elif self._type == ResourceKey.ASSET_IMG_TYPE:
            return self._key
        elif self._type == ResourceKey.COURSE_SETTINGS_TYPE:
            return course.create_settings_schema()
        elif self._type in [
                ResourceKey.QUESTION_MC_TYPE, ResourceKey.QUESTION_SA_TYPE]:
            qu = models.QuestionDAO.load(self._key)
            return qu
        elif self._type in ResourceKey.QUESTION_GROUP_TYPE:
            qgp = models.QuestionGroupDAO.load(self._key)
            return qgp
        else:
            return None

    def get_resource_title(self, resource):
        if not resource:
            return None

        if self._type == ResourceKey.UNIT_TYPE:
            return utils.display_unit_title(resource)
        elif self._type == ResourceKey.LESSON_TYPE:
            return utils.display_lesson_title(resource[0], resource[1])
        elif self._type in (ResourceKey.ASSESSMENT_TYPE, ResourceKey.LINK_TYPE):
            return resource.title
        elif self._type == ResourceKey.ASSET_IMG_TYPE:
            return resource
        elif self._type == ResourceKey.COURSE_SETTINGS_TYPE:
            return resource.sub_registries[self._key].title
        elif self._type in (ResourceKey.QUESTION_MC_TYPE,
                            ResourceKey.QUESTION_SA_TYPE,
                            ResourceKey.QUESTION_GROUP_TYPE):
            return resource.description
        else:
            return None

    def get_schema(self, app_context):
        if self.type == ResourceKey.ASSESSMENT_TYPE:
            return unit_lesson_editor.AssessmentRESTHandler.SCHEMA
        elif self.type == ResourceKey.LINK_TYPE:
            return unit_lesson_editor.LinkRESTHandler.SCHEMA
        elif self.type == ResourceKey.UNIT_TYPE:
            return unit_lesson_editor.UnitRESTHandler.SCHEMA
        elif self.type == ResourceKey.QUESTION_MC_TYPE:
            return question_editor.McQuestionRESTHandler.get_schema()
        elif self.type == ResourceKey.QUESTION_SA_TYPE:
            return question_editor.SaQuestionRESTHandler.get_schema()
        elif self.type == ResourceKey.QUESTION_GROUP_TYPE:
            return question_group_editor.QuestionGroupRESTHandler.get_schema()
        elif self.type == ResourceKey.LESSON_TYPE:
            course = self._get_course(app_context)
            units = course.get_units()
            return unit_lesson_editor.LessonRESTHandler.get_schema(units)
        elif self.type == ResourceKey.COURSE_SETTINGS_TYPE:
            return courses.Course.create_base_settings_schema(
                ).clone_only_items_named([self.key])
        else:
            raise ValueError('Unknown content type: %s' % self.type)

    def get_data_dict(self, app_context):
        course = self._get_course(app_context)
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
    locale = db.StringProperty(indexed=True)


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

    @classmethod
    def before_put(cls, dto, entity):
        resource_bundle_key = ResourceBundleKey.fromstring(dto.id)
        entity.locale = resource_bundle_key.locale

    @classmethod
    def get_all_for_locale(cls, locale):
        query = cls.ENTITY.all()
        query.filter('locale = ', locale)
        result = []
        for e in query.run(batch_size=100):
            result.append(
                cls.DTO(e.key().id_or_name(), transforms.loads(e.data)))
        return result


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
        return ResourceKey(
            self._type, self._key,
            course=self._course).get_title(self._course.app_context)

    @property
    def class_name(self):
        if self._i18n_progress_dto.is_translatable:
            return ''
        else:
            return self.NOT_TRANSLATABLE_CLASS

    @property
    def resource_key(self):
        return ResourceKey(self._type, self._key, course=self._course)

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
        elif self._type in [
                ResourceKey.COURSE_SETTINGS_TYPE, ResourceKey.LINK_TYPE,
                ResourceKey.QUESTION_MC_TYPE, ResourceKey.QUESTION_SA_TYPE,
                ResourceKey.QUESTION_GROUP_TYPE]:
            return None

        raise ValueError('Unknown type %s' % self._type)

    def edit_url(self, locale):
        return TranslationConsole.get_edit_url(
            ResourceBundleKey(self._type, self._key, locale))


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
    def is_readonly(cls, course):
        return course.app_context.get_environ()[
                'course'].get('prevent_translation_edits')

    @classmethod
    def format_readonly_message(cls):
        return safe_dom.Element('P').add_text(
            'Translation console is currently disabled. '
            'Course administrator can enable it via I18N Settings.')

    @classmethod
    def register(cls):
        def get_action(handler):
            cls(handler).render()

        dashboard.DashboardHandler.get_actions.append(cls.ACTION)
        setattr(
            dashboard.DashboardHandler, 'get_%s' % cls.ACTION, get_action)
        dashboard.DashboardHandler.map_action_to_permission(
            'get_%s' % cls.ACTION, ACCESS_PERMISSION)

    @classmethod
    def unregister(cls):
        dashboard.DashboardHandler.get_actions.remove(cls.ACTION)
        setattr(dashboard.DashboardHandler, 'get_%s' % cls.ACTION, None)
        dashboard.DashboardHandler.unmap_action_to_permission(
            'get_%s' % cls.ACTION)

    def __init__(self, handler):
        """Initialize the class with a request handler.

        Args:
            handler: modules.dashboard.DashboardHandler. This is the handler
                which will do the rendering.
        """
        self.handler = handler


class TranslationsAndLocations(object):

    def __init__(self):
        self._translations = set()
        self._locations = []
        self._comments = []

    def add_translation(self, translation):
        # Don't add "translations" that are blank, unless we have no other
        # alternatives.
        if translation or not self._translations:
            self._translations.add(translation)
        # If all we have so far is blank translations, and this one is
        # nonblank, throw away all the blank ones.
        if translation and not any(self._translations):
            self._translations = [translation]

    def add_location(self, location):
        self._locations.append(location)

    def add_comment(self, comment):
        comment = str(comment)  # May be Node or NodeList.
        self._comments.append(comment)

    @property
    def locations(self):
        return self._locations

    @property
    def translations(self):
        return self._translations

    @property
    def comments(self):
        return self._comments


class I18nDownloadHandler(BaseDashboardExtension):
    ACTION = 'i18n_download'

    @staticmethod
    def build_translations(handler, locales):
        """Build up a dictionary of all translated strings -> locale.

        For each {original-string,locale}, keep track of the course
        locations where this occurs, and each of the translations given.

        Args:
          handler: webapp2 handler for looking up context and course.
          locales: Locales for which translations are desired.
        Returns:
          Map of original-string -> locale -> TranslationsAndLocations.
        """

        translations = collections.defaultdict(
            lambda: collections.defaultdict(TranslationsAndLocations))

        course = handler.get_course()
        app_context = handler.app_context
        transformer = xcontent.ContentTransformer(
            config=I18nTranslationContext.instance(
                app_context).get_xcontent_configuration())
        resource_key_map = _get_language_resource_keys(course)

        for locale in locales:

            key2dto = {
                dto.id: dto
                for dto in ResourceBundleDAO.get_all_for_locale(locale)}

            for resource, resource_key in resource_key_map:
                if resource_key.type == ResourceKey.ASSET_IMG_TYPE:
                    continue
                key = ResourceBundleKey(
                    resource_key.type, resource_key.key, locale)
                binding, sections = _build_sections_for_key_ex(
                    key, app_context, key2dto.get(str(key)), transformer)
                for section in sections:
                    section_name = section['name']
                    section_type = section['type']
                    description = (
                        binding.find_field(section_name).description or '')

                    for translation in section['data']:
                        message = unicode(translation['source_value'] or '')
                        translated_message = translation['target_value'] or ''
                        t_and_l = translations[message][locale]
                        t_and_l.add_translation(translated_message)
                        t_and_l.add_location('GCB-1|%s|%s|%s' % (
                            section_name, section_type, str(key)))
                        if not t_and_l.comments and message:
                            t_and_l.add_comment(description)
                            title = resource_key.get_resource_title(resource)
                            if title:
                                t_and_l.add_comment(title)
        return translations

    @staticmethod
    def build_babel_catalog_for_locale(handler, translations, locale):
        course = handler.get_course()
        environ = course.get_environ(handler.app_context)
        course_title = environ['course'].get('title')
        bugs_address = environ['course'].get('admin_user_emails')
        organization = environ['base'].get('nav_header')
        with common_utils.ZipAwareOpen():
            # Load metadata for locale to which we are translating.
            localedata.load(locale)
        cat = catalog.Catalog(
            locale=locale,
            project='Translation for %s of %s' % (locale, course_title),
            msgid_bugs_address=bugs_address,
            copyright_holder=organization)
        for tr_id in translations:
            if locale in translations[tr_id]:
                t_and_l = translations[tr_id][locale]
                cat.add(
                    tr_id, string=t_and_l.translations.pop(),
                    locations=[(l, 0) for l in t_and_l.locations],
                    user_comments=t_and_l.comments,
                    auto_comments=['also translated as "%s"' % s
                                   for s in t_and_l.translations])
        return cat

    @staticmethod
    def build_zip_file(handler, out_stream, translations):
        """Create a .zip file with one .po file for each translated language.

        Args:
          handler: webapp2 handler for looking up course and app context
          out_stream: An open file-like which can be written and seeked.
          translations: Map of string -> locale -> TranslationsAndLocations
            as returned from build_translations().
        """
        original_locale = handler.app_context.default_locale
        with common_utils.ZipAwareOpen():
            # Load metadata for 'en', which Babel uses internally.
            localedata.load('en')
            # Load metadata for source language for course.
            localedata.load(original_locale)
        zf = zipfile.ZipFile(out_stream, 'w', allowZip64=True)
        try:
            for locale in handler.app_context.get_all_locales():
                if locale == original_locale:
                    continue
                cat = I18nDownloadHandler.build_babel_catalog_for_locale(
                    handler, translations, locale)
                filename = os.path.join(
                    'locale', locale, 'LC_MESSAGES', 'messages.po')
                content = cStringIO.StringIO()
                try:
                    pofile.write_po(content, cat)
                    zf.writestr(filename, content.getvalue())
                finally:
                    content.close()
        finally:
            zf.close()

    def _send_response(self, out_stream):
        self.handler.response.headers.add(
            'Content-Disposition', 'attachment; filename="translations.zip"')
        self.handler.response.headers.add(
            'Content-Type', 'application/octet-stream')
        self.handler.response.write(out_stream.getvalue())

    def render(self):
        models.MemcacheManager.begin_readonly()
        try:
            all_locales = self.handler.app_context.get_all_locales()
            translations = self.build_translations(self.handler, all_locales)
            out_stream = StringIO.StringIO()
            # zip assumes stream has a real fp; fake it.
            out_stream.fp = out_stream
            try:
                self.build_zip_file(self.handler, out_stream, translations)
                self._send_response(out_stream)
            finally:
                out_stream.close()
        finally:
            models.MemcacheManager.end_readonly()


class I18nUploadHandler(BaseDashboardExtension):
    ACTION = 'i18n_upload'

    def render(self):
        main_content = oeditor.ObjectEditor.get_html_for(
            self.handler,
            TranslationUploadRestHandler.SCHEMA.get_json_schema(),
            TranslationUploadRestHandler.SCHEMA.get_schema_dict(),
            '',
            self.handler.canonicalize_url(TranslationUploadRestHandler.URL),
            self.handler.get_action_url(I18nDashboardHandler.ACTION),
            required_modules=TranslationUploadRestHandler.REQUIRED_MODULES,
            save_method='upload', save_button_caption='Upload')
        self.handler.render_page({
            'page_title': self.handler.format_title('I18n Translation Upload'),
            'main_content': main_content,
            })


def translation_upload_generate_schema():
    schema = schema_fields.FieldRegistry('Translation Upload')
    schema.add_property(schema_fields.SchemaField(
        'file', 'Translation File', 'file',
        description='Use this option to nominate a .po file containing '
        'translations for a single language, or a .zip file containing '
        'multiple translated languages.  The internal structure of the .zip '
        'file is unimportant; all files ending in ".po" will be considered.'))
    return schema


def _recalculate_translation_progress(app_context):
    transformer = xcontent.ContentTransformer(
        config=I18nTranslationContext.instance(
            app_context).get_xcontent_configuration())
    course = courses.Course(None, app_context)
    all_resource_keys = _get_language_resource_keys(course)
    key2progress = {
        resource_key: I18nProgressDAO.load_or_create(resource_key)
        for _, resource_key in all_resource_keys}

    for _, resource_key in all_resource_keys:
        progress = key2progress[resource_key]
        for locale in app_context.get_all_locales():
            key = ResourceBundleKey(resource_key.type, resource_key.key, locale)
            _, sections = _build_sections_for_key(
                key, app_context, transformer=transformer)
            partially_translated = False
            fully_translated = True
            for section in sections:
                for translation in section['data']:
                    if translation['source_value']:
                        if translation['target_value']:
                            partially_translated = True
                        else:
                            fully_translated = False

            if fully_translated:
                # NOTE: Yes, it's considered "fully translated" even if all
                # the translatable items are blank.  What we want to show on
                # the I18N console is whether any work remains be done.  The
                # fact that there may be blanks in the source text is not
                # something about which this module needs to be nanny-ing the
                # admin.
                new_state = I18nProgressDTO.DONE
            elif partially_translated:
                new_state = I18nProgressDTO.IN_PROGRESS
            else:
                new_state = I18nProgressDTO.NOT_STARTED
            if progress.get_progress(locale) != new_state:
                progress.set_progress(locale, new_state)

    for _, progress in key2progress.items():
        I18nProgressDAO.save(progress)


class TranslationUploadRestHandler(utils.BaseRESTHandler):
    URL = '/rest/modules/i18n_dashboard/upload'
    XSRF_TOKEN_NAME = 'translation-upload'
    SCHEMA = translation_upload_generate_schema()
    REQUIRED_MODULES = ['inputex-hidden', 'inputex-select', 'inputex-string',
                        'inputex-uneditable', 'inputex-file',
                        'io-upload-iframe']

    class ProtocolError(Exception):
        pass

    def get(self):
        transforms.send_json_response(
            self, 200, 'Success.', payload_dict={'key': None},
            xsrf_token=crypto.XsrfTokenManager.create_xsrf_token(
                self.XSRF_TOKEN_NAME))

    @staticmethod
    def update_translation(data):
        pseudo_file = cStringIO.StringIO(data)
        the_catalog = pofile.read_po(pseudo_file)
        total_translations = 0
        matched_translations = 0
        updated_translations = 0
        added_translations = 0
        for message in the_catalog:
            for location, _ in message.locations:
                total_translations += 1
                protocol, component_name, ttype, key = location.split('|', 4)
                if protocol != 'GCB-1':
                    raise TranslationUploadRestHandler.ProtocolError(
                        'Expected location format GCB-1, but had %s' % protocol)
                dto = ResourceBundleDAO.load(key)
                if not dto:
                    dto = ResourceBundleDTO(key, {})

                component = dto.dict.get(component_name)
                if not component:
                    component = {
                        'type': ttype,
                        'data': [],
                        'source_value': None
                        }
                    dto.dict[component_name] = component

                dirty = False
                found = False
                for translation_item in component['data']:
                    if translation_item['source_value'] == message.id:
                        found = True
                        matched_translations += 1
                        if translation_item['target_value'] != message.string:
                            dirty = True
                            translation_item['target_value'] = message.string
                            updated_translations += 1
                if not found and message.id and message.string:
                    component['data'].append({
                        'source_value': message.id,
                        'target_value': message.string,
                        })
                    dirty = True
                    added_translations += 1
                if dirty:
                    ResourceBundleDAO.save(dto)
        return (
            total_translations,
            matched_translations,
            updated_translations,
            added_translations)

    def post(self):
        request = transforms.loads(self.request.get('request'))
        if not self.assert_xsrf_token_or_fail(
            request, self.XSRF_TOKEN_NAME, {'key': None}):
            return
        if not roles.Roles.is_course_admin(self.app_context):
            transforms.send_file_upload_response(self, 401, 'Access denied.')
            return

        upload = self.request.POST['file']
        if not isinstance(upload, cgi.FieldStorage):
            transforms.send_file_upload_response(
                self, 400, 'Must provide a .zip or .po file to upload')
            return
        file_content = upload.file.read()
        if not isinstance(upload, cgi.FieldStorage):
            transforms.send_file_upload_response(
                self, 400, 'The .zip or .po file must not be empty.')
            return

        # Get meta-data for supported locales loaded.
        for locale in self.app_context.get_all_locales():
            with common_utils.ZipAwareOpen():
                localedata.load(locale)

        stats_total = [0] * 4
        try:
            try:
                zf = zipfile.ZipFile(cStringIO.StringIO(file_content), 'r')
                for item in zf.infolist():
                    if item.filename.endswith('.po'):
                        # pylint: disable-msg=unpacking-non-sequence
                        stats = self.update_translation(zf.read(item))
                        stats_total = [
                            i + j for i, j in zip(stats, stats_total)]
            except zipfile.BadZipfile:
                try:
                    stats_total = self.update_translation(file_content)
                except UnicodeDecodeError:
                    transforms.send_file_upload_response(
                        self, 400,
                        'Uploaded file did not parse as .zip or .po file.')
                    return
        except TranslationUploadRestHandler.ProtocolError, ex:
            transforms.send_file_upload_response(self, 400, str(ex))
            return

        if stats_total[0] == 0:
            # .PO file parser is pretty lenient; random text files don't
            # necessarily result in exceptions, but count of total
            # translations will be zero, so also consider that an error.
            transforms.send_file_upload_response(
                self, 400, 'No translations found in provided file.')
            return

        _recalculate_translation_progress(self.app_context)
        transforms.send_file_upload_response(
            self, 200,
            '%d total, %d matched, %d changed, %d added translations' %
            tuple(stats_total))


class I18nProgressManager(object):
    """Class that manages optimized loading of I18N data from datastore."""

    def __init__(self, course):
        self._course = course
        self._key_to_progress = {}
        self._preload_progress()

    def _preload_progress(self):
        for row in I18nProgressDAO.get_all_iter():
            self._key_to_progress[str(ResourceKey.fromstring(row.id))] = row

    def get_resource_row(self, resource, type_str, key):
        resource_key = ResourceKey(type_str, key)
        row = self._key_to_progress.get(str(resource_key))
        if not row:
            row = I18nProgressDAO.load_or_create(resource_key)
        return ResourceRow(
            self._course, resource, type_str, key,
            i18n_progress_dto=row)


class I18nTranslationContext(sites.RequestScopedSingleton):

    def __init__(self, app_context):
        self.app_context = app_context
        self._xcontent_config = None

    @classmethod
    def _init_xcontent_configuration(cls, app_context):
        inline_tag_names = list(xcontent.DEFAULT_INLINE_TAG_NAMES)
        opaque_decomposable_tag_names = list(
            xcontent.DEFAULT_OPAQUE_DECOMPOSABLE_TAG_NAMES)
        recomposable_attributes_map = dict(
            xcontent.DEFAULT_RECOMPOSABLE_ATTRIBUTES_MAP)

        for tag_name, tag_cls in tags.Registry.get_all_tags().items():
            tag_schema = None
            try:
                # TODO(jorr): refactor BaseTag.get_schema to work
                # without handler
                fake_handler = utils.BaseHandler()
                fake_handler.app_context = app_context
                tag_schema = tag_cls().get_schema(fake_handler)
            except Exception:  # pylint: disable-msg=broad-except
                logging.exception('Cannot get schema for %s', tag_name)
                continue

            index = schema_fields.FieldRegistryIndex(tag_schema)
            index.rebuild()

            for name in (
                TRANSLATABLE_FIELDS_FILTER.filter_field_registry_index(index)
            ):
                inline_tag_names.append(tag_name.upper())
                opaque_decomposable_tag_names.append(tag_name.upper())
                recomposable_attributes_map.setdefault(
                    name.upper(), set()).add(tag_name.upper())

        return xcontent.Configuration(
            inline_tag_names=inline_tag_names,
            opaque_decomposable_tag_names=opaque_decomposable_tag_names,
            recomposable_attributes_map=recomposable_attributes_map,
            omit_empty_opaque_decomposable=False)

    def get_xcontent_configuration(self):
        if not self._xcontent_config:
            self._xcontent_config = self._init_xcontent_configuration(
                self.app_context)
        return self._xcontent_config


class I18nReverseCaseHandler(BaseDashboardExtension):
    """Provide "translation" that swaps case of letters."""

    ACTION = 'i18n_reverse_case'

    def _add_reverse_case_locale(self, locale):
        course = self.handler.get_course()
        environ = course.get_environ(self.handler.app_context)
        extra_locales = environ.get('extra_locales', [])
        if not any(l['locale'] == locale for l in extra_locales):
            extra_locales.append({'locale': locale,
                                  'availability': 'unavailable'})
            environ['extra_locales'] = extra_locales
            course.save_settings(environ)

    def _add_reverse_case_translations(self, locale):
        original_locale = self.handler.app_context.default_locale
        with common_utils.ZipAwareOpen():
            # Load metadata for 'en', which Babel uses internally.
            localedata.load('en')
            # Load metadata for base course language.
            localedata.load(original_locale)

        translations = I18nDownloadHandler.build_translations(
            self.handler, [locale])
        cat = I18nDownloadHandler.build_babel_catalog_for_locale(
            self.handler, translations, locale)
        for message in cat:
            message.string = re.sub(
                r'&[a-zA-Z0-9]+;',
                lambda m: m.group().swapcase(),
                message.id.swapcase())
        try:
            content = cStringIO.StringIO()
            pofile.write_po(content, cat)
            TranslationUploadRestHandler.update_translation(content.getvalue())
        finally:
            content.close()

    def render(self):
        # Here, using 'ln' because we need a language that Babel knows.
        # Lingala ( http://en.wikipedia.org/wiki/Lingala ) is not likely to be
        # a target language for courses hosted in CB in the next few years.
        locale = 'ln'
        self._add_reverse_case_locale(locale)
        self._add_reverse_case_translations(locale)
        _recalculate_translation_progress(self.handler.app_context)
        self.handler.redirect(
            self.handler.get_action_url(I18nDashboardHandler.ACTION))


def _get_course_resource_keys(course):
    ret = []
    schema = course.create_settings_schema()
    for section_name in sorted(courses.Course.get_schema_sections()):
        ret.append(
            (schema,
             ResourceKey(ResourceKey.COURSE_SETTINGS_TYPE, section_name)))
    return ret


def _get_course_component_keys(course):
    ret = []
    for unit in course.get_units():
        if course.get_parent_unit(unit):
            continue
        ret.append((unit, ResourceKey.for_unit(unit)))
        if unit.type == verify.UNIT_TYPE_UNIT:
            if unit.pre_assessment:
                assessment = course.find_unit_by_id(unit.pre_assessment)
                ret.append(
                    (assessment,
                     ResourceKey(
                         ResourceKey.ASSESSMENT_TYPE, unit.pre_assessment)))
            for lesson in course.get_lessons(unit.unit_id):
                ret.append(((unit, lesson),
                            ResourceKey(
                                ResourceKey.LESSON_TYPE, lesson.lesson_id)))
            if unit.post_assessment:
                assessment = course.find_unit_by_id(unit.pre_assessment)
                ret.append(
                    (assessment,
                     ResourceKey(
                         ResourceKey.ASSESSMENT_TYPE, unit.post_assessment)))
    return ret


def _get_asset_keys(handler):
    ret = []
    for path in dashboard_utils.list_files(handler, '/assets/img',
                                           merge_local_files=True):
        ret.append((None, ResourceKey(ResourceKey.ASSET_IMG_TYPE, path)))
    return ret


def _get_question_keys():
    ret = []
    for qu in models.QuestionDAO.get_all():
        ret.append((qu, ResourceKey(ResourceKey.get_question_type(qu), qu.id)))
    return ret


def _get_question_group_keys():
    ret = []
    for qg in models.QuestionGroupDAO.get_all():
        ret.append((qg, ResourceKey(ResourceKey.QUESTION_GROUP_TYPE, qg.id)))
    return ret


def _get_language_resource_keys(course):
    return (
        _get_course_resource_keys(course) +
        _get_course_component_keys(course) +
        _get_question_keys() +
        _get_question_group_keys()
        )


class I18nDashboardHandler(BaseDashboardExtension):
    """Provides the logic for rendering the i18n workflow dashboard."""

    ACTION = 'i18n_dashboard'

    def __init__(self, handler):
        super(I18nDashboardHandler, self).__init__(handler)
        self.course = handler.get_course()
        all_locales = self.handler.app_context.get_all_locales()
        self.main_locale = all_locales[0]
        self.extra_locales = all_locales[1:]
        self.rm = None

    def _make_table_section(self, data_rows, section_title):
        rows = []
        rows.append(EmptyRow(name='', class_name='blank-row'))
        rows.append(SectionRow(section_title))
        if data_rows:
            rows += data_rows
        else:
            rows.append(EmptyRow())
        return rows

    def render(self):
        self.rm = I18nProgressManager(self.course)
        rows = []

        # Course settings
        data_rows = []
        for resource, key in _get_course_resource_keys(self.course):
            data_rows.append(self.rm.get_resource_row(
                resource, key.type, key.key))
        rows += self._make_table_section(data_rows, 'Course Settings')

        # Run over units and lessons
        data_rows = []
        for resource, key in _get_course_component_keys(self.course):
            if key.type == ResourceKey.LESSON_TYPE:
                data_rows.append(self.rm.get_resource_row(
                    resource[1], key.type, key.key))
            else:  # Unit, Assessment or Link
                data_rows.append(self.rm.get_resource_row(
                    resource, key.type, key.key))
        rows += self._make_table_section(data_rows, 'Course Outline')

        # Run over questions and question groups
        data_rows = []
        for resource, key in _get_question_keys():
            data_rows.append(self.rm.get_resource_row(
                resource, key.type, key.key))
        rows += self._make_table_section(data_rows, 'Questions')

        data_rows = []
        for resource, key in _get_question_group_keys():
            data_rows.append(self.rm.get_resource_row(
                resource, key.type, key.key))
        rows += self._make_table_section(data_rows, 'Question Groups')

        if not [row for row in rows if type(row) is ResourceRow]:
            rows = [EmptyRow(name='No course content')]

        permitted_locales = []
        for locale in self.extra_locales:
            if roles.Roles.is_user_allowed(
                self.handler.app_context, custom_module,
                locale_to_permission(locale)
            ):
                permitted_locales.append(locale)

        template_values = {
            'extra_locales': permitted_locales,
            'rows': rows,
            'num_columns': len(permitted_locales) + 1,
            'is_readonly': self.is_readonly(self.course)
        }

        if roles.Roles.is_course_admin(self.handler.app_context):
            template_values['main_locale'] = self.main_locale
            template_values['is_translatable_xsrf_token'] = (
                crypto.XsrfTokenManager.create_xsrf_token(
                    IsTranslatableRestHandler.XSRF_TOKEN_NAME))
            template_values['num_columns'] += 1

        main_content = self.handler.get_template(
            'i18n_dashboard.html', [TEMPLATES_DIR]).render(template_values)
        edit_actions = [
            {
                'id': 'translate_to_reverse_case',
                'caption': '"Translate" to rEVERSED cAPS',
                'href': self.handler.get_action_url(
                    I18nReverseCaseHandler.ACTION),
                },
            {
                'id': 'upload_translation_files',
                'caption': 'Upload Translation Files',
                'href': self.handler.get_action_url(I18nUploadHandler.ACTION),
                },
            {
                'id': 'download_translation_files',
                'caption': 'Download Translation Files',
                'href': self.handler.get_action_url(I18nDownloadHandler.ACTION),
                }]

        actions = []
        if not self.is_readonly(self.course):
            actions += edit_actions
        actions += [
            {
                'id': 'edit_18n_settings',
                'caption': 'Edit I18N Settings',
                'href': self.handler.get_action_url(
                    'settings', extra_args={'tab': 'i18n'})
                },
            ]
        self.handler.render_page({
            'page_title': self.handler.format_title('I18n Workflow'),
            'main_content': jinja2.utils.Markup(main_content),
            'sections': [{
                    'title': 'Internationalization%s' % (
                        ' (readonly)' if self.is_readonly(
                            self.course) else ''),
                    'actions': actions,
                    'pre': ' ',
                    }]
            })


class TranslationConsole(BaseDashboardExtension):
    ACTION = 'i18_console'

    @classmethod
    def get_edit_url(cls, key):
        return 'dashboard?%s' % urllib.urlencode({
            'action': cls.ACTION,
            'key': key})

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

        if self.is_readonly(self.handler.get_course()):
            main_content = self.format_readonly_message()

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
        'name', '', 'string', hidden=True))
    section.add_property(schema_fields.SchemaField(
        'label', 'Name', 'string', editable=False))
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

    def get(self):

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

        key = ResourceBundleKey.fromstring(self.request.get('key'))
        if not has_locale_rights(self.app_context, key.locale):
            transforms.send_json_response(
                self, 401, 'Access denied.', {'key': str(key)})
            return

        binding, sections = _build_sections_for_key(key, self.app_context)
        payload_dict = {
            'key': str(key),
            'title': str(key.resource_key.get_title(self.app_context)),
            'source_locale': self.app_context.default_locale,
            'target_locale': key.locale,
            'sections': sorted(sections, cmp=cmp_sections)
        }

        transforms.send_json_response(
            self, 200, 'Success.',
            payload_dict=payload_dict,
            xsrf_token=crypto.XsrfTokenManager.create_xsrf_token(
                self.XSRF_TOKEN_NAME))

    def put(self):
        request = transforms.loads(self.request.get('request'))
        key = request['key']
        resource_bundle_key = ResourceBundleKey.fromstring(key)

        if not self.assert_xsrf_token_or_fail(
                request, self.XSRF_TOKEN_NAME, {'key': key}):
            return

        if not has_locale_rights(self.app_context, resource_bundle_key.locale):
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


def _build_sections_for_key(
    key, app_context, resource_bundle_dto=None, transformer=None):
    if not resource_bundle_dto:
        resource_bundle_dto = ResourceBundleDAO.load(str(key))
    if not transformer:
        transformer = xcontent.ContentTransformer(
            config=I18nTranslationContext.instance(
                app_context).get_xcontent_configuration())
    return _build_sections_for_key_ex(
        key, app_context, resource_bundle_dto, transformer=transformer)


def _build_sections_for_key_ex(
    key, app_context, resource_bundle_dto, transformer):

    def add_known_translations_as_defaults(locale, sections):
        translations = i18n.get_store().get_translations(locale)
        for section in sections:
            for item in section['data']:
                if item['verb'] == VERB_NEW:
                    # NOTE: The types of source values we are getting here
                    # include: unicode, str, float, and None.  It appears to
                    # be harmless to force a conversion to unicode so that we
                    # are uniform in what we are asking for a translation for.
                    source_value = unicode(item['source_value'] or '')
                    if source_value:
                        target_value = translations.gettext(source_value)

                        # File under very weird: Mostly, the i18n library
                        # hands back unicode instances.  However, sometimes
                        # it will give back a string.  And sometimes, that
                        # string is the UTF-8 encoding of a unicode string.
                        # Convert it back to unicode, because trying to do
                        # reasonable things on such values (such as casting
                        # to unicode) will raise an exception.
                        if type(target_value) == str:
                            try:
                                target_value = target_value.decode('utf-8')
                            except UnicodeDecodeError:
                                pass
                        if target_value != source_value:
                            item['target_value'] = target_value
                            item['verb'] = VERB_CURRENT

    schema = key.resource_key.get_schema(app_context)
    values = key.resource_key.get_data_dict(app_context)
    binding = schema_fields.ValueToTypeBinding.bind_entity_to_schema(
        values, schema)
    allowed_names = TRANSLATABLE_FIELDS_FILTER.filter_value_to_type_binding(
        binding)

    existing_mappings = []
    if resource_bundle_dto:
        for name, value in resource_bundle_dto.dict.items():
            if value['type'] == TYPE_HTML:
                source_value = value['source_value']
                target_value = ''
            else:
                source_value = value['data'][0]['source_value']
                target_value = value['data'][0]['target_value']

            existing_mappings.append(xcontent.SourceToTargetMapping(
                name, None, value['type'], source_value, target_value))

    mappings = xcontent.SourceToTargetDiffMapping.map_source_to_target(
        binding, allowed_names=allowed_names,
        existing_mappings=existing_mappings)

    map_lists_source_to_target = (
        xcontent.SourceToTargetDiffMapping.map_lists_source_to_target)

    sections = []
    for mapping in mappings:
        if mapping.type == TYPE_HTML:
            existing_mappings = []
            if resource_bundle_dto:
                field_dict = resource_bundle_dto.dict.get(mapping.name)
                if field_dict:
                    existing_mappings = field_dict['data']
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

        if any([item['source_value'] for item in data]):
            sections.append({
                'name': mapping.name,
                'label': mapping.label,
                'type': mapping.type,
                'source_value': source_value,
                'data': data
            })

    if key.locale != app_context.default_locale:
        add_known_translations_as_defaults(key.locale, sections)
    return binding, sections


class LazyTranslator(object):

    @classmethod
    def json_encode(cls, obj):
        if isinstance(obj, cls):
            return unicode(obj)
        return None

    def __init__(self, app_context, key, source_value, translation_dict):
        assert isinstance(source_value, basestring)
        self._app_context = app_context
        self._key = key
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

    def __add__(self, other):
        if isinstance(other, basestring):
            return other + unicode(self)
        return super(LazyTranslator, self).__add__(other)

    def _translate_html(self):
        try:
            context = xcontent.Context(xcontent.ContentIO.fromstring(
                self.source_value))
            transformer = xcontent.ContentTransformer(
                config=I18nTranslationContext.instance(
                    self._app_context).get_xcontent_configuration())
            transformer.decompose(context)

            data_list = self.translation_dict['data']
            diff_mapping_list = (
                xcontent.SourceToTargetDiffMapping.map_lists_source_to_target(
                    context.resource_bundle, [
                        data['source_value']
                        for data in data_list]))

            count_misses = 0
            if len(context.resource_bundle) < len(data_list):
                count_misses = len(data_list) - len(context.resource_bundle)

            resource_bundle = []
            for mapping in diff_mapping_list:
                if mapping.verb == VERB_CURRENT:
                    resource_bundle.append(
                        data_list[mapping.target_value_index]['target_value'])
                elif mapping.verb in [VERB_CHANGED, VERB_NEW]:
                    count_misses += 1
                    resource_bundle.append(
                        context.resource_bundle[mapping.source_value_index])
                else:
                    raise ValueError('Unknown verb: %s' % mapping.verb)

            errors = []
            transformer.recompose(context, resource_bundle, errors)
            body = xcontent.ContentIO.tostring(context.tree)
            if count_misses == 0 and not errors:
                return body
            else:
                parts = 'part' if count_misses == 1 else 'parts'
                are = 'is' if count_misses == 1 else 'are'
                return self._detailed_error(
                    'The content has changed and {n} {parts} of the '
                    'translation {are} out of date.'.format(
                    n=count_misses, parts=parts, are=are), body)

        except Exception as ex:  # pylint: disable-msg=broad-except
            logging.exception('Unable to translate: %s', self.source_value)
            if roles.Roles.is_user_allowed(
                    self._app_context, custom_module,
                    locale_to_permission(
                        self._app_context.get_current_locale())):
                return self._detailed_error(str(ex), self.source_value)
            else:
                return self.source_value

    def _detailed_error(self, msg, body):
        template_env = self._app_context.get_template_environ(
            self._app_context.default_locale, [TEMPLATES_DIR])
        template = template_env.get_template('lazy_loader_error.html')
        return template.render({
            'error_message': msg,
            'edit_url': TranslationConsole.get_edit_url(self._key),
            'body': body})


def set_attribute(course, key, thing, attribute_name, translation_dict):
    # TODO(jorr): Need to be able to deal with hierarchical names from the
    # schema, not just top-level names.
    assert hasattr(thing, attribute_name)

    source_value = getattr(thing, attribute_name)
    setattr(thing, attribute_name, LazyTranslator(
        course.app_context, key, source_value, translation_dict))


def translate_lessons(course, locale):
    lesson_list = course.get_lessons_for_all_units()
    key_list = [
        str(ResourceBundleKey(
            ResourceKey.LESSON_TYPE, lesson.lesson_id, locale))
        for lesson in lesson_list]

    bundle_list = ResourceBundleDAO.bulk_load(key_list)

    for key, lesson, bundle in zip(key_list, lesson_list, bundle_list):
        if bundle is not None:
            for name, translation_dict in bundle.dict.items():
                set_attribute(course, key, lesson, name, translation_dict)


def translate_units(course, locale):
    unit_list = course.get_units()
    key_list = []
    for unit in unit_list:
        key = ResourceKey.for_unit(unit)
        key_list.append(ResourceBundleKey(key.type, key.key, locale))

    bundle_list = ResourceBundleDAO.bulk_load([str(key) for key in key_list])
    unit_tools = unit_lesson_editor.UnitTools(course)

    for key, unit, bundle in zip(key_list, unit_list, bundle_list):
        if bundle is None:
            continue

        schema = key.resource_key.get_schema(course.app_context)
        data_dict = unit_tools.unit_to_dict(unit, keys=bundle.dict.keys())
        binding = schema_fields.ValueToTypeBinding.bind_entity_to_schema(
            data_dict, schema)

        for name, translation_dict in bundle.dict.items():
            source_value = binding.name_to_value[name].value
            binding.name_to_value[name].value = LazyTranslator(
                course.app_context, key, source_value, translation_dict)

        errors = []
        unit_tools.apply_updates(unit, data_dict, errors)


def is_translation_required():
    """Returns True if current locale is different from the course default."""
    app_context = sites.get_course_for_current_request()
    if not app_context:
        return False
    default_locale = app_context.default_locale
    current_locale = app_context.get_current_locale()
    if not current_locale:
        return False
    return current_locale != default_locale


def translate_course(course):
    if not is_translation_required():
        return
    appengine_config.log_appstats_event(
        'translate_course.begin_translate_course')
    models.MemcacheManager.begin_readonly()
    try:
        app_context = sites.get_course_for_current_request()
        translate_units(course, app_context.get_current_locale())
        translate_lessons(course, app_context.get_current_locale())
    finally:
        models.MemcacheManager.end_readonly()
        appengine_config.log_appstats_event(
            'translate_course.end_translate_course')


def translate_course_env(env):
    if not is_translation_required():
        return
    app_context = sites.get_course_for_current_request()
    key_list = [
        ResourceBundleKey(
            ResourceKey.COURSE_SETTINGS_TYPE,
            key, app_context.get_current_locale())
        for key in courses.Course.get_schema_sections()]

    bundle_list = ResourceBundleDAO.bulk_load([str(key) for key in key_list])
    for key, bundle in zip(key_list, bundle_list):
        if bundle is None:
            continue

        schema = key.resource_key.get_schema(app_context)
        binding = schema_fields.ValueToTypeBinding.bind_entity_to_schema(
            env, schema)

        for name, translation_dict in bundle.dict.items():
            field = binding.name_to_value[name]
            source_value = field.value
            field.value = LazyTranslator(
                app_context, key, source_value, translation_dict)


def translate_dto_list(dto_list, resource_key_list):
    if not is_translation_required():
        return

    app_context = sites.get_course_for_current_request()
    key_list = [
        ResourceBundleKey(
            key.type,
            key.key, app_context.get_current_locale())
        for key in resource_key_list]

    bundle_list = ResourceBundleDAO.bulk_load([
        str(key) for key in key_list])

    for key, dto, bundle in zip(key_list, dto_list, bundle_list):
        if bundle is None:
            continue
        schema = key.resource_key.get_schema(app_context)
        binding = schema_fields.ValueToTypeBinding.bind_entity_to_schema(
            dto.dict, schema)
        for name, translation_dict in bundle.dict.items():
            source_value = binding.name_to_value[name].value
            binding.name_to_value[name].value = LazyTranslator(
                app_context, key, source_value, translation_dict)


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


def has_locale_rights(app_context, locale):
    return roles.Roles.is_user_allowed(
        app_context, dashboard.custom_module, ACCESS_PERMISSION
    ) and roles.Roles.is_user_allowed(
        app_context, custom_module, locale_to_permission(locale)
    )


def locale_to_permission(locale):
    return 'translate_%s' % locale


def permissions_callback(app_context):
    for locale in app_context.get_environ().get('extra_locales', []):
        yield roles.Permission(
            locale_to_permission(locale['locale']),
            'Can submit translations for the locale "%s".' % locale['locale']
        )


def notify_module_enabled():
    dashboard.DashboardHandler.nav_mappings.append(
        [I18nDashboardHandler.ACTION, 'I18N'])
    dashboard.DashboardHandler.add_external_permission(
        ACCESS_PERMISSION, ACCESS_PERMISSION_DESCRIPTION)
    roles.Roles.register_permissions(
        custom_module, permissions_callback)

    courses.ADDITIONAL_ENTITIES_FOR_COURSE_IMPORT.add(ResourceBundleEntity)
    courses.ADDITIONAL_ENTITIES_FOR_COURSE_IMPORT.add(I18nProgressEntity)

    I18nDashboardHandler.register()
    I18nDownloadHandler.register()
    I18nUploadHandler.register()
    I18nReverseCaseHandler.register()
    TranslationConsole.register()
    courses.Course.POST_LOAD_HOOKS.append(translate_course)
    courses.Course.COURSE_ENV_POST_LOAD_HOOKS.append(translate_course_env)
    models.QuestionDAO.POST_LOAD_HOOKS.append(translate_question_dto)
    models.QuestionGroupDAO.POST_LOAD_HOOKS.append(translate_question_group_dto)
    transforms.CUSTOM_JSON_ENCODERS.append(LazyTranslator.json_encode)
    utils.ApplicationHandler.EXTRA_GLOBAL_CSS_URLS.append(GLOBAL_CSS)


def notify_module_disabled():
    dashboard.DashboardHandler.nav_mappings.remove(
        [I18nDashboardHandler.ACTION, 'I18N'])
    dashboard.DashboardHandler.remove_external_permission(ACCESS_PERMISSION)
    roles.Roles.unregister_permissions(custom_module)

    courses.ADDITIONAL_ENTITIES_FOR_COURSE_IMPORT.pop(ResourceBundleEntity)
    courses.ADDITIONAL_ENTITIES_FOR_COURSE_IMPORT.pop(I18nProgressEntity)

    I18nDashboardHandler.unregister()
    I18nDownloadHandler.unregister()
    I18nUploadHandler.unregister()
    I18nReverseCaseHandler.unregister()
    TranslationConsole.unregister()
    courses.Course.POST_LOAD_HOOKS.remove(translate_course)
    courses.Course.COURSE_ENV_POST_LOAD_HOOKS.remove(translate_course_env)
    models.QuestionDAO.POST_LOAD_HOOKS.remove(translate_question_dto)
    models.QuestionGroupDAO.POST_LOAD_HOOKS.remove(translate_question_group_dto)
    transforms.CUSTOM_JSON_ENCODERS.append(LazyTranslator.json_encode)
    utils.ApplicationHandler.EXTRA_GLOBAL_CSS_URLS.remove(GLOBAL_CSS)


def register_module():
    """Registers this module in the registry."""

    global_routes = [
        (os.path.join(RESOURCES_PATH, 'js', '.*'), tags.JQueryHandler),
        (os.path.join(RESOURCES_PATH, '.*'), tags.ResourcesHandler)]
    namespaced_routes = [
        (TranslationConsoleRestHandler.URL, TranslationConsoleRestHandler),
        (TranslationUploadRestHandler.URL, TranslationUploadRestHandler),
        (IsTranslatableRestHandler.URL, IsTranslatableRestHandler),]

    global custom_module
    custom_module = custom_modules.Module(
        'I18N Dashboard Module',
        'A module provide i18n workflow.',
        global_routes, namespaced_routes,
        notify_module_enabled=notify_module_enabled,
        notify_module_disabled=notify_module_disabled)

    return custom_module
