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

from common import utils
from controllers import sites
from models import courses
from modules.unsubscribe import unsubscribe
from tests.functional import actions

from google.appengine.ext import db


class BaseUnsubscribeTests(actions.TestBase):

    def assertUnsubscribed(self, email, namespace):
        with utils.Namespace(namespace):
            self.assertTrue(unsubscribe.has_unsubscribed(email))

    def assertSubscribed(self, email, namespace):
        with utils.Namespace(namespace):
            self.assertFalse(unsubscribe.has_unsubscribed(email))


class GetUnsubscribeUrlTests(actions.TestBase):

    def test_get_unsubscribe_url(self):
        handler = actions.MockHandler(
            app_context=actions.MockAppContext(slug='new_course'))
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

    def setUp(self):
        super(SubscribeAndUnsubscribeTests, self).setUp()
        self.namespace = 'namespace'

    def test_subscription_state_never_set(self):
        with utils.Namespace(self.namespace):
            self.assertSubscribed(self.EMAIL, self.namespace)

    def test_set_subscription_state(self):
        with utils.Namespace(self.namespace):
            unsubscribe.set_subscribed(self.EMAIL, False)
            self.assertUnsubscribed(self.EMAIL, self.namespace)

    def test_set_then_unset_subscription_state(self):
        with utils.Namespace(self.namespace):
            self.assertSubscribed(self.EMAIL, self.namespace)
            unsubscribe.set_subscribed(self.EMAIL, True)
            self.assertSubscribed(self.EMAIL, self.namespace)
            unsubscribe.set_subscribed(self.EMAIL, False)
            self.assertUnsubscribed(self.EMAIL, self.namespace)

    def test_subscription_state_entity_must_have_key_name(self):
        with self.assertRaises(db.BadValueError):
            unsubscribe.SubscriptionStateEntity()

        with self.assertRaises(db.BadValueError):
            unsubscribe.SubscriptionStateEntity(id='23')


class UnsubscribeHandlerTests(BaseUnsubscribeTests):

    def setUp(self):
        super(UnsubscribeHandlerTests, self).setUp()
        self.base = '/a'
        self.namespace = 'ns_a'
        sites.setup_courses('course:/a::ns_a')
        self.app_context = actions.MockAppContext(
            namespace=self.namespace, slug='a')
        self.handler = actions.MockHandler(
            base_href='http://localhost/',
            app_context=self.app_context)
        self.email = 'test@example.com'
        actions.login(self.email, is_admin=True)

    def test_unsubscribe_and_resubscribe(self):
        self.assertSubscribed(self.email, self.namespace)

        unsubscribe_url = unsubscribe.get_unsubscribe_url(
            self.handler, self.email)
        response = self.get(unsubscribe_url)

        # Confirm the user has unsubscribed
        self.assertUnsubscribed(self.email, self.namespace)

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
        self.assertSubscribed(self.email, self.namespace)

        # Confirm the page content of the response
        root = self.parse_html_string(response.body).find(
            './/*[@id="resubscribe-message"]')

        confirm_elt = root.find('./p[1]')
        self.assertTrue('has been subscribed' in confirm_elt.text)

        email_elt = root.find('.//div[1]')
        self.assertEquals(self.email, email_elt.text.strip())

    def test_bad_signature_rejected_with_401(self):
        response = self.get(
            'modules/unsubscribe'
            '?email=test%40example.com&s=bad_signature',
            expect_errors=True)
        self.assertEquals(401, response.status_code)

    def test_unsubscribe_request_with_no_email_prompts_for_login(self):
        actions.logout()
        course = courses.Course(None, app_context=sites.get_all_courses()[0])
        course.set_course_availability(courses.COURSE_AVAILABILITY_PUBLIC)
        response = self.get('modules/unsubscribe')
        self.assertEquals(302, response.status_int)
        self.assertEquals(
            'https://www.google.com/accounts/Login'
            '?continue=http%3A//localhost/a/modules/unsubscribe',
            response.headers['Location'])

    def test_unsubscribe_with_no_email_and_in_session(self):
        response = self.get('modules/unsubscribe')

        # Confirm the user has unsubscribed
        self.assertUnsubscribed(self.email, self.namespace)

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
        self.assertSubscribed(self.email, self.namespace)

    def test_analytics_are_suppressed_on_unsubscribe_page(self):
        with actions.OverriddenEnvironment(
            {'course': {'google_analytics_id': '12345',
                        'google_tag_manager_id': '67890'}}):
            response = self.get('modules/unsubscribe')
            self.assertNotIn('GoogleAnalyticsObject', response.body)
            self.assertNotIn('Google Tag Manager', response.body)
