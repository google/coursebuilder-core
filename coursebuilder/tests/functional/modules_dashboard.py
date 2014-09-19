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

"""Tests for modules/dashboard/."""

__author__ = 'Glenn De Jonghe (gdejonghe@google.com)'

import cgi
import time

import actions
from common import crypto
from common.utils import Namespace
from controllers import utils
from models import courses
from models import models
from models import transforms
from models.custom_modules import Module
from models.roles import Permission
from models.roles import Roles
from modules.dashboard import dashboard
from modules.dashboard.dashboard import DashboardHandler
from modules.dashboard.question_group_editor import QuestionGroupRESTHandler
from modules.dashboard.role_editor import RoleRESTHandler

from google.appengine.api import namespace_manager


class QuestionDashboardTestCase(actions.TestBase):
    """Tests Assets > Questions."""
    COURSE_NAME = 'question_dashboard'
    ADMIN_EMAIL = 'admin@foo.com'
    URL = 'dashboard?action=assets&tab=questions'

    def setUp(self):
        super(QuestionDashboardTestCase, self).setUp()

        actions.login(self.ADMIN_EMAIL, is_admin=True)
        self.base = '/' + self.COURSE_NAME
        context = actions.simple_add_course(
            self.COURSE_NAME, self.ADMIN_EMAIL, 'Questions Dashboard')
        self.old_namespace = namespace_manager.get_namespace()
        namespace_manager.set_namespace('ns_%s' % self.COURSE_NAME)

        self.course = courses.Course(None, context)

    def tearDown(self):
        namespace_manager.set_namespace(self.old_namespace)
        super(QuestionDashboardTestCase, self).tearDown()

    def test_table_entries(self):
        # Create a question
        mc_question_description = 'Test MC Question'
        mc_question_dto = models.QuestionDTO(None, {
            'description': mc_question_description,
            'type': 0  # MC
        })
        mc_question_id = models.QuestionDAO.save(mc_question_dto)

        # Create an assessment and add the question to the content
        assessment_one = self.course.add_assessment()
        assessment_one.title = 'Test Assessment One'
        assessment_one.html_content = """
            <question quid="%s" weight="1" instanceid="1"></question>
        """ % mc_question_id

        # Create a second question
        sa_question_description = 'Test SA Question'
        sa_question_dto = models.QuestionDTO(None, {
            'description': sa_question_description,
            'type': 1  # SA
        })
        sa_question_id = models.QuestionDAO.save(sa_question_dto)

        # Create a question group and add the second question
        qg_description = 'Question Group'
        qg_dto = models.QuestionGroupDTO(None, {
              'description': qg_description,
             'items': [{'question': str(sa_question_id)}]
        })
        qg_id = models.QuestionGroupDAO.save(qg_dto)

        # Create a second assessment and add the question group to the content
        assessment_two = self.course.add_assessment()
        assessment_two.title = 'Test Assessment'
        assessment_two.html_content = """
            <question-group qgid="%s" instanceid="QG"></question-group>
        """ % qg_id

        self.course.save()

        # Get the Assets > Question tab
        dom = self.parse_html_string(self.get(self.URL).body)
        asset_tables = dom.findall('.//table[@class="assets-table"]')
        self.assertEquals(len(asset_tables), 2)

        # First check Question Bank table
        questions_table = asset_tables[0]
        question_rows = questions_table.findall('./tbody/tr[@data-filter]')
        self.assertEquals(len(question_rows), 2)

        # Check edit link and description of the first question
        first_row = list(question_rows[0])
        first_cell = first_row[0]
        self.assertEquals(first_cell.findall('a')[1].tail,
                          mc_question_description)
        self.assertEquals(first_cell.find('a').get('href'), (
            'dashboard?action=edit_question&key=%s' % mc_question_id))
        # Check if the assessment is listed
        location_link = first_row[2].find('ul/li/a')
        self.assertEquals(location_link.get('href'), (
            'assessment?name=%s' % assessment_one.unit_id))
        self.assertEquals(location_link.text, assessment_one.title)

        # Check second question (=row)
        second_row = list(question_rows[1])
        self.assertEquals(
            second_row[0].findall('a')[1].tail, sa_question_description)
        # Check whether the containing Question Group is listed
        self.assertEquals(second_row[1].find('ul/li').text, qg_description)

        # Now check Question Group table
        question_groups_table = asset_tables[1]
        row = question_groups_table.find('./tbody/tr')
        # Check edit link and description
        edit_link = row[0].find('a')
        self.assertEquals(edit_link.tail, qg_description)
        self.assertEquals(edit_link.get('href'), (
            'dashboard?action=edit_question_group&key=%s' % qg_id))

        # The question that is part of this group, should be listed
        self.assertEquals(row[1].find('ul/li').text, sa_question_description)

        # Assessment where this Question Group is located, should be linked
        location_link = row[2].find('ul/li/a')
        self.assertEquals(location_link.get('href'), (
            'assessment?name=%s' % assessment_two.unit_id))
        self.assertEquals(location_link.text, assessment_two.title)

    def _load_tables(self):
        asset_tables = self.parse_html_string(self.get(self.URL).body).findall(
            './/table[@class="assets-table"]')
        self.assertEquals(len(asset_tables), 2)
        return asset_tables

    def test_no_questions_and_question_groups(self):
        asset_tables = self._load_tables()
        self.assertEquals(
            asset_tables[0].find('./tfoot/tr/td').text, 'No questions available'
        )
        self.assertEquals(
            asset_tables[1].find('./tfoot/tr/td').text,
            'No question groups available'
        )

    def test_no_question_groups(self):
        description = 'Question description'
        models.QuestionDAO.save(models.QuestionDTO(None, {
            'description': description
        }))
        asset_tables = self._load_tables()
        self.assertEquals(
            asset_tables[0].findall('./tbody/tr/td/a')[1].tail, description
        )
        self.assertEquals(
            asset_tables[1].find('./tfoot/tr/td').text,
            'No question groups available'
        )

    def test_no_questions(self):
        description = 'Group description'
        models.QuestionGroupDAO.save(models.QuestionGroupDTO(None, {
                    'description': description
        }))
        asset_tables = self._load_tables()
        self.assertEquals(
            asset_tables[0].find('./tfoot/tr/td').text, 'No questions available'
        )
        self.assertEquals(
            asset_tables[1].find('./tbody/tr/td/a').tail, description
        )

    def test_if_buttons_are_present(self):
        """Tests if all buttons are present.

            In the past it wasn't allowed to add a question group when there
            were no questions yet.
        """
        body = self.get(self.URL).body
        self.assertIn('Add Short Answer', body)
        self.assertIn('Add Multiple Choice', body)
        self.assertIn('Add Question Group', body)

    def test_adding_empty_question_group(self):
        QG_URL = '/%s%s' % (self.COURSE_NAME, QuestionGroupRESTHandler.URI)
        xsrf_token = crypto.XsrfTokenManager.create_xsrf_token(
            QuestionGroupRESTHandler.XSRF_TOKEN)
        description = 'Question Group'
        payload = {
            'description': description,
            'version': QuestionGroupRESTHandler.SCHEMA_VERSIONS[0],
            'introduction': '',
            'items': []
        }
        response = self.put(QG_URL, {'request': transforms.dumps({
            'xsrf_token': cgi.escape(xsrf_token),
            'payload': transforms.dumps(payload)})})
        self.assertEquals(response.status_int, 200)
        payload = transforms.loads(response.body)
        self.assertEquals(payload['status'], 200)
        self.assertEquals(payload['message'], 'Saved.')
        asset_tables = self._load_tables()
        self.assertEquals(
            asset_tables[1].find('./tbody/tr/td/a').tail, description
        )

    def test_last_modified_timestamp(self):
        begin_time = time.time()
        question_dto = models.QuestionDTO(None, {})
        models.QuestionDAO.save(question_dto)
        self.assertTrue((begin_time <= question_dto.last_modified) and (
            question_dto.last_modified <= time.time()))

        qg_dto = models.QuestionGroupDTO(None, {})
        models.QuestionGroupDAO.save(qg_dto)
        self.assertTrue((begin_time <= qg_dto.last_modified) and (
            question_dto.last_modified <= time.time()))

        asset_tables = self._load_tables()
        self.assertEquals(
            asset_tables[0].find('./tbody/tr/td[@data-timestamp]').get(
                'data-timestamp', ''),
            str(question_dto.last_modified)
        )
        self.assertEquals(
            asset_tables[1].find('./tbody/tr/td[@data-timestamp]').get(
                'data-timestamp', ''),
            str(qg_dto.last_modified)
        )

    def test_question_clone(self):
        # Add a question by just nailing it in to the datastore.
        mc_question_description = 'Test MC Question'
        mc_question_dto = models.QuestionDTO(None, {
            'description': mc_question_description,
            'type': 0  # MC
        })
        models.QuestionDAO.save(mc_question_dto)

        # On the assets -> questions page, clone the question.
        response = self.get(self.URL)
        dom = self.parse_html_string(self.get(self.URL).body)
        clone_link = dom.find('.//a[@class="icon icon-clone"]')
        response = self.get(clone_link.get('href'), response).follow()
        self.assertIn(mc_question_description + ' (clone)', response.body)

    def _call_add_to_question_group(self, qu_id, qg_id, weight, xsrf_token):
        return self.post('dashboard', {
            'action': 'add_to_question_group',
            'question_id': qu_id,
            'group_id': qg_id,
            'weight': weight,
            'xsrf_token': xsrf_token,
        }, True)

    def test_add_to_question_group(self):
        # Create a question
        question_description = 'Question'
        question_dto = models.QuestionDTO(None, {
            'description': question_description,
            'type': 0  # MC
        })
        question_id = models.QuestionDAO.save(question_dto)

        # No groups are present so no add_to_group icon should be present
        self.assertIsNone(self._load_tables()[0].find('./tbody/tr/td[ul]div'))

        # Create a group
        qg_description = 'Question Group'
        qg_dto = models.QuestionGroupDTO(None, {
            'description': qg_description,
            'items': []
        })
        qg_id = models.QuestionGroupDAO.save(qg_dto)

        # Since we now have a group, the add_to_group icon should be visible
        self.assertIsNotNone(
            self._load_tables()[0].find('./tbody/tr/td[ul]/div'))

        # Add Question to Question Group via post_add_to_question_group
        asset_tables = self._load_tables()
        xsrf_token = asset_tables[0].get('data-qg-xsrf-token', '')
        response = self._call_add_to_question_group(
            question_id, qg_id, 1, xsrf_token)

        # Check if operation was successful
        self.assertEquals(response.status_int, 200)
        asset_tables = self._load_tables()
        self.assertEquals(
            asset_tables[0].find('./tbody/tr/td/ul/li').text,
            qg_description
        )
        self.assertEquals(
            asset_tables[1].find('./tbody/tr/td/ul/li').text,
            question_description
        )

        # Check a bunch of calls that should fail
        response = self._call_add_to_question_group(question_id, qg_id, 1, 'a')
        self.assertEquals(response.status_int, 403)

        response = transforms.loads(self._call_add_to_question_group(
            -1, qg_id, 1, xsrf_token).body)
        self.assertEquals(response['status'], 500)

        response = transforms.loads(self._call_add_to_question_group(
            question_id, -1, 1, xsrf_token).body)
        self.assertEquals(response['status'], 500)

        response = transforms.loads(self._call_add_to_question_group(
            'a', qg_id, 1, xsrf_token).body)
        self.assertEquals(response['status'], 500)

        response = transforms.loads(self._call_add_to_question_group(
            question_id, qg_id, 'a', xsrf_token).body)
        self.assertEquals(response['status'], 500)


class CourseOutlineTestCase(actions.TestBase):
    """Tests the Course Outline."""
    COURSE_NAME = 'outline'
    ADMIN_EMAIL = 'admin@foo.com'
    URL = 'dashboard'

    def setUp(self):
        super(CourseOutlineTestCase, self).setUp()

        actions.login(self.ADMIN_EMAIL, is_admin=True)
        self.base = '/' + self.COURSE_NAME
        context = actions.simple_add_course(
            self.COURSE_NAME, self.ADMIN_EMAIL, 'Outline Testing')

        self.course = courses.Course(None, context)

    def _set_draft_status(self, key, component_type, xsrf_token, set_draft):
        return self.post(self.URL, {
            'action': 'set_draft_status',
            'key': key,
            'type': component_type,
            'xsrf_token': xsrf_token,
            'set_draft': set_draft
        }, True)

    def _check_list_item(self, li, href, title, ctype, key, lock_class):
        a = li.find('a')
        self.assertEquals(a.get('href', ''), href)
        self.assertEquals(a.text, title)
        padlock = li.find('div')
        self.assertEquals(padlock.get('data-component-type', ''), ctype)
        self.assertEquals(padlock.get('data-key', ''), str(key))
        self.assertIn(lock_class, padlock.get('class', ''))

    def test_action_icons(self):
        assessment = self.course.add_assessment()
        assessment.title = 'Test Assessment'
        assessment.now_available = True
        link = self.course.add_link()
        link.title = 'Test Link'
        link.now_available = False
        unit = self.course.add_unit()
        unit.title = 'Test Unit'
        unit.now_available = True
        lesson = self.course.add_lesson(unit)
        lesson.title = 'Test Lesson'
        lesson.now_available = False
        self.course.save()

        dom = self.parse_html_string(self.get(self.URL).body)
        course_outline = dom.find('.//ul[@id="course-outline"]')
        xsrf_token = course_outline.get('data-status-xsrf-token', '')
        lis = course_outline.findall('li')
        self.assertEquals(len(lis), 3)

        # Test Assessment
        self._check_list_item(
            lis[0], 'assessment?name=%s' % assessment.unit_id,
            assessment.title, 'unit', assessment.unit_id, 'icon-unlocked'
        )

        # Test Link
        self._check_list_item(
            lis[1], '', link.title, 'unit', link.unit_id, 'icon-locked')

        # Test Unit
        unit_li = lis[2]
        self._check_list_item(
            unit_li, 'unit?unit=%s' % unit.unit_id,
            utils.display_unit_title(unit, {'course': {}}), 'unit',
            unit.unit_id, 'icon-unlocked'
        )

        # Test Lesson
        self._check_list_item(
            unit_li.find('ol/li'),
            'unit?unit=%s&lesson=%s' % (unit.unit_id, lesson.lesson_id),
            lesson.title, 'lesson', lesson.lesson_id, 'icon-locked'
        )

        # Send POST without xsrf token, should give 403
        response = self._set_draft_status(
            assessment.unit_id, 'unit', 'xyz', '1')
        self.assertEquals(response.status_int, 403)

        # Set assessment to private
        response = self._set_draft_status(
            assessment.unit_id, 'unit', xsrf_token, '1')
        self.assertEquals(response.status_int, 200)
        payload = transforms.loads(transforms.loads(response.body)['payload'])
        self.assertEquals(payload['is_draft'], True)

        # Set lesson to public
        response = self._set_draft_status(
            lesson.lesson_id, 'lesson', xsrf_token, '0')
        self.assertEquals(response.status_int, 200)
        payload = transforms.loads(transforms.loads(response.body)['payload'])
        self.assertEquals(payload['is_draft'], False)

        # Refresh page, check results
        lis = self.parse_html_string(
            self.get(self.URL).body).findall('.//ul[@id="course-outline"]/li')
        self.assertIn('icon-locked', lis[0].find('div').get('class', ''))
        self.assertIn(
            'icon-unlocked', lis[2].find('ol/li/div').get('class', ''))

        # Repeat but set assessment to public and lesson to private
        response = self._set_draft_status(
            assessment.unit_id, 'unit', xsrf_token, '0')
        response = self._set_draft_status(
            lesson.lesson_id, 'lesson', xsrf_token, '1')

        # Refresh page, check results
        lis = self.parse_html_string(
            self.get(self.URL).body).findall('.//ul[@id="course-outline"]/li')
        self.assertIn('icon-unlocked', lis[0].find('div').get('class', ''))
        self.assertIn('icon-locked', lis[2].find('ol/li/div').get('class', ''))


class RoleEditorTestCase(actions.TestBase):
    """Tests the Roles tab and Role Editor."""
    COURSE_NAME = 'role_editor'
    ADMIN_EMAIL = 'admin@foo.com'
    URL = 'dashboard?action=roles'

    def setUp(self):
        super(RoleEditorTestCase, self).setUp()

        actions.login(self.ADMIN_EMAIL, is_admin=True)
        self.base = '/' + self.COURSE_NAME
        context = actions.simple_add_course(
            self.COURSE_NAME, self.ADMIN_EMAIL, 'Roles Testing')

        self.course = courses.Course(None, context)

        self.old_namespace = namespace_manager.get_namespace()
        namespace_manager.set_namespace('ns_%s' % self.COURSE_NAME)

        # pylint: disable-msg=protected-access
        self.old_registered_permission = Roles._REGISTERED_PERMISSIONS
        Roles._REGISTERED_PERMISSIONS = {}

    def tearDown(self):
        # pylint: disable-msg=protected-access
        Roles._REGISTERED_PERMISSIONS = self.old_registered_permission
        namespace_manager.set_namespace(self.old_namespace)
        super(RoleEditorTestCase, self).tearDown()

    def _create_role(self, role):
        role_dto = models.RoleDTO(None, {
            'name': role,
        })
        return models.RoleDAO.save(role_dto)

    def test_roles_tab(self):
        role_name = 'Test Role'
        role_id = self._create_role(role_name)
        li = self.parse_html_string(self.get(self.URL).body).find('.//ul/li')
        self.assertEquals(li.text, role_name)
        self.assertEquals(li.find('a').get('href'), (
            'dashboard?action=edit_role&key=%s' % role_id))

    def test_editor_hooks(self):
        # pylint: disable-msg=g-long-lambda
        module1 = Module('module1', '', [], [])
        module2 = Module('module2', '', [], [])
        module3 = Module('module3', '', [], [])
        module4 = Module('module4', '', [], [])
        Roles.register_permissions(module1, lambda unused: [
            Permission('permissiona', 'a'), Permission('permissionb', 'b')])

        Roles.register_permissions(module2, lambda unused: [
            Permission('permissionc', 'c'), Permission('permissiond', 'd')])
        Roles.register_permissions(module4, lambda unused: [
            Permission('permissiong', 'g'), Permission('permissiond', 'h')])
        handler = RoleRESTHandler()
        handler.course = self.course

        datastore_permissions = {
            module1.name: ['permission', 'permissiona', 'permissionb'],
            module2.name: ['permissionc', 'permissiond'],
            module3.name: ['permissione', 'permissionf']
        }
        datastore_dict = {
            'name': 'Role Name',
            'users': ['test@test.com', 'test2@test.com'],
            'permissions': datastore_permissions
        }
        editor_dict = handler.transform_for_editor_hook(datastore_dict)
        self.assertEquals(editor_dict['name'], 'Role Name')
        self.assertEquals(editor_dict['users'], 'test@test.com, test2@test.com')
        modules = editor_dict['modules']
        # Test registered assigned permission
        permissionc = modules[module2.name][0]
        self.assertEquals(permissionc['assigned'], True)
        self.assertEquals(permissionc['name'], 'permissionc')
        self.assertEquals(permissionc['description'], 'c')
        # Test unregistered module with assigned permission
        permissionsf = modules[RoleRESTHandler.INACTIVE_MODULES][1]
        self.assertEquals(permissionsf['assigned'], True)
        self.assertEquals(permissionsf['name'], 'permissionf')
        self.assertEquals(
            permissionsf['description'],
            'This permission was set by the module "module3" which is '
            'currently not registered.'
        )
        # Test registered module with assigned unregistered permission
        permission = modules[module1.name][2]
        self.assertEquals(permission['assigned'], True)
        self.assertEquals(permission['name'], 'permission')
        self.assertEquals(
            permission['description'],
            'This permission is currently not registered.'
        )
        # Test registered unassigned permissions
        permissiong = editor_dict['modules'][module4.name][0]
        self.assertEquals(permissiong['assigned'], False)
        self.assertEquals(permissiong['name'], 'permissiong')
        self.assertEquals(permissiong['description'], 'g')
        # Call the hook which gets called when saving
        new_datastore_dict = handler.transform_after_editor_hook(datastore_dict)
        # If original dict matches new dict then both hooks work correctly
        self.assertEquals(datastore_dict, new_datastore_dict)

    def test_not_unique_role_name(self):
        role_name = 'Test Role'
        role_id = self._create_role(role_name)
        handler = RoleRESTHandler()
        handler.course = self.course
        editor_dict = {
            'name': role_name
        }
        errors = []
        handler.validate(editor_dict, role_id + 1, None, errors)
        self.assertEquals(
            errors[0], 'The role must have a unique non-empty name.')


class DashboardAccessTestCase(actions.TestBase):
    ACCESS_COURSE_NAME = 'dashboard_access_yes'
    NO_ACCESS_COURSE_NAME = 'dashboard_access_no'
    ADMIN_EMAIL = 'admin@foo.com'
    USER_EMAIL = 'user@foo.com'
    ROLE = 'test_role'
    ACTION = 'outline'
    PERMISSION = 'can_access_dashboard'
    PERMISSION_DESCRIPTION = 'Can Access Dashboard.'

    def setUp(self):
        super(DashboardAccessTestCase, self).setUp()
        actions.login(self.ADMIN_EMAIL, is_admin=True)

        context = actions.simple_add_course(
            self.ACCESS_COURSE_NAME, self.ADMIN_EMAIL, 'Course with access')

        self.course_with_access = courses.Course(None, context)

        with Namespace(self.course_with_access.app_context.namespace):
            role_dto = models.RoleDTO(None, {
                'name': self.ROLE,
                'users': [self.USER_EMAIL],
                'permissions': {dashboard.custom_module.name: [self.PERMISSION]}
            })
            models.RoleDAO.save(role_dto)

        context = actions.simple_add_course(
            self.NO_ACCESS_COURSE_NAME, self.ADMIN_EMAIL,
            'Course with no access'
        )

        self.course_without_access = courses.Course(None, context)

        self.old_nav_mappings = DashboardHandler.nav_mappings
        DashboardHandler.nav_mappings = [(self.ACTION, 'outline')]
        DashboardHandler.map_action_to_permission(
            'get_%s'% self.ACTION, self.PERMISSION)
        actions.logout()

    def tearDown(self):
        DashboardHandler.nav_mappings = self.old_nav_mappings
        super(DashboardAccessTestCase, self).tearDown()

    def test_dashboard_access_method(self):
        with Namespace(self.course_with_access.app_context.namespace):
            self.assertFalse(DashboardHandler.current_user_has_access(
                self.course_with_access.app_context))
        with Namespace(self.course_without_access.app_context.namespace):
            self.assertFalse(DashboardHandler.current_user_has_access(
                self.course_without_access.app_context))
        actions.login(self.USER_EMAIL, is_admin=False)
        with Namespace(self.course_with_access.app_context.namespace):
            self.assertTrue(DashboardHandler.current_user_has_access(
                self.course_with_access.app_context))
        with Namespace(self.course_without_access.app_context.namespace):
            self.assertFalse(DashboardHandler.current_user_has_access(
                self.course_without_access.app_context))
        actions.logout()

    def _get_all_picker_options(self):
        return self.parse_html_string(
            self.get('/%s/dashboard' % self.ACCESS_COURSE_NAME).body
        ).findall(
            './/select[@id="gcb-course-picker"]/option')

    def test_course_picker(self):
        actions.login(self.USER_EMAIL, is_admin=False)
        picker_options = self._get_all_picker_options()
        self.assertEquals(len(list(picker_options)), 1)
        self.assertEquals(picker_options[0].get(
            'value'), '/%s/dashboard' % self.ACCESS_COURSE_NAME)
        actions.logout()

        actions.login(self.ADMIN_EMAIL, is_admin=True)
        picker_options = self._get_all_picker_options()
        # Expect 3 courses, as the default one is also considered for the picker
        self.assertEquals(len(picker_options), 3)
        actions.logout()

    def _get_right_nav_links(self):
        return self.parse_html_string(
            self.get('/%s/' % self.ACCESS_COURSE_NAME).body
        ).findall(
            './/div[@id="gcb-nav-x"]/div/ul/li[@class="gcb-pull-right"]')

    def test_dashboard_link(self):
        # Not signed in => no dashboard or admin link visible
        self.assertEquals(len(self._get_right_nav_links()), 0)
        # Sign in user with dashboard permissions => dashboard link visible
        actions.login(self.USER_EMAIL, is_admin=False)
        links = self._get_right_nav_links()
        self.assertEquals(len(links), 1)
        self.assertEquals(links[0].find('a').get('href'), 'dashboard')
        self.assertEquals(links[0].find('a').text, 'Dashboard')
        # Sign in course admin => dashboard link visible
        actions.login(self.ADMIN_EMAIL, is_admin=False)
        links = self._get_right_nav_links()
        self.assertEquals(len(links), 1)
        self.assertEquals(links[0].find('a').get('href'), 'dashboard')
        self.assertEquals(links[0].find('a').text, 'Dashboard')
        # Sign in super admin => dashboard and admin link visible
        actions.login('dummy@email.com', is_admin=True)
        links = self._get_right_nav_links()
        self.assertEquals(len(links), 2)
        self.assertEquals(links[0].find('a').get('href'), '/admin')
        self.assertEquals(links[0].find('a').text, 'Admin')
        self.assertEquals(links[1].find('a').get('href'), 'dashboard')
        self.assertEquals(links[1].find('a').text, 'Dashboard')
