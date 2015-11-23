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
from models import models
from models import transforms
from models.models import PersonalProfile
from modules.course_explorer import course_explorer
from modules.course_explorer import student
from tests.functional import actions


class BaseExplorerTest(actions.TestBase):
    """Base class for testing explorer pages."""

    def setUp(self):
        super(BaseExplorerTest, self).setUp()
        config.Registry.test_overrides[
            models.CAN_SHARE_STUDENT_PROFILE.name] = True
        config.Registry.test_overrides[
            course_explorer.GCB_ENABLE_COURSE_EXPLORER_PAGE.name] = True

    def tearDown(self):
        config.Registry.test_overrides = {}
        super(BaseExplorerTest, self).tearDown()


class CourseExplorerTest(BaseExplorerTest):
    """Tests course_explorer module."""

    def test_single_uncompleted_course(self):
        """Tests for a single available course."""
        # This call should redirect to explorer page.
        response = self.get('/')
        actions.assert_contains('/explorer', response.location)

        name = 'Test student courses page'
        email = 'Student'

        actions.login(email)

        # Test the explorer page.
        response = self.get('/explorer')
        actions.assert_equals(response.status_int, 200)
        actions.assert_contains('Register', response.body)

        # Navbar should not contain profile tab.
        actions.assert_does_not_contain(
            '<a href="/explorer/profile">Profile</a>', response.body)

        # Test 'my courses' page when a student is not enrolled in any course.
        response = self.get('/explorer/courses')
        actions.assert_equals(response.status_int, 200)
        actions.assert_contains('You are not currently enrolled in any course',
                        response.body)

        # Test 'my courses' page when a student is enrolled in all courses.
        actions.register(self, name)
        response = self.get('/explorer/courses')
        actions.assert_equals(response.status_int, 200)
        actions.assert_contains('Go to course', response.body)
        actions.assert_does_not_contain(
            'You are not currently enrolled in any course', response.body)

        # After the student registers for a course,
        # profile tab should be visible in navbar.
        actions.assert_contains(
            '<a href="/explorer/profile">Profile</a>', response.body)

        # Test profile page.
        response = self.get('/explorer/profile')
        actions.assert_contains('<td>%s</td>' % email, response.body)
        actions.assert_contains('<td>%s</td>' % name, response.body)
        actions.assert_contains('Progress', response.body)
        actions.assert_does_not_contain('View score', response.body)

    def test_single_completed_course(self):
        """Tests when a single completed course is present."""
        name = 'Test Assessments'

        # Register.
        user = actions.login('test_assessments@google.com')
        actions.register(self, name)

        response = self.get('/explorer')
        # Before a course is not completed,
        # explorer page should not show 'view score' button.
        actions.assert_does_not_contain('View score', response.body)

        # Assign a grade to the course enrolled to mark it complete.
        profile = PersonalProfile.get_by_key_name(user.user_id())
        info = {'final_grade': 'A'}
        course_info_dict = {'': info}
        profile.course_info = transforms.dumps(course_info_dict)
        profile.put()

        # Check if 'View score' text is visible on profile page.
        response = self.get('/explorer/profile')
        actions.assert_contains('View score', response.body)

        # Check if 'Go to course' button is not visible on explorer page.
        response = self.get('/explorer')
        actions.assert_does_not_contain('Go to course', response.body)

        # Check if 'View score' button is visible on explorer page.
        response = self.get('/explorer')
        actions.assert_contains('View score', response.body)

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
        response = self.get('/explorer/courses')
        # Assert if 'View course list' text is shown on my course page.
        actions.assert_contains('View course list', response.body)

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


class CourseExplorerDisabledTest(actions.TestBase):
    """Tests when course explorer is disabled."""

    def get_auto_deploy(self):
        return False

    def test_anonymous_access(self):
        """Tests for disabled course explorer page."""

        # disable the explorer
        config.Registry.test_overrides[
            course_explorer.GCB_ENABLE_COURSE_EXPLORER_PAGE.name] = False
        self.assertFalse(course_explorer.GCB_ENABLE_COURSE_EXPLORER_PAGE.value)

        # check root URL's properly redirect to login
        response = self.get('/')
        actions.assert_equals(response.status_int, 302)
        actions.assert_contains(
            'http://localhost/admin/welcome', response.location)

        # check course level assets are not accessible
        response = self.get(
            '/assets/img/your_logo_here.png', expect_errors=True)
        actions.assert_equals(response.status_int, 404)

        # check explorer pages are not accessible
        not_accessibles = [
            '/explorer',
            '/explorer/courses',
            '/explorer/profile',
            '/explorer/assets/img/your_logo_here.png']
        for not_accessible in not_accessibles:
            response = self.get(not_accessible, expect_errors=True)
            actions.assert_equals(response.status_int, 404)

        # enable course explorer
        config.Registry.test_overrides[
            course_explorer.GCB_ENABLE_COURSE_EXPLORER_PAGE.name] = True
        self.assertTrue(course_explorer.GCB_ENABLE_COURSE_EXPLORER_PAGE.value)

        # check explorer pages are accessible
        accessibles = [
            '/explorer',
            '/explorer/courses',
            '/explorer/assets/img/your_logo_here.png']
        for accessible in accessibles:
            response = self.get(accessible, expect_errors=True)
            actions.assert_equals(response.status_int, 200)

        # check student pages are not accessible
        response = self.get('/explorer/profile')
        actions.assert_equals(response.status_int, 302)
        self.assertEqual('http://localhost/explorer', response.location)

    def test_student_access(self):
        # enable course explorer
        config.Registry.test_overrides[
            course_explorer.GCB_ENABLE_COURSE_EXPLORER_PAGE.name] = True
        self.assertTrue(course_explorer.GCB_ENABLE_COURSE_EXPLORER_PAGE.value)

        # check not being logged in
        response = self.get('/explorer')
        actions.assert_contains('Explore Courses', response.body)
        actions.assert_does_not_contain('My Courses', response.body)
        actions.assert_does_not_contain('Dashboard', response.body)

        # login and check logged in student perspective
        config.Registry.test_overrides[
            sites.GCB_COURSES_CONFIG.name] = 'course:/:/'

        email = 'student'
        actions.login(email)
        response = self.get('/explorer')
        actions.assert_contains('Explore Courses', response.body)
        actions.assert_contains('My Courses', response.body)
        actions.assert_does_not_contain('Dashboard', response.body)

    def test_admin_access(self):
        # enable course explorer
        config.Registry.test_overrides[
            course_explorer.GCB_ENABLE_COURSE_EXPLORER_PAGE.name] = True
        self.assertTrue(course_explorer.GCB_ENABLE_COURSE_EXPLORER_PAGE.value)

        # check the admin site link
        actions.login('admin@test.foo', is_admin=True)
        response = self.get('/explorer')
        actions.assert_contains(
            '<a href="/modules/admin">Dashboard</a>', response.body)


class GlobalProfileTest(BaseExplorerTest):
    """Tests course_explorer module."""

    def test_change_of_name(self):
        """Tests for a single available course."""
        # This call should redirect to explorer page.
        response = self.get('/')
        actions.assert_contains('/explorer', response.location)

        name = 'Test global profile page'
        email = 'student_global_profile@example.com'

        actions.login(email)

        # Test the explorer page.
        response = self.get('/explorer')
        actions.assert_equals(response.status_int, 200)
        actions.assert_contains('Register', response.body)

        # Test 'my courses' page when a student is enrolled in all courses.
        actions.register(self, name)
        # Test profile page.
        response = self.get('/explorer/profile')
        actions.assert_contains('<td>%s</td>' % email, response.body)
        actions.assert_contains('<td>%s</td>' % name, response.body)

        # Change the name now
        new_name = 'New global name'
        response.form.set('name', new_name)
        response = self.submit(response.form)
        actions.assert_equals(response.status_int, 302)
        response = self.get('/explorer/profile')
        actions.assert_contains('<td>%s</td>' % email, response.body)
        actions.assert_contains('<td>%s</td>' % new_name, response.body)

        # Change name with bad xsrf token.
        response = self.get('/explorer/profile')
        actions.assert_equals(response.status_int, 200)
        new_name = 'New Bad global name'
        response.form.set('name', new_name)
        response.form.set('xsrf_token', 'asdfsdf')
        response = response.form.submit(expect_errors=True)
        actions.assert_equals(response.status_int, 403)

        # Change name with empty name shold fail.
        response = self.get('/explorer/profile')
        actions.assert_equals(response.status_int, 200)
        new_name = ''
        response.form.set('name', new_name)
        response = response.form.submit(expect_errors=True)
        actions.assert_equals(response.status_int, 400)

        # Change name with overlong name should fail for str.
        response = self.get('/explorer/profile')
        actions.assert_equals(response.status_int, 200)
        # Treat as module-protected. pylint: disable=protected-access
        new_name = 'a' * (student._STRING_PROPERTY_MAX_BYTES + 1)
        response.form.set('name', new_name)
        response = response.form.submit(expect_errors=True)
        actions.assert_equals(response.status_int, 400)

        # Change name with overlong name should fail for unicode.
        response = self.get('/explorer/profile')
        actions.assert_equals(response.status_int, 200)
        # \u03a3 == Sigma. len == 1 for unicode; 2 for utf-8 encoded str.
        # Treat as module-protected. pylint: disable=protected-access
        new_name = u'\u03a3' + ('a' * (student._STRING_PROPERTY_MAX_BYTES - 1))
        response.form.set('name', new_name)
        response = response.form.submit(expect_errors=True)
        actions.assert_equals(response.status_int, 400)
