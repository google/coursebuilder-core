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

"""Common classes and methods for managing long running jobs."""

__author__ = 'Pavel Simakov (psimakov@google.com)'

from datetime import datetime
import logging
import time
import traceback
import entities
import transforms

from google.appengine import runtime
from google.appengine.api import namespace_manager
from google.appengine.ext import db
from google.appengine.ext import deferred


# A job can be in one of these states.
STATUS_CODE_QUEUED = 0
STATUS_CODE_STARTED = 1
STATUS_CODE_COMPLETED = 2
STATUS_CODE_FAILED = 3


class DurableJob(object):
    """A class that represents a deferred durable job at runtime."""

    # The methods in DurableJobEntity are module-level protected
    # pylint: disable-msg=protected-access

    def __init__(self, app_context):
        self._namespace = app_context.get_namespace_name()
        self._job_name = 'job-%s-%s' % (
            self.__class__.__name__, self._namespace)

    def run(self):
        """Override this method to provide actual business logic."""

    def main(self):
        """Main method of the deferred task."""
        logging.info('Job started: %s', self._job_name)

        time_started = time.time()
        old_namespace = namespace_manager.get_namespace()
        try:
            namespace_manager.set_namespace(self._namespace)
            try:
                db.run_in_transaction(DurableJobEntity._start_job,
                                      self._job_name)
                result = self.run()
                db.run_in_transaction(DurableJobEntity._complete_job,
                                      self._job_name, transforms.dumps(result),
                                      long(time.time() - time_started))
                logging.info('Job completed: %s', self._job_name)
            except (Exception, runtime.DeadlineExceededError) as e:
                logging.error(traceback.format_exc())
                logging.error('Job failed: %s\n%s', self._job_name, e)
                db.run_in_transaction(DurableJobEntity._fail_job,
                                      self._job_name, traceback.format_exc(),
                                      long(time.time() - time_started))
                raise deferred.PermanentTaskFailure(e)
        finally:
            namespace_manager.set_namespace(old_namespace)

    def submit(self):
        """Submits this job for deferred execution."""
        old_namespace = namespace_manager.get_namespace()
        try:
            namespace_manager.set_namespace(self._namespace)
            db.run_in_transaction(DurableJobEntity._create_job, self._job_name)
            deferred.defer(self.main)
        finally:
            namespace_manager.set_namespace(old_namespace)

    def non_transactional_submit(self):
        old_namespace = namespace_manager.get_namespace()
        try:
            namespace_manager.set_namespace(self._namespace)
            DurableJobEntity._create_job(self._job_name)
            deferred.defer(self.main)
        finally:
            namespace_manager.set_namespace(old_namespace)

    def load(self):
        """Loads the last known state of this job from the datastore."""
        old_namespace = namespace_manager.get_namespace()
        try:
            namespace_manager.set_namespace(self._namespace)
            entity = DurableJobEntity._get_by_name(self._job_name)
            return entity
        finally:
            namespace_manager.set_namespace(old_namespace)


class DurableJobEntity(entities.BaseEntity):
    """A class that represents a persistent database entity of durable job."""

    updated_on = db.DateTimeProperty(indexed=True)
    execution_time_sec = db.IntegerProperty(indexed=False)
    status_code = db.IntegerProperty(indexed=False)
    output = db.TextProperty(indexed=False)

    @classmethod
    def _get_by_name(cls, name):
        return DurableJobEntity.get_by_key_name(name)

    @classmethod
    def _update(cls, name, status_code, output, execution_time_sec):
        """Updates job state in a datastore."""
        assert db.is_in_transaction()

        job = DurableJobEntity._get_by_name(name)
        if not job:
            logging.error('Job was not started or was deleted: %s', name)
            return
        job.updated_on = datetime.now()
        job.execution_time_sec = execution_time_sec
        job.status_code = status_code
        job.output = output
        job.put()

    @classmethod
    def _create_job(cls, name):
        """Creates new or reset a state of existing job in a datastore."""
        assert db.is_in_transaction()

        job = DurableJobEntity._get_by_name(name)
        if not job:
            job = DurableJobEntity(key_name=name)
        job.updated_on = datetime.now()
        job.execution_time_sec = 0
        job.status_code = STATUS_CODE_QUEUED
        job.output = None
        job.put()

    @classmethod
    def _start_job(cls, name):
        return cls._update(name, STATUS_CODE_STARTED, None, 0)

    @classmethod
    def _complete_job(cls, name, output, execution_time_sec):
        return cls._update(
            name, STATUS_CODE_COMPLETED, output, execution_time_sec)

    @classmethod
    def _fail_job(cls, name, output, execution_time_sec):
        return cls._update(name, STATUS_CODE_FAILED, output, execution_time_sec)

    @property
    def has_finished(self):
        return self.status_code in [STATUS_CODE_COMPLETED, STATUS_CODE_FAILED]
