# Copyright 2013 Google Inc. All Rights Reserved.
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

"""Core service interface definitions."""


class Service(object):
    """Abstract base service interface."""

    def enabled(self):
        raise NotImplementedError()


class HelpUrls(Service):

    def get(self, topic_id):
        """Gets the help URL for a given topic_id string.

        Args:
            topic_id: string. The unique identifier of the topic to get a help
                url for.

        Returns:
            String. The help URL for the requested topic_id.

        Raises:
            ValueError: if no URL mapping exists for the requested topic_id.
        """
        raise NotImplementedError()

    def make_learn_more_message(self, text, topic_id, to_string=False):
        """Makes a sanitized message with a 'Learn more' link for display in UI.

        Args:
            text: string. Text of the help message.
            topic_id: string. Unique identifier for the help message to get a
                redirect URL for.
            to_string: boolean. If True, returns a string. If False, returns a
                safe_dom.NodeList.

        Raises:
            ValueError: if no URL mapping exists for the requested topic_id.
        """
        raise NotImplementedError()


class Notifications(Service):

    def query(self, to, intent):
        """Gets the Status of notifications queued previously via send_async().

        Serially performs one datastore query per user in the to list.

        Args:
          to: list of string. The recipients of the notification.
          intent: string. Short string identifier of the intent of the
          notification (for example, 'invitation' or 'reminder').

        Returns:
          Dict of to string -> [Status, sorted by descending enqueue date]. See
          modules.notifications.notifications.Status for an example of the
          Status object.
        """
        raise NotImplementedError()

    def send_async(
        self, to, sender, intent, body, subject, audit_trail=None, html=None,
        retention_policy=None):
        """Asyncronously sends a notification via email.

        Args:
          to: string. Recipient email address. Must have a valid form, but we
              cannot know that the address can actually be delivered to.

          sender: string. Email address of the sender of the
              notification. Must be a valid sender for the App Engine
              deployment at the time the deferred send_mail() call actually
              executes (meaning it cannot be the email address of the user
              currently in session, because the user will not be in session at
              call time). See
              https://developers.google.com/appengine/docs/python/mail/emailmessagefields.
          intent: string. Short string identifier of the intent of the
              notification (for example, 'invitation' or 'reminder'). Each kind
              of notification you are sending should have its own intent.
              Used when creating keys in the index; values that cause the
              resulting key to be >500B will fail. May not contain a colon.
          body: string. The data payload of the notification. Must fit in a
              datastore entity.
          subject: string. Subject line for the notification.
          audit_trail: JSON-serializable object. An optional audit trail that,
              when used with the default retention policy, will be retained
              even after the body is scrubbed from the datastore.
          html: optional string. The data payload of the notification as html.
                  Must fit in a datastore entity when combined with the plain
                  text version. Both the html and plain text body will be
                  sent, and the recipient's mail client will decide which to
                  show.
          retention_policy: RetentionPolicy. The retention policy to use for
              data after a Notification has been sent. By default, we retain the
              audit_trail but not the body.

        Returns:
          (notification_key, payload_key). A 2-tuple of datastore keys for the
          created notification and payload.

        Raises:
          Exception: if values delegated to model initializers are invalid.
          ValueError: if to or sender are malformed according to App Engine
              (note that well-formed values do not guarantee success).

        """
        raise NotImplementedError()


class Unsubscribe(Service):

    def get_unsubscribe_url(self, handler, email):
        """Create an individualized unsubscribe link for a user.

        Args:
          handler: controllers.utils.ApplicationHandler. The current request
              handler.
          email: string. The email address of the users for whom the unsubscribe
              link is being generated.

        Returns:
          string. A URL for the users to unsubscribe from notifications.
        """
        raise NotImplementedError()

    def has_unsubscribed(self, email):
        """Check whether the user has requested to be unsubscribed.

        Args:
          email: string. The email address of the user.

        Returns:
          bool. True if the user has requested to be unsubscribed.
        """
        raise NotImplementedError()

    def set_subscribed(self, email, is_subscribed):
        """Set the state of a given user.

        Args:
          email: string. The email address of the user.
          is_subscribed: bool. The state to set. True means that the user is
              subscribed and should continue to receive emails; False means that
              they should not.

        Returns:
          None.
        """
        raise NotImplementedError()


help_urls = HelpUrls()
notifications = Notifications()
unsubscribe = Unsubscribe()
