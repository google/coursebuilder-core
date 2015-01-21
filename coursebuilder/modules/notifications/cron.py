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

"""Notification subsystem background jobs."""

__author__ = [
    'johncox@google.com (John Cox)',
]

import datetime
import logging

from common import utils as common_utils
from controllers import sites
from controllers import utils as controllers_utils
from models import utils as model_utils
from modules.notifications import notifications

from google.appengine.ext import db
from google.appengine.ext import deferred


_LOG = logging.getLogger('modules.notifications.cron')
logging.basicConfig()


@db.transactional(xg=True)
def process_notification(notification, now, stats):
    notification_key = notification.key()
    policy = None
    stats.started += 1

    # Treat as module-protected. pylint: disable=protected-access
    if notification._done_date:
        _LOG.info(
            'Skipping offline processing of notification with key %s; already '
            'done at %s', notification_key, notification._done_date
            )
        stats.skipped_already_done += 1
        return

    if notifications.Manager._is_still_enqueued(notification, now):
        _LOG.info(
            'Skipping offline processing of notification with key %s; still on '
            'queue (last enqueued: %s)', notification_key,
            notification._last_enqueue_date)
        stats.skipped_still_enqueued += 1
        return

    payload_key = db.Key.from_path(
        notifications.Payload.kind(),
        notifications.Payload.key_name(
            notification.to, notification.intent, notification.enqueue_date)
        )
    payload = db.get(payload_key)

    if not payload:
        _LOG.error(
            'Could not process notification with key %s; associated payload '
            'with key %s not found', notification_key, payload_key
        )
        stats.missing_payload += 1
        return

    if notifications.Manager._is_too_old_to_reenqueue(
        notification.enqueue_date, now):

        stats.too_old += 1
        exception = notifications.NotificationTooOldError((
            'Notification %s with enqueue_date %s too old to re-enqueue at %s; '
            'limit is %s days') % (
                notification_key, notification.enqueue_date, now,
                notifications._MAX_RETRY_DAYS,
        ))
        notifications.Manager._mark_failed(
            notification, now, exception, permanent=True)

    if notification._fail_date or notification._send_date:
        policy = notifications._RETENTION_POLICIES.get(
            notification._retention_policy)
        notifications.Manager._mark_done(notification, now)

        if policy:
            policy.run(notification, payload)
            stats.policy_run += 1
        else:
            _LOG.warning(
                'Cannot apply retention policy %s to notification %s and '
                'payload %s; policy not found. Existing policies are: %s',
                notification._retention_policy, notification_key, payload_key,
                ', '.join(sorted(notifications._RETENTION_POLICIES.keys()))
                )
            stats.missing_policy += 1
        db.put([notification, payload])
    else:
        notifications.Manager._mark_enqueued(notification, now)
        db.put(notification)
        deferred.defer(
            notifications.Manager._transactional_send_mail_task,
            notification_key, payload_key,
            _retry_options=notifications.Manager._get_retry_options()
            )
        stats.reenqueued += 1


class _Stats(object):

    def __init__(self, namespace):
        self.missing_payload = 0
        self.missing_policy = 0
        self.namespace = namespace
        self.policy_run = 0
        self.reenqueued = 0
        self.skipped_already_done = 0
        self.skipped_still_enqueued = 0
        self.started = 0
        self.too_old = 0

    def __str__(self):
        return (
            'Stats for namespace "%(namespace)s":'
            '\n\tmissing_payload: %(missing_payload)s'
            '\n\tmissing_policy: %(missing_policy)s'
            '\n\tpolicy_run: %(policy_run)s'
            '\n\tre-enqueued: %(reenqueued)s'
            '\n\tskipped_already_done: %(skipped_already_done)s'
            '\n\tskipped_still_enqueued: %(skipped_still_enqueued)s'
            '\n\tstarted: %(started)s'
            '\n\ttoo_old: %(too_old)s'
            ) % self.__dict__


class ProcessPendingNotificationsHandler(controllers_utils.BaseHandler):
    """Iterates through all courses, re-enqueueing or expiring pending items.

    Only one of these jobs runs at any given time. This is enforced by App
    Engine's 10 minute limit plus scheduling this to run daily.

    However, write operations here must still be atomic because admins could
    manually visit the handler at any time.
    """

    def get(self):
        self.response.headers['Content-Type'] = 'text/plain'
        namespaces = [
            context.get_namespace_name() for context in sites.get_all_courses()
        ]
        now = datetime.datetime.utcnow()
        _LOG.info(
            'Begin process_pending_notifications cron; found namespaces %s at '
            '%s', ', '.join(["'%s'" % n for n in namespaces]), now
        )

        for namespace in namespaces:
            stats = _Stats(namespace)
            _LOG.info("Begin processing notifications for namespace '%s'",
                      namespace)
            self._process_records(namespace, now, stats)
            _LOG.info('Done processing. %s', stats)

    def _process_records(self, namespace, now, stats):
        with common_utils.Namespace(namespace):
            # Treating as module-protected. pylint: disable=protected-access
            mapper = model_utils.QueryMapper(
                notifications.Manager._get_in_process_notifications_query())
            mapper.run(process_notification, now, stats)
