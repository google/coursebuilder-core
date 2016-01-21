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

"""Downloads spreadsheets and documents from Google Drive."""

__author__ = 'Nick Retallack (nretallack@google.com)'

from models import custom_modules
from modules.drive import constants
from modules.drive import drive_settings
from modules.drive import handlers


def register_module():

    handlers.DriveListHandler.add_to_menu(
        'edit', constants.MODULE_NAME, 'Drive')

    drive_settings.make_drive_settings_section()

    global custom_module  # pylint: disable=global-statement
    custom_module = custom_modules.Module(
        constants.MODULE_TITLE,
        'Sync spreadsheets and documents from Google Drive',
        handlers.global_routes, handlers.namespaced_routes)

    return custom_module


custom_module = None
