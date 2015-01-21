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

"""A module that adds the ability to do ajax requests."""

__author__ = 'Abhinav Khandelwal (abhinavk@google.com)'


from common import tags
from models import custom_modules

MODULE_NAME = 'Ajax Registry Library'


# Module registration
custom_module = None


def register_module():
    """Registers this module in the registry."""

    global_routes = [
        ('/modules/ajax_registry/assets/.*', tags.ResourcesHandler)
    ]

    global custom_module  # pylint: disable=global-statement
    custom_module = custom_modules.Module(
        MODULE_NAME, 'Provides library to register ajax calls',
        global_routes, [])
    return custom_module
