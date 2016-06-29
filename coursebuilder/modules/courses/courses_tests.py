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

"""Tests for modules/courses/."""

__author__ = 'Glenn De Jonghe (gdejonghe@google.com)'

import collections
import copy
import logging
import re
import urlparse

from common import utils as common_utils
from common import crypto
from common import resource
from common import utc
from controllers import sites
from controllers import utils
from models import config
from models import courses
from models import custom_modules
from models import models
from models import resources_display
from models import review
from models import transforms
from modules.courses import availability
from modules.courses import availability_cron
from modules.courses import constants
from modules.courses import courses as modules_courses
from modules.courses import lessons
from modules.courses import triggers
from modules.courses import unit_lesson_editor
from tests.functional import actions

from google.appengine.ext import deferred

class CourseAccessPermissionsTests(actions.CourseOutlineTest):
    COURSE_NAME = 'outline_permissions'
    ADMIN_EMAIL = 'admin@foo.com'
    USER_EMAIL = 'user@foo.com'
    ROLE = 'test_role'
    NAMESPACE = 'ns_%s' % COURSE_NAME
    COURSE_EDIT_XPATH = './/*[@id="edit-course"]'

    def setUp(self):
        super(CourseAccessPermissionsTests, self).setUp()
        self.base = '/' + self.COURSE_NAME
        self.context = actions.simple_add_course(
            self.COURSE_NAME, self.ADMIN_EMAIL, 'Access Draft Testing')
        self.course = courses.Course(None, self.context)
        self.unit = self.course.add_unit()
        self.assessment = self.course.add_assessment()
        self.link = self.course.add_link()
        self.course.save()
        actions.login(self.USER_EMAIL, is_admin=False)

    def _add_role_with_permissions(self, module, permissions):
        with common_utils.Namespace(self.NAMESPACE):
            role_dto = models.RoleDTO(None, {
                'name': self.ROLE,
                'users': [self.USER_EMAIL],
                'permissions': {module: permissions},
                })
            models.RoleDAO.save(role_dto)

    def test_no_permission(self):
        response = self.get('dashboard?action=outline')
        self.assertEquals(302, response.status_int)
        self.assertEquals('http://localhost/%s' % self.COURSE_NAME,
                          response.location)

    def test_course_structure_reorder_permission(self):
        self._add_role_with_permissions(
            modules_courses.MODULE_NAME,
            [constants.COURSE_OUTLINE_REORDER_PERMISSION])
        response = self.get('dashboard?action=outline')
        self.assertEquals(200, response.status_int)
        soup = self.parse_html_string_to_soup(response.body)

        # No buttons for add unit/assessment, import course.
        self.assertEquals(len(soup.select('.gcb-button-toolbar > *')), 0)

        # Should have reorder drag handles
        self.assertGreater(len(soup.select('.reorder')), 0)

        # No add-lesson item.
        self.assertEquals(len(soup.select('.add-lesson')), 0)

    def _get_dom(self):
        response = self.get('dashboard?action=outline')
        self.assertEquals(200, response.status_int)
        return self.parse_html_string(response.body)

    def _get_soup(self):
        response = self.get('dashboard?action=outline')
        self.assertEquals(200, response.status_int)
        return self.parse_html_string_to_soup(response.body)

    def test_course_edit_settings_link(self):
        # Add role permission so we can see the course outline page at all.
        self._add_role_with_permissions(
            modules_courses.MODULE_NAME,
            [constants.COURSE_OUTLINE_REORDER_PERMISSION])

        # Give this user permission to *edit* some random course property that's
        # not course-availability
        with actions.OverriddenSchemaPermission(
            'fake_course_perm', constants.SCOPE_COURSE_SETTINGS,
            self.USER_EMAIL, editable_perms=['course/course:title']):

            element = self._get_dom().find(self.COURSE_EDIT_XPATH)
            self.assertEquals('a', element.tag)

        # Give this user permission to *view* some random course property that's
        # not course-availability
        with actions.OverriddenSchemaPermission(
            'fake_course_perm', constants.SCOPE_COURSE_SETTINGS,
            self.USER_EMAIL, readable_perms=['course/course:title']):

            element = self._get_dom().find(self.COURSE_EDIT_XPATH)
            self.assertEquals('a', element.tag)

    def test_edit_unit_property_editor_link(self):
        # Verify readability on some random property allows pencil icon
        # link to edit/view props page.

        UNIT_EDIT_LINK_SELECTOR = \
            '[data-unit-id={}] .name'
        UNIT_SELECTOR = UNIT_EDIT_LINK_SELECTOR.format(
            self.unit.unit_id)
        ASSESSMENT_SELECTOR = UNIT_EDIT_LINK_SELECTOR.format(
            self.assessment.unit_id)
        LINK_SELECTOR = UNIT_EDIT_LINK_SELECTOR.format(
            self.link.unit_id)

        with actions.OverriddenSchemaPermission(
            'fake_unit_perm', constants.SCOPE_UNIT,
            self.USER_EMAIL, editable_perms=['description']):

            soup = self._get_soup()
            self.assertEditabilityState(soup.select(UNIT_SELECTOR)[0], True)
            self.assertEditabilityState(
                soup.select(ASSESSMENT_SELECTOR)[0], False)
            self.assertEditabilityState(soup.select(LINK_SELECTOR)[0], False)

        # Only assessment property editable
        with actions.OverriddenSchemaPermission(
            'fake_unit_perm', constants.SCOPE_ASSESSMENT,
            self.USER_EMAIL, editable_perms=['assessment/description']):

            soup = self._get_soup()
            self.assertEditabilityState(soup.select(UNIT_SELECTOR)[0], False)
            self.assertEditabilityState(
                soup.select(ASSESSMENT_SELECTOR)[0], True)
            self.assertEditabilityState(soup.select(LINK_SELECTOR)[0], False)

        # Only link property editable
        with actions.OverriddenSchemaPermission(
            'fake_unit_perm', constants.SCOPE_LINK,
            self.USER_EMAIL, editable_perms=['description']):

            soup = self._get_soup()
            self.assertEditabilityState(soup.select(UNIT_SELECTOR)[0], False)
            self.assertEditabilityState(
                soup.select(ASSESSMENT_SELECTOR)[0], False)
            self.assertEditabilityState(soup.select(LINK_SELECTOR)[0], True)

    def test_when_user_is_not_in_any_roles_private_course_is_invisible(self):
        self.course.set_course_availability(courses.COURSE_AVAILABILITY_PRIVATE)
        response = self.get('course', expect_errors=True)
        self.assertEquals(404, response.status_int)
        response = self.get('unit?unit=%s' % self.unit.unit_id,
                            expect_errors=True)
        self.assertEquals(404, response.status_int)
        response = self.get('assessment?name=%s' % self.assessment.unit_id,
                            expect_errors=True)
        self.assertEquals(404, response.status_int)

    def test_user_in_admin_role_can_view_drafts(self):
        self.course.set_course_availability(courses.COURSE_AVAILABILITY_PRIVATE)
        self._add_role_with_permissions(
            custom_modules.MODULE_NAME,
            [custom_modules.SEE_DRAFTS_PERMISSION])
        response = self.get('course')
        self.assertEquals(200, response.status_int)
        response = self.get('unit?unit=%s' % self.unit.unit_id)
        self.assertEquals(200, response.status_int)
        response = self.get('assessment?name=%s' % self.assessment.unit_id)
        self.assertEquals(200, response.status_int)

    def test_admin_can_view_drafts(self):
        self.course.set_course_availability(courses.COURSE_AVAILABILITY_PRIVATE)
        actions.login(self.ADMIN_EMAIL, is_admin=True)
        response = self.get('course')
        self.assertEquals(200, response.status_int)
        response = self.get('unit?unit=%s' % self.unit.unit_id)
        self.assertEquals(200, response.status_int)
        response = self.get('assessment?name=%s' % self.assessment.unit_id)
        self.assertEquals(200, response.status_int)


class UnitLessonEditorAccess(actions.TestBase):

    COURSE_NAME = 'outline_permissions'
    ADMIN_EMAIL = 'admin@foo.com'
    USER_EMAIL = 'user@foo.com'
    ROLE = 'test_role'
    NAMESPACE = 'ns_%s' % COURSE_NAME

    def setUp(self):
        super(UnitLessonEditorAccess, self).setUp()
        self.base = '/' + self.COURSE_NAME
        self.context = actions.simple_add_course(
            self.COURSE_NAME, self.ADMIN_EMAIL, 'Access Draft Testing')
        self.course = courses.Course(None, self.context)
        self.unit = self.course.add_unit()
        self.assessment = self.course.add_assessment()
        self.link = self.course.add_link()
        self.course.save()
        actions.login(self.USER_EMAIL, is_admin=False)

        self.unit_url = '/%s%s' % (
            self.COURSE_NAME,
            unit_lesson_editor.UnitRESTHandler.URI)
        self.assessment_url = '/%s%s' % (
            self.COURSE_NAME,
            unit_lesson_editor.AssessmentRESTHandler.URI)
        self.link_url = '/%s%s' % (
            self.COURSE_NAME,
            unit_lesson_editor.LinkRESTHandler.URI)

    def _get(self, url, key, expect_error=False):
        response = self.get(url + '?key=%s' % key)
        self.assertEquals(200, response.status_int)
        payload = transforms.loads(response.body)
        if expect_error:
            self.assertEquals(401, int(payload['status']))
            return None
        else:
            self.assertEquals(200, int(payload['status']))
            return transforms.loads(payload['payload'])

    def _put(self, url, key, payload, expect_error=False):
        params = {
            'request': transforms.dumps({
                'xsrf_token': crypto.XsrfTokenManager.create_xsrf_token(
                    'put-unit'),
                'key': key,
                'payload': transforms.dumps(payload),
            })
        }
        response = self.put(url, params)
        self.assertEquals(200, response.status_int)
        payload = transforms.loads(response.body)
        if expect_error:
            self.assertEquals(401, payload['status'])
        else:
            self.assertEquals(200, payload['status'])

    def test_get_and_put_return_error_when_no_permissions(self):
        self._get(self.unit_url, self.unit.unit_id, expect_error=True)
        self._get(self.assessment_url, self.assessment.unit_id,
                  expect_error=True)
        self._get(self.link_url, self.link.unit_id, expect_error=True)

        self._put(self.unit_url, self.unit.unit_id, {}, expect_error=True)
        self._put(self.assessment_url, self.assessment.unit_id, {},
                  expect_error=True)
        self._put(self.link_url, self.link.unit_id, {}, expect_error=True)

    def test_readonly_perms(self):
        # Can read only the one property specified; get error on write of
        # that property.
        with actions.OverriddenSchemaPermission(
            'fake_unit_perm', constants.SCOPE_UNIT,
            self.USER_EMAIL, readable_perms=['description']):

            content = self._get(self.unit_url, self.unit.unit_id)
            self.assertIn('description', content)
            self.assertEquals(1, len(content))

            self._put(self.unit_url, self.unit.unit_id,
                      {'description': 'foo'}, expect_error=True)

        with actions.OverriddenSchemaPermission(
            'fake_unit_perm', constants.SCOPE_ASSESSMENT,
            self.USER_EMAIL, readable_perms=['assessment/description']):

            content = self._get(self.assessment_url, self.assessment.unit_id)
            self.assertIn('assessment', content)
            self.assertIn('description', content['assessment'])
            self.assertEquals(1, len(content))

            self._put(self.assessment_url, self.assessment.unit_id,
                      {'assessment': {'description': 'foo'}}, expect_error=True)

        with actions.OverriddenSchemaPermission(
            'fake_unit_perm', constants.SCOPE_LINK,
            self.USER_EMAIL, readable_perms=['description']):

            content = self._get(self.link_url, self.link.unit_id)
            self.assertIn('description', content)
            self.assertEquals(1, len(content))

            self._put(self.link_url, self.link.unit_id,
                      {'description': 'foo'}, expect_error=True)

    def test_editable_perms(self):
        # Verify writablility and effect of write of property.
        # Verify that only writable fields get written
        with actions.OverriddenSchemaPermission(
            'fake_unit_perm', constants.SCOPE_UNIT,
            self.USER_EMAIL, editable_perms=['description']):

            content = self._get(self.unit_url, self.unit.unit_id)
            self.assertIn('description', content)
            self.assertEquals(1, len(content))

            self._put(self.unit_url, self.unit.unit_id, {
                'description': 'foo',
                'title': 'FOO',
                })
            with common_utils.Namespace(self.NAMESPACE):
                ctx = sites.get_app_context_for_namespace(self.NAMESPACE)
                course = courses.Course(None, app_context=ctx)
                unit = course.find_unit_by_id(self.unit.unit_id)
                self.assertEquals(unit.description, 'foo')
                self.assertEquals(unit.title, 'New Unit')

        with actions.OverriddenSchemaPermission(
            'fake_unit_perm', constants.SCOPE_ASSESSMENT,
            self.USER_EMAIL, editable_perms=['assessment/description']):

            content = self._get(self.assessment_url, self.assessment.unit_id)
            self.assertIn('assessment', content)
            self.assertIn('description', content['assessment'])
            self.assertEquals(1, len(content))

            self._put(self.assessment_url, self.assessment.unit_id,
                      {'assessment': {'description': 'bar', 'title': 'BAR'}})
            with common_utils.Namespace(self.NAMESPACE):
                ctx = sites.get_app_context_for_namespace(self.NAMESPACE)
                course = courses.Course(None, app_context=ctx)
                assessment = course.find_unit_by_id(self.assessment.unit_id)
                self.assertEquals(assessment.description, 'bar')
                self.assertEquals(assessment.title, 'New Assessment')

        with actions.OverriddenSchemaPermission(
            'fake_unit_perm', constants.SCOPE_LINK,
            self.USER_EMAIL, editable_perms=['description']):

            content = self._get(self.link_url, self.link.unit_id)
            self.assertIn('description', content)
            self.assertEquals(1, len(content))

            self._put(self.link_url, self.link.unit_id, {
                'description': 'baz',
                'title': 'BAZ',
                })
            with common_utils.Namespace(self.NAMESPACE):
                ctx = sites.get_app_context_for_namespace(self.NAMESPACE)
                course = courses.Course(None, app_context=ctx)
                link = course.find_unit_by_id(self.link.unit_id)
                self.assertEquals(link.description, 'baz')
                self.assertEquals(link.title, 'New Link')


class ReorderAccess(actions.TestBase):

    COURSE_NAME = 'outline_permissions'
    ADMIN_EMAIL = 'admin@foo.com'
    USER_EMAIL = 'user@foo.com'
    ROLE = 'test_role'
    NAMESPACE = 'ns_%s' % COURSE_NAME

    def setUp(self):
        super(ReorderAccess, self).setUp()
        self.base = '/' + self.COURSE_NAME
        self.context = actions.simple_add_course(
            self.COURSE_NAME, self.ADMIN_EMAIL, 'Access Draft Testing')
        self.course = courses.Course(None, self.context)
        self.unit = self.course.add_unit()
        self.assessment = self.course.add_assessment()
        self.link = self.course.add_link()
        self.course.save()
        actions.login(self.USER_EMAIL, is_admin=False)

        self.url = '/%s%s' % (self.COURSE_NAME,
                              unit_lesson_editor.UnitLessonTitleRESTHandler.URI)

    def _put(self, payload, expect_error=False):
        params = {
            'request': transforms.dumps({
                'xsrf_token': crypto.XsrfTokenManager.create_xsrf_token(
                    unit_lesson_editor.UnitLessonTitleRESTHandler.XSRF_TOKEN),
                'payload': transforms.dumps(payload),
            })
        }
        response = self.put(self.url, params)
        self.assertEquals(200, response.status_int)
        payload = transforms.loads(response.body)
        if expect_error:
            self.assertEquals(401, payload['status'])
        else:
            self.assertEquals(200, payload['status'])

    def _add_reorder_permission(self):
        with common_utils.Namespace(self.NAMESPACE):
            role_dto = models.RoleDTO(None, {
                'name': self.ROLE,
                'users': [self.USER_EMAIL],
                'permissions': {
                    modules_courses.MODULE_NAME: [
                        constants.COURSE_OUTLINE_REORDER_PERMISSION]
                    }
                })
            models.RoleDAO.save(role_dto)

    def test_put_with_no_permission(self):
        response = self._put({}, expect_error=True)

    def test_put_with_permission(self):
        # Verify original order before changing things.
        with common_utils.Namespace(self.NAMESPACE):
            ctx = sites.get_app_context_for_namespace(self.NAMESPACE)
            course = courses.Course(None, app_context=ctx)
            units = course.get_units()
            self.assertEquals(3, len(units))
            self.assertEquals(self.unit.unit_id, units[0].unit_id)
            self.assertEquals(self.assessment.unit_id, units[1].unit_id)
            self.assertEquals(self.link.unit_id, units[2].unit_id)

        self._add_reorder_permission()
        self._put({'outline': [
            {'id': self.link.unit_id, 'title': '', 'lessons': []},
            {'id': self.unit.unit_id, 'title': '', 'lessons': []},
            {'id': self.assessment.unit_id, 'title': '', 'lessons': []},
            ]})

        with common_utils.Namespace(self.NAMESPACE):
            ctx = sites.get_app_context_for_namespace(self.NAMESPACE)
            course = courses.Course(None, app_context=ctx)
            units = course.get_units()
            self.assertEquals(3, len(units))
            self.assertEquals(self.link.unit_id, units[0].unit_id)
            self.assertEquals(self.unit.unit_id, units[1].unit_id)
            self.assertEquals(self.assessment.unit_id, units[2].unit_id)


class BackgroundImportTests(actions.TestBase):

    FROM_COURSE_NAME = 'from_background_import'
    FROM_NAMESPACE = 'ns_%s' % FROM_COURSE_NAME
    TO_COURSE_NAME = 'to_background_import'
    TO_NAMESPACE = 'ns_%s' % TO_COURSE_NAME
    ADMIN_EMAIL = 'admin@foo.com'
    UNIT_TITLE = 'Jabberwocky'

    def setUp(self):
        super(BackgroundImportTests, self).setUp()
        self.from_context = actions.simple_add_course(
            self.FROM_COURSE_NAME, self.ADMIN_EMAIL, 'From Course')
        from_course = courses.Course(None, app_context=self.from_context)
        unit = from_course.add_unit()
        unit.title = self.UNIT_TITLE
        from_course.save()

        self.to_context = actions.simple_add_course(
            self.TO_COURSE_NAME, self.ADMIN_EMAIL, 'To Course')
        actions.login(self.ADMIN_EMAIL, is_admin=False)
        self.import_start_url = '%s%s' % (
            self.TO_COURSE_NAME,
            unit_lesson_editor.ImportCourseRESTHandler.URI)
        job_name = unit_lesson_editor.ImportCourseBackgroundJob(
            self.to_context, None).name
        self.import_status_url = '%s%s?name=%s' % (
            self.TO_COURSE_NAME,
            utils.JobStatusRESTHandler.URL,
            job_name)
        self.dashboard_url = '%s/dashboard' % self.TO_COURSE_NAME

    def _initiate_import(self):
        # GET and then POST to the clone-a-course REST handler.
        response = transforms.loads(self.get(self.import_start_url).body)
        payload = transforms.loads(response['payload'])
        content = transforms.dumps({
            'course': payload['course'],
            })
        request = transforms.dumps({
            'xsrf_token': response['xsrf_token'],
            'payload': content,
            })
        response = self.put(self.import_start_url, {'request': request})
        self.assertEquals(transforms.loads(response.body)['status'], 200)

    def _complete_import(self):
        # Allow the import to complete.
        self.execute_all_deferred_tasks()

    def _cancel_import(self):
        self.post(self.dashboard_url, {
            'action':
                unit_lesson_editor.UnitLessonEditor.ACTION_POST_CANCEL_IMPORT,
            'xsrf_token': crypto.XsrfTokenManager.create_xsrf_token(
                unit_lesson_editor.UnitLessonEditor.ACTION_POST_CANCEL_IMPORT),
            })

    def _verify_normal_add_controls_and_import_controls(self):
        # Verify dashboard page has normal buttons as well as Import button
        # when course is blank.  We should _not_ have wait-for-it buttons for
        # import.
        response = self.get(self.dashboard_url)
        dom = self.parse_html_string(response.body)
        controls = dom.findall('.//div[@class="gcb-button-toolbar"]/*')
        control_ids = [f.get('id') for f in controls]
        self.assertIn('add_unit', control_ids)
        self.assertIn('add_assessment', control_ids)
        self.assertIn('add_link', control_ids)
        self.assertIn('import_course', control_ids)
        self.assertIsNone(dom.find('.//div[@id="import-course-cancel"]'))
        self.assertIsNone(dom.find('.//div[@id="import-course-ready"]'))

    def _verify_normal_add_controls_with_no_import_controls(self):
        # Verify dashboard page has normal Add buttons.  All import-related
        # buttons should now be gone.
        response = self.get(self.dashboard_url)
        dom = self.parse_html_string(response.body)
        controls = dom.findall('.//div[@class="gcb-button-toolbar"]/*')
        control_ids = [f.get('id') for f in controls]
        self.assertIn('add_unit', control_ids)
        self.assertIn('add_assessment', control_ids)
        self.assertIn('add_link', control_ids)
        self.assertNotIn('import_course', control_ids)
        self.assertIsNone(dom.find('.//div[@id="import-course-cancel"]'))
        self.assertIsNone(dom.find('.//div[@id="import-course-ready"]'))

    def _get_names(self):
        response = self.get(self.dashboard_url)
        soup = self.parse_html_string_to_soup(response.body)
        name_items = soup.select('.name a')
        return [ni.text.strip() for ni in name_items]

    def _verify_imported_course_content_present(self):
        # Also verify that the imported course's unit is there.
        self.assertIn(self.UNIT_TITLE, self._get_names())

    def _verify_imported_course_content_absent(self):
        # Also verify that the imported course's unit is there.
        self.assertNotIn(self.UNIT_TITLE, self._get_names())

    def _verify_import_wait_controls_and_no_add_controls(self):
        # Verify that the usual add/import buttons are *NOT* present.  Verify
        # that while course import is pending, we have wait-for-it buttons.
        response = self.get(self.dashboard_url)
        dom = self.parse_html_string(response.body)
        controls = dom.findall('.//div[@class="gcb-button-toolbar"]/*')
        control_ids = [f.get('id') for f in controls]
        self.assertNotIn('add_unit', control_ids)
        self.assertNotIn('add_assessment', control_ids)
        self.assertNotIn('add_link', control_ids)
        self.assertNotIn('import_course', control_ids)
        self.assertIsNotNone(dom.find('.//div[@id="import-course-cancel"]'))
        self.assertIsNotNone(dom.find('.//div[@id="import-course-ready"]'))

    def test_import_success(self):
        self._verify_normal_add_controls_and_import_controls()
        self._initiate_import()
        self._verify_import_wait_controls_and_no_add_controls()
        self._complete_import()
        self._verify_normal_add_controls_with_no_import_controls()
        self._verify_imported_course_content_present()

    def test_import_cancel(self):
        self._initiate_import()
        self._verify_import_wait_controls_and_no_add_controls()
        self._cancel_import()

        # We should get our add controls back on the dashboard immediately,
        # despite having the task still pending on the deferred queue.
        # Should still have import controls, since we don't have any
        # units in the course.
        self._verify_normal_add_controls_and_import_controls()
        self._verify_imported_course_content_absent()

        # Run the queue to completion; we should *not* now see new course
        # content; the queue handler should notice the cancellation and
        # not commit the updated version of the course.
        self._complete_import()
        self._verify_imported_course_content_absent()

    def test_import_cancel_import(self):
        self._initiate_import()
        self._cancel_import()
        self._initiate_import()
        self._complete_import()
        self._verify_normal_add_controls_with_no_import_controls()
        self._verify_imported_course_content_present()

    def test_import_has_errors(self):
        self._initiate_import()
        try:
            save_import_from = courses.Course.import_from
            def fake_import_from(slf, src, errors):
                errors.append('Fake error')
            courses.Course.import_from = fake_import_from
            with self.assertRaises(deferred.PermanentTaskFailure):
                self._complete_import()
        finally:
            courses.Course.import_from = save_import_from
        self._verify_normal_add_controls_and_import_controls()
        self._verify_imported_course_content_absent()

    def test_import_canceled_while_import_running(self):
        self._initiate_import()
        try:
            save_import_from = courses.Course.import_from
            def fake_import_from(slf, src, err):
                job = unit_lesson_editor.ImportCourseBackgroundJob(
                    self.to_context, None)
                job.cancel()
            courses.Course.import_from = fake_import_from
            with self.assertRaises(deferred.PermanentTaskFailure):
                self._complete_import()
        finally:
            courses.Course.import_from = save_import_from
        self._verify_normal_add_controls_and_import_controls()
        self._verify_imported_course_content_absent()

    def test_cancel_import_not_admin(self):
        actions.logout()
        response = self.post(self.dashboard_url, {
            'action':
                unit_lesson_editor.UnitLessonEditor.ACTION_POST_CANCEL_IMPORT,
            'xsrf_token': crypto.XsrfTokenManager.create_xsrf_token(
                unit_lesson_editor.UnitLessonEditor.ACTION_POST_CANCEL_IMPORT),
            })
        self.assertEquals(302, response.status_int)

    def test_cancel_import_no_xsrf(self):
        response = self.post(self.dashboard_url, {
            'action':
                unit_lesson_editor.UnitLessonEditor.ACTION_POST_CANCEL_IMPORT,
            }, expect_errors=True)
        self.assertEquals(403, response.status_int)


Element = collections.namedtuple('Element',
                                 ['text', 'link', 'progress', 'contents'])


class AvailabilityTests(actions.TestBase):

    COURSE_NAME = 'availability_tests'
    ADMIN_EMAIL = 'admin@foo.com'
    USER_EMAIL = 'user@foo.com'
    ROLE = 'test_role'
    NAMESPACE = 'ns_%s' % COURSE_NAME

    TOP_LEVEL_NO_LINKS_NO_PROGRESS = [
        Element('Unit 1 - Unit One', None, None, []),
        Element('Link One', None, None, []),
        Element('Assessment One', None, None, []),
        Element('Unit 2 - Unit Two', None, None, []),
        Element('Link Two', None, None, []),
        Element('Assessment Two', None, None, []),
        Element('Unit 3 - Unit Three', None, None, []),
        Element('Link Three', None, None, []),
        Element('Assessment Three', None, None, []),
        ]
    TOP_LEVEL_WITH_LINKS_NO_PROGRESS = [
        Element('Unit 1 - Unit One', 'unit?unit=1', None, []),
        Element('Link One', 'http://www.foo.com', None, []),
        Element('Assessment One', 'assessment?name=3', None, []),
        Element('Unit 2 - Unit Two', 'unit?unit=4', None, []),
        Element('Link Two', 'http://www.bar.com', None, []),
        Element('Assessment Two', 'assessment?name=6', None, []),
        Element('Unit 3 - Unit Three', 'unit?unit=7', None, []),
        Element('Link Three', None, None, []),
        Element('Assessment Three', 'assessment?name=9', None, []),
        ]
    TOP_LEVEL_WITH_LINKS_ASSESSMENT_PROGRESS = [
        Element('Unit 1 - Unit One', 'unit?unit=1', None, []),
        Element('Link One', 'http://www.foo.com', None, []),
        Element('Assessment One', 'assessment?name=3',
                'progress-notstarted-3', []),
        Element('Unit 2 - Unit Two', 'unit?unit=4', None, []),
        Element('Link Two', 'http://www.bar.com', None, []),
        Element('Assessment Two', 'assessment?name=6',
                'progress-notstarted-6', []),
        Element('Unit 3 - Unit Three', 'unit?unit=7', None, []),
        Element('Link Three', None, None, []),
        Element('Assessment Three', 'assessment?name=9',
                'progress-notstarted-9', []),
        ]
    TOP_LEVEL_WITH_LINKS_ALL_PROGRESS = [
        Element('Unit 1 - Unit One', 'unit?unit=1', None, []),
        Element('Link One', 'http://www.foo.com', None, []),
        Element('Assessment One', 'assessment?name=3',
                'progress-notstarted-3', []),
        Element('Unit 2 - Unit Two', 'unit?unit=4', None, []),
        Element('Link Two', 'http://www.bar.com', None, []),
        Element('Assessment Two', 'assessment?name=6',
                'progress-notstarted-6', []),
        Element('Unit 3 - Unit Three', 'unit?unit=7', None, []),
        Element('Link Three', None, None, []),
        Element('Assessment Three', 'assessment?name=9',
                'progress-notstarted-9', []),
        ]
    ALL_LEVELS_NO_LINKS_NO_PROGRESS = [
        Element('Unit 1 - Unit One', None, None, [
            Element('1.1 Lesson Zero', None, None, [])]),
        Element('Link One', None, None, []),
        Element('Assessment One', None, None, []),
        Element('Unit 2 - Unit Two', None, None, contents=[
            Element('2.1 Lesson One', None, None, []),
            Element('2.2 Lesson Two', None, None, []),
            Element('2.3 Lesson Three', None, None, []),
            ]),
        Element('Link Two', None, None, []),
        Element('Assessment Two', None, None, []),
        Element('Unit 3 - Unit Three', None, None, contents=[
            Element('Pre Assessment', None, None, []),
            # Non-registered students don't see peer-review step.
            Element('3.1 Mid Lesson', None, None, []),
            Element('Post Assessment', None, None, []),
            ]),
        Element('Link Three', None, None, []),
        Element('Assessment Three', None, None, []),
        ]
    ALL_LEVELS_WITH_LINKS_NO_PROGRESS = [
        Element('Unit 1 - Unit One', 'unit?unit=1', None, [
            Element('1.1 Lesson Zero', 'unit?unit=1&lesson=16', None, [])]),
        Element('Link One', 'http://www.foo.com', None, []),
        Element('Assessment One', 'assessment?name=3', None, []),
        Element('Unit 2 - Unit Two', 'unit?unit=4', None, contents=[
            Element('2.1 Lesson One', 'unit?unit=4&lesson=10', None, []),
            Element('2.2 Lesson Two', 'unit?unit=4&lesson=11', None, []),
            Element('2.3 Lesson Three', 'unit?unit=4&lesson=12', None, [])]),
        Element('Link Two', 'http://www.bar.com', None, []),
        Element('Assessment Two', 'assessment?name=6', None, []),
        Element('Unit 3 - Unit Three', 'unit?unit=7', None, contents=[
            Element('Pre Assessment', 'unit?unit=7&assessment=13', None, []),
            Element('Review peer assignments', None, None, []),
            Element('3.1 Mid Lesson', 'unit?unit=7&lesson=15', None, []),
            Element('Post Assessment', 'unit?unit=7&assessment=14', None, [])]),
        Element('Link Three', None, None, []),
        Element('Assessment Three', 'assessment?name=9', None, []),
        ]
    ALL_LEVELS_WITH_LINKS_ASSESSMENT_PROGRESS = [
        Element('Unit 1 - Unit One', 'unit?unit=1', None, [
            Element('1.1 Lesson Zero', 'unit?unit=1&lesson=16', None, [])]),
        Element('Link One', 'http://www.foo.com', None, []),
        Element('Assessment One', 'assessment?name=3',
                'progress-notstarted-3', []),
        Element('Unit 2 - Unit Two', 'unit?unit=4', None, contents=[
            Element('2.1 Lesson One', 'unit?unit=4&lesson=10', None, []),
            Element('2.2 Lesson Two', 'unit?unit=4&lesson=11', None, []),
            Element('2.3 Lesson Three', 'unit?unit=4&lesson=12', None, [])]),
        Element('Link Two', 'http://www.bar.com', None, []),
        Element('Assessment Two', 'assessment?name=6',
                'progress-notstarted-6', []),
        Element('Unit 3 - Unit Three', 'unit?unit=7', None, contents=[
            Element('Pre Assessment', 'unit?unit=7&assessment=13',
                    'progress-notstarted-13', []),
            Element('Review peer assignments', None,
                    'progress-notstarted-13', []),
            Element('3.1 Mid Lesson', 'unit?unit=7&lesson=15', None, []),
            Element('Post Assessment', 'unit?unit=7&assessment=14',
                    'progress-notstarted-14', [])]),
        Element('Link Three', None, None, []),
        Element('Assessment Three', 'assessment?name=9',
                'progress-notstarted-9', []),
        ]

    def setUp(self):
        super(AvailabilityTests, self).setUp()
        self.base = '/' + self.COURSE_NAME
        self.app_context = actions.simple_add_course(
            self.COURSE_NAME, self.ADMIN_EMAIL, 'Availability Tests')

        self.course = courses.Course(None, self.app_context)
        self.unit_one = self.course.add_unit()
        self.unit_one.title = 'Unit One'
        self.unit_one.availability = courses.AVAILABILITY_COURSE
        self.link_one = self.course.add_link()
        self.link_one.title = 'Link One'
        self.link_one.href = 'http://www.foo.com'
        self.link_one.availability = courses.AVAILABILITY_COURSE
        self.assessment_one = self.course.add_assessment()
        self.assessment_one.title = 'Assessment One'
        self.assessment_one.availability = courses.AVAILABILITY_COURSE

        self.unit_two = self.course.add_unit()
        self.unit_two.title = 'Unit Two'
        self.unit_two.availability = courses.AVAILABILITY_COURSE
        self.link_two = self.course.add_link()
        self.link_two.title = 'Link Two'
        self.link_two.href = 'http://www.bar.com'
        self.link_two.availability = courses.AVAILABILITY_COURSE
        self.assessment_two = self.course.add_assessment()
        self.assessment_two.title = 'Assessment Two'
        self.assessment_two.availability = courses.AVAILABILITY_COURSE

        self.unit_three = self.course.add_unit()
        self.unit_three.title = 'Unit Three'
        self.unit_three.availability = courses.AVAILABILITY_COURSE
        self.link_three = self.course.add_link()
        self.link_three.title = 'Link Three'
        self.link_three.availability = courses.AVAILABILITY_COURSE
        self.assessment_three = self.course.add_assessment()
        self.assessment_three.title = 'Assessment Three'
        self.assessment_three.availability = courses.AVAILABILITY_COURSE

        self.lesson_one = self.course.add_lesson(self.unit_two)
        self.lesson_one.title = 'Lesson One'
        self.lesson_two = self.course.add_lesson(self.unit_two)
        self.lesson_two.title = 'Lesson Two'
        self.lesson_three = self.course.add_lesson(self.unit_two)
        self.lesson_three.title = 'Lesson Three'

        self.pre_assessment = self.course.add_assessment()
        self.pre_assessment.title = 'Pre Assessment'
        self.pre_assessment.availability = courses.AVAILABILITY_COURSE
        self.pre_assessment.workflow_yaml = (
            '{'
            '%s: %s, ' % (courses.GRADER_KEY, courses.HUMAN_GRADER) +
            '%s: %s, ' % (courses.MATCHER_KEY, review.PEER_MATCHER) +
            '%s: %s, ' % (courses.REVIEW_MIN_COUNT_KEY, 1) +
            '%s: %s, ' % (courses.REVIEW_DUE_DATE_KEY, '"2099-01-01 00:00"') +
            '%s: %s, ' % (courses.SUBMISSION_DUE_DATE_KEY,
                          '"2099-01-01 00:00"') +
            '}'
            )

        self.post_assessment = self.course.add_assessment()
        self.post_assessment.title = 'Post Assessment'
        self.post_assessment.availability = courses.AVAILABILITY_COURSE
        self.mid_lesson = self.course.add_lesson(self.unit_three)
        self.mid_lesson.title = 'Mid Lesson'
        self.unit_three.pre_assessment = self.pre_assessment.unit_id
        self.unit_three.post_assessment = self.post_assessment.unit_id

        self.lesson_zero = self.course.add_lesson(self.unit_one)
        self.lesson_zero.title = 'Lesson Zero'

        self.course.save()
        self.action_url = '/%s/dashboard?action=%s' % (
            self.COURSE_NAME, availability.AvailabilityRESTHandler.ACTION)
        self.rest_url = '/%s/%s' % (
            self.COURSE_NAME, availability.AvailabilityRESTHandler.URL)

    def _add_availability_permission(self):
        with common_utils.Namespace(self.NAMESPACE):
            role_dto = models.RoleDTO(None, {
                'name': self.ROLE,
                'users': [self.USER_EMAIL],
                'permissions': {
                    modules_courses.MODULE_NAME: [
                        constants.MODIFY_AVAILABILITY_PERMISSION]
                    }
                })
            models.RoleDAO.save(role_dto)

    def test_availability_page_unavailable_to_plain_users(self):
        # Requesting dashboard just jumps straight to course title page.
        actions.login(self.USER_EMAIL, is_admin=False)
        response = self.get(self.action_url)
        self.assertEquals(302, response.status_int)
        self.assertEquals(response.location, 'http://localhost/%s' %
                          self.COURSE_NAME)

    def test_availability_page_available_to_course_admin(self):
        actions.login(self.ADMIN_EMAIL, is_admin=True)
        response = self.get(self.action_url)
        self.assertEquals(200, response.status_int)

    def test_availability_page_accessable_with_permission(self):
        actions.login(self.USER_EMAIL)
        self._add_availability_permission()
        response = self.get(self.action_url)
        self.assertEquals(200, response.status_int)

    def test_availability_rest_handler_unavailable_to_plain_users(self):
        actions.login(self.USER_EMAIL)
        response = self.get(self.rest_url)
        self.assertEquals(response.status_int, 200)
        response = transforms.loads(response.body)
        self.assertEquals(response['status'], 401)
        self.assertEquals(response['message'], 'Access denied.')
        self.assertNotIn('payload', response)

    def test_availability_rest_handler_available_to_course_admin(self):
        actions.login(self.ADMIN_EMAIL, is_admin=True)
        response = self.get(self.rest_url)
        self.assertEquals(response.status_int, 200)
        response = transforms.loads(response.body)
        self.assertEquals(response['status'], 200)
        self.assertEquals(response['message'], 'OK.')
        self.assertIn('payload', response)

    def test_availability_rest_handler_available_with_permission(self):
        actions.login(self.USER_EMAIL)
        self._add_availability_permission()
        response = self.get(self.rest_url)
        self.assertEquals(response.status_int, 200)
        response = transforms.loads(response.body)
        self.assertEquals(response['status'], 200)
        self.assertEquals(response['message'], 'OK.')
        self.assertIn('payload', response)

    def _post(self, data):
        data = {
            'request': transforms.dumps({
                'xsrf_token': crypto.XsrfTokenManager.create_xsrf_token(
                    availability.AvailabilityRESTHandler.ACTION),
                'payload': transforms.dumps(data)
            })
        }
        return self.put(self.rest_url, data)

    def test_availability_post_as_plain_user(self):
        actions.login(self.USER_EMAIL)
        response = self._post({})
        self.assertEquals(response.status_int, 200)
        response = transforms.loads(response.body)
        self.assertEquals(401, response['status'])
        self.assertEquals('Access denied.', response['message'])

    def test_availability_post_as_admin(self):
        actions.login(self.ADMIN_EMAIL, is_admin=True)
        app_context = sites.get_app_context_for_namespace(self.NAMESPACE)
        self.assertEquals(
            app_context.get_environ()['reg_form']['whitelist'], '')
        response = self._post({'whitelist': self.USER_EMAIL})
        app_context = sites.get_app_context_for_namespace(self.NAMESPACE)
        self.assertEquals(
            app_context.get_environ()['reg_form']['whitelist'], self.USER_EMAIL)

    def test_availability_post_with_permission(self):
        actions.login(self.USER_EMAIL)
        self._add_availability_permission()
        app_context = sites.get_app_context_for_namespace(self.NAMESPACE)
        self.assertEquals(
            app_context.get_environ()['reg_form']['whitelist'], '')
        response = self._post({'whitelist': self.USER_EMAIL})
        app_context = sites.get_app_context_for_namespace(self.NAMESPACE)
        self.assertEquals(
            app_context.get_environ()['reg_form']['whitelist'], self.USER_EMAIL)

    def test_course_availability_private(self):
        actions.login(self.ADMIN_EMAIL, is_admin=True)
        self._post({'course_availability': 'private'})

        app_context = sites.get_app_context_for_namespace(self.NAMESPACE)
        self.assertEquals(
            app_context.get_environ()['course']['now_available'], False)
        self.assertEquals(
            app_context.get_environ()['course']['browsable'], False)
        self.assertEquals(
            app_context.get_environ()['reg_form']['can_register'], False)

        # User sees course page as 404.
        actions.login(self.USER_EMAIL)
        response = self.get('/%s/course' % self.COURSE_NAME, expect_errors=True)
        self.assertEquals(response.status_int, 404)

    def test_course_availability_registration_required(self):
        actions.login(self.ADMIN_EMAIL, is_admin=True)
        self._post({'course_availability': 'registration_required'})
        app_context = sites.get_app_context_for_namespace(self.NAMESPACE)
        self.assertEquals(
            app_context.get_environ()['course']['now_available'], True)
        self.assertEquals(
            app_context.get_environ()['course']['browsable'], False)
        self.assertEquals(
            app_context.get_environ()['reg_form']['can_register'], True)

        actions.login(self.USER_EMAIL)
        response = self.get('/%s/course' % self.COURSE_NAME)
        self.assertEquals(response.status_int, 200)
        dom = self.parse_html_string(response.body)
        links = [l.text.strip() for l in dom.findall('.//a')]
        self.assertIn('Register', links)

    def test_course_availability_registration_optional(self):
        actions.login(self.ADMIN_EMAIL, is_admin=True)
        self._post({'course_availability': 'registration_optional'})
        app_context = sites.get_app_context_for_namespace(self.NAMESPACE)
        self.assertEquals(
            app_context.get_environ()['course']['now_available'], True)
        self.assertEquals(
            app_context.get_environ()['course']['browsable'], True)
        self.assertEquals(
            app_context.get_environ()['reg_form']['can_register'], True)

        actions.login(self.USER_EMAIL)
        response = self.get('/%s/course' % self.COURSE_NAME)
        self.assertEquals(response.status_int, 200)
        dom = self.parse_html_string(response.body)
        links = [l.text.strip() for l in dom.findall('.//a')]
        self.assertIn('Register', links)

    def test_course_availability_public(self):
        actions.login(self.ADMIN_EMAIL, is_admin=True)
        self._post({'course_availability': 'public'})
        app_context = sites.get_app_context_for_namespace(self.NAMESPACE)
        self.assertEquals(
            app_context.get_environ()['course']['now_available'], True)
        self.assertEquals(
            app_context.get_environ()['course']['browsable'], True)
        self.assertEquals(
            app_context.get_environ()['reg_form']['can_register'], False)

        actions.login(self.USER_EMAIL)
        response = self.get('/%s/course' % self.COURSE_NAME)
        self.assertEquals(response.status_int, 200)
        dom = self.parse_html_string(response.body)
        links = [l.text.strip() for l in dom.findall('.//a')]
        self.assertNotIn('Register', links)

    def _parse_nav_level(self, owning_item):
        ret = []
        prev_item = None
        for item in owning_item.findall('./*') if owning_item else []:
            if item.tag == 'li':
                text = ' '.join((''.join(item.itertext())).strip().split())
                a_tag = item.find('.//a')
                link = a_tag.get('href') if a_tag is not None else None
                progress = None
                img_tag = item.find('.//img[@class="gcb-progress-icon"]')
                if img_tag is not None:
                    progress = img_tag.get('id')
                prev_item = Element(text, link, progress, [])
                ret.append(prev_item)
            elif (item.tag == 'ul' or
                  (item.tag == 'div' and
                   'gcb-lesson-container' in item.get('class'))):
                prev_item.contents.extend(self._parse_nav_level(item))
        return ret

    def _parse_leftnav(self, response):
        dom = self.parse_html_string(response.body)
        item = dom.find('.//div[@id="gcb-nav-y"]/ul')
        return self._parse_nav_level(item)

    def test_syllabus_reg_required_elements_private(self):
        self.unit_one.availability = courses.AVAILABILITY_UNAVAILABLE
        self.link_one.availability = courses.AVAILABILITY_UNAVAILABLE
        self.assessment_one.availability = courses.AVAILABILITY_UNAVAILABLE
        self.unit_two.availability = courses.AVAILABILITY_UNAVAILABLE
        self.link_two.availability = courses.AVAILABILITY_UNAVAILABLE
        self.assessment_two.availability = courses.AVAILABILITY_UNAVAILABLE
        self.unit_three.availability = courses.AVAILABILITY_UNAVAILABLE
        self.link_three.availability = courses.AVAILABILITY_UNAVAILABLE
        self.assessment_three.availability = courses.AVAILABILITY_UNAVAILABLE
        self.course.save()

        self.course.set_course_availability(
            courses.COURSE_AVAILABILITY_REGISTRATION_REQUIRED)

        # Check as non-logged-in user; not even "Syllabus" should show.
        response = self.get('course')
        self.assertNotIn('Syllabus', response.body)
        self.assertEquals([], self._parse_leftnav(response))

        # Check as logged-in user;  not even "Syllabus" should show.
        actions.login(self.USER_EMAIL, is_admin=False)
        response = self.get('course')
        self.assertNotIn('Syllabus', response.body)
        self.assertEquals([], self._parse_leftnav(response))

        # Registered students see no items.
        actions.register(self, self.USER_EMAIL)
        response = self.get('course')
        self.assertNotIn('Syllabus', response.body)
        self.assertEquals([], self._parse_leftnav(response))

        # Check as admin; all should show and be linked, but marked as (Private)
        actions.login(self.ADMIN_EMAIL, is_admin=True)
        response = self.get('course')
        self.assertIn('Syllabus', response.body)
        expected = [
            Element('Unit 1 - Unit One (Private)', 'unit?unit=1', None, []),
            Element('Link One (Private)', 'http://www.foo.com', None, []),
            Element('Assessment One (Private)', 'assessment?name=3', None, []),
            Element('Unit 2 - Unit Two (Private)', 'unit?unit=4', None, []),
            Element('Link Two (Private)', 'http://www.bar.com', None, []),
            Element('Assessment Two (Private)', 'assessment?name=6', None, []),
            Element('Unit 3 - Unit Three (Private)', 'unit?unit=7', None, []),
            Element('Link Three (Private)', None, None, []),
            Element('Assessment Three (Private)', 'assessment?name=9', None, [])
            ]
        self.assertEquals(expected, self._parse_leftnav(response))

    def test_syllabus_reg_required_elements_same_as_course(self):
        with actions.OverriddenEnvironment({'course': {
                'can_record_student_events': False}}):

            self.course.set_course_availability(
                courses.COURSE_AVAILABILITY_REGISTRATION_REQUIRED)

            # Not-even-logged-in users see syllabus items, but no links.
            actions.logout()
            self.assertEquals(self.TOP_LEVEL_NO_LINKS_NO_PROGRESS,
                              self._parse_leftnav(self.get('course')))

            # Non-students see syllabus, but nothing is linked.
            actions.login(self.USER_EMAIL, is_admin=False)
            self.assertEquals(self.TOP_LEVEL_NO_LINKS_NO_PROGRESS,
                              self._parse_leftnav(self.get('course')))

            # Registered tudents see syllabus with links and assessment
            # progress.
            actions.register(self, self.USER_EMAIL)
            self.assertEquals(self.TOP_LEVEL_WITH_LINKS_ASSESSMENT_PROGRESS,
                              self._parse_leftnav(self.get('course')))

            # Admins see syllabus; no (Private) or (Public); all are linked.
            # (Since admin is not also a registered student, no progress
            # indicators) appear
            actions.login(self.ADMIN_EMAIL, is_admin=True)
            self.assertEquals(self.TOP_LEVEL_WITH_LINKS_NO_PROGRESS,
                              self._parse_leftnav(self.get('course')))

    def test_syllabus_reg_required_elements_public(self):
        self.unit_one.availability = courses.AVAILABILITY_AVAILABLE
        self.link_one.availability = courses.AVAILABILITY_AVAILABLE
        self.assessment_one.availability = courses.AVAILABILITY_AVAILABLE
        self.unit_two.availability = courses.AVAILABILITY_AVAILABLE
        self.link_two.availability = courses.AVAILABILITY_AVAILABLE
        self.assessment_two.availability = courses.AVAILABILITY_AVAILABLE
        self.unit_three.availability = courses.AVAILABILITY_AVAILABLE
        self.link_three.availability = courses.AVAILABILITY_AVAILABLE
        self.assessment_three.availability = courses.AVAILABILITY_AVAILABLE
        self.course.save()

        self.course.set_course_availability(
            courses.COURSE_AVAILABILITY_REGISTRATION_REQUIRED)

        with actions.OverriddenEnvironment({'course': {
                'can_record_student_events': False}}):

            # Not-even-logged-in users see titles of everything.
            # Still get links to units even if they have no content.
            actions.logout()
            self.assertEquals(self.TOP_LEVEL_WITH_LINKS_NO_PROGRESS,
                              self._parse_leftnav(self.get('course')))

            # Non-students see links to all content, but still no progress.
            actions.login(self.USER_EMAIL, is_admin=False)
            self.assertEquals(self.TOP_LEVEL_WITH_LINKS_NO_PROGRESS,
                              self._parse_leftnav(self.get('course')))

            # Students see syllabus with links.
            actions.register(self, self.USER_EMAIL)
            self.assertEquals(self.TOP_LEVEL_WITH_LINKS_ASSESSMENT_PROGRESS,
                              self._parse_leftnav(self.get('course')))

            # Admins see syllabus; all marked (Public); all are linked.
            actions.login(self.ADMIN_EMAIL, is_admin=True)
            expected = [
                Element('Unit 1 - Unit One (Public)', 'unit?unit=1', None, []),
                Element('Link One (Public)', 'http://www.foo.com', None, []),
                Element(
                    'Assessment One (Public)', 'assessment?name=3', None, []),
                Element('Unit 2 - Unit Two (Public)', 'unit?unit=4', None, []),
                Element('Link Two (Public)', 'http://www.bar.com', None, []),
                Element(
                    'Assessment Two (Public)', 'assessment?name=6', None, []),
                Element(
                    'Unit 3 - Unit Three (Public)', 'unit?unit=7', None, []),
                Element('Link Three (Public)', None, None, []),
                Element(
                    'Assessment Three (Public)', 'assessment?name=9', None, [])]
            self.assertEquals(expected, self._parse_leftnav(self.get('course')))

        # Now make lessons public as well; non-registered students should
        # now see links to units.
        self.lesson_zero.availability = courses.AVAILABILITY_AVAILABLE
        self.lesson_one.availability = courses.AVAILABILITY_AVAILABLE
        self.mid_lesson.availability = courses.AVAILABILITY_AVAILABLE
        self.course.save()
        actions.logout()
        self.assertEquals(self.TOP_LEVEL_WITH_LINKS_NO_PROGRESS,
                          self._parse_leftnav(self.get('course')))

    def test_syllabus_reg_optional_elements_private(self):
        self.unit_one.availability = courses.AVAILABILITY_UNAVAILABLE
        self.link_one.availability = courses.AVAILABILITY_UNAVAILABLE
        self.assessment_one.availability = courses.AVAILABILITY_UNAVAILABLE
        self.unit_two.availability = courses.AVAILABILITY_UNAVAILABLE
        self.link_two.availability = courses.AVAILABILITY_UNAVAILABLE
        self.assessment_two.availability = courses.AVAILABILITY_UNAVAILABLE
        self.unit_three.availability = courses.AVAILABILITY_UNAVAILABLE
        self.link_three.availability = courses.AVAILABILITY_UNAVAILABLE
        self.assessment_three.availability = courses.AVAILABILITY_UNAVAILABLE
        self.course.save()

        for _availability in (
            courses.COURSE_AVAILABILITY_REGISTRATION_OPTIONAL,
            courses.COURSE_AVAILABILITY_PUBLIC):
            self.course.set_course_availability(_availability)

            # Check as non-logged-in user; not even "Syllabus" should show.
            actions.logout()
            response = self.get('course')
            self.assertNotIn('Syllabus', response.body)
            self.assertEquals([], self._parse_leftnav(response))

            # Check as logged-in user;  not even "Syllabus" should show.
            actions.login(self.USER_EMAIL, is_admin=False)
            response = self.get('course')
            self.assertNotIn('Syllabus', response.body)
            self.assertEquals([], self._parse_leftnav(response))

            if _availability != courses.COURSE_AVAILABILITY_PUBLIC:
                # Registered students see no items.
                actions.register(self, self.USER_EMAIL)
                response = self.get('course')
                self.assertNotIn('Syllabus', response.body)
                self.assertEquals([], self._parse_leftnav(response))

            # Check as admin; all should show and be linked, but
            # marked as (Private)
            actions.login(self.ADMIN_EMAIL, is_admin=True)
            response = self.get('course')
            self.assertIn('Syllabus', response.body)
            expected = [
                Element(
                    'Unit 1 - Unit One (Private)', 'unit?unit=1', None, []),
                Element(
                    'Link One (Private)', 'http://www.foo.com', None, []),
                Element(
                    'Assessment One (Private)', 'assessment?name=3', None, []),
                Element(
                    'Unit 2 - Unit Two (Private)', 'unit?unit=4', None, []),
                Element(
                    'Link Two (Private)', 'http://www.bar.com', None, []),
                Element(
                    'Assessment Two (Private)', 'assessment?name=6', None, []),
                Element(
                    'Unit 3 - Unit Three (Private)', 'unit?unit=7', None, []),
                Element(
                    'Link Three (Private)', None, None, []),
                Element(
                    'Assessment Three (Private)', 'assessment?name=9', None, [])
                ]
            self.assertEquals(expected, self._parse_leftnav(response))

    def test_syllabus_reg_optional_elements_same_as_course(self):
        with actions.OverriddenEnvironment({'course': {
                'can_record_student_events': False}}):

            for _availability in (
                courses.COURSE_AVAILABILITY_REGISTRATION_OPTIONAL,
                courses.COURSE_AVAILABILITY_PUBLIC):
                self.course.set_course_availability(_availability)

                # Check as non-logged-in user
                actions.logout()
                self.assertEquals(self.TOP_LEVEL_WITH_LINKS_NO_PROGRESS,
                                  self._parse_leftnav(self.get('course')))

                # Check as logged-in user
                actions.login(self.USER_EMAIL, is_admin=False)
                self.assertEquals(self.TOP_LEVEL_WITH_LINKS_NO_PROGRESS,
                                  self._parse_leftnav(self.get('course')))

                # As registered student.  Registration only available with
                # registration-optional; browse-only courses do not support
                # this.
                if _availability != courses.COURSE_AVAILABILITY_PUBLIC:
                    actions.register(self, self.USER_EMAIL)
                    self.assertEquals(
                        self.TOP_LEVEL_WITH_LINKS_ASSESSMENT_PROGRESS,
                        self._parse_leftnav(self.get('course')))
                    actions.unregister(self)

                # Check as admin
                actions.login(self.ADMIN_EMAIL, is_admin=True)
                self.assertEquals(self.TOP_LEVEL_WITH_LINKS_NO_PROGRESS,
                                  self._parse_leftnav(self.get('course')))

    def test_syllabus_reg_optional_elements_public(self):
        self.unit_one.availability = courses.AVAILABILITY_AVAILABLE
        self.link_one.availability = courses.AVAILABILITY_AVAILABLE
        self.assessment_one.availability = courses.AVAILABILITY_AVAILABLE
        self.unit_two.availability = courses.AVAILABILITY_AVAILABLE
        self.link_two.availability = courses.AVAILABILITY_AVAILABLE
        self.assessment_two.availability = courses.AVAILABILITY_AVAILABLE
        self.unit_three.availability = courses.AVAILABILITY_AVAILABLE
        self.link_three.availability = courses.AVAILABILITY_AVAILABLE
        self.assessment_three.availability = courses.AVAILABILITY_AVAILABLE
        self.course.save()

        with actions.OverriddenEnvironment({'course': {
                'can_record_student_events': False}}):

            for _availability in (
                courses.COURSE_AVAILABILITY_REGISTRATION_OPTIONAL,
                courses.COURSE_AVAILABILITY_PUBLIC):
                self.course.set_course_availability(_availability)

                # Check as non-logged-in user.
                self.assertEquals(self.TOP_LEVEL_WITH_LINKS_NO_PROGRESS,
                                  self._parse_leftnav(self.get('course')))

                # Check as logged-in user.
                actions.login(self.USER_EMAIL, is_admin=False)
                self.assertEquals(self.TOP_LEVEL_WITH_LINKS_NO_PROGRESS,
                                  self._parse_leftnav(self.get('course')))

                # As registered user (only meaningful when registration is
                # available)
                if _availability != courses.COURSE_AVAILABILITY_PUBLIC:
                    actions.register(self, self.USER_EMAIL)
                    self.assertEquals(
                        self.TOP_LEVEL_WITH_LINKS_ASSESSMENT_PROGRESS,
                        self._parse_leftnav(self.get('course')))
                    actions.unregister(self)

                # Check as admin; all should show and be linked.  No
                # public/private markers, since all items are available to all.
                actions.login(self.ADMIN_EMAIL, is_admin=True)
                self.assertEquals(self.TOP_LEVEL_WITH_LINKS_NO_PROGRESS,
                                  self._parse_leftnav(self.get('course')))
                actions.logout()

    def test_syllabus_with_lessons(self):
        self.course.set_course_availability(
            courses.COURSE_AVAILABILITY_REGISTRATION_REQUIRED)
        with actions.OverriddenEnvironment({'course': {
                'show_lessons_in_syllabus': True,
                'can_record_student_events': False}}):

            # Check as non-logged-in user; labels but no links or progress.
            self.assertEquals(self.ALL_LEVELS_NO_LINKS_NO_PROGRESS,
                              self._parse_leftnav(self.get('course')))

            # Check as logged-in user; labels but no links or progress.
            actions.login(self.USER_EMAIL, is_admin=False)
            self.assertEquals(self.ALL_LEVELS_NO_LINKS_NO_PROGRESS,
                              self._parse_leftnav(self.get('course')))

            # Registered students see links and progress for assessments and
            # peer-reviews.
            actions.register(self, self.USER_EMAIL)
            self.assertEquals(self.ALL_LEVELS_WITH_LINKS_ASSESSMENT_PROGRESS,
                              self._parse_leftnav(self.get('course')))

            # Admins see syllabus; no (Private) or (Public); all are linked.
            actions.login(self.ADMIN_EMAIL, is_admin=True)
            self.assertEquals(self.ALL_LEVELS_WITH_LINKS_NO_PROGRESS,
                              self._parse_leftnav(self.get('course')))

    def test_unit_view_shows_only_this_units_links(self):
        with actions.OverriddenEnvironment({
            'unit': {'show_unit_links_in_leftnav': False}}):

            # Note that here, we expect to _not_ have a link for the
            # first item, despite the fact that the user is entitled to
            # see it.  This is suppressed, since that's the page the user
            # is currently viewing.
            expected = [
                Element('Pre Assessment', None, progress=None, contents=[]),
                Element('3.1 Mid Lesson', 'unit?unit=7&lesson=15', None, []),
                Element('Post Assessment', 'unit?unit=7&assessment=14',
                        None, [])
                ]
            response = self.get('unit?unit=%s' % self.unit_three.unit_id)
            self.assertEquals(expected, self._parse_leftnav(response))

            # Same thing again; just make sure that when we look at the
            # middle thing, the link for the first thing shows up and the
            # link for the middle thing disappears.
            expected = [
                Element('Pre Assessment', 'unit?unit=7&assessment=13',
                        None, contents=[]),
                Element('3.1 Mid Lesson', None, None, []),
                Element('Post Assessment', 'unit?unit=7&assessment=14',
                        None, [])
                ]
            response = self.get('unit?unit=%s&lesson=%s' % (
                self.unit_three.unit_id, self.mid_lesson.lesson_id))
            self.assertEquals(expected, self._parse_leftnav(response))

    def test_unit_view_shows_all_unit_links(self):
        with actions.OverriddenEnvironment({
            'unit': {'show_unit_links_in_leftnav': True}}):

            actions.login(self.ADMIN_EMAIL, is_admin=True)
            response = self.get('unit?unit=%s' % self.unit_three.unit_id)
            actual = self._parse_leftnav(response)

            # We expect to not have links to unit 3, and to its first
            # element (the pre-assessment and the peer-review of same)
            # since that's what's open.
            replacement = Element('Unit 3 - Unit Three', None, None, contents=[
                Element('Pre Assessment', None, None, []),
                Element('Review peer assignments', None, None, []),
                Element('3.1 Mid Lesson', 'unit?unit=7&lesson=15', None, []),
                Element('Post Assessment', 'unit?unit=7&assessment=14',
                        None, []),
                ])
            expected = copy.deepcopy(self.ALL_LEVELS_WITH_LINKS_NO_PROGRESS)
            replace_at_index = expected.index(
                common_utils.find(lambda x: x.text == 'Unit 3 - Unit Three',
                                  expected))
            expected[replace_at_index] = replacement
            self.assertEquals(expected, actual)

    def test_unavailable_owning_unit_does_not_override_lesson_publicness(self):
        # Only experimenting on unit_two; make other items non-visible
        # to shorten expected results constants.
        self.unit_one.availability = courses.AVAILABILITY_UNAVAILABLE
        self.link_one.availability = courses.AVAILABILITY_UNAVAILABLE
        self.assessment_one.availability = courses.AVAILABILITY_UNAVAILABLE
        self.link_two.availability = courses.AVAILABILITY_UNAVAILABLE
        self.assessment_two.availability = courses.AVAILABILITY_UNAVAILABLE
        self.unit_three.availability = courses.AVAILABILITY_UNAVAILABLE
        self.link_three.availability = courses.AVAILABILITY_UNAVAILABLE
        self.assessment_three.availability = courses.AVAILABILITY_UNAVAILABLE
        self.course.save()

        self.unit_two.availability = courses.AVAILABILITY_UNAVAILABLE
        self.lesson_one.availability = courses.AVAILABILITY_UNAVAILABLE
        self.lesson_two.availability = courses.AVAILABILITY_COURSE
        self.lesson_three.availability = courses.AVAILABILITY_AVAILABLE
        self.course.save()

        self.course.set_course_availability(
            courses.COURSE_AVAILABILITY_REGISTRATION_REQUIRED)

        # Check this from syllabus; don't want link suppression for active
        # lesson to confound the issue.
        with actions.OverriddenEnvironment({'course': {
                'show_lessons_in_syllabus': True,
                'can_record_student_events': False}}):

            # Check as non-logged-in user; not even "Syllabus" should show.
            actions.logout()
            response = self.get('course')
            self.assertNotIn('Syllabus', response.body)
            self.assertEquals([], self._parse_leftnav(response))

            # Ditto for logged-in user.
            actions.login(self.USER_EMAIL, is_admin=False)
            response = self.get('course')
            self.assertNotIn('Syllabus', response.body)
            self.assertEquals([], self._parse_leftnav(response))

            # Registered students see no items.
            actions.register(self, self.USER_EMAIL)
            response = self.get('course')
            self.assertNotIn('Syllabus', response.body)
            self.assertEquals([], self._parse_leftnav(response))
            actions.unregister(self)

        self.unit_two.availability = courses.AVAILABILITY_COURSE
        self.course.save()

        # Check this from syllabus; don't want link suppression for active
        # lesson to confound the issue.
        with actions.OverriddenEnvironment({'course': {
            'show_lessons_in_syllabus': True,
            'can_record_student_events': False}}):

            # Check as non-logged-in user; unit visible, last two items
            # should be visible, and lesson3 should be linkable, since it
            # is marked as public.
            actions.logout()
            response = self.get('course')
            self.assertEquals([
                Element('Unit 2 - Unit Two', None, None, contents=[
                    Element('2.2 Lesson Two', None, None, []),
                    Element('2.3 Lesson Three', 'unit?unit=4&lesson=12',
                            None, [])])],
                self._parse_leftnav(response))

            # Ditto for logged-in user
            actions.login(self.USER_EMAIL, is_admin=False)
            response = self.get('course')
            self.assertEquals([
                Element('Unit 2 - Unit Two', None, None, contents=[
                    Element('2.2 Lesson Two', None, None, []),
                    Element('2.3 Lesson Three', 'unit?unit=4&lesson=12',
                            None, [])])],
                self._parse_leftnav(response))

            # Registered students see both available lessons.
            actions.register(self, self.USER_EMAIL)
            response = self.get('course')
            self.assertEquals([
                Element('Unit 2 - Unit Two', 'unit?unit=4', None, [
                    Element('2.2 Lesson Two', 'unit?unit=4&lesson=11',
                            None, []),
                    Element('2.3 Lesson Three', 'unit?unit=4&lesson=12'
                            , None, []),
                    ])],
                self._parse_leftnav(response))
            actions.unregister(self)

        self.unit_two.availability = courses.AVAILABILITY_AVAILABLE
        self.course.save()

        # Check this from syllabus; don't want link suppression for active
        # lesson to confound the issue.
        with actions.OverriddenEnvironment({'course': {
            'show_lessons_in_syllabus': True,
            'can_record_student_events': False}}):

            # Check as non-logged-in user; unit visible and linkable;
            # 1st unit still not visible; 2nd visible only, 3rd linkable.
            actions.logout()
            response = self.get('course')
            self.assertEquals([
                Element('Unit 2 - Unit Two', 'unit?unit=4', None, [
                    Element('2.2 Lesson Two', None, None, []),
                    Element('2.3 Lesson Three', 'unit?unit=4&lesson=12',
                            None, [])])],
                self._parse_leftnav(response))

            # Ditto for logged-in user
            actions.login(self.USER_EMAIL, is_admin=False)
            response = self.get('course')
            self.assertEquals([
                Element('Unit 2 - Unit Two', 'unit?unit=4', None, [
                    Element('2.2 Lesson Two', None, None, []),
                    Element('2.3 Lesson Three', 'unit?unit=4&lesson=12',
                            None, [])])],
                self._parse_leftnav(response))

            # Registered students see both available lessons.
            actions.register(self, self.USER_EMAIL)
            response = self.get('course')
            self.assertEquals([
                Element('Unit 2 - Unit Two', 'unit?unit=4', None, [
                    Element('2.2 Lesson Two', 'unit?unit=4&lesson=11',
                            None, []),
                    Element('2.3 Lesson Three', 'unit?unit=4&lesson=12',
                            None, [])])],
                self._parse_leftnav(response))
            actions.unregister(self)

    def test_assessment_progress(self):
        # Hide irrelevant items.
        self.unit_one.availability = courses.AVAILABILITY_UNAVAILABLE
        self.link_one.availability = courses.AVAILABILITY_UNAVAILABLE
        self.unit_two.availability = courses.AVAILABILITY_UNAVAILABLE
        self.link_two.availability = courses.AVAILABILITY_UNAVAILABLE
        self.assessment_two.availability = courses.AVAILABILITY_UNAVAILABLE
        self.unit_three.availability = courses.AVAILABILITY_UNAVAILABLE
        self.link_three.availability = courses.AVAILABILITY_UNAVAILABLE
        self.assessment_three.availability = courses.AVAILABILITY_UNAVAILABLE
        self.course.save()
        self.course.set_course_availability(
            courses.COURSE_AVAILABILITY_REGISTRATION_REQUIRED)

        actions.login(self.USER_EMAIL)
        actions.register(self, self.USER_EMAIL)

        # Verify behavior on a top-level assessment
        response = self.get('course')
        expected = [
            Element('Assessment One', 'assessment?name=3',
                    'progress-notstarted-3', [])]
        self.assertEquals(self._parse_leftnav(response), expected)
        self.post('answer', {
            'xsrf_token': crypto.XsrfTokenManager.create_xsrf_token(
                'assessment-post'),
            'assessment_type': '%s' % self.assessment_one.unit_id,
            'score': 1,
            })
        response = self.get('course')
        expected = [
            Element('Assessment One', 'assessment?name=3',
                    'progress-completed-3', [])]
        self.assertEquals(self._parse_leftnav(response), expected)

    def test_peer_reviewed_assessment_progress(self):
        # Hide irrelevant items.
        self.unit_one.availability = courses.AVAILABILITY_UNAVAILABLE
        self.link_one.availability = courses.AVAILABILITY_UNAVAILABLE
        self.assessment_one.availability = courses.AVAILABILITY_UNAVAILABLE
        self.unit_two.availability = courses.AVAILABILITY_UNAVAILABLE
        self.link_two.availability = courses.AVAILABILITY_UNAVAILABLE
        self.assessment_two.availability = courses.AVAILABILITY_UNAVAILABLE
        self.link_three.availability = courses.AVAILABILITY_UNAVAILABLE
        self.assessment_three.availability = courses.AVAILABILITY_UNAVAILABLE
        self.course.save()
        self.course.set_course_availability(
            courses.COURSE_AVAILABILITY_REGISTRATION_REQUIRED)
        with actions.OverriddenEnvironment({'course': {
                'show_lessons_in_syllabus': True,
                'can_record_student_events': False}}):

            # Logged in but non-student doesn't even see peer review
            actions.login(self.USER_EMAIL)
            expected = [
                Element('Unit 3 - Unit Three', None, None, [
                    Element('Pre Assessment', None, None, []),
                    Element('3.1 Mid Lesson', None, None, []),
                    Element('Post Assessment', None, None, [])])]
            response = self.get('course')
            self.assertEquals(expected, self._parse_leftnav(response))

            # Peer-review step visible, but not linked until assessment
            # submitted.
            actions.register(self, self.USER_EMAIL)
            expected = [
                Element('Unit 3 - Unit Three', 'unit?unit=7', None, [
                    Element('Pre Assessment', 'unit?unit=7&assessment=13',
                            'progress-notstarted-13', []),
                    Element('Review peer assignments', None,
                            'progress-notstarted-13', []),
                    Element('3.1 Mid Lesson', 'unit?unit=7&lesson=15',
                            None, []),
                    Element('Post Assessment', 'unit?unit=7&assessment=14',
                            'progress-notstarted-14', [])])]
            response = self.get('course')
            self.assertEquals(expected, self._parse_leftnav(response))
            expected = [
                Element('Pre Assessment', None, 'progress-notstarted-13', []),
                Element('Review peer assignments', None,
                        'progress-notstarted-13', []),
                Element('3.1 Mid Lesson', 'unit?unit=7&lesson=15',
                        None, []),
                Element('Post Assessment', 'unit?unit=7&assessment=14',
                        'progress-notstarted-14', [])]
            response = self.get('unit?unit=7')
            self.assertEquals(expected, self._parse_leftnav(response))

            # Submit a set of answers to the assessment.  Verify that
            # assessment completion is now completed, and peer review
            # progress is marked as not-started.
            self.post('answer', {
                'xsrf_token': crypto.XsrfTokenManager.create_xsrf_token(
                    'assessment-post'),
                'assessment_type': '%s' % self.pre_assessment.unit_id,
                'score': 1,
                })

            expected = [
                Element('Unit 3 - Unit Three', 'unit?unit=7', None, [
                    Element('Pre Assessment', 'unit?unit=7&assessment=13',
                            'progress-completed-13', []),
                    Element('Review peer assignments',
                            'reviewdashboard?unit=13',
                            'progress-notstarted-13', []),
                    Element('3.1 Mid Lesson', 'unit?unit=7&lesson=15',
                            None, []),
                    Element('Post Assessment', 'unit?unit=7&assessment=14',
                            'progress-notstarted-14', [])])]
            response = self.get('course')
            self.assertEquals(expected, self._parse_leftnav(response))
            expected = [
                Element('Pre Assessment', None, 'progress-completed-13', []),
                Element('Review peer assignments',
                        'reviewdashboard?unit=13',
                        'progress-notstarted-13', []),
                Element('3.1 Mid Lesson', 'unit?unit=7&lesson=15',
                        None, []),
                Element('Post Assessment', 'unit?unit=7&assessment=14',
                        'progress-notstarted-14', [])]
            response = self.get('unit?unit=7')
            self.assertEquals(expected, self._parse_leftnav(response))

            # Become another student and submit that assessment, so first
            # student has something to review.
            other_email = 'peer@bar.com'
            actions.login(other_email)
            actions.register(self, other_email)
            self.post('answer', {
                'xsrf_token': crypto.XsrfTokenManager.create_xsrf_token(
                    'assessment-post'),
                'assessment_type': '%s' % self.pre_assessment.unit_id,
                'score': 1,
                })
            actions.login(self.USER_EMAIL)

            # Request a review to do.
            response = self.post('reviewdashboard', {
                'xsrf_token': crypto.XsrfTokenManager.create_xsrf_token(
                    'review-dashboard-post'),
                'unit': '%s' % self.pre_assessment.unit_id})
            self.assertEquals(response.status_int, 302)
            parts = urlparse.urlparse(response.location)
            params = urlparse.parse_qs(parts.query)
            key = params['key']  # Get ID of the review we have been assigned.

            # Progress should now show as in-progress.
            expected = [
                Element('Unit 3 - Unit Three', 'unit?unit=7', None, [
                    Element('Pre Assessment', 'unit?unit=7&assessment=13',
                            'progress-completed-13', []),
                    Element('Review peer assignments',
                            'reviewdashboard?unit=13',
                            'progress-inprogress-13', []),
                    Element('3.1 Mid Lesson', 'unit?unit=7&lesson=15',
                            None, []),
                    Element('Post Assessment', 'unit?unit=7&assessment=14',
                            'progress-notstarted-14', [])])]
            response = self.get('course')
            self.assertEquals(expected, self._parse_leftnav(response))
            expected = [
                Element('Pre Assessment', None, 'progress-completed-13', []),
                Element('Review peer assignments',
                        'reviewdashboard?unit=13',
                        'progress-inprogress-13', []),
                Element('3.1 Mid Lesson', 'unit?unit=7&lesson=15',
                        None, []),
                Element('Post Assessment', 'unit?unit=7&assessment=14',
                        'progress-notstarted-14', [])]
            response = self.get('unit?unit=7')
            self.assertEquals(expected, self._parse_leftnav(response))

            # Submit the review.
            self.post('review', {
                'xsrf_token': crypto.XsrfTokenManager.create_xsrf_token(
                    'review-post'),
                'unit_id': '%s' % self.pre_assessment.unit_id,
                'key': key,
                'is_draft': 'false',
                })

            expected = [
                Element('Unit 3 - Unit Three', 'unit?unit=7', None, [
                    Element('Pre Assessment', 'unit?unit=7&assessment=13',
                            'progress-completed-13', []),
                    Element('Review peer assignments',
                            'reviewdashboard?unit=13',
                            'progress-completed-13', []),
                    Element('3.1 Mid Lesson', 'unit?unit=7&lesson=15',
                            None, []),
                    Element('Post Assessment', 'unit?unit=7&assessment=14',
                            'progress-notstarted-14', [])])]
            response = self.get('course')
            self.assertEquals(expected, self._parse_leftnav(response))
            expected = [
                Element('Pre Assessment', None, 'progress-completed-13', []),
                Element('Review peer assignments',
                        'reviewdashboard?unit=13',
                        'progress-completed-13', []),
                Element('3.1 Mid Lesson', 'unit?unit=7&lesson=15',
                        None, []),
                Element('Post Assessment', 'unit?unit=7&assessment=14',
                        'progress-notstarted-14', [])]
            response = self.get('unit?unit=7')
            self.assertEquals(expected, self._parse_leftnav(response))

    def test_unit_progress_shown(self):
        # Hide irrelevant items.
        self.unit_one.availability = courses.AVAILABILITY_UNAVAILABLE
        self.link_one.availability = courses.AVAILABILITY_UNAVAILABLE
        self.assessment_one.availability = courses.AVAILABILITY_UNAVAILABLE

        self.link_two.availability = courses.AVAILABILITY_UNAVAILABLE
        self.assessment_two.availability = courses.AVAILABILITY_UNAVAILABLE
        self.unit_three.availability = courses.AVAILABILITY_UNAVAILABLE
        self.link_three.availability = courses.AVAILABILITY_UNAVAILABLE
        self.assessment_three.availability = courses.AVAILABILITY_UNAVAILABLE
        self.course.save()
        self.course.set_course_availability(
            courses.COURSE_AVAILABILITY_REGISTRATION_REQUIRED)

        actions.login(self.USER_EMAIL)
        actions.register(self, self.USER_EMAIL)

        with actions.OverriddenEnvironment({
            'course': {
                'show_lessons_in_syllabus': True,
                'can_record_student_events': True,
                }
            }):

            expected = [
                Element('Unit 2 - Unit Two', 'unit?unit=4',
                        'progress-notstarted-4', [
                    Element('2.1 Lesson One', 'unit?unit=4&lesson=10',
                            'progress-notstarted-10', []),
                    Element('2.2 Lesson Two', 'unit?unit=4&lesson=11',
                            'progress-notstarted-11', []),
                    Element('2.3 Lesson Three', 'unit?unit=4&lesson=12',
                            'progress-notstarted-12', [])])]
            response = self.get('course')
            self.assertEquals(expected, self._parse_leftnav(response))

            # Visit lesson two, then check progress.  Upon very first visit,
            # progress is recorded, but not reported to the page.  Thus,
            # the progress for "Lesson Two" is still not-started.
            response = self.get('unit?unit=4&lesson=11')
            expected = [
                Element(text=u'2.1 Lesson One', link=u'unit?unit=4&lesson=10',
                        progress=u'progress-notstarted-10', contents=[]),
                Element(text=u'2.2 Lesson Two', link=None,
                        progress=u'progress-notstarted-11', contents=[]),
                Element(text=u'2.3 Lesson Three', link=u'unit?unit=4&lesson=12',
                        progress=u'progress-notstarted-12', contents=[])]
            self.assertEquals(expected, self._parse_leftnav(response))

            # Check state of progress on syllabus; Lesson Two should show as
            # complete.  (No in-progress for lessons).  Unit is now in-progress
            # because it's partly done.
            expected = [
                Element('Unit 2 - Unit Two', 'unit?unit=4',
                        'progress-inprogress-4', [
                    Element('2.1 Lesson One', 'unit?unit=4&lesson=10',
                            'progress-notstarted-10', []),
                    Element('2.2 Lesson Two', 'unit?unit=4&lesson=11',
                            'progress-completed-11', []),
                    Element('2.3 Lesson Three', 'unit?unit=4&lesson=12',
                            'progress-notstarted-12', [])])]
            response = self.get('course')
            self.assertEquals(expected, self._parse_leftnav(response))

            # Re-visit lesson two, then check progress.  Progress should
            # now show as completed.
            response = self.get('unit?unit=4&lesson=11')
            expected = [
                Element(text=u'2.1 Lesson One', link=u'unit?unit=4&lesson=10',
                        progress=u'progress-notstarted-10', contents=[]),
                Element(text=u'2.2 Lesson Two', link=None,
                        progress=u'progress-completed-11', contents=[]),
                Element(text=u'2.3 Lesson Three', link=u'unit?unit=4&lesson=12',
                        progress=u'progress-notstarted-12', contents=[])]
            self.assertEquals(expected, self._parse_leftnav(response))

            # Visit other lessons.  Unit should now show as completed.
            response = self.get('unit?unit=4&lesson=10')
            response = self.get('unit?unit=4&lesson=12')

            expected = [
                Element('Unit 2 - Unit Two', 'unit?unit=4',
                        'progress-completed-4', [
                    Element('2.1 Lesson One', 'unit?unit=4&lesson=10',
                            'progress-completed-10', []),
                    Element('2.2 Lesson Two', 'unit?unit=4&lesson=11',
                            'progress-completed-11', []),
                    Element('2.3 Lesson Three', 'unit?unit=4&lesson=12',
                            'progress-completed-12', [])])]
            response = self.get('course')
            self.assertEquals(expected, self._parse_leftnav(response))

            expected = [
                Element('2.1 Lesson One', None, 'progress-completed-10', []),
                Element('2.2 Lesson Two', 'unit?unit=4&lesson=11',
                        'progress-completed-11', []),
                Element('2.3 Lesson Three', 'unit?unit=4&lesson=12',
                        'progress-completed-12', [])]
            response = self.get('unit?unit=4&lesson=10')
            self.assertEquals(expected, self._parse_leftnav(response))

    def test_next_prev_links_in_complex_unit(self):

        def get_prev_next_links(response):
            dom = self.parse_html_string(response.body)
            prev_link = dom.find('.//div[@class="gcb-prev-button"]/a')
            if prev_link is not None:
                prev_link = prev_link.get('href')
            next_link = dom.find('.//div[@class="gcb-next-button"]/a')
            if next_link is not None:
                next_link = next_link.get('href')
            return prev_link, next_link

        # Hide irrelevant items.
        self.unit_one.availability = courses.AVAILABILITY_UNAVAILABLE
        self.link_one.availability = courses.AVAILABILITY_UNAVAILABLE
        self.assessment_one.availability = courses.AVAILABILITY_UNAVAILABLE
        self.unit_two.availability = courses.AVAILABILITY_UNAVAILABLE
        self.link_two.availability = courses.AVAILABILITY_UNAVAILABLE
        self.assessment_two.availability = courses.AVAILABILITY_UNAVAILABLE
        self.link_three.availability = courses.AVAILABILITY_UNAVAILABLE
        self.assessment_three.availability = courses.AVAILABILITY_UNAVAILABLE
        self.course.save()
        self.course.set_course_availability(
            courses.COURSE_AVAILABILITY_REGISTRATION_REQUIRED)

        actions.login(self.USER_EMAIL)
        actions.register(self, self.USER_EMAIL)

        # Since we have not submitted the assessment, the review step
        # is not available, so expect that the 'next' link will be lesson 15.
        response = self.get('unit?unit=7')
        prev_link, next_link = get_prev_next_links(response)
        self.assertEquals(prev_link, None)
        self.assertEquals(next_link, 'unit?unit=7&lesson=15')

        response = self.get(next_link)
        prev_link, next_link = get_prev_next_links(response)
        self.assertEquals(prev_link, 'unit?unit=7&assessment=13')
        self.assertEquals(next_link, 'unit?unit=7&assessment=14')

        response = self.get(next_link)
        prev_link, next_link = get_prev_next_links(response)
        self.assertEquals(prev_link, 'unit?unit=7&lesson=15')
        self.assertEquals(next_link, 'course')  # End link back to syllabus

        # Pretend to submit the pre-assessment.  Prev/next links should
        # change to reflect the new availability of the review step.
        self.post('answer', {
            'xsrf_token': crypto.XsrfTokenManager.create_xsrf_token(
                'assessment-post'),
            'assessment_type': '%s' % self.pre_assessment.unit_id,
            'score': 1,
            })

        # Get the lesson; verify prev now goes to review dashboard.
        response = self.get('unit?unit=7&lesson=15')
        prev_link, next_link = get_prev_next_links(response)
        self.assertEquals(prev_link, 'reviewdashboard?unit=13')
        self.assertEquals(next_link, 'unit?unit=7&assessment=14')

        # TODO(mgainer): Review dashboard should be integrated to inline
        # lesson flow.  When it its, test that it fits.

    def test_previously_visited_link_marked(self):

        def get_last_location_href(response):
            dom = self.parse_html_string(response.body)
            last_link = dom.find('.//li[@class="gcb-last-location"]//a')
            if last_link is not None:
                last_link = last_link.get('href')
            return last_link

        # Hide irrelevant items.
        self.unit_one.availability = courses.AVAILABILITY_UNAVAILABLE
        self.link_one.availability = courses.AVAILABILITY_UNAVAILABLE
        self.assessment_one.availability = courses.AVAILABILITY_UNAVAILABLE
        self.unit_two.availability = courses.AVAILABILITY_UNAVAILABLE
        self.link_two.availability = courses.AVAILABILITY_UNAVAILABLE
        self.assessment_two.availability = courses.AVAILABILITY_UNAVAILABLE
        self.link_three.availability = courses.AVAILABILITY_UNAVAILABLE
        self.assessment_three.availability = courses.AVAILABILITY_UNAVAILABLE
        self.course.save()
        self.course.set_course_availability(
            courses.COURSE_AVAILABILITY_REGISTRATION_REQUIRED)

        actions.login(self.USER_EMAIL)
        actions.register(self, self.USER_EMAIL)

        # Visit lesson; no item should be marked as previously visited.
        response = self.get('unit?unit=7&lesson=15')
        self.assertIsNone(get_last_location_href(response))

        # Now visit pre-assessment.  Lesson should be marked as being the
        # previous link visited.
        response = self.get('unit?unit=7&assessment=13')
        self.assertEquals('unit?unit=7&lesson=15',
                          get_last_location_href(response))

        # Now visit post-assessment.  Pre-assessment should be last visited.
        response = self.get('unit?unit=7&assessment=14')
        self.assertEquals('unit?unit=7&assessment=13',
                          get_last_location_href(response))

    def test_default_unit_creation_availability(self):

        self.course.set_course_availability(courses.COURSE_AVAILABILITY_PRIVATE)
        self.assertEquals(
            courses.AVAILABILITY_COURSE, self.course.add_unit().availability)
        self.assertEquals(
            courses.AVAILABILITY_COURSE, self.course.add_link().availability)
        self.assertEquals(
            courses.AVAILABILITY_COURSE,
            self.course.add_assessment().availability)

        for a in (courses.COURSE_AVAILABILITY_REGISTRATION_REQUIRED,
                  courses.COURSE_AVAILABILITY_REGISTRATION_OPTIONAL,
                  courses.COURSE_AVAILABILITY_PUBLIC):
            self.course.set_course_availability(a)
            self.assertEquals(
                courses.AVAILABILITY_UNAVAILABLE,
                self.course.add_unit().availability)
            self.assertEquals(
                courses.AVAILABILITY_UNAVAILABLE,
                self.course.add_link().availability)
            self.assertEquals(
                courses.AVAILABILITY_UNAVAILABLE,
                self.course.add_assessment().availability)

    def _hide_immaterial_items(self):
        self.unit_one.availability = courses.AVAILABILITY_UNAVAILABLE
        self.link_one.availability = courses.AVAILABILITY_UNAVAILABLE
        self.assessment_one.availability = courses.AVAILABILITY_UNAVAILABLE
        self.link_two.availability = courses.AVAILABILITY_UNAVAILABLE
        self.assessment_two.availability = courses.AVAILABILITY_UNAVAILABLE
        self.unit_three.availability = courses.AVAILABILITY_UNAVAILABLE
        self.link_three.availability = courses.AVAILABILITY_UNAVAILABLE
        self.assessment_three.availability = courses.AVAILABILITY_UNAVAILABLE

    def test_all_on_one_page_syllabus(self):
        self._hide_immaterial_items()
        self.unit_two.show_contents_on_one_page = True
        self.course.save()
        actions.login(self.USER_EMAIL)

        expected = [Element('Unit 2 - Unit Two', 'unit?unit=4', None, contents=[
            Element('2.1 Lesson One', 'unit?unit=4#lesson_title_10', None, []),
            Element('2.2 Lesson Two', 'unit?unit=4#lesson_title_11', None, []),
            Element('2.3 Lesson Three', 'unit?unit=4#lesson_title_12', None, [])
        ])]
        with actions.OverriddenEnvironment({'course': {
                'show_lessons_in_syllabus': True}}):
            response = self.get('course')
        self.assertEquals(expected, self._parse_leftnav(response))

    def test_all_on_one_page_leftnav(self):
        self._hide_immaterial_items()
        self.unit_two.show_contents_on_one_page = True
        self.course.save()
        actions.login(self.USER_EMAIL)

        expected = [
            Element('2.1 Lesson One', 'unit?unit=4#lesson_title_10', None, []),
            Element('2.2 Lesson Two', 'unit?unit=4#lesson_title_11', None, []),
            Element('2.3 Lesson Three', 'unit?unit=4#lesson_title_12', None, [])
        ]
        with actions.OverriddenEnvironment({'course': {
                'show_lessons_in_syllabus': True}}):
            response = self.get('unit?unit=4')
        self.assertEquals(expected, self._parse_leftnav(response))

        soup = self.parse_html_string_to_soup(response.body)
        self.assertIsNotNone(soup.select_one('#lesson_title_10'))
        self.assertIsNotNone(soup.select_one('#lesson_title_11'))
        self.assertIsNotNone(soup.select_one('#lesson_title_12'))

    def test_all_on_one_page_link_specifying_lesson_succeeds(self):
        self._hide_immaterial_items()
        self.unit_two.show_contents_on_one_page = True
        self.course.save()
        actions.login(self.USER_EMAIL)

        expected = [
            Element('2.1 Lesson One', 'unit?unit=4#lesson_title_10', None, []),
            Element('2.2 Lesson Two', 'unit?unit=4#lesson_title_11', None, []),
            Element('2.3 Lesson Three', 'unit?unit=4#lesson_title_12', None, [])
        ]
        with actions.OverriddenEnvironment({'course': {
                'show_lessons_in_syllabus': True}}):
            response = self.get('unit?unit=4&lesson=12')
        self.assertEquals(expected, self._parse_leftnav(response))

        soup = self.parse_html_string_to_soup(response.body)
        self.assertIsNotNone(soup.select_one('#lesson_title_10'))
        self.assertIsNotNone(soup.select_one('#lesson_title_11'))
        self.assertIsNotNone(soup.select_one('#lesson_title_12'))

    def test_all_on_one_page_some_lessons_unavailable(self):
        self._hide_immaterial_items()
        self.lesson_one.availability = courses.AVAILABILITY_UNAVAILABLE
        self.lesson_three.availability = courses.AVAILABILITY_UNAVAILABLE
        self.unit_two.show_contents_on_one_page = True
        self.course.save()
        actions.login(self.USER_EMAIL)

        expected = [
            Element('2.2 Lesson Two', 'unit?unit=4#lesson_title_11', None, []),
        ]
        with actions.OverriddenEnvironment({'course': {
                'show_lessons_in_syllabus': True}}):
            response = self.get('unit?unit=4')
        actual = self._parse_leftnav(response)
        self.assertEquals(expected, actual)

        soup = self.parse_html_string_to_soup(response.body)
        self.assertIsNone(soup.select_one('#lesson_title_10'))
        self.assertIsNotNone(soup.select_one('#lesson_title_11'))
        self.assertIsNone(soup.select_one('#lesson_title_12'))

    def test_all_on_one_page_all_lessons_unavailable(self):
        self._hide_immaterial_items()
        self.lesson_one.availability = courses.AVAILABILITY_UNAVAILABLE
        self.lesson_two.availability = courses.AVAILABILITY_UNAVAILABLE
        self.lesson_three.availability = courses.AVAILABILITY_UNAVAILABLE
        self.unit_two.show_contents_on_one_page = True
        self.course.save()
        actions.login(self.USER_EMAIL)

        # Verify link to Unit still works when none of its lessons are available
        with actions.OverriddenEnvironment({'course': {
                'show_lessons_in_syllabus': True}}):
            response = self.get('unit?unit=4')

        self.assertEquals(response.status_int, 200)

        # Verify link to specific lesson just redirects to course when
        # lesson not available
        with actions.OverriddenEnvironment({'course': {
                'show_lessons_in_syllabus': True}}):
            response = self.get('unit?unit=4&lesson=11')
        self.assertEquals(response.status_int, 200)

        # Verify syllabus shows no sub-lessons but unit is still linkable
        with actions.OverriddenEnvironment({'course': {
                'show_lessons_in_syllabus': True}}):
            response = self.get('course')
        expected = [
            Element('Unit 2 - Unit Two', 'unit?unit=4', None, contents=[])]
        actual = self._parse_leftnav(response)
        self.assertEquals(expected, actual)

    def test_all_on_one_page_lessons_available_but_unit_unavailable(self):
        self._hide_immaterial_items()
        self.lesson_one.availability = courses.AVAILABILITY_AVAILABLE
        self.lesson_two.availability = courses.AVAILABILITY_AVAILABLE
        self.lesson_three.availability = courses.AVAILABILITY_AVAILABLE
        self.unit_two.availability = courses.AVAILABILITY_UNAVAILABLE
        self.unit_two.show_contents_on_one_page = True
        self.course.save()
        actions.login(self.USER_EMAIL)

        # Verify link to Unit just redirects to course when no lessons avail.
        with actions.OverriddenEnvironment({'course': {
                'show_lessons_in_syllabus': True}}):
            response = self.get('unit?unit=4')
        self.assertEquals(response.status_int, 302)
        self.assertEquals(response.location,
                          'http://localhost/availability_tests/course')

        # Verify link to specific lesson just redirects to course when
        # no lessons avail.
        with actions.OverriddenEnvironment({'course': {
                'show_lessons_in_syllabus': True}}):
            response = self.get('unit?unit=4&leson=11')
        self.assertEquals(response.status_int, 302)
        self.assertEquals(response.location,
                          'http://localhost/availability_tests/course')

        # Verify syllabus shows no sub-lessons and unit is not linkable
        with actions.OverriddenEnvironment({'course': {
                'show_lessons_in_syllabus': True}}):
            response = self.get('course')
        expected = []
        actual = self._parse_leftnav(response)
        self.assertEquals(expected, actual)

    DetectOption = collections.namedtuple(
        'DetectOption', 'type indent link_re note_re text_re')

    DETECT_OPTION_ORDER = [
        DetectOption(
            'unit',
            '',  # Top-level assessments are not indented.
            re.compile(r'^assessment\?name=([0-9]+)$'),
            re.compile(r' \(assessment\)$'),
            None,
        ),
        DetectOption(
            'lesson',
            '&emsp;',  # Lessons are under units and indented.
            re.compile(r'^unit\?unit=[0-9]+&lesson=([0-9]+)$'),
            None,
            re.compile(r'[0-9]+\.[0-9]+ '),  # E.g. "2.1 "
        ),
        DetectOption(
            'unit',
            '&emsp;' * 2,  # Double-indented for emphasis, compared to lesson.
            re.compile(r'^unit\?unit=[0-9]+&assessment=([0-9]+)$'),
            re.compile(r' \((pre|post)-assessment\)$'),
            None
        ),
        DetectOption(
            'unit', '',
            re.compile(r'^unit\?unit=([0-9]+)$'),
            re.compile(r' \(unit\)$'),
            re.compile(r'Unit [0-9]+ - '),  # E.g. "Unit 1 - "
        ),
        DetectOption(
            'unit',
            '',  # Top-level links are not indented.
            None,
            re.compile(r' \(link\)$'),
            None,
        ),
    ]

    def _check_content_option(self, option, element):
        expected_text = element.text
        link = element.link

        for detect in self.DETECT_OPTION_ORDER:
            expected_type = detect.type
            expected_indent = detect.indent
            expected_note_re = detect.note_re

            if link and detect.link_re:
                matched = detect.link_re.match(link)
                if matched:
                    expected_id = matched.group(1)
                    if detect.text_re:
                        prefixed = detect.text_re.match(expected_text)
                        if prefixed:
                            prefix = prefixed.group(0)
                            expected_text = expected_text[len(prefix):]
                    break
            else:
                # Top-level link is the only thing remaining?
                expected_id = None  # No way to determine from Link Element.

        label = option['label']
        text = label
        if expected_indent:
            text = text[len(expected_indent):]  # Trim off the indentation.

        content_type, content_id = option['value'].split(':')

        if expected_note_re:
            annotated = expected_note_re.search(label)
            self.assertTrue(annotated)
            annotation = annotated.group(0)
            text = text[:-len(annotation)]  # Trim off the annotation.

        if expected_indent:
            self.assertTrue(label.startswith(expected_indent))
        else:
            self.assertFalse(label.startswith('emsp;'))

        self.assertEquals(expected_type, content_type)
        if expected_id:
            self.assertEquals(expected_id, content_id)

        self.assertEquals(expected_text, text)

    JSON_PARSE_CALL = 'JSON.parse('

    def _check_content_select_json(self, json):
        decoded = transforms.loads(transforms.loads(json))
        self.assertEquals(
            'trigger-content inputEx-Field', decoded['className'])
        self.assertEquals('select', decoded['_type'])
        options = decoded['choices']
        for unit in self.ALL_LEVELS_WITH_LINKS_NO_PROGRESS:
            self._check_content_option(options.pop(0), unit)
            for item in unit.contents:
                if not item.link:
                    # E.g. "Review peer assignments" which dot show up in
                    # traverse_course() results on the Publish > Availability
                    # page in the Content Availability section either.
                    continue
                self._check_content_option(options.pop(0), item)

    def test_content_select(self):
        actions.login(self.ADMIN_EMAIL, is_admin=True)
        response = self.get(self.action_url)
        self.assertEquals(200, response.status_int)

        # Find all of the <script> tags that contain inlined Javascript.
        soup = self.parse_html_string_to_soup(response.body)
        scripts = soup.find('script', type='text/javascript', src='')

        # Combine all of the lines from these scripts that contain a
        # JSON.parse() call. This works for the purposes of this test because
        # currently the JSON.parse() call that defines the trigger-content
        # <select> definition of interest is always a single, long line of
        # text.
        trigger_content_json = []
        for script in scripts:
            for line in str(script).splitlines():
                call_start = line.find(self.JSON_PARSE_CALL)
                if call_start > -1:
                    arg_start = call_start + len(self.JSON_PARSE_CALL)
                    escaped_json = line[arg_start:-1]
                    if 'trigger-content' in escaped_json:
                        trigger_content_json.append(escaped_json)

        # ['content_triggers']['items']['properties']['content'] encoded JSON
        # is found in two places in schema.root:
        # 1) ['properties']
        #    (the original <select> for course content triggers)
        # 2) ['properties']['student_group_settings']['properties']
        #    (the <select> for student_groups content triggers)
        self.assertEquals(2, len(trigger_content_json))
        for json in trigger_content_json:
            self._check_content_select_json(json)

    def _utc_past_text(self, now):
        return utc.to_text(seconds=utc.hour_start(now - (60 * 60)))

    def _some_past_content_triggers(self, now):
        when = self._utc_past_text(now)

        # Define a unit trigger and a lesson trigger somewhat in the past, to
        # insure that a cron job will execute them at test time.
        return [{
            'content': str(resource.Key('unit', self.unit_one.unit_id)),
            'availability': courses.AVAILABILITY_AVAILABLE,
            'when': when,
        }, {
            'content': str(resource.Key('lesson', self.lesson_two.lesson_id)),
            'availability': courses.AVAILABILITY_UNAVAILABLE,
            'when': when,
        }]

    def _utc_future_text(self, now):
        return utc.to_text(seconds=utc.hour_end(now + (60 * 60)) + 1)

    def _some_future_content_triggers(self, now):
        when = self._utc_future_text(now)

        # Define a unit trigger and a lesson trigger somewhat into the future,
        # so there is no chance that a cron task will execute them and remove
        # them from the course settings prematurely.
        return [{
            'content': str(resource.Key('unit', self.unit_two.unit_id)),
            'availability': courses.AVAILABILITY_AVAILABLE,
            'when': when,
        }, {
            'content': str(resource.Key('lesson', self.lesson_one.lesson_id)),
            'availability': courses.AVAILABILITY_UNAVAILABLE,
            'when': when,
        }]

    _BAD_CONTENT_KEY = 'not a valid resource Key'
    _BAD_AVAIL = 'not a valid availability value'
    _BAD_WHEN = 'not a valid UTC date/time'

    # A valid resource.Key type
    _VALID_BUT_NOT_OUTLINE = resources_display.ResourceUnitBase.ASSESSMENT_TYPE

    def _specific_bad_content_triggers(self, now):
        past = self._utc_past_text(now)
        future = self._utc_future_text(now)

        # An empty trigger, missing all of the required fields.
        empty = {}

        # A trigger with completely bogus required field values.
        bad = {
            'content': self._BAD_CONTENT_KEY,
            'availability': self._BAD_AVAIL,
            'when': self._BAD_WHEN,
        }

        # A trigger with a valid, but not course outline, content type.
        unexpected = {
            'content': str(resource.Key(
                self._VALID_BUT_NOT_OUTLINE, self.assessment_two.unit_id)),
            'availability': courses.AVAILABILITY_AVAILABLE,
            'when': past,
        }

        # A valid trigger missing its associated course content. Also checks
        # that even a trigger that is in the future is discarded if faulty.
        missing = {
            'content': str(resource.Key('unit', "9999")),
            'availability': courses.AVAILABILITY_AVAILABLE,
            'when': future,
        }
        # Not really a bad trigger, per se, but simply a no-op trigger,
        # because the result is no change in the existing availability.
        unchanged = {
            'content': str(resource.Key('unit', self.assessment_one.unit_id)),
            'availability': courses.AVAILABILITY_COURSE,
            'when': past,
        }
        return (empty, bad, unexpected, missing, unchanged)

    def _run_availability_jobs(self, app_context):
        cron_job = availability_cron.UpdateCourseAvailability(app_context)
        self.assertFalse(cron_job.is_active())
        cron_job.submit()
        self.execute_all_deferred_tasks()

    def _separating_logged(self, logs, count, trigger_typename):
        self.assertIn(
            'SEPARATING %d encoded %s(s) in %s.' % (
                count, trigger_typename, self.NAMESPACE), logs)

    def _awaiting_logged(self, logs, count, trigger_typename):
        self.assertIn(
            'AWAITING %d future %s(s) in %s.' % (
                count, trigger_typename, self.NAMESPACE), logs)

    def _untouched_logged(self, logs):
        self.assertIn(
            'UNTOUCHED %s course content availability.' % self.NAMESPACE,
            logs)

    def _kept_logged(self, logs, count, trigger_typename):
        self.assertIn(
            'KEPT %d future %s(s) in %s.' % (
                count, trigger_typename, self.NAMESPACE), logs)

    def _saved_logged(self, logs, count):
        self.assertIn(
            'SAVED %d changes to %s course content availability.' % (
                count, self.NAMESPACE), logs)

    _ENCODED_TRIGGER_RE = '{.+}'

    def _error_logged(self, logs, trigger, what, why, cause):
        self.assertRegexpMatches(logs,
            '.*%s \'%s\' in namespace %s encoded: "%s" cause: "%s".*' % (
                what, why, self.NAMESPACE, trigger, cause))

    def _error_not_logged(self, logs, trigger, what, why, cause):
        self.assertNotRegexpMatches(logs,
            '.*%s \'%s\' in namespace %s encoded: "%s" cause: "%s".*' % (
                what, why, self.NAMESPACE, trigger, cause))

    def _unchanged_logged(self, logs, current, trigger, course):
        decoded = triggers.ContentTrigger.decode(trigger, course=course)
        self.assertIn(
            'UNCHANGED %s content availability "%s": %s' % (
                self.NAMESPACE, current, decoded.logged), logs)

    def _triggers_logged(self, logs, logged, previous_avail, course):
        for lt in logged:
            decoded = triggers.ContentTrigger.decode(lt, course=course)
            avail = lt.get('availability')
            if avail != previous_avail:
                self.assertIn(
                    'TRIGGERED %s content availability "%s" to "%s": %s' % (
                        self.NAMESPACE, previous_avail, avail, decoded.logged),
                    logs)
            else:
                self.assertIn(
                    'UNCHANGED %s content availability "%s": %s' % (
                        self.NAMESPACE, previous_avail, decoded.logged), logs)

    def _find_trigger_content(self, course, trigger):
        content = resource.Key.fromstring(trigger['content'])
        if content.type == 'lesson':
            return course.find_lesson_by_id(None, content.key)
        return course.find_unit_by_id(content.key)

    def _check_triggers_applied(self, course, applied):
        for at in applied:
            found = self._find_trigger_content(course, at)
            self.assertEquals(at['availability'], found.availability)

    def _check_triggers_unapplied(self, course, original_avail, unapplied):
        for ut in unapplied:
            found = self._find_trigger_content(course, ut)
            self.assertEquals(original_avail, found.availability)
            # Assumes no "UNCHANGED" future test cases.
            self.assertNotEquals(ut['availability'], found.availability)

    LOG_LEVEL = logging.INFO

    def test_update_availability(self):
        now = utc.now_as_timestamp()
        actions.login(self.ADMIN_EMAIL, is_admin=True)
        app_context = sites.get_app_context_for_namespace(self.NAMESPACE)

        tdtt = triggers.DateTimeTrigger
        tat = triggers.AvailabilityTrigger
        tct = triggers.ContentTrigger

        self.assertNotIn(
            self._VALID_BUT_NOT_OUTLINE, tct.ALLOWED_CONTENT_TYPES)

        # Expect no triggers to be present in course settings initially.
        empty_settings = app_context.get_environ()
        self.assertEquals(tct.get_from_settings(empty_settings), [])

        # Cron job should log that there were triggers no waiting.
        self._run_availability_jobs(app_context)
        logs = self.get_log()
        self._untouched_logged(logs)

        # POST some past, future, and "bad" triggers to the course settings.
        future_cts = self._some_future_content_triggers(now)
        past_cts = self._some_past_content_triggers(now)

        empty, bad, unexpected, missing, unchanged = (
            self._specific_bad_content_triggers(now))
        bad_cts = [None, empty, bad, unexpected, missing, unchanged]
        all_cts = future_cts + past_cts + bad_cts
        response = self._post({'content_triggers': all_cts})
        self.assertEquals(200, response.status_int)
        posted_settings = app_context.get_environ()
        self.assertEquals(all_cts, tct.get_from_settings(posted_settings))

        # All triggers now in course settings, so evaluate them in cron job.
        self._run_availability_jobs(app_context)

        # Cron job should log some consumed and some future triggers.
        # Checking the logs first for anomolies pinpoints problems faster.
        logs = self.get_log()
        self._separating_logged(logs, len(all_cts), tct.typename())

        # All of the "exceptional" triggers should have been logged.
        self._error_logged(logs, 'None', 'MISSING', tct.typename(),
            re.escape("'None' trigger is missing."))

        self._error_logged(logs, {'when': None}, 'INVALID', 'datetime',
            re.escape("TypeError('must be string, not None',)"))
        self._error_logged(logs, {'availability': None}, 'INVALID',
            'availability', re.escape(tat.UNEXPECTED_AVAIL_FMT.format(
                None, tct.AVAILABILITY_VALUES)))
        self._error_logged(logs, {'content_type': None}, 'INVALID',
            'resource.Key', re.escape(
                "Content type \"None\" not in ['lesson', 'unit']."))

        self._error_logged(logs, {'when': bad['when']}, 'INVALID', 'datetime',
            re.escape("ValueError(\"time data 'not a valid UTC date/time' "
                      "does not match format '%Y-%m-%dT%H:%M:%S.%fZ'\",)"))
        self._error_logged(logs, {'availability': bad['availability']},
            'INVALID', 'availability', re.escape(
                tat.UNEXPECTED_AVAIL_FMT.format(
                    self._BAD_AVAIL, tct.AVAILABILITY_VALUES)))
        self._error_logged(logs, {'content': bad['content']}, 'INVALID',
            'resource.Key', re.escape(
                "ValueError('substring not found',)"))

        unexpected_content = unexpected.get('content')
        unexpected_type = resource.Key.fromstring(unexpected_content).type
        self._error_logged(logs, {'content': unexpected_content}, 'INVALID',
            'resource.Key', re.escape(tct.UNEXPECTED_CONTENT_FMT.format(
                unexpected_type, tct.ALLOWED_CONTENT_TYPES)))
        self._error_logged(logs, {'content_type': unexpected_type}, 'INVALID',
            'resource.Key', re.escape(tct.UNEXPECTED_CONTENT_FMT.format(
                unexpected_type, tct.ALLOWED_CONTENT_TYPES)))

        self._error_logged(logs, {'content': missing['content']}, 'OBSOLETE',
            'resource.Key', re.escape(
                tct.MISSING_CONTENT_FMT.format(missing['content'])))

        self._error_not_logged(logs, self._ENCODED_TRIGGER_RE, 'UNEXPECTED',
            'trigger', re.escape(
                tdtt.UNEXPECTED_TRIGGER_FMT.format(True, True, True)))

        original_avail = courses.AVAILABILITY_COURSE
        course = courses.Course(None, app_context=app_context)

        self._unchanged_logged(logs, original_avail, unchanged, course)
        self._triggers_logged(logs, past_cts, original_avail, course)
        self._kept_logged(logs, len(future_cts), tct.typename())
        self._saved_logged(logs, len(past_cts))

        # Confirm that only valid future triggers remain (faulty triggers were
        # dropped and past triggers applied.
        after_settings = app_context.get_environ()
        self.assertEquals(future_cts, tct.get_from_settings(after_settings))

        # Confirm that the availability changes specified by the valid past
        # triggers were applied.
        self._check_triggers_applied(course, past_cts + [unchanged])
        # Also confirm that *future* triggers were *not* applied.
        self._check_triggers_unapplied(course, original_avail, future_cts)

        # Manually confirm that, while referring to the unit_id of an actual
        # assessment, the `unexpected` trigger was not actually applied, due
        # to the type not being one of ['unit', 'lesson'].
        self.assertEquals(original_avail, self.assessment_two.availability)
        self.assertNotEquals(
            unexpected['availability'], self.assessment_two.availability)

        # Only future triggers remain, so run cron again and confirm no change.
        self._run_availability_jobs(app_context)
        logs = self.get_log()
        self._awaiting_logged(logs, len(future_cts), tct.typename())


class CourseSettingsRESTHandlerTests(actions.TestBase):
    _ADMIN_EMAIL = 'admin@foo.com'
    _COURSE_NAME = 'course_settings'
    _USER_EMAIL = 'user@foo.com'
    _NAMESPACE = 'ns_%s' % _COURSE_NAME
    _URI = 'rest/course/settings'
    _XSRF_ACTION = 'basic-course-settings-put'

    def setUp(self):
        super(CourseSettingsRESTHandlerTests, self).setUp()
        self.base = '/' + self._COURSE_NAME
        self.app_context = actions.simple_add_course(
            self._COURSE_NAME, self._ADMIN_EMAIL, 'Course Settings')
        self.course = courses.Course(None, self.app_context)

    def tearDown(self):
        sites.reset_courses()
        super(CourseSettingsRESTHandlerTests, self).tearDown()

    def _get_locale_label_titles(self):
        with common_utils.Namespace(self._NAMESPACE):
            locale_label_list = models.LabelDAO.get_all_of_type(
                models.LabelDTO.LABEL_TYPE_LOCALE)
            return {label.title for label in locale_label_list}

    def _put_extra_locales(self, base_locale, extra_locales):
        xsrf_token = crypto.XsrfTokenManager.create_xsrf_token(
            self._XSRF_ACTION)
        payload = {
            'course:locale': base_locale,
            'extra_locales': [
                {'locale': locale, 'availability': 'available'}
                for locale in extra_locales]
        }
        request = {
            'key': 'course.yaml',
            'payload': transforms.dumps(payload),
            'xsrf_token': xsrf_token
        }
        response = self.put(self._URI, {'request': transforms.dumps(request)})
        self.assertEquals(200, response.status_int)
        response = transforms.loads(response.body)
        self.assertEquals(200, response['status'])

    def test_process_extra_locales(self):
        """Expect locale lables to be kept in sync with locale settings."""
        actions.login(self._ADMIN_EMAIL)

        # Expect no locale lables to have been set up
        self.assertEquals(set(), self._get_locale_label_titles())

        # Expect the base and two extra locales to have been set
        self._put_extra_locales('en_US', ['en_GB', 'el'])
        self.assertEquals(
            {'en_US', 'en_GB', 'el'}, self._get_locale_label_titles())

        # Expect one of the locales to have been deleted
        self._put_extra_locales('en_US', ['el'])
        self.assertEquals(
            {'en_US', 'el'}, self._get_locale_label_titles())

        # Expect one to be removed and one to be added
        self._put_extra_locales('en_US', ['fr'])
        self.assertEquals(
            {'en_US', 'fr'}, self._get_locale_label_titles())

        # Expect base locale to change
        self._put_extra_locales('el', ['fr'])
        self.assertEquals(
            {'el', 'fr'}, self._get_locale_label_titles())


class EventRecordingRestHandlerTests(actions.TestBase):

    ADMIN_EMAIL = 'admin@foo.com'
    COURSE_ONE_NAME = 'events_tests_one'
    COURSE_TWO_NAME = 'events_tests_two'
    COURSE_THREE_NAME = 'events_tests_three'
    COURSE_ONE_NS = 'ns_%s' % COURSE_ONE_NAME
    COURSE_TWO_NS = 'ns_%s' % COURSE_TWO_NAME
    COURSE_THREE_NS = 'ns_%s' % COURSE_THREE_NAME
    COURSE_ONE_SLUG = '/c1'
    COURSE_TWO_SLUG = '/c2'
    COURSE_THREE_SLUG = '/'
    USER_EMAIL = 'user@foo.com'

    def setUp(self):
        super(EventRecordingRestHandlerTests, self).setUp()
        self.app_context_one = actions.simple_add_course(
            self.COURSE_ONE_NAME, self.ADMIN_EMAIL, 'Course Settings')
        self.app_context_two = actions.simple_add_course(
            self.COURSE_TWO_NAME, self.ADMIN_EMAIL, 'Course Settings')
        self.app_context_three = actions.simple_add_course(
            self.COURSE_THREE_NAME, self.ADMIN_EMAIL, 'Course Settings')

        # Take direct control of the courses config so that we can have one
        # course with a slug of just "/" and another with a nonblank slug
        # so that we can verify that cookies for "/" and "/c2" are handled.
        course_config = config.Registry.test_overrides[
            sites.GCB_COURSES_CONFIG.name] = '\n'.join([
                'course:' + self.COURSE_ONE_SLUG + '::' + self.COURSE_ONE_NS,
                'course:' + self.COURSE_TWO_SLUG + '::' + self.COURSE_TWO_NS,
                'course:' + self.COURSE_THREE_SLUG + '::' + self.COURSE_THREE_NS
            ])
        self.user_id = actions.login(self.USER_EMAIL).user_id()

    def tearDown(self):
        del config.Registry.test_overrides[sites.GCB_COURSES_CONFIG.name]
        sites.reset_courses()
        super(EventRecordingRestHandlerTests, self).tearDown()

    def _post_event(self, slug, source=None, payload=None):
        source = source or 'course'
        payload = payload or {}
        request = {
            'xsrf_token': crypto.XsrfTokenManager.create_xsrf_token(
                lessons.EventsRESTHandler.XSRF_TOKEN),
            'source': source,
            'payload': transforms.dumps(payload),
            }

        url = slug.rstrip('/') + lessons.EventsRESTHandler.URL
        response = self.post(url, {'request': transforms.dumps(request)})
        self.assertEquals(response.status_int, 200)

    def _get_event(self, namespace):
        with common_utils.Namespace(namespace):
            return models.EventEntity.all().get()

    def test_non_student_gets_randomized_id(self):
        # Check that we get an ID starting with "RND_" and which is not
        # equal to our user ID.
        self._post_event(self.COURSE_ONE_SLUG)
        event = self._get_event(self.COURSE_ONE_NS)
        random_id = event.user_id
        self.assertTrue(random_id.startswith('RND_'))
        self.assertNotEquals(random_id, self.user_id)

        # Bonk that event and make another.  Verify that we get the same
        # random ID so that non-registered user activity can be tracked.
        event.delete()
        self._post_event(self.COURSE_ONE_SLUG)
        event = self._get_event(self.COURSE_ONE_NS)
        self.assertEquals(event.user_id, random_id)

        # Clear cookies; verify that the random ID we get is now different.
        self.testapp.cookiejar.clear()
        event.delete()
        self._post_event(self.COURSE_ONE_SLUG)
        event = self._get_event(self.COURSE_ONE_NS)
        self.assertNotEquals(event.user_id, random_id)

        # And verify that this new ID is also persistent.
        new_random_id = event.user_id
        event.delete()
        self._post_event(self.COURSE_ONE_SLUG)
        event = self._get_event(self.COURSE_ONE_NS)
        self.assertEquals(event.user_id, new_random_id)
        self.assertNotEquals(event.user_id, random_id)

    def test_non_student_gets_different_ids_in_different_courses(self):
        self._post_event(self.COURSE_ONE_SLUG)
        event = self._get_event(self.COURSE_ONE_NS)
        random_id_one = event.user_id
        event.delete()

        self._post_event(self.COURSE_TWO_SLUG)
        event = self._get_event(self.COURSE_TWO_NS)
        random_id_two = event.user_id
        event.delete()

        self._post_event(self.COURSE_THREE_SLUG)
        event = self._get_event(self.COURSE_THREE_NS)
        random_id_three = event.user_id
        event.delete()

        # Verify that IDs from different courses are different.
        self.assertNotEquals(random_id_one, random_id_two)
        self.assertNotEquals(random_id_one, random_id_three)
        self.assertNotEquals(random_id_two, random_id_three)

        # And just for safety, verify that the IDs are consistent.  (As
        # opposed to us having gotten reassigned a new random ID each time we
        # change courses or similar silliness) Sadly, however, since course
        # three is intentionally being a jerk and using a slug of "/", it's
        # legit for the path matching on cookies for a path matching course
        # one or course two to also match on course three's path - "/", even
        # if there's a longer match.  Sigh.
        self._post_event(self.COURSE_ONE_SLUG)
        event = self._get_event(self.COURSE_ONE_NS)
        self.assertTrue(
            event.user_id == random_id_one or
            event.user_id == random_id_three)

        self._post_event(self.COURSE_TWO_SLUG)
        event = self._get_event(self.COURSE_TWO_NS)
        self.assertTrue(
            event.user_id == random_id_two or
            event.user_id == random_id_three)

        self._post_event(self.COURSE_THREE_SLUG)
        event = self._get_event(self.COURSE_THREE_NS)
        self.assertEquals(event.user_id, random_id_three)

    def test_user_id_used_after_registration(self):
        self._post_event(self.COURSE_ONE_SLUG)
        event = self._get_event(self.COURSE_ONE_NS)
        random_id_one = event.user_id
        event.delete()

        # Verify that once the student is registered, events *are* tagged
        # with that student's user_id.
        actions.register(self, 'John Smith', self.COURSE_ONE_SLUG.lstrip('/'))
        self._post_event(self.COURSE_ONE_SLUG)
        event = self._get_event(self.COURSE_ONE_NS)

        self.assertEquals(self.user_id, event.user_id)
        self.assertNotEquals(random_id_one, self.user_id)
