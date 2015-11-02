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

"""Tests for the question tag."""

__author__ = 'John Orr (jorr@google.com)'

from common import utils
from controllers import sites
from models import courses
from models import models
from models import transforms
from tests.functional import actions

import base64
import re


ADMIN_EMAIL = 'admin@foo.com'
STUDENT_EMAIL = 'student@foo.com'
STUDENT_NAME = 'A S Tudent'
COURSE_NAME = 'assessment_tags'

# TODO(jorr): Add a full set of functional tests for the behavior of the
# <question> tag to core CB.


class MultipleChoiceTagTests(actions.TestBase):
    MC_1_JSON = """
{
  "type": 0,
  "version": "1.5",
  "question": "Choose A",
  "description": "choose a",
  "multiple_selections": false,
  "choices": [
    {"text": "A", "feedback": "", "score": 1.0},
    {"text": "B", "feedback": "", "score": 0.0},
    {"text": "C", "feedback": "", "score": 0.0},
    {"text": "D", "feedback": "", "score": 0.0}
  ]
}
"""
    MC_2_JSON = """
{
  "type": 0,
  "version": "1.5",
  "question": "Choose 1",
  "description": "choose 1",
  "multiple_selections": false,
  "choices": [
    {"text": "1", "feedback": "", "score": 1.0},
    {"text": "2", "feedback": "", "score": 0.0},
    {"text": "3", "feedback": "", "score": 0.0},
    {"text": "4", "feedback": "", "score": 0.0}
  ]
}
"""
    QG_1_JSON_TEMPLATE = """
{
  "version": "1.5",
  "introduction": "",
  "description": "group 1",
  "items": [
    {"question": %s, "weight": 1.0},
    {"question": %s, "weight": 1.0}
  ]
}
"""

    def setUp(self):
        super(MultipleChoiceTagTests, self).setUp()

        self.base = '/' + COURSE_NAME
        self.app_context = actions.simple_add_course(
            COURSE_NAME, ADMIN_EMAIL, 'Assessment Tags')
        self.namespace = 'ns_%s' % COURSE_NAME

        with utils.Namespace(self.namespace):
            dto = models.QuestionDTO(None, transforms.loads(self.MC_1_JSON))
            self.mc_1_id = models.QuestionDAO.save(dto)
            dto = models.QuestionDTO(None, transforms.loads(self.MC_2_JSON))
            self.mc_2_id = models.QuestionDAO.save(dto)
            dto = models.QuestionGroupDTO(
                None, transforms.loads(
                    self.QG_1_JSON_TEMPLATE % (self.mc_1_id, self.mc_2_id)))
            self.qg_1_id = models.QuestionGroupDAO.save(dto)

        self.course = courses.Course(None, self.app_context)
        self.assessment = self.course.add_assessment()
        self.assessment.availability = courses.AVAILABILITY_AVAILABLE
        self.assessment.html_content = (
            '<question quid="%s" weight="1" instanceid="q1"></question>'
            '<question-group qgid="%s" instanceid="qg1"></question-group' % (
                self.mc_1_id, self.qg_1_id))
        self.course.save()

    def tearDown(self):
        del sites.Registry.test_overrides[sites.GCB_COURSES_CONFIG.name]
        super(MultipleChoiceTagTests, self).tearDown()

    def test_question_data_is_obfuscated(self):
        response = self.get('assessment?name=%s' % self.assessment.unit_id)

        # Expect the question to be encoded
        match = re.search(
            r'questionData\[\'q1\'\] = JSON.parse\(window.atob\(\"([^\"]*)\"\)',
            response.body)
        self.assertIsNotNone(match)
        decoded_dict = transforms.loads(base64.b64decode(match.group(1)))
        self.assertEquals(self.mc_1_id, int(decoded_dict['quid']))

        # Expect the question group to be encoded
        match = re.search(
            r'questionData\[\'qg1\'\] '
            r'= JSON.parse\(window.atob\(\"([^\"]*)\"\)',
            response.body)
        self.assertIsNotNone(match)
        decoded_dict = transforms.loads(base64.b64decode(match.group(1)))
        self.assertIn('qg1.0.%s' % self.mc_1_id, decoded_dict)
