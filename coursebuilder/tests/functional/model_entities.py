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

from models import entities
from models import entity_transforms
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

    def setUp(self):
        super(ExportEntityTestCase, self).setUp()
        self.entity = entities.ExportEntity(safe_key='foo')

    def test_constructor_requires_safe_key(self):
        self.assertRaises(AssertionError, entities.ExportEntity)

    def test_put_raises_not_implemented_error(self):
        self.assertRaises(NotImplementedError, self.entity.put)


class TestEntity(entities.BaseEntity):
    prop_int = db.IntegerProperty()
    prop_float = db.FloatProperty(required=True)
    prop_bool = db.BooleanProperty()
    prop_string = db.StringProperty()
    prop_text = db.TextProperty()
    prop_date = db.DateProperty()
    prop_datetime = db.DateTimeProperty()
    prop_intlist = db.ListProperty(int)
    prop_stringlist = db.StringListProperty()
    prop_ref = db.SelfReferenceProperty()


class DefaultConstructableEntity(entities.BaseEntity):
    prop_int = db.IntegerProperty()
    prop_float = db.FloatProperty()
    prop_bool = db.BooleanProperty()
    prop_string = db.StringProperty()
    prop_text = db.TextProperty()
    prop_date = db.DateProperty()
    prop_datetime = db.DateTimeProperty()
    prop_intlist = db.ListProperty(int)
    prop_stringlist = db.StringListProperty()
    prop_ref = db.SelfReferenceProperty()


class EntityTransformsTest(actions.TestBase):

    def test_class_schema(self):
        registry = entity_transforms.get_schema_for_entity(TestEntity)
        schema = registry.get_json_schema_dict()
        self.assertEquals(schema['type'], 'object')
        self.assertEquals(schema['id'], 'TestEntity')
        props = schema['properties']

        self.assertTrue(props['prop_int']['optional'])
        self.assertEquals(props['prop_int']['type'], 'integer')

        self.assertNotIn('optional', props['prop_float'])
        self.assertEquals(props['prop_float']['type'], 'number')

        self.assertTrue(props['prop_bool']['optional'])
        self.assertEquals(props['prop_bool']['type'], 'boolean')

        self.assertTrue(props['prop_string']['optional'])
        self.assertEquals(props['prop_string']['type'], 'string')

        self.assertTrue(props['prop_text']['optional'])
        self.assertEquals(props['prop_text']['type'], 'text')

        self.assertTrue(props['prop_date']['optional'])
        self.assertEquals(props['prop_date']['type'], 'date')

        self.assertTrue(props['prop_datetime']['optional'])
        self.assertEquals(props['prop_datetime']['type'], 'datetime')

        self.assertEquals(props['prop_intlist']['type'], 'array')
        self.assertTrue(props['prop_intlist']['items']['optional'])
        self.assertEquals(props['prop_intlist']['items']['type'], 'integer')

        self.assertEquals(props['prop_stringlist']['type'], 'array')
        self.assertTrue(props['prop_stringlist']['items']['optional'])
        self.assertEquals(props['prop_stringlist']['items']['type'], 'string')

        self.assertTrue(props['prop_ref']['optional'])
        self.assertEquals(props['prop_ref']['type'], 'string')

    def _verify_contents_equal(self, recovered_entity, test_entity):
        self.assertEquals(recovered_entity.prop_int, test_entity.prop_int)
        self.assertEquals(recovered_entity.prop_float, test_entity.prop_float)
        self.assertEquals(recovered_entity.prop_bool, test_entity.prop_bool)
        self.assertEquals(recovered_entity.prop_string, test_entity.prop_string)
        self.assertEquals(recovered_entity.prop_text, test_entity.prop_text)
        self.assertEquals(recovered_entity.prop_date, test_entity.prop_date)
        self.assertEquals(recovered_entity.prop_datetime,
                          test_entity.prop_datetime)
        self.assertEquals(recovered_entity.prop_intlist,
                          test_entity.prop_intlist)
        self.assertEquals(recovered_entity.prop_stringlist,
                          test_entity.prop_stringlist)
        if test_entity.prop_ref is None:
            self.assertIsNone(recovered_entity.prop_ref)
        else:
            self.assertEquals(recovered_entity.prop_ref.key(),
                              test_entity.prop_ref.key())

    def test_roundtrip_conversion_all_members_set(self):
        referent = TestEntity(key_name='that_one_over_there', prop_float=2.71)
        referent.put()
        test_entity = TestEntity(
            prop_int=123,
            prop_float=3.14,
            prop_bool=True,
            prop_string='Mary had a little lamb',
            prop_text='She fed it beans and buns',
            prop_date=datetime.date.today(),
            prop_datetime=datetime.datetime.now(),
            prop_intlist=[4, 3, 2, 1],
            prop_stringlist=['Flopsy', 'Mopsy', 'Cottontail'],
            prop_ref=referent
            )
        test_entity.put()

        converted = entity_transforms.entity_to_dict(test_entity)
        init_dict = entity_transforms.json_dict_to_entity_initialization_dict(
            TestEntity, converted)
        recovered_entity = TestEntity(**init_dict)
        self._verify_contents_equal(recovered_entity, test_entity)

    def test_roundtrip_conversion_optional_members_none(self):
        test_entity = TestEntity(
            prop_int=None,
            prop_float=2.31,
            prop_bool=None,
            prop_string=None,
            prop_text=None,
            prop_date=None,
            prop_datetime=None,
            prop_intlist=[],
            prop_stringlist=[],
            prop_ref=None
            )
        test_entity.put()

        converted = entity_transforms.entity_to_dict(test_entity)
        init_dict = entity_transforms.json_dict_to_entity_initialization_dict(
            TestEntity, converted)
        recovered_entity = TestEntity(**init_dict)
        self._verify_contents_equal(recovered_entity, test_entity)

    def test_roundtrip_conversion_default_constructable(self):
        referent = DefaultConstructableEntity(key_name='that_one_over_there')
        referent.put()
        test_entity = DefaultConstructableEntity(
            prop_int=123,
            prop_float=3.14,
            prop_bool=True,
            prop_string='Mary had a little lamb',
            prop_text='She fed it beans and buns',
            prop_date=datetime.date.today(),
            prop_datetime=datetime.datetime.now(),
            prop_intlist=[4, 3, 2, 1],
            prop_stringlist=['Flopsy', 'Mopsy', 'Cottontail'],
            prop_ref=referent
            )
        test_entity.put()

        converted = entity_transforms.entity_to_dict(test_entity)
        recovered_entity = DefaultConstructableEntity()
        entity_transforms.dict_to_entity(recovered_entity, converted)
        self._verify_contents_equal(recovered_entity, test_entity)
