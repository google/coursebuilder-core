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

"""Tests for modules/help."""

__author__ = [
    'John Cox (johncox@google.com)',
]

import copy
import os

from common import safe_dom
from models import services
from modules.help_urls import help_urls
from modules.help_urls import topics
from tests.functional import actions


class TestBase(actions.TestBase):

    def setUp(self):
        super(TestBase, self).setUp()
        self.old_topic_registry_map = copy.deepcopy(
            help_urls._TopicRegistry._MAP)
        self.old_topics_all = copy.deepcopy(topics._ALL)

    def tearDown(self):
        topics._ALL = self.old_topics_all
        help_urls._TopicRegistry._MAP = self.old_topic_registry_map
        super(TestBase, self).tearDown()

    def _set_topics(self, mappings):
        topics._ALL = mappings
        help_urls._TopicRegistry._MAP = {}
        help_urls._TopicRegistry.build(topics._ALL)


class RedirectHandlerTest(TestBase):

    def test_all_registered_topic_ids_redirect_to_correct_url(self):
        for key, _ in topics._ALL:
            response = self.get(
                help_urls._REDIRECT_HANDLER_URL + '?topic_id=' + key)

            self.assertEquals(302, response.status_code)
            self.assertEquals(
                help_urls._TopicRegistry.get_url(key), response.location)
            # We don't check that the target of the redirect 200s. This is
            # because those URLs can live outside a system we control, and we
            # don't want our tests to flake if that system has problems.

    def test_400_if_topic_id_not_registered(self):
        response = self.get(
            help_urls._REDIRECT_HANDLER_URL + '?topic_id=not_registered',
            expect_errors=True)

        self.assertEquals(400, response.status_code)
        self.assertLogContains("topic_id 'not_registered' not found")

    def test_400_if_topic_id_not_in_url(self):
        response = self.get(help_urls._REDIRECT_HANDLER_URL, expect_errors=True)

        self.assertEquals(400, response.status_code)
        self.assertLogContains('No topic_id')


class ServicesHelpUrlsTest(TestBase):

    def setUp(self):
        super(ServicesHelpUrlsTest, self).setUp()
        self.default_product_version = os.environ.get('GCB_PRODUCT_VERSION')
        self.old_os_environ = dict(os.environ)

    def tearDown(self):
        os.environ = self.old_os_environ
        super(ServicesHelpUrlsTest, self).tearDown()

    def test_get_for_topic_id_with_legacy_url_uses_verbatim_value(self):
        os.environ['GCB_PRODUCT_VERSION'] = '1.2.3'
        self._set_topics(
            [('topic_id', topics._LegacyUrl('http://example.com'))])

        self.assertEquals(
            'http://example.com', services.help_urls.get('topic_id'))

    def test_get_for_suffix_starting_with_non_slash(self):
        os.environ['GCB_PRODUCT_VERSION'] = '1.2.3'
        self._set_topics([('topic_id', 'suffix')])

        self.assertEquals(
            '%s/%s/%s' % (help_urls._BASE_URL, '1.2', 'suffix'),
            services.help_urls.get('topic_id'))

    def test_get_for_suffix_starting_with_slash(self):
        os.environ['GCB_PRODUCT_VERSION'] = '1.2.3'
        self._set_topics([('topic_id', '/suffix')])

        self.assertEquals(
            '%s/%s/%s' % (help_urls._BASE_URL, '1.2', 'suffix'),
            services.help_urls.get('topic_id'))

    def test_get_version_infix_discards_trailing_zero(self):
        os.environ['GCB_PRODUCT_VERSION'] = '1.0.0'
        self._set_topics([('topic_id', 'suffix')])

        self.assertEquals(
            '%s/%s/%s' % (help_urls._BASE_URL, '1.0', 'suffix'),
            services.help_urls.get('topic_id'))

    def test_get_version_infix_discards_trivial_version(self):
        os.environ['GCB_PRODUCT_VERSION'] = '1.2.3'
        self._set_topics([('topic_id', 'suffix')])

        self.assertEquals(
            '%s/%s/%s' % (help_urls._BASE_URL, '1.2', 'suffix'),
            services.help_urls.get('topic_id'))

    def test_make_learn_more_message_returns_node_list(self):
        os.environ['GCB_PRODUCT_VERSION'] = '1.2.3'
        self._set_topics([('topic_id', 'suffix')])
        node_list = services.help_urls.make_learn_more_message(
            'text', 'topic_id', to_string=False)

        self.assertTrue(isinstance(node_list, safe_dom.NodeList))

        message = str(node_list)

        self.assertIn('text', message)
        self.assertIn(
            '%s?topic_id=%s' % (help_urls._REDIRECT_HANDLER_URL, 'topic_id'),
            message)

    def test_make_learn_more_message_returns_string_by_default(self):
        os.environ['GCB_PRODUCT_VERSION'] = '1.2.3'
        self._set_topics([('topic_id', 'suffix')])
        message = services.help_urls.make_learn_more_message('text', 'topic_id')

        self.assertTrue(isinstance(message, str))
        self.assertIn('text', message)
        self.assertIn(
            '%s?topic_id=%s' % (help_urls._REDIRECT_HANDLER_URL, 'topic_id'),
            message)


class TopicValidationTest(TestBase):

    def test_raises_value_error_if_key_already_registered(self):
        with self.assertRaisesRegexp(
                ValueError,
                'Topic mappings must be unique; "key" already registered'):
            self._set_topics([('key', 'value'), ('key', 'other_value')])

    def test_raises_value_error_if_key_or_value_or_both_falsy(self):
        with self.assertRaisesRegexp(
                ValueError,
                'Topic mapping values must both be set; got "" and "value"'):
            self._set_topics([('', 'value')])

        with self.assertRaisesRegexp(
                ValueError,
                'Topic mapping values must both be set; got "key" and ""'):
            self._set_topics([('key', '')])

        with self.assertRaisesRegexp(
                ValueError,
                'Topic mapping values must both be set; got "None" and "None"'):
            self._set_topics([(None, None)])

    def test_raises_value_error_if_row_wrong_length(self):
        with self.assertRaisesRegexp(
                ValueError, 'Topic row must have exactly 2 items; got 1'):
            self._set_topics([('too_few_items',)])
