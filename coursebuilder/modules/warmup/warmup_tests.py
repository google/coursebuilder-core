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

import appengine_config
from modules.warmup import warmup
from tests.functional import actions

class WarmupTests(actions.TestBase):

    def test_warmup_dev(self):
        self.get('http://localhost:8081' + warmup.WarmupHandler.URL)
        self.assertLogContains('Course Builder is now available')
        self.assertLogContains('at ' + self.INTEGRATION_SERVER_BASE_URL)
        self.assertLogContains('or http://0.0.0.0:8081')

    def test_warmup_dev_different_port(self):
        self.get('http://localhost:4321' + warmup.WarmupHandler.URL)
        self.assertLogContains('Course Builder is now available')
        self.assertLogContains('at http://localhost:4321')
        self.assertLogContains('or http://0.0.0.0:4321')

    def test_warmup_prod(self):
        try:
            appengine_config.PRODUCTION_MODE = True
            self.get('http://localhost:8081' + warmup.WarmupHandler.URL)
            self.assertLogDoesNotContain('Course Builder is now available')
            self.assertLogDoesNotContain(
                'at ' + self.INTEGRATION_SERVER_BASE_URL)
            self.assertLogDoesNotContain('or http://0.0.0.0:8081')
        finally:
            appengine_config.PRODUCTION_MODE = False
