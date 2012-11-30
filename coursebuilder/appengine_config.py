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
#
# @author: psimakov@google.com (Pavel Simakov)


"""Custom configurations and functions for Google App Engine."""


import os


# this is the official location of this app for computing of all relative paths
BUNDLE_ROOT = os.path.dirname(__file__)


from controllers import sites
from google.appengine.api import namespace_manager


def namespace_manager_default_namespace_for_request():
  """Set a namespace appropriate for this request."""
  return sites.ApplicationContext.getNamespaceName()
