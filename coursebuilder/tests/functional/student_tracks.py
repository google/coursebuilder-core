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

from common import utils as common_utils
from controllers import sites
from models import courses
from models import models
from tests.functional import actions

COURSE_NAME = 'tracks_test'
COURSE_TITLE = 'Tracks Test'
NAMESPACE = 'ns_%s' % COURSE_NAME
ADMIN_EMAIL = 'admin@foo.com'
REGISTERED_STUDENT_EMAIL = 'foo@bar.com'
REGISTERED_STUDENT_NAME = 'John Smith'
UNREGISTERED_STUDENT_EMAIL = 'bar@bar.com'
COURSE_OVERVIEW_URL = '/%s/course' % COURSE_NAME
STUDENT_LABELS_URL = '/%s/rest/student/labels' % COURSE_NAME
STUDENT_SETTINGS_URL = '/%s/student/home' % COURSE_NAME


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

        # Add a course that will show up.
        actions.simple_add_course(COURSE_NAME, ADMIN_EMAIL, COURSE_TITLE)

        # Add labels
        with common_utils.Namespace(NAMESPACE):
            self.foo_id = models.LabelDAO.save(models.LabelDTO(
                None, {'title': 'Foo',
                       'descripton': 'foo',
                       'type': models.LabelDTO.LABEL_TYPE_COURSE_TRACK}))
            self.bar_id = models.LabelDAO.save(models.LabelDTO(
                None, {'title': 'Bar',
                       'descripton': 'bar',
                       'type': models.LabelDTO.LABEL_TYPE_COURSE_TRACK}))
            self.baz_id = models.LabelDAO.save(models.LabelDTO(
                None, {'title': 'Baz',
                       'descripton': 'baz',
                       'type': models.LabelDTO.LABEL_TYPE_COURSE_TRACK}))
            self.quux_id = models.LabelDAO.save(models.LabelDTO(
                None, {'title': 'Quux',
                       'descripton': 'quux',
                       'type': models.LabelDTO.LABEL_TYPE_GENERAL}))

        # Register a student for that course.
        actions.login(REGISTERED_STUDENT_EMAIL)
        actions.register(self, REGISTERED_STUDENT_NAME, COURSE_NAME)
        actions.logout()

        # Add some units to the course.
        self._course = courses.Course(
            None, app_context=sites.get_all_courses()[0])
        self._unit_no_labels = self._course.add_unit()
        self._unit_no_labels.title = 'Unit No Labels'
        self._unit_no_labels.availability = courses.AVAILABILITY_AVAILABLE
        self._course.add_lesson(self._unit_no_labels)
        self._unit_labels_foo = self._course.add_unit()
        self._unit_labels_foo.title = 'Unit Labels: Foo'
        self._unit_labels_foo.availability = courses.AVAILABILITY_AVAILABLE
        self._unit_labels_foo.labels = str(self.foo_id)
        self._course.add_lesson(self._unit_labels_foo)
        self._unit_labels_foo_bar = self._course.add_unit()
        self._unit_labels_foo_bar.title = 'Unit Labels: Bar, Foo'
        self._unit_labels_foo_bar.availability = courses.AVAILABILITY_AVAILABLE
        self._unit_labels_foo_bar.labels = '%s %s' % (self.bar_id, self.foo_id)
        self._course.add_lesson(self._unit_labels_foo_bar)
        self._unit_labels_quux = self._course.add_unit()
        self._unit_labels_quux.title = 'Unit Labels: Quux'
        self._unit_labels_quux.availability = courses.AVAILABILITY_AVAILABLE
        self._unit_labels_quux.labels = str(self.quux_id)
        self._course.add_lesson(self._unit_labels_quux)
        self._unit_labels_foo_quux = self._course.add_unit()
        self._unit_labels_foo_quux.title = 'Unit Labels: Foo Quux'
        self._unit_labels_foo_quux.availability = courses.AVAILABILITY_AVAILABLE
        self._unit_labels_foo_quux.labels = '%s %s' % (str(self.foo_id),
                                                       str(self.quux_id))
        self._course.add_lesson(self._unit_labels_foo_quux)
        self._course.save()

    def tearDown(self):
        super(StudentTracksTest, self).tearDown()
        sites.reset_courses()

    def _choose_tracks(self, label_ids):
        response = self.get(STUDENT_SETTINGS_URL)
        form = response.forms['student_set_tracks']
        labels_by_ids = {}
        for label_field in form.fields['labels']:
            labels_by_ids[label_field.id] = label_field
        for label_id in label_ids:
            labels_by_ids['label_id_%d' % label_id].checked = True
        self.submit(form, response)

    def test_unit_matching_no_labels(self):
        actions.login(REGISTERED_STUDENT_EMAIL)
        self._choose_tracks([])
        response = self.get(COURSE_OVERVIEW_URL)
        self.assertIn(self._unit_no_labels.title, response.body)
        self.assertIn(self._unit_labels_foo.title, response.body)
        self.assertIn(self._unit_labels_foo_bar.title, response.body)

    def test_unit_matching_foo(self):
        actions.login(REGISTERED_STUDENT_EMAIL)
        self._choose_tracks([self.foo_id])
        response = self.get(COURSE_OVERVIEW_URL)
        self.assertIn(self._unit_no_labels.title, response.body)
        self.assertIn(self._unit_labels_foo.title, response.body)
        self.assertIn(self._unit_labels_foo_bar.title, response.body)

    def test_unit_matching_foo_bar(self):
        actions.login(REGISTERED_STUDENT_EMAIL)
        self._choose_tracks([self.foo_id, self.bar_id])
        response = self.get(COURSE_OVERVIEW_URL)
        self.assertIn(self._unit_no_labels.title, response.body)
        self.assertIn(self._unit_labels_foo.title, response.body)
        self.assertIn(self._unit_labels_foo_bar.title, response.body)

    def test_unit_matching_bar(self):
        actions.login(REGISTERED_STUDENT_EMAIL)
        self._choose_tracks([self.bar_id])
        response = self.get(COURSE_OVERVIEW_URL)
        self.assertIn(self._unit_no_labels.title, response.body)
        self.assertNotIn(self._unit_labels_foo.title, response.body)
        self.assertIn(self._unit_labels_foo_bar.title, response.body)

    def test_unit_matching_baz(self):
        actions.login(REGISTERED_STUDENT_EMAIL)
        self._choose_tracks([self.baz_id])
        response = self.get(COURSE_OVERVIEW_URL)
        self.assertIn(self._unit_no_labels.title, response.body)
        self.assertNotIn(self._unit_labels_foo.title, response.body)
        self.assertNotIn(self._unit_labels_foo_bar.title, response.body)

    def test_unit_with_general_and_tracks_student_with_no_tracks(self):
        actions.login(REGISTERED_STUDENT_EMAIL)
        response = self.put(STUDENT_LABELS_URL, {'labels': str(self.quux_id)})
        response = self.get(COURSE_OVERVIEW_URL)
        self.assertIn(self._unit_labels_quux.title, response.body)
        self.assertIn(self._unit_labels_foo_quux.title, response.body)

    def test_unit_with_general_and_tracks_student_with_matching_tracks(self):
        actions.login(REGISTERED_STUDENT_EMAIL)
        response = self.put(STUDENT_LABELS_URL, {'labels': str(self.foo_id)})
        response = self.get(COURSE_OVERVIEW_URL)
        self.assertIn(self._unit_labels_quux.title, response.body)
        self.assertIn(self._unit_labels_foo_quux.title, response.body)

    def test_unit_with_general_and_tracks_student_with_mismatched_tracks(self):
        actions.login(REGISTERED_STUDENT_EMAIL)
        response = self.put(STUDENT_LABELS_URL, {'labels': str(self.bar_id)})
        response = self.get(COURSE_OVERVIEW_URL)
        self.assertIn(self._unit_labels_quux.title, response.body)
        self.assertNotIn(self._unit_labels_foo_quux.title, response.body)

    def test_load_units_student_no_labels(self):
        actions.login(REGISTERED_STUDENT_EMAIL)
        self._choose_tracks([])
        response = self.get(COURSE_OVERVIEW_URL)
        self.assertEquals(200, self.get('unit?unit=%d' %
                                        self._unit_no_labels.unit_id,
                                        response).status_int)
        self.assertEquals(200, self.get('unit?unit=%d' %
                                        self._unit_labels_foo.unit_id,
                                        response).status_int)
        self.assertEquals(200, self.get('unit?unit=%d' %
                                        self._unit_labels_foo_bar.unit_id,
                                        response).status_int)
        self.assertEquals(200, self.get('unit?unit=%d' %
                                        self._unit_labels_quux.unit_id,
                                        response).status_int)
        self.assertEquals(200, self.get('unit?unit=%d' %
                                        self._unit_labels_foo_quux.unit_id,
                                        response).status_int)

    def test_load_units_student_labeled_foo(self):
        actions.login(REGISTERED_STUDENT_EMAIL)
        self._choose_tracks([self.foo_id])
        response = self.get(COURSE_OVERVIEW_URL)
        self.assertEquals(200, self.get('unit?unit=%d' %
                                        self._unit_no_labels.unit_id,
                                        response).status_int)
        self.assertEquals(200, self.get('unit?unit=%d' %
                                        self._unit_labels_foo.unit_id,
                                        response).status_int)
        self.assertEquals(200, self.get('unit?unit=%d' %
                                        self._unit_labels_foo_bar.unit_id,
                                        response).status_int)
        self.assertEquals(200, self.get('unit?unit=%d' %
                                        self._unit_labels_quux.unit_id,
                                        response).status_int)
        self.assertEquals(200, self.get('unit?unit=%d' %
                                        self._unit_labels_foo_quux.unit_id,
                                        response).status_int)
