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

from common import resource
from common import utc
from controllers import sites
from controllers import utils
from models import courses
from models import jobs
from modules.courses import availability


class UpdateCourseAvailability(jobs.DurableJob):
    """Examines date/time triggers and updates content availability."""

    @classmethod
    def get_description(cls):
        return "Update content availability based on date/time triggers."

    def run(self):
        now = utc.now_as_datetime()
        ns = namespace_manager.get_namespace()
        course = courses.Course(
            None, app_context=sites.get_app_context_for_namespace(ns))
        settings = course.app_context.get_environ()
        publish = settings.setdefault('publish', {})
        triggers = publish.get('triggers', [])

        changes = 0
        future = []
        self._ns = ns  # Used by _decode...() methods when logging.

        logging.info(
            'EXAMINING %d existing "%s" availability triggers.',
            len(triggers), ns)

        for t in triggers:
            when = self._decode_when(t)
            avail = self._decode_avail(t)
            content = self._decode_content(t)
            found = self._find_content(content, course, t)

            if not all([when, avail, content, found]):
                # Drop corrupt or obsolete (that is, associated course content
                # no longer exists) availability triggers. No action is taken,
                # and the trigger is not added back to the future list.
                continue

            if when > now:
                # Valid trigger, but still in the future, so save for later.
                future.append(t)
                continue

            # Any trigger past this point is *not* malformed, is "in the
            # past", and also still has associated course content that exists.
            # Act on the trigger and consume it (it is not added back to the
            # future list).
            current = found.availability
            if current != avail:
                changes += 1
                found.availability = avail
                logging.info(
                    'TRIGGERED "%s" content availability "%s" to "%s": %s',
                    ns, current, avail, t)
            else:
                logging.info(
                    'UNCHANGED "%s" content availability "%s": %s',
                    ns, current, t)

        if len(triggers) != len(future):
            # At least one of publish['triggers'] was consumed or discarded.
            publish['triggers'] = future

            if course.save_settings(settings):
                logging.info(
                    'KEPT %d future "%s" availability triggers.',
                    len(future), ns)
            else:
                logging.warning(
                    'FAILED to keep %d future "%s" availability triggers.',
                    len(future), ns)
        else:
            logging.info(
                'AWAITING %d future "%s" availability triggers.',
                len(future), ns)

        if changes:
            course.save()
            logging.info(
                'SAVED %d changes to "%s" course content availability.',
                changes, ns)
        else:
            logging.info(
                'UNTOUCHED "%s" course content availability.', ns)

    _OUTLINE_CONTENT_TYPES = (
        availability.AvailabilityRESTHandler.OUTLINE_CONTENT_TYPES)
    _UNEXPECTED_CONTENT_FMT = (
        availability.AvailabilityRESTHandler.UNEXPECTED_CONTENT_FMT)
    _MISSING_CONTENT_FMT = (
        availability.AvailabilityRESTHandler.MISSING_CONTENT_FMT)
    _UNEXPECTED_AVAIL_FMT = (
        availability.AvailabilityRESTHandler.UNEXPECTED_AVAIL_FMT)

    def _decode_when(self, trigger):
        try:
            return utc.text_to_datetime(trigger.get('when'))
        except (ValueError, TypeError) as err:
            availability.AvailabilityRESTHandler.log_trigger_error(
                trigger, why='date/time', ns=self._ns, cause=repr(err))
            return None

    def _decode_avail(self, trigger):
        avail = trigger.get('availability')
        if avail in courses.AVAILABILITY_VALUES:
            return avail
        availability.AvailabilityRESTHandler.log_trigger_error(
            trigger, why='availability', ns=self._ns,
            cause=self._UNEXPECTED_AVAIL_FMT % avail)
        return None

    def _decode_content(self, trigger):
        try:
            content = resource.Key.fromstring(trigger.get('content'))
        except (ValueError, AttributeError) as err:
            availability.AvailabilityRESTHandler.log_trigger_error(
                trigger, ns=self._ns, cause=repr(err))
            return None

        if content and (content.type not in self._OUTLINE_CONTENT_TYPES):
            availability.AvailabilityRESTHandler.log_trigger_error(
                trigger, ns=self._ns,
                cause=self._UNEXPECTED_CONTENT_FMT % content.type)
            return None

        return content

    def _find_content(self, content, course, trigger):
        if not content:
            # Any `content` errors were already logged by _decode_content().
            return None

        if content.type == 'unit':
            item = course.find_unit_by_id(content.key)
        elif content.type == 'lesson':
            item = course.find_lesson_by_id(None, content.key)
        else:
            availability.AvailabilityRESTHandler.log_trigger_error(
                trigger, ns=self._ns,
                cause=self._UNEXPECTED_CONTENT_FMT % content.type)
            return None

        # TODO(tlarsen): Add hook into content item (unit, lesson etc.)
        #   deletion to delete any date/time availability triggers associated
        #   with the deleted item.
        if not item:
            availability.AvailabilityRESTHandler.log_trigger_error(
                trigger, what='OBSOLETE', ns=self._ns,
                cause=self._MISSING_CONTENT_FMT % content)

        return item


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
