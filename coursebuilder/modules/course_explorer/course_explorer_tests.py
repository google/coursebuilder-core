# Copyright 2013 Google Inc. All Rights Reserved.
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

"""Functional tests for modules/course_explorer/course_explorer.py."""

__author__ = 'rahulsingal@google.com (Rahul Singal)'


from controllers import sites
from models import config
from models import courses
from models import transforms
from models.models import PersonalProfile
from modules.course_explorer import course_explorer
from tests.functional import actions


class BaseExplorerTest(actions.TestBase):
    """Base class for testing explorer pages."""

    def setUp(self):
        super(BaseExplorerTest, self).setUp()
        config.Registry.test_overrides[
            course_explorer.GCB_ENABLE_COURSE_EXPLORER_PAGE.name] = True

    def tearDown(self):
        config.Registry.test_overrides = {}
        super(BaseExplorerTest, self).tearDown()


class CourseExplorerTest(BaseExplorerTest):
    """Tests course_explorer module."""
    STUDENT_EMAIL = 'Student'

    def test_single_unregistered_course(self):
        # This call should redirect to explorer page.
        response = self.get('/')
        self.assertIn('/explorer', response.location)

        actions.login(self.STUDENT_EMAIL)

        # Test the explorer page.
        response = self.get('/explorer')
        self.assertEquals(response.status_int, 200)
        self.assertIn('Register', response.body)

        # Test 'my courses' page when a student is not enrolled in any course.
        response = self.get('/')
        self.assertEquals(response.status_int, 302)
        self.assertEquals(
            response.headers['Location'], 'http://localhost/explorer')

    def test_single_uncompleted_course(self):
        """Tests for a single available course."""

        # Test 'my courses' page when a student is enrolled in all courses.
        name = 'Test student courses page'
        actions.login(self.STUDENT_EMAIL)
        actions.register(self, name)
        response = self.get('/')
        self.assertEquals(response.status_int, 200)
        self.assertIn('Progress', response.body)
        self.assertNotIn(
            'You are not currently enrolled in any course', response.body)

        self.assertIn('Explore Courses', response.body)
        self.assertIn('My Courses', response.body)
        self.assertNotIn('Dashboard', response.body)

        response = self.get('/explorer')

    def test_single_completed_course(self):
        """Tests when a single completed course is present."""
        name = 'Test Assessments'

        # Register.
        user = actions.login('test_assessments@google.com')
        actions.register(self, name)

        response = self.get('/explorer')
        # Before a course is not completed,
        # explorer page should not show 'view score' button.
        self.assertNotIn('View score', response.body)

        # Assign a grade to the course enrolled to mark it complete.
        profile = PersonalProfile.get_by_key_name(user.user_id())
        info = {'final_grade': 'A'}
        course_info_dict = {'': info}
        profile.course_info = transforms.dumps(course_info_dict)
        profile.put()

        # Check if 'Go to course' button is not visible on explorer page.
        response = self.get('/explorer')
        self.assertNotIn('Go to course', response.body)

        # Check if 'View score' button is visible on explorer page.
        response = self.get('/explorer')
        self.assertIn('View score', response.body)

    def test_multiple_course(self):
        """Tests when multiple courses are available."""
        sites.setup_courses('course:/test::ns_test, course:/:/')
        name = 'Test completed course'
        email = 'Student'

        # Make the course available.
        get_environ_old = sites.ApplicationContext.get_environ

        def get_environ_new(self):
            environ = get_environ_old(self)
            environ['course']['now_available'] = True
            return environ

        sites.ApplicationContext.get_environ = get_environ_new

        actions.login(email)
        actions.register(self, name)
        response = self.get('/')

        # Clean up app_context.
        sites.ApplicationContext.get_environ = get_environ_old
        sites.reset_courses()

    def test_can_register_true(self):
        courses.Course.ENVIRON_TEST_OVERRIDES = {
            'reg_form': {'can_register': True}}

        dom = self.parse_html_string(self.get('/explorer').body)
        item = dom.find('.//li[@class="gcb-explorer-list-item"]')
        self.assertEquals(
            'Power Searching with Google',
            item.find('.//a[@class="gcb-explorer-course-title"]').text)
        # Registration button present
        self.assertIsNotNone(item.find('.//a[@href="/register"]'))

    def test_can_register_false(self):
        courses.Course.ENVIRON_TEST_OVERRIDES = {
            'reg_form': {'can_register': False}}

        dom = self.parse_html_string(self.get('/explorer').body)
        item = dom.find('.//li[@class="gcb-explorer-list-item"]')
        self.assertEquals(
            'Power Searching with Google',
            item.find('.//a[@class="gcb-explorer-course-title"]').text)
        # No registration button present
        self.assertIsNone(item.find('.//a[@href="/register"]'))

    def test_student_access(self):
        config.Registry.test_overrides[
            sites.GCB_COURSES_CONFIG.name] = 'course:/:/'

        email = 'student'
        actions.login(email)
        response = self.get('/explorer')
        self.assertIn('Explore Courses', response.body)
        self.assertNotIn('My Courses', response.body)
        self.assertNotIn('Dashboard', response.body)

    def test_admin_access(self):
        # check the admin site link
        actions.login('admin@test.foo', is_admin=True)
        response = self.get('/explorer')
        self.assertIn(
            '<a href="/modules/admin">Dashboard</a>', response.body)
        self.assertIn('Explore Courses', response.body)
        self.assertNotIn('My Courses', response.body)

    def test_anonymous_access(self):
        # check explorer pages are accessible
        accessibles = [
            '/explorer',
            '/explorer/assets/img/your_logo_here.png']
        for accessible in accessibles:
            response = self.get(accessible, expect_errors=True)
            self.assertEquals(response.status_int, 200)

        response = self.get('/')
        self.assertEquals(
            response.headers['Location'], 'http://localhost/explorer')

        response = self.get('/explorer')
        self.assertIn('Explore Courses', response.body)
        self.assertNotIn('My Courses', response.body)
        self.assertNotIn('Dashboard', response.body)


class CourseExplorerDisabledTest(actions.TestBase):
    """Tests when course explorer is disabled."""

    def get_auto_deploy(self):
        return False

    def test_anonymous_access(self):
        """Tests for disabled course explorer page."""
        # check root URL's properly redirect to login
        response = self.get('/')
        self.assertEquals(response.status_int, 302)
        self.assertIn('http://localhost/admin/welcome', response.location)

        # check course level assets are not accessible
        response = self.get(
            '/assets/img/your_logo_here.png', expect_errors=True)
        self.assertEquals(response.status_int, 404)

        # check explorer pages are not accessible
        not_accessibles = [
            '/explorer',
            '/explorer/assets/img/your_logo_here.png']
        for not_accessible in not_accessibles:
            response = self.get(not_accessible, expect_errors=True)
            self.assertEquals(response.status_int, 404)
