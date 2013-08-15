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
from common import jinja_utils
import jinja2
from entities import BaseEntity
from models import MemcacheManager
from google.appengine.api import namespace_manager
from google.appengine.ext import db


# We want to use memcache for both objects that exist and do not exist in the
# datastore. If object exists we cache its instance, if object does not exist
# we cache this object below.
NO_OBJECT = {}


class AbstractFileSystem(object):
    """A generic file system interface that forwards to an implementation."""

    def __init__(self, impl):
        self._impl = impl

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

    def isfile(self, filename):
        """Checks if file exists, similar to os.path.isfile(...)."""
        return self._impl.isfile(filename)

    def open(self, filename):
        """Returns a stream with the file content, similar to open(...)."""
        return self._impl.get(filename)

    def get(self, filename):
        """Returns bytes with the file content, but no metadata."""
        return self._impl.get(filename).read()

    def put(self, filename, stream, **kwargs):
        """Replaces the contents of the file with the bytes in the stream."""
        self._impl.put(filename, stream, **kwargs)

    def delete(self, filename):
        """Deletes a file and metadata associated with it."""
        self._impl.delete(filename)

    def list(self, dir_name):
        """Lists all files in a directory."""
        return self._impl.list(dir_name)

    def get_jinja_environ(self, dir_names):
        """Configures jinja environment loaders for this file system."""
        return self._impl.get_jinja_environ(dir_names)

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
        return open(self._logical_to_physical(filename), 'rb')

    def put(self, unused_filename, unused_stream):
        raise Exception('Not implemented.')

    def delete(self, unused_filename):
        raise Exception('Not implemented.')

    def list(self, root_dir):
        """Lists all files in a directory."""
        files = []
        for dirname, unused_dirnames, filenames in os.walk(
                self._logical_to_physical(root_dir)):
            for filename in filenames:
                files.append(
                    self._physical_to_logical(os.path.join(dirname, filename)))
        return sorted(files)

    def get_jinja_environ(self, dir_names):
        """Configure the environment for Jinja templates."""
        physical_dir_names = []
        for dir_name in dir_names:
            physical_dir_names.append(self._logical_to_physical(dir_name))

        return jinja_utils.create_jinja_environment(
            loader=jinja2.FileSystemLoader(physical_dir_names))

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
            if self._fs.isfile(filename):
                return self._fs.get(
                    filename).read().decode('utf-8'), filename, True
        raise jinja2.TemplateNotFound(template)

    def list_templates(self):
        all_templates = []
        for dir_name in self._dir_names:
            all_templates += self._fs.list(dir_name)
        return all_templates


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

        # We cache files loaded via inherited fs; make sure they don't change.
        if inherits_from and not isinstance(
                inherits_from, LocalReadOnlyFileSystem):
            raise Exception('Can only inherit from LocalReadOnlyFileSystem.')

        self._ns = ns
        self._logical_home_folder = AbstractFileSystem.normpath(
            logical_home_folder)
        self._inherits_from = inherits_from
        self._inheritable_folders = []

        if inheritable_folders:
            for folder in inheritable_folders:
                self._inheritable_folders.append(AbstractFileSystem.normpath(
                    folder))

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
                    return attr(*args, **kwargs)
                finally:
                    namespace_manager.set_namespace(old_namespace)

            return newfunc

        # Don't intercept access to non-method attributes.
        return attr

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
        """Gets a file from a datastore. Raw bytes stream, no encodings."""
        filename = self._logical_to_physical(afilename)

        # Load from cache.
        result = MemcacheManager.get(
            self.make_key(filename), namespace=self._ns)
        if result:
            return result
        if NO_OBJECT == result:
            return None

        # Load from a datastore.
        metadata = FileMetadataEntity.get_by_key_name(filename)
        if metadata:
            data = FileDataEntity.get_by_key_name(filename)
            if data:
                result = FileStreamWrapped(metadata, data.data)
                MemcacheManager.set(
                    self.make_key(filename), result, namespace=self._ns)
                return result

        result = None
        metadata = None

        # Load from parent fs.
        if self._inherits_from and self._can_inherit(filename):
            result = self._inherits_from.get(afilename)

        # Cache result.
        if result:
            result = FileStreamWrapped(metadata, result.read())
            MemcacheManager.set(
                self.make_key(filename), result, namespace=self._ns)
        else:
            MemcacheManager.set(
                self.make_key(filename), NO_OBJECT, namespace=self._ns)

        return result

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
        metadata.updated_on = datetime.datetime.now()
        metadata.is_draft = is_draft

        if not metadata_only:
            # We operate with raw bytes. The consumer must deal with encoding.
            raw_bytes = stream.read()

            metadata.size = len(raw_bytes)

            data = FileDataEntity(key_name=filename)
            data.data = raw_bytes
            data.put()

        metadata.put()

        MemcacheManager.delete(self.make_key(filename), namespace=self._ns)

    @db.transactional(xg=True)
    def delete(self, filename):
        filename = self._logical_to_physical(filename)

        metadata = FileMetadataEntity.get_by_key_name(filename)
        if metadata:
            metadata.delete()
        data = FileDataEntity(key_name=filename)
        if data:
            data.delete()
        MemcacheManager.delete(self.make_key(filename), namespace=self._ns)

    def isfile(self, afilename):
        """Checks file existence by looking up the datastore row."""
        filename = self._logical_to_physical(afilename)

        # Check cache.
        result = MemcacheManager.get(
            self.make_key(filename), namespace=self._ns)
        if result:
            return True
        if NO_OBJECT == result:
            return False

        # Check datastore.
        metadata = FileMetadataEntity.get_by_key_name(filename)
        if metadata:
            return True

        result = False

        # Check with parent fs.
        if self._inherits_from and self._can_inherit(filename):
            result = self._inherits_from.isfile(afilename)

        # Put NO_OBJECT marker into memcache to avoid repeated lookups.
        if not result:
            MemcacheManager.set(
                self.make_key(filename), NO_OBJECT, namespace=self._ns)

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
                result.update(set(self._inherits_from.list(
                    self._physical_to_logical(inheritable_folder))))
        return sorted(list(result))

    def get_jinja_environ(self, dir_names):
        return jinja_utils.create_jinja_environment(
            loader=VirtualFileSystemTemplateLoader(
                self, self._logical_home_folder, dir_names))

    def is_read_write(self):
        return True


def run_all_unit_tests():
    """Runs all unit tests in the project."""


if __name__ == '__main__':
    run_all_unit_tests()
