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

"""ETL testing utilities."""

from controllers import sites
from tests.functional import actions


class EtlTestBase(actions.TestBase):
    # Allow access to protected members under test.
    # pylint: disable=protected-access

    def setUp(self):
        """Configures EtlMainTestCase."""
        super(EtlTestBase, self).setUp()
        self.url_prefix = '/test'
        self.namespace = 'ns_test'
        self.raw = 'course:%s::%s' % (self.url_prefix, self.namespace)
        sites.setup_courses(self.raw + ', course:/:/')

    def tearDown(self):
        sites.reset_courses()
        super(EtlTestBase, self).tearDown()
