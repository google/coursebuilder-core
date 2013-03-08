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
import jinja2
from entities import BaseEntity
from models import MemcacheManager
from google.appengine.api import namespace_manager
from google.appengine.ext import db


class AbstractFileSystem(object):
    """A generic file system interface that forwards to an implementation."""

    def __init__(self, impl):
        self._impl = impl

    @property
    def impl(self):
        return self._impl

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


class LocalReadOnlyFileSystem(object):
    """A read-only file system serving only local files."""

    def __init__(self, logical_home_folder=None, physical_home_folder=None):
        """Create a new instance of the object.

        Args:
            logical_home_folder: A logical home dir of all files (/a/b/c/...).
            physical_home_folder: A physical location on the file system (/x/y).

        Returns:
            A new instance of the object.
        """
        self._logical_home_folder = logical_home_folder
        self._physical_home_folder = physical_home_folder

    def _logical_to_physical(self, filename):
        if not (self._logical_home_folder and self._physical_home_folder):
            return filename
        return os.path.join(
            self._physical_home_folder,
            os.path.relpath(filename, self._logical_home_folder))

    def _physical_to_logical(self, filename):
        if not (self._logical_home_folder and self._physical_home_folder):
            return filename
        return os.path.join(
            self._logical_home_folder,
            os.path.relpath(filename, self._physical_home_folder))

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
        physical_dir_names = []
        for dir_name in dir_names:
            physical_dir_names.append(self._logical_to_physical(dir_name))

        return jinja2.Environment(
            extensions=['jinja2.ext.i18n'],
            loader=jinja2.FileSystemLoader(physical_dir_names))


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

    def __init__(self, fs, logical_home_folder):
        self._fs = fs
        self._logical_home_folder = logical_home_folder

    def get_source(self, unused_environment, template):
        filename = os.path.join(os.path.join(
            self._logical_home_folder, 'views'), template)
        stream = self._fs.get(filename)
        if not stream:
            raise jinja2.TemplateNotFound(template)
        return stream.read().decode('utf-8'), filename, True

    def list_templates(self):
        return self._fs.list(os.path.join(self._logical_home_folder, 'views'))


class DatastoreBackedFileSystem(object):
    """A read-write file system backed by a datastore."""

    @classmethod
    def make_key(cls, filename):
        return 'vfs:dsbfs:%s' % filename

    def __init__(self, ns, logical_home_folder):
        self._ns = ns
        self._logical_home_folder = logical_home_folder

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
        return self._physical_to_logical(filename)

    def _physical_to_logical(self, filename):
        # For now we only support '/' as a physical folder name.
        if self._logical_home_folder == '/':
            return filename
        return '%s%s' % (self._logical_home_folder, filename)

    def get(self, filename):
        """Gets a file from a datastore. Raw bytes stream, no encodings."""
        filename = self._logical_to_physical(filename)

        result = MemcacheManager.get(self.make_key(filename))
        if not result:
            metadata = FileMetadataEntity.get_by_key_name(filename)
            if not metadata:
                return None
            data = FileDataEntity.get_by_key_name(filename)
            if not data:
                return None
            result = FileStreamWrapped(metadata, data.data)
            MemcacheManager.set(self.make_key(filename), result)
        return result

    @db.transactional(xg=True)
    def put(self, filename, stream, is_draft=True):
        """Puts a file stream to a database. Raw bytes stream, no encodings."""
        filename = self._logical_to_physical(filename)

        # We operate with raw bytes. The consumer must deal with encoding.
        raw_bytes = stream.read()

        metadata = FileMetadataEntity.get_by_key_name(filename)
        if not metadata:
            metadata = FileMetadataEntity(key_name=filename)
        metadata.updated_on = datetime.datetime.now()
        metadata.is_draft = is_draft
        metadata.size = len(raw_bytes)

        data = FileDataEntity(key_name=filename)
        data.data = raw_bytes

        metadata.put()
        data.put()

        MemcacheManager.delete(self.make_key(filename))

    @db.transactional(xg=True)
    def delete(self, filename):
        filename = self._logical_to_physical(filename)

        metadata = FileMetadataEntity.get_by_key_name(filename)
        if metadata:
            metadata.delete()
        data = FileDataEntity(key_name=filename)
        if data:
            data.delete()
        MemcacheManager.delete(self.make_key(filename))

    def isfile(self, filename):
        """Checks file existence by looking up the datastore row."""
        filename = self._logical_to_physical(filename)

        result = MemcacheManager.get(self.make_key(filename))
        if result:
            return True
        metadata = FileMetadataEntity.get_by_key_name(filename)
        if metadata:
            return True
        return False

    def list(self, dir_name):
        """Lists all files in a directory by using datastore query."""
        dir_name = self._logical_to_physical(dir_name)

        result = []
        keys = FileMetadataEntity.all(keys_only=True)
        for key in keys.fetch(1000):
            filename = key.name()
            if filename.startswith(dir_name):
                result.append(self._physical_to_logical(filename))
        return sorted(result)

    def get_jinja_environ(self, unused_dir_names):
        return jinja2.Environment(
            extensions=['jinja2.ext.i18n'],
            loader=VirtualFileSystemTemplateLoader(
                self, self._logical_home_folder))


def run_all_unit_tests():
    """Runs all unit tests in the project."""


if __name__ == '__main__':
    run_all_unit_tests()
