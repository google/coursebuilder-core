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

"""Functional tests for models/jobs.py."""

__author__ = [
    'mgainer@google.com (Mike Gainer)',
]

from common.utils import Namespace
from models import jobs
from models import transforms
from tests.functional import actions

from google.appengine.ext import db

TEST_NAMESPACE = 'test'
TEST_DATA = {'bunny_names': ['flopsy', 'mopsy', 'cottontail']}
TEST_DURATION = 123
TEST_BAD_DATA = {'wolf_actions': ['huff', 'puff', 'blow your house down']}
TEST_BAD_DURATION = 4


class MockAppContext(object):

    def __init__(self, namespace):
        self._namespace = namespace

    def get_namespace_name(self):
        return self._namespace


class TestJob(jobs.DurableJobBase):

    def __init__(self, namespace):
        super(TestJob, self).__init__(MockAppContext(namespace))

    def force_start_job(self, sequence_num):
        with Namespace(self._namespace):
            db.run_in_transaction(
                jobs.DurableJobEntity._start_job, self._job_name,
                sequence_num)

    def force_complete_job(self, sequence_num, data, duration):
        data = transforms.dumps(data)
        with Namespace(self._namespace):
            db.run_in_transaction(
                jobs.DurableJobEntity._complete_job, self._job_name,
                sequence_num, data, duration)

    def force_fail_job(self, sequence_num, data, duration):
        data = transforms.dumps(data)
        with Namespace(self._namespace):
            db.run_in_transaction(
                jobs.DurableJobEntity._fail_job, self._job_name,
                sequence_num, data, duration)

    def get_output(self):
        return transforms.loads(self.load().output)


class JobOperationsTest(actions.TestBase):
    """Validate operation of job behaviors."""

    def setUp(self):
        super(JobOperationsTest, self).setUp()
        self.test_job = TestJob(TEST_NAMESPACE)

    # ---------------------------------------------------------------------
    # Tests with no item in datastore

    def test_load_finds_none(self):
        self.assertIsNone(self.test_job.load())

    def test_cancel_finds_none(self):
        self.assertIsNone(self.test_job.cancel())

    def test_not_active(self):
        self.assertFalse(self.test_job.is_active())

    # ---------------------------------------------------------------------
    # Normal operation w/ no admin intervention

    def test_submit_enqueues_job(self):
        self.assertFalse(self.test_job.is_active())
        self.test_job.submit()
        self.assertTrue(self.test_job.is_active())
        self.assertEquals(jobs.STATUS_CODE_QUEUED,
                          self.test_job.load().status_code)

    def test_start_starts_job(self):
        self.assertFalse(self.test_job.is_active())
        sequence_num = self.test_job.submit()
        self.test_job.force_start_job(sequence_num)
        self.assertTrue(self.test_job.is_active())
        self.assertEquals(jobs.STATUS_CODE_STARTED,
                          self.test_job.load().status_code)

    def test_complete_job_saves_result(self):
        self._test_saves_result(self.test_job.force_complete_job,
                                jobs.STATUS_CODE_COMPLETED)

    def test_fail_job_saves_result(self):
        self._test_saves_result(self.test_job.force_fail_job,
                                jobs.STATUS_CODE_FAILED)

    def _test_saves_result(self, func, expected_status):
        self.assertFalse(self.test_job.is_active())
        sequence_num = self.test_job.submit()
        self.test_job.force_start_job(sequence_num)
        self.assertIsNone(self.test_job.load().output)
        func(sequence_num, TEST_DATA, TEST_DURATION)
        self.assertFalse(self.test_job.is_active())
        self.assertEquals(expected_status, self.test_job.load().status_code)
        self.assertEquals(TEST_DATA, self.test_job.get_output())
        self.assertEquals(TEST_DURATION,
                          self.test_job.load().execution_time_sec)

    def test_submit_does_not_restart_running_job(self):
        sequence_num = self.test_job.submit()
        self.test_job.force_start_job(sequence_num)
        next_seq = self.test_job.submit()
        self.assertEquals(next_seq, -1)
        # Check status is still STARTED, not QUEUED, which it would be
        # if we'd started the job anew.
        self.assertEquals(jobs.STATUS_CODE_STARTED,
                          self.test_job.load().status_code)

    # --------------------------------------------------------------------
    # Cancelling jobs

    def test_cancel_kills_queued_job(self):
        self.assertFalse(self.test_job.is_active())
        self.test_job.submit()
        self.test_job.cancel()
        self.assertFalse(self.test_job.is_active())
        self.assertIn('Canceled by default', self.test_job.load().output)
        self.assertEquals(jobs.STATUS_CODE_FAILED,
                          self.test_job.load().status_code)

    def test_cancel_kills_started_job(self):
        self.assertFalse(self.test_job.is_active())
        sequence_num = self.test_job.submit()
        self.test_job.force_start_job(sequence_num)
        self.test_job.cancel()
        self.assertFalse(self.test_job.is_active())
        self.assertEquals(jobs.STATUS_CODE_FAILED,
                          self.test_job.load().status_code)

    def test_cancel_does_not_kill_completed_job(self):
        sequence_num = self.test_job.submit()
        self.test_job.force_start_job(sequence_num)
        self.test_job.force_complete_job(sequence_num, TEST_DATA,
                                         TEST_DURATION)
        self.assertFalse(self.test_job.is_active())
        self.test_job.cancel()
        self.assertEquals(jobs.STATUS_CODE_COMPLETED,
                          self.test_job.load().status_code)

    def test_killed_job_can_still_complete(self):
        self._killed_job_can_still_record_results(
            self.test_job.force_complete_job, jobs.STATUS_CODE_COMPLETED)

    def test_killed_job_can_still_fail(self):
        self._killed_job_can_still_record_results(
            self.test_job.force_fail_job, jobs.STATUS_CODE_FAILED)

    def _killed_job_can_still_record_results(self, func, expected_status):
        sequence_num = self.test_job.submit()
        self.test_job.force_start_job(sequence_num)
        self.test_job.cancel()
        self.assertIn('Canceled by default', self.test_job.load().output)
        self.assertEquals(jobs.STATUS_CODE_FAILED,
                          self.test_job.load().status_code)

        func(sequence_num, TEST_DATA, TEST_DURATION)
        self.assertEquals(expected_status, self.test_job.load().status_code)
        self.assertEquals(TEST_DATA, self.test_job.get_output())
        self.assertEquals(TEST_DURATION,
                          self.test_job.load().execution_time_sec)

    # --------------------------------------------------------------------
    # Results from older runs are ignored, even if a seemingly-hung job
    # later completes or fails.

    def test_kill_and_restart_job_old_job_completes(self):
        self._test_kill_and_restart(self.test_job.force_complete_job)

    def test_kill_and_restart_job_old_job_fails(self):
        self._test_kill_and_restart(self.test_job.force_fail_job)

    def _test_kill_and_restart(self, func):

        sequence_num = self.test_job.submit()
        self.test_job.force_start_job(sequence_num)
        self.test_job.cancel()
        sequence_num_2 = self.test_job.submit()
        self.assertEquals(sequence_num_2, sequence_num + 1)
        self.test_job.force_start_job(sequence_num_2)
        self.test_job.force_complete_job(sequence_num_2, TEST_DATA,
                                         TEST_DURATION)

        # Now try to complete the (long-running) first try.
        # Results from previous run should not overwrite more-recent.
        func(sequence_num, TEST_BAD_DATA, TEST_BAD_DURATION)
        self.assertEquals(TEST_DATA, self.test_job.get_output())
        self.assertEquals(TEST_DURATION,
                          self.test_job.load().execution_time_sec)
