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

"""GITKit federated authentication module.

This module lets Course Builder use the Google Identity Toolkit (GITKit;
https://developers.google.com/identity/toolkit/) in place of the App Engine
users service (https://cloud.google.com/appengine/docs/python/users/) for user
authentication.

GITKit is a federated identity provider, meaning end users can choose from a set
of third-party identity providers (Google, Facebook, etc.) or username/password
via an external service (accountchooser.com). GITKit provides a common interface
for interacting with all of these providers; multiple providers can be enabled
at runtime by configuration; and users can select between any of these providers
each time they authenticate.

Currently, this implementation is known to work with the Google and Facebook
providers. Other providers are likely possible but have not been tested.
Notably, we do not yet support username/password via accountchooser.com, and any
attempts to use email functionality (either with Google and Facebook, or with
username/password) will break.

TODO(johncox): add email functionality (forgot password, etc.).
TODO(johncox): add support for username/password.

The basic authentication flow is

1) User clicks sign in button. This captures some information, most notably
   their desired destination after authentication, that is delegated through the
   steps below.
2) This takes them to the sign-in widget.
3) The sign-in widget takes them to GITKit's accountchooser.com site.
4) They select a provider and authenticate. They are dispatched to the provider
   (Google, Facebook, etc.) to prove their identity. If they fail, the flow
   ends.
5) If they succeed, they're sent back to GITKit.
6) GITKit sends them back to our sign-in handler. This is a post-authentication
   callback that does bookkeeping on our end to keep user records up to date.
7) We then 302 the user to the sign-in continue handler. This is a customization
   seam: if you wish to extend the authentication flow, you can override this
   handler to do whatever you like. You must conclude by 302-ing the user to
   their requested destination.

The sign-out flow works similarly:

1) User clicks a sign out button. We capture their desired end destination and
   delegate it through the chain.
2) They go our sign out handler, which calls Gitkit's sign out.
3) We redirect to the continue handler.
4) The sign out continue handler is a customization seam for you to add
   behavior. It must 302 the user to their requested final destination.

Configuring this system is complex:

1) Enable this module in app.yaml. It is disabled by default.
2) Edit its configuration in resources/config.yaml. This configuration file lets
   you switch between the App Engine auth system, and it lets you define a set
   of admins. See that file for details and workflow. Briefly, you need to use
   this to bootstrap the auth process, since you need to provision keys/secrets
   with each external authentication provider and enter them via the Course
   Builder admin page. That page requires an auth system in order to function.

   Deploy a version with your email address in config.yaml's admins list and
   enabled: False.
4) Provision your keys and secrets with each provider. Enter them via the Course
   Builder admin console. See GITKit's docs (linked above) for pointers to each
   provider's applications for doing this.
5) Edit config.yaml and flip enabled to True.
6) Deploy a new version.

Good luck!
"""

__author__ = [
    'johncox@google.com (John Cox)',
]

import logging
import os
import threading
import urllib

import httplib2
import webapp2
import yaml

from common import jinja_utils
from common import users
from common import utils
from controllers import utils as controllers_utils
from models import config
from models import custom_modules
from models import models
from models import transforms

import appengine_config

from google.appengine.ext import db
from identitytoolkit import gitkitclient
from oauth2client import client

_BAD_CRYPTO_NEEDLE = 'PKCS12 format is not supported by the PyCrypto library'
_BASE_PATH = os.path.dirname(os.path.abspath(__file__))
_BASE_URL = '/modules/gitkit'
_BROWSER_API_KEY_NAME = 'browser_api_key'
_DEST_URL_NAME = 'dest_url'
_EMAIL_CHANGE_EVENT_SOURCE = 'gitkit-email-change'
_EMAIL_URL = '%s/email' % _BASE_URL
_EMAIL_URL_NAME = 'email_url'
_GITKIT_DEST_URL_NAME = 'signInSuccessUrl'
_GITKIT_TOKEN_COOKIE_NAME = 'gtoken'
_RESOURCES_DIR = os.path.join(_BASE_PATH, 'resources')
_SERVICE_ACCOUNT_EMAIL_NAME = 'client_email'
_SERVICE_ACCOUNT_KEY_NAME = 'private_key'

_BRANDING_URL = '%s/branding' % _BASE_URL
_BRANDING_URL_NAME = 'branding_url'

_FAVICON_PATH = os.path.join(_RESOURCES_DIR, 'favicon.ico')
_FAVICON_URL = '%s/favicon.ico' % _BASE_URL
_FAVICON_URL_NAME = 'favicon_url'

_SIGN_IN_URL = '%s/signin' % _BASE_URL
_SIGN_IN_URL_NAME = 'signin_url'
_SIGN_IN_CONTINUE_URL = '%s/continue' % _SIGN_IN_URL

_SIGN_OUT_URL = '%s/signout' % _BASE_URL
_SIGN_OUT_CONTINUE_URL = '%s/continue' % _SIGN_OUT_URL

_TITLE_NAME = 'title'

_WIDGET_URL = '%s/widget' % _BASE_URL

_CONFIG_YAML_ADMINS_NAME = 'admins'
_CONFIG_YAML_ENABLED_NAME = 'enabled'
_CONFIG_YAML_PATH = os.path.join(_RESOURCES_DIR, 'config.yaml')

_TEMPLATES_DIR = os.path.join(_BASE_PATH, 'templates')
_BRANDING_TEMPLATE_PATH = 'branding.html'
_SIGN_OUT_TEMPLATE_PATH = 'signout.html'
_WIDGET_TEMPLATE_PATH = 'widget.html'

_LOG = logging.getLogger('modules.gitkit.gitkit')

_BROWSER_API_KEY = config.ConfigProperty(
    'gcb_modules_gitkit_browser_api_key', str,
    ('Browser API Key from the Google Developer console. This field is found '
     'under Key from browser applications > API key. See %s for instructions') %
        'https://developers.google.com/identity/toolkit/web/configure-service',
    default_value='', label='GITKit module browser API key')
_CLIENT_ID = config.ConfigProperty(
    'gcb_modules_gitkit_client_id', str,
    ('Client ID from the Google Developer console. This field is found under '
     'Client ID for web application > Client ID. See %s for instructions') %
        'https://developers.google.com/identity/toolkit/web/configure-service',
    default_value='', label='GITKit module client ID')
_SERVER_API_KEY = config.ConfigProperty(
    'gcb_modules_gitkit_server_api_key', str,
    ('Server API key from the Google Developer console. This field is found '
     'under Key for server applications > API key. See %s for instructions') %
        'https://developers.google.com/identity/toolkit/web/configure-service',
    default_value='', label='GITKit module server API key')
_SERVICE_ACCOUNT_JSON = config.ConfigProperty(
    'gcb_modules_gitkit_service_account_json', str,
    ('JSON file contents from Google Developer console. To create, click '
     '"Generate new JSON key", and copy the contents in here. See %s for '
     'instructions') %
        'https://developers.google.com/identity/toolkit/web/configure-service',
    default_value='', label='GITKit module service account JSON')
_TITLE = config.ConfigProperty(
    'gcb_modules_gitkit_title', str, 'Title of accountchooser.com page',
    default_value='Please sign in', label='GITKit module widget title')


def _make_gitkit_service(
        client_id, server_api_key, service_account_email, service_account_key,
        widget_url, http=None):
    # Extracted to helper for easy swap() in tests.
    return GitkitService(
        client_id, server_api_key, service_account_email,
        service_account_key, widget_url, http=http)


class EmailMapping(models.BaseEntity):
    """A mapping between GITKit email and user_id.

    We update this mapping every time the user signs on. GITKit user_ids are not
    scoped to a Course Builder course; consequently, we force storage of these
    entities in the global namespace. This is also desirable because the
    authentication handlers are not themselves namespaced.
    """

    email = db.StringProperty(required=True)

    _PROPERTY_EXPORT_BLACKLIST = [email]

    @classmethod
    @db.transactional
    def create_or_update(cls, email, user_id):
        """Returns key, bool where bool is True iff datastore write."""
        with utils.Namespace(appengine_config.DEFAULT_NAMESPACE_NAME):
            entity = cls.get_by_user_id(user_id)

            if not entity:
                return cls._new(email, user_id).put(), True
            elif entity and entity.email != email:
                entity.email = email
                return entity.put(), True
            else:
                return entity.key(), False

    @classmethod
    def get_by_user_id(cls, user_id):
        with utils.Namespace(appengine_config.DEFAULT_NAMESPACE_NAME):
            return db.get(cls._get_key(user_id))

    @classmethod
    def safe_key(cls, db_key, transform_fn):
        with utils.Namespace(appengine_config.DEFAULT_NAMESPACE_NAME):
            return db.Key.from_path(
                cls.kind(), transform_fn(db_key.id_or_name()))

    @classmethod
    def _get_key(cls, user_id):
        with utils.Namespace(appengine_config.DEFAULT_NAMESPACE_NAME):
            return db.Key.from_path(cls.kind(), user_id)

    @classmethod
    def _new(cls, email, user_id):
        with utils.Namespace(appengine_config.DEFAULT_NAMESPACE_NAME):
            return cls(key_name=user_id, email=email)


class EmailUpdatePolicy(object):
    """Policy that updates email mappings based on auth provider state."""

    @classmethod
    def apply(cls, user):
        user_id = user.user_id()
        student = models.Student.get_by_user_id(user.user_id())
        new_email = user.email()
        old_email = student.federated_email if student else None

        key, caused_write = EmailMapping.create_or_update(new_email, user_id)
        if caused_write:
            data = transforms.dumps({'from': old_email, 'to': new_email})

            with utils.Namespace(appengine_config.DEFAULT_NAMESPACE_NAME):
                models.EventEntity.record(
                    _EMAIL_CHANGE_EVENT_SOURCE, user, data)


class FederatedEmailResolver(users.FederatedEmailResolver):

    @classmethod
    def get(cls, user_id):
        entity = EmailMapping.get_by_user_id(user_id)
        return entity.email if entity else None


class GitkitService(object):

    # Wire ops cause nonintuitive numbers of RPCs that can make operation slow
    # (for example, the first call often gets public certs). Cache these results
    # and share them across all instances within a process.
    _CACHE = client.MemoryCache()

    def __init__(self,
            client_id, server_api_key, service_account_email,
            service_account_key, widget_url, http=None):
        self._instance = gitkitclient.GitkitClient(
            client_id, service_account_email, service_account_key,
            http=http if http is not None else httplib2.Http(self._CACHE),
            server_api_key=server_api_key, widget_url=widget_url)

    def get_provider_id(self, token):
        """Returns the provider id string if token is valid, else None.

        Args:
            token: string. Raw GITKit response token.

        Raises:
            GitkitClientError: if invalid input from caller.
            GitkitServerError: if error from GITKit server.
            RuntimeError: if GITKit is misconfigured.

        Returns:
            String. An identifier for the user's provider (for example,
            'google.com').
        """
        gitkit_user = self._get_gitkit_user(token)
        return gitkit_user.provider_id if gitkit_user else None

    def get_user(self, token):
        """Returns a users.User if token is valid, else None.

        This method also verifies the GITKit token. If the token is invalid we
        return None. Note that token age is one of the things that can make a
        token invalid. This means persisting this object is risky, because there
        is no guarantee that an old object's token is still valid.

        If having a valid user is important to you, always call this method
        rather than re-using a previously-returned value. Note that it may
        cause an RPC in order to get public certs, but unless you pass your own
        http object to __init__, responses are cached across _Gitkit intances.

        Args:
            token: string. Raw GITKit response token.

        Raises:
            GitkitClientError: if invalid input from caller.
            GitkitServerError: if error from GITKit server.
            RuntimeError: if GITKit is misconfigured.

        Returns:
            users.User if token is valid else None.
        """
        gitkit_user = self._get_gitkit_user(token)
        return self._get_users_user(gitkit_user) if gitkit_user else None

    def _get_gitkit_user(self, token):
        try:
            return self._instance.VerifyGitkitToken(token)
        except NotImplementedError, e:
            # When GITKit is misconfigured, the error it returns complains about
            # bad crypto. Detecting misconfiguration this way is risky: we could
            # be getting a false positive from real bad crypto. There is no good
            # way to disambiguate, and the value of giving a useful error
            # message here outweighs the rare chance of a false positive where
            # someone has turned off pycrypto in prod (which would require them
            # changing the libraries in app.yaml, and is really a you-broke-it-
            # you-bought-it situation).
            if _BAD_CRYPTO_NEEDLE in e.message:
                raise RuntimeError(
                    'Unable to communicate with users service. Please check '
                    'your configuration values and try again.')

    def _get_users_user(self, gitkit_user):
        """Gets a users.User given a gitkitclient.GitkitUser."""
        # Note that we do not attempt to set federated provider information on
        # the user. Their general-sounding names notwithstanding, these are
        # specific to GAE's OpenID federated identity implementation, which is
        # not us. Note also that the private __auth_domain of the user will be
        # drawn from os.environ, not from GITKit (so it is likely to be
        # 'gmail.com'). Clients who rely on the auth domain are already breaking
        # encapsulation, so they're on their own.
        #
        # Note that user_id here is the GITKit-specific identifier, unique
        # across all GITKit identity providers. It has no relationship to the
        # actual id of the user at the identity provider itself. If clients have
        # a need for underlying information from the identity provider, they
        # must obtain it on their own. The user_id is PII.
        return users.User(
            email=gitkit_user.email, _user_id=gitkit_user.user_id)


class RequestContext(webapp2.RequestContext):

    def __enter__(self):
        request, response = super(RequestContext, self).__enter__()
        runtime_config = Runtime.get_runtime_config(
            request.host, request.scheme)

        # Do *not* validate the config -- some requests will not have values,
        # and this must be OK (for example, when rendering the admin console so
        # a user can populate configuration data, there will not yet be
        # configuration data, and rejecting the config as invalid will prevent
        # users from taking the actions necessary to make the config valid).
        # Downstream consumers of the config will need to validate it before
        # use.
        Runtime.set_current_runtime_config(runtime_config)
        Runtime.set_current_token(
            request.cookies.get(_GITKIT_TOKEN_COOKIE_NAME))

        return request, response

    def __exit__(self, exc_type, exc_value, traceback):
        Runtime.set_current_runtime_config(None)
        Runtime.set_current_token(None)

        return super(RequestContext, self).__exit__(
            exc_type, exc_value, traceback)


class Runtime(object):
    """Accessor for system runtime state."""

    _CONFIG_YAML = None  # Cache to avoid repeated filesystem hits.
    _threadlocal = threading.local()
    _threadlocal.current_runtime_config = None
    _threadlocal.current_token = None

    @classmethod
    def get_runtime_config(cls, host, scheme):
        """Gets runtime config or throws ValueError if system misconfigured."""
        return RuntimeConfig(
            cls._get_admins(), cls._get_browser_api_key(), cls._get_client_id(),
            cls._get_enabled(), cls._get_server_api_key(),
            cls._get_service_account_email(), cls._get_service_account_key(),
            cls._get_sign_out_url(host, scheme), cls._get_title(),
            cls._get_widget_url(host, scheme))

    @classmethod
    def get_current_runtime_config(cls):
        return cls._threadlocal.current_runtime_config

    @classmethod
    def get_current_token(cls):
        return cls._threadlocal.current_token

    @classmethod
    def set_current_runtime_config(cls, value):
        cls._threadlocal.current_runtime_config = value

    @classmethod
    def set_current_token(cls, value):
        cls._threadlocal.current_token = value

    @classmethod
    def _get_admins(cls):
        value = cls._get_config_yaml().get(_CONFIG_YAML_ADMINS_NAME)
        return value or []

    @classmethod
    def _get_browser_api_key(cls):
        return _BROWSER_API_KEY.value

    @classmethod
    def _get_client_id(cls):
        return _CLIENT_ID.value

    @classmethod
    def _get_config_yaml(cls):
        if cls._CONFIG_YAML is None:
            try:
                with open(_CONFIG_YAML_PATH) as f:
                    cls._CONFIG_YAML = yaml.safe_load(f.read())
            except:  # All errors are the same. pylint: disable=bare-except
                _LOG.error('%s missing or malformed', _CONFIG_YAML_PATH)
                cls._CONFIG_YAML = {}

        return cls._CONFIG_YAML

    @classmethod
    def _get_enabled(cls):
        return cls._get_config_yaml().get(_CONFIG_YAML_ENABLED_NAME)

    @classmethod
    def _get_service_account_email(cls):
        return cls._get_service_account_json().get(
            _SERVICE_ACCOUNT_EMAIL_NAME, '')

    @classmethod
    def _get_server_api_key(cls):
        return _SERVER_API_KEY.value

    @classmethod
    def _get_service_account_json(cls):
        parsed = {}
        try:
            parsed = transforms.loads(_SERVICE_ACCOUNT_JSON.value)
        except:  # Swallow all errors. pylint: disable=bare-except
            pass

        return parsed

    @classmethod
    def _get_service_account_key(cls):
        return cls._get_service_account_json().get(
            _SERVICE_ACCOUNT_KEY_NAME, '')

    @classmethod
    def _get_sign_out_url(cls, host, scheme):
        return '%s://%s%s' % (scheme, host, _SIGN_OUT_URL)

    @classmethod
    def _get_title(cls):
        return _TITLE.value

    @classmethod
    def _get_widget_url(cls, host, scheme):
        return '%s://%s%s' % (scheme, host, _WIDGET_URL)


class RuntimeConfig(object):
    """DDO for system configuration data."""

    def __init__(
            self, admins, browser_api_key, client_id, enabled, server_api_key,
            service_account_email, service_account_key, sign_out_url, title,
            widget_url):
        self.admins = admins
        self.browser_api_key = browser_api_key
        self.client_id = client_id
        self.enabled = enabled
        self.server_api_key = server_api_key
        self.service_account_email = service_account_email
        self.service_account_key = service_account_key
        self.sign_out_url = sign_out_url
        self.title = title
        self.widget_url = widget_url

    def __str__(self):
        return str(vars(self))

    def validate(self):
        errors = []
        if not self._admins_valid():
            errors.append(
                '%s %s missing or invalid' % (
                    _CONFIG_YAML_PATH, _CONFIG_YAML_ADMINS_NAME))
        if not self.browser_api_key:
            errors.append(_BROWSER_API_KEY.name + ' not set')
        if not self.client_id:
            errors.append(_CLIENT_ID.name + ' not set')
        if not self._enabled_valid():
            errors.append(
                '%s %s missing or invalid' % (
                    _CONFIG_YAML_PATH, _CONFIG_YAML_ENABLED_NAME))
        if not self.server_api_key:
            errors.append(_SERVER_API_KEY.name + ' not set')
        if not self.service_account_email:
            errors.append(
                '%s not set in %s' % (
                    _SERVICE_ACCOUNT_EMAIL_NAME, _SERVICE_ACCOUNT_JSON.name))
        if not self.service_account_key:
            errors.append(
                '%s not set in %s' % (
                    _SERVICE_ACCOUNT_KEY_NAME, _SERVICE_ACCOUNT_JSON.name))
        if not self.title:
            errors.append('%s missing or invalid' % (_TITLE.name))

        if errors:
            raise RuntimeError(
                'GITKit integration misconfigured; errors:\n%s' % (
                    '\n'.join(sorted(errors))))

        return True

    def _admins_valid(self):
        return isinstance(self.admins, list) and len(self.admins) >= 1

    def _enabled_valid(self):
        return isinstance(self.enabled, bool)


class UsersService(users.AbstractUsersService):

    @classmethod
    def create_login_url(
            cls, dest_url=None, _auth_domain=None, federated_identity=None):
        runtime_config = Runtime.get_current_runtime_config()
        if not (runtime_config and runtime_config.enabled):
            return users.AppEnginePassthroughUsersService.create_login_url(
                dest_url=dest_url, _auth_domain=_auth_domain,
                federated_identity=federated_identity)

        return cls._get_login_url(runtime_config.widget_url, dest_url=dest_url)

    @classmethod
    def create_logout_url(cls, dest_url):
        runtime_config = Runtime.get_current_runtime_config()
        if not (runtime_config and runtime_config.enabled):
            return users.AppEnginePassthroughUsersService.create_logout_url(
                dest_url)

        return cls._get_logout_url(dest_url=dest_url)

    @classmethod
    def get_current_user(cls):
        runtime_config = Runtime.get_current_runtime_config()

        user = users.AppEnginePassthroughUsersService.get_current_user()
        if not runtime_config:
            return user

        if not runtime_config.enabled:
            if not user:
                return
            elif user.email() in runtime_config.admins:
                return user
            else:
                _LOG.warning(
                    'Disallowing get_current_user() for non-admin %s while %s '
                    '%s False', user.email(), _CONFIG_YAML_PATH,
                    _CONFIG_YAML_ENABLED_NAME)
                return None

        token = Runtime.get_current_token()
        if not token:
            return None

        service = _make_gitkit_service(
            runtime_config.client_id, runtime_config.server_api_key,
            runtime_config.service_account_email,
            runtime_config.service_account_key,
            widget_url=runtime_config.widget_url)

        # Let GITKit errors percolate up -- desired behavior when auth is broken
        # is a 500.
        return service.get_user(token)

    @classmethod
    def get_email_update_policy_class(cls):
        return EmailUpdatePolicy

    @classmethod
    def get_federated_email_resolver_class(cls):
        return FederatedEmailResolver

    @classmethod
    def get_request_context_class(cls):
        return RequestContext

    @classmethod
    def is_current_user_admin(cls):
        runtime_config = Runtime.get_current_runtime_config()
        if not (runtime_config and runtime_config.enabled):
            return (
                users.AppEnginePassthroughUsersService.is_current_user_admin())

        user = cls.get_current_user()
        # App Engine does not provide an API for getting a list of admin users.
        # Consequently, we must provide one.
        return user and user.email() in runtime_config.admins

    @classmethod
    def _get_login_url(cls, widget_url, dest_url=None):
        query = {'mode': 'select'}
        if dest_url:
            query[_GITKIT_DEST_URL_NAME] = dest_url

        return '%s?%s' % (widget_url, urllib.urlencode(query))

    @classmethod
    def _get_logout_url(cls, dest_url):
        query = {_DEST_URL_NAME: dest_url}
        return '%s?%s' % (_SIGN_OUT_URL, urllib.urlencode(query))


class BaseHandler(controllers_utils.BaseHandler):

    def _get_next_url(self, prefix, url_param_name):
        dest_url = self.request.get(url_param_name)
        suffix = ''
        if dest_url:
            suffix = '?%s' % urllib.urlencode({_DEST_URL_NAME: dest_url})

        return '%s%s' % (prefix, suffix)

    def _get_redirect_url_from_dest_url(self):
        dest_url = self.request.get(_DEST_URL_NAME)
        return str(dest_url) if dest_url else '/'


class AccountChooserCustomizationBaseHandler(BaseHandler):
    """Base handler for resources loaded by accountchooser.com.

    These resources must set CORS headers so they can be loaded by an external
    domain. Note, though, that you will run afoul of security policies on
    accountchooser.com if you attempt to load content via http rather than
    https. This is not an issue for prod, but for dev you are likely to get
    warnings or errors when loading data into accountchooser.com.
    """

    def get(self):
        self.response.headers['Access-Control-Allow-Origin'] = (
            'https://www.accountchooser.com')
        self._real_get()

    def _real_get(self):
        raise NotImplementedError


class BrandingHandler(AccountChooserCustomizationBaseHandler):

    def _real_get(self):
        # Add content to templates/branding.html to customize the lefthand side
        # of the accountchooser.com UX. This HTML is scrubbed by
        # accountchooser.com before render; see
        # https://developers.google.com/identity/toolkit/web/setup-frontend for
        # details.
        template = jinja_utils.get_template(
            _BRANDING_TEMPLATE_PATH, [_TEMPLATES_DIR])
        self.response.out.write(template.render({}))


class EmailHandler(BaseHandler):

    def get(self):
        # TODO(johncox): implement.
        raise NotImplementedError


class FaviconHandler(AccountChooserCustomizationBaseHandler):

    def _real_get(self):
        self.response.headers['Content-Type'] = 'image/x-icon'

        with open(_FAVICON_PATH) as f:
            self.response.out.write(f.read())


class SignInContinueHandler(BaseHandler):
    """This handler is a seam to add business logic to the login flow."""

    def get(self):
        """Your business logic here.

        This method must end with redirect to _get_redirect_url_from_dest_url().
        """
        self.redirect(self._get_redirect_url_from_dest_url())


class SignInHandler(BaseHandler):

    def get(self):
        users_service = users.UsersServiceManager.get()
        runtime_config = Runtime.get_current_runtime_config()
        try:
            runtime_config.validate()
        except RuntimeError as e:
            _LOG.error(e.message)
            self.error(500)
            return

        token = Runtime.get_current_token()
        if not token:
            _LOG.error(
                'Bad request: %s not found in GITKit request cookies',
                _GITKIT_TOKEN_COOKIE_NAME)
            self.error(400)
            return

        service = _make_gitkit_service(
            runtime_config.client_id, runtime_config.server_api_key,
            runtime_config.service_account_email,
            runtime_config.service_account_key,
            widget_url=runtime_config.widget_url)

        try:
            user = service.get_user(token)
        # All errors are the same. pylint: disable=broad-except
        except Exception, e:
            _LOG.error('Error communicating with GITKit: %s', e)
            self.error(500)
            return

        if not user:
            _LOG.error('Bad request: invalid token')
            self.error(400)
            return

        users_service.get_email_update_policy_class().apply(user)
        self.redirect(self._get_continue_url())

    def _get_continue_url(self):
        return self._get_next_url(_SIGN_IN_CONTINUE_URL, _GITKIT_DEST_URL_NAME)


class SignOutContinueHandler(BaseHandler):
    """This handler is a seam to add business logic to the logout flow."""

    def get(self):
        """Your business logic here.

        This method must end with redirect to _get_redirect_url_from_dest_url().
        """
        user = users.get_current_user()
        if user:
            _LOG.error('User still in session after sign out; aborting')
            self.error(500)
            return

        self.redirect(self._get_redirect_url_from_dest_url())


class SignOutHandler(controllers_utils.BaseHandler):

    def get(self):
        runtime_config = Runtime.get_current_runtime_config()
        try:
            runtime_config.validate()
        except RuntimeError as e:
            _LOG.error(e.message)
            self.error(500)
            return

        template = jinja_utils.get_template(
            _SIGN_OUT_TEMPLATE_PATH, [_TEMPLATES_DIR])
        self.response.out.write(template.render({
            _BROWSER_API_KEY_NAME: runtime_config.browser_api_key,
            _DEST_URL_NAME: _DEST_URL_NAME,
        }))


class WidgetHandler(controllers_utils.BaseHandler):

    def get(self):
        runtime_config = Runtime.get_current_runtime_config()
        try:
            runtime_config.validate()
        except RuntimeError as e:
            _LOG.error(e.message)
            self.error(500)
            return

        template = jinja_utils.get_template(
            _WIDGET_TEMPLATE_PATH, [_TEMPLATES_DIR])
        self.response.out.write(template.render({
            _BRANDING_URL_NAME: self._get_branding_url(),
            _BROWSER_API_KEY_NAME: runtime_config.browser_api_key,
            _EMAIL_URL_NAME: _EMAIL_URL,
            _FAVICON_URL_NAME: self._get_favicon_url(),
            _SIGN_IN_URL_NAME: _SIGN_IN_URL,
            _TITLE_NAME: runtime_config.title,
        }))

    def _get_branding_url(self):
        return self.request.host_url + _BRANDING_URL

    def _get_favicon_url(self):
        return self.request.host_url + _FAVICON_URL


custom_module = None
GLOBAL_HANDLERS = [
    (_BRANDING_URL, BrandingHandler),
    (_EMAIL_URL, EmailHandler),
    (_FAVICON_URL, FaviconHandler),
    (_SIGN_IN_URL, SignInHandler),
    (_SIGN_IN_CONTINUE_URL, SignInContinueHandler),
    (_SIGN_OUT_URL, SignOutHandler),
    (_SIGN_OUT_CONTINUE_URL, SignOutContinueHandler),
    (_WIDGET_URL, WidgetHandler),
]
NAMESPACED_HANDLERS = []


def register_module():
    # Allow global per CB module pattern.  # pylint: disable=global-statement
    global custom_module

    def on_module_enabled():
        users.UsersServiceManager.set(UsersService)

    custom_module = custom_modules.Module(
        'GITKit Module', 'GITKit Federated Authentication Module',
        GLOBAL_HANDLERS, NAMESPACED_HANDLERS,
        notify_module_enabled=on_module_enabled)

    return custom_module
