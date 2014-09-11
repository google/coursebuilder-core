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

import unittest

from common import crypto
from models import courses
from models import models
from models import transforms
from modules.i18n_dashboard.i18n_dashboard import I18nProgressDAO
from modules.i18n_dashboard.i18n_dashboard import I18nProgressDTO
from modules.i18n_dashboard.i18n_dashboard import ResourceBundleDAO
from modules.i18n_dashboard.i18n_dashboard import ResourceBundleDTO
from modules.i18n_dashboard.i18n_dashboard import ResourceBundleKey
from modules.i18n_dashboard.i18n_dashboard import ResourceKey
from modules.i18n_dashboard.i18n_dashboard import ResourceRow
from modules.i18n_dashboard.i18n_dashboard import VERB_CHANGED
from modules.i18n_dashboard.i18n_dashboard import VERB_CURRENT
from modules.i18n_dashboard.i18n_dashboard import VERB_NEW
from tests.functional import actions

from google.appengine.api import namespace_manager


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
        namespace_manager.set_namespace(self.old_namespace)
        super(I18nDashboardHandlerTests, self).tearDown()

    def test_page_data(self):
        dom = self.parse_html_string(self.get(self.URL).body)
        table = dom.find('.//table[@class="i18n-progress-table"]')
        rows = table.findall('./tbody/tr')

        expected_row_data = [
            'Course Settings',
            'Course',
            'Registration',
            'Homepage',
            'Units and Lessons',
            'I18N',
            'Invitation',
            'Course Outline',
            'Unit 1 - Test Unit',
            '1.1 Test Lesson',
            'Images and Documents',
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

        lesson_row_index = 9
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
        self.assertEquals(1, len(title_section['data']))
        self.assertEquals(VERB_CURRENT, title_section['data'][0]['verb'])
        self.assertEquals('TEST UNIT', title_section['data'][0]['target_value'])

        # Confirm there is a new description
        description_section = sections[1]
        self.assertEquals('description', description_section['name'])
        self.assertEquals(VERB_NEW, description_section['data'][0]['verb'])

        # Confirm there is a translation for one of the two paragraphs
        header_section = sections[2]
        self.assertEquals('unit_header', header_section['name'])
        self.assertEquals(2, len(header_section['data']))
        self.assertEquals(VERB_CURRENT, header_section['data'][0]['verb'])
        self.assertEquals('a', header_section['data'][0]['source_value'])
        self.assertEquals('a', header_section['data'][0]['old_source_value'])
        self.assertEquals('A', header_section['data'][0]['target_value'])
        self.assertEquals(VERB_NEW, header_section['data'][1]['verb'])

        # Confirm there is a no footer data
        footer_section = sections[3]
        self.assertEquals('unit_footer', footer_section['name'])
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
        self.assertEquals(1, len(title_section['data']))
        self.assertEquals(VERB_CHANGED, title_section['data'][0]['verb'])
        self.assertEquals(
            'OLD TEST UNIT', title_section['data'][0]['target_value'])

        # Confirm there is a new description
        description_section = sections[1]
        self.assertEquals('description', description_section['name'])
        self.assertEquals(VERB_NEW, description_section['data'][0]['verb'])

        # Confirm there is a translation for one of the two paragraphs
        header_section = sections[2]
        self.assertEquals('unit_header', header_section['name'])
        self.assertEquals(2, len(header_section['data']))
        self.assertEquals(VERB_CHANGED, header_section['data'][0]['verb'])
        self.assertEquals('a', header_section['data'][0]['source_value'])
        self.assertEquals('aa', header_section['data'][0]['old_source_value'])
        self.assertEquals('AA', header_section['data'][0]['target_value'])
        self.assertEquals(VERB_NEW, header_section['data'][1]['verb'])

        # Confirm there is a no footer data
        footer_section = sections[3]
        self.assertEquals('unit_footer', footer_section['name'])
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
        self.assertEquals('text<gcb-youtube#1 />', data[0]['source_value'])


class CourseContentTranslationTests(actions.TestBase):
    ADMIN_EMAIL = 'admin@foo.com'
    COURSE_NAME = 'i18n_course'

    def setUp(self):
        super(CourseContentTranslationTests, self).setUp()

        self.base = '/' + self.COURSE_NAME
        app_context = actions.simple_add_course(
            self.COURSE_NAME, self.ADMIN_EMAIL, 'I18N Course')
        self.old_namespace = namespace_manager.get_namespace()
        namespace_manager.set_namespace('ns_%s' % self.COURSE_NAME)

        self.course = courses.Course(None, app_context)
        self.unit = self.course.add_unit()
        self.unit.title = 'Test Unit'
        self.unit.unit_header = '<p>a</p><p>b</p>'

        self.lesson = self.course.add_lesson(self.unit)
        self.lesson.title = 'Test Lesson'
        self.lesson.objectives = '<p>c</p><p>d</p>'

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
        videoid = 'Kdg2drcUjYI'
        unit_header = (
            'text'
            '<gcb-youtube videoid="%s" instanceid="c4CLTDvttJEu">'
            '</gcb-youtube>' % videoid)

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
                        'source_value': 'text<gcb-youtube#1 />',
                        'target_value': 'TEXT<gcb-youtube#1 />'}]
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
        self.assertIn(videoid, main[0][0].attrib['src'])
