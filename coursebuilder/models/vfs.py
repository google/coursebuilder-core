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

import os
import jinja2


class AbstractReadOnlyFileSystem(object):
    """A generic ro file system interface that forwards to an implementation."""

    def __init__(self, impl):
        self._impl = impl

    def isfile(self, filename):
        """Checks if file exists, similar to os.path.isfile(...)."""
        return self._impl.isfile(filename)

    def open(self, filename):
        """Returns a stream with the file content, similar to open(...)."""
        return self._impl.open(filename)

    def list(self, dir_name):
        """Lists all files in a directory."""
        return self._impl.list(dir_name)

    def get_jinja_environ(self):
        """Configures jinja environment loaders for this file system."""
        return self._impl.get_jinja_environ()


class LocalReadOnlyFileSystem(object):
    """A ro file system serving only local files."""

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

    def open(self, filename):
        return open(self._logical_to_physical(filename), 'rb')

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


def run_all_unit_tests():
    """Runs all unit tests in the project."""


if __name__ == '__main__':
    run_all_unit_tests()
