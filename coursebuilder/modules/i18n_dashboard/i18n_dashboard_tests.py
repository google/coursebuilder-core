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
import collections
import cStringIO
import logging
import StringIO
import traceback
import unittest
import urllib
import zipfile

from babel.messages import pofile

import appengine_config

from common import crypto
from common import resource
from common import tags
from common import users
from common import utils
from common.utils import Namespace
from controllers import sites
from models import config
from models import courses
from models import resources_display
from models import models
from models import roles
from models import transforms
from modules.dashboard import dashboard
from modules.i18n_dashboard import i18n_dashboard
from modules.i18n_dashboard.i18n_dashboard import I18nProgressDAO
from modules.i18n_dashboard.i18n_dashboard import I18nProgressDTO
from modules.i18n_dashboard.i18n_dashboard import LazyTranslator
from modules.i18n_dashboard.i18n_dashboard import ResourceBundleDAO
from modules.i18n_dashboard.i18n_dashboard import ResourceBundleDTO
from modules.i18n_dashboard.i18n_dashboard import ResourceBundleKey
from modules.i18n_dashboard.i18n_dashboard import ResourceRow
from modules.i18n_dashboard.i18n_dashboard import TranslationConsoleRestHandler
from modules.i18n_dashboard.i18n_dashboard import TranslationUploadRestHandler
from modules.i18n_dashboard.i18n_dashboard import VERB_CHANGED
from modules.i18n_dashboard.i18n_dashboard import VERB_CURRENT
from modules.i18n_dashboard.i18n_dashboard import VERB_NEW
from modules.notifications import notifications
from tests.functional import actions

from google.appengine.api import memcache
from google.appengine.api import namespace_manager
from google.appengine.datastore import datastore_rpc


class ResourceBundleKeyTests(unittest.TestCase):

    def test_roundtrip_data(self):
        key1 = ResourceBundleKey(
            resources_display.ResourceAssessment.TYPE, '23', 'el')
        key2 = ResourceBundleKey.fromstring(str(key1))
        self.assertEquals(key1.locale, key2.locale)
        self.assertEquals(key1.resource_key.type, key2.resource_key.type)
        self.assertEquals(key1.resource_key.key, key2.resource_key.key)

    def test_from_resource_key(self):
        resource_key = resource.Key(
            resources_display.ResourceAssessment.TYPE, '23')
        key = ResourceBundleKey.from_resource_key(resource_key, 'el')
        self.assertEquals(resources_display.ResourceAssessment.TYPE,
                          key.resource_key.type)
        self.assertEquals('23', key.resource_key.key)
        self.assertEquals('el', key.locale)


class ResourceRowTests(unittest.TestCase):

    def setUp(self):
        super(ResourceRowTests, self).setUp()
        course = object()
        rsrc = object()
        self.type_str = resources_display.ResourceAssessment.TYPE
        self.key = '23'
        self.i18n_progress_dto = I18nProgressDTO(None, {})
        self.resource_row = ResourceRow(
            course, rsrc, self.type_str, self.key,
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


class TranslationContentsTests(actions.TestBase):
    MAX_ENTRIES_PER_FILE = 100

    def test_file_selection_all_in_one(self):
        contents = i18n_dashboard.TranslationContents(
            separate_files_by_type=False)
        resource_key_question = i18n_dashboard.ResourceBundleKey(
            resources_display.ResourceSAQuestion.TYPE, '123', 'de')
        resource_key_lesson_1 = i18n_dashboard.ResourceBundleKey(
            resources_display.ResourceLesson.TYPE, '234', 'de')
        resource_key_lesson_2 = i18n_dashboard.ResourceBundleKey(
            resources_display.ResourceLesson.TYPE, '345', 'de')

        messge_question = contents.get_message(resource_key_question, 'z')
        messge_lesson_1 = contents.get_message(resource_key_lesson_1, 'z')
        messge_lesson_2 = contents.get_message(resource_key_lesson_2, 'z')

        self.assertEqual(messge_question, messge_lesson_1)
        self.assertEqual(messge_question, messge_lesson_2)

    def test_file_selection_separate_files(self):
        contents = i18n_dashboard.TranslationContents(
            separate_files_by_type=True)
        resource_key_question = i18n_dashboard.ResourceBundleKey(
            resources_display.ResourceSAQuestion.TYPE, '123', 'de')
        resource_key_lesson_1 = i18n_dashboard.ResourceBundleKey(
            resources_display.ResourceLesson.TYPE, '234', 'de')
        resource_key_lesson_2 = i18n_dashboard.ResourceBundleKey(
            resources_display.ResourceLesson.TYPE, '345', 'de')

        messge_question = contents.get_message(resource_key_question, 'z')
        messge_lesson_1 = contents.get_message(resource_key_lesson_1, 'z')
        messge_lesson_2 = contents.get_message(resource_key_lesson_2, 'z')

        self.assertNotEqual(messge_question, messge_lesson_1)
        self.assertNotEqual(messge_question, messge_lesson_2)
        self.assertNotEqual(messge_lesson_1, messge_lesson_2)

    def _verify_encoding(self, original):
        encoded = (
            i18n_dashboard.TranslationMessage._encode_angle_brackets(
                original))
        decoded = (
            i18n_dashboard.TranslationMessage._decode_angle_brackets(
                encoded))
        self.assertEquals(original, decoded)
        if any([c in original for c in '[]<>\\']):
            self.assertNotEquals(original, encoded)
        else:
            self.assertEquals(original, encoded)

    def test_bracket_encoding(self):
        self._verify_encoding('')
        self._verify_encoding('A simple string')
        self._verify_encoding('<p>')
        self._verify_encoding('<i>italic</i>')
        self._verify_encoding('tag <i>not</i> at start or end of string')
        self._verify_encoding('[braces at beginning and ending of string]')
        self._verify_encoding('braces [within] string')
        self._verify_encoding('multiple [braces [ not necessarily []]] paired')
        self._verify_encoding('\\')
        self._verify_encoding('[\\]')
        self._verify_encoding(']\\[')
        self._verify_encoding('a[\\]b')
        self._verify_encoding('a]\\[b')
        self._verify_encoding('<\\>')
        self._verify_encoding('<\\\\>')
        self._verify_encoding('>\\<')
        self._verify_encoding('a<\\>b')
        self._verify_encoding('a>\\<b')
        self._verify_encoding('<<')
        self._verify_encoding('<<<<<<<<<<<<<<<<<<')
        self._verify_encoding('>>>>>>>>>>>>>>>>>>')
        self._verify_encoding('[[[[[[[[[[[[[[[[[[')
        self._verify_encoding(']]]]]]]]]]]]]]]]]]')
        self._verify_encoding('<<<not necessarily> balanced <>><<angles<')
        self._verify_encoding('mixed <b>[brackets] and </b>braces')
        self._verify_encoding('[[<\\<[]<><[<\\[>]\\\\[>>>\\>>>>>>>\\')

    def _add_entries_to_file(self, translation_contents):
        resource_bundle_keys = (
            i18n_dashboard.ResourceBundleKey('unit', 1, 'de'),
            i18n_dashboard.ResourceBundleKey('unit', 2, 'de'))
        for resource_bundle_key in resource_bundle_keys:
            for message_key in xrange(self.MAX_ENTRIES_PER_FILE + 1):
                translation_contents.get_message(
                    resource_bundle_key, 'foo_%4.4d' % message_key)

    def _get_file_data(self, translation_contents):
        return sorted([(f.file_name, f._get_num_translations())
                       for f in translation_contents.iterfiles()])

    def test_max_entries_per_file_not_separated_by_type(self):
        translation_contents = i18n_dashboard.TranslationContents(
            separate_files_by_type=False,
            max_entries_per_file=self.MAX_ENTRIES_PER_FILE)
        self._add_entries_to_file(translation_contents)
        self.assertEquals(
            [('messages_001.po', self.MAX_ENTRIES_PER_FILE),
             ('messages_002.po', 1)],
            self._get_file_data(translation_contents))

    def test_max_entries_per_file_separated_by_type(self):
        translation_contents = i18n_dashboard.TranslationContents(
            separate_files_by_type=True,
            max_entries_per_file=self.MAX_ENTRIES_PER_FILE)
        self._add_entries_to_file(translation_contents)
        self.assertEquals(
            [('unit_1_001.po', self.MAX_ENTRIES_PER_FILE),
             ('unit_1_002.po', 1),
             ('unit_2_001.po', self.MAX_ENTRIES_PER_FILE),
             ('unit_2_002.po', 1)],
            self._get_file_data(translation_contents))

    def test_no_max_entries_per_file_not_separated_by_type(self):
        translation_contents = i18n_dashboard.TranslationContents(
            separate_files_by_type=False,
            max_entries_per_file=None)
        self._add_entries_to_file(translation_contents)
        self.assertEquals(
            # Note: Not 202 files, but 101, because of same msg. keys!
            [('messages.po', self.MAX_ENTRIES_PER_FILE + 1)],
            self._get_file_data(translation_contents))

    def test_no_max_entries_per_file_separated_by_type(self):
        translation_contents = i18n_dashboard.TranslationContents(
            separate_files_by_type=True,
            max_entries_per_file=None)
        self._add_entries_to_file(translation_contents)
        self.assertEquals(
            [('unit_1.po', self.MAX_ENTRIES_PER_FILE + 1),
             ('unit_2.po', self.MAX_ENTRIES_PER_FILE + 1)],
            self._get_file_data(translation_contents))


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
        self.assessment = self.course.add_assessment()
        self.assessment.title = 'Post Assessment'
        self.unit.post_assessment = self.assessment.unit_id
        self.lesson = self.course.add_lesson(self.unit)
        self.lesson.title = 'Test Lesson'
        self.course.save()

        actions.login(self.ADMIN_EMAIL, is_admin=True)

    def tearDown(self):
        del sites.Registry.test_overrides[sites.GCB_COURSES_CONFIG.name]
        namespace_manager.set_namespace(self.old_namespace)
        super(I18nDashboardHandlerTests, self).tearDown()

    def test_page_data(self):
        response = self.get(self.URL)
        soup = self.parse_html_string_to_soup(response.body)
        tables = soup.select('.i18n-progress-table')

        expected_settings_rows = []
        expected_tables = [
            {
                'title': 'Settings',
                'rows': expected_settings_rows,
            },
            {
                'title': 'Create > Outline',
                'rows': [
                    'Unit 1 - Test Unit',
                    '1.1 Test Lesson',
                    'Post Assessment',
                ],
            },
            {
                'title': 'Questions',
                'rows': [],
            },
            {
                'title': 'Question Groups',
                'rows': [],
            },
            {
                'title': 'Skills',
                'rows': [],
            },
            {
                'title': 'Student Groups',
                'rows': [],
            },
            {
                'title': 'Announcements',
                'rows': [],
            },
            {
                'title': 'HTML Hooks',
                'rows': [
                    'base.after_body_tag_begins',
                    'base.after_main_content_ends',
                    'base.after_navbar_begins',
                    'base.after_top_content_ends',
                    'base.before_body_tag_ends',
                    'base.before_head_tag_ends',
                    'base.before_navbar_ends',
                ],
            },
        ]

        for rsrc, key in (i18n_dashboard.TranslatableResourceCourseSettings
                            .get_resources_and_keys(self.course)):
            resource_handler = resource.Registry.get(key.type)
            title = resource_handler.get_resource_title(rsrc)
            expected_settings_rows.append(title)

        for table, expected_table in zip(tables, expected_tables):
            self.assertEquals(table.select(
                'thead .title')[0].text.strip(), expected_table['title'])
            rows = table.select('tbody tr')
            self.assertEqual(len(rows), len(expected_table['rows']))
            for row, row_name in zip(rows, expected_table['rows']):
                self.assertEquals(row.select('.name')[0].text.strip(), row_name)

    def test_multiple_locales(self):
        extra_env = {
            'extra_locales': [
                {'locale': 'el', 'availability': 'unavailable'},
                {'locale': 'ru', 'availability': 'unavailable'},
            ]}
        with actions.OverriddenEnvironment(extra_env):
            soup = self.parse_html_string_to_soup(self.get(self.URL).body)
            table = soup.select('.i18n-progress-table')[0]
            columns = table.select('.language-header')
            expected_col_data = [
                'el',
                'ru',
            ]
            self.assertEquals(len(expected_col_data), len(columns))
            for index, expected in enumerate(expected_col_data):
                self.assertEquals(expected, columns[index].text)

    def test_is_translatable(self):
        soup = self.parse_html_string_to_soup(self.get(self.URL).body)
        rows = soup.select('tbody .not-translatable')
        self.assertEquals(0, len(rows))

        dto_key = resource.Key(resources_display.ResourceLesson.TYPE,
                               self.lesson.lesson_id)
        dto = I18nProgressDTO(str(dto_key), {})
        dto.is_translatable = False
        I18nProgressDAO.save(dto)

        soup = self.parse_html_string_to_soup(self.get(self.URL).body)
        rows = soup.select('tbody .not-translatable')
        self.assertEquals(1, len(rows))

    def test_progress(self):
        def assert_progress(class_name, row, index):
            td = row.select('.status')[index]
            self.assertIn(class_name, td.get('class'))

        lesson_row_selector = ('.i18n-progress-table > tbody > '
            'tr[data-resource-key="lesson:{}"]').format(self.lesson.lesson_id)

        extra_env = {
            'extra_locales': [
                {'locale': 'el', 'availability': 'unavailable'},
                {'locale': 'ru', 'availability': 'unavailable'},
            ]}
        with actions.OverriddenEnvironment(extra_env):
            soup = self.parse_html_string_to_soup(self.get(self.URL).body)
            lesson_row = soup.select(lesson_row_selector)[0]
            lesson_title = lesson_row.select('.name')[0].getText().strip()
            self.assertEquals('1.1 Test Lesson', lesson_title)
            assert_progress('not-started', lesson_row, 0)
            assert_progress('not-started', lesson_row, 1)

            dto_key = resource.Key(
                resources_display.ResourceLesson.TYPE, self.lesson.lesson_id)
            dto = I18nProgressDTO(str(dto_key), {})
            dto.set_progress('el', I18nProgressDTO.DONE)
            dto.set_progress('ru', I18nProgressDTO.IN_PROGRESS)
            I18nProgressDAO.save(dto)

            soup = self.parse_html_string_to_soup(self.get(self.URL).body)
            lesson_row = soup.select(lesson_row_selector)[0]

            assert_progress('done', lesson_row, 0)
            assert_progress('in-progress', lesson_row, 1)


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
        key = ResourceBundleKey(
            resources_display.ResourceUnit.TYPE, self.unit.unit_id, 'el')
        response = self._get_by_key(key)
        self.assertEquals(401, response['status'])

    def test_get_unit_content_with_no_existing_values(self):
        key = ResourceBundleKey(
            resources_display.ResourceUnit.TYPE, self.unit.unit_id, 'el')
        response = self._get_by_key(key)
        self.assertEquals(200, response['status'])

        payload = transforms.loads(response['payload'])
        self.assertEquals('en_US', payload['source_locale'])
        self.assertEquals('el', payload['target_locale'])

        sections = payload['sections']

        self.assertEquals(
            ['title', 'unit_header'],
            [s['name'] for s in sections])

        self.assertEquals(
            ['Title', 'Header'],
            [s['label'] for s in sections])

        expected_values = [
            ('title', 'string', 1, ''),
            ('unit_header', 'html', 2, '<p>a</p><p>b</p>')]

        for i, (name, type_str, data_size, source_value) in enumerate(
                expected_values):
            self._assert_section_values(
                sections[i], name, type_str, data_size, source_value)

        # confirm all the data is new
        for section in sections:
            for data in section['data']:
                self.assertEquals(VERB_NEW, data['verb'])

        header_data = sections[1]['data']
        for item in header_data:
            self.assertIsNone(item['old_source_value'])
            self.assertEquals('', item['target_value'])
            self.assertFalse(item['changed'])
        self.assertEquals('a', header_data[0]['source_value'])
        self.assertEquals('b', header_data[1]['source_value'])

    def test_get_unit_content_with_existing_values(self):
        key = ResourceBundleKey(
            resources_display.ResourceUnit.TYPE, self.unit.unit_id, 'el')
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
        self.assertEquals(2, len(sections))

        # Confirm there is a translation for the title
        title_section = sections[0]
        self.assertEquals('title', title_section['name'])
        self.assertEquals('Title', title_section['label'])
        self.assertEquals(1, len(title_section['data']))
        self.assertEquals(VERB_CURRENT, title_section['data'][0]['verb'])
        self.assertEquals('TEST UNIT', title_section['data'][0]['target_value'])

        # Confirm there is a translation for one of the two paragraphs
        header_section = sections[1]
        self.assertEquals('unit_header', header_section['name'])
        self.assertEquals('Header', header_section['label'])
        self.assertEquals(2, len(header_section['data']))
        self.assertEquals(VERB_CURRENT, header_section['data'][0]['verb'])
        self.assertEquals('a', header_section['data'][0]['source_value'])
        self.assertEquals('a', header_section['data'][0]['old_source_value'])
        self.assertEquals('A', header_section['data'][0]['target_value'])
        self.assertEquals(VERB_NEW, header_section['data'][1]['verb'])

    def test_get_unit_content_with_changed_values(self):
        key = ResourceBundleKey(
            resources_display.ResourceUnit.TYPE, self.unit.unit_id, 'el')
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
        self.assertEquals(2, len(sections))

        # Confirm there is a translation for the title
        title_section = sections[0]
        self.assertEquals('title', title_section['name'])
        self.assertEquals('Title', title_section['label'])
        self.assertEquals(1, len(title_section['data']))
        self.assertEquals(VERB_CHANGED, title_section['data'][0]['verb'])
        self.assertEquals(
            'OLD TEST UNIT', title_section['data'][0]['target_value'])

        # Confirm there is a translation for one of the two paragraphs
        header_section = sections[1]
        self.assertEquals('unit_header', header_section['name'])
        self.assertEquals('Header', header_section['label'])
        self.assertEquals(2, len(header_section['data']))
        self.assertEquals(VERB_CHANGED, header_section['data'][0]['verb'])
        self.assertEquals('a', header_section['data'][0]['source_value'])
        self.assertEquals('aa', header_section['data'][0]['old_source_value'])
        self.assertEquals('AA', header_section['data'][0]['target_value'])
        self.assertEquals(VERB_NEW, header_section['data'][1]['verb'])

    def test_core_tags_handle_none_handler(self):
        for _, tag_cls in tags.Registry.get_all_tags().items():
            self.assertTrue(tag_cls().get_schema(None))

    def test_get_unit_content_with_custom_tag(self):
        unit = self.course.add_unit()
        unit.title = 'Test Unit with Tag'
        unit.unit_header = (
            'text'
            '<gcb-youtube videoid="Kdg2drcUjYI" instanceid="c4CLTDvttJEu">'
            '</gcb-youtube>')
        self.course.save()

        key = ResourceBundleKey(
            resources_display.ResourceUnit.TYPE, unit.unit_id, 'el')
        response = self._get_by_key(key)
        payload = transforms.loads(response['payload'])
        data = payload['sections'][1]['data']
        self.assertEquals(1, len(data))
        self.assertEquals(
            'text<gcb-youtube#1 videoid="Kdg2drcUjYI" />',
            data[0]['source_value'])

    def test_get_unit_content_with_custom_tag_with_body(self):
        unit = self.course.add_unit()
        unit.title = 'Test Unit with Tag'
        unit.unit_header = '<gcb-markdown>*hello*</gcb-markdown>'
        self.course.save()

        key = ResourceBundleKey(
            resources_display.ResourceUnit.TYPE, unit.unit_id, 'el')
        response = self._get_by_key(key)
        payload = transforms.loads(response['payload'])
        data = payload['sections'][1]['data']
        self.assertEquals(1, len(data))
        self.assertEquals(
            '<gcb-markdown#1>*hello*</gcb-markdown#1>', data[0]['source_value'])

    def test_defaults_to_known_translations(self):
        unit = self.course.add_unit()

        # Make the unit title be a string which is part of CB's i18n data
        unit.title = 'Registration'
        self.course.save()

        key = ResourceBundleKey(
            resources_display.ResourceUnit.TYPE, unit.unit_id, 'el')
        response = self._get_by_key(key)
        payload = transforms.loads(response['payload'])
        data = payload['sections'][0]['data']
        self.assertEqual(VERB_CHANGED, data[0]['verb'])
        self.assertEqual(u'Εγγραφή', data[0]['target_value'])


class TranslationConsoleValidationTests(actions.TestBase):
    ADMIN_EMAIL = 'admin@foo.com'
    COURSE_NAME = 'i18n_course'
    URL = 'rest/modules/i18n_dashboard/translation_console'

    INVALID = LazyTranslator.INVALID_TRANSLATION
    VALID = LazyTranslator.VALID_TRANSLATION

    def setUp(self):
        super(TranslationConsoleValidationTests, self).setUp()

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

        self.key = ResourceBundleKey(
            resources_display.ResourceUnit.TYPE, self.unit.unit_id, 'el')
        self.validation_payload = {
            'key': str(self.key),
            'title': 'Unit 1 - Test Unit',
            'source_locale': 'en_US',
            'target_locale': 'el',
            'sections': [
                {
                    'name': 'title',
                    'label': 'Title',
                    'type': 'string',
                    'source_value': '',
                    'data': [
                        {
                            'source_value': 'Test Unit',
                            'target_value': 'TEST UNIT',
                            'verb': 1,  # verb NEW
                            'old_source_value': '',
                            'changed': True
                        }
                    ]
                },
                {
                    'name': 'unit_header',
                    'label': 'Unit Header',
                    'type': 'html',
                    'source_value': '<p>a</p><p>b</p>',
                    'data': [
                        {
                            'source_value': 'a',
                            'target_value': 'A',
                            'verb': 1,  # verb NEW
                            'old_source_value': 'a',
                            'changed': True
                        },
                        {
                            'source_value': 'b',
                            'target_value': 'B',
                            'verb': 1,  # verb NEW
                            'old_source_value': 'b',
                            'changed': True
                        },
                    ]
                },
            ]}

        self.resource_bundle_dict = {
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
                    {'source_value': 'a', 'target_value': 'B'}]
            }
        }

    def tearDown(self):
        del sites.Registry.test_overrides[sites.GCB_COURSES_CONFIG.name]
        namespace_manager.set_namespace(self.old_namespace)
        super(TranslationConsoleValidationTests, self).tearDown()

    def _validate(self):
        request_dict = {
            'key': str(self.key),
            'xsrf_token': crypto.XsrfTokenManager.create_xsrf_token(
                'translation-console'),
                  'payload': transforms.dumps(self.validation_payload),
                  'validate': True}

        response = self.put(
            self.URL, {'request': transforms.dumps(request_dict)})
        response = transforms.loads(response.body)
        self.assertEquals(200, response['status'])
        payload = transforms.loads(response['payload'])
        expected_keys = {
            section['name'] for section in self.validation_payload['sections']}
        self.assertEquals(expected_keys, set(payload.keys()))

        return payload

    def test_valid_content(self):
        payload = self._validate()
        self.assertEquals(self.VALID, payload['title']['status'])
        self.assertEquals('', payload['title']['errm'])
        self.assertEquals(self.VALID, payload['unit_header']['status'])
        self.assertEquals('', payload['unit_header']['errm'])

    def test_invalid_content(self):
        self.validation_payload[
            'sections'][1]['data'][0]['target_value'] = '<img#1/>'
        payload = self._validate()
        self.assertEquals(self.VALID, payload['title']['status'])
        self.assertEquals('', payload['title']['errm'])
        self.assertEquals(self.INVALID, payload['unit_header']['status'])
        self.assertEquals(
            'Error in chunk 1. Unexpected tag: <img#1>.',
            payload['unit_header']['errm'])

    def test_with_bundle(self):
        dto = ResourceBundleDTO(str(self.key), self.resource_bundle_dict)
        ResourceBundleDAO.save(dto)

        payload = self._validate()
        self.assertEquals(self.VALID, payload['title']['status'])
        self.assertEquals('', payload['title']['errm'])
        self.assertEquals(self.VALID, payload['unit_header']['status'])
        self.assertEquals('', payload['unit_header']['errm'])

    def test_with_bundle_with_extra_fields(self):
        self.resource_bundle_dict['description'] = {
            'type': 'string',
            'source_value': '',
            'data': [
                {'source_value': 'descr', 'target_value': 'DESCR'}]
        }
        dto = ResourceBundleDTO(str(self.key), self.resource_bundle_dict)
        ResourceBundleDAO.save(dto)

        payload = self._validate()
        self.assertEquals(self.VALID, payload['title']['status'])
        self.assertEquals('', payload['title']['errm'])
        self.assertEquals(self.VALID, payload['unit_header']['status'])
        self.assertEquals('', payload['unit_header']['errm'])

    def test_untranslated_section(self):
        # Add a section to the unit which has no translation in the bundle
        self.unit.unit_footer = 'footer'
        self.course.save()

        self.validation_payload['sections'].append(
            {
                'name': 'unit_footer',
                'label': 'Unit Footer',
                'type': 'html',
                'source_value': 'footer',
                'data': [
                    {
                        'source_value': 'footer',
                        'target_value': '',
                        'verb': 1,  # verb NEW
                        'old_source_value': None,
                        'changed': False
                    }
                ]
            })

        payload = self._validate()
        footer_data = payload['unit_footer']
        self.assertEqual(
            LazyTranslator.NOT_STARTED_TRANSLATION, footer_data['status'])
        self.assertEqual('No translation saved yet', footer_data['errm'])


class I18nProgressDeferredUpdaterTests(actions.TestBase):
    ADMIN_EMAIL = 'admin@foo.com'
    COURSE_NAME = 'i18n_course'
    COURSE_TITLE = 'I18N Course'

    def setUp(self):
        super(I18nProgressDeferredUpdaterTests, self).setUp()

        self.base = '/' + self.COURSE_NAME
        self.app_context = actions.simple_add_course(
            self.COURSE_NAME, self.ADMIN_EMAIL, self.COURSE_TITLE)
        self.old_namespace = namespace_manager.get_namespace()
        namespace_manager.set_namespace('ns_%s' % self.COURSE_NAME)

        self.course = courses.Course(None, self.app_context)
        self.unit = self.course.add_unit()
        self.unit.title = 'Test Unit'
        self.unit.unit_header = '<p>a</p><p>b</p>'
        self.unit.availability = courses.AVAILABILITY_AVAILABLE

        self.lesson = self.course.add_lesson(self.unit)
        self.lesson.title = 'Test Lesson'
        self.lesson.objectives = '<p>c</p><p>d</p>'
        self.lesson.availability = courses.AVAILABILITY_AVAILABLE

        self.course.save()

        courses.Course.ENVIRON_TEST_OVERRIDES = {
            'extra_locales': [
                {'locale': 'el', 'availability': 'available'},
                {'locale': 'ru', 'availability': 'available'}]
        }

        actions.login(self.ADMIN_EMAIL)

    def tearDown(self):
        del sites.Registry.test_overrides[sites.GCB_COURSES_CONFIG.name]
        namespace_manager.set_namespace(self.old_namespace)
        courses.Course.ENVIRON_TEST_OVERRIDES = {}
        super(I18nProgressDeferredUpdaterTests, self).tearDown()

    def _put_payload(self, url, xsrf_name, key, payload):
        request_dict = {
            'key': key,
            'xsrf_token': (
                crypto.XsrfTokenManager.create_xsrf_token(xsrf_name)),
            'payload': transforms.dumps(payload)
        }
        response = transforms.loads(self.put(
            url, {'request': transforms.dumps(request_dict)}).body)
        self.assertEquals(200, response['status'])
        self.assertEquals('Saved.', response['message'])
        return response

    def _assert_progress(self, key, el_progress=None, ru_progress=None):
        progress_dto = I18nProgressDAO.load(str(key))
        self.assertIsNotNone(progress_dto)
        self.assertEquals(el_progress, progress_dto.get_progress('el'))
        self.assertEquals(ru_progress, progress_dto.get_progress('ru'))

    def test_on_lesson_changed(self):
        unit = self.course.add_unit()
        unit.title = 'Test Unit'

        lesson = self.course.add_lesson(unit)
        lesson.title = 'Test Lesson'
        lesson.objectives = '<p>a</p><p>b</p>'
        lesson.availability = courses.AVAILABILITY_AVAILABLE

        self.course.save()

        lesson_bundle = {
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
                'source_value': '<p>a</p><p>b</p>',
                'data': [
                    {'source_value': 'a', 'target_value': 'A'},
                    {'source_value': 'b', 'target_value': 'B'}]
            }
        }

        lesson_key = resource.Key(
            resources_display.ResourceLesson.TYPE, lesson.lesson_id)

        lesson_key_el = ResourceBundleKey.from_resource_key(lesson_key, 'el')
        ResourceBundleDAO.save(
            ResourceBundleDTO(str(lesson_key_el), lesson_bundle))

        progress_dto = I18nProgressDAO.load(str(lesson_key))
        self.assertIsNone(progress_dto)

        edit_lesson_payload = {
            'key': lesson.lesson_id,
            'unit_id': [{'label': '', 'value': unit.unit_id, 'selected': True}],
            'title': 'Test Lesson',
            'objectives': '<p>a</p><p>b</p>',
            'auto_index': True,
            'is_draft': True,
            'video': '',
            'scored': 'not_scored',
            'notes': '',
            'activity_title': '',
            'activity_listed': True,
            'activity': '',
            'manual_progress': False,
        }
        self._put_payload(
            'rest/course/lesson', 'lesson-edit', lesson.lesson_id,
            edit_lesson_payload)
        self.execute_all_deferred_tasks()
        self._assert_progress(
            lesson_key,
            el_progress=I18nProgressDTO.DONE,
            ru_progress=I18nProgressDTO.NOT_STARTED)

        edit_lesson_payload['title'] = 'New Title'
        self._put_payload(
            'rest/course/lesson', 'lesson-edit', lesson.lesson_id,
            edit_lesson_payload)
        self.execute_all_deferred_tasks()
        self._assert_progress(
            lesson_key,
            el_progress=I18nProgressDTO.IN_PROGRESS,
            ru_progress=I18nProgressDTO.NOT_STARTED)

    def test_on_unit_changed(self):
        unit = self.course.add_unit()
        unit.title = 'Test Unit'
        self.course.save()

        unit_bundle = {
            'title': {
                'type': 'string',
                'source_value': '',
                'data': [
                    {'source_value': 'Test Unit', 'target_value': 'TEST UNIT'}]
            }
        }

        unit_key = resource.Key(
            resources_display.ResourceUnit.TYPE, unit.unit_id)

        unit_key_el = ResourceBundleKey.from_resource_key(unit_key, 'el')
        ResourceBundleDAO.save(
            ResourceBundleDTO(str(unit_key_el), unit_bundle))

        progress_dto = I18nProgressDAO.load(str(unit_key))
        self.assertIsNone(progress_dto)

        edit_unit_payload = {
            'key': unit.unit_id,
            'type': 'Unit',
            'title': 'Test Unit',
            'description': '',
            'label_groups': [],
            'is_draft': True,
            'unit_header': '',
            'pre_assessment': -1,
            'post_assessment': -1,
            'show_contents_on_one_page': False,
            'manual_progress': False,
            'unit_footer': ''
        }
        self._put_payload(
            'rest/course/unit', 'put-unit', unit.unit_id, edit_unit_payload)
        self.execute_all_deferred_tasks()
        self._assert_progress(
            unit_key,
            el_progress=I18nProgressDTO.DONE,
            ru_progress=I18nProgressDTO.NOT_STARTED)

        edit_unit_payload['title'] = 'New Title'
        self._put_payload(
            'rest/course/unit', 'put-unit', unit.unit_id, edit_unit_payload)
        self.execute_all_deferred_tasks()
        self._assert_progress(
            unit_key,
            el_progress=I18nProgressDTO.IN_PROGRESS,
            ru_progress=I18nProgressDTO.NOT_STARTED)

    def test_on_question_changed(self):
        qu_payload = {
            'version': '1.5',
            'question': 'What is a question?',
            'description': 'Test Question',
            'hint': '',
            'defaultFeedback': '',
            'rows': '1',
            'columns': '100',
            'graders': [{
                'score': '1.0',
                'matcher': 'case_insensitive',
                'response': 'yes',
                'feedback': ''}]
        }
        response = self._put_payload(
            'rest/question/sa', 'sa-question-edit', '', qu_payload)
        key = transforms.loads(response['payload'])['key']
        qu_key = resource.Key(resources_display.ResourceSAQuestion.TYPE, key)

        qu_bundle = {
            'question': {
                'type': 'html',
                'source_value': 'What is a question?',
                'data': [{
                    'source_value': 'What is a question?',
                    'target_value': 'WHAT IS A QUESTION?'}]
            },
            'description': {
                'type': 'string',
                'source_value': '',
                'data': [{
                    'source_value': 'Test Question',
                    'target_value': 'TEST QUESTION'}]
            },
            'graders:[0]:response': {
                'type': 'string',
                'source_value': '',
                'data': [{
                    'source_value': 'yes',
                    'target_value': 'YES'}]
            }
        }
        qu_key_el = ResourceBundleKey.from_resource_key(qu_key, 'el')
        ResourceBundleDAO.save(
            ResourceBundleDTO(str(qu_key_el), qu_bundle))

        self.execute_all_deferred_tasks()
        self._assert_progress(
            qu_key,
            el_progress=I18nProgressDTO.DONE,
            ru_progress=I18nProgressDTO.NOT_STARTED)

        qu_payload['description'] = 'New Description'
        qu_payload['key'] = key
        response = self._put_payload(
            'rest/question/sa', 'sa-question-edit', key, qu_payload)

        self.execute_all_deferred_tasks()
        self._assert_progress(
            qu_key,
            el_progress=I18nProgressDTO.IN_PROGRESS,
            ru_progress=I18nProgressDTO.NOT_STARTED)

    def test_on_question_group_changed(self):
        qgp_payload = {
            'version': '1.5',
            'description': 'Test Question Group',
            'introduction': 'Test introduction',
            'items': []
        }
        response = self._put_payload(
            'rest/question_group', 'question-group-edit', '', qgp_payload)
        key = transforms.loads(response['payload'])['key']
        qgp_key = resource.Key(
            resources_display.ResourceQuestionGroup.TYPE, key)

        qgp_bundle = {
            'description': {
                'type': 'string',
                'source_value': '',
                'data': [{
                    'source_value': 'Test Question Group',
                    'target_value': 'TEST QUESTION GROUP'}]
            },
            'introduction': {
                'type': 'html',
                'source_value': 'Test introduction',
                'data': [{
                    'source_value': 'Test introduction',
                    'target_value': 'TEST INTRODUCTION'}]
            }
        }
        qgp_key_el = ResourceBundleKey.from_resource_key(qgp_key, 'el')
        ResourceBundleDAO.save(
            ResourceBundleDTO(str(qgp_key_el), qgp_bundle))

        self.execute_all_deferred_tasks()
        self._assert_progress(
            qgp_key,
            el_progress=I18nProgressDTO.DONE,
            ru_progress=I18nProgressDTO.NOT_STARTED)

        qgp_payload['description'] = 'New Description'
        qgp_payload['key'] = key
        response = self._put_payload(
            'rest/question_group', 'question-group-edit', key, qgp_payload)

        self.execute_all_deferred_tasks()
        self._assert_progress(
            qgp_key,
            el_progress=I18nProgressDTO.IN_PROGRESS,
            ru_progress=I18nProgressDTO.NOT_STARTED)

    def test_on_course_settings_changed(self):
        homepage_payload = {
            'homepage': {
                'base:show_gplus_button': True,
                'base:nav_header': 'Search Education',
                'course:title': 'My New Course',
                'course:blurb': 'Awesome course',
                'course:instructor_details': '',
                'course:main_image:url': '',
                'course:main_image:alt_text': '',
                'base:privacy_terms_url': 'Privacy Policy'}
        }

        homepage_bundle = {
            'course:title': {
                'type': 'string',
                'source_value': '',
                'data': [{
                    'source_value': 'My New Course',
                    'target_value': 'MY NEW COURSE'}]
            },
            'course:blurb': {
                'type': 'html',
                'source_value': 'Awesome course',
                'data': [{
                    'source_value': 'Awesome course',
                    'target_value': 'AWESOME COURSE'}]
            },
            'base:nav_header': {
                'type': 'string',
                'source_value': '',
                'data': [{
                    'source_value': 'Search Education',
                    'target_value': 'SEARCH EDUCATION'}]
            },
            'base:privacy_terms_url': {
                'type': 'string',
                'source_value': '',
                'data': [{
                    'source_value': 'Privacy Policy',
                    'target_value': 'PRIVACY_POLICY'}]
            },
            'institution:logo:url': {
                'type': 'string',
                'source_value': 'assets/img/your_logo_here.png',
                'data': [{
                    'source_value': 'assets/img/your_logo_here.png',
                    'target_value': 'assets/img/your_greek_logo_here.png',
                }],
            },
        }
        homepage_key = resource.Key(
            resources_display.ResourceCourseSettings.TYPE, 'homepage')
        homepage_key_el = ResourceBundleKey.from_resource_key(
            homepage_key, 'el')
        ResourceBundleDAO.save(
            ResourceBundleDTO(str(homepage_key_el), homepage_bundle))

        self._put_payload(
            'rest/course/settings', 'basic-course-settings-put',
            '/course.yaml', homepage_payload)
        self.execute_all_deferred_tasks()
        self._assert_progress(
            homepage_key,
            el_progress=I18nProgressDTO.DONE,
            ru_progress=I18nProgressDTO.NOT_STARTED)

        homepage_payload['homepage']['course:title'] = 'New Title'
        self._put_payload(
            'rest/course/settings', 'basic-course-settings-put',
            '/course.yaml', homepage_payload)
        self.execute_all_deferred_tasks()
        self._assert_progress(
            homepage_key,
            el_progress=I18nProgressDTO.IN_PROGRESS,
            ru_progress=I18nProgressDTO.NOT_STARTED)


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
        key = ResourceBundleKey(
            resources_display.ResourceLesson.TYPE, '23', 'el')
        lazy_translator = LazyTranslator(
            self.app_context, key, source_value, translation_dict)
        self.assertEquals(
            '{"lt": "HELLO"}', transforms.dumps({'lt': lazy_translator}))

    def test_lazy_translator_supports_addition(self):
        source_value = 'hello, '
        translation_dict = {
            'type': 'string',
            'data': [
                {'source_value': 'hello, ', 'target_value': 'HELLO, '}]}
        key = ResourceBundleKey(
            resources_display.ResourceLesson.TYPE, '23', 'el')
        lazy_translator = LazyTranslator(
            self.app_context, key, source_value, translation_dict)
        self.assertEquals('HELLO, world', lazy_translator + 'world')

    def test_lazy_translator_supports_interpolation(self):
        source_value = 'hello, %s'
        translation_dict = {
            'type': 'string',
            'data': [
                {'source_value': 'hello, %s', 'target_value': 'HELLO, %s'}]}
        key = ResourceBundleKey(
            resources_display.ResourceLesson.TYPE, '23', 'el')
        lazy_translator = LazyTranslator(
            self.app_context, key, source_value, translation_dict)
        self.assertEquals('HELLO, world', lazy_translator % 'world')

    def test_lazy_translator_supports_upper_and_lower(self):
        source_value = 'Hello'
        translation_dict = {
            'type': 'string',
            'data': [
                {'source_value': 'Hello', 'target_value': 'Bonjour'}]}
        key = ResourceBundleKey(
            resources_display.ResourceLesson.TYPE, '23', 'el')
        lazy_translator = LazyTranslator(
            self.app_context, key, source_value, translation_dict)
        self.assertEquals('BONJOUR', lazy_translator.upper())
        self.assertEquals('bonjour', lazy_translator.lower())

    def test_lazy_translator_records_status(self):
        source_value = 'hello'
        translation_dict = {
            'type': 'html',
            'source_value': 'hello',
            'data': [
                {'source_value': 'hello', 'target_value': 'HELLO'}]}
        key = ResourceBundleKey(
            resources_display.ResourceLesson.TYPE, '23', 'el')

        lazy_translator = LazyTranslator(
            self.app_context, key, source_value, translation_dict)
        self.assertEquals(
            LazyTranslator.NOT_STARTED_TRANSLATION, lazy_translator.status)

        str(lazy_translator)
        self.assertEquals(
            LazyTranslator.VALID_TRANSLATION, lazy_translator.status)

        # Monkey patch get_template_environ because the app_context is not
        # fully setn up
        def mock_get_template_environ(unused_locale, dirs):
            return self.app_context.fs.get_jinja_environ(dirs)
        self.app_context.get_template_environ = mock_get_template_environ

        lazy_translator = LazyTranslator(
            self.app_context, key, 'changed', translation_dict)
        str(lazy_translator)
        self.assertEquals(
            LazyTranslator.INVALID_TRANSLATION, lazy_translator.status)
        self.assertEquals(
            'The content has changed and 1 part '
            'of the translation is out of date.',
            lazy_translator.errm)


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
        self.unit.availability = courses.AVAILABILITY_AVAILABLE

        self.lesson = self.course.add_lesson(self.unit)
        self.lesson.title = 'Test Lesson'
        self.lesson.objectives = '<p>c</p><p>d</p>'
        self.lesson.availability = courses.AVAILABILITY_AVAILABLE

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
            resources_display.ResourceUnit.TYPE, self.unit.unit_id, 'el')
        self.lesson_key_el = ResourceBundleKey(
            resources_display.ResourceLesson.TYPE, self.lesson.lesson_id, 'el')

        actions.login(self.ADMIN_EMAIL, is_admin=True)
        prefs = models.StudentPreferencesDAO.load_or_default()
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

    def test_i18n_course_element_title(self):
        self._store_resource_bundle()
        lesson_key = resource.Key(resources_display.ResourceLesson.TYPE,
                                  self.lesson.lesson_id)
        unit_key = resource.Key(resources_display.ResourceUnit.TYPE,
                                self.unit.unit_id)

        # Verify that one-off title translation also works.
        try:
            sites.set_path_info('/' + self.COURSE_NAME)
            ctx = sites.get_course_for_current_request()
            save_locale = ctx.get_current_locale()

            # Untranslated
            courses.Course.clear_current()
            ctx.set_current_locale(None)
            resource_class = i18n_dashboard.TranslatableResourceCourseComponents
            i18n_title = str(resource_class.get_i18n_title(lesson_key))
            self.assertEquals('Test Lesson', i18n_title)
            i18n_title = str(resource_class.get_i18n_title(unit_key))
            self.assertEquals('Test Unit', i18n_title)

            # Translated
            courses.Course.clear_current()
            ctx.set_current_locale('el')
            i18n_title = str(resource_class.get_i18n_title(lesson_key))
            self.assertEquals('TEST LESSON', i18n_title)
            i18n_title = str(resource_class.get_i18n_title(unit_key))
            self.assertEquals('TEST UNIT', i18n_title)
        finally:
            ctx.set_current_locale(save_locale)
            sites.unset_path_info()

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
            resources_display.ResourceLink.TYPE, link.unit_id, 'el')
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
            resources_display.ResourceAssessment.TYPE, assessment.unit_id, 'el')
        ResourceBundleDAO.save(
            ResourceBundleDTO(str(assessment_key), assessment_bundle))

        page_html = self.get('assessment?name=%s' % assessment.unit_id).body
        self.assertIn('TEST ASSESSMENT', page_html)
        self.assertIn('<p>A</p><p>B</p>', page_html)

    def test_bad_translations_are_flagged_for_admin(self):
        self.unit_bundle['unit_header']['data'][1] = {
            'source_value': 'b', 'target_value': '<b#1>b</b#1>'}
        self._store_resource_bundle()

        dom = self.parse_html_string(self.get('unit?unit=1').body)

        self.assertEquals(
            'Error in chunk 2. Unexpected tag: <b#1>.',
            dom.find('.//div[@class="gcb-translation-error-body"]/p[1]').text)

        edit_link = dom.find(
            './/div[@class="gcb-translation-error-body"]/p[2]a')
        self.assertEquals('Edit the resource', edit_link.text)
        self.assertEquals(
            'dashboard?action=i18_console&key=unit%%3A%s%%3Ael' % (
                self.unit.unit_id),
            edit_link.attrib['href'])

    def test_bad_translations_are_not_flagged_for_student(self):
        self.unit_bundle['unit_header']['data'][1] = {
            'source_value': 'b', 'target_value': '<b#1>b</b#1>'}
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

    def test_partial_translations(self):

        def update_lesson_objectives(objectives):
            self.lesson = self.course.find_lesson_by_id(
                self.unit.unit_id, self.lesson.lesson_id)
            self.lesson.objectives = objectives
            self.course.save()

        def assert_p_tags(dom, expected_content_list, expected_error_msg):
            # Ensure that the lesson body is a list of <p>..</p> tags with the
            # expected content. All should be inside an error warning div.
            p_tag_content_list = [
                p_tag.text for p_tag in dom.findall(
                 './/div[@class="gcb-lesson-content"]'
                 '//div[@class="gcb-translation-error-alt"]/p')]
            self.assertEquals(expected_content_list, p_tag_content_list)

            error_msg = dom.find(
                 './/div[@class="gcb-lesson-content"]'
                 '//div[@class="gcb-translation-error-body"]/p[1]')
            self.assertIn('content has changed', error_msg.text)
            if expected_error_msg:
                self.assertIn(expected_error_msg, error_msg.text)

        self._store_resource_bundle()

        # Delete first para from lesson
        update_lesson_objectives('<p>d</p>')
        dom = self.parse_html_string(self.get('unit?unit=1').body)
        assert_p_tags(
            dom, ['C', 'D'], '1 part of the translation is out of date')

        # Delete second para from lesson
        update_lesson_objectives('<p>c</p>')
        dom = self.parse_html_string(self.get('unit?unit=1').body)
        assert_p_tags(
            dom, ['C', 'D'], '1 part of the translation is out of date')

        # Add para to lesson
        update_lesson_objectives('<p>c</p><p>d</p><p>e</p>')
        dom = self.parse_html_string(self.get('unit?unit=1').body)
        assert_p_tags(
            dom, ['C', 'D'], '1 part of the translation is out of date')

        # Change para in lesson
        update_lesson_objectives('<p>cc</p><p>d</p>')
        dom = self.parse_html_string(self.get('unit?unit=1').body)
        assert_p_tags(
            dom, ['C', 'D'], '1 part of the translation is out of date')

        # Change two paras
        update_lesson_objectives('<p>cc</p><p>dd</p>')
        dom = self.parse_html_string(self.get('unit?unit=1').body)
        assert_p_tags(
            dom, ['C', 'D'], '2 parts of the translation are out of date')

        # A student should see the partial translation but no error message
        actions.logout()
        actions.login(self.STUDENT_EMAIL, is_admin=False)
        prefs = models.StudentPreferencesDAO.load_or_default()
        prefs.locale = 'el'
        models.StudentPreferencesDAO.save(prefs)

        dom = self.parse_html_string(self.get('unit?unit=1').body)
        self.assertEquals(
            ['C', 'D'],
            [p_tag.text for p_tag in dom.findall(
                './/div[@class="gcb-lesson-content"]/p')])
        self.assertIsNone(dom.find('.//div[@class="gcb-translation-error"]'))

    def test_custom_tag_expanded_without_analytics(self):
        with actions.OverriddenEnvironment(
                {'course': {'can_record_student_events': False}}):

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
                    'data': [{
                        'source_value': 'Tag Unit',
                        'target_value': 'TAG UNIT'}]
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
                resources_display.ResourceUnit.TYPE, unit.unit_id, 'el')
            ResourceBundleDAO.save(
                ResourceBundleDTO(str(unit_key_el), unit_bundle))

            page_html = self.get('unit?unit=%s' % unit.unit_id).body
            dom = self.parse_html_string(page_html)
            main = dom.find('.//div[@id="gcb-main-article"]/div[2]')
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
            resources_display.ResourceUnit.TYPE, unit.unit_id, 'el')
        ResourceBundleDAO.save(
            ResourceBundleDTO(str(unit_key_el), unit_bundle))

        page_html = self.get('unit?unit=%s' % unit.unit_id).body
        dom = self.parse_html_string(page_html)
        main = dom.find('.//div[@id="gcb-main-article"]/div[2]')
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
            resources_display.ResourceMCQuestion.TYPE, qu_id, 'el')
        ResourceBundleDAO.save(
            ResourceBundleDTO(str(key_el), qu_bundle))

        return qu_id

    def test_questions_are_translated(self):
        # Create an assessment and add the question to the content
        assessment = self.course.add_assessment()
        assessment.title = 'Test Assessment'
        assessment.html_content = """
            <question quid="%s" weight="1" instanceid="test_question">%s
        """ % (self._add_question(), '</question>')
        self.course.save()

        page_html = self.get('assessment?name=%s' % assessment.unit_id).body
        self.assertIn('QUESTION TEXT', page_html)
        self.assertIn('CHOICE 1', page_html)
        self.assertIn('CHOICE 2', page_html)

    def test_course_settings_i18n_title(self):
        # Course settings don't have student-visible titles, so the 'title' is
        # nearly a no-op.  Test here is not for functionality, but rather just
        # to ensure that when course settings are handled polymorphically,
        # nothing explodes.
        found_any = False
        for rsrc, key in (i18n_dashboard.TranslatableResourceCourseSettings
                          .get_resources_and_keys(self.course)):
            title = (i18n_dashboard.TranslatableResourceCourseSettings
                     .get_i18n_title(key))
            self.assertEquals(title, key.key)
            found_any = True
        self.assertTrue(found_any)

    def test_course_settings_html_hooks(self):
        # HTML hooks don't have student-visible titles, so the 'title' is
        # nearly a no-op.  Test here is not for functionality, but rather just
        # to ensure that when course settings are handled polymorphically,
        # nothing explodes.
        found_any = False
        for rsrc, key in (i18n_dashboard.TranslatableResourceHtmlHooks
                          .get_resources_and_keys(self.course)):
            title = (i18n_dashboard.TranslatableResourceHtmlHooks.
                     get_i18n_title(key))
            self.assertEquals(title, key.key)
            found_any = True
        self.assertTrue(found_any)

    def test_question_i18n_title(self):
        qu_id = self._add_question()
        key = resource.Key(resources_display.ResourceMCQuestion.TYPE, qu_id)

        try:
            sites.set_path_info('/' + self.COURSE_NAME)
            ctx = sites.get_course_for_current_request()
            save_locale = ctx.get_current_locale()

            # Untranslated
            ctx.set_current_locale(None)
            resource_class = i18n_dashboard.TranslatableResourceQuestions
            i18n_title = str(resource_class.get_i18n_title(key))
            self.assertEquals('description text', i18n_title)

            # Translated
            courses.Course.clear_current()
            ctx.set_current_locale('el')
            i18n_title = str(resource_class.get_i18n_title(key))
            self.assertEquals('DESCRIPTION TEXT', i18n_title)
        finally:
            ctx.set_current_locale(save_locale)
            sites.unset_path_info()

    def test_legacy_questions_with_null_body(self):
        # Create a question
        qu_dict = {
            'type': 0,
            'question': None,
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

        assessment = self.course.add_assessment()
        assessment.title = 'Test Assessment'
        assessment.html_content = """
            <question quid="%s" weight="1" instanceid="test_question">%s
        """ % (qu_id, '</question>')
        self.course.save()

        # Store translation data for the question
        qu_bundle = {
            'question': {
                'type': 'html',
                'source_value': 'None',
                'data': [
                    {
                        'source_value': 'None',
                        'target_value': 'NONE'
                    }]
            }
        }
        key_el = ResourceBundleKey(
            resources_display.ResourceMCQuestion.TYPE, qu_id, 'el')
        ResourceBundleDAO.save(
            ResourceBundleDTO(str(key_el), qu_bundle))

        dom = self.parse_html_string(
            self.get('assessment?name=%s' % assessment.unit_id).body)
        self.assertIsNone(dom.find('.//div[@class="qt-question"]').text)

    def _add_question_group_and_translations(self):
        qgp_dict = {
            'description': 'description text',
            'introduction': '<p>a</p><p>b</p>',
            'items': [{'question': self._add_question(), 'weight': '1'}],
            'last_modified': 1410451682.042784,
            'version': '1.5'
        }
        qgp_dto = models.QuestionGroupDTO(None, qgp_dict)
        qgp_id = models.QuestionGroupDAO.save(qgp_dto)

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
            resources_display.ResourceQuestionGroup.TYPE, qgp_id, 'el')
        ResourceBundleDAO.save(
            ResourceBundleDTO(str(key_el), qgp_bundle))
        return qgp_id

    def test_question_groups_are_translated(self):
        # Create a question group with one question
        qgp_id = self._add_question_group_and_translations()

        # Create an assessment and add the question group to the content
        assessment = self.course.add_assessment()
        assessment.title = 'Test Assessment'
        assessment.html_content = """
            <question-group qgid="%s" instanceid="test-qgp">
            </question-group><br>
        """ % qgp_id
        self.course.save()

        # Store translation data for the question

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

    def test_question_group_i18n_title(self):
        qgp_id = self._add_question_group_and_translations()
        key = resource.Key(resources_display.ResourceQuestionGroup.TYPE, qgp_id)

        try:
            sites.set_path_info('/' + self.COURSE_NAME)
            ctx = sites.get_course_for_current_request()
            save_locale = ctx.get_current_locale()

            # Untranslated
            ctx.set_current_locale(None)
            resource_class = i18n_dashboard.TranslatableResourceQuestionGroups
            i18n_title = str(resource_class.get_i18n_title(key))
            self.assertEquals('description text', i18n_title)

            # Translated
            courses.Course.clear_current()
            ctx.set_current_locale('el')
            i18n_title = str(resource_class.get_i18n_title(key))
            self.assertEquals('DESCRIPTION TEXT', i18n_title)
        finally:
            ctx.set_current_locale(save_locale)
            sites.unset_path_info()

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
            resources_display.ResourceCourseSettings.TYPE, 'homepage', 'el')
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
        prefs = models.StudentPreferencesDAO.load_or_default()
        models.StudentPreferencesDAO.delete(prefs)

        page_html = self.get('course').body
        dom = self.parse_html_string(page_html)
        self.assertEquals(
            self.COURSE_TITLE,
            dom.find('.//h1[@class="gcb-product-headers-large"]').text.strip())

    def test_invitations_are_translated(self):
        student_name = 'A. Student'
        sender_email = 'sender@foo.com'
        recipient_email = 'recipient@foo.com'
        translated_subject = 'EMAIL_FROM A. Student'

        # The invitation email
        email_env = {
        'course': {
            'invitation_email': {
                'enabled': True,
                'sender_email': sender_email,
                'subject_template': 'Email from {{sender_name}}',
                'body_template':
                    'From {{sender_name}}. Unsubscribe: {{unsubscribe_url}}'}}}

        # Translate the subject line of the email
        invitation_bundle = {
            'course:invitation_email:subject_template': {
                'type': 'string',
                'source_value': None,
                'data': [{
                    'source_value': 'Email from {{sender_name}}',
                    'target_value': 'EMAIL_FROM {{sender_name}}'}]}}
        key_el = ResourceBundleKey(
            resources_display.ResourceCourseSettings.TYPE, 'invitation', 'el')
        ResourceBundleDAO.save(
            ResourceBundleDTO(str(key_el), invitation_bundle))

        # Set up a spy to capture mails sent
        send_async_call_log = []
        def send_async_spy(unused_cls, *args, **kwargs):
            send_async_call_log.append({'args': args, 'kwargs': kwargs})

        # Patch the course env and the notifications sender
        courses.Course.ENVIRON_TEST_OVERRIDES = email_env
        old_send_async = notifications.Manager.send_async
        notifications.Manager.send_async = classmethod(send_async_spy)
        try:
            # register a student
            actions.login(self.STUDENT_EMAIL, is_admin=False)
            actions.register(self, student_name)

            # Set locale prefs
            prefs = models.StudentPreferencesDAO.load_or_default()
            prefs.locale = 'el'
            models.StudentPreferencesDAO.save(prefs)

            # Read the sample email displayed to the student
            self.assertIn(
                translated_subject, self.get('modules/invitation').body)

            # Post a request to the REST handler
            request_dict = {
                'xsrf_token': (
                    crypto.XsrfTokenManager.create_xsrf_token('invitation')),
                'payload': {'emailList': recipient_email}
            }
            response = transforms.loads(self.post(
                'rest/modules/invitation',
                {'request': transforms.dumps(request_dict)}).body)
            self.assertEquals(200, response['status'])
            self.assertEquals('OK, 1 messages sent', response['message'])

            self.assertEquals(
                translated_subject, send_async_call_log[0]['args'][4])

        finally:
            courses.Course.ENVIRON_TEST_OVERRIDES = []
            notifications.Manager.send_async = old_send_async


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
        self.unit.title = 'Unit Title'
        self.unit.description = 'unit description'
        self.unit.unit_header = 'unit header'
        self.unit.unit_footer = 'unit footer'
        self.unit.availability = courses.AVAILABILITY_AVAILABLE

        self.assessment = self.course.add_assessment()
        self.assessment.title = 'Assessment Title'
        self.assessment.description = 'assessment description'
        self.assessment.html_content = 'assessment html content'
        self.assessment.html_review_form = 'assessment html review form'
        self.assessment.availability = courses.AVAILABILITY_AVAILABLE

        self.link = self.course.add_link()
        self.link.title = 'Link Title'
        self.link.description = 'link description'
        self.link.url = 'link url'

        self.lesson = self.course.add_lesson(self.unit)
        self.lesson.unit_id = self.unit.unit_id
        self.lesson.title = 'Lesson Title'
        self.lesson.objectives = 'lesson objectives'
        self.lesson.video_id = 'lesson video'
        self.lesson.notes = 'lesson notes'
        self.lesson.availability = courses.AVAILABILITY_AVAILABLE

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
        prefs = models.StudentPreferencesDAO.load_or_default()
        prefs.locale = 'el'
        models.StudentPreferencesDAO.save(prefs)

    def tearDown(self):
        namespace_manager.set_namespace(self.old_namespace)
        super(TranslationImportExportTests, self).tearDown()

    def _do_download(self, payload, method='put'):
        request = {
            'xsrf_token': crypto.XsrfTokenManager.create_xsrf_token(
                i18n_dashboard.TranslationDownloadRestHandler.XSRF_TOKEN_NAME),
            'payload': transforms.dumps(payload),
            }
        if method == 'put':
            fp = self.put
        else:
            fp = self.post
        response = fp(
            '/%s%s' % (self.COURSE_NAME,
                       i18n_dashboard.TranslationDownloadRestHandler.URL),
            {'request': transforms.dumps(request)})
        return response

    def _do_deletion(self, payload):
        request = {
            'xsrf_token': crypto.XsrfTokenManager.create_xsrf_token(
                i18n_dashboard.TranslationDeletionRestHandler.XSRF_TOKEN_NAME),
            'payload': transforms.dumps(payload),
            }
        response = self.put(
            '/%s%s' % (self.COURSE_NAME,
                       i18n_dashboard.TranslationDeletionRestHandler.URL),
            params={'request': transforms.dumps(request)})
        return response

    def _do_upload(self, contents, warn_not_used=False, warn_not_found=False):
        xsrf_token = crypto.XsrfTokenManager.create_xsrf_token(
            i18n_dashboard.TranslationUploadRestHandler.XSRF_TOKEN_NAME)
        response = self.post(
            '/%s%s' % (self.COURSE_NAME,
                       i18n_dashboard.TranslationUploadRestHandler.URL),
            {'request': transforms.dumps({
                'xsrf_token': xsrf_token,
                'payload': transforms.dumps({
                    'warn_not_found': warn_not_found,
                    'warn_not_used': warn_not_used,
                    }),
                })},
            upload_files=[('file', 'doesntmatter', contents)])
        return response

    def test_deletion_ui_no_request(self):
        response = self.put(
            '/%s%s' % (self.COURSE_NAME,
                       i18n_dashboard.TranslationDeletionRestHandler.URL),
            {})
        rsp = transforms.loads(response.body)
        self.assertEquals(rsp['status'], 400)
        self.assertEquals(
            rsp['message'], 'Malformed or missing "request" parameter.')

    def test_deletion_ui_no_payload(self):
        response = self.put(
            '/%s%s' % (self.COURSE_NAME,
                       i18n_dashboard.TranslationDeletionRestHandler.URL),
            {'request': transforms.dumps({'foo': 'bar'})})
        rsp = transforms.loads(response.body)
        self.assertEquals(rsp['status'], 400)
        self.assertEquals(
            rsp['message'], 'Malformed or missing "payload" parameter.')

    def test_deletion_ui_no_xsrf(self):
        response = self.put(
            '/%s%s' % (self.COURSE_NAME,
                       i18n_dashboard.TranslationDeletionRestHandler.URL),
            {'request': transforms.dumps({'payload': '{}'})})
        rsp = transforms.loads(response.body)
        self.assertEquals(rsp['status'], 403)
        self.assertEquals(
            rsp['message'],
            'Bad XSRF token. Please reload the page and try again')

    def test_deletion_ui_no_locales(self):
        rsp = transforms.loads(self._do_deletion({'locales': []}).body)
        self.assertEquals(rsp['status'], 400)
        self.assertEquals(rsp['message'],
                          'Please select at least one language to delete.')

    def test_deletion_ui_malformed_locales(self):
        actions.login('foo@bar.com', is_admin=False)
        rsp = transforms.loads(self._do_deletion(
            {'locales': [{'checked': True}]}).body)
        self.assertEquals(rsp['status'], 400)
        self.assertEquals('Language specification not as expected.',
                          rsp['message'])

    def test_deletion_ui_no_selected_locales(self):
        actions.login('foo@bar.com', is_admin=False)
        rsp = transforms.loads(self._do_deletion(
            {'locales': [{'locale': 'de'}]}).body)
        self.assertEquals(rsp['status'], 400)
        self.assertEquals('Please select at least one language to delete.',
                          rsp['message'])

    def test_deletion_ui_no_permissions(self):
        actions.login('foo@bar.com', is_admin=False)
        rsp = transforms.loads(self._do_deletion(
            {'locales': [{'locale': 'de', 'checked': True}]}).body)
        self.assertEquals(401, rsp['status'])
        self.assertEquals('Access denied.', rsp['message'])

    def test_deletion(self):
        self.get('dashboard?action=i18n_reverse_case')

        # Verify that there are translation bundle rows for 'ln',
        # and progress items with settings for 'ln'.
        bundles = ResourceBundleDAO.get_all_for_locale('ln')
        self.assertGreater(len(bundles), 0)
        progress = I18nProgressDAO.get_all()
        self.assertGreater(len(progress), 0)
        for p in progress:
            self.assertEquals(I18nProgressDTO.DONE, p.get_progress('ln'))

        rsp = transforms.loads(self._do_deletion(
            {'locales': [{'locale': 'ln', 'checked': True}]}).body)
        self.assertEquals(200, rsp['status'])
        self.assertEquals('Success.', rsp['message'])

        # Verify that there are no translation bundle rows for 'ln',
        # and no progress items with settings for 'ln'.
        bundles = ResourceBundleDAO.get_all_for_locale('ln')
        self.assertEquals(len(bundles), 0)
        progress = I18nProgressDAO.get_all()
        self.assertGreater(len(progress), 0)
        for p in progress:
            self.assertEquals(I18nProgressDTO.NOT_STARTED, p.get_progress('ln'))

    def test_upload_ui_no_request(self):
        response = self.post(
            '/%s%s' % (self.COURSE_NAME,
                       i18n_dashboard.TranslationUploadRestHandler.URL),
            {})
        self.assertEquals(
            '<response><status>400</status><message>'
            'Malformed or missing "request" parameter.</message></response>',
            response.body)

    def test_upload_ui_no_xsrf(self):
        response = self.post(
            '/%s%s' % (self.COURSE_NAME,
                       i18n_dashboard.TranslationUploadRestHandler.URL),
            {'request': transforms.dumps({})})
        self.assertEquals(
            '<response><status>403</status><message>'
            'Missing or invalid XSRF token.</message></response>',
            response.body)

    def test_upload_ui_no_file(self):
        xsrf_token = crypto.XsrfTokenManager.create_xsrf_token(
            i18n_dashboard.TranslationUploadRestHandler.XSRF_TOKEN_NAME)
        response = self.post(
            '/%s%s' % (self.COURSE_NAME,
                       i18n_dashboard.TranslationUploadRestHandler.URL),
            {'request': transforms.dumps({'xsrf_token': xsrf_token})})
        self.assertEquals(
            '<response><status>400</status><message>'
            'Must select a .zip or .po file to upload.</message></response>',
            response.body)

    def test_upload_ui_bad_file_param(self):
        xsrf_token = crypto.XsrfTokenManager.create_xsrf_token(
            i18n_dashboard.TranslationUploadRestHandler.XSRF_TOKEN_NAME)
        response = self.post(
            '/%s%s' % (self.COURSE_NAME,
                       i18n_dashboard.TranslationUploadRestHandler.URL),
            {
                'request': transforms.dumps({'xsrf_token': xsrf_token}),
                'file': ''
            })
        self.assertEquals(
            '<response><status>400</status><message>'
            'Must select a .zip or .po file to upload</message></response>',
            response.body)

    def test_upload_ui_empty_file(self):
        response = self._do_upload('')
        self.assertEquals(
            '<response><status>400</status><message>'
            'The .zip or .po file must not be empty.</message></response>',
            response.body)

    def test_upload_ui_bad_content(self):
        response = self._do_upload('23 skidoo')
        self.assertEquals(
            '<response><status>400</status><message>'
            'No translations found in provided file.</message></response>',
            response.body)

    def test_upload_ui_no_permissions(self):
        actions.login('foo@bar.com', is_admin=False)
        response = self._do_upload(
            '# <span class="">1.1 Lesson Title</span>\n'
            '#: GCB-1|title|string|lesson:4:de:0\n'
            '#| msgid ""\n'
            'msgid "Lesson Title"\n'
            'msgstr "Lektion Titel"\n')
        self.assertEquals(
            '<response><status>401</status><message>'
            'Access denied.</message></response>',
            response.body)

    def test_upload_ui_bad_protocol(self):
        actions.login('foo@bar.com', is_admin=False)
        response = self._do_upload(
            '# <span class="">1.1 Lesson Title</span>\n'
            '#: GCB-2|title|string|lesson:4:de:0\n'
            '#| msgid ""\n'
            'msgid "Lesson Title"\n'
            'msgstr "Lektion Titel"\n')
        self.assertEquals(
            '<response><status>400</status><message>'
            'Expected location format GCB-1, but had GCB-2'
            '</message></response>',
            response.body)

    def test_upload_ui_multiple_languages(self):
        actions.login('foo@bar.com', is_admin=False)
        response = self._do_upload(
            '# <span class="">1.1 Lesson Title</span>\n'
            '#: GCB-1|title|string|lesson:4:de:0\n'
            '#: GCB-1|title|string|lesson:4:fr:0\n'
            '#| msgid ""\n'
            'msgid "Lesson Title"\n'
            'msgstr "Lektion Titel"\n')
        self.assertEquals(
            '<response><status>400</status><message>'
            'File has translations for both "de" and "fr"'
            '</message></response>',
            response.body)

    def test_upload_ui_one_item(self):
        # Do export to force creation of progress, bundle entities
        self._do_download({'locales': [{'locale': 'de', 'checked': True}],
                           'export_what': 'all'}, method='post')
        # Upload one translation.
        response = self._do_upload(
            '# <span class="">1.1 Lesson Title</span>\n'
            '#: GCB-1|title|string|lesson:4:de:0\n'
            '#| msgid ""\n'
            'msgid "Lesson Title"\n'
            'msgstr "Lektion Titel"\n')
        self.assertIn(
            '<response><status>200</status><message>Success.</message>',
            response.body)
        self.assertIn('made 1 total replacements', response.body)

        # Verify uploaded translation makes it to lesson page when
        # viewed with appropriate language preference.
        prefs = models.StudentPreferencesDAO.load_or_default()
        prefs.locale = 'de'
        models.StudentPreferencesDAO.save(prefs)
        response = self.get(
            '/%s/unit?unit=%s&lesson=%s' % (
                self.COURSE_NAME, self.unit.unit_id, self.lesson.lesson_id))
        self.assertIn('Lektion Titel', response.body)

    def _parse_messages(self, response):
        dom = self.parse_html_string(response.body)
        payload = dom.find('.//payload')
        return transforms.loads(payload.text)['messages']

    def test_upload_ui_no_bundles_created(self):
        # Upload one translation.
        response = self._do_upload(
            '# <span class="">1.1 Lesson Title</span>\n'
            '#: GCB-1|title|string|lesson:4:de:0\n'
            '#| msgid ""\n'
            'msgid "Lesson Title"\n'
            'msgstr "Lektion Titel"\n')
        messages = self._parse_messages(response)

        # Expect no messages other than the expected missing translations and
        # the summary line indicating that we did something.
        for message in messages:
            self.assertTrue(
                message.startswith('Did not find translation for') or
                message.startswith('For Deutsch (de), made 1 total replacem'))

    def test_upload_ui_with_bundles_created(self):
        # Do export to force creation of progress, bundle entities
        self._do_download({'locales': [{'locale': 'de', 'checked': True}],
                           'export_what': 'all'}, method='post')
        # Upload one translation.
        response = self._do_upload(
            '# <span class="">1.1 Lesson Title</span>\n'
            '#: GCB-1|title|string|lesson:4:de:0\n'
            '#| msgid ""\n'
            'msgid "Lesson Title"\n'
            'msgstr "Lektion Titel"\n')
        messages = self._parse_messages(response)
        # Expect no messages other than the expected missing translations and
        # the summary line indicating that we did something.
        for message in messages:
            self.assertTrue(
                message.startswith('Did not find translation for') or
                message.startswith('For Deutsch (de), made 1 total replacem'))

    def test_upload_ui_with_unexpected_resource(self):
        # Here, we are uploading something where we will have a match on
        # "Lesson Title" in the translation item key, but we will then _not_
        # match on any location (there is no lesson:999 in the course)

        # Do export to force creation of progress, bundle entities
        self._do_download({'locales': [{'locale': 'de', 'checked': True}],
                           'export_what': 'all'}, method='post')
        # Upload one translation.
        response = self._do_upload(
            '# <span class="">1.1 Lesson Title</span>\n'
            '#: GCB-1|title|string|lesson:999:de:0\n'
            '#| msgid ""\n'
            'msgid "Lesson Title"\n'
            'msgstr "Lektion Titel"\n', warn_not_used=True, warn_not_found=True)
        messages = self._parse_messages(response)
        self.assertIn(
            'Unused translation in file messages.po for '
            '"Lesson Title" -> "Lektion Titel" for locations: lesson:999:de',
            messages)

    def test_upload_ui_with_unexpected_translation(self):
        # Here, we are uploading something where we will not have a match
        # on the "FizzBuzz" item key, although that item will have a valid
        # location (lesson:4:de is a valid location target)

        # Do export to force creation of progress, bundle entities
        self._do_download({'locales': [{'locale': 'de', 'checked': True}],
                           'export_what': 'all'}, method='post')
        # Upload one translation.
        response = self._do_upload(
            '# <span class="">1.1 Lesson Title</span>\n'
            '#: GCB-1|title|string|lesson:4:de:0\n'
            '#| msgid ""\n'
            'msgid "FizzBuzz"\n'
            'msgstr "Lektion Titel"\n', warn_not_used=True, warn_not_found=True)
        messages = self._parse_messages(response)
        self.assertIn(
            'Unused translation in file messages.po for '
            '"FizzBuzz" -> "Lektion Titel" for locations: lesson:4:de',
            messages)

    def test_upload_ui_with_missing_translation(self):
        # Do export to force creation of progress, bundle entities
        self._do_download({'locales': [{'locale': 'de', 'checked': True}],
                           'export_what': 'all'}, method='post')
        # Upload one translation.
        response = self._do_upload(
            '# <span class="">1.1 Lesson Title</span>\n'
            '#: GCB-1|title|string|lesson:4:de:0\n'
            '#| msgid ""\n'
            'msgid "FizzBuzz"\n'
            'msgstr "Lektion Titel"\n', warn_not_found=True, warn_not_used=True)
        messages = self._parse_messages(response)
        self.assertIn(
            'Did not find translation for "Lesson Title" at lesson:4', messages)

    def test_upload_ui_with_blank_translation(self):
        resource_key_map = (i18n_dashboard.TranslatableResourceRegistry.
                            get_resources_and_keys(self.course))
        resource_count = len(resource_key_map)

        # Do export to force creation of progress, bundle entities
        self._do_download({'locales': [{'locale': 'de', 'checked': True}],
                           'export_what': 'all'}, method='post')
        # Upload one translation.
        response = self._do_upload(
            '# <span class="">1.1 Lesson Title</span>\n'
            '#: GCB-1|title|string|lesson:4:de:0\n'
            '#| msgid ""\n'
            'msgid "Lesson Title"\n'
            'msgstr ""\n')
        messages = self._parse_messages(response)
        self.assertIn(
            'For Deutsch (de), made 0 total replacements in {} resources.  '
            '1 items in the uploaded file did not have translations.'.format(
                resource_count), messages)

    def test_download_ui_no_request(self):
        response = self.put(
            '/%s%s' % (self.COURSE_NAME,
                       i18n_dashboard.TranslationDownloadRestHandler.URL),
            {})
        rsp = transforms.loads(response.body)
        self.assertEquals(rsp['status'], 400)
        self.assertEquals(
            rsp['message'], 'Malformed or missing "request" parameter.')

    def test_download_ui_no_payload(self):
        response = self.put(
            '/%s%s' % (self.COURSE_NAME,
                       i18n_dashboard.TranslationDownloadRestHandler.URL),
            {'request': transforms.dumps({'foo': 'bar'})})
        rsp = transforms.loads(response.body)
        self.assertEquals(rsp['status'], 400)
        self.assertEquals(
            rsp['message'], 'Malformed or missing "payload" parameter.')

    def test_download_ui_no_xsrf(self):
        response = self.put(
            '/%s%s' % (self.COURSE_NAME,
                       i18n_dashboard.TranslationDownloadRestHandler.URL),
            {'request': transforms.dumps({'payload': '{}'})})
        rsp = transforms.loads(response.body)
        self.assertEquals(rsp['status'], 403)
        self.assertEquals(
            rsp['message'],
            'Bad XSRF token. Please reload the page and try again')

    def test_download_ui_no_locales(self):
        rsp = transforms.loads(self._do_download({'locales': []}).body)
        self.assertEquals(rsp['status'], 400)
        self.assertEquals(rsp['message'],
                          'Please select at least one language to export.')

    def test_download_ui_malformed_locales(self):
        actions.login('foo@bar.com', is_admin=False)
        rsp = transforms.loads(self._do_download(
            {'locales': [{'checked': True}]}).body)
        self.assertEquals(rsp['status'], 400)
        self.assertEquals('Language specification not as expected.',
                          rsp['message'])

    def test_download_ui_no_selected_locales(self):
        actions.login('foo@bar.com', is_admin=False)
        rsp = transforms.loads(self._do_download(
            {'locales': [{'locale': 'de'}]}).body)
        self.assertEquals(rsp['status'], 400)
        self.assertEquals('Please select at least one language to export.',
                          rsp['message'])

    def test_download_ui_no_permissions(self):
        actions.login('foo@bar.com', is_admin=False)
        rsp = transforms.loads(self._do_download(
            {'locales': [{'locale': 'de', 'checked': True}]}).body)
        self.assertEquals(401, rsp['status'])
        self.assertEquals('Access denied.', rsp['message'])

    def test_download_ui_file_name_default(self):
        extra_env = {
            'extra_locales': [{'locale': 'de', 'availability': 'available'}]
            }
        with actions.OverriddenEnvironment(extra_env):
            rsp = self._do_download(
                {'locales': [{'locale': 'de', 'checked': True}]}, method='post')
            self.assertEquals('application/octet-stream', rsp.content_type)
            self.assertEquals('attachment; filename="i18n_course.zip"',
                              rsp.content_disposition)

    def test_download_ui_file_name_set(self):
        extra_env = {
            'extra_locales': [{'locale': 'de', 'availability': 'available'}]
            }
        with actions.OverriddenEnvironment(extra_env):
            rsp = self._do_download({
                'locales': [{'locale': 'de', 'checked': True}],
                'file_name': 'xyzzy.zip',
                }, method='post')
            self.assertEquals('application/octet-stream', rsp.content_type)
            self.assertEquals('attachment; filename="xyzzy.zip"',
                              rsp.content_disposition)

    def _translated_value_swapcase(self, key, section_name):
        get_response = self.get(
            '/%s%s?%s' % (
                self.COURSE_NAME,
                i18n_dashboard.TranslationConsoleRestHandler.URL,
                urllib.urlencode({'key': str(key)})))
        response = transforms.loads(get_response.body)
        payload = transforms.loads(response['payload'])
        s = next(s for s in payload['sections'] if s['name'] == section_name)
        s['data'][0]['changed'] = True
        s['data'][0]['target_value'] = s['data'][0]['source_value'].swapcase()

        response['payload'] = transforms.dumps(payload)
        response['key'] = payload['key']
        response = self.put(
            '/%s%s' % (self.COURSE_NAME,
                       i18n_dashboard.TranslationConsoleRestHandler.URL),
            {'request': transforms.dumps(response)})

    def _make_current_and_stale_translation(self):
        # Provide translations for lesson title and assessment title.
        self._translated_value_swapcase(
            ResourceBundleKey(resources_display.ResourceLesson.TYPE,
                              self.lesson.lesson_id, 'de'),
            'title')
        self._translated_value_swapcase(
            ResourceBundleKey(resources_display.ResourceAssessment.TYPE,
                              self.assessment.unit_id, 'de'),
            'assessment:title')

        # Make assessment out-of-date by changing the assessment title
        # via the course interface.
        assessment = self.course.find_unit_by_id(self.assessment.unit_id)
        assessment.title = 'Edited Assessment Title'
        self.course.save()

    def _parse_zip_response(self, response):
        download_zf = zipfile.ZipFile(cStringIO.StringIO(response.body), 'r')
        out_stream = StringIO.StringIO()
        out_stream.fp = out_stream
        for item in download_zf.infolist():
            file_data = download_zf.read(item)
            catalog = pofile.read_po(cStringIO.StringIO(file_data))
            yield catalog

    def test_export_only_selected_languages(self):
        extra_env = {
            'extra_locales': [
                {'locale': 'de', 'availability': 'available'},
                {'locale': 'fr', 'availability': 'available'},
                {'locale': 'es', 'availability': 'available'},
                ]
            }
        with actions.OverriddenEnvironment(extra_env):
            payload = {
                'locales': [
                    {'locale': 'de', 'checked': True},
                    {'locale': 'fr', 'checked': True},
                    {'locale': 'es'},
                    ],
                'export_what': 'all'}
            response = self._do_download(payload, method='post')
            zf = zipfile.ZipFile(cStringIO.StringIO(response.body), 'r')
            contents = [item.filename for item in zf.infolist()]
            self.assertIn('locale/de/LC_MESSAGES/messages.po', contents)
            self.assertIn('locale/fr/LC_MESSAGES/messages.po', contents)
            self.assertNotIn('locale/es/LC_MESSAGES/messages.po', contents)

    def _test_export(self, export_what, expect_lesson):
        def find_message(catalog, the_id):
            for message in catalog:
                if message.id == the_id:
                    return message
            return None

        extra_env = {
            'extra_locales': [{'locale': 'de', 'availability': 'available'}]
            }
        with actions.OverriddenEnvironment(extra_env):
            self._make_current_and_stale_translation()

            payload = {
                'locales': [{'locale': 'de', 'checked': True}],
                'export_what': export_what,
                }
            response = self._do_download(payload)
            rsp = transforms.loads(response.body)
            self.assertEquals(200, rsp['status'])
            self.assertEquals('Success.', rsp['message'])
            response = self._do_download(payload, method='post')
            for catalog in self._parse_zip_response(response):
                unit = find_message(catalog, 'Unit Title')
                self.assertEquals(1, len(unit.locations))
                self.assertEquals('GCB-1|title|string|unit:1:de',
                                  unit.locations[0][0])
                self.assertEquals('', unit.string)

                assessment = find_message(catalog, 'Edited Assessment Title')
                self.assertEquals(1, len(assessment.locations))
                self.assertEquals(
                    'GCB-1|assessment:title|string|assessment:2:de',
                    assessment.locations[0][0])
                self.assertEquals('', assessment.string)

                lesson = find_message(catalog, 'Lesson Title')
                if expect_lesson:
                    self.assertEquals(1, len(lesson.locations))
                    self.assertEquals('GCB-1|title|string|lesson:4:de',
                                      lesson.locations[0][0])
                    self.assertEquals('lESSON tITLE', lesson.string)
                    self.assertEquals([], lesson.previous_id)
                else:
                    self.assertIsNone(lesson)

    def test_export_only_new(self):
        self._test_export('new', False)

    def test_export_all(self):
        self._test_export('all', True)

    def test_added_items_appear_on_dashboard(self):
        """Ensure that all items added in setUp are present on dashboard.

        Do this so that we can trust in other tests that when we don't
        see something that we don't expect to see it's not because we failed
        to add the item, but instead it really is getting actively suppressed.
        """
        response = self.get(self.URL)
        self.assertIn('Unit Title', response.body)
        self.assertIn('Assessment Title', response.body)
        self.assertIn('Link Title', response.body)
        self.assertIn('Lesson Title', response.body)
        self.assertIn('mc description', response.body)
        self.assertIn('sa description', response.body)
        self.assertIn('question group description', response.body)

    def test_download_exports_all_expected_fields(self):
        extra_env = {
            'extra_locales': [{'locale': 'de', 'availability': 'available'}]
            }
        with actions.OverriddenEnvironment(extra_env):
            response = self._do_download(
                {'locales': [{'locale': 'de', 'checked': True}],
                 'export_what': 'all'}, method='post')
            for catalog in self._parse_zip_response(response):
                messages = [msg.id for msg in catalog]
                self.assertIn('Unit Title', messages)
                self.assertIn('unit description', messages)
                self.assertIn('unit header', messages)
                self.assertIn('unit footer', messages)
                self.assertIn('Assessment Title', messages)
                self.assertIn('assessment description', messages)
                self.assertIn('assessment html content', messages)
                self.assertIn('assessment html review form', messages)
                self.assertIn('Link Title', messages)
                self.assertIn('link description', messages)
                self.assertIn('Lesson Title', messages)
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
        response = self._do_download(
            {'locales': [{'locale': 'el', 'checked': True}],
             'export_what': 'all'}, method='post')
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
                      'payload': transforms.dumps({'key': ''})})},
                  upload_files=[('file', 'doesntmatter', upload_contents)])

        # Download the translations; verify the doubling.
        response = self._do_download(
            {'locales': [{'locale': 'el', 'checked': True}],
             'export_what': 'all'}, method='post')
        for catalog in self._parse_zip_response(response):
            num_translations = 0
            for msg in catalog:
                if msg.locations:  # Skip header pseudo-message entry
                    num_translations += 1
                    self.assertNotEquals(msg.id, msg.string)
                    self.assertEquals(msg.id.upper() * 2, msg.string)
            self.assertEquals(29, num_translations)

        # And verify the presence of the translated versions on actual
        # course pages.
        response = self.get('unit?unit=%s' % self.unit.unit_id)
        self.assertIn(self.unit.title.upper() * 2, response.body)
        self.assertIn(self.lesson.title.upper() * 2, response.body)

    def test_reverse_case(self):
        response = self.get('dashboard?action=i18n_reverse_case')
        prefs = models.StudentPreferencesDAO.load_or_default()
        prefs.locale = 'ln'
        models.StudentPreferencesDAO.save(prefs)
        response = self.get('unit?unit=%s' % self.unit.unit_id)
        self.assertIn('uNIT tITLE', response.body)
        self.assertIn('lESSON tITLE', response.body)

    def _test_progress_calculation(self, sections, expected_status):
        key = i18n_dashboard.ResourceBundleKey.fromstring('assessment:1:de')
        i18n_progress_dto = i18n_dashboard.I18nProgressDAO.create_blank(key)
        for section in sections:
            section['name'] = 'fred'
            section['type'] = 'string'
        TranslationConsoleRestHandler.update_dtos_with_section_data(
            key, sections, None, i18n_progress_dto)
        self.assertEquals(expected_status,
                          i18n_progress_dto.get_progress(key.locale))

    def test_progress_no_sections_is_done(self):
        self._test_progress_calculation([], i18n_dashboard.I18nProgressDTO.DONE)

    def test_progress_one_section_current_and_not_changed_is_done(self):
        self._test_progress_calculation(
            [{'data': [{'verb': i18n_dashboard.VERB_CURRENT,
                        'changed': False,
                        'source_value': 'yes',
                        'target_value': 'ja'}]}],
            i18n_dashboard.I18nProgressDTO.DONE)

    def test_progress_one_section_current_and_changed_is_done(self):
        self._test_progress_calculation(
            [{'data': [{'verb': i18n_dashboard.VERB_CURRENT,
                        'changed': True,
                        'source_value': 'yes',
                        'target_value': 'yup'}]}],
            i18n_dashboard.I18nProgressDTO.DONE)

    def test_progress_one_section_stale_and_not_changed_is_in_progress(self):
        self._test_progress_calculation(
            [{'data': [{'verb': i18n_dashboard.VERB_CHANGED,
                        'changed': False,
                        'old_source_value': 'yse',
                        'source_value': 'yes',
                        'target_value': 'ja'}]}],
            i18n_dashboard.I18nProgressDTO.IN_PROGRESS)

    def test_progress_one_section_stale_but_changed_is_done(self):
        self._test_progress_calculation(
            [{'data': [{'verb': i18n_dashboard.VERB_CHANGED,
                        'changed': True,
                        'old_source_value': 'yse',
                        'source_value': 'yes',
                        'target_value': 'ja'}]}],
            i18n_dashboard.I18nProgressDTO.DONE)

    def test_progress_one_section_new_and_not_translated_is_not_started(self):
        self._test_progress_calculation(
            [{'data': [{'verb': i18n_dashboard.VERB_NEW,
                        'changed': False,
                        'source_value': 'yes',
                        'target_value': ''}]}],
            i18n_dashboard.I18nProgressDTO.NOT_STARTED)

    def test_progress_one_section_new_and_translated_is_done(self):
        self._test_progress_calculation(
            [{'data': [{'verb': i18n_dashboard.VERB_NEW,
                        'changed': False,
                        'source_value': 'yes',
                        'target_value': 'ja'}]}],
            i18n_dashboard.I18nProgressDTO.NOT_STARTED)

    def test_progress_one_section_current_but_changed_to_blank_unstarted(self):
        self._test_progress_calculation(
            [{'data': [{'verb': i18n_dashboard.VERB_CURRENT,
                        'changed': True,
                        'source_value': 'yes',
                        'target_value': ''}]}],
            i18n_dashboard.I18nProgressDTO.NOT_STARTED)

    def test_progress_one_section_changed_but_changed_to_blank_unstarted(self):
        self._test_progress_calculation(
            [{'data': [{'verb': i18n_dashboard.VERB_CHANGED,
                        'changed': True,
                        'source_value': 'yes',
                        'target_value': ''}]}],
            i18n_dashboard.I18nProgressDTO.NOT_STARTED)

    def test_progress_one_section_new_but_changed_to_blank_is_unstarted(self):
        self._test_progress_calculation(
            [{'data': [{'verb': i18n_dashboard.VERB_NEW,
                        'changed': True,
                        'source_value': 'yes',
                        'target_value': ''}]}],
            i18n_dashboard.I18nProgressDTO.NOT_STARTED)

    def test_progress_one_not_started_and_one_done_is_in_progress(self):
        self._test_progress_calculation(
            [{'data': [{'verb': i18n_dashboard.VERB_NEW,
                        'changed': False,
                        'source_value': 'yes',
                        'target_value': ''},
                       {'verb': i18n_dashboard.VERB_CURRENT,
                        'changed': False,
                        'source_value': 'yes',
                        'target_value': 'ja'}]}],
            i18n_dashboard.I18nProgressDTO.IN_PROGRESS)

    def test_progress_one_stale_and_one_done_is_in_progress(self):
        self._test_progress_calculation(
            [{'data': [{'verb': i18n_dashboard.VERB_CHANGED,
                        'changed': False,
                        'old_source_value': 'yse',
                        'source_value': 'yes',
                        'target_value': 'ja'},
                       {'verb': i18n_dashboard.VERB_CURRENT,
                        'changed': False,
                        'source_value': 'yes',
                        'target_value': 'ja'}]}],
            i18n_dashboard.I18nProgressDTO.IN_PROGRESS)

    def test_progress_one_stale_and_one_not_started_is_in_progress(self):
        self._test_progress_calculation(
            [{'data': [{'verb': i18n_dashboard.VERB_CHANGED,
                        'changed': False,
                        'old_source_value': 'yse',
                        'source_value': 'yes',
                        'target_value': 'ja'},
                       {'verb': i18n_dashboard.VERB_NEW,
                        'changed': False,
                        'source_value': 'yes',
                        'target_value': ''}]}],
            i18n_dashboard.I18nProgressDTO.IN_PROGRESS)


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

        # Need to muck with internals of code under test.
        # pylint: disable=protected-access
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
            soup = self.parse_html_string_to_soup(
                self.get(self.DASHBOARD_URL).body)
            table = soup.select('.i18n-progress-table')[0]
            columns = table.select('.language-header')
            expected_col_data = [
                'el'
            ]
            self.assertEquals(len(expected_col_data), len(columns))
            for index, expected in enumerate(expected_col_data):
                self.assertEquals(expected, columns[index].text)
            response = self.get('%s?key=%s' % (
                self.CONSOLE_REST_URL, 'course_settings%3Ahomepage%3Aru'))
            self.assertEquals(transforms.loads(response.body)['status'], 401)
            response = self.get('%s?key=%s' % (
                self.CONSOLE_REST_URL, 'course_settings%3Ahomepage%3Ael'))
            self.assertEquals(transforms.loads(response.body)['status'], 200)


class CourseLocalizationTestBase(actions.TestBase):

    COURSE = 'first'
    NAMESPACE = 'ns_%s' % COURSE
    ADMIN_EMAIL = 'test_course_localization@google.com'

    def setUp(self):
        super(CourseLocalizationTestBase, self).setUp()
        if sites.GCB_COURSES_CONFIG.name in sites.Registry.test_overrides:
            del sites.Registry.test_overrides[sites.GCB_COURSES_CONFIG.name]
        self.auto_deploy = sites.ApplicationContext.AUTO_DEPLOY_DEFAULT_COURSE
        sites.ApplicationContext.AUTO_DEPLOY_DEFAULT_COURSE = False
        self._import_course()
        self._locale_to_label = {}

    def tearDown(self):
        del sites.Registry.test_overrides[sites.GCB_COURSES_CONFIG.name]
        sites.ApplicationContext.AUTO_DEPLOY_DEFAULT_COURSE = self.auto_deploy
        super(CourseLocalizationTestBase, self).tearDown()

    def _import_course(self):
        actions.login(self.ADMIN_EMAIL, is_admin=True)
        return actions.simple_add_course(self.COURSE, self.ADMIN_EMAIL,
                                         'My First Course')


class SampleCourseLocalizationTest(CourseLocalizationTestBase):

    def _import_sample_course(self):
        dst_app_context = actions.simple_add_course(
            'sample', 'test_course_localization@google.com',
            'Power Searching with Google')
        dst_course = courses.Course(None, dst_app_context)
        src_app_context = sites.get_all_courses('course:/:/:')[0]
        errors = []
        dst_course.import_from(src_app_context, errors)
        dst_course.save()
        self.assertEquals(0, len(errors))

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

    def _add_units(self, locale_labels=False):
        with Namespace('ns_first'):
            course = courses.Course(None, sites.get_all_courses()[0])

            _en = course.add_unit()
            _en.type = 'U'
            _en.availability = courses.AVAILABILITY_AVAILABLE
            _en.title = 'Unit en_US'

            _ru = course.add_unit()
            _ru.type = 'U'
            _ru.availability = courses.AVAILABILITY_AVAILABLE
            _ru.title = 'Unit ru_RU'

            _es = course.add_unit()
            _es.type = 'U'
            _es.availability = courses.AVAILABILITY_AVAILABLE
            _es.title = 'Unit es_ES'

            _all = course.add_unit()
            _all.type = 'U'
            _all.availability = courses.AVAILABILITY_AVAILABLE
            _all.title = 'Unit all_ALL'

            _none = course.add_unit()
            _none.type = 'U'
            _none.availability = courses.AVAILABILITY_AVAILABLE
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
            prefs = models.StudentPreferencesDAO.load_or_default()
            if prefs:
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
            self._assert_picker(False)
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
            self._assert_picker(
                True, ['en_US', 'ru_RU', 'es_ES'], is_admin=True)

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

    def test_button_captions(self):
        self._import_sample_course()
        self._setup_locales(course='sample')

        self._set_prefs_locale('ru', course='sample')

        response = self.get('/sample/course')
        # TODO(psimakov): 'Search' button caption must be localized; but it's
        # in the hook and we don't curently support gettext() inside hook :(
        self.assertIn('type="submit" value="Search"', response.body)

        response = self.get('/sample/unit?unit=14&lesson=20')
        self.assertIn('Проверить ответ', response.body)
        self.assertIn('Подсказка', response.body)
        self.assertIn('Баллов: 1', response.body)
        self.assertIn('Предыдущая страница', response.body)
        self.assertIn('Следующая страница', response.body)

        response = self.get('/sample/assessment?name=1')
        self.assertIn('Отправить ответы', response.body)

        for url in [
            '/sample/assessment?name=35', '/sample/assessment?name=65']:
            response = self.get(url)
            self.assertIn('Баллов: 1', response.body)
            self.assertIn('Проверить ответы', response.body)
            self.assertIn('Отправить ответы', response.body)

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
            unit_1.availability = courses.AVAILABILITY_AVAILABLE
            unit_1.title = 'Unit for Track A and Locale ru_RU'
            unit_1.labels = utils.list_to_text(
                [track_a_id, locale_ru_id])
            unit_2 = course.add_unit()
            unit_2.type = 'U'
            unit_2.availability = courses.AVAILABILITY_AVAILABLE
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

    def test_set_current_locale_reloads_environ(self):
        app_context = sites.get_all_courses()[0]
        self._setup_locales()
        course = courses.Course(None, app_context)

        course_bundle = {
            'course:title': {
                'source_value': None,
                'type': 'string',
                'data': [
                    {
                        'source_value': app_context.get_title(),
                        'target_value': 'TRANSLATED TITLE'
                    }]
            }}
        with Namespace('ns_first'):
            key_el = ResourceBundleKey(
                resources_display.ResourceCourseSettings.TYPE, 'homepage',
                'es_ES')
            ResourceBundleDAO.save(
                ResourceBundleDTO(str(key_el), course_bundle))

        sites.set_path_info('/first')
        app_context.set_current_locale('ru_RU')
        ru_env = course.get_environ(app_context)
        app_context.set_current_locale('es_ES')
        es_env = course.get_environ(app_context)
        sites.unset_path_info()

        self.assertNotEquals(ru_env, es_env)

    def test_swapcase(self):
        source = '12345'
        target = u'12345λ'
        self.assertEquals(target, i18n_dashboard.swapcase(source))

        source = '<img alt="Hello!">W0rld</img>'
        target = u'<img alt="Hello!">w0RLDλ</img>'
        self.assertEquals(target, i18n_dashboard.swapcase(source))

        source = 'Hello W0rld!'
        target = u'hELLO w0RLD!λ'
        self.assertEquals(target, i18n_dashboard.swapcase(source))

        source = 'Hello&apos;W0rld!'
        target = u'hELLO\'w0RLD!λ'
        self.assertEquals(target, i18n_dashboard.swapcase(source))

        # content inside tags must be preserved
        source = (
            'Hello<img src="http://a.b.com/'
            'foo?bar=baz&amp;cookie=sweet"/>W0rld')
        target = (
            u'hELLOλ<img src="http://a.b.com/'
            u'foo?bar=baz&amp;cookie=sweet"/>w0RLDλ')
        self.assertEquals(target, i18n_dashboard.swapcase(source))

        # %s and other formatting must be preserved
        source = 'Hello%sW0rld!'
        target = u'hELLO%sw0RLD!λ'
        self.assertEquals(target, i18n_dashboard.swapcase(source))

        source = 'Hello%(foo)sW0rld!'
        target = u'hELLO%(foo)sw0RLD!λ'
        self.assertEquals(target, i18n_dashboard.swapcase(source))

        # we dont support {foo} type formatting
        source = 'Hello{s}W0rld!'
        target = u'hELLO{S}w0RLD!λ'
        self.assertEquals(target, i18n_dashboard.swapcase(source))

    def test_reverse_case(self):
        self._import_sample_course()
        actions.login('test_reverse_case@example.com', is_admin=True)

        self.get('sample/dashboard?action=i18n_reverse_case')
        self._set_prefs_locale('ln', course='sample')

        def check_all_in(response, texts):
            self.assertEquals(200, response.status_int)
            for text in texts:
                self.assertIn(text, response.body)

        # check selected pages
        check_all_in(self.get('sample/course'), [
            'dANIEL rUSSELL', 'pRE-COURSE ASSESSMENT', 'iNTRODUCTION'])
        check_all_in(self.get('sample/assessment?name=1'), [
            'tHANK YOU, AND HAVE FUN!', 'wHEN SEARCHING gOOGLE iMAGES',
            'a AND c', 'iF YOU DO NOT KNOW'])
        check_all_in(self.get('sample/unit?unit=14'), [
            'Unit 2 - iNTERPRETING RESULTS', 'wHEN SEARCH RESULTS SUGGEST',
            'lESSON 2.3 aCTIVITY'])
        check_all_in(self.get('sample/unit?unit=2&lesson=9'), [
            'lESSON 1.4 aCTIVITY'])
        check_all_in(self.get('sample/unit?unit=14&lesson=16'), [
            'hAVE YOU EVER PLAYED THE'])
        check_all_in(self.get('sample/unit?unit=47&lesson=53'), [
            'dID dARWIN, HIMSELF, USE', 'aDVENTURES IN wONDERLAND'])
        check_all_in(self.get('sample/assessment?name=64'), [
            'sOLVE THE PROBLEM BELOW', 'hOW MANY pOWER sEARCH CONCEPTS',
            'lIST THE pOWER sEARCH CONCEPTS'])

        # check assesment submition; it has fragile %s type complex formatting
        # functions that we need to check
        actions.register(self, 'test_reverse_case', course='sample')
        response = self.post('sample/answer', {
            'xsrf_token': crypto.XsrfTokenManager.create_xsrf_token(
                'assessment-post'),
            'score': 0, 'assessment_type': 65, 'answers': {}})
        self.assertEquals(200, response.status_int)
        for text in ['for taking the pOST-COURSE', 'cERTIFICATE OR NOT, WE']:
            self.assertIn(text, response.body)

        # check
        invalid_question = 0
        translation_error = 0
        course = courses.Course(None, sites.get_all_courses()[0])
        for unit in course.get_units():
            for lesson in course.get_lessons(unit.unit_id):
                response = self.get('sample/unit?unit=%s&lesson=%s' % (
                    unit.unit_id, lesson.lesson_id))

                self.assertEquals(200, response.status_int)
                self.assertIn(
                    unit.title.swapcase(), response.body.decode('utf-8'))
                self.assertIn(
                    lesson.title.swapcase(), response.body.decode('utf-8'))

                # check standard multibyte character is present
                self.assertIn(u'λ', response.body.decode('utf-8'))

                try:
                    self.assertNotIn('[Invalid question]', response.body)
                except AssertionError:
                    invalid_question += 1
                try:
                    self.assertNotIn('gcb-translation-error', response.body)
                except AssertionError:
                    translation_error += 1

        self.assertEquals((invalid_question, translation_error), (0, 0))

    def test_course_with_one_common_unit_and_two_per_locale_units(self):
        # TODO(psimakov): incomplete
        pass

    def test_readonly(self):
        self._import_sample_course()
        self._setup_locales(course='sample')
        actions.login('test_readonly@example.com', is_admin=True)

        response = self.get('sample/dashboard?action=i18n_dashboard')
        self.assertNotIn('input disabled', response.body)
        self.assertIn('action=i18n_download', response.body)
        self.assertIn('action=i18n_upload', response.body)
        self.assertIn('action=i18n_reverse_case', response.body)
        self.assertIn('action=i18_console', response.body)

        with actions.OverriddenEnvironment(
            {'course': {'prevent_translation_edits': True}}):
            response = self.get('sample/dashboard?action=i18n_dashboard')
            self.assertIn('input disabled', response.body)
            self.assertNotIn('action=i18n_download', response.body)
            self.assertNotIn('action=i18n_upload', response.body)
            self.assertNotIn('action=i18n_reverse_case', response.body)
            self.assertNotIn('action=i18_console', response.body)

    def test_dev_only_button_visibility(self):
        self._import_sample_course()
        extra_env = {
            'extra_locales': [
                {'locale': 'de', 'availability': 'available'},
            ]}
        with actions.OverriddenEnvironment(extra_env):
            response = self.get('sample/dashboard?action=i18n_dashboard')
            self.assertIn('action=i18n_download', response.body)
            self.assertIn('action=i18n_upload', response.body)
            self.assertIn('action=i18n_reverse_case', response.body)

            try:
                appengine_config.PRODUCTION_MODE = True
                response = self.get('sample/dashboard?action=i18n_dashboard')
                self.assertNotIn('action=i18n_download', response.body)
                self.assertNotIn('action=i18n_upload', response.body)
                self.assertNotIn('action=i18n_reverse_case', response.body)
            finally:
                appengine_config.PRODUCTION_MODE = False

    def test_rpc_performance(self):
        """Tests various common actions for the number of memcache/db rpc."""
        self._import_sample_course()

        # add fake 'ln' locale and fake translations
        response = self.get('sample/dashboard?action=i18n_reverse_case')
        self.assertEquals(302, response.status_int)
        response = self.get('sample/dashboard?action=i18n_dashboard')
        self.assertEquals(200, response.status_int)
        self.assertIn('>ln</th>', response.body)

        config.Registry.test_overrides[models.CAN_USE_MEMCACHE.name] = True

        # Need to muck with internals of code under test.
        # pylint: disable=protected-access
        old_memcache_make_async_call = memcache._CLIENT._make_async_call
        old_db_make_rpc_call = datastore_rpc.BaseConnection._make_rpc_call
        try:
            lines = []
            over_quota = [False]

            def _profile(url, hint, quota=(128, 32)):
                """Fetches a URL while counting a number of RPC calls.

                Args:
                  url: URL to fetch
                  hint: hint about this operation to put in the report
                  quota: tuple of max counts of (memcache, db) RPC calls
                    allowed during this request
                """

                counters = [0, 0]
                memcache_stacks = collections.defaultdict(int)
                db_stacks = collections.defaultdict(int)

                def reset():
                    counters[0] = 0
                    counters[1] = 0

                def _memcache_make_async_call(*args, **kwds):
                    memcache_stacks[tuple(traceback.extract_stack())] += 1
                    counters[0] += 1
                    return old_memcache_make_async_call(*args, **kwds)

                def _db_make_rpc_call(*args, **kwds):
                    db_stacks[tuple(traceback.extract_stack())] += 1
                    counters[1] += 1
                    return old_db_make_rpc_call(*args, **kwds)

                def _assert_quota(quota, actual, lines):
                    memcache_quota, db_quota = quota
                    memcache_actual, db_actual = actual
                    respects_quota = True
                    if memcache_quota is not None and (
                        memcache_quota < memcache_actual):
                        respects_quota = False
                    if db_quota is not None and (db_quota < db_actual):
                        respects_quota = False

                    if not respects_quota:
                        over_quota[0] = True
                        lines.append(
                            'Request metrics '
                            '[memcache:%s, db:%s] exceed RPC quota '
                            '[memcache:%s, db:%s]: %s (%s)' % (
                                memcache_actual, db_actual,
                                memcache_quota, db_quota, hint, url))
                        for stacktrace, count in memcache_stacks.iteritems():
                            lines.append('Memcache: %d calls to:' % count)
                            lines += [l.rstrip() for l in
                                      traceback.format_list(stacktrace)]
                        for stacktrace, count in db_stacks.iteritems():
                            lines.append('DB: %d calls to:' % count)
                            lines += [l.rstrip() for l in
                                      traceback.format_list(stacktrace)]

                counters_list = []
                memcache._CLIENT._make_async_call = _memcache_make_async_call
                datastore_rpc.BaseConnection._make_rpc_call = _db_make_rpc_call

                for locale in ['en_US', 'ln']:
                    self._set_prefs_locale(locale, course='sample')

                    memcache.flush_all()
                    app_context = sites.get_all_courses()[0]
                    app_context.clear_per_process_cache()
                    app_context.clear_per_request_cache()

                    for attempt in [0, 1]:
                        reset()
                        response = self.get(url)
                        self.assertEquals(200, response.status_int)
                        actual = [] + counters
                        counters_list.append((actual))
                        if quota is not None and attempt == 1:
                            _assert_quota(quota, actual, lines)

                stats = ' '.join([
                    '[% 4d|% 4d]' % (_memcache, _db)
                    for _memcache, _db in counters_list])
                lines.append('\t{ %s }\t%s (%s)' % (stats, hint, url))

            header = (
                '[memcache|db] for {first load, second load, '
                'first locale load, second locale load}')

            with actions.OverriddenEnvironment(
                {'course': {
                    'now_available': True, 'can_student_change_locale': True}}):

                actions.logout()

                lines.append('RPC Profile, anonymous user %s' % header)
                _profile(
                    '/modules/oeditor/resources/butterbar.js', # deprecated
                    'Butterbar', quota=(0, 0))
                _profile('sample/assets/css/main.css', 'main.css', quota=(6, 0))
                _profile('sample/course', 'Home page', quota=(None, 1))
                _profile(
                    'sample/announcements', 'Announcements', quota=(None, 1))

                actions.login('test_rpc_performance@example.com')
                actions.register(self, 'test_rpc_performance', course='sample')

                lines.append('RPC Profile, registered user %s' % header)
                _profile(
                    '/modules/oeditor/resources/butterbar.js', # deprecated
                    'Butterbar', quota=(0, 0))
                _profile(
                    'sample/assets/css/main.css', 'main.css', quota=(3, 1))
                _profile('sample/course', 'Home page')
                _profile('sample/announcements', 'Announcements')
                _profile('sample/unit?unit=14&lesson=17', 'Lesson 2.2')
                _profile('sample/assessment?name=35', 'Mid-term exam')

                actions.logout()
                actions.login('test_rpc_performance@example.com', is_admin=True)

                lines.append('RPC Profile, admin user %s' % header)
                _profile(
                    '/modules/oeditor/resources/butterbar.js', # deprecated
                    'Butterbar', quota=(0, 0))
                _profile(
                    'sample/assets/css/main.css', 'main.css', quota=(3, 1))
                _profile('sample/course', 'Home page')
                _profile('sample/announcements', 'Announcements')
                _profile('sample/unit?unit=14&lesson=17', 'Lesson 2.2')
                _profile('sample/assessment?name=35', 'Mid-term exam')
                _profile('sample/admin', 'Admin home')
                _profile('sample/admin?action=settings', 'Settings')
                _profile('sample/dashboard', 'Dashboard', quota=(150, 60))
                _profile('sample/dashboard?action=edit_questions',
                    'Questions')
                _profile('sample/dashboard?action=edit_question_groups',
                    'Question Groups')
                _profile(
                    'sample/dashboard?action=i18n_dashboard',
                    'I18N Dashboard')
                _profile('sample/dashboard?action=i18n_download', 'I18N Export')

            logging.info('\n'.join(lines))
            self.assertFalse(over_quota[0], msg='Some items exceed quota.')

        finally:
            memcache._CLIENT._make_async_call = old_memcache_make_async_call
            datastore_rpc.BaseConnection._make_rpc_call = old_db_make_rpc_call
            del config.Registry.test_overrides[models.CAN_USE_MEMCACHE.name]


class FooEntity(object):

    def __init__(self, description):
        self._description = description

    @property
    def description(self):
        return self._description

    @description.setter
    def description(self, value):
        self._description = value


class ResourceHandlerFoo(resource.AbstractResourceHandler):

    TYPE = 'foo'

    # Nominally should implement all the required methods here, but they
    # are not required for the tests.


class TranslatableResourceFoo(i18n_dashboard.AbstractTranslatableResourceType):

    THE_ENTITY = FooEntity('This is a FooEntity.')
    TYPE = 'foo'

    NOTIFIED_OF_CHANGE_FOR_KEYS = []

    @classmethod
    def get_ordering(cls):
        return i18n_dashboard.TranslatableResourceRegistry.ORDERING_LAST

    @classmethod
    def get_title(cls):
        return 'Foo'

    @classmethod
    def get_resources_and_keys(cls, course):
        return [(cls.THE_ENTITY, resource.Key(cls.TYPE, '1', course))]

    @classmethod
    def get_resource_types(cls):
        return [cls.TYPE]

    @classmethod
    def notify_translations_changed(cls, key):
        cls.NOTIFIED_OF_CHANGE_FOR_KEYS.append(key)


class NotificationTests(actions.TestBase):

    COURSE = 'notifications'
    NAMESPACE = 'ns_%s' % COURSE
    ADMIN_EMAIL = 'admin@foo.com'
    URL = 'rest/modules/i18n_dashboard/translation_console'

    def setUp(self):
        super(NotificationTests, self).setUp()
        actions.simple_add_course(self.COURSE, self.ADMIN_EMAIL, 'Notification')
        self.old_namespace = namespace_manager.get_namespace()
        namespace_manager.set_namespace('ns_%s' % self.COURSE)
        actions.login(self.ADMIN_EMAIL, is_admin=True)
        TranslatableResourceFoo.NOTIFIED_OF_CHANGE_FOR_KEYS = []
        resource.Registry.register(ResourceHandlerFoo)
        i18n_dashboard.TranslatableResourceRegistry.register(
            TranslatableResourceFoo)

    def tearDown(self):
        namespace_manager.set_namespace(self.old_namespace)
        sites.reset_courses()
        i18n_dashboard.TranslatableResourceRegistry.unregister(
            TranslatableResourceFoo)
        resource.Registry.unregister(ResourceHandlerFoo)
        super(NotificationTests, self).tearDown()

    def _put_translations(self, key, translations):
        request = {
            'key': str(key),
            'xsrf_token': crypto.XsrfTokenManager.create_xsrf_token(
                'translation-console'),
                  'payload': transforms.dumps(translations),
                  'validate': True}

        response = self.put(self.URL, {'request': transforms.dumps(request)})
        self.assertEquals(200, response.status_int)
        response = transforms.loads(response.body)
        self.assertEquals(200, response['status'])
        payload = transforms.loads(response['payload'])
        return payload

    def test_notifications(self):
        key = i18n_dashboard.ResourceBundleKey(
            TranslatableResourceFoo.TYPE, '1', 'de')
        self._put_translations(key, {
            'title': 'Foo',
            'key': str(key),
            'source_locale': 'en_US',
            'target_locale': 'de',
            'sections': [{
                'name': 'description',
                'label': 'Description',
                'type': 'string',
                'source_value': '',
                'data': [{
                    'source_value': 'old description',
                    'target_value': 'new description',
                    'verb': 1,  # verb NEW
                    'old_source_value': '',
                    'changed': True
                }]
            }]
        })

        # Verify that we got notified about the change to our resource's
        # translation bundle
        self.assertEquals(
            [str(key)],
            [str(k) for k in
             TranslatableResourceFoo.NOTIFIED_OF_CHANGE_FOR_KEYS])
