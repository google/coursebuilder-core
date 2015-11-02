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

"""Verify operation of student setting to remember last page visited."""

from common import utils as common_utils
from controllers import sites
from models import config
from models import courses
from models import models
from tests.functional import actions

COURSE_NAME = 'test_course'
COURSE_TITLE = 'Test Course'
NAMESPACE = 'ns_%s' % COURSE_NAME
ADMIN_EMAIL = 'admin@foo.com'
BASE_URL = '/%s' % COURSE_NAME
COURSE_URL = '/%s/course' % COURSE_NAME
REGISTERED_STUDENT_EMAIL = 'foo@bar.com'
REGISTERED_STUDENT_NAME = 'John Smith'
UNREGISTERED_STUDENT_EMAIL = 'bar@bar.com'


class StudentRedirectTestBase(actions.TestBase):

    def setUp(self):
        super(StudentRedirectTestBase, self).setUp()
        context = actions.simple_add_course(COURSE_NAME, ADMIN_EMAIL,
                                            COURSE_TITLE)
        course = courses.Course(None, context)
        self.unit = course.add_unit()
        self.unit.title = 'The Unit'
        self.unit.availability = courses.AVAILABILITY_AVAILABLE
        self.lesson_one = course.add_lesson(self.unit)
        self.lesson_one.title = 'Lesson One'
        self.lesson_one.availability = courses.AVAILABILITY_AVAILABLE
        self.lesson_two = course.add_lesson(self.unit)
        self.lesson_two.title = 'Lesson Two'
        self.lesson_two.availability = courses.AVAILABILITY_AVAILABLE
        self.assessment = course.add_assessment()
        self.assessment.title = 'The Assessment'
        self.assessment.availability = courses.AVAILABILITY_AVAILABLE
        course.save()

        actions.login(REGISTERED_STUDENT_EMAIL)
        actions.register(self, REGISTERED_STUDENT_NAME, COURSE_NAME)
        # Actions.register views the student's profile page; clear this out.
        with common_utils.Namespace(NAMESPACE):
            prefs = models.StudentPreferencesDAO.load_or_default()
            prefs.last_location = None
            models.StudentPreferencesDAO.save(prefs)


class NonRootCourse(StudentRedirectTestBase):

    def test_load_base_with_no_pref_gives_no_redirect(self):
        response = self.get(BASE_URL)
        self.assertEquals(200, response.status_int)

    def test_unregistered_student_does_not_use_prefs(self):
        actions.login(UNREGISTERED_STUDENT_EMAIL)
        response = self.get(BASE_URL)
        response = response.click('Unit 1 - The Unit')
        response = self.get(BASE_URL)
        self.assertEquals(200, response.status_int)

    def test_logged_out_does_not_use_prefs(self):
        actions.logout()
        response = self.get(BASE_URL)
        response = response.click('Unit 1 - The Unit')
        response = self.get(BASE_URL)
        self.assertEquals(200, response.status_int)

    def _test_redirects(self, saved_path):
        response = self.get(BASE_URL)
        self.assertEquals(302, response.status_int)
        self.assertEquals(saved_path, response.location)
        response = self.get(BASE_URL + '/')
        self.assertEquals(302, response.status_int)
        self.assertEquals(saved_path, response.location)

    def test_redirects_to_unit(self):
        response = self.get(BASE_URL)
        response = self.click(response, 'Unit 1 - The Unit')
        self._test_redirects(response.request.url)

    def test_redirects_to_lesson(self):
        response = self.get(BASE_URL)
        response = self.click(response, 'Unit 1 - The Unit')
        response = self.click(response, 'Next Page')
        self._test_redirects(response.request.url)

    def test_redirects_to_assessment(self):
        response = self.get(BASE_URL)
        response = self.click(response, 'The Assessment')
        self._test_redirects(response.request.url)

    def test_redirects_to_profile(self):
        response = self.get(BASE_URL)
        response = self.click(response, 'Progress')
        self._test_redirects(response.request.url)

    def test_redirects_to_course(self):
        response = self.get(COURSE_URL)
        self._test_redirects(response.request.url)

    def test_course_does_not_redirect(self):
        response = self.get(COURSE_URL)
        response = response.click('Unit 1 - The Unit')
        response = self.get(COURSE_URL)
        self.assertEquals(200, response.status_int)


class RootCourse(StudentRedirectTestBase):

    def setUp(self):
        super(RootCourse, self).setUp()
        config.Registry.test_overrides[sites.GCB_COURSES_CONFIG.name] = (
            'course:/default:/, course:/::ns_test_course')

    def tearDown(self):
        super(RootCourse, self).tearDown()
        config.Registry.test_overrides.clear()

    def test_root_redirects(self):
        response = self.get('/')
        self.assertEquals(302, response.status_int)
        self.assertEquals('http://localhost/course?use_last_location=true',
                          response.location)

    def test_root_with_no_pref_does_not_redirect_beyond_course(self):
        response = self.get('/').follow()
        self.assertEquals(200, response.status_int)
        self.assertIn('The Unit', response.body)

    def test_root_with_pref_redirects(self):
        response = self.get('/').follow()
        response = self.click(response, 'Unit 1 - The Unit')
        saved_path = response.request.url

        response = self.get('/').follow()
        self.assertEquals(302, response.status_int)
        self.assertEquals(saved_path, response.location)
