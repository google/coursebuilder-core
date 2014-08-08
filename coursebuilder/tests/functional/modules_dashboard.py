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
from controllers import utils
from models import courses
from models import models
from models import transforms
from modules.dashboard.question_group_editor import QuestionGroupRESTHandler

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
        mc_question_id = 1
        mc_question_description = 'Test MC Question'
        mc_question_dto = models.QuestionDTO(mc_question_id, {
            'description': mc_question_description,
            'type': 0  # MC
        })
        models.QuestionDAO.save(mc_question_dto)

        # Create an assessment and add the question to the content
        assessment_one = self.course.add_assessment()
        assessment_one.title = 'Test Assessment One'
        assessment_one.html_content = """
            <question quid="%s" weight="1" instanceid="1"></question>
        """ % mc_question_id

        # Create a second question
        sa_question_id = 2
        sa_question_description = 'Test SA Question'
        sa_question_dto = models.QuestionDTO(sa_question_id, {
            'description': sa_question_description,
            'type': 1  # SA
        })
        models.QuestionDAO.save(sa_question_dto)

        # Create a question group and add the second question
        qg_id = 3
        qg_description = 'Question Group'
        qg_dto = models.QuestionGroupDTO(qg_id, {
              'description': qg_description,
             'items': [{'question': str(sa_question_id)}]
        })
        models.QuestionGroupDAO.save(qg_dto)

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
        question_rows = questions_table.findall('./tbody/tr')
        self.assertEquals(len(question_rows), 2)

        # Check edit link and description of the first question
        first_row = list(question_rows[0])
        first_cell = first_row[0]
        self.assertEquals(first_cell.find('img').tail, mc_question_description)
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
            second_row[0].find('img').tail, sa_question_description)
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
            asset_tables[0].find('./tbody/tr/td').text, 'No questions available'
        )
        self.assertEquals(
            asset_tables[1].find('./tbody/tr/td').text,
            'No question groups available'
        )

    def test_no_question_groups(self):
        description = 'Question description'
        models.QuestionDAO.save(models.QuestionDTO(1, {
            'description': description
        }))
        asset_tables = self._load_tables()
        self.assertEquals(
            asset_tables[0].find('./tbody/tr/td/img').tail, description
        )
        self.assertEquals(
            asset_tables[1].find('./tbody/tr/td').text,
            'No question groups available'
        )

    def test_no_questions(self):
        description = 'Group description'
        models.QuestionGroupDAO.save(models.QuestionGroupDTO(1, {
                    'description': description
        }))
        asset_tables = self._load_tables()
        self.assertEquals(
            asset_tables[0].find('./tbody/tr/td').text, 'No questions available'
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
        question_dto = models.QuestionDTO(1, {})
        models.QuestionDAO.save(question_dto)
        self.assertTrue((begin_time <= question_dto.last_modified) and (
            question_dto.last_modified <= time.time()))

        qg_dto = models.QuestionGroupDTO(1, {})
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
