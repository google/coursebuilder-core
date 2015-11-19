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
import urlparse

from common import utils as common_utils
from common import crypto
from controllers import sites
from controllers import utils
from models import courses
from models import custom_modules
from models import models
from models import review
from models import transforms
from modules.courses import availability
from modules.courses import constants
from modules.courses import courses as modules_courses
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
        self.link_one = self.course.add_link()
        self.link_one.title = 'Link One'
        self.link_one.href = 'http://www.foo.com'
        self.assessment_one = self.course.add_assessment()
        self.assessment_one.title = 'Assessment One'

        self.unit_two = self.course.add_unit()
        self.unit_two.title = 'Unit Two'
        self.link_two = self.course.add_link()
        self.link_two.title = 'Link Two'
        self.link_two.href = 'http://www.bar.com'
        self.assessment_two = self.course.add_assessment()
        self.assessment_two.title = 'Assessment Two'

        self.unit_three = self.course.add_unit()
        self.unit_three.title = 'Unit Three'
        self.link_three = self.course.add_link()
        self.link_three.title = 'Link Three'
        self.assessment_three = self.course.add_assessment()
        self.assessment_three.title = 'Assessment Three'

        self.lesson_one = self.course.add_lesson(self.unit_two)
        self.lesson_one.title = 'Lesson One'
        self.lesson_two = self.course.add_lesson(self.unit_two)
        self.lesson_two.title = 'Lesson Two'
        self.lesson_three = self.course.add_lesson(self.unit_two)
        self.lesson_three.title = 'Lesson Three'

        self.pre_assessment = self.course.add_assessment()
        self.pre_assessment.title = 'Pre Assessment'
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

            # Not-even-logged-in users see titles of everything, but since
            # no sub-items within units are public, we don't get links to them.
            actions.logout()
            expected = [
                Element('Unit 1 - Unit One', None, None, []),
                Element('Link One', 'http://www.foo.com', None, []),
                Element('Assessment One', 'assessment?name=3', None, []),
                Element('Unit 2 - Unit Two', None, None, []),
                Element('Link Two', 'http://www.bar.com', None, []),
                Element('Assessment Two', 'assessment?name=6', None, []),
                Element('Unit 3 - Unit Three', None, None, []),
                Element('Link Three', None, None, []),
                Element('Assessment Three', 'assessment?name=9', None, []),
            ]
            self.assertEquals(expected, self._parse_leftnav(self.get('course')))

            # Non-students see links to all content.
            actions.login(self.USER_EMAIL, is_admin=False)
            self.assertEquals(expected, self._parse_leftnav(self.get('course')))

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

