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

"""MapReduce job to set the student total enrollment count for courses.

This MapReduce updates two of the course enrollments counters, the simple
'total' enrollment count and the daily-binned 'adds' counts.

The 'total' counter is updated by calling enrollments.TotalEnrollmentDAO.set()
to force a known value on the 'total' counter for a specified course. The
purpose of this MapReduce is to "reset" the total enrollment count to an
absolute starting point, and then allow that count to be incremented and
decremented in real time, between runs of the MapReduce, by the registered
StudentLifecycleObserver handlers. Those handlers adjust the MapReduce-computed
starting point by the equivalent of:
  (number of EVENT_ADD + number of EVENT_REENROLL)
    - (number of EVENT_UNENROLL + number of EVENT_UNENROLL_COMMANDED)

Counters in the daily bins of the 'adds' counters are updated by calling
enrollments.EnrollmentsAddedDAO.set() overwrite the values for each daily
bin. The bin is determined from the Student.enrolled_on value of each student
enrolled in the specified course. To avoid race conditions between this
MapReduce and real time updates being made by the student lifecycle event
handlers, the bin corresponding to "today" when the MapReduce is run is *not*
overwritten.
"""

__author__ = 'Todd Larsen (tlarsen@google.com)'

from google.appengine.api import namespace_manager

from common import utc
from controllers import utils
from models import jobs
from models import models
from modules.admin import enrollments


class SetCourseEnrollments(jobs.MapReduceJob):
    """MapReduce job to set student 'total' and 'adds' counts for a course."""

    @staticmethod
    def get_description():
        return "Update the 'total' and 'adds' counters for a course."

    def entity_class(self):
        return models.Student

    @staticmethod
    def map(student):
        yield (enrollments.TotalEnrollmentEntity.COUNTING, 1)
        bin_seconds_since_epoch = enrollments.BinnedEnrollmentsDTO.bin(
            utc.datetime_to_timestamp(student.enrolled_on))
        yield (bin_seconds_since_epoch, 1)

    @staticmethod
    def combine(unused_key, values, previously_combined_outputs=None):
        total = sum([int(value) for value in values])
        if previously_combined_outputs is not None:
            total += sum([int(value) for value in previously_combined_outputs])
        yield total

    @staticmethod
    def reduce(key, values):
        total = sum(int(value) for value in values)
        ns_name = namespace_manager.get_namespace()

        if key == enrollments.TotalEnrollmentEntity.COUNTING:
            enrollments.TotalEnrollmentDAO.set(ns_name, total)
        else:
            # key is actually a daily 'adds' counter bin seconds since epoch.
            bin_seconds_since_epoch = long(key)
            today = utc.day_start(utc.now_as_timestamp())
            # Avoid race conditions by not updating today's daily bin (which
            # is being updated by student lifecycle events).
            if bin_seconds_since_epoch != today:
                date_time = utc.timestamp_to_datetime(bin_seconds_since_epoch)
                enrollments.EnrollmentsAddedDAO.set(ns_name, date_time, total)


class StartEnrollmentsJobs(utils.AbstractAllCoursesCronHandler):
    """Handle callback from cron by launching enrollments counts MapReduce."""

    # /cron/site_admin_enrollments/total
    URL = '/cron/%s/%s' % (
        enrollments.MODULE_NAME, enrollments.TotalEnrollmentEntity.COUNTING)

    @classmethod
    def is_globally_enabled(cls):
        return True

    @classmethod
    def is_enabled_for_course(cls, app_context):
        return True

    def cron_action(self, app_context, global_state):
        cron_jobs = [SetCourseEnrollments(app_context)]
        for job in cron_jobs:
            if job.is_active():
                job.cancel()
            job.submit()
