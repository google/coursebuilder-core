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

"""Oauth2 module implementation.

In order to use this module with your app you must enable it in main.py by
changing

    modules.oauth2.oauth2.register_module()

to

    modules.oauth2.oauth2.register_module().enable()

Additionally, you must:

1. Visit https://appengine.google.com  Click on API Access and create a
   client id for your web app with redirect URI set to either appspot

   https://<appid>.appspot.com/<callback_uri>

   and optionally include

   http://localhost:<port>/<callback_uri>

   where <appid> is your app id, <callback_uri> is the oauth2 callback URI you'd
   like to use, and <port> is the port you'd like to use for localhost. You can
   set <port> and <callback_uri> to basically whatever you want as long as they
   are unique.

2. Once you've created the client id, click Download JSON. Take the file you get
   and overwrite client_secrets.json in this directory.

3. In the https://appengine.google.com console, click on Services and enable the
   services your app requires. For these demos, you'll need to enable Drive API
   and Google+.

Whenever you change scopes you'll need to revoke your access tokens. You can do
this at https://accounts.google.com/b/0/IssuedAuthSubTokens.

You can find a list of the available APIs at
http://api-python-client-doc.appspot.com/.

Finally, a note about dependencies. Oauth2 requires google-api-python-client.
We bundle version 1.4 with Course Builder, along with its dependencies.

Good luck!
"""

__author__ = [
    'johncox@google.com (John Cox)',
]

import os
import traceback

from apiclient import discovery
from oauth2client import appengine
import webapp2

from common import jinja_utils
from common import safe_dom
from models import custom_modules

# In real life we'd check in a blank file and set up the code to error with a
# message pointing people to https://appengine.google.com
_CLIENTSECRETS_JSON_PATH = os.path.join(
    os.path.dirname(__file__), 'client_secrets.json')
_TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), 'templates')


class _ErrorDecorator(object):
    """Decorator used when a real decorator cannot be created.

    Most often this is because there is no valid client_secrets.json. This
    decorator replaces the wrapped method with one that either is a no-op, or,
    if an error was given, displays the error.
    """

    def __init__(self, **kwargs):
        self.callback_path = 'not_enabled'
        self.error = kwargs.pop('error', '')

    def callback_handler(self):
        """Stub for API compatibility."""
        pass

    def oauth_required(self, unused_method):
        """Prints an error messsage and exits with a 500."""

        def print_error_and_return_500(
            request_handler, *unused_args, **unused_kwargs):
            contents = safe_dom.NodeList().append(
                safe_dom.Element('h1').add_text('500 internal server error')
            ).append(
                safe_dom.Element('pre').add_text(self.error)
            )
            request_handler.response.write(contents.sanitized)
            request_handler.response.status = 500

        return print_error_and_return_500


# In real life we'd want to make one decorator per service because we wouldn't
# want users to have to give so many permissions.
def _build_decorator():
    """Builds a decorator for using oauth2 with webapp2.RequestHandlers."""
    try:
        return appengine.oauth2decorator_from_clientsecrets(
            _CLIENTSECRETS_JSON_PATH,
            scope=[
                'https://www.googleapis.com/auth/drive.readonly',
                'https://www.googleapis.com/auth/plus.login',
                'https://www.googleapis.com/auth/userinfo.email',
                'https://www.googleapis.com/auth/userinfo.profile',
            ],
            message='client_secrets.json missing')
    # Deliberately catch everything. pylint: disable=broad-except
    except Exception as e:
        display_error = (
            'oauth2 module enabled, but unable to load client_secrets.json. '
            'See docs in modules/oauth2.py. Original exception was:\n\n%s') % (
                traceback.format_exc(e))
        return _ErrorDecorator(error=display_error)


_DECORATOR = _build_decorator()


class ServiceHandler(webapp2.RequestHandler):

    def build_service(self, oauth2_decorator, name, version):
        http = oauth2_decorator.credentials.authorize(oauth2_decorator.http())
        return discovery.build(name, version, http=http)


class _ExampleHandler(ServiceHandler):

    def _write_result(self, service_name, result):
        template = jinja_utils.get_template('result.html', [_TEMPLATES_DIR])
        self.response.out.write(template.render({
            'service_name': service_name,
            'result': result,
        }))


class GoogleDriveHandler(_ExampleHandler):

    @_DECORATOR.oauth_required
    def get(self):
        drive = self.build_service(_DECORATOR, 'drive', 'v2')
        about = drive.about().get().execute()
        self._write_result('Drive', about['user']['displayName'])


class GoogleOauth2Handler(_ExampleHandler):

    @_DECORATOR.oauth_required
    def get(self):
        oauth2 = self.build_service(_DECORATOR, 'oauth2', 'v2')
        userinfo = oauth2.userinfo().get().execute()
        self._write_result('Oauth2', userinfo['name'])


class GooglePlusHandler(_ExampleHandler):

    @_DECORATOR.oauth_required
    def get(self):
        plus = self.build_service(_DECORATOR, 'plus', 'v1')
        # This call will barf if you're logged in as @google.com because your
        # profile will not be fetchable. Log in as @gmail.com and you'll be
        # fine.
        me = plus.people().get(userId='me').execute()
        self._write_result('Plus', me['displayName'])


# None or custom_modules.Module. Placeholder for the module created by
# register_module.
module = None


def register_module():
    """Adds this module to the registry."""

    global module    # pylint: disable=global-statement

    handlers = [
        ('/oauth2_google_drive', GoogleDriveHandler),
        ('/oauth2_google_oauth2', GoogleOauth2Handler),
        ('/oauth2_google_plus', GooglePlusHandler),
        (_DECORATOR.callback_path, _DECORATOR.callback_handler()),
    ]
    module = custom_modules.Module('Oauth2', 'Oauth2 pages', handlers, [])

    return module
