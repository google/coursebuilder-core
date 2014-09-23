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

from models import config
from models import entities
from models import models
from models import services
from modules.notifications import notifications
from tests.functional import actions

from google.appengine.ext import db

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


class ContentChunkTestCase(actions.ExportTestBase):
    """Tests ContentChunkEntity|DAO|DTO."""

    # Allow access to protected members under test.
    # pylint: disable-msg=protected-access

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

    def test_dao_get_returns_datastore_entity_and_populates_cache(self):
        self.assertIsNone(models.MemcacheManager.get(self.memcache_key))

        key = models.ContentChunkDAO.save(models.ContentChunkDTO({
            'content_type': self.content_type,
            'contents': self.contents,
            'resource_id': self.resource_id,
            'supports_custom_tags': self.supports_custom_tags,
            'type_id': self.type_id,
        }))
        expected_dto = models.ContentChunkDAO._make_dto(db.get(key))
        from_datastore = models.ContentChunkEntity.get_by_id(self.id)
        from_cache = models.MemcacheManager.get(self.memcache_key)

        self.assert_fuzzy_equal(
            expected_dto, models.ContentChunkDAO._make_dto(from_datastore))
        self.assert_fuzzy_equal(expected_dto, from_cache)

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

    def test_dao_save_creates_new_object_and_populates_cache(self):
        self.assertIsNone(models.MemcacheManager.get(self.memcache_key))

        key = models.ContentChunkDAO.save(models.ContentChunkDTO({
            'content_type': self.content_type,
            'contents': self.contents,
            'id': self.id,
            'resource_id': self.resource_id,
            'supports_custom_tags': self.supports_custom_tags,
            'type_id': self.type_id,
        }))
        expected_dto = models.ContentChunkDAO._make_dto(db.get(key))

        self.assert_fuzzy_equal(
            expected_dto, models.MemcacheManager.get(self.memcache_key))

    def test_dao_save_updates_existing_object_and_populates_cache(self):
        key = models.ContentChunkDAO.save(models.ContentChunkDTO({
            'content_type': self.content_type,
            'contents': self.contents,
            'id': self.id,
            'resource_id': self.resource_id,
            'supports_custom_tags': self.supports_custom_tags,
            'type_id': self.type_id,
        }))
        original_dto = models.ContentChunkDAO._make_dto(db.get(key))

        self.assert_fuzzy_equal(
            original_dto, models.MemcacheManager.get(self.memcache_key))

        original_dto.content_type = 'new_content_type'
        original_dto.contents = 'new_contents'
        original_dto.supports_custom_tags = True
        original_dto.uid = 'new_system_id:new_resource:id'
        models.ContentChunkDAO.save(original_dto)
        expected_dto = models.ContentChunkDAO._make_dto(db.get(key))

        self.assert_fuzzy_equal(
            expected_dto, models.MemcacheManager.get(self.memcache_key))


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

    # Name determined by parent. pylint: disable-msg=g-bad-name
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


class StudentProfileDAOTestCase(actions.ExportTestBase):

    # Allow tests of protected state. pylint: disable-msg=protected-access

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
        email = 'user@example.com'
        sender = 'sender@example.com'
        title = 'title'
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
        models.StudentProfileDAO._send_welcome_notification(handler, email)
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
