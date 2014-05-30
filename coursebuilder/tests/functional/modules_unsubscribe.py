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

"""Tests for the module to support users unsubscribing from notifications."""

__author__ = 'John Orr (jorr@google.com)'

import urlparse

from controllers import sites
from modules.unsubscribe import unsubscribe
from tests.functional import actions

from google.appengine.ext import db


class BaseUnsubscribeTests(actions.TestBase):

    def assertUnsubscribed(self, email):
        self.assertTrue(unsubscribe.has_unsubscribed(email))

    def assertSubscribed(self, email):
        self.assertFalse(unsubscribe.has_unsubscribed(email))


class GetUnsubscribeUrlTests(actions.TestBase):

    def test_get_unsubscribe_url_fails_if_no_secret_set(self):
        with self.assertRaises(AssertionError):
            unsubscribe.get_unsubscribe_url(
                actions.MockHandler(), 'test@example.com')

    def test_get_unsubscribe_url_fails_if_secret_key_too_short(self):
        app_context = actions.MockAppContext(environ={
            'modules': {
                'unsubscribe': {
                    'key': 'x' * 15}}})
        handler = actions.MockHandler(app_context=app_context)
        with self.assertRaises(AssertionError):
            unsubscribe.get_unsubscribe_url(handler, 'test@example.com')

    def test_get_unsubscribe_url_fails_if_secret_key_too_long(self):
        app_context = actions.MockAppContext(environ={
            'modules': {
                'unsubscribe': {
                    'key': 'x' * 65}}})
        handler = actions.MockHandler(app_context=app_context)
        with self.assertRaises(AssertionError):
            unsubscribe.get_unsubscribe_url(handler, 'test@example.com')

    def test_get_unsubscribe_url(self):
        app_context = actions.MockAppContext(environ={
            'modules': {
                'unsubscribe': {
                    'key': 'a_good_secret_key'}}})
        handler = actions.MockHandler(app_context=app_context)
        url = unsubscribe.get_unsubscribe_url(handler, 'test@example.com')
        parsed_url = urlparse.urlparse(url)
        self.assertEquals('http', parsed_url.scheme)
        self.assertEquals('mycourse.appspot.com', parsed_url.netloc)
        self.assertEquals('/new_course/modules/unsubscribe', parsed_url.path)
        query_dict = urlparse.parse_qs(parsed_url.query)
        self.assertEquals(['test@example.com'], query_dict['email'])
        self.assertRegexpMatches(query_dict['s'][0], r'[0-9a-f]{32}')


class SubscribeAndUnsubscribeTests(BaseUnsubscribeTests):
    EMAIL = 'test@example.com'

    def test_subscription_state_never_set(self):
        self.assertSubscribed(self.EMAIL)

    def test_set_subscription_state(self):
        unsubscribe.set_subscribed(self.EMAIL, False)
        self.assertUnsubscribed(self.EMAIL)

    def test_set_then_unset_subscription_state(self):
        self.assertSubscribed(self.EMAIL)
        unsubscribe.set_subscribed(self.EMAIL, True)
        self.assertSubscribed(self.EMAIL)
        unsubscribe.set_subscribed(self.EMAIL, False)
        self.assertUnsubscribed(self.EMAIL)

    def test_subscription_state_entity_must_have_key_name(self):
        with self.assertRaises(db.BadValueError):
            unsubscribe.SubscriptionStateEntity()

        with self.assertRaises(db.BadValueError):
            unsubscribe.SubscriptionStateEntity(id='23')


class UnsubscribeHandlerTests(BaseUnsubscribeTests):

    def setUp(self):
        def get_environ_new(cxt):
            environ = self.get_environ_old(cxt)
            environ['modules'] = {
                'unsubscribe': {'key': 'a_good_secret_key'}}
            return environ

        super(UnsubscribeHandlerTests, self).setUp()
        self.get_environ_old = sites.ApplicationContext.get_environ
        sites.ApplicationContext.get_environ = get_environ_new

        self.app_context = actions.MockAppContext(environ={
            'modules': {
                'unsubscribe': {
                    'key': 'a_good_secret_key'}}})
        self.handler = actions.MockHandler(
            base_href='http://localhost/',
            app_context=self.app_context)
        self.email = 'test@example.com'

    def tearDown(self):
        sites.ApplicationContext.get_environ = self.get_environ_old
        super(UnsubscribeHandlerTests, self).tearDown()

    def test_unsubscribe_and_resubscribe(self):
        self.assertSubscribed(self.email)

        unsubscribe_url = unsubscribe.get_unsubscribe_url(
            self.handler, self.email)
        response = self.get(unsubscribe_url)

        # Confirm the user has unsubscribed
        self.assertUnsubscribed(self.email)

        # Confirm the page content of the response
        root = self.parse_html_string(response.body).find(
            './/*[@id="unsubscribe-message"]')

        confirm_elt = root.find('./p[1]')
        self.assertTrue('has been unsubscribed' in confirm_elt.text)

        email_elt = root.find('.//div[1]')
        self.assertEquals(self.email, email_elt.text.strip())

        resubscribe_url = root.find('.//div[2]/button').attrib[
            'data-resubscribe-url']

        response = self.get(resubscribe_url)

        # Confirm the user has now resubscribed
        self.assertSubscribed(self.email)

        # Confirm the page content of the response
        root = self.parse_html_string(response.body).find(
            './/*[@id="resubscribe-message"]')

        confirm_elt = root.find('./p[1]')
        self.assertTrue('has been subscribed' in confirm_elt.text)

        email_elt = root.find('.//div[1]')
        self.assertEquals(self.email, email_elt.text.strip())

    def test_bad_signature_rejected_with_401(self):
        response = self.get(
            'http://localhost/modules/unsubscribe'
            '?email=test%40example.com&s=bad_signature',
            expect_errors=True)
        self.assertEquals(401, response.status_code)
