# coding: utf-8
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

"""Tests for the internationalization (i18n) workflow."""

__author__ = 'John Orr (jorr@google.com)'

import cgi
import cStringIO
import StringIO
import unittest
import zipfile

from babel.messages import pofile

from common import crypto
from common import utils
from common.utils import Namespace
from controllers import sites
from models import courses
from models import models
from models import roles
from models import transforms
from modules.announcements import announcements
from modules.dashboard import dashboard
from modules.i18n_dashboard import i18n_dashboard
from modules.i18n_dashboard.i18n_dashboard import I18nProgressDAO
from modules.i18n_dashboard.i18n_dashboard import I18nProgressDTO
from modules.i18n_dashboard.i18n_dashboard import LazyTranslator
from modules.i18n_dashboard.i18n_dashboard import ResourceBundleDAO
from modules.i18n_dashboard.i18n_dashboard import ResourceBundleDTO
from modules.i18n_dashboard.i18n_dashboard import ResourceBundleKey
from modules.i18n_dashboard.i18n_dashboard import ResourceKey
from modules.i18n_dashboard.i18n_dashboard import ResourceRow
from modules.i18n_dashboard.i18n_dashboard import TranslationUploadRestHandler
from modules.i18n_dashboard.i18n_dashboard import VERB_CHANGED
from modules.i18n_dashboard.i18n_dashboard import VERB_CURRENT
from modules.i18n_dashboard.i18n_dashboard import VERB_NEW
from tests.functional import actions
from tests.functional import assets_rest
from tools import verify

from google.appengine.api import namespace_manager
from google.appengine.api import users


class ResourceKeyTests(unittest.TestCase):

    def test_roundtrip_data(self):
        key1 = ResourceKey(ResourceKey.ASSESSMENT_TYPE, '23')
        key2 = ResourceKey.fromstring(str(key1))
        self.assertEquals(key1.type, key2.type)
        self.assertEquals(key1.key, key2.key)

    def test_reject_bad_type(self):
        with self.assertRaises(AssertionError):
            ResourceKey('BAD_TYPE', '23')
        with self.assertRaises(AssertionError):
            ResourceKey.fromstring('BAD_TYPE:23')

    def test_for_unit(self):
        type_table = [
            (verify.UNIT_TYPE_ASSESSMENT, ResourceKey.ASSESSMENT_TYPE),
            (verify.UNIT_TYPE_LINK, ResourceKey.LINK_TYPE),
            (verify.UNIT_TYPE_UNIT, ResourceKey.UNIT_TYPE)]
        for unit_type, key_type in type_table:
            unit = courses.Unit13()
            unit.type = unit_type
            unit.unit_id = 5
            key = ResourceKey.for_unit(unit)
            self.assertEquals(key_type, key.type)
            self.assertEquals(5, key.key)


class ResourceBundleKeyTests(unittest.TestCase):

    def test_roundtrip_data(self):
        key1 = ResourceBundleKey(ResourceKey.ASSESSMENT_TYPE, '23', 'el')
        key2 = ResourceBundleKey.fromstring(str(key1))
        self.assertEquals(key1.locale, key2.locale)
        self.assertEquals(key1.resource_key.type, key2.resource_key.type)
        self.assertEquals(key1.resource_key.key, key2.resource_key.key)


class ResourceRowTests(unittest.TestCase):

    def setUp(self):
        super(ResourceRowTests, self).setUp()
        course = object()
        resource = object()
        self.type_str = ResourceKey.ASSESSMENT_TYPE
        self.key = '23'
        self.i18n_progress_dto = I18nProgressDTO(None, {})
        self.resource_row = ResourceRow(
            course, resource, self.type_str, self.key,
            i18n_progress_dto=self.i18n_progress_dto)

    def test_class_name(self):
        self.i18n_progress_dto.is_translatable = True
        self.assertEquals('', self.resource_row.class_name)
        self.i18n_progress_dto.is_translatable = False
        self.assertEquals('not-translatable', self.resource_row.class_name)

    def test_resource_key(self):
        key = self.resource_row.resource_key
        self.assertEquals(self.type_str, key.type)
        self.assertEquals(self.key, key.key)

    def test_is_translatable(self):
        self.i18n_progress_dto.is_translatable = True
        self.assertTrue(self.resource_row.is_translatable)
        self.i18n_progress_dto.is_translatable = False
        self.assertFalse(self.resource_row.is_translatable)

    def test_status(self):
        self.i18n_progress_dto.set_progress('fr', I18nProgressDTO.NOT_STARTED)
        self.i18n_progress_dto.set_progress('el', I18nProgressDTO.IN_PROGRESS)
        self.i18n_progress_dto.set_progress('ru', I18nProgressDTO.DONE)
        self.assertEquals('Not started', self.resource_row.status('fr'))
        self.assertEquals('In progress', self.resource_row.status('el'))
        self.assertEquals('Done', self.resource_row.status('ru'))

    def test_status_class(self):
        self.i18n_progress_dto.set_progress('fr', I18nProgressDTO.NOT_STARTED)
        self.i18n_progress_dto.set_progress('el', I18nProgressDTO.IN_PROGRESS)
        self.i18n_progress_dto.set_progress('ru', I18nProgressDTO.DONE)
        self.assertEquals('not-started', self.resource_row.status_class('fr'))
        self.assertEquals('in-progress', self.resource_row.status_class('el'))
        self.assertEquals('done', self.resource_row.status_class('ru'))

    def test_edit_url(self):
        self.assertEquals(
            'dashboard?action=i18_console&key=assessment%3A23%3Ael',
            self.resource_row.edit_url('el'))


class IsTranslatableRestHandlerTests(actions.TestBase):
    ADMIN_EMAIL = 'admin@foo.com'
    COURSE_NAME = 'i18n_course'
    URL = 'rest/modules/i18n_dashboard/is_translatable'

    def setUp(self):
        super(IsTranslatableRestHandlerTests, self).setUp()

        self.base = '/' + self.COURSE_NAME
        context = actions.simple_add_course(
            self.COURSE_NAME, self.ADMIN_EMAIL, 'I18N Course')
        self.old_namespace = namespace_manager.get_namespace()
        namespace_manager.set_namespace('ns_%s' % self.COURSE_NAME)

        self.course = courses.Course(None, context)

    def tearDown(self):
        del sites.Registry.test_overrides[sites.GCB_COURSES_CONFIG.name]
        namespace_manager.set_namespace(self.old_namespace)
        super(IsTranslatableRestHandlerTests, self).tearDown()

    def _post_response(self, request_dict):
        return transforms.loads(self.post(
            self.URL,
            {'request': transforms.dumps(request_dict)}).body)

    def _get_request(self, payload_dict):
        xsrf_token = crypto.XsrfTokenManager.create_xsrf_token(
            'is-translatable')
        return {
            'xsrf_token': xsrf_token,
            'payload': payload_dict
        }

    def test_require_xsrf_token(self):
        response = self._post_response({'xsrf_token': 'BAD TOKEN'})
        self.assertEquals(403, response['status'])

    def test_require_course_admin(self):
        response = self._post_response(self._get_request({}))
        self.assertEquals(401, response['status'])

        actions.login(self.ADMIN_EMAIL, is_admin=True)
        response = self._post_response(self._get_request(
            {'resource_key': 'assessment:23', 'value': True}))
        self.assertEquals(200, response['status'])

    def test_set_data(self):
        resource_key_str = 'assessment:23'
        actions.login(self.ADMIN_EMAIL, is_admin=True)

        self.assertIsNone(I18nProgressDAO.load(resource_key_str))

        response = self._post_response(self._get_request(
            {'resource_key': 'assessment:23', 'value': True}))
        self.assertEquals(200, response['status'])

        dto = I18nProgressDAO.load(resource_key_str)
        self.assertTrue(dto.is_translatable)

        response = self._post_response(self._get_request(
            {'resource_key': 'assessment:23', 'value': False}))
        self.assertEquals(200, response['status'])

        dto = I18nProgressDAO.load(resource_key_str)
        self.assertFalse(dto.is_translatable)


class I18nDashboardHandlerTests(actions.TestBase):
    ADMIN_EMAIL = 'admin@foo.com'
    COURSE_NAME = 'i18n_course'
    URL = 'dashboard?action=i18n_dashboard'

    def setUp(self):
        super(I18nDashboardHandlerTests, self).setUp()

        self.base = '/' + self.COURSE_NAME
        context = actions.simple_add_course(
            self.COURSE_NAME, self.ADMIN_EMAIL, 'I18N Course')
        self.old_namespace = namespace_manager.get_namespace()
        namespace_manager.set_namespace('ns_%s' % self.COURSE_NAME)

        self.course = courses.Course(None, context)
        self.unit = self.course.add_unit()
        self.unit.title = 'Test Unit'
        self.lesson = self.course.add_lesson(self.unit)
        self.lesson.title = 'Test Lesson'
        self.course.save()

        actions.login(self.ADMIN_EMAIL, is_admin=True)

    def tearDown(self):
        del sites.Registry.test_overrides[sites.GCB_COURSES_CONFIG.name]
        namespace_manager.set_namespace(self.old_namespace)
        super(I18nDashboardHandlerTests, self).tearDown()

    def test_page_data(self):
        dom = self.parse_html_string(self.get(self.URL).body)
        table = dom.find('.//table[@class="i18n-progress-table"]')
        rows = table.findall('./tbody/tr')

        expected_row_data = [
            'Course Settings',
            'Assessments',
            'Course',
            'Homepage',
            'I18N',
            'Invitation',
            'Registration',
            'Units and Lessons',
            'Course Outline',
            'Unit 1 - Test Unit',
            '1.1 Test Lesson',
            'Images & Documents',
            'Empty section',
            'Questions',
            'Empty section',
            'Question Groups',
            'Empty section'
        ]
        self.assertEquals(len(expected_row_data), len(rows))
        for index, expected in enumerate(expected_row_data):
            td_text = ''.join(rows[index].find('td').itertext())
            self.assertEquals(expected, td_text)

    def test_multiple_locales(self):
        extra_env = {
            'extra_locales': [
                {'locale': 'el', 'availability': 'unavailable'},
                {'locale': 'ru', 'availability': 'unavailable'},
            ]}
        with actions.OverriddenEnvironment(extra_env):
            dom = self.parse_html_string(self.get(self.URL).body)
            table = dom.find('.//table[@class="i18n-progress-table"]')
            columns = table.findall('./thead/tr/th')
            expected_col_data = [
                'Asset',
                'en_US (Base locale)',
                'el',
                'ru',
            ]
            self.assertEquals(len(expected_col_data), len(columns))
            for index, expected in enumerate(expected_col_data):
                self.assertEquals(expected, columns[index].text)

    def test_is_translatable(self):
        dom = self.parse_html_string(self.get(self.URL).body)
        table = dom.find('.//table[@class="i18n-progress-table"]')
        rows = table.findall('./tbody/tr[@class="not-translatable"]')
        self.assertEquals(0, len(rows))

        dto_key = ResourceKey(ResourceKey.LESSON_TYPE, self.lesson.lesson_id)
        dto = I18nProgressDTO(str(dto_key), {})
        dto.is_translatable = False
        I18nProgressDAO.save(dto)

        dom = self.parse_html_string(self.get(self.URL).body)
        table = dom.find('.//table[@class="i18n-progress-table"]')
        rows = table.findall('./tbody/tr[@class="not-translatable"]')
        self.assertEquals(1, len(rows))

    def test_progress(self):
        def assert_progress(class_name, row, index):
            td = row.findall('td')[index]
            self.assertIn(class_name, td.get('class').split())

        lesson_row_index = 10
        extra_env = {
            'extra_locales': [
                {'locale': 'el', 'availability': 'unavailable'},
                {'locale': 'ru', 'availability': 'unavailable'},
            ]}
        with actions.OverriddenEnvironment(extra_env):
            dom = self.parse_html_string(self.get(self.URL).body)
            table = dom.find('.//table[@class="i18n-progress-table"]')
            lesson_row = table.findall('./tbody/tr')[lesson_row_index]

            lesson_title = ''.join(lesson_row.find('td[1]').itertext())
            self.assertEquals('1.1 Test Lesson', lesson_title)
            assert_progress('not-started', lesson_row, 2)
            assert_progress('not-started', lesson_row, 3)

            dto_key = ResourceKey(
                ResourceKey.LESSON_TYPE, self.lesson.lesson_id)
            dto = I18nProgressDTO(str(dto_key), {})
            dto.set_progress('el', I18nProgressDTO.DONE)
            dto.set_progress('ru', I18nProgressDTO.IN_PROGRESS)
            I18nProgressDAO.save(dto)

            dom = self.parse_html_string(self.get(self.URL).body)
            table = dom.find('.//table[@class="i18n-progress-table"]')
            lesson_row = table.findall('./tbody/tr')[lesson_row_index]

            assert_progress('done', lesson_row, 2)
            assert_progress('in-progress', lesson_row, 3)

    def test_no_image_assets(self):
        dom = self.parse_html_string(self.get(self.URL).body)
        table = dom.find('.//table[@class="i18n-progress-table"]')
        rows_text = [''.join(row.itertext())
                     for row in table.findall('./tbody/tr/td[1]')]
        self.assertIn('Images & Documents', rows_text)
        self.assertEquals('Empty section',
                          rows_text[rows_text.index('Images & Documents') + 1])

    def test_unlocalized_image_asset(self):
        actions.update_course_config(self.COURSE_NAME, {
            'extra_locales': [{'locale': 'de', 'availability': 'available'}]})

        base = 'assets/img'
        name = 'foo.jpg'
        en_content = 'xyzzy'
        assets_rest._post_asset(self, base, name, name, en_content)

        dom = self.parse_html_string(self.get(self.URL).body)
        table = dom.find('.//table[@class="i18n-progress-table"]')
        rows_text = [''.join(row.itertext())
                     for row in table.findall('./tbody/tr/td[1]')]
        row_index = rows_text.index('Images & Documents') + 2
        row_text = [''.join(td.itertext()).strip()
                    for td in table.findall('./tbody/tr[%d]/td' % row_index)]
        self.assertEquals('assets/img/foo.jpg', row_text[0])
        self.assertEquals('Translatable', row_text[1])
        self.assertEquals('Not started', row_text[2])

    def test_localized_image_asset(self):
        actions.update_course_config(self.COURSE_NAME, {
            'extra_locales': [{'locale': 'de', 'availability': 'available'}]})

        base = 'assets/img'
        name = 'foo.jpg'
        locale = 'de'
        en_content = 'xyzzy'
        de_content = 'plugh'
        assets_rest._post_asset(self, base, name, name, en_content)
        assets_rest._post_asset(self, base, name, name, de_content, locale)

        dom = self.parse_html_string(self.get(self.URL).body)
        table = dom.find('.//table[@class="i18n-progress-table"]')
        rows_text = [''.join(row.itertext())
                     for row in table.findall('./tbody/tr/td[1]')]
        row_index = rows_text.index('Images & Documents') + 2
        row_text = [''.join(td.itertext()).strip()
                    for td in table.findall('./tbody/tr[%d]/td' % row_index)]
        self.assertEquals('assets/img/foo.jpg', row_text[0])
        self.assertEquals('Translatable', row_text[1])
        self.assertEquals('Done', row_text[2])


class TranslationConsoleRestHandlerTests(actions.TestBase):
    ADMIN_EMAIL = 'admin@foo.com'
    COURSE_NAME = 'i18n_course'
    URL = 'rest/modules/i18n_dashboard/translation_console'

    def setUp(self):
        super(TranslationConsoleRestHandlerTests, self).setUp()

        self.base = '/' + self.COURSE_NAME
        context = actions.simple_add_course(
            self.COURSE_NAME, self.ADMIN_EMAIL, 'I18N Course')
        self.old_namespace = namespace_manager.get_namespace()
        namespace_manager.set_namespace('ns_%s' % self.COURSE_NAME)

        self.course = courses.Course(None, context)
        self.unit = self.course.add_unit()
        self.unit.title = 'Test Unit'
        self.unit.unit_header = '<p>a</p><p>b</p>'

        self.course.save()

        actions.login(self.ADMIN_EMAIL, is_admin=True)

    def tearDown(self):
        del sites.Registry.test_overrides[sites.GCB_COURSES_CONFIG.name]
        namespace_manager.set_namespace(self.old_namespace)
        super(TranslationConsoleRestHandlerTests, self).tearDown()

    def _get_by_key(self, key):
        return transforms.loads(
            self.get('%s?key=%s' % (self.URL, str(key))).body)

    def _assert_section_values(
            self, section, name, type_str, data_size, source_value):
        self.assertEquals(name, section['name'])
        self.assertEquals(type_str, section['type'])
        self.assertEquals(data_size, len(section['data']))
        self.assertEquals(source_value, section['source_value'])

    def test_get_requires_admin_role(self):
        actions.logout()
        key = ResourceBundleKey(ResourceKey.UNIT_TYPE, self.unit.unit_id, 'el')
        response = self._get_by_key(key)
        self.assertEquals(401, response['status'])

    def test_get_unit_content_with_no_existing_values(self):
        key = ResourceBundleKey(ResourceKey.UNIT_TYPE, self.unit.unit_id, 'el')
        response = self._get_by_key(key)
        self.assertEquals(200, response['status'])

        payload = transforms.loads(response['payload'])
        self.assertEquals('en_US', payload['source_locale'])
        self.assertEquals('el', payload['target_locale'])

        sections = payload['sections']

        self.assertEquals(
            ['title', 'description', 'unit_header', 'unit_footer'],
            [s['name'] for s in sections])

        self.assertEquals(
            ['Title', 'Description', 'Unit Header', 'Unit Footer'],
            [s['label'] for s in sections])

        expected_values = [
            ('title', 'string', 1, ''),
            ('description', 'string', 1, ''),
            ('unit_header', 'html', 2, '<p>a</p><p>b</p>'),
            ('unit_footer', 'html', 0, '')]

        for i, (name, type_str, data_size, source_value) in enumerate(
                expected_values):
            self._assert_section_values(
                sections[i], name, type_str, data_size, source_value)

        # confirm all the data is new
        for section in sections:
            for data in section['data']:
                self.assertEquals(VERB_NEW, data['verb'])

        header_data = sections[2]['data']
        for item in header_data:
            self.assertIsNone(item['old_source_value'])
            self.assertEquals('', item['target_value'])
            self.assertFalse(item['changed'])
        self.assertEquals('a', header_data[0]['source_value'])
        self.assertEquals('b', header_data[1]['source_value'])

    def test_get_unit_content_with_existing_values(self):
        key = ResourceBundleKey(ResourceKey.UNIT_TYPE, self.unit.unit_id, 'el')
        resource_bundle_dict = {
            'title': {
                'type': 'string',
                'source_value': '',
                'data': [
                    {'source_value': 'Test Unit', 'target_value': 'TEST UNIT'}]
            },
            'unit_header': {
                'type': 'html',
                'source_value': '<p>a</p><p>b</p>',
                'data': [
                    {'source_value': 'a', 'target_value': 'A'}]
            }
        }
        dto = ResourceBundleDTO(str(key), resource_bundle_dict)
        ResourceBundleDAO.save(dto)

        response = self._get_by_key(key)
        self.assertEquals(200, response['status'])

        sections = transforms.loads(response['payload'])['sections']

        # Confirm there is a translation for the title
        title_section = sections[0]
        self.assertEquals('title', title_section['name'])
        self.assertEquals('Title', title_section['label'])
        self.assertEquals(1, len(title_section['data']))
        self.assertEquals(VERB_CURRENT, title_section['data'][0]['verb'])
        self.assertEquals('TEST UNIT', title_section['data'][0]['target_value'])

        # Confirm there is a new description
        description_section = sections[1]
        self.assertEquals('description', description_section['name'])
        self.assertEquals('Description', description_section['label'])
        self.assertEquals(VERB_NEW, description_section['data'][0]['verb'])

        # Confirm there is a translation for one of the two paragraphs
        header_section = sections[2]
        self.assertEquals('unit_header', header_section['name'])
        self.assertEquals('Unit Header', header_section['label'])
        self.assertEquals(2, len(header_section['data']))
        self.assertEquals(VERB_CURRENT, header_section['data'][0]['verb'])
        self.assertEquals('a', header_section['data'][0]['source_value'])
        self.assertEquals('a', header_section['data'][0]['old_source_value'])
        self.assertEquals('A', header_section['data'][0]['target_value'])
        self.assertEquals(VERB_NEW, header_section['data'][1]['verb'])

        # Confirm there is a no footer data
        footer_section = sections[3]
        self.assertEquals('Unit Footer', footer_section['label'])
        self.assertEquals(0, len(footer_section['data']))

    def test_get_unit_content_with_changed_values(self):
        key = ResourceBundleKey(ResourceKey.UNIT_TYPE, self.unit.unit_id, 'el')
        resource_bundle_dict = {
            'title': {
                'type': 'string',
                'source_value': '',
                'data': [
                    {
                        'source_value': 'Old Test Unit',
                        'target_value': 'OLD TEST UNIT'}]
            },
            'unit_header': {
                'type': 'html',
                'source_value': '<p>a</p><p>b</p>',
                'data': [
                    {'source_value': 'aa', 'target_value': 'AA'}]
            }
        }
        dto = ResourceBundleDTO(str(key), resource_bundle_dict)
        ResourceBundleDAO.save(dto)

        response = self._get_by_key(key)
        self.assertEquals(200, response['status'])

        sections = transforms.loads(response['payload'])['sections']

        # Confirm there is a translation for the title
        title_section = sections[0]
        self.assertEquals('title', title_section['name'])
        self.assertEquals('Title', title_section['label'])
        self.assertEquals(1, len(title_section['data']))
        self.assertEquals(VERB_CHANGED, title_section['data'][0]['verb'])
        self.assertEquals(
            'OLD TEST UNIT', title_section['data'][0]['target_value'])

        # Confirm there is a new description
        description_section = sections[1]
        self.assertEquals('description', description_section['name'])
        self.assertEquals('Description', description_section['label'])
        self.assertEquals(VERB_NEW, description_section['data'][0]['verb'])

        # Confirm there is a translation for one of the two paragraphs
        header_section = sections[2]
        self.assertEquals('unit_header', header_section['name'])
        self.assertEquals('Unit Header', header_section['label'])
        self.assertEquals(2, len(header_section['data']))
        self.assertEquals(VERB_CHANGED, header_section['data'][0]['verb'])
        self.assertEquals('a', header_section['data'][0]['source_value'])
        self.assertEquals('aa', header_section['data'][0]['old_source_value'])
        self.assertEquals('AA', header_section['data'][0]['target_value'])
        self.assertEquals(VERB_NEW, header_section['data'][1]['verb'])

        # Confirm there is a no footer data
        footer_section = sections[3]
        self.assertEquals('unit_footer', footer_section['name'])
        self.assertEquals('Unit Footer', footer_section['label'])
        self.assertEquals(0, len(footer_section['data']))

    def test_get_unit_content_with_custom_tag(self):
        unit = self.course.add_unit()
        unit.title = 'Test Unit with Tag'
        unit.unit_header = (
            'text'
            '<gcb-youtube videoid="Kdg2drcUjYI" instanceid="c4CLTDvttJEu">'
            '</gcb-youtube>')
        self.course.save()

        key = ResourceBundleKey(ResourceKey.UNIT_TYPE, unit.unit_id, 'el')
        response = self._get_by_key(key)
        payload = transforms.loads(response['payload'])
        data = payload['sections'][2]['data']
        self.assertEquals(1, len(data))
        self.assertEquals(
            'text<gcb-youtube#1 videoid="Kdg2drcUjYI" />',
            data[0]['source_value'])

    def test_get_unit_content_with_custom_tag_with_body(self):
        unit = self.course.add_unit()
        unit.title = 'Test Unit with Tag'
        unit.unit_header = '<gcb-markdown>*hello*</gcb-markdown>'
        self.course.save()

        key = ResourceBundleKey(ResourceKey.UNIT_TYPE, unit.unit_id, 'el')
        response = self._get_by_key(key)
        payload = transforms.loads(response['payload'])
        data = payload['sections'][2]['data']
        self.assertEquals(1, len(data))
        self.assertEquals(
            '<gcb-markdown#1>*hello*</gcb-markdown#1>', data[0]['source_value'])


class LazyTranslatorTests(actions.TestBase):
    ADMIN_EMAIL = 'admin@foo.com'
    COURSE_NAME = 'i18n_course'
    COURSE_TITLE = 'I18N Course'

    def setUp(self):
        super(LazyTranslatorTests, self).setUp()

        self.base = '/' + self.COURSE_NAME
        self.app_context = actions.simple_add_course(
            self.COURSE_NAME, self.ADMIN_EMAIL, self.COURSE_TITLE)

    def test_lazy_translator_is_json_serializable(self):
        source_value = 'hello'
        translation_dict = {
            'type': 'string',
            'data': [
                {'source_value': 'hello', 'target_value': 'HELLO'}]}
        lazy_translator = LazyTranslator(
            self.app_context, source_value, translation_dict)
        self.assertEquals(
            '{"lt": "HELLO"}', transforms.dumps({'lt': lazy_translator}))


class CourseContentTranslationTests(actions.TestBase):
    ADMIN_EMAIL = 'admin@foo.com'
    COURSE_NAME = 'i18n_course'
    COURSE_TITLE = 'I18N Course'
    STUDENT_EMAIL = 'student@foo.com'

    def setUp(self):
        super(CourseContentTranslationTests, self).setUp()

        self.base = '/' + self.COURSE_NAME
        app_context = actions.simple_add_course(
            self.COURSE_NAME, self.ADMIN_EMAIL, self.COURSE_TITLE)
        self.old_namespace = namespace_manager.get_namespace()
        namespace_manager.set_namespace('ns_%s' % self.COURSE_NAME)

        self.course = courses.Course(None, app_context)
        self.unit = self.course.add_unit()
        self.unit.title = 'Test Unit'
        self.unit.unit_header = '<p>a</p><p>b</p>'
        self.unit.now_available = True

        self.lesson = self.course.add_lesson(self.unit)
        self.lesson.title = 'Test Lesson'
        self.lesson.objectives = '<p>c</p><p>d</p>'
        self.lesson.now_available = True

        self.course.save()

        self.unit_bundle = {
            'title': {
                'type': 'string',
                'source_value': '',
                'data': [
                    {'source_value': 'Test Unit', 'target_value': 'TEST UNIT'}]
            },
            'unit_header': {
                'type': 'html',
                'source_value': '<p>a</p><p>b</p>',
                'data': [
                    {'source_value': 'a', 'target_value': 'A'},
                    {'source_value': 'b', 'target_value': 'B'}]
            }
        }

        self.lesson_bundle = {
            'title': {
                'type': 'string',
                'source_value': '',
                'data': [
                    {
                        'source_value': 'Test Lesson',
                        'target_value': 'TEST LESSON'}]
            },
            'objectives': {
                'type': 'html',
                'source_value': '<p>c</p><p>d</p>',
                'data': [
                    {'source_value': 'c', 'target_value': 'C'},
                    {'source_value': 'd', 'target_value': 'D'}]
            }
        }

        self.unit_key_el = ResourceBundleKey(
            ResourceKey.UNIT_TYPE, self.unit.unit_id, 'el')
        self.lesson_key_el = ResourceBundleKey(
            ResourceKey.LESSON_TYPE, self.lesson.lesson_id, 'el')

        actions.login(self.ADMIN_EMAIL, is_admin=True)
        prefs = models.StudentPreferencesDAO.load_or_create()
        prefs.locale = 'el'
        models.StudentPreferencesDAO.save(prefs)

    def tearDown(self):
        del sites.Registry.test_overrides[sites.GCB_COURSES_CONFIG.name]
        namespace_manager.set_namespace(self.old_namespace)
        super(CourseContentTranslationTests, self).tearDown()

    def _store_resource_bundle(self):
        ResourceBundleDAO.save_all([
            ResourceBundleDTO(str(self.unit_key_el), self.unit_bundle),
            ResourceBundleDTO(str(self.lesson_key_el), self.lesson_bundle)])

    def test_lesson_and_unit_translated(self):
        self._store_resource_bundle()

        page_html = self.get('unit?unit=1').body

        self.assertIn('TEST UNIT', page_html)
        self.assertIn('<p>A</p><p>B</p>', page_html)
        self.assertIn('TEST LESSON', page_html)
        self.assertIn('<p>C</p><p>D</p>', page_html)

    def test_links_are_translated(self):
        link = self.course.add_link()
        link.title = 'Test Link'
        link.description = 'Test Description'
        link.href = 'http://www.foo.com'
        self.course.save()

        link_bundle = {
            'title': {
                'type': 'string',
                'source_value': '',
                'data': [
                    {
                        'source_value': 'Test Link',
                        'target_value': 'TEST LINK'}]
            },
            'description': {
                'type': 'string',
                'source_value': '',
                'data': [
                    {
                        'source_value': 'Test description',
                        'target_value': 'TEST DESCRIPTION'}]
            },
            'url': {
                'type': 'string',
                'source_value': '',
                'data': [
                    {
                    'source_value': 'http://www.foo.com',
                    'target_value': 'http://www.foo.gr'}]
            }
        }
        link_key = ResourceBundleKey(
            ResourceKey.LINK_TYPE, link.unit_id, 'el')
        ResourceBundleDAO.save(
            ResourceBundleDTO(str(link_key), link_bundle))

        page_html = self.get('course').body
        self.assertIn('TEST LINK', page_html)
        self.assertIn('TEST DESCRIPTION', page_html)
        self.assertIn('http://www.foo.gr', page_html)

    def test_assessments_are_translated(self):
        assessment = self.course.add_assessment()
        assessment.title = 'Test Assessment'
        assessment.html_content = '<p>a</p><p>b</p>'
        self.course.save()

        assessment_bundle = {
            'assessment:title': {
                'type': 'string',
                'source_value': '',
                'data': [
                    {
                        'source_value': 'Test Assessment',
                        'target_value': 'TEST ASSESSMENT'}]
            },
            'assessment:html_content': {
                'type': 'html',
                'source_value': '<p>a</p><p>b</p>',
                'data': [
                    {'source_value': 'a', 'target_value': 'A'},
                    {'source_value': 'b', 'target_value': 'B'}]
            }
        }
        assessment_key = ResourceBundleKey(
            ResourceKey.ASSESSMENT_TYPE, assessment.unit_id, 'el')
        ResourceBundleDAO.save(
            ResourceBundleDTO(str(assessment_key), assessment_bundle))

        page_html = self.get('assessment?name=%s' % assessment.unit_id).body
        self.assertIn('TEST ASSESSMENT', page_html)
        self.assertIn('<p>A</p><p>B</p>', page_html)

    def test_bad_translations_are_flagged_for_admin(self):
        del self.unit_bundle['unit_header']['data'][1]
        self._store_resource_bundle()

        dom = self.parse_html_string(self.get('unit?unit=1').body)

        self.assertEquals(
            'The lists of translations must have the same number of items (1) '
            'as extracted from the original content (2).',
            dom.find('.//div[@class="gcb-translation-error-body"]').text)

    def test_bad_translations_are_not_flagged_for_student(self):
        del self.unit_bundle['unit_header']['data'][1]
        self._store_resource_bundle()

        actions.logout()
        actions.login(self.STUDENT_EMAIL, is_admin=False)
        self.assertIn('<p>a</p><p>b</p>', self.get('unit?unit=1').body)

    def test_fallback_to_default_when_translation_missing(self):
        del self.lesson_bundle['objectives']
        self._store_resource_bundle()

        page_html = self.get('unit?unit=1').body

        self.assertIn('TEST UNIT', page_html)
        self.assertIn('<p>A</p><p>B</p>', page_html)
        self.assertIn('TEST LESSON', page_html)
        self.assertNotIn('<p>C</p><p>D</p>', page_html)
        self.assertIn('<p>c</p><p>d</p>', page_html)

    def test_fallback_to_default_when_partial_translation_found(self):
        del self.lesson_bundle['objectives']['data'][1]
        self._store_resource_bundle()

        page_html = self.get('unit?unit=1').body

        self.assertIn('TEST UNIT', page_html)
        self.assertIn('<p>A</p><p>B</p>', page_html)
        self.assertIn('TEST LESSON', page_html)
        self.assertNotIn('<p>C</p><p>D</p>', page_html)
        self.assertIn('<p>c</p><p>d</p>', page_html)

    def test_custom_tag_expanded(self):
        source_video_id = 'Kdg2drcUjYI'
        target_video_id = 'jUfccP5Rl5M'
        unit_header = (
            'text'
            '<gcb-youtube videoid="%s" instanceid="c4CLTDvttJEu">'
            '</gcb-youtube>') % source_video_id

        unit = self.course.add_unit()
        unit.title = 'Tag Unit'
        unit.unit_header = unit_header
        self.course.save()

        unit_bundle = {
            'title': {
                'type': 'string',
                'source_value': '',
                'data': [
                    {'source_value': 'Tag Unit', 'target_value': 'TAG UNIT'}]
            },
            'unit_header': {
                'type': 'html',
                'source_value': unit_header,
                'data': [
                    {
                        'source_value': (
                            'text<gcb-youtube#1 videoid="%s" />'
                        ) % source_video_id,
                        'target_value': (
                            'TEXT<gcb-youtube#1 videoid="%s" />'
                        ) % target_video_id}]
            }
        }
        unit_key_el = ResourceBundleKey(
            ResourceKey.UNIT_TYPE, unit.unit_id, 'el')
        ResourceBundleDAO.save(
            ResourceBundleDTO(str(unit_key_el), unit_bundle))

        page_html = self.get('unit?unit=%s' % unit.unit_id).body
        dom = self.parse_html_string(page_html)
        main = dom.find('.//div[@id="gcb-main-article"]/div[1]')
        self.assertEquals('TEXT', main.text.strip())
        self.assertEquals('div', main[0].tag)
        self.assertEquals('gcb-video-container', main[0].attrib['class'])
        self.assertEquals(1, len(main[0]))
        self.assertEquals('iframe', main[0][0].tag)
        self.assertIn(target_video_id, main[0][0].attrib['src'])

    def test_custom_tag_with_body_is_translated(self):
        tag_string = (
            '<gcb-markdown instanceid="c4CLTDvttJEu">'
            '*hello*'
            '</gcb-markdown>')
        unit = self.course.add_unit()
        unit.title = 'Tag Unit'
        unit.unit_header = tag_string
        self.course.save()

        unit_bundle = {
            'unit_header': {
                'type': 'html',
                'source_value': tag_string,
                'data': [
                    {
                        'source_value': (
                            '<gcb-markdown#1>*hello*</gcb-markdown#1>'),
                        'target_value': (
                            '<gcb-markdown#1>*HELLO*</gcb-markdown#1>')}
                ]
            }
        }
        unit_key_el = ResourceBundleKey(
            ResourceKey.UNIT_TYPE, unit.unit_id, 'el')
        ResourceBundleDAO.save(
            ResourceBundleDTO(str(unit_key_el), unit_bundle))

        page_html = self.get('unit?unit=%s' % unit.unit_id).body
        dom = self.parse_html_string(page_html)
        main = dom.find('.//div[@id="gcb-main-article"]/div[1]')
        markdown = main.find('.//div[@class="gcb-markdown"]/p')
        self.assertEquals('HELLO', markdown.find('./em').text)

    def _add_question(self):
        # Create a question
        qu_dict = {
            'type': 0,
            'question': 'question text',
            'description': 'description text',
            'choices': [
                {'text': 'choice 1', 'score': 0.0, 'feedback': ''},
                {'text': 'choice 2', 'score': 1.0, 'feedback': ''}],
            'multiple_selections': False,
            'last_modified': 1410451682.042784,
            'version': '1.5'
        }
        qu_dto = models.QuestionDTO(None, qu_dict)
        qu_id = models.QuestionDAO.save(qu_dto)

        # Store translation data for the question
        qu_bundle = {
            'question': {
                'type': 'html',
                'source_value': 'question text',
                'data': [
                    {
                        'source_value': 'question text',
                        'target_value': 'QUESTION TEXT'
                    }]
            },
            'description': {
                'source_value': None,
                'type': 'string',
                'data': [
                    {
                        'source_value': 'description text',
                        'target_value': 'DESCRIPTION TEXT'
                    }]
            },
            'choices:[0]:text': {
                'type': 'html',
                'source_value': 'choice 1',
                'data': [
                    {
                        'source_value': 'choice 1',
                        'target_value': 'CHOICE 1'
                    }
                ]
            },
            'choices:[1]:text': {
                'source_value': 'choice 2',
                'type': 'html',
                'data': [
                    {
                        'source_value': 'choice 2',
                        'target_value': 'CHOICE 2'
                    }
                ]
            }}
        key_el = ResourceBundleKey(
            ResourceKey.QUESTION_MC_TYPE, qu_id, 'el')
        ResourceBundleDAO.save(
            ResourceBundleDTO(str(key_el), qu_bundle))

        return qu_id

    def test_questions_are_translated(self):
        # Create an assessment and add the question to the content
        assessment = self.course.add_assessment()
        assessment.title = 'Test Assessment'
        assessment.html_content = """
            <question quid="%s" weight="1" instanceid="test_question"></question>
        """ % self._add_question()
        self.course.save()

        page_html = self.get('assessment?name=%s' % assessment.unit_id).body
        self.assertIn('QUESTION TEXT', page_html)
        self.assertIn('CHOICE 1', page_html)
        self.assertIn('CHOICE 2', page_html)

    def test_question_groups_are_translated(self):
        # Create a question group with one question
        qgp_dict = {
            'description': 'description text',
            'introduction': '<p>a</p><p>b</p>',
            'items': [{'question': self._add_question(), 'weight': '1'}],
            'last_modified': 1410451682.042784,
            'version': '1.5'
        }
        qgp_dto = models.QuestionGroupDTO(None, qgp_dict)
        qgp_id = models.QuestionGroupDAO.save(qgp_dto)

        # Create an assessment and add the question group to the content
        assessment = self.course.add_assessment()
        assessment.title = 'Test Assessment'
        assessment.html_content = """
            <question-group qgid="%s" instanceid="test-qgp">
            </question-group><br>
        """ % qgp_id
        self.course.save()

        # Store translation data for the question
        qgp_bundle = {
            'description': {
                'source_value': None,
                'type': 'string',
                'data': [
                    {
                        'source_value': 'description text',
                        'target_value': 'DESCRIPTION TEXT'
                    }]
            },
            'introduction': {
                'type': 'html',
                'source_value': '<p>a</p><p>b</p>',
                'data': [
                    {
                        'source_value': 'a',
                        'target_value': 'A'
                    },
                    {
                        'source_value': 'b',
                        'target_value': 'B'
                    }
                ]
            }}
        key_el = ResourceBundleKey(
            ResourceKey.QUESTION_GROUP_TYPE, qgp_id, 'el')
        ResourceBundleDAO.save(
            ResourceBundleDTO(str(key_el), qgp_bundle))

        page_html = self.get('assessment?name=%s' % assessment.unit_id).body
        dom = self.parse_html_string(page_html)
        main = dom.find('.//div[@id="test-qgp"]')
        self.assertEquals(
            'A', main.find('.//div[@class="qt-introduction"]/p[1]').text)
        self.assertEquals(
            'B', main.find('.//div[@class="qt-introduction"]/p[2]').text)
        self.assertEquals(
            'QUESTION TEXT', main.find('.//div[@class="qt-question"]').text)
        self.assertEquals(
            'CHOICE 1',
            main.findall('.//div[@class="qt-choices"]//label')[0].text.strip())
        self.assertEquals(
            'CHOICE 2',
            main.findall('.//div[@class="qt-choices"]//label')[1].text.strip())

    def test_course_settings_are_translated(self):
        course_bundle = {
            'course:title': {
                'source_value': None,
                'type': 'string',
                'data': [
                    {
                        'source_value': self.COURSE_TITLE,
                        'target_value': 'TRANSLATED TITLE'
                    }]
            }}
        key_el = ResourceBundleKey(
            ResourceKey.COURSE_SETTINGS_TYPE, 'homepage', 'el')
        ResourceBundleDAO.save(
            ResourceBundleDTO(str(key_el), course_bundle))

        page_html = self.get('course').body
        dom = self.parse_html_string(page_html)
        self.assertEquals(
            'TRANSLATED TITLE',
            dom.find('.//h1[@class="gcb-product-headers-large"]').text.strip())

    def test_course_settings_load_with_default_locale(self):
        # NOTE: This is to test the protections against a vulnerability
        # to infinite recursion in the course settings translation. The issue
        # is that when no locale is set, then sites.get_current_locale needs
        # to refer to the course settings to find the default locale. However
        # if this call to get_current_locale takes place inside the translation
        # callback from loading the course settings, there will be infinite
        # recursion. This test checks that this case is defended.
        prefs = models.StudentPreferencesDAO.load_or_create()
        models.StudentPreferencesDAO.delete(prefs)

        page_html = self.get('course').body
        dom = self.parse_html_string(page_html)
        self.assertEquals(
            self.COURSE_TITLE,
            dom.find('.//h1[@class="gcb-product-headers-large"]').text.strip())


class TranslationImportExportTests(actions.TestBase):
    ADMIN_EMAIL = 'admin@foo.com'
    COURSE_NAME = 'i18n_course'
    COURSE_TITLE = 'I18N Course'
    STUDENT_EMAIL = 'student@foo.com'

    URL = 'dashboard?action=i18n_dashboard'

    def setUp(self):
        super(TranslationImportExportTests, self).setUp()

        self.base = '/' + self.COURSE_NAME
        app_context = actions.simple_add_course(
            self.COURSE_NAME, self.ADMIN_EMAIL, self.COURSE_TITLE)
        self.old_namespace = namespace_manager.get_namespace()
        namespace_manager.set_namespace('ns_%s' % self.COURSE_NAME)

        self.course = courses.Course(None, app_context)

        self.unit = self.course.add_unit()
        self.unit.title = 'unit title'
        self.unit.description = 'unit description'
        self.unit.unit_header = 'unit header'
        self.unit.unit_footer = 'unit footer'
        self.unit.now_available = True

        self.assessment = self.course.add_assessment()
        self.assessment.title = 'assessment title'
        self.assessment.description = 'assessment description'
        self.assessment.html_content = 'assessment html content'
        self.assessment.html_review_form = 'assessment html review form'
        self.assessment.now_available = True

        self.link = self.course.add_link()
        self.link.title = 'link title'
        self.link.description = 'link description'
        self.link.url = 'link url'

        self.lesson = self.course.add_lesson(self.unit)
        self.lesson.title = 'lesson title'
        self.lesson.objectives = 'lesson objectives'
        self.lesson.video_id = 'lesson video'
        self.lesson.notes = 'lesson notes'
        self.lesson.now_available = True

        self.course.save()

        foo_content = StringIO.StringIO('content of foo.jpg')
        fs = app_context.fs.impl
        fs.put(fs.physical_to_logical('/assets/img/foo.jpg'), foo_content)

        mc_qid = models.QuestionDAO.save(models.QuestionDTO(
            None,
            {
                'question': 'mc question',
                'description': 'mc description',
                'type': 0,
                'choices': [
                    {'score': 1.0,
                     'feedback': 'mc feedback one',
                     'text': 'mc answer one'},
                    {'score': 0.0,
                     'feedback': 'mc feedback two',
                     'text': 'mc answer two'}
                    ],
                'multiple_selections': False,
                'version': '1.5',
                }))
        sa_qid = models.QuestionDAO.save(models.QuestionDTO(
            None,
            {
                'question': 'sa question',
                'description': 'sa description',
                'type': 1,
                'columns': 100,
                'hint': 'sa hint',
                'graders': [
                    {'score': '1.0',
                     'response': 'sa response',
                     'feedback': 'sa feedback',
                     'matcher': 'case_insensitive'}
                    ],
                'version': '1.5',
                'defaultFeedback': 'sa default feedback',
                'rows': 1}))

        models.QuestionGroupDAO.save(models.QuestionGroupDTO(
            None,
            {'items': [
                {'weight': '1',
                 'question': mc_qid},
                {'weight': '1',
                 'question': sa_qid}],
             'version': '1.5',
             'introduction': 'question group introduction',
             'description': 'question group description'}))

        actions.login(self.ADMIN_EMAIL, is_admin=True)
        prefs = models.StudentPreferencesDAO.load_or_create()
        prefs.locale = 'el'
        models.StudentPreferencesDAO.save(prefs)

    def tearDown(self):
        namespace_manager.set_namespace(self.old_namespace)
        super(TranslationImportExportTests, self).tearDown()

    def test_added_items_appear_on_dashboard(self):
        """Ensure that all items added in setUp are present on dashboard.

        Do this so that we can trust in other tests that when we don't
        see something that we don't expect to see it's not because we failed
        to add the item, but instead it really is getting actively suppressed.
        """
        response = self.get(self.URL)
        self.assertIn('unit title', response.body)
        self.assertIn('assessment title', response.body)
        self.assertIn('link title', response.body)
        self.assertIn('lesson title', response.body)
        self.assertIn('mc description', response.body)
        self.assertIn('sa description', response.body)
        self.assertIn('question group description', response.body)
        self.assertIn('assets/img/foo.jpg', response.body)

    def test_download_exports_all_expected_fields(self):
        extra_env = {
            'extra_locales': [{'locale': 'de', 'availability': 'available'}]
            }
        with actions.OverriddenEnvironment(extra_env):
            response = self.get(self.URL)
            response = self.click(response, 'Download Translation Files')
            self.assertEquals(200, response.status_int)
            download_zf = zipfile.ZipFile(
                cStringIO.StringIO(response.body), 'r')
            out_stream = StringIO.StringIO()
            out_stream.fp = out_stream
            for item in download_zf.infolist():
                catalog = pofile.read_po(
                    cStringIO.StringIO(download_zf.read(item)))
                messages = [msg.id for msg in catalog]
                self.assertIn('unit title', messages)
                self.assertIn('unit description', messages)
                self.assertIn('unit header', messages)
                self.assertIn('unit footer', messages)
                self.assertIn('assessment title', messages)
                self.assertIn('assessment description', messages)
                self.assertIn('assessment html content', messages)
                self.assertIn('assessment html review form', messages)
                self.assertIn('link title', messages)
                self.assertIn('link description', messages)
                self.assertIn('lesson title', messages)
                self.assertIn('lesson objectives', messages)
                self.assertIn('lesson notes', messages)
                self.assertIn('mc question', messages)
                self.assertIn('mc description', messages)
                self.assertIn('mc feedback one', messages)
                self.assertIn('mc answer one', messages)
                self.assertIn('mc feedback two', messages)
                self.assertIn('mc answer two', messages)
                self.assertIn('sa question', messages)
                self.assertIn('sa description', messages)
                self.assertIn('sa hint', messages)
                self.assertIn('sa response', messages)
                self.assertIn('sa feedback', messages)
                self.assertIn('sa default feedback', messages)
                self.assertIn('question group introduction', messages)
                self.assertIn('question group description', messages)

                # Non-translatable items; will require manual attention from
                # someone who understands the course material.
                self.assertNotIn('link url', messages)
                self.assertNotIn('lesson video', messages)
                self.assertNotIn('foo.jpg', messages)

    def test_upload_translations(self):
        actions.update_course_config(
            self.COURSE_NAME,
            {'extra_locales': [{'locale': 'el', 'availability': 'available'}]})

        # Download the course translations, and build a catalog containing
        # all the translations repeated.
        response = self.get('dashboard?action=i18n_download')
        download_zf = zipfile.ZipFile(cStringIO.StringIO(response.body), 'r')
        out_stream = StringIO.StringIO()
        out_stream.fp = out_stream
        upload_zf = zipfile.ZipFile(out_stream, 'w')
        num_translations = 0
        for item in download_zf.infolist():
            catalog = pofile.read_po(cStringIO.StringIO(download_zf.read(item)))
            for msg in catalog:
                if msg.locations:
                    msg.string = msg.id.upper() * 2
            content = cStringIO.StringIO()
            pofile.write_po(content, catalog)
            upload_zf.writestr(item.filename, content.getvalue())
            content.close()
        upload_zf.close()

        # Upload the modified translations.
        upload_contents = out_stream.getvalue()
        xsrf_token = crypto.XsrfTokenManager.create_xsrf_token(
            TranslationUploadRestHandler.XSRF_TOKEN_NAME)
        self.post('/%s%s' % (self.COURSE_NAME,
                             TranslationUploadRestHandler.URL),
                  {'request': transforms.dumps({
                      'xsrf_token': cgi.escape(xsrf_token),
                      'payload': transforms.dumps({'key', ''})})},
                  upload_files=[('file', 'doesntmatter', upload_contents)])

        # Download the translations; verify the doubling.
        response = self.get('dashboard?action=i18n_download')
        zf = zipfile.ZipFile(cStringIO.StringIO(response.body), 'r')
        num_translations = 0
        for item in zf.infolist():
            catalog = pofile.read_po(cStringIO.StringIO(zf.read(item)))
            for msg in catalog:
                if msg.locations:  # Skip header pseudo-message entry
                    num_translations += 1
                    self.assertNotEquals(msg.id, msg.string)
                    self.assertEquals(msg.id.upper() * 2, msg.string)
        self.assertEquals(30, num_translations)

        # And verify the presence of the translated versions on actual
        # course pages.
        response = self.get('unit?unit=%s' % self.unit.unit_id)
        self.assertIn(self.unit.title.upper() * 2, response.body)
        self.assertIn(self.lesson.title.upper() * 2, response.body)


class TranslatorRoleTests(actions.TestBase):
    ADMIN_EMAIL = 'admin@foo.com'
    USER_EMAIL = 'user@foo.com'
    COURSE_NAME = 'i18n_course'
    DASHBOARD_URL = 'dashboard?action=i18n_dashboard'
    CONSOLE_REST_URL = 'rest/modules/i18n_dashboard/translation_console'
    ENVIRON = {
        'extra_locales': [
            {'locale': 'el', 'availability': 'unavailable'},
            {'locale': 'ru', 'availability': 'unavailable'},
        ]}

    def setUp(self):
        super(TranslatorRoleTests, self).setUp()

        self.base = '/' + self.COURSE_NAME
        actions.simple_add_course(
            self.COURSE_NAME, self.ADMIN_EMAIL, 'I18N Course')
        self.old_namespace = namespace_manager.get_namespace()
        namespace_manager.set_namespace('ns_%s' % self.COURSE_NAME)

        self.old_registered_permission = roles.Roles._REGISTERED_PERMISSIONS
        roles.Roles.REGISTERED_PERMISSIONS = {}

    def tearDown(self):
        del sites.Registry.test_overrides[sites.GCB_COURSES_CONFIG.name]
        roles.Roles.REGISTERED_PERMISSIONS = self.old_registered_permission
        namespace_manager.set_namespace(self.old_namespace)
        super(TranslatorRoleTests, self).tearDown()

    def _createTranslatorRole(self, name, locales):
        permissions = {
            dashboard.custom_module.name: [i18n_dashboard.ACCESS_PERMISSION],
            i18n_dashboard.custom_module.name: [
                i18n_dashboard.locale_to_permission(loc) for loc in locales]
        }
        role_dto = models.RoleDTO(None, {
            'name': name,
            'users': [self.USER_EMAIL],
            'permissions': permissions
        })
        models.RoleDAO.save(role_dto)

    def test_no_permission_redirect(self):
        with actions.OverriddenEnvironment(self.ENVIRON):
            actions.login(self.USER_EMAIL, is_admin=False)
            self.assertEquals(self.get(self.DASHBOARD_URL).status_int, 302)

    def test_restricted_access(self):
        with actions.OverriddenEnvironment(self.ENVIRON):
            self._createTranslatorRole('ElTranslator', ['el'])
            actions.login(self.USER_EMAIL, is_admin=False)
            dom = self.parse_html_string(self.get(self.DASHBOARD_URL).body)
            table = dom.find('.//table[@class="i18n-progress-table"]')
            columns = table.findall('./thead/tr/th')
            expected_col_data = [
                'Asset',
                'el'
            ]
            self.assertEquals(len(expected_col_data), len(columns))
            for index, expected in enumerate(expected_col_data):
                self.assertEquals(expected, columns[index].text)
            response = self.get('%s?key=%s' % (
                self.CONSOLE_REST_URL, 'course_settings%3Acourse%3Aru'))
            self.assertEquals(transforms.loads(response.body)['status'], 401)
            response = self.get('%s?key=%s' % (
                self.CONSOLE_REST_URL, 'course_settings%3Acourse%3Ael'))
            self.assertEquals(transforms.loads(response.body)['status'], 200)


class SampleCourseLocalizationTest(actions.TestBase):

    def setUp(self):
        super(SampleCourseLocalizationTest, self).setUp()
        if sites.GCB_COURSES_CONFIG.name in sites.Registry.test_overrides:
            del sites.Registry.test_overrides[sites.GCB_COURSES_CONFIG.name]
        self.auto_deploy = sites.ApplicationContext.AUTO_DEPLOY_DEFAULT_COURSE
        sites.ApplicationContext.AUTO_DEPLOY_DEFAULT_COURSE = False
        self._import_course()
        self._locale_to_label = {}

    def tearDown(self):
        del sites.Registry.test_overrides[sites.GCB_COURSES_CONFIG.name]
        sites.ApplicationContext.AUTO_DEPLOY_DEFAULT_COURSE = self.auto_deploy
        super(SampleCourseLocalizationTest, self).tearDown()

    def _import_course(self):
        email = 'test_course_localization@google.com'
        actions.login(email, is_admin=True)

        response = self.get('/admin?action=welcome')
        self.assertEquals(response.status_int, 200)
        response = self.post(
            '/admin?action=add_first_course',
            params={'xsrf_token': crypto.XsrfTokenManager.create_xsrf_token(
                'add_first_course')})
        self.assertEquals(response.status_int, 302)

        sites.setup_courses('course:/first::ns_first')

        response = self.get('first/dashboard')
        self.assertIn('My First Course', response.body)
        self.assertEquals(response.status_int, 200)

    def _import_sample_course(self):
        email = 'test_course_localization@google.com'
        actions.login(email, is_admin=True)

        response = self.get('/admin?action=welcome')
        self.assertEquals(response.status_int, 200)
        response = self.post(
            '/admin?action=explore_sample',
            params={'xsrf_token': crypto.XsrfTokenManager.create_xsrf_token(
                'explore_sample')})
        self.assertEquals(response.status_int, 302)

        sites.setup_courses('course:/sample::ns_sample')

        response = self.get('sample/dashboard')
        self.assertIn('Power Searching with Google', response.body)
        self.assertEquals(response.status_int, 200)

    def _setup_locales(self, availability='available', course='first'):
        request = {
            'key': '/course.yaml',
            'payload': (
                '{\"i18n\":{\"course:locale\":\"en_US\",\"extra_locales\":['
                '{\"locale\":\"ru_RU\",\"availability\":\"%s\"}, '
                '{\"locale\":\"es_ES\",\"availability\":\"%s\"}'
                ']}}' % (availability, availability)),
            'xsrf_token': crypto.XsrfTokenManager.create_xsrf_token(
                'basic-course-settings-put')}
        response = self.put(
            '%s/rest/course/settings' % course, params={
            'request': transforms.dumps(request)})
        self.assertEquals(response.status_int, 200)

        # check labels exist
        with Namespace('ns_%s' % course):
            labels = models.LabelDAO.get_all_of_type(
                models.LabelDTO.LABEL_TYPE_LOCALE)
            self.assertEqual(3, len(labels))
            for label in labels:
                self._locale_to_label[label.title] = label

    def _add_announcement(self, title, locales):
        with Namespace('ns_first'):
            labels = models.LabelDAO.get_all_of_type(
                models.LabelDTO.LABEL_TYPE_LOCALE)
            label_ids = []
            for label in labels:
                for locale in locales:
                    if label.title == locale:
                        label_ids.append(label.id)
            annon = announcements.AnnouncementEntity()
            annon.title = title
            annon.labels = utils.list_to_text(label_ids)
            annon.is_draft = False
            annon.put()

    def _add_announcements(self):
        self._add_announcement('Test announcement EN', ['en_US'])
        self._add_announcement('Test announcement RU', ['ru_RU'])
        self._add_announcement('Test announcement ES', ['es_ES'])
        self._add_announcement(
            'Test announcement ALL', ['en_US', 'ru_RU', 'es_ES'])
        self._add_announcement('Test announcement NONE', [])
        with Namespace('ns_first'):
            items = announcements.AnnouncementEntity.get_announcements()
            self.assertEqual(5, len(items))

    def _add_units(self, locale_labels=False):
        with Namespace('ns_first'):
            course = courses.Course(None, sites.get_all_courses()[0])

            _en = course.add_unit()
            _en.type = 'U'
            _en.now_available = True
            _en.title = 'Unit en_US'

            _ru = course.add_unit()
            _ru.type = 'U'
            _ru.now_available = True
            _ru.title = 'Unit ru_RU'

            _es = course.add_unit()
            _es.type = 'U'
            _es.now_available = True
            _es.title = 'Unit es_ES'

            _all = course.add_unit()
            _all.type = 'U'
            _all.now_available = True
            _all.title = 'Unit all_ALL'

            _none = course.add_unit()
            _none.type = 'U'
            _none.now_available = True
            _none.title = 'Unit none_NONE'

            if locale_labels:
                _en.labels = utils.list_to_text(
                    [self._locale_to_label['en_US'].id])
                _ru.labels = utils.list_to_text(
                    [self._locale_to_label['ru_RU'].id])
                _es.labels = utils.list_to_text(
                    [self._locale_to_label['es_ES'].id])
                _all.labels = utils.list_to_text([
                    self._locale_to_label['es_ES'].id,
                    self._locale_to_label['ru_RU'].id])
                _none.labels = utils.list_to_text([])

            course.save()

            self._locale_to_unit = {}
            self._locale_to_unit['en_US'] = _en
            self._locale_to_unit['ru_RU'] = _ru
            self._locale_to_unit['es_ES'] = _es

    def _set_labels_on_current_student(self, labels, ids=None):
        with Namespace('ns_first'):
            user = users.get_current_user()
            if ids is None:
                ids = [label.id for label in labels]
            labels = utils.list_to_text(ids)
            models.StudentProfileDAO.update(
                user.user_id(), user.email(), labels=labels)

    def _set_prefs_locale(self, locale, course='first'):
        with Namespace('ns_%s' % course):
            prefs = models.StudentPreferencesDAO.load_or_create()
            prefs.locale = locale
            models.StudentPreferencesDAO.save(prefs)

    def _assert_picker(self, is_present, has_locales=None, is_admin=False):
        actions.login('_assert_picker_visible@example.com', is_admin=is_admin)
        response = self.get('first/course')
        self.assertEquals(response.status_int, 200)
        dom = self.parse_html_string(response.body)
        if is_present:
            self.assertTrue(dom.find('.//select[@id="locale-select"]'))
            for has_locale in has_locales:
                option = dom.find(
                    './/select[@id="locale-select"]'
                    '/option[@value="%s"]' % has_locale)
                self.assertIsNotNone(option)
        else:
            self.assertFalse(dom.find('.//select[@id="locale-select"]'))
        actions.logout()

    def _assert_en_ru_es_all_none(self, en, ru, es, _all, _none, lang):
        response = self.get('first/announcements')
        self.assertEquals(response.status_int, 200)
        if en:
            self.assertIn('Test announcement EN', response.body)
        else:
            self.assertNotIn('Test announcement EN', response.body)
        if ru:
            self.assertIn('Test announcement RU', response.body)
        else:
            self.assertNotIn('Test announcement RU', response.body)
        if es:
            self.assertIn('Test announcement ES', response.body)
        else:
            self.assertNotIn('Test announcement ES', response.body)
        if _all:
            self.assertIn('Test announcement ALL', response.body)
        else:
            self.assertNotIn('Test announcement ALL', response.body)
        if _none:
            self.assertIn('Test announcement NONE', response.body)
        else:
            self.assertNotIn('Test announcement NONE', response.body)
        self.assertEquals(self.parse_html_string(
                response.body).get('lang'), lang)
        return response

    def _course_en_ru_es_all_none(self, en, ru, es, _all, _none, lang):
        response = self.get('first/course')
        self.assertEquals(response.status_int, 200)
        if en:
            self.assertIn('Unit en_US', response.body)
        else:
            self.assertNotIn('Unit en_US', response.body)
        if ru:
            self.assertIn('Unit ru_RU', response.body)
        else:
            self.assertNotIn('Unit ru_RU', response.body)
        if es:
            self.assertIn('Unit es_ES', response.body)
        else:
            self.assertNotIn('Unit es_ES', response.body)
        if _all:
            self.assertIn('Unit all_ALL', response.body)
        else:
            self.assertNotIn('Unit all_ALL', response.body)
        if _none:
            self.assertIn('Unit none_NONE', response.body)
        else:
            self.assertNotIn('Unit none_NONE', response.body)
        self.assertEquals(self.parse_html_string(
                response.body).get('lang'), lang)
        return response

    def test_locale_picker_visibility_for_available_locales_as_student(self):
        self._setup_locales()
        with actions.OverriddenEnvironment(
            {'course': {
                'now_available': True, 'can_student_change_locale': True}}):
            self._assert_picker(True, ['en_US', 'ru_RU', 'es_ES'])
        with actions.OverriddenEnvironment(
            {'course': {
                'now_available': True, 'can_student_change_locale': False}}):
            self._assert_picker(False)

    def test_locale_picker_visibility_for_unavailable_locales_as_student(self):
        self._setup_locales(availability='unavailable')
        with actions.OverriddenEnvironment(
            {'course': {
                'now_available': True, 'can_student_change_locale': True}}):
            self._assert_picker(True, ['en_US'])
        with actions.OverriddenEnvironment(
            {'course': {
                'now_available': True, 'can_student_change_locale': False}}):
            self._assert_picker(False)

    def test_locale_picker_visibility_for_unavailable_locales_as_admin(self):
        self._setup_locales(availability='unavailable')
        with actions.OverriddenEnvironment(
            {'course': {
                'now_available': True, 'can_student_change_locale': True}}):
            self._assert_picker(
                True, ['en_US', 'ru_RU', 'es_ES'], is_admin=True)
        with actions.OverriddenEnvironment(
            {'course': {
                'now_available': True, 'can_student_change_locale': False}}):
            self._assert_picker(False, is_admin=True)

    def test_view_announcement_via_locale_picker(self):
        self._setup_locales()
        self._add_announcements()

        actions.logout()
        actions.login('test_view_announcement_via_locale_picker@example.com')

        with actions.OverriddenEnvironment(
            {'course': {
                'now_available': True, 'can_student_change_locale': True}}):
            actions.register(
                self,
                'test_view_announcement_via_locale_picker', course='first')

            self._set_prefs_locale(None)
            response = self._assert_en_ru_es_all_none(
                True, False, False, True, True, 'en_US')
            self.assertIn('Announcements', response.body)

            self._set_prefs_locale('ru_RU')
            response = self._assert_en_ru_es_all_none(
                False, True, False, True, True, 'ru_RU')
            self.assertIn('Сообщения', response.body)

            self._set_prefs_locale('es_ES')
            response = self._assert_en_ru_es_all_none(
                False, False, True, True, True, 'es_ES')
            self.assertIn('Avisos', response.body)

            # when locale labels are combined with prefs, labels win
            self._set_prefs_locale(None)
            self._set_labels_on_current_student(
                [self._locale_to_label['ru_RU']])
            self._assert_en_ru_es_all_none(
                False, True, False, True, True, 'ru_RU')

            self._set_prefs_locale('es_ES')
            self._set_labels_on_current_student(
                [self._locale_to_label['ru_RU']])
            self._assert_en_ru_es_all_none(
                False, True, False, True, True, 'ru_RU')

    def test_announcements_via_locale_labels(self):
        self._setup_locales()
        self._add_announcements()

        actions.logout()
        actions.login('test_announcements_via_locale_labels@example.com')

        with actions.OverriddenEnvironment(
            {'course': {
                'now_available': True, 'can_student_change_locale': False}}):
            actions.register(
                self, 'test_announcements_via_locale_labels', course='first')

            self._set_prefs_locale(None)
            self._set_labels_on_current_student([])
            self._assert_en_ru_es_all_none(
                True, True, True, True, True, 'en_US')

            self._set_labels_on_current_student(
                [self._locale_to_label['en_US']])
            self._assert_en_ru_es_all_none(
                True, False, False, True, True, 'en_US')

            self._set_labels_on_current_student(
                [self._locale_to_label['ru_RU']])
            self._assert_en_ru_es_all_none(
                False, True, False, True, True, 'ru_RU')

            self._set_labels_on_current_student(
                [self._locale_to_label['es_ES']])
            self._assert_en_ru_es_all_none(
                False, False, True, True, True, 'es_ES')

            self._set_prefs_locale('ru_RU')
            self._set_labels_on_current_student([])
            response = self._assert_en_ru_es_all_none(
                True, True, True, True, True, 'ru_RU')
            self.assertIn('Сообщения', response.body)

            self._set_prefs_locale('ru_RU')
            self._set_labels_on_current_student(
                [self._locale_to_label['es_ES']])
            response = self._assert_en_ru_es_all_none(
                False, False, True, True, True, 'es_ES')
            self.assertIn('Avisos', response.body)

    def test_course_track_via_locale_picker(self):
        self._setup_locales()
        self._add_units(locale_labels=True)

        actions.logout()
        actions.login('test_course_track_via_locale_picker@example.com')

        with actions.OverriddenEnvironment(
            {'course': {
                'now_available': True, 'can_student_change_locale': True}}):
            actions.register(
                self, 'test_course_track_via_locale_picker', course='first')

            self._set_prefs_locale(None)
            self._course_en_ru_es_all_none(
                True, False, False, False, True, 'en_US')

            self._set_prefs_locale('en_US')
            response = self._course_en_ru_es_all_none(
                True, False, False, False, True, 'en_US')
            self.assertIn('Announcements', response.body)

            self._set_prefs_locale('ru_RU')
            response = self._course_en_ru_es_all_none(
                False, True, False, True, True, 'ru_RU')
            self.assertIn('Сообщения', response.body)

            self._set_prefs_locale('es_ES')
            response = self._course_en_ru_es_all_none(
                False, False, True, True, True, 'es_ES')
            self.assertIn('Avisos', response.body)

    def test_course_track_via_locale_labels(self):
        self._setup_locales()
        self._add_units(locale_labels=True)

        actions.logout()
        actions.login('test_course_track_via_locale_picker@example.com')

        with actions.OverriddenEnvironment(
            {'course': {
                'now_available': True, 'can_student_change_locale': True}}):
            actions.register(
                self, 'test_course_track_via_locale_picker', course='first')

            self._set_labels_on_current_student([])
            self._course_en_ru_es_all_none(
                True, False, False, False, True, 'en_US')

            self._set_labels_on_current_student(
                [self._locale_to_label['en_US']])
            self._course_en_ru_es_all_none(
                True, False, False, False, True, 'en_US')

            self._set_labels_on_current_student(
                [self._locale_to_label['ru_RU']])
            self._course_en_ru_es_all_none(
                False, True, False, True, True, 'ru_RU')

            self._set_labels_on_current_student(
                [self._locale_to_label['es_ES']])
            self._course_en_ru_es_all_none(
                False, False, True, True, True, 'es_ES')

    def test_track_and_locale_labels_do_work_together(self):
        self._setup_locales()

        with Namespace('ns_first'):
            track_a_id = models.LabelDAO.save(models.LabelDTO(
                None, {'title': 'Track A',
                       'version': '1.0',
                       'description': 'Track A',
                       'type': models.LabelDTO.LABEL_TYPE_COURSE_TRACK}))

            track_b_id = models.LabelDAO.save(models.LabelDTO(
                None, {'title': 'Track B',
                       'version': '1.0',
                       'description': 'Track B',
                       'type': models.LabelDTO.LABEL_TYPE_COURSE_TRACK}))

            locale_ru_id = self._locale_to_label['ru_RU'].id
            locale_es_id = self._locale_to_label['es_ES'].id

            course = courses.Course(None, sites.get_all_courses()[0])
            unit_1 = course.add_unit()
            unit_1.type = 'U'
            unit_1.now_available = True
            unit_1.title = 'Unit for Track A and Locale ru_RU'
            unit_1.labels = utils.list_to_text(
                [track_a_id, locale_ru_id])
            unit_2 = course.add_unit()
            unit_2.type = 'U'
            unit_2.now_available = True
            unit_2.title = 'Unit for Track B and Locale es_ES'
            unit_2.labels = utils.list_to_text(
                [track_b_id, locale_es_id])
            course.save()

        def _assert_course(
            locale, label_ids, is_unit_1_visible, is_unit_2_visible):
            self._set_prefs_locale(locale)
            self._set_labels_on_current_student(None, ids=label_ids)
            response = self.get('first/course')
            if is_unit_1_visible:
                self.assertIn(unit_1.title, response.body)
            else:
                self.assertNotIn(unit_1.title, response.body)
            if is_unit_2_visible:
                self.assertIn(unit_2.title, response.body)
            else:
                self.assertNotIn(unit_2.title, response.body)

        actions.logout()

        with actions.OverriddenEnvironment(
            {'course': {'now_available': True}}):
            actions.login(
                'test_track_and_locale_labels_dont_interfere@example.com')
            actions.register(
                self, 'test_track_and_locale_labels_dont_interfere',
                course='first')

        with actions.OverriddenEnvironment(
            {'course': {
                'now_available': True, 'can_student_change_locale': True}}):
            _assert_course(None, [], False, False)
            _assert_course('ru_RU', [], True, False)
            _assert_course('es_ES', [], False, True)

            _assert_course(None, [track_a_id], False, False)
            _assert_course('ru_RU', [track_a_id], True, False)
            _assert_course('ru_RU', [track_b_id], False, False)
            _assert_course('es_ES', [track_a_id], False, False)
            _assert_course('es_ES', [track_b_id], False, True)

            _assert_course(None, [locale_ru_id], True, False)
            _assert_course('ru_RU', [locale_ru_id], True, False)
            _assert_course('ru_RU', [locale_es_id], False, True)
            _assert_course('es_ES', [locale_ru_id], True, False)
            _assert_course('es_ES', [locale_es_id], False, True)

            _assert_course(None, [track_a_id, track_b_id], False, False)
            _assert_course('ru_RU', [track_a_id, track_b_id], True, False)
            _assert_course('es_ES', [track_a_id, track_b_id], False, True)

            _assert_course(
                None, [track_a_id, locale_ru_id], True, False)
            _assert_course('ru_RU', [track_a_id, locale_ru_id], True, False)
            _assert_course(
                'ru_RU', [track_a_id, locale_es_id], False, False)
            _assert_course('ru_RU', [track_b_id, locale_es_id], False, True)
            _assert_course('ru_RU', [track_b_id, locale_ru_id], False, False)

            _assert_course(
                None, [track_a_id, track_b_id, locale_ru_id], True, False)
            _assert_course(
                None, [track_a_id, track_b_id, locale_es_id], False, True)
            _assert_course(
                'ru_RU', [track_a_id, track_b_id, locale_ru_id], True, False)
            _assert_course(
                'ru_RU', [track_a_id, track_b_id, locale_es_id], False, True)
            _assert_course(
                'es_ES', [track_a_id, track_b_id, locale_ru_id], True, False)
            _assert_course(
                'es_ES', [track_a_id, track_b_id, locale_es_id], False, True)

        with actions.OverriddenEnvironment(
            {'course': {
                'now_available': True, 'can_student_change_locale': False}}):
            _assert_course(None, [], True, True)
            _assert_course('ru_RU', [], True, True)
            _assert_course('es_ES', [], True, True)

            _assert_course(None, [locale_ru_id], True, False)
            _assert_course('ru_RU', [locale_ru_id], True, False)
            _assert_course('ru_RU', [locale_es_id], False, True)
            _assert_course('es_ES', [locale_ru_id], True, False)
            _assert_course('es_ES', [locale_es_id], False, True)

            _assert_course(None, [track_a_id], True, False)
            _assert_course('ru_RU', [track_a_id], True, False)
            _assert_course('ru_RU', [track_b_id], False, True)
            _assert_course('es_ES', [track_a_id], True, False)
            _assert_course('es_ES', [track_b_id], False, True)

            _assert_course(None, [track_a_id, track_b_id], True, True)
            # the one below is not an error; the empty locale label set on
            # student is a match for unit labeled with any locale or none
            _assert_course('ru_RU', [track_a_id, track_b_id], True, True)
            _assert_course('es_ES', [track_a_id, track_b_id], True, True)

            _assert_course(None, [track_a_id, locale_ru_id], True, False)
            _assert_course('ru_RU', [track_a_id, locale_ru_id], True, False)
            _assert_course('ru_RU', [track_a_id, locale_es_id], False, False)
            _assert_course('ru_RU', [track_b_id, locale_es_id], False, True)
            _assert_course('ru_RU', [track_b_id, locale_ru_id], False, False)

            _assert_course(
                None, [track_a_id, track_b_id, locale_ru_id], True, False)
            _assert_course(
                None, [track_a_id, track_b_id, locale_es_id], False, True)
            _assert_course(
                'ru_RU', [track_a_id, track_b_id, locale_ru_id], True, False)
            _assert_course(
                'ru_RU', [track_a_id, track_b_id, locale_es_id], False, True)
            _assert_course(
                'es_ES', [track_a_id, track_b_id, locale_ru_id], True, False)
            _assert_course(
                'es_ES', [track_a_id, track_b_id, locale_es_id], False, True)

    def test_localized_course_with_images(self):
        self._import_sample_course()
        self._setup_locales(course='sample')

        with actions.OverriddenEnvironment(
            {'course': {'now_available': True}}):
            actions.logout()
            actions.login(
                'test_track_and_locale_labels_dont_interfere@example.com')
            actions.register(
                self, 'test_track_and_locale_labels_dont_interfere',
                course='sample')

        def _assert_image():
            response = self.get('sample/assets/img/Image2.2.1.png')
            self.assertEquals(200, response.status_int)
            self.assertEquals(215086, len(response.body))

        with actions.OverriddenEnvironment(
            {'course': {
                'now_available': True, 'can_student_change_locale': True}}):

            self._set_prefs_locale('en_US', course='sample')
            response = self.get('sample/unit?unit=14&lesson=18')
            self.assertIn(
                'You are a cosmetologist and business owner', response.body)
            self.assertIn('Announcements', response.body)
            _assert_image()

            self._set_prefs_locale('ru_RU', course='sample')
            response = self.get('sample/unit?unit=14&lesson=18')
            self.assertIn(
                'You are a cosmetologist and business owner', response.body)
            self.assertIn('Сообщения', response.body)
            _assert_image()

    def test_export_import(self):
        self._import_sample_course()
        self._setup_locales(course='sample')

        # export
        response = self.get('/sample/dashboard?action=i18n_download')
        self.assertEquals(response.status_int, 200)
        self.assertIn('locale/ru_RU/LC_MESSAGES/messages.po', response.body)
        self.assertIn(
            'Translation for ru_RU of Power Searching with Google',
            response.body)
        self.assertIn(
            'You are a cosmetologist and business owner', response.body)

        # import
        # TODO(psimakov): incomplete

    def test_course_with_one_common_unit_and_two_per_locale_units(self):
        # TODO(psimakov): incomplete
        pass
