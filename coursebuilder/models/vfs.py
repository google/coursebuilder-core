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
import re
import sys
import threading
import unittest

from config import ConfigProperty
from counters import PerfCounter
from entities import BaseEntity
from entities import put as entities_put
import jinja2

from common import caching
from common import jinja_utils
from models import messages

from google.appengine.api import namespace_manager
from google.appengine.ext import db


# all caches must have limits
MAX_GLOBAL_CACHE_SIZE_BYTES = 16 * 1024 * 1024

# max size of each item; no point in storing images for example
MAX_GLOBAL_CACHE_ITEM_SIZE_BYTES = 256 * 1024

# The maximum number of bytes stored per VFS cache shard.
_MAX_VFS_SHARD_SIZE = 1000 * 1000

# Max number of shards for a single VFS cached file.
_MAX_VFS_NUM_SHARDS = 4

# Global memcache controls.
CAN_USE_VFS_IN_PROCESS_CACHE = ConfigProperty(
    'gcb_can_use_vfs_in_process_cache', bool,
    messages.SITE_SETTINGS_CACHE_CONTENT, default_value=True,
    label='Cache Content')


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
    # pylint: disable=unused-argument
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


class ProcessScopedVfsCache(caching.ProcessScopedSingleton):
    """This class holds in-process global cache of VFS objects."""

    @classmethod
    def get_vfs_cache_len(cls):
        # pylint: disable=protected-access
        return len(ProcessScopedVfsCache.instance()._cache.items.keys())

    @classmethod
    def get_vfs_cache_size(cls):
        # pylint: disable=protected-access
        return ProcessScopedVfsCache.instance()._cache.total_size

    def __init__(self):
        self._cache = caching.LRUCache(
            max_size_bytes=MAX_GLOBAL_CACHE_SIZE_BYTES,
            max_item_size_bytes=MAX_GLOBAL_CACHE_ITEM_SIZE_BYTES)
        self._cache.get_entry_size = self._get_entry_size

    def _get_entry_size(self, key, value):
        return sys.getsizeof(key) + value.getsizeof() if value else 0

    @property
    def cache(self):
        return self._cache


VFS_CACHE_LEN = PerfCounter(
    'gcb-models-VfsCacheConnection-cache-len',
    'A total number of items in vfs cache.')
VFS_CACHE_SIZE_BYTES = PerfCounter(
    'gcb-models-VfsCacheConnection-cache-bytes',
    'A total size of items in vfs cache in bytes.')

VFS_CACHE_LEN.poll_value = ProcessScopedVfsCache.get_vfs_cache_len
VFS_CACHE_SIZE_BYTES.poll_value = ProcessScopedVfsCache.get_vfs_cache_size


class CacheFileEntry(caching.AbstractCacheEntry):
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

    def is_up_to_date(self, key, update):
        metadata = update
        if not self.metadata and not metadata:
            return True
        if self.metadata and metadata:
            return (
                metadata.updated_on == self.metadata.updated_on and
                metadata.is_draft == self.metadata.is_draft)
        return False

    def updated_on(self):
        return self.metadata.updated_on

    @classmethod
    def externalize(cls, key, entry):
        return FileStreamWrapped(entry.metadata, entry.body)

    @classmethod
    def internalize(cls, key, metadata, data):
        if metadata and data:
            return CacheFileEntry(key, metadata, data)
        return None


class VfsCacheConnection(caching.AbstractCacheConnection):

    PERSISTENT_ENTITY = FileMetadataEntity
    CACHE_ENTRY = CacheFileEntry

    @classmethod
    def init_counters(cls):
        super(VfsCacheConnection, cls).init_counters()

        cls.CACHE_NO_METADATA = PerfCounter(
            'gcb-models-VfsCacheConnection-cache-no-metadata',
            'A number of times an object was requested, but was not found and '
            'had no metadata.')
        cls.CACHE_INHERITED = PerfCounter(
            'gcb-models-VfsCacheConnection-cache-inherited',
            'A number of times an object was obtained from the inherited vfs.')

    @classmethod
    def is_enabled(cls):
        return CAN_USE_VFS_IN_PROCESS_CACHE.value

    def __init__(self, namespace):
        super(VfsCacheConnection, self).__init__(namespace)
        self.cache = ProcessScopedVfsCache.instance().cache


VfsCacheConnection.init_counters()


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
                            VfsCacheConnection.new_connection(self.ns))
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
        found, stream = self.cache.get(filename)
        if found and stream:
            return stream
        if not found:
            metadata = FileMetadataEntity.get_by_key_name(filename)
            if metadata:
                keys = self._generate_file_key_names(filename, metadata.size)
                data_shards = []
                for data_entity in FileDataEntity.get_by_key_name(keys):
                    data_shards.append(data_entity.data)
                data = ''.join(data_shards)
                # TODO: Note that this will ask the cache to accept
                # potentially very large items.  The caching strategy both
                # for in-memory and Memcache should be revisited to
                # determine how best to address chunking strategies.
                self.cache.put(filename, metadata, data)
                return FileStreamWrapped(metadata, data)

            # lets us cache the (None, None) so next time we asked for this key
            # we fall right into the inherited section without trying to load
            # the metadata/data from the datastore; if a new object with this
            # key is added in the datastore, we will see it in the update list
            VfsCacheConnection.CACHE_NO_METADATA.inc()
            self.cache.put(filename, None, None)

        result = None
        if self._inherits_from and self._can_inherit(filename):
            result = self._inherits_from.get(afilename)
        if result:
            VfsCacheConnection.CACHE_INHERITED.inc()
            return FileStreamWrapped(None, result.read())
        VfsCacheConnection.CACHE_NOT_FOUND.inc()
        return None

    def put(self, filename, stream, is_draft=False, metadata_only=False):
        """Puts a file stream to a database. Raw bytes stream, no encodings."""
        if stream:  # Must be outside the transactional operation
            content = stream.read()
        else:
            content = stream
        self._transactional_put(filename, content, is_draft, metadata_only)

    @db.transactional(xg=True)
    def _transactional_put(
        self, filename, stream, is_draft=False, metadata_only=False):
        self.non_transactional_put(
            filename, stream, is_draft=is_draft, metadata_only=metadata_only)

    @classmethod
    def _generate_file_key_names(cls, filename, size):
        """Generate names for key(s) for DB entities holding file data.

        Files may be larger than 1M, the AppEngine limit.  To work around
        that, just store more entities.  Names of additional entities beyond
        the first are of the form "<filename>:shard:<number>".  This naming
        scheme is "in-band", in the sense that it is possible that a user
        could try to name a file with this format.  However, that format is
        unusual enough that prohibiting it in incoming file names is both
        simple and very unlikely to cause users undue distress.

        Args:
          filename: The base name of the file.
          size: The size of the file, in bytes.
        Returns:
          A list of database entity keys. Files smaller than
          _MAX_VFS_SHARD_SIZE are stored in one entity named by the
          'filename' parameter.  If larger, sufficient additional names of the
          form <filename>/0, <filename>/1, ..... <filename>/N are added.
        """
        if re.search(':shard:[0-9]+$', filename):
            raise ValueError(
                'Files may not end with ":shard:NNN"; this pattern is '
                'reserved for internal use.  Filename "%s" violates this. ' %
                filename)
        if size > _MAX_VFS_SHARD_SIZE * _MAX_VFS_NUM_SHARDS:
            raise ValueError(
                'Cannot store file "%s"; its size of %d bytes is larger than '
                'the maximum supported size of %d.' % (
                    filename, size, _MAX_VFS_SHARD_SIZE * _MAX_VFS_NUM_SHARDS))

        key_names = [filename]
        for segment_id in range(size // _MAX_VFS_SHARD_SIZE):
            key_names.append('%s:shard:%d' % (filename, segment_id))

        return key_names

    def non_transactional_put(
        self, filename, content, is_draft=False, metadata_only=False):
        """Non-transactional put; use only when transactions are impossible."""
        filename = self._logical_to_physical(filename)

        metadata = FileMetadataEntity.get_by_key_name(filename)
        if not metadata:
            metadata = FileMetadataEntity(key_name=filename)
        metadata.updated_on = datetime.datetime.utcnow()
        metadata.is_draft = is_draft

        if not metadata_only:
            # We operate with raw bytes. The consumer must deal with encoding.
            metadata.size = len(content)

            # Chunk the data into entites based on max entity size limits
            # imposed by AppEngine
            key_names = self._generate_file_key_names(filename, metadata.size)
            shard_entities = []
            for index, key_name in enumerate(key_names):
                data = FileDataEntity(key_name=key_name)
                start_offset = index * _MAX_VFS_SHARD_SIZE
                end_offset = (index + 1) * _MAX_VFS_SHARD_SIZE
                data.data = content[start_offset:end_offset]
                shard_entities.append(data)

            entities_put(shard_entities)

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

            # we do call delete here; so this instance will not increment EVICT
            # counter value, but the DELETE value; other instance will not
            # record DELETE, but EVICT when they query for updates
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
        import pickle
        pickle.dumps(caching.NoopCacheConnection())
        pickle.dumps(caching.AbstractCacheConnection(None))
        pickle.dumps(caching.AbstractCacheEntry())

        pickle.dumps(CacheFileEntry('foo.bar', 'file metadata', 'file data'))
        pickle.dumps(DatastoreBackedFileSystem('/', 'ns_test'))
        with self.assertRaises(TypeError):
            pickle.dumps(VfsCacheConnection('ns_test'))

    def _setup_cache_with_one_entry(self, is_draft=True, updated_on=None):
        ProcessScopedVfsCache.clear_all()
        conn = VfsCacheConnection('ns_test')

        meta = FileMetadataEntity()
        meta.is_draft = is_draft
        meta.updated_on = updated_on
        conn.put('sample.txt', meta, 'file data')
        found, stream = conn.get('sample.txt')
        self.assertTrue(found)
        self.assertEquals(stream.metadata.is_draft, meta.is_draft)
        return conn

    def test_expire(self):
        conn = self._setup_cache_with_one_entry()
        entry = conn.cache.items.get(conn.make_key('ns_test', 'sample.txt'))
        self.assertTrue(entry)
        entry.created_on = datetime.datetime.utcnow() - datetime.timedelta(
            0, CacheFileEntry.CACHE_ENTRY_TTL_SEC + 1)
        old_expire_count = VfsCacheConnection.CACHE_EXPIRE.value
        found, stream = conn.get('sample.txt')
        self.assertFalse(found)
        self.assertEquals(stream, None)
        self.assertEquals(
            VfsCacheConnection.CACHE_EXPIRE.value - old_expire_count, 1)

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
            _, stream = conn.get('sample.txt')
            meta = FileMetadataEntity()
            meta.key = _key
            meta.is_draft = stream.metadata.is_draft
            meta.updated_on = stream.metadata.updated_on

            updates = {'sample.txt': meta}
            old_expire_count = VfsCacheConnection.CACHE_EVICT.value
            conn.apply_updates(updates)
            found, _ = conn.get('sample.txt')
            self.assertTrue(found)
            self.assertEquals(
                VfsCacheConnection.CACHE_EVICT.value - old_expire_count, 0)

    def test_empty_updates_dont_evict(self):
        conn = self._setup_cache_with_one_entry()
        updates = {}
        old_expire_count = VfsCacheConnection.CACHE_EVICT.value
        conn.apply_updates(updates)
        found, _ = conn.get('sample.txt')
        self.assertTrue(found)
        self.assertEquals(
            VfsCacheConnection.CACHE_EVICT.value - old_expire_count, 0)

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

            updates = {'sample.txt': meta}
            conn.apply_updates(updates)
            found, _ = conn.get('sample.txt')
            self.assertFalse(found)

    def test_apply_updates_expires_entries(self):
        conn = self._setup_cache_with_one_entry()
        entry = conn.cache.items.get(conn.make_key('ns_test', 'sample.txt'))
        self.assertTrue(entry)
        entry.created_on = datetime.datetime.utcnow() - datetime.timedelta(
            0, CacheFileEntry.CACHE_ENTRY_TTL_SEC + 1)
        updates = {}
        conn.apply_updates(updates)

        old_expire_count = VfsCacheConnection.CACHE_EXPIRE.value
        found, stream = conn.get('sample.txt')
        self.assertFalse(found)
        self.assertEquals(stream, None)
        self.assertEquals(
            VfsCacheConnection.CACHE_EXPIRE.value - old_expire_count, 1)

    def test_no_metadata_and_no_data_is_evicted(self):
        ProcessScopedVfsCache.clear_all()
        conn = VfsCacheConnection('ns_test')

        conn.put('sample.txt', None, None)

        meta = FileMetadataEntity()
        meta.key = 'sample/txt'
        updates = {'sample.txt': meta}
        conn.apply_updates(updates)

        found, stream = conn.get('sample.txt')
        self.assertFalse(found)
        self.assertEquals(stream, None)

    def test_metadata_but_no_data_is_evicted(self):
        ProcessScopedVfsCache.clear_all()
        conn = VfsCacheConnection('ns_test')

        meta = FileMetadataEntity()
        meta.is_draft = True
        meta.updated_on = datetime.datetime.utcnow()
        conn.put('sample.txt', meta, None)

        meta = FileMetadataEntity()
        meta.key = 'sample/txt'
        updates = {'sample.txt': meta}
        conn.apply_updates(updates)

        found, stream = conn.get('sample.txt')
        self.assertFalse(found)
        self.assertEquals(stream, None)


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
