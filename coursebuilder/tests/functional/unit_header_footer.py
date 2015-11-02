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

"""Tests for unit header/footer presence."""

__author__ = 'Mike Gainer (mgainer@google.com)'

from models import courses
from tests.functional import actions

COURSE_NAME = 'unit_header_footer'
COURSE_TITLE = 'Unit Header Footer'
ADMIN_EMAIL = 'admin@foo.com'
BASE_URL = '/' + COURSE_NAME

UNIT_HEADER_TEXT = 'This is the unit header.'
UNIT_FOOTER_TEXT = 'The unit footer is here.'


class UnitHeaderFooterTest(actions.TestBase):

    def setUp(self):
        super(UnitHeaderFooterTest, self).setUp()

        context = actions.simple_add_course(
            COURSE_NAME, ADMIN_EMAIL, COURSE_TITLE)
        self.course = courses.Course(None, context)
        self.unit = self.course.add_unit()
        self.unit.availability = courses.AVAILABILITY_AVAILABLE
        self.unit.unit_header = UNIT_HEADER_TEXT
        self.unit.unit_footer = UNIT_FOOTER_TEXT
        self.course.save()
        self.url = BASE_URL + '/unit?unit=' + str(self.unit.unit_id)
        actions.login(ADMIN_EMAIL)

    def _add_assessment(self, title):
        assessment = self.course.add_assessment()
        assessment.title = title
        assessment.html_content = 'assessment content'
        assessment.availability = courses.AVAILABILITY_AVAILABLE
        return assessment

    def _add_lesson(self, title):
        lesson = self.course.add_lesson(self.unit)
        lesson.lesson_title = title
        lesson.objectives = 'lesson content'
        lesson.availability = courses.AVAILABILITY_AVAILABLE
        return lesson

    def test_no_lessons_or_assessments_or_header_or_footer(self):
        self.unit.unit_header = None
        self.unit.unit_footer = None
        self.course.save()

        response = self.get(self.url)
        self.assertNotIn(UNIT_HEADER_TEXT, response)
        self.assertNotIn(UNIT_FOOTER_TEXT, response)
        self.assertIn('This unit has no content', response)

    def test_no_lessons_or_assessments(self):
        response = self.get(self.url)
        self.assertIn(UNIT_HEADER_TEXT, response)
        self.assertIn(UNIT_FOOTER_TEXT, response)
        self.assertNotIn('This unit has no content', response)

    def test_no_lessons_or_assessments_all_on_one_page(self):
        self.unit.show_contents_on_one_page = True
        self.course.save()

        response = self.get(self.url)
        self.assertIn(UNIT_HEADER_TEXT, response)
        self.assertIn(UNIT_FOOTER_TEXT, response)
        self.assertNotIn('This unit has no content', response)

    def test_only_pre_assessment(self):
        assessment = self._add_assessment('The Assessment')
        self.unit.pre_assessment = assessment.unit_id
        self.course.save()

        response = self.get(self.url)
        self.assertIn(UNIT_HEADER_TEXT, response)
        self.assertIn(UNIT_FOOTER_TEXT, response)

    def test_only_post_assessment(self):
        assessment = self._add_assessment('The Assessment')
        self.unit.post_assessment = assessment.unit_id
        self.course.save()

        response = self.get(self.url)
        self.assertIn(UNIT_HEADER_TEXT, response)
        self.assertIn(UNIT_FOOTER_TEXT, response)

    def test_only_lesson(self):
        self._add_lesson('The Lesson')
        self.course.save()

        response = self.get(self.url)
        self.assertIn(UNIT_HEADER_TEXT, response)
        self.assertIn(UNIT_FOOTER_TEXT, response)

    def test_multiple_lessons(self):
        self._add_lesson('Lesson One')
        lesson_two = self._add_lesson('Lesson Two')
        lesson_three = self._add_lesson('Lesson Three')
        self.course.save()

        response = self.get(self.url)
        self.assertIn(UNIT_HEADER_TEXT, response)
        self.assertNotIn(UNIT_FOOTER_TEXT, response)

        response = self.get(self.url +
                            '&lesson=' + str(lesson_two.lesson_id))
        self.assertNotIn(UNIT_HEADER_TEXT, response)
        self.assertNotIn(UNIT_FOOTER_TEXT, response)

        response = self.get(self.url +
                            '&lesson=' + str(lesson_three.lesson_id))
        self.assertNotIn(UNIT_HEADER_TEXT, response)
        self.assertIn(UNIT_FOOTER_TEXT, response)

    def test_pre_post_assessment_and_lesson(self):
        pre_assessment = self._add_assessment('Pre Assessment')
        self.unit.pre_assessment = pre_assessment.unit_id
        post_assessment = self._add_assessment('Post Assessment')
        self.unit.post_assessment = post_assessment.unit_id
        lesson = self._add_lesson('The Lesson')
        self.course.save()

        response = self.get(self.url)
        self.assertIn(UNIT_HEADER_TEXT, response)
        self.assertNotIn(UNIT_FOOTER_TEXT, response)

        response = self.get(self.url +
                            '&lesson=' + str(lesson.lesson_id))
        self.assertNotIn(UNIT_HEADER_TEXT, response)
        self.assertNotIn(UNIT_FOOTER_TEXT, response)

        response = self.get(self.url +
                            '&assessment=' + str(post_assessment.unit_id))
        self.assertNotIn(UNIT_HEADER_TEXT, response)
        self.assertIn(UNIT_FOOTER_TEXT, response)

    def test_lesson_with_activity(self):
        lesson = self._add_lesson('The Lesson')
        lesson.has_activity = True
        lesson.activity_title = 'The Activity'
        self.course.save()

        response = self.get(self.url)
        self.assertIn(UNIT_HEADER_TEXT, response)
        self.assertNotIn(UNIT_FOOTER_TEXT, response)

        response = self.get(self.url +
                            '&activity=true')
        self.assertNotIn(UNIT_HEADER_TEXT, response)
        self.assertIn(UNIT_FOOTER_TEXT, response)

    def test_lesson_with_activity_and_post_assessment(self):
        lesson = self._add_lesson('The Lesson')
        lesson.has_activity = True
        lesson.activity_title = 'The Activity'
        post_assessment = self._add_assessment('The Assessment')
        self.unit.post_assessment = post_assessment.unit_id
        self.course.save()

        response = self.get(self.url)
        self.assertIn(UNIT_HEADER_TEXT, response)
        self.assertNotIn(UNIT_FOOTER_TEXT, response)

        response = self.get(self.url +
                            '&activity=true')
        self.assertNotIn(UNIT_HEADER_TEXT, response)
        self.assertNotIn(UNIT_FOOTER_TEXT, response)

        response = self.get(self.url +
                            '&assessment=' + str(post_assessment.unit_id))
        self.assertNotIn(UNIT_HEADER_TEXT, response)
        self.assertIn(UNIT_FOOTER_TEXT, response)

    def test_unit_all_on_one_page(self):
        pre_assessment = self._add_assessment('Pre Assessment')
        self.unit.pre_assessment = pre_assessment.unit_id
        post_assessment = self._add_assessment('Post Assessment')
        self.unit.post_assessment = post_assessment.unit_id
        self._add_lesson('The Lesson')
        self.unit.show_contents_on_one_page = True
        self.course.save()

        response = self.get(self.url)
        self.assertIn(UNIT_HEADER_TEXT, response)
        self.assertIn(UNIT_FOOTER_TEXT, response)
