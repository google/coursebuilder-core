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

"""Utilities for dashboard module.  Separated here to break include loops."""

__author__ = 'Mike Gainer (mgainer@google.com)'

import os

import appengine_config

RESOURCES_PATH = '/modules/dashboard/resources'
RESOURCES_DIR = os.path.join(appengine_config.BUNDLE_ROOT,
                             RESOURCES_PATH.lstrip('/'))


def build_assets_url(tab_name):
    return '/dashboard?action=assets&tab=%s' % tab_name
