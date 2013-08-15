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

import datetime

from models import models
from tests.functional import actions

# Disable complaints about docstrings for self-documenting tests.
# pylint: disable-msg=g-missing-docstring


class EventEntityTestCase(actions.ExportTestBase):

    def test_for_export_transforms_correctly(self):
        event = models.EventEntity(source='source', user_id='1')
        key = event.put()
        exported = event.for_export(self.transform)

        self.assert_blacklisted_properties_removed(event, exported)
        self.assertEqual('source', event.source)
        self.assertEqual('transformed_1', exported.user_id)
        self.assertEqual(key, models.EventEntity.safe_key(key, self.transform))


class PersonalProfileTestCase(actions.ExportTestBase):

    def test_for_export_transforms_correctly_and_sets_safe_key(self):
        date_of_birth = datetime.date.today()
        email = 'test@example.com'
        legal_name = 'legal_name'
        nick_name = 'nick_name'
        user_id = '1'
        profile = models.PersonalProfile(
            date_of_birth=date_of_birth, email=email, key_name=user_id,
            legal_name=legal_name, nick_name=nick_name)
        profile.put()
        exported = profile.for_export(self.transform)

        self.assert_blacklisted_properties_removed(profile, exported)
        self.assertEqual(
            self.transform(user_id), exported.safe_key.name())


class QuestionDAOTestCase(actions.TestBase):
    """Functional tests for QuestionDAO."""

    # Name determined by parent. pylint: disable-msg=g-bad-name
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


class StudentTestCase(actions.ExportTestBase):

    def test_for_export_transforms_correctly(self):
        user_id = '1'
        student = models.Student(key_name='name', user_id='1', is_enrolled=True)
        key = student.put()
        exported = student.for_export(self.transform)

        self.assert_blacklisted_properties_removed(student, exported)
        self.assertTrue(exported.is_enrolled)
        self.assertEqual('transformed_1', exported.user_id)
        self.assertEqual(
            'transformed_' + user_id, exported.key_by_user_id.name())
        self.assertEqual(
            models.Student.safe_key(key, self.transform), exported.safe_key)

    def test_get_key_does_not_transform_by_default(self):
        user_id = 'user_id'
        student = models.Student(key_name='name', user_id=user_id)
        student.put()
        self.assertEqual(user_id, student.get_key().name())

    def test_safe_key_transforms_name(self):
        key = models.Student(key_name='name').put()
        self.assertEqual(
            'transformed_name',
            models.Student.safe_key(key, self.transform).name())


class StudentAnswersEntityTestCase(actions.ExportTestBase):

    def test_safe_key_transforms_name(self):
        student_key = models.Student(key_name='name').put()
        answers = models.StudentAnswersEntity(key_name=student_key.name())
        answers_key = answers.put()
        self.assertEqual(
            'transformed_name',
            models.StudentAnswersEntity.safe_key(
                answers_key, self.transform).name())


class StudentPropertyEntityTestCase(actions.ExportTestBase):

    def test_safe_key_transforms_user_id_component(self):
        user_id = 'user_id'
        student = models.Student(key_name='email@example.com', user_id=user_id)
        student.put()
        property_name = 'property-name'
        student_property_key = models.StudentPropertyEntity.create(
            student, property_name).put()
        self.assertEqual(
            'transformed_%s-%s' % (user_id, property_name),
            models.StudentPropertyEntity.safe_key(
                student_property_key, self.transform).name())
