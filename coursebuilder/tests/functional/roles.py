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

import urllib

from common import crypto
from controllers import sites
from models import config
from models import roles
from models import transforms
from tests.functional import actions

COURSE_NAME = 'roles_test'
SUPER_ADMIN_EMAIL = 'super@foo.com'
SITE_ADMIN_EMAIL = 'site@foo.com'
COURSE_ADMIN_EMAIL = 'course@foo.como'
STUDENT_EMAIL = 'student@foo.com'
DUMMY_EMAIL = 'dummy@foo.com'


class RolesTest(actions.TestBase):

    _course_added = False
    _get_environ_old = None

    @classmethod
    def setUpClass(cls):
        sites.ApplicationContext.get_environ_old = (
            sites.ApplicationContext.get_environ)
        def get_environ_new(slf):
            environ = slf.get_environ_old()
            environ['course']['now_available'] = True
            environ['course'][roles.KEY_ADMIN_USER_EMAILS] = (
                '[%s]' % COURSE_ADMIN_EMAIL)
            return environ
        sites.ApplicationContext.get_environ = get_environ_new

    @classmethod
    def tearDownClass(cls):
        sites.ApplicationContext.get_environ = (
            sites.ApplicationContext.get_environ_old)

    def tearDown(self):
        super(RolesTest, self).tearDown()
        sites.reset_courses()
        RolesTest._roles = ''
        config.Registry.test_overrides.clear()

    def setUp(self):
        super(RolesTest, self).setUp()

        actions.login(COURSE_ADMIN_EMAIL, is_admin=True)
        payload_dict = {
            'name': COURSE_NAME,
            'title': 'Roles Test',
            'admin_email': COURSE_ADMIN_EMAIL}
        request = {
            'payload': transforms.dumps(payload_dict),
            'xsrf_token': crypto.XsrfTokenManager.create_xsrf_token(
                'add-course-put')}
        response = self.testapp.put('/rest/courses/item?%s' % urllib.urlencode(
            {'request': transforms.dumps(request)}), {})
        self.assertEquals(response.status_int, 200)
        sites.setup_courses('course:/%s::ns_%s, course:/:/' % (
                COURSE_NAME, COURSE_NAME))
        actions.logout()

        config.Registry.test_overrides[roles.GCB_ADMIN_LIST.name] = (
            '[%s]' % SITE_ADMIN_EMAIL)

    def _get_course(self):
        courses = sites.get_all_courses()
        for course in courses:
            if course.namespace == 'ns_' + COURSE_NAME:
                return course
        return None

    #----------------------------- Super admin tests
    def test_super_admin_when_super_admin(self):
        actions.login(SUPER_ADMIN_EMAIL, is_admin=True)
        self.assertTrue(roles.Roles.is_direct_super_admin())

    def test_super_admin_when_site_admin(self):
        actions.login(SUPER_ADMIN_EMAIL)
        self.assertFalse(roles.Roles.is_direct_super_admin())

    def test_super_admin_when_course_admin(self):
        actions.login(COURSE_ADMIN_EMAIL)
        self.assertFalse(roles.Roles.is_direct_super_admin())

    def test_super_admin_when_student(self):
        actions.login(STUDENT_EMAIL)
        self.assertFalse(roles.Roles.is_direct_super_admin())

    def test_super_admin_when_not_logged_in(self):
        self.assertFalse(roles.Roles.is_direct_super_admin())

    #----------------------------- Site admin tests
    def test_site_admin_when_super_admin(self):
        actions.login(SUPER_ADMIN_EMAIL, is_admin=True)
        self.assertTrue(roles.Roles.is_super_admin())

    def test_site_admin_when_site_admin(self):
        actions.login(SITE_ADMIN_EMAIL)
        self.assertTrue(roles.Roles.is_super_admin())

    def test_site_admin_when_course_admin(self):
        actions.login(COURSE_ADMIN_EMAIL)
        self.assertFalse(roles.Roles.is_super_admin())

    def test_site_admin_when_student(self):
        actions.login(STUDENT_EMAIL)
        self.assertFalse(roles.Roles.is_super_admin())

    def test_site_admin_when_not_logged_in(self):
        self.assertFalse(roles.Roles.is_super_admin())

    #----------------------------- Course admin tests
    def test_course_admin_when_super_admin(self):
        actions.login(SUPER_ADMIN_EMAIL, is_admin=True)
        self.assertTrue(roles.Roles.is_course_admin(self._get_course()))

    def test_course_admin_when_site_admin(self):
        actions.login(SITE_ADMIN_EMAIL, is_admin=True)
        self.assertTrue(roles.Roles.is_course_admin(self._get_course()))

    def test_course_admin_when_course_admin(self):
        actions.login(COURSE_ADMIN_EMAIL)
        self.assertTrue(roles.Roles.is_course_admin(self._get_course()))

    def test_course_admin_when_student(self):
        actions.login(STUDENT_EMAIL)
        self.assertFalse(roles.Roles.is_course_admin(self._get_course()))

    def test_course_admin_when_not_logged_in(self):
        self.assertFalse(roles.Roles.is_course_admin(self._get_course()))

    # --------------------------- Whitelisting tests:
    # See tests/functional/whitelist.py, which covers both the actual
    # role behavior as well as more-abstract can-you-see-the-resource
    # operations.
