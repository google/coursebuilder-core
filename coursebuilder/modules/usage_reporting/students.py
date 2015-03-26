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

"""Reporting of anonymized CourseBuilder usage statistics: count students."""

__author__ = [
    'Michael Gainer (mgainer@google.com)',
]

from models import jobs
from models import models
from modules.usage_reporting import messaging


class StudentCounter(jobs.MapReduceJob):
    """M/R job to count students in the course."""

    @staticmethod
    def get_description():
        return 'Count number of students in course.  Used for usage reporting.'

    def entity_class(self):
        return models.Student

    @staticmethod
    def map(student):
        # TODO - count: registered, unregistered, completed, certificated
        yield (messaging.Message.METRIC_STUDENT_COUNT, 1)

    @staticmethod
    def combine(unused_key, values, previously_combined_outputs=None):
        total = sum([int(value) for value in values])
        if previously_combined_outputs is not None:
            total += sum([int(value) for value in previously_combined_outputs])
        yield total

    @staticmethod
    def reduce(key, values):
        total = sum(int(value) for value in values)
        messaging.Message.send_course_message(key, total)
        yield key, total
