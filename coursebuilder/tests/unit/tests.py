# Copyright 2012 Google Inc. All Rights Reserved.
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

"""Runs all unit tests."""

__author__ = 'Pavel Simakov (psimakov@google.com)'

import unittest
from controllers import sites
from models import config
from models import transforms
from tools import verify


class InvokeExistingUnitTest(unittest.TestCase):
    """Run all units tests declared elsewhere."""

    def test_existing_unit_tests(self):
        """Run all units tests declared elsewhere."""
        sites.run_all_unit_tests()
        config.run_all_unit_tests()
        verify.run_all_unit_tests()
        transforms.run_all_unit_tests()

if __name__ == '__main__':
    unittest.TextTestRunner().run(
        unittest.TestLoader().loadTestsFromTestCase(InvokeExistingUnitTest))
