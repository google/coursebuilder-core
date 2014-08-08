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

import time

import actions
from models import courses
from models import models

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
        assessment_one.title = 'Test Asssessment One'
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
        edit_link = first_row[0].find('a')
        self.assertEquals(edit_link.tail, mc_question_description)
        self.assertEquals(edit_link.get('href'), (
            'dashboard?action=edit_question&key=%s' % mc_question_id))
        # Check if the assessment is listed
        location_link = first_row[2].find('ul/li/a')
        self.assertEquals(location_link.get('href'), (
            'assessment?name=%s' % assessment_one.unit_id))
        self.assertEquals(location_link.text, assessment_one.title)

        # Check second question (=row)
        second_row = list(question_rows[1])
        edit_link = second_row[0].find('a')
        self.assertEquals(edit_link.tail, sa_question_description)
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
            asset_tables[0].find('./tbody/tr/td/a').tail, description
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
