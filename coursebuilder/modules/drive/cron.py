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

"""Cron job handlers for the Drive module."""

__author__ = [
    'nretallack@google.com (Nick Retallack)',
]

import logging

from controllers import utils
from modules.drive import jobs
from modules.drive import drive_api_manager
from modules.drive import errors


class DriveCronHandler(utils.AbstractAllCoursesCronHandler):
    URL = 'cron/drive/sync'

    @classmethod
    def is_globally_enabled(cls):
        return True

    @classmethod
    def is_enabled_for_course(cls, app_context):
        try:
            # pylint: disable=protected-access
            drive_manager = drive_api_manager._DriveManager.from_app_context(
                app_context)
            # pylint: enable=protected-access
            return True
        except errors.NotConfigured:
            pass
        except errors.Misconfigured as error:
            logging.error('Drive is misconfigured in %s: %s',
                app_context.get_title(), error)
        return False

    def cron_action(self, app_context, global_state):
        jobs.DriveSyncJob(app_context).submit()
