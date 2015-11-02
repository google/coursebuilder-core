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

from common import crypto
from models import courses
from tests.functional import actions

COURSE_NAME = 'unit_test'
COURSE_TITLE = 'Unit Test'
NAMESPACE = 'ns_%s' % COURSE_NAME
ADMIN_EMAIL = 'admin@foo.com'
STUDENT_EMAIL = 'foo@foo.com'
BASE_URL = '/' + COURSE_NAME
UNIT_URL_PREFIX = BASE_URL + '/unit?unit='


class UnitOnOnePageTest(actions.TestBase):

    def setUp(self):
        super(UnitOnOnePageTest, self).setUp()

        app_context = actions.simple_add_course(COURSE_NAME, ADMIN_EMAIL,
                                                COURSE_TITLE)
        self.course = courses.Course(None, app_context=app_context)

        self.unit = self.course.add_unit()
        self.unit.title = 'One Big Unit'
        self.unit.availability = courses.AVAILABILITY_AVAILABLE
        self.unit.show_contents_on_one_page = True

        self.top_assessment = self.course.add_assessment()
        self.top_assessment.title = 'Top Assessment'
        self.top_assessment.html_content = 'content of top assessment'
        self.top_assessment.availability = courses.AVAILABILITY_AVAILABLE
        self.unit.pre_assessment = self.top_assessment.unit_id

        self.bottom_assessment = self.course.add_assessment()
        self.bottom_assessment.title = 'Bottom Assessment'
        self.bottom_assessment.html_content = 'content of bottom assessment'
        self.bottom_assessment.availability = courses.AVAILABILITY_AVAILABLE
        self.unit.post_assessment = self.bottom_assessment.unit_id

        self.lesson_one = self.course.add_lesson(self.unit)
        self.lesson_one.title = 'Lesson One'
        self.lesson_one.objectives = 'body of lesson one'
        self.lesson_one.availability = courses.AVAILABILITY_AVAILABLE

        self.lesson_two = self.course.add_lesson(self.unit)
        self.lesson_two.title = 'Lesson Two'
        self.lesson_two.objectives = 'body of lesson two'
        self.lesson_two.availability = courses.AVAILABILITY_AVAILABLE

        self.course.save()

        actions.login(STUDENT_EMAIL)
        actions.register(self, STUDENT_EMAIL, COURSE_NAME)

    def _assert_contains_in_order(self, response, expected):
        index = 0
        for item in expected:
            index = response.body.find(item, index)
            if index == -1:
                self.fail('Did not find expected content "%s" ' % item)

    def _post_assessment(self, assessment_id):
        return self.post(BASE_URL + '/answer', {
            'xsrf_token': crypto.XsrfTokenManager.create_xsrf_token(
                'assessment-post'),
            'assessment_type': assessment_id,
            'score': '100'})

    def _verify_contents(self, response):
        self._assert_contains_in_order(
            response,
            ['Unit 1 - One Big Unit',
             'Top Assessment',
             'content of top assessment',
             'Submit Answers',
             'Lesson One',
             'body of lesson one',
             'Lesson Two',
             'body of lesson two',
             'Bottom Assessment',
             'content of bottom assessment',
             'Submit Answers'])
        self.assertNotIn('Next Page', response.body)
        self.assertNotIn('Prev Page', response.body)
        self.assertNotIn('End', response.body)

    def test_appearance(self):
        response = self.get(UNIT_URL_PREFIX + str(self.unit.unit_id))
        self._verify_contents(response)

    def test_content_url_insensitive(self):
        url = UNIT_URL_PREFIX + str(self.unit.unit_id)

        response = self.get(
            url + '&assessment=' + str(self.top_assessment.unit_id))
        self._verify_contents(response)
        response = self.get(
            url + '&assessment=' + str(self.bottom_assessment.unit_id))
        self._verify_contents(response)
        response = self.get(
            url + '&lesson=' + str(self.lesson_one.lesson_id))
        self._verify_contents(response)
        response = self.get(
            url + '&lesson=' + str(self.lesson_two.lesson_id))
        self._verify_contents(response)

    def _test_submit_assessment(self, assessment):
        response = self.get(UNIT_URL_PREFIX + str(self.unit.unit_id))
        response = self._post_assessment(assessment.unit_id).follow()
        self._assert_contains_in_order(
            response,
            ['Thank you for taking the %s' % assessment.title.lower(),
             'Return to Unit'])
        self.assertNotIn('Next Page', response.body)
        self.assertNotIn('Prev Page', response.body)
        self.assertNotIn('End', response.body)

        response = self.click(response, 'Return to Unit')
        self._verify_contents(response)

    def test_submit_assessments(self):
        self._test_submit_assessment(self.top_assessment)
        self._test_submit_assessment(self.bottom_assessment)

    def test_edit_lesson_buttons_for_each_lesson(self):
        actions.logout()
        actions.login(ADMIN_EMAIL)
        dom = self.parse_html_string(
            self.get(UNIT_URL_PREFIX + str(self.unit.unit_id)).body)
        # The Edit Lesson buttons all have a data-lesson-id attribute set
        buttons = dom.findall('.//*[@data-lesson-id]')
        self.assertEquals(2, len(buttons))
        self.assertEquals(
            str(self.lesson_one.lesson_id), buttons[0].get('data-lesson-id'))
        self.assertEquals(
            str(self.lesson_two.lesson_id), buttons[1].get('data-lesson-id'))
