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

"""Guide: new, non-linear learning experience module."""

__author__ = [
    'davyrisso@google.com (Davy Risso)',
]

from models import custom_modules

from modules.guide import constants
from modules.guide import course_settings
from modules.guide import graphql
from modules.guide import handlers
from modules.guide import messages
from modules.guide import settings


def register_module():
    course_settings.register()
    graphql.register()

    global custom_module  # pylint: disable=global-statement
    custom_module = custom_modules.Module(
        constants.MODULE_TITLE, messages.MODULE_DESCRIPTION,
        handlers.global_routes,
        handlers.namespaced_routes + settings.namespaced_routes)

    return custom_module


custom_module = None
