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

"""Custom configurations and functions for Google App Engine."""

__author__ = 'psimakov@google.com (Pavel Simakov)'

import os
import sys


# Whether we are running in the production environment.
PRODUCTION_MODE = not os.environ.get(
    'SERVER_SOFTWARE', 'Development').startswith('Development')

# Set this flag to true to enable bulk downloads of Javascript/CSS files in lib
BUNDLE_LIB_FILES = True

# this is the official location of this app for computing of all relative paths
BUNDLE_ROOT = os.path.dirname(__file__)

# make all Windows and Linux paths have the same separator '/'
BUNDLE_ROOT = BUNDLE_ROOT.replace('\\', '/')

# Default namespace name is '' and not None.
DEFAULT_NAMESPACE_NAME = ''


class _Library(object):
    """DDO that represents a Python library contained in a .zip file."""

    def __init__(self, zipfile, relative_path=None):
        self._relative_path = relative_path
        self._zipfile = zipfile

    @property
    def file_path(self):
        """Path to the library's file on disk."""
        return os.path.join(BUNDLE_ROOT, 'lib', self._zipfile)

    @property
    def full_path(self):
        """Full path for imports, containing archive-relative paths if any."""
        path = self.file_path
        if self._relative_path:
            path = os.path.join(path, self._relative_path)
        return path


# Third-party library zip files.
THIRD_PARTY_LIBS = [
    _Library('babel-0.9.6.zip'),
    _Library('html5lib-0.95.zip'),
    _Library('httplib2-0.8.zip', relative_path='httplib2-0.8/python2'),
    _Library('gaepytz-2011h.zip'),
    _Library(
        'google-api-python-client-1.1.zip',
        relative_path='google-api-python-client-1.1'),
    # .zip repackaged from .tar.gz download.
    _Library('mrs-mapreduce-0.9.zip', relative_path='mrs-mapreduce-0.9'),
    # .zip repackaged from .tar.gz download.
    _Library('python-gflags-2.0.zip', relative_path='python-gflags-2.0'),
    _Library('pyparsing-1.5.7.zip'),
]


def gcb_force_default_encoding(encoding):
    """Force default encoding to a specific value."""

    # Eclipse silently sets default encoding to 'utf-8', while GAE forces
    # 'ascii'. We need to control this directly for consistency.
    if sys.getdefaultencoding() != encoding:
        reload(sys)
        sys.setdefaultencoding(encoding)


def gcb_init_third_party():
    """Add all third party libraries to system path."""
    for lib in THIRD_PARTY_LIBS:
        if not os.path.exists(lib.file_path):
            raise Exception('Library does not exist: %s' % lib.file_path)
        sys.path.insert(0, lib.full_path)


gcb_init_third_party()
