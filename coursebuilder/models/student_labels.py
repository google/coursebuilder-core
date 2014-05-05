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

import re

from common import utils as common_utils
from controllers import utils
import models
from models import transforms

from google.appengine.api import users

PARAMETER_LABELS = 'labels'
STUDENT_LABELS_URL = '/rest/student/labels/'

GROUP_TO_PROPERTY = {
    'tracks': models.Student.labels_for_tracks,
    # Extend when we need more kinds of labels.  This should be the
    # only place where a new label type needs to be registered; code below
    # is done in terms of the property accessor objects listed here.
}


class StudentLabelsRestHandler(utils.ApplicationHandler):
    """Allow web pages to mark students as having labels."""

    def get(self):
        student, group = self._setup()
        if not student or not group:
            return

        return self._send_response(student, group)

    def put(self):
        student, group = self._setup()
        if not student or not group:
            return

        labels = common_utils.list_to_text(
            common_utils.text_to_list(self.request.get(PARAMETER_LABELS)))
        self._save_labels(student, group, labels)
        return self._send_response(student, group)

    def post(self):
        student, group = self._setup()
        if not student or not group:
            return

        request_labels = set(
            common_utils.text_to_list(self.request.get(PARAMETER_LABELS)))
        existing_labels = set(
            common_utils.text_to_list(group.__get__(student, models.Student)))
        existing_labels.update(request_labels)
        self._save_labels(student, group,
                          common_utils.list_to_text(existing_labels))
        return self._send_response(student, group)

    def delete(self):
        student, group = self._setup()
        if not student or not group:
            return

        self._save_labels(student, group, '')
        return self._send_response(student, group)

    def _setup(self):
        user = users.get_current_user()
        if not user:
            self._send_response(None, None, 403, 'No logged-in user')
            return None, None
        student = (
            models.StudentProfileDAO.get_enrolled_student_by_email_for(
                user.email(), self.app_context))
        if not student or not student.is_enrolled:
            self._send_response(None, None, 403, 'User is not enrolled')
            return None, None

        group_name = re.sub('.*' + STUDENT_LABELS_URL, '', self.request.path)
        if not group_name:
            self._send_response(None, None, 400, 'No label group specified')
            return None, None

        if group_name not in GROUP_TO_PROPERTY:
            self._send_response(None, None, 400,
                                'Label group not in: ' + ', '.join(
                                    GROUP_TO_PROPERTY.keys()))
            return None, None

        return student, GROUP_TO_PROPERTY[group_name]

    def _save_labels(self, student, group, labels):
        with common_utils.Namespace(self.app_context.get_namespace_name()):
            group.__set__(student, labels)
            student.put()

    def _send_response(self, student, group, status_code=None, message=None):
        payload = {}
        if student and group:
            payload['labels'] = common_utils.text_to_list(
                group.__get__(student, models.Student))
        transforms.send_json_response(
            self, status_code or 200, message or 'OK', payload)


def get_namespaced_handlers():
    ret = []
    for name in GROUP_TO_PROPERTY:
        ret.append(('/rest/student/labels/' + name, StudentLabelsRestHandler))
    return ret
