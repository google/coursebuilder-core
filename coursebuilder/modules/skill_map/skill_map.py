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

"""Module to provide skill mapping of Course Builder content."""

__author__ = 'John Orr (jorr@google.com)'

from models import custom_modules


skill_mapping_module = None


def notify_module_enabled():
    pass


def register_module():
    """Registers this module in the registry."""

    global_routes = []
    namespaced_routes = []

    global skill_mapping_module  # pylint: disable=global-statement
    skill_mapping_module = custom_modules.Module(
        'Skill Mapping Module',
        'Provide skill mapping of course content',
        global_routes, namespaced_routes,
        notify_module_enabled=notify_module_enabled)

    return skill_mapping_module
