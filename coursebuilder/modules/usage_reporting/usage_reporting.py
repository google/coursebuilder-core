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

"""Enable reporting of anonymized usage statistics to CourseBuilder team."""

__author__ = [
    'Michael Gainer (mgainer@google.com)',
]

from controllers import utils
from models import custom_modules
from modules.usage_reporting import config
from modules.usage_reporting import consent_banner
from modules.usage_reporting import course_creation
from modules.usage_reporting import enrollment
from modules.usage_reporting import students

custom_module = None


class StartReportingJobs(utils.AbstractAllCoursesCronHandler):
    """Handle callback from cron; launch map/reduce jobs which report stats."""

    URL = '/cron/usage_reporting/report_usage'

    @classmethod
    def is_globally_enabled(cls):
        return config.REPORT_ALLOWED.value

    @classmethod
    def is_enabled_for_course(cls, app_context):
        return True

    def cron_action(self, app_context, global_state):
        per_course_jobs = [
            students.StudentCounter(app_context),
            enrollment.StudentEnrollmentEventCounter(app_context),
            ]
        for job in per_course_jobs:
            if job.is_active():
                job.cancel()
            job.submit()


def _notify_module_enabled():
    config.notify_module_enabled()
    consent_banner.notify_module_enabled()
    course_creation.notify_module_enabled()
    enrollment.notify_module_enabled()


def register_module():
    global custom_module  # pylint: disable=global-statement
    global_handlers = [
        (StartReportingJobs.URL, StartReportingJobs),
        (
            consent_banner.ConsentBannerRestHandler.URL,
            consent_banner.ConsentBannerRestHandler)]
    custom_module = custom_modules.Module(
        'Usage Reporting',
        'Sends anonymized usage statistics to CourseBuilder team.',
        global_handlers, [],
        notify_module_enabled=_notify_module_enabled)
    return custom_module
