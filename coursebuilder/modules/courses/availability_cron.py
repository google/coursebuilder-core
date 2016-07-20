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

import datetime
import logging

import appengine_config
from common import utils as common_utils
from common import utc
from controllers import sites
from controllers import utils
from models import courses
from models import jobs
from modules.courses import triggers

from google.appengine.api import namespace_manager
from google.appengine.ext import db
from google.appengine.ext import deferred


class UpdateAvailability(jobs.DurableJob):
    """Examines date/time triggers and updates course and content availability.

    Modules can register to be called back when run() is called. These are
    called strictly after course-level triggers have been applied and saved.
    Callbacks are registered like this:

        availability_cron.UpdateAvailability.RUN_HOOKS[
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
        return "Update course and content availability via date/time triggers."

    def run(self):
        now = utc.now_as_datetime()
        namespace = namespace_manager.get_namespace()
        app_context = sites.get_app_context_for_namespace(namespace)
        course = courses.Course.get(app_context)
        env = app_context.get_environ()

        tct = triggers.ContentTrigger
        content_acts = tct.act_on_settings(course, env, now)

        tmt = triggers.MilestoneTrigger
        course_acts = tmt.act_on_settings(course, env, now)

        save_settings = content_acts.num_consumed or course_acts.num_consumed
        if save_settings:
            # At least one of the settings['publish'] triggers was consumed
            # or discarded, so save changes to triggers into the settings.
            settings_saved = course.save_settings(env)
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


class StartAvailabilityJobsStatus(db.Model):

    SINGLETON_KEY = 'singleton'

    last_run = db.DateTimeProperty(indexed=False)

    @classmethod
    def get_singleton(cls):
        with common_utils.Namespace(appengine_config.DEFAULT_NAMESPACE_NAME):
            entity = cls.get_by_key_name(cls.SINGLETON_KEY)
            if not entity:
                entity = cls(key_name=cls.SINGLETON_KEY)
                entity.last_run = datetime.datetime(1970, 1, 1)
            return entity

    @classmethod
    def update_singleton(cls, entity):
        with common_utils.Namespace(appengine_config.DEFAULT_NAMESPACE_NAME):
            entity.put()


class StartAvailabilityJobs(utils.CronHandler):
    """Handle callback from cron by launching availability jobs.

    NOTE: This is pretty seriously hacktastic.  App Engine enforces a limit of
    a max of 20 entries in cron.yaml, and does not provide a clean way to
    express "hourly, at the top of the hour".  It does support "hourly", but
    this just starts a timer whenever the instance starts, and does a call
    ever 3600 seconds, at whatever position in the hour that happens to be.
    Here, we do some ridiculous stuff with the deferred queue to get a timer
    that operates as we wish.

    Operation: get() is called approximately twice/hour, via the good offices
    of cron.yaml.  This adds adds an item on the deferred queue with an ETA at
    the top of the next hour.  When that hour rolls around, we run
    maybe_start_jobs().  If this is the first time within this hour that
    the deferred queue has called us, we start jobs.  If it is not the first
    time, we just drop the request on the floor.  In all cases, we simply
    return normally, indicating to the queue manager that the task can be
    dropped.  We don't need to re-enqueue work for ourselves, since we are
    guaranteed to be tickled by cron anyhow.
    """

    URL = '/cron/availability/update'

    def get(self):
        eta_timestamp = utc.hour_end(utc.now_as_timestamp()) + 1
        eta = utc.timestamp_to_datetime(eta_timestamp)
        deferred.defer(self.maybe_start_jobs, _eta=eta)
        logging.info(
            'StartAvailabilityJobs - scheduling deferred task at %s', eta)

    @classmethod
    def maybe_start_jobs(cls):
        # Current time, rounded to top of hour.
        @db.transactional(xg=True)
        def should_start_jobs():
            now_timestamp = utc.hour_start(utc.now_as_timestamp())
            status = StartAvailabilityJobsStatus.get_singleton()
            last_run = utc.hour_start(
                utc.datetime_to_timestamp(status.last_run))
            if now_timestamp > last_run:
                status.last_run = utc.timestamp_to_datetime(now_timestamp)
                StartAvailabilityJobsStatus.update_singleton(status)
                return True
            return False

        if should_start_jobs():
            logging.info('StartAvailabilityJobs: running jobs')
            for app_context in sites.get_all_courses():
                job = UpdateAvailability(app_context)
                if job.is_active():
                    job.cancel()
                job.submit()
        else:
            logging.info('StartAvailabilityJobs: skipping jobs')
