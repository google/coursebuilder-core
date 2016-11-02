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

"""Collect sets of students into groups."""

__author__ = 'Mike Gainer (mgainer@google.com)'

import datetime
import logging
import urllib
import zlib

from common import crypto
from common import resource
from common import users
from common import utils as common_utils
from controllers import sites
from models import courses
from models.data_sources import paginated_table
from models import models
from models import transforms
from modules.analytics import gradebook
from modules.analytics import student_aggregate
from modules.courses import constants as course_constants
from modules.courses import triggers_tests
from modules.i18n_dashboard import i18n_dashboard
from modules.student_groups import messages
from modules.student_groups import student_groups
from tests.functional import actions

from google.appengine.api import namespace_manager

AvailabilityRestHandler = student_groups.StudentGroupAvailabilityRestHandler

class StudentGroupsTestBase(actions.TestBase):

    ADMIN_EMAIL = 'admin@example.com'
    ADMIN_ASSISTANT_EMAIL = 'Admin.Assistant@example.com'
    STUDENT_EMAIL = 'Student@Example.Com'

    COURSE_NAME = 'student_groups_test'
    COURSE_TITLE = 'Title'
    NAMESPACE = 'ns_%s' % COURSE_NAME

    def setUp(self):
        super(StudentGroupsTestBase, self).setUp()
        self.base = '/' + self.COURSE_NAME
        self.app_context = actions.simple_add_course(
            self.COURSE_NAME, self.ADMIN_EMAIL, self.COURSE_TITLE)
        self.STUDENT_LOWER = self.STUDENT_EMAIL.lower()

    def _grant_student_groups_permission_to_assistant(self):
        with common_utils.Namespace(self.NAMESPACE):
            role_dto = models.RoleDTO(None, {
                'name': 'modify_student_groups_role',
                'users': [self.ADMIN_ASSISTANT_EMAIL],
                'permissions': {
                    student_groups.MODULE_NAME:
                    [student_groups.EDIT_STUDENT_GROUPS_PERMISSION]
                    },
                })
            models.RoleDAO.save(role_dto)

    def _grant_availability_permission_to_assistant(self):
        with common_utils.Namespace(self.NAMESPACE):
            role_dto = models.RoleDTO(None, {
                'name': 'modify_availability_role',
                'users': [self.ADMIN_ASSISTANT_EMAIL],
                'permissions': {
                    course_constants.MODULE_NAME:
                    [course_constants.MODIFY_AVAILABILITY_PERMISSION]
                    },
                })
            models.RoleDAO.save(role_dto)


    def tearDown(self):
        sites.remove_course(self.app_context)
        super(StudentGroupsTestBase, self).tearDown()

    def _get_group(self, key):
        response = self.get(
            student_groups.StudentGroupRestHandler.URL.lstrip('/') +
            '?key=' + str(key))
        self.assertEquals(200, response.status_int)
        return transforms.loads(response.body)

    def _put_group(self, key, name, description, xsrf_token=None):
        if not xsrf_token:
            xsrf_token = crypto.XsrfTokenManager.create_xsrf_token(
                student_groups.StudentGroupRestHandler.ACTION)
        payload = {
            student_groups.StudentGroupDTO.NAME_PROPERTY: name,
            student_groups.StudentGroupDTO.DESCRIPTION_PROPERTY: description,
            }
        request = {
            'xsrf_token': xsrf_token,
            'key': str(key),
            'payload': transforms.dumps(payload),
            }

        response = self.put(
            student_groups.StudentGroupRestHandler.URL.lstrip('/'),
            {'request': transforms.dumps(request)})
        self.assertEquals(200, response.status_int)
        return transforms.loads(response.body)

    def _get_availability(self, key):
        response = self.get(
            AvailabilityRestHandler.URL.lstrip('/') + '?key=' + str(key))
        self.assertEquals(200, response.status_int)
        return transforms.loads(response.body)

    def _settings_with_defaults(self, default_availability,
                                course_availability, course_triggers,
                                element_settings, content_triggers):
        if not course_availability:
            course_availability = default_availability
        if course_triggers is None:
            course_triggers = {}
        if element_settings is None:
            element_settings = []
        if content_triggers is None:
            content_triggers = []
        settings = {
            AvailabilityRestHandler.COURSE_AVAILABILITY:
                course_availability,
            AvailabilityRestHandler._ELEMENT_SETTINGS:
                element_settings,
            student_groups.StudentGroupDTO.CONTENT_TRIGGERS_PROPERTY:
                content_triggers,
        }
        # course_triggers are merged into the `settings` dict because that
        # is how 'course_start' and 'course_end' actually appear in the form
        # data that this is simulating. This is in contrast to how the
        # triggers eventually end up, being transformed by from_payload()
        # into a single list value of a 'course_triggers' key for saving via
        # set_into_settings().
        settings.update(course_triggers)
        return settings

    def _put_availability(self, key, members, xsrf_token=None,
        course_availability=None, course_triggers=None,
        element_settings=None, content_triggers=None):

        if not xsrf_token:
            xsrf_token = crypto.XsrfTokenManager.create_xsrf_token(
                AvailabilityRestHandler.ACTION)

        group_settings = self._settings_with_defaults(
            student_groups.AVAILABILITY_NO_OVERRIDE,
            course_availability, course_triggers,
            element_settings, content_triggers)
        group_settings[AvailabilityRestHandler._MEMBERS] = '\n'.join(members)

        payload = {
            AvailabilityRestHandler._STUDENT_GROUP: key,
            AvailabilityRestHandler._STUDENT_GROUP_SETTINGS: group_settings,
        }
        request = {
            'xsrf_token': xsrf_token,
            'key': str(key),
            'payload': transforms.dumps(payload),
        }
        response = self.put(
            AvailabilityRestHandler.URL.lstrip('/'),
            {'request': transforms.dumps(request)})
        self.assertEquals(200, response.status_int)
        return transforms.loads(response.body)

    # The student_groups module hijacks the handler for availability
    # settings at the overall course level so that we can show course and
    # group level settings on the same page.  Verify that we pass through
    # and affect course level settings when we don't send a student_group
    # ID as part of the parameters.
    def _put_course_availability(self,
        course_availability=None, course_triggers=None,
        element_settings=None, content_triggers=None):

        xsrf_token = crypto.XsrfTokenManager.create_xsrf_token(
            AvailabilityRestHandler.ACTION)
        payload = self._settings_with_defaults(
            # This default is the most common value to appear in test cases.
            courses.COURSE_AVAILABILITY_REGISTRATION_REQUIRED,
            course_availability, course_triggers,
            element_settings, content_triggers)
        payload[AvailabilityRestHandler._STUDENT_GROUP] = ''
        request = {
            'xsrf_token': xsrf_token,
            'payload': transforms.dumps(payload),
            }
        response = self.put(
            AvailabilityRestHandler.URL.lstrip('/'),
            {'request': transforms.dumps(request)})
        self.assertEquals(200, response.status_int)
        return transforms.loads(response.body)

    def _delete_group(self, key, xsrf_token=None):
        if not xsrf_token:
            xsrf_token = crypto.XsrfTokenManager.create_xsrf_token(
                student_groups.StudentGroupRestHandler.ACTION)
        response = self.delete(
            student_groups.StudentGroupRestHandler.URL.lstrip('/') +
            '?%s' % urllib.urlencode({
                'key': str(key),
                'xsrf_token': xsrf_token,
                }))
        self.assertEquals(200, response.status_int)
        return transforms.loads(response.body)


class GroupLifecycleTests(StudentGroupsTestBase):

    def test_list_page_not_available_without_permission(self):
        actions.login(self.STUDENT_EMAIL)
        response = self.get('dashboard?action=%s' %
                            student_groups.StudentGroupListHandler.ACTION)
        self.assertEquals(302, response.status_int)
        self.assertEquals('http://localhost/' + self.COURSE_NAME,
                          response.location)

    def test_list_page_available_to_admin_assisstant(self):
        self._grant_student_groups_permission_to_assistant()
        actions.login(self.ADMIN_ASSISTANT_EMAIL)
        response = self.get('dashboard?action=%s' %
                            student_groups.StudentGroupListHandler.ACTION)
        self.assertEquals(200, response.status_int)
        self.assertIn(str(messages.STUDENT_GROUPS_DESCRIPTION), response.body)

    def test_list_page_with_no_groups(self):
        actions.login(self.ADMIN_EMAIL)
        response = self.get('dashboard?action=%s' %
                            student_groups.StudentGroupListHandler.ACTION)
        self.assertEquals(200, response.status_int)
        self.assertIn(str(messages.STUDENT_GROUPS_DESCRIPTION), response.body)
        self.assertIn('No items', response.body)

    def test_button_to_add_new_student_group(self):
        actions.login(self.ADMIN_EMAIL)
        response = self.get('dashboard?action=%s' %
                            student_groups.StudentGroupListHandler.ACTION)
        response = self.click(response, 'Add Group')
        self.assertEquals(200, response.status_int)
        self.assertIn(
            '<title>Course Builder &gt; Title &gt; Dashboard &gt; '
            'Edit Student Group</title>', response.body)

    def test_link_to_edit_existing_group(self):
        actions.login(self.ADMIN_EMAIL)
        self._put_group(None, 'My Test Group', 'this is my group')
        response = self.get('dashboard?action=%s' %
                            student_groups.StudentGroupListHandler.ACTION)
        response = self.click(response, 'My Test Group')
        self.assertEquals(200, response.status_int)
        self.assertIn(
            '<title>Course Builder &gt; Title &gt; Dashboard &gt; '
            'Edit Student Group</title>', response.body)

    def test_rest_not_available_without_permission(self):
        actions.login(self.STUDENT_EMAIL)
        response = self._get_group(12345)
        self.assertEquals(401, response['status'])
        self.assertEquals('Access denied.', response['message'])

        response = self._put_group(12345, 'Some Group', 'this is my group')
        self.assertEquals(401, response['status'])
        self.assertEquals('Access denied.', response['message'])

        response = self._delete_group(12345)
        self.assertEquals(401, response['status'])
        self.assertEquals('Access denied.', response['message'])

    def test_rest_with_permission(self):
        self._grant_student_groups_permission_to_assistant()
        actions.login(self.ADMIN_ASSISTANT_EMAIL)
        response = self._put_group(None, 'My New Group', 'this is my group')
        self.assertEquals(200, response['status'])
        self.assertEquals('Saved.', response['message'])
        payload = transforms.loads(response['payload'])
        group_id = payload['key']

        response = self._get_group(group_id)
        self.assertEquals(200, response['status'])
        self.assertEquals('OK.', response['message'])

        response = self._delete_group(group_id)
        self.assertEquals(200, response['status'])
        self.assertEquals('Deleted.', response['message'])

    def test_put_with_bad_xsrf_token(self):
        actions.login(self.ADMIN_EMAIL)
        response = self._put_group(None, 'My New Group', 'this is my group',
                                   'bad xsrf token')
        self.assertEquals(403, response['status'])
        self.assertEquals(
            'Bad XSRF token. Please reload the page and try again',
            response['message'])

    def test_delete_with_bad_xsrf_token(self):
        actions.login(self.ADMIN_EMAIL)
        response = self._delete_group(12345, 'bad xsrf token')
        self.assertEquals(403, response['status'])
        self.assertEquals(
            'Bad XSRF token. Please reload the page and try again',
            response['message'])

    def test_get_nonexistent_group(self):
        actions.login(self.ADMIN_EMAIL)
        response = self._get_group(1234)
        self.assertEquals(404, response['status'])
        self.assertEquals('Not found.', response['message'])

    def test_put_nonexistent_group(self):
        actions.login(self.ADMIN_EMAIL)
        response = self._put_group(1234, 'My Group', 'this is my group')
        self.assertEquals(404, response['status'])
        self.assertEquals('Not found.', response['message'])

    def test_delete_nonexistent_group(self):
        actions.login(self.ADMIN_EMAIL)
        response = self._delete_group(1234)
        self.assertEquals(200, response['status'])
        self.assertEquals('Deleted.', response['message'])

    def test_with_malformed_email(self):
        actions.login(self.ADMIN_EMAIL)
        response = self._put_group(None, 'My New Group', 'this is my group')
        group_id = transforms.loads(response['payload'])['key']

        response = self._put_availability(group_id, ['@domain.com'])
        self.assertEquals(400, response['status'])
        self.assertEquals(
            '"@domain.com" is not a valid email address.', response['message'])

        response = self._put_availability(group_id, ['@'])
        self.assertEquals(400, response['status'])
        self.assertEquals(
            '"@" is not a valid email address.', response['message'])

        response = self._put_availability(group_id, ['x@'])
        self.assertEquals(400, response['status'])
        self.assertEquals(
            '"x@" is not a valid email address.', response['message'])

    def test_lifecycle(self):
        actions.login(self.ADMIN_EMAIL)

        # Make new group.
        response = self._put_group(None, 'My New Group', 'this is my group')
        self.assertEquals(200, response['status'])
        self.assertEquals('Saved.', response['message'])
        payload = transforms.loads(response['payload'])
        group_id = payload['key']

        # Verify contents.
        response = self._get_group(group_id)
        self.assertEquals(200, response['status'])
        self.assertEquals('OK.', response['message'])
        payload = transforms.loads(response['payload'])
        self.assertEquals(
            'My New Group',
            payload[student_groups.StudentGroupDTO.NAME_PROPERTY])
        self.assertEquals(
            'this is my group',
            payload[student_groups.StudentGroupDTO.DESCRIPTION_PROPERTY])

        # Change all fields.
        response = self._put_group(group_id, 'New Name',
                                   'there are many like it')

        # Verify changes.
        response = self._get_group(group_id)
        self.assertEquals(200, response['status'])
        self.assertEquals('OK.', response['message'])
        payload = transforms.loads(response['payload'])
        self.assertEquals(
            'New Name',
            payload[student_groups.StudentGroupDTO.NAME_PROPERTY])
        self.assertEquals(
            'there are many like it',
            payload[student_groups.StudentGroupDTO.DESCRIPTION_PROPERTY])

        # Delete.
        response = self._delete_group(group_id)
        self.assertEquals(200, response['status'])
        self.assertEquals('Deleted.', response['message'])

        # Verify get returns not-found response now.
        response = self._get_group(group_id)
        self.assertEquals(404, response['status'])
        self.assertEquals('Not found.', response['message'])

    def test_add_too_many_groups(self):
        actions.login(self.ADMIN_EMAIL)

        for unused in xrange(
            student_groups.StudentGroupRestHandler.MAX_NUM_STUDENT_GROUPS):
            response = self._put_group(None, 'My New Group', 'this one is mine')
            self.assertEquals(response['status'], 200)
        # Save group ID of last group successfully added.
        group_id = transforms.loads(response['payload'])['key']

        # Verify that adding the next group fails.
        response = self._put_group(None, 'My New Group', 'this one is mine')
        self.assertEquals(response['status'], 403)
        self.assertEquals(
            response['message'],
            'Cannot create more groups; already have %s.' %
            student_groups.StudentGroupRestHandler.MAX_NUM_STUDENT_GROUPS)

        # Remove a pre-existing group and verify that we can now add another.
        self._delete_group(group_id)
        response = self._put_group(None, 'My New Group', 'this one is mine')
        self.assertEquals(response['status'], 200)
        self.assertEquals(response['message'], 'Saved.')

    def test_put_does_not_affect_sibling_groups(self):
        actions.login(self.ADMIN_EMAIL)

        response = self._put_group(None, 'Group One', 'group one')
        group_one_id = transforms.loads(response['payload'])['key']
        response = self._put_group(None, 'Group Two', 'group two')
        group_two_id = transforms.loads(response['payload'])['key']

        self._put_availability(group_one_id, ['Group.One@example.com'])
        self._put_availability(group_two_id, ['Group.Two@example.com'])

        response = self._get_availability(group_one_id)
        payload = transforms.loads(response['payload'])
        actual = payload[AvailabilityRestHandler._STUDENT_GROUP_SETTINGS][
            AvailabilityRestHandler._MEMBERS].split()
        group_one_email = 'Group.One@example.com'.lower()
        self.assertEquals([group_one_email], actual)


class UserIdLookupLifecycleTests(StudentGroupsTestBase):

    def test_immediate_removal(self):
        actions.login(self.ADMIN_EMAIL)
        response = self._put_group(None, 'My New Group', 'this is my group')
        group_id = transforms.loads(response['payload'])['key']
        self._put_availability(group_id, [self.STUDENT_EMAIL])

        with common_utils.Namespace(self.NAMESPACE):
            found_any = student_groups.EmailToObfuscatedUserId.all().get()
            self.assertIsNone(found_any)

    def test_cron_removal(self):
        # Add a row (and verify that it's there)
        actions.login(self.ADMIN_EMAIL)
        with common_utils.Namespace(self.NAMESPACE):
            student_groups.EmailToObfuscatedUserId(
                user=users.get_current_user()).put()
            found_any = student_groups.EmailToObfuscatedUserId.all().get()
            self.assertIsNotNone(found_any)

        # NOT in namespace, call cron cleanup handler.
        Cleanup = student_groups.EmailToObfuscatedUserIdCleanup
        try:
            tmp = Cleanup.MIN_AGE
            # Due to last_modified having a fractional seconds part and cutoff
            # only being in whole seconds, it can sometimes appear that
            # last_modified is later in the same whole second than cutoff
            # (whose truncated fractional seconds is zero).
            Cleanup.MIN_AGE = datetime.timedelta(seconds=-1)
            Cleanup._for_testing_only_get()
        finally:
            Cleanup.MIN_AGE = tmp

        # Verify row is now gone.
        with common_utils.Namespace(self.NAMESPACE):
            found_any = student_groups.EmailToObfuscatedUserId.all().get()
            self.assertIsNone(found_any)

    def test_cron_removal_with_no_work_to_do(self):
        # Just looking for no crashes.
        student_groups.EmailToObfuscatedUserIdCleanup._for_testing_only_get()


class UserIdentityTests(StudentGroupsTestBase):

    def test_add_group_then_register(self):
        actions.login(self.ADMIN_EMAIL)
        response = self._put_group(None, 'My New Group', 'this is my group')
        group_id = transforms.loads(response['payload'])['key']
        self._put_availability(group_id, [self.STUDENT_EMAIL])

        with common_utils.Namespace(self.NAMESPACE):
            membership = student_groups.StudentGroupMembership.all().get()
            self.assertEquals(self.STUDENT_LOWER, membership.key().name())
            self.assertEquals(group_id, membership.group_id)
            self.assertIsNone(models.Student.all().get())

        actions.login(self.STUDENT_EMAIL)
        actions.register(self, 'John Smith')

        with common_utils.Namespace(self.NAMESPACE):
            self.assertIsNone(student_groups.StudentGroupMembership.all().get())
            student = models.Student.all().get()
            self.assertEquals(self.STUDENT_LOWER, student.email)
            self.assertEquals(group_id, student.group_id)

    def test_register_then_add_group(self):
        actions.login(self.STUDENT_EMAIL)
        actions.register(self, 'John Smith')

        with common_utils.Namespace(self.NAMESPACE):
            self.assertIsNone(student_groups.StudentGroupMembership.all().get())
            student = models.Student.all().get()
            self.assertEquals(self.STUDENT_LOWER, student.email)
            self.assertIsNone(student.group_id)

        actions.login(self.ADMIN_EMAIL)
        response = self._put_group(None, 'My New Group', 'this is my group')
        group_id = transforms.loads(response['payload'])['key']
        self._put_availability(group_id, [self.STUDENT_EMAIL])

        with common_utils.Namespace(self.NAMESPACE):
            self.assertIsNone(student_groups.StudentGroupMembership.all().get())
            student = models.Student.all().get()
            self.assertEquals(self.STUDENT_LOWER, student.email)
            self.assertEquals(group_id, student.group_id)

    def test_add_group_then_register_mismatched_case(self):
        actions.login(self.ADMIN_EMAIL)
        response = self._put_group(None, 'My New Group', 'this is my group')
        group_id = transforms.loads(response['payload'])['key']
        self._put_availability(group_id, [self.STUDENT_EMAIL.upper()])

        actions.login(self.STUDENT_EMAIL.lower())
        actions.register(self, 'John Smith')
        with common_utils.Namespace(self.NAMESPACE):
            student = models.Student.all().get()
            self.assertEquals(self.STUDENT_EMAIL.lower(), student.email)
            self.assertEquals(group_id, student.group_id)

    def test_register_then_add_group_mismatched_case(self):
        actions.login(self.STUDENT_EMAIL.upper())
        actions.register(self, 'John Smith')

        actions.login(self.ADMIN_EMAIL)
        response = self._put_group(None, 'My New Group', 'this is my group')
        group_id = transforms.loads(response['payload'])['key']
        self._put_availability(group_id, [self.STUDENT_EMAIL])

        with common_utils.Namespace(self.NAMESPACE):
            self.assertIsNone(student_groups.StudentGroupMembership.all().get())
            student = models.Student.all().get()
            self.assertEquals(self.STUDENT_LOWER, student.email)
            self.assertEquals(group_id, student.group_id)


    def test_move_unregistered_student_to_new_group(self):
        actions.login(self.ADMIN_EMAIL)
        response = self._put_group(None, 'My New Group', 'this is my group')
        group_one_id = transforms.loads(response['payload'])['key']
        response = self._put_group(None, 'My New Group', 'this is my group')
        group_two_id = transforms.loads(response['payload'])['key']
        self._put_availability(group_one_id, [self.STUDENT_EMAIL])

        with common_utils.Namespace(self.NAMESPACE):
            membership = student_groups.StudentGroupMembership.all().get()
            self.assertEquals(self.STUDENT_LOWER, membership.key().name())
            self.assertEquals(group_one_id, membership.group_id)
            self.assertIsNone(models.Student.all().get())

        self._put_availability(group_two_id, [self.STUDENT_EMAIL])

        with common_utils.Namespace(self.NAMESPACE):
            membership = student_groups.StudentGroupMembership.all().get()
            self.assertEquals(self.STUDENT_LOWER, membership.key().name())
            self.assertEquals(group_two_id, membership.group_id)
            self.assertIsNone(models.Student.all().get())

    def test_move_registered_student_to_new_group(self):
        actions.login(self.STUDENT_EMAIL)
        actions.register(self, 'John Smith')

        actions.login(self.ADMIN_EMAIL)
        response = self._put_group(None, 'My New Group', 'this is my group')
        group_one_id = transforms.loads(response['payload'])['key']
        response = self._put_group(None, 'My New Group', 'this is my group')
        group_two_id = transforms.loads(response['payload'])['key']
        self._put_availability(group_one_id, [self.STUDENT_EMAIL])

        with common_utils.Namespace(self.NAMESPACE):
            self.assertIsNone(student_groups.StudentGroupMembership.all().get())
            student = models.Student.all().get()
            self.assertEquals(self.STUDENT_LOWER, student.email)
            self.assertEquals(group_one_id, student.group_id)

        self._put_availability(group_two_id, [self.STUDENT_EMAIL])

        with common_utils.Namespace(self.NAMESPACE):
            self.assertIsNone(student_groups.StudentGroupMembership.all().get())
            student = models.Student.all().get()
            self.assertEquals(self.STUDENT_LOWER, student.email)
            self.assertEquals(group_two_id, student.group_id)

    def test_move_unregistered_student_to_same_group(self):
        actions.login(self.ADMIN_EMAIL)
        response = self._put_group(None, 'My New Group', 'this is my group')
        group_one_id = transforms.loads(response['payload'])['key']
        response = self._put_group(None, 'My New Group', 'this is my group')
        group_two_id = transforms.loads(response['payload'])['key']
        self._put_availability(group_one_id, [self.STUDENT_EMAIL])

        with common_utils.Namespace(self.NAMESPACE):
            membership = student_groups.StudentGroupMembership.all().get()
            self.assertEquals(self.STUDENT_LOWER, membership.key().name())
            self.assertEquals(group_one_id, membership.group_id)
            self.assertIsNone(models.Student.all().get())

        self._put_availability(group_one_id, [self.STUDENT_EMAIL])

        with common_utils.Namespace(self.NAMESPACE):
            membership = student_groups.StudentGroupMembership.all().get()
            self.assertEquals(self.STUDENT_LOWER, membership.key().name())
            self.assertEquals(group_one_id, membership.group_id)
            self.assertIsNone(models.Student.all().get())

    def test_move_registered_student_to_same_group(self):
        actions.login(self.STUDENT_EMAIL)
        actions.register(self, 'John Smith')

        actions.login(self.ADMIN_EMAIL)
        response = self._put_group(None, 'My New Group', 'this is my group')
        group_one_id = transforms.loads(response['payload'])['key']
        response = self._put_group(None, 'My New Group', 'this is my group')
        group_two_id = transforms.loads(response['payload'])['key']
        self._put_availability(group_one_id, [self.STUDENT_EMAIL])

        with common_utils.Namespace(self.NAMESPACE):
            self.assertIsNone(student_groups.StudentGroupMembership.all().get())
            student = models.Student.all().get()
            self.assertEquals(self.STUDENT_LOWER, student.email)
            self.assertEquals(group_one_id, student.group_id)

        self._put_availability(group_one_id, [self.STUDENT_EMAIL])

        with common_utils.Namespace(self.NAMESPACE):
            self.assertIsNone(student_groups.StudentGroupMembership.all().get())
            student = models.Student.all().get()
            self.assertEquals(self.STUDENT_LOWER, student.email)
            self.assertEquals(group_one_id, student.group_id)

    def test_remove_unregistered_student_from_group(self):
        actions.login(self.ADMIN_EMAIL)
        response = self._put_group(None, 'My New Group', 'this is my group')
        group_id = transforms.loads(response['payload'])['key']
        self._put_availability(group_id, [self.STUDENT_EMAIL])

        with common_utils.Namespace(self.NAMESPACE):
            membership = student_groups.StudentGroupMembership.all().get()
            self.assertEquals(self.STUDENT_LOWER, membership.key().name())
            self.assertEquals(group_id, membership.group_id)
            self.assertIsNone(models.Student.all().get())

        self._put_availability(group_id, [])

        with common_utils.Namespace(self.NAMESPACE):
            self.assertIsNone(student_groups.StudentGroupMembership.all().get())
            self.assertIsNone(models.Student.all().get())

    def test_remove_registered_student_from_group(self):
        actions.login(self.STUDENT_EMAIL)
        actions.register(self, 'John Smith')

        actions.login(self.ADMIN_EMAIL)
        response = self._put_group(None, 'My New Group', 'this is my group')
        group_id = transforms.loads(response['payload'])['key']
        self._put_availability(group_id, [self.STUDENT_EMAIL])

        with common_utils.Namespace(self.NAMESPACE):
            self.assertIsNone(student_groups.StudentGroupMembership.all().get())
            student = models.Student.all().get()
            self.assertEquals(self.STUDENT_LOWER, student.email)
            self.assertEquals(group_id, student.group_id)

        self._put_availability(group_id, [])

        with common_utils.Namespace(self.NAMESPACE):
            self.assertIsNone(student_groups.StudentGroupMembership.all().get())
            student = models.Student.all().get()
            self.assertEquals(self.STUDENT_LOWER, student.email)
            self.assertIsNone(student.group_id)

    def test_in_group_user_signup_to_otherwise_private_course(self):
        actions.login(self.ADMIN_EMAIL)
        self._put_course_availability(
            course_availability=courses.COURSE_AVAILABILITY_PRIVATE)
        response = self._put_group(None, 'My New Group', 'this is my group')
        group_id = transforms.loads(response['payload'])['key']
        self._put_availability(
            group_id, [self.STUDENT_EMAIL], course_availability=(
                courses.COURSE_AVAILABILITY_REGISTRATION_REQUIRED))

        actions.login(self.STUDENT_EMAIL)
        response = self.get('register')
        register_form = actions.get_form_by_action(response, 'register')
        register_form.set('form01', 'John Smith')
        response = self.submit(register_form, response)
        self.assertEquals(302, response.status_int)
        self.assertEquals('http://localhost/student_groups_test/course'
                          '#registration_confirmation', response.location)
        response = self.get(response.location)

        # Here, if user group membership does not move transactionally with
        # Student creation, we'd expect a 404.  (b/27206132)
        self.assertEquals(200, response.status_int)
        self.assertIn('Thank you for registering for the course', response.body)


class AvailabilityLifecycleTests(StudentGroupsTestBase):

    def _group_for_email(self, email):
        with common_utils.Namespace(self.NAMESPACE):
            m = student_groups.StudentGroupMembership.get_by_key_name(email)
            return m.group_id if m else None

    def test_email_to_uid_conversion(self):
        pass

    def test_add_and_remove_student_in_group(self):
        actions.login(self.ADMIN_EMAIL)
        self.assertIsNone(self._group_for_email(self.ADMIN_EMAIL))
        self.assertIsNone(self._group_for_email(self.STUDENT_EMAIL))

        response = self._put_group(None, 'My New Group', 'this is my group')
        group_id = transforms.loads(response['payload'])['key']
        self._put_availability(
            group_id, [self.STUDENT_EMAIL, self.ADMIN_EMAIL])

        # Verify REST response
        response = self._get_availability(group_id)
        payload = transforms.loads(response['payload'])
        expected = set([self.STUDENT_LOWER, self.ADMIN_EMAIL.lower()])
        actual = set(payload[AvailabilityRestHandler._STUDENT_GROUP_SETTINGS][
            AvailabilityRestHandler._MEMBERS].split())
        self.assertEquals(expected, actual)

        # Verify via DB layer access.
        self.assertEquals(group_id, self._group_for_email(self.ADMIN_EMAIL))
        self.assertEquals(group_id, self._group_for_email(self.STUDENT_LOWER))

        # Remove admin from group
        self._put_availability(group_id, [self.STUDENT_EMAIL])

        # Verify REST response
        response = self._get_availability(group_id)
        payload = transforms.loads(response['payload'])
        expected = set([self.STUDENT_LOWER])
        actual = set(payload[AvailabilityRestHandler._STUDENT_GROUP_SETTINGS][
            AvailabilityRestHandler._MEMBERS].split())
        self.assertEquals(expected, actual)

        # Verify via DB layer access.
        self.assertEquals(group_id, self._group_for_email(self.STUDENT_LOWER))
        self.assertIsNone(self._group_for_email(self.ADMIN_EMAIL))

    def test_move_student_to_new_group(self):
        actions.login(self.ADMIN_EMAIL)

        self.assertIsNone(self._group_for_email(self.ADMIN_EMAIL))

        response = self._put_group(None, 'Group One', 'this is my group')
        group_one_id = transforms.loads(response['payload'])['key']
        self._put_availability(group_one_id, [self.ADMIN_EMAIL])
        self.assertEquals(group_one_id, self._group_for_email(self.ADMIN_EMAIL))

        response = self._put_group(None, 'Group Two', 'this is another group')
        group_two_id = transforms.loads(response['payload'])['key']
        self._put_availability(group_two_id, [self.ADMIN_EMAIL])
        self.assertEquals(group_two_id, self._group_for_email(self.ADMIN_EMAIL))

        # Also verify that we didn't just get lucky finding group two; check
        # that the count of records in StudentGroupMembership is exactly one.
        with common_utils.Namespace(self.NAMESPACE):
            records = list(student_groups.StudentGroupMembership.all().run())
            self.assertEquals(1, len(records))

    def test_remove_group_removes_group_membership(self):
        actions.login(self.ADMIN_EMAIL)

        self.assertIsNone(self._group_for_email(self.ADMIN_EMAIL))

        response = self._put_group(None, 'Group One', 'this is my group')
        group_id = transforms.loads(response['payload'])['key']
        self._put_availability(group_id, [self.ADMIN_EMAIL])
        self.assertEquals(group_id, self._group_for_email(self.ADMIN_EMAIL))

        self._delete_group(group_id)
        self.assertIsNone(self._group_for_email(self.ADMIN_EMAIL))

    def test_large_group_lifecycle(self):
        # Group operations with more than the number of entities that
        # can be handled in a single transaction.
        actions.login(self.ADMIN_EMAIL)

        # Add group w/ 50 members.
        emails = ['Test_User_%3.3d@example.com' % i for i in xrange(50)]
        response = self._put_group(None, 'Big Group', 'lots of students here')
        group_id = transforms.loads(response['payload'])['key']
        self._put_availability(group_id, emails)

        # Verify content.
        response = self._get_availability(group_id)
        payload = transforms.loads(response['payload'])
        email_text = payload[AvailabilityRestHandler._STUDENT_GROUP_SETTINGS][
            AvailabilityRestHandler._MEMBERS]
        fetched_emails = sorted(email_text.split('\n'))
        expected_emails = [email.lower() for email in emails]
        self.assertEquals(expected_emails, fetched_emails)

        # Change membership: Remove 250 users, add 250 new ones,
        # and leave 250 the same.
        emails = ['Test_User_%3.3d@example.com' % i for i in xrange(0, 100, 2)]
        response = self._put_availability(group_id, emails)

        # Verify content
        response = self._get_availability(group_id)
        payload = transforms.loads(response['payload'])
        email_text = payload[AvailabilityRestHandler._STUDENT_GROUP_SETTINGS][
            AvailabilityRestHandler._MEMBERS]
        fetched_emails = sorted(email_text.split('\n'))
        expected_emails = [email.lower() for email in emails]
        self.assertEquals(expected_emails, fetched_emails)

        # Delete group; verify.
        self._delete_group(group_id)
        response = self._get_group(group_id)
        self.assertEquals(404, response['status'])

        # All items should be gone from the DB.
        with common_utils.Namespace(self.NAMESPACE):
            self.assertIsNone(student_groups.StudentGroupMembership.all().get())
            self.assertIsNone(student_groups.StudentGroupEntity.all().get())

    def test_large_group_too_big(self):
        actions.login(self.ADMIN_EMAIL)

        # Add group w/ 50 members.
        emails = ['Test_User_%3.3d@example.com' % i for i in xrange(
            student_groups.StudentGroupAvailabilityRestHandler.MAX_NUM_MEMBERS
            + 1)]
        response = self._put_group(None, 'Big Group', 'lots of students')
        group_id = transforms.loads(response['payload'])['key']
        response = self._put_availability(group_id, emails)
        self.assertEquals(400, response['status'])
        self.assertEquals(
            'A group may contain at most %d members.' %
            student_groups.StudentGroupAvailabilityRestHandler.MAX_NUM_MEMBERS,
            response['message'])

        response = self._get_availability(group_id)
        payload = transforms.loads(response['payload'])
        email_text = payload[AvailabilityRestHandler._STUDENT_GROUP_SETTINGS][
            AvailabilityRestHandler._MEMBERS]
        self.assertEquals('', email_text)

    def test_availability_can_set_zero_members(self):
        actions.login(self.ADMIN_EMAIL)
        response = self._put_group(None, 'Big Group', 'lots of students')
        group_id = transforms.loads(response['payload'])['key']
        response = self._put_availability(group_id, [])
        self.assertEquals(200, response['status'])

    def test_course_availability_lifecycle(self):
        actions.login(self.ADMIN_EMAIL)
        response = self._put_group(None, 'Big Group', 'lots of students')
        group_id = transforms.loads(response['payload'])['key']

        # Verify default availability.
        response = self._get_availability(group_id)
        self.assertEquals(200, response['status'])
        self.assertEquals('OK.', response['message'])
        payload = transforms.loads(response['payload'])
        availability = payload[AvailabilityRestHandler._STUDENT_GROUP_SETTINGS][
            AvailabilityRestHandler.COURSE_AVAILABILITY]
        self.assertEquals(
            student_groups.AVAILABILITY_NO_OVERRIDE, availability)

        # Set availability to something non-default; verify.
        response = self._put_availability(group_id, [],
            course_availability=courses.AVAILABILITY_UNAVAILABLE)
        self.assertEquals(200, response['status'])
        self.assertEquals('Saved', response['message'])
        response = self._get_availability(group_id)
        self.assertEquals(200, response['status'])
        self.assertEquals('OK.', response['message'])
        payload = transforms.loads(response['payload'])
        availability = payload[AvailabilityRestHandler._STUDENT_GROUP_SETTINGS][
            AvailabilityRestHandler.COURSE_AVAILABILITY]
        self.assertEquals(courses.AVAILABILITY_UNAVAILABLE, availability)

        # Delete group; verify availability API responds with 404.
        self._delete_group(group_id)
        response = self._get_availability(group_id)
        self.assertEquals(404, response['status'])
        self.assertEquals('Not found.', response['message'])
        response = self._put_availability(group_id, [])
        self.assertEquals(404, response['status'])
        self.assertEquals('Not found.', response['message'])

    def test_component_availability_lifecycle(self):
        actions.login(self.ADMIN_EMAIL)

        # Add a unit and a lesson.
        course = courses.Course(None, app_context=self.app_context)
        unit = course.add_unit()
        unit.availability = courses.AVAILABILITY_COURSE
        lesson = course.add_lesson(unit)
        course.save()

        response = self._put_group(None, 'Big Group', 'lots of students')
        group_id = transforms.loads(response['payload'])['key']

        # Verify default availability
        response = self._get_availability(group_id)
        payload = transforms.loads(response['payload'])
        settings = payload[AvailabilityRestHandler._STUDENT_GROUP_SETTINGS][
            AvailabilityRestHandler._ELEMENT_SETTINGS]
        unit_settings = common_utils.find(
            lambda e: str(e['id']) == str(unit.unit_id), settings)
        lesson_settings = common_utils.find(
            lambda e: str(e['id']) == str(lesson.lesson_id), settings)

        # unit default availability
        self.assertEquals(
            student_groups.AVAILABILITY_NO_OVERRIDE,
            unit_settings['availability'])
        self.assertEquals(
            courses.AVAILABILITY_COURSE.title(),
            unit_settings[AvailabilityRestHandler._DEFAULT_AVAILABILITY])
        self.assertEquals(False, unit_settings['indent'])
        self.assertEquals('unit', unit_settings['type'])
        self.assertEquals('New Unit', unit_settings['name'])

        # lesson default availability
        self.assertEquals(student_groups.AVAILABILITY_NO_OVERRIDE,
                          lesson_settings['availability'])
        self.assertEquals(
            courses.AVAILABILITY_COURSE.title(),
            lesson_settings[AvailabilityRestHandler._DEFAULT_AVAILABILITY])
        self.assertEquals(True, lesson_settings['indent'])
        self.assertEquals('lesson', lesson_settings['type'])
        self.assertEquals('New Lesson', lesson_settings['name'])

        # Now, change underlying availability for unit and lesson.  Make unit
        # public and lesson private, so we can be sure these are independent
        # both of each other, and of our overrides.
        unit.availability = courses.AVAILABILITY_AVAILABLE
        lesson.availability = courses.AVAILABILITY_UNAVAILABLE
        course.save()
        response = self._get_availability(group_id)
        payload = transforms.loads(response['payload'])
        settings = payload[AvailabilityRestHandler._STUDENT_GROUP_SETTINGS][
            AvailabilityRestHandler._ELEMENT_SETTINGS]
        unit_settings = common_utils.find(
            lambda e: str(e['id']) == str(unit.unit_id), settings)
        lesson_settings = common_utils.find(
            lambda e: str(e['id']) == str(lesson.lesson_id), settings)

        self.assertEquals(student_groups.AVAILABILITY_NO_OVERRIDE,
                          unit_settings['availability'])
        self.assertEquals(
            courses.AVAILABILITY_AVAILABLE.title(),
            unit_settings[AvailabilityRestHandler._DEFAULT_AVAILABILITY])

        self.assertEquals(student_groups.AVAILABILITY_NO_OVERRIDE,
                          lesson_settings['availability'])
        self.assertEquals(
            courses.AVAILABILITY_UNAVAILABLE.title(),
            lesson_settings[AvailabilityRestHandler._DEFAULT_AVAILABILITY])

        # Set overrides at the group level to be opposite of the settings on
        # the base unit and lesson.
        response = self._put_availability(
            group_id, [], element_settings=[
             {'id': str(unit.unit_id),
              'type': 'unit',
              'availability': courses.AVAILABILITY_UNAVAILABLE},
             {'id': str(lesson.lesson_id),
              'type': 'lesson',
              'availability': courses.AVAILABILITY_AVAILABLE}])
        self.assertEquals(200, response['status'])
        response = self._get_availability(group_id)
        payload = transforms.loads(response['payload'])
        settings = payload[AvailabilityRestHandler._STUDENT_GROUP_SETTINGS][
            AvailabilityRestHandler._ELEMENT_SETTINGS]
        unit_settings = common_utils.find(
            lambda e: str(e['id']) == str(unit.unit_id), settings)
        lesson_settings = common_utils.find(
            lambda e: str(e['id']) == str(lesson.lesson_id), settings)

        self.assertEquals(
            courses.AVAILABILITY_UNAVAILABLE,
            unit_settings['availability'])
        self.assertEquals(
            courses.AVAILABILITY_AVAILABLE.title(),
            unit_settings[AvailabilityRestHandler._DEFAULT_AVAILABILITY])

        self.assertEquals(
            courses.AVAILABILITY_AVAILABLE,
            lesson_settings['availability'])
        self.assertEquals(
            courses.AVAILABILITY_UNAVAILABLE.title(),
            lesson_settings[AvailabilityRestHandler._DEFAULT_AVAILABILITY])

    def test_passthrough_to_course_settings_lifecycle(self):
        actions.login(self.ADMIN_EMAIL)

        # Add a unit and a lesson.
        course = courses.Course(None, app_context=self.app_context)
        unit = course.add_unit()
        unit.availability = courses.AVAILABILITY_COURSE
        lesson = course.add_lesson(unit)
        course.save()

        # NOTE: we add no groups, and we still expect passthrough to work.

        # Verify defaults.  (Well, not really default, but what we get when
        # setUp uses actions.simple_add_course() )
        response = self._get_availability('')
        self.assertEquals(200, response['status'])
        self.assertEquals('OK.', response['message'])
        payload = transforms.loads(response['payload'])
        self.assertEquals(
            payload['course_availability'],
            courses.COURSE_AVAILABILITY_REGISTRATION_OPTIONAL)
        settings = payload['element_settings']
        unit_settings = common_utils.find(
            lambda e: str(e['id']) == str(unit.unit_id), settings)
        lesson_settings = common_utils.find(
            lambda e: str(e['id']) == str(lesson.lesson_id), settings)
        self.assertEquals(
            courses.AVAILABILITY_COURSE, unit_settings['availability'])
        self.assertEquals(
            courses.AVAILABILITY_COURSE, lesson_settings['availability'])

        # Set to non-default; verify.
        self._put_course_availability(
            element_settings=[
             {'id': str(unit.unit_id),
              'type': 'unit',
              'availability': courses.AVAILABILITY_UNAVAILABLE},
             {'id': str(lesson.lesson_id),
              'type': 'lesson',
              'availability': courses.AVAILABILITY_AVAILABLE}])

        response = self._get_availability('')
        self.assertEquals(200, response['status'])
        self.assertEquals('OK.', response['message'])
        payload = transforms.loads(response['payload'])
        self.assertEquals(
            payload['course_availability'],
            courses.COURSE_AVAILABILITY_REGISTRATION_REQUIRED)
        settings = payload['element_settings']
        unit_settings = common_utils.find(
            lambda e: str(e['id']) == str(unit.unit_id), settings)
        lesson_settings = common_utils.find(
            lambda e: str(e['id']) == str(lesson.lesson_id), settings)
        self.assertEquals(
            courses.AVAILABILITY_UNAVAILABLE, unit_settings['availability'])
        self.assertEquals(
            courses.AVAILABILITY_AVAILABLE, lesson_settings['availability'])

    def test_set_availability_bad_xsrf_token(self):
        actions.login(self.ADMIN_EMAIL)
        response = self._put_group(None, 'Group One', 'this is my group')
        group_id = transforms.loads(response['payload'])['key']
        response = self._put_availability(
            group_id, [], xsrf_token='not a valid XSRF token')
        self.assertEquals(403, response['status'])
        self.assertEquals(
            'Bad XSRF token. Please reload the page and try again',
            response['message'])

    def test_set_availability_non_admin_with_no_permission(self):
        actions.login(self.ADMIN_EMAIL)
        response = self._put_group(None, 'Group One', 'this is my group')
        group_id = transforms.loads(response['payload'])['key']

        actions.login(self.ADMIN_ASSISTANT_EMAIL)
        response = self._put_availability(group_id, [])
        self.assertEquals(401, response['status'])
        self.assertEquals('Access denied.', response['message'])

    def test_set_availability_non_admin_with_permission(self):
        actions.login(self.ADMIN_EMAIL)
        response = self._put_group(None, 'Group One', 'this is my group')
        group_id = transforms.loads(response['payload'])['key']
        self._grant_student_groups_permission_to_assistant()

        actions.login(self.ADMIN_ASSISTANT_EMAIL)
        response = self._put_availability(group_id, [])
        self.assertEquals(200, response['status'])
        self.assertEquals('Saved', response['message'])

    def test_get_course_whitelist_non_admin_shows_actual_whitelist(self):
        actions.login(self.ADMIN_EMAIL)
        response = self._put_group(None, 'Group One', 'this is my group')
        group_id = transforms.loads(response['payload'])['key']
        self._put_availability(
            group_id, [self.ADMIN_EMAIL, self.ADMIN_ASSISTANT_EMAIL])
        self._grant_student_groups_permission_to_assistant()
        self._grant_availability_permission_to_assistant()

        url = student_groups.StudentGroupAvailabilityRestHandler.URL.lstrip('/')
        with actions.OverriddenEnvironment(
            {'course': {'whitelist': 'FAKE CONTENT'}}):

            response = self.get(url)
            payload = transforms.loads(
                transforms.loads(response.body)['payload'])
            self.assertEquals(payload['whitelist'], 'FAKE CONTENT')

            actions.login(self.ADMIN_ASSISTANT_EMAIL)
            response = self.get(url)
            payload = transforms.loads(
                transforms.loads(response.body)['payload'])
            self.assertEquals(payload['whitelist'], 'FAKE CONTENT')



class AvailabilityTests(StudentGroupsTestBase):

    COURSE_URL = 'http://localhost/%s/' % StudentGroupsTestBase.COURSE_NAME
    SYLLABUS_URL = COURSE_URL + 'course'
    LESSON_ONE_URL = COURSE_URL + 'unit?unit=1&lesson=2'
    LESSON_TWO_URL = COURSE_URL + 'unit?unit=3&lesson=4'

    IN_GROUP_STUDENT_EMAIL = 'In_Group@example.com'
    NON_GROUP_STUDENT_EMAIL = 'Hoi_Polloi@example.com'

    def setUp(self):
        super(AvailabilityTests, self).setUp()
        self.course = courses.Course(None, app_context=self.app_context)
        self.unit_one = self.course.add_unit()
        self.unit_one.availability = courses.AVAILABILITY_COURSE
        self.lesson_one = self.course.add_lesson(self.unit_one)
        self.unit_two = self.course.add_unit()
        self.unit_two.availability = courses.AVAILABILITY_COURSE
        self.lesson_two = self.course.add_lesson(self.unit_two)
        self.course.save()

        actions.login(self.ADMIN_EMAIL)
        response = self._put_group(None, 'Group One', 'this is my group')
        self.group_id = transforms.loads(response['payload'])['key']
        self._put_availability(self.group_id, [self.IN_GROUP_STUDENT_EMAIL])

    def test_group_creation_defaults_pass_through_to_course(self):
        actions.login(self.IN_GROUP_STUDENT_EMAIL)

        # Verify accessibility to non-logged-in user.
        response = self.get(self.SYLLABUS_URL)
        self.assertEquals(response.status_int, 200)
        response = self.get(self.LESSON_ONE_URL)
        self.assertEquals(response.status_int, 200)
        response = self.get(self.LESSON_TWO_URL)
        self.assertEquals(response.status_int, 200)

        # Change course accessibility to require login; verify non-access.
        # Despite being in group with default settings, course-level settings
        # still show through.
        # Set to non-default; verify.
        actions.login(self.ADMIN_EMAIL)
        self._put_course_availability()
        actions.login(self.IN_GROUP_STUDENT_EMAIL)
        response = self.get(self.SYLLABUS_URL)
        self.assertEquals(response.status_int, 200)
        response = self.get(self.LESSON_ONE_URL)
        self.assertEquals(response.status_int, 302)
        self.assertEquals(response.location, self.SYLLABUS_URL)
        response = self.get(self.LESSON_TWO_URL)
        self.assertEquals(response.status_int, 302)
        self.assertEquals(response.location, self.SYLLABUS_URL)

        # Register, should now be able to access.
        actions.register(self, 'John Smith')
        response = self.get(self.SYLLABUS_URL)
        self.assertEquals(response.status_int, 200)
        response = self.get(self.LESSON_ONE_URL)
        self.assertEquals(response.status_int, 200)
        response = self.get(self.LESSON_TWO_URL)
        self.assertEquals(response.status_int, 200)

        # Set course-level access on unit two, lesson two to private.
        actions.login(self.ADMIN_EMAIL)
        self._put_course_availability(
            element_settings=[
             {'id': str(self.unit_two.unit_id),
              'type': 'unit',
              'availability': courses.AVAILABILITY_UNAVAILABLE},
             {'id': str(self.lesson_two.lesson_id),
              'type': 'lesson',
              'availability': courses.AVAILABILITY_UNAVAILABLE}])

        actions.login(self.IN_GROUP_STUDENT_EMAIL)
        response = self.get(self.SYLLABUS_URL)
        self.assertEquals(response.status_int, 200)
        response = self.get(self.LESSON_ONE_URL)
        self.assertEquals(response.status_int, 200)
        response = self.get(self.LESSON_TWO_URL)
        self.assertEquals(response.status_int, 302)
        self.assertEquals(response.location, self.SYLLABUS_URL)

    def test_group_member_versus_nonmember(self):
        # Most-commonly expected use case.  Here, we're just verifying that
        # in-group users get different settings than non-group users, not
        # exhaustively verifying override properties: Make unit two generally
        # unavailable, but available to group members.
        self._put_course_availability(
            element_settings=[
             {'id': str(self.unit_two.unit_id),
              'type': 'unit',
              'availability': courses.AVAILABILITY_UNAVAILABLE},
             {'id': str(self.lesson_two.lesson_id),
              'type': 'lesson',
              'availability': courses.AVAILABILITY_UNAVAILABLE}])
        self._put_availability(
            self.group_id, [self.IN_GROUP_STUDENT_EMAIL],
            element_settings=[
             {'id': str(self.unit_two.unit_id),
              'type': 'unit',
              'availability': courses.AVAILABILITY_AVAILABLE},
             {'id': str(self.lesson_two.lesson_id),
              'type': 'lesson',
              'availability': courses.AVAILABILITY_AVAILABLE}])

        actions.login(self.IN_GROUP_STUDENT_EMAIL)
        actions.register(self, 'John Smith')
        response = self.get(self.LESSON_ONE_URL)
        self.assertEquals(response.status_int, 200)
        response = self.get(self.LESSON_TWO_URL)
        self.assertEquals(response.status_int, 200)

        actions.login(self.NON_GROUP_STUDENT_EMAIL)
        actions.register(self, 'Jane Smith')
        response = self.get(self.LESSON_ONE_URL)
        self.assertEquals(response.status_int, 200)
        response = self.get(self.LESSON_TWO_URL)
        self.assertEquals(response.status_int, 302)

    def test_course_availability_overrides(self):
        # Register normal student before we make the course private.
        actions.login(self.NON_GROUP_STUDENT_EMAIL)
        actions.register(self, 'Jane Smith')

        # Make course setting say absolutely no-one can see anything.
        actions.login(self.ADMIN_EMAIL)
        self._put_course_availability(
            course_availability=courses.COURSE_AVAILABILITY_PRIVATE)

        # Verify that a logged-in, registered (how?) student can not even
        # see the syllabus.
        actions.login(self.NON_GROUP_STUDENT_EMAIL)
        response = self.get(self.SYLLABUS_URL, expect_errors=True)
        self.assertEquals(response.status_int, 404)
        response = self.get(self.LESSON_ONE_URL, expect_errors=True)
        self.assertEquals(response.status_int, 404)

        # Admin adds group, and student to group.
        actions.login(self.ADMIN_EMAIL)
        response = self._put_group(None, 'My New Group', 'this is my group')
        group_id = transforms.loads(response['payload'])['key']
        self._put_availability(group_id, [self.STUDENT_EMAIL],
            course_availability=(
                courses.COURSE_AVAILABILITY_REGISTRATION_REQUIRED))

        # As student in group, login.  Should be able to see syllabus, but
        # not lesson since not yet registered.
        actions.login(self.STUDENT_EMAIL)
        response = self.get(self.SYLLABUS_URL, expect_errors=True)
        self.assertEquals(response.status_int, 200)
        response = self.get(self.LESSON_ONE_URL, expect_errors=True)
        self.assertEquals(response.status_int, 302)

        # Register; verify that override to reg-required and satisfying the
        # condition allows us to see course content, not just syllabus.
        actions.register(self, 'John Smith')
        response = self.get(self.LESSON_ONE_URL, expect_errors=True)
        self.assertEquals(response.status_int, 200)

    def test_unit_and_lesson_availability_overrides(self):
        self._put_course_availability(
            element_settings=[
             {'id': str(self.unit_one.unit_id),
              'type': 'unit',
              'availability': courses.AVAILABILITY_UNAVAILABLE},
             {'id': str(self.lesson_one.lesson_id),
              'type': 'lesson',
              'availability': courses.AVAILABILITY_UNAVAILABLE},
             {'id': str(self.unit_two.unit_id),
              'type': 'unit',
              'availability': courses.AVAILABILITY_UNAVAILABLE},
             {'id': str(self.lesson_two.lesson_id),
              'type': 'lesson',
              'availability': courses.AVAILABILITY_UNAVAILABLE}])

        response = self._put_group(None, 'My New Group', 'this is my group')
        group_id = transforms.loads(response['payload'])['key']
        self._put_availability(
            group_id, [self.STUDENT_EMAIL],
            element_settings=[
             {'id': str(self.unit_one.unit_id),
              'type': 'unit',
              'availability': courses.AVAILABILITY_COURSE},
             {'id': str(self.lesson_one.lesson_id),
              'type': 'lesson',
              'availability': courses.AVAILABILITY_COURSE},
             {'id': str(self.unit_two.unit_id),
              'type': 'unit',
              'availability': courses.AVAILABILITY_AVAILABLE},
             {'id': str(self.lesson_two.lesson_id),
              'type': 'lesson',
              'availability': courses.AVAILABILITY_AVAILABLE}])

        # No course-level override from group, so we should see the
        # reg-required from the base course.  Both lessons marked
        # private in base course, so here we mark one public, and
        # one 'course', so one should be available w/o registration.
        actions.login(self.STUDENT_EMAIL)
        response = self.get(self.SYLLABUS_URL, expect_errors=True)
        self.assertEquals(response.status_int, 200)
        response = self.get(self.LESSON_ONE_URL, expect_errors=True)
        self.assertEquals(response.status_int, 302)
        response = self.get(self.LESSON_TWO_URL, expect_errors=True)
        self.assertEquals(response.status_int, 200)

        # Register; now lesson-one should also be available.
        actions.register(self, 'John Smith')
        response = self.get(self.LESSON_ONE_URL, expect_errors=True)
        self.assertEquals(response.status_int, 200)

    def test_course_and_element_overrides_combined(self):
        self._put_course_availability(
            course_availability=courses.COURSE_AVAILABILITY_PRIVATE,
            element_settings=[{'id': str(self.unit_one.unit_id),
              'type': 'unit',
              'availability': courses.AVAILABILITY_UNAVAILABLE},
             {'id': str(self.lesson_one.lesson_id),
              'type': 'lesson',
              'availability': courses.AVAILABILITY_UNAVAILABLE},
             {'id': str(self.unit_two.unit_id),
              'type': 'unit',
              'availability': courses.AVAILABILITY_UNAVAILABLE},
             {'id': str(self.lesson_two.lesson_id),
              'type': 'lesson',
              'availability': courses.AVAILABILITY_UNAVAILABLE}])

        response = self._put_group(None, 'My New Group', 'this is my group')
        group_id = transforms.loads(response['payload'])['key']
        self._put_availability(
            group_id, [self.STUDENT_EMAIL], course_availability=(
                courses.COURSE_AVAILABILITY_REGISTRATION_REQUIRED),
            element_settings=[
             {'id': str(self.unit_one.unit_id),
              'type': 'unit',
              'availability': courses.AVAILABILITY_COURSE},
             {'id': str(self.lesson_one.lesson_id),
              'type': 'lesson',
              'availability': courses.AVAILABILITY_COURSE},
             {'id': str(self.unit_two.unit_id),
              'type': 'unit',
              'availability': courses.AVAILABILITY_AVAILABLE},
             {'id': str(self.lesson_two.lesson_id),
              'type': 'lesson',
              'availability': courses.AVAILABILITY_AVAILABLE}])

        # No course-level override from group, so we should see the
        # reg-required from the base course.  Both lessons marked
        # private in base course, so here we mark one public, and
        # one 'course', so one should be available w/o registration.
        actions.login(self.STUDENT_EMAIL)
        response = self.get(self.SYLLABUS_URL, expect_errors=True)
        self.assertEquals(response.status_int, 200)
        response = self.get(self.LESSON_ONE_URL, expect_errors=True)
        self.assertEquals(response.status_int, 302)
        response = self.get(self.LESSON_TWO_URL, expect_errors=True)
        self.assertEquals(response.status_int, 200)

        # Register; now lesson-one should also be available.
        actions.register(self, 'John Smith')

        response = self.get(self.LESSON_ONE_URL, expect_errors=True)
        self.assertEquals(response.status_int, 200)


class I18nTests(StudentGroupsTestBase):

    COURSE_URL = 'http://localhost/%s/' % StudentGroupsTestBase.COURSE_NAME
    PROFILE_URL = COURSE_URL + 'student/home'
    TRANSLATE_URL = (COURSE_URL.rstrip('/') +
                     i18n_dashboard.TranslationConsoleRestHandler.URL)
    LOCALE = 'de'

    def setUp(self):
        super(I18nTests, self).setUp()

        # Add setting for additional language.
        actions.update_course_config(
            self.COURSE_NAME,
            {'extra_locales': [
                {'locale': self.LOCALE, 'availability': 'available'}]})

        actions.login(self.STUDENT_EMAIL)
        actions.register(self, 'John Smith')

        with common_utils.Namespace(self.NAMESPACE):
            prefs = models.StudentPreferencesDAO.load_or_default()
            prefs.locale = self.LOCALE
            models.StudentPreferencesDAO.save(prefs)

    def _put_translation(self, key, name, description):
        key = '%s:%s' % (str(key), self.LOCALE)
        payload = {
            'title': 'unused',
            'key': key,
            'source_locale': 'en_US',
            'target_locale': self.LOCALE,
            'sections': [
                {
                    'name': student_groups.StudentGroupDTO.NAME_PROPERTY,
                    'label': 'Name',
                    'type': 'string',
                    'source_value': '',
                    'data': [
                        {
                            'source_value': 'My New Group',
                            'target_value': name,
                            'verb': 1,
                            'old_source_value': '',
                            'changed': True
                            }]},
                {
                    'name': student_groups.StudentGroupDTO.DESCRIPTION_PROPERTY,
                    'label': 'Description',
                    'type': 'text',
                    'source_value': '',
                    'data': [
                        {
                            'source_value': 'this is my group',
                            'target_value': description,
                            'verb': 1,
                            'old_source_value': '',
                            'changed': True
                            }]},

            ],
            }
        request_dict = {
            'key': key,
            'xsrf_token': crypto.XsrfTokenManager.create_xsrf_token(
                i18n_dashboard.TranslationConsoleRestHandler.XSRF_TOKEN_NAME),
            'payload': transforms.dumps(payload),
            'validate': False}
        response = self.put(
            self.TRANSLATE_URL, {'request': transforms.dumps(request_dict)})
        response = transforms.loads(response.body)
        self.assertEquals(200, response['status'])
        self.assertEquals('Saved.', response['message'])

    def _verify_progress(self, key, expected_status):
        with common_utils.Namespace(self.NAMESPACE):
            progress_dto = i18n_dashboard.I18nProgressDAO.load(str(key))
            self.assertEquals(expected_status,
                              progress_dto.get_progress(self.LOCALE))

    def test_translation_event_flow(self):
        actions.login(self.ADMIN_EMAIL)
        response = self._put_group(None, 'My New Group', 'this is my group')
        group_id = transforms.loads(response['payload'])['key']

        # Verify that saving the student group DAO implicitly starts a job
        # to buff up I18N progress.
        key = resource.Key(student_groups.ResourceHandlerStudentGroup.TYPE,
                           group_id)
        self.execute_all_deferred_tasks()
        self._verify_progress(key, i18n_dashboard.I18nProgressDTO.NOT_STARTED)

        # Provide a translation; verify state change.
        self._put_translation(key, 'MY NEW GROUP', 'THIS IS MY GROUP')
        self.execute_all_deferred_tasks()
        self._verify_progress(key, i18n_dashboard.I18nProgressDTO.DONE)

        # Now, change the original group and save; verify that we notice
        # the change via the progress changing from DONE to IN_PROGRESS.
        self._put_group(group_id, 'A New Name', 'a new description')
        self.execute_all_deferred_tasks()
        self._verify_progress(key, i18n_dashboard.I18nProgressDTO.IN_PROGRESS)

    def _verify_profile_content(self, expected_name, expected_description):
        response = self.get(self.PROFILE_URL)
        soup = self.parse_html_string_to_soup(response.body)
        name_p = soup.select('#student-group-name')
        description_p = soup.select('#student-group-description')
        if expected_name is None:
            self.assertEquals([], name_p)
        else:
            self.assertEquals(expected_name, name_p[0].text)
        if expected_description is None:
            self.assertEquals([], description_p)
        else:
            self.assertEquals(expected_description, description_p[0].text)

    def test_profile_with_translations(self):
        # No group -> No group content on profile page.
        actions.login(self.STUDENT_EMAIL)
        self._verify_profile_content(None, None)

        # Group exists, but student not in group -> No group content on profile
        actions.login(self.ADMIN_EMAIL)
        response = self._put_group(None, 'My New Group', 'this is my group')
        group_id = transforms.loads(response['payload'])['key']
        self.execute_all_deferred_tasks()

        actions.login(self.STUDENT_EMAIL)
        self._verify_profile_content(None, None)

        # Student in group sees name/descr.  No translations yet, so sees
        # untranslated (lowercase) version.
        actions.login(self.ADMIN_EMAIL)
        self._put_availability(group_id, [self.STUDENT_EMAIL])
        self.execute_all_deferred_tasks()

        actions.login(self.STUDENT_EMAIL)
        self._verify_profile_content('My New Group', 'this is my group')

        # Provide a translation; verify state change.
        actions.login(self.ADMIN_EMAIL)
        key = resource.Key(student_groups.ResourceHandlerStudentGroup.TYPE,
                           group_id)
        self._put_translation(key, 'MY NEW GROUP', 'THIS IS MY GROUP')
        self.execute_all_deferred_tasks()

        actions.login(self.STUDENT_EMAIL)
        self._verify_profile_content('MY NEW GROUP', 'THIS IS MY GROUP')

    def test_i18n_title(self):
        actions.login(self.ADMIN_EMAIL)
        response = self._put_group(None, 'My New Group', 'this is my group')
        group_id = transforms.loads(response['payload'])['key']
        self._put_availability(group_id, [self.STUDENT_EMAIL])
        self.execute_all_deferred_tasks()
        key = resource.Key(student_groups.ResourceHandlerStudentGroup.TYPE,
                           group_id)
        self._put_translation(key, 'MY NEW GROUP', 'THIS IS MY GROUP')
        self.execute_all_deferred_tasks()

        actions.login(self.STUDENT_EMAIL)

        # Verify that one-off title translation also works.
        try:
            sites.set_path_info('/' + self.COURSE_NAME)
            ctx = sites.get_course_for_current_request()
            save_locale = ctx.get_current_locale()

            # Untranslated
            ctx.set_current_locale(None)
            i18n_title = str(
                student_groups.TranslatableResourceStudentGroups.get_i18n_title(
                    key))
            self.assertEquals('My New Group', i18n_title)

            # Translated
            ctx.set_current_locale(self.LOCALE)
            i18n_title = str(
                student_groups.TranslatableResourceStudentGroups.get_i18n_title(
                    key))
            self.assertEquals('MY NEW GROUP', i18n_title)
        finally:
            ctx.set_current_locale(save_locale)
            sites.unset_path_info()

    def test_with_blank_description(self):
        actions.login(self.ADMIN_EMAIL)
        response = self._put_group(None, 'My New Group', '')
        group_id = transforms.loads(response['payload'])['key']
        self._put_availability(group_id, [self.STUDENT_EMAIL])
        self.execute_all_deferred_tasks()

        # Student sees name, but not description.
        actions.login(self.STUDENT_EMAIL)
        self._verify_profile_content('My New Group', None)

        # Provide a translation for name but not descr; verify student view.
        actions.login(self.ADMIN_EMAIL)
        key = resource.Key(student_groups.ResourceHandlerStudentGroup.TYPE,
                           group_id)
        self._put_translation(key, 'MY NEW GROUP', '')
        self.execute_all_deferred_tasks()

        actions.login(self.STUDENT_EMAIL)
        self._verify_profile_content('MY NEW GROUP', None)

        # Set nonblank en_US description; verify that this shows through.
        actions.login(self.ADMIN_EMAIL)
        response = self._put_group(group_id, 'My New Group', 'this is my group')
        actions.login(self.STUDENT_EMAIL)
        self._verify_profile_content('MY NEW GROUP', None)

        # Set translation to explicitly blank; verify that this overrides.
        actions.login(self.ADMIN_EMAIL)
        self._put_translation(key, 'MY NEW GROUP', '')
        self.execute_all_deferred_tasks()
        actions.login(self.STUDENT_EMAIL)
        self._verify_profile_content('MY NEW GROUP', None)


class AggregateEventTests(actions.TestBase):

    ADMIN_EMAIL = 'admin@example.com'
    STUDENT_EMAIL = 'Student@Example.Com'
    COURSE_NAME = 'test_course'
    NAMESPACE = 'ns_%s' % COURSE_NAME
    GROUP_NAME = 'A Test Group'

    def setUp(self):
        super(AggregateEventTests, self).setUp()
        self.base = '/' + self.COURSE_NAME
        self.app_context = actions.simple_add_course(
            self.COURSE_NAME, self.ADMIN_EMAIL, 'Title')

        actions.login(self.STUDENT_EMAIL)
        actions.register(self, 'John Smith')

        with common_utils.Namespace(self.NAMESPACE):
            new_group = student_groups.StudentGroupDAO.create_new(
                {student_groups.StudentGroupDTO.NAME_PROPERTY: self.GROUP_NAME})
            self.group_id = new_group.id

    def tearDown(self):
        sites.remove_course(self.app_context)
        super(AggregateEventTests, self).tearDown()

    def _post_student_event(self):
        actions.login(self.STUDENT_EMAIL)
        with actions.OverriddenEnvironment({'course': {
                'can_record_student_events': True}}):
            self.post('rest/events', {
                'request': transforms.dumps({
                    'xsrf_token': crypto.XsrfTokenManager.create_xsrf_token(
                        'event-post'),
                    'source': 'enter-page',
                    'payload': transforms.dumps({
                        'location': 'https://localhost:8081/test_course',
                    })
                })
            })

    def _run_aggregator_job(self):
        job = student_aggregate.StudentAggregateGenerator(self.app_context)
        job.submit()
        self.execute_all_deferred_tasks()

    def test_student_group_in_aggregate(self):
        self._post_student_event()

        # Verify students not in groups get no content for student group section
        with common_utils.Namespace(self.NAMESPACE):
            self._run_aggregator_job()
            entry = student_aggregate.StudentAggregateEntity.all().get()
        content = transforms.loads(zlib.decompress(entry.data))
        self.assertNotIn(student_groups.AddToStudentAggregate.SECTION, content)

        # Verify students in groups get accurate ID, name for group
        with common_utils.Namespace(self.NAMESPACE):
            student_groups.StudentGroupMembership.set_members(
                self.group_id, [self.STUDENT_EMAIL])
            self._run_aggregator_job()
            entry = student_aggregate.StudentAggregateEntity.all().get()
        content = transforms.loads(zlib.decompress(entry.data))
        self.assertEquals(
            self.group_id,
            content[
                student_groups.AddToStudentAggregate.SECTION][
                    student_groups.AddToStudentAggregate.ID_FIELD])
        self.assertEquals(
            self.GROUP_NAME,
            content[
                student_groups.AddToStudentAggregate.SECTION][
                    student_groups.AddToStudentAggregate.NAME_FIELD])


class OverrideTests(actions.TestBase):

    def test_override_defaults(self):
        dto = student_groups.StudentGroupDTO(None, {})
        self.assertIsNone(dto.get_override(['a']))
        self.assertEquals(123, dto.get_override(['a'], 123))
        self.assertEquals(345, dto.get_override(['a'], 345))

    def test_override_in_memory_lifecycle(self):
        dto = student_groups.StudentGroupDTO(None, {})
        self.assertIsNone(dto.get_override(['a']))
        dto.set_override(['a'], 123)
        self.assertEquals(123, dto.get_override(['a']))
        dto.set_override(['a'], 456)
        self.assertEquals(456, dto.get_override(['a']))
        dto.remove_override(['a'])
        self.assertIsNone(dto.get_override(['a']))

    def test_save_restore(self):
        dto = student_groups.StudentGroupDAO.create_new()
        dto.set_override(['a'], 123)
        dto.set_override(['b'], 345)
        student_groups.StudentGroupDAO.save(dto)
        loaded = student_groups.StudentGroupDAO.load(dto.id)
        self.assertEquals(dto.dict, loaded.dict)

    def test_nested_settings_load_store(self):
        dto = student_groups.StudentGroupDAO.create_new()
        dto.set_override(['a'], 123)
        dto.set_override(['b', 'c', 'd'], 234)
        dto.set_override(['b', 'c', 'e'], 345)
        dto.set_override(['b', 'd'], 456)
        dto.set_override(['b', 'e'], 567)
        student_groups.StudentGroupDAO.save(dto)
        loaded = student_groups.StudentGroupDAO.load(dto.id)
        self.assertEquals(dto.dict, loaded.dict)

    def test_nested_lifecycle(self):
        dto = student_groups.StudentGroupDAO.create_new({})
        dto.set_override(['a'], 123)
        dto.set_override(['b', 'c', 'd'], 234)
        dto.set_override(['b', 'c', 'e'], 345)
        dto.set_override(['b', 'd'], 456)
        dto.set_override(['b', 'e'], 567)
        self.assertEquals(dto.get_override(['b', 'c']), {'d': 234, 'e': 345})
        dto.remove_override(['b', 'c', 'd'])
        self.assertEquals(dto.get_override(['b', 'c']), {'e': 345})
        dto.remove_override(['b', 'c', 'e'])
        self.assertIsNone(dto.get_override(['b', 'c']))
        self.assertEquals(dto.get_override(['b', 'd']), 456)
        self.assertEquals(dto.get_override(['b', 'e']), 567)
        dto.remove_override(['b'])
        self.assertIsNone(dto.get_override(['b']))


class GradebookTests(StudentGroupsTestBase):

    IN_GROUP_STUDENT_EMAIL = 'In_Group@example.com'
    NON_GROUP_STUDENT_EMAIL = 'Hoi_Polloi@example.com'

    def setUp(self):
        super(GradebookTests, self).setUp()

        self.old_namespace = namespace_manager.get_namespace()
        namespace_manager.set_namespace(self.NAMESPACE)
        self.question_id = models.QuestionEntity(
            data=u'{"description": "a", "question": "aa"}').put().id()
        self.instance_id = "6YXFKKxFTddd"

        course = courses.Course(None, app_context=self.app_context)
        self.assessment = course.add_assessment()
        self.assessment.title = 'Top-Level Assessment'
        self.assessment.html_content = (
            '<question quid="%s" instanceid="%s">' % (
                self.question_id, self.instance_id))
        course.save()

    def tearDown(self):
        # Clean up app_context.
        namespace_manager.set_namespace(self.old_namespace)
        super(GradebookTests, self).tearDown()

    def _post_event(self):
        answers = {
            "version":"1.5",
            "individualScores": {
                self.instance_id: 1,
                },
            "containedTypes": {
                self.instance_id: "SaQuestion"
                },
            "answers":{
                self.instance_id: "b"},
            "quids":{
                self.instance_id: str(self.question_id)
                },
            "rawScore": 1,
            "totalWeight": 1,
            "percentScore": 100,
            self.instance_id: {
                "response": "b"}
            }
        xsrf_token = crypto.XsrfTokenManager.create_xsrf_token(
            'assessment-post')
        payload = {
            'assessment_type': self.assessment.unit_id,
            'score': '100.00',
            'answers': transforms.dumps(answers),
            'xsrf_token': xsrf_token,
            }
        response = self.post('answer', payload)
        self.assertEquals(200, response.status_int)

    def _get_gradebook_data(self, data_filter=None):
        data_source_token = paginated_table._DbTableContext._build_secret(
            {'data_source_token': 'xyzzy'})
        parameters = {
            'page_number': 0,
            'chunk_size': 25,
            'data_source_token': data_source_token,
            }
        if data_filter:
            parameters['filters'] = data_filter
        response = self.post('rest/data/raw_student_answers/items', parameters)
        result = transforms.loads(response.body)
        return result.get('data')

    def test_no_data(self):
        # Here, just looking to see that we don't get exceptions.
        actions.login(self.ADMIN_EMAIL)
        self.assertIsNone(self._get_gradebook_data())
        self.assertIsNone(self._get_gradebook_data('student_group='))
        self.assertIsNone(self._get_gradebook_data('student_group=1234'))

    def test_filtering_with_no_groups_created(self):
        actions.login(self.STUDENT_EMAIL)
        actions.register(self, 'John Smith')
        self._post_event()
        gradebook.RawAnswersGenerator(self.app_context).submit()
        self.execute_all_deferred_tasks()

        actions.login(self.ADMIN_EMAIL)
        self.assertEqual(1, len(self._get_gradebook_data()))
        self.assertEqual(1, len(self._get_gradebook_data('student_group=')))
        self.assertEqual(0, len(self._get_gradebook_data('student_group=3')))

    def test_filtering_with_groups(self):
        actions.login(self.ADMIN_EMAIL)
        response = self._put_group(None, 'My New Group', '')
        group_id = transforms.loads(response['payload'])['key']
        self._put_availability(group_id, [self.IN_GROUP_STUDENT_EMAIL])

        actions.login(self.IN_GROUP_STUDENT_EMAIL)
        actions.register(self, 'John Smith')
        self._post_event()

        actions.login(self.NON_GROUP_STUDENT_EMAIL)
        actions.register(self, 'Jane Smith')
        self._post_event()

        actions.login(self.ADMIN_EMAIL)
        gradebook.RawAnswersGenerator(self.app_context).submit()
        self.execute_all_deferred_tasks()
        self.assertEqual(3, len(self._get_gradebook_data()))

        data = self._get_gradebook_data('student_group=')
        self.assertEquals(2, len(data))

        # Order cannot be assumed, so convert to a set of email addresses.
        all_emails = frozenset([datum['user_email'] for datum in data])
        non_group_email = self.NON_GROUP_STUDENT_EMAIL.lower()
        self.assertIn(non_group_email, all_emails)
        in_group_email = self.IN_GROUP_STUDENT_EMAIL.lower()
        self.assertIn(in_group_email, all_emails)

        data = self._get_gradebook_data('student_group=%s' % group_id)
        self.assertEquals(1, len(data))
        self.assertEquals(in_group_email, data[0]['user_email'])

        data = self._get_gradebook_data('student_group=999')
        self.assertEquals(0, len(data))

    def test_user_changing_groups(self):
        # Add event with no student_group_id.
        actions.login(self.IN_GROUP_STUDENT_EMAIL)
        actions.register(self, 'John Smith')
        self._post_event()

        # Add a student group.
        actions.login(self.ADMIN_EMAIL)
        response = self._put_group(None, 'My New Group', '')
        group_id = transforms.loads(response['payload'])['key']
        self._put_availability(group_id, [self.IN_GROUP_STUDENT_EMAIL])

        # Add event with this group.
        actions.login(self.IN_GROUP_STUDENT_EMAIL)
        self._post_event()

        # Another group, and move user to that group.
        actions.login(self.ADMIN_EMAIL)
        response = self._put_group(None, 'Another Group', '')
        group_id = transforms.loads(response['payload'])['key']
        self._put_availability(group_id, [self.IN_GROUP_STUDENT_EMAIL])

        # Add event with different group.
        actions.login(self.IN_GROUP_STUDENT_EMAIL)
        self._post_event()

        actions.login(self.ADMIN_EMAIL)
        gradebook.RawAnswersGenerator(self.app_context).submit()
        self.execute_all_deferred_tasks()
        self.assertEqual(5, len(self._get_gradebook_data()))
        self.assertEquals(3, len(self._get_gradebook_data('student_group=')))

        data = self._get_gradebook_data('student_group=%s' % group_id)
        self.assertEquals(1, len(data))
        in_group_email = self.IN_GROUP_STUDENT_EMAIL.lower()
        self.assertEquals(in_group_email, data[0]['user_email'])


class CourseStartEndDatesTests(triggers_tests.MilestoneTriggerTestsMixin,
                               StudentGroupsTestBase):

    LOG_LEVEL = logging.DEBUG

    COURSE_NAME = 'student_groups_course_dates_test'
    COURSE_TITLE = 'Student Groups Course Dates Tests'
    NAMESPACE = 'ns_%s' % COURSE_NAME

    # COURSE_UNUSED_AVAIL is an alias for REGISTRATION_OPTIONAL and is not
    # used by other triggers tests (hence "UNUSED" in the name).
    TEST_AVAIL = triggers_tests.MilestoneTriggerTestsMixin.COURSE_UNUSED_AVAIL

    SGCOT = student_groups.CourseOverrideTrigger

    def setUp(self):
        triggers_tests.MilestoneTriggerTestsMixin.setUp(self)
        StudentGroupsTestBase.setUp(self)
        self.course = courses.Course(None, app_context=self.app_context)

    def tearDown(self):
        self.clear_course_start_end_dates(
            self.app_context.get_environ(), self.course)
        StudentGroupsTestBase.tearDown(self)

    def _create_group(self, name, description, student_email=None):
        """Creates a new student group."""
        students = [student_email] if student_email else []

        actions.login(self.ADMIN_EMAIL)
        response = self._put_group(None, name, description)
        group_id = transforms.loads(response['payload'])['key']
        self._put_availability(
            group_id, students, course_availability=self.TEST_AVAIL)

        if student_email:
            self._check_student_in_group(student_email, group_id)
        return group_id

    def _check_registered_student(self, student_email, group_id=None):
        expected_email = student_email.lower()
        with common_utils.Namespace(self.NAMESPACE):
            student = models.Student.all().get()
            self.assertEquals(expected_email, student.email)
            if group_id is not None:
                self.assertEquals(group_id, student.group_id)
            else:
                self.assertFalse(student.group_id)

    def _check_no_students_registered(self):
        with common_utils.Namespace(self.NAMESPACE):
            self.assertIsNone(models.Student.all().get())

    def _check_student_in_group(self, student_email, group_id):
        expected_email = student_email.lower()
        with common_utils.Namespace(self.NAMESPACE):
            membership = student_groups.StudentGroupMembership.all().get()
            self.assertEquals(expected_email, membership.key().name())
            self.assertEquals(group_id, membership.group_id)

    def _check_no_students_in_groups(self):
        with common_utils.Namespace(self.NAMESPACE):
            self.assertIsNone(
                student_groups.StudentGroupMembership.all().get())

    def _set_group_start_end_dates(self, start_date, end_date, group_id):
        """Sets start/end dates for specified student group ID."""
        with common_utils.Namespace(self.NAMESPACE):
            dto_to_save = student_groups.StudentGroupDAO.load(group_id)
            dto_to_save.start_date = start_date
            dto_to_save.end_date = end_date
            student_groups.StudentGroupDAO.save(dto_to_save)

    def _check_group_start_end_dates(self, start_date, end_date, group_id):
        with common_utils.Namespace(self.NAMESPACE):
            dto = student_groups.StudentGroupDAO.load(group_id)
            self.assertEquals(start_date, dto.start_date)
            self.assertEquals(end_date, dto.end_date)

    def _log_in_and_register_student(self, student_email, group_id,
                                     student_name='John Smith'):
        """ Logs in using student_email and registers."""
        actions.login(student_email)
        actions.register(self, student_name)
        self._check_registered_student(student_email, group_id=group_id)

    def test_date_modified_in_course_env(self):
        # Create a new student group, but initially containing no students.
        actions.login(self.ADMIN_EMAIL, is_admin=True)
        self.group_id = self._create_group('Modified Group', 'modified group')
        self._check_no_students_in_groups()

        pre_save_env = self.app_context.get_environ()
        self.check_course_start_end_dates(None, None, pre_save_env)
        self.set_course_start_end_dates(self.past_hour_text,
            self.next_hour_text, pre_save_env, self.course)

        # Set start_date and end_date values different for student group.
        self._set_group_start_end_dates(
            self.LAST_CENTURY, self.FAR_FUTURE, self.group_id)

        # _run_env_post_copy_hooks is run, but logged-in student is not in
        # a student group, so should see values in Course 'course' dict.
        actions.login(self.STUDENT_EMAIL)
        post_save_env = courses.Course.get_environ(self.app_context)
        self.check_course_start_end_dates(
            self.past_hour_text, self.next_hour_text, post_save_env)

        # Add student to previously created student group and make the course
        # availability override non-private.
        actions.login(self.ADMIN_EMAIL, is_admin=True)
        self._put_availability(self.group_id,
            [self.STUDENT_EMAIL], course_availability=self.TEST_AVAIL)
        self._check_no_students_registered()
        self._check_student_in_group(self.STUDENT_EMAIL, self.group_id)

        # Remains logged in as student after this call.
        self._log_in_and_register_student(self.STUDENT_EMAIL, self.group_id)
        self._check_no_students_in_groups()  # Non-admin cannot see membership.
        self._check_group_start_end_dates(
            self.LAST_CENTURY, self.FAR_FUTURE, self.group_id)

        # Confirm that, once student is in the student group, start_date
        # and end_date values are used from the student group, not the
        # original Course 'course' settings values.
        with common_utils.Namespace(self.NAMESPACE):
            app_context = sites.get_app_context_for_namespace(self.NAMESPACE)
            in_group_env = courses.Course.get_environ(app_context)
            self.check_course_start_end_dates(
                self.LAST_CENTURY, self.FAR_FUTURE, in_group_env)

    def test_act_hooks(self):
        # modules.student_groups.student_groups.notify_module_enabled()
        # registers some ACT_HOOKS callbacks that save the `when` date/time of
        # course start and end override triggers that are acted on into the
        # corresponding StudentGroupDTO, as UTC ISO-8601 strings.
        #
        # This test confirms that the side effects of those callbacks occur.

        # Create a new student group, but initially containing no students.
        actions.login(self.ADMIN_EMAIL, is_admin=True)
        self.group_id = self._create_group('Hooks Group', 'hooks group')
        self._check_no_students_in_groups()

        # Add student to previously created student group and make the course
        # availability override non-private.
        actions.login(self.ADMIN_EMAIL, is_admin=True)
        self._put_availability(self.group_id,
            [self.STUDENT_EMAIL], course_availability=self.TEST_AVAIL)
        self._check_no_students_registered()
        self._check_student_in_group(self.STUDENT_EMAIL, self.group_id)

        initial_env = self.app_context.get_environ()

        # First, confirm there are no start_date or end_date values in the
        # course settings or the student group.
        self.check_course_start_end_dates(None, None, initial_env)
        self._check_group_start_end_dates(None, None, self.group_id)

        # Remains logged in as student after this call.
        self._log_in_and_register_student(self.STUDENT_EMAIL, self.group_id)

        # Confirm that, once student is in the student group, start_date
        # and end_date values are still not set by either student group or
        # course settings.
        with common_utils.Namespace(self.NAMESPACE):
            in_group_ctx = sites.get_app_context_for_namespace(self.NAMESPACE)
            in_group_env = courses.Course.get_environ(in_group_ctx)
            self.check_course_start_end_dates(None, None, in_group_env)

        # Set a course_start override trigger for the student group.
        actions.login(self.ADMIN_EMAIL, is_admin=True)
        self._put_availability(self.group_id,
            [self.STUDENT_EMAIL], course_triggers=self.only_course_start)

        # Just one course start override trigger was POSTed into student group.
        with common_utils.Namespace(self.NAMESPACE):
            start_dto = student_groups.StudentGroupDAO.load(self.group_id)
            self.assertEquals(
                len(self.SGCOT.copy_from_settings(start_dto)), 1)
            self.assertEquals(self.only_course_start, self.SGCOT.for_form(
                start_dto, course=self.course))

            # Check then remove start_date property, so the act() side-effects
            # can also be confirmed, after run_availability_jobs.
            logs = self.get_log()
            self.check_and_clear_milestone_course_setting('course_start',
                self.past_start_text, start_dto, self.SGCOT)

        # Start override trigger is now in the student group DTO, so act on
        # it in cron job.
        self.run_availability_jobs(self.app_context)

        # Confirm that update_start_date_from_start_override_when() was run,
        # but that course settings were not affected (only student group
        # properties should have changed).
        with common_utils.Namespace(self.NAMESPACE):
            after_run_ctx = sites.get_app_context_for_namespace(self.NAMESPACE)
            after_run_env = courses.Course.get_environ(after_run_ctx)
            self.check_course_start_end_dates(None, None, after_run_env)

            # POSTed course_start `when` ended up as the 'start_date' in the
            # course settings. 'end_date' should still be undefined.
            self._check_group_start_end_dates(
                self.past_start_text, None, self.group_id)

        # All course start/end override triggers were acted on and consumed.
        with common_utils.Namespace(self.NAMESPACE):
            none_start_dto = student_groups.StudentGroupDAO.load(self.group_id)
            # Now that the course_start override trigger should have been
            # acted on, and thus the value of 'start_date' stored in the
            # student group will have changed, provide the 'when' value for
            # the expected default course_start override trigger in
            # only_course_end, only_early_end, and defaults_only.
            when_start = self.SGCOT.encoded_defaults(
                availability=self.SGCOT.NONE_SELECTED, course=self.course,
                milestone='course_start', settings=none_start_dto)

            logs = self.get_log()
            self.retrieve_logged('course_start', 'start_date',
                self.past_start_text, self.SGCOT, logs, where='student group')
            self.assertEquals(self.past_start_text, when_start['when'])
            self.defaults_start = when_start
            self.defaults_only['course_start'][0] = when_start
            self.only_course_end['course_start'][0] = when_start
            self.only_early_end['course_start'][0] = when_start

            self.assertEquals(
                len(self.SGCOT.copy_from_settings(none_start_dto)), 0)
            self.assertEquals(self.defaults_only, self.SGCOT.for_form(
                none_start_dto, course=self.course))

        # Confirm that, logged in as the student, the start_date visible to
        # the student is the one updated by the ACT_HOOKS callback.
        actions.login(self.STUDENT_EMAIL, is_admin=False)
        with common_utils.Namespace(self.NAMESPACE):
            new_start_ctx = sites.get_app_context_for_namespace(self.NAMESPACE)
            new_start_env = courses.Course.get_environ(new_start_ctx)
            self.check_course_start_end_dates(
                self.past_start_text, None, new_start_env)

        # No change in availability (setting course_end['availability'] to the
        # same as course_start['availability']) should still invoke ACT_HOOKS.
        actions.login(self.ADMIN_EMAIL, is_admin=True)
        self._put_availability(self.group_id,
            [self.STUDENT_EMAIL], course_triggers=self.only_early_end)

        # Just the one course_end trigger was POSTed into the student group.
        with common_utils.Namespace(self.NAMESPACE):
            early_dto = student_groups.StudentGroupDAO.load(self.group_id)
            self.assertEquals(
                len(self.SGCOT.copy_from_settings(early_dto)), 1)
            self.assertEquals(self.only_early_end, self.SGCOT.for_form(
                early_dto, course=self.course))

            # Check then remove end_date property, so the act() side-effects
            # can also be confirmed, after run_availability_jobs.
            logs = self.get_log()
            self.check_and_clear_milestone_course_setting('course_end',
                self.an_earlier_end_hour_text, early_dto, self.SGCOT)

        # End trigger is now in course settings, so act on it in cron job.
        self.run_availability_jobs(self.app_context)

        # Confirm that update_end_date_from_end_override_when() was run, but
        # that course settings were not affected (only student group
        # properties should have changed).
        with common_utils.Namespace(self.NAMESPACE):
            after_end_ctx = sites.get_app_context_for_namespace(self.NAMESPACE)
            after_end_env = courses.Course.get_environ(after_end_ctx)
            self.check_course_start_end_dates(None, None, after_end_env)

        # All course start/end override triggers were acted on and consumed.
        with common_utils.Namespace(self.NAMESPACE):
            none_end_dto = student_groups.StudentGroupDAO.load(self.group_id)
            # Now that the course_end override trigger should have been
            # acted on, and thus the value of 'end_date' stored in the
            # student group will have changed, provide the 'when' value for
            # the expected default course_end override trigger in
            # only_course_start and defaults_only.
            when_end = self.SGCOT.encoded_defaults(
                availability=self.SGCOT.NONE_SELECTED, course=self.course,
                milestone='course_end', settings=none_end_dto)

            logs = self.get_log()
            self.retrieve_logged('course_end', 'end_date',
                self.an_earlier_end_hour_text, self.SGCOT, logs,
                where='student group')
            self.assertEquals(self.an_earlier_end_hour_text, when_end['when'])
            self.defaults_end = when_end
            self.defaults_only['course_end'][0] = when_end
            self.only_course_start['course_end'][0] = when_end

            self.assertEquals(
                len(self.SGCOT.copy_from_settings(none_end_dto)), 0)
            self.assertEquals(self.defaults_only, self.SGCOT.for_form(
                none_end_dto, course=self.course))

        # A different end_date value should now be present in the student
        # group. Previously-POSTed start_date should be unchanged.
        self._check_group_start_end_dates(self.past_start_text,
            self.an_earlier_end_hour_text, self.group_id)

        # Confirm that, logged in as the student, the end_date visible to
        # the student is the one updated by the ACT_HOOKS callback.
        actions.login(self.STUDENT_EMAIL, is_admin=False)
        with common_utils.Namespace(self.NAMESPACE):
            new_end_ctx = sites.get_app_context_for_namespace(self.NAMESPACE)
            new_end_env = courses.Course.get_environ(new_end_ctx)
            self.check_course_start_end_dates(self.past_start_text,
                self.an_earlier_end_hour_text, new_end_env)
