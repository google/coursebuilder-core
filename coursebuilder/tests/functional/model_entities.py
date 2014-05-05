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

from models import entities
from models import transforms
from tests.functional import actions
from google.appengine.ext import db


class FirstChild(entities.BaseEntity):
    first_kept = db.Property()
    first_removed = db.Property()

    _PROPERTY_EXPORT_BLACKLIST = [first_removed]


class SecondChild(FirstChild):
    second_kept = db.Property()
    second_removed = db.Property()

    _PROPERTY_EXPORT_BLACKLIST = [second_removed]


class MockStudent(entities.BaseEntity):
    name = db.StringProperty(indexed=False)
    class_rank = db.IntegerProperty(indexed=False)
    additional_fields = db.TextProperty(indexed=False)

    _PROPERTY_EXPORT_BLACKLIST = [
        'name',
        'additional_fields.age',
        'additional_fields.gender',
        'additional_fields.hobby.cost',
    ]


class BaseEntityTestCase(actions.TestBase):

    # Disable complaints about docstrings for self-documenting tests.
    # pylint: disable-msg=g-missing-docstring
    def test_for_export_returns_populated_export_entity_with_key(self):
        first_kept = 'first_kept'
        second_kept = 'second_kept'
        second = SecondChild(first_kept=first_kept, second_kept=second_kept)
        db.put(second)
        second_export = second.for_export(lambda x: x)

        self.assertEqual(first_kept, second_export.first_kept)
        self.assertEqual(second_kept, second_export.second_kept)
        self.assertEqual(second.key(), second_export.safe_key)

    def test_for_export_removes_properties_up_inheritance_chain(self):
        first = FirstChild()
        second = SecondChild()
        db.put([first, second])
        first_export = first.for_export(lambda x: x)
        second_export = second.for_export(lambda x: x)

        self.assertTrue(hasattr(first_export, FirstChild.first_kept.name))
        self.assertFalse(hasattr(first_export, FirstChild.first_removed.name))
        self.assertTrue(hasattr(second_export, SecondChild.first_kept.name))
        self.assertTrue(hasattr(second_export, SecondChild.second_kept.name))
        self.assertFalse(hasattr(second_export, SecondChild.first_removed.name))
        self.assertFalse(
            hasattr(second_export, SecondChild.second_removed.name))

    def test_blacklist_by_name(self):
        additional = transforms.dict_to_nested_lists_as_string({
            'age': 37,
            'class_goal': 'Completion',
            'gender': 'Male',
            'hobby': transforms.dict_to_nested_lists_as_string({
                'name': 'woodworking',
                'level': 'journeyman',
                'cost': 10000,
            })
        })

        blacklisted = transforms.dict_to_nested_lists_as_string({
            'class_goal': 'Completion',
            'hobby': transforms.dict_to_nested_lists_as_string({
                'name': 'woodworking',
                'level': 'journeyman',
            })
        })

        mock_student = MockStudent(name='John Smith', class_rank=23,
                                   additional_fields=additional)
        db.put(mock_student)
        data = mock_student.for_export(lambda x: x)
        self.assertFalse(hasattr(data, 'name'))
        self.assertEquals(23, data.class_rank)
        self.assertEquals(blacklisted, data.additional_fields)


class ExportEntityTestCase(actions.TestBase):

    # Name determined by parent. pylint: disable-msg=g-bad-name
    def setUp(self):
        super(ExportEntityTestCase, self).setUp()
        self.entity = entities.ExportEntity(safe_key='foo')

    def test_constructor_requires_safe_key(self):
        self.assertRaises(AssertionError, entities.ExportEntity)

    def test_put_raises_not_implemented_error(self):
        self.assertRaises(NotImplementedError, self.entity.put)
