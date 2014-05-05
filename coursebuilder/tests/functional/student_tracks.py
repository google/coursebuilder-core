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

"""Tests that walk through Course Builder pages."""

__author__ = 'Mike Gainer (mgainer@google.com)'

import urllib

from common import crypto
from controllers import sites
from models import courses
from models import transforms
from tests.functional import actions

COURSE_NAME = 'tracks_test'
ADMIN_EMAIL = 'admin@foo.com'
REGISTERED_STUDENT_EMAIL = 'foo@bar.com'
REGISTERED_STUDENT_NAME = 'John Smith'
UNREGISTERED_STUDENT_EMAIL = 'bar@bar.com'
STUDENT_LABELS_URL = '/%s/rest/student/labels/tracks' % COURSE_NAME
COURSE_OVERVIEW_URL = '/%s/course' % COURSE_NAME


class StudentTracksTest(actions.TestBase):

    _get_environ_old = None

    @classmethod
    def setUpClass(cls):
        super(StudentTracksTest, cls).setUpClass()

        sites.ApplicationContext.get_environ_old = (
            sites.ApplicationContext.get_environ)
        def get_environ_new(slf):
            environ = slf.get_environ_old()
            environ['course']['now_available'] = True
            return environ
        sites.ApplicationContext.get_environ = get_environ_new

    @classmethod
    def tearDownClass(cls):
        sites.ApplicationContext.get_environ = (
            sites.ApplicationContext.get_environ_old)

    def setUp(self):
        super(StudentTracksTest, self).setUp()

        # Add a course that is real enough to show on /<ns>/course
        actions.login(ADMIN_EMAIL, is_admin=True)
        payload_dict = {
            'name': COURSE_NAME,
            'title': 'Tracks Test',
            'admin_email': ADMIN_EMAIL}
        request = {
            'payload': transforms.dumps(payload_dict),
            'xsrf_token': crypto.XsrfTokenManager.create_xsrf_token(
                'add-course-put')}
        response = self.testapp.put('/rest/courses/item?%s' % urllib.urlencode(
            {'request': transforms.dumps(request)}), {})
        self.assertEquals(response.status_int, 200)
        sites.setup_courses('course:/%s::ns_%s, course:/:/' % (
                COURSE_NAME, COURSE_NAME))
        actions.logout()

        # Register a student for that course.
        actions.login(REGISTERED_STUDENT_EMAIL)
        actions.register(self, REGISTERED_STUDENT_NAME, COURSE_NAME)
        actions.logout()

        # Add some units to the course.
        self._course = courses.Course(
            None, app_context=sites.get_all_courses()[0])
        self._unit_no_labels = self._course.add_unit()
        self._unit_no_labels.title = 'Unit No Labels'
        self._unit_no_labels.now_available = True
        self._unit_labels_foo = self._course.add_unit()
        self._unit_labels_foo.title = 'Unit Labels: Foo'
        self._unit_labels_foo.now_available = True
        self._unit_labels_foo.labels = 'foo'
        self._unit_labels_foo_bar = self._course.add_unit()
        self._unit_labels_foo_bar.title = 'Unit Labels: Bar, Foo'
        self._unit_labels_foo_bar.now_available = True
        self._unit_labels_foo_bar.labels = 'bar, foo'
        self._course.save()

    def tearDown(self):
        super(StudentTracksTest, self).tearDown()
        sites.reset_courses()

    def test_unit_matching_no_labels(self):
        actions.login(REGISTERED_STUDENT_EMAIL)
        response = self.get(COURSE_OVERVIEW_URL)
        self.assertIn(self._unit_no_labels.title, response.body)
        self.assertIn(self._unit_labels_foo.title, response.body)
        self.assertIn(self._unit_labels_foo_bar.title, response.body)

    def test_unit_matching_foo(self):
        actions.login(REGISTERED_STUDENT_EMAIL)
        self.put(STUDENT_LABELS_URL, {'labels': 'foo'})
        response = self.get(COURSE_OVERVIEW_URL)
        self.assertIn(self._unit_no_labels.title, response.body)
        self.assertIn(self._unit_labels_foo.title, response.body)
        self.assertIn(self._unit_labels_foo_bar.title, response.body)

    def test_unit_matching_foo_bar(self):
        actions.login(REGISTERED_STUDENT_EMAIL)
        self.put(STUDENT_LABELS_URL, {'labels': 'foo, bar'})
        response = self.get(COURSE_OVERVIEW_URL)
        self.assertIn(self._unit_no_labels.title, response.body)
        self.assertIn(self._unit_labels_foo.title, response.body)
        self.assertIn(self._unit_labels_foo_bar.title, response.body)

    def test_unit_matching_bar(self):
        actions.login(REGISTERED_STUDENT_EMAIL)
        response = self.put(STUDENT_LABELS_URL, {'labels': 'bar'})
        response = self.get(COURSE_OVERVIEW_URL)
        self.assertIn(self._unit_no_labels.title, response.body)
        self.assertNotIn(self._unit_labels_foo.title, response.body)
        self.assertIn(self._unit_labels_foo_bar.title, response.body)

    def test_unit_matching_baz(self):
        actions.login(REGISTERED_STUDENT_EMAIL)
        self.put(STUDENT_LABELS_URL, {'labels': 'baz'})
        response = self.get(COURSE_OVERVIEW_URL)
        self.assertIn(self._unit_no_labels.title, response.body)
        self.assertNotIn(self._unit_labels_foo.title, response.body)
        self.assertNotIn(self._unit_labels_foo_bar.title, response.body)
