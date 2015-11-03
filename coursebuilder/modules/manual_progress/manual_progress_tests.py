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
from common import utils as common_utils
from models import courses
from models import models
from models import transforms
from modules.analytics import analytics
from modules.manual_progress import manual_progress
from tests.functional import actions

COURSE_NAME = 'tracks_test'
COURSE_TITLE = 'Tracks Test'
NAMESPACE = 'ns_%s' % COURSE_NAME
ADMIN_EMAIL = 'admin@foo.com'
REGISTERED_STUDENT_EMAIL = 'foo@bar.com'
REGISTERED_STUDENT_NAME = 'John Smith'
UNREGISTERED_STUDENT_EMAIL = 'bar@bar.com'
COURSE_OVERVIEW_URL = '/%s/course' % COURSE_NAME
STUDENT_LABELS_URL = '/%s/rest/student/labels' % COURSE_NAME
STUDENT_SETTINGS_URL = '/%s/student/home' % COURSE_NAME

LESSON_PROGRESS_URL = '/%s%s' % (COURSE_NAME,
                                 manual_progress.LessonProgressRESTHandler.URI)
UNIT_PROGRESS_URL = '/%s%s' % (COURSE_NAME,
                               manual_progress.UnitProgressRESTHandler.URI)
COURSE_PROGRESS_URL = '/%s%s' % (COURSE_NAME,
                                 manual_progress.CourseProgressRESTHandler.URI)
ASSESSMENT_COMPLETION_URL = '/%s/answer' % COURSE_NAME


class ManualProgressTest(actions.TestBase):

    def setUp(self):
        super(ManualProgressTest, self).setUp()

        # Add a course that will show up.
        context = actions.simple_add_course(COURSE_NAME, ADMIN_EMAIL,
                                            COURSE_TITLE)

        # Register a student for that course.
        actions.login(REGISTERED_STUDENT_EMAIL)
        actions.register(self, REGISTERED_STUDENT_NAME, COURSE_NAME)

        # Add content to course
        self._course = courses.Course(None, context)

        self._unit_one = self._course.add_unit()
        self._unit_one.title = 'Unit Labels: Foo'
        self._unit_one.availability = courses.AVAILABILITY_AVAILABLE
        self._lesson_1_1 = self._course.add_lesson(self._unit_one)
        self._lesson_1_1.title = 'Unit One, Lesson One'
        self._lesson_1_1.availability = courses.AVAILABILITY_AVAILABLE
        self._lesson_1_1.manual_progress = True
        self._lesson_1_2 = self._course.add_lesson(self._unit_one)
        self._lesson_1_2.title = 'Unit One, Lesson Two'
        self._lesson_1_2.availability = courses.AVAILABILITY_AVAILABLE
        self._lesson_1_2.manual_progress = True

        self._unit_two = self._course.add_unit()
        self._unit_two.title = 'Unit Labels: Foo'
        self._unit_two.availability = courses.AVAILABILITY_AVAILABLE
        self._unit_two.manual_progress = True
        self._lesson_2_1 = self._course.add_lesson(self._unit_two)
        self._lesson_2_1.title = 'Unit Two, Lesson One'
        self._lesson_2_1.availability = courses.AVAILABILITY_AVAILABLE
        self._lesson_2_2 = self._course.add_lesson(self._unit_two)
        self._lesson_2_2.title = 'Unit Two, Lesson Two'
        self._lesson_2_2.availability = courses.AVAILABILITY_AVAILABLE

        self._sub_assessment = self._course.add_assessment()
        self._sub_assessment.availability = courses.AVAILABILITY_AVAILABLE

        self._toplevel_assessment = self._course.add_assessment()
        self._sub_assessment.availability = courses.AVAILABILITY_AVAILABLE

        self._unit_three = self._course.add_unit()
        self._unit_three.pre_assessment = self._sub_assessment.unit_id

        self._course.save()

        with common_utils.Namespace(NAMESPACE):
            self.foo_id = models.LabelDAO.save(models.LabelDTO(
                None, {'title': 'Foo',
                       'descripton': 'foo',
                       'type': models.LabelDTO.LABEL_TYPE_COURSE_TRACK}))
            self.bar_id = models.LabelDAO.save(models.LabelDTO(
                None, {'title': 'Bar',
                       'descripton': 'bar',
                       'type': models.LabelDTO.LABEL_TYPE_COURSE_TRACK}))
        self.overridden_environment = actions.OverriddenEnvironment(
            {'course': {analytics.CAN_RECORD_STUDENT_EVENTS: 'true'}})
        self.overridden_environment.__enter__()

    def tearDown(self):
        self.overridden_environment.__exit__()
        super(ManualProgressTest, self).tearDown()


    def _expect_response(self, response, status, message, html_status=200):
        content = transforms.loads(response.body)
        self.assertEquals(html_status, response.status_int)
        self.assertEquals(status, content['status'])
        self.assertEquals(message, content['message'])

    def _expect_payload(self, response, status):
        content = transforms.loads(response.body)
        self.assertEquals(200, response.status_int)
        self.assertEquals(200, content['status'])
        self.assertEquals('OK.', content['message'])
        if status:
            payload = transforms.loads(content['payload'])
            self.assertEquals(status, payload['status'])

    def _assert_progress_state(self, expected, lesson_title, response):
        title_index = response.body.index(lesson_title)
        alt_marker = 'alt="'
        state_start = response.body.rfind(
            alt_marker, 0, title_index) + len(alt_marker)
        state_end = response.body.find('"', state_start)
        self.assertEquals(expected, response.body[state_start:state_end])

    def _get(self, url, unit_id):
        return self.get(
            url +
            '?xsrf_token=%s' % crypto.XsrfTokenManager.create_xsrf_token(
                manual_progress.XSRF_ACTION) +
            '&key=%s' % unit_id)

    def _get_course(self):
        return self._get(COURSE_PROGRESS_URL, 'course')

    def _get_unit(self, unit_id):
        return self._get(UNIT_PROGRESS_URL, unit_id)

    def _get_lesson(self, lesson_id):
        return self._get(LESSON_PROGRESS_URL, lesson_id)

    def _post(self, url, key):
        params = {
            'xsrf_token': crypto.XsrfTokenManager.create_xsrf_token(
                manual_progress.XSRF_ACTION),
            'key': key,
        }
        return self.post(url, params)

    def _post_course(self):
        return self._post(COURSE_PROGRESS_URL, 'course')

    def _post_unit(self, unit_id):
        return self._post(UNIT_PROGRESS_URL, str(unit_id))

    def _post_lesson(self, lesson_id):
        return self._post(LESSON_PROGRESS_URL, str(lesson_id))

    def _post_assessment(self, assessment_id):
        self.post(ASSESSMENT_COMPLETION_URL, {
            'assessment_type': str(assessment_id),
            'score': '0',
            'xsrf_token': crypto.XsrfTokenManager.create_xsrf_token(
                'assessment-post')})

    def test_not_logged_in(self):
        actions.logout()
        response = self.get(UNIT_PROGRESS_URL +
                            '?key=%s' % self._unit_one.unit_id)
        self._expect_response(
            response, 403,
            'Bad XSRF token. Please reload the page and try again')

    def test_not_registered(self):
        actions.logout()
        actions.login(UNREGISTERED_STUDENT_EMAIL)
        xsrf_token = crypto.XsrfTokenManager.create_xsrf_token(
            manual_progress.XSRF_ACTION)
        response = self.get(UNIT_PROGRESS_URL +
                            '?key=%s' % self._unit_one.unit_id +
                            '&xsrf_token=%s' % xsrf_token)
        self._expect_response(response, 401, 'Access Denied.')

    def test_no_key(self):
        xsrf_token = crypto.XsrfTokenManager.create_xsrf_token(
            manual_progress.XSRF_ACTION)
        response = self.get(UNIT_PROGRESS_URL +
                            '?xsrf_token=%s' % xsrf_token)
        self._expect_response(response, 400, 'Bad Request.')

    def test_no_such_course(self):
        url = '/no_such_course%s?key=%s' % (
            manual_progress.UnitProgressRESTHandler.URI, self._unit_one.unit_id)
        response = self.get(url, expect_errors=True)
        self.assertEquals(404, response.status_int)

    def test_no_xsrf_token(self):
        response = self.get(UNIT_PROGRESS_URL + '?key=monkeyshines')
        self._expect_response(
            response, 403,
            'Bad XSRF token. Please reload the page and try again')

    def test_no_such_unit(self):
        response = self._get_unit('monkeyshines')
        self._expect_response(response, 400, 'Bad Request.')

    def test_no_such_lesson(self):
        response = self._get_lesson('monkeyshines')
        self._expect_response(response, 400, 'Bad Request.')

    def test_unit_manual_progress_not_allowed(self):
        response = self._post_unit(self._unit_one.unit_id)
        self._expect_response(response, 401, 'Access Denied.')

    def test_lesson_manual_progress_not_allowed(self):
        response = self._post_lesson(self._lesson_2_2.lesson_id)
        self._expect_response(response, 401, 'Access Denied.')

    def test_uncompleted_unit_status(self):
        response = self._get_unit(self._unit_one.unit_id)
        self._expect_payload(response, None)

    def test_uncompleted_lesson_status(self):
        response = self._get_lesson(self._lesson_1_1.lesson_id)
        self._expect_payload(response, None)

    def test_uncompleted_course_status(self):
        response = self._get_course()
        self._expect_payload(response, 0)

    def test_manual_lesson_progress(self):
        # Complete 1 of 2 lessons; unit should show as partial.
        response = self._post_lesson(self._lesson_1_1.lesson_id)
        self._expect_payload(response, 2)
        response = self._get_unit(self._unit_one.unit_id)
        self._expect_payload(response, 1)
        response = self._get_course()
        self._expect_payload(response, 1)

        # Complete 2 of 2 lessons; unit should show as fully successful.
        response = self._post_lesson(self._lesson_1_2.lesson_id)
        self._expect_payload(response, 2)
        response = self._get_unit(self._unit_one.unit_id)
        self._expect_payload(response, 2)
        response = self._get_course()
        self._expect_payload(response, 1)

    def test_manual_unit_progress(self):
        response = self._post_unit(self._unit_two.unit_id)
        self._expect_payload(response, 2)

        # Component lessons should not show as completed.
        response = self._get_lesson(self._lesson_2_1.lesson_id)
        self._expect_payload(response, 0)
        response = self._get_lesson(self._lesson_2_2.lesson_id)
        self._expect_payload(response, 0)

    def test_view_non_manual_lesson_increments_progress(self):
        url = '/%s/unit?unit=%s&lesson=%s' % (
            COURSE_NAME, self._unit_two.unit_id, self._lesson_2_2.lesson_id)
        response = self.get(url)
        self._assert_progress_state(
            'Not yet started', '2.1 ' + self._lesson_2_1.title, response)
        self._assert_progress_state(
            'Not yet started', '2.2 ' + self._lesson_2_2.title, response)

        response = self._get_lesson(self._lesson_2_2.lesson_id)
        self._expect_payload(response, 2)
        response = self._get_course()
        self._expect_payload(response, 1)

        response = self.get(url)
        self._assert_progress_state(
            'Not yet started', '2.1 ' + self._lesson_2_1.title, response)
        self._assert_progress_state(
            'Completed', '2.2 ' + self._lesson_2_2.title, response)

    def test_view_manual_lesson_does_not_increment_progress(self):
        url = '/%s/unit?unit=%s&lesson=%s' % (
            COURSE_NAME, self._unit_one.unit_id, self._lesson_1_2.lesson_id)
        response = self.get(url)
        self._assert_progress_state(
            'Not yet started', '1.1 ' + self._lesson_1_1.title, response)
        self._assert_progress_state(
            'Not yet started', '1.2 ' + self._lesson_1_2.title, response)

        response = self._get_lesson(self._lesson_1_2.lesson_id)
        self._expect_payload(response, None)

        response = self.get(url)
        self._assert_progress_state(
            'Not yet started', '1.1 ' + self._lesson_1_1.title, response)
        self._assert_progress_state(
            'Not yet started', '1.2 ' + self._lesson_1_2.title, response)

        response = self._post_lesson(self._lesson_1_2.lesson_id)
        response = self.get(url)
        self._assert_progress_state(
            'Not yet started', '1.1 ' + self._lesson_1_1.title, response)
        self._assert_progress_state(
            'Completed', '1.2 ' + self._lesson_1_2.title, response)

    def test_events_handler_ignores_manually_completed_items(self):
        url = '/%s/rest/events' % COURSE_NAME
        payload = transforms.dumps({
            'location': 'http://localhost:8081/%s/unit?unit=%s&lesson=%s' % (
                COURSE_NAME, self._unit_one.unit_id, self._lesson_1_2.lesson_id)
        })
        request = transforms.dumps({
            'xsrf_token': crypto.XsrfTokenManager.create_xsrf_token(
                'event-post'),
            'source': 'attempt-lesson',
            'payload': payload
        })
        response = self.post(url, {'request': request})
        response = self._get_lesson(self._lesson_1_2.lesson_id)
        self._expect_payload(response, None)

    def test_events_handler_processes_normally_completed_items(self):
        url = '/%s/rest/events' % COURSE_NAME
        payload = transforms.dumps({
            'location': 'http://localhost:8081/%s/unit?unit=%s&lesson=%s' % (
                COURSE_NAME, self._unit_two.unit_id, self._lesson_2_2.lesson_id)
        })
        request = transforms.dumps({
            'xsrf_token': crypto.XsrfTokenManager.create_xsrf_token(
                'event-post'),
            'source': 'attempt-lesson',
            'payload': payload
        })
        response = self.post(url, {'request': request})
        response = self._get_lesson(self._lesson_2_2.lesson_id)
        self._expect_payload(response, 2)

    def test_manual_complete_course(self):
        response = self._get_course()
        self._expect_payload(response, 0)

        response = self._post_course()
        self._expect_payload(response, 2)

    def test_completing_assessment_as_lesson(self):
        self._post_assessment(self._sub_assessment.unit_id)

        # Assessment is the only content in the unit, so completing it
        # should also complete its containing unit.
        response = self._get_unit(self._unit_three.unit_id)
        self._expect_payload(response, 2)

        response = self._get_course()
        self._expect_payload(response, 1)

    def test_completing_toplevel_assessment(self):
        self._post_assessment(self._toplevel_assessment.unit_id)

        response = self._get_course()
        self._expect_payload(response, 1)

    def test_completing_all_units_completes_course(self):
        self._post_lesson(self._lesson_1_1.lesson_id)
        self._post_lesson(self._lesson_1_2.lesson_id)
        self._post_unit(self._unit_two.unit_id)
        self._post_assessment(self._sub_assessment.unit_id)
        self._post_assessment(self._toplevel_assessment.unit_id)

        response = self._get_course()
        self._expect_payload(response, 2)

    def test_unit_completion_with_labels_looks_complete(self):
        # Mark all but self._unit_two as in 'bar' track.  Especially note
        # that here we are *not* marking the sub-assessment in unit 3
        # as being in that track; this should be skipped when considering
        # unit-level completeness.
        self._unit_one.labels = str(self.bar_id)
        self._unit_three.labels = str(self.bar_id)
        self._toplevel_assessment.labels = str(self.bar_id)
        self._course.save()

        # Mark student as being in 'foo' track; student only sees
        # unit two.
        self.put(STUDENT_LABELS_URL, {'labels': str(self.foo_id)})

        # Complete unit two, and verify that the course is now complete.
        self._post_unit(self._unit_two.unit_id)
        response = self._get_course()
        self._expect_payload(response, 2)

    def test_assessment_completion_with_labels_looks_complete(self):
        # Mark all but self._unit_two as in 'bar' track.  Especially note
        # that here we are *not* marking the sub-assessment in unit 3
        # as being in that track; this should be skipped when considering
        # unit-level completeness.
        self._unit_one.labels = str(self.bar_id)
        self._unit_two.labels = str(self.bar_id)
        self._unit_three.labels = str(self.bar_id)
        self._course.save()

        # Mark student as being in 'foo' track; student only sees
        # unit two.
        self.put(STUDENT_LABELS_URL, {'labels': str(self.foo_id)})

        # Complete unit two, and verify that the course is now complete.
        self._post_assessment(self._toplevel_assessment.unit_id)
        response = self._get_course()
        self._expect_payload(response, 2)
