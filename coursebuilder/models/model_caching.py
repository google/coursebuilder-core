# Copyright 2016 Google Inc. All Rights Reserved.
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

"""Helper classes to simplify common cases of cache implementation."""

__author__ = 'Mike Gainer (mgainer@google.com)'

import collections
import datetime
import logging
import sys

from common import caching
from common import utils
from models import config
from models import counters
from models import transforms

from google.appengine.api import namespace_manager


CacheFactoryEntry = collections.namedtuple(
    'CacheFactoryEntry',
    ['cache_class',
     'cache_entry_class',
     'connection_class',
     'manager_class',
     'config_property',
     'perf_counter_length',
     'perf_counter_size'])


class CacheFactory(object):

    _CACHES = {}

    @classmethod
    def build(cls, name, label, desc, max_size_bytes, ttl_sec, dao_class):
        """Build the family of classes for a process-scoped Entity cache.

        Args:
          name: Name under which cache is registered.  This should be in the
              lower_case_and_underscores naming style
          label: Label for the course-level setting enabling/disabling
              process-level caching for this entity type.
          desc: Description to add to the course-level setting
              enabling/disabling process level caching for this entity type.
          max_size_bytes: Largest size the cache may take on.  If adding
              an item to the cache would make it exceed this size, items
              are LRU'd out until the item fits.
          ttl_sec: Number of seconds after which cached entries are
              considered stale and a (lazy) refresh is performed.
          dao_class: The class of an DAO in the Entity/DTO/DAO scheme
              common for Course Builder data access.  Used for itself
              and also for its references to its matching DTO, Entity
              classes.
        Returns:
          A ResourceCacheFactory entry containing the constellation of
          objects that interoperate to form a cche.
        """

        if name in cls._CACHES:
            return cls._CACHES[name]

        config_property = config.ConfigProperty(
            'gcb_can_use_%s_in_process_cache' % name, bool, desc, label=label,
            default_value=True)

        class EntityCache(caching.ProcessScopedSingleton):
            """This class holds in-process global cache of objects."""

            @classmethod
            def get_cache_len(cls):
                # pylint: disable=protected-access
                return len(cls.instance()._cache.items.keys())

            @classmethod
            def get_cache_size(cls):
                 # pylint: disable=protected-access
                return cls.instance()._cache.total_size

            def __init__(self):
                self._cache = caching.LRUCache(max_size_bytes=max_size_bytes)
                self._cache.get_entry_size = self._get_entry_size

            def _get_entry_size(self, key, value):
                if not value:
                    return 0
                return sys.getsizeof(key) + sys.getsizeof(value)

            @property
            def cache(self):
                return self._cache

        class CacheEntry(caching.AbstractCacheEntry):
            """Cache entry containing an entity."""

            def __init__(self, entity):
                self.entity = entity
                self.created_on = datetime.datetime.utcnow()

            def getsizeof(self):
                return (
                    dao_class.ENTITY.getsizeof(self.entity) +
                    sys.getsizeof(self.created_on))

            def has_expired(self):
                age = (datetime.datetime.utcnow() -
                       self.created_on).total_seconds()
                return age > ttl_sec

            def is_up_to_date(self, key, update):
                if update and self.entity:
                    return update.updated_on == self.entity.updated_on
                return not update and not self.entity

            def updated_on(self):
                if self.entity:
                    return self.entity.updated_on
                return None

            @classmethod
            def externalize(cls, key, entry):
                entity = entry.entity
                if not entity:
                    return None
                return dao_class.DTO(
                    entity.key().id_or_name(),
                    transforms.loads(entity.data))

            @classmethod
            def internalize(cls, key, entity):
                return cls(entity)

        class CacheConnection(caching.AbstractCacheConnection):

            PERSISTENT_ENTITY = dao_class.ENTITY
            CACHE_ENTRY = CacheEntry

            @classmethod
            def init_counters(cls):
                caching.AbstractCacheConnection.init_counters()

            @classmethod
            def is_enabled(cls):
                return config_property.value

            def __init__(self, namespace):
                caching.AbstractCacheConnection.__init__(self, namespace)
                self.cache = EntityCache.instance().cache

            def get_updates_when_empty(self):
                """Load in all ResourceBundles when cache is empty."""
                q = self.PERSISTENT_ENTITY.all()
                for entity in caching.iter_all(q):
                    self.put(entity.key().name(), entity)
                    self.CACHE_UPDATE_COUNT.inc()

                # we don't have any updates to apply; all items are new
                return {}

        class ConnectionManager(caching.RequestScopedSingleton):
            """Class that provides access to in-process Entity cache.

            This class only supports get() and does not intercept
            put() or delete() and is unaware of changes to
            Entities made in this very process.  When
            entites change, the changes will be picked up
            when new instance of this class is created. If you are
            watching perfomance counters, you will see EVICT and
            EXPIRE being incremented, but not DELETE or PUT.
            """

            def __init__(self):
                # Keep a separate CacheConnection for each namespace that
                # makes a get() request.
                self._conns = {}

            def _conn(self, ns):
                connected = self._conns.get(ns)
                if not connected:
                    logging.debug(
                        'CONNECTING a CacheConnection for namespace "%s",', ns)
                    connected = CacheConnection.new_connection(ns)
                    self._conns[ns] = connected
                return connected

            @classmethod
            def _ns(cls, app_context):
                if app_context:
                    return app_context.get_namespace_name()
                return namespace_manager.get_namespace()

            def _get(self, key, namespace):
                found, stream = self._conn(namespace).get(key)
                if found and stream:
                    return stream
                with utils.Namespace(namespace):
                    entity = dao_class.ENTITY_KEY_TYPE.get_entity_by_key(
                        dao_class.ENTITY, str(key))
                if entity:
                    self._conn(namespace).put(key, entity)
                    return dao_class.DTO(
                        entity.key().id_or_name(),
                        transforms.loads(entity.data))
                self._conn(namespace).CACHE_NOT_FOUND.inc()
                self._conn(namespace).put(key, None)
                return None

            def _get_multi(self, keys, namespace):
                return [self._get(key, namespace) for key in keys]

            @classmethod
            def get(cls, key, app_context=None):
                # pylint: disable=protected-access
                return cls.instance()._get(key, cls._ns(app_context))

            @classmethod
            def get_multi(cls, keys, app_context=None):
                # pylint: disable=protected-access
                return cls.instance()._get_multi(keys, cls._ns(app_context))

        cache_len = counters.PerfCounter(
            'gcb-models-%sCacheConnection-cache-len' %
            dao_class.ENTITY.__name__,
            'Total number of items in the cache')
        cache_len.poll_value = EntityCache.get_cache_len

        cache_size = counters.PerfCounter(
            'gcb-models-%sCacheConnection-cache-bytes' %
            dao_class.ENTITY.__name__,
            'Total number of bytes in the cache.')
        cache_size.poll_value = EntityCache.get_cache_size

        CacheConnection.init_counters()

        entry = CacheFactoryEntry(
            EntityCache, CacheEntry, CacheConnection, ConnectionManager,
            config_property, cache_len, cache_size)
        cls._CACHES[name] = entry
        return entry

    @classmethod
    def get_cache_instance(cls, name):
        if name not in cls._CACHES:
            return None
        return cls._CACHES[name].cache_class.instance()

    @classmethod
    def get_manager_class(cls, name):
        if name not in cls._CACHES:
            return None
        return cls._CACHES[name].manager_class

    @classmethod
    def all_instances(cls):
        return [cls.get_cache_instance(name) for name in cls._CACHES]
