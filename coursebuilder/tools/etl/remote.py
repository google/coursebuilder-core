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

import logging
import sys
import traceback

from google.appengine.ext.remote_api import remote_api_stub

# Url of help documentation we send the user to if there is an authentication
# error.
_AUTH_HELP_URL = 'https://code.google.com/p/course-builder/wiki/EtlAuth'
# String. Prefix used to detect if a server is running locally.
_LOCAL_SERVER_PREFIX = 'localhost'
_LOG = logging.getLogger('coursebuilder.tools.etl')
logging.basicConfig()


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
            self, server, path='/_ah/remote_api', port=None, testing=False):
        """Constructs a new Environment.

        Args:
            server: string. The full name of the server to connect to
                (myurl.appspot.com).
            path: string. The URL of your app's remote api entry point.
            port: int. When server is 'localhost', must be set to the API port
                of the dev appserver. Ignored otherwise.
            testing: boolean. For tests only, indicates testing mode.
        """
        self._path = path
        self._port = port
        self._server = server
        self._testing = testing

    def _get_formatted_last_traceback(self):
        return ''.join(traceback.format_tb(sys.exc_info()[2]))

    def _get_secure(self):
        """Returns boolean indicating whether or not to use https."""
        return not self._is_localhost()

    def _get_server(self):
        if not self._is_localhost():
            return self._server
        else:
            assert self._port
            return '%s:%s' % (_LOCAL_SERVER_PREFIX, self._port)

    def _is_localhost(self):
        """Returns True if environment is dev_appserver and False otherwise."""
        return self._server.startswith(_LOCAL_SERVER_PREFIX)

    def establish(self):
        """Establishes the environment for RPC execution."""
        if self._testing:
            return

        try:
            remote_api_stub.ConfigureRemoteApiForOAuth(
                self._get_server(), self._path, secure=self._get_secure())
            remote_api_stub.MaybeInvokeAuthentication()
        # Must be broad -- we cannot know what types of exceptions App Engine
        # raises due to auth errors. pylint: disable=bare-except
        except:
            _LOG.error(
                'Unable to authenticate. The most likely cause is that you '
                'are missing OAuth2 credentials. For help getting those '
                'credentials, see %s. Original error was:\n%s',
                    _AUTH_HELP_URL, self._get_formatted_last_traceback())
            sys.exit(1)

    def get_info(self):
        """Returns string representation of the environment for logging."""
        return 'server: %(server)s, path: %(path)s, port: %(port)s' % {
            'path': self._path,
            'port': self._port if self._is_localhost() else '<ignored>',
            'server': self._server,
        }

