# Copyright 2014 Google Inc. All Rights Reserved.
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

"""Helper classes to implement caching."""

__author__ = 'Pavel Simakov (psimakov@google.com)'


import collections
import datetime
import logging
import sys
import threading
import unittest

import appengine_config
from models.counters import PerfCounter


def iter_all(query, batch_size=100):
    """Yields query results iterator. Proven method for large datasets."""
    prev_cursor = None
    any_records = True
    while any_records:
        any_records = False
        query = query.with_cursor(prev_cursor)
        for entity in query.run(batch_size=batch_size):
            any_records = True
            yield entity
        prev_cursor = query.cursor()


class AbstractScopedSingleton(object):
    """A singleton object bound to and managed by a container.

    This singleton stores its instance inside the container. When container is
    wiped, the singleton instance is garbage collected and destroyed. You can
    use a dict as a container and then wipe it yourself. You can use
    threading.local as a container and it will be wiped automatically when
    thread exits.
    """

    CONTAINER = None

    @classmethod
    def _instances(cls):
        assert cls.CONTAINER is not None
        if 'instances' not in cls.CONTAINER:
            cls.CONTAINER['instances'] = {}
        return cls.CONTAINER['instances']

    @classmethod
    def instance(cls, *args, **kwargs):
        """Creates new or returns existing instance of the object."""
        # pylint: disable=protected-access
        _instance = cls._instances().get(cls)
        if not _instance:
            try:
                _instance = cls(*args, **kwargs)
            except:
                logging.exception(
                    'Failed to instantiate %s: %s, %s', cls, args, kwargs)
                raise
            appengine_config.log_appstats_event('%s.create' % cls.__name__, {})
            _instance._init_args = (args, kwargs)
            cls._instances()[cls] = _instance
        else:
            _before = _instance._init_args
            _now = (args, kwargs)
            if _now != _before:
                raise AssertionError(
                    'Singleton initiated with %s already exists. '
                    'Failed to re-initialize it with %s.' % (_before, _now))
        return _instance

    @classmethod
    def clear_all(cls):
        """Clear all active instances."""
        if cls._instances():
            for _instance in list(cls._instances().values()):
                _instance.clear()
            del cls.CONTAINER['instances']

    @classmethod
    def clear_instance(cls):
        """Destroys the instance of this cls."""
        appengine_config.log_appstats_event(
            '%s.destroy' % cls.__name__, {})
        _instance = cls._instances().get(cls)
        if _instance:
            del cls._instances()[cls]

    def clear(self):
        """Destroys this object and its content."""
        appengine_config.log_appstats_event(
            '%s.destroy' % self.__class__.__name__, {})
        _instance = self._instances().get(self.__class__)
        if _instance:
            del self._instances()[self.__class__]

_process_scoped_singleton = {}
_request_scoped_singleton = threading.local()


class ProcessScopedSingleton(AbstractScopedSingleton):
    """A singleton object bound to the process."""

    CONTAINER = _process_scoped_singleton


class RequestScopedSingleton(AbstractScopedSingleton):
    """A singleton object bound to the request scope."""

    CONTAINER = _request_scoped_singleton.__dict__


class LRUCache(object):
    """A dict that supports capped size and LRU eviction of items."""

    def __init__(
        self, max_item_count=None,
        max_size_bytes=None, max_item_size_bytes=None):
        assert max_item_count or max_size_bytes
        if max_item_count:
            assert max_item_count > 0
        if max_size_bytes:
            assert max_size_bytes > 0
        self.total_size = 0
        self.max_item_count = max_item_count
        self.max_size_bytes = max_size_bytes
        self.max_item_size_bytes = max_item_size_bytes
        self.items = collections.OrderedDict([])

    def get_entry_size(self, key, value):
        """Computes item size. Override and compute properly for your items."""
        return sys.getsizeof(key) + sys.getsizeof(value)

    def _compute_current_size(self):
        total = 0
        for key, item in self.items.iteritems():
            total += sys.getsizeof(key) + self.get_item_size(item)
        return total

    def _allocate_space(self, key, value):
        """Remove items in FIFO order until size constraints are met."""
        entry_size = self.get_entry_size(key, value)
        if self.max_item_size_bytes and entry_size > self.max_item_size_bytes:
            return False
        while True:
            over_count = False
            over_size = False
            if self.max_item_count:
                over_count = len(self.items) >= self.max_item_count
            if self.max_size_bytes:
                over_size = self.total_size + entry_size >= self.max_size_bytes
            if not (over_count or over_size):
                if self.max_size_bytes:
                    self.total_size += entry_size
                    assert self.total_size < self.max_size_bytes
                return True
            if self.items:
                _key, _value = self.items.popitem(last=False)
                if self.max_size_bytes:
                    self.total_size -= self.get_entry_size(_key, _value)
                    assert self.total_size >= 0
            else:
                break
        return False

    def _record_access(self, key):
        """Pop and re-add the item."""
        item = self.items.pop(key)
        self.items[key] = item

    def contains(self, key):
        """Checks if item is contained without accessing it."""
        assert key
        return key in self.items

    def put(self, key, value):
        assert key
        if self._allocate_space(key, value):
            self.items[key] = value
            return True
        return False

    def get(self, key):
        """Accessing item makes it less likely to be evicted."""
        assert key
        if key in self.items:
            self._record_access(key)
            return True, self.items[key]
        return False, None

    def delete(self, key):
        assert key
        if key in self.items:
            del self.items[key]
            return True
        return False


class NoopCacheConnection(object):
    """Connection to no-op cache that provides no caching."""

    def put(self, *unused_args, **unused_kwargs):
        return None

    def get(self, *unused_args, **unused_kwargs):
        return False, None

    def delete(self, *unused_args, **unused_kwargs):
        return None


class AbstractCacheEntry(object):
    """Object representation while in cache."""

    # we don't track deletions; deleted item will hang around this long
    CACHE_ENTRY_TTL_SEC = 5 * 60

    @classmethod
    def internalize(cls, unused_key, *args, **kwargs):
        """Converts incoming objects into cache entry object."""
        return (args, kwargs)

    @classmethod
    def externalize(cls, unused_key, *args, **kwargs):
        """Converts cache entry into external object."""
        return (args, kwargs)

    def has_expired(self):
        age = (datetime.datetime.utcnow() - self.created_on).total_seconds()
        return age > self.CACHE_ENTRY_TTL_SEC

    def is_up_to_date(self, unused_key, unused_update):
        """Compare entry and the update object to decide if entry is fresh."""
        raise NotImplementedError()

    def updated_on(self):
        """Return last update time for entity."""
        raise NotImplementedError()


class AbstractCacheConnection(object):

    PERSISTENT_ENTITY = None
    CACHE_ENTRY = None

    @classmethod
    def init_counters(cls):
        name = cls.__name__
        cls.CACHE_RESYNC = PerfCounter(
            'gcb-models-%s-cache-resync' % name,
            'A number of times an vfs cache was updated.')
        cls.CACHE_PUT = PerfCounter(
            'gcb-models-%s-cache-put' % name,
            'A number of times an object was put into cache.')
        cls.CACHE_GET = PerfCounter(
            'gcb-models-%s-cache-get' % name,
            'A number of times an object was pulled from cache.')
        cls.CACHE_DELETE = PerfCounter(
            'gcb-models-%s-cache-delete' % name,
            'A number of times an object was deleted from cache.')
        cls.CACHE_HIT = PerfCounter(
            'gcb-models-%s-cache-hit' % name,
            'A number of times an object was found cache.')
        cls.CACHE_HIT_NONE = PerfCounter(
            'gcb-models-%s-cache-hit-none' % name,
            'A number of times an object was found cache, but it was None.')
        cls.CACHE_MISS = PerfCounter(
            'gcb-models-%s-cache-miss' % name,
            'A number of times an object was not found in the cache.')
        cls.CACHE_NOT_FOUND = PerfCounter(
            'gcb-models-%s-cache-not-found' % name,
            'A number of times an object was requested, but was not found in '
            'the cache or underlying provider.')
        cls.CACHE_UPDATE_COUNT = PerfCounter(
            'gcb-models-%s-cache-update-count' % name,
            'A number of update objects received.')
        cls.CACHE_EVICT = PerfCounter(
            'gcb-models-%s-cache-evict' % name,
            'A number of times an object was evicted from cache because it was '
            'changed.')
        cls.CACHE_EXPIRE = PerfCounter(
            'gcb-models-%s-cache-expire' % name,
            'A number of times an object has expired from cache because it was '
            'too old.')

    @classmethod
    def make_key_prefix(cls, ns):
        return '%s:%s' % (cls.__name__, ns)

    @classmethod
    def make_key(cls, ns, entry_key):
        return '%s:%s' % (cls.make_key_prefix(ns), entry_key)

    @classmethod
    def is_enabled(cls):
        raise NotImplementedError()

    @classmethod
    def new_connection(cls, *args, **kwargs):
        if not cls.is_enabled():
            return NoopCacheConnection()
        conn = cls(*args, **kwargs)
        # pylint: disable=protected-access
        conn.apply_updates(conn._get_incremental_updates())
        return conn

    def __init__(self, namespace):
        """Override this method and properly instantiate self.cache."""
        self.namespace = namespace
        self.cache = None
        appengine_config.log_appstats_event(
            '%s.connect' % self.__class__.__name__, {'namespace': namespace})

    def apply_updates(self, updates):
        """Applies a list of global changes to the local cache."""
        self.CACHE_RESYNC.inc()
        for key, update in updates.iteritems():
            _key = self.make_key(self.namespace, key)
            found, entry = self.cache.get(_key)
            if not found:
                continue
            if entry is None:
                self.CACHE_EVICT.inc()
                self.cache.delete(_key)
                continue
            if not entry.is_up_to_date(key, update):
                self.CACHE_EVICT.inc()
                self.cache.delete(_key)
                continue
            if entry.has_expired():
                self.CACHE_EXPIRE.inc()
                self.cache.delete(_key)
                continue

    def _get_most_recent_updated_on(self):
        """Get the most recent item cached. Datastore deletions are missed..."""
        has_items = False
        max_updated_on = datetime.datetime.fromtimestamp(0)
        prefix = self.make_key_prefix(self.namespace)
        for key, entry in self.cache.items.iteritems():
            if not key.startswith(prefix):
                continue
            has_items = True
            if not entry:
                continue
            updated_on = entry.updated_on()
            if not updated_on:  # old entities may be missing this field
                updated_on = datetime.datetime.fromtimestamp(0)
            if updated_on > max_updated_on:
                max_updated_on = updated_on
        return has_items, max_updated_on

    def get_updates_when_empty(self):
        """Override this method to pre-load cache when it's completely empty."""
        return {}

    def _get_incremental_updates(self):
        """Gets a list of global changes older than the most recent item cached.

        WARNING!!! We fetch the updates since the timestamp of the oldest item
        we have cached so far. This will bring all objects that have changed or
        were created since that time.

        This will NOT bring the notifications about object deletions. Thus cache
        will continue to serve deleted objects until they expire.

        Returns:
          a dict of {key: update} objects that represent recent updates
        """
        has_items, updated_on = self._get_most_recent_updated_on()
        if not has_items:
            return self.get_updates_when_empty()
        q = self.PERSISTENT_ENTITY.all()
        if updated_on:
            q.filter('updated_on > ', updated_on)
        result = {
            entity.key().name(): entity for entity in iter_all(q)}
        self.CACHE_UPDATE_COUNT.inc(len(result.keys()))
        return result

    def put(self, key, *args):
        self.CACHE_PUT.inc()
        self.cache.put(
            self.make_key(self.namespace, key),
            self.CACHE_ENTRY.internalize(key, *args))

    def get(self, key):
        self.CACHE_GET.inc()
        _key = self.make_key(self.namespace, key)
        found, entry = self.cache.get(_key)
        if not found:
            self.CACHE_MISS.inc()
            return False, None
        if not entry:
            self.CACHE_HIT_NONE.inc()
            return True, None
        if entry.has_expired():
            self.CACHE_EXPIRE.inc()
            self.cache.delete(_key)
            return False, None
        self.CACHE_HIT.inc()
        return True, self.CACHE_ENTRY.externalize(key, entry)

    def delete(self, key):
        self.CACHE_DELETE.inc()
        self.cache.delete(self.make_key(self.namespace, key))


class LRUCacheTests(unittest.TestCase):

    def test_ordereddict_works(self):
        _dict = collections.OrderedDict([])
        _dict['a'] = '1'
        _dict['b'] = '2'
        _dict['c'] = '3'
        self.assertEqual(('a', '1'), _dict.popitem(last=False))
        self.assertEqual(('c', '3'), _dict.popitem(last=True))

    def test_initialization(self):
        with self.assertRaises(AssertionError):
            LRUCache()
        with self.assertRaises(AssertionError):
            LRUCache(max_item_count=-1)
        with self.assertRaises(AssertionError):
            LRUCache(max_size_bytes=-1)
        LRUCache(max_item_count=1)
        LRUCache(max_size_bytes=1)

    def test_evict_by_count(self):
        cache = LRUCache(max_item_count=3)
        self.assertTrue(cache.put('a', '1'))
        self.assertTrue(cache.put('b', '2'))
        self.assertTrue(cache.put('c', '3'))
        self.assertTrue(cache.contains('a'))
        self.assertTrue(cache.put('d', '4'))
        self.assertFalse(cache.contains('a'))
        self.assertEquals(cache.get('a'), (False, None))

    def test_evict_by_count_lru(self):
        cache = LRUCache(max_item_count=3)
        self.assertTrue(cache.put('a', '1'))
        self.assertTrue(cache.put('b', '2'))
        self.assertTrue(cache.put('c', '3'))
        self.assertEquals(cache.get('a'), (True, '1'))
        self.assertTrue(cache.put('d', '4'))
        self.assertTrue(cache.contains('a'))
        self.assertFalse(cache.contains('b'))

    def test_evict_by_size(self):
        min_size = sys.getsizeof(LRUCache(max_item_count=1).items)
        item_size = sys.getsizeof('a1')
        cache = LRUCache(max_size_bytes=min_size + 3 * item_size)
        self.assertTrue(cache.put('a', '1'))
        self.assertTrue(cache.put('b', '2'))
        self.assertTrue(cache.put('c', '3'))
        self.assertFalse(cache.put('d', bytearray(1000)))

    def test_evict_by_size_lru(self):
        cache = LRUCache(max_size_bytes=5000)
        self.assertTrue(cache.put('a', bytearray(4500)))
        self.assertTrue(cache.put('b', '2'))
        self.assertTrue(cache.put('c', '3'))
        self.assertTrue(cache.contains('a'))
        self.assertTrue(cache.put('d', bytearray(1000)))
        self.assertFalse(cache.contains('a'))
        self.assertTrue(cache.contains('b'))

    def test_max_item_size(self):
        cache = LRUCache(max_size_bytes=5000, max_item_size_bytes=1000)
        self.assertFalse(cache.put('a', bytearray(4500)))
        self.assertEquals(cache.get('a'), (False, None))
        self.assertTrue(cache.put('a', bytearray(500)))
        found, _ = cache.get('a')
        self.assertTrue(found)


class SingletonTests(unittest.TestCase):

    def test_singleton(self):

        class A(RequestScopedSingleton):

            def __init__(self, data):
                self.data = data

        class B(RequestScopedSingleton):

            def __init__(self, data):
                self.data = data

        # TODO(psimakov): prevent direct instantiation
        A('aaa')
        B('bbb')

        # using instance() creates and returns the same instance
        RequestScopedSingleton.clear_all()
        a = A.instance('bar')
        b = A.instance('bar')
        assert a.data == 'bar'
        assert b.data == 'bar'
        assert a is b

        # re-initialization fails if arguments differ
        RequestScopedSingleton.clear_all()
        a = A.instance('dog')
        try:
            b = A.instance('cat')
            raise Exception('Expected to fail.')
        except AssertionError:
            pass

        # clearing one keep others
        RequestScopedSingleton.clear_all()
        a = A.instance('bar')
        b = B.instance('cat')
        a.clear()
        c = B.instance('cat')
        assert c is b

        # clearing all clears all
        RequestScopedSingleton.clear_all()
        a = A.instance('bar')
        b = B.instance('cat')
        RequestScopedSingleton.clear_all()
        c = A.instance('bar')
        d = B.instance('cat')
        assert a is not c
        assert b is not d


def run_all_unit_tests():
    """Runs all unit tests in this module."""
    suites_list = []
    for test_class in [LRUCacheTests, SingletonTests]:
        suite = unittest.TestLoader().loadTestsFromTestCase(test_class)
        suites_list.append(suite)
    unittest.TextTestRunner().run(unittest.TestSuite(suites_list))


if __name__ == '__main__':
    run_all_unit_tests()
