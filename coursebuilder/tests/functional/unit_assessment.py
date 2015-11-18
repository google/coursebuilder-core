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

from common import crypto
from common import utils as common_utils
from controllers import sites
from models import courses
from models import models
from modules.analytics import analytics
from modules.courses import unit_lesson_editor
from tests.functional import actions
from tools import verify

COURSE_NAME = 'unit_pre_post'
COURSE_TITLE = 'Unit Pre/Post Assessments'
NAMESPACE = 'ns_%s' % COURSE_NAME
ADMIN_EMAIL = 'admin@foo.com'
BASE_URL = '/' + COURSE_NAME
COURSE_URL = BASE_URL + '/course'
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
        self.unit_no_lessons.availability = courses.AVAILABILITY_AVAILABLE

        self.unit_one_lesson = self.course.add_unit()
        self.unit_one_lesson.title = 'One Lesson'
        self.unit_one_lesson.availability = courses.AVAILABILITY_AVAILABLE
        self.lesson = self.course.add_lesson(self.unit_one_lesson)
        self.lesson.title = 'Lesson One'
        self.lesson.objectives = 'body of lesson'
        self.lesson.availability = courses.AVAILABILITY_AVAILABLE

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

        with common_utils.Namespace(NAMESPACE):
            self.track_one_id = models.LabelDAO.save(models.LabelDTO(
                None, {'title': 'Track One',
                       'descripton': 'track_one',
                       'type': models.LabelDTO.LABEL_TYPE_COURSE_TRACK}))
            self.general_one_id = models.LabelDAO.save(models.LabelDTO(
                None, {'title': 'Track One',
                       'descripton': 'track_one',
                       'type': models.LabelDTO.LABEL_TYPE_GENERAL}))

    def tearDown(self):
        self.overridden_environment.__exit__()
        super(UnitPrePostAssessmentTest, self).tearDown()

    def _get_unit_page(self, unit):
        return self.get(BASE_URL + '/unit?unit=' + str(unit.unit_id))

    def _unit_assessment_url(self, unit_id, assessment_id):
        return "{base}/unit?unit={unit}&assessment={assessment}".format(
            base=BASE_URL,
            unit=unit_id,
            assessment=assessment_id,
        )

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
        response = self.get(COURSE_URL)
        self.assertIn(self.unit_no_lessons.title, response.body)
        self.assertIn(self.unit_one_lesson.title, response.body)
        self.assertIn(self.assessment_one.title, response.body)
        self.assertIn(self.assessment_two.title, response.body)

        self.unit_no_lessons.pre_assessment = self.assessment_one.unit_id
        self.unit_no_lessons.post_assessment = self.assessment_two.unit_id
        self.course.save()
        response = self.get(COURSE_URL)
        self.assertIn(self.unit_no_lessons.title, response.body)
        self.assertIn(self.unit_one_lesson.title, response.body)
        self.assertNotIn(self.assessment_one.title, response.body)
        self.assertNotIn(self.assessment_two.title, response.body)

    def test_pre_assessment_as_only_lesson(self):
        self.unit_no_lessons.pre_assessment = self.assessment_one.unit_id
        self.course.save()
        response = self._get_unit_page(self.unit_no_lessons)
        self.assertNotIn('This unit has no content', response.body)
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
        self.assertNotIn('This unit has no content', response.body)
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

        response = self.get(COURSE_URL)
        self._assert_progress_state(
            'Not yet started', 'Unit 2 - %s' % self.unit_one_lesson.title,
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
            'In progress', 'Unit 2 - %s' % self.unit_one_lesson.title,
            response)

    def _post_assessment(self, assessment_id):
        return self.post(BASE_URL + '/answer', {
            'xsrf_token': crypto.XsrfTokenManager.create_xsrf_token(
                'assessment-post'),
            'assessment_type': assessment_id,
            'score': '1'})

    def test_progress_via_assessment_submission(self):
        self.unit_one_lesson.pre_assessment = self.assessment_one.unit_id
        self.unit_one_lesson.post_assessment = self.assessment_two.unit_id
        self.course.save()

        # Submit pre-assessment; verify completion status.
        response = self._get_unit_page(self.unit_one_lesson)
        response = self._post_assessment(self.assessment_one.unit_id).follow()
        self._assert_progress_state(
            'Completed', self.assessment_one.title, response)
        self._assert_progress_state(
            'Not yet started', '2.1 ' + self.lesson.title, response)
        self._assert_progress_state(
            'Not yet submitted', self.assessment_two.title, response)

        # Verify that we're on the assessment confirmation page.
        self.assertIn('Thank you for taking the assessment one', response.body)
        response = self._click_next_button(response)

        # Next-button past the lesson content
        response = self._click_next_button(response)
        self._assert_progress_state(
            'Completed', self.assessment_one.title, response)
        self._assert_progress_state(
            'Completed', '2.1 ' + self.lesson.title, response)
        self._assert_progress_state(
            'Not yet submitted', self.assessment_two.title, response)

        # Submit post-assessment; unit should now be marked complete.
        response = self._post_assessment(self.assessment_two.unit_id).follow()

        # Verify that we get confirmation page on post-assessment
        self.assertIn('Thank you for taking the assessment two', response.body)
        self._assert_progress_state(
            'Completed', self.assessment_one.title, response)
        self._assert_progress_state(
            'Completed', '2.1 ' + self.lesson.title, response)
        self._assert_progress_state(
            'Completed', self.assessment_two.title, response)

        # Verify that the overall course state is completed.
        response = self._click_next_button(response)
        self._assert_progress_state(
            'Completed', 'Unit 2 - %s' % self.unit_one_lesson.title,
            response)

    def _get_selection_choices(self, schema, match):
        ret = {}
        for item in schema:
            if item[0] == match:
                for choice in item[1]['choices']:
                    ret[choice['label']] = choice['value']
        return ret

    def test_old_assessment_availability(self):
        actions.login(ADMIN_EMAIL, is_admin=True)
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
        schema = unit_rest_handler.get_schema(
            new_course, unit.unit_id).get_schema_dict()

        # Verify that there are 4 valid choices for pre- or post-asssments
        # for this unit
        choices = self._get_selection_choices(
            schema, ['properties', 'pre_assessment', '_inputex'])
        self.assertEquals(5, len(choices))
        self.assertEquals(-1, choices['-- None --'])

        choices = self._get_selection_choices(
            schema, ['properties', 'post_assessment', '_inputex'])
        self.assertEquals(5, len(choices))
        self.assertEquals(-1, choices['-- None --'])

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
                'label_groups': [],
                'pre_assessment': assessment.unit_id,
                'post_assessment': -1,
                'show_contents_on_one_page': False,
                'manual_progress': False,
                'description': None,
                'unit_header': None,
                'unit_footer': None,
            }, errors)
        assert not errors

    def test_new_assessment_availability(self):
        actions.login(ADMIN_EMAIL, is_admin=True)
        unit_rest_handler = unit_lesson_editor.UnitRESTHandler()

        schema = unit_rest_handler.get_schema(
            self.course, self.unit_no_lessons.unit_id).get_schema_dict()
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
        actions.login(ADMIN_EMAIL, is_admin=True)
        unit_rest_handler = unit_lesson_editor.UnitRESTHandler()
        unit_rest_handler.app_context = self.course.app_context
        # Use REST handler function to save pre/post handlers on one unit.
        errors = []
        unit_rest_handler.apply_updates(
            self.unit_no_lessons,
            {
                'title': self.unit_no_lessons.title,
                'label_groups': [],
                'pre_assessment': self.assessment_one.unit_id,
                'post_assessment': self.assessment_two.unit_id,
                'show_contents_on_one_page': False,
                'manual_progress': False,
                'description': None,
                'unit_header': None,
                'unit_footer': None,
            }, errors)
        self.assertEquals([], errors)
        self.assertEquals(self.unit_no_lessons.pre_assessment,
                          self.assessment_one.unit_id)
        self.assertEquals(self.unit_no_lessons.post_assessment,
                          self.assessment_two.unit_id)
        self.course.save()

        # Verify that the assessments are no longer available for choosing
        # on the other unit.
        schema = unit_rest_handler.get_schema(
            self.course, self.unit_one_lesson.unit_id).get_schema_dict()
        choices = self._get_selection_choices(
            schema, ['properties', 'pre_assessment', '_inputex'])
        self.assertEquals({'-- None --': -1}, choices)

        # Verify that they are available for choosing on the unit where
        # they are assigned.
        schema = unit_rest_handler.get_schema(
            self.course, self.unit_no_lessons.unit_id).get_schema_dict()
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
                'label_groups': [],
                'pre_assessment': self.assessment_one.unit_id,
                'post_assessment': self.assessment_two.unit_id,
                'show_contents_on_one_page': False,
                'manual_progress': False,
                'description': None,
                'unit_header': None,
                'unit_footer': None,
            }, errors)
        self.assertEquals(
            ['Assessment "Assessment One" is already '
             'associated to unit "No Lessons"',
             'Assessment "Assessment Two" is already '
             'associated to unit "No Lessons"'], errors)
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
                'label_groups': [],
                'pre_assessment': self.assessment_two.unit_id,
                'post_assessment': self.assessment_one.unit_id,
                'show_contents_on_one_page': False,
                'manual_progress': False,
                'description': None,
                'unit_header': None,
                'unit_footer': None,
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
                'label_groups': [],
                'pre_assessment': self.assessment_one.unit_id,
                'post_assessment': self.assessment_one.unit_id,
                'show_contents_on_one_page': False,
                'manual_progress': False,
                'description': None,
                'unit_header': None,
                'unit_footer': None,
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

    def test_delete_assessment_as_lesson(self):
        self.unit_no_lessons.pre_assessment = self.assessment_one.unit_id
        self.unit_no_lessons.post_assessment = self.assessment_two.unit_id
        self.course.save()
        self.course.delete_unit(self.assessment_one)
        self.course.delete_unit(self.assessment_two)
        self.course.save()

        actions.login(ADMIN_EMAIL, is_admin=True)
        response = self.get(DASHBOARD_URL)
        self.assertEquals(200, response.status_int)

    def test_assessments_with_tracks_not_settable_as_pre_post(self):
        self.assessment_one.labels = str(self.track_one_id)
        self.assessment_two.labels = str(self.track_one_id)
        self.course.save()
        unit_rest_handler = unit_lesson_editor.UnitRESTHandler()
        unit_rest_handler.app_context = self.course.app_context

        with common_utils.Namespace(NAMESPACE):
            errors = []
            unit_rest_handler.apply_updates(
                self.unit_no_lessons,
                {
                    'title': self.unit_no_lessons.title,
                    'label_groups': [],
                    'pre_assessment': self.assessment_one.unit_id,
                    'post_assessment': self.assessment_two.unit_id,
                    'show_contents_on_one_page': False,
                    'manual_progress': False,
                    'description': None,
                    'unit_header': None,
                    'unit_footer': None,
                }, errors)
            self.assertEquals([
                'Assessment "Assessment One" has track labels, so it '
                'cannot be used as a pre/post unit element',
                'Assessment "Assessment Two" has track labels, so it '
                'cannot be used as a pre/post unit element'], errors)

    def _test_assessments_as_pre_post_labels(
            self, label_id, label_type, expected_errors):

        class FakeRequest(object):
            host_url = 'https://www.example.com'

        self.unit_no_lessons.pre_assessment = self.assessment_one.unit_id
        self.unit_no_lessons.post_assessment = self.assessment_two.unit_id
        self.course.save()

        assessment_rest_handler = unit_lesson_editor.AssessmentRESTHandler()
        assessment_rest_handler.app_context = self.course.app_context
        assessment_rest_handler.request = FakeRequest()

        with common_utils.Namespace(NAMESPACE):
            errors = []
            properties = assessment_rest_handler.unit_to_dict(
                self.assessment_one)
            properties[label_type] = [label_id]
            assessment_rest_handler.apply_updates(self.assessment_one,
                                                  properties, errors)
            self.assertEquals(expected_errors, errors)

    def test_assessments_as_pre_post_cannot_have_tracks_added(self):
        self._test_assessments_as_pre_post_labels(
            self.track_one_id, 'tracks',
            ['Cannot set track labels on entities which are used within other '
            'units.'])

    def test_assessments_as_pre_post_can_have_general_labels_added(self):
        self._test_assessments_as_pre_post_labels(
            self.general_one_id, 'labels', [])

    def test_suppress_next_prev_buttons(self):
        # Set up one-lesson unit w/ pre, post assessment.  Set course
        # settings to suppress prev/next buttons only on assessments.
        actions.login(ADMIN_EMAIL)
        actions.update_course_config(COURSE_NAME, {
            'unit': {'hide_assessment_navigation_buttons': True}})
        actions.login(STUDENT_EMAIL)
        self.unit_one_lesson.pre_assessment = self.assessment_one.unit_id
        self.unit_one_lesson.post_assessment = self.assessment_two.unit_id
        self.course.save()

        # Verify we have suppressed prev/next/end buttons on pre-assessment.
        response = self._get_unit_page(self.unit_one_lesson)
        self.assertNotIn('Previous Page', response.body)
        self.assertNotIn('Next Page', response.body)
        self.assertNotIn(' End ', response.body)

        # Submit assessment.  Verify confirmation page _does_ have prev/next.
        response = self._post_assessment(self.assessment_one.unit_id).follow()
        self.assertIn('Previous Page', response.body)
        self.assertIn('Next Page', response.body)

        # Click to lesson.  Verify have prev/next.
        response = self._click_next_button(response)
        self.assertIn('Previous Page', response.body)
        self.assertIn('Next Page', response.body)

        # Verify we have suppressed prev/next/end buttons on post-assessment.
        response = self._click_next_button(response)
        self.assertNotIn('Previous Page', response.body)
        self.assertNotIn('Next Page', response.body)
        self.assertNotIn(' End ', response.body)

        # Submit post-assessment; verify we have prev/end buttons
        response = self._post_assessment(self.assessment_two.unit_id).follow()
        self.assertIn('Previous Page', response.body)
        self.assertNotIn('Next Page', response.body)
        self.assertIn(' End ', response.body)

    def test_private_assessments(self):
        actions.login(ADMIN_EMAIL)

        self.unit_one_lesson.pre_assessment = self.assessment_one.unit_id
        self.unit_one_lesson.post_assessment = self.assessment_two.unit_id
        self.assessment_one.availability = courses.AVAILABILITY_UNAVAILABLE
        self.assessment_two.availability = courses.AVAILABILITY_UNAVAILABLE
        self.course.save()

        actions.login(STUDENT_EMAIL)

        response = self.get(self._unit_assessment_url(
            self.unit_one_lesson.unit_id, self.assessment_one.unit_id))
        self.assertNotIn(self.assessment_one.html_content, response.body,
            msg=('Private pre-assessment content should not be visible to '
                'student'))
        self.assertEquals(response.status_int, 302)  # expect redir to /

        actions.login(ADMIN_EMAIL)

        response = self.get(self._unit_assessment_url(
            self.unit_one_lesson.unit_id, self.assessment_one.unit_id))
        self.assertIn(self.assessment_one.html_content, response.body,
            msg='Private pre-assessment content should be visible to admin')

        response = self.get(self._unit_assessment_url(
            self.unit_one_lesson.unit_id, self.assessment_two.unit_id))
        self.assertIn(self.assessment_two.html_content, response.body,
            msg='Private post-assessment content should be visible to admin')


class UnitPartialUpdateTests(actions.TestBase):

    def setUp(self):
        super(UnitPartialUpdateTests, self).setUp()
        context = actions.simple_add_course(
            COURSE_NAME, ADMIN_EMAIL, COURSE_TITLE)
        self.course = courses.Course(None, context)
        self.unit = self.course.add_unit()
        self.assessment = self.course.add_assessment()
        self.link = self.course.add_link()
        self.course.save()
        actions.login(ADMIN_EMAIL, is_admin=True)

        self.rest_handler = unit_lesson_editor.CommonUnitRESTHandler()
        self.rest_handler.app_context = self.course.app_context

    def test_set_none(self):
        errors = []
        self.rest_handler.apply_updates(self.unit, {}, errors)
        self.rest_handler.apply_updates(self.assessment, {}, errors)
        self.rest_handler.apply_updates(self.link, {}, errors)
        self.assertEquals(0, len(errors))

    def test_set_only_title(self):
        errors = []
        self.rest_handler.apply_updates(
            self.unit, {'title': 'Title'}, errors)
        self.rest_handler.apply_updates(
            self.assessment, {'title': 'Title'}, errors)
        self.rest_handler.apply_updates(
            self.link, {'title': 'Title'}, errors)
        self.assertEquals(self.unit.title, 'Title')
        self.assertEquals(self.assessment.title, 'Title')
        self.assertEquals(self.link.title, 'Title')
        self.assertEquals(0, len(errors))

    def test_set_only_unit_header(self):
        errors = []
        self.rest_handler.apply_updates(
            self.unit, {'unit_header': 'content'}, errors)
        self.assertEquals(self.unit.unit_header, 'content')
        self.assertEquals(0, len(errors))

    def test_set_only_assessment_weight(self):
        errors = []
        self.rest_handler.apply_updates(
            self.assessment, {'weight': '123.4'}, errors)
        self.assertEquals(self.assessment.weight, 123.4)
        self.assertEquals(0, len(errors))

    def test_set_only_link_href(self):
        errors = []
        self.rest_handler.apply_updates(
            self.link, {'url': 'foo'}, errors)
        self.assertEquals(self.link.href, 'foo')
        self.assertEquals(0, len(errors))
