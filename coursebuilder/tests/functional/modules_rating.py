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

"""Tests for the rating widget."""

__author__ = 'John Orr (jorr@google.com)'

import urllib

from controllers import utils
from common import crypto
from common import users
from models import courses
from models import models
from models import transforms
from models.data_sources import utils as data_sources_utils
from modules.rating import rating
from tests.functional import actions

from google.appengine.api import namespace_manager


ADMIN_EMAIL = 'admin@foo.com'
COURSE_NAME = 'rating_course'
SENDER_EMAIL = 'sender@foo.com'
STUDENT_EMAIL = 'student@foo.com'
STUDENT_NAME = 'A. Student'

RATINGS_DISABLED = {'unit': {'ratings_module': {'enabled': False}}}
RATINGS_ENABLED = {'unit': {'ratings_module': {'enabled': True}}}


class BaseRatingsTests(actions.TestBase):

    def setUp(self):
        super(BaseRatingsTests, self).setUp()

        self.base = '/' + COURSE_NAME
        context = actions.simple_add_course(
            COURSE_NAME, ADMIN_EMAIL, 'Ratings Course')
        self.course = courses.Course(None, context)
        self.unit = self.course.add_unit()
        self.unit.availability = courses.AVAILABILITY_AVAILABLE
        self.lesson = self.course.add_lesson(self.unit)
        self.lesson.objectives = 'Some lesson content'
        self.lesson.availability = courses.AVAILABILITY_AVAILABLE
        self.course.save()

        self.key = '/%s/unit?unit=%s&lesson=%s' % (
            COURSE_NAME, self.unit.unit_id, self.lesson.lesson_id)

        self.old_namespace = namespace_manager.get_namespace()
        namespace_manager.set_namespace('ns_%s' % COURSE_NAME)

    def tearDown(self):
        namespace_manager.set_namespace(self.old_namespace)
        super(BaseRatingsTests, self).tearDown()

    def register_student(self):
        actions.login(STUDENT_EMAIL, is_admin=False)
        actions.register(self, STUDENT_NAME)
        return users.get_current_user()

    def get_lesson_dom(self):
        response = self.get('unit?unit=%s&lesson=%s' % (
            self.unit.unit_id, self.lesson.lesson_id))
        self.assertEquals(200, response.status_int)
        return self.parse_html_string(response.body)


class ExtraContentProvideTests(BaseRatingsTests):

    def test_returns_none_when_ratings_disabled_in_course_settings(self):
        with actions.OverriddenEnvironment(RATINGS_DISABLED):
            self.register_student()
            dom = self.get_lesson_dom()
            self.assertFalse(dom.find('.//div[@class="gcb-ratings-widget"]'))

    def test_returns_none_when_no_user_in_session(self):
        with actions.OverriddenEnvironment(RATINGS_ENABLED):
            dom = self.get_lesson_dom()
            self.assertFalse(dom.find('.//div[@class="gcb-ratings-widget"]'))

    def test_returns_none_when_user_not_registered(self):
        with actions.OverriddenEnvironment(RATINGS_ENABLED):
            actions.login(STUDENT_EMAIL, is_admin=False)
            dom = self.get_lesson_dom()
            self.assertFalse(dom.find('.//div[@class="gcb-ratings-widget"]'))

    def test_widget_html(self):
        with actions.OverriddenEnvironment(RATINGS_ENABLED):
            self.register_student()
            dom = self.get_lesson_dom()
            self.assertTrue(dom.find('.//div[@class="gcb-ratings-widget"]'))


class RatingHandlerTests(BaseRatingsTests):

    def setUp(self):
        super(RatingHandlerTests, self).setUp()
        courses.Course.ENVIRON_TEST_OVERRIDES = RATINGS_ENABLED

    def tearDown(self):
        courses.Course.ENVIRON_TEST_OVERRIDES = {}
        super(RatingHandlerTests, self).tearDown()

    def get_data(self, key=None, xsrf_token=None):
        if key is None:
            key = self.key
        if xsrf_token is None:
            xsrf_token = utils.XsrfTokenManager.create_xsrf_token('rating')

        request = {
            'xsrf_token': xsrf_token,
            'payload': transforms.dumps({'key': key})
        }
        return transforms.loads(
            self.get('rest/modules/rating?%s' % urllib.urlencode(
                {'request': transforms.dumps(request)})).body)

    def post_data(
            self, key=None, rating_int=None, additional_comments=None,
            xsrf_token=None):

        if key is None:
            key = self.key

        if xsrf_token is None:
            xsrf_token = utils.XsrfTokenManager.create_xsrf_token('rating')

        request = {
            'xsrf_token': xsrf_token,
            'payload': transforms.dumps({
                'key': key,
                'rating': rating_int,
                'additional_comments': additional_comments})
        }
        return transforms.loads(self.post(
            'rest/modules/rating?%s',
            {'request': transforms.dumps(request)}).body)

    def test_get_requires_ratings_enabled(self):
        courses.Course.ENVIRON_TEST_OVERRIDES = RATINGS_DISABLED
        self.register_student()
        response = self.get_data()
        self.assertEquals(401, response['status'])
        self.assertIn('Access denied', response['message'])

    def test_get_requires_valid_xsrf_token(self):
        response = self.get_data(xsrf_token='bad-xsrf-key')
        self.assertEquals(403, response['status'])
        self.assertIn('Bad XSRF token', response['message'])

    def test_get_requires_user_in_session(self):
        response = self.get_data()
        self.assertEquals(401, response['status'])
        self.assertIn('Access denied', response['message'])

    def test_get_requires_registered_student(self):
        actions.login(STUDENT_EMAIL, is_admin=False)
        response = self.get_data()
        self.assertEquals(401, response['status'])
        self.assertIn('Access denied', response['message'])

    def test_get_returns_null_for_no_existing_rating(self):
        self.register_student()
        response = self.get_data()
        self.assertEquals(200, response['status'])
        payload = transforms.loads(response['payload'])
        self.assertIsNone(payload['rating'])

    def test_get_returns_existing_rating(self):
        user = self.register_student()
        student = models.Student.get_enrolled_student_by_user(user)
        prop = rating.StudentRatingProperty.load_or_default(student)
        prop.set_rating(self.key, 3)
        prop.put()

        response = self.get_data()
        self.assertEquals(200, response['status'])
        payload = transforms.loads(response['payload'])
        self.assertEquals(3, payload['rating'])

    def test_post_requires_ratings_enabled(self):
        courses.Course.ENVIRON_TEST_OVERRIDES = RATINGS_DISABLED
        self.register_student()
        response = self.post_data(rating_int=2)
        self.assertEquals(401, response['status'])
        self.assertIn('Access denied', response['message'])

    def test_post_requires_valid_xsrf_token(self):
        response = self.post_data(rating_int=3, xsrf_token='bad-xsrf=token')
        self.assertEquals(403, response['status'])
        self.assertIn('Bad XSRF token', response['message'])

    def test_post_requires_user_in_session(self):
        response = self.post_data(rating_int=3)
        self.assertEquals(401, response['status'])
        self.assertIn('Access denied', response['message'])

    def test_post_requires_registered_student(self):
        actions.login(STUDENT_EMAIL, is_admin=False)
        response = self.post_data(rating_int=3)
        self.assertEquals(401, response['status'])
        self.assertIn('Access denied', response['message'])

    def test_post_records_rating_in_property(self):
        user = self.register_student()
        response = self.post_data(rating_int=2)
        self.assertEquals(200, response['status'])
        self.assertIn('Thank you for your feedback', response['message'])

        student = models.Student.get_enrolled_student_by_user(user)
        prop = rating.StudentRatingProperty.load_or_default(student)
        self.assertEquals(2, prop.get_rating(self.key))

    def test_post_records_rating_and_comment_in_event(self):
        self.register_student()
        response = self.post_data(
            rating_int=2, additional_comments='Good lesson')
        self.assertEquals(200, response['status'])
        self.assertIn('Thank you for your feedback', response['message'])

        event_list = rating.StudentRatingEvent.all().fetch(100)
        self.assertEquals(1, len(event_list))
        event = event_list[0]
        event_data = transforms.loads(event.data)
        self.assertEquals('rating-event', event.source)
        self.assertEquals(users.get_current_user().user_id(), event.user_id)
        self.assertEquals(2, event_data['rating'])
        self.assertEquals('Good lesson', event_data['additional_comments'])
        self.assertEquals(self.key, event_data['key'])

    def test_for_export_scrubs_extraneous_data(self):
        def transform_fn(s):
            return s.upper()

        event = rating.StudentRatingEvent()
        event.source = 'rating-event'
        event.user_id = 'a_user'
        event.data = transforms.dumps({
            'key': self.key,
            'rating': 1,
            'additional_comments': 'Good lesson',
            'bizarre_unforeseen_extra_field': 'odd...'
        })
        event.put()

        event = event.for_export(transform_fn)
        self.assertEquals('rating-event', event.source)
        self.assertEquals('A_USER', event.user_id)
        self.assertEquals(
            {
                'key': self.key,
                'rating': 1,
                'additional_comments': 'Good lesson'},
            transforms.loads(event.data))

    def test_data_source(self):

        # Register a student and give some feedback
        user = self.register_student()
        student = models.Student.get_enrolled_student_by_user(user)
        response = self.post_data(
            rating_int=2, additional_comments='Good lesson')
        self.assertEquals(200, response['status'])
        self.assertIn('Thank you for your feedback', response['message'])

        # Log in as admin for the data query
        actions.logout()
        actions.login(ADMIN_EMAIL, is_admin=True)

        xsrf_token = crypto.XsrfTokenManager.create_xsrf_token(
            data_sources_utils.DATA_SOURCE_ACCESS_XSRF_ACTION)

        pii_secret = crypto.generate_transform_secret_from_xsrf_token(
            xsrf_token, data_sources_utils.DATA_SOURCE_ACCESS_XSRF_ACTION)

        safe_user_id = crypto.hmac_sha_2_256_transform(
            pii_secret, student.user_id)

        response = self.get(
            'rest/data/rating_events/items?'
            'data_source_token=%s&page_number=0' % xsrf_token)
        data = transforms.loads(response.body)['data']

        self.assertEqual(1, len(data))
        record = data[0]

        self.assertEqual(7, len(record))
        self.assertEqual(safe_user_id, record['user_id'])
        self.assertEqual('2', record['rating'])
        self.assertEqual('Good lesson', record['additional_comments'])
        self.assertEqual(
            '/rating_course/unit?unit=%s&lesson=%s' % (
                self.unit.unit_id, self.lesson.lesson_id),
            record['content_url'])
        self.assertEqual(str(self.unit.unit_id), record['unit_id'])
        self.assertEqual(str(self.lesson.lesson_id), record['lesson_id'])
        self.assertIn('recorded_on', record)

    def test_data_source_is_exportable(self):
        self.assertTrue(rating.RatingEventDataSource.exportable())
