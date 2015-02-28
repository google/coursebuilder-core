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

"""Unit tests for common/locale.py."""

__author__ = 'Mike Gainer (mgainer@google.com)'

import unittest

from common import resource
from models import courses
from models import resources_display
from tools import verify

class ResourceKeyTests(unittest.TestCase):

    def setUp(self):
        super(ResourceKeyTests, self).setUp()
        resource.Registry.register(resources_display.ResourceAssessment)
        resource.Registry.register(resources_display.ResourceLink)
        resource.Registry.register(resources_display.ResourceUnit)

    def tearDown(self):
        resource.Registry._RESOURCE_HANDLERS.clear()

    def test_roundtrip_data(self):
        key1 = resource.Key(resources_display.ResourceAssessment.TYPE, '23')
        key2 = resource.Key.fromstring(str(key1))
        self.assertEquals(key1.type, key2.type)
        self.assertEquals(key1.key, key2.key)

    def test_reject_bad_type(self):
        with self.assertRaises(AssertionError):
            resource.Key('BAD_TYPE', '23')
        with self.assertRaises(AssertionError):
            resource.Key.fromstring('BAD_TYPE:23')

    def test_for_unit(self):
        type_table = [
            (verify.UNIT_TYPE_ASSESSMENT,
             resources_display.ResourceAssessment.TYPE),
            (verify.UNIT_TYPE_LINK, resources_display.ResourceLink.TYPE),
            (verify.UNIT_TYPE_UNIT, resources_display.ResourceUnit.TYPE)]
        for unit_type, key_type in type_table:
            unit = courses.Unit13()
            unit.type = unit_type
            unit.unit_id = 5
            key = resources_display.ResourceUnitBase.key_for_unit(unit)
            self.assertEquals(key_type, key.type)
            self.assertEquals(5, key.key)
