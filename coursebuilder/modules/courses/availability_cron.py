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

"""Background job to update course and content availability.

This DurableJob examines the course content (e.g. unit, lesson) date/time
availability triggers for each course to see if any of them indicate a
requested availability change that is now in the past.

Any triggers whose date & time are before the current start time of the cron
job are consumed (removed from the course settings), and the requested
availability change is made to the course content referred to by the trigger.

Any past triggers found to refer to course content that no longer exists are
logged and then discarded (removed from course settings). No action is
possible if the content no longer exists, so none is taken.

Any triggers that are missing required content are similarly logged and then
removed from the course settings.
"""

__author__ = 'Todd Larsen (tlarsen@google.com)'

import logging

from google.appengine.api import namespace_manager

from common import utc
from controllers import sites
from controllers import utils
from models import courses
from models import jobs
from modules.courses import triggers


class UpdateCourseAvailability(jobs.DurableJob):
    """Examines date/time triggers and updates content availability."""

    @classmethod
    def get_description(cls):
        return "Update content availability based on date/time triggers."

    def run(self):
        now = utc.now_as_datetime()
        namespace = namespace_manager.get_namespace()
        app_context = sites.get_app_context_for_namespace(namespace)
        course = courses.Course.get(app_context)
        settings = course.app_context.get_environ()

        tct = triggers.ContentTrigger
        all_cts = tct.get_from_settings(settings)
        num_cts = len(all_cts)
        logging.info(
            'EXAMINING %d existing "%s" content triggers.', num_cts, namespace)

        # separate_valid_triggers() logs any invalid content triggers and
        # just discards them by not returning them. The only triggers of
        # interest are those triggers ready to be applied now and any
        # triggers who await a future time to be applied.
        future_cts, ready_cts = tct.separate_valid_triggers(
            all_cts, course=course, now=now)

        changes = tct.apply_triggers(ready_cts, namespace=namespace)
        cts_remaining = len(future_cts)

        if num_cts != cts_remaining:
            # At least one of the settings['publish']['content_triggers']
            # was consumed or discarded, so update 'content_triggers' stored
            # in the course settings with the remaining future_cts triggers.
            tct.set_into_settings(future_cts, settings)

            if course.save_settings(settings):
                logging.info(
                    'KEPT %d future "%s" content triggers.',
                    cts_remaining, namespace)
            else:
                logging.warning(
                    'FAILED to keep %d future "%s" content triggers.',
                    cts_remaining, namespace)
        else:
            logging.info(
                'AWAITING %d future "%s" content triggers.',
                cts_remaining, namespace)

        if changes:
            course.save()
            logging.info(
                'SAVED %d changes to "%s" course content availability.',
                changes, namespace)
        else:
            logging.info(
                'UNTOUCHED "%s" course content availability.', namespace)


class StartAvailabilityJobs(utils.AbstractAllCoursesCronHandler):
    """Handle callback from cron by launching availability jobs."""

    URL = '/cron/course_availability/update'

    @classmethod
    def is_globally_enabled(cls):
        return True

    @classmethod
    def is_enabled_for_course(cls, app_context):
        return True

    def cron_action(self, app_context, global_state):
        cron_jobs = [UpdateCourseAvailability(app_context)]
        for job in cron_jobs:
            if job.is_active():
                job.cancel()
            job.submit()
