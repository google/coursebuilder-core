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

"""Module to support users unsubscribing from notifications.

Note: In order for this module to function, the course admin must set a secret
key which is used to sign the unsubscribe request URLs. This key is set by
editing course.yaml in the Dashboard > Settings with the Advanced Edit button.
Add the following YAML snippet, replacing <secret_key> with your own string:

modules:
  unsubscribe:
    key: <secret_key>

The key must be between 16 and 64 characters long, and must be kept secure to
prevent malevolent third-parties from unsusbcribing your users.
"""

__author__ = 'John Orr (jorr@google.com)'

import os
import sha
import urllib
import urlparse

import appengine_config
from controllers import utils
from models import custom_modules
from models import entities

from google.appengine.ext import db


TEMPLATES_DIR = os.path.join(
    appengine_config.BUNDLE_ROOT, 'modules', 'unsubscribe', 'templates')

# The shortest length allowed for the secret in modules/unsubscribe/key
MIN_SECRET_KEY_LENGTH = 16
# The breatest length allowed for the secret in modules/unsubscribe/key
MAX_SECRET_KEY_LENGTH = 64


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
        signature = self.request.get('s')
        action = self.request.get('action')

        if signature != _get_signature(self, email):
            self.error(401)
            return

        if action == self.RESUBSCRIBE_ACTION:
            set_subscribed(email, True)
            template_file = 'resubscribe.html'
        else:
            set_subscribed(email, False)
            template_file = 'unsubscribe.html'
            self.template_value[
                'resubscribe_url'] = self.get_resubscribe_url(email)

        self.template_value['navbar'] = {}
        self.template_value['email'] = email

        template = self.get_template(template_file, [TEMPLATES_DIR])
        self.response.out.write(template.render(self.template_value))

    def get_resubscribe_url(self, email):
        abs_url = urlparse.urljoin(self.get_base_href(self), self.URL[1:])
        query = urllib.urlencode({
            'email': email,
            's': _get_signature(self, email),
            'action': self.RESUBSCRIBE_ACTION})
        return '%s?%s' % (abs_url, query)


def _get_signature(handler, email):
    secret_key = handler.app_context.get_environ().get('modules', {}).get(
        'unsubscribe', {}).get('key')
    assert secret_key, 'No secret_key set in course.yaml'
    assert len(secret_key) >= MIN_SECRET_KEY_LENGTH, (
        'The secret_key must be at least %s characters' % MIN_SECRET_KEY_LENGTH)
    assert len(secret_key) <= MAX_SECRET_KEY_LENGTH, (
        'The secret_key must be less than %s characters' %
        MAX_SECRET_KEY_LENGTH)
    return sha.new('%s%s' % (email, secret_key)).hexdigest()


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
        return db.Key(cls.kind(), transform_fn(db_key.name()))


custom_module = None


def register_module():
    """Registers this module in the registry."""

    namespaced_routes = [
        (UnsubscribeHandler.URL, UnsubscribeHandler)]

    global custom_module
    custom_module = custom_modules.Module(
        'Unsubscribe Module',
        'A module to enable unsubscription from emails.',
        [], namespaced_routes)
    return custom_module
