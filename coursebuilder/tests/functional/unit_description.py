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

"""Tests for unit description presence."""

__author__ = 'Mike Gainer (mgainer@google.com)'

from models import courses
from tests.functional import actions

COURSE_NAME = 'unit_descriptions'
COURSE_TITLE = 'Unit Descriptions'
ADMIN_EMAIL = 'admin@foo.com'
BASE_URL = '/' + COURSE_NAME

UNIT_DESCRIPTION = 'This is the unit.  There are many like it, but...'
ASSESSMENT_DESCRIPTION = 'None shall pass.'
LINK_DESCRIPTION = 'Over the hills and a great way off'


class UnitDescriptionsTest(actions.TestBase):

    def test_descriptions(self):
        context = actions.simple_add_course(
            COURSE_NAME, ADMIN_EMAIL, COURSE_TITLE)
        course = courses.Course(None, context)
        unit = course.add_unit()
        unit.title = 'The Unit'
        unit.availability = courses.AVAILABILITY_AVAILABLE
        unit.description = UNIT_DESCRIPTION

        assessment = course.add_assessment()
        assessment.title = 'The Assessment'
        assessment.availability = courses.AVAILABILITY_AVAILABLE
        assessment.description = ASSESSMENT_DESCRIPTION

        link = course.add_link()
        link.title = 'The Link'
        link.availability = courses.AVAILABILITY_AVAILABLE
        link.description = LINK_DESCRIPTION

        course.save()
        actions.login(ADMIN_EMAIL)

        response = self.get(BASE_URL)
        self.assertIn(unit.description, response)
        self.assertIn(assessment.description, response)
        self.assertIn(link.description, response)
