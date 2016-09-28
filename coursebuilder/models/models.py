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

"""Core data model classes."""

__author__ = 'Pavel Simakov (psimakov@google.com)'

import collections
import copy
import datetime
import logging
import os
import sys
import time
import webapp2

import jinja2

import config
import counters
from counters import PerfCounter
from entities import BaseEntity
from entities import delete
from entities import get
from entities import put
import data_removal
import messages
import services
import transforms

import appengine_config
from common import caching
from common import utils as common_utils
from common import users

from google.appengine.api import app_identity
from google.appengine.api import mail
from google.appengine.api import memcache
from google.appengine.api import namespace_manager
from google.appengine.api import taskqueue
from google.appengine.ext import db

# We want to use memcache for both objects that exist and do not exist in the
# datastore. If object exists we cache its instance, if object does not exist
# we cache this object below.
NO_OBJECT = {}

# The default amount of time to cache the items for in memcache.
DEFAULT_CACHE_TTL_SECS = 60 * 5

# https://developers.google.com/appengine/docs/python/memcache/#Python_Limits
MEMCACHE_MAX = (1000 * 1000 - 96 - 250)
MEMCACHE_MULTI_MAX = 32 * 1000 * 1000

# Update frequency for Student.last_seen_on.
STUDENT_LAST_SEEN_ON_UPDATE_SEC = 24 * 60 * 60  # 1 day.

# Global memcache controls.
CAN_USE_MEMCACHE = config.ConfigProperty(
    'gcb_can_use_memcache', bool, messages.SITE_SETTINGS_MEMCACHE,
    default_value=appengine_config.PRODUCTION_MODE, label='Memcache')

# performance counters
CACHE_PUT = PerfCounter(
    'gcb-models-cache-put',
    'A number of times an object was put into memcache.')
CACHE_PUT_TOO_BIG = PerfCounter(
    'gcb-models-cache-put-too-big',
    'Number of times an object was too big to put in memcache.')
CACHE_HIT = PerfCounter(
    'gcb-models-cache-hit',
    'A number of times an object was found in memcache.')
CACHE_MISS = PerfCounter(
    'gcb-models-cache-miss',
    'A number of times an object was not found in memcache.')
CACHE_DELETE = PerfCounter(
    'gcb-models-cache-delete',
    'A number of times an object was deleted from memcache.')

# performance counters for in-process cache
CACHE_PUT_LOCAL = PerfCounter(
    'gcb-models-cache-put-local',
    'A number of times an object was put into local memcache.')
CACHE_HIT_LOCAL = PerfCounter(
    'gcb-models-cache-hit-local',
    'A number of times an object was found in local memcache.')
CACHE_MISS_LOCAL = PerfCounter(
    'gcb-models-cache-miss-local',
    'A number of times an object was not found in local memcache.')

# Intent for sending welcome notifications.
WELCOME_NOTIFICATION_INTENT = 'welcome'


class MemcacheManager(object):
    """Class that consolidates all memcache operations."""

    _LOCAL_CACHE = None
    _IS_READONLY = False
    _READONLY_REENTRY_COUNT = 0
    _READONLY_APP_CONTEXT = None

    @classmethod
    def _is_same_app_context_if_set(cls):
        if cls._READONLY_APP_CONTEXT is None:
            return True
        from controllers import sites
        app_context = sites.get_course_for_current_request()
        return cls._READONLY_APP_CONTEXT == app_context

    @classmethod
    def _assert_true_clear_cache_and_raise_if_not(cls, value_to_assert, msg):
        if not value_to_assert:
            cls.clear_readonly_cache()
            raise AssertionError(msg)

    @classmethod
    def _fs_begin_readonly(cls):
        from controllers import sites
        cls._READONLY_APP_CONTEXT = sites.get_course_for_current_request()
        if cls._READONLY_APP_CONTEXT:
            cls._READONLY_APP_CONTEXT.fs.begin_readonly()

    @classmethod
    def _fs_end_readonly(cls):
        if cls._READONLY_APP_CONTEXT:
            cls._READONLY_APP_CONTEXT.fs.end_readonly()
        cls._READONLY_APP_CONTEXT = None

    @classmethod
    def begin_readonly(cls):
        cls._assert_true_clear_cache_and_raise_if_not(
            cls._READONLY_REENTRY_COUNT >= 0, 'Re-entry counter is < 0.')
        cls._assert_true_clear_cache_and_raise_if_not(
            cls._is_same_app_context_if_set(), 'Unable to switch app_context.')
        if cls._READONLY_REENTRY_COUNT == 0:
            appengine_config.log_appstats_event(
                'MemcacheManager.begin_readonly')
            cls._IS_READONLY = True
            cls._LOCAL_CACHE = {}
            cls._fs_begin_readonly()
        cls._READONLY_REENTRY_COUNT += 1

    @classmethod
    def end_readonly(cls):
        cls._assert_true_clear_cache_and_raise_if_not(
            cls._READONLY_REENTRY_COUNT > 0, 'Re-entry counter <= 0.')
        cls._assert_true_clear_cache_and_raise_if_not(
            cls._is_same_app_context_if_set(), 'Unable to switch app_context.')
        cls._READONLY_REENTRY_COUNT -= 1
        if cls._READONLY_REENTRY_COUNT == 0:
            cls._fs_end_readonly()
            cls._IS_READONLY = False
            cls._LOCAL_CACHE = None
            cls._READONLY_APP_CONTEXT = None
            appengine_config.log_appstats_event('MemcacheManager.end_readonly')

    @classmethod
    def clear_readonly_cache(cls):
        cls._LOCAL_CACHE = None
        cls._IS_READONLY = False
        cls._READONLY_REENTRY_COUNT = 0
        if cls._READONLY_APP_CONTEXT and (
            cls._READONLY_APP_CONTEXT.fs.is_in_readonly):
            cls._READONLY_APP_CONTEXT.fs.end_readonly()
        cls._READONLY_APP_CONTEXT = None

    @classmethod
    def _local_cache_get(cls, key, namespace):
        if cls._IS_READONLY:
            assert cls._is_same_app_context_if_set()
            _dict = cls._LOCAL_CACHE.get(namespace)
            # TODO(nretallack): change to: if _dict is None
            if not _dict:
                _dict = {}
                cls._LOCAL_CACHE[namespace] = _dict
            if key in _dict:
                CACHE_HIT_LOCAL.inc()
                value = _dict[key]
                return True, value
            else:
                CACHE_MISS_LOCAL.inc()
        return False, None

    @classmethod
    def _local_cache_put(cls, key, namespace, value):
        if cls._IS_READONLY:
            assert cls._is_same_app_context_if_set()
            _dict = cls._LOCAL_CACHE.get(namespace)
            # TODO(nretallack): change to: if _dict is None
            if not _dict:
                _dict = {}
                cls._LOCAL_CACHE[namespace] = _dict
            _dict[key] = value
            CACHE_PUT_LOCAL.inc()

    @classmethod
    def _local_cache_get_multi(cls, keys, namespace):
        if cls._IS_READONLY:
            assert cls._is_same_app_context_if_set()
            values = []
            for key in keys:
                is_cached, value = cls._local_cache_get(key, namespace)
                if not is_cached:
                    return False, []
                else:
                    values.append(value)
            return True, values
        return False, []

    @classmethod
    def _local_cache_put_multi(cls, values, namespace):
        if cls._IS_READONLY:
            assert cls._is_same_app_context_if_set()
            for key, value in values.items():
                cls._local_cache_put(key, namespace, value)

    @classmethod
    def get_namespace(cls):
        """Look up namespace from namespace_manager or use default."""
        namespace = namespace_manager.get_namespace()
        if namespace:
            return namespace
        return appengine_config.DEFAULT_NAMESPACE_NAME

    @classmethod
    def _get_namespace(cls, namespace):
        if namespace is not None:
            return namespace
        return cls.get_namespace()

    @classmethod
    def get(cls, key, namespace=None):
        """Gets an item from memcache if memcache is enabled."""
        if not CAN_USE_MEMCACHE.value:
            return None
        _namespace = cls._get_namespace(namespace)

        is_cached, value = cls._local_cache_get(key, _namespace)
        if is_cached:
            return copy.deepcopy(value)

        value = memcache.get(key, namespace=_namespace)

        # We store some objects in memcache that don't evaluate to True, but are
        # real objects, '{}' for example. Count a cache miss only in a case when
        # an object is None.
        if value is not None:
            CACHE_HIT.inc()
        else:
            CACHE_MISS.inc(context=key)

        cls._local_cache_put(key, _namespace, value)
        return copy.deepcopy(value)

    @classmethod
    def get_multi(cls, keys, namespace=None):
        """Gets a set of items from memcache if memcache is enabled."""
        if not CAN_USE_MEMCACHE.value:
            return {}

        _namespace = cls._get_namespace(namespace)

        is_cached, values = cls._local_cache_get_multi(keys, _namespace)
        if is_cached:
            return values

        values = memcache.get_multi(keys, namespace=_namespace)
        for key, value in values.items():
            if value is not None:
                CACHE_HIT.inc()
            else:
                logging.info('Cache miss, key: %s. %s', key, Exception())
                CACHE_MISS.inc(context=key)

        cls._local_cache_put_multi(values, _namespace)
        return values

    @classmethod
    def set(cls, key, value, ttl=DEFAULT_CACHE_TTL_SECS, namespace=None,
            propagate_exceptions=False):
        """Sets an item in memcache if memcache is enabled."""
        # Ensure subsequent mods to value do not affect the cached copy.
        value = copy.deepcopy(value)

        try:
            if CAN_USE_MEMCACHE.value:
                size = sys.getsizeof(value)
                if size > MEMCACHE_MAX:
                    CACHE_PUT_TOO_BIG.inc()
                else:
                    CACHE_PUT.inc()
                    _namespace = cls._get_namespace(namespace)
                    memcache.set(key, value, ttl, namespace=_namespace)
                    cls._local_cache_put(key, _namespace, value)
        except:  # pylint: disable=bare-except
            if propagate_exceptions:
                raise
            else:
                logging.exception(
                    'Failed to set: %s, %s', key, cls._get_namespace(namespace))
            return None

    @classmethod
    def set_multi(cls, mapping, ttl=DEFAULT_CACHE_TTL_SECS, namespace=None):
        """Sets a dict of items in memcache if memcache is enabled."""
        try:
            if CAN_USE_MEMCACHE.value:
                if not mapping:
                    return
                size = sum([
                    sys.getsizeof(key) + sys.getsizeof(value)
                    for key, value in mapping.items()])
                if size > MEMCACHE_MULTI_MAX:
                    CACHE_PUT_TOO_BIG.inc()
                else:
                    CACHE_PUT.inc()
                    _namespace = cls._get_namespace(namespace)
                    memcache.set_multi(mapping, time=ttl, namespace=_namespace)
                    cls._local_cache_put_multi(mapping, _namespace)
        except:  # pylint: disable=bare-except
            logging.exception(
                'Failed to set_multi: %s, %s',
                mapping, cls._get_namespace(namespace))
            return None

    @classmethod
    def delete(cls, key, namespace=None):
        """Deletes an item from memcache if memcache is enabled."""
        assert not cls._IS_READONLY
        if CAN_USE_MEMCACHE.value:
            CACHE_DELETE.inc()
            memcache.delete(key, namespace=cls._get_namespace(namespace))

    @classmethod
    def delete_multi(cls, key_list, namespace=None):
        """Deletes a list of items from memcache if memcache is enabled."""
        assert not cls._IS_READONLY
        if CAN_USE_MEMCACHE.value:
            CACHE_DELETE.inc(increment=len(key_list))
            memcache.delete_multi(
                key_list, namespace=cls._get_namespace(namespace))

    @classmethod
    def incr(cls, key, delta, namespace=None):
        """Incr an item in memcache if memcache is enabled."""
        if CAN_USE_MEMCACHE.value:
            memcache.incr(
                key, delta,
                namespace=cls._get_namespace(namespace), initial_value=0)


CAN_AGGREGATE_COUNTERS = config.ConfigProperty(
    'gcb_can_aggregate_counters', bool,
    messages.SITE_SETTINGS_AGGREGATE_COUNTERS, default_value=False,
    label='Aggregate Counters')


def incr_counter_global_value(name, delta):
    if CAN_AGGREGATE_COUNTERS.value:
        MemcacheManager.incr(
            'counter:' + name, delta,
            namespace=appengine_config.DEFAULT_NAMESPACE_NAME)


def get_counter_global_value(name):
    if CAN_AGGREGATE_COUNTERS.value:
        return MemcacheManager.get(
            'counter:' + name,
            namespace=appengine_config.DEFAULT_NAMESPACE_NAME)
    else:
        return None

counters.get_counter_global_value = get_counter_global_value
counters.incr_counter_global_value = incr_counter_global_value

DEPRECATED_CAN_SHARE_STUDENT_PROFILE = config.ConfigProperty(
    'gcb_can_share_student_profile', bool, '', default_value=False,
    deprecated=True)

class CollisionError(Exception):
    """Exception raised to show that a collision in a namespace has occurred."""


class ValidationError(Exception):
    """Exception raised to show that a validation failed."""


class ContentChunkEntity(BaseEntity):
    """Defines storage for ContentChunk, a blob of opaque content to display."""

    _PROPERTY_EXPORT_BLACKLIST = []  # No PII in ContentChunks.

    # A string that gives the type of the content chunk. At the data layer we
    # make no restrictions on the values that can be used here -- we only
    # require that a type is given. The type here may be independent of any
    # notion of Content-Type in an HTTP header.
    content_type = db.StringProperty(required=True)
    # UTC last modification timestamp.
    last_modified = db.DateTimeProperty(auto_now=True, required=True)
    # Whether or not the chunk supports custom tags. If True, the renderer may
    # be extended to parse and render those tags at display time (this is a stub
    # for future functionality that does not exist yet). If False, the contents
    # of the chunk will be rendered verbatim.
    supports_custom_tags = db.BooleanProperty(default=False)
    # Optional identifier for the chunk in the system it was sourced from.
    # Format is type_id:resource_id where type_id is an identifier that maps to
    # an external system and resource_id is the identifier for a resource within
    # that system (e.g. 'drive:1234' or 'web:http://example.com/index.html').
    # Exact values are up to the caller, but if either type_id or resource_id is
    # given, both must be, they must both be truthy, and type_id cannot contain
    # ':'. Max size is 500B, enforced by datastore.
    uid = db.StringProperty(indexed=True)

    # Payload of the chunk. Max size is 1MB, enforced by datastore.
    contents = db.TextProperty()


class ContentChunkDAO(object):
    """Data access object for ContentChunks."""

    @classmethod
    def delete(cls, entity_id):
        """Deletes ContentChunkEntity for datastore id int; returns None."""
        memcache_key = cls._get_memcache_key(entity_id)
        entity = ContentChunkEntity.get_by_id(entity_id)

        if entity:
            delete(entity)

        MemcacheManager.delete(memcache_key)

    @classmethod
    def get(cls, entity_id):
        """Gets ContentChunkEntityDTO or None from given datastore id int."""
        if entity_id is None:
            return

        memcache_key = cls._get_memcache_key(entity_id)
        found = MemcacheManager.get(memcache_key)

        if found == NO_OBJECT:
            return None
        elif found:
            return found
        else:
            result = None
            cache_value = NO_OBJECT

            entity = ContentChunkEntity.get_by_id(entity_id)
            if entity:
                result = cls._make_dto(entity)
                cache_value = result

            MemcacheManager.set(memcache_key, cache_value)
            return result

    @classmethod
    def get_by_uid(cls, uid):
        """Gets list of DTOs for all entities with given uid string."""
        results = ContentChunkEntity.all().filter(
            ContentChunkEntity.uid.name, uid
        ).fetch(1000)
        return sorted(
            [cls._make_dto(result) for result in results],
            key=lambda dto: dto.id)

    @classmethod
    def get_or_new_by_uid(cls, uid):
        result = cls.get_one_by_uid(uid)
        if result is not None:
            return result
        else:
            type_id, resource_id = cls._split_uid(uid)
            return ContentChunkDTO({
                'type_id': type_id,
                'resource_id': resource_id,
            })

    @classmethod
    def get_one_by_uid(cls, uid):
        matches = cls.get_by_uid(uid)
        if matches:
            # There is a data race in the DAO -- it's possible to create two
            # entries at the same time with the same UID. If that happened,
            # use the first one saved.
            return matches[0]
        else:
            return None

    @classmethod
    def make_uid(cls, type_id, resource_id):
        """Makes a uid string (or None) from the given strings (or Nones)."""
        if type_id is None and resource_id is None:
            return None

        assert type_id and resource_id and ':' not in type_id
        return '%s:%s' % (type_id, resource_id)

    @classmethod
    def save(cls, dto):
        """Saves content of DTO and returns the key of the saved entity.

        Handles both creating new and updating existing entities. If the id of a
        passed DTO is found, the entity will be updated; otherwise, the entity
        will be created.

        Note that this method does not refetch the saved entity from the
        datastore after put since this is impossible in a transaction. This
        means the last_modified date we put in the cache skews from the actual
        saved value by however long put took. This is expected datastore
        behavior; we do not at present have a use case for perfect accuracy in
        this value for our getters.

        Args:
            dto: ContentChunkDTO. DTO to save. Its last_modified field is
                ignored.

        Returns:
            db.Key of saved ContentChunkEntity.
        """
        return cls.save_all([dto])[0]

    @classmethod
    def save_all(cls, dtos):
        """Saves all given DTOs; see save() for semantics.

        Args:
            dtos: list of ContentChunkDTO. The last_modified field is ignored.

        Returns:
            List of db.Key of saved ContentChunkEntities, in order of dto input.
        """
        entities = []
        for dto in dtos:
            if dto.id is None:
                entity = ContentChunkEntity(content_type=dto.content_type)
            else:
                entity = ContentChunkEntity.get_by_id(dto.id)

                if entity is None:
                    entity = ContentChunkEntity(content_type=dto.content_type)

            entity.content_type = dto.content_type
            entity.contents = dto.contents
            entity.supports_custom_tags = dto.supports_custom_tags
            entity.uid = cls.make_uid(dto.type_id, dto.resource_id)
            entities.append(entity)

        db.put(entities)

        for entity in entities:
            MemcacheManager.delete(cls._get_memcache_key(entity.key().id()))

        return [entity.key() for entity in entities]

    @classmethod
    def _get_memcache_key(cls, entity_id):
        assert entity_id is not None
        return '(%s:%s)' % (ContentChunkEntity.kind(), entity_id)

    @classmethod
    def _make_dto(cls, entity):
        type_id, resource_id = cls._split_uid(entity.uid)
        return ContentChunkDTO({
            'content_type': entity.content_type,
            'contents': entity.contents,
            'id': entity.key().id(),
            'last_modified': entity.last_modified,
            'resource_id': resource_id,
            'supports_custom_tags': entity.supports_custom_tags,
            'type_id': type_id,
        })

    @classmethod
    def _split_uid(cls, uid):
        resource_id = None
        type_id = None

        if uid is not None:
            assert ':' in uid
            type_id, resource_id = uid.split(':', 1)
            assert type_id and resource_id

        return type_id, resource_id


class ContentChunkDTO(object):
    """Data transfer object for ContentChunks."""

    def __init__(self, entity_dict):
        self.content_type = entity_dict.get('content_type')
        self.contents = entity_dict.get('contents')
        self.id = entity_dict.get('id')
        self.last_modified = entity_dict.get('last_modified')
        self.resource_id = entity_dict.get('resource_id')
        self.supports_custom_tags = entity_dict.get('supports_custom_tags')
        self.type_id = entity_dict.get('type_id')

    def __eq__(self, other):
        return (
            isinstance(other, ContentChunkDTO) and
            self.content_type == other.content_type and
            self.contents == other.contents and
            self.id == other.id and
            self.last_modified == other.last_modified and
            self.resource_id == other.resource_id and
            self.supports_custom_tags == other.supports_custom_tags and
            self.type_id == other.type_id)


class PersonalProfile(BaseEntity):
    """Personal information not specific to any course instance."""

    email = db.StringProperty(indexed=False)
    legal_name = db.StringProperty(indexed=False)
    nick_name = db.StringProperty(indexed=False)
    date_of_birth = db.DateProperty(indexed=False)
    course_info = db.TextProperty()

    _PROPERTY_EXPORT_BLACKLIST = [email, legal_name, nick_name, date_of_birth]

    @property
    def user_id(self):
        return self.key().name()

    @classmethod
    def safe_key(cls, db_key, transform_fn):
        return db.Key.from_path(cls.kind(), transform_fn(db_key.name()))


class PersonalProfileDTO(object):
    """DTO for PersonalProfile."""

    def __init__(self, personal_profile=None):
        self.course_info = '{}'
        if personal_profile:
            self.user_id = personal_profile.user_id
            self.email = personal_profile.email
            self.legal_name = personal_profile.legal_name
            self.nick_name = personal_profile.nick_name
            self.date_of_birth = personal_profile.date_of_birth
            self.course_info = personal_profile.course_info


QUEUE_RETRIES_BEFORE_SENDING_MAIL = config.ConfigProperty(
    'gcb_lifecycle_queue_retries_before_sending_mail', int,
    messages.SITE_SETTINGS_QUEUE_NOTIFICATION, default_value=10,
    label='Queue Notification',
    validator=config.ValidateIntegerRange(1, 50).validate)


class StudentLifecycleObserver(webapp2.RequestHandler):
    """Provides notification on major events to Students for interested modules.

    Notification is done from an App Engine deferred work queue.  This is done
    so that observers who _absolutely_ _positively_ _have_ _to_ _be_ _notified_
    are either going to be notified, or a site administrator is going to get
    an ongoing sequence of email notifications that Something Is Wrong, and
    will then address the problem manually.

    Modules can register to be called back for the lifecycle events listed
    below.  Callbacks should be registered like this:

        models.StudentLifecycleObserver.EVENT_CALLBACKS[
            models.StudentLifecycleObserver.EVENT_ADD]['my_module'] = my_handler

    If a callback function needs to have extra information passed to it that
    needs to be collected in the context where the lifecycle event is actually
    happening, modules can register a function in the ENQUEUE_CALLBACKS.  Add
    one of those in the same way as for event callbacks:

        models.StudentLifecycleObserver.ENQUEUE_CALLBACKS[
            models.StudentLifecycleObserver.EVENT_ADD]['my_module'] = a_function

    Event notification callbacks are called repeatedly until they return
    without raising an exception.  Note that due to retries having an
    exponential backoff (to a maximum of two hours), you cannot rely on
    notifications being delivered in any particular order relative to one
    another.

    Event notification callbacks must take two or three parameters:
    - the user_id (a string)
    - the datetime.datetime UTC timestamp when the event originally occurred.
    - If-and-only-if the the enqueue callback was registered and returned a
      non-None value, this argument is passed.  If this value is mutable, any
      changes made by the event callback will be retained in any future
      re-tries.

    Enqueue callback functions must take exactly one parameter:
    - the user_id of the user to which the event pertains.
    The function may return any data type which is convertible to a JSON
    string using transforms.dumps().  This value is passed to the event
    notification callback.

    """

    QUEUE_NAME = 'user-lifecycle'
    URL = '/_ah/queue/' + QUEUE_NAME
    EVENT_ADD = 'add'
    EVENT_UNENROLL = 'unenroll'
    EVENT_UNENROLL_COMMANDED = 'unenroll_commanded'
    EVENT_REENROLL = 'reenroll'

    EVENT_CALLBACKS = {
        EVENT_ADD: {},
        EVENT_UNENROLL: {},
        EVENT_UNENROLL_COMMANDED: {},
        EVENT_REENROLL: {},
    }
    ENQUEUE_CALLBACKS = {
        EVENT_ADD: {},
        EVENT_UNENROLL: {},
        EVENT_UNENROLL_COMMANDED: {},
        EVENT_REENROLL: {},
    }

    @classmethod
    def enqueue(cls, event, user_id, transactional=True):
        if event not in cls.EVENT_CALLBACKS:
            raise ValueError('Event "%s" not in allowed list: %s' % (
                event, ' '.join(cls.EVENT_CALLBACKS)))
        if not user_id:
            raise ValueError('User ID must be non-blank')
        if not cls.EVENT_CALLBACKS[event]:
            return  # No callbacks registered for event -> nothing to do; skip.
        extra_data = {}
        for name, callback in cls.ENQUEUE_CALLBACKS[event].iteritems():
            extra_data[name] = callback(user_id)
        cls._internal_enqueue(
            event, user_id, cls.EVENT_CALLBACKS[event].keys(), extra_data,
            transactional=transactional)

    @classmethod
    def _internal_enqueue(cls, event, user_id, callbacks, extra_data,
                          transactional):
        for callback in callbacks:
            if callback not in cls.EVENT_CALLBACKS[event]:
                raise ValueError(
                    'Callback "%s" not in callbacks registered for event %s'
                    % (callback, event))

        task = taskqueue.Task(params={
            'event': event,
            'user_id': user_id,
            'callbacks': ' '.join(callbacks),
            'timestamp': datetime.datetime.utcnow().strftime(
                transforms.ISO_8601_DATETIME_FORMAT),
            'extra_data': transforms.dumps(extra_data),
        })
        task.add(cls.QUEUE_NAME, transactional=transactional)

    def post(self):
        if 'X-AppEngine-QueueName' not in self.request.headers:
            self.response.set_status(500)
            return
        user_id = self.request.get('user_id')
        if not user_id:
            logging.critical('Student lifecycle queue had item with no user')
            self.response.set_status(200)
            return
        event = self.request.get('event')
        if not event:
            logging.critical('Student lifecycle queue had item with no event')
            self.response.set_status(200)
            return
        timestamp_str = self.request.get('timestamp')
        try:
            timestamp = datetime.datetime.strptime(
                timestamp_str, transforms.ISO_8601_DATETIME_FORMAT)
        except ValueError:
            logging.critical('Student lifecycle queue: malformed timestamp %s',
                             timestamp_str)
            self.response.set_status(200)
            return

        extra_data = self.request.get('extra_data')
        if extra_data:
            extra_data = transforms.loads(extra_data)
        else:
            extra_data = {}

        callbacks = self.request.get('callbacks')
        if not callbacks:
            logging.warning('Odd: Student lifecycle with no callback items')
            self.response.set_status(200)
            return
        callbacks = callbacks.split(' ')

        # Configure path in threadlocal cache in sites; callbacks may
        # be dynamically determining their current context by calling
        # sites.get_app_context_for_current_request(), which relies on
        # sites.PATH_INFO_THREAD_LOCAL.path.
        current_namespace = namespace_manager.get_namespace()
        logging.info(
            '-- Dequeue in namespace "%s" handling event %s for user %s --',
            current_namespace, event, user_id)
        from controllers import sites
        app_context = sites.get_course_index().get_app_context_for_namespace(
            current_namespace)
        path = app_context.get_slug()
        if hasattr(sites.PATH_INFO_THREAD_LOCAL, 'path'):
            has_path_info = True
            save_path_info = sites.PATH_INFO_THREAD_LOCAL.path
        else:
            has_path_info = False
        sites.PATH_INFO_THREAD_LOCAL.path = path

        try:
            remaining_callbacks = []
            for callback in callbacks:
                if callback not in self.EVENT_CALLBACKS[event]:
                    logging.error(
                        'Student lifecycle event enqueued with callback named '
                        '"%s", but no such callback is currently registered.',
                        callback)
                    continue
                try:
                    logging.info('-- Student lifecycle callback %s starting --',
                                 callback)
                    callback_extra_data = extra_data.get(callback)
                    if callback_extra_data is None:
                        self.EVENT_CALLBACKS[event][callback](
                            user_id, timestamp)
                    else:
                        self.EVENT_CALLBACKS[event][callback](
                            user_id, timestamp, callback_extra_data)
                    logging.info('-- Student lifecycle callback %s success --',
                                 callback)
                except Exception, ex:  # pylint: disable=broad-except
                    logging.error(
                        '-- Student lifecycle callback %s fails: %s --',
                        callback, str(ex))
                    common_utils.log_exception_origin()
                    remaining_callbacks.append(callback)
        finally:
            if has_path_info:
                sites.PATH_INFO_THREAD_LOCAL.path = save_path_info
            else:
                del sites.PATH_INFO_THREAD_LOCAL.path

        if remaining_callbacks == callbacks:
            # If we have made _no_ progress, emit error and get queue backoff.
            num_tries = 1 + int(
                self.request.headers.get('X-AppEngine-TaskExecutionCount', '0'))
            complaint = (
                'Student lifecycle callback in namespace %s for '
                'event %s enqueued at %s made no progress on any of the '
                'callbacks %s for user %s after %d attempts' % (
                namespace_manager.get_namespace() or '<blank>',
                event, timestamp_str, callbacks, user_id, num_tries))
            logging.warning(complaint)

            if num_tries >= QUEUE_RETRIES_BEFORE_SENDING_MAIL.value:
                app_id = app_identity.get_application_id()
                sender = 'queue_admin@%s.appspotmail.com' % app_id
                subject = ('Queue processing: Excessive retries '
                           'on student lifecycle queue')
                body = complaint + ' in application ' + app_id
                mail.send_mail_to_admins(sender, subject, body)
            raise RuntimeError(
                'Queued work incomplete; raising error to force retries.')
        else:
            # If we made some progress, but still have work to do, re-enqueue
            # remaining work.
            if remaining_callbacks:
                logging.warning(
                    'Student lifecycle callback for event %s enqueued at %s '
                    'made some progress, but needs retries for the following '
                    'callbacks: %s', event, timestamp_str, callbacks)
                self._internal_enqueue(
                    event, user_id, remaining_callbacks, extra_data,
                    transactional=False)
            # Claim success if any work done, whether or not any work remains.
            self.response.set_status(200)


class StudentProfileDAO(object):
    """All access and mutation methods for PersonalProfile and Student."""

    TARGET_NAMESPACE = appengine_config.DEFAULT_NAMESPACE_NAME

    # Only for use from modules with fields in Student or PersonalProfile.
    # (As of 2016-02-19, this is only student_groups).  Other modules should
    # register with StudentLifecycleObserver.
    STUDENT_CREATION_HOOKS = []

    @classmethod
    def _memcache_key(cls, key):
        """Makes a memcache key from primary key."""
        return 'entity:personal-profile:%s' % key

    @classmethod
    def _get_profile_by_user_id(cls, user_id):
        """Loads profile given a user_id and returns Entity object."""
        old_namespace = namespace_manager.get_namespace()
        try:
            namespace_manager.set_namespace(cls.TARGET_NAMESPACE)

            profile = MemcacheManager.get(
                cls._memcache_key(user_id), namespace=cls.TARGET_NAMESPACE)
            if profile == NO_OBJECT:
                return None
            if profile:
                return profile
            profile = PersonalProfile.get_by_key_name(user_id)
            MemcacheManager.set(
                cls._memcache_key(user_id), profile if profile else NO_OBJECT,
                namespace=cls.TARGET_NAMESPACE)
            return profile
        finally:
            namespace_manager.set_namespace(old_namespace)

    @classmethod
    def delete_profile_by_user_id(cls, user_id):
        with common_utils.Namespace(cls.TARGET_NAMESPACE):
            PersonalProfile.delete_by_key(user_id)
            MemcacheManager.delete(
                cls._memcache_key(user_id), namespace=cls.TARGET_NAMESPACE)

    @classmethod
    def add_new_profile(cls, user_id, email):
        """Adds new profile for a user_id and returns Entity object."""
        old_namespace = namespace_manager.get_namespace()
        try:
            namespace_manager.set_namespace(cls.TARGET_NAMESPACE)
            profile = PersonalProfile(key_name=user_id)
            profile.email = email
            profile.put()
            return profile
        finally:
            namespace_manager.set_namespace(old_namespace)

    @classmethod
    def _update_global_profile_attributes(
        cls, profile,
        email=None, legal_name=None, nick_name=None,
        date_of_birth=None, is_enrolled=None, final_grade=None,
        course_info=None):
        """Modifies various attributes of Student's Global Profile."""
        if email is not None:
            profile.email = email.lower()

        if legal_name is not None:
            profile.legal_name = legal_name

        if nick_name is not None:
            profile.nick_name = nick_name

        if date_of_birth is not None:
            profile.date_of_birth = date_of_birth

        # TODO(nretallack): Remove this block and re-calculate this dynamically
        if final_grade is not None or course_info is not None:

            # Defer to avoid circular import.
            from controllers import sites
            course = sites.get_course_for_current_request()
            course_namespace = course.get_namespace_name()

            course_info_dict = {}
            if profile.course_info:
                course_info_dict = transforms.loads(profile.course_info)
            info = course_info_dict.get(course_namespace, {})
            if final_grade:
                info['final_grade'] = final_grade
            if course_info:
                info['info'] = course_info
            course_info_dict[course_namespace] = info
            profile.course_info = transforms.dumps(course_info_dict)

    @classmethod
    def _update_course_profile_attributes(
        cls, student, nick_name=None, is_enrolled=None, labels=None):
        """Modifies various attributes of Student's Course Profile."""

        if nick_name is not None:
            student.name = nick_name

        if is_enrolled is not None:
            student.is_enrolled = is_enrolled

        if labels is not None:
            student.labels = labels

    @classmethod
    def _update_attributes(
        cls, profile, student,
        email=None, legal_name=None, nick_name=None,
        date_of_birth=None, is_enrolled=None, final_grade=None,
        course_info=None, labels=None):
        """Modifies various attributes of Student and Profile."""

        if profile:
            cls._update_global_profile_attributes(
                profile, email=email, legal_name=legal_name,
                nick_name=nick_name, date_of_birth=date_of_birth,
                is_enrolled=is_enrolled, final_grade=final_grade,
                course_info=course_info)

        if student:
            cls._update_course_profile_attributes(
                student, nick_name=nick_name, is_enrolled=is_enrolled,
                labels=labels)

    @classmethod
    def _put_profile(cls, profile):
        """Does a put() on profile objects."""
        if not profile:
            return
        profile.put()
        MemcacheManager.delete(
            cls._memcache_key(profile.user_id),
            namespace=cls.TARGET_NAMESPACE)

    @classmethod
    def get_profile_by_user_id(cls, user_id):
        """Loads profile given a user_id and returns DTO object."""
        profile = cls._get_profile_by_user_id(user_id)
        if profile:
            return PersonalProfileDTO(personal_profile=profile)
        return None

    @classmethod
    def get_profile_by_user(cls, user):
        return cls.get_profile_by_user_id(user.user_id())

    @classmethod
    def add_new_student_for_current_user(
        cls, nick_name, additional_fields, handler, labels=None):
        user = users.get_current_user()

        student_by_uid = Student.get_by_user_id(user.user_id())
        is_valid_student = (student_by_uid is None or
                            student_by_uid.user_id == user.user_id())
        assert is_valid_student, (
            'Student\'s email and user id do not match.')

        student = cls._add_new_student_for_current_user(
            user.user_id(), user.email(), nick_name, additional_fields, labels)

        try:
            cls._send_welcome_notification(handler, student)
        except Exception, e:  # On purpose. pylint: disable=broad-except
            logging.error(
                'Unable to send welcome notification; error was: ' + str(e))

    @classmethod
    def _add_new_student_for_current_user(
        cls, user_id, email, nick_name, additional_fields, labels=None):
        student = Student.get_by_user_id(user_id)
        key_name = None
        if student:
            key_name = student.key().name()
        student = cls._add_new_student_for_current_user_in_txn(
          key_name, user_id, email, nick_name, additional_fields, labels)
        return student

    @classmethod
    @db.transactional(xg=True)
    def _add_new_student_for_current_user_in_txn(
        cls, key_name, user_id, email, nick_name, additional_fields,
        labels=None):
        """Create new or re-enroll old student."""

        # create profile if does not exist
        profile = cls._get_profile_by_user_id(user_id)
        if not profile:
            profile = cls.add_new_profile(user_id, email)

        # create new student or re-enroll existing
        if key_name:
            student = Student.get_by_key_name(key_name)
        else:
            student = Student._add_new(  # pylint: disable=protected-access
                user_id, email)

        # update profile
        cls._update_attributes(
            profile, student, nick_name=nick_name, is_enrolled=True,
            labels=labels)

        # update student
        student.email = email.lower()
        student.additional_fields = additional_fields
        common_utils.run_hooks(cls.STUDENT_CREATION_HOOKS, student, profile)

        # put both
        cls._put_profile(profile)

        student.put()
        StudentLifecycleObserver.enqueue(
            StudentLifecycleObserver.EVENT_ADD, user_id)
        return student

    @classmethod
    def _send_welcome_notification(cls, handler, student):
        if not cls._can_send_welcome_notifications(handler):
            return

        if services.unsubscribe.has_unsubscribed(student.email):
            return

        course_settings = handler.app_context.get_environ()['course']
        course_title = course_settings['title']
        sender = cls._get_welcome_notifications_sender(handler)

        assert sender, 'Must set welcome_notifications_sender in course.yaml'

        context = {
            'student_name': student.name,
            'course_title': course_title,
            'course_url': handler.get_base_href(handler),
            'unsubscribe_url': services.unsubscribe.get_unsubscribe_url(
                handler, student.email)
        }

        if course_settings.get('welcome_notifications_subject'):
            subject = jinja2.Template(unicode(
                course_settings['welcome_notifications_subject']
            )).render(context)
        else:
            subject = 'Welcome to ' + course_title

        if course_settings.get('welcome_notifications_body'):
            body = jinja2.Template(unicode(
                course_settings['welcome_notifications_body']
            )).render(context)
        else:
            jinja_environment = handler.app_context.fs.get_jinja_environ(
                [os.path.join(
                    appengine_config.BUNDLE_ROOT, 'views', 'notifications')],
                autoescape=False)
            body = jinja_environment.get_template('welcome.txt').render(context)

        services.notifications.send_async(
            student.email, sender, WELCOME_NOTIFICATION_INTENT,
            body, subject, audit_trail=context,
        )

    @classmethod
    def _can_send_welcome_notifications(cls, handler):
        return (
            services.notifications.enabled() and services.unsubscribe.enabled()
            and cls._get_send_welcome_notifications(handler))

    @classmethod
    def _get_send_welcome_notifications(cls, handler):
        return handler.app_context.get_environ().get(
            'course', {}
        ).get('send_welcome_notifications', False)

    @classmethod
    def _get_welcome_notifications_sender(cls, handler):
        return handler.app_context.get_environ().get(
            'course', {}
        ).get('welcome_notifications_sender')

    @classmethod
    def get_enrolled_student_by_user_for(cls, user, app_context):
        """Returns student for a specific course."""
        old_namespace = namespace_manager.get_namespace()
        try:
            namespace_manager.set_namespace(app_context.get_namespace_name())
            return Student.get_enrolled_student_by_user(user)
        finally:
            namespace_manager.set_namespace(old_namespace)

    @classmethod
    def unregister_user(cls, user_id, unused_timestamp):
        student = Student.get_by_user_id(user_id)
        if not student:
            logging.info(
                'Unregister commanded for user %s, but user already gone.',
                user_id)
            return
        cls.update(user_id, None, is_enrolled=False)

    @classmethod
    def update(
        cls, user_id, email, legal_name=None, nick_name=None,
        date_of_birth=None, is_enrolled=None, final_grade=None,
        course_info=None, labels=None, profile_only=False):
        student = Student.get_by_user_id(user_id)
        key_name = None
        if student:
            key_name = student.key().name()
        cls._update_in_txn(
            key_name, user_id, email, legal_name, nick_name, date_of_birth,
            is_enrolled, final_grade, course_info, labels, profile_only)

    @classmethod
    @db.transactional(xg=True)
    def _update_in_txn(
        cls, key_name, user_id, email, legal_name=None, nick_name=None,
        date_of_birth=None, is_enrolled=None, final_grade=None,
        course_info=None, labels=None, profile_only=False):
        """Updates a student and/or their global profile."""
        student = None
        if not profile_only:
            if key_name:
                student = Student.get_by_key_name(key_name)
            if not student:
                raise Exception('Unable to find student for: %s' % email)

        profile = cls._get_profile_by_user_id(user_id)
        if not profile:
            profile = cls.add_new_profile(user_id, email)

        if (student and is_enrolled is not None and
            student.is_enrolled != is_enrolled):
            if is_enrolled:
                event = StudentLifecycleObserver.EVENT_REENROLL
            else:
                event = StudentLifecycleObserver.EVENT_UNENROLL
            StudentLifecycleObserver.enqueue(event, student.user_id)

        cls._update_attributes(
            profile, student, email=email, legal_name=legal_name,
            nick_name=nick_name, date_of_birth=date_of_birth,
            is_enrolled=is_enrolled, final_grade=final_grade,
            course_info=course_info, labels=labels)

        cls._put_profile(profile)
        if not profile_only:
            student.put()


class StudentCache(caching.RequestScopedSingleton):
    """Class that manages optimized loading of Students from datastore."""

    def __init__(self):
        self._key_name_to_student = {}

    @classmethod
    def _key(cls, user_id):
        """Make key specific to user_id and current namespace."""
        return '%s-%s' % (MemcacheManager.get_namespace(), user_id)

    def _get_by_user_id_from_datastore(self, user_id):
        """Load Student by user_id. Fail if user_id is not unique."""
        # In the CB 1.8 and below email was the key_name. This is no longer
        # true. To support legacy Student entities do a double look up here:
        # first by the key_name value and then by the user_id field value.
        student = Student.get_by_key_name(user_id)
        if student:
            return student

        students = Student.all().filter(
            Student.user_id.name, user_id).fetch(limit=2)
        if len(students) > 1:
            raise Exception(
                'There is more than one student with user_id "%s"' % user_id)

        return students[0] if students else None

    def _get_by_user_id(self, user_id):
        """Get cached Student with user_id or load one from datastore."""
        key = self._key(user_id)
        if key in self._key_name_to_student:
            return self._key_name_to_student[key]
        student = self._get_by_user_id_from_datastore(user_id)
        self._key_name_to_student[key] = student
        return student

    def _remove(self, user_id):
        """Remove cached value by user_id."""
        key = self._key(user_id)
        if key in self._key_name_to_student:
            del self._key_name_to_student[key]

    @classmethod
    def remove(cls, user_id):
        # pylint: disable=protected-access
        return cls.instance()._remove(user_id)

    @classmethod
    def get_by_user_id(cls, user_id):
        # pylint: disable=protected-access
        return cls.instance()._get_by_user_id(user_id)


class _EmailProperty(db.StringProperty):
    """Class that provides dual look up of email property value."""

    def __get__(self, model_instance, model_class):
        if model_instance is None:
            return self

        # Try to get and use the actual stored value.
        value = super(_EmailProperty, self).__get__(model_instance, model_class)
        if value:
            return value

        # In CB 1.8 and before email was used as a key to Student entity. This
        # is no longer true. Here we provide the backwards compatibility for the
        # legacy Student instances. If user_id and key.name match, it means that
        # the user_id is a key and we should not use key as email and email is
        # not set. If key.name and user_id don't match, the key is also an
        # email.
        if model_instance.is_saved():
            user_id = model_instance.user_id
            key_name = model_instance.key().name()
            if key_name != user_id:
                return key_name

        return None


class _ReadOnlyStringProperty(db.StringProperty):
    """Class that provides set once read-only property."""

    def __set__(self, model_instance, value):
        if model_instance:
            validated_value = self.validate(value)
            current_value = self.get_value_for_datastore(model_instance)
            if current_value and current_value != validated_value:
                raise ValueError(
                    'Unable to change set once read-only property '
                    '%s.' % self.name)
        super(_ReadOnlyStringProperty, self).__set__(model_instance, value)


class Student(BaseEntity):
    """Student data specific to a course instance.

    This entity represents a student in a specific course. It has somewhat
    complex key_name/user_id/email behavior that comes from the legacy mistakes.
    Current and historical behavior of this class is documented in detail below.

    Let us start with the historical retrospect. In CB 1.8 and below:
        - key_name
            - is email for new users
        - email
            - is used as key_name
            - is unique
            - is immutable
        - user_id
            - was introduced in CB 1.2.0
            - was an independent field and not a key_name
            - held google.appengine.api.users.get_current_user().user_id()
            - mutations were not explicitly prevented, but no mutations are
              known to have occurred
            - was used as foreign key in other tables

    Anyone who attempts federated identity will find use of email as key_name
    completely unacceptable. So we decided to make user_id a key_name.

    The ideal solution would have been:
        - store user_id as key_name for new and legacy users
        - store email as an independent mutable field

    The ideal solution was rejected upon discussion. It required taking course
    offline and running M/R or ETL job to modify key_name. All foreign key
    relationships that used old key_name value would need to be fixed up to use
    new value. ETL would also need to be aware of different key structure before
    and after CB 1.8. All in all the ideal approach is complex, invasive and
    error prone. It was ultimately rejected.

    The currently implemented solution is:
        - key_name
            - == user_id for new users
            - == email for users created in CB 1.8 and below
        - user_id
            - is used as key_name
            - is immutable independent field
            - holds google.appengine.api.users.get_current_user().user_id()
            - historical convention is to use user_id as foreign key in other
              tables
        - email
            - is an independent field
            - is mutable

    This solution is a bit complex, but provides all of the behaviors of the
    ideal solution. It is 100% backwards compatible and does not require offline
    upgrade step. For example, if student, who registered and unregistered in
    CB 1.8 or below, now re-registers, we will reactivate his original student
    entry thus keeping all prior progress (modulo data-removal policy).

    The largest new side effects is:
        - there may be several users with the same email in one course

    If email uniqueness is desired it needs to be added on separately.

    We automatically execute core CB functional tests under both the old and the
    new key_name logic. This is done in LegacyEMailAsKeyNameTest. The exact
    interplay of key_name/user_id/email is tested in StudentKeyNameTest. We also
    manually ran the entire test suite with _LEGACY_EMAIL_AS_KEY_NAME_ENABLED
    set to True and all test passed, except test_rpc_performance in the class
    tests.functional.modules_i18n_dashboard.SampleCourseLocalizationTest. This
    failure is expected as we have extra datastore lookup in get() by email.

    We did not optimize get() by email RPC performance as this call is used
    rarely. To optimize dual datastore lookup in get_by_user_id() we tried
    memcache and request-scope cache for Student. Request-scoped cache provided
    much better results and this is what we implemented.

    We are confident that core CB components, including peer review system, use
    user_id as foreign key and will continue working with no changes. Any custom
    components that used email as foreign key they will stop working and will
    require modifications and an upgrade step.

    TODO(psimakov):
        - review how email changes propagate between global and per-course
          namespaces

    Good luck!

    """

    enrolled_on = db.DateTimeProperty(auto_now_add=True, indexed=True)
    user_id = _ReadOnlyStringProperty(indexed=True)
    email = _EmailProperty(indexed=True)
    name = db.StringProperty(indexed=False)
    additional_fields = db.TextProperty(indexed=False)
    is_enrolled = db.BooleanProperty(indexed=False)

    # UTC timestamp of when the user last rendered a page that's aware they've
    # enrolled in a course.
    last_seen_on = db.DateTimeProperty(indexed=True)

    # Each of the following is a string representation of a JSON dict.
    scores = db.TextProperty(indexed=False)
    labels = db.StringProperty(indexed=False)

    # Group ID of group in which student is a member; can be None.
    group_id = db.IntegerProperty(indexed=True)

    # In CB 1.8 and below an email was used as a key_name. This is no longer
    # true and a user_id is the key_name. We transparently support legacy
    # Student entity instances that still have email as key_name, but we no
    # longer create new entries. If you need to enable this old behavior set the
    # flag below to True.
    _LEGACY_EMAIL_AS_KEY_NAME_ENABLED = False

    # TODO(mgainer): why is user_id is not here?
    _PROPERTY_EXPORT_BLACKLIST = [
        additional_fields,  # Suppress all additional_fields items.
        # Convenience items if not all additional_fields should be suppressed:
        #'additional_fields.xsrf_token',  # Not PII, but also not useful.
        #'additional_fields.form01',  # User's name on registration form.
        email, name]

    def __init__(self, *args, **kwargs):
        super(Student, self).__init__(*args, **kwargs)
        self._federated_email_cached = False
        self._federated_email_value = None

    @classmethod
    def safe_key(cls, db_key, transform_fn):
        return db.Key.from_path(cls.kind(), transform_fn(db_key.id_or_name()))

    @classmethod
    def _add_new(cls, user_id, email):
        if cls._LEGACY_EMAIL_AS_KEY_NAME_ENABLED:
            return Student(key_name=email, email=email, user_id=user_id)
        else:
            return Student(
                key_name=user_id, email=email.lower(), user_id=user_id)

    def for_export(self, transform_fn):
        """Creates an ExportEntity populated from this entity instance."""
        assert not hasattr(self, 'key_by_user_id')
        model = super(Student, self).for_export(transform_fn)
        model.user_id = transform_fn(self.user_id)
        # Add a version of the key that always uses the user_id for the name
        # component. This can be used to establish relationships between objects
        # where the student key used was created via get_key(). In general,
        # this means clients will join exports on this field, not the field made
        # from safe_key().
        model.key_by_user_id = self.get_key(transform_fn=transform_fn)
        return model

    @property
    def federated_email(self):
        """Gets the federated email address of the student.

        This always returns None unless federated authentication is enabled and
        the federated authentication implementation implements an email
        resolver. See common.users.FederatedEmailResolver.
        """
        if not self._federated_email_cached:
            manager = users.UsersServiceManager.get()
            resolver = manager.get_federated_email_resolver_class()
            assert resolver
            self._federated_email_value = (
                resolver.get(self.user_id) if self.user_id else None)
            self._federated_email_cached = True

        return self._federated_email_value

    @property
    def is_transient(self):
        return False

    @property
    def profile(self):
        return StudentProfileDAO.get_profile_by_user_id(self.user_id)

    def put(self):
        """Do the normal put() and also add the object to cache."""
        StudentCache.remove(self.user_id)
        return super(Student, self).put()

    def delete(self):
        """Do the normal delete() and also remove the object from cache."""
        StudentCache.remove(self.user_id)
        super(Student, self).delete()

    @classmethod
    def add_new_student_for_current_user(
        cls, nick_name, additional_fields, handler, labels=None):
        StudentProfileDAO.add_new_student_for_current_user(
            nick_name, additional_fields, handler, labels)

    @classmethod
    def get_first_by_email(cls, email):
        """Get the first student matching requested email.

        Returns:
            A tuple: (Student, unique). The first value is the first student
            object with requested email. The second value is set to True if only
            exactly one student has this email on record; False otherwise.
        """
        # In the CB 1.8 and below email was the key_name. This is no longer
        # true. To support legacy Student entities do a double look up here:
        # first by the key_name value and then by the email field value.
        student = cls.get_by_key_name(email)
        if student:
            return (student, True)
        students = cls.all().filter(cls.email.name, email).fetch(limit=2)
        if not students:
            return (None, False)
        return (students[0], len(students) == 1)

    @classmethod
    def get_by_user(cls, user):
        return cls.get_by_user_id(user.user_id())

    @classmethod
    def get_enrolled_student_by_user(cls, user):
        """Returns enrolled student or None."""
        student = cls.get_by_user_id(user.user_id())
        if student and student.is_enrolled:
            return student
        return None

    @classmethod
    def is_email_in_use(cls, email):
        """Checks if an email is in use by one of existing student."""
        if cls.all().filter(cls.email.name, email).fetch(limit=1):
            return True
        return False

    @classmethod
    def _get_user_and_student(cls):
        """Loads user and student and asserts both are present."""
        user = users.get_current_user()
        if not user:
            raise Exception('No current user.')
        student = Student.get_by_user(user)
        if not student:
            raise Exception('Student instance corresponding to user_id %s not '
                            'found.' % user.user_id())
        return user, student

    @classmethod
    def rename_current(cls, new_name):
        """Gives student a new name."""
        _, student = cls._get_user_and_student()
        StudentProfileDAO.update(
            student.user_id, student.email, nick_name=new_name)

    @classmethod
    def set_enrollment_status_for_current(cls, is_enrolled):
        """Changes student enrollment status."""
        _, student = cls._get_user_and_student()
        StudentProfileDAO.update(
            student.user_id, student.email, is_enrolled=is_enrolled)

    @classmethod
    def set_labels_for_current(cls, labels):
        """Set labels for tracks on the student."""
        _, student = cls._get_user_and_student()
        StudentProfileDAO.update(
            student.user_id, student.email, labels=labels)

    def get_key(self, transform_fn=None):
        """Gets a version of the key that uses user_id for the key name."""
        if not self.user_id:
            raise Exception('Student instance has no user_id set.')
        user_id = transform_fn(self.user_id) if transform_fn else self.user_id
        return db.Key.from_path(Student.kind(), user_id)

    @classmethod
    def get_by_user_id(cls, user_id):
        """Get object from datastore with the help of cache."""
        return StudentCache.get_by_user_id(user_id)

    @classmethod
    def delete_by_user_id(cls, user_id):
        student = cls.get_by_user_id(user_id)
        if student:
            student.delete()

    def has_same_key_as(self, key):
        """Checks if the key of the student and the given key are equal."""
        return key == self.get_key()

    def get_labels_of_type(self, label_type):
        if not self.labels:
            return set()
        label_ids = LabelDAO.get_set_of_ids_of_type(label_type)
        return set([int(label) for label in
                    common_utils.text_to_list(self.labels)
                    if int(label) in label_ids])

    def update_last_seen_on(self, now=None, value=None):
        """Updates last_seen_on.

        Args:
            now: datetime.datetime.utcnow or None. Injectable for tests only.
            value: datetime.datetime.utcnow or None. Injectable for tests only.
        """
        now = now if now is not None else datetime.datetime.utcnow()
        value = value if value is not None else now

        if self._should_update_last_seen_on(value):
            self.last_seen_on = value
            self.put()
            StudentCache.remove(self.user_id)

    def _should_update_last_seen_on(self, value):
        if self.last_seen_on is None:
            return True

        return (
            (value - self.last_seen_on).total_seconds() >
            STUDENT_LAST_SEEN_ON_UPDATE_SEC)

class TransientStudent(object):
    """A transient student (i.e. a user who hasn't logged in or registered)."""

    @property
    def is_transient(self):
        return True

    @property
    def is_enrolled(self):
        return False

    @property
    def scores(self):
        return {}


class EventEntity(BaseEntity):
    """Generic events.

    Each event has a 'source' that defines a place in a code where the event was
    recorded. Each event has a 'user_id' to represent an actor who triggered
    the event. The event 'data' is a JSON object, the format of which is defined
    elsewhere and depends on the type of the event.

    When extending this class, be sure to register your new class with
    models.data_removal.Registry so that instances can be cleaned up on user
    un-registration.
    """
    recorded_on = db.DateTimeProperty(auto_now_add=True, indexed=True)
    source = db.StringProperty(indexed=False)
    user_id = db.StringProperty(indexed=False)

    # Each of the following is a string representation of a JSON dict.
    data = db.TextProperty(indexed=False)

    # Modules may add functions to this list which will receive notification
    # whenever an event is recorded. The method will be called with the
    # arguments (source, user, data) from record().
    EVENT_LISTENERS = []

    @classmethod
    @db.non_transactional
    def _run_record_hooks(cls, source, user, data_dict):
        for listener in cls.EVENT_LISTENERS:
            try:
                listener(source, user, data_dict)
            except Exception:  # On purpose. pylint: disable=broad-except
                logging.exception(
                    'Event record hook failed: %s, %s, %s',
                    source, user.user_id(), data_dict)

    @classmethod
    def record(cls, source, user, data, user_id=None):
        """Records new event into a datastore."""
        data_dict = transforms.loads(data)
        cls._run_record_hooks(source, user, data_dict)
        data = transforms.dumps(data_dict)

        event = cls()
        event.source = source
        event.user_id = user_id if user_id else user.user_id()
        event.data = data
        event.put()

    def for_export(self, transform_fn):
        model = super(EventEntity, self).for_export(transform_fn)
        model.user_id = transform_fn(self.user_id)
        return model

    def get_user_ids(self):
        # Thus far, events pertain only to one user; no need to look in data.
        return [self.user_id]


class StudentAnswersEntity(BaseEntity):
    """Student answers to the assessments."""

    updated_on = db.DateTimeProperty(indexed=True)

    # Each of the following is a string representation of a JSON dict.
    data = db.TextProperty(indexed=False)

    @classmethod
    def safe_key(cls, db_key, transform_fn):
        return db.Key.from_path(cls.kind(), transform_fn(db_key.id_or_name()))


class StudentPropertyEntity(BaseEntity):
    """A property of a student, keyed by the string STUDENT_ID-PROPERTY_NAME.

    When extending this class, be sure to register your new class with
    models.data_removal.Registry so that instances can be cleaned up on user
    un-registration.  See an example of how to do that at the bottom of this
    file.

    """

    updated_on = db.DateTimeProperty(indexed=True)

    name = db.StringProperty()
    # Each of the following is a string representation of a JSON dict.
    value = db.TextProperty()

    @classmethod
    def _memcache_key(cls, key):
        """Makes a memcache key from primary key."""
        return 'entity:student_property:%s' % key

    @classmethod
    def create_key(cls, student_id, property_name):
        return '%s-%s' % (student_id, property_name)

    @classmethod
    def create(cls, student, property_name):
        return cls(
            key_name=cls.create_key(student.user_id, property_name),
            name=property_name)

    @classmethod
    def safe_key(cls, db_key, transform_fn):
        user_id, name = db_key.name().split('-', 1)
        return db.Key.from_path(
            cls.kind(), '%s-%s' % (transform_fn(user_id), name))

    def put(self):
        """Do the normal put() and also add the object to memcache."""
        result = super(StudentPropertyEntity, self).put()
        MemcacheManager.set(self._memcache_key(self.key().name()), self)
        return result

    def delete(self):
        """Do the normal delete() and also remove the object from memcache."""
        super(StudentPropertyEntity, self).delete()
        MemcacheManager.delete(self._memcache_key(self.key().name()))

    @classmethod
    def get(cls, student, property_name):
        """Loads student property."""
        key = cls.create_key(student.user_id, property_name)
        value = MemcacheManager.get(cls._memcache_key(key))
        if NO_OBJECT == value:
            return None
        if not value:
            value = cls.get_by_key_name(key)
            if value:
                MemcacheManager.set(cls._memcache_key(key), value)
            else:
                MemcacheManager.set(cls._memcache_key(key), NO_OBJECT)
        return value


class BaseJsonDao(object):
    """Base DAO class for entities storing their data in a single JSON blob."""

    class EntityKeyTypeId(object):

        @classmethod
        def get_entity_by_key(cls, entity_class, key):
            return entity_class.get_by_id(int(key))

        @classmethod
        def new_entity(cls, entity_class, unused_key):
            return entity_class()  # ID auto-generated when entity is put().

    class EntityKeyTypeName(object):

        @classmethod
        def get_entity_by_key(cls, entity_class, key):
            return entity_class.get_by_key_name(key)

        @classmethod
        def new_entity(cls, entity_class, key_name):
            return entity_class(key_name=key_name)

    @classmethod
    def _memcache_key(cls, obj_id):
        """Makes a memcache key from datastore id."""
        # Keeping case-sensitivity in kind() because Foo(object) != foo(object).
        return '(entity:%s:%s)' % (cls.ENTITY.kind(), obj_id)

    @classmethod
    def _memcache_all_key(cls):
        """Makes a memcache key for caching get_all()."""
        # Keeping case-sensitivity in kind() because Foo(object) != foo(object).
        return '(entity-get-all:%s)' % cls.ENTITY.kind()

    @classmethod
    def get_all_mapped(cls):
        # try to get from memcache
        entities = MemcacheManager.get(cls._memcache_all_key())
        if entities is not None and entities != NO_OBJECT:
            cls._maybe_apply_post_load_hooks(entities.itervalues())
            return entities

        # get from datastore
        result = {dto.id: dto for dto in cls.get_all_iter()}

        # put into memcache
        result_to_cache = NO_OBJECT
        if result:
            result_to_cache = result
        MemcacheManager.set(cls._memcache_all_key(), result_to_cache)

        cls._maybe_apply_post_load_hooks(result.itervalues())
        return result

    @classmethod
    def get_all(cls):
        return cls.get_all_mapped().values()

    @classmethod
    def get_all_iter(cls):
        """Return a generator that will produce all DTOs of a given type.

        Yields:
          A DTO for each row in the Entity type's table.
        """

        prev_cursor = None
        any_records = True
        while any_records:
            any_records = False
            query = cls.ENTITY.all().with_cursor(prev_cursor)
            for entity in query.run():
                any_records = True
                yield cls.DTO(entity.key().id_or_name(),
                              transforms.loads(entity.data))
            prev_cursor = query.cursor()

    @classmethod
    def _maybe_apply_post_load_hooks(cls, dto_list):
        """Run any post-load processing hooks.

        Modules may insert post-load processing hooks (e.g. for i18n
        translation) into the list POST_LOAD_HOOKS defined on the DAO class.
        If the class has this list and any hook functions are present, they
        are passed the list of DTO's for in-place processing.

        Args:
            dto_list: list of DTO objects
        """
        if hasattr(cls, 'POST_LOAD_HOOKS'):
            for hook in cls.POST_LOAD_HOOKS:
                hook(dto_list)

    @classmethod
    def _maybe_apply_post_save_hooks(cls, dto_and_id_list):
        """Run any post-save processing hooks.

        Modules may insert post-save processing hooks (e.g. for i18n
        translation) into the list POST_SAVE_HOOKS defined on the DAO class.
        If the class has this list and any hook functions are present, they
        are passed the list of DTO's for in-place processing.

        Args:
            dto_and_id_list: list of pairs of (id, DTO) objects
        """
        dto_list = [
            cls.DTO(dto_id, orig_dto.dict)
            for dto_id, orig_dto in dto_and_id_list]
        if hasattr(cls, 'POST_SAVE_HOOKS'):
            common_utils.run_hooks(cls.POST_SAVE_HOOKS, dto_list)

    @classmethod
    def _load_entity(cls, obj_id):
        if not obj_id:
            return None
        memcache_key = cls._memcache_key(obj_id)
        entity = MemcacheManager.get(memcache_key)
        if NO_OBJECT == entity:
            return None
        if not entity:
            entity = cls.ENTITY_KEY_TYPE.get_entity_by_key(cls.ENTITY, obj_id)
            if entity:
                MemcacheManager.set(memcache_key, entity)
            else:
                MemcacheManager.set(memcache_key, NO_OBJECT)
        return entity

    @classmethod
    def load(cls, obj_id):
        entity = cls._load_entity(obj_id)
        if entity:
            dto = cls.DTO(obj_id, transforms.loads(entity.data))
            cls._maybe_apply_post_load_hooks([dto])
            return dto
        else:
            return None

    @classmethod
    @appengine_config.timeandlog('Models.bulk_load')
    def bulk_load(cls, obj_id_list):
        # fetch from memcache
        memcache_keys = [cls._memcache_key(obj_id) for obj_id in obj_id_list]
        memcache_entities = MemcacheManager.get_multi(memcache_keys)

        # fetch missing from datastore
        both_keys = zip(obj_id_list, memcache_keys)
        datastore_keys = [
            obj_id for obj_id, memcache_key in both_keys
            if memcache_key not in memcache_entities]
        if datastore_keys:
            datastore_entities = dict(zip(
                datastore_keys, get([
                    db.Key.from_path(cls.ENTITY.kind(), obj_id)
                    for obj_id in datastore_keys])))
        else:
            datastore_entities = {}

        # weave the results together
        ret = []
        memcache_update = {}
        dtos_for_post_hooks = []
        for obj_id, memcache_key in both_keys:
            entity = datastore_entities.get(obj_id)
            if entity is not None:
                dto = cls.DTO(obj_id, transforms.loads(entity.data))
                ret.append(dto)
                dtos_for_post_hooks.append(dto)
                memcache_update[memcache_key] = entity
            elif memcache_key not in memcache_entities:
                ret.append(None)
                memcache_update[memcache_key] = NO_OBJECT
            else:
                entity = memcache_entities[memcache_key]
                if NO_OBJECT == entity:
                    ret.append(None)
                else:
                    ret.append(cls.DTO(obj_id, transforms.loads(entity.data)))

        # run hooks
        cls._maybe_apply_post_load_hooks(dtos_for_post_hooks)

        # put into memcache
        if datastore_entities:
            MemcacheManager.set_multi(memcache_update)

        return ret

    @classmethod
    def _create_if_necessary(cls, dto):
        entity = cls._load_entity(dto.id)
        if not entity:
            entity = cls.ENTITY_KEY_TYPE.new_entity(cls.ENTITY, dto.id)
        entity.data = transforms.dumps(dto.dict)
        return entity

    @classmethod
    def before_put(cls, dto, entity):
        pass

    @classmethod
    def save(cls, dto):
        entity = cls._create_if_necessary(dto)
        cls.before_put(dto, entity)
        entity.put()
        MemcacheManager.delete(cls._memcache_all_key())
        id_or_name = entity.key().id_or_name()
        MemcacheManager.set(cls._memcache_key(id_or_name), entity)
        cls._maybe_apply_post_save_hooks([(id_or_name, dto)])
        return id_or_name

    @classmethod
    def save_all(cls, dtos):
        """Performs a block persist of a list of DTO's."""
        entities = []
        for dto in dtos:
            entity = cls._create_if_necessary(dto)
            entities.append(entity)
            cls.before_put(dto, entity)

        keys = put(entities)
        MemcacheManager.delete(cls._memcache_all_key())
        for key, entity in zip(keys, entities):
            MemcacheManager.set(cls._memcache_key(key.id_or_name()), entity)

        id_or_name_list = [key.id_or_name() for key in keys]
        cls._maybe_apply_post_save_hooks(zip(id_or_name_list, dtos))
        return id_or_name_list

    @classmethod
    def delete(cls, dto):
        entity = cls._load_entity(dto.id)
        entity.delete()
        MemcacheManager.delete(cls._memcache_all_key())
        MemcacheManager.delete(cls._memcache_key(entity.key().id_or_name()))

    @classmethod
    def clone(cls, dto):
        return cls.DTO(None, copy.deepcopy(dto.dict))


class LastModifiedJsonDao(BaseJsonDao):
    """Base DAO that updates the last_modified field of entities on every save.

    DTOs managed by this DAO must have a settable field last_modified defined.
    """

    @classmethod
    def save(cls, dto):
        dto.last_modified = time.time()
        return super(LastModifiedJsonDao, cls).save(dto)

    @classmethod
    def save_all(cls, dtos):
        for dto in dtos:
            dto.last_modified = time.time()
        return super(LastModifiedJsonDao, cls).save_all(dtos)


class QuestionEntity(BaseEntity):
    """An object representing a top-level question."""
    data = db.TextProperty(indexed=False)


class QuestionDTO(object):
    """DTO for question entities."""
    MULTIPLE_CHOICE = 0
    SHORT_ANSWER = 1

    def __init__(self, the_id, the_dict):
        self.id = the_id
        self.dict = the_dict

    @property
    def type(self):
        return self.dict.get('type')

    @type.setter
    def type(self, value):
        self.dict['type'] = value

    @property
    def description(self):
        return self.dict.get('description') or ''

    @description.setter
    def description(self, value):
        self.dict['description'] = value

    @property
    def last_modified(self):
        return self.dict.get('last_modified') or ''

    @last_modified.setter
    def last_modified(self, value):
        self.dict['last_modified'] = value


class QuestionDAO(LastModifiedJsonDao):
    VERSION = '1.5'
    DTO = QuestionDTO
    ENTITY = QuestionEntity
    ENTITY_KEY_TYPE = BaseJsonDao.EntityKeyTypeId
    # Enable other modules to add post-load transformations
    POST_LOAD_HOOKS = []
    # Enable other modules to add post-save transformations
    POST_SAVE_HOOKS = []

    @classmethod
    def used_by(cls, question_id):
        """Returns the question groups using a question.

        Args:
            question_id: int. Identifier of the question we're testing.

        Returns:
            List of question groups. The list of all question groups that use
            the given question.
        """
        # O(num_question_groups), but deserialization of 1 large group takes
        # ~1ms so practically speaking latency is OK for the admin console.
        matches = []
        for group in QuestionGroupDAO.get_all():
            # Add the group the same amount of times as it contains the question
            matches.extend([group] * (
                [long(x) for x in group.question_ids].count(long(question_id))
            ))

        return matches

    @classmethod
    def create_question(cls, question_dict, question_type):
        question = cls.DTO(None, question_dict)
        question.type = question_type
        return cls.save(question)

    @classmethod
    def get_questions_descriptions(cls):
        return set([q.description for q in cls.get_all()])

    @classmethod
    def validate_unique_description(cls, description):
        if description in cls.get_questions_descriptions():
            raise CollisionError(
                'Non-unique question description: %s' % description)
        return None


class QuestionImporter(object):
    """Helper class for converting ver. 1.2 questoins to ver. 1.3 ones."""

    @classmethod
    def _gen_description(cls, unit, lesson_title, question_number):
        return (
            'Unit "%s", lesson "%s" (question #%s)' % (
                unit.title, lesson_title, question_number))

    @classmethod
    def import_freetext(cls, question, description, task):
        QuestionDAO.validate_unique_description(description)
        try:
            response = question.get('correctAnswerRegex')
            # Regex /.*/ is added as a guard for questions with no answer.
            response = response.value if response else '/.*/'
            return {
                'version': QuestionDAO.VERSION,
                'description': description,
                'question': task,
                'hint': question['showAnswerOutput'],
                'graders': [{
                    'score': 1.0,
                    'matcher': 'regex',
                    'response': response,
                    'feedback': question.get('correctAnswerOutput', '')
                }],
                'defaultFeedback': question.get('incorrectAnswerOutput', '')}
        except KeyError as e:
            raise ValidationError('Invalid question: %s, %s' % (description, e))

    @classmethod
    def import_question(
            cls, question, unit, lesson_title, question_number, task):
        question_type = question['questionType']
        task = ''.join(task)
        description = cls._gen_description(unit, lesson_title, question_number)
        if question_type == 'multiple choice':
            question_dict = cls.import_multiple_choice(
                question, description, task)
            qid = QuestionDAO.create_question(
                question_dict, QuestionDAO.DTO.MULTIPLE_CHOICE)
        elif question_type == 'freetext':
            question_dict = cls.import_freetext(question, description, task)
            qid = QuestionDAO.create_question(
                question_dict, QuestionDTO.SHORT_ANSWER)
        elif question_type == 'multiple choice group':
            question_group_dict = cls.import_multiple_choice_group(
                question, description, unit, lesson_title, question_number,
                task)
            qid = QuestionGroupDAO.create_question_group(question_group_dict)
        else:
            raise ValueError('Unknown question type: %s' % question_type)
        return (qid, common_utils.generate_instance_id())

    @classmethod
    def import_multiple_choice(cls, question, description, task):
        QuestionDAO.validate_unique_description(description)
        task = ''.join(task) if task else ''
        qu_dict = {
            'version': QuestionDAO.VERSION,
            'description': description,
            'question': task,
            'multiple_selections': False,
            'choices': [
                {
                    'text': choice[0],
                    'score': 1.0 if choice[1].value else 0.0,
                    'feedback': choice[2]
                } for choice in question['choices']]}
        # Add optional fields
        if 'defaultFeedback' in question:
            qu_dict['defaultFeedback'] = question['defaultFeedback']
        if 'permute_choices' in question:
            qu_dict['permute_choices'] = question['permute_choices']
        if 'show_answer_when_incorrect' in question:
            qu_dict['show_answer_when_incorrect'] = (
                question['show_answer_when_incorrect'])
        if 'all_or_nothing_grading' in question:
            qu_dict['all_or_nothing_grading'] = (
                question['all_or_nothing_grading'])

        return qu_dict

    @classmethod
    def import_multiple_choice_group(
            cls, group, description, unit, lesson_title, question_number, task):
        """Import a 'multiple choice group' as a question group."""

        QuestionGroupDAO.validate_unique_description(description)
        question_group_dict = {
            'version': QuestionDAO.VERSION,
            'description': description,
            'introduction': task}
        question_list = []
        for index, question in enumerate(group['questionsList']):
            description = (
                'Unit "%s", lesson "%s" (question #%s, part #%s)'
                % (unit.title, lesson_title, question_number, index + 1))
            question_dict = cls.import_multiple_choice_group_question(
                question, description)
            question = QuestionDTO(None, question_dict)
            question.type = QuestionDTO.MULTIPLE_CHOICE
            question_list.append(question)
        qid_list = QuestionDAO.save_all(question_list)
        question_group_dict['items'] = [{
            'question': quid,
            'weight': 1.0} for quid in qid_list]
        return question_group_dict

    @classmethod
    def import_multiple_choice_group_question(cls, orig_question, description):
        """Import the questions from a group as individual questions."""

        QuestionDAO.validate_unique_description(description)
        # TODO(jorr): Handle allCorrectOutput and someCorrectOutput
        correct_index = orig_question['correctIndex']
        multiple_selections = not isinstance(correct_index, int)
        if multiple_selections:
            partial = 1.0 / len(correct_index)
            choices = [{
                'text': text,
                'score': partial if i in correct_index else -1.0
            } for i, text in enumerate(orig_question['choices'])]
        else:
            choices = [{
                'text': text,
                'score': 1.0 if i == correct_index else 0.0
            } for i, text in enumerate(orig_question['choices'])]

        return {
            'version': QuestionDAO.VERSION,
            'description': description,
            'question': orig_question.get('questionHTML') or '',
            'multiple_selections': multiple_selections,
            'choices': choices}

    @classmethod
    def build_short_answer_question_dict(cls, question_html, matcher, response):
        return {
            'version': QuestionDAO.VERSION,
            'question': question_html or '',
            'graders': [{
                'score': 1.0,
                'matcher': matcher,
                'response': response,
            }]
        }

    @classmethod
    def build_multiple_choice_question_dict(cls, question):
        """Assemble the dict for a multiple choice question."""

        question_dict = {
            'version': QuestionDAO.VERSION,
            'question': question.get('questionHTML') or '',
            'multiple_selections': False
        }
        choices = []
        for choice in question.get('choices'):
            if isinstance(choice, basestring):
                text = choice
                score = 0.0
            else:
                text = choice.value
                score = 1.0
            choices.append({
                'text': text,
                'score': score
            })
        question_dict['choices'] = choices
        return question_dict

    @classmethod
    def import_assessment_question(cls, question):
        if 'questionHTML' in question:
            question['questionHTML'] = question['questionHTML'].decode(
                'string-escape')
        # Convert a single question into a QuestioDTO.
        if 'choices' in question:
            q_dict = cls.build_multiple_choice_question_dict(
                question)
            question_type = QuestionDTO.MULTIPLE_CHOICE
        elif 'correctAnswerNumeric' in question:
            q_dict = cls.build_short_answer_question_dict(
                question.get('questionHTML'),
                'numeric',
                question.get('correctAnswerNumeric'))
            question_type = QuestionDTO.SHORT_ANSWER
        elif 'correctAnswerString' in question:
            q_dict = cls.build_short_answer_question_dict(
                question.get('questionHTML'),
                'case_insensitive',
                question.get('correctAnswerString'))
            question_type = QuestionDTO.SHORT_ANSWER
        elif 'correctAnswerRegex' in question:
            q_dict = cls.build_short_answer_question_dict(
                question.get('questionHTML'),
                'regex',
                question.get('correctAnswerRegex').value)
            question_type = QuestionDTO.SHORT_ANSWER
        else:
            raise ValueError('Unknown question type')
        question_dto = QuestionDTO(None, q_dict)
        question_dto.type = question_type
        return question_dto

    @classmethod
    def build_question_dtos(cls, assessment_dict, template, unit, errors):
        """Convert the assessment into a list of QuestionDTO's."""

        descriptions = QuestionDAO.get_questions_descriptions()
        question_dtos = []
        try:
            for i, q in enumerate(assessment_dict['questionsList']):
                description = template % (unit.title, (i + 1))
                if description in descriptions:
                    raise CollisionError(
                        'Non-unique question description: %s' % description)
                question_dto = cls.import_assessment_question(q)
                question_dto.dict['description'] = description
                question_dtos.append(question_dto)
        except CollisionError:
            errors.append(
                    'This assessment has already been imported. Remove '
                    'duplicate questions from the question bank in '
                    'order to re-import: %s.' % description)
            return None
        except Exception as ex:  # pylint: disable=broad-except
            errors.append('Unable to convert: %s' % ex)
            return None
        return question_dtos


class QuestionGroupEntity(BaseEntity):
    """An object representing a question group in the datastore."""
    data = db.TextProperty(indexed=False)


class QuestionGroupDTO(object):
    """Data transfer object for question groups."""

    def __init__(self, the_id, the_dict):
        self.id = the_id
        self.dict = the_dict

    @property
    def description(self):
        return self.dict.get('description') or ''

    @property
    def introduction(self):
        return self.dict.get('introduction') or ''

    @property
    def question_ids(self):
        return [item['question'] for item in self.dict.get('items', [])]

    @property
    def items(self):
        return copy.deepcopy(self.dict.get('items', []))

    def add_question(self, question_id, weight):
        self.dict['items'].append({'question': question_id, 'weight': weight})

    @property
    def last_modified(self):
        return self.dict.get('last_modified') or ''

    @last_modified.setter
    def last_modified(self, value):
        self.dict['last_modified'] = value


class QuestionGroupDAO(LastModifiedJsonDao):
    DTO = QuestionGroupDTO
    ENTITY = QuestionGroupEntity
    ENTITY_KEY_TYPE = BaseJsonDao.EntityKeyTypeId
    # Enable other modules to add post-load transformations
    POST_LOAD_HOOKS = []
    # Enable other modules to add post-save transformations
    POST_SAVE_HOOKS = []

    @classmethod
    def get_question_groups_descriptions(cls):
        return set([g.description for g in cls.get_all()])

    @classmethod
    def create_question_group(cls, question_group_dict):
        question_group = QuestionGroupDTO(None, question_group_dict)
        return cls.save(question_group)

    @classmethod
    def validate_unique_description(cls, description):
        if description in cls.get_question_groups_descriptions():
            raise CollisionError(
                'Non-unique question group description: %s' % description)


class LabelEntity(BaseEntity):
    """A class representing labels that can be applied to Student, Unit, etc."""
    data = db.TextProperty(indexed=False)

    MEMCACHE_KEY = 'labels'
    _PROPERTY_EXPORT_BLACKLIST = []  # No PII in labels.

    def put(self):
        """Save the content to the datastore.

        To support caching the list of all labels, we must invalidate
        the cache on any change to any label.

        Returns:
          Value of entity as modified by put() (i.e., key setting)
        """

        result = super(LabelEntity, self).put()
        MemcacheManager.delete(self.MEMCACHE_KEY)
        return result

    def delete(self):
        """Remove a label from the datastore.

        To support caching the list of all labels, we must invalidate
        the cache on any change to any label.
        """

        super(LabelEntity, self).delete()
        MemcacheManager.delete(self.MEMCACHE_KEY)


class LabelDTO(object):

    LABEL_TYPE_GENERAL = 0
    LABEL_TYPE_COURSE_TRACK = 1
    LABEL_TYPE_LOCALE = 2
    # ... etc.
    # If you are extending CourseBuilder, please consider picking
    # a number at 1,000 or over to avoid any potential conflicts
    # with types added by the CourseBuilder team in future releases.

    # Provide consistent naming and labeling for admin UI elements.
    LabelType = collections.namedtuple(
        'LabelType', ['type', 'name', 'title', 'menu_order'])
    USER_EDITABLE_LABEL_TYPES = [
        LabelType(LABEL_TYPE_GENERAL, 'general', 'General', 0),
        LabelType(LABEL_TYPE_COURSE_TRACK, 'course_track', 'Course Track', 1),
        ]
    SYSTEM_EDITABLE_LABEL_TYPES = [
        LabelType(LABEL_TYPE_LOCALE, 'locale', 'Language', 2),
        ]
    LABEL_TYPES = USER_EDITABLE_LABEL_TYPES + SYSTEM_EDITABLE_LABEL_TYPES

    def __init__(self, the_id, the_dict):
        self.id = the_id
        self.dict = the_dict  # UI layer takes care of sanity-checks.

    @property
    def title(self):
        return self.dict.get('title', '')

    @property
    def description(self):
        return self.dict.get('description', '')

    @property
    def type(self):
        return self.dict.get('type', self.LABEL_TYPE_GENERAL)


class LabelManager(caching.RequestScopedSingleton):
    """Class that manages optimized loading of I18N data from datastore."""

    def __init__(self):
        self._key_to_label = None

    def _preload(self):
        self._key_to_label = {}
        for row in LabelDAO.get_all_iter():
            self._key_to_label[row.id] = row

    def _get_all(self):
        if self._key_to_label is None:
            self._preload()
        return self._key_to_label.values()

    @classmethod
    def get_all(cls):
        # pylint: disable=protected-access
        return cls.instance()._get_all()


class LabelDAO(BaseJsonDao):
    DTO = LabelDTO
    ENTITY = LabelEntity
    ENTITY_KEY_TYPE = BaseJsonDao.EntityKeyTypeId

    @classmethod
    def get_all(cls):
        items = LabelManager.get_all()
        order = {lt.type: lt.menu_order for lt in LabelDTO.LABEL_TYPES}
        return sorted(items, key=lambda l: (order[l.type], l.title))

    @classmethod
    def get_all_of_type(cls, label_type):
        return [label for label in cls.get_all()
                if label.type == label_type]

    @classmethod
    def get_set_of_ids_of_type(cls, label_type):
        return set([label.id for label in cls.get_all_of_type(label_type)])

    @classmethod
    def _apply_locale_labels_to_locale(cls, locale, items):
        """Filter out items not matching locale labels and current locale."""
        if locale:
            id_to_label = {}
            for label in LabelDAO.get_all_of_type(
                LabelDTO.LABEL_TYPE_LOCALE):
                id_to_label[int(label.id)] = label
            for item in list(items):
                item_matches = set([int(label_id) for label_id in
                                    common_utils.text_to_list(item.labels)
                                    if int(label_id) in id_to_label.keys()])
                found = False
                for item_match in item_matches:
                    label = id_to_label[item_match]
                    if id_to_label and label and label.title == locale:
                        found = True
                if id_to_label and item_matches and not found:
                    items.remove(item)
        return items

    @classmethod
    def apply_course_track_labels_to_student_labels(
        cls, course, student, items):
        MemcacheManager.begin_readonly()
        try:
            items = cls._apply_labels_to_student_labels(
                LabelDTO.LABEL_TYPE_COURSE_TRACK, student, items)
            if course.get_course_setting('can_student_change_locale'):
                return cls._apply_locale_labels_to_locale(
                    course.app_context.get_current_locale(), items)
            else:
                return cls._apply_labels_to_student_labels(
                    LabelDTO.LABEL_TYPE_LOCALE, student, items)
        finally:
            MemcacheManager.end_readonly()

    @classmethod
    def _apply_labels_to_student_labels(cls, label_type, student, items):
        """Filter out items whose labels don't match those on the student.

        If the student has no labels, all items are taken.
        Similarly, if a item has no labels, it is included.

        Args:
          label_type: a label types to consider.
          student: the logged-in Student matching the user for this request.
          items: a list of item instances, each having 'labels' attribute.
        Returns:
          A list of item instances whose labels match those on the student.
        """
        label_ids = LabelDAO.get_set_of_ids_of_type(label_type)
        if student and not student.is_transient:
            student_matches = student.get_labels_of_type(label_type)
            for item in list(items):
                item_matches = set([int(label_id) for label_id in
                                    common_utils.text_to_list(item.labels)
                                    if int(label_id) in label_ids])
                if (student_matches and item_matches and
                    student_matches.isdisjoint(item_matches)):
                    items.remove(item)
        return items


class StudentPreferencesEntity(BaseEntity):
    """A class representing an individual's preferences for a course.

    Note that here, we are using "Student" in the broadest sense possible:
    some human associated with a course.  This basically means that we want to
    support preferences that are relevant to a student's view of a course, as
    well as a course administrator's preferences.  These will be saved in the
    same object but will be edited in different editors, appropriate to the
    scope of the particular field in the DTO.  For example, show_hooks and
    show_jinja_context are edited in the Dashboard, in
        modules/dashboard/admin_preferences_editor.py
    while locale is set by an Ajax widget in base.html.

    Note that this type is indexed by "name" -- the key is the same as
    that of the user.get_current_user().user_id(), which is a string.
    This type is course-specific, so it must be accessed within a namespaced
    context.
    """
    data = db.TextProperty(indexed=False)

    @classmethod
    def safe_key(cls, db_key, transform_fn):
        return db.Key.from_path(cls.kind(), transform_fn(db_key.name()))


class StudentPreferencesDTO(object):

    def __init__(self, the_id, the_dict):
        self.id = the_id
        self.dict = the_dict

    @property
    def show_hooks(self):
        """Show controls to permit editing of HTML inclusions (hook points).

        On course pages, there are various locations (hook points) at which
        HTML content is inserted.  Turn this setting on to see those locations
        with controls that permit an admin to edit that HTML, and off to see
        the content as a student would.

        Returns:
          True when admin wants to see edit controls, False when he doesn't.
        """
        return self.dict.get('show_hooks', True)

    @show_hooks.setter
    def show_hooks(self, value):
        self.dict['show_hooks'] = value

    @property
    def show_jinja_context(self):
        """Do/don't show dump of Jinja context on bottom of pages."""
        return self.dict.get('show_jinja_context', False)

    @show_jinja_context.setter
    def show_jinja_context(self, value):
        self.dict['show_jinja_context'] = value

    @property
    def locale(self):
        return self.dict.get('locale')

    @locale.setter
    def locale(self, value):
        self.dict['locale'] = value

    # Save the most recently visited course page so we can redirect there
    # when student revisits the (presumably bookmarked) base URL.
    @property
    def last_location(self):
        return self.dict.get('last_location')

    @last_location.setter
    def last_location(self, value):
        self.dict['last_location'] = value


class StudentPreferencesDAO(BaseJsonDao):
    DTO = StudentPreferencesDTO
    ENTITY = StudentPreferencesEntity
    ENTITY_KEY_TYPE = BaseJsonDao.EntityKeyTypeName
    CURRENT_VERSION = '1.0'

    @classmethod
    def load_or_default(cls):
        user = users.get_current_user()
        if not user:
            return None
        user_id = user.user_id()
        prefs = cls.load(user_id)
        if not prefs:
            prefs = StudentPreferencesDTO(
                user_id, {
                    'version': cls.CURRENT_VERSION,
                    'show_hooks': False,
                    'show_jinja_context': False
                })
        return prefs


class RoleEntity(BaseEntity):
    data = db.TextProperty(indexed=False)


class RoleDTO(object):
    """Data transfer object for roles."""

    def __init__(self, the_id, the_dict):
        self.id = the_id
        self.dict = the_dict

    @property
    def name(self):
        return self.dict.get('name', '')

    @property
    def description(self):
        return self.dict.get('description', '')

    @property
    def users(self):
        return self.dict.get('users', [])

    @property
    def permissions(self):
        return self.dict.get('permissions', {})


class RoleDAO(BaseJsonDao):
    DTO = RoleDTO
    ENTITY = RoleEntity
    ENTITY_KEY_TYPE = BaseJsonDao.EntityKeyTypeId


def get_global_handlers():
    return [
        (StudentLifecycleObserver.URL, StudentLifecycleObserver),
    ]

def register_for_data_removal():
    data_removal.Registry.register_sitewide_indexed_by_user_id_remover(
        StudentProfileDAO.delete_profile_by_user_id)
    removers = [
        Student.delete_by_user_id,
        StudentAnswersEntity.delete_by_key,
        StudentPropertyEntity.delete_by_user_id_prefix,
        StudentPreferencesEntity.delete_by_key,
    ]
    for remover in removers:
        data_removal.Registry.register_indexed_by_user_id_remover(remover)
    data_removal.Registry.register_unindexed_entity_class(EventEntity)
