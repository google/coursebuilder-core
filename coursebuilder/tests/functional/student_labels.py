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

from common import crypto
from common import users
from common import utils as common_utils
from models import models
from models import transforms
from tests.functional import actions

COURSE_NAME = 'labels_test'
COURSE_TITLE = 'Labels Test'
NAMESPACE = 'ns_%s' % COURSE_NAME
ADMIN_EMAIL = 'admin@foo.com'
REGISTERED_STUDENT_EMAIL = 'foo@bar.com'
REGISTERED_STUDENT_NAME = 'John Smith'
UNREGISTERED_STUDENT_EMAIL = 'bar@bar.com'
STUDENT_LABELS_URL = '/%s/rest/student/labels' % COURSE_NAME
STUDENT_SETTRACKS_URL = '/%s/student/settracks' % COURSE_NAME
ANALYTICS_URL = '/%s/dashboard?action=analytics_students' % COURSE_NAME
LABELS_STUDENT_EMAIL = 'labels@bar.com'


class FakeContext(object):

    def __init__(self, namespace):
        self._namespace = namespace

    def get_namespace_name(self):
        return self._namespace


class StudentLabelsTest(actions.TestBase):

    def setUp(self):
        super(StudentLabelsTest, self).setUp()
        actions.simple_add_course(COURSE_NAME, ADMIN_EMAIL, COURSE_TITLE)

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

        actions.login(REGISTERED_STUDENT_EMAIL)
        actions.register(self, REGISTERED_STUDENT_NAME, COURSE_NAME)
        actions.logout()

    # ------------------------------- failures when unsupported label subtype
    def test_bad_url_404(self):
        actions.login(UNREGISTERED_STUDENT_EMAIL)
        response = self.get('/rest/student/labels/interests',
                            expect_errors=True)
        self.assertEquals(404, response.status_int)

    # ------------------------------- failures when not logged in.
    def _verify_error(self, response, expected_message, expected_status=None):
        self.assertEquals(200, response.status_int)
        content = transforms.loads(response.body)
        self.assertEquals(expected_message, content['message'])
        self.assertEquals(expected_status or 403, content['status'])
        payload = transforms.loads(content['payload'])
        self.assertItemsEqual([], payload['labels'])

    def test_get_fails_not_logged_in(self):
        self._verify_error(self.get(STUDENT_LABELS_URL),
                           'No logged-in user')

    def test_post_fails_not_logged_in(self):
        self._verify_error(self.post(STUDENT_LABELS_URL, {}),
                           'No logged-in user')

    def test_put_fails_not_logged_in(self):
        self._verify_error(self.put(STUDENT_LABELS_URL, {}),
                           'No logged-in user')

    def test_delete_fails_not_logged_in(self):
        self._verify_error(self.delete(STUDENT_LABELS_URL),
                           'No logged-in user')

    # ------------------------------- failures when not registered student.
    def test_get_fails_logged_in_unregistered(self):
        actions.login(UNREGISTERED_STUDENT_EMAIL)
        self._verify_error(self.get(STUDENT_LABELS_URL),
                           'User is not enrolled')

    def test_post_fails_logged_in_unregistered(self):
        actions.login(UNREGISTERED_STUDENT_EMAIL)
        self._verify_error(self.post(STUDENT_LABELS_URL, {}),
                           'User is not enrolled')

    def test_put_fails_logged_in_unregistered(self):
        actions.login(UNREGISTERED_STUDENT_EMAIL)
        self._verify_error(self.put(STUDENT_LABELS_URL, {}),
                           'User is not enrolled')

    def test_delete_fails_logged_in_unregistered(self):
        actions.login(UNREGISTERED_STUDENT_EMAIL)
        self._verify_error(self.delete(STUDENT_LABELS_URL),
                           'User is not enrolled')

    # ------------------------------- Failure when put/post bad label ID

    def test_put_invalid_label_id(self):
        actions.login(REGISTERED_STUDENT_EMAIL)
        self._verify_error(self.put(STUDENT_LABELS_URL, {'labels': '123'}),
                           'Unknown label id(s): [\'123\']', 400)

    def test_post_invalid_label_id(self):
        actions.login(REGISTERED_STUDENT_EMAIL)
        self._verify_error(self.post(STUDENT_LABELS_URL, {'labels': '123'}),
                           'Unknown label id(s): [\'123\']', 400)

    # ------------------------------- Bad tags parameter
    def test_put_no_labels_param(self):
        actions.login(REGISTERED_STUDENT_EMAIL)
        self._verify_labels(self.put(STUDENT_LABELS_URL, {}), [])

    def test_post_no_labels_param(self):
        actions.login(REGISTERED_STUDENT_EMAIL)
        self._verify_labels(self.post(STUDENT_LABELS_URL, {}), [])

    def test_put_blank_labels_param(self):
        actions.login(REGISTERED_STUDENT_EMAIL)
        self._verify_labels(self.put(STUDENT_LABELS_URL, 'labels'), [])

    def test_post_blank_labels_param(self):
        actions.login(REGISTERED_STUDENT_EMAIL)
        self._verify_labels(self.post(STUDENT_LABELS_URL, 'labels'), [])

    # ------------------------------- Actual manipulations.
    def _verify_labels(self, response, expected_labels):
        self.assertEquals(200, response.status_int)
        content = transforms.loads(response.body)
        self.assertEquals('OK', content['message'])
        self.assertEquals(200, content['status'])
        payload = transforms.loads(content['payload'])
        self.assertItemsEqual(expected_labels, payload['labels'])

    def test_get_labels_empty_on_registration(self):
        actions.login(REGISTERED_STUDENT_EMAIL)
        self._verify_labels(self.get(STUDENT_LABELS_URL), [])

    def test_put_labels_to_blank(self):
        actions.login(REGISTERED_STUDENT_EMAIL)
        self._verify_labels(
            self.put(STUDENT_LABELS_URL,
                     {'labels': '%d,%d,%d' % (
                         self.foo_id, self.bar_id, self.baz_id)}),
            [self.foo_id, self.bar_id, self.baz_id])
        self._verify_labels(self.get(STUDENT_LABELS_URL),
                            [self.foo_id, self.bar_id, self.baz_id])

    def test_post_labels_to_blank(self):
        actions.login(REGISTERED_STUDENT_EMAIL)
        self._verify_labels(
            self.post(STUDENT_LABELS_URL,
                      {'labels': '%d,%d' % (
                          self.foo_id, self.baz_id)}),
            [self.foo_id, self.baz_id])
        self._verify_labels(self.get(STUDENT_LABELS_URL),
                            [self.foo_id, self.baz_id])

    def test_delete_labels_from_blank(self):
        actions.login(REGISTERED_STUDENT_EMAIL)
        self._verify_labels(self.delete(STUDENT_LABELS_URL), [])

    def test_put_labels_replaces(self):
        actions.login(REGISTERED_STUDENT_EMAIL)
        self._verify_labels(
            self.put(STUDENT_LABELS_URL,
                     {'labels': '%d,%d' % (
                         self.foo_id, self.bar_id)}),
            [self.foo_id, self.bar_id])
        self._verify_labels(
            self.put(STUDENT_LABELS_URL,
                     {'labels': '%d' % self.baz_id}),
            [self.baz_id])

    def test_post_labels_merges(self):
        actions.login(REGISTERED_STUDENT_EMAIL)
        self._verify_labels(
            self.put(STUDENT_LABELS_URL,
                     {'labels': '%d,%d' % (self.foo_id, self.bar_id)}),
            [self.foo_id, self.bar_id])
        self._verify_labels(
            self.post(STUDENT_LABELS_URL, {'labels': '%d' % self.baz_id}),
            [self.foo_id, self.bar_id, self.baz_id])

    def test_delete_labels_deletes(self):
        actions.login(REGISTERED_STUDENT_EMAIL)
        self._verify_labels(
            self.put(STUDENT_LABELS_URL,
                     {'labels': '%d,%d' % (self.foo_id, self.bar_id)}),
            [self.foo_id, self.bar_id])
        self._verify_labels(self.delete(STUDENT_LABELS_URL), [])

    # ------------------------------------- Removal of broken label references
    def _add_broken_label_references(self):
        # Add some broken references to student's labels list.
        actions.login(REGISTERED_STUDENT_EMAIL)
        user = users.get_current_user()
        student = (
            models.StudentProfileDAO.get_enrolled_student_by_user_for(
                user, FakeContext(NAMESPACE)))
        student.labels = '123123123 456456456 %d' % self.foo_id
        student.put()

    def test_get_expired_label_ids(self):
        self._add_broken_label_references()
        self._verify_labels(self.get(STUDENT_LABELS_URL), [self.foo_id])

    def test_put_expired_label_ids(self):
        self._add_broken_label_references()
        self._verify_labels(self.put(STUDENT_LABELS_URL,
                                     {'labels': '%d' % (self.bar_id)}),
                            [self.bar_id])

    def test_post_expired_label_ids(self):
        self._add_broken_label_references()
        self._verify_labels(self.post(STUDENT_LABELS_URL,
                                      {'labels': '%d' % (self.bar_id)}),
                            [self.foo_id, self.bar_id])

    def test_delete_expired_label_ids(self):
        self._add_broken_label_references()
        self._verify_labels(self.delete(STUDENT_LABELS_URL,
                                        {'labels': '%d' % (self.bar_id)}),
                            [])

    # ------------------------------------ POST on student tracks selection
    def test_post_tracks_replaces(self):
        actions.login(REGISTERED_STUDENT_EMAIL)
        xsrf_token = crypto.XsrfTokenManager.create_xsrf_token('student-edit')
        self.put(STUDENT_LABELS_URL,
                 {'labels': '%d,%d' % (
                     self.foo_id, self.bar_id)})
        self.post(STUDENT_SETTRACKS_URL,
                  {'labels': '%d' % self.baz_id,
                   'xsrf_token': xsrf_token})
        self._verify_labels(self.get(STUDENT_LABELS_URL), [self.baz_id])

    def test_post_tracks_clears(self):
        actions.login(REGISTERED_STUDENT_EMAIL)
        xsrf_token = crypto.XsrfTokenManager.create_xsrf_token('student-edit')
        self.put(STUDENT_LABELS_URL,
                 {'labels': '%d,%d' % (
                     self.foo_id, self.bar_id)})
        self.post(STUDENT_SETTRACKS_URL,
                  {'xsrf_token': xsrf_token})
        self._verify_labels(self.get(STUDENT_LABELS_URL), [])

    def test_post_tracks_sets(self):
        actions.login(REGISTERED_STUDENT_EMAIL)
        xsrf_token = crypto.XsrfTokenManager.create_xsrf_token('student-edit')
        self.post(STUDENT_SETTRACKS_URL,
                  {'labels': '%d' % self.foo_id,
                   'xsrf_token': xsrf_token})
        self._verify_labels(self.get(STUDENT_LABELS_URL), [self.foo_id])

    def test_post_tracks_does_not_affect_non_tracks_labels(self):
        actions.login(REGISTERED_STUDENT_EMAIL)
        xsrf_token = crypto.XsrfTokenManager.create_xsrf_token('student-edit')
        self.put(STUDENT_LABELS_URL,
                 {'labels': '%d,%d' % (
                     self.foo_id, self.quux_id)})
        self.post(STUDENT_SETTRACKS_URL,
                  {'labels': '%d' % self.baz_id,
                   'xsrf_token': xsrf_token})
        self._verify_labels(self.get(STUDENT_LABELS_URL), [self.baz_id,
                                                           self.quux_id])

    # ---------------------------------- Analytics page.
    def test_analytics(self):
        actions.login(REGISTERED_STUDENT_EMAIL)
        self.put(STUDENT_LABELS_URL,
                 {'labels': '%d,%d' % (
                     self.foo_id, self.quux_id)})

        actions.login(ADMIN_EMAIL)
        response = self.get(ANALYTICS_URL)
        self.submit(response.forms['gcb-run-visualization-labels_on_students'],
                    response)
        self.execute_all_deferred_tasks()

        rest_url = (
            '/%s/rest/data/labels_on_students/items' % COURSE_NAME +
            '?data_source_token=%s&page_number=0&chunk_size=0' %
            crypto.XsrfTokenManager.create_xsrf_token('data_source_access'))
        label_counts = transforms.loads(self.get(rest_url).body)
        self.assertEquals(
            [{'title': 'Quux',
              'count': 1,
              'type': 'General',
              'description': ''},
             {'title': 'Bar',
              'count': 0,
              'type': 'Course Track',
              'description': ''},
             {'title': 'Baz',
              'count': 0,
              'type': 'Course Track',
              'description': ''},
             {'title': 'Foo',
              'count': 1,
              'type': 'Course Track',
              'description': ''}],
            label_counts['data'])

    # --------------------------------- Registration
    def test_register_with_labels(self):
        student_name = 'John Smith from Back East'
        actions.login(LABELS_STUDENT_EMAIL)
        user = users.get_current_user()
        response = actions.view_registration(self, COURSE_NAME)
        register_form = actions.get_form_by_action(response, 'register')
        self.post('/%s/%s' % (COURSE_NAME, register_form.action), {
            'form01': student_name,
            'xsrf_token': register_form['xsrf_token'].value,
            'labels': common_utils.list_to_text([self.bar_id, self.baz_id])})
        self._verify_labels(self.get(STUDENT_LABELS_URL), [self.bar_id,
                                                           self.baz_id])
        with common_utils.Namespace(NAMESPACE):
            student = models.Student.get_enrolled_student_by_user(user)
            self.assertEquals(student.name, student_name)
