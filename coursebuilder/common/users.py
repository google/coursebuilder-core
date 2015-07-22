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

"""Users service -- use instead of google.appengine.api.users.

IMPORTANT: always use this service instead of google.appengine.api.users. Never
use google.appengine.api.users directly.

This users service is API-compatible with google.appengine.api.users, and its
default implementation is a passthrough to google.appengine.api.users. It
functions as a seam that allows clients to swap out the default implementation
with their own when they want to use a custom auth system (for example, GitKit).

To use your own users service, extend AbstractUsersService. Then, using any of
the ordinary runtime modification hook points (appengine_config.py, main.py, or
custom_modules.py's notify_module_enabled), do

    UsersServiceManager.set(MyUsersService)

to swap in your service at runtime. Of those approaches, we recommend doing this
in a module using the module system's notify_module_enabled hook, though pay
close attention to module loading order, since modules loaded before your hook
will not yet see your custom auth system.

The default implementation is registered in main.py. It is in effect everywhere
main runs (so if you're using taskqueue and not executing main, for example, you
will need to do registration yourself if you want to use the users service).

When writing an auth service, you must meet the contract of the App Engine users
service for your code to work at its callsites in Course Builder. See the App
Engine users module docs at

    https://cloud.google.com/appengine/docs/python/users/

and in particular

    https://cloud.google.com/appengine/docs/python/users/userclass
    https://cloud.google.com/appengine/docs/python/users/functions
    https://cloud.google.com/appengine/docs/python/users/exceptions
"""

__author__ = [
    'johncox@google.com (John Cox)',
]

import logging

import webapp2

from google.appengine.api import users

_LOG = logging.getLogger('coursebuilder.common.users')
logging.basicConfig()


# Error classes from google.appengine.api.users. Keep protected symbols in case
# clients clobber the public ones.

_Error = users.Error
_NotAllowedError = users.NotAllowedError
_RedirectTooLongError = users.RedirectTooLongError
_UserNotFoundError = users.UserNotFoundError
Error = _Error
NotAllowedError = _NotAllowedError
RedirectTooLongError = _RedirectTooLongError
UserNotFoundError = _UserNotFoundError


# Public methods from google.appengine.api.users.

def create_login_url(dest_url=None, _auth_domain=None, federated_identity=None):
    # Treat as module-protected. pylint: disable=protected-access
    return UsersServiceManager.get().create_login_url(
        dest_url=dest_url, _auth_domain=_auth_domain,
        federated_identity=federated_identity)


def create_logout_url(dest_url):
    # Treat as module-protected. pylint: disable=protected-access
    return UsersServiceManager.get().create_logout_url(dest_url)


def get_current_user():
    # Treat as module-protected. pylint: disable=protected-access
    return UsersServiceManager.get().get_current_user()


def is_current_user_admin():
    # Treat as module-protected. pylint: disable=protected-access
    return UsersServiceManager.get().is_current_user_admin()


# Public classes from google.appengine.api.users. Keep protected symbols in case
# clients clobber the public ones.

_User = users.User
User = _User


# Base classes, default implementation, and manager.


class AuthInterceptorWSGIApplication(webapp2.WSGIApplication):
    """WSGIApplication that adds an auth seam bracketing requests.

    To apply pre- and post-request hooks to a request, implement a subclass of
    webapp2.RequestContext. This is a Python context object; your pre-request
    hook is __enter__ and your post-request hook is __exit__. See
    https://webapp-improved.appspot.com/api/webapp2.html#webapp2.RequestContext
    for the contract you must fulfill.

    Return a reference to this class from your AbstractUserService
    implementation's get_request_context_class().
    """

    @property
    def request_context_class(self):
        users_service = UsersServiceManager.get()
        if not users_service:
            raise Exception(
                'Users service not set. See common.users.UsersServiceManager.')

        return users_service.get_request_context_class()


class AbstractUsersService(object):
    """Base users service for custom auth integrations.

    Your implementations must fulfill the contract at
    https://cloud.google.com/appengine/docs/python/users/functions. When you
    need a type from google.appengine.api.users, use the aliases above. Your
    implementations should never import google.appengine.api.users.
    """

    # Methods that constitute the service interface.

    @classmethod
    def create_login_url(
            cls, dest_url=None, _auth_domain=None, federated_identity=None):
        raise NotImplementedError

    @classmethod
    def create_logout_url(cls, dest_url):
        raise NotImplementedError

    @classmethod
    def get_current_user(cls):
        raise NotImplementedError

    @classmethod
    def is_current_user_admin(cls):
        raise NotImplementedError

    # Methods that aren't part of the service interface, but are used elsewhere
    # in the system.

    @classmethod
    def get_email_update_policy_class(cls):
        return EmailUpdatePolicy

    @classmethod
    def get_federated_email_resolver_class(cls):
        return FederatedEmailResolver

    @classmethod
    def get_mailer_class(cls):
        return Mailer

    @classmethod
    def get_request_context_class(cls):
        """Gets the Context class for this users service."""
        return webapp2.RequestContext

    @classmethod
    def get_service_name(cls):
        """Returns the name of the auth service for display in admin site."""
        return '%s.%s' % (cls.__module__, cls.__name__)

    @classmethod
    def get_template_resolver_class(cls):
        return TemplateResolver


class AppEnginePassthroughUsersService(AbstractUsersService):
    """Users service that's just a passthrough to google.appengine.api.users."""

    @classmethod
    def create_login_url(
            cls, dest_url=None, _auth_domain=None, federated_identity=None):
        return users.create_login_url(
            dest_url=dest_url, _auth_domain=_auth_domain,
            federated_identity=federated_identity)

    @classmethod
    def create_logout_url(cls, dest_url):
        return users.create_logout_url(dest_url)

    @classmethod
    def get_current_user(cls):
        return users.get_current_user()

    @classmethod
    def is_current_user_admin(cls):
        return users.is_current_user_admin()


class EmailUpdatePolicy(object):
    """Policy that updates email mappings based on auth provider state.

    Default implementation is a noop since default auth doesn't use email
    mappings.
    """

    @classmethod
    def apply(cls, unused_user):
        """Applies the policy.

        Args:
            unused_user: users.User. The user to apply the policy to.
        """
        pass


class FederatedEmailResolver(object):
    """Resolves federated emails for users.

    By default, there is no federated authentication, so we always return None.
    """

    @classmethod
    def get(cls, unused_user_id):
        return None


class Mailer(object):
    """Sender for auth-related notifications.

    Default auth sends no auth-related notifications, so implementation is a
    noop.
    """

    @classmethod
    def send_async(cls, unused_locale, unused_context):
        """Sends email notification(s) asynchronously.

        Args:
            locale: string. The user's preferred locale code (e.g. 'en_US').
            oob_email_response: object. Response object from auth service
                containing template values used to compose mails to user.

        Returns:
            (notification_key, payload_key). A 2-tuple of datastore keys for the
                created notification and payload.

        Raises:
            Exception: if values delegated to model initializers are invalid.
            ValueError: if to or sender are malformed according to App Engine
                (note that well-formed values do not guarantee success).
        """
        return (None, None)


class TemplateResolver(object):
    """Gets templates used to send auth-related notifications.

    By default there are no auth-related notifications, so the implementation
    returns no templates.
    """

    @classmethod
    def get(cls, unused_path, unused_locale=None):
        """Gets a single template (None in default implementation).

        Args:
            unused_path: string. Name of template.
            unused_locale: string. The user's requested locale code.

        Returns:
            Template instance (or None in the default implementation).
        """
        return None

    @classmethod
    def get_email_templates(cls, unused_action, unused_locale=None):
        """Returns templates used to compose an email (Nones by default).

        Args:
            unused_action: string. Identifier for the kind of email.
            unused_locale: string or None. The user's requested locale code.

        Returns:
            3-tuple of
            (body_html_template, body_text_template, subject_text_template).

        Raises:
            Exception: if the template system encoutered a problem.
            ValueError: if the action is invalid.
        """
        return (None, None, None)


class UsersServiceManager(object):
    """Accessor/mutator for the users service executing at runtime."""

    _SERVICE = None

    @classmethod
    def get(cls):
        return cls._SERVICE

    @classmethod
    def set(cls, users_service):
        cls._SERVICE = users_service
