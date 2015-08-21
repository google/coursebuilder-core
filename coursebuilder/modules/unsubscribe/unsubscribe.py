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

"""Module to support users unsubscribing from notifications."""

__author__ = 'John Orr (jorr@google.com)'

import os
import urllib
import urlparse

import appengine_config
from common import crypto
from common import users
from controllers import utils
from models import custom_modules
from models import data_removal
from models import entities
from models import services

from google.appengine.ext import db


TEMPLATES_DIR = os.path.join(
    appengine_config.BUNDLE_ROOT, 'modules', 'unsubscribe', 'templates')


def get_unsubscribe_url(handler, email):
    """Create an individualized unsubscribe link for a user.

    Args:
      handler: controllers.utils.ApplicationHandler. The current request
          handler.
      email: string. The email address of the users for whom the unsubscribe
          link is being generated.

    Returns:
      string. A URL for the users to unsubscribe from notifications.
    """
    abs_url = urlparse.urljoin(
        handler.get_base_href(handler), UnsubscribeHandler.URL[1:])
    query = urllib.urlencode({
        'email': email,
        's': _get_signature(handler, email)})
    return '%s?%s' % (abs_url, query)


def get_resubscribe_url(handler, email):
    """Create an individualized resubscribe link for a user.

    Args:
      handler: controllers.utils.ApplicationHandler. The current request
          handler.
      email: string. The email address of the users for whom the resubscribe
          link is being generated.

    Returns:
      string. A URL for the users to resubscribe to notifications.
    """
    abs_url = urlparse.urljoin(
        handler.get_base_href(handler), UnsubscribeHandler.URL[1:])
    query = urllib.urlencode({
        'email': email,
        's': _get_signature(handler, email),
        'action': UnsubscribeHandler.RESUBSCRIBE_ACTION})
    return '%s?%s' % (abs_url, query)


def has_unsubscribed(email):
    """Check whether the user has requested to be unsubscribed.

    Args:
      email: string. The email address of the user.

    Returns:
      bool. True if the user has requested to be unsubscribed.
    """
    model = SubscriptionStateEntity.get_by_key_name(email)
    return (model is not None) and not model.is_subscribed


def set_subscribed(email, is_subscribed):
    """Set the state of a given user.

    Args:
      email: string. The email address of the user.
      is_subscribed: bool. The state to set. True means that the user is
          subscribed and should continue to receive emails; False means that
          they should not.

    Returns:
      None.
    """
    model = SubscriptionStateEntity.get_by_key_name(email)
    if model is None:
        model = SubscriptionStateEntity(key_name=email)

    model.is_subscribed = is_subscribed
    model.put()


class UnsubscribeHandler(utils.BaseHandler):
    """Receive an unsubscribe request and process it."""

    URL = '/modules/unsubscribe'
    RESUBSCRIBE_ACTION = 'resubscribe'

    def get(self):
        email = self.request.get('email')
        if email:
            signature = self.request.get('s')
            if signature != _get_signature(self, email):
                self.error(401)
                return
        else:
            # If no email and signature is provided, unsubscribe will prompt
            # for login. NOTE: This is only intended to support access by users
            # who are known to have already registered with Course Builder. In
            # general subscription management should use the encoded email and
            # signature as this places the minimum burden on the user when
            # unsubscribing (ie no need for Google account, no need for login).
            user = self.get_user()
            if user is None:
                self.redirect(users.create_login_url(self.request.uri))
                return
            email = user.email()

        action = self.request.get('action')
        if action == self.RESUBSCRIBE_ACTION:
            set_subscribed(email, True)
            template_file = 'resubscribe.html'
        else:
            set_subscribed(email, False)
            template_file = 'unsubscribe.html'
            self.template_value[
                'resubscribe_url'] = get_resubscribe_url(self, email)

        self.template_value['navbar'] = {}
        self.template_value['email'] = email

        template = self.get_template(template_file, [TEMPLATES_DIR])
        self.response.out.write(template.render(self.template_value))


def _get_signature(handler, email):
    return crypto.EncryptionManager.hmac(
        [email, handler.app_context.get_namespace_name()]).encode('hex')


class SubscriptionStateEntity(entities.BaseEntity):
    """Entity which holds the subscription state of a user.

    This entity must be given a key_name equal to the email address of the user
    whose subscription state is being set.
    """

    is_subscribed = db.BooleanProperty(indexed=False)

    def __init__(self, *args, **kwargs):
        if 'key' not in kwargs and 'key_name' not in kwargs:
            raise db.BadValueError('key_name must be email address')
        super(SubscriptionStateEntity, self).__init__(*args, **kwargs)

    @classmethod
    def safe_key(cls, db_key, transform_fn):
        return db.Key.from_path(cls.kind(), transform_fn(db_key.name()))

    @classmethod
    def delete_by_email(cls, email_address):
        db.delete(db.Key.from_path(cls.kind(), email_address))

custom_module = None


def register_module():
    """Registers this module in the registry."""

    namespaced_routes = [
        (UnsubscribeHandler.URL, UnsubscribeHandler)]

    def notify_module_enabled():
        data_removal.Registry.register_indexed_by_email_remover(
            SubscriptionStateEntity.delete_by_email)

    global custom_module  # pylint: disable=global-statement
    custom_module = custom_modules.Module(
        'Unsubscribe Module',
        'A module to enable unsubscription from emails.',
        [], namespaced_routes, notify_module_enabled=notify_module_enabled)

    class Service(services.Unsubscribe):

        def enabled(self):
            return custom_module.enabled

        def get_unsubscribe_url(self, handler, email):
            return get_unsubscribe_url(handler, email)

        def  has_unsubscribed(self, email):
            return has_unsubscribed(email)

        def set_subscribed(self, email, is_subscribed):
            return set_subscribed(email, is_subscribed)

    services.unsubscribe = Service()
    return custom_module
