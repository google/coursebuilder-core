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

"""Reporting of anonymized CourseBuilder usage statistics: enrollment counts.

To avoid sending a message to the Google Forms instance on every single
student enroll/unenroll event, we internally store enroll/unenroll events in
the DB.  The weekly reporting cron notification will kick off a map/reduce job
to count the number of enroll/unenroll events per hour; these will be
separately posted to the Google Form.  After a suitable amount of time, the
older entries will be purged.  Here, "suitable" means that we wait long
enough that we are certain that the usage has been reported, even after some
retries.

Deduplication of reports is handled separately.  Our data reporting mechanism
is simply POSTs to a Google Forms document, which forwards results to a
spreadsheet, whence the data can be downloaded as CSV, which will be run
through a simple Python script to do deduplication and any other sanitization
steps required.

"""

__author__ = [
    'Michael Gainer (mgainer@google.com)',
]

import time

from mapreduce import context

from models import jobs
from models import models
from models import transforms
from modules.usage_reporting import messaging

from google.appengine.ext import db

SECONDS_PER_HOUR = 60 * 60
MODULE_NAME = 'usage_reporting'

class StudentEnrollmentEventEntity(models.BaseEntity):
    """Each record represents one enroll/unenroll event.  Contains no PII."""

    data = db.TextProperty(indexed=False)


class StudentEnrollmentEventDTO(object):
    """Convenience functions accessing items 'data' JSON in entity."""

    METRIC = 'metric'
    TIMESTAMP = 'timestamp'

    def __init__(self, the_id, the_dict):
        for key in the_dict:
            if key not in (self.METRIC, self.TIMESTAMP):
                raise ValueError(
                    'Unexpected field present in StudentEnrollmentEventEntity. '
                    'Please consider whether this field might ever contain '
                    'personally identifiable information, and if so, take '
                    'appropriate measures to ensure that this information is '
                    'subject to wipeout restrictions: list the field in '
                    'StudentEnrollmentEventEntity._PROPERTY_EXPORT_BLACKLIST, '
                    'or implement safe_key() (for the key field), or '
                    'for_export() for non-key fields.  See '
                    'models.models.Student for example code.')
        self.id = the_id
        self.dict = the_dict

    @property
    def metric(self):
        return self.dict[self.METRIC]

    @metric.setter
    def metric(self, metric):
        self.dict[self.METRIC] = metric

    @property
    def timestamp(self):
        return self.dict[self.TIMESTAMP]

    @timestamp.setter
    def timestamp(self, timestamp):
        self.dict[self.TIMESTAMP] = timestamp


class StudentEnrollmentEventDAO(models.BaseJsonDao):
    """Manager/policy-definition object for StudentEnrollmentEventEntity."""

    DTO = StudentEnrollmentEventDTO
    ENTITY = StudentEnrollmentEventEntity
    ENTITY_KEY_TYPE = models.BaseJsonDao.EntityKeyTypeId

    @classmethod
    def insert(cls, metric):
        event = StudentEnrollmentEventDTO(None, {})
        event.timestamp = int(time.time())
        event.metric = metric
        cls.save(event)


def _student_add_callback(user_id, timestamp):
    StudentEnrollmentEventDAO.insert(messaging.Message.METRIC_ENROLLED)


def _student_unenroll_callback(user_id, timestamp):
    StudentEnrollmentEventDAO.insert(messaging.Message.METRIC_UNENROLLED)


def _student_reenroll_callback(user_id, timestamp):
    StudentEnrollmentEventDAO.insert(messaging.Message.METRIC_ENROLLED)



class StudentEnrollmentEventCounter(jobs.AbstractCountingMapReduceJob):
    """M/R job to aggregate, report enroll/unenroll counts bucketed by hour."""

    MAX_AGE = SECONDS_PER_HOUR * 24 * 7 * 4  # 4 weeks
    MIN_TIMESTAMP = 'min_timestamp'

    @staticmethod
    def get_description():
        return 'Count enroll/unenroll events, grouped by hour. Clean old items.'

    def entity_class(self):
        return StudentEnrollmentEventEntity

    def build_additional_mapper_params(self, app_context):
        # Pick a single time in the past which is on an even hour boundary
        # so that if this job runs across an hour boundary, we don't wind
        # up changing our minds in the middle of things about what "too old"
        # is, and reporting inconsistent data.
        now = int(time.time())
        min_timestamp = now - (now % SECONDS_PER_HOUR) - self.MAX_AGE
        return {self.MIN_TIMESTAMP: min_timestamp}

    @staticmethod
    def form_key(event):
        """Generate a map key: timestamp, then metric name."""
        return '%d_%s' % (
            event.timestamp - (event.timestamp % SECONDS_PER_HOUR),
            event.metric)

    @staticmethod
    def parse_key(key_string):
        """Split a map key string into component timestamp and metric name."""
        parts = key_string.split('_', 1)
        return int(parts[0]), parts[1]

    @staticmethod
    def map(event):
        """For each event, either discard or send to reducer for aggregation."""

        event = StudentEnrollmentEventDTO(
            event.key().id(), transforms.loads(event.data))
        # Clear out events that are "very old" - i.e., those that we are
        # sure we will already have reported on.
        mapper_params = context.get().mapreduce_spec.mapper.params
        min_timestamp = (
            mapper_params[StudentEnrollmentEventCounter.MIN_TIMESTAMP])
        if event.timestamp < min_timestamp:
            StudentEnrollmentEventDAO.delete(event)
        else:
            yield StudentEnrollmentEventCounter.form_key(event), 1

    @staticmethod
    def combine(unused_key, values, previously_combined_outputs=None):
        total = sum([int(value) for value in values])
        if previously_combined_outputs is not None:
            total += sum([int(value) for value in previously_combined_outputs])
        yield total

    @staticmethod
    def reduce(key, values):
        """Sum count of events, and send report to Google Form."""

        total = sum(int(value) for value in values)
        timestamp, metric = StudentEnrollmentEventCounter.parse_key(key)
        messaging.Message.send_course_message(
            metric, total, timestamp=timestamp)


def notify_module_enabled():
    models.StudentLifecycleObserver.EVENT_CALLBACKS[
        models.StudentLifecycleObserver.EVENT_ADD][MODULE_NAME] = (
          _student_add_callback)
    models.StudentLifecycleObserver.EVENT_CALLBACKS[
        models.StudentLifecycleObserver.EVENT_UNENROLL][MODULE_NAME] = (
          _student_unenroll_callback)
    models.StudentLifecycleObserver.EVENT_CALLBACKS[
        models.StudentLifecycleObserver.EVENT_REENROLL][MODULE_NAME] = (
          _student_reenroll_callback)
