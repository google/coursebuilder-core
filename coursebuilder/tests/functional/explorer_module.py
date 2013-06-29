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
from models import models
from models import transforms
from models.models import PersonalProfile
from modules.course_explorer import course_explorer
from modules.course_explorer import student

import actions
from actions import assert_contains
from actions import assert_does_not_contain
from actions import assert_equals


class BaseExplorerTest(actions.TestBase):
    """Base class for testing explorer pages."""

    def setUp(self):  # pylint: disable-msg=g-bad-name
        super(BaseExplorerTest, self).setUp()
        config.Registry.test_overrides[
            models.CAN_SHARE_STUDENT_PROFILE.name] = True
        config.Registry.test_overrides[
            course_explorer.GCB_ENABLE_COURSE_EXPLORER_PAGE.name] = True

    def tearDown(self):  # pylint: disable-msg=g-bad-name
        config.Registry.test_overrides = {}
        super(BaseExplorerTest, self).tearDown()


class CourseExplorerTest(BaseExplorerTest):
    """Tests course_explorer module."""

    def test_single_uncompleted_course(self):
        """Tests for a single available course."""
        # This call should redirect to explorer page.
        response = self.get('/')
        assert_contains('/explorer', response.location)

        name = 'Test student courses page'
        email = 'Student'

        actions.login(email)

        # Test the explorer page.
        response = self.get('/explorer')
        assert_equals(response.status_int, 200)
        assert_contains('Register', response.body)

        # Navbar should not contain profile tab.
        assert_does_not_contain(
            '<a href="/explorer/profile">Profile</a>', response.body)

        # Test 'my courses' page when a student is not enrolled in any course.
        response = self.get('/explorer/courses')
        assert_equals(response.status_int, 200)
        assert_contains('You are not currently enrolled in any course',
                        response.body)

        # Test 'my courses' page when a student is enrolled in all courses.
        actions.register(self, name)
        response = self.get('/explorer/courses')
        assert_equals(response.status_int, 200)
        assert_contains('Go to course', response.body)
        assert_does_not_contain('You are not currently enrolled in any course',
                                response.body)

        # After the student registers for a course,
        # profile tab should be visible in navbar.
        assert_contains(
            '<a href="/explorer/profile">Profile</a>', response.body)

        # Test profile page.
        response = self.get('/explorer/profile')
        assert_contains('<td>%s</td>' % email, response.body)
        assert_contains('<td>%s</td>' % name, response.body)
        assert_contains('Progress', response.body)
        assert_does_not_contain('View score', response.body)

    def test_single_completed_course(self):
        """Tests when a single completed course is present."""
        email = 'test_assessments@google.com'
        name = 'Test Assessments'

        # Register.
        actions.login(email)
        actions.register(self, name)

        response = self.get('/explorer')
        # Before a course is not completed,
        # explorer page should not show 'view score' button.
        assert_does_not_contain('View score', response.body)

        # Assign a grade to the course enrolled to mark it complete.
        profile = PersonalProfile.get_by_key_name(email)
        info = {'final_grade': 'A'}
        course_info_dict = {'': info}
        profile.course_info = transforms.dumps(course_info_dict)
        profile.put()

        # Check if 'View score' text is visible on profile page.
        response = self.get('/explorer/profile')
        assert_contains('View score', response.body)

        # Check if 'Go to course' button is not visible on explorer page.
        response = self.get('/explorer')
        assert_does_not_contain('Go to course', response.body)

        # Check if 'View score' button is visible on explorer page.
        response = self.get('/explorer')
        assert_contains('View score', response.body)

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
        assert_contains('View course list', response.body)

        # Clean up app_context.
        sites.ApplicationContext.get_environ = get_environ_old
        sites.reset_courses()


class CourseExplorerDisabledTest(actions.TestBase):
    """Tests when course explorer is disabled."""

    def test_course_explorer_disabled(self):
        """Tests for disabled course explorer page."""
        # This call should redirect to course page not explorer page.
        response = self.get('/')
        assert_contains('/course', response.location)

        name = 'Test explorer page off'
        email = 'student'

        # Register
        actions.login(email)
        actions.register(self, name)

        response = self.get('/course')
        # 'My courses' and 'Profile' tab should not be present in tab bar.
        assert_does_not_contain('My Courses', response.body)
        assert_does_not_contain('Profile', response.body)


class GlobalProfileTest(BaseExplorerTest):
    """Tests course_explorer module."""

    def test_change_of_name(self):
        """Tests for a single available course."""
        # This call should redirect to explorer page.
        response = self.get('/')
        assert_contains('/explorer', response.location)

        name = 'Test global profile page'
        email = 'student_global_profile@example.com'

        actions.login(email)

        # Test the explorer page.
        response = self.get('/explorer')
        assert_equals(response.status_int, 200)
        assert_contains('Register', response.body)

        # Test 'my courses' page when a student is enrolled in all courses.
        actions.register(self, name)
        # Test profile page.
        response = self.get('/explorer/profile')
        assert_contains('<td>%s</td>' % email, response.body)
        assert_contains('<td>%s</td>' % name, response.body)

        # Change the name now
        new_name = 'New global name'
        response.form.set('name', new_name)
        response = self.submit(response.form)
        assert_equals(response.status_int, 302)
        response = self.get('/explorer/profile')
        assert_contains('<td>%s</td>' % email, response.body)
        assert_contains('<td>%s</td>' % new_name, response.body)

        # Change name with bad xsrf token.
        response = self.get('/explorer/profile')
        assert_equals(response.status_int, 200)
        new_name = 'New Bad global name'
        response.form.set('name', new_name)
        response.form.set('xsrf_token', 'asdfsdf')
        response = response.form.submit(expect_errors=True)
        assert_equals(response.status_int, 403)

        # Change name with empty name shold fail.
        response = self.get('/explorer/profile')
        assert_equals(response.status_int, 200)
        new_name = ''
        response.form.set('name', new_name)
        response = response.form.submit(expect_errors=True)
        assert_equals(response.status_int, 400)

        # Change name with overlong name should fail for str.
        response = self.get('/explorer/profile')
        assert_equals(response.status_int, 200)
        # Constant is module-protected. pylint: disable-msg=protected-access
        new_name = 'a' * (student._STRING_PROPERTY_MAX_BYTES + 1)
        response.form.set('name', new_name)
        response = response.form.submit(expect_errors=True)
        assert_equals(response.status_int, 400)

        # Change name with overlong name should fail for unicode.
        response = self.get('/explorer/profile')
        assert_equals(response.status_int, 200)
        # \u03a3 == Sigma. len == 1 for unicode; 2 for utf-8 encoded str.
        new_name = u'\u03a3' + ('a' * (student._STRING_PROPERTY_MAX_BYTES - 1))
        response.form.set('name', new_name)
        response = response.form.submit(expect_errors=True)
        assert_equals(response.status_int, 400)
