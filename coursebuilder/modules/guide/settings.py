# Copyright 2015 Google Inc. All Rights Reserved.
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

"""Settings for the Guide module."""

__author__ = [
    'davyrisso@google.com (Davy Risso)',
]

from models import config

from modules.guide import messages


GCB_ENABLE_GUIDE_PAGE = config.ConfigProperty(
    'gcb_enable_guide_page', bool, messages.SITE_SETTINGS_GUIDE,
    default_value=True, label='Guide', multiline=False, validator=None)


namespaced_routes = []
