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
import logging

from common import users
from common import utils as common_utils
from models import config
from models import entities
from models import models
from models import services
from models import transforms
from modules.notifications import notifications
from tests.functional import actions

from google.appengine.ext import db


class EventEntityTestCase(actions.ExportTestBase):

    def test_for_export_transforms_correctly(self):
        event = models.EventEntity(source='source', user_id='1')
        key = event.put()
        exported = event.for_export(self.transform)

        self.assert_blacklisted_properties_removed(event, exported)
        self.assertEqual('source', event.source)
        self.assertEqual('transformed_1', exported.user_id)
        self.assertEqual(key, models.EventEntity.safe_key(key, self.transform))


class ContentChunkTestCase(actions.ExportTestBase):
    """Tests ContentChunkEntity|DAO|DTO."""

    def setUp(self):
        super(ContentChunkTestCase, self).setUp()
        config.Registry.test_overrides[models.CAN_USE_MEMCACHE.name] = True
        self.content_type = 'content_type'
        self.contents = 'contents'
        self.id = 1
        self.memcache_key = models.ContentChunkDAO._get_memcache_key(self.id)
        self.resource_id = 'resource:id'  # To check colons are preserved.
        self.supports_custom_tags = True
        self.type_id = 'type_id'
        self.uid = models.ContentChunkDAO.make_uid(
            self.type_id, self.resource_id)

    def tearDown(self):
        config.Registry.test_overrides = {}
        super(ContentChunkTestCase, self).tearDown()

    def assert_fuzzy_equal(self, first, second):
        """Assert doesn't check last_modified, allowing clock skew."""
        self.assertTrue(isinstance(first, models.ContentChunkDTO))
        self.assertTrue(isinstance(second, models.ContentChunkDTO))
        self.assertEqual(first.content_type, second.content_type)
        self.assertEqual(first.contents, second.contents)
        self.assertEqual(first.id, second.id)
        self.assertEqual(first.resource_id, second.resource_id)
        self.assertEqual(
            first.supports_custom_tags, second.supports_custom_tags)
        self.assertEqual(first.type_id, second.type_id)

    def assert_list_fuzzy_equal(self, first, second):
        self.assertEqual(len(first), len(second))

        for f, s in zip(first, second):
            self.assert_fuzzy_equal(f, s)

    def test_dao_delete_deletes_entity_and_cached_dto(self):
        key = models.ContentChunkDAO.save(models.ContentChunkDTO({
            'content_type': self.content_type,
            'contents': self.contents,
            'id': self.id,
            'resource_id': self.resource_id,
            'supports_custom_tags': self.supports_custom_tags,
            'type_id': self.type_id,
        }))
        entity = db.get(key)
        dto = models.ContentChunkDAO.get(key.id())

        self.assertIsNotNone(entity)
        self.assertIsNotNone(dto)

        models.ContentChunkDAO.delete(key.id())
        entity = db.get(key)
        dto = models.ContentChunkDAO.get(key.id())

        self.assertIsNone(entity)
        self.assertIsNone(dto)

    def test_dao_delete_runs_successfully_when_no_entity_present(self):
        self.assertIsNone(models.ContentChunkDAO.delete(self.id))

    def test_dao_get_returns_cached_entity(self):
        key = models.ContentChunkDAO.save(models.ContentChunkDTO({
            'content_type': self.content_type,
            'contents': self.contents,
            'resource_id': self.resource_id,
            'supports_custom_tags': self.supports_custom_tags,
            'type_id': self.type_id,
        }))
        entity = db.get(key)
        entity.contents = 'patched'
        patched_dto = models.ContentChunkDAO._make_dto(entity)
        models.MemcacheManager.set(self.memcache_key, patched_dto)
        from_datastore = models.ContentChunkEntity.get_by_id(self.id)
        from_cache = models.MemcacheManager.get(self.memcache_key)

        self.assert_fuzzy_equal(patched_dto, from_cache)
        self.assertNotEqual(patched_dto.contents, from_datastore.contents)

    def test_dao_get_returns_dto_and_populates_cache(self):
        self.assertIsNone(models.MemcacheManager.get(self.memcache_key))

        key = models.ContentChunkDAO.save(models.ContentChunkDTO({
            'content_type': self.content_type,
            'contents': self.contents,
            'resource_id': self.resource_id,
            'supports_custom_tags': self.supports_custom_tags,
            'type_id': self.type_id,
        }))
        from_datastore = models.ContentChunkDAO._make_dto(db.get(key))

        self.assertIsNone(models.MemcacheManager.get(self.memcache_key))

        first_get_result = models.ContentChunkDAO.get(self.id)
        from_cache = models.MemcacheManager.get(self.memcache_key)

        self.assert_fuzzy_equal(first_get_result, from_datastore)
        self.assert_fuzzy_equal(from_cache, from_datastore)

    def test_dao_get_returns_none_when_entity_id_none(self):
        self.assertIsNone(models.ContentChunkDAO.get(None))

    def test_dao_get_returns_none_when_no_entity_in_datastore(self):
        self.assertIsNone(models.MemcacheManager.get(self.memcache_key))
        self.assertIsNone(models.ContentChunkDAO.get(self.id))
        self.assertEqual(
            models.NO_OBJECT, models.MemcacheManager.get(self.memcache_key))

    def test_dao_get_by_uid_returns_empty_list_if_no_matches(self):
        self.assertEqual([], models.ContentChunkDAO.get_by_uid(self.uid))

    def test_dao_get_by_uid_returns_matching_dtos_sorted_by_id(self):
        different_uid = models.ContentChunkDAO.make_uid(
            'other', self.resource_id)
        first_key = models.ContentChunkEntity(
            content_type=self.content_type, contents=self.contents,
            supports_custom_tags=self.supports_custom_tags, uid=self.uid).put()
        second_key = models.ContentChunkEntity(
            content_type=self.content_type, contents=self.contents + '2',
            supports_custom_tags=self.supports_custom_tags, uid=self.uid).put()
        unused_different_uid_key = models.ContentChunkEntity(
            content_type=self.content_type, contents=self.contents,
            supports_custom_tags=self.supports_custom_tags,
            uid=different_uid).put()
        expected_dtos = [
            models.ContentChunkDAO.get(first_key.id()),
            models.ContentChunkDAO.get(second_key.id())]
        actual_dtos = models.ContentChunkDAO.get_by_uid(self.uid)

        self.assert_list_fuzzy_equal(expected_dtos, actual_dtos)

    def test_dao_make_dto(self):
        key = models.ContentChunkEntity(
            content_type=self.content_type, contents=self.contents,
            supports_custom_tags=self.supports_custom_tags, uid=self.uid).put()
        entity = db.get(key)  # Refetch to avoid timestamp skew.
        dto = models.ContentChunkDAO._make_dto(entity)

        self.assertEqual(entity.content_type, dto.content_type)
        self.assertEqual(entity.contents, dto.contents)
        self.assertEqual(entity.key().id(), dto.id)
        self.assertEqual(entity.last_modified, dto.last_modified)
        self.assertEqual(entity.supports_custom_tags, dto.supports_custom_tags)

        entity_type_id, entity_resource_id = models.ContentChunkDAO._split_uid(
            entity.uid)
        self.assertEqual(entity_resource_id, dto.resource_id)
        self.assertEqual(entity_type_id, dto.type_id)

    def test_dao_make_uid(self):
        self.assertEqual(None, models.ContentChunkDAO.make_uid(None, None))
        self.assertEqual(
            'foo:bar', models.ContentChunkDAO.make_uid('foo', 'bar'))

    def test_dao_make_uid_requires_both_args_disallows_colons_in_type_id(self):
        bad_pairs = [
            (None, 'foo'),
            ('foo', None),
            (':', None),
            (':', 'foo'),
            ('', ''),
            ('', 'foo'),
            ('foo', ''),
            (':', ''),
            (':', 'foo'),
        ]

        for bad_pair in bad_pairs:
            with self.assertRaises(AssertionError):
                models.ContentChunkDAO.make_uid(*bad_pair)

    def test_dao_split_uid(self):
        self.assertEqual(
            (None, None), models.ContentChunkDAO._split_uid(None))
        self.assertEqual(
            ('foo', 'bar'), models.ContentChunkDAO._split_uid('foo:bar'))
        self.assertEqual(
            ('foo', 'http://bar'),
            models.ContentChunkDAO._split_uid('foo:http://bar'))

    def test_dao_split_uid_requires_colon_and_both_values_are_truthy(self):
        with self.assertRaises(AssertionError):
            models.ContentChunkDAO._split_uid('foo')

        with self.assertRaises(AssertionError):
            models.ContentChunkDAO._split_uid(':')

        with self.assertRaises(AssertionError):
            models.ContentChunkDAO._split_uid('foo:')

        with self.assertRaises(AssertionError):
            models.ContentChunkDAO._split_uid(':foo')

    def test_dao_save_creates_new_object_and_does_not_populate_cache(self):
        self.assertIsNone(models.MemcacheManager.get(self.memcache_key))

        dto = models.ContentChunkDTO({
            'content_type': self.content_type,
            'contents': self.contents,
            'id': self.id,
            'resource_id': self.resource_id,
            'supports_custom_tags': self.supports_custom_tags,
            'type_id': self.type_id,
        })
        key = models.ContentChunkDAO.save(dto)
        saved_dto = models.ContentChunkDAO._make_dto(db.get(key))

        self.assert_fuzzy_equal(dto, saved_dto)
        self.assertIsNone(models.MemcacheManager.get(self.memcache_key))

    def test_dao_save_updates_existing_object_and_does_not_populate_cache(self):
        self.assertIsNone(models.MemcacheManager.get(self.memcache_key))

        dto = models.ContentChunkDTO({
            'content_type': self.content_type,
            'contents': self.contents,
            'id': self.id,
            'resource_id': self.resource_id,
            'supports_custom_tags': self.supports_custom_tags,
            'type_id': self.type_id,
        })
        key = models.ContentChunkDAO.save(dto)
        saved_dto = models.ContentChunkDAO._make_dto(db.get(key))

        self.assert_fuzzy_equal(dto, saved_dto)
        self.assertIsNone(models.MemcacheManager.get(self.memcache_key))

        dto.content_type = 'new_content_type'
        dto.contents = 'new_contents'
        dto.supports_custom_tags = True
        dto.uid = 'new_system_id:new_resource:id'
        models.ContentChunkDAO.save(dto)
        saved_dto = models.ContentChunkDAO._make_dto(db.get(key))

        self.assert_fuzzy_equal(dto, saved_dto)
        self.assertIsNone(models.MemcacheManager.get(self.memcache_key))

    def test_dao_save_all_saves_multiple_dtos(self):
        # All other behavior of save_all() tested via save() since they share
        # implementation and save() provides a simpler interface.
        first_dto = models.ContentChunkDTO({
            'content_type': self.content_type,
            'contents': self.contents,
            'id': self.id,
            'resource_id': self.resource_id,
            'supports_custom_tags': self.supports_custom_tags,
            'type_id': self.type_id,
        })
        second_dto = models.ContentChunkDTO({
            'content_type': 'second_' + self.content_type,
            'contents': 'second_' + self.contents,
            'id': self.id + 1,
            'resource_id': 'resource:second_id',
            'supports_custom_tags': self.supports_custom_tags,
            'type_id': 'second_' + self.type_id,
        })
        keys = models.ContentChunkDAO.save_all([first_dto, second_dto])
        saved_dtos = [
            models.ContentChunkDAO._make_dto(entity) for entity in db.get(keys)]

        self.assertEqual(2, len(keys))
        self.assertEqual(2, len(saved_dtos))
        self.assert_fuzzy_equal(first_dto, saved_dtos[0])
        self.assert_fuzzy_equal(second_dto, saved_dtos[1])


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


class MemcacheManagerTestCase(actions.TestBase):

    def setUp(self):
        super(MemcacheManagerTestCase, self).setUp()
        config.Registry.test_overrides = {models.CAN_USE_MEMCACHE.name: True}

    def tearDown(self):
        config.Registry.test_overrides = {}
        super(MemcacheManagerTestCase, self).tearDown()

    def test_set_multi(self):
        data = {'a': 'A', 'b': 'B'}
        models.MemcacheManager.set_multi(data)

        self.assertEquals('A', models.MemcacheManager.get('a'))
        self.assertEquals('B', models.MemcacheManager.get('b'))

    def test_get_multi(self):
        models.MemcacheManager.set('a', 'A')
        models.MemcacheManager.set('b', 'B')

        data = models.MemcacheManager.get_multi(['a', 'b', 'c'])
        self.assertEquals(2, len(data.keys()))
        self.assertEquals('A', data['a'])
        self.assertEquals('B', data['b'])

    def test_set_multi_no_memcache(self):
        config.Registry.test_overrides = {}
        data = {'a': 'A', 'b': 'B'}
        models.MemcacheManager.set_multi(data)

        self.assertEquals(None, models.MemcacheManager.get('a'))
        self.assertEquals(None, models.MemcacheManager.get('b'))

    def test_get_multi_no_memcache(self):
        config.Registry.test_overrides = {}
        models.MemcacheManager.set('a', 'A')
        models.MemcacheManager.set('b', 'B')

        data = models.MemcacheManager.get_multi(['a', 'b', 'c'])
        self.assertEquals(0, len(data.keys()))


class TestEntity(entities.BaseEntity):
    data = db.TextProperty(indexed=False)


class TestDto(object):

    def __init__(self, the_id, the_dict):
        self.id = the_id
        self.dict = the_dict


class TestDao(models.BaseJsonDao):
    DTO = TestDto
    ENTITY = TestEntity
    ENTITY_KEY_TYPE = models.BaseJsonDao.EntityKeyTypeName


class BaseJsonDaoTestCase(actions.TestBase):

    def setUp(self):
        super(BaseJsonDaoTestCase, self).setUp()
        config.Registry.test_overrides = {models.CAN_USE_MEMCACHE.name: True}

    def tearDown(self):
        config.Registry.test_overrides = {}
        super(BaseJsonDaoTestCase, self).tearDown()

    def test_bulk_load(self):
        key_0 = 'dto_0'
        key_1 = 'dto_1'
        mc_key_0 = '(entity:TestEntity:dto_0)'
        mc_key_1 = '(entity:TestEntity:dto_1)'

        dto = TestDto(key_0, {'a': 0})
        TestDao.save(dto)
        dto = TestDto(key_1, {'a': 1})
        TestDao.save(dto)

        def assert_bulk_load_succeeds():
            dtos = TestDao.bulk_load([key_0, key_1, 'dto_2'])
            self.assertEquals(3, len(dtos))
            self.assertEquals(key_0, dtos[0].id)
            self.assertEquals({'a': 0}, dtos[0].dict)
            self.assertEquals(key_1, dtos[1].id)
            self.assertEquals({'a': 1}, dtos[1].dict)
            self.assertIsNone(dtos[2])

        # Confirm entities in memcache
        memcache_entities = models.MemcacheManager.get_multi(
            [mc_key_0, mc_key_1])
        self.assertEquals(2, len(memcache_entities))
        self.assertIn(mc_key_0, memcache_entities)
        self.assertIn(mc_key_1, memcache_entities)

        assert_bulk_load_succeeds()

        # Evict one from memcache
        models.MemcacheManager.delete(mc_key_0)
        memcache_entities = models.MemcacheManager.get_multi(
            [mc_key_0, mc_key_1])
        self.assertEquals(1, len(memcache_entities))
        self.assertIn(mc_key_1, memcache_entities)

        assert_bulk_load_succeeds()

        # Evict both from memcache
        models.MemcacheManager.delete(mc_key_0)
        models.MemcacheManager.delete(mc_key_1)
        memcache_entities = models.MemcacheManager.get_multi(
            [mc_key_0, mc_key_1])
        self.assertEquals(0, len(memcache_entities))

        assert_bulk_load_succeeds()


class QuestionDAOTestCase(actions.TestBase):
    """Functional tests for QuestionDAO."""

    def setUp(self):
        """Sets up datastore contents."""
        super(QuestionDAOTestCase, self).setUp()

        self.used_twice_question_dto = models.QuestionDTO(None, {})
        self.used_twice_question_id = models.QuestionDAO.save(
            self.used_twice_question_dto)

        self.used_once_question_dto = models.QuestionDTO(None, {})
        self.used_once_question_id = models.QuestionDAO.save(
            self.used_once_question_dto)

        self.unused_question_dto = models.QuestionDTO(None, {})
        self.unused_question_id = models.QuestionDAO.save(
            self.unused_question_dto)

        # Handcoding the dicts. This is dangerous because they're handcoded
        # elsewhere, the implementations could fall out of sync, and these tests
        # may then pass erroneously.
        self.first_question_group_description = 'first_question_group'
        self.first_question_group_dto = models.QuestionGroupDTO(
            None,
            {'description': self.first_question_group_description,
             'items': [{'question': str(self.used_once_question_id)}]})
        self.first_question_group_id = models.QuestionGroupDAO.save(
            self.first_question_group_dto)

        self.second_question_group_description = 'second_question_group'
        self.second_question_group_dto = models.QuestionGroupDTO(
            None,
            {'description': self.second_question_group_description,
             'items': [{'question': str(self.used_twice_question_id)}]})
        self.second_question_group_id = models.QuestionGroupDAO.save(
            self.second_question_group_dto)

        self.third_question_group_description = 'third_question_group'
        self.third_question_group_dto = models.QuestionGroupDTO(
            None,
            {'description': self.third_question_group_description,
             'items': [{'question': str(self.used_twice_question_id)}]})
        self.third_question_group_id = models.QuestionGroupDAO.save(
            self.third_question_group_dto)

    def test_used_by_returns_single_question_group(self):
        self.assertEqual(
            long(self.first_question_group_id),
            models.QuestionDAO.used_by(self.used_once_question_id)[0].id)

    def test_used_by_returns_multiple_question_groups(self):
        used_by = models.QuestionDAO.used_by(self.used_twice_question_id)
        self.assertEqual(long(self.second_question_group_id), used_by[0].id)
        self.assertEqual(long(self.third_question_group_id), used_by[1].id)

    def test_used_by_returns_empty_list_for_unused_question(self):
        not_found_id = 7
        self.assertFalse(models.QuestionDAO.load(not_found_id))
        self.assertEqual([], models.QuestionDAO.used_by(not_found_id))


class StudentTestCase(actions.ExportTestBase):

    def setUp(self):
        super(StudentTestCase, self).setUp()
        self.old_users_service = users.UsersServiceManager.get()

    def tearDown(self):
        users.UsersServiceManager.set(self.old_users_service)
        super(StudentTestCase, self).tearDown()

    def test_federated_email_returns_and_caches_none_by_default(self):
        student = models.Student(user_id='1')

        # Check backing value starts at None, uncached. On access of the public
        # computed property, check the backing value is still None (since the
        # expected value is None in this case), but that the None value is now
        # cached.
        self.assertIsNone(student._federated_email_value)
        self.assertFalse(student._federated_email_cached)

        self.assertIsNone(student.federated_email)

        self.assertIsNone(student._federated_email_value)
        self.assertTrue(student._federated_email_cached)

    def test_federated_email_returns_and_caches_data_from_custom_resolver(self):

        class Resolver(users.FederatedEmailResolver):

            @classmethod
            def get(cls, unused_user_id):
                return 'resolved@example.com'

        class UsersService(users.AbstractUsersService):

            @classmethod
            def get_federated_email_resolver_class(cls):
                return Resolver

        users.UsersServiceManager.set(UsersService)

        student = models.Student(user_id='1')

        # Check backing value starts at None, uncached. On access of the public
        # computed property, check the backing value is now set and cached.
        self.assertIsNone(student._federated_email_value)
        self.assertFalse(student._federated_email_cached)

        self.assertEquals('resolved@example.com', student.federated_email)

        self.assertEquals(
            'resolved@example.com', student._federated_email_value)
        self.assertTrue(student._federated_email_cached)

    def test_federated_email_returns_none_for_legacy_users_sans_user_id(self):
        student = models.Student()

        # Check backing value starts at None, uncached. On access of the public
        # computed property, check the backing value is still None (since the
        # expected value is None in this case), but that the None value is now
        # cached.
        self.assertIsNone(student._federated_email_value)
        self.assertFalse(student._federated_email_cached)

        self.assertIsNone(student.federated_email)

        self.assertIsNone(student._federated_email_value)
        self.assertTrue(student._federated_email_cached)

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

    def test_registration_sets_last_seen_on(self):
        actions.login('test@example.com')
        actions.register(self, 'User 1')
        student = models.Student.all().get()

        self.assertTrue(isinstance(student.last_seen_on, datetime.datetime))

    def test_update_last_seen_on_does_not_update_when_last_seen_too_new(self):
        now = datetime.datetime.utcnow()
        student = models.Student(last_seen_on=now, user_id='1')
        key = student.put()
        too_new = now + datetime.timedelta(
            seconds=models.STUDENT_LAST_SEEN_ON_UPDATE_SEC)

        self.assertEquals(now, student.last_seen_on)

        student.update_last_seen_on(now=now, value=too_new)
        student = db.get(key)

        self.assertEquals(now, student.last_seen_on)

    def test_update_last_seen_on_updates_when_last_seen_on_is_none(self):
        now = datetime.datetime.utcnow()
        student = models.Student(last_seen_on=None, user_id='1')
        key = student.put()
        # Must be too new to otherwise update.
        too_new = now + datetime.timedelta(
            seconds=models.STUDENT_LAST_SEEN_ON_UPDATE_SEC)

        self.assertIsNone(student.last_seen_on)

        student.update_last_seen_on(now=now, value=too_new)
        student = db.get(key)

        self.assertEquals(too_new, student.last_seen_on)

    def test_update_last_seen_on_updates_when_last_seen_on_is_none_noarg(self):
        now = datetime.datetime.utcnow()
        student = models.Student(last_seen_on=None, user_id='1')
        key = student.put()
        # Must be too new to otherwise update.
        too_new = now + datetime.timedelta(
            seconds=models.STUDENT_LAST_SEEN_ON_UPDATE_SEC)

        self.assertIsNone(student.last_seen_on)

        student.update_last_seen_on()
        student = db.get(key)

        self.assertTrue(isinstance(student.last_seen_on, datetime.datetime))

    def test_update_last_seen_on_updates_when_last_seen_on_is_old_enough(self):
        now = datetime.datetime.utcnow()
        student = models.Student(last_seen_on=now, user_id='1')
        key = student.put()
        old_enough = now + datetime.timedelta(
            seconds=models.STUDENT_LAST_SEEN_ON_UPDATE_SEC + 1)

        self.assertEquals(now, student.last_seen_on)

        student.update_last_seen_on(now=now, value=old_enough)
        student = db.get(key)

        self.assertEquals(old_enough, student.last_seen_on)


class StudentProfileDAOTestCase(actions.ExportTestBase):

    def test_can_send_welcome_notifications_false_if_config_value_false(self):
        self.swap(services.notifications, 'enabled', lambda: True)
        self.swap(services.unsubscribe, 'enabled', lambda: True)
        handler = actions.MockHandler(
            app_context=actions.MockAppContext(environ={
                'course': {'send_welcome_notifications': False}
            }))

        self.assertFalse(
            models.StudentProfileDAO._can_send_welcome_notifications(handler))

    def test_can_send_welcome_notifications_false_notifications_disabled(self):
        self.swap(services.notifications, 'enabled', lambda: False)
        self.swap(services.unsubscribe, 'enabled', lambda: True)
        handler = actions.MockHandler(
            app_context=actions.MockAppContext(environ={
                'course': {'send_welcome_notifications': True}
            }))

        self.assertFalse(
            models.StudentProfileDAO._can_send_welcome_notifications(handler))

    def test_can_send_welcome_notifications_false_unsubscribe_disabled(self):
        self.swap(services.notifications, 'enabled', lambda: True)
        self.swap(services.unsubscribe, 'enabled', lambda: False)
        handler = actions.MockHandler(
            app_context=actions.MockAppContext(environ={
                'course': {'send_welcome_notifications': True}
            }))

        self.assertFalse(
            models.StudentProfileDAO._can_send_welcome_notifications(handler))

    def test_can_send_welcome_notifications_true_if_all_true(self):
        self.swap(services.notifications, 'enabled', lambda: True)
        self.swap(services.unsubscribe, 'enabled', lambda: True)
        handler = actions.MockHandler(
            app_context=actions.MockAppContext(environ={
                'course': {'send_welcome_notifications': True}
            }))

        self.assertTrue(
            models.StudentProfileDAO._can_send_welcome_notifications(handler))

    def test_get_send_welcome_notifications(self):
        handler = actions.MockHandler(app_context=actions.MockAppContext())
        self.assertFalse(
            models.StudentProfileDAO._get_send_welcome_notifications(handler))

        handler = actions.MockHandler(
            app_context=actions.MockAppContext(environ={
                'course': {}
            }))
        self.assertFalse(
            models.StudentProfileDAO._get_send_welcome_notifications(handler))

        handler = actions.MockHandler(
            app_context=actions.MockAppContext(environ={
                'course': {'send_welcome_notifications': False}
            }))
        self.assertFalse(
            models.StudentProfileDAO._get_send_welcome_notifications(handler))

        handler = actions.MockHandler(
            app_context=actions.MockAppContext(environ={
                'course': {'send_welcome_notifications': True}
            }))
        self.assertTrue(
            models.StudentProfileDAO._get_send_welcome_notifications(handler))

    def test_send_welcome_notification_enqueues_and_sends(self):
        nick_name = 'No Body'
        email = 'user@example.com'
        sender = 'sender@example.com'
        title = 'title'
        student = models.Student(key_name=email, name=nick_name)
        student.put()
        self.swap(services.notifications, 'enabled', lambda: True)
        self.swap(services.unsubscribe, 'enabled', lambda: True)
        handler = actions.MockHandler(
            app_context=actions.MockAppContext(environ={
                'course': {
                    'send_welcome_notifications': True,
                    'title': title,
                    'welcome_notifications_sender': sender,
                },
            }))
        models.StudentProfileDAO._send_welcome_notification(handler, student)
        self.execute_all_deferred_tasks()
        notification = notifications.Notification.all().get()
        payload = notifications.Payload.all().get()
        audit_trail = notification.audit_trail

        self.assertEqual(title, audit_trail['course_title'])
        self.assertEqual(
            'http://mycourse.appspot.com/slug/',
            audit_trail['course_url'])
        self.assertTrue(audit_trail['unsubscribe_url'].startswith(
            'http://mycourse.appspot.com/slug/modules/unsubscribe'))
        self.assertTrue(notification._done_date)
        self.assertEqual(email, notification.to)
        self.assertEqual(sender, notification.sender)
        self.assertEqual('Welcome to ' + title, notification.subject)
        self.assertTrue(payload)


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

class StudentLifecycleObserverTestCase(actions.TestBase):

    COURSE = 'lifecycle_test'
    NAMESPACE = 'ns_' + COURSE
    ADMIN_EMAIL = 'admin@foo.com'
    STUDENT_EMAIL = 'student@foo.com'
    LOG_LEVEL = logging.WARNING

    def setUp(self):
        super(StudentLifecycleObserverTestCase, self).setUp()
        app_context = actions.simple_add_course(
            self.COURSE, self.ADMIN_EMAIL, 'Lifecycle Test')
        self.base = '/' + self.COURSE
        self._user_id = None
        self._num_add_calls = 0
        models.StudentLifecycleObserver.EVENT_CALLBACKS[
            models.StudentLifecycleObserver.EVENT_ADD][self.COURSE] = (
                self._add_callback)
        self._num_unenroll_calls = 0
        models.StudentLifecycleObserver.EVENT_CALLBACKS[
            models.StudentLifecycleObserver.EVENT_UNENROLL][self.COURSE] = (
                self._unenroll_callback)
        self._num_reenroll_calls = 0
        models.StudentLifecycleObserver.EVENT_CALLBACKS[
            models.StudentLifecycleObserver.EVENT_REENROLL][self.COURSE] = (
                self._reenroll_callback)

        self._num_exception_calls = 0
        self._num_exceptions_to_raise = 0
        models.StudentLifecycleObserver.EVENT_CALLBACKS[
            models.StudentLifecycleObserver.EVENT_ADD]['raises'] = (
                self._raise_exceptions)
        models.StudentLifecycleObserver.EVENT_CALLBACKS[
            models.StudentLifecycleObserver.EVENT_UNENROLL]['raises'] = (
                self._raise_exceptions)
        models.StudentLifecycleObserver.EVENT_CALLBACKS[
            models.StudentLifecycleObserver.EVENT_REENROLL]['raises'] = (
                self._raise_exceptions)

        event_callbacks = models.StudentLifecycleObserver.EVENT_CALLBACKS
        for event_type in event_callbacks:
            if 'wipeout' in event_callbacks[event_type]:
                del event_callbacks[event_type]['wipeout']
        enqueue_callbacks = models.StudentLifecycleObserver.EVENT_CALLBACKS
        for event_type in enqueue_callbacks:
            if 'wipeout' in enqueue_callbacks[event_type]:
                del enqueue_callbacks[event_type]['wipeout']

    def _add_callback(self, user_id, timestamp):
        self._user_id = user_id
        self._timestamp = timestamp
        self._num_add_calls += 1

    def _unenroll_callback(self, user_id, timestamp):
        self._num_unenroll_calls += 1

    def _reenroll_callback(self, user_id, timestamp):
        self._num_reenroll_calls += 1

    def _raise_exceptions(self, user_id, timestamp):
        self._num_exception_calls += 1
        if self._num_exceptions_to_raise:
            self._num_exceptions_to_raise -= 1
            raise ValueError('bogus error')

    def test_notifications_succeed(self):
        actions.login(self.STUDENT_EMAIL)
        user_id = None

        actions.register(self, self.STUDENT_EMAIL)
        self.assertIsNone(self._user_id)
        self.execute_all_deferred_tasks(
            models.StudentLifecycleObserver.QUEUE_NAME)
        self.assertIsNotNone(self._user_id)
        user_id = self._user_id
        self.assertEquals(1, self._num_add_calls)
        self.assertEquals(0, self._num_unenroll_calls)
        self.assertEquals(0, self._num_reenroll_calls)

        actions.unregister(self)
        self.execute_all_deferred_tasks(
            models.StudentLifecycleObserver.QUEUE_NAME)
        self.assertEquals(1, self._num_add_calls)
        self.assertEquals(1, self._num_unenroll_calls)
        self.assertEquals(0, self._num_reenroll_calls)


        with common_utils.Namespace(self.NAMESPACE):
            models.StudentProfileDAO.update(
                user_id, self.STUDENT_EMAIL, is_enrolled=True)
        self.execute_all_deferred_tasks(
            models.StudentLifecycleObserver.QUEUE_NAME)
        self.assertEquals(1, self._num_add_calls)
        self.assertEquals(1, self._num_unenroll_calls)
        self.assertEquals(1, self._num_reenroll_calls)

    def test_bad_event_name(self):
        with self.assertRaises(ValueError):
            models.StudentLifecycleObserver.enqueue(
                'not_a_real_event_name', 123)

    def test_bad_user_id(self):
        with self.assertRaises(ValueError):
            models.StudentLifecycleObserver.enqueue(
                models.StudentLifecycleObserver.EVENT_ADD, None)

    def test_bad_post_not_from_appengine_queue_internals(self):
        response = self.post(models.StudentLifecycleObserver.URL, {},
                             expect_errors=True)
        self.assertEquals(response.status_int, 500)

    def test_bad_post_no_user_id(self):
        response = self.post(
            models.StudentLifecycleObserver.URL, {},
            headers={'X-AppEngine-QueueName':
                     models.StudentLifecycleObserver.QUEUE_NAME})
        self.assertEquals(response.status_int, 200)
        self.assertLogContains('Student lifecycle queue had item with no user')

    def test_bad_post_no_event(self):
        response = self.post(
            models.StudentLifecycleObserver.URL, {'user_id': '123'},
            headers={'X-AppEngine-QueueName':
                     models.StudentLifecycleObserver.QUEUE_NAME})
        self.assertEquals(response.status_int, 200)
        self.assertLogContains('Student lifecycle queue had item with no event')

    def test_bad_post_no_timestamp(self):
        response = self.post(
            models.StudentLifecycleObserver.URL,
            {'user_id': '123', 'event': 'add'},
            headers={'X-AppEngine-QueueName':
                     models.StudentLifecycleObserver.QUEUE_NAME})
        self.assertEquals(response.status_int, 200)
        self.assertLogContains('Student lifecycle queue: malformed timestamp')

    def test_bad_post_bad_timestamp(self):
        response = self.post(
            models.StudentLifecycleObserver.URL,
            {'user_id': '123', 'event': 'add', 'timestamp': '12333'},
            headers={'X-AppEngine-QueueName':
                     models.StudentLifecycleObserver.QUEUE_NAME})
        self.assertEquals(response.status_int, 200)
        self.assertLogContains(
            'Student lifecycle queue: malformed timestamp 12333')

    def test_post_user_id_and_timestamp_pass_through_without_change(self):
        user_id = '123'
        timestamp = '2015-05-14T10:02:09.758704Z'

        response = self.post(
            models.StudentLifecycleObserver.URL,
            {'user_id': user_id,
             'event': 'add',
             'extra_data': '{}',
             'timestamp': timestamp,
             'callbacks': self.COURSE},
            headers={'X-AppEngine-QueueName':
                     models.StudentLifecycleObserver.QUEUE_NAME})
        self.assertEquals(response.status_int, 200)
        self.assertEquals(user_id, self._user_id)
        self.assertEquals(timestamp, self._timestamp.strftime(
            transforms.ISO_8601_DATETIME_FORMAT))

    def test_bad_post_no_callbacks(self):
        response = self.post(
            models.StudentLifecycleObserver.URL,
            {'user_id': '123',
             'event': 'add',
             'extra_data': '{}',
             'timestamp': '2015-05-14T10:02:09.758704Z'},
            headers={'X-AppEngine-QueueName':
                     models.StudentLifecycleObserver.QUEUE_NAME})
        self.assertEquals(response.status_int, 200)
        self.assertLogContains('Odd: Student lifecycle with no callback items')

    def test_bad_post_bad_callback(self):
        response = self.post(
            models.StudentLifecycleObserver.URL,
            {'user_id': '123',
             'event': 'add',
             'extra_data': '{}',
             'timestamp': '2015-05-14T10:02:09.758704Z',
             'callbacks': 'fred'},
            headers={'X-AppEngine-QueueName':
                     models.StudentLifecycleObserver.QUEUE_NAME})
        self.assertEquals(response.status_int, 200)
        self.assertLogContains(
            'Student lifecycle event enqueued with callback named '
            '"fred", but no such callback is currently registered.')

    def test_retry_on_exception(self):
        num_exceptions = 1  # testing queue does not permit errors.  :-{
        self._num_exceptions_to_raise = num_exceptions
        actions.login(self.STUDENT_EMAIL)
        actions.register(self, self.STUDENT_EMAIL)
        self.execute_all_deferred_tasks(
            models.StudentLifecycleObserver.QUEUE_NAME)
        self.assertEquals(1, self._num_add_calls)
        self.assertEquals(0, self._num_unenroll_calls)
        self.assertEquals(0, self._num_reenroll_calls)
        self.assertEquals(num_exceptions + 1, self._num_exception_calls)

    def test_extra_data_callback(self):
        user = actions.login(self.STUDENT_EMAIL)
        extra_data = {
            'this': 'that',
            'these': ['those']
            }

        def _no_extra_callback(user_id, timestamp):
            self.assertEquals(user_id, user.user_id())

        def _generate_extra_data_callback(user_id):
            self._generate_extra_data_callback_called = True
            self.assertEqual(user_id, user.user_id())
            return extra_data

        def _with_extra_data_callback(user_id, timestamp, actual_extra_data):
            self._with_extra_data_callback_called = True
            self.assertEquals(actual_extra_data, extra_data)

        models.StudentLifecycleObserver.EVENT_CALLBACKS[
            models.StudentLifecycleObserver.EVENT_ADD]['no_extra'] = (
                _no_extra_callback)
        models.StudentLifecycleObserver.EVENT_CALLBACKS[
            models.StudentLifecycleObserver.EVENT_ADD]['with_extra'] = (
                _with_extra_data_callback)
        models.StudentLifecycleObserver.ENQUEUE_CALLBACKS[
            models.StudentLifecycleObserver.EVENT_ADD]['with_extra'] = (
                _generate_extra_data_callback)

        actions.register(self, self.STUDENT_EMAIL)
        self.execute_all_deferred_tasks(
            models.StudentLifecycleObserver.QUEUE_NAME)
        self.assertTrue(self._generate_extra_data_callback_called)
        self.assertTrue(self._with_extra_data_callback_called)

        del (models.StudentLifecycleObserver.EVENT_CALLBACKS[
            models.StudentLifecycleObserver.EVENT_ADD]['no_extra'])
        del (models.StudentLifecycleObserver.EVENT_CALLBACKS[
            models.StudentLifecycleObserver.EVENT_ADD]['with_extra'])
        del (models.StudentLifecycleObserver.ENQUEUE_CALLBACKS[
            models.StudentLifecycleObserver.EVENT_ADD]['with_extra'])
