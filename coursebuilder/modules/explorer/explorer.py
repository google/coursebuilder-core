# Copyright 2016 Google Inc. All Rights Reserved.
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

"""Course Explorer Module"""

__author__ = [
    'nretallack@google.com (Nick Retallack)',
]

from models import custom_modules
from modules.explorer import constants
from modules.explorer import course_settings
from modules.explorer import handlers
from modules.explorer import graphql
from modules.explorer import settings
from modules.explorer import hooks


def register_module():
    graphql.register()
    settings.register()
    course_settings.register()
    hooks.register()

    global custom_module  # pylint: disable=global-statement
    custom_module = custom_modules.Module(
        constants.MODULE_TITLE,
        'Student view outside of any specific course.',
        handlers.global_routes,
        handlers.namespaced_routes + settings.namespaced_routes)

    return custom_module


custom_module = None
