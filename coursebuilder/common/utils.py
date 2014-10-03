# Copyright 2012 Google Inc. All Rights Reserved.
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

"""General utility functions common to all of CourseBuilder."""

__author__ = 'Mike Gainer (mgainer@google.com)'

import collections
import cStringIO
import logging
import random
import re
import string
import sys
import threading
import unittest
import zipfile

import appengine_config
from models.counters import PerfCounter
from google.appengine.api import namespace_manager

BACKWARD_COMPATIBLE_SPLITTER = re.compile(r'[\[\] ,\t\n]+', flags=re.M)
SPLITTER = re.compile(r'[ ,\t\n]+', flags=re.M)
ALPHANUM = string.ascii_letters + string.digits


def text_to_list(text, splitter=SPLITTER):
    if not text:
        return []
    return [item for item in splitter.split(text) if item]


def list_to_text(items):
    if not items:
        return ''
    return ' '.join([unicode(item) for item in items])


def generate_instance_id():
    length = 12
    return ''.join([random.choice(ALPHANUM) for _ in xrange(length)])


def truncate(x, precision=2):
    assert isinstance(precision, int) and precision >= 0
    factor = 10 ** precision
    return int(x * factor) / float(factor)


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


class Namespace(object):
    """Save current namespace and reset it.

    This is inteded to be used in a 'with' statement.  The verbose code:
      old_namespace = namespace_manager.get_namespace()
      try:
          namespace_manager.set_namespace(self._namespace)
          app_specific_stuff()
      finally:
          namespace_manager.set_namespace(old_namespace)

    can be replaced with the much more terse:
      with Namespace(self._namespace):
          app_specific_stuff()

    This style can be used in classes that need to be pickled; the
    @in_namespace function annotation (see below) is arguably visually
    cleaner, but can't be used with pickling.

    The other use-case for this style of acquire/release guard is when
    only portions of a function need to be done within a namespaced
    context.
    """

    def __init__(self, new_namespace):
        self.new_namespace = new_namespace

    def __enter__(self):
        self.old_namespace = namespace_manager.get_namespace()
        namespace_manager.set_namespace(self.new_namespace)
        return self

    def __exit__(self, *unused_exception_info):
        namespace_manager.set_namespace(self.old_namespace)
        return False  # Don't suppress exceptions


def find(predicate, iterable):
    """Find the first matching item in a list, or None if not found.

    This is as a more-usable alternative to filter(), in that it does
    not raise an exception if the item is not found.

    Args:
      predicate: A function taking one argument: an item from the iterable.
      iterable: A list or generator providing items passed to "predicate".
    Returns:
      The first item in "iterable" where "predicate" returns True, or
      None if no item matches.
    """
    for item in iterable:
        if predicate(item):
            return item
    return None


class ZipAwareOpen(object):
    """Provide open() services for third party libraries in .zip files.

    Some libraries that are commonly downloaded and pushed alongside
    CourseBuilder are shipped with data files.  These libraries make the
    assumption that when shipped in a product, they are packaged as plain
    files in a normal directory hierarchy.  Thus, when that library is
    actually packaged in a .zip file, the open() call will fail.  This
    class provides a convenient syntax around functionality that wraps
    calls to the builtin open() (or in the case of AppEngine, the version
    of 'open()' that AppEngine itself provides).  When an attempt is made
    to open a file that is actually packaged within a .zip file, this
    wrapper will intelligently look within the .zip file for that member.

    Only read access is supported.

    No recursion into .zip files within other .zip files is supported.

    Example:
        with common_utils.ZipAwareOpen():
            third_party_module.some_func_that_calls_open()
    """

    THIRD_PARTY_LIB_PATHS = {
        l.file_path: l.full_path for l in appengine_config.THIRD_PARTY_LIBS}

    def zip_aware_open(self, name, *args, **kwargs):
        """Override open() iff opening a file in a library .zip for reading."""

        # First cut: Don't even consider checking .zip files unless the
        # open is for read-only and ".zip" is in the filename.
        mode = args[0] if args else kwargs['mode'] if 'mode' in kwargs else 'r'
        if '.zip' in name and (not mode or mode == 'r' or mode == 'rb'):

            # Only consider .zip files known in the third-party libraries
            # registered in appengine_config.py
            for path in ZipAwareOpen.THIRD_PARTY_LIB_PATHS:

                # Don't use zip-open if the file we are looking for _is_
                # the sought .zip file.  (We are recursed into from the
                # zipfile module when it needs to open a file.)
                if path in name and path != name:
                    zf = zipfile.ZipFile(path, 'r')

                    # Possibly extend simple path to .zip file with relative
                    # path inside .zip file to meaningful contents.
                    name = name.replace(
                        path, ZipAwareOpen.THIRD_PARTY_LIB_PATHS[path])

                    # Strip off on-disk path to .zip file.  This leaves
                    # us with the absolute path within the .zip file.
                    name = name.replace(path, '').lstrip('/')

                    # Return a file-like object containing the data extracted
                    # from the .zip file for the given name.
                    data = zf.read(name)
                    return cStringIO.StringIO(data)

        # All other cases pass through to builtin open().
        return self._real_open(name, *args, **kwargs)

    def __enter__(self):
        """Wrap Python's internal open() with our version."""
        # No particular reason to use __builtins__ in the 'zipfile' module; the
        # set of builtins is shared among all modules implemented in Python.
        self._real_open = sys.modules['zipfile'].__builtins__['open']
        sys.modules['zipfile'].__builtins__['open'] = self.zip_aware_open

    def __exit__(self, *unused_exception_info):
        """Reset open() to be the Python internal version."""
        sys.modules['zipfile'].__builtins__['open'] = self._real_open
        return False  # Don't suppress exceptions.


class AbstractScopedSingleton(object):
    """A singleton object bound to and managed by a container.

    This singleton stores its instance inside the container. When container is
    wiped, the singleton instance is garbage collected and  destroyed. You can
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
        # pylint: disable-msg=protected-access
        _instance = cls._instances().get(cls)
        if not _instance:
            try:
                _instance = cls(*args, **kwargs)
            except:
                logging.exception(
                    'Failed to instantiate %s: %s, %s', cls, args, kwargs)
                raise
            appengine_config.log_appstats_event(
                '%s.create.%s' % (cls.__name__, id(_instance)), {})
            _instance._init_args = (args, kwargs)
            cls._instances()[cls] = _instance
        else:
            _before = _instance._init_args
            _now = (args, kwargs)
            if _now != _before:
                raise AssertionError(
                    'Singleton initiated with %s already exists. '
                    'Failed to re-initialized it with %s.' % (_before, _now))
        return _instance

    @classmethod
    def clear_all(cls):
        """Clear all active instances."""
        if cls._instances():
            for _instance in list(cls._instances().values()):
                _instance.clear()
            del cls.CONTAINER['instances']

    def clear(self):
        """Destroys this object and its content."""
        appengine_config.log_appstats_event(
            '%s.destroy.%s' % (self.__class__.__name__, id(self)), {})
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

    def __init__(self, max_item_count=None, max_size_bytes=None):
        assert max_item_count or max_size_bytes
        if max_item_count:
            assert max_item_count > 0
        if max_size_bytes:
            assert max_size_bytes > 0
        self.total_size = 0
        self.max_item_count = max_item_count
        self.max_size_bytes = max_size_bytes
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
        while True:
            over_count = False
            over_size = False
            if self.max_item_count:
                over_count = len(self.items) >= self.max_item_count
            if self.max_size_bytes:
                entry_size = self.get_entry_size(key, value)
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

    def put(self, unused_filename, unused_metadata, unused_data):
        return None

    def open(self, unused_filename):
        return False, None

    def delete(self, unused_filename):
        return None


class AbstractCacheEntry(object):
    """Object representation while in cache."""

    @classmethod
    def internalize(cls, unused_key, *args, **kwargs):
        """Converts incoming objects into cache entry object."""
        return (args, kwargs)

    @classmethod
    def externalize(cls, unused_key, *args, **kwargs):
        """Converts cache entry into external object."""
        return (args, kwargs)

    def is_up_to_date(self, unused_key, unused_update):
        """Compare entry and the update object to decide if entry is fresh."""
        return False

    def has_expired(self):
        """Override this method and check if this entry has expired."""
        return True


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
        cls.CACHE_MISS = PerfCounter(
            'gcb-models-%s-cache-miss' % name,
            'A number of times an object was not found cache.')
        cls.CACHE_NO_METADATA = PerfCounter(
            'gcb-models-%s-cache-no-metadata' % name,
            'A number of times an object was requested, but was not found and '
            'had no metadata.')
        cls.CACHE_NOT_FOUND = PerfCounter(
            'gcb-models-%s-cache-not-found' % name,
            'A number of times an object was requested, but was not found in '
            'this cache.')
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
        return '%s:%s' % (cls.__class__, ns)

    @classmethod
    def make_key(cls, ns, entry_key):
        return '%s:%s' % (cls.make_key_prefix(ns), entry_key)

    @classmethod
    def is_enabled(cls):
        raise NotImplementedError()

    @classmethod
    def new_connection(cls, fs):
        if not cls.is_enabled():
            return NoopCacheConnection()
        conn = cls(fs)
        conn.apply_updates(conn._get_incremental_updates())
        return conn

    def __init__(self, fs):
        """Override this method and properly instantiate self.cache."""
        self.fs = fs
        self.cache = None

    def apply_updates(self, updates):
        """Applies a list of global changes to the local cache."""
        self.CACHE_RESYNC.inc()
        for key, update in updates.iteritems():
            _key = self.make_key(self.fs.ns, key)
            found, entry = self.cache.get(_key)
            if not found:
                continue
            if not entry.is_up_to_date(key, update):
                self.CACHE_EVICT.inc()
                self.cache.delete(_key)
            elif entry.has_expired():
                self.CACHE_EXPIRE.inc()
                self.cache.delete(_key)

    def _get_most_recent_updated_on(self):
        """Get the most recent item cached. Datastore deletions are missed..."""
        has_items = False
        max_updated_on = None
        prefix = self.make_key_prefix(self.fs.ns)
        for key, entry in self.cache.items.iteritems():
            if not key.startswith(prefix):
                continue
            has_items = True
            if not entry:
                continue
            if max_updated_on is None or (
                entry.metadata.updated_on > max_updated_on):
                max_updated_on = entry.metadata.updated_on
        return has_items, max_updated_on

    def _get_incremental_updates(self):
        """Gets a list of global changes older than the most recent item cached.

        WARNING!!! We fetch the updates since the timestamp of the oldest item
        we have cached so far. This will bring all objects that have changed or
        were created since that time.

        This will NOT bring the notifications about object deletions. Thus cache
        will continue to serve deleted objects until they expire.

        Returns:
          an dict of {key: update} objects that represent recent updates
        """
        has_items, updated_on = self._get_most_recent_updated_on()
        if not has_items:
            return {}
        q = self.PERSISTENT_ENTITY.all()
        if updated_on:
            q.filter('updated_on > ', updated_on)
        return {
            metadata.key().name(): metadata for metadata in iter_all(q)}

    def put(self, key, *args):
        self.CACHE_PUT.inc()
        self.cache.put(
            self.make_key(self.fs.ns, key),
            self.CACHE_ENTRY.internalize(key, *args))

    def open(self, key):
        self.CACHE_GET.inc()
        _key = self.make_key(self.fs.ns, key)
        found, entry = self.cache.get(_key)
        if not found:
            return False, None
        if not entry:
            return True, None
        if entry.has_expired():
            self.CACHE_EXPIRE.inc()
            self.cache.delete(_key)
            return False, None
        return True, self.CACHE_ENTRY.externalize(key, entry)

    def delete(self, key):
        self.CACHE_DELETE.inc()
        self.cache.delete(self.make_key(self.fs.ns, key))


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


def run_all_unit_tests():
    """Runs all unit tests in this module."""
    suites_list = []
    for test_class in [LRUCacheTests]:
        suite = unittest.TestLoader().loadTestsFromTestCase(test_class)
        suites_list.append(suite)
    unittest.TextTestRunner().run(unittest.TestSuite(suites_list))


if __name__ == '__main__':
    run_all_unit_tests()
