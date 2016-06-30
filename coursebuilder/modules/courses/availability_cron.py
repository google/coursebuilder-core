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

from google.appengine.api import namespace_manager

from common import utils as common_utils
from common import utc
from controllers import sites
from controllers import utils
from models import courses
from models import jobs
from modules.courses import triggers


class UpdateCourseAvailability(jobs.DurableJob):
    """Examines date/time triggers and updates content availability.

    Modules can register to be called back when run() is called. These are
    called strictly after course-level triggers have been applied and saved.
    Callbacks are registered like this:

        availability_cron.UpdateCourseAvailability.RUN_HOOKS[
            'my_module'] = my_handler

    RUN_HOOKS callbacks are called a single time, and in no particular order,
    via common.utils.run_hooks().

    Hooks should accept the following parameters:
        - course, a normal models.courses.Course instance; app context,
            settings, and the rest can all be fetched from this.
    """

    RUN_HOOKS = {}

    @classmethod
    def get_description(cls):
        return "Update content availability based on date/time triggers."

    def run(self):
        now = utc.now_as_datetime()
        namespace = namespace_manager.get_namespace()
        app_context = sites.get_app_context_for_namespace(namespace)
        course = courses.Course.get(app_context)
        settings = app_context.get_environ()

        tct = triggers.ContentTrigger
        content_acts = tct.act_on_settings(course, settings, now)

        tmt = triggers.MilestoneTrigger
        course_acts = tmt.act_on_settings(course, settings, now)

        if content_acts.num_consumed or course_acts.num_consumed:
            # At least one of the settings['publish'] triggers was consumed
            # or discarded, so save changes to triggers into the settings.
            settings_saved = course.save_settings(settings)
        else:
            settings_saved = False

        save_course = content_acts.num_changed or course_acts.num_changed
        if save_course:
            course.save()

        tct.log_acted_on(
            namespace, content_acts, save_course, settings_saved)
        tmt.log_acted_on(
            namespace, course_acts, save_course, settings_saved)

        common_utils.run_hooks(self.RUN_HOOKS.itervalues(), course)


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
        job = UpdateCourseAvailability(app_context)
        if job.is_active():
            job.cancel()
        job.submit()
