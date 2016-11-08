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

"""Verify operation of custom tags from core_tags module."""

__author__ = 'Mike Gainer (mgainer@google.com)'

import os
import StringIO

import appengine_config
from controllers import sites
from models import config
from models import courses
from models import models
from models import transforms
from modules.core_tags import core_tags
from tests.functional import actions

COURSE_NAME = 'test_course'
COURSE_TITLE = 'Test Course'
ADMIN_EMAIL = 'test@example.com'
PRE_INCLUDE = 'XXX'
POST_INCLUDE = 'YYY'
HTML_DIR = os.path.join(appengine_config.BUNDLE_ROOT, 'assets/html')
HTML_FILE = 'test.html'
HTML_PATH = os.path.join(HTML_DIR, HTML_FILE)
GCB_INCLUDE = (PRE_INCLUDE +
               '<gcb-include path="/assets/html/%s" ' +
               'instanceid="uODxjWHTxxIC"></gcb-include>' +
               POST_INCLUDE)
LESSON_URL = '/test_course/unit?unit=1&lesson=2'


class GoogleDriveTestBase(actions.TestBase):

    def tearDown(self):
        config.Registry.test_overrides = {}
        super(GoogleDriveTestBase, self).tearDown()

    def get_env(self, api_key=None, client_id=None):
        # Treat as module-protected. pylint: disable=protected-access
        result = {
            courses._CONFIG_KEY_PART_COURSE: {
                courses._CONFIG_KEY_PART_GOOGLE: {}
            }
        }
        google_config = result.get(
            courses._CONFIG_KEY_PART_COURSE
        ).get(
            courses._CONFIG_KEY_PART_GOOGLE)

        if api_key is not None:
            google_config[courses._CONFIG_KEY_PART_API_KEY] = api_key

        if client_id is not None:
            google_config[courses._CONFIG_KEY_PART_CLIENT_ID] = client_id

        return result


class RuntimeTest(GoogleDriveTestBase):

    def setUp(self):
        super(RuntimeTest, self).setUp()
        self.app_context = sites.get_all_courses()[0]
        self.api_key = 'api_key_value'
        self.client_id = 'client_id_value'
        self.email = 'admin@example.com'

    def tearDown(self):
        config.Registry.test_overrides = {}
        super(RuntimeTest, self).tearDown()

    def test_can_edit_false_if_user_is_not_logged_in(self):
        # Treat as module-protected. pylint: disable=protected-access
        self.assertFalse(core_tags._Runtime(self.app_context).can_edit())

    def test_can_edit_false_if_user_is_not_admin(self):
        actions.login(self.email, is_admin=False)

        # Treat as module-protected. pylint: disable=protected-access
        self.assertFalse(core_tags._Runtime(self.app_context).can_edit())

    def test_can_edit_true_if_user_is_admin(self):
        actions.login(self.email, is_admin=True)
        # Treat as module-protected. pylint: disable=protected-access
        runtime = core_tags._Runtime(self.app_context)

        self.assertTrue(runtime.can_edit())

    def test_configured_false_when_api_key_empty(self):
        with actions.OverriddenEnvironment(self.get_env(
                client_id=self.client_id)):
            # Treat as module-protected. pylint: disable=protected-access
            self.assertFalse(core_tags._Runtime(self.app_context).configured())

    def test_configured_false_when_client_id_empty(self):
        with actions.OverriddenEnvironment(self.get_env(
                api_key=self.api_key)):
            # Treat as module-protected. pylint: disable=protected-access
            self.assertFalse(core_tags._Runtime(self.app_context).configured())

    def test_configured_true_when_enabled_and_api_key_and_client_id_set(self):
        with actions.OverriddenEnvironment(self.get_env(
                api_key=self.api_key, client_id=self.client_id)):
            # Treat as module-protected. pylint: disable=protected-access
            self.assertTrue(core_tags._Runtime(self.app_context).configured())

    def test_get_api_key_returns_empty_string_when_not_set(self):
        # Treat as module-protected. pylint: disable=protected-access
        self.assertEqual('', core_tags._Runtime(self.app_context).get_api_key())

    def test_get_api_key_returns_expected_value_when_set(self):
        with actions.OverriddenEnvironment(self.get_env(api_key=self.api_key)):
            # Treat as module-protected. pylint: disable=protected-access
            self.assertEqual(
                self.api_key,
                core_tags._Runtime(self.app_context).get_api_key())

    def test_get_client_id_returns_empty_string_when_not_set(self):
        # Treat as module-protected. pylint: disable=protected-access
        self.assertEqual(
            '', core_tags._Runtime(self.app_context).get_client_id())

    def test_get_client_id_returns_expected_value_when_set(self):
        with actions.OverriddenEnvironment(self.get_env(
                client_id=self.client_id)):
            # Treat as module-protected. pylint: disable=protected-access
            self.assertEqual(
                self.client_id,
                core_tags._Runtime(self.app_context).get_client_id())


class GoogleDriveRESTHandlerTest(GoogleDriveTestBase):

    def setUp(self):
        super(GoogleDriveRESTHandlerTest, self).setUp()
        self.content_type = 'text/html'
        self.contents = 'contents_value'
        self.document_id = 'document_id_value'
        self.type_id = 'type_id_value'
        self.xsrf_token = core_tags.GoogleDriveRESTHandler.get_xsrf_token()
        self.uid = models.ContentChunkDAO.make_uid(
            self.type_id, self.document_id)

    def assert_response(self, code, body_needle, response):
        from_json = transforms.loads(response.body)

        self.assertEqual(200, response.status_code)
        self.assertEqual(code, from_json['status'])
        self.assertIn(body_needle, from_json['message'])

    def assert_200_response(self, response):
        self.assert_response(200, 'Success.', response)

    def assert_400_response_type_id_not_set(self, response):
        self.assert_response(400, 'type_id not set', response)

    def assert_400_response_no_item_chosen(self, response):
        self.assert_response(400, 'no Google Drive item chosen', response)

    def assert_403_response(self, response):
        self.assert_response(403, 'Bad XSRF token', response)

    def assert_500_response(self, body_needle, response):
        self.assert_response(500, body_needle, response)

    def _get_payload(self, body):
        return transforms.loads(body)

    def _make_params(self, params):
        return {'request': transforms.dumps(params)}

    def test_put_returns_200_and_creates_new_entity(self):
        params = self._make_params({
            'contents': self.contents,
            'document_id': self.document_id,
            'type_id': self.type_id,
            'xsrf_token': self.xsrf_token,
        })
        # Treat as module-protected. pylint: disable=protected-access
        response = self.testapp.put(
            core_tags._GOOGLE_DRIVE_TAG_PATH, params=params)
        matches = models.ContentChunkDAO.get_by_uid(self.uid)
        created = matches[0]

        self.assert_200_response(response)
        self.assertEqual(1, len(matches))
        self.assertEqual(self.contents, created.contents)
        self.assertEqual(self.document_id, created.resource_id)
        self.assertEqual(self.type_id, created.type_id)

    def test_put_returns_200_and_updates_existing_entity(self):
        models.ContentChunkDAO.save(models.ContentChunkDTO({
            'content_type': 'old_' + self.content_type,
            'contents': 'old_' + self.contents,
            'resource_id': self.document_id,
            'type_id': self.type_id,
        }))
        params = self._make_params({
            'contents': self.contents,
            'document_id': self.document_id,
            'type_id': self.type_id,
            'xsrf_token': self.xsrf_token,
        })
        old_dto = models.ContentChunkDAO.get_by_uid(self.uid)[0]

        self.assertEqual('old_' + self.contents, old_dto.contents)
        self.assertEqual('old_' + self.content_type, old_dto.content_type)

        # Treat as module-protected. pylint: disable=protected-access
        response = self.testapp.put(
            core_tags._GOOGLE_DRIVE_TAG_PATH, params=params)
        matches = models.ContentChunkDAO.get_by_uid(self.uid)
        created = matches[0]

        self.assert_200_response(response)
        self.assertEqual(1, len(matches))
        self.assertEqual(self.contents, created.contents)
        self.assertEqual(self.document_id, created.resource_id)
        self.assertEqual(self.type_id, created.type_id)

    def test_put_returns_400_if_contents_not_set(self):
        params = self._make_params({
            'document_id': self.document_id,
            'type_id': self.type_id,
            'xsrf_token': self.xsrf_token,
        })
        # Treat as module-protected. pylint: disable=protected-access
        response = self.testapp.put(
            core_tags._GOOGLE_DRIVE_TAG_PATH, expect_errors=True, params=params)

        self.assert_400_response_no_item_chosen(response)

    def test_put_returns_400_if_document_id_not_set(self):
        params = self._make_params({
            'contents': self.contents,
            'type_id': self.type_id,
            'xsrf_token': self.xsrf_token,
        })
        # Treat as module-protected. pylint: disable=protected-access
        response = self.testapp.put(
            core_tags._GOOGLE_DRIVE_TAG_PATH, expect_errors=True, params=params)

        self.assert_400_response_no_item_chosen(response)

    def test_put_returns_400_if_type_id_not_set(self):
        params = self._make_params({
            'contents': self.contents,
            'document_id': self.document_id,
            'xsrf_token': self.xsrf_token,
        })
        # Treat as module-protected. pylint: disable=protected-access
        response = self.testapp.put(
            core_tags._GOOGLE_DRIVE_TAG_PATH, expect_errors=True, params=params)

        self.assert_400_response_type_id_not_set(response)

    def test_put_returns_403_if_xsrf_token_invalid(self):
        params = self._make_params({
            'xsrf_token': 'bad_' + self.xsrf_token,
        })
        # Treat as module-protected. pylint: disable=protected-access
        response = self.testapp.put(
            core_tags._GOOGLE_DRIVE_TAG_PATH, expect_errors=True, params=params)

        self.assert_403_response(response)

    def test_put_returns_500_if_save_throws(self):

        def throw(
                unused_self, unused_contents, unused_type_id,
                unused_document_id):
            raise ValueError('save failed')

        self.swap(
            core_tags.GoogleDriveRESTHandler, '_save_content_chunk', throw)
        params = self._make_params({
            'contents': self.contents,
            'document_id': self.document_id,
            'type_id': self.type_id,
            'xsrf_token': self.xsrf_token,
        })
        # Treat as module-protected. pylint: disable=protected-access
        response = self.testapp.put(
            core_tags._GOOGLE_DRIVE_TAG_PATH, expect_errors=True, params=params)

        self.assert_500_response('save failed', response)


class GoogleDriveTagRendererTest(GoogleDriveTestBase):

    def setUp(self):
        super(GoogleDriveTagRendererTest, self).setUp()
        self.contents = 'contents_value'
        self.resource_id = 'resource_id_value'
        self.type_id = 'type_id_value'
        dto = models.ContentChunkDTO({
            'content_type': 'text/html',
            'contents': self.contents,
            'resource_id': self.resource_id,
            'type_id': self.type_id,
        })
        self.uid = models.ContentChunkDAO.make_uid(
            self.type_id, self.resource_id)
        models.ContentChunkDAO.save(dto)
        self.dto = models.ContentChunkDAO.get_by_uid(self.uid)

    def assert_response(self, code, body_needle, response):
        self.assertEqual(code, response.status_code)
        self.assertIn(body_needle, response.body)

    def assert_200_response(self, body_needle, response):
        self.assert_response(200, body_needle, response)

    def assert_400_response(self, response):
        self.assert_response(400, 'Bad request', response)

    def assert_404_response(self, response):
        self.assert_response(404, 'Content chunk not found', response)

    def test_get_returns_200_if_content_chunk_found(self):
        # Treat as module-protected. pylint: disable=protected-access
        response = self.testapp.get(
            core_tags._GOOGLE_DRIVE_TAG_RENDERER_PATH,
            params={
                'resource_id': self.resource_id,
                'type_id': self.type_id,
        })

        self.assert_200_response(self.contents, response)

    def test_get_returns_200_with_first_chunk_if_multiple_matches(self):
        models.ContentChunkDAO.save(models.ContentChunkDTO({
            'content_type': 'text/html',
            'contents': 'other contents',
            'resource_id': self.resource_id,
            'type_id': self.type_id,
        }))
        # Treat as module-protected. pylint: disable=protected-access
        response = self.testapp.get(
            core_tags._GOOGLE_DRIVE_TAG_RENDERER_PATH,
            params={
                'resource_id': self.resource_id,
                'type_id': self.type_id,
        })

        self.assertEqual(2, len(models.ContentChunkDAO.get_by_uid(self.uid)))
        self.assert_200_response(self.contents, response)

    def test_get_returns_400_if_resource_id_missing(self):
        # Treat as module-protected. pylint: disable=protected-access
        response = self.testapp.get(
            core_tags._GOOGLE_DRIVE_TAG_RENDERER_PATH, expect_errors=True,
            params={'type_id': self.type_id})

        self.assert_400_response(response)

    def test_get_returns_400_if_type_id_missing(self):
        # Treat as module-protected. pylint: disable=protected-access
        response = self.testapp.get(
            core_tags._GOOGLE_DRIVE_TAG_RENDERER_PATH, expect_errors=True,
            params={'resource_id': self.resource_id})

        self.assert_400_response(response)

    def test_get_returns_404_if_content_chunk_not_found(self):
        # Treat as module-protected. pylint: disable=protected-access
        response = self.testapp.get(
            core_tags._GOOGLE_DRIVE_TAG_RENDERER_PATH, expect_errors=True,
            params={
                'type_id': 'other_' + self.type_id,
                'resource_id': 'other_' + self.resource_id,
        })

        self.assert_404_response(response)

    def test_get_tag_renderer_url_for_course_at_root(self):
        # Treat as module-protected. pylint: disable=protected-access
        self.assertEqual(
            '/modules/core_tags/googledrivetagrenderer?'
            'resource_id=resource_id&type_id=type_id',
            core_tags.GoogleDrive._get_tag_renderer_url(
                '/', 'type_id', 'resource_id'))

    def test_get_tag_renderer_url_for_course_with_slug(self):
        # Treat as module-protected. pylint: disable=protected-access
        self.assertEqual(
            '/slug/modules/core_tags/googledrivetagrenderer?'
            'resource_id=resource_id&type_id=type_id',
            core_tags.GoogleDrive._get_tag_renderer_url(
                '/slug', 'type_id', 'resource_id'))


class TagsMarkdown(actions.TestBase):
    def setUp(self):
        super(TagsMarkdown, self).setUp()
        self.context = actions.simple_add_course(COURSE_NAME, ADMIN_EMAIL,
                                                 COURSE_TITLE)
        self.course = courses.Course(None, self.context)
        self.unit = self.course.add_unit()
        self.unit.title = 'The Unit'
        self.unit.availability = courses.AVAILABILITY_AVAILABLE
        self.lesson = self.course.add_lesson(self.unit)
        self.lesson.title = 'The Lesson'
        self.lesson.availability = courses.AVAILABILITY_AVAILABLE
        self.course.save()

    def test_markdown(self):
        self.lesson.objectives = '''
 Welcome to Markdown!

<gcb-markdown instanceid="BHpNAOMuLdMn">
# This is an H1

## This is an H2

This is [an example](http://example.com/ &quot;Title&quot;) inline link.

[This link](http://example.net/) has no title attribute.

 Text attributes *italic*,
 **bold**, `monospace`.

 Shopping list:

   * apples
   * oranges
   * pears

 Numbered list:

   1. apples
   2. oranges
   3. pears
</gcb-markdown><br>'''
        self.course.save()

        response = self.get(LESSON_URL)
        self.assertIn('<h1>This is an H1</h1>', response.body)
        self.assertIn('<h2>This is an H2</h2>', response.body)
        self.assertIn(
            '<p><a href="http://example.net/">This link</a> '
            'has no title attribute.</p>', response.body)
        self.assertIn('<em>italic</em>', response.body)
        self.assertIn('<strong>bold</strong>', response.body)
        self.assertIn('<code>monospace</code>', response.body)
        self.assertIn('<li>apples</li>', response.body)
        self.assertIn('<li>oranges</li>', response.body)
        self.assertIn('<ul>\n<li>apples</li>', response.body)
        self.assertIn('<ol>\n<li>apples</li>', response.body)
        self.assertIn(
            '<p>This is <a href="http://example.com/" title="Title">'
            'an example</a> inline link.</p>', response.body)
        self.assertIn(
            '<link href="/modules/core_tags/_static/css/markdown.css"',
            response.body)

    def test_extensions(self):
        md_using_extensions = """
<gcb-markdown extension="%s">

# The First Section

This is the content for the first section.

# The Second Section

*[CB]: Course Builder
*[MD]: Markdown

CB MD supports the abbreviation extension

</gcb-markdown>"""

        # Expect the extensions to be active
        self.lesson.objectives = md_using_extensions % (
            'markdown.extensions.toc markdown.extensions.abbr')
        self.course.save()

        response = self.get(LESSON_URL)
        dom = self.parse_html_string_to_soup(response.body)
        rendered_md = dom.select_one('.gcb-lesson-content .gcb-markdown')
        # The TOC extension inserted id's on the header tags
        self.assertEqual(
            'The First Section',
            rendered_md.select_one('h1#the-first-section').text)
        # The abbr extension inserted <abbr> tags
        self.assertEqual(
            'MD', rendered_md.select_one('abbr[title="Markdown"]').text)

        # Expect the extensions to be inactive
        self.lesson.objectives = md_using_extensions % ''
        self.course.save()

        response = self.get(LESSON_URL)
        dom = self.parse_html_string_to_soup(response.body)
        rendered_md = dom.select_one('.gcb-lesson-content .gcb-markdown')
        # Expect no id's on the header tags
        self.assertIsNone(rendered_md.select_one('h1#the-first-section'))
        # Expect no <abbr> tags
        self.assertIsNone(rendered_md.select_one('abbr'))


class TagsInclude(actions.TestBase):

    def setUp(self):
        super(TagsInclude, self).setUp()

        self.context = actions.simple_add_course(COURSE_NAME, ADMIN_EMAIL,
                                                 COURSE_TITLE)
        self.course = courses.Course(None, self.context)
        self.unit = self.course.add_unit()
        self.unit.title = 'The Unit'
        self.unit.availability = courses.AVAILABILITY_AVAILABLE
        self.lesson = self.course.add_lesson(self.unit)
        self.lesson.title = 'The Lesson'
        self.lesson.availability = courses.AVAILABILITY_AVAILABLE
        self.lesson.objectives = GCB_INCLUDE % HTML_FILE
        self.course.save()

    def tearDown(self):
        self.context.fs.delete(HTML_PATH)

    def _set_content(self, content):
        self.context.fs.put(HTML_PATH, StringIO.StringIO(content))

    def _expect_content(self, expected, response):
        expected = '%s<div>%s</div>%s' % (PRE_INCLUDE, expected, POST_INCLUDE)
        self.assertIn(expected, response.body)

    def test_missing_file_gives_error(self):
        self.lesson.objectives = GCB_INCLUDE % 'no_such_file.html'
        self.course.save()
        response = self.get(LESSON_URL)
        self.assertIn('Invalid HTML tag: no_such_file.html', response.body)

    def test_file_from_actual_filesystem(self):
        # Note: This has the potential to cause a test flake: Adding an
        # actual file to the filesystem and then removing it may cause
        # ETL tests to complain - they saw the file, then failed to copy
        # it because it went away.
        simple_content = 'Fiery the angels fell'
        if not os.path.isdir(HTML_DIR):
            os.mkdir(HTML_DIR)
        with open(HTML_PATH, 'w') as fp:
            fp.write(simple_content)
        response = self.get(LESSON_URL)
        os.unlink(HTML_PATH)
        self._expect_content(simple_content, response)

    def test_simple(self):
        simple_content = 'Deep thunder rolled around their shores'
        self._set_content(simple_content)
        response = self.get(LESSON_URL)
        self._expect_content(simple_content, response)

    def test_content_containing_tags(self):
        content = '<h1>This is a test</h1><p>This is only a test.</p>'
        self._set_content(content)
        response = self.get(LESSON_URL)
        self._expect_content(content, response)

    def test_jinja_base_path(self):
        content = '{{ base_path }}'
        self._set_content(content)
        response = self.get(LESSON_URL)
        self._expect_content('assets/html', response)

    def test_jinja_course_base(self):
        content = '{{ gcb_course_base }}'
        self._set_content(content)
        response = self.get(LESSON_URL)
        self._expect_content('http://localhost/test_course/', response)

    def test_jinja_course_title(self):
        content = '{{ course_info.course.title }}'
        self._set_content(content)
        response = self.get(LESSON_URL)
        self._expect_content('Test Course', response)

    def test_inclusion(self):
        content = 'Hello, World!'
        sub_path = os.path.join(
            appengine_config.BUNDLE_ROOT, HTML_DIR, 'sub.html')
        self.context.fs.put(sub_path, StringIO.StringIO(content))

        self._set_content('{% include "sub.html" %}')
        try:
            response = self.get(LESSON_URL)
            self._expect_content(content, response)
        finally:
            self.context.fs.delete(sub_path)
