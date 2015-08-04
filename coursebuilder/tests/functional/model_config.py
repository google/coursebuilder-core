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

"""Functional tests for VFS features."""

__author__ = [
    'mgainer@google.com (Mike Gainer)',
]

import appengine_config
import logging

from models import config
from models import models
from tests.functional import actions


class ValueLoadingTests(actions.TestBase):

    LOG_LEVEL = logging.INFO

    def test_in_db_but_not_registered_not_registering_modules(self):
        config.ConfigPropertyEntity(key_name='foo', value='foo_value').put()
        # Trigger load from DB
        models.CAN_USE_MEMCACHE.value  # pylint: disable=pointless-statement
        self.assertLogContains(
            'WARNING: Property is not registered (skipped): foo')

    def test_in_db_but_not_registered_while_registering_modules(self):
        try:
            appengine_config.MODULE_REGISTRATION_IN_PROGRESS = True
            config.ConfigPropertyEntity(key_name='foo', value='foo_value').put()
            # Trigger load from DB
            models.CAN_USE_MEMCACHE.value  # pylint: disable=pointless-statement
            self.assertLogContains(
                'INFO: Property is not registered (skipped): foo')
        finally:
            appengine_config.MODULE_REGISTRATION_IN_PROGRESS = False
