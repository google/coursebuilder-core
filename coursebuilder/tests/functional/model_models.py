# Copyright 2013 Google Inc. All Rights Reserved.
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

"""Functional tests for models.models."""

__author__ = [
    'johncox@google.com (John Cox)',
]

from models import models
from tests.functional import actions


class QuestionDAOTestCase(actions.TestBase):
    """Functional tests for QuestionDAO."""

    # Method name set by superclass. pylint: disable-msg=g-bad-name
    def setUp(self):
        """Sets up datastore contents."""
        super(QuestionDAOTestCase, self).setUp()
        self.used_twice_question_id = 1
        self.used_twice_question_dto = models.QuestionDTO(
            self.used_twice_question_id, {})

        self.used_once_question_id = 2
        self.used_once_question_dto = models.QuestionDTO(
            self.used_once_question_id, {})

        self.unused_question_id = 3
        self.unused_question_dto = models.QuestionDTO(
            self.unused_question_id, {})
        models.QuestionDAO.save_all([
            self.used_twice_question_dto, self.used_once_question_dto,
            self.unused_question_dto])

        # Handcoding the dicts. This is dangerous because they're handcoded
        # elsewhere, the implementations could fall out of sync, and these tests
        # may then pass erroneously.
        self.first_question_group_description = 'first_question_group'
        self.first_question_group_id = 4
        self.first_question_group_dto = models.QuestionGroupDTO(
            self.first_question_group_id,
            {'description': self.first_question_group_description,
             'items': [{'question': str(self.used_once_question_id)}]})

        self.second_question_group_description = 'second_question_group'
        self.second_question_group_id = 5
        self.second_question_group_dto = models.QuestionGroupDTO(
            self.second_question_group_id,
            {'description': self.second_question_group_description,
             'items': [{'question': str(self.used_twice_question_id)}]})

        self.third_question_group_description = 'third_question_group'
        self.third_question_group_id = 6
        self.third_question_group_dto = models.QuestionGroupDTO(
            self.third_question_group_id,
            {'description': self.third_question_group_description,
             'items': [{'question': str(self.used_twice_question_id)}]})

        models.QuestionGroupDAO.save_all([
            self.first_question_group_dto, self.second_question_group_dto,
            self.third_question_group_dto])

    def test_used_by_returns_description_of_single_question_group(self):
        self.assertEqual(
            [self.first_question_group_description],
            models.QuestionDAO.used_by(self.used_once_question_id))

    def test_used_by_returns_descriptions_of_multiple_question_groups(self):
        self.assertEqual(
            [self.second_question_group_description,
             self.third_question_group_description],
            models.QuestionDAO.used_by(self.used_twice_question_id))

    def test_used_by_returns_empty_list_for_unused_question(self):
        not_found_id = 7
        self.assertFalse(models.QuestionDAO.load(not_found_id))
        self.assertEqual([], models.QuestionDAO.used_by(not_found_id))
