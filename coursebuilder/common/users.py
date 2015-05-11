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
    return UsersServiceManager.get()._create_login_url(
        dest_url=dest_url, _auth_domain=_auth_domain,
        federated_identity=federated_identity)


def create_logout_url(dest_url):
    # Treat as module-protected. pylint: disable=protected-access
    return UsersServiceManager.get()._create_logout_url(dest_url)


def get_current_user():
    # Treat as module-protected. pylint: disable=protected-access
    return UsersServiceManager.get()._get_current_user()


def is_current_user_admin():
    # Treat as module-protected. pylint: disable=protected-access
    return UsersServiceManager.get()._is_current_user_admin()


# Public classes from google.appengine.api.users. Keep protected symbols in case
# clients clobber the public ones.

_User = users.User
User = _User


# Base classes, default implementation, and manager.


class Context(object):
    """Default (noop) Context implementation.

    Provides pre- (__enter__) and post- (__exit__) hooks around handler
    dispatch() calls. Can be used to establish invariants or do teardown. Usage:

        with UsersServiceManager.get().get_context(handler) as c:
            handler.dispatch()
    """

    def __init__(self, handler):
        """Creates a new Context.

        Args:
            handler: controllers.sites.ApplicationRequestHandler. The handler
                for the current request.
        """
        self.handler = handler

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        pass


class AbstractUsersService(object):
    """Base users service for custom auth integrations.

    Your implementations must fulfill the contract at
    https://cloud.google.com/appengine/docs/python/users/functions. When you
    need a type from google.appengine.api.users, use the aliases above. Your
    implementations should never import google.appengine.api.users.
    """

    # Methods that constitute the service interface.

    @classmethod
    def _create_login_url(
            cls, dest_url=None, _auth_domain=None, federated_identity=None):
        raise NotImplementedError

    @classmethod
    def _create_logout_url(cls, dest_url):
        raise NotImplementedError

    @classmethod
    def _get_current_user(cls):
        raise NotImplementedError

    @classmethod
    def _is_current_user_admin(cls):
        raise NotImplementedError

    # Methods that aren't part of the service interface, but are used elsewhere
    # in the system.

    @classmethod
    def get_context(cls, handler):
        """Gets the Context for this users service.

        Returns:
            Context. The Context used to provide pre- or post-request dispatch
                hooks.
        """
        return Context(handler)

    @classmethod
    def get_service_name(cls):
        """Returns the name of the auth service for display in admin site."""
        return '%s.%s' % (cls.__module__, cls.__name__)


class AppEnginePassthroughUsersService(AbstractUsersService):
    """Users service that's just a passthrough to google.appengine.api.users."""

    @classmethod
    def _create_login_url(
            cls, dest_url=None, _auth_domain=None, federated_identity=None):
        return users.create_login_url(
            dest_url=dest_url, _auth_domain=_auth_domain,
            federated_identity=federated_identity)

    @classmethod
    def _create_logout_url(cls, dest_url):
        return users.create_logout_url(dest_url)

    @classmethod
    def _get_current_user(cls):
        return users.get_current_user()

    @classmethod
    def _is_current_user_admin(cls):
        return users.is_current_user_admin()


class UsersServiceManager(object):
    """Accessor/mutator for the users service executing at runtime."""

    _SERVICE = None

    @classmethod
    def get(cls):
        return cls._SERVICE

    @classmethod
    def set(cls, users_service):
        cls._SERVICE = users_service
