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

import re

from controllers import sites
from controllers import utils
from models import config
from models import courses
from modules.dashboard import unit_lesson_editor
from tests.functional import actions
from tools import verify

COURSE_NAME = 'unit_pre_post'
COURSE_TITLE = 'Unit Pre/Post Assessments'
ADMIN_EMAIL = 'admin@foo.com'
BASE_URL = '/' + COURSE_NAME
DASHBOARD_URL = BASE_URL + '/dashboard'
STUDENT_EMAIL = 'foo@foo.com'


class UnitPrePostAssessmentTest(actions.TestBase):

    def setUp(self):
        super(UnitPrePostAssessmentTest, self).setUp()

        context = actions.simple_add_course(
            COURSE_NAME, ADMIN_EMAIL, COURSE_TITLE)
        self.course = courses.Course(None, context)

        self.unit_no_lessons = self.course.add_unit()
        self.unit_no_lessons.title = 'No Lessons'
        self.unit_no_lessons.now_available = True

        self.unit_one_lesson = self.course.add_unit()
        self.unit_one_lesson.title = 'One Lesson'
        self.unit_one_lesson.now_available = True
        self.lesson = self.course.add_lesson(self.unit_one_lesson)
        self.lesson.title = 'Lesson One'
        self.lesson.objectives = 'body of lesson'
        self.lesson.now_available = True

        self.assessment_one = self.course.add_assessment()
        self.assessment_one.title = 'Assessment One'
        self.assessment_one.html_content = 'assessment one content'
        self.assessment_one.now_available = True

        self.assessment_two = self.course.add_assessment()
        self.assessment_two.title = 'Assessment Two'
        self.assessment_two.html_content = 'assessment two content'
        self.assessment_two.now_available = True

        self.course.save()
        actions.login(STUDENT_EMAIL)
        actions.register(self, STUDENT_EMAIL, COURSE_NAME)
        config.Registry.test_overrides[
            utils.CAN_PERSIST_ACTIVITY_EVENTS.name] = True

    def _get_unit_page(self, unit):
        return self.get(BASE_URL + '/unit?unit=' + str(unit.unit_id))

    def _click_button(self, class_name, response):
        matches = re.search(
            r'<div class="%s">\s*<a href="([^"]*)"' % class_name, response.body)
        url = matches.group(1).replace('&amp;', '&')
        return self.get(url, response)

    def _click_next_button(self, response):
        return self._click_button('gcb-next-button', response)

    def _click_prev_button(self, response):
        return self._click_button('gcb-prev-button', response)

    def _assert_contains_in_order(self, response, expected):
        index = 0
        for item in expected:
            index = response.body.find(item, index)
            if index == -1:
                self.fail('Did not find expected content "%s" ' % item)

    def test_assements_in_units_not_shown_on_course_page(self):
        response = self.get(BASE_URL)
        self.assertIn(self.unit_no_lessons.title, response.body)
        self.assertIn(self.unit_one_lesson.title, response.body)
        self.assertIn(self.assessment_one.title, response.body)
        self.assertIn(self.assessment_two.title, response.body)

        self.unit_no_lessons.pre_assessment = self.assessment_one.unit_id
        self.unit_no_lessons.post_assessment = self.assessment_two.unit_id
        self.course.save()
        response = self.get(BASE_URL)
        self.assertIn(self.unit_no_lessons.title, response.body)
        self.assertIn(self.unit_one_lesson.title, response.body)
        self.assertNotIn(self.assessment_one.title, response.body)
        self.assertNotIn(self.assessment_two.title, response.body)

    def test_pre_assessment_as_only_lesson(self):
        self.unit_no_lessons.pre_assessment = self.assessment_one.unit_id
        self.course.save()
        response = self._get_unit_page(self.unit_no_lessons)
        self.assertNotIn('This unit does not contain any lessons',
                         response.body)
        self.assertIn(self.assessment_one.title, response.body)
        self.assertIn(self.assessment_one.html_content, response.body)
        self.assertIn('Submit Answers', response.body)
        self.assertNotIn('Previous Page', response.body)
        self.assertNotIn('Next Page', response.body)
        self.assertIn(' End ', response.body)

    def test_post_assessment_as_only_lesson(self):
        self.unit_no_lessons.post_assessment = self.assessment_one.unit_id
        self.course.save()
        response = self._get_unit_page(self.unit_no_lessons)
        self.assertNotIn('This unit does not contain any lessons',
                         response.body)
        self.assertIn(self.assessment_one.title, response.body)
        self.assertIn(self.assessment_one.html_content, response.body)
        self.assertIn('Submit Answers', response.body)
        self.assertNotIn('Previous Page', response.body)
        self.assertNotIn('Next Page', response.body)
        self.assertIn(' End ', response.body)

    def test_pre_and_post_assessment_as_only_lessons(self):
        self.unit_no_lessons.pre_assessment = self.assessment_one.unit_id
        self.unit_no_lessons.post_assessment = self.assessment_two.unit_id
        self.course.save()
        response = self._get_unit_page(self.unit_no_lessons)
        self.assertIn(self.assessment_one.title, response.body)
        self.assertIn(self.assessment_two.title, response.body)
        self.assertIn(self.assessment_one.html_content, response.body)
        self.assertNotIn('Previous Page', response.body)
        self.assertIn('Next Page', response.body)
        self.assertNotIn(' End ', response.body)

        response = self._click_next_button(response)
        self.assertIn(self.assessment_one.title, response.body)
        self.assertIn(self.assessment_two.title, response.body)
        self.assertIn(self.assessment_two.html_content, response.body)
        self.assertIn('Previous Page', response.body)
        self.assertNotIn('Next Page', response.body)
        self.assertIn(' End ', response.body)

        response = self._click_prev_button(response)
        self.assertIn(self.assessment_one.html_content, response.body)

    def test_pre_and_post_assessment_with_other_lessons(self):
        self.unit_one_lesson.pre_assessment = self.assessment_one.unit_id
        self.unit_one_lesson.post_assessment = self.assessment_two.unit_id
        self.course.save()
        response = self._get_unit_page(self.unit_one_lesson)
        self.assertIn(self.assessment_one.title, response.body)
        self.assertIn('2.1 ' + self.lesson.title, response.body)
        self.assertIn(self.assessment_two.title, response.body)
        self.assertIn(self.assessment_one.html_content, response.body)
        self.assertNotIn('Previous Page', response.body)
        self.assertIn('Next Page', response.body)
        self.assertNotIn(' End ', response.body)

        response = self._click_next_button(response)
        self.assertIn(self.lesson.objectives, response.body)

        response = self._click_next_button(response)
        self.assertIn(self.assessment_two.html_content, response.body)

        response = self._click_next_button(response)  # Back to /course page
        self.assertIn(self.unit_no_lessons.title, response.body)
        self.assertIn(self.unit_one_lesson.title, response.body)
        self.assertNotIn(self.assessment_one.title, response.body)
        self.assertNotIn(self.assessment_two.title, response.body)

    def _assert_progress_state(self, expected, lesson_title, response):
        title_index = response.body.index(lesson_title)
        alt_marker = 'alt="'
        state_start = response.body.rfind(
            alt_marker, 0, title_index) + len(alt_marker)
        state_end = response.body.find('"', state_start)
        self.assertEquals(expected, response.body[state_start:state_end])

    def test_progress_via_next_buttons(self):
        self.unit_one_lesson.pre_assessment = self.assessment_one.unit_id
        self.unit_one_lesson.post_assessment = self.assessment_two.unit_id
        self.course.save()

        response = self.get(BASE_URL)
        self._assert_progress_state(
            'Not yet started', 'Unit 2 - %s</a>' % self.unit_one_lesson.title,
            response)

        # On pre-assessment; no progress markers on any lesson.
        response = self._get_unit_page(self.unit_one_lesson)
        self._assert_progress_state(
            'Not yet submitted', self.assessment_one.title, response)
        self._assert_progress_state(
            'Not yet started', '2.1 ' + self.lesson.title, response)
        self._assert_progress_state(
            'Not yet submitted', self.assessment_two.title, response)

        # On actual lesson; no progress markers set when lesson first shown.
        response = self._click_next_button(response)
        self._assert_progress_state(
            'Not yet submitted', self.assessment_one.title, response)
        self._assert_progress_state(
            'Not yet started', '2.1 ' + self.lesson.title, response)
        self._assert_progress_state(
            'Not yet submitted', self.assessment_two.title, response)

        # On post-assessment; progress for lesson, but not for pre-assessment.
        response = self._click_next_button(response)
        self._assert_progress_state(
            'Not yet submitted', self.assessment_one.title, response)
        self._assert_progress_state(
            'Completed', '2.1 ' + self.lesson.title, response)
        self._assert_progress_state(
            'Not yet submitted', self.assessment_two.title, response)

        # Back on course page; expect partial progress.
        response = self._click_next_button(response)
        self._assert_progress_state(
            'In progress', 'Unit 2 - %s</a>' % self.unit_one_lesson.title,
            response)

    def _get_question_data(self, name, response):
        matches = re.search('questionData.%s = \'([^\']*)\'' % name,
                            response.body)
        return matches.group(1)

    def _post_assessment(self, response):
        return self.post(BASE_URL + '/answer', {
            'xsrf_token': self._get_question_data('xsrfToken', response),
            'assessment_type': self._get_question_data('unitId', response),
            'score': '1'})

    def test_progress_via_assessment_submission(self):
        self.unit_one_lesson.pre_assessment = self.assessment_one.unit_id
        self.unit_one_lesson.post_assessment = self.assessment_two.unit_id
        self.course.save()

        # Submit pre-assessment; verify completion status.
        response = self._get_unit_page(self.unit_one_lesson)
        response = self._post_assessment(response).follow()
        self._assert_progress_state(
            'Completed', self.assessment_one.title, response)
        self._assert_progress_state(
            'Not yet started', '2.1 ' + self.lesson.title, response)
        self._assert_progress_state(
            'Not yet submitted', self.assessment_two.title, response)

        # Next-button past the lesson content
        response = self._click_next_button(response)
        self._assert_progress_state(
            'Completed', self.assessment_one.title, response)
        self._assert_progress_state(
            'Completed', '2.1 ' + self.lesson.title, response)
        self._assert_progress_state(
            'Not yet submitted', self.assessment_two.title, response)

        # Submit post-assessment; unit should now be marked complete.
        response = self._post_assessment(response).follow()
        self._assert_progress_state(
            'Completed', 'Unit 2 - %s</a>' % self.unit_one_lesson.title,
            response)

    def _get_selection_choices(self, schema, match):
        ret = {}
        for item in schema:
            if item[0] == match:
                for choice in item[1]['choices']:
                    ret[choice['label']] = choice['value']
        return ret

    def test_old_assessment_availability(self):
        new_course_context = actions.simple_add_course(
            'new_course', ADMIN_EMAIL, 'My New Course')
        new_course = courses.Course(None, new_course_context)
        new_course.import_from(
            sites.get_all_courses(rules_text='course:/:/')[0])
        new_course.save()

        # Prove that there are at least some assessments in this course.
        assessments = new_course.get_units_of_type(verify.UNIT_TYPE_ASSESSMENT)
        self.assertIsNotNone(assessments[0])

        # Get the first Unit
        unit = new_course.get_units_of_type(verify.UNIT_TYPE_UNIT)[0]

        unit_rest_handler = unit_lesson_editor.UnitRESTHandler()
        schema = unit_rest_handler.get_annotations_dict(
            new_course, unit.unit_id)

        # Verify that despite having some Assessments, we don't have any
        # valid choices for pre- or post-asssments for the unit, since
        # old-style assessments don't play nicely in that role.
        choices = self._get_selection_choices(
            schema, ['properties', 'pre_assessment', '_inputex'])
        self.assertEquals({'-- None --': -1}, choices)

        choices = self._get_selection_choices(
            schema, ['properties', 'post_assessment', '_inputex'])
        self.assertEquals({'-- None --': -1}, choices)

    def test_old_assessment_assignment(self):
        new_course_context = actions.simple_add_course(
            'new_course', ADMIN_EMAIL, 'My New Course')
        new_course = courses.Course(None, new_course_context)
        new_course.import_from(
            sites.get_all_courses(rules_text='course:/:/')[0])
        new_course.save()

        unit_rest_handler = unit_lesson_editor.UnitRESTHandler()
        unit_rest_handler.app_context = new_course_context

        # Use REST handler function to save pre/post handlers on one unit.
        errors = []
        unit = new_course.get_units_of_type(verify.UNIT_TYPE_UNIT)[0]
        assessment = new_course.get_units_of_type(
            verify.UNIT_TYPE_ASSESSMENT)[0]
        unit_rest_handler.apply_updates(
            unit,
            {
                'title': unit.title,
                'now_available': unit.now_available,
                'label_groups': [],
                'pre_assessment': assessment.unit_id,
                'post_assessment': -1,
            }, errors)
        self.assertEquals([
            'The version of assessment "Pre-course assessment" is '
            'not compatible with use as a pre/post unit element'], errors)

    def test_new_assessment_availability(self):
        unit_rest_handler = unit_lesson_editor.UnitRESTHandler()

        schema = unit_rest_handler.get_annotations_dict(
            self.course, self.unit_no_lessons.unit_id)
        choices = self._get_selection_choices(
            schema, ['properties', 'pre_assessment', '_inputex'])
        self.assertEquals({
            '-- None --': -1,
            self.assessment_one.title: self.assessment_one.unit_id,
            self.assessment_two.title: self.assessment_two.unit_id}, choices)

        choices = self._get_selection_choices(
            schema, ['properties', 'post_assessment', '_inputex'])
        self.assertEquals({
            '-- None --': -1,
            self.assessment_one.title: self.assessment_one.unit_id,
            self.assessment_two.title: self.assessment_two.unit_id}, choices)

    def test_rest_unit_assignment(self):
        unit_rest_handler = unit_lesson_editor.UnitRESTHandler()
        unit_rest_handler.app_context = self.course.app_context
        # Use REST handler function to save pre/post handlers on one unit.
        errors = []
        unit_rest_handler.apply_updates(
            self.unit_no_lessons,
            {
                'title': self.unit_no_lessons.title,
                'now_available': self.unit_no_lessons.now_available,
                'label_groups': [],
                'pre_assessment': self.assessment_one.unit_id,
                'post_assessment': self.assessment_two.unit_id,
            }, errors)
        self.assertEquals([], errors)
        self.assertEquals(self.unit_no_lessons.pre_assessment,
                          self.assessment_one.unit_id)
        self.assertEquals(self.unit_no_lessons.post_assessment,
                          self.assessment_two.unit_id)
        self.course.save()

        # Verify that the assessments are no longer available for choosing
        # on the other unit.
        schema = unit_rest_handler.get_annotations_dict(
            self.course, self.unit_one_lesson.unit_id)
        choices = self._get_selection_choices(
            schema, ['properties', 'pre_assessment', '_inputex'])
        self.assertEquals({'-- None --': -1}, choices)

        # Verify that they are available for choosing on the unit where
        # they are assigned.
        schema = unit_rest_handler.get_annotations_dict(
            self.course, self.unit_no_lessons.unit_id)
        choices = self._get_selection_choices(
            schema, ['properties', 'pre_assessment', '_inputex'])
        self.assertEquals({
            '-- None --': -1,
            self.assessment_one.title: self.assessment_one.unit_id,
            self.assessment_two.title: self.assessment_two.unit_id}, choices)

        # Verify that attempting to set pre/post assessments that
        # are already in use fails.
        errors = []
        unit_rest_handler.apply_updates(
            self.unit_one_lesson,
            {
                'title': self.unit_one_lesson.title,
                'now_available': self.unit_one_lesson.now_available,
                'label_groups': [],
                'pre_assessment': self.assessment_one.unit_id,
                'post_assessment': self.assessment_two.unit_id,
            }, errors)
        self.assertEquals(
            ['Assessment "Assessment One" is already '
             'asssociated to unit "No Lessons"',
             'Assessment "Assessment Two" is already '
             'asssociated to unit "No Lessons"'], errors)
        self.assertEquals(self.unit_one_lesson.pre_assessment, None)
        self.assertEquals(self.unit_one_lesson.post_assessment, None)
        self.course.save()

        # Verify that swapping the order of pre/post assessments on the
        # unit that already has them is fine.
        errors = []
        unit_rest_handler.apply_updates(
            self.unit_no_lessons,
            {
                'title': self.unit_no_lessons.title,
                'now_available': self.unit_no_lessons.now_available,
                'label_groups': [],
                'pre_assessment': self.assessment_two.unit_id,
                'post_assessment': self.assessment_one.unit_id,
            }, errors)
        self.assertEquals([], errors)
        self.assertEquals(self.unit_no_lessons.pre_assessment,
                          self.assessment_two.unit_id)
        self.assertEquals(self.unit_no_lessons.post_assessment,
                          self.assessment_one.unit_id)
        self.course.save()

        # Verify that using the same assessment as both pre and post fails.
        errors = []
        unit_rest_handler.apply_updates(
            self.unit_no_lessons,
            {
                'title': self.unit_no_lessons.title,
                'now_available': self.unit_no_lessons.now_available,
                'label_groups': [],
                'pre_assessment': self.assessment_one.unit_id,
                'post_assessment': self.assessment_one.unit_id,
            }, errors)
        self.assertEquals([
            'The same assessment cannot be used as both the pre '
            'and post assessment of a unit.'], errors)
        self.assertEquals(self.unit_no_lessons.pre_assessment,
                          self.assessment_one.unit_id)
        self.assertEquals(self.unit_no_lessons.post_assessment, None)
        self.course.save()

    def test_admin_page_display_ordering(self):
        actions.login(ADMIN_EMAIL, is_admin=True)
        response = self.get(DASHBOARD_URL)

        # In order declared.
        self._assert_contains_in_order(response, [
            'No Lessons',
            'One Lesson',
            'Lesson One',
            'Assessment One',
            'Assessment Two',
            ])

        # Assessments attached to 'No Lessons' unit
        self.unit_no_lessons.pre_assessment = self.assessment_one.unit_id
        self.unit_no_lessons.post_assessment = self.assessment_two.unit_id
        self.course.save()
        response = self.get(DASHBOARD_URL)
        self._assert_contains_in_order(response, [
            'No Lessons',
            'Assessment One',
            'Assessment Two',
            'One Lesson',
            'Lesson One',
            ])

        # Assessments attached to 'One Lesson' unit
        self.unit_no_lessons.pre_assessment = None
        self.unit_no_lessons.post_assessment = None
        self.unit_one_lesson.pre_assessment = self.assessment_one.unit_id
        self.unit_one_lesson.post_assessment = self.assessment_two.unit_id
        self.course.save()
        response = self.get(DASHBOARD_URL)
        self._assert_contains_in_order(response, [
            'No Lessons',
            'One Lesson',
            'Assessment One',
            'Lesson One',
            'Assessment Two',
            ])

        # One as pre-asssesment on one unit, one as post- on the other.
        self.unit_no_lessons.pre_assessment = None
        self.unit_no_lessons.post_assessment = self.assessment_two.unit_id
        self.unit_one_lesson.pre_assessment = self.assessment_one.unit_id
        self.unit_one_lesson.post_assessment = None
        self.course.save()
        response = self.get(DASHBOARD_URL)
        self._assert_contains_in_order(response, [
            'No Lessons',
            'Assessment Two',
            'One Lesson',
            'Assessment One',
            'Lesson One',
            ])
