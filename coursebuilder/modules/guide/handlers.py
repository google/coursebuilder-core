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

"""Guide handlers."""

__author__ = [
    'davyrisso@google.com (Davy Risso)',
]

import appengine_config
from common import jinja_utils
from common.crypto import XsrfTokenManager
from controllers import utils

from modules.guide import constants
from modules.guide import settings


def get_can_record_student_events(handler):
    # TODO(davyrisso): Fix.
    # can_record_student_events only set on course aware handlers.
    return False


def get_event_xsrf_token():
    return XsrfTokenManager.create_xsrf_token('event-post')


class GuideHandler(utils.ApplicationHandler, utils.QueryableRouteMixin):
    URL = 'modules/' + constants.MODULE_NAME

    @classmethod
    def can_handle_route_method_path_now(cls, route, method, path):
        return settings.GCB_ENABLE_GUIDE_PAGE.value

    def get(self):
        self.response.write(jinja_utils.get_template(
            'guide.html', [constants.TEMPLATE_DIR], handler=self).render({
                'event_xsrf_token': get_event_xsrf_token(),
                'can_record_student_events': (
                    get_can_record_student_events(self)),
                'use_flattened_html_imports': (
                    appengine_config.USE_FLATTENED_HTML_IMPORTS),
            }))


global_routes = utils.map_handler_urls([
    GuideHandler,
])

namespaced_routes = []
