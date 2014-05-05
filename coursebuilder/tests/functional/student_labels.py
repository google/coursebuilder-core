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

from models import transforms
from tests.functional import actions

REGISTERED_STUDENT_EMAIL = 'foo@bar.com'
REGISTERED_STUDENT_NAME = 'John Smith'
UNREGISTERED_STUDENT_EMAIL = 'bar@bar.com'
STUDENT_LABELS_URL = '/rest/student/labels/tracks'


class StudentLabelsTest(actions.TestBase):

    def setUp(self):
        super(StudentLabelsTest, self).setUp()
        actions.login(REGISTERED_STUDENT_EMAIL)
        actions.register(self, REGISTERED_STUDENT_NAME)
        actions.logout()

    # ------------------------------- failures when unsupported label subtye
    def test_bad_url_404(self):
        actions.login(UNREGISTERED_STUDENT_EMAIL)
        response = self.get('/rest/student/labels/interests',
                            expect_errors=True)
        self.assertEquals(404, response.status_int)

    # ------------------------------- failures when not logged in.
    def _verify_error(self, response, expected_message):
        self.assertEquals(200, response.status_int)
        content = transforms.loads(response.body)
        self.assertEquals(403, content['status'])
        self.assertEquals(expected_message, content['message'])
        self.assertNotIn('payload', content)

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
        self.assertEquals(200, content['status'])
        self.assertEquals('OK', content['message'])
        payload = transforms.loads(content['payload'])
        self.assertItemsEqual(expected_labels, payload['labels'])

    def test_get_labels_empty_on_registration(self):
        actions.login(REGISTERED_STUDENT_EMAIL)
        self._verify_labels(self.get(STUDENT_LABELS_URL), [])

    def test_put_labels_to_blank(self):
        actions.login(REGISTERED_STUDENT_EMAIL)
        self._verify_labels(self.put(STUDENT_LABELS_URL,
                                     {'labels': 'foo,bar,baz'}),
                            ['foo', 'bar', 'baz'])
        self._verify_labels(self.get(STUDENT_LABELS_URL), ['foo', 'bar', 'baz'])

    def test_post_labels_to_blank(self):
        actions.login(REGISTERED_STUDENT_EMAIL)
        self._verify_labels(self.put(STUDENT_LABELS_URL, {'labels': 'a,b,c'}),
                            ['a', 'b', 'c'])
        self._verify_labels(self.get(STUDENT_LABELS_URL), ['a', 'b', 'c'])

    def test_delete_labels_from_blank(self):
        actions.login(REGISTERED_STUDENT_EMAIL)
        self._verify_labels(self.delete(STUDENT_LABELS_URL), [])

    def test_put_labels_replaces(self):
        actions.login(REGISTERED_STUDENT_EMAIL)
        self._verify_labels(self.put(STUDENT_LABELS_URL, {'labels': 'foo,bar'}),
                            ['foo', 'bar'])
        self._verify_labels(self.put(STUDENT_LABELS_URL, {'labels': 'baz'}),
                            ['baz'])

    def test_post_labels_merges(self):
        actions.login(REGISTERED_STUDENT_EMAIL)
        self._verify_labels(self.put(STUDENT_LABELS_URL, {'labels': 'foo,bar'}),
                            ['foo', 'bar'])
        self._verify_labels(self.post(STUDENT_LABELS_URL, {'labels': 'baz'}),
                            ['foo', 'bar', 'baz'])

    def test_delete_labels_deletes(self):
        actions.login(REGISTERED_STUDENT_EMAIL)
        self._verify_labels(self.put(STUDENT_LABELS_URL, {'labels': 'foo,bar'}),
                            ['foo', 'bar'])
        self._verify_labels(self.delete(STUDENT_LABELS_URL), [])
