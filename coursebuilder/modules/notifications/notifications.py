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

TODO(johncox): fill in docs after full implementation written.
"""

__author__ = [
  'John Cox'
]

import datetime
import pickle

from models import custom_modules
from models import entities

from google.appengine.ext import db


# String. Delimiter used when calculating keys.
_KEY_DELIMITER = ':'
# Int. Microseconds in a second.
_USECS_PER_SECOND = 10 ** 6

# TODO(johncox): remove suppression once stubs are implemented.
# pylint: disable-msg=unused-argument


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


class RetentionPolicy(object):
  """Retention policy for notification data.

  Notification data is spread between the Notification and Payload objects (of
  which see below). Two parts of this data may be large: the context for
  rendering the notification body, or the contents of the rendered body itself.

  We allow clients to specify a retention policy when calling
  Manager.send_async(). This retention policy is a bundle of logic applied after
  we know a notification has been sent. How and when the retention policy is run
  is up to the implementation; we make no guarantees except that once the
  notification is sent we will attempt run() at least once, and if it mutates
  its input we will attempt to apply those mutations at least once.

  Practically, it can be used to prevent retention of data in the datastore that
  is of no use to the client, even for audit purposes.

  Note that 'retention' here has nothing to do with broader user data privacy
  and retention concerns -- this is purely about responsible resource usage.
  """

  # String. Name used to identify the retention policy (in the datastore, for)
  # example.
  NAME = None

  @classmethod
  def run(cls, notification, payload):
    """Runs the policy, transforming notification and payload.

    run does not apply mutations to the backing datastore entities; it merely
    returns versions of those entities that we will later attempt to persist.

    Args:
      notification: Notification. The notification to process.
      payload: Payload. The payload to process.

    Returns:
      A (notification, payload) 2-tuple with the desired mutations done.
    """
    return notification, payload


class RetainAll(RetentionPolicy):
  """Policy that retains all data."""

  NAME = 'all'


class RetainContext(RetentionPolicy):
  """Policy that blanks payload but not context."""

  NAME = 'context'

  @classmethod
  def run(cls, notification, payload):
    # TODO(johncox): write after send_async.
    raise NotImplementedError()


# Dict of string -> RetentionPolicy where key is the policy's NAME. All
# available retention policies.
_RETENTION_POLICIES = {
    RetainAll.NAME: RetainAll,
    RetainContext.NAME: RetainContext,
}


class Status(object):
  """DTO for email status."""

  FAILED = 1
  PENDING = 2
  SUCCEEDED = 3
  _STATES = frozenset((FAILED, PENDING, SUCCEEDED))

  def __init__(self, to, sender, intent, state):
    assert state in self._STATES

    self.intent = intent
    self.to = to
    self.sender = sender
    self.state = state


class Manager(object):
  """Manages state and operation of the notifications subsystem."""

  @classmethod
  def query(cls, to, intent):
    """Gets the Status of notifications queued previously via send_async().

    Args:
      to: list of string. The recipients of the notification.
      intent: string. Short string identifier of the intent of the notification
          (for example, 'invitation' or 'reminder').

    Returns:
      List of Status objects matching query.
    """
    # TODO(johncox): fill in stub.
    raise NotImplementedError()

  @classmethod
  def send_async(
      cls, to, sender, intent, context, template_path, subject,
      retention_policy=None, send_after=None):
    """Asyncronously sends a notification via email.

    Args:
      to: string. Recipient email address. Must have a valid form, but we cannot
          know that the address can actually be delivered to.
      sender: string. Email address of the sender of the notification. Must be a
          valid sender for the App Engine deployment. See
          https://developers.google.com/appengine/docs/python/mail/emailmessagefields.
      intent: string. Short string identifier of the intent of the notification
          (for example, 'invitation' or 'reminder'). Each kind of notification
          you are sending should have its own intent. Used when creating keys in
          the index; values that cause the resulting key to be >500B will fail.
          May not contain a colon.
      context: dict of string -> object. The template context used to render the
          notification body. Must be pickle-able; see
          https://docs.python.org/2/library/pickle.html?highlight=pickle#what-can-be-pickled-and-unpickled
      template_path: string. Path to the Jinja2 template for the notification
          body. Templates are expected to be plain text; HTML is not yet
          supported, but this is not enforced.
      subject: string. Subject line for the notification.
      retention_policy: RetentionPolicy. The retention policy to use for data
          after a Notification has been sent. By default, we retain the context
          but not the rendered payload.
      send_after: datetime.datetime. UTC datetime of the earliest this
          notification should be sent. Defaults to utcnow (that is, no delay).

    Returns:
      None.

    Raises:
      ValueError: if intent is invalid.
    """
    # TODO(johncox): fill in stub.
    raise NotImplementedError()


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
  """Custom property that stores serialized Python dicts of pickle-able data."""

  def get_value_for_datastore(self, model_instance):
    return pickle.dumps(super(
        _SerializedProperty, self
    ).get_value_for_datastore(model_instance))

  def make_value_from_datastore(self, value):
    return pickle.loads(value)

  def validate(self, value):
    value = super(_SerializedProperty, self).validate(value)

    if value is not None and not isinstance(value, dict):
      raise db.BadValueError(
          'value must be a dict; got %s' % type(value).__name__)

    try:
      pickle.dumps(value)
    except TypeError as e:
      raise db.BadValueError(
          '%s is not serializable; error was "%s"' % (value, e))

    return value


class _Model(entities.BaseEntity):
  """Abstract base model that handles key calculation."""

  # String. Template used in key generation.
  _KEY_TEMPLATE = (
      '(%(kind)s%(delim)s%(to)s%(delim)s%(intent)s%(delim)s%(enqueue_date)s)'
  )

  def __init__(self, *args, **kwargs):
    assert 'key_name' not in kwargs, 'Setting key_name manually not supported'
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

  # Information used to compose messages.

  # Context dict used to render the template for the notification. Must be
  # pickle-serializable.
  context = _SerializedProperty()
  # String indicating the intent of the notification. Intents are used to group
  # and index notifications. Used in key formation; may not contain a colon.
  intent = _IntentProperty(required=True)
  # Date before which the notification will be skipped during processing. Used
  # for rudimentary scheduling.
  send_after = db.DateTimeProperty(required=True)
  # Email address used to compose the From:. Subject to the sender restrictions
  # of the underlying App Engine mail library; see the sender field in
  # https://developers.google.com/appengine/docs/python/mail/emailmessagefields.
  sender = db.StringProperty(required=True)
  # Subject line of the notification.
  subject = db.TextProperty(required=True)
  # Path to the template used to render the text of the notification.
  template = db.StringProperty(required=True)
  # Email address used to compose the To:. May house only one value. Subject to
  # the restrictions of the underlying App Engine mail library; see the to field
  # in
  # https://developers.google.com/appengine/docs/python/mail/emailmessagefields.
  to = db.StringProperty(required=True)

  # Bookkeeping information used for system state.

  # When the record was last changed.
  change_date = db.DateTimeProperty(auto_now=True, required=True)
  # When the record was enqueued in client code.
  enqueue_date = db.DateTimeProperty(required=True)
  # When processing of the record last started. May be None if the record has
  # never been processed.
  start_date = db.DateTimeProperty()
  # When processing of the record completed successfully, meaning a send_mail
  # call finshed for the record and we recorded it in the datastore. May be None
  # if this has not yet happend.
  complete_date = db.DateTimeProperty()
  # When processing of the record failed unrecoverably. Unrecoverable failure is
  # failure that does not get retried (for example, because we know a priori
  # that subsequent attempts will fail). An example of unrecoverable error is a
  # malformed sender. May be None if failure has not occurred. Note that entries
  # that are past the retry cutoff will not be retried, but this is not
  # considered unrecoverable failure.
  fail_date = db.DateTimeProperty()
  # String representation of the last exception encountered when processing the
  # record. May be None if there has never been an exception during processing.
  last_exception = db.TextProperty()
  # RetentionPolicy.NAME string. Identifier for the retention policy for the
  # Notification.
  retention_policy = db.StringProperty(
      required=True, choices=_RETENTION_POLICIES.keys())

  _PROPERTY_EXPORT_BLACKLIST = [context, last_exception]

  def __init__(self, *args, **kwargs):
    # Injectable for tests only -- do not pass in ordinary operation.
    utcnow_fn = kwargs.get('utcnow_fn', datetime.datetime.utcnow)
    kwargs['send_after'] = kwargs.get('send_after', utcnow_fn())
    super(Notification, self).__init__(*args, **kwargs)

  def for_export(self, transform_fn):
    model = super(Notification, self).for_export(transform_fn)
    model.to = transform_fn(model.to)
    model.sender = transform_fn(model.sender)
    return model


class Payload(_Model):
  """The data payload of a Notification.

  In the current implementation, this is the email body rendered from the
  context and the template supplied by the user when Manager.send_async() is
  called.

  We calculate the payload at call time rather than at send time because there
  may be an arbitrary delay between the two during which the template changes.
  This would cause the actual payload of the notification to differ from the
  payload expected at call time, with no way for the caller to be aware of the
  resulting payload in the notification.

  We extract this data from Notification to increase the total size budget
  available to the user, which is capped at 1MB/entity.
  """

  # When the record was last changed.
  change_date = db.DateTimeProperty(auto_now=True, required=True)
  # Text of the payload.
  data = db.TextProperty()
  # When the record was enqueued in client code.
  enqueue_date = db.DateTimeProperty(required=True)
  # RetentionPolicy.NAME string. Identifier for the retention policy for the
  # Payload.
  retention_policy = db.StringProperty(
      required=True, choices=_RETENTION_POLICIES.keys())

  _PROPERTY_EXPORT_BLACKLIST = [data]

  def __init__(self, *args, **kwargs):
    super(Payload, self).__init__(*args, **kwargs)
    _IntentProperty().validate(kwargs.get('intent'))


custom_module = None


def register_module():
  """Registers the module with the Registry."""

  global custom_module

  custom_module = custom_modules.Module(
      'Notifications', 'Student notification management system.', [], [])
  return custom_module
