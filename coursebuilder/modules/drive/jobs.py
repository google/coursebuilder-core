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

"""Background jobs for the Drive module."""

__author__ = 'Nick Retallack (nretallack@google.com)'

import logging

from google.appengine.ext import deferred
from google.appengine.ext import db

from models import jobs
from modules.drive import drive_api_manager
from modules.drive import drive_models
from modules.drive import errors


class DriveSyncJob(jobs.DurableJobBase):

    def get_a_valid_work_item(self):
        return sorted(
            (dto for dto in drive_models.DriveSyncDAO.get_all_iter()
                if dto.needs_sync),
            key=lambda dto: dto.sync_priority,
            reverse=True)[0]

    def complete(self, sequence_num):
        # Nothing left to do.
        # pylint: disable=protected-access
        db.run_in_transaction(
            jobs.DurableJobEntity._complete_job, self._job_name,
            sequence_num, '')
        # pylint: enable=protected-access

    def main(self, sequence_num):
        logging.info('Drive job waking up')
        job = self.load()
        if not job:
            raise deferred.PermanentTaskFailure(
                'Job object for {} not found!'.format(self._job_name))
        if job.has_finished:
            return

        try:
            # pylint: disable=protected-access
            drive_manager = drive_api_manager._DriveManager.from_app_context(
                self._app_context)
            # pylint: enable=protected-access
        except errors.NotConfigured:
            self.complete(sequence_num)
            return
        except errors.Misconfigured as error:
            logging.error('%s: Drive is misconfigured in %s: %s',
                self._job_name, self._app_context.get_title(), error)
            raise deferred.PermanentTaskFailure('Job {} failed: {}'.format(
                self._job_name, error))

        try:
            dto = self.get_a_valid_work_item()
        except IndexError:
            self.complete(sequence_num)
            return

        try:
            logging.info('Starting download of %s', dto.title)
            drive_manager.download_file(dto)
            logging.info('Finished download of %s', dto.title)
        except Exception as error:  #pylint: disable=broad-except
            # Normally errors.Error covers everything, but this covers the
            # possibility of an unexpected parse error.
            logging.info(
                'Failed to sync %s (%s) from drive: %s', dto.title, dto.key,
                error)

        deferred.defer(self.main, sequence_num)

    def non_transactional_submit(self):
        """Callback used when UI gesture indicates this job should start."""

        sequence_num = super(DriveSyncJob, self).non_transactional_submit()
        deferred.defer(self.main, sequence_num)
        return sequence_num
