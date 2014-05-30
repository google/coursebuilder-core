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

"""Functional tests for the notifications module."""

__author__ = [
    'johncox@google.com (John Cox)'
]

import datetime
import types

from models import config
from models import counters
from modules.notifications import cron
from modules.notifications import notifications
from tests.functional import actions

from google.appengine.api import mail_errors
from google.appengine.ext import db
from google.appengine.ext import deferred


# Allow access to code under test. pylint: disable-msg=protected-access


class UnregisteredRetentionPolicy(notifications.RetentionPolicy):
  NAME = 'unregistered'


class CronTest(actions.TestBase):
  """Tests notifications/cron.py."""

  def setUp(self):
    super(CronTest, self).setUp()
    self.now = datetime.datetime.utcnow()
    self.old_retention_policies = dict(notifications._RETENTION_POLICIES)

    self.audit_trail = {'key': 'value'}
    self.body = 'body'
    self.intent = 'intent'
    self.to = 'to@example.com'
    self.sender = 'sender@example.com'
    self.stats = cron._Stats('namespace')
    self.subject = 'subject'

  def tearDown(self):
    config.Registry.test_overrides.clear()
    counters.Registry._clear_all()
    notifications._RETENTION_POLICIES = self.old_retention_policies
    super(CronTest, self).tearDown()

  def assert_task_enqueued(self):
    self.assertEqual(1, len(self.taskq.GetTasks('default')))

  def assert_task_not_enqueued(self):
    self.assertEqual(0, len(self.taskq.GetTasks('default')))

  def test_process_notification_enqueues_notification_correctly(self):
    notification_key, _ = db.put(
        notifications.Manager._make_unsaved_models(
            self.audit_trail, self.body, self.now, self.intent,
            notifications.RetainAuditTrail.NAME, self.sender, self.subject,
            self.to,
        )
    )
    cron.process_notification(db.get(notification_key), self.now, self.stats)

    self.assert_task_enqueued()

    self.execute_all_deferred_tasks()

    self.assertTrue(db.get(notification_key)._done_date)
    self.assertEqual(1, self.stats.started)
    self.assertEqual(1, self.stats.reenqueued)

  def test_process_notification_if_fail_date_set_and_policy_found(self):
    notification_key, payload_key = db.put(
        notifications.Manager._make_unsaved_models(
            self.audit_trail, self.body, self.now, self.intent,
            notifications.RetainAuditTrail.NAME, self.sender, self.subject,
            self.to,
        )
    )
    notification = db.get(notification_key)
    notification._fail_date = self.now
    notification.put()
    cron.process_notification(db.get(notification_key), self.now, self.stats)
    notification, payload = db.get([notification_key, payload_key])

    self.assert_task_not_enqueued()
    self.assertTrue(notification._done_date)
    self.assertFalse(payload.body)  # RetainAuditTrail applied.
    self.assertEqual(0, self.stats.missing_policy)
    self.assertEqual(1, self.stats.policy_run)
    self.assertEqual(1, self.stats.started)

  def test_process_notification_if_fail_date_set_and_policy_missing(self):
    notification_key, payload_key = db.put(
        notifications.Manager._make_unsaved_models(
            self.audit_trail, self.body, self.now, self.intent,
            notifications.RetainAuditTrail.NAME, self.sender, self.subject,
            self.to,
        )
    )
    notification = db.get(notification_key)
    notification._fail_date = self.now
    notification.put()
    notifications._RETENTION_POLICIES.pop(notifications.RetainAuditTrail.NAME)
    cron.process_notification(db.get(notification_key), self.now, self.stats)
    notification, payload = db.get([notification_key, payload_key])

    self.assert_task_not_enqueued()
    self.assertTrue(notification._done_date)
    self.assertTrue(payload.body)  # RetainAuditTrail not applied.
    self.assertEqual(0, self.stats.policy_run)
    self.assertEqual(0, self.stats.reenqueued)
    self.assertEqual(1, self.stats.started)

  def test_process_notification_if_notification_too_old(self):
    too_old = self.now - datetime.timedelta(
        days=notifications._MAX_RETRY_DAYS, seconds=1)
    notification_key, payload_key = db.put(
        notifications.Manager._make_unsaved_models(
            self.audit_trail, self.body, too_old, self.intent,
            notifications.RetainAuditTrail.NAME, self.sender, self.subject,
            self.to,
        )
    )
    cron.process_notification(db.get(notification_key), self.now, self.stats)
    notification, payload = db.get([notification_key, payload_key])

    self.assert_task_not_enqueued()
    self.assertTrue(notification._done_date)
    self.assertTrue(notification._fail_date)
    self.assertIn(
        'NotificationTooOldError', notification._last_exception['type'])
    self.assertIsNone(payload.body)  # RetainAuditTrail applied.
    self.assertEqual(1, self.stats.policy_run)
    self.assertEqual(1, self.stats.started)
    self.assertEqual(1, self.stats.too_old)

  def test_process_notification_if_payload_missing(self):
    notification_key, payload_key = db.put(
        notifications.Manager._make_unsaved_models(
            self.audit_trail, self.body, self.now, self.intent,
            notifications.RetainAuditTrail.NAME, self.sender, self.subject,
            self.to,
        )
    )
    db.delete(payload_key)
    cron.process_notification(db.get(notification_key), self.now, self.stats)

    self.assert_task_not_enqueued()
    self.assertEqual(1, self.stats.missing_payload)
    self.assertEqual(1, self.stats.started)

  def test_process_notification_if_send_date_set_and_policy_missing(self):
    notification_key, payload_key = db.put(
        notifications.Manager._make_unsaved_models(
            self.audit_trail, self.body, self.now, self.intent,
            notifications.RetainAuditTrail.NAME, self.sender, self.subject,
            self.to,
        )
    )
    notification = db.get(notification_key)
    notification._send_date = self.now
    notification.put()
    notifications._RETENTION_POLICIES.pop(notifications.RetainAuditTrail.NAME)
    cron.process_notification(db.get(notification_key), self.now, self.stats)
    notification, payload = db.get([notification_key, payload_key])

    self.assert_task_not_enqueued()
    self.assertTrue(notification._done_date)
    self.assertTrue(payload.body)  # RetainAuditTrail not applied.
    self.assertEqual(1, self.stats.missing_policy)
    self.assertEqual(0, self.stats.policy_run)
    self.assertEqual(1, self.stats.started)

  def test_process_notification_if_send_date_set_and_policy_found(self):
    notification_key, payload_key = db.put(
        notifications.Manager._make_unsaved_models(
            self.audit_trail, self.body, self.now, self.intent,
            notifications.RetainAuditTrail.NAME, self.sender, self.subject,
            self.to,
        )
    )
    notification = db.get(notification_key)
    notification._send_date = self.now
    notification.put()
    cron.process_notification(db.get(notification_key), self.now, self.stats)
    notification, payload = db.get([notification_key, payload_key])

    self.assert_task_not_enqueued()
    self.assertTrue(notification._done_date)
    self.assertFalse(payload.body)  # RetainAuditTrail applied.
    self.assertEqual(0, self.stats.missing_policy)
    self.assertEqual(1, self.stats.policy_run)
    self.assertEqual(1, self.stats.started)

  def test_process_notification_skips_if_already_done(self):
    notification_key, _ = db.put(
        notifications.Manager._make_unsaved_models(
            self.audit_trail, self.body, self.now, self.intent,
            notifications.RetainAuditTrail.NAME, self.sender, self.subject,
            self.to,
        )
    )
    notification = db.get(notification_key)
    notification._done_date = self.now
    notification.put()
    cron.process_notification(db.get(notification_key), self.now, self.stats)

    self.assert_task_not_enqueued()
    self.assertEqual(1, self.stats.skipped)
    self.assertEqual(1, self.stats.started)


class DatetimeConversionTest(actions.TestBase):

  def test_utc_datetime_round_trips_correctly(self):
    dt_with_usec = datetime.datetime(2000, 1, 1, 1, 1, 1, 1)

    self.assertEqual(
      dt_with_usec,
      notifications._epoch_usec_to_dt(
          notifications._dt_to_epoch_usec(dt_with_usec)))


class ManagerTest(actions.TestBase):

  def setUp(self):
    super(ManagerTest, self).setUp()
    self.now = datetime.datetime.utcnow()
    self.old_retention_policies = dict(notifications._RETENTION_POLICIES)

    self.audit_trail = {'key': 'value'}
    self.body = 'body'
    self.intent = 'intent'
    self.to = 'to@example.com'
    self.sender = 'sender@example.com'
    self.subject = 'subject'

  def tearDown(self):
    config.Registry.test_overrides.clear()
    counters.Registry._clear_all()
    notifications._RETENTION_POLICIES = self.old_retention_policies
    super(ManagerTest, self).tearDown()

  def test_get_in_process_notifications_query(self):
    exact_cutoff = self.now - datetime.timedelta(
        days=notifications._MAX_RETRY_DAYS)
    already_done = notifications.Notification(
        enqueue_date=exact_cutoff, to=self.to, intent=self.intent,
        _done_date=exact_cutoff,
        _retention_policy=notifications.RetainAuditTrail.NAME,
        sender=self.sender, subject=self.subject)
    oldest_match = notifications.Notification(
        enqueue_date=exact_cutoff - datetime.timedelta(seconds=1), to=self.to,
        intent=self.intent,
        _retention_policy=notifications.RetainAuditTrail.NAME,
        sender=self.sender, subject=self.subject)
    newest_match = notifications.Notification(
        enqueue_date=exact_cutoff, to=self.to, intent=self.intent,
        _retention_policy=notifications.RetainAuditTrail.NAME,
        sender=self.sender, subject=self.subject
    )
    db.put([already_done, oldest_match, newest_match])
    found = notifications.Manager._get_in_process_notifications_query().fetch(
        10
    )

    self.assertEqual(
        [newest_match.key(), oldest_match.key()],
        [match.key() for match in found]
    )

  def test_is_too_old_to_reenqueue(self):
    newer = self.now - datetime.timedelta(
        days=notifications._MAX_RETRY_DAYS - 1)
    equal = self.now - datetime.timedelta(days=notifications._MAX_RETRY_DAYS)
    older = self.now - datetime.timedelta(
        days=notifications._MAX_RETRY_DAYS + 1)

    self.assertFalse(
        notifications.Manager._is_too_old_to_reenqueue(newer, self.now)
    )
    self.assertFalse(
        notifications.Manager._is_too_old_to_reenqueue(equal, self.now)
    )
    self.assertTrue(
        notifications.Manager._is_too_old_to_reenqueue(older, self.now)
    )

  def test_send_async_with_defaults_set_initial_state_and_can_run_tasks(self):
    notification_key, payload_key = notifications.Manager.send_async(
        self.to, self.sender, self.intent, self.body, self.subject
    )
    notification, payload = db.get([notification_key, payload_key])

    self.assertIsNone(notification.audit_trail)
    self.assertTrue(notification.enqueue_date)
    self.assertEqual(self.intent, notification.intent)
    self.assertEqual(self.sender, notification.sender)
    self.assertEqual(self.subject, notification.subject)
    self.assertEqual(self.to, notification.to)

    self.assertTrue(notification._change_date)
    self.assertIsNone(notification._done_date)
    self.assertIsNone(notification._fail_date)
    self.assertIsNone(notification._last_exception)
    self.assertEqual(
        notifications.RetainAuditTrail.NAME, notification._retention_policy)
    self.assertIsNone(notification._send_date)

    self.assertEqual(notification.enqueue_date, payload.enqueue_date)
    self.assertEqual(self.intent, payload.intent)
    self.assertEqual(self.to, payload.to)

    self.assertEqual(self.body, payload.body)
    self.assertTrue(payload._change_date)
    self.assertEqual(
        notifications.RetainAuditTrail.NAME, payload._retention_policy)

    self.assertEqual(1, len(self.taskq.GetTasks('default')))
    self.execute_all_deferred_tasks()
    messages = self.get_mail_stub().get_sent_messages()
    self.assertEqual(1, len(messages))

    self.assertIsNone(db.get(payload_key).body)  # Ran default policy.

    self.assertEqual(1, notifications.COUNTER_RETENTION_POLICY_RUN.value)
    self.assertEqual(0, notifications.COUNTER_SEND_MAIL_TASK_FAILED.value)
    self.assertEqual(
        0, notifications.COUNTER_SEND_MAIL_TASK_FAILED_PERMANENTLY.value)
    self.assertEqual(1, notifications.COUNTER_SEND_MAIL_TASK_SENT.value)
    self.assertEqual(0, notifications.COUNTER_SEND_MAIL_TASK_SKIPPED.value)
    self.assertEqual(1, notifications.COUNTER_SEND_MAIL_TASK_STARTED.value)
    self.assertEqual(1, notifications.COUNTER_SEND_MAIL_TASK_SUCCESS.value)

  def test_send_async_with_overrides_sets_initial_state_and_can_run_tasks(self):
    notification_key, payload_key = notifications.Manager.send_async(
        self.to, self.sender, self.intent, self.body, self.subject,
        audit_trail=self.audit_trail, retention_policy=notifications.RetainAll,
    )
    notification, payload = db.get([notification_key, payload_key])

    self.assertEqual(self.audit_trail, notification.audit_trail)
    self.assertTrue(notification.enqueue_date)
    self.assertEqual(self.intent, notification.intent)
    self.assertEqual(self.sender, notification.sender)
    self.assertEqual(self.subject, notification.subject)
    self.assertEqual(self.to, notification.to)

    self.assertTrue(notification._change_date)
    self.assertIsNone(notification._done_date)
    self.assertIsNone(notification._fail_date)
    self.assertIsNone(notification._last_exception)
    self.assertEqual(
        notifications.RetainAll.NAME, notification._retention_policy)
    self.assertIsNone(notification._send_date)

    self.assertEqual(notification.enqueue_date, payload.enqueue_date)
    self.assertEqual(self.intent, payload.intent)
    self.assertEqual(self.to, payload.to)

    self.assertEqual(self.body, payload.body)
    self.assertTrue(payload._change_date)
    self.assertEqual(notifications.RetainAll.NAME, payload._retention_policy)

    self.assertEqual(1, len(self.taskq.GetTasks('default')))
    self.execute_all_deferred_tasks()
    messages = self.get_mail_stub().get_sent_messages()
    self.assertEqual(1, len(messages))

    self.assertEqual(self.body, db.get(payload_key).body)  # Policy override.

    self.assertEqual(1, notifications.COUNTER_RETENTION_POLICY_RUN.value)
    self.assertEqual(0, notifications.COUNTER_SEND_MAIL_TASK_FAILED.value)
    self.assertEqual(
        0, notifications.COUNTER_SEND_MAIL_TASK_FAILED_PERMANENTLY.value)
    self.assertEqual(1, notifications.COUNTER_SEND_MAIL_TASK_SENT.value)
    self.assertEqual(0, notifications.COUNTER_SEND_MAIL_TASK_SKIPPED.value)
    self.assertEqual(1, notifications.COUNTER_SEND_MAIL_TASK_STARTED.value)
    self.assertEqual(1, notifications.COUNTER_SEND_MAIL_TASK_SUCCESS.value)

  def test_send_async_raises_exception_if_datastore_errors(self):

    def throw(unused_self, unused_notification, unused_payload):
      raise db.Error('thrown')

    bound_throw = types.MethodType(
        throw, notifications.Manager(), notifications.Manager)
    self.swap(
        notifications.Manager, '_save_notification_and_payload', bound_throw
    )

    with self.assertRaisesRegexp(db.Error, 'thrown'):
      notifications.Manager.send_async(
          self.to, self.sender, self.intent, self.body, self.subject,
      )

  def test_send_async_raises_exception_if_models_cannot_be_made(self):
    bad_audit_trail = self.now
    with self.assertRaisesRegexp(db.BadValueError, 'not JSON-serializable'):
      notifications.Manager.send_async(
          self.to, self.sender, self.intent, self.body, self.subject,
          audit_trail=bad_audit_trail,
      )

  def test_send_async_raises_value_error_if_retention_policy_missing(self):
    self.assertNotIn(
        UnregisteredRetentionPolicy.NAME, notifications._RETENTION_POLICIES)

    with self.assertRaisesRegexp(ValueError, 'Invalid retention policy: '):
      notifications.Manager.send_async(
          self.to, self.sender, self.intent, self.body, self.subject,
          retention_policy=UnregisteredRetentionPolicy,
      )

  def test_send_async_raises_value_error_if_sender_invalid(self):
    # App Engine's validator is not comprehensive, but blank is bad.
    invalid_sender = ''

    with self.assertRaisesRegexp(ValueError, 'Malformed email address: ""'):
      notifications.Manager.send_async(
          self.to, invalid_sender, self.intent, self.body, self.subject,
      )

  def test_send_async_raises_value_error_if_to_invalid(self):
    # App Engine's validator is not comprehensive, but blank is bad.
    invalid_to = ''

    with self.assertRaisesRegexp(ValueError, 'Malformed email address: ""'):
      notifications.Manager.send_async(
          invalid_to, self.sender, self.intent, self.body, self.subject,
      )

  def test_send_mail_task_fails_permanently_and_marks_entities_if_cap_hit(self):
    over_cap = notifications._RECOVERABLE_FAILURE_CAP + 1
    notification_key, payload_key = db.put(
        notifications.Manager._make_unsaved_models(
            self.audit_trail, self.body, self.now, self.intent,
            notifications.RetainAuditTrail.NAME, self.sender, self.subject,
            self.to,
        )
    )
    notification = db.get(notification_key)
    notification._recoverable_failure_count = over_cap
    notification.put()

    with self.assertRaisesRegexp(
        deferred.PermanentTaskFailure, 'Recoverable failure cap'):
      notifications.Manager._send_mail_task(notification_key, payload_key)

    notification, payload = db.get([notification_key, payload_key])

    self.assertIsNotNone(notification._done_date)
    self.assertEqual(notification._done_date, notification._fail_date)
    self.assertIn(
        'Recoverable failure cap', notification._last_exception['string'])
    self.assertEqual(over_cap + 1, notification._recoverable_failure_count)
    self.assertIsNone(payload.body)  # Policy applied.

    self.assertEqual(1, notifications.COUNTER_RETENTION_POLICY_RUN.value)
    self.assertEqual(0, notifications.COUNTER_SEND_MAIL_TASK_FAILED.value)
    self.assertEqual(
        1, notifications.COUNTER_SEND_MAIL_TASK_FAILED_PERMANENTLY.value)
    self.assertEqual(
        1, notifications.COUNTER_SEND_MAIL_TASK_FAILURE_CAP_EXCEEDED.value)
    self.assertEqual(0, notifications.COUNTER_SEND_MAIL_TASK_SENT.value)
    self.assertEqual(0, notifications.COUNTER_SEND_MAIL_TASK_SKIPPED.value)
    self.assertEqual(1, notifications.COUNTER_SEND_MAIL_TASK_STARTED.value)
    self.assertEqual(0, notifications.COUNTER_SEND_MAIL_TASK_SUCCESS.value)

  def test_send_mail_error_promotion_with_record_failure_error(self):
    over_cap = notifications._RECOVERABLE_FAILURE_CAP + 1
    notification_key, payload_key = db.put(
        notifications.Manager._make_unsaved_models(
            self.audit_trail, self.body, self.now, self.intent,
            notifications.RetainAuditTrail.NAME, self.sender, self.subject,
            self.to,
        )
    )
    notification = db.get(notification_key)
    notification._recoverable_failure_count = over_cap
    notification.put()

    def record_failure(unused_notification, unused_payload, unused_exception):
      raise ValueError('message')

    bound_record_failure = types.MethodType(
        record_failure, notifications.Manager(), notifications.Manager)
    self.swap(
        notifications.Manager, '_record_failure', bound_record_failure
    )

    with self.assertRaisesRegexp(
        deferred.PermanentTaskFailure, 'Recoverable failure cap '):
      notifications.Manager._send_mail_task(notification_key, payload_key)

    self.assertEqual(
        1, notifications.COUNTER_SEND_MAIL_TASK_RECORD_FAILURE_CALLED.value)
    self.assertEqual(
        1, notifications.COUNTER_SEND_MAIL_TASK_RECORD_FAILURE_FAILED.value)
    self.assertEqual(
        0, notifications.COUNTER_SEND_MAIL_TASK_RECORD_FAILURE_SUCCESS.value)

  def test_send_mail_task_fails_permanently_if_notification_missing(self):
    notification_key = db.Key.from_path(
        notifications.Notification.kind(),
        notifications.Notification.key_name(self.to, self.intent, self.now)
    )
    payload_key = db.Key.from_path(
        notifications.Notification.kind(),
        notifications.Notification.key_name(self.to, self.intent, self.now)
    )

    with self.assertRaisesRegexp(
        deferred.PermanentTaskFailure, 'Notification missing: '):
      notifications.Manager._send_mail_task(notification_key, payload_key)

    self.assertEqual(0, notifications.COUNTER_RETENTION_POLICY_RUN.value)
    self.assertEqual(0, notifications.COUNTER_SEND_MAIL_TASK_FAILED.value)
    self.assertEqual(
        1, notifications.COUNTER_SEND_MAIL_TASK_FAILED_PERMANENTLY.value)
    self.assertEqual(
        0, notifications.COUNTER_SEND_MAIL_TASK_FAILURE_CAP_EXCEEDED.value)
    self.assertEqual(0, notifications.COUNTER_SEND_MAIL_TASK_SENT.value)
    self.assertEqual(0, notifications.COUNTER_SEND_MAIL_TASK_SKIPPED.value)
    self.assertEqual(1, notifications.COUNTER_SEND_MAIL_TASK_STARTED.value)
    self.assertEqual(0, notifications.COUNTER_SEND_MAIL_TASK_SUCCESS.value)

  def test_send_mail_task_fails_permanently_if_payload_missing(self):
    notification_key, payload_key = db.put(
        notifications.Manager._make_unsaved_models(
            self.audit_trail, self.body, self.now, self.intent,
            notifications.RetainAuditTrail.NAME, self.sender, self.subject,
            self.to,
        )
    )
    db.delete(payload_key)

    with self.assertRaisesRegexp(
        deferred.PermanentTaskFailure, 'Payload missing: '):
      notifications.Manager._send_mail_task(notification_key, payload_key)

    self.assertEqual(0, notifications.COUNTER_RETENTION_POLICY_RUN.value)
    self.assertEqual(0, notifications.COUNTER_SEND_MAIL_TASK_FAILED.value)
    self.assertEqual(
        0, notifications.COUNTER_SEND_MAIL_TASK_FAILURE_CAP_EXCEEDED.value)
    self.assertEqual(
        1, notifications.COUNTER_SEND_MAIL_TASK_FAILED_PERMANENTLY.value)
    self.assertEqual(0, notifications.COUNTER_SEND_MAIL_TASK_SENT.value)
    self.assertEqual(0, notifications.COUNTER_SEND_MAIL_TASK_SKIPPED.value)
    self.assertEqual(1, notifications.COUNTER_SEND_MAIL_TASK_STARTED.value)
    self.assertEqual(0, notifications.COUNTER_SEND_MAIL_TASK_SUCCESS.value)

  def test_send_mail_task_fails_permanently_if_retention_policy_missing(self):
    notification_key, payload_key = db.put(
        notifications.Manager._make_unsaved_models(
            self.audit_trail, self.body, self.now, self.intent,
            notifications.RetainAuditTrail.NAME, self.sender, self.subject,
            self.to,
        )
    )
    notification = db.get(notification_key)
    notifications._RETENTION_POLICIES.pop(notification._retention_policy)

    with self.assertRaisesRegexp(
        deferred.PermanentTaskFailure, 'Unknown retention policy: '):
      notifications.Manager._send_mail_task(notification_key, payload_key)

    self.assertEqual(0, notifications.COUNTER_RETENTION_POLICY_RUN.value)
    self.assertEqual(0, notifications.COUNTER_SEND_MAIL_TASK_FAILED.value)
    self.assertEqual(
        0, notifications.COUNTER_SEND_MAIL_TASK_FAILURE_CAP_EXCEEDED.value)
    self.assertEqual(
        1, notifications.COUNTER_SEND_MAIL_TASK_FAILED_PERMANENTLY.value)
    self.assertEqual(0, notifications.COUNTER_SEND_MAIL_TASK_SENT.value)
    self.assertEqual(0, notifications.COUNTER_SEND_MAIL_TASK_SKIPPED.value)
    self.assertEqual(1, notifications.COUNTER_SEND_MAIL_TASK_STARTED.value)
    self.assertEqual(0, notifications.COUNTER_SEND_MAIL_TASK_SUCCESS.value)

  def test_send_mail_task_throws_if_send_mail_failure_recoverable(self):
    # Ideally we'd do a full test of the retry mechanism, but the testbed just
    # throws when your task raises an uncaught error.
    exception_text = 'thrown'

    def recoverable_error(
        unused_sender, unused_to, unused_subject, unused_body):
      raise ValueError(exception_text)

    notification_key, payload_key = db.put(
        notifications.Manager._make_unsaved_models(
            self.audit_trail, self.body, self.now, self.intent,
            notifications.RetainAuditTrail.NAME, self.sender, self.subject,
            self.to,
        )
    )

    with self.assertRaisesRegexp(ValueError, 'thrown'):
      notifications.Manager._send_mail_task(
          notification_key, payload_key, recoverable_error)
    notification = db.get(notification_key)

    self.assertEqual(exception_text, notification._last_exception['string'])
    self.assertEqual(1, notification._recoverable_failure_count)

    self.assertEqual(0, notifications.COUNTER_RETENTION_POLICY_RUN.value)
    self.assertEqual(1, notifications.COUNTER_SEND_MAIL_TASK_FAILED.value)
    self.assertEqual(
        0, notifications.COUNTER_SEND_MAIL_TASK_FAILURE_CAP_EXCEEDED.value)
    self.assertEqual(
        0, notifications.COUNTER_SEND_MAIL_TASK_FAILED_PERMANENTLY.value)
    self.assertEqual(0, notifications.COUNTER_SEND_MAIL_TASK_SENT.value)
    self.assertEqual(0, notifications.COUNTER_SEND_MAIL_TASK_SKIPPED.value)
    self.assertEqual(1, notifications.COUNTER_SEND_MAIL_TASK_STARTED.value)
    self.assertEqual(0, notifications.COUNTER_SEND_MAIL_TASK_SUCCESS.value)

  def test_send_mail_task_recoverable_error_record_failure_error(self):
    exception_text = 'thrown'

    def recoverable_error(
        unused_sender, unused_to, unused_subject, unused_body):
      raise ValueError(exception_text)

    def record_failure(unused_notification, unused_payload, unused_exception):
      raise IOError('not_' + exception_text)

    bound_record_failure = types.MethodType(
        record_failure, notifications.Manager(), notifications.Manager)
    self.swap(
        notifications.Manager, '_record_failure', bound_record_failure
    )
    notification_key, payload_key = db.put(
        notifications.Manager._make_unsaved_models(
            self.audit_trail, self.body, self.now, self.intent,
            notifications.RetainAuditTrail.NAME, self.sender, self.subject,
            self.to,
        )
    )

    with self.assertRaisesRegexp(ValueError, '^thrown$'):
      notifications.Manager._send_mail_task(
          notification_key, payload_key, recoverable_error)

    self.assertEqual(
        1, notifications.COUNTER_SEND_MAIL_TASK_RECORD_FAILURE_CALLED.value)
    self.assertEqual(
        1, notifications.COUNTER_SEND_MAIL_TASK_RECORD_FAILURE_FAILED.value)
    self.assertEqual(
        0, notifications.COUNTER_SEND_MAIL_TASK_RECORD_FAILURE_SUCCESS.value)

  def test_send_mail_task_marks_fatal_failure_of_send_mail_and_succeeds(self):
    def fatal_error(unused_sender, unused_to, unused_subject, unused_body):
      raise mail_errors.BadRequestError('thrown')

    notification_key, payload_key = db.put(
        notifications.Manager._make_unsaved_models(
            self.audit_trail, self.body, self.now, self.intent,
            notifications.RetainAuditTrail.NAME, self.sender, self.subject,
            self.to,
        )
    )
    notifications.Manager._send_mail_task(
        notification_key, payload_key, fatal_error)
    notification, payload = db.get([notification_key, payload_key])
    expected_last_exception = {
        'type': 'google.appengine.api.mail_errors.BadRequestError',
        'string': 'thrown'
    }

    self.assertEqual(expected_last_exception, notification._last_exception)
    self.assertGreater(notification._fail_date, notification._enqueue_date)
    self.assertIsNone(payload.body)  # Policy applied.

    self.assertEqual(1, notifications.COUNTER_RETENTION_POLICY_RUN.value)
    self.assertEqual(0, notifications.COUNTER_SEND_MAIL_TASK_FAILED.value)
    self.assertEqual(
        0, notifications.COUNTER_SEND_MAIL_TASK_FAILURE_CAP_EXCEEDED.value)
    self.assertEqual(
        1, notifications.COUNTER_SEND_MAIL_TASK_FAILED_PERMANENTLY.value)
    self.assertEqual(0, notifications.COUNTER_SEND_MAIL_TASK_SENT.value)
    self.assertEqual(0, notifications.COUNTER_SEND_MAIL_TASK_SKIPPED.value)
    self.assertEqual(1, notifications.COUNTER_SEND_MAIL_TASK_STARTED.value)
    self.assertEqual(1, notifications.COUNTER_SEND_MAIL_TASK_SUCCESS.value)

  def test_send_mail_task_sends_marks_and_applies_default_policy(self):
    notification_key, payload_key = db.put(
        notifications.Manager._make_unsaved_models(
            self.audit_trail, self.body, self.now, self.intent,
            notifications.RetainAuditTrail.NAME, self.sender, self.subject,
            self.to,
        )
    )
    notifications.Manager._send_mail_task(notification_key, payload_key)
    notification, payload = db.get([notification_key, payload_key])
    messages = self.get_mail_stub().get_sent_messages()
    message = messages[0]

    self.assertEqual(1, len(messages))
    self.assertEqual(self.body, message.body.decode())
    self.assertEqual(self.sender, message.sender)
    self.assertEqual(self.subject, message.subject)
    self.assertEqual(self.to, message.to)

    self.assertGreater(notification._send_date, notification._enqueue_date)
    self.assertEqual(notification._done_date, notification._send_date)
    self.assertIsNone(notification._fail_date)
    self.assertIsNone(notification._last_exception)

    self.assertIsNotNone(notification.audit_trail)
    self.assertIsNone(payload.body)

    self.assertEqual(1, notifications.COUNTER_RETENTION_POLICY_RUN.value)
    self.assertEqual(0, notifications.COUNTER_SEND_MAIL_TASK_FAILED.value)
    self.assertEqual(
        0, notifications.COUNTER_SEND_MAIL_TASK_FAILURE_CAP_EXCEEDED.value)
    self.assertEqual(
        0, notifications.COUNTER_SEND_MAIL_TASK_FAILED_PERMANENTLY.value)
    self.assertEqual(1, notifications.COUNTER_SEND_MAIL_TASK_SENT.value)
    self.assertEqual(0, notifications.COUNTER_SEND_MAIL_TASK_SKIPPED.value)
    self.assertEqual(1, notifications.COUNTER_SEND_MAIL_TASK_STARTED.value)
    self.assertEqual(1, notifications.COUNTER_SEND_MAIL_TASK_SUCCESS.value)

  def test_send_mail_task_skips_if_already_done(self):
    notification_key, payload_key = db.put(
        notifications.Manager._make_unsaved_models(
            self.audit_trail, self.body, self.now, self.intent,
            notifications.RetainAuditTrail.NAME, self.sender, self.subject,
            self.to,
        )
    )
    notification = db.get(notification_key)
    notification._done_date = self.now
    notification.put()
    notifications.Manager._send_mail_task(notification_key, payload_key)

    self.assertEqual(0, notifications.COUNTER_RETENTION_POLICY_RUN.value)
    self.assertEqual(0, notifications.COUNTER_SEND_MAIL_TASK_FAILED.value)
    self.assertEqual(
        0, notifications.COUNTER_SEND_MAIL_TASK_FAILURE_CAP_EXCEEDED.value)
    self.assertEqual(
        0, notifications.COUNTER_SEND_MAIL_TASK_FAILED_PERMANENTLY.value)
    self.assertEqual(0, notifications.COUNTER_SEND_MAIL_TASK_SENT.value)
    self.assertEqual(1, notifications.COUNTER_SEND_MAIL_TASK_SKIPPED.value)
    self.assertEqual(1, notifications.COUNTER_SEND_MAIL_TASK_STARTED.value)
    self.assertEqual(1, notifications.COUNTER_SEND_MAIL_TASK_SUCCESS.value)

  def test_send_mail_task_skips_if_already_failed(self):
    notification_key, payload_key = db.put(
        notifications.Manager._make_unsaved_models(
            self.audit_trail, self.body, self.now, self.intent,
            notifications.RetainAuditTrail.NAME, self.sender, self.subject,
            self.to,
        )
    )
    notification = db.get(notification_key)
    notification._fail_date = self.now
    notification.put()
    notifications.Manager._send_mail_task(notification_key, payload_key)

    self.assertEqual(0, notifications.COUNTER_RETENTION_POLICY_RUN.value)
    self.assertEqual(0, notifications.COUNTER_SEND_MAIL_TASK_FAILED.value)
    self.assertEqual(
        0, notifications.COUNTER_SEND_MAIL_TASK_FAILURE_CAP_EXCEEDED.value)
    self.assertEqual(
        0, notifications.COUNTER_SEND_MAIL_TASK_FAILED_PERMANENTLY.value)
    self.assertEqual(0, notifications.COUNTER_SEND_MAIL_TASK_SENT.value)
    self.assertEqual(1, notifications.COUNTER_SEND_MAIL_TASK_SKIPPED.value)
    self.assertEqual(1, notifications.COUNTER_SEND_MAIL_TASK_STARTED.value)
    self.assertEqual(1, notifications.COUNTER_SEND_MAIL_TASK_SUCCESS.value)

  def test_send_mail_task_skips_if_already_sent(self):
    notification_key, payload_key = db.put(
        notifications.Manager._make_unsaved_models(
            self.audit_trail, self.body, self.now, self.intent,
            notifications.RetainAuditTrail.NAME, self.sender, self.subject,
            self.to,
        )
    )
    notification = db.get(notification_key)
    notification._send_date = self.now
    notification.put()
    notifications.Manager._send_mail_task(notification_key, payload_key)

    self.assertEqual(0, notifications.COUNTER_RETENTION_POLICY_RUN.value)
    self.assertEqual(0, notifications.COUNTER_SEND_MAIL_TASK_FAILED.value)
    self.assertEqual(
        0, notifications.COUNTER_SEND_MAIL_TASK_FAILURE_CAP_EXCEEDED.value)
    self.assertEqual(
        0, notifications.COUNTER_SEND_MAIL_TASK_FAILED_PERMANENTLY.value)
    self.assertEqual(0, notifications.COUNTER_SEND_MAIL_TASK_SENT.value)
    self.assertEqual(1, notifications.COUNTER_SEND_MAIL_TASK_SKIPPED.value)
    self.assertEqual(1, notifications.COUNTER_SEND_MAIL_TASK_STARTED.value)
    self.assertEqual(1, notifications.COUNTER_SEND_MAIL_TASK_SUCCESS.value)


class ModelTestBase(actions.TestBase):

  def setUp(self):
    super(ModelTestBase, self).setUp()
    self.enqueue_date = datetime.datetime(2000, 1, 1, 1, 1, 1, 1)
    self.intent = 'intent'
    self.retention_policy = notifications.RetainAuditTrail.NAME
    self.transform_fn = lambda x: 'transformed_' + x
    self.to = 'to@example.com'

  def assert_constructor_argument_required(self, name):
    kwargs = self._get_init_kwargs()
    kwargs.pop(name)

    with self.assertRaisesRegexp(
        AssertionError, 'Missing required property: ' + name):
      self.ENTITY_CLASS(**kwargs)

  def assert_for_export_removes_blacklisted_fields(self, unsafe_model):
    safe_model = unsafe_model.for_export(self.transform_fn)

    for blacklisted_property in self.ENTITY_CLASS._PROPERTY_EXPORT_BLACKLIST:
      self.assertTrue(hasattr(unsafe_model, blacklisted_property.name))
      self.assertFalse(hasattr(safe_model, blacklisted_property.name))

  def _get_init_kwargs(self):
    return {}


class ModelTestSpec(object):
  """Tests that must be executed against each child of notifications._Model."""

  # Require children replace with a callable. pylint: disable-msg=not-callable
  ENTITY_CLASS = None

  def test_constructor_raises_value_error_if_intent_contains_delimiter(self):
    with self.assertRaisesRegexp(ValueError, 'cannot contain'):
      kwargs = self._get_init_kwargs()
      kwargs['intent'] += notifications._KEY_DELIMITER
      self.ENTITY_CLASS(**kwargs)

  def test_constructor_requires_args_for_key_name(self):
    self.assert_constructor_argument_required('enqueue_date')
    self.assert_constructor_argument_required('intent')
    self.assert_constructor_argument_required('to')

  def test_key_name(self):
    kind, to, intent, usec_str = self.ENTITY_CLASS._split_key_name(
        self.key.name())

    self.assertEqual(self.ENTITY_CLASS.kind().lower(), kind)
    self.assertEqual(self.to, to)
    self.assertEqual(self.intent, intent)
    self.assertEqual(
        self.enqueue_date, notifications._epoch_usec_to_dt(int(usec_str)))

  def test_key_name_raises_value_error_if_intent_contains_delimiter(self):
    with self.assertRaisesRegexp(ValueError, 'cannot contain'):
      self.ENTITY_CLASS.key_name(
          self.to, self.intent + notifications._KEY_DELIMITER,
          self.enqueue_date)

  def test_safe_key_transforms_to(self):
    safe_key = self.ENTITY_CLASS.safe_key(self.key, self.transform_fn)
    kind, to, intent, usec_str = self.ENTITY_CLASS._split_key_name(
        safe_key.name())

    self.assertEqual(self.ENTITY_CLASS.kind().lower(), kind)
    self.assertEqual(self.transform_fn(self.to), to)
    self.assertEqual(self.intent, intent)
    self.assertEqual(
        self.enqueue_date, notifications._epoch_usec_to_dt(int(usec_str)))


class NotificationTest(ModelTestSpec, ModelTestBase):

  ENTITY_CLASS = notifications.Notification

  def setUp(self):
    super(NotificationTest, self).setUp()
    self.sender = 'sender@example.com'
    self.subject = 'subject'
    self.template_path = 'template_path'
    self.utcnow = datetime.datetime.utcnow()
    self.test_utcnow_fn = lambda: self.utcnow
    self.notification = notifications.Notification(
        enqueue_date=self.enqueue_date, intent=self.intent,
        _retention_policy=self.retention_policy, sender=self.sender,
        subject=self.subject, template_path=self.template_path, to=self.to,
    )
    self.key = self.notification.put()

  def _get_init_kwargs(self):
    return {
        'audit_trail': {},
        'enqueue_date': self.enqueue_date,
        'intent': self.intent,
        'retention_policy': self.retention_policy,
        'sender': self.sender,
        'subject': self.subject,
        'to': self.to,
    }

  def test_audit_trail_round_trips_successfully(self):
    serializable = {
        'int': 1,
        'bool': True,
    }
    notification = notifications.Notification(
        audit_trail=serializable, enqueue_date=self.enqueue_date,
        intent=self.intent, _retention_policy=self.retention_policy,
        sender=self.sender, subject=self.subject, to=self.to,
    )
    notification = db.get(notification.put())

    self.assertEqual(serializable, db.get(notification.put()).audit_trail)

  def test_ctor_raises_bad_value_error_when_not_serializable(self):
    not_json_serializable = datetime.datetime.utcnow()

    with self.assertRaisesRegexp(db.BadValueError, 'is not JSON-serializable'):
      notifications.Notification(
          audit_trail=not_json_serializable, enqueue_date=self.enqueue_date,
          intent=self.intent, _retention_policy=self.retention_policy,
          sender=self.sender, subject=self.subject, to=self.to,
      )

  def test_for_export_transforms_to_and_sender_and_strips_blacklist_items(self):
    audit_trail = {'will_be': 'stripped'}
    last_exception = 'will_be_stripped'
    unsafe = notifications.Notification(
        audit_trail=audit_trail, enqueue_date=self.enqueue_date,
        intent=self.intent, last_exception=last_exception,
        _retention_policy=self.retention_policy, sender=self.sender,
        subject=self.subject, to=self.to,
    )
    unsafe.put()
    safe = unsafe.for_export(self.transform_fn)

    self.assertEqual('transformed_' + self.sender, safe.sender)
    self.assertEqual('transformed_' + self.to, safe.to)
    self.assert_for_export_removes_blacklisted_fields(unsafe)


class PayloadTest(ModelTestSpec, ModelTestBase):

  ENTITY_CLASS = notifications.Payload

  def setUp(self):
    super(PayloadTest, self).setUp()
    self.body = 'body'
    self.payload = notifications.Payload(
        body='body', enqueue_date=self.enqueue_date, intent=self.intent,
        _retention_policy=self.retention_policy, to=self.to)
    self.key = self.payload.put()

  def _get_init_kwargs(self):
    return {
        'enqueue_date': self.enqueue_date,
        'intent': self.intent,
        'retention_policy': self.retention_policy,
        'to': self.to,
    }

  def test_for_export_blacklists_data(self):
    self.assert_for_export_removes_blacklisted_fields(self.payload)
