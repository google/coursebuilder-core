# Copyright 2012 Google Inc. All Rights Reserved.
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

"""Models and helper utilities for the review workflow."""

__author__ = 'mgainer@google.com (Mike Gainer)'

from common import users
from common import utils as common_utils
from controllers import utils
import models
from models import transforms

PARAMETER_LABELS = 'labels'
STUDENT_LABELS_URL = '/rest/student/labels'


class StudentLabelsRestHandler(utils.ApplicationHandler):
    """Allow web pages to mark students as having labels."""

    def get(self):
        student = self._setup()
        if not student:
            return
        label_ids = self._get_existing_label_ids(student)
        return self._send_response(student, label_ids)

    def put(self):
        student = self._setup()
        if not student:
            return
        request_ids = self._get_request_label_ids()
        if not self._request_label_ids_ok(request_ids):
            return
        self._save_labels(student, request_ids)
        return self._send_response(student, request_ids)

    def post(self):
        student = self._setup()
        if not student:
            return
        request_ids = self._get_request_label_ids()
        if not self._request_label_ids_ok(request_ids):
            return
        existing_ids = self._get_existing_label_ids(student)
        label_ids = existing_ids.union(request_ids)
        self._save_labels(student, existing_ids.union(label_ids))
        return self._send_response(student, label_ids)

    def delete(self):
        student = self._setup()
        if not student:
            return

        label_ids = []
        self._save_labels(student, label_ids)
        return self._send_response(student, label_ids)

    def _setup(self):
        user = users.get_current_user()
        if not user:
            self._send_response(None, [], 403, 'No logged-in user')
            return None
        student = (
            models.StudentProfileDAO.get_enrolled_student_by_user_for(
                user, self.app_context))
        if not student or not student.is_enrolled:
            self._send_response(None, [], 403, 'User is not enrolled')
            return None
        return student

    def _get_request_label_ids(self):
        return set([int(l) for l in common_utils.text_to_list(
            self.request.get(PARAMETER_LABELS))])

    def _request_label_ids_ok(self, label_ids):
        all_label_ids = {label.id for label in models.LabelDAO.get_all()}
        invalid = label_ids.difference(all_label_ids)
        if invalid:
            self._send_response(
                None, [], 400, 'Unknown label id(s): %s' %
                ([str(label_id) for label_id in invalid]))
            return False
        return True

    def _get_existing_label_ids(self, student):
        # Prune label IDs that no longer refer to a valid Label object.
        all_label_ids = {label.id for label in models.LabelDAO.get_all()}
        existing_labels = set([int(label_id) for label_id in
                               common_utils.text_to_list(student.labels)])
        return existing_labels.intersection(all_label_ids)

    def _save_labels(self, student, labels):
        student.labels = common_utils.list_to_text(labels)
        student.put()

    def _send_response(self, student, label_ids, status_code=None,
                       message=None):
        transforms.send_json_response(
            self, status_code or 200, message or 'OK',
            {'labels': list(label_ids)})


def get_namespaced_handlers():
    ret = []
    ret.append((STUDENT_LABELS_URL, StudentLabelsRestHandler))
    return ret
