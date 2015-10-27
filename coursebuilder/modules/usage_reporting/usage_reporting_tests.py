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

"""Tests for modules/usage_reporting/*"""

__author__ = 'Mike Gainer (mgainer@google.com)'

import collections
import copy
import os
import time
import urlparse

from common import crypto
from common import utils as common_utils
from controllers import sites
from models import courses
from models import models
from models import transforms
from modules.usage_reporting import config
from modules.usage_reporting import course_creation
from modules.usage_reporting import enrollment
from modules.usage_reporting import messaging
from modules.usage_reporting import usage_reporting
from tests.functional import actions

from google.appengine.api import namespace_manager
from google.appengine.api import urlfetch

# pylint: disable=protected-access

ADMIN_EMAIL = 'admin@foo.com'
FAKE_COURSE_ID = 'CCCCCCCCCCCCCCCCCCCCC'
FAKE_INSTALLATION_ID = 'IIIIIIIIIIIIIIIIIIII'
FAKE_TIMESTAMP = 1234567890


class MockSender(messaging.Sender):

    _messages = []

    @classmethod
    def send_message(cls, the_dict):
        cls._messages.append(the_dict)

    @classmethod
    def get_sent(cls):
        return copy.deepcopy(cls._messages)

    @classmethod
    def clear_sent(cls):
        del cls._messages[:]


class MockMessage(messaging.Message):

    @classmethod
    def _get_random_course_id(cls, course):
        return FAKE_COURSE_ID

    @classmethod
    def _get_random_installation_id(cls):
        return FAKE_INSTALLATION_ID

    @classmethod
    def _get_time(cls):
        return FAKE_TIMESTAMP



class UsageReportingTestBase(actions.TestBase):

    def setUp(self):
        super(UsageReportingTestBase, self).setUp()
        self.save_sender = messaging.Sender
        self.save_message = messaging.Message
        messaging.Sender = MockSender
        messaging.Message = MockMessage
        messaging.ENABLED_IN_DEV_FOR_TESTING = True
        actions.login(ADMIN_EMAIL, is_admin=True)

        # If the optional wipeout module is present, it will enforce some
        # requirements that we're not prepared to construct in core
        # Course Builder.  Unilaterally remove its registrations.
        event_callbacks = models.StudentLifecycleObserver.EVENT_CALLBACKS
        for event_type in event_callbacks:
            if 'wipeout' in event_callbacks[event_type]:
                del event_callbacks[event_type]['wipeout']
        enqueue_callbacks = models.StudentLifecycleObserver.EVENT_CALLBACKS
        for event_type in enqueue_callbacks:
            if 'wipeout' in enqueue_callbacks[event_type]:
                del enqueue_callbacks[event_type]['wipeout']

    def tearDown(self):
        MockSender.clear_sent()
        messaging.ENABLED_IN_DEV_FOR_TESTING = False
        messaging.Sender = self.save_sender
        messaging.Message = self.save_message
        sites.reset_courses()
        super(UsageReportingTestBase, self).tearDown()


class ConfigTests(UsageReportingTestBase):

    def test_set_report_allowed(self):
        config.set_report_allowed(True)
        self.assertEquals(True, config.REPORT_ALLOWED.value)

        config.set_report_allowed(False)
        self.assertEquals(False, config.REPORT_ALLOWED.value)

        config.set_report_allowed(True)
        self.assertEquals(True, config.REPORT_ALLOWED.value)

        config.set_report_allowed(False)
        self.assertEquals(False, config.REPORT_ALLOWED.value)

    def test_on_change_report_allowed(self):
        config.set_report_allowed(True)
        config._on_change_report_allowed(config.REPORT_ALLOWED, False)
        config.set_report_allowed(False)
        config._on_change_report_allowed(config.REPORT_ALLOWED, True)

        expected = [{
            messaging.Message._INSTALLATION: FAKE_INSTALLATION_ID,
            messaging.Message._TIMESTAMP: FAKE_TIMESTAMP,
            messaging.Message._VERSION: os.environ['GCB_PRODUCT_VERSION'],
            messaging.Message._METRIC: messaging.Message.METRIC_REPORT_ALLOWED,
            messaging.Message._VALUE: True,
            messaging.Message._SOURCE: messaging.Message.ADMIN_SOURCE,
        }, {
            messaging.Message._INSTALLATION: FAKE_INSTALLATION_ID,
            messaging.Message._TIMESTAMP: FAKE_TIMESTAMP,
            messaging.Message._VERSION: os.environ['GCB_PRODUCT_VERSION'],
            messaging.Message._METRIC: messaging.Message.METRIC_REPORT_ALLOWED,
            messaging.Message._VALUE: False,
            messaging.Message._SOURCE: messaging.Message.ADMIN_SOURCE,
        }]
        self.assertEquals(expected, MockSender.get_sent())

    def test_admin_post_change_report_allowed(self):
        xsrf_token = crypto.XsrfTokenManager.create_xsrf_token(
            'config_override')
        response = self.post(
            '/admin?action=config_override&name=%s' %
            config.REPORT_ALLOWED.name,
            {'xsrf_token': xsrf_token})
        response = self.get('/rest/config/item?key=%s' %
                            config.REPORT_ALLOWED.name)
        payload = {
            'name': config.REPORT_ALLOWED.name,
            'value': True,
            'is_draft': False,
            }
        message = {
            'key': config.REPORT_ALLOWED.name,
            'payload': transforms.dumps(payload),
            'xsrf_token': crypto.XsrfTokenManager.create_xsrf_token(
                'config-property-put'),
            }
        response = self.put('/rest/config/item',
                            {'request': transforms.dumps(message)})
        self.assertEqual(200, response.status_int)

        payload = {
            'name': config.REPORT_ALLOWED.name,
            'value': False,
            'is_draft': False,
            }
        message = {
            'key': config.REPORT_ALLOWED.name,
            'payload': transforms.dumps(payload),
            'xsrf_token': crypto.XsrfTokenManager.create_xsrf_token(
                'config-property-put'),
            }
        response = self.put('/rest/config/item',
                            {'request': transforms.dumps(message)})
        self.assertEqual(200, response.status_int)

        expected = [{
            messaging.Message._INSTALLATION: FAKE_INSTALLATION_ID,
            messaging.Message._TIMESTAMP: FAKE_TIMESTAMP,
            messaging.Message._VERSION: os.environ['GCB_PRODUCT_VERSION'],
            messaging.Message._METRIC: messaging.Message.METRIC_REPORT_ALLOWED,
            messaging.Message._VALUE: True,
            messaging.Message._SOURCE: messaging.Message.ADMIN_SOURCE,
        }, {
            messaging.Message._INSTALLATION: FAKE_INSTALLATION_ID,
            messaging.Message._TIMESTAMP: FAKE_TIMESTAMP,
            messaging.Message._VERSION: os.environ['GCB_PRODUCT_VERSION'],
            messaging.Message._METRIC: messaging.Message.METRIC_REPORT_ALLOWED,
            messaging.Message._VALUE: False,
            messaging.Message._SOURCE: messaging.Message.ADMIN_SOURCE,
        }]
        self.assertEquals(expected, MockSender.get_sent())


class CourseCreationTests(UsageReportingTestBase):

    def test_welcome_page(self):
        with actions.OverriddenConfig(sites.GCB_COURSES_CONFIG.name, ''):
            response = self.get('/admin/welcome')
            self.assertEquals(200, response.status_int)
            self.assertIn('Start Using Course Builder', response.body)
            self.assertIn(
                'I agree that Google may collect information about this',
                response.body)
            self.assertIn(
                'name="%s"' %
                course_creation.USAGE_REPORTING_CONSENT_CHECKBOX_NAME,
                response.body)

    def test_welcome_page_checkbox_state(self):
        # Expect checkbox checked when no setting made
        dom = self.parse_html_string(self.get('/admin/welcome').body)
        checkbox = dom.find('.//input[@type="checkbox"]')
        self.assertEqual('checked', checkbox.attrib['checked'])

        # Expect checkbox unchecked when setting is False
        config.set_report_allowed(False)
        dom = self.parse_html_string(self.get('/admin/welcome').body)
        checkbox = dom.find('.//input[@type="checkbox"]')
        self.assertNotIn('checked', checkbox.attrib)

        # Expect checkbox checked when setting is True
        config.set_report_allowed(True)
        dom = self.parse_html_string(self.get('/admin/welcome').body)
        checkbox = dom.find('.//input[@type="checkbox"]')
        self.assertEqual('checked', checkbox.attrib['checked'])

    def test_submit_welcome_with_accept_checkbox_checked(self):
        xsrf_token = crypto.XsrfTokenManager.create_xsrf_token(
            'add_first_course')
        response = self.post(
            '/admin/welcome',
            {
                'action': 'add_first_course',
                'xsrf_token': xsrf_token,
                course_creation.USAGE_REPORTING_CONSENT_CHECKBOX_NAME:
                course_creation.USAGE_REPORTING_CONSENT_CHECKBOX_VALUE,
            })

        self.assertEquals(True, config.REPORT_ALLOWED.value)

        expected = [{
            messaging.Message._INSTALLATION: FAKE_INSTALLATION_ID,
            messaging.Message._TIMESTAMP: FAKE_TIMESTAMP,
            messaging.Message._VERSION: os.environ['GCB_PRODUCT_VERSION'],
            messaging.Message._METRIC: messaging.Message.METRIC_REPORT_ALLOWED,
            messaging.Message._VALUE: True,
            messaging.Message._SOURCE: messaging.Message.WELCOME_SOURCE,
        }]
        self.assertEquals(expected, MockSender.get_sent())

    def test_submit_welcome_with_accept_checkbox_unchecked(self):
        xsrf_token = crypto.XsrfTokenManager.create_xsrf_token(
            'add_first_course')
        response = self.post(
            '/admin/welcome',
            {
                'action': 'add_first_course',
                'xsrf_token': xsrf_token,
                course_creation.USAGE_REPORTING_CONSENT_CHECKBOX_NAME: '',
            })

        self.assertEquals(False, config.REPORT_ALLOWED.value)

        expected = [{
            messaging.Message._INSTALLATION: FAKE_INSTALLATION_ID,
            messaging.Message._TIMESTAMP: FAKE_TIMESTAMP,
            messaging.Message._VERSION: os.environ['GCB_PRODUCT_VERSION'],
            messaging.Message._METRIC: messaging.Message.METRIC_REPORT_ALLOWED,
            messaging.Message._VALUE: False,
            messaging.Message._SOURCE: messaging.Message.WELCOME_SOURCE,
        }]
        self.assertEquals(expected, MockSender.get_sent())


class EnrollmentTests(UsageReportingTestBase):

    def test_unexpected_field_raises(self):
        with self.assertRaises(ValueError):
            enrollment.StudentEnrollmentEventDTO(None, {'bad_field': 'x'})

    def test_enrollment_map_reduce_job(self):
        self.maxDiff = None
        MOCK_NOW = 1427247511
        COURSE = 'xyzzy'
        NAMESPACE = 'ns_xyzzy'
        MIN_TIMESTAMP = (
            MOCK_NOW
            - (MOCK_NOW % enrollment.SECONDS_PER_HOUR)
            - enrollment.StudentEnrollmentEventCounter.MAX_AGE)

        # Insert some bogus StudentEnrollmentEventEntity for the M/R job
        # to count or delete.
        very_old_enroll = enrollment.StudentEnrollmentEventDTO(None, {})
        very_old_enroll.timestamp = 0
        very_old_enroll.metric = messaging.Message.METRIC_ENROLLED

        very_old_unenroll = enrollment.StudentEnrollmentEventDTO(None, {})
        very_old_unenroll.timestamp = 0
        very_old_unenroll.metric = messaging.Message.METRIC_UNENROLLED

        just_too_old_enroll = enrollment.StudentEnrollmentEventDTO(None, {})
        just_too_old_enroll.timestamp = MIN_TIMESTAMP - 1
        just_too_old_enroll.metric = messaging.Message.METRIC_ENROLLED

        just_too_old_unenroll = enrollment.StudentEnrollmentEventDTO(None, {})
        just_too_old_unenroll.timestamp = MIN_TIMESTAMP - 1
        just_too_old_unenroll.metric = messaging.Message.METRIC_UNENROLLED

        young_enough_enroll = enrollment.StudentEnrollmentEventDTO(None, {})
        young_enough_enroll.timestamp = MIN_TIMESTAMP
        young_enough_enroll.metric = messaging.Message.METRIC_ENROLLED

        young_enough_unenroll = enrollment.StudentEnrollmentEventDTO(None, {})
        young_enough_unenroll.timestamp = MIN_TIMESTAMP
        young_enough_unenroll.metric = messaging.Message.METRIC_UNENROLLED

        now_enroll = enrollment.StudentEnrollmentEventDTO(None, {})
        now_enroll.timestamp = MOCK_NOW
        now_enroll.metric = messaging.Message.METRIC_ENROLLED

        now_unenroll = enrollment.StudentEnrollmentEventDTO(None, {})
        now_unenroll.timestamp = MOCK_NOW
        now_unenroll.metric = messaging.Message.METRIC_UNENROLLED

        dtos = [
            very_old_enroll,
            very_old_unenroll,
            just_too_old_enroll,
            just_too_old_unenroll,
            young_enough_enroll,
            young_enough_unenroll,
            now_enroll,
            now_unenroll,
        ]

        app_context = actions.simple_add_course(COURSE, ADMIN_EMAIL, 'Test')
        with common_utils.Namespace(NAMESPACE):
            enrollment.StudentEnrollmentEventDAO.save_all(dtos)

        # Run map/reduce job with a setup function replaced so that it will
        # always choose the same timestamp as the start time.
        job_class = enrollment.StudentEnrollmentEventCounter
        save_b_a_m_p = job_class.build_additional_mapper_params
        try:
            def fixed_time_b_a_m_p(self, app_context):
                return {self.MIN_TIMESTAMP: MIN_TIMESTAMP}
            job_class.build_additional_mapper_params = fixed_time_b_a_m_p

            # Actually run the job.
            enrollment.StudentEnrollmentEventCounter(app_context).submit()
            self.execute_all_deferred_tasks(
                models.StudentLifecycleObserver.QUEUE_NAME)
            self.execute_all_deferred_tasks()
        finally:
            job_class.build_additional_mapper_params = save_b_a_m_p

        # Verify that the DTOs older than the cutoff have been removed from
        # the datastore.
        with common_utils.Namespace(NAMESPACE):
            dtos = enrollment.StudentEnrollmentEventDAO.get_all()
            dtos.sort(key=lambda dto: (dto.timestamp, dto.metric))
            self.assertEqual(
                [young_enough_enroll.dict,
                 young_enough_unenroll.dict,
                 now_enroll.dict,
                 now_unenroll.dict],
                [d.dict for d in dtos])

        # Verify that we have messages for the new-enough items, and no
        # messages for the older items.
        messages = MockSender.get_sent()
        messages.sort(key=lambda m: (m['timestamp'], m['metric']))

        MOCK_NOW_HOUR = MOCK_NOW - (MOCK_NOW % enrollment.SECONDS_PER_HOUR)
        expected = [{
            messaging.Message._INSTALLATION: FAKE_INSTALLATION_ID,
            messaging.Message._COURSE: FAKE_COURSE_ID,
            messaging.Message._TIMESTAMP: MIN_TIMESTAMP,
            messaging.Message._VERSION: os.environ['GCB_PRODUCT_VERSION'],
            messaging.Message._METRIC: messaging.Message.METRIC_ENROLLED,
            messaging.Message._VALUE: 1,
        }, {
            messaging.Message._INSTALLATION: FAKE_INSTALLATION_ID,
            messaging.Message._COURSE: FAKE_COURSE_ID,
            messaging.Message._TIMESTAMP: MIN_TIMESTAMP,
            messaging.Message._VERSION: os.environ['GCB_PRODUCT_VERSION'],
            messaging.Message._METRIC: messaging.Message.METRIC_UNENROLLED,
            messaging.Message._VALUE: 1,
        }, {
            messaging.Message._INSTALLATION: FAKE_INSTALLATION_ID,
            messaging.Message._COURSE: FAKE_COURSE_ID,
            messaging.Message._TIMESTAMP: MOCK_NOW_HOUR,
            messaging.Message._VERSION: os.environ['GCB_PRODUCT_VERSION'],
            messaging.Message._METRIC: messaging.Message.METRIC_ENROLLED,
            messaging.Message._VALUE: 1,
        }, {
            messaging.Message._INSTALLATION: FAKE_INSTALLATION_ID,
            messaging.Message._COURSE: FAKE_COURSE_ID,
            messaging.Message._TIMESTAMP: MOCK_NOW_HOUR,
            messaging.Message._VERSION: os.environ['GCB_PRODUCT_VERSION'],
            messaging.Message._METRIC: messaging.Message.METRIC_UNENROLLED,
            messaging.Message._VALUE: 1,
        }]
        self.assertEquals(expected, messages)
        sites.reset_courses()


    def test_end_to_end(self):
        """Actually enroll and unenroll students; verify reporting counts."""

        COURSE_NAME_BASE = 'test'
        NUM_COURSES = 2
        NUM_STUDENTS = 3
        THE_TIMESTAMP = 1427245200

        for course_num in range(NUM_COURSES):
            course_name = '%s_%d' % (COURSE_NAME_BASE, course_num)
            actions.simple_add_course(course_name, ADMIN_EMAIL, course_name)
            actions.update_course_config(
                course_name,
                {
                    'course': {
                        'now_available': True,
                        'browsable': True,
                    },
                })
            for student_num in range(NUM_STUDENTS):
                name = '%s_%d_%d' % (COURSE_NAME_BASE, course_num, student_num)
                actions.login(name + '@foo.com')
                actions.register(self, name, course_name)
                if student_num == 0:
                    actions.unregister(self, course_name)
                actions.logout()

        # Expect no messages yet; haven't run job.
        self.assertEquals([], MockSender.get_sent())

        # Run all counting jobs.
        with actions.OverriddenConfig(config.REPORT_ALLOWED.name, True):
            usage_reporting.StartReportingJobs._for_testing_only_get()
        self.execute_all_deferred_tasks(
            models.StudentLifecycleObserver.QUEUE_NAME)
        self.execute_all_deferred_tasks()

        # Verify counts.  (Ignore dates, these are fickle and subject to
        # weirdness on hour boundaries.  Also ignore course/instance IDs;
        # they are non-random and thus all the same.)
        num_enrolled_msgs = 0
        num_unenrolled_msgs = 0
        num_student_count_msgs = 0
        for message in MockSender.get_sent():
            if (message[messaging.Message._METRIC] ==
                messaging.Message.METRIC_STUDENT_COUNT):
                num_student_count_msgs += 1
                self.assertEquals(
                    NUM_STUDENTS, message[messaging.Message._VALUE])
            elif (message[messaging.Message._METRIC] ==
                  messaging.Message.METRIC_ENROLLED):
                num_enrolled_msgs += 1
                self.assertEquals(
                    NUM_STUDENTS, message[messaging.Message._VALUE])
            elif (message[messaging.Message._METRIC] ==
                  messaging.Message.METRIC_UNENROLLED):
                num_unenrolled_msgs += 1
                self.assertEquals(
                    1, message[messaging.Message._VALUE])

        self.assertEquals(NUM_COURSES, num_enrolled_msgs)
        self.assertEquals(NUM_COURSES, num_unenrolled_msgs)
        self.assertEquals(NUM_COURSES, num_student_count_msgs)
        sites.reset_courses()


class UsageReportingTests(UsageReportingTestBase):

    def test_disallowed(self):
        config.set_report_allowed(False)
        response = self.get(usage_reporting.StartReportingJobs.URL,
                            headers={'X-AppEngine-Cron': 'True'})
        self.assertEquals(200, response.status_int)
        self.assertEquals('Disabled.', response.body)

    def test_not_from_cron_and_not_admin(self):
        config.set_report_allowed(True)
        actions.logout()
        response = self.get(usage_reporting.StartReportingJobs.URL,
                            expect_errors=True)
        self.assertEquals(403, response.status_int)
        self.assertEquals('Forbidden.', response.body)

    def test_not_from_cron_but_is_admin(self):
        config.set_report_allowed(True)
        response = self.get(usage_reporting.StartReportingJobs.URL,
                            expect_errors=True)
        self.assertEquals(200, response.status_int)
        self.assertEquals('OK.', response.body)

    def test_jobs_run(self):
        COURSE = 'test'
        app_context = actions.simple_add_course(COURSE, ADMIN_EMAIL, 'Test')
        actions.register(self, 'Joe Admin', COURSE)
        config.set_report_allowed(True)
        response = self.get(usage_reporting.StartReportingJobs.URL,
                            headers={'X-AppEngine-Cron': 'True'})
        self.assertEquals(200, response.status_int)
        self.assertEquals('OK.', response.body)
        now = int(time.time())
        self.execute_all_deferred_tasks(
            models.StudentLifecycleObserver.QUEUE_NAME)
        self.execute_all_deferred_tasks()

        expected = [{
            messaging.Message._INSTALLATION: FAKE_INSTALLATION_ID,
            messaging.Message._COURSE: FAKE_COURSE_ID,
            messaging.Message._TIMESTAMP: FAKE_TIMESTAMP,
            messaging.Message._VERSION: os.environ['GCB_PRODUCT_VERSION'],
            messaging.Message._METRIC: messaging.Message.METRIC_STUDENT_COUNT,
            messaging.Message._VALUE: 1,
        }, {
            messaging.Message._INSTALLATION: FAKE_INSTALLATION_ID,
            messaging.Message._COURSE: FAKE_COURSE_ID,
            messaging.Message._TIMESTAMP: now - (now % 3600),
            messaging.Message._VERSION: os.environ['GCB_PRODUCT_VERSION'],
            messaging.Message._METRIC: messaging.Message.METRIC_ENROLLED,
            messaging.Message._VALUE: 1,
        }]
        actual = MockSender.get_sent()
        actual.sort(key=lambda x: x['timestamp'])
        self.assertEquals(expected, actual)
        sites.reset_courses()

    def test_course_message_with_google_admin(self):
        actions.login('student@foo.com')
        course_name = 'google_test_course'
        course_title = 'Google Test Course'
        course_namespace = 'ns_%s' % course_name
        course_slug = '/%s' % course_name

        def add_course_and_register_student(admin_email):
            google_app_context = actions.simple_add_course(
                course_name, admin_email, course_title)
            actions.update_course_config(
                course_name,
                {'course': {'now_available': True, 'browsable': True,},})
            actions.register(self, 'John Smith', course_name)

            with actions.OverriddenConfig(config.REPORT_ALLOWED.name, True):
                usage_reporting.StartReportingJobs._for_testing_only_get()
            self.execute_all_deferred_tasks(
                models.StudentLifecycleObserver.QUEUE_NAME)
            self.execute_all_deferred_tasks()

        # With admin@google.com - should get extra fields in reports.
        add_course_and_register_student('admin@google.com')
        for message in MockSender.get_sent():
            self.assertEquals(message[messaging.Message._COURSE_TITLE],
                              course_title)
            self.assertEquals(message[messaging.Message._COURSE_SLUG],
                              course_slug)
            self.assertEquals(message[messaging.Message._COURSE_NAMESPACE],
                              course_namespace)
        MockSender.clear_sent()
        sites.reset_courses()

        # Without admin@google.com - should not get extra fields in reports.
        add_course_and_register_student('admin@foo.com')
        for message in MockSender.get_sent():
            self.assertNotIn(messaging.Message._COURSE_TITLE, message)
            self.assertNotIn(messaging.Message._COURSE_SLUG, message)
            self.assertNotIn(messaging.Message._COURSE_NAMESPACE, message)
        MockSender.clear_sent()
        sites.reset_courses()


class MessageCatcher(object):

    URL = 'https://docs.google.com/a/google.com/forms/d/<IDNUMBER>/formResponse'
    FORM_FIELD = 'entry.12345'
    DEFAULT_CONFIG = transforms.dumps({
        messaging.Sender._REPORT_ENABLED: True,
        messaging.Sender._REPORT_TARGET: URL,
        messaging.Sender._REPORT_FORM_FIELD: FORM_FIELD,
        })
    _config = DEFAULT_CONFIG
    _return_code = 200
    _messages = []

    Response = collections.namedtuple('Response', ['status_code', 'content'])

    @classmethod
    def get(cls):
        return cls.Response(cls._return_code, cls._config)

    @classmethod
    def post(cls, request):
        if cls._return_code == 200:
            # Pretend to not have seen the message if reporting a failure.
            message = transforms.loads(request.get(cls.FORM_FIELD)[0])
            cls._messages.append(message)
        return cls.Response(cls._return_code, '')

    @classmethod
    def get_sent(cls):
        return copy.deepcopy(cls._messages)

    @classmethod
    def clear_sent(cls):
        del cls._messages[:]

    @classmethod
    def set_return_code(cls, return_code):
        cls._return_code = return_code

    @classmethod
    def set_config(cls, cfg):
        cls._config = cfg


class MessagingTests(actions.TestBase):

    COURSE_NAME = 'test'
    NAMESPACE = 'ns_test'

    # Object to emulate response from urlfetch.fetch for our mock.
    Response = collections.namedtuple('Response', ('status_code', 'content'))

    def mock_urlfetch_fetch(self, url, method=None, payload=None,
                            follow_redirects=None):
        """Override of urlfetch.fetch method; forwards to self.get/post."""
        if not url.startswith('https://'):
            raise urlfetch.Error('Malformed URL')
        if method == 'GET':
            return MessageCatcher.get()
        elif method == 'POST':
            return MessageCatcher.post(urlparse.parse_qs(payload))

    def setUp(self):
        super(MessagingTests, self).setUp()
        messaging.ENABLED_IN_DEV_FOR_TESTING = True
        self.save_urlfetch_fetch = urlfetch.fetch
        urlfetch.fetch = self.mock_urlfetch_fetch
        actions.login(ADMIN_EMAIL, is_admin=True)
        self.app_config = actions.simple_add_course(
            self.COURSE_NAME, ADMIN_EMAIL, self.COURSE_NAME)

    def tearDown(self):
        messaging.ENABLED_IN_DEV_FOR_TESTING = False
        messaging.Sender._report_settings_timestamp = 0
        urlfetch.fetch = self.save_urlfetch_fetch
        MessageCatcher.clear_sent()
        MessageCatcher.set_return_code(200)
        MessageCatcher.set_config(MessageCatcher.DEFAULT_CONFIG)
        sites.reset_courses()
        super(MessagingTests, self).tearDown()

    def test_blue_sky_instance_message(self):
        messaging.Message.send_instance_message(
            messaging.Message.METRIC_REPORT_ALLOWED, True)

        messages = MessageCatcher.get_sent()
        self.assertEquals(1, len(messages))
        message = messages[0]
        self.assertEquals(messaging.Message.METRIC_REPORT_ALLOWED,
                          message[messaging.Message._METRIC])
        self.assertEquals(True,
                          message[messaging.Message._VALUE])
        self.assertAlmostEqual(int(time.time()),
                               message[messaging.Message._TIMESTAMP],
                               delta=10)
        self.assertEquals(os.environ['GCB_PRODUCT_VERSION'],
                          message[messaging.Message._VERSION])
        self.assertNotEquals(0, len(message[messaging.Message._INSTALLATION]))
        self.assertNotIn(messaging.Message._COURSE, message)

    def test_blue_sky_course_message(self):
        student_count = 1453
        with common_utils.Namespace(self.NAMESPACE):
            messaging.Message.send_course_message(
                messaging.Message.METRIC_STUDENT_COUNT, student_count)

        messages = MessageCatcher.get_sent()
        self.assertEquals(1, len(messages))
        message = messages[0]
        self.assertEquals(messaging.Message.METRIC_STUDENT_COUNT,
                          message[messaging.Message._METRIC])
        self.assertEquals(student_count,
                          message[messaging.Message._VALUE])
        self.assertAlmostEqual(int(time.time()),
                               message[messaging.Message._TIMESTAMP],
                               delta=10)
        self.assertEquals(os.environ['GCB_PRODUCT_VERSION'],
                          message[messaging.Message._VERSION])
        self.assertNotEquals(0, len(message[messaging.Message._INSTALLATION]))
        self.assertNotEquals(0, len(message[messaging.Message._COURSE]))

    def test_random_ids_are_consistent(self):
        num_messages = 10
        student_count = 123
        with common_utils.Namespace(self.NAMESPACE):
            for unused in range(num_messages):
                messaging.Message.send_course_message(
                    messaging.Message.METRIC_STUDENT_COUNT, student_count)

        messages = MessageCatcher.get_sent()
        self.assertEquals(num_messages, len(messages))
        for message in messages:
            self.assertEquals(
                messages[0][messaging.Message._INSTALLATION],
                message[messaging.Message._INSTALLATION])
            self.assertEquals(
                messages[0][messaging.Message._COURSE],
                message[messaging.Message._COURSE])

    def test_report_disabled_by_config(self):
        MessageCatcher.set_config(
            transforms.dumps({
                messaging.Sender._REPORT_ENABLED: False,
                messaging.Sender._REPORT_TARGET: 'irrelevant',
                messaging.Sender._REPORT_FORM_FIELD: 'irrelevant',
            }))
        messaging.Message.send_instance_message(
            messaging.Message.METRIC_REPORT_ALLOWED, True)

        # Should have no messages sent, and nothing queued.
        messages = MessageCatcher.get_sent()
        self.assertEquals(0, len(messages))
        tasks = self.taskq.GetTasks('default')
        self.assertEquals(0, len(tasks))

    def _assert_message_queued_and_succeeds(self):
        # Should have no messages sent, and one item queued.
        messages = MessageCatcher.get_sent()
        self.assertEquals(0, len(messages))

        # Now execute background tasks; expect one message.
        self.execute_all_deferred_tasks(
            models.StudentLifecycleObserver.QUEUE_NAME)
        self.execute_all_deferred_tasks()
        messages = MessageCatcher.get_sent()
        self.assertEquals(1, len(messages))
        message = messages[0]

        self.assertEquals(messaging.Message.METRIC_REPORT_ALLOWED,
                          message[messaging.Message._METRIC])
        self.assertEquals(True,
                          message[messaging.Message._VALUE])
        self.assertAlmostEqual(int(time.time()),
                               message[messaging.Message._TIMESTAMP],
                               delta=10)
        self.assertEquals(os.environ['GCB_PRODUCT_VERSION'],
                          message[messaging.Message._VERSION])
        self.assertNotEquals(0, len(message[messaging.Message._INSTALLATION]))
        self.assertNotIn(messaging.Message._COURSE, message)

    def test_report_queued_when_config_malformed(self):
        MessageCatcher.set_config(
            'this will not properly decode as JSON')
        messaging.Message.send_instance_message(
            messaging.Message.METRIC_REPORT_ALLOWED, True)
        MessageCatcher.set_config(MessageCatcher.DEFAULT_CONFIG)
        self._assert_message_queued_and_succeeds()

    def test_report_queued_when_config_unavailable(self):
        MessageCatcher.set_return_code(500)
        messaging.Message.send_instance_message(
            messaging.Message.METRIC_REPORT_ALLOWED, True)
        MessageCatcher.set_return_code(200)
        self._assert_message_queued_and_succeeds()

    def test_report_queued_when_config_url_malformed(self):
        MessageCatcher.set_config(
            transforms.dumps({
                messaging.Sender._REPORT_ENABLED: True,
                messaging.Sender._REPORT_TARGET: 'a malformed url',
                messaging.Sender._REPORT_FORM_FIELD: 'entry.12345',
            }))
        messaging.Message.send_instance_message(
            messaging.Message.METRIC_REPORT_ALLOWED, True)
        MessageCatcher.set_config(MessageCatcher.DEFAULT_CONFIG)
        self._assert_message_queued_and_succeeds()

    def test_report_queued_when_post_receives_non_200(self):
        # Send one message through cleanly; this will get the messaging
        # module to retain its notion of the destination URL and not re-get
        # it on the next message.
        messaging.Message.send_instance_message(
            messaging.Message.METRIC_REPORT_ALLOWED, True)
        MessageCatcher.clear_sent()

        # Set reponse code so that the POST fails; verify that that retries
        # using the deferred task queue.
        MessageCatcher.set_return_code(500)
        messaging.Message.send_instance_message(
            messaging.Message.METRIC_REPORT_ALLOWED, True)
        MessageCatcher.set_return_code(200)
        self._assert_message_queued_and_succeeds()


class ConsentBannerTests(UsageReportingTestBase):
    COURSE_NAME = 'test_course'
    SUPER_MESSAGE = 'Would you like to help improve Course Builder?'
    NOT_SUPER_MESSAGE = 'Please ask your Course Builder Administrator'
    NOT_SUPER_EMAIL = 'not-super@test.com'

    def setUp(self):
        super(ConsentBannerTests, self).setUp()

        self.base = '/' + self.COURSE_NAME
        self.app_context = actions.simple_add_course(
            self.COURSE_NAME, ADMIN_EMAIL, 'Banner Test Course')
        self.old_namespace = namespace_manager.get_namespace()
        namespace_manager.set_namespace('ns_%s' % self.COURSE_NAME)
        courses.Course.ENVIRON_TEST_OVERRIDES = {
            'course': {'admin_user_emails': self.NOT_SUPER_EMAIL}}

    def tearDown(self):
        del sites.Registry.test_overrides[sites.GCB_COURSES_CONFIG.name]
        namespace_manager.set_namespace(self.old_namespace)
        courses.Course.ENVIRON_TEST_OVERRIDES = {}
        super(ConsentBannerTests, self).tearDown()

    def test_banner_with_buttons_shown_to_super_user_on_dashboard(self):
        dom = self.parse_html_string(self.get('dashboard').body)
        banner = dom.find('.//div[@class="consent-banner"]')
        self.assertIsNotNone(banner)
        self.assertIn(self.SUPER_MESSAGE, banner.find('.//h1').text)
        self.assertEqual(2, len(banner.findall('.//button')))

    def test_banner_with_buttons_shown_to_super_user_on_global_admin(self):
        dom = self.parse_html_string(self.get('/modules/admin').body)
        banner = dom.find('.//div[@class="consent-banner"]')
        self.assertIsNotNone(banner)
        self.assertIn(self.SUPER_MESSAGE, banner.find('.//h1').text)
        self.assertEqual(2, len(banner.findall('.//button')))

    def test_banner_without_buttons_shown_to_instructor_on_dashboard(self):
        actions.logout()
        actions.login(self.NOT_SUPER_EMAIL, is_admin=False)

        dom = self.parse_html_string(self.get('dashboard').body)
        banner = dom.find('.//div[@class="consent-banner"]')
        self.assertIsNotNone(banner)
        self.assertIn(self.NOT_SUPER_MESSAGE, banner.findall('.//p')[1].text)
        self.assertEqual(0, len(banner.findall('.//button')))

    def test_banner_not_shown_when_choices_have_been_made(self):
        config.set_report_allowed(False)

        # Check super-user role; global admin
        dom = self.parse_html_string(self.get('/modules/admin').body)
        self.assertIsNone(dom.find('.//div[@class="consent-banner"]'))

        # check super-user role; dashboard
        dom = self.parse_html_string(self.get('dashboard').body)
        self.assertIsNone(dom.find('.//div[@class="consent-banner"]'))

        # Check non-super role; dashboadd
        actions.logout()
        actions.login(self.NOT_SUPER_EMAIL, is_admin=False)
        dom = self.parse_html_string(self.get('dashboard').body)
        self.assertIsNone(dom.find('.//div[@class="consent-banner"]'))


class ConsentBannerRestHandlerTests(UsageReportingTestBase):
    URL = '/rest/modules/usage_reporting/consent'
    XSRF_TOKEN = 'usage_reporting_consent_banner'
    def do_post(self, xsrf_token, is_allowed):
        request = {
          'xsrf_token': xsrf_token,
          'payload': transforms.dumps({'is_allowed': is_allowed})
        }
        return self.post(self.URL, {'request': transforms.dumps(request)})

    def test_handler_rejects_bad_xsrf_token(self):
        response = self.do_post('bad_xsrf_token', False)
        self.assertEqual(200, response.status_int)
        response_dict = transforms.loads(response.body)
        self.assertEqual(403, response_dict['status'])
        self.assertIn('Bad XSRF token.', response_dict['message'])

    def test_handler_rejects_non_super_user(self):
        actions.logout()
        xsrf_token = crypto.XsrfTokenManager.create_xsrf_token(self.XSRF_TOKEN)
        response = self.do_post(xsrf_token, False)
        self.assertEqual(200, response.status_int)
        response_dict = transforms.loads(response.body)
        self.assertEqual(401, response_dict['status'])
        self.assertIn('Access denied.', response_dict['message'])

    def test_handler_sets_consent_and_sends_message(self):
        self.assertFalse(config.is_consent_set())
        xsrf_token = crypto.XsrfTokenManager.create_xsrf_token(self.XSRF_TOKEN)

        response = self.do_post(xsrf_token, True)
        self.assertTrue(config.is_consent_set())
        self.assertTrue(config.REPORT_ALLOWED.value)

        response = self.do_post(xsrf_token, False)
        self.assertFalse(config.REPORT_ALLOWED.value)

        expected = [{
            messaging.Message._INSTALLATION: FAKE_INSTALLATION_ID,
            messaging.Message._TIMESTAMP: FAKE_TIMESTAMP,
            messaging.Message._VERSION: os.environ['GCB_PRODUCT_VERSION'],
            messaging.Message._METRIC: messaging.Message.METRIC_REPORT_ALLOWED,
            messaging.Message._VALUE: True,
            messaging.Message._SOURCE: messaging.Message.BANNER_SOURCE,
        }, {
            messaging.Message._INSTALLATION: FAKE_INSTALLATION_ID,
            messaging.Message._TIMESTAMP: FAKE_TIMESTAMP,
            messaging.Message._VERSION: os.environ['GCB_PRODUCT_VERSION'],
            messaging.Message._METRIC: messaging.Message.METRIC_REPORT_ALLOWED,
            messaging.Message._VALUE: False,
            messaging.Message._SOURCE: messaging.Message.BANNER_SOURCE,
        }]
        self.assertEquals(expected, MockSender.get_sent())


class DevServerTests(UsageReportingTestBase):
    """Test that consent widgets are turned off in normal dev mode."""

    def test_welcome_page_message_not_shown_in_dev(self):
        # First check the text is present in test mode
        response = self.get('/admin/welcome')
        self.assertIn(
            'I agree that Google may collect information about this',
            response.body)

        # Switch off test mode
        messaging.ENABLED_IN_DEV_FOR_TESTING = False

        # Expect text is missing
        response = self.get('/admin/welcome')
        self.assertNotIn(
            'I agree that Google may collect information about this',
            response.body)


    def test_consent_banner_not_shown_in_dev(self):
        # First check banner is present in test mode
        dom = self.parse_html_string(self.get('/modules/admin').body)
        banner = dom.find('.//div[@class="consent-banner"]')
        self.assertIsNotNone(banner)

        # Switch off test mode
        messaging.ENABLED_IN_DEV_FOR_TESTING = False

        # Expect to see banner missing
        dom = self.parse_html_string(self.get('/modules/admin').body)
        banner = dom.find('.//div[@class="consent-banner"]')
        self.assertIsNone(banner)
