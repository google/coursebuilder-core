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

"""Remote environment manager for extract-transform-load utilities."""

__author__ = [
    'johncox@google.com',
]

import os
import sys
import appengine_config

# Override SERVER_SOFTWARE before doing any App Engine imports so import-time
# detection of dev mode, done against SERVER_SOFTWARE of 'Development*', fails.
# Once imports are done, this environment variable can be reset as needed (for
# tests, etc.). pylint: disable-msg=g-import-not-at-top
SERVER_SOFTWARE = 'Production Emulation'
if appengine_config.PRODUCTION_MODE:
    sys.exit('Running etl/tools/remote.py in production is not supported.')
os.environ['SERVER_SOFTWARE'] = SERVER_SOFTWARE

from google.appengine.ext.remote_api import remote_api_stub
from google.appengine.tools import appengine_rpc
from google.appengine.tools import remote_api_shell

# String. Used to detect appspot.com servers.
_APPSPOT_SERVER_SUFFIX = 'appspot.com'
# String. Password used when a password is not necessary.
_BOGUS_PASSWORD = 'bogus_password'
# String. Infix for google.com application ids.
_GOOGLE_APPLICATION_INFIX = 'google.com'
# String. Prefix App Engine uses application ids in the dev appserver.
_LOCAL_APPLICATION_ID_PREFIX = 'dev~'
# String. Prefix used to detect if a server is running locally.
_LOCAL_SERVER_PREFIX = 'localhost'
# String. Prefix App Engine uses for application ids in production.
_REMOTE_APPLICATION_ID_PREFIX = 's~'
# String. Email address used unless os.environ['USER_EMAIL'] is set in tests.
_TEST_EMAIL = 'test@example.com'
# String. os.ENVIRON['SERVER_SOFTWARE'] value that indicates we're running under
# the test environment.
TEST_SERVER_SOFTWARE = 'Test'


class Error(Exception):
    """Base error type."""


class EnvironmentAuthenticationError(Error):
    """Raised when establishing an environment fails due to bad credentials."""


class Environment(object):
    """Sets up the execution environment to use remote_api for RPCs.

    As with any use of remote_api, this has three important caveats:

    1. By going through the Remote API rather than your application's handlers,
       you are bypassing any business logic in those handlers. It is easy in
       this way to accidentally corrupt the system receiving your RPCs.
    2. There is no guarantee that the code running on the system receiving your
       RPCs is the same version as the code running locally. It is easy to have
       version skew that corrupts the destination system.
    3. Execution is markedly slower than running in production.
    """

    def __init__(
        self, application_id, server, path='/_ah/remote_api'):
        """Constructs a new Environment.

        Args:
            application_id: string. The application id of the environment
                (myapp).
            server: string. The full name of the server to connect to
                (myurl.appspot.com).
            path: string. The URL of your app's remote api entry point.
        """
        self._application_id = application_id
        self._path = path
        self._server = server

    @staticmethod
    def _dev_appserver_auth_func():
        """Auth function to run for dev_appserver (bogus password)."""
        return raw_input('Email: '), _BOGUS_PASSWORD

    @staticmethod
    def _test_auth_func():
        """Auth function to run in tests (bogus username and password)."""
        return os.environ.get('USER_EMAIL', _TEST_EMAIL), _BOGUS_PASSWORD

    def _get_auth_func(self):
        """Returns authentication function for the remote API."""
        if os.environ.get('SERVER_SOFTWARE', '').startswith(
                TEST_SERVER_SOFTWARE):
            return self._test_auth_func
        elif self._is_localhost():
            return self._dev_appserver_auth_func
        else:
            return remote_api_shell.auth_func

    def _get_internal_application_id(self):
        """Returns string containing App Engine's internal id representation."""
        prefix = _REMOTE_APPLICATION_ID_PREFIX
        if self._is_localhost():
            prefix = _LOCAL_APPLICATION_ID_PREFIX
        elif not self._is_appspot():
            prefix = '%s%s:' % (prefix, _GOOGLE_APPLICATION_INFIX)
        return prefix + self._application_id

    def _get_secure(self):
        """Returns boolean indicating whether or not to use https."""
        return not self._is_localhost()

    def _is_appspot(self):
        """Returns True iff server is appspot.com."""
        return self._server.endswith(_APPSPOT_SERVER_SUFFIX)

    def _is_localhost(self):
        """Returns True if environment is dev_appserver and False otherwise."""
        return self._server.startswith(_LOCAL_SERVER_PREFIX)

    def establish(self):
        """Establishes the environment for RPC execution."""
        try:
            remote_api_stub.ConfigureRemoteApi(
                self._get_internal_application_id(), self._path,
                self._get_auth_func(), servername=self._server,
                save_cookies=True, secure=self._get_secure(),
                rpc_server_factory=appengine_rpc.HttpRpcServer)
            remote_api_stub.MaybeInvokeAuthentication()
        except AttributeError:
            raise EnvironmentAuthenticationError
