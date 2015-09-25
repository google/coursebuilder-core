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

"""Functional tests for controllers.utils."""

import os

import appengine_config

from common import users
from controllers import utils
from tests.functional import actions


_TEMPLATES_DIR = os.path.join(
    appengine_config.BUNDLE_ROOT, 'tests', 'functional', 'controllers_utils',
    'templates')


class TestHandler(utils.LocalizedGlobalHandler):

    def get(self):
        template = self.get_template(
            'test_template.html', additional_dirs=[_TEMPLATES_DIR])
        self.response.out.write(template.render({}))


class LocalizedGlobalHandlersTest(actions.TestBase):

    def getApp(self):
        return users.AuthInterceptorWSGIApplication([('/', TestHandler)])

    def test_get_accept_language(self):
        self.assertEquals(
            'accept_language',
            utils.LocalizedGlobalHandler._get_accept_language(
                {'Accept-Language': 'accept_language'}))
        self.assertIsNone(utils.LocalizedGlobalHandler._get_accept_language({}))

    def test_get_locale_defaults_if_no_header(self):
        self.assertEquals(
            utils.LocalizedGlobalHandler._DEFAULT_LOCALE,
            utils.LocalizedGlobalHandler._get_locale(None))
        self.assertEquals(
            utils.LocalizedGlobalHandler._DEFAULT_LOCALE,
            utils.LocalizedGlobalHandler._get_locale(''))

    def test_template_renders_successfully_with_accept_language(self):
        response = self.testapp.get('/', headers={'Accept-Language': 'fr'})

        self.assertIn('Success!', response.body)

    def test_template_renders_successfully_with_no_accept_language(self):
        response = self.testapp.get('/')

        self.assertIn('Success!', response.body)
