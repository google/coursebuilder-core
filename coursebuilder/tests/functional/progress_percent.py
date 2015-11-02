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

"""Tests verifying progress in units."""

__author__ = 'Mike Gainer (mgainer@google.com)'

import re

from common import crypto
from common import users
from common.utils import Namespace
from models import courses
from models import models
from modules.analytics import analytics
from tests.functional import actions

COURSE_NAME = 'percent_completion'
NAMESPACE = 'ns_%s' % COURSE_NAME
COURSE_TITLE = 'Percent Completion'
ADMIN_EMAIL = 'admin@foo.com'
BASE_URL = '/' + COURSE_NAME
STUDENT_EMAIL = 'foo@foo.com'


class ProgressPercent(actions.TestBase):

    def setUp(self):
        super(ProgressPercent, self).setUp()

        context = actions.simple_add_course(
            COURSE_NAME, ADMIN_EMAIL, COURSE_TITLE)
        self.course = courses.Course(None, context)

        self.unit = self.course.add_unit()
        self.unit.title = 'No Lessons'
        self.unit.availability = courses.AVAILABILITY_AVAILABLE

        self.lesson_one = self.course.add_lesson(self.unit)
        self.lesson_one.title = 'Lesson One'
        self.lesson_one.objectives = 'body of lesson'
        self.lesson_one.availability = courses.AVAILABILITY_AVAILABLE

        self.lesson_two = self.course.add_lesson(self.unit)
        self.lesson_two.title = 'Lesson Two'
        self.lesson_two.objectives = 'body of lesson'
        self.lesson_two.availability = courses.AVAILABILITY_AVAILABLE

        self.lesson_three = self.course.add_lesson(self.unit)
        self.lesson_three.title = 'Lesson Three'
        self.lesson_three.objectives = 'body of lesson'
        self.lesson_three.availability = courses.AVAILABILITY_AVAILABLE

        self.assessment_one = self.course.add_assessment()
        self.assessment_one.title = 'Assessment One'
        self.assessment_one.html_content = 'assessment one content'
        self.assessment_one.availability = courses.AVAILABILITY_AVAILABLE

        self.assessment_two = self.course.add_assessment()
        self.assessment_two.title = 'Assessment Two'
        self.assessment_two.html_content = 'assessment two content'
        self.assessment_two.availability = courses.AVAILABILITY_AVAILABLE

        self.course.save()
        actions.login(STUDENT_EMAIL)
        actions.register(self, STUDENT_EMAIL, COURSE_NAME)
        self.overridden_environment = actions.OverriddenEnvironment(
            {'course': {analytics.CAN_RECORD_STUDENT_EVENTS: 'true'}})
        self.overridden_environment.__enter__()

        self.tracker = self.course.get_progress_tracker()
        with Namespace(NAMESPACE):
            self.student = models.Student.get_by_user(users.get_current_user())

    def tearDown(self):
        self.overridden_environment.__exit__()
        super(ProgressPercent, self).tearDown()

    def _get_unit_page(self, unit):
        return self.get(BASE_URL + '/unit?unit=' + str(unit.unit_id))

    def _click_button(self, class_name, response):
        matches = re.search(
            r'<div class="%s">\s*<a href="([^"]*)"' % class_name, response.body)
        url = matches.group(1).replace('&amp;', '&')
        return self.get(url, response)

    def _click_next_button(self, response):
        return self._click_button('gcb-next-button', response)

    def _post_assessment(self, assessment_id, score):
        return self.post(BASE_URL + '/answer', {
            'xsrf_token': crypto.XsrfTokenManager.create_xsrf_token(
                'assessment-post'),
            'assessment_type': assessment_id,
            'score': score})

    def test_progress_no_pre_assessment(self):

        # Zero progress when no unit actions taken.
        with Namespace(NAMESPACE):
            self.assertEquals(0.0, self.tracker.get_unit_percent_complete(
                self.student)[self.unit.unit_id])

        # Progress is counted when navigating _on to_ lesson.
        response = self._get_unit_page(self.unit)
        with Namespace(NAMESPACE):
            self.assertEquals(0.333, self.tracker.get_unit_percent_complete(
                self.student)[self.unit.unit_id])

        # Navigate to next lesson.  Verify rounding to 3 decimal places.
        response = self._click_next_button(response)
        with Namespace(NAMESPACE):
            self.assertEquals(0.667, self.tracker.get_unit_percent_complete(
                self.student)[self.unit.unit_id])

        # Navigate to next lesson.
        response = self._click_next_button(response)
        with Namespace(NAMESPACE):
            self.assertEquals(1.000, self.tracker.get_unit_percent_complete(
                self.student)[self.unit.unit_id])

    def test_progress_pre_assessment_unsubmitted(self):
        self.unit.pre_assessment = self.assessment_one.unit_id
        self.unit.post_assessment = self.assessment_two.unit_id
        self.course.save()

        # Zero progress when no unit actions taken.
        with Namespace(NAMESPACE):
            self.assertEquals(0.0, self.tracker.get_unit_percent_complete(
                self.student)[self.unit.unit_id])

        # Zero progress when navigate to pre-assessment
        response = self._get_unit_page(self.unit)
        with Namespace(NAMESPACE):
            self.assertEquals(0.000, self.tracker.get_unit_percent_complete(
                self.student)[self.unit.unit_id])

        # Progress is counted when navigating _on to_ lesson.
        response = self._click_next_button(response)
        with Namespace(NAMESPACE):
            self.assertEquals(0.333, self.tracker.get_unit_percent_complete(
                self.student)[self.unit.unit_id])

        # Navigate to next lesson.  Verify rounding to 3 decimal places.
        response = self._click_next_button(response)
        with Namespace(NAMESPACE):
            self.assertEquals(0.667, self.tracker.get_unit_percent_complete(
                self.student)[self.unit.unit_id])

        # Navigate to next lesson.
        response = self._click_next_button(response)
        with Namespace(NAMESPACE):
            self.assertEquals(1.000, self.tracker.get_unit_percent_complete(
                self.student)[self.unit.unit_id])

        # Navigate to post-assessment does not change completion
        response = self._click_next_button(response)
        with Namespace(NAMESPACE):
            self.assertEquals(1.000, self.tracker.get_unit_percent_complete(
                self.student)[self.unit.unit_id])

    def test_progress_pre_assessment_submitted_but_wrong(self):
        self.unit.pre_assessment = self.assessment_one.unit_id
        self.unit.post_assessment = self.assessment_two.unit_id
        self.course.save()

        self._get_unit_page(self.unit)
        response = self._post_assessment(self.assessment_one.unit_id, '99')

        # Reload student; assessment scores are cached in student.
        with Namespace(NAMESPACE):
            self.student = models.Student.get_by_user(users.get_current_user())

        # Zero progress because posting the assessment did not score 100%.
        with Namespace(NAMESPACE):
            self.assertEquals(0.000, self.tracker.get_unit_percent_complete(
                self.student)[self.unit.unit_id])

        # Still zero progress when take redirect to assessment confirmation.
        response = response.follow()
        with Namespace(NAMESPACE):
            self.assertEquals(0.000, self.tracker.get_unit_percent_complete(
                self.student)[self.unit.unit_id])

        # But have 33% progress when following the link to the 1st lesson
        response = self._click_next_button(response)
        with Namespace(NAMESPACE):
            self.assertEquals(0.333, self.tracker.get_unit_percent_complete(
                self.student)[self.unit.unit_id])

    def test_progress_pre_assessment_submitted_and_fully_correct(self):
        self.unit.pre_assessment = self.assessment_one.unit_id
        self.unit.post_assessment = self.assessment_two.unit_id
        self.course.save()

        self._get_unit_page(self.unit)
        response = self._post_assessment(self.assessment_one.unit_id, '100')

        # Reload student; assessment scores are cached in student.
        with Namespace(NAMESPACE):
            self.student = models.Student.get_by_user(users.get_current_user())

        # 100% progress because pre-assessment was 100% correct.
        with Namespace(NAMESPACE):
            self.assertEquals(1.000, self.tracker.get_unit_percent_complete(
                self.student)[self.unit.unit_id])

        # Still 100% after navigating onto a lesson
        response = response.follow()
        with Namespace(NAMESPACE):
            self.assertEquals(1.000, self.tracker.get_unit_percent_complete(
                self.student)[self.unit.unit_id])
