# coding=utf8
# Copyright 2016 Google Inc. All Rights Reserved.
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

"""Course Explorer tests"""

__author__ = 'Nick Retallack (nretallack@google.com)'

import base64
from common import crypto
from models import config
from models import courses
from models import transforms
from modules.courses import constants as courses_constants
from modules.explorer import constants
from modules.explorer import settings
from modules.gql import gql_tests
from modules.gql import gql
from tests.functional import actions


class GraphQLTests(gql_tests.BaseGqlTests):
    COURSE_NAME = 'course'
    ADMIN_EMAIL = 'admin@example.com'

    def setUp(self):
        super(GraphQLTests, self).setUp()
        config.Registry.test_overrides.update({
            gql.GQL_SERVICE_ENABLED.name: True,
        })

        self.base = '/' + self.COURSE_NAME
        self.course_id = gql_tests.get_course_id(self.base)
        self.app_context = actions.simple_add_course(
            self.COURSE_NAME, self.ADMIN_EMAIL, 'Course')

    def tearDown(self):
        config.Registry.test_overrides = {}
        super(GraphQLTests, self).tearDown()

    def test_settings_values(self):
        entity = config.ConfigPropertyEntity(
            key_name=settings.COURSE_EXPLORER_SETTINGS.name)
        entity.value = transforms.dumps({
            'title': 'The Title',
            'logo_alt_text': 'alt',
            'institution_name': u'🐱Institution',
            'institution_url': 'http://example.com',
            'logo_bytes_base64': 'logo-contents',
            'logo_mime_type': 'image/png',
        })
        entity.is_draft = False
        entity.put()

        self.assertEqual(
            self.get_response("""
            {
                site {
                    title,
                    logo {
                        url,
                        altText
                    },
                    courseExplorer {
                        extraContent
                    }
                }
            }
            """),
            {
                'errors': [],
                'data': {
                    'site': {
                        'title': 'The Title',
                        'logo': {
                            'url': 'data:image/png;base64,logo-contents',
                            'altText': 'alt',
                        },
                        'courseExplorer': {
                            'extraContent': None,
                        }
                    }
                }
            }
        )

    def test_course_fields(self):
        app_context = actions.update_course_config_as_admin(
            self.COURSE_NAME, self.ADMIN_EMAIL, {
                'course': {
                    courses_constants.START_DATE_SETTING:
                        '2016-05-11T07:00:00.000Z',
                    courses_constants.END_DATE_SETTING:
                        '2016-10-11T07:00:00.000Z',
                    'estimated_workload': '10hrs',
                    'category_name': 'Biology',
                    'show_in_explorer': False,
                },
            })
        self.maxDiff = None
        self.assertEqual(
            self.get_response("""
            {
                course (id: "%s") {
                    startDate,
                    endDate,
                    estimatedWorkload,
                    category {name},
                    showInExplorer,
                }
            }
            """ % self.course_id),
            {
                'errors': [],
                'data': {
                    'course': {
                        'startDate': '2016-05-11T07:00:00.000Z',
                        'endDate': '2016-10-11T07:00:00.000Z',
                        'estimatedWorkload': '10hrs',
                        'category': {
                            'name': 'Biology',
                        },
                        'showInExplorer': False,
                    }
                }
            })


class CourseExplorerSettingsTest(actions.TestBase):
    ADMIN_EMAIL = 'test@example.com'
    COURSE_NAME = 'course'

    def setUp(self):
        super(CourseExplorerSettingsTest, self).setUp()
        actions.login(self.ADMIN_EMAIL, is_admin=True)
        self.app_context = actions.simple_add_course(
            self.COURSE_NAME, self.ADMIN_EMAIL, 'Course')
        self.base = '/{}'.format(self.COURSE_NAME)

    def post_settings(self, payload, upload_files=None):
        response = self.post('rest/explorer-settings', {
            'request': transforms.dumps({
                'xsrf_token': crypto.XsrfTokenManager.create_xsrf_token(
                    'explorer-settings-rest'),
                'payload': transforms.dumps(payload),
            })
        }, upload_files=upload_files)
        self.assertEqual(response.status_code, 200)
        return response

    # tests

    def test_visit_page(self):
        self.assertEqual(self.get('explorer-settings').status_code, 200)
        self.assertEqual(
            transforms.loads(self.get('rest/explorer-settings').body)['status'],
            200)

    def test_without_icon(self):
        self.post_settings({
            'title': 'The Title',
            'logo': '',
            'logo_alt_text': 'alt',
            'institution_name': u'🐱Institution',
            'institution_url': 'http://example.com',
        })

        self.assertEqual(
            transforms.loads(settings.COURSE_EXPLORER_SETTINGS.value), {
            'title': 'The Title',
            'logo_alt_text': 'alt',
            'institution_name': u'🐱Institution',
            'institution_url': 'http://example.com',
        })

    def test_with_icon(self):
        contents = 'File Contents!'
        encoded_contents = base64.b64encode(contents)

        self.post_settings({
            'title': 'The Title',
            'logo': 'icon.png',
            'logo_alt_text': 'alt',
            'institution_name': u'🐱Institution',
            'institution_url': 'http://example.com',
        }, upload_files=[('logo', 'icon.png', contents)])

        self.assertEqual(
            transforms.loads(settings.COURSE_EXPLORER_SETTINGS.value), {
            'title': 'The Title',
            'logo_alt_text': 'alt',
            'institution_name': u'🐱Institution',
            'institution_url': 'http://example.com',
            'logo_bytes_base64': encoded_contents,
            'logo_mime_type': 'image/png',
        })

    def test_dont_lose_existing_icon(self):
        entity = config.ConfigPropertyEntity(
            key_name=settings.COURSE_EXPLORER_SETTINGS.name)
        entity.value = transforms.dumps({
            'title': 'The Title',
            'logo_alt_text': 'alt',
            'institution_name': u'🐱Institution',
            'institution_url': 'http://example.com',
            'logo_bytes_base64': 'logo-contents',
            'logo_mime_type': 'image/png',
        })
        entity.is_draft = False
        entity.put()

        self.post_settings({
            'title': 'Another Title',
            'logo': '',
            'logo_alt_text': 'alt',
            'institution_name': u'New 🐱Institution',
            'institution_url': 'http://example.com',
        })

        self.assertEqual(
            transforms.loads(settings.COURSE_EXPLORER_SETTINGS.value), {
            'title': 'Another Title',
            'logo_alt_text': 'alt',
            'institution_name': u'New 🐱Institution',
            'institution_url': 'http://example.com',
            'logo_bytes_base64': 'logo-contents',
            'logo_mime_type': 'image/png',
        })

    def _verify_course_list_state(self, expected):
        response = self.get('/modules/admin')
        soup = self.parse_html_string_to_soup(response.body)
        row = soup.select('tr[data-course-namespace="ns_%s"]' %
                          self.COURSE_NAME)
        actual = row[0].select('.show_in_explorer')[0].text
        self.assertEquals(expected, actual)

    def test_course_list_text(self):
        course = courses.Course.get(self.app_context)

        # show_in_explorer setting not explicitly set - do we default to True?
        self._verify_course_list_state('Yes')

        # Explicitly set show_in_explorer to True.
        with actions.OverriddenEnvironment(
            {'course': {constants.SHOW_IN_EXPLORER: True}}):
            self._verify_course_list_state('Yes')

        # Explicitly set show_in_explorer to False
        with actions.OverriddenEnvironment(
            {'course': {constants.SHOW_IN_EXPLORER: False}}):
            self._verify_course_list_state('No')


class CourseExplorerEnabledTest(actions.TestBase):

    def setUp(self):
        super(CourseExplorerEnabledTest, self).setUp()
        config.Registry.test_overrides.update({
            settings.GCB_ENABLE_COURSE_EXPLORER_PAGE.name: True,
            gql.GQL_SERVICE_ENABLED.name: True,
        })

    def tearDown(self):
        config.Registry.test_overrides = {}
        super(CourseExplorerEnabledTest, self).tearDown()

    def test_front_page(self):
        response = self.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('<course-explorer></course-explorer>', response.body)


class CourseExplorerDisabledTest(actions.TestBase):
    def test_disabled(self):
        response = self.get('/')
        self.assertNotIn('<course-explorer></course-explorer>', response.body)
