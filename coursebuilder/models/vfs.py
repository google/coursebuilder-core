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

"""Virtual file system for managing files locally or in the cloud."""

__author__ = 'Pavel Simakov (psimakov@google.com)'

import datetime
import os
import sys
import threading
import unittest

from config import ConfigProperty
from counters import PerfCounter
from entities import BaseEntity
import jinja2

from common import jinja_utils
from common import utils

from google.appengine.api import namespace_manager
from google.appengine.ext import db


# all caches must have limits
MAX_GLOBAL_CACHE_SIZE_BYTES = 16 * 1024 * 1024

# we don't track deletions; deleted item will hang around this long
CACHE_ENTRY_TTL_SEC = 5 * 60

DB_GET_ALL_BATCH_SIZE = 100

# Global memcache controls.
CAN_USE_VFS_IN_PROCESS_CACHE = ConfigProperty(
    'gcb_can_use_vfs_in_process_cache', bool, (
        'Whether or not to cache content objects. For production this value '
        'should be on to enable maximum performance. For development this '
        'value should be off so you can see your changes to course content '
        'instantaneously.'), default_value=True)


class AbstractFileSystem(object):
    """A generic file system interface that forwards to an implementation."""

    def __init__(self, impl):
        self._impl = impl
        self._readonly = False

    @property
    def impl(self):
        return self._impl

    @classmethod
    def normpath(cls, path):
        """Make Windows and Linux filenames to have the same separator '/'."""
        # Replace '\' into '/' and force Unicode.
        if not path:
            return path
        return u'' + path.replace('\\', '/')

    def begin_readonly(self):
        """Activates caching of resources and prevents mutations."""
        self._assert_not_readonly()
        self._readonly = True

    def end_readonly(self):
        """Deactivates caching of resources and enables mutations."""
        if not self._readonly:
            raise Exception('Not readonly.')
        self._readonly = False

    @property
    def is_readonly(self):
        return self._readonly

    def _assert_not_readonly(self):
        if self._readonly:
            raise Exception(
                'Unable to execute requested operation while readonly.')

    def isfile(self, filename):
        """Checks if file exists, similar to os.path.isfile(...)."""
        return self._impl.isfile(filename)

    def open(self, filename):
        """Returns a stream with the file content, similar to open(...)."""
        return self._impl.get(filename)

    def get(self, filename):
        """Returns bytes with the file content, but no metadata."""
        return self.open(filename).read()

    def put(self, filename, stream, **kwargs):
        """Replaces the contents of the file with the bytes in the stream."""
        self._assert_not_readonly()
        self._impl.put(filename, stream, **kwargs)

    def delete(self, filename):
        """Deletes a file and metadata associated with it."""
        self._assert_not_readonly()
        self._impl.delete(filename)

    def list(self, dir_name, include_inherited=False):
        """Lists all files in a directory."""
        return self._impl.list(dir_name, include_inherited)

    def get_jinja_environ(self, dir_names, autoescape=True):
        """Configures jinja environment loaders for this file system."""
        return self._impl.get_jinja_environ(dir_names, autoescape=autoescape)

    def is_read_write(self):
        return self._impl.is_read_write()

    def is_draft(self, stream):
        if not hasattr(stream, 'metadata'):
            return False
        if not stream.metadata:
            return False
        return stream.metadata.is_draft


class LocalReadOnlyFileSystem(object):
    """A read-only file system serving only local files."""

    def __init__(self, logical_home_folder=None, physical_home_folder=None):
        """Creates a new instance of the disk-backed read-only file system.

        Args:
            logical_home_folder: A logical home dir of all files (/a/b/c/...).
            physical_home_folder: A physical location on the file system (/x/y).

        Returns:
            A new instance of the object.
        """
        self._logical_home_folder = AbstractFileSystem.normpath(
            logical_home_folder)
        self._physical_home_folder = AbstractFileSystem.normpath(
            physical_home_folder)

    def _logical_to_physical(self, filename):
        filename = AbstractFileSystem.normpath(filename)
        if not (self._logical_home_folder and self._physical_home_folder):
            return filename
        filename = os.path.join(
            self._physical_home_folder,
            os.path.relpath(filename, self._logical_home_folder))
        return AbstractFileSystem.normpath(filename)

    def _physical_to_logical(self, filename):
        filename = AbstractFileSystem.normpath(filename)
        if not (self._logical_home_folder and self._physical_home_folder):
            return filename
        filename = os.path.join(
            self._logical_home_folder,
            os.path.relpath(filename, self._physical_home_folder))
        return AbstractFileSystem.normpath(filename)

    def isfile(self, filename):
        return os.path.isfile(self._logical_to_physical(filename))

    def get(self, filename):
        if not self.isfile(filename):
            return None
        return open(self._logical_to_physical(filename), 'rb')

    def put(self, unused_filename, unused_stream):
        raise Exception('Not implemented.')

    def delete(self, unused_filename):
        raise Exception('Not implemented.')

    # Need argument to be named exactly 'include_inherited' to match
    # keyword-parameter names from derived/related classes.
    # pylint: disable-msg=unused-argument
    def list(self, root_dir, include_inherited=False):
        """Lists all files in a directory."""
        files = []
        for dirname, unused_dirnames, filenames in os.walk(
                self._logical_to_physical(root_dir)):
            for filename in filenames:
                files.append(
                    self._physical_to_logical(os.path.join(dirname, filename)))
        return sorted(files)

    def get_jinja_environ(self, dir_names, autoescape=True):
        """Configure the environment for Jinja templates."""
        physical_dir_names = []
        for dir_name in dir_names:
            physical_dir_names.append(self._logical_to_physical(dir_name))

        return jinja_utils.create_jinja_environment(
            loader=jinja2.FileSystemLoader(physical_dir_names),
            autoescape=autoescape)

    def is_read_write(self):
        return False


class FileMetadataEntity(BaseEntity):
    """An entity to represent a file metadata; absolute file name is a key."""
    # TODO(psimakov): do we need 'version' to support concurrent updates
    # TODO(psimakov): can we put 'data' here and still have fast isfile/list?
    created_on = db.DateTimeProperty(auto_now_add=True, indexed=False)
    updated_on = db.DateTimeProperty(indexed=True)

    # Draft file is just as any other file. It's up to the consumer of the file
    # to decide whether to treat draft differently (not to serve it to the
    # public, for example). This class does not care and just stores the bit.
    is_draft = db.BooleanProperty(indexed=False)

    size = db.IntegerProperty(indexed=False)


class FileDataEntity(BaseEntity):
    """An entity to represent file content; absolute file name is a key."""
    data = db.BlobProperty()


class FileStreamWrapped(object):
    """A class that wraps a file stream, but adds extra attributes to it."""

    def __init__(self, metadata, data):
        self._metadata = metadata
        self._data = data

    def read(self):
        """Emulates stream.read(). Returns all bytes and emulates EOF."""
        data = self._data
        self._data = ''
        return data

    @property
    def metadata(self):
        return self._metadata


class StringStream(object):
    """A wrapper to pose a string as a UTF-8 byte stream."""

    def __init__(self, text):
        self._data = unicode.encode(text, 'utf-8')

    def read(self):
        """Emulates stream.read(). Returns all bytes and emulates EOF."""
        data = self._data
        self._data = ''
        return data


def string_to_stream(text):
    return StringStream(text)


def stream_to_string(stream):
    return stream.read().decode('utf-8')


class VirtualFileSystemTemplateLoader(jinja2.BaseLoader):
    """Loader of jinja2 templates from a virtual file system."""

    def __init__(self, fs, logical_home_folder, dir_names):
        self._fs = fs
        self._logical_home_folder = AbstractFileSystem.normpath(
            logical_home_folder)
        self._dir_names = []
        if dir_names:
            for dir_name in dir_names:
                self._dir_names.append(AbstractFileSystem.normpath(dir_name))

    def get_source(self, unused_environment, template):
        for dir_name in self._dir_names:
            filename = AbstractFileSystem.normpath(
                os.path.join(dir_name, template))
            stream = self._fs.open(filename)
            if stream:
                return stream.read().decode('utf-8'), filename, True
        raise jinja2.TemplateNotFound(template)

    def list_templates(self):
        all_templates = []
        for dir_name in self._dir_names:
            all_templates += self._fs.list(dir_name)
        return all_templates


VFS_CACHE_RESYNC = PerfCounter(
    'gcb-models-vfs-cache-resync',
    'A number of times an vfs cache was updated.')
VFS_CACHE_PUT = PerfCounter(
    'gcb-models-vfs-cache-put',
    'A number of times an object was put into vfs cache.')
VFS_CACHE_GET = PerfCounter(
    'gcb-models-vfs-cache-get',
    'A number of times an object was pulled from vfs cache.')
VFS_CACHE_DELETE = PerfCounter(
    'gcb-models-vfs-cache-delete',
    'A number of times an object was deleted from vfs cache.')
VFS_CACHE_HIT = PerfCounter(
    'gcb-models-vfs-cache-hit',
    'A number of times an object was found vfs cache.')
VFS_CACHE_MISS = PerfCounter(
    'gcb-models-vfs-cache-miss',
    'A number of times an object was not found vfs cache.')
VFS_CACHE_NO_METADATA = PerfCounter(
    'gcb-models-vfs-cache-no-metadata',
    'A number of times an object was requested, but was not found and had no '
    'metadata.')
VFS_CACHE_INHERITED = PerfCounter(
    'gcb-models-vfs-cache-inherited',
    'A number of times an object was obtained from the inherited vfs.')
VFS_CACHE_NOT_FOUND = PerfCounter(
    'gcb-models-vfs-cache-not-found',
    'A number of times an object was requested, but was not found in this or '
    'the vfs, inherited from.')
VFS_CACHE_EVICT = PerfCounter(
    'gcb-models-vfs-cache-evict',
    'A number of times an object was evicted from vfs cache because it was '
    'changed.')
VFS_CACHE_EXPIRE = PerfCounter(
    'gcb-models-vfs-cache-expire',
    'A number of times an object has expired from vfs cache because it was '
    'too old.')

VFS_CACHE_LEN = PerfCounter(
    'gcb-models-vfs-cache-len',
    'A total number of items in vfs cache.')
VFS_CACHE_SIZE_BYTES = PerfCounter(
    'gcb-models-vfs-cache-bytes',
    'A total size of items in vfs cache in bytes.')


class ProcessScopedVfsCache(utils.ProcessScopedSingleton):
    """This class holds in-process global cache of VFS objects."""

    @classmethod
    def get_vfs_cache_len(cls):
        return len(ProcessScopedVfsCache.instance()._cache.items.keys())

    @classmethod
    def get_vfs_cache_size(cls):
        return ProcessScopedVfsCache.instance()._cache.total_size

    def __init__(self):
        self._cache = utils.LRUCache(max_size_bytes=MAX_GLOBAL_CACHE_SIZE_BYTES)
        self._cache.get_entry_size = self._get_entry_size

    def _get_entry_size(self, key, value):
        return sys.getsizeof(key) + value.getsizeof() if value else 0

    @property
    def cache(self):
        return self._cache


VFS_CACHE_LEN.poll_value = ProcessScopedVfsCache.get_vfs_cache_len
VFS_CACHE_SIZE_BYTES.poll_value = ProcessScopedVfsCache.get_vfs_cache_size


class CacheFileEntry(object):
    """Cache entry representing a file."""

    def __init__(self, filename, metadata, body):
        self.filename = filename
        self.metadata = metadata
        self.body = body
        self.created_on = datetime.datetime.utcnow()

    def getsizeof(self):
        return (
            sys.getsizeof(self.filename) +
            sys.getsizeof(self.metadata) +
            sys.getsizeof(self.body) +
            sys.getsizeof(self.created_on))

    def has_expired(self):
        age = (datetime.datetime.utcnow() - self.created_on).total_seconds()
        return age > CACHE_ENTRY_TTL_SEC

    def is_up_to_date(self, metadata):
        if not self.metadata and not metadata:
            return True
        if self.metadata and metadata:
            return (
                metadata.updated_on == self.metadata.updated_on and
                metadata.is_draft == self.metadata.is_draft)
        return False


class NoopCacheConnection(object):
    """Connection to no-op cache that provides no caching."""

    def put(self, unused_filename, unused_metadata, unused_data):
        return None

    def open(self, unused_filename):
        return False, None

    def delete(self, unused_filename):
        return None


class VfsCacheConnection(object):

    @classmethod
    def _make_key_prefix(cls, ns):
        return 'vfs:%s' % ns

    @classmethod
    def make_key(cls, ns, filename):
        return '%s:%s' % (cls._make_key_prefix(ns), filename)

    @classmethod
    def new_connection(cls, fs):
        if not CAN_USE_VFS_IN_PROCESS_CACHE.value:
            return NoopCacheConnection()
        conn = cls(fs)
        conn.apply_updates(conn._get_incremental_updates())
        return conn

    def __init__(self, fs):
        self.fs = fs
        self.cache = ProcessScopedVfsCache.instance().cache

    def apply_updates(self, updates):
        """Applies a list of global changes to the local cache."""
        VFS_CACHE_RESYNC.inc()
        for metadata in updates:
            filename = metadata.key().name()
            _key = self.make_key(self.fs.ns, filename)
            found, entry = self.cache.get(_key)
            if not found:
                continue
            if not entry.is_up_to_date(metadata):
                VFS_CACHE_EVICT.inc()
                self.cache.delete(_key)
            elif entry.has_expired():
                VFS_CACHE_EXPIRE.inc()
                self.cache.delete(_key)

    def _get_most_recent_updated_on(self):
        """Get the most recent item cached. Datastore deletions are missed..."""
        has_items = False
        max_updated_on = None
        prefix = self._make_key_prefix(self.fs.ns)
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
        we have cached so far. This will bring metadata of all objects that have
        changed or were created since that time.

        This will NOT bring the notifications about object deletions. Thus cache
        will continue to serve deleted objects until they expire.

        Returns:
          an array of FileMetadataEntity objects that represent recent updates
        """
        has_items, updated_on = self._get_most_recent_updated_on()
        if not has_items:
            return []
        q = FileMetadataEntity.all()
        if updated_on:
            q.filter('updated_on > ', updated_on)
        return [metadata for metadata in self._get_all(q)]

    def _get_all(self, q):
        prev_cursor = None
        any_records = True
        while any_records:
            any_records = False
            query = q.with_cursor(prev_cursor)
            for entity in query.fetch(DB_GET_ALL_BATCH_SIZE):
                any_records = True
                yield entity
            prev_cursor = query.cursor()

    def put(self, filename, metadata, data):
        VFS_CACHE_PUT.inc()
        entry = None
        if metadata and data:
            entry = CacheFileEntry(filename, metadata, data)
        self.cache.put(self.make_key(self.fs.ns, filename), entry)

    def open(self, filename):
        VFS_CACHE_GET.inc()
        _key = self.make_key(self.fs.ns, filename)
        found, entry = self.cache.get(_key)
        if not found:
            return False, None
        if not entry:
            return True, None
        if entry.has_expired():
            VFS_CACHE_EXPIRE.inc()
            self.cache.delete(_key)
            return False, None
        return True, FileStreamWrapped(entry.metadata, entry.body)

    def delete(self, filename):
        VFS_CACHE_DELETE.inc()
        self.cache.delete(self.make_key(self.fs.ns, filename))


class DatastoreBackedFileSystem(object):
    """A read-write file system backed by a datastore."""

    @classmethod
    def make_key(cls, filename):
        return 'vfs:dsbfs:%s' % filename

    def __init__(
        self, ns, logical_home_folder,
        inherits_from=None, inheritable_folders=None):
        """Creates a new instance of the datastore-backed file system.

        Args:
            ns: A datastore namespace to use for storing all data and metadata.
            logical_home_folder: A logical home dir of all files (/a/b/c/...).
            inherits_from: A file system to use for the inheritance.
            inheritable_folders: A list of folders that support inheritance.

        Returns:
            A new instance of the object.

        Raises:
            Exception: if invalid inherits_from is given.
        """

        if inherits_from and not isinstance(
                inherits_from, LocalReadOnlyFileSystem):
            raise Exception('Can only inherit from LocalReadOnlyFileSystem.')

        self._ns = ns
        self._logical_home_folder = AbstractFileSystem.normpath(
            logical_home_folder)
        self._inherits_from = inherits_from
        self._inheritable_folders = []
        self._cache = threading.local()

        if inheritable_folders:
            for folder in inheritable_folders:
                self._inheritable_folders.append(AbstractFileSystem.normpath(
                    folder))

    def __getstate__(self):
        """Remove transient members that can't survive pickling."""
        # TODO(psimakov): we need to properly pickle app_context so vfs is not
        # being serialized at all
        state = self.__dict__.copy()
        if '_cache' in state:
            del state['_cache']
        return state

    def __setstate__(self, state_dict):
        """Set persistent members and re-initialize transient members."""
        self.__dict__ = state_dict
        self._cache = threading.local()

    def __getattribute__(self, name):
        attr = object.__getattribute__(self, name)

        # Don't intercept access to private methods and attributes.
        if name.startswith('_'):
            return attr

        # Do intercept all methods.
        if hasattr(attr, '__call__'):

            def newfunc(*args, **kwargs):
                """Set proper namespace for each method call."""
                old_namespace = namespace_manager.get_namespace()
                try:
                    namespace_manager.set_namespace(self._ns)
                    if not hasattr(self._cache, 'connection'):
                        self._cache.connection = (
                            VfsCacheConnection.new_connection(self))
                    return attr(*args, **kwargs)
                finally:
                    namespace_manager.set_namespace(old_namespace)

            return newfunc

        # Don't intercept access to non-method attributes.
        return attr

    @property
    def ns(self):
        return self._ns

    @property
    def cache(self):
        return self._cache.connection

    def _logical_to_physical(self, filename):
        filename = AbstractFileSystem.normpath(filename)

        # For now we only support '/' as a physical folder name.
        if self._logical_home_folder == '/':
            return filename
        if not filename.startswith(self._logical_home_folder):
            raise Exception(
                'Expected path \'%s\' to start with a prefix \'%s\'.' % (
                    filename, self._logical_home_folder))

        rel_path = filename[len(self._logical_home_folder):]
        if not rel_path.startswith('/'):
            rel_path = '/%s' % rel_path
        return rel_path

    def physical_to_logical(self, filename):
        """Converts an internal filename to and external filename."""

        # This class receives and stores absolute file names. The logical
        # filename is the external file name. The physical filename is an
        # internal filename. This function does the convertions.

        # Let's say you want to store a file named '/assets/img/foo.png'.
        # This would be a physical filename in the VFS. But the put() operation
        # expects an absolute filename from the root of the app installation,
        # i.e. something like '/dev/apps/coursebuilder/assets/img/foo.png',
        # which is called a logical filename. This is a legacy expectation from
        # the days the course was defined as files on the file system.
        #
        # This function will do the conversion you need.

        return self._physical_to_logical(filename)

    def _physical_to_logical(self, filename):
        filename = AbstractFileSystem.normpath(filename)

        # For now we only support '/' as a physical folder name.
        if filename and not filename.startswith('/'):
            filename = '/' + filename
        if self._logical_home_folder == '/':
            return filename
        return '%s%s' % (self._logical_home_folder, filename)

    def _can_inherit(self, filename):
        """Checks if a file can be inherited from a parent file system."""
        for prefix in self._inheritable_folders:
            if filename.startswith(prefix):
                return True
        return False

    def get(self, afilename):
        return self.open(afilename)

    def open(self, afilename):
        """Gets a file from a datastore. Raw bytes stream, no encodings."""
        filename = self._logical_to_physical(afilename)
        found, stream = self.cache.open(filename)
        if found and stream:
            VFS_CACHE_HIT.inc()
            return stream
        if not found:
            metadata = FileMetadataEntity.get_by_key_name(filename)
            if metadata:
                data = FileDataEntity.get_by_key_name(filename)
                if data:
                    VFS_CACHE_MISS.inc()
                    self.cache.put(filename, metadata, data.data)
                    return FileStreamWrapped(metadata, data.data)
            VFS_CACHE_NO_METADATA.inc()
            self.cache.put(filename, None, None)
        result = None
        if self._inherits_from and self._can_inherit(filename):
            result = self._inherits_from.get(afilename)
        if result:
            VFS_CACHE_INHERITED.inc()
            return FileStreamWrapped(None, result.read())
        VFS_CACHE_NOT_FOUND.inc()
        return None

    @db.transactional(xg=True)
    def put(self, filename, stream, is_draft=False, metadata_only=False):
        """Puts a file stream to a database. Raw bytes stream, no encodings."""
        self.non_transactional_put(
            filename, stream, is_draft=is_draft, metadata_only=metadata_only)

    def non_transactional_put(
        self, filename, stream, is_draft=False, metadata_only=False):
        """Non-transactional put; use only when transactions are impossible."""
        filename = self._logical_to_physical(filename)

        metadata = FileMetadataEntity.get_by_key_name(filename)
        if not metadata:
            metadata = FileMetadataEntity(key_name=filename)
        metadata.updated_on = datetime.datetime.utcnow()
        metadata.is_draft = is_draft

        if not metadata_only:
            # We operate with raw bytes. The consumer must deal with encoding.
            raw_bytes = stream.read()

            metadata.size = len(raw_bytes)

            data = FileDataEntity(key_name=filename)
            data.data = raw_bytes
            data.put()

        metadata.put()
        self.cache.delete(filename)

    def put_multi_async(self, filedata_list):
        """Initiate an async put of the given files.

        This method initiates an asynchronous put of a list of file data
        (presented as pairs of the form (filename, data_source)). It is not
        transactional, and does not block, and instead immediately returns a
        callback function. When this function is called it will block until
        the puts are confirmed to have completed. For maximum efficiency it's
        advisable to defer calling the callback until all other request handling
        has completed, but in any event, it MUST be called before the request
        handler can exit successfully.

        Args:
            filedata_list: list. A list of tuples. The first entry of each
                tuple is the file name, the second is a filelike object holding
                the file data.

        Returns:
            callable. Returns a wait-and-finalize function. This function must
            be called at some point before the request handler exists, in order
            to confirm that the puts have succeeded.
        """
        filename_list = []
        data_list = []
        metadata_list = []

        for filename, stream in filedata_list:
            filename = self._logical_to_physical(filename)
            filename_list.append(filename)

            metadata = FileMetadataEntity.get_by_key_name(filename)
            if not metadata:
                metadata = FileMetadataEntity(key_name=filename)
            metadata_list.append(metadata)
            metadata.updated_on = datetime.datetime.utcnow()

            # We operate with raw bytes. The consumer must deal with encoding.
            raw_bytes = stream.read()

            metadata.size = len(raw_bytes)

            data = FileDataEntity(key_name=filename)
            data_list.append(data)
            data.data = raw_bytes

            self.cache.delete(filename)

        data_future = db.put_async(data_list)
        metadata_future = db.put_async(metadata_list)

        def wait_and_finalize():
            data_future.check_success()
            metadata_future.check_success()

        return wait_and_finalize

    @db.transactional(xg=True)
    def delete(self, filename):
        filename = self._logical_to_physical(filename)
        metadata = FileMetadataEntity.get_by_key_name(filename)
        if metadata:
            metadata.delete()
        data = FileDataEntity(key_name=filename)
        if data:
            data.delete()
        self.cache.delete(filename)

    def isfile(self, afilename):
        """Checks file existence by looking up the datastore row."""
        filename = self._logical_to_physical(afilename)
        metadata = FileMetadataEntity.get_by_key_name(filename)
        if metadata:
            return True
        result = False
        if self._inherits_from and self._can_inherit(filename):
            result = self._inherits_from.isfile(afilename)
        return result

    def list(self, dir_name, include_inherited=False):
        """Lists all files in a directory by using datastore query.

        Args:
            dir_name: string. Directory to list contents of.
            include_inherited: boolean. If True, includes all inheritable files
                from the parent filesystem.

        Returns:
            List of string. Lexicographically-sorted unique filenames
            recursively found in dir_name.
        """
        dir_name = self._logical_to_physical(dir_name)
        result = set()
        keys = FileMetadataEntity.all(keys_only=True)
        for key in keys.fetch(1000):
            filename = key.name()
            if filename.startswith(dir_name):
                result.add(self._physical_to_logical(filename))
        if include_inherited and self._inherits_from:
            for inheritable_folder in self._inheritable_folders:
                logical_folder = self._physical_to_logical(inheritable_folder)
                result.update(set(self._inherits_from.list(
                    logical_folder,
                    include_inherited)))
        return sorted(list(result))

    def get_jinja_environ(self, dir_names, autoescape=True):
        return jinja_utils.create_jinja_environment(
            loader=VirtualFileSystemTemplateLoader(
                self, self._logical_home_folder, dir_names),
            autoescape=autoescape)

    def is_read_write(self):
        return True


class VfsTests(unittest.TestCase):

    def test_pickling(self):
        # pylint: disable-msg=g-import-not-at-top
        import pickle
        pickle.dumps(NoopCacheConnection())
        pickle.dumps(CacheFileEntry('foo.bar', 'file metadata', 'file data'))
        pickle.dumps(DatastoreBackedFileSystem('/', 'ns_test'))
        with self.assertRaises(TypeError):
            pickle.dumps(VfsCacheConnection(LocalReadOnlyFileSystem()))

    def _setup_cache_with_one_entry(self, is_draft=True, updated_on=None):
        ProcessScopedVfsCache.clear_all()
        fs = DatastoreBackedFileSystem('ns_test', '/')
        conn = VfsCacheConnection(fs)

        meta = FileMetadataEntity()
        meta.is_draft = is_draft
        meta.updated_on = updated_on
        conn.put('sample.txt', meta, 'file data')
        found, stream = conn.open('sample.txt')
        self.assertTrue(found)
        self.assertEquals(stream.metadata.is_draft, meta.is_draft)
        return conn

    def test_expire(self):
        conn = self._setup_cache_with_one_entry()
        entry = conn.cache.items.get(conn.make_key('ns_test', 'sample.txt'))
        self.assertTrue(entry)
        entry.created_on = datetime.datetime.utcnow() - datetime.timedelta(
            0, CACHE_ENTRY_TTL_SEC + 1)
        old_expire_count = VFS_CACHE_EXPIRE.value
        found, stream = conn.open('sample.txt')
        self.assertFalse(found)
        self.assertEquals(stream, None)
        self.assertEquals(VFS_CACHE_EXPIRE.value - old_expire_count, 1)

    def test_updates_with_no_changes_dont_evict(self):
        class _Key(object):

            def name(self):
                return 'sample.txt'

        def _key():
            return _Key()

        for is_draft, updated_on in [
            (True, None), (True, datetime.datetime.utcnow()),
            (False, None), (False, datetime.datetime.utcnow())]:
            conn = self._setup_cache_with_one_entry(
                is_draft=is_draft, updated_on=updated_on)
            _, stream = conn.open('sample.txt')
            meta = FileMetadataEntity()
            meta.key = _key
            meta.is_draft = stream.metadata.is_draft
            meta.updated_on = stream.metadata.updated_on

            updates = [meta]
            old_expire_count = VFS_CACHE_EVICT.value
            conn.apply_updates(updates)
            found, _ = conn.open('sample.txt')
            self.assertTrue(found)
            self.assertEquals(VFS_CACHE_EVICT.value - old_expire_count, 0)

    def test_empty_updates_dont_evict(self):
        conn = self._setup_cache_with_one_entry()
        updates = []
        old_expire_count = VFS_CACHE_EVICT.value
        conn.apply_updates(updates)
        found, _ = conn.open('sample.txt')
        self.assertTrue(found)
        self.assertEquals(VFS_CACHE_EVICT.value - old_expire_count, 0)

    def test_updates_with_changes_do_evict(self):
        class _Key(object):

            def name(self):
                return 'sample.txt'

        def _key():
            return _Key()

        def set_is_draft(meta, value):
            meta.is_draft = value

        def set_updated_on(meta, value):
            meta.updated_on = value

        conn = self._setup_cache_with_one_entry()

        mutations = [
            (lambda meta: set_is_draft(meta, False)),
            (lambda meta: set_updated_on(meta, datetime.datetime.utcnow()))]

        for mutation in mutations:
            meta = FileMetadataEntity()
            meta.key = _key

            mutation(meta)

            updates = [meta]
            conn.apply_updates(updates)
            found, _ = conn.open('sample.txt')
            self.assertFalse(found)

    def test_apply_updates_expires_entries(self):
        conn = self._setup_cache_with_one_entry()
        entry = conn.cache.items.get(conn.make_key('ns_test', 'sample.txt'))
        self.assertTrue(entry)
        entry.created_on = datetime.datetime.utcnow() - datetime.timedelta(
            0, CACHE_ENTRY_TTL_SEC + 1)
        updates = []
        conn.apply_updates(updates)

        old_expire_count = VFS_CACHE_EXPIRE.value
        found, stream = conn.open('sample.txt')
        self.assertFalse(found)
        self.assertEquals(stream, None)
        self.assertEquals(VFS_CACHE_EXPIRE.value - old_expire_count, 1)


def run_all_unit_tests():
    """Runs all unit tests in this module."""
    suites_list = []
    for test_class in [VfsTests]:
        suite = unittest.TestLoader().loadTestsFromTestCase(test_class)
        suites_list.append(suite)
    result = unittest.TextTestRunner().run(unittest.TestSuite(suites_list))
    if not result.wasSuccessful() or result.errors:
        raise Exception(result)


if __name__ == '__main__':
    run_all_unit_tests()
