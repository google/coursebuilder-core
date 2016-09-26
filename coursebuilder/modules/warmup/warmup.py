# Copyright 2016 Google Inc. All Rights Reserved.
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

"""Handle /_ah/warmup requests on instance start."""

__author__ = 'Mike Gainer (mgainer@google.com)'

import logging
import urlparse
import webapp2

import appengine_config
from models import custom_modules

MODULE_NAME = 'warmup'
_LOG = logging.getLogger('modules.warmup.warmup')
_LOG.setLevel(logging.INFO)
logging.basicConfig()

custom_module = None


class WarmupHandler(webapp2.RequestHandler):

    URL = '/_ah/warmup'

    def get(self):
        if not appengine_config.PRODUCTION_MODE:
            port = urlparse.urlparse(self.request.url).port
            _LOG.info(' -------------------------------')
            _LOG.info('')
            _LOG.info(' Course Builder is now available')
            _LOG.info('    at http://localhost:%d', port)
            _LOG.info('     or http://0.0.0.0:%d', port)
            _LOG.info('')
            _LOG.info(' -------------------------------')


def register_module():
    """Callback for module registration.  Sets up URL routes."""

    global custom_module  # pylint: disable=global-statement
    custom_module = custom_modules.Module(
        MODULE_NAME, 'Actions to warm-up newly started instance.',
        global_routes=[(WarmupHandler.URL, WarmupHandler)],
        namespaced_routes=[])
    return custom_module
