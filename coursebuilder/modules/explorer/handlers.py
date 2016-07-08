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

"""Explorer handlers"""

__author__ = [
    'nretallack@google.com (Nick Retallack)',
]

import appengine_config
from modules.explorer import constants
from controllers import utils
from common import jinja_utils
from models import transforms
from modules.explorer import settings


def get_institution_name():
    try:
        return transforms.loads(settings.COURSE_EXPLORER_SETTINGS.value)[
            'institution_name']
    except (ValueError, KeyError):
        return ''


class ExplorerHandler(utils.ApplicationHandler, utils.QueryableRouteMixin):
    URL = ''

    @classmethod
    def can_handle_route_method_path_now(cls, route, method, path):
        return settings.GCB_ENABLE_COURSE_EXPLORER_PAGE.value

    def get(self):
        self.response.write(jinja_utils.get_template(
            'explorer.html', [constants.TEMPLATE_DIR], handler=self).render({
                'institution_name': get_institution_name(),
                'use_flattened_html_imports': (
                    appengine_config.USE_FLATTENED_HTML_IMPORTS),
            }))

global_routes = utils.map_handler_urls([
    ExplorerHandler,
])

namespaced_routes = []
