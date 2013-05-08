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

# Third-party library zip files.
THIRD_PARTY_LIBS = [
    'babel-0.9.6.zip', 'gaepytz-2011h.zip', 'pyparsing-1.5.7.zip',
    'html5lib-0.95.zip']


def gcb_force_default_encoding(encoding):
    """Force default encoding to a specific value."""

    # Eclipse silently sets default encoding to 'utf-8', while GAE forces
    # 'ascii'. We need to control this directly for consistency.
    if not sys.getdefaultencoding() == encoding:
        reload(sys)
        sys.setdefaultencoding(encoding)


def gcb_init_third_party():
    """Add all third party libraries to system path."""
    for lib in THIRD_PARTY_LIBS:
        thirdparty_lib = os.path.join(BUNDLE_ROOT, 'lib/%s' % lib)
        if not os.path.exists(thirdparty_lib):
            raise Exception('Library does not exist: %s' % thirdparty_lib)
        sys.path.insert(0, thirdparty_lib)


gcb_init_third_party()
