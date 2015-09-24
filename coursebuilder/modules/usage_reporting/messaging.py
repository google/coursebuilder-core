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

"""Reporting of anonymized CourseBuilder usage statistics: send messages."""

__author__ = [
    'Michael Gainer (mgainer@google.com)',
]

import logging
import os
import time
import urllib
import uuid

import appengine_config

from common import utils as common_utils
from controllers import sites
from models import config
from models import courses
from models import roles
from models import transforms

from google.appengine.api import namespace_manager
from google.appengine.api import taskqueue
from google.appengine.api import urlfetch
from google.appengine.ext import deferred

_INSTALLATION_IDENTIFIER = config.ConfigProperty(
    'gcb_report_usage_identifier', str, (
        'Randomized string used to identify this installation of '
        'CourseBuilder when reporting usage statistics.  This value '
        'has no intrinsic meaning, and no relation to any data or '
        'course setting; it is just used to correlate the weekly '
        'reports from this installation.'),
    default_value='A random value will be picked when the first report is '
    'sent.', label='Usage report ID',
    )

# Name of the item in the course settings dictionary which contains the
# randomly-generated identifier for the course.  (This name needs to be
# defined here to prevent circular inclusion problems with this module
# versus 'config')
USAGE_REPORTING_FIELD_ID = 'usage_reporting_id'

# Usage reporting is turned off on dev, but this flag overrides that, to
# enable testing of messaging and UI.
ENABLED_IN_DEV_FOR_TESTING = False


def is_disabled():
    return (
        not appengine_config.PRODUCTION_MODE and not ENABLED_IN_DEV_FOR_TESTING)


class Sender(object):
    """Namespace to permit replacement of messaging functions for testing."""

    # We want to be able to re-point the statistics reporting at some later
    # time.  To do that, we fetch an enablement flag and a destination URL
    # from a JSON document hosted at this URL.
    _REPORT_SETTINGS_INFO_URL = (
        'https://www.google.com/edu/coursebuilder/stats/config.json')

    # Field in control document indicating whether stats reporting is enabled.
    _REPORT_ENABLED = 'enabled'

    # Field in control document giving target URL to which to POST reports.
    _REPORT_TARGET = 'target'

    # Field in control document naming form field to use in POST.
    _REPORT_FORM_FIELD = 'form_field'

    # If we need to make a report, and the target URL is older than this,
    # re-fetch the control page so we are current on the latest state of
    # the 'enable' and 'target' parameters.
    _REPORT_SETTINGS_MAX_AGE = 3600

    # Latest values of report settings as loaded from _REPORT_SETTINGS_INFO_URL
    _report_settings = {
        _REPORT_ENABLED: False,
        _REPORT_TARGET: ''
    }
    _report_settings_timestamp = 0

    # Config options for task retries.
    _RETRY_OPT_NUM_TRIES = 10
    _RETRY_OPT_AGE_LIMIT_SECONDS = 60 * 60 * 10
    _RETRY_OPT_MIN_BACKOFF_SECONDS = 60
    _RETRY_OPT_MAX_DOUBLINGS = 6
    _RETRY_OPT_MAX_BACKOFF_SECONDS = (
        _RETRY_OPT_MIN_BACKOFF_SECONDS * (2 ** (_RETRY_OPT_MAX_DOUBLINGS - 1)))

    @classmethod
    def _refresh_report_settings(cls):
        """Ensure report settings are up-to-date, or raise an exception."""

        max_age = cls._report_settings_timestamp + cls._REPORT_SETTINGS_MAX_AGE
        if time.time() > max_age:
            response = urlfetch.fetch(
                cls._REPORT_SETTINGS_INFO_URL, method='GET',
                follow_redirects=True)
            if response.status_code != 200:
                raise RuntimeError(
                    'Failed to load statistics reporting settings from "%s"' %
                    cls._REPORT_SETTINGS_INFO_URL)
            cls._report_settings = transforms.loads(response.content)
            cls._report_settings_timestamp = int(time.time())

    @classmethod
    def _emit_message(cls, message):
        """Emit message if allowed, not if not, or raise exception."""
        cls._refresh_report_settings()
        if cls._report_settings[cls._REPORT_ENABLED] and not is_disabled():

            try:
                payload = urllib.urlencode(
                    {cls._report_settings[cls._REPORT_FORM_FIELD]: message})
                response = urlfetch.fetch(
                    cls._report_settings[cls._REPORT_TARGET], method='POST',
                    follow_redirects=True, payload=payload)
            except urlfetch.Error:
                # If something went so wrong we got an exception (as opposed
                # to simply getting a 500 server error from the target),
                # reset the timer so we re-fetch configs; presumably humans
                # will notice the problem and fix the configs "soon".
                cls._report_settings_timestamp = 0
                raise
            if response.status_code != 200:
                raise RuntimeError(
                    'Failed to send statistics report "%s" to "%s"' % (
                        message, cls._report_settings[cls._REPORT_TARGET]))

    @classmethod
    def send_message(cls, the_dict):
        message = transforms.dumps(the_dict)
        try:
            # One attempt to get the message out synchronously.
            cls._emit_message(message)
        except Exception, ex:  # pylint: disable=broad-except
            # Anything goes wrong, it goes on the deferred queue for retries.
            logging.critical('Problem trying to report statistics: %s', ex)
            common_utils.log_exception_origin()
            options = taskqueue.TaskRetryOptions(
                task_retry_limit=cls._RETRY_OPT_NUM_TRIES,
                task_age_limit=cls._RETRY_OPT_AGE_LIMIT_SECONDS,
                min_backoff_seconds=cls._RETRY_OPT_MIN_BACKOFF_SECONDS,
                max_backoff_seconds=cls._RETRY_OPT_MAX_BACKOFF_SECONDS,
                max_doublings=cls._RETRY_OPT_MAX_DOUBLINGS)
            deferred.defer(cls._emit_message, message, _retry_options=options)


class Message(object):
    """Namespace to permit replacement of messaging functions for testing."""

    # Each message sent to the form is a JSON dict containing these fields.
    _TIMESTAMP = 'timestamp'
    _VERSION = 'version'  # CourseBuilder version
    _INSTALLATION = 'installation'  # Randomly-chosen install ID
    _COURSE = 'course'  # Randomly-chosen course ID.  Optional.
    _METRIC = 'metric'  # A name from the set below.
    _VALUE = 'value'  # Integer or boolean value.
    _SOURCE = 'source'  # String name of system component.
    _COURSE_TITLE = 'course_title'  # Only sent for Google-run courses
    _COURSE_SLUG = 'course_slug'  # Only sent for Google-run courses
    _COURSE_NAMESPACE = 'course_namespace'  # Only sent for Google-run courses

    # Values to be used for the _SOURCE field
    ADMIN_SOURCE = 'ADMIN_SETTINGS'
    BANNER_SOURCE = 'CONSENT_BANNER'
    WELCOME_SOURCE = 'WELCOME_PAGE'

    # Allowed values that can be used for the 'metric' parameter in
    # send_course_message() and send_instance_message().
    METRIC_REPORT_ALLOWED = 'report_allowed'  #  True/False
    METRIC_STUDENT_COUNT = 'student_count'  #  Num students in course.
    METRIC_ENROLLED = 'enrolled'  # Num students enrolled in 1-hour block.
    METRIC_UNENROLLED = 'unenrolled' # Num students unenrolled in 1-hour block.
    METRIC_COURSE_CREATED = 'course_created'  # Always 1 when course created.
    _ALLOWED_METRICS = [
        METRIC_REPORT_ALLOWED,
        METRIC_STUDENT_COUNT,
        METRIC_ENROLLED,
        METRIC_UNENROLLED,
        METRIC_COURSE_CREATED,
    ]

    @classmethod
    def _get_random_course_id(cls, course):
        """If not yet chosen, randomly select an identifier for this course."""

        all_settings = course.get_environ(course.app_context)
        course_settings = all_settings['course']
        reporting_id = course_settings.get(USAGE_REPORTING_FIELD_ID)
        if not reporting_id or reporting_id == 'None':
            reporting_id = str(uuid.uuid4())
            course_settings[USAGE_REPORTING_FIELD_ID] = reporting_id
            course.save_settings(all_settings)
        return reporting_id

    @classmethod
    def _get_random_installation_id(cls):
        """If not yet chosen, pick a random identifier for the installation."""

        cfg = _INSTALLATION_IDENTIFIER
        if not cfg.value or cfg.value == cfg.default_value:
            with common_utils.Namespace(
                appengine_config.DEFAULT_NAMESPACE_NAME):

                entity = config.ConfigPropertyEntity.get_by_key_name(cfg.name)
                if not entity:
                    entity = config.ConfigPropertyEntity(key_name=cfg.name)
                ret = str(uuid.uuid4())
                entity.value = ret
                entity.is_draft = False
                entity.put()
        else:
            ret = cfg.value
        return ret

    @classmethod
    def _get_time(cls):
        return int(time.time())

    @classmethod
    def _add_course_field(cls, message):
        if cls._COURSE not in message:
            namespace = namespace_manager.get_namespace()
            app_context = (
                sites.get_course_index().get_app_context_for_namespace(
                    namespace))
            course = courses.Course(None, app_context=app_context)
            message[cls._COURSE] = cls._get_random_course_id(course)
            cls._maybe_add_google_produced_course_info(course, message)

    @classmethod
    def _maybe_add_google_produced_course_info(cls, course, message):

        # If you would like your course to additionally report title,
        # short-name, and namespace, you may remove lines below, up
        # through and including the 'if' statement; simply leave the
        # lines from "app_context = course.app_context" and below.
        # This will also require fixing up the unit test named
        # "test_course_message_with_google_admin" in
        # tests/functional/modules_usage_reporting.py to always expect
        # these extra data.
        all_settings = course.get_environ(course.app_context)
        course_settings = all_settings['course']
        admin_email_str = course_settings.get(roles.KEY_ADMIN_USER_EMAILS)
        addrs = common_utils.text_to_list(
            admin_email_str,
            common_utils.BACKWARD_COMPATIBLE_SPLITTER)
        if addrs and all([addr.endswith('@google.com') for addr in addrs]):
            app_context = course.app_context
            message[cls._COURSE_TITLE] = app_context.get_title()
            message[cls._COURSE_SLUG] = app_context.get_slug()
            message[cls._COURSE_NAMESPACE] = app_context.get_namespace_name()

    @classmethod
    def _build_message(cls, metric, value, source, timestamp):
        if metric not in cls._ALLOWED_METRICS:
            raise ValueError('Metric name "%s" not in %s' % (
                metric, ' '.join(cls._ALLOWED_METRICS)))
        message = {
            cls._METRIC: metric,
            cls._VALUE: value,
            cls._VERSION: os.environ['GCB_PRODUCT_VERSION'],
            cls._INSTALLATION: cls._get_random_installation_id()
        }
        if source is not None:
            message[cls._SOURCE] = source
        if not timestamp:
            timestamp = cls._get_time()
        message[cls._TIMESTAMP] = timestamp
        return message

    @classmethod
    def send_course_message(cls, metric, value, source=None, timestamp=None):
        message = cls._build_message(metric, value, source, timestamp)
        cls._add_course_field(message)
        Sender.send_message(message)

    @classmethod
    def send_instance_message(cls, metric, value, source=None, timestamp=None):
        message = cls._build_message(metric, value, source, timestamp)
        Sender.send_message(message)
