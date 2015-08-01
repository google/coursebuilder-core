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
   provider's applications for doing this. You will also want to add each
   provider you want to enable to the idps array in templates/widget.html. This
   only affects whether or not the provider is displayed as a choice in the
   GITKit UX in some cases. Note, however, that the set of providers in the
   Google Developer Console is authoritative: if you've enabled Facebook in the
   Google Developer Console but not in widget.html, users will still be able to
   sign in with Facebook.
5) Edit config.yaml and flip enabled to True.
6) Customize your templates (see below).
7) Deploy a new version.

When we need to send email (when users change their password or email address,
for example), we localize contents using the standard template system. The
built-in templates for these flows are:

    templates/
        change_email.html: HTML body of change email messages.
        change_email.txt: plain text body of change email messages.
        change_email_subject.txt: plain text subject of change email messages.
        reset_password.html: HTML body of password reset messages.
        reset_password.txt: plain text body of password reset messages.
        reset_password_subject.txt: plain text subject of password reset
            messages.

These templates are localized via gettext(), just like all other Course Builder
templates. And just like other Course Builder templates, if you customize their
contents, you should supply translations for those customizations in each of
the languages you want to support (beyond the language the customizations are
made in, of course). You should customize these templates with your own language
and branding; the shipped templates are for example purposes only.

The user's preferred locale is determined by their HTTP headers because we often
need to localize when a user is not in session. Note that localization is
honored in our handlers and in accountchooser.com, but not in the Gitkit widget
UX. This is because, at the time of this writing, the UX created by the Gitkit
widget code is English-only. Also, there is no communication channel between
the accountchooser.com language selector and the branding handler, so they are
not guaranteed to display the same language (if, for example, the user selects
one language, but their preferred locale is a second language, two different
languages will display).

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
import jinja2
import webapp2
import yaml

from common import jinja_utils
from common import locales
from common import users
from common import utils
from controllers import utils as controllers_utils
from models import config
from models import custom_modules
from models import data_removal
from models import models
from models import services
from models import transforms

import appengine_config

from google.appengine.api import app_identity
from google.appengine.ext import db
from identitytoolkit import gitkitclient
from oauth2client import client

_BAD_CRYPTO_NEEDLE = 'PKCS12 format is not supported by the PyCrypto library'
_BASE_PATH = os.path.dirname(os.path.abspath(__file__))
_BASE_URL = '/modules/gitkit'
_BROWSER_API_KEY_NAME = 'browser_api_key'
_DEFAULT_TEMPLATE_LOCALE = 'en_US'
_DEST_URL_NAME = 'dest_url'
_EMAIL_CHANGE_EVENT_SOURCE = 'gitkit-email-change'
_EMAIL_URL = '%s/email' % _BASE_URL
_EMAIL_URL_NAME = 'email_url'
_GITKIT_DEST_URL_NAME = 'signInSuccessUrl'
_GITKIT_RESPONSE_KEY_ACTION = 'action'
_GITKIT_RESPONSE_KEY_EMAIL = 'email'
_GITKIT_RESPONSE_KEY_NEW_EMAIL = 'new_email'
_GITKIT_RESPONSE_KEY_OOB_CODE = 'oob_code'
_GITKIT_RESPONSE_KEY_OOB_LINK = 'oob_link'
_GITKIT_RESPONSE_KEY_RESPONSE_BODY = 'response_body'
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
_CHANGE_EMAIL_NOTIFICATIONS_INTENT = 'gitkit_change_email'
_CHANGE_EMAIL_TEMPLATE_PREFIX = 'change_email'
_EXTENSION_HTML = '.html'
_EXTENSION_TXT = '.txt'
_RESET_PASSWORD_NOTIFICATIONS_INTENT = 'gitkit_reset_password'
_RESET_PASSWORD_TEMPLATE_PREFIX = 'reset_password'
_SIGN_OUT_TEMPLATE_PATH = 'signout.html'
_SUBJECT_INFIX = '_subject'
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
    default_value='Please sign in', label='GITKit module account chooser title')


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

    @classmethod
    def register_for_data_removal(cls):
        data_removal.Registry.register_sitewide_indexed_by_user_id_remover(
            cls.delete_by_key)


class EmailUpdatePolicy(users.EmailUpdatePolicy):
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


class AbstractOobResponse(object):
    """Abstract return value base for GitkitService.get_oob_response()."""

    def __init__(self, response_body):
        self.response_body = response_body

    @classmethod
    def _get_expected_response_keys(cls):
        """Gets keys from gitkit response that are fed to __init__.

        GITKit responses are plain dicts. This returns a sorted list of string
        containing the keys that can be accepted by this particular child class.
        If that sorted key list exactly matches the sorted key list of a GITKit
        response dict, that dict can be cast to the particular child class type.

        Returns:
            Lexicographically-ordered list of string.
        """
        raise NotImplementedError

    @classmethod
    def make(cls, gitkit_response):
        """Casts gitkit_response dict to OobResponse or throws ValueError."""
        gitkit_response = dict(gitkit_response)  # Make a copy for mutations.
        matches, error = cls.match(gitkit_response)
        if not matches:
            raise ValueError(
                'Unable to create %s; error: %s' % (cls.__name__, error))

        # response_body must be present. It contains a json string we must
        # convert to plain old Python values.
        response_body = gitkit_response.get(_GITKIT_RESPONSE_KEY_RESPONSE_BODY)
        if response_body is None:
            raise ValueError(
                'Unable to parse GITKit OOB response: response_body missing')

        try:
            gitkit_response[_GITKIT_RESPONSE_KEY_RESPONSE_BODY] = (
                transforms.loads(response_body))
        except Exception, e:
            raise ValueError(
                'Unable to parse %s from GITKit OOB response: got %s' % (
                    _GITKIT_RESPONSE_KEY_RESPONSE_BODY, response_body))

        return cls(**gitkit_response)

    @classmethod
    def match(cls, gitkit_response):
        """Checks if a gitkit_response dict can be made into instance of cls.

        Args:
            gitkit_reponse: dict. Raw gitkitclient.GitkitClient.GetOobResult
                result.

        Returns:
            bool, string. bool is True if gitkit_response can be cast to cls and
                False otherwise. string is empty if bool is True and contains a
                descriptive error message otherwise.
        """
        actual_keys = set(gitkit_response.keys())
        expected_keys = set(cls._get_expected_response_keys())
        matches = actual_keys == expected_keys
        fmt = lambda keys: ', '.join(sorted(keys))
        error = None if matches else 'Expected: "%s", got: "%s"' % (
            fmt(expected_keys), fmt(actual_keys))
        return matches, error

    def __str__(self):
        return str(vars(self))


class AbstractOobEmailResponse(AbstractOobResponse):
    """Abstract base for all OobResponses that involve sending a user email."""

    def get_target_emails(self):
        """Gets the addresses messages about this response should be sent to."""
        # Seam in case GITKit changes their requirements about where mails
        # should be sent. This is necessary because they may elect to send email
        # to new_email rather than email when email changes, or they may elect
        # to send to both.
        return [self.email]


class OobFailureResponse(AbstractOobResponse):
    """OOB response indicating failure (but the request completed)."""

    @classmethod
    def _get_expected_response_keys(cls):
        return sorted([_GITKIT_RESPONSE_KEY_RESPONSE_BODY])

    @classmethod
    def from_error_message(cls, error_message):
        return cls(response_body={'error': error_message})


class OobChangeEmailResponse(AbstractOobEmailResponse):
    """OOB response for an email change request; requires email to user."""

    def __init__(
            self, action, email, new_email, oob_code, oob_link, response_body):
        super(OobChangeEmailResponse, self).__init__(response_body)

        if not GitkitService.is_change_email(action):
            raise ValueError(
                'Unable to parse change email response with action: %s' % (
                    action))

        self.action = action
        self.email = email
        self.new_email = new_email
        self.oob_code = oob_code
        self.oob_link = oob_link

    @classmethod
    def _get_expected_response_keys(cls):
        return sorted([
            _GITKIT_RESPONSE_KEY_ACTION, _GITKIT_RESPONSE_KEY_EMAIL,
            _GITKIT_RESPONSE_KEY_NEW_EMAIL, _GITKIT_RESPONSE_KEY_OOB_CODE,
            _GITKIT_RESPONSE_KEY_OOB_LINK, _GITKIT_RESPONSE_KEY_RESPONSE_BODY])


class OobResetPasswordResponse(AbstractOobEmailResponse):
    """OOB response for a password reset request; requires email to user."""

    def __init__(self, action, email, oob_code, oob_link, response_body):
        super(OobResetPasswordResponse, self).__init__(response_body)

        if not GitkitService.is_reset_password(action):
            raise ValueError(
                'Unable to parse reset password response with action: %s' % (
                    action))

        self.action = action
        self.email = email
        self.oob_code = oob_code
        self.oob_link = oob_link

    @classmethod
    def _get_expected_response_keys(cls):
        return sorted([
            _GITKIT_RESPONSE_KEY_ACTION, _GITKIT_RESPONSE_KEY_EMAIL,
            _GITKIT_RESPONSE_KEY_OOB_CODE, _GITKIT_RESPONSE_KEY_OOB_LINK,
            _GITKIT_RESPONSE_KEY_RESPONSE_BODY])


class GitkitService(object):

    # Wire ops cause nonintuitive numbers of RPCs that can make operation slow
    # (for example, the first call often gets public certs). Cache these results
    # and share them across all instances within a process.
    _CACHE = client.MemoryCache()
    # Known OobResponse types we can cast raw Gitkit responses into.
    _OOB_RESPONSE_TYPES = [
        OobChangeEmailResponse, OobFailureResponse, OobResetPasswordResponse,
    ]

    def __init__(self,
            client_id, server_api_key, service_account_email,
            service_account_key, widget_url, http=None):
        self._instance = gitkitclient.GitkitClient(
            client_id, service_account_email, service_account_key,
            http=http if http is not None else httplib2.Http(self._CACHE),
            server_api_key=server_api_key, widget_url=widget_url)

    @classmethod
    def get_intent(cls, action):
        """Gets intent for notifications."""
        return {
            gitkitclient.GitkitClient.CHANGE_EMAIL_ACTION: (
                _CHANGE_EMAIL_NOTIFICATIONS_INTENT),
            gitkitclient.GitkitClient.RESET_PASSWORD_ACTION: (
                _RESET_PASSWORD_NOTIFICATIONS_INTENT),
        }[action]

    @classmethod
    def is_change_email(cls, action):
        return action == gitkitclient.GitkitClient.CHANGE_EMAIL_ACTION

    @classmethod
    def is_reset_password(cls, action):
        return action == gitkitclient.GitkitClient.RESET_PASSWORD_ACTION

    @classmethod
    def _make_oob_response(cls, gitkit_response):
        """Cast gitkit_response dict to OobResponse or throw ValueError."""
        # Gitkit OOB responses are plain dicts. Many, but not all, of them
        # contain type information under the same key. Because some responses do
        # not have this type information, the best we can do is match types by
        # looking at the set of provided keys and checking it for compatibility
        # against each of our types. Individual OobResponse types can and should
        # do further validation in their initializers.
        response = None

        for oob_response_type in cls._OOB_RESPONSE_TYPES:
            match, error = oob_response_type.match(gitkit_response)
            if match:
                response = oob_response_type.make(gitkit_response)
                break

        if response is None:
            raise ValueError(
                'Unable to map GITKit OOB response to known type: %s' % (
                    gitkit_response))

        return response

    def get_oob_response(self, request_post, request_remote_addr, token=None):
        """Gets OobResponse from GITKit (or None if unexpected response type).

        Out-of-band (OOB) responses happen when a user going through a GITKit
        flow clicks a control that requires our involvement. An example of this
        is clicking the 'problems logging in?' link.

        These cause a POST to our email hander because we need to send an email
        containing GITKit data for the user to act on. Our email handler needs
        to decode the POST and respond appropriately. We do this by calling
        GITKit with the post information. GITKit responds with a dict of
        response data that can indicate an error, or a response. We cast these
        to our own types so callers can handle the different out-of-band cases
        appropriately.

        Args:
            request_post: dict or dict-like. webapp2.Response POST data.
            requst_remote_addr: string. IP address of the webapp2.Response.
            token: string or None. Optional GITKit token; will be string if the
                user is in session and None otherwise.

        Raises:
            Exception: if there is an error communicating with GITKit (if the
                service is down, for example).
            ValueError: if we got a response back we could not parse into a
                known type.

        Returns:
            OobResponse: GITKit response data, cast if the response completed
                (even if 'completed' means 'returned a failed state').
        """
        gitkit_oob_response = self._instance.GetOobResult(
            request_post, request_remote_addr, gitkit_token=token)
        return self._make_oob_response(gitkit_oob_response)

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
        http object to __init__, responses are cached across GitkitService
        intances.

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
        return self._make_users_user(gitkit_user) if gitkit_user else None

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

    def _make_users_user(self, gitkit_user):
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


class Mailer(users.Mailer):
    """Sends email messages."""

    @classmethod
    def get_sender(cls):
        """Email address of the sender.

        Must conform to the restrictions in
        https://cloud.google.com/appengine/docs/python/mail/sendingmail.
        """
        return 'noreply@%s.appspotmail.com' % app_identity.get_application_id()

    @classmethod
    def send_async(cls, locale, oob_email_response):
        """Sends email notification(s) asynchronously.

        Args:
            locale: string. The user's preferred locale code (e.g. 'en_US').
            oob_email_response: OobEmailResponse. GITKit response object
                containing information to be mailed to user.

        Returns:
            (notification_key, payload_key). A 2-tuple of datastore keys for the
                created notification and payload.

        Raises:
            Exception: if values delegated to model initializers are invalid.
            ValueError: if to or sender are malformed according to App Engine
                (note that well-formed values do not guarantee success).
        """
        users_service = users.UsersServiceManager.get()
        template_resolver = users_service.get_template_resolver_class()

        intent = GitkitService.get_intent(oob_email_response.action)
        sender = cls.get_sender()
        target_emails = oob_email_response.get_target_emails()

        # Allow all template resolution to throw. If action is valid and
        # mappings are correct, mappings will resolve correctly here. Any errors
        # here are most likely due to bad mappings in user-supplied code
        # customizations; we want loud errors so people writing customizations
        # can find and fix problems.
        oob_dict = vars(oob_email_response)
        body_html_template, body_text_template, subject_text_template = (
            template_resolver.get_email_templates(
                oob_email_response.action, locale=locale))
        body = body_text_template.render(oob_dict)
        html = body_html_template.render(oob_dict)
        subject = subject_text_template.render(oob_dict)

        for to in target_emails:
            services.notifications.send_async(
                to, sender, intent, body, subject, audit_trail=oob_dict,
                html=html)


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


class TemplateResolver(users.TemplateResolver):
    """Gets templates."""

    @classmethod
    def get(cls, path, locale=None):
        """Gets the template at path (rooted in _TEMPLATES_DIR)."""
        return cls._get_env(locale=locale).get_template(path)

    @classmethod
    def get_email_templates(cls, action, locale=None):
        """Returns templates used to compose an email.

        Args:
            action: string. AbstractOobEmailResponse action string.
            locale: string or None. The user's requested locale code.

        Returns:
            3-tuple of
            (body_html_template, body_text_template, subject_text_template).

        Raises:
            Exception: if the template system encoutered a problem.
            ValueError: if the action is invalid.
        """
        env = cls._get_env(locale=locale)
        body_html_template = env.get_template(
            cls._get_email_template_path(action, extension='.html'))
        body_text_template = env.get_template(
            cls._get_email_template_path(action, extension='.txt'))
        subject_text_template = env.get_template(
            cls._get_email_template_path(
                action, extension='.txt', subject=True))

        return (
            body_html_template, body_text_template, subject_text_template)

    @classmethod
    def _get_env(cls, locale=None):
        return jinja_utils.create_jinja_environment(
            jinja2.FileSystemLoader([_TEMPLATES_DIR]),
            locale=locale if locale else _DEFAULT_TEMPLATE_LOCALE,
            autoescape=True)

    @classmethod
    def _get_email_template_path(
            cls, action, extension=_EXTENSION_HTML, subject=False):
        assert extension in [_EXTENSION_HTML, _EXTENSION_TXT]

        prefix = None
        if GitkitService.is_change_email(action):
            prefix = _CHANGE_EMAIL_TEMPLATE_PREFIX
        elif GitkitService.is_reset_password(action):
            prefix = _RESET_PASSWORD_TEMPLATE_PREFIX
        else:
            raise ValueError(
                'Unable to resolve templates for action: %s' % action)

        infix = _SUBJECT_INFIX if subject else ''

        return '%s%s%s' % (prefix, infix, extension)


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
    def get_mailer_class(cls):
        return Mailer

    @classmethod
    def get_request_context_class(cls):
        return RequestContext

    @classmethod
    def get_template_resolver_class(cls):
        return TemplateResolver

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

    @classmethod
    def _get_locale(cls, accept_language_header=None):
        # The Accept-Language header is set to whatever the user's browser or
        # computer ordinarily wants to consume. This makes it a good bet for the
        # authoritative best locale to use, absent a database of user
        # preferences (which we do not always have because users are often not
        # signed in when going through this flow -- after all, this is where you
        # recover a lost password). We take the highest-priority locale if a
        # value is present, and chauvinistically default to en_US otherwise.
        #
        # We cannot use the normal CB locale mechanism because auth is scoped to
        # the deployment, not the course.
        locale = _DEFAULT_TEMPLATE_LOCALE

        pairs = []
        if accept_language_header:
            pairs = locales.parse_accept_language(accept_language_header)

        if pairs:
            locale = sorted(pairs, key=lambda t: t[1], reverse=True)[0][0]

        return locale

    def _format_exception(self, exception):
        return '%s: %s' % (exception.__class__.__name__, exception.message)

    def _get_accept_language_header(self):
        return self.request.headers.get('Accept-Language')

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
        locale = self._get_locale(self._get_accept_language_header())
        users_service = users.UsersServiceManager.get()
        template = users_service.get_template_resolver_class().get(
            _BRANDING_TEMPLATE_PATH, locale=locale)
        self.response.out.write(template.render({}))


class EmailRestHandler(BaseHandler):
    """Rest handler that communicates with GITKit clients we do not control.

    Their requirements are slightly different than standard CB rest clients (for
    example, they do not support XSSI prefixing, and they have their own
    requirements about response formatting).

    We never want to 500 here when handling errors -- instead, we want to
    compose failure json responses. If we 500, the Gitkit clients will hang in a
    spinner state; if we return json responses, they will display an error
    message and their UX will still be usable. We do, however, want to 500 iff
    there is an unexpected error, since that likely indicates a new problem that
    needs programmer attention.
    """

    def post(self):
        users_service = users.UsersServiceManager.get()
        runtime_config = Runtime.get_current_runtime_config()
        try:
            runtime_config.validate()
        except RuntimeError as e:
            _LOG.error(self._format_exception(e))
            self._write_failure_json_response('Server misconfigured')
            return

        token = Runtime.get_current_token()
        service = _make_gitkit_service(
            runtime_config.client_id, runtime_config.server_api_key,
            runtime_config.service_account_email,
            runtime_config.service_account_key,
            widget_url=runtime_config.widget_url)

        try:
            oob_response = service.get_oob_response(
                self.request.POST, self.request.remote_addr, token=token)
        # Treat all errors the same. pylint: disable=broad-except
        except Exception, e:
            _LOG.error('Error getting OOB response from GITKit: %s', e)
            self._write_failure_json_response('Communication error')
            return

        if isinstance(oob_response, OobFailureResponse):
            self._write_json_response(oob_response.response_body)
            return

        locale = self._get_locale(self._get_accept_language_header())
        try:
            users_service.get_mailer_class().send_async(locale, oob_response)
        # Treat all errors the same. pylint: disable=broad-except
        except Exception, e:
            _LOG.error(
                'Unable to send mail; error: %s', self._format_exception(e))
            self._write_failure_json_response('Mailer error')
            return

        self._write_json_response(oob_response.response_body)

    def _write_json_response(self, response_body):
        # GITKit requires slightly different formatting of the response compared
        # to normal CB JS clients, so we set our ordinary headers but do not
        # send the XSSI prefix.
        self.response.headers['Content-Disposition'] = 'attachment'
        self.response.headers[
            'Content-Type'] = 'application/javascript; charset=utf-8'
        self.response.headers['X-Content-Type-Options'] = 'nosniff'
        self.response.out.write(transforms.dumps(response_body))

    def _write_failure_json_response(self, error_message):
        oob_response = OobFailureResponse.from_error_message(error_message)
        self._write_json_response(oob_response.response_body)


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
            _LOG.error(self._format_exception(e))
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


class SignOutHandler(BaseHandler):

    def get(self):
        users_service = users.UsersServiceManager.get()
        runtime_config = Runtime.get_current_runtime_config()
        try:
            runtime_config.validate()
        except RuntimeError as e:
            _LOG.error(self._format_exception(e))
            self.error(500)
            return

        locale = self._get_locale(self._get_accept_language_header())
        template = users_service.get_template_resolver_class().get(
            _SIGN_OUT_TEMPLATE_PATH, locale=locale)
        self.response.out.write(template.render({
            _BROWSER_API_KEY_NAME: runtime_config.browser_api_key,
            _DEST_URL_NAME: _DEST_URL_NAME,
        }))


class WidgetHandler(BaseHandler):

    def get(self):
        users_service = users.UsersServiceManager.get()
        runtime_config = Runtime.get_current_runtime_config()
        try:
            runtime_config.validate()
        except RuntimeError as e:
            _LOG.error(self._format_exception(e))
            self.error(500)
            return

        locale = self._get_locale(self._get_accept_language_header())
        template = users_service.get_template_resolver_class().get(
            _WIDGET_TEMPLATE_PATH, locale=locale)
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
    (_EMAIL_URL, EmailRestHandler),
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
        EmailMapping.register_for_data_removal()

    custom_module = custom_modules.Module(
        'GITKit Module', 'GITKit Federated Authentication Module',
        GLOBAL_HANDLERS, NAMESPACED_HANDLERS,
        notify_module_enabled=on_module_enabled)

    return custom_module
