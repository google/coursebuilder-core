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

"""Functional tests for modules/notifications/notifications.py."""

__author__ = [
    'johncox@google.com'
]

import datetime

from modules.notifications import notifications
from tests.functional import actions

from google.appengine.ext import db


# Allow access to code under test. pylint: disable-msg=protected-access


class Custom(object):
  """Custom toplevel class to test serialization."""

  SOME_DATA = 'some_value'

  def has_some_behavior(self):
    return True

  def __eq__(self, other):
    return str(self) == str(other)

  def __str__(self):
    return str(self.__dict__)


class DatetimeConversionTest(actions.TestBase):

  def test_utc_datetime_round_trips_correctly(self):
    dt_with_usec = datetime.datetime(2000, 1, 1, 1, 1, 1, 1)

    self.assertEqual(
      dt_with_usec,
      notifications._epoch_usec_to_dt(
          notifications._dt_to_epoch_usec(dt_with_usec)))


class ModelTestBase(actions.TestBase):

  def setUp(self):
    super(ModelTestBase, self).setUp()
    self.enqueue_date = datetime.datetime(2000, 1, 1, 1, 1, 1, 1)
    self.intent = 'intent'
    self.retention_policy = notifications.RetainContext.NAME
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
    self.template = 'template'
    self.utcnow = datetime.datetime.utcnow()
    self.test_utcnow_fn = lambda: self.utcnow
    self.notification = notifications.Notification(
        enqueue_date=self.enqueue_date, intent=self.intent,
        retention_policy=self.retention_policy, sender=self.sender,
        subject=self.subject, template=self.template, to=self.to,
    )
    self.key = self.notification.put()

  def _get_init_kwargs(self):
    return {
        'context': {},
        'enqueue_date': self.enqueue_date,
        'intent': self.intent,
        'retention_policy': self.retention_policy,
        'sender': self.sender,
        'subject': self.subject,
        'template': self.template,
        'to': self.to,
    }

  def test_constructor_defaults_send_after_and_accepts_override(self):
    defaulted = notifications.Notification(
        context={}, enqueue_date=self.enqueue_date, intent=self.intent,
        retention_policy=self.retention_policy, sender=self.sender,
        subject=self.subject, template=self.template, to=self.to,
        utcnow_fn=self.test_utcnow_fn
    )

    self.assertEqual(self.utcnow, defaulted.send_after)

    utcnow = datetime.datetime.utcnow()
    overridden = notifications.Notification(
        context={}, enqueue_date=self.enqueue_date, intent=self.intent,
        retention_policy=self.retention_policy, send_after=utcnow,
        sender=self.sender, subject=self.subject, template=self.template,
        to=self.to,
    )

    self.assertEqual(utcnow, overridden.send_after)

  def test_context_raise_bad_value_error_when_not_dict(self):
    with self.assertRaisesRegexp(db.BadValueError, 'must be a dict'):
      notifications.Notification(
          context='', enqueue_date=self.enqueue_date, intent=self.intent,
          retention_policy=self.retention_policy, sender=self.sender,
          subject=self.subject, template=self.template, to=self.to,
      )

  def test_context_raises_bad_value_error_when_not_serializable(self):
    unpicklable = {'modules_cannot_be_pickled': datetime}

    with self.assertRaisesRegexp(db.BadValueError, 'is not serializable'):
      notifications.Notification(
          context=unpicklable, enqueue_date=self.enqueue_date,
          intent=self.intent, retention_policy=self.retention_policy,
          sender=self.sender, subject=self.subject, template=self.template,
          to=self.to,
      )

  def test_context_round_trips_complex_dict_to_datastore_successfully(self):
    context = {
        'string': 1,
        False: None,
        'can_handle_custom_toplevel_types': Custom,
        'can_handle_custom_toplevel_type_instances': Custom(),
        'nested': {
            'key': [datetime.datetime.utcnow(), datetime.datetime.utcnow()],
        },
    }
    notification = notifications.Notification(
        context=context, enqueue_date=self.enqueue_date, intent=self.intent,
        retention_policy=self.retention_policy, sender=self.sender,
        subject=self.subject, template=self.template, to=self.to,
    )

    self.assertEqual(context, db.get(notification.put()).context)

  def test_for_export_transforms_to_and_sender_and_strips_blacklist_items(self):
    context = {'will_be': 'stripped'}
    last_exception = 'will_be_stripped'
    unsafe = notifications.Notification(
        context=context, enqueue_date=self.enqueue_date, intent=self.intent,
        last_exception=last_exception, retention_policy=self.retention_policy,
        sender=self.sender, subject=self.subject, template=self.template,
        to=self.to,
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
    self.data = 'data'
    self.payload = notifications.Payload(
        data='data', enqueue_date=self.enqueue_date, intent=self.intent,
        retention_policy=self.retention_policy, to=self.to)
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
