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

"""Notification module.

Provides Manager.send_async, which sends notifications; and Manager.query, which
queries the current status of notifications.

Notifications are transported by email. Every message you send consumes email
quota. A message is a single payload delivered to a single user. We do not
provide the entire interface email does (no CC, BCC, attachments). Note that
messages are not sent when you call Manager.send_async(), but instead enqueued
and sent later -- usually within a minute.

This module has several advantages over using App Engine's mail.send_mail()
directly.

First, we queue and retry sending messages. This happens on two levels: first,
send_async() adds items to a task queue, which retries if there are transient
failures (like the datastore being slow, or you enqueueing more messages than
App Engine's mail service can send in a minute). Second, we provide a cron that
retries message delivery for several days, so if you exhaust your daily mail
quota today we'll try again tomorrow.

The second major advantage is that we keep a record of messages sent, so you can
do analytics on them. We provide a base set of dashboards in the admin UI
showing both overall and recent notification state.

For users who are sending mail occasionally, this module smoothes away some of
the gotchas of App Engine's mail service. However, App Engine is not optimized
to be a bulk mail delivery service, so if you need to send amounts of mail in
excess of App Engine's max daily quota (1.7M messages) or minute-by-minute quota
(5k messages), you should consider using a third-party mail delivery service.

We provide a second module that allows your users to opt out of receiving email.
We strongly encourage use of that module so you don't spam people. See
modules/unsubscribe/unsubscribe.py. The general pattern for using these modules
is:

  from common import users

  from modules.notifications import notifications
  from modules.unsubscribe import unsubscribe

  user = users.get_current_user()

  if user and not unsubscribe.has_unsubscribed(user.email):
    notifications.Manager.send_async(
        user.email, 'sender@example.com', 'intent', 'body', 'subject',
        html='<p>html</p>'
    )
"""

__author__ = [
  'johncox@google.com (John Cox)'
]

import datetime
import logging

from models import counters
from models import custom_modules
from models import entities
from models import services
from models import transforms
from models import utils
from modules.dashboard import asset_paths

from google.appengine.api import mail
from google.appengine.api import mail_errors
from google.appengine.api import taskqueue
from google.appengine.datastore import datastore_rpc
from google.appengine.ext import db
from google.appengine.ext import deferred


_LOG = logging.getLogger('modules.notifications.notifications')
logging.basicConfig()


_APP_ENGINE_MAIL_FATAL_ERRORS = frozenset([
    mail_errors.BadRequestError, mail_errors.InvalidSenderError,
])
_ENQUEUED_BUFFER_MULTIPLIER = 1.5
_KEY_DELIMITER = ':'
_MAX_ENQUEUED_HOURS = 3
_MAX_RETRY_DAYS = 3
# Number of times past which recoverable failure of send_mail() calls becomes
# hard failure. Used as a brake on runaway queues. Should be larger than the
# expected cap on the number of retries imposed by taskqueue.
_RECOVERABLE_FAILURE_CAP = 20
_SECONDS_PER_HOUR = 60 * 60
_SECONDS_PER_DAY = 24 * _SECONDS_PER_HOUR
_USECS_PER_SECOND = 10 ** 6

COUNTER_RETENTION_POLICY_RUN = counters.PerfCounter(
    'gcb-notifications-retention-policy-run',
    'number of times a retention policy was run'
)
COUNTER_SEND_ASYNC_FAILED_BAD_ARGUMENTS = counters.PerfCounter(
    'gcb-notifications-send-async-failed-bad-arguments',
    'number of times send_async failed because arguments were bad'
)
COUNTER_SEND_ASYNC_FAILED_DATASTORE_ERROR = counters.PerfCounter(
    'gcb-notifications-send-async-failed-datastore-error',
    'number of times send_async failed because of datastore error'
)
COUNTER_SEND_ASYNC_START = counters.PerfCounter(
    'gcb-notifications-send-async-called',
    'number of times send_async has been called'
)
COUNTER_SEND_ASYNC_SUCCESS = counters.PerfCounter(
    'gcb-notifications-send-async-success',
    'number of times send_async succeeded'
)
COUNTER_SEND_MAIL_TASK_FAILED = counters.PerfCounter(
    'gcb-notifications-send-mail-task-failed',
    'number of times the send mail task failed, but could be retried'
)
COUNTER_SEND_MAIL_TASK_FAILED_PERMANENTLY = counters.PerfCounter(
    'gcb-notifications-send-mail-task-failed-permanently',
    'number of times the send mail task failed permanently'
)
COUNTER_SEND_MAIL_TASK_FAILURE_CAP_EXCEEDED = counters.PerfCounter(
    'gcb-notifications-send-mail-task-recoverable-failure-cap-exceeded',
    'number of times the recoverable failure cap was exceeded'
)
COUNTER_SEND_MAIL_TASK_RECORD_FAILURE_CALLED = counters.PerfCounter(
    'gcb-notifications-send-mail-task-record-failure-called',
    'number of times _record_failure was called in the send mail task'
)
COUNTER_SEND_MAIL_TASK_RECORD_FAILURE_FAILED = counters.PerfCounter(
    'gcb-notifications-send-mail-task-record-failure-failed',
    'number of times _record_failure failed in the send mail task'
)
COUNTER_SEND_MAIL_TASK_RECORD_FAILURE_SUCCESS = counters.PerfCounter(
    'gcb-notifications-send-mail-task-record-failure-success',
    'number of times _record_failure succeeded in the send mail task'
)
COUNTER_SEND_MAIL_TASK_SENT = counters.PerfCounter(
    'gcb-notifications-send-mail-task-sent',
    'number of times the send mail task called send_mail successfully'
)
COUNTER_SEND_MAIL_TASK_SKIPPED = counters.PerfCounter(
    'gcb-notifications-send-mail-task-skipped',
    'number of times send mail task skipped sending mail'
)
COUNTER_SEND_MAIL_TASK_STARTED = counters.PerfCounter(
    'gcb-notifications-send-mail-task-started',
    'number of times the send mail task was dequeued and started')
COUNTER_SEND_MAIL_TASK_SUCCESS = counters.PerfCounter(
    'gcb-notifications-send-mail-task-success',
    'number of times send mail task completed successfully'
)


# TODO(johncox): remove suppression once stubs are implemented.
# pylint: disable=unused-argument


def _dt_to_epoch_usec(dt):
    """Converts datetime (assumed UTC) to epoch microseconds."""
    return int((_USECS_PER_SECOND) * (
        dt - datetime.datetime.utcfromtimestamp(0)).total_seconds())


def _epoch_usec_to_dt(usec):
    """Converts microseconds since epoch int to datetime (UTC, no tzinfo)."""
    return (
        datetime.datetime.utcfromtimestamp(0) +
        datetime.timedelta(microseconds=usec)
    )


class Error(Exception):
    """Base error class."""


class NotificationTooOldError(Error):
    """Recorded on a notification by cron when it's too old to re-enqueue."""


class RetentionPolicy(object):
    """Retention policy for notification data.

    Notification data is spread between the Notification and Payload objects (of
    which see below). Three parts of this data may be large:
    Notification.audit_trail, Payload.body, and Payload.html.

    We allow clients to specify a retention policy when calling
    Manager.send_async(). This retention policy is a bundle of logic applied
    after we know a notification has been sent. How and when the retention
    policy is run is up to the implementation; we make no guarantees except that
    once the notification is sent we will attempt run() at least once, and if it
    mutates its input we will attempt to apply those mutations at least once.

    Practically, it can be used to prevent retention of data in the datastore
    that is of no use to the client, even for audit purposes.

    Note that 'retention' here has nothing to do with broader user data privacy
    and retention concerns -- this is purely about responsible resource usage.

    """

    # String. Name used to identify the retention policy (in the datastore, for)
    # example.
    NAME = None

    @classmethod
    def run(cls, notification, payload):
        """Runs the policy, transforming notification and payload in place.

        run does not apply mutations to the backing datastore entities; it
        merely returns versions of those entities that we will later attempt to
        persist.  Your transforms must not touch protected fields on
        notification or payload; those are used by the subsystem, and changing
        them can violate constraints and cause unpredictable behavior and data
        corruption.

        Args:
          notification: Notification. The notification to process.
          payload: Payload. The payload to process.

        """
        pass


class RetainAll(RetentionPolicy):
    """Policy that retains all data."""

    NAME = 'all'


class RetainAuditTrail(RetentionPolicy):
    """Policy that blanks body and html but not audit trail."""

    NAME = 'audit_trail'

    @classmethod
    def run(cls, unused_notification, payload):
        payload.body = None
        payload.html = None


# Dict of string -> RetentionPolicy where key is the policy's NAME. All
# available retention policies.
_RETENTION_POLICIES = {
    RetainAll.NAME: RetainAll,
    RetainAuditTrail.NAME: RetainAuditTrail,
}


class Status(object):
    """DTO for email status."""

    FAILED = 'failed'
    PENDING = 'pending'
    SUCCEEDED = 'succeeded'
    _STATES = frozenset((FAILED, PENDING, SUCCEEDED))

    def __init__(self, to, sender, intent, enqueue_date, state):
        assert state in self._STATES

        self.enqueue_date = enqueue_date
        self.intent = intent
        self.sender = sender
        self.state = state
        self.to = to

    @classmethod
    def from_notification(cls, notification):
        state = cls.PENDING

        # Treating as module-protected. pylint: disable=protected-access
        if notification._fail_date:
            state = cls.FAILED
        elif notification._done_date:
            state = cls.SUCCEEDED

        return cls(
            notification.to, notification.sender, notification.intent,
            notification.enqueue_date, state
            )

    def __eq__(self, other):
        return (
            self.enqueue_date == other.enqueue_date and
            self.intent == other.intent and
            self.sender == other.sender and
            self.state == other.state and
            self.to == other.to
            )

    def __str__(self):
        return (
            'Status - to: %(to)s, from: %(sender)s, intent: %(intent)s, '
            'enqueued: %(enqueue_date)s, state: %(state)s' % {
                'enqueue_date': self.enqueue_date,
                'intent': self.intent,
                'sender': self.sender,
                'state': self.state,
                'to': self.to,
                })


def _accumulate_statuses(notification, results):
    for_user = results.get(notification.to, [])
    for_user.append(Status.from_notification(notification))
    results[notification.to] = for_user


class Manager(object):
    """Manages state and operation of the notifications subsystem."""

    # Treating access as module-protected. pylint: disable=protected-access

    @classmethod
    def query(cls, to, intent):
        """Gets the Status of notifications queued previously via send_async().

        Serially performs one datastore query per user in the to list.

        Args:
          to: list of string. The recipients of the notification.
          intent: string. Short string identifier of the intent of the
              notification (for example, 'invitation' or 'reminder').

        Returns:
            Dict of to string -> [Status, sorted by descending enqueue date].
        """
        results = {}

        for address in to:
            mapper = utils.QueryMapper(cls._get_query_query(address, intent))
            mapper.run(_accumulate_statuses, results)

        return results

    @classmethod
    def send_async(
            cls, to, sender, intent, body, subject, audit_trail=None,
            html=None, retention_policy=None):
        """Asyncronously sends a notification via email.

        Args:

            to: string. Recipient email address. Must have a valid form, but we
                    cannot know that the address can actually be delivered to.

            sender: string. Email address of the sender of the
                    notification. Must be a valid sender for the App Engine
                    deployment at the time the deferred send_mail() call
                    actually executes (meaning it cannot be the email address of
                    the user currently in session, because the user will not be
                    in session at call time). See
                    https://developers.google.com/appengine/docs/python/mail/emailmessagefields.
            intent: string. Short string identifier of the intent of the
                    notification (for example, 'invitation' or 'reminder'). Each
                    kind of notification you are sending should have its own
                    intent. Used when creating keys in the index; values that
                    cause the resulting key to be >500B will fail.  May not
                    contain a colon.
            body: string. The data payload of the notification as plain text.
                    Must fit in a datastore entity.
            subject: string. Subject line for the notification.
            audit_trail: JSON-serializable object. An optional audit trail that,
                    when used with the default retention policy, will be
                    retained even after the body is scrubbed from the datastore.
            html: optional string. The data payload of the notification as html.
                    Must fit in a datastore entity when combined with the plain
                    text version. Both the html and plain text body will be
                    sent, and the recipient's mail client will decide which to
                    show.
            retention_policy: RetentionPolicy. The retention policy to use for
                    data after a Notification has been sent. By default, we
                    retain the audit_trail but not the body.

        Returns:
            (notification_key, payload_key). A 2-tuple of datastore keys for the
            created notification and payload.

        Raises:
            Exception: if values delegated to model initializers are invalid.
            ValueError: if to or sender are malformed according to App Engine
                    (note that well-formed values do not guarantee success).

        """
        COUNTER_SEND_ASYNC_START.inc()
        enqueue_date = datetime.datetime.utcnow()
        retention_policy = (
            retention_policy if retention_policy else RetainAuditTrail)

        for email in (to, sender):
            if not mail.is_email_valid(email):
                COUNTER_SEND_ASYNC_FAILED_BAD_ARGUMENTS.inc()
                raise ValueError('Malformed email address: "%s"' % email)

        if retention_policy.NAME not in _RETENTION_POLICIES:
            COUNTER_SEND_ASYNC_FAILED_BAD_ARGUMENTS.inc()
            raise ValueError('Invalid retention policy: ' +
                             str(retention_policy))

        try:
            # pylint: disable=unbalanced-tuple-unpacking,unpacking-non-sequence
            notification, payload = cls._make_unsaved_models(
                audit_trail, body, enqueue_date, intent, retention_policy.NAME,
                sender, subject, to, html=html,
                )
        except Exception, e:
            COUNTER_SEND_ASYNC_FAILED_BAD_ARGUMENTS.inc()
            raise e

        cls._mark_enqueued(notification, enqueue_date)

        try:
            # pylint: disable=unbalanced-tuple-unpacking,unpacking-non-sequence
            notification_key, payload_key = cls._save_notification_and_payload(
                notification, payload,
                )
        except Exception, e:
            COUNTER_SEND_ASYNC_FAILED_DATASTORE_ERROR.inc()
            raise e

        deferred.defer(
            cls._transactional_send_mail_task, notification_key, payload_key,
            _retry_options=cls._get_retry_options())
        COUNTER_SEND_ASYNC_SUCCESS.inc()

        return notification_key, payload_key

    @classmethod
    def _make_unsaved_models(
        cls, audit_trail, body, enqueue_date, intent, retention_policy, sender,
        subject, to, html=None):
        notification = Notification(
            audit_trail=audit_trail, enqueue_date=enqueue_date, intent=intent,
            _retention_policy=retention_policy, sender=sender, subject=subject,
            to=to
        )
        payload = Payload(
            body=body, enqueue_date=enqueue_date, html=html, intent=intent,
            to=to, _retention_policy=retention_policy,
        )

        return notification, payload

    @classmethod
    @db.transactional(xg=True)
    def _save_notification_and_payload(cls, notification, payload):
        return db.put([notification, payload])

    @classmethod
    def _send_mail_task(
            cls, notification_key, payload_key, test_send_mail_fn=None):
        exception = None
        failed_permanently = False
        now = datetime.datetime.utcnow()
        # pylint: disable=unbalanced-tuple-unpacking,unpacking-non-sequence
        notification, payload = db.get([notification_key, payload_key])
        # pylint: enable=unbalanced-tuple-unpacking,unpacking-non-sequence
        send_mail_fn = (
            test_send_mail_fn if test_send_mail_fn else mail.send_mail)
        sent = False

        COUNTER_SEND_MAIL_TASK_STARTED.inc()

        if not notification:
            COUNTER_SEND_MAIL_TASK_FAILED_PERMANENTLY.inc()
            raise deferred.PermanentTaskFailure(
                'Notification missing: ' + str(notification_key)
                )

        if not payload:
            COUNTER_SEND_MAIL_TASK_FAILED_PERMANENTLY.inc()
            raise deferred.PermanentTaskFailure(
                'Payload missing: ' + str(payload_key)
                )

        policy = _RETENTION_POLICIES.get(notification._retention_policy)
        if not policy:
            COUNTER_SEND_MAIL_TASK_FAILED_PERMANENTLY.inc()
            raise deferred.PermanentTaskFailure(
                'Unknown retention policy: ' + notification._retention_policy
                )

        if (cls._done(notification) or cls._failed(notification) or
                cls._sent(notification)):
            COUNTER_SEND_MAIL_TASK_SKIPPED.inc()
            COUNTER_SEND_MAIL_TASK_SUCCESS.inc()
            return

        if notification._recoverable_failure_count > _RECOVERABLE_FAILURE_CAP:
            message = (
                'Recoverable failure cap (%s) exceeded for notification with '
                'key %s'
                ) % (_RECOVERABLE_FAILURE_CAP, str(notification.key()))
            _LOG.error(message)
            permanent_failure = deferred.PermanentTaskFailure(message)

            try:
                COUNTER_SEND_MAIL_TASK_RECORD_FAILURE_CALLED.inc()
                cls._record_failure(
                    notification, payload, permanent_failure, dt=now,
                    permanent=True, policy=policy
                    )
                COUNTER_SEND_MAIL_TASK_RECORD_FAILURE_SUCCESS.inc()
            # Must be vague. pylint: disable=broad-except
            except Exception, e:
                _LOG.error(
                    cls._get_record_failure_error_message(
                        notification, payload, e)
                    )
                COUNTER_SEND_MAIL_TASK_RECORD_FAILURE_FAILED.inc()

            COUNTER_SEND_MAIL_TASK_FAILED_PERMANENTLY.inc()
            COUNTER_SEND_MAIL_TASK_FAILURE_CAP_EXCEEDED.inc()

            raise permanent_failure

        try:
            # Avoid passing falsy kwargs to appengine's mail.py since it will
            # throw an exception.
            kwargs = {}
            if payload.html:
                kwargs['html'] = payload.html

            send_mail_fn(
                notification.sender, notification.to, notification.subject,
                payload.body, **kwargs
            )
            sent = True
        # Must be vague. pylint: disable=broad-except
        except Exception, exception:
            failed_permanently = cls._is_send_mail_error_permanent(exception)

            if not failed_permanently:

                try:
                    COUNTER_SEND_MAIL_TASK_RECORD_FAILURE_CALLED.inc()
                    cls._record_failure(notification, payload, exception)
                    COUNTER_SEND_MAIL_TASK_RECORD_FAILURE_SUCCESS.inc()
                # Must be vague. pylint: disable=broad-except
                except Exception, e:
                    _LOG.error(
                        cls._get_record_failure_error_message(
                            notification, payload, exception
                            )
                        )
                    COUNTER_SEND_MAIL_TASK_RECORD_FAILURE_FAILED.inc()

                _LOG.error(
                    ('Recoverable error encountered when processing '
                     'notification task; will retry. Error was: ' +
                     str(exception))
                )
                COUNTER_SEND_MAIL_TASK_FAILED.inc()

                # Set by except: clause above. pylint: disable=raising-bad-type
                raise exception

        if sent:
            cls._mark_sent(notification, now)

        if failed_permanently:
            cls._mark_failed(notification, now, exception, permanent=True)

        if sent or failed_permanently:
            policy.run(notification, payload)
            cls._mark_done(notification, now)

        db.put([notification, payload])

        COUNTER_RETENTION_POLICY_RUN.inc()

        if sent:
            COUNTER_SEND_MAIL_TASK_SENT.inc()
        elif failed_permanently:
            COUNTER_SEND_MAIL_TASK_FAILED_PERMANENTLY.inc()

        COUNTER_SEND_MAIL_TASK_SUCCESS.inc()

    @classmethod
    @db.transactional(
            propagation=datastore_rpc.TransactionOptions.INDEPENDENT, xg=True)
    def _record_failure(
            cls, notification, payload, exception, dt=None, permanent=False,
            policy=None):
        """Marks failure data on entities in an external transaction.

        IMPORTANT: because we're using
        datastore_rpc.TransactionOptions.INDEPENDENT, mutations on notification
        and payload here are *not* transactionally consistent in the caller.
        Consequently, callers must not read or mutate them after calling this
        method.

        The upside is that this allows us to record failure data on entities
        inside a transaction, and that transaction can throw without rolling
        back these mutations.

        Args:
            notification: Notification. The notification to mutate.
            payload: Payload. The payload to mutate.
            exception: Exception. The exception that prompted the mutation.
            dt: datetime. notification_fail_time and notification._done_time
                    to record if permanent is True.
            permanent: boolean. If True, the notification will be marked done
                    and the retention policy will be run.
            policy: RetentionPolicy. The retention policy to apply if permanent
                    was True.

        Returns:
            (notification_key, payload_key) 2-tuple.

        """
        notification._recoverable_failure_count += 1
        cls._mark_failed(notification, dt, exception, permanent=permanent)

        if permanent:
            assert dt and policy

            cls._mark_done(notification, dt)
            policy.run(notification, payload)
            COUNTER_RETENTION_POLICY_RUN.inc()

        return db.put([notification, payload])

    @classmethod
    def _get_record_failure_error_message(
        cls, notification, payload, exception):
        return (
            'Unable to record failure for notification with key %s and payload '
            'with key %s; encountered %s error with text: "%s"') % (
                str(notification.key()), str(payload.key()),
                exception.__class__.__name__, str(exception))

    @classmethod
    def _transactional_send_mail_task(cls, notification_key, payload_key):
        # Can't use decorator because of taskqueue serialization.
        db.run_in_transaction_options(
            db.create_transaction_options(xg=True), cls._send_mail_task,
            notification_key, payload_key)

    @classmethod
    def _done(cls, notification):
        return bool(notification._done_date)

    @classmethod
    def _failed(cls, notification):
        return bool(notification._fail_date)

    @classmethod
    def _get_in_process_notifications_query(cls):
        return Notification.all(
        ).filter(
            '%s =' % Notification._done_date.name, None
        ).order(
            '-' + Notification.enqueue_date.name
        )

    @classmethod
    def _get_query_query(cls, to, intent):
        return Notification.all(
        ).filter(
            Notification.to.name, to
        ).filter(
            Notification.intent.name, intent
        ).order(
            '-' + Notification.enqueue_date.name
        )

    @classmethod
    def _get_last_exception_value(cls, exception):
        return {
            'type': '%s.%s' % (
                exception.__class__.__module__, exception.__class__.__name__),
            'string': str(exception),
            }

    @classmethod
    def _get_retry_options(cls):
        # Retry up to once every hour with exponential backoff; limit tasks to
        # three hours; cron will re-enqueue them for days. This is because the
        # purpose of the queue is retrying in case of transient errors
        # (datastore or send_mail burbles), and the purpose of the cron is
        # retrying in case of longer errors (quota exhaustion).
        return taskqueue.TaskRetryOptions(
            min_backoff_seconds=1, max_backoff_seconds=_SECONDS_PER_HOUR,
            max_doublings=12,    # Overflow task age limit; don't want underflow
            task_age_limit=cls._get_task_age_limit_seconds(),
            )

    @classmethod
    def _get_task_age_limit_seconds(cls):
        return _MAX_ENQUEUED_HOURS * _SECONDS_PER_HOUR

    @classmethod
    def _is_too_old_to_reenqueue(cls, dt, now):
        return now - dt > datetime.timedelta(days=_MAX_RETRY_DAYS)

    @classmethod
    def _is_send_mail_error_permanent(cls, exception):
        return type(exception) in _APP_ENGINE_MAIL_FATAL_ERRORS

    @classmethod
    def _is_still_enqueued(cls, notification, dt):
        """Whether or not an item is still on the deferred queue.

        This isn't exact -- we can't query the queue. We can know how long items
        can be on the queue, so we can make a guess. Our guess has false
        positives: there is clock skew between datastore and taskqueue, and
        false negatives are terrible because they cause multiple messages to get
        sent. Consequently, we consider items that were last enqueued slightly
        too long ago to still be on the queue. This can cause re-enqueueing of
        some items to get delayed by one cron interval. We ameliorate this a bit
        by checking for side-effects of the dequeue (_done|fail|send_date set).

        Args:
            notification: Notification. The notification to check status of.
            dt: datetime, assumed UTC. The datetime to check enqueued status at.

        Returns:
            Boolean. False if the item has never been enqueued, or was enqueued
            long enough ago we're sure it's no longer on the queue, or has
            already been processed (indicating it's been enqueued and
            dequeued). True otherwise.

        """
        if (notification._done_date or notification._fail_date or
            notification._send_date) or not notification._last_enqueue_date:
            return False

        return cls._get_task_age_limit_seconds() > (
            ((dt - notification._last_enqueue_date).total_seconds() *
             _ENQUEUED_BUFFER_MULTIPLIER)
        )

    @classmethod
    def _mark_done(cls, notification, dt):
        notification._done_date = dt

    @classmethod
    def _mark_enqueued(cls, notification, dt):
        notification._last_enqueue_date = dt

    @classmethod
    def _mark_failed(cls, notification, dt, exception, permanent=False):
        notification._last_exception = cls._get_last_exception_value(exception)

        if permanent:
            notification._fail_date = dt

    @classmethod
    def _mark_sent(cls, notification, dt):
        notification._send_date = dt

    @classmethod
    def _sent(cls, notification):
        return bool(notification._send_date)


class _IntentProperty(db.StringProperty):
    """Property that holds intent strings."""

    @classmethod
    def _get_message(cls, value):
        return 'Intent "%s" cannot contain "%s"' % (value, _KEY_DELIMITER)

    @classmethod
    def check(cls, value):
        if _KEY_DELIMITER in value:
            raise ValueError(cls._get_message(value))

    def validate(self, value):
        value = super(_IntentProperty, self).validate(value)

        try:
            self.check(value)
        except ValueError:
            raise db.BadValueError(self._get_message(value))

        return value


class _SerializedProperty(db.Property):
    """Custom property that stores JSON-serialized data."""

    def __init__(self, *args, **kwargs):
        # Disallow indexing and explicitly set indexed=False. If indexed is
        # unset it defaults to True; if True, it imposes a 500 byte limit on the
        # value, and longer values throw during db.put(). We want to support
        # larger values rather than searching, and we do not want this to be a
        # TextProperty because the underlying type is not db.Text.
        if kwargs.get('indexed'):
            raise ValueError('_SerializedProperty does not support indexing')

        kwargs['indexed'] = False
        super(_SerializedProperty, self).__init__(*args, **kwargs)

    def get_value_for_datastore(self, model_instance):
        return transforms.dumps(super(
            _SerializedProperty, self
        ).get_value_for_datastore(model_instance))

    def make_value_from_datastore(self, value):
        return transforms.loads(value)

    def validate(self, value):
        value = super(_SerializedProperty, self).validate(value)
        try:
            transforms.dumps(value)
        except TypeError, e:
            raise db.BadValueError(
                '%s is not JSON-serializable; error was "%s"' % (value, e))

        return value


class _Model(entities.BaseEntity):
    """Abstract base model that handles key calculation."""

    # String. Template used in key generation.
    _KEY_TEMPLATE = (
        '(%(kind)s%(delim)s%(to)s%(delim)s%(intent)s%(delim)s%(enqueue_date)s)'
    )

    # When the record was enqueued in client code.
    enqueue_date = db.DateTimeProperty(required=True)
    # String indicating the intent of the notification. Intents are used to
    # group and index notifications. Used in key formation; may not contain a
    # colon.
    intent = _IntentProperty(required=True)
    # Email address used to compose the To:. May house only one value. Subject
    # to the restrictions of the underlying App Engine mail library; see the to
    # field in
    # https://developers.google.com/appengine/docs/python/mail/emailmessagefields.
    to = db.StringProperty(required=True)

    # When the record was last changed.
    _change_date = db.DateTimeProperty(auto_now=True, required=True)
    # RetentionPolicy.NAME string. Identifier for the retention policy for the
    # Payload.
    _retention_policy = db.StringProperty(
            required=True, choices=_RETENTION_POLICIES.keys())

    def __init__(self, *args, **kwargs):
        assert 'key_name' not in kwargs, (
            'Setting key_name manually not supported')
        kwargs['key_name'] = self.key_name(
            self._require_kwarg('to', kwargs),
            self._require_kwarg('intent', kwargs),
            self._require_kwarg('enqueue_date', kwargs))
        super(_Model, self).__init__(*args, **kwargs)

    @classmethod
    def key_name(cls, to, intent, enqueue_date):
        _IntentProperty.check(intent)

        return cls._KEY_TEMPLATE % {
            'delim': _KEY_DELIMITER,
            'enqueue_date': _dt_to_epoch_usec(enqueue_date),
            'intent': intent,
            'kind': cls.kind().lower(),
            'to': to,
            }

    @classmethod
    def safe_key(cls, db_key, transform_fn):
        _, unsafe_to, intent, serialized_dt = cls._split_key_name(db_key.name())

        return db.Key.from_path(
            cls.kind(), cls.key_name(
                transform_fn(unsafe_to), intent,
                _epoch_usec_to_dt(int(serialized_dt))))

    @classmethod
    def _split_key_name(cls, key_name):
        return key_name[1:-1].split(_KEY_DELIMITER)

    def _require_kwarg(self, name, kwargs):
        """Gets kwarg with given name or dies."""
        value = kwargs.get(name)
        assert value, 'Missing required property: ' + name

        return value


class Notification(_Model):

    # Audit trail of JSON-serializable data. By default Payload.body
    # and Payload.html are deleted when they are no longer needed.
    # If you need information for audit purposes,
    # pass it here, and the default retention policy will keep it.
    audit_trail = _SerializedProperty()
    # Email address used to compose the From:. Subject to the sender
    # restrictions of the underlying App Engine mail library; see the sender
    # field in
    # https://developers.google.com/appengine/docs/python/mail/emailmessagefields.
    sender = db.StringProperty(required=True)
    # Subject line of the notification.
    subject = db.TextProperty(required=True)

    # When processing the record fully finished, meaning that the record will
    # never be processed by the notification subsystem again. None if the record
    # is still in flight. Indicates that the record has either succeeded or
    # failed and its retention policy has been applied.
    _done_date = db.DateTimeProperty()
    # When processing of the record failed and will no longer be retried. None
    # if this has not happened. Does not indicated the retention policy has been
    # applied; see _done_date.
    _fail_date = db.DateTimeProperty()
    # When the notification was last placed on the deferred queue.
    _last_enqueue_date = db.DateTimeProperty()
    # JSON representation of the last recordable exception encountered while
    # processing the notification. Format is
    # {'type': type_str, 'string': str(exception)}.
    _last_exception = _SerializedProperty()
    # Number of recoverable failures we've had for this notification.
    _recoverable_failure_count = db.IntegerProperty(required=True, default=0)
    # When a send_mail # call finshed for the record and we recorded it in the
    # datastore. May be None if this has not yet happend. Does not indicate the
    # retention policy has been applied; see _done_date.
    _send_date = db.DateTimeProperty()

    _PROPERTY_EXPORT_BLACKLIST = [audit_trail, _last_exception, subject]

    def for_export(self, transform_fn):
        model = super(Notification, self).for_export(transform_fn)
        model.to = transform_fn(model.to)
        model.sender = transform_fn(model.sender)
        return model


class Payload(_Model):
    """The data payload of a Notification.

    We extract this data from Notification to increase the total size budget
    available to the user, which is capped at 1MB/entity.
    """

    # Body of the payload.
    body = db.TextProperty()
    html = db.TextProperty()

    _PROPERTY_EXPORT_BLACKLIST = [body, html]

    def __init__(self, *args, **kwargs):
        super(Payload, self).__init__(*args, **kwargs)
        _IntentProperty().validate(kwargs.get('intent'))


custom_module = None


def register_module():
    """Registers the module with the Registry."""

    def on_module_enabled():
        asset_paths.AllowedBases.add_text_base('views/notifications')

    global custom_module  # pylint: disable=global-statement

    # Avert circular dependency. pylint: disable=g-import-not-at-top
    from modules.notifications import cron
    from modules.notifications import stats

    stats.register_analytic()
    cron_handlers = [(
            '/cron/process_pending_notifications',
            cron.ProcessPendingNotificationsHandler
    )]
    custom_module = custom_modules.Module(
        'Notifications', 'Student notification management system.',
        cron_handlers,
        [],
        notify_module_enabled=on_module_enabled
    )

    class Service(services.Notifications):

        def enabled(self):
            return custom_module.enabled

        def query(self, to, intent):
            return Manager.query(to, intent)

        def send_async(
            self, to, sender, intent, body, subject, audit_trail=None,
            html=None, retention_policy=None):
            return Manager.send_async(
                to, sender, intent, body, subject, audit_trail=audit_trail,
                html=html, retention_policy=retention_policy)

    services.notifications = Service()
    return custom_module
