# Copyright 2014 Google Inc. All Rights Reserved.
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

"""Tests that walk through Course Builder pages."""

__author__ = 'Mike Gainer (mgainer@google.com)'

from common import utils as common_utils
from models import models
from tests.functional import actions

COURSE_NAME = 'labels_test'
COURSE_TITLE = 'Labels Test'
NAMESPACE = 'ns_%s' % COURSE_NAME
ADMIN_EMAIL = 'admin@foo.com'
SETTINGS_URL = '/%s/dashboard?action=settings' % COURSE_NAME


class AdminSettingsTests(actions.TestBase):

    def setUp(self):
        super(AdminSettingsTests, self).setUp()
        actions.simple_add_course(COURSE_NAME, ADMIN_EMAIL, COURSE_TITLE)
        actions.login(ADMIN_EMAIL)

    def test_defaults(self):
        prefs = models.StudentPreferencesDAO.ensure_exists()
        self.assertEquals(False, prefs.show_hooks)

    def test_settings_page(self):
        response = self.get(SETTINGS_URL)
        self.assertIn('Show hook edit buttons: False', response.body)

        with common_utils.Namespace(NAMESPACE):
            prefs = models.StudentPreferencesDAO.ensure_exists()
            prefs.show_hooks = True
            models.StudentPreferencesDAO.save(prefs)
        response = self.get(SETTINGS_URL)
        self.assertIn('Show hook edit buttons: True', response.body)
