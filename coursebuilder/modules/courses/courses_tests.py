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

from common import utils as common_utils
from common import crypto
from controllers import sites
from controllers import utils
from models import courses
from models import custom_modules
from models import models
from models import transforms
from modules.courses import constants
from modules.courses import courses as modules_courses
from modules.courses import unit_lesson_editor
from tests.functional import actions

from google.appengine.api import namespace_manager
from google.appengine.ext import deferred

class AccessDraftsTestCase(actions.TestBase):
    COURSE_NAME = 'draft_access'
    ADMIN_EMAIL = 'admin@foo.com'
    USER_EMAIL = 'user@foo.com'
    ROLE = 'test_role'
    ACTION = 'test_action'

    def setUp(self):
        super(AccessDraftsTestCase, self).setUp()
        actions.login(self.ADMIN_EMAIL, is_admin=True)
        self.base = '/' + self.COURSE_NAME
        self.context = actions.simple_add_course(
            self.COURSE_NAME, self.ADMIN_EMAIL, 'Access Draft Testing')

        self.course = courses.Course(None, self.context)

        self.old_namespace = namespace_manager.get_namespace()
        namespace_manager.set_namespace('ns_%s' % self.COURSE_NAME)

        role_dto = models.RoleDTO(None, {
            'name': self.ROLE,
            'users': [self.USER_EMAIL],
            'permissions': {
                custom_modules.core_module.name: [
                    custom_modules.SEE_DRAFTS_PERMISSION]
            }
        })
        models.RoleDAO.save(role_dto)
        actions.logout()

    def tearDown(self):
        namespace_manager.set_namespace(self.old_namespace)
        super(AccessDraftsTestCase, self).tearDown()

    def test_access_assessment(self):
        assessment = self.course.add_assessment()
        assessment.is_draft = True
        self.course.save()
        self.assertEquals(
            self.get('assessment?name=%s' % assessment.unit_id).status_int, 302)
        actions.login(self.USER_EMAIL, is_admin=False)
        self.assertEquals(
            self.get('assessment?name=%s' % assessment.unit_id).status_int, 200)
        actions.logout()

    def test_access_lesson(self):
        unit = self.course.add_unit()
        unit.is_draft = True
        lesson = self.course.add_lesson(unit)
        lesson.is_draft = True
        self.course.save()
        self.assertEquals(
            self.get('unit?unit=%s&lesson=%s' % (
            unit.unit_id, lesson.lesson_id)).status_int, 302)
        actions.login(self.USER_EMAIL, is_admin=False)
        self.assertEquals(
            self.get('unit?unit=%s&lesson=%s' % (
            unit.unit_id, lesson.lesson_id)).status_int, 200)
        actions.logout()


class CourseAccessPermissionsTests(actions.CourseOutlineTest):
    COURSE_NAME = 'outline_permissions'
    ADMIN_EMAIL = 'admin@foo.com'
    USER_EMAIL = 'user@foo.com'
    ROLE = 'test_role'
    NAMESPACE = 'ns_%s' % COURSE_NAME
    COURSE_AVAILABILITY_XPATH = './/*[@id="course-availability"]'
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

    def _add_role_with_permissions(self, permissions):
        with common_utils.Namespace(self.NAMESPACE):
            role_dto = models.RoleDTO(None, {
                'name': self.ROLE,
                'users': [self.USER_EMAIL],
                'permissions': {modules_courses.MODULE_NAME: permissions},
                })
            models.RoleDAO.save(role_dto)

    def test_no_permission(self):
        response = self.get('dashboard?action=outline')
        self.assertEquals(302, response.status_int)
        self.assertEquals('http://localhost/%s' % self.COURSE_NAME,
                          response.location)

    def test_course_structure_readonly_permission(self):
        self._add_role_with_permissions(
            [constants.COURSE_OUTLINE_VIEW_PERMISSION])
        response = self.get('dashboard?action=outline')
        self.assertEquals(200, response.status_int)
        dom = self.parse_html_string(response.body)

        # No buttons for add unit/assessment, import course.
        toolbar = dom.find('.//div[@class="gcb-button-toolbar"]')
        self.assertEquals(len(toolbar.getchildren()), 0)

        # No reorder drag handles
        handles = dom.findall(
            './/div[@class="reorder icon row-hover md md-view-headline"]')
        self.assertEquals(len(handles), 0)

        # No add-lesson item.
        add_lesson = dom.find('.//div[@class="row add-lesson"]')
        self.assertIsNone(add_lesson)

    def test_course_structure_reorder_permission(self):
        self._add_role_with_permissions(
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

    def test_course_availability_icon(self):
        self._add_role_with_permissions(
            [constants.COURSE_OUTLINE_VIEW_PERMISSION])

        element = self._get_dom().find(self.COURSE_AVAILABILITY_XPATH)
        self.assertEquals('div', element.tag)
        self.assertAvailabilityState(element, available=True, active=False)

        # Give this user permission to edit course availability.  Lock should
        # now be a button, with CSS indicating icon clickability.
        with actions.OverriddenSchemaPermission(
            'fake_course_perm', constants.SCOPE_COURSE_SETTINGS,
            self.USER_EMAIL, editable_perms=['course/course:now_available']):

            element = self._get_dom().find(self.COURSE_AVAILABILITY_XPATH)
            self.assertEquals('button', element.tag)
            self.assertAvailabilityState(element, available=True, active=True)

    def test_course_edit_settings_link(self):
        self._add_role_with_permissions(
            [constants.COURSE_OUTLINE_VIEW_PERMISSION])

        # Course-available lock should not be clickable and should not
        # have CSS indicating clickability.
        element = self._get_dom().find(self.COURSE_AVAILABILITY_XPATH)
        self.assertEquals('div', element.tag)
        self.assertAvailabilityState(element, active=False)

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

    def test_edit_unit_availability(self):
        self._add_role_with_permissions(
            [constants.COURSE_OUTLINE_VIEW_PERMISSION])

        UNIT_AVAILABILITY_SELECTOR_TEMPLATE = \
            '[data-unit-id="{}"] .icon-draft-status'
        UNIT_SELECTOR = UNIT_AVAILABILITY_SELECTOR_TEMPLATE.format(
            self.unit.unit_id)
        ASSESSMENT_SELECTOR = UNIT_AVAILABILITY_SELECTOR_TEMPLATE.format(
            self.assessment.unit_id)
        LINK_SELECTOR = UNIT_AVAILABILITY_SELECTOR_TEMPLATE.format(
            self.link.unit_id)

        # Only unit lock editable.
        with actions.OverriddenSchemaPermission(
            'fake_unit_perm', constants.SCOPE_UNIT,
            self.USER_EMAIL, editable_perms=['is_draft']):

            dom = self._get_soup()

            self.assertAvailabilityState(
                dom.select(UNIT_SELECTOR)[0], available=False, active=True)

            self.assertAvailabilityState(
                dom.select(ASSESSMENT_SELECTOR)[0], available=False,
                active=False)

            self.assertAvailabilityState(
                dom.select(LINK_SELECTOR)[0], available=False, active=False)

        # Only assessment lock editable
        with actions.OverriddenSchemaPermission(
            'fake_unit_perm', constants.SCOPE_ASSESSMENT,
            self.USER_EMAIL, editable_perms=['assessment/is_draft']):

            dom = self._get_soup()

            self.assertAvailabilityState(
                dom.select(UNIT_SELECTOR)[0], available=False, active=False)

            self.assertAvailabilityState(
                dom.select(ASSESSMENT_SELECTOR)[0], available=False,
                active=True)

            self.assertAvailabilityState(
                dom.select(LINK_SELECTOR)[0], available=False, active=False)

        # Only link lock editable
        with actions.OverriddenSchemaPermission(
            'fake_unit_perm', constants.SCOPE_LINK,
            self.USER_EMAIL, editable_perms=['is_draft']):

            dom = self._get_soup()

            self.assertAvailabilityState(
                dom.select(UNIT_SELECTOR)[0], available=False, active=False)

            self.assertAvailabilityState(
                dom.select(ASSESSMENT_SELECTOR)[0], available=False,
                active=False)

            self.assertAvailabilityState(
                dom.select(LINK_SELECTOR)[0], available=False, active=True)

    def test_edit_unit_property_editor_link(self):
        # Verify readability on some random property allows pencil icon
        # link to edit/view props page.

        self._add_role_with_permissions(
            [constants.COURSE_OUTLINE_VIEW_PERMISSION])

        UNIT_EDIT_LINK_SELECTOR = \
            '[data-unit-id={}] .name'
        UNIT_SELECTOR = UNIT_EDIT_LINK_SELECTOR.format(
            self.unit.unit_id)
        ASSESSMENT_SELECTOR = UNIT_EDIT_LINK_SELECTOR.format(
            self.assessment.unit_id)
        LINK_SELECTOR = UNIT_EDIT_LINK_SELECTOR.format(
            self.link.unit_id)

        # Only unit lock editable.
        with actions.OverriddenSchemaPermission(
            'fake_unit_perm', constants.SCOPE_UNIT,
            self.USER_EMAIL, editable_perms=['description']):

            soup = self._get_soup()
            self.assertEditabilityState(soup.select(UNIT_SELECTOR)[0], True)
            self.assertEditabilityState(
                soup.select(ASSESSMENT_SELECTOR)[0], False)
            self.assertEditabilityState(soup.select(LINK_SELECTOR)[0], False)

        # Only assessment lock editable
        with actions.OverriddenSchemaPermission(
            'fake_unit_perm', constants.SCOPE_ASSESSMENT,
            self.USER_EMAIL, editable_perms=['assessment/description']):

            soup = self._get_soup()
            self.assertEditabilityState(soup.select(UNIT_SELECTOR)[0], False)
            self.assertEditabilityState(
                soup.select(ASSESSMENT_SELECTOR)[0], True)
            self.assertEditabilityState(soup.select(LINK_SELECTOR)[0], False)

        # Only link lock editable
        with actions.OverriddenSchemaPermission(
            'fake_unit_perm', constants.SCOPE_LINK,
            self.USER_EMAIL, editable_perms=['description']):

            soup = self._get_soup()
            self.assertEditabilityState(soup.select(UNIT_SELECTOR)[0], False)
            self.assertEditabilityState(
                soup.select(ASSESSMENT_SELECTOR)[0], False)
            self.assertEditabilityState(soup.select(LINK_SELECTOR)[0], True)

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
