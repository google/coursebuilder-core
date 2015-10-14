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

"""Module to hold shared client-side (JavaScript) UI."""

__author__ = 'John Orr (jorr@google.com)'

import os

import appengine_config
from common import jinja_utils
from controllers import utils
from models import custom_modules

custom_module = None


# TODO(jorr): Bring IifeHandler and JQueryHandler in here.


class StyleGuideHandler(utils.ApplicationHandler):
    _TEMPLATES = os.path.join(
        appengine_config.BUNDLE_ROOT, 'modules', 'core_ui', 'templates',
        'style_guide')

    def get(self):
        if appengine_config.PRODUCTION_MODE:
            self.error(404)
            return
        self.response.write(jinja_utils.get_template(
            'style_guide.html', [self._TEMPLATES]).render())


def register_module():

    global_routes = [
        ('/modules/core_ui/style_guide/style_guide.html', StyleGuideHandler)]
    namespaced_routes = []

    global custom_module  # pylint: disable=global-statement
    custom_module = custom_modules.Module(
        'Core UI',
        'Shared client-side UI',
        global_routes,
        namespaced_routes)

    return custom_module
