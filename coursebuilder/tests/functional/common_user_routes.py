# Copyright 2016 Google Inc. All Rights Reserved.
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

"""Manages user-defined URL routing inside courses."""

__author__ = [
    'nretallack@google.com (Nick Retallack)',
]

from common import user_routes
from common import utils as common_utils
from controllers import utils
from tests.functional import actions


class TestUserRoutes(actions.TestBase):
    ADMIN_EMAIL = 'admin@example.com'
    STUDENT_EMAIL = 'student@example.com'
    COURSE_NAME = 'drive-course'

    # pylint: disable=no-self-argument
    def setUp(testcase):
        super(TestUserRoutes, testcase).setUp()

        testcase.times_routed = 0
        testcase.times_other_routed = 0

        class TestHandler(utils.CourseHandler):
            def get(handler):
                testcase.times_routed += 1
                handler.response.write('test response')

        user_routes.register_handler(
            TestHandler, 'test_handler', 'Test Handler')

        class OtherHandler(utils.CourseHandler):
            def get(handler):
                testcase.times_other_routed += 1
                handler.response.write('test response')

        user_routes.register_handler(
            OtherHandler, 'other_handler', 'Other Handler')

        actions.login(testcase.ADMIN_EMAIL, is_admin=True)
        testcase.app_context = actions.simple_add_course(
            testcase.COURSE_NAME, testcase.ADMIN_EMAIL, 'User Route Course')
        testcase.base = '/{}'.format(testcase.COURSE_NAME)
    # pylint: enable=no-self-argument

    def tearDown(self):
        del user_routes.USER_ROUTABLE_HANDLERS['test_handler']
        del user_routes.USER_ROUTABLE_HANDLERS['other_handler']

    def test_override_slash(self):
        # should give us the course page by default
        response = self.get('')
        self.assertEquals(self.times_routed, 0)
        self.assertEquals(response.status_code, 200)
        self.assertIn('drive-course', response.body)

        # override it
        with common_utils.Namespace(self.app_context.namespace):
            router = (
                user_routes.UserCourseRouteManager.from_current_appcontext())
            router.add('/', 'test_handler')
            router.save()

        # now it should be our custom handler
        response = self.get('')
        self.assertEquals(self.times_routed, 1)
        self.assertEquals(response.body, 'test response')

        # adding a slash should also work
        response = self.get('')
        self.assertEquals(self.times_routed, 2)
        self.assertEquals(response.body, 'test response')

    def test_normal_url(self):
        response = self.get('something', expect_errors=True)
        self.assertEquals(self.times_routed, 0)
        self.assertEquals(response.status_code, 404)

        with common_utils.Namespace(self.app_context.namespace):
            router = (
                user_routes.UserCourseRouteManager.from_current_appcontext())
            router.add('something', 'test_handler')
            router.save()

        response = self.get('something')
        self.assertEquals(self.times_routed, 1)
        self.assertEquals(response.body, 'test response')

        # Adding a trailing slash should work too
        response = self.get('something/')
        self.assertEquals(self.times_routed, 2)
        self.assertEquals(response.body, 'test response')

    def test_trailing_slash(self):
        response = self.get('something', expect_errors=True)
        self.assertEquals(self.times_routed, 0)
        self.assertEquals(response.status_code, 404)

        # Registering it this way should be no different, since it should be
        # normalized.
        with common_utils.Namespace(self.app_context.namespace):
            router = (
                user_routes.UserCourseRouteManager.from_current_appcontext())
            router.add('something/', 'test_handler')
            router.save()

        response = self.get('something')
        self.assertEquals(self.times_routed, 1)
        self.assertEquals(response.body, 'test response')

    def test_internal_slashes_allowed(self):
        response = self.get('one/two/three', expect_errors=True)
        self.assertEquals(self.times_routed, 0)
        self.assertEquals(response.status_code, 404)

        # It should allow slashes in the URL
        with common_utils.Namespace(self.app_context.namespace):
            router = (
                user_routes.UserCourseRouteManager.from_current_appcontext())
            router.add('one/two/three', 'test_handler')
            router.save()

        response = self.get('one/two/three')
        self.assertEquals(self.times_routed, 1)
        self.assertEquals(response.body, 'test response')

    def test_cant_override_reserved_url(self):
        with common_utils.Namespace(self.app_context.namespace):
            with self.assertRaises(user_routes.URLReservedError):
                router = (
                    user_routes.UserCourseRouteManager
                    .from_current_appcontext())
                router.add('course', 'test_handler')
                router.save()

    def test_cant_collide(self):
        with common_utils.Namespace(self.app_context.namespace):
            router = (
                user_routes.UserCourseRouteManager
                .from_current_appcontext())
            router.add('this', 'test_handler')
            router.save()

            with self.assertRaises(user_routes.URLTakenError):
                router = (
                    user_routes.UserCourseRouteManager
                    .from_current_appcontext())
                router.add('this', 'other_handler')
                router.save()

    def test_cant_collide_with_slash_variations(self):
        with common_utils.Namespace(self.app_context.namespace):
            router = (
                user_routes.UserCourseRouteManager
                .from_current_appcontext())
            router.add('/this', 'test_handler')
            router.save()

            with self.assertRaises(user_routes.URLTakenError):
                router = (
                    user_routes.UserCourseRouteManager
                    .from_current_appcontext())
                router.add('this/', 'other_handler')
                router.save()

    def test_normalize_path(self):
        pairs = (
            ('', '/'),
            ('/', '/'),
            ('foo', '/foo'),
            ('foo/', '/foo'),
            ('/foo/', '/foo'),
            ('/foo/bar/baz', '/foo/bar/baz'),
            ('/foo/../bar', '/foo/../bar'),
            ('/foo/./bar/', '/foo/./bar'),
        )

        for before, after in pairs:
            self.assertEqual(user_routes.normalize_path(before), after)

    def test_validate_path(self):
        # This path should be valid.
        user_routes.validate_path('/foo-bar/Baz.qux')

        # Fragment identifiers should never be valid
        with self.assertRaises(user_routes.URLInvalidError):
            user_routes.validate_path('/foo#bar')

        # Querystrings are not allowed either
        with self.assertRaises(user_routes.URLInvalidError):
            user_routes.validate_path('/foo?bar')
