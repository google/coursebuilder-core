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

"""Tests the capability for registered students to invite others."""


__author__ = 'John Orr (jorr@google.com)'

import urlparse

from common import crypto
from models import courses
from models import models
from models import transforms
from modules.invitation import invitation
from modules.notifications import notifications
from modules.unsubscribe import unsubscribe
from tests.functional import actions

from google.appengine.api import namespace_manager


class BaseInvitationTests(actions.TestBase):
    ADMIN_EMAIL = 'admin@foo.com'
    COURSE_NAME = 'invitation_course'
    SENDER_EMAIL = 'sender@foo.com'
    STUDENT_EMAIL = 'student@foo.com'
    STUDENT_NAME = 'A. Student'

    EMAIL_ENV = {
        'course': {
            'invitation_email': {
                'enabled': True,
                'sender_email': SENDER_EMAIL,
                'subject_template': 'Email from {{sender_name}}',
                'body_template':
                    'From {{sender_name}}. Unsubscribe: {{unsubscribe_url}}'}}}

    def setUp(self):
        super(BaseInvitationTests, self).setUp()

        self.base = '/' + self.COURSE_NAME
        context = actions.simple_add_course(
            self.COURSE_NAME, self.ADMIN_EMAIL, 'Invitation Course')
        self.course = courses.Course(None, context)
        self.old_namespace = namespace_manager.get_namespace()
        namespace_manager.set_namespace('ns_%s' % self.COURSE_NAME)
        self._is_registered = False

    def tearDown(self):
        namespace_manager.set_namespace(self.old_namespace)
        super(BaseInvitationTests, self).tearDown()

    def register(self):
        if not self._is_registered:
            actions.login(self.STUDENT_EMAIL, is_admin=False)
            actions.register(self, self.STUDENT_NAME)
            self._is_registered = True


class InvitationHandlerTests(BaseInvitationTests):
    INVITATION_INTENT = 'course_invitation'
    URL = 'modules/invitation'
    REST_URL = 'rest/modules/invitation'

    def setUp(self):
        super(InvitationHandlerTests, self).setUp()

        self.old_send_async = notifications.Manager.send_async
        notifications.Manager.send_async = self._send_async_spy
        self.send_async_count = 0
        self.send_async_call_log = []

    def tearDown(self):
        notifications.Manager.send_async = self.old_send_async
        super(InvitationHandlerTests, self).tearDown()

    def _send_async_spy(self, *args, **kwargs):
        self.send_async_count += 1
        self.send_async_call_log.append({'args': args, 'kwargs': kwargs})

    def test_invitation_panel_unavailable_when_email_is_not_fully_set_up(self):
        self.register()
        for sender_email in ['', 'foo@bar.com']:
            for subject_template in ['', 'the subject']:
                for body_template in ['', 'the body']:
                    email_env = {
                        'course': {
                            'invitation_email': {
                                'sender_email': sender_email,
                                'subject_template': subject_template,
                                'body_template': body_template}}}
                    with actions.OverriddenEnvironment(email_env):
                        response = self.get(self.URL)
                        if sender_email and subject_template and body_template:
                            self.assertEquals(200, response.status_code)
                        else:
                            self.assertEquals(302, response.status_code)
                            self.assertEquals(
                                'http://localhost/invitation_course/course',
                                response.headers['Location'])

    def test_invitation_panel_available_only_for_registered_student(self):
        with actions.OverriddenEnvironment(self.EMAIL_ENV):

            response = self.get(self.URL)
            self.assertEquals(302, response.status_code)
            self.assertEquals(
                'http://localhost/invitation_course/course',
                response.headers['Location'])

            actions.login(self.STUDENT_EMAIL, is_admin=False)
            response = self.get(self.URL)
            self.assertEquals(302, response.status_code)
            self.assertEquals(
                'http://localhost/invitation_course/course',
                response.headers['Location'])

            actions.register(self, self.STUDENT_NAME)
            response = self.get(self.URL)
            self.assertEquals(200, response.status_code)

    def test_invitation_page_content(self):
        self.register()
        with actions.OverriddenEnvironment(self.EMAIL_ENV):
            response = self.get(self.URL)
            self.assertEquals(200, response.status_code)
            dom = self.parse_html_string(response.body)

            # A sample email is displayed
            self.assertIn(
                'Email from A. Student',
                ''.join(dom.find('.//div[@class="subject-line"]').itertext()))
            self.assertIn(
                'From A. Student. Unsubscribe: '
                'http://localhost/invitation_course/modules/unsubscribe',
                dom.find('.//div[@class="email-body"]').text)

    def _post_to_rest_handler(self, request_dict):
        return transforms.loads(self.post(
            self.REST_URL,
            {'request': transforms.dumps(request_dict)}).body)

    def _get_rest_request(self, payload_dict):
        xsrf_token = crypto.XsrfTokenManager.create_xsrf_token(
            'invitation')
        return {
            'xsrf_token': xsrf_token,
            'payload': payload_dict
        }

    def test_rest_handler_requires_xsrf(self):
        response = self._post_to_rest_handler({'xsrf_token': 'BAD TOKEN'})
        self.assertEquals(403, response['status'])

    def test_rest_handler_requires_enrolled_user_in_session(self):
        response = self._post_to_rest_handler(self._get_rest_request({}))
        self.assertEquals(401, response['status'])

        actions.login(self.STUDENT_EMAIL, is_admin=False)
        response = self._post_to_rest_handler(self._get_rest_request({}))
        self.assertEquals(401, response['status'])

    def test_rest_handler_requires_email_available(self):
        self.register()
        response = self._post_to_rest_handler(self._get_rest_request({}))
        self.assertEquals(500, response['status'])

    def _do_valid_email_list_post(self, email_list):
        self.register()
        with actions.OverriddenEnvironment(self.EMAIL_ENV):
            return self._post_to_rest_handler(
                self._get_rest_request({'emailList': ','.join(email_list)}))

    def test_rest_handler_requires_non_empty_email_list(self):
        response = self._do_valid_email_list_post([''])
        self.assertEquals(400, response['status'])
        self.assertEquals('Error: Empty email list', response['message'])

    def test_rest_handler_rejects_bad_email_address(self):
        response = self._do_valid_email_list_post(['bad email'])
        self.assertEquals(400, response['status'])
        self.assertIn('Invalid email "bad email"', response['message'])

    def test_rest_handler_rejects_sending_repeat_invitations(self):
        spammed_email = 'spammed@foo.com'
        response = self._do_valid_email_list_post([spammed_email])
        self.assertEquals(200, response['status'])
        response = self._do_valid_email_list_post([spammed_email])
        self.assertEquals(400, response['status'])
        self.assertIn(
            'You have already sent an invitation email to "spammed@foo.com"',
            response['message'])

    def test_rest_handler_sends_only_one_invitation_to_repeated_addresses(self):
        spammed_email = 'spammed@foo.com'
        response = self._do_valid_email_list_post(
            [spammed_email, spammed_email])
        self.assertEquals(200, response['status'])
        self.assertEquals('OK, 1 messages sent', response['message'])
        self.assertEqual(1, self.send_async_count)

    def test_rest_handler_discretely_does_not_mail_unsubscribed_users(self):
        # For privacy reasons the service should NOT email unsubscribed users,
        # but should report to the requestor that it did.
        unsubscribed_email = 'unsubscribed@foo.com'
        unsubscribe.set_subscribed(unsubscribed_email, False)

        response = self._do_valid_email_list_post([unsubscribed_email])
        self.assertEquals(200, response['status'])
        self.assertEquals('OK, 1 messages sent', response['message'])
        self.assertEqual(0, self.send_async_count)

    def test_rest_handler_discretely_does_not_mail_registered_users(self):
        # To reduce spam the service should NOT email registered users, but for
        # privacy reasons should report to the requestor that it did.
        registered_student = 'some_other_student@foo.com'
        actions.login(registered_student)
        actions.register(self, 'Test User')

        response = self._do_valid_email_list_post([registered_student])
        self.assertEquals(200, response['status'])
        self.assertEquals('OK, 1 messages sent', response['message'])
        self.assertEqual(0, self.send_async_count)

    def test_rest_handler_can_send_invitation(self):
        recipient = 'recipient@foo.com'

        response = self._do_valid_email_list_post([recipient])
        self.assertEquals(200, response['status'])
        self.assertEqual(1, self.send_async_count)
        self.assertEquals(1, len(self.send_async_call_log))

        args = self.send_async_call_log[0]['args']
        kwargs = self.send_async_call_log[0]['kwargs']

        self.assertEquals(5, len(args))
        self.assertEquals(recipient, args[0])
        self.assertEquals(self.SENDER_EMAIL, args[1])
        self.assertEquals(self.INVITATION_INTENT, args[2])
        self.assertIn(
            'From A. Student. Unsubscribe: '
            'http://localhost/invitation_course/modules/unsubscribe',
            args[3])
        self.assertEquals('Email from A. Student', args[4])

    def test_rest_handler_can_send_multiple_invitations(self):
        email_list = ['a@foo.com', 'b@foo.com', 'c@foo.com']
        response = self._do_valid_email_list_post(email_list)
        self.assertEquals(200, response['status'])
        self.assertEquals('OK, 3 messages sent', response['message'])
        self.assertEqual(3, self.send_async_count)
        self.assertEquals(
            set(email_list),
            {log['args'][0] for log in self.send_async_call_log})

    def test_rest_handler_can_send_some_invitations_but_not_others(self):
        spammed_email = 'spammed@foo.com'
        response = self._do_valid_email_list_post([spammed_email])
        self.assertEquals(200, response['status'])
        self.assertEqual(1, self.send_async_count)

        self.send_async_count = 0

        unsubscribed_email = 'unsubscribed@foo.com'
        unsubscribe.set_subscribed(unsubscribed_email, False)

        response = self._do_valid_email_list_post(
            ['a@foo.com', unsubscribed_email, 'b@foo.com', spammed_email])
        self.assertEquals(400, response['status'])
        self.assertIn('Not all messages were sent (3 / 4)', response['message'])
        self.assertIn(
            'You have already sent an invitation email to "spammed@foo.com"',
            response['message'])
        self.assertEqual(2, self.send_async_count)

    def test_rest_handler_limits_number_of_invitations(self):
        old_max_emails = invitation.MAX_EMAILS
        invitation.MAX_EMAILS = 2
        try:
            email_list = ['a@foo.com', 'b@foo.com', 'c@foo.com']
            response = self._do_valid_email_list_post(email_list)
            self.assertEquals(200, response['status'])
            self.assertEquals(
                'This exceeds your email cap. '
                'Number of remaining invitations: 2. '
                'No messages sent.', response['message'])
            self.assertEqual(0, self.send_async_count)
        finally:
            invitation.MAX_EMAILS = old_max_emails


class ProfileViewInvitationTests(BaseInvitationTests):
    URL = 'student/home'

    def _find_row(self, dom, title):
        for row in dom.findall('.//table[@class="gcb-student-data-table"]//tr'):
            if row.find('th').text == title:
                return row
        return None

    def test_invitation_row_supressed_if_invitations_disabled(self):
        email_env = {'course': {'invitation_email': {'enabled': False}}}
        with actions.OverriddenEnvironment(email_env):
            self.register()
            dom = self.parse_html_string(self.get(self.URL).body)
            self.assertIsNone(self._find_row(dom, 'Invite Friends'))
            self.assertIsNotNone(self._find_row(dom, 'Subscribe/Unsubscribe'))

    def test_invitation_link_supressed_if_email_not_configured(self):
        email_env = {'course': {'invitation_email': {'enabled': True}}}
        with actions.OverriddenEnvironment(email_env):
            self.register()
            dom = self.parse_html_string(self.get(self.URL).body)
            invite_friends_row = self._find_row(dom, 'Invite Friends')
            td = invite_friends_row.find('td')
            self.assertEquals('Invitations not currently available', td.text)

    def test_invitation_link_shown(self):
        self.register()
        with actions.OverriddenEnvironment(self.EMAIL_ENV):
            dom = self.parse_html_string(self.get(self.URL).body)
            invite_friends_row = self._find_row(dom, 'Invite Friends')
            link = invite_friends_row.find('td/a')
            self.assertEquals(
                'Click to send invitations to family and friends', link.text)
            self.assertEquals(InvitationHandlerTests.URL, link.attrib['href'])

    def test_unsubscribe_link_shown_to_subscribed_user(self):
        self.register()
        dom = self.parse_html_string(self.get(self.URL).body)
        subscribe_row = self._find_row(dom, 'Subscribe/Unsubscribe')
        td = subscribe_row.find('td')
        self.assertEquals(
            'You are currently receiving course-related emails. ', td.text)
        link = td[0]
        self.assertEquals(
            'Click here to unsubscribe.', link.text)

        unsubscribe_url = urlparse.urlparse(link.attrib['href'])
        self.assertEquals(
            '/invitation_course/modules/unsubscribe', unsubscribe_url.path)
        query = urlparse.parse_qs(unsubscribe_url.query)
        self.assertEquals(self.STUDENT_EMAIL, query['email'][0])
        self.assertFalse('action' in query)

    def test_subscribe_link_shown_to_unsubscribed_user(self):
        self.register()
        unsubscribe.set_subscribed(self.STUDENT_EMAIL, False)

        dom = self.parse_html_string(self.get(self.URL).body)
        subscribe_row = self._find_row(dom, 'Subscribe/Unsubscribe')
        td = subscribe_row.find('td')
        self.assertEquals(
            'You are currently unsubscribed from course-related emails.',
            td.text)
        link = td[0]
        self.assertEquals(
            'Click here to re-subscribe.', link.text)

        unsubscribe_url = urlparse.urlparse(link.attrib['href'])
        self.assertEquals(
            '/invitation_course/modules/unsubscribe', unsubscribe_url.path)
        query = urlparse.parse_qs(unsubscribe_url.query)
        self.assertEquals(self.STUDENT_EMAIL, query['email'][0])
        self.assertEquals('resubscribe', query['action'][0])


class SantitationTests(BaseInvitationTests):

    def transform(self, x):
        return 'tr_' + x

    def test_for_export_transforms_value_for_invitation_student_property(self):
        orig_model = invitation.InvitationStudentProperty.load_or_default(
            models.Student())
        orig_model.append_to_invited_list(['a@foo.com'])
        safe_model = orig_model.for_export(self.transform)
        self.assertEquals('{"email_list": ["tr_a@foo.com"]}', safe_model.value)
