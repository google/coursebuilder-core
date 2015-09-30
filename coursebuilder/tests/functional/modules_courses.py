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
from models import courses
from models import custom_modules
from models import models
from models import transforms
from modules.courses import constants
from modules.courses import courses as modules_courses
from modules.courses import unit_lesson_editor
from tests.functional import actions

from google.appengine.api import namespace_manager


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


class CourseAccessPermissionsTests(actions.TestBase):
    COURSE_NAME = 'outline_permissions'
    ADMIN_EMAIL = 'admin@foo.com'
    USER_EMAIL = 'user@foo.com'
    ROLE = 'test_role'
    NAMESPACE = 'ns_%s' % COURSE_NAME

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
        dom = self.parse_html_string(response.body)

        # No buttons for add unit/assessment, import course.
        toolbar = dom.find('.//div[@class="gcb-button-toolbar"]')
        self.assertEquals(len(toolbar.getchildren()), 0)

        # Should have reorder drag handles
        handles = dom.findall(
            './/div[@class="reorder icon row-hover md md-view-headline"]')
        self.assertGreater(len(handles), 0)

        # No add-lesson item.
        add_lesson = dom.find('.//div[@class="row add-lesson"]')
        self.assertIsNone(add_lesson)

    def _find_element(self, xpath, tag, css_class):
        response = self.get('dashboard?action=outline')
        self.assertEquals(200, response.status_int)
        dom = self.parse_html_string(response.body)
        element = dom.find(xpath)
        self.assertIsNotNone(element)
        self.assertEquals(element.tag, tag)
        self.assertEquals(element.get('class'), css_class)
        return element

    def test_course_availability_icon(self):
        self._add_role_with_permissions(
            [constants.COURSE_OUTLINE_VIEW_PERMISSION])

        self._find_element(
            './/div[@class="row course"]/div[@class="left-matter"]/div[1]',
            'div',
            'row-hover icon md md-lock-open read-only inactive')

        # Give this user permission to edit course availability.  Lock should
        # now be a button, with CSS indicating icon clickability.
        with actions.OverriddenSchemaPermission(
            'fake_course_perm', constants.SCOPE_COURSE_SETTINGS,
            self.USER_EMAIL, editable_perms=['course/course:now_available']):

            self._find_element(
                './/div[@class="row course"]'
                '/div[@class="left-matter"]/form/button',
                'button', 'row-hover icon md md-lock-open')

    def test_course_edit_settings_icon(self):
        self._add_role_with_permissions(
            [constants.COURSE_OUTLINE_VIEW_PERMISSION])

        # Course-available lock should not be clickable and should not
        # have CSS indicating clickability.
        self._find_element(
            './/div[@class="row course"]/div[@class="left-matter"]/div[2]',
            'div', 'icon inactive')

        # Give this user permission to *edit* some random course property that's
        # not course-availability
        with actions.OverriddenSchemaPermission(
            'fake_course_perm', constants.SCOPE_COURSE_SETTINGS,
            self.USER_EMAIL, editable_perms=['course/course:title']):

            self._find_element(
                './/div[@class="row course"]/div[@class="left-matter"]/a',
                'a', 'icon row-hover md-mode-edit')

        # Give this user permission to *view* some random course property that's
        # not course-availability
        with actions.OverriddenSchemaPermission(
            'fake_course_perm', constants.SCOPE_COURSE_SETTINGS,
            self.USER_EMAIL, readable_perms=['course/course:title']):

            self._find_element(
                './/div[@class="row course"]/div[@class="left-matter"]/a',
                'a', 'icon row-hover md-mode-edit')

    def test_edit_unit_availability(self):
        self._add_role_with_permissions(
            [constants.COURSE_OUTLINE_VIEW_PERMISSION])

        # Only unit lock editable.
        with actions.OverriddenSchemaPermission(
            'fake_unit_perm', constants.SCOPE_UNIT,
            self.USER_EMAIL, editable_perms=['is_draft']):

            self._find_element(
                './/li[@data-unit-id="%s"]//div[@class="left-matter"]/div[2]' %
                self.unit.unit_id,
                'div', 'row-hover icon icon-draft-status md md-lock')
            self._find_element(
                './/li[@data-unit-id="%s"]//div[@class="left-matter"]/div[2]' %
                self.assessment.unit_id,
                'div', 'row-hover icon icon-draft-status md inactive md-lock')
            self._find_element(
                './/li[@data-unit-id="%s"]//div[@class="left-matter"]/div[2]' %
                self.link.unit_id,
                'div', 'row-hover icon icon-draft-status md inactive md-lock')

        # Only assessment lock editable
        with actions.OverriddenSchemaPermission(
            'fake_unit_perm', constants.SCOPE_ASSESSMENT,
            self.USER_EMAIL, editable_perms=['assessment/is_draft']):

            self._find_element(
                './/li[@data-unit-id="%s"]//div[@class="left-matter"]/div[2]' %
                self.unit.unit_id,
                'div', 'row-hover icon icon-draft-status md inactive md-lock')
            self._find_element(
                './/li[@data-unit-id="%s"]//div[@class="left-matter"]/div[2]' %
                self.assessment.unit_id,
                'div', 'row-hover icon icon-draft-status md md-lock')
            self._find_element(
                './/li[@data-unit-id="%s"]//div[@class="left-matter"]/div[2]' %
                self.link.unit_id,
                'div', 'row-hover icon icon-draft-status md inactive md-lock')

        # Only link lock editable
        with actions.OverriddenSchemaPermission(
            'fake_unit_perm', constants.SCOPE_LINK,
            self.USER_EMAIL, editable_perms=['is_draft']):

            self._find_element(
                './/li[@data-unit-id="%s"]//div[@class="left-matter"]/div[2]' %
                self.unit.unit_id,
                'div', 'row-hover icon icon-draft-status md inactive md-lock')
            self._find_element(
                './/li[@data-unit-id="%s"]//div[@class="left-matter"]/div[2]' %
                self.assessment.unit_id,
                'div', 'row-hover icon icon-draft-status md inactive md-lock')
            self._find_element(
                './/li[@data-unit-id="%s"]//div[@class="left-matter"]/div[2]' %
                self.link.unit_id,
                'div', 'row-hover icon icon-draft-status md md-lock')

    def test_edit_unit_property_editor_link(self):
        # Verify readability on some random property allows pencil icon
        # link to edit/view props page.

        self._add_role_with_permissions(
            [constants.COURSE_OUTLINE_VIEW_PERMISSION])

        # Only unit lock editable.
        with actions.OverriddenSchemaPermission(
            'fake_unit_perm', constants.SCOPE_UNIT,
            self.USER_EMAIL, editable_perms=['description']):

            self._find_element(
                './/li[@data-unit-id="%s"]//div[@class="left-matter"]/a' %
                self.unit.unit_id,
                'a', 'icon md-mode-edit md row-hover')
            self._find_element(
                './/li[@data-unit-id="%s"]//div[@class="left-matter"]/div[3]' %
                self.assessment.unit_id,
                'div', 'icon inactive')
            self._find_element(
                './/li[@data-unit-id="%s"]//div[@class="left-matter"]/div[3]' %
                self.link.unit_id,
                'div', 'icon inactive')

        # Only assessment lock editable
        with actions.OverriddenSchemaPermission(
            'fake_unit_perm', constants.SCOPE_ASSESSMENT,
            self.USER_EMAIL, editable_perms=['assessment/description']):

            self._find_element(
                './/li[@data-unit-id="%s"]//div[@class="left-matter"]/div[3]' %
                self.unit.unit_id,
                'div', 'icon inactive')
            self._find_element(
                './/li[@data-unit-id="%s"]//div[@class="left-matter"]/a' %
                self.assessment.unit_id,
                'a', 'icon md-mode-edit md row-hover')
            self._find_element(
                './/li[@data-unit-id="%s"]//div[@class="left-matter"]/div[3]' %
                self.link.unit_id,
                'div', 'icon inactive')

        # Only link lock editable
        with actions.OverriddenSchemaPermission(
            'fake_unit_perm', constants.SCOPE_LINK,
            self.USER_EMAIL, editable_perms=['description']):

            self._find_element(
                './/li[@data-unit-id="%s"]//div[@class="left-matter"]/div[3]' %
                self.unit.unit_id,
                'div', 'icon inactive')
            self._find_element(
                './/li[@data-unit-id="%s"]//div[@class="left-matter"]/div[3]' %
                self.assessment.unit_id,
                'div', 'icon inactive')
            self._find_element(
                './/li[@data-unit-id="%s"]//div[@class="left-matter"]/a' %
                self.link.unit_id,
                'a', 'icon md-mode-edit md row-hover')

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
