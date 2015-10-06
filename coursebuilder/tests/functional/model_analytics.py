# coding: utf-8
# Copyright 2013 Google Inc. All Rights Reserved.
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

"""Tests for modules/dashboard/analytics."""

__author__ = 'Julia Oh(juliaoh@google.com)'

import datetime
import os
import time

import cloudstorage

import actions
from actions import assert_contains
from actions import assert_does_not_contain
from actions import assert_equals
from pipeline import models as pipeline_models
from pipeline import pipeline

import appengine_config
from common import utils as common_utils
from controllers import sites
from models import config
from models import courses
from models import entities
from models import jobs
from models import models
from models import transforms
from models.progress import ProgressStats
from models.progress import UnitLessonCompletionTracker
from modules.analytics import analytics
from modules.analytics import rest_providers
from modules.analytics import synchronous_providers
from modules.mapreduce import mapreduce_module

from google.appengine.ext import db


class AnalyticsTabsWithNoJobs(actions.TestBase):

    def tearDown(self):
        config.Registry.test_overrides.clear()

    def test_blank_students_tab_no_mr(self):
        email = 'admin@google.com'
        actions.login(email, is_admin=True)
        self.get('dashboard?action=analytics_students')

    def test_blank_questions_tab_no_mr(self):
        email = 'admin@google.com'
        actions.login(email, is_admin=True)
        self.get('dashboard?action=analytics_questions')

    def test_blank_assessments_tab_no_mr(self):
        email = 'admin@google.com'
        actions.login(email, is_admin=True)
        self.get('dashboard?action=analytics_assessments')

    def test_blank_peer_review_tab_no_mr(self):
        email = 'admin@google.com'
        actions.login(email, is_admin=True)
        self.get('dashboard?action=peer_review')

    def test_blank_students_tab_with_mr(self):
        config.Registry.test_overrides[
            mapreduce_module.GCB_ENABLE_MAPREDUCE_DETAIL_ACCESS.name] = True
        email = 'admin@google.com'
        actions.login(email, is_admin=True)
        self.get('dashboard?action=analytics_students')

    def test_blank_questions_tab_with_mr(self):
        config.Registry.test_overrides[
            mapreduce_module.GCB_ENABLE_MAPREDUCE_DETAIL_ACCESS.name] = True
        email = 'admin@google.com'
        actions.login(email, is_admin=True)
        self.get('dashboard?action=analytics_questions')

    def test_blank_assessments_tab_with_mr(self):
        config.Registry.test_overrides[
            mapreduce_module.GCB_ENABLE_MAPREDUCE_DETAIL_ACCESS.name] = True
        email = 'admin@google.com'
        actions.login(email, is_admin=True)
        self.get('dashboard?action=analytics_assessments')

    def test_blank_peer_review_tab_with_mr(self):
        config.Registry.test_overrides[
            mapreduce_module.GCB_ENABLE_MAPREDUCE_DETAIL_ACCESS.name] = True
        email = 'admin@google.com'
        actions.login(email, is_admin=True)
        self.get('dashboard?action=peer_review')


class ProgressAnalyticsTest(actions.TestBase):
    """Tests the progress analytics page on the Course Author dashboard."""

    EXPECTED_TASK_COUNT = 3

    def test_empty_student_progress_stats_analytics_displays_nothing(self):
        """Test analytics page on course dashboard when no progress stats."""

        # The admin looks at the analytics page on the board to check right
        # message when no progress has been recorded.

        email = 'admin@google.com'
        actions.login(email, is_admin=True)
        response = self.get('dashboard?action=analytics_students')
        assert_contains(
            'Google &gt; Dashboard &gt; Manage &gt; Students', response.body)
        assert_contains('have not been calculated yet', response.body)

        response = response.forms[
            'gcb-generate-analytics-data'].submit().follow()
        assert len(self.taskq.GetTasks('default')) == (
            ProgressAnalyticsTest.EXPECTED_TASK_COUNT)

        assert_contains('is running', response.body)

        self.execute_all_deferred_tasks()

        response = self.get(response.request.url)
        assert_contains('were last updated at', response.body)
        assert_contains('currently enrolled: 0', response.body)
        assert_contains('total: 0', response.body)

        assert_contains('Student Progress', response.body)
        assert_contains(
            'No student progress has been recorded for this course.',
            response.body)
        actions.logout()

    def test_student_progress_stats_analytics_displays_on_dashboard(self):
        """Test analytics page on course dashboard."""

        with actions.OverriddenEnvironment(
            {'course': {analytics.CAN_RECORD_STUDENT_EVENTS: 'true'}}):

            student1 = 'student1@google.com'
            name1 = 'Test Student 1'
            student2 = 'student2@google.com'
            name2 = 'Test Student 2'

            # Student 1 completes a unit.
            actions.login(student1)
            actions.register(self, name1)
            actions.view_unit(self)
            actions.logout()

            # Student 2 completes a unit.
            actions.login(student2)
            actions.register(self, name2)
            actions.view_unit(self)
            actions.logout()

            # Admin logs back in and checks if progress exists.
            email = 'admin@google.com'
            actions.login(email, is_admin=True)
            response = self.get('dashboard?action=analytics_students')
            assert_contains(
                'Google &gt; Dashboard &gt; Manage &gt; Students',
                response.body)
            assert_contains('have not been calculated yet', response.body)

            response = response.forms[
                'gcb-generate-analytics-data'].submit().follow()
            assert len(self.taskq.GetTasks('default')) == (
                ProgressAnalyticsTest.EXPECTED_TASK_COUNT)

            response = self.get('dashboard?action=analytics_students')
            assert_contains('is running', response.body)

            self.execute_all_deferred_tasks()

            response = self.get('dashboard?action=analytics_students')
            assert_contains('were last updated at', response.body)
            assert_contains('currently enrolled: 2', response.body)
            assert_contains('total: 2', response.body)

            assert_contains('Student Progress', response.body)
            assert_does_not_contain(
                'No student progress has been recorded for this course.',
                response.body)
            # JSON code for the completion statistics.
            assert_contains(
                '\\"u.1.l.1\\": {\\"progress\\": 0, \\"completed\\": 2}',
                response.body)
            assert_contains(
                '\\"u.1\\": {\\"progress\\": 2, \\"completed\\": 0}',
                response.body)

    def test_analytics_are_individually_cancelable_and_runnable(self):
        """Test run/cancel controls for individual analytics jobs."""

        # Submit all analytics.
        email = 'admin@google.com'
        actions.login(email, is_admin=True)
        response = self.get('dashboard?action=peer_review')
        response = response.forms[
            'gcb-generate-analytics-data'].submit().follow()

        # Ensure that analytics appear to be running and have cancel buttons.
        assert_contains('is running', response.body)
        assert_contains('Cancel', response.body)

        # Now that all analytics are pending, ensure that update-all button
        # is hidden.
        dom = self.parse_html_string(response.body)
        update_all = dom.find('.//div[@id="analytics-update-all"]')
        cancel_all = dom.find('.//div[@id="analytics-cancel-all"]')
        self.assertEquals(update_all.get('class'),
                          'gcb-button-toolbar not-displayed')
        self.assertEquals(cancel_all.get('class'),
                          'gcb-button-toolbar ')

        # Click the cancel button for one of the slower jobs.
        response = response.forms[
            'gcb-cancel-visualization-peer_review'].submit().follow()

        # Verify that page shows job was canceled.
        assert_contains('error updating peer review statistics', response.body)
        assert_contains('Canceled by ' + email, response.body)

        # We should now have our update-statistics button back.
        self.assertIsNotNone(response.forms['gcb-generate-analytics-data'])

        # Should also have a button to run the canceled job; click that.
        response = response.forms[
            'gcb-run-visualization-peer_review'].submit().follow()

        # All jobs should now again be running, and update-all button hidden.
        dom = self.parse_html_string(response.body)
        update_all = dom.find('.//div[@id="analytics-update-all"]')
        cancel_all = dom.find('.//div[@id="analytics-cancel-all"]')
        self.assertEquals(update_all.get('class'),
                          'gcb-button-toolbar not-displayed')
        self.assertEquals(cancel_all.get('class'),
                          'gcb-button-toolbar ')

    def test_cancel_map_reduce(self):
        email = 'admin@google.com'
        actions.login(email, is_admin=True)
        response = self.get('dashboard?action=peer_review')
        response = response.forms[
            'gcb-run-visualization-peer_review'].submit().follow()

        # Launch 1st stage of map/reduce job; we must do this in order to
        # get the pipeline woken up enough to have built a root pipeline
        # record.  Without this, we do not have an ID to use when canceling.
        self.execute_all_deferred_tasks(iteration_limit=1)

        # Cancel the job.
        response = response.forms[
            'gcb-cancel-visualization-peer_review'].submit().follow()
        assert_contains('Canceled by ' + email, response.body)

        # Now permit any pending tasks to complete, and expect the job's
        # status message to remain at "Canceled by ...".
        #
        # If the cancel didn't take effect, the map/reduce should have run to
        # completion and the job's status would change to completed, changing
        # the message.  This is verified in
        # model_jobs.JobOperationsTest.test_killed_job_can_still_complete
        self.execute_all_deferred_tasks()
        response = self.get(response.request.url)
        assert_contains('Canceled by ' + email, response.body)

    def test_get_entity_id_wrapper_in_progress_works(self):
        """Tests get_entity_id wrappers in progress.ProgressStats."""
        sites.setup_courses('course:/test::ns_test, course:/:/')
        course = courses.Course(None, app_context=sites.get_all_courses()[0])
        progress_stats = ProgressStats(course)
        unit1 = course.add_unit()

        assert_equals(
            progress_stats._get_unit_ids_of_type_unit(), [unit1.unit_id])
        assessment1 = course.add_assessment()
        assert_equals(
            progress_stats._get_assessment_ids(), [assessment1.unit_id])
        lesson11 = course.add_lesson(unit1)
        lesson12 = course.add_lesson(unit1)
        assert_equals(
            progress_stats._get_lesson_ids(unit1.unit_id),
            [lesson11.lesson_id, lesson12.lesson_id])
        lesson11.has_activity = True
        course.set_activity_content(lesson11, u'var activity=[]', [])
        assert_equals(
            progress_stats._get_activity_ids(unit1.unit_id, lesson11.lesson_id),
            [0])
        assert_equals(
            progress_stats._get_activity_ids(unit1.unit_id, lesson12.lesson_id),
            [])

    def test_get_entity_label_wrapper_in_progress_works(self):
        """Tests get_entity_label wrappers in progress.ProgressStats."""
        sites.setup_courses('course:/test::ns_test, course:/:/')
        course = courses.Course(None, app_context=sites.get_all_courses()[0])
        progress_stats = ProgressStats(course)
        unit1 = course.add_unit()

        assert_equals(
            progress_stats._get_unit_label(unit1.unit_id),
            'Unit %s' % unit1.index)
        assessment1 = course.add_assessment()
        assert_equals(
            progress_stats._get_assessment_label(assessment1.unit_id),
            assessment1.title)
        lesson11 = course.add_lesson(unit1)
        lesson12 = course.add_lesson(unit1)
        assert_equals(
            progress_stats._get_lesson_label(unit1.unit_id, lesson11.lesson_id),
            lesson11.index)
        lesson11.has_activity = True
        course.set_activity_content(lesson11, u'var activity=[]', [])
        assert_equals(
            progress_stats._get_activity_label(
                unit1.unit_id, lesson11.lesson_id, 0), 'L1.1')
        assert_equals(
            progress_stats._get_activity_label(
                unit1.unit_id, lesson12.lesson_id, 0), 'L1.2')
        lesson12.objectives = """
            <question quid="123" weight="1" instanceid=1></question>
            random_text
            <gcb-youtube videoid="Kdg2drcUjYI" instanceid="VD"></gcb-youtube>
            more_random_text
            <question-group qgid="456" instanceid=2></question-group>
            yet_more_random_text
        """
        cpt_ids = progress_stats._get_component_ids(
            unit1.unit_id, lesson12.lesson_id, 0)
        self.assertEqual(set([u'1', u'2']), set(cpt_ids))

    def test_compute_entity_dict_constructs_dict_correctly(self):
        sites.setup_courses('course:/test::ns_test, course:/:/')
        course = courses.Course(None, app_context=sites.get_all_courses()[0])
        progress_stats = ProgressStats(course)
        course_dict = progress_stats.compute_entity_dict('course', [])
        assert_equals(course_dict, {
            'label': 'UNTITLED COURSE', 'u': [], 's': []})

    def test_compute_entity_dict_for_non_empty_course_correctly(self):
        """Tests correct entity_structure is built."""

        sites.setup_courses('course:/test::ns_test, course:/:/')
        course = courses.Course(None, app_context=sites.get_all_courses()[0])
        unit1 = course.add_unit()
        assessment1 = course.add_assessment()
        progress_stats = ProgressStats(course)
        expected = {
            'label': 'UNTITLED COURSE',
            'u':
                [{
                    'child_id': unit1.unit_id,
                    'child_val': {
                        'label': 'Unit %s' % unit1.index,
                        'l': [],
                        's': []
                    }
            }],
            's':
                [{
                    'child_id': assessment1.unit_id,
                    'child_val': {'label': assessment1.title}
            }]
        }
        assert_equals(
            expected, progress_stats.compute_entity_dict('course', []))

        lesson11 = course.add_lesson(unit1)
        expected = {
            's': [{
                'child_id': assessment1.unit_id,
                'child_val': {
                    'label': assessment1.title}
                }],
            'u': [{
                'child_id': unit1.unit_id,
                'child_val': {
                    's': [],
                    'l': [{
                        'child_id': lesson11.lesson_id,
                        'child_val': {
                            'a': [],
                            'h': [{
                                'child_id': 0,
                                'child_val': {
                                    'c': [],
                                    'label': 'L1.1'
                                }}],
                            'label': lesson11.index
                        }}],
                    'label': 'Unit %s' % unit1.index}
                }],
            'label': 'UNTITLED COURSE'
        }
        assert_equals(
            expected, progress_stats.compute_entity_dict('course', []))

        lesson11.objectives = """
            <question quid="123" weight="1" instanceid="1"></question>
            random_text
            <gcb-youtube videoid="Kdg2drcUjYI" instanceid="VD"></gcb-youtube>
            more_random_text
            <question-group qgid="456" instanceid="2"></question-group>
            yet_more_random_text
        """
        expected = {
            'label': 'UNTITLED COURSE',
            's': [{
                'child_id': assessment1.unit_id,
                'child_val': {'label': assessment1.title}}],
            'u': [{
                'child_id': unit1.unit_id,
                'child_val': {
                    'label': 'Unit %s' % unit1.index,
                    's': [],
                    'l': [{
                        'child_id': lesson11.lesson_id,
                        'child_val': {
                            'label': lesson11.index,
                            'a': [],
                            'h': [{
                                'child_id': 0,
                                'child_val': {
                                    'c': [{
                                        'child_id': '1',
                                        'child_val': {
                                            'label': 'L1.1.1'
                                        }}, {
                                        'child_id': '2',
                                        'child_val': {
                                            'label': 'L1.1.2'
                                        }
                                        }],
                                    'label': 'L1.1'
                                }
                            }]
                        }
                    }]
                }
            }]
        }
        assert_equals(
            expected, progress_stats.compute_entity_dict('course', []))

    def test_entity_dict_for_pre_post_assessment(self):
        """Tests correct entity_structure is built."""
        sites.setup_courses('course:/test::ns_test, course:/:/')
        course = courses.Course(None, app_context=sites.get_all_courses()[0])
        unit1 = course.add_unit()
        pre_assessment = course.add_assessment()
        pre_assessment.title = 'Pre Assessment'
        post_assessment = course.add_assessment()
        post_assessment.title = 'Post Assessment'

        # Neither pre nor post assessment for unit
        unit1.pre_assessment = None
        unit1.post_assessment = None
        progress_stats = ProgressStats(course)
        expected = {
            's': [{
                'child_id': pre_assessment.unit_id,
                'child_val': {
                    'label': 'Pre Assessment'}}, {
                'child_id': post_assessment.unit_id,
                'child_val': {
                    'label': 'Post Assessment'}}],
             'u': [{
                'child_id': unit1.unit_id,
                'child_val': {
                        's': [],
                        'l': [],
                        'label': 'Unit 1'}}],
             'label': 'UNTITLED COURSE'}
        assert_equals(
            expected, progress_stats.compute_entity_dict('course', []))

        # Only pre
        unit1.pre_assessment = pre_assessment.unit_id
        unit1.post_assessment = None
        progress_stats = ProgressStats(course)
        expected = {
            's': [{
                'child_id': post_assessment.unit_id,
                'child_val': {'label': 'Post Assessment'}}],
            'u': [{
                'child_id': unit1.unit_id,
                'child_val': {
                    's': [{
                        'child_id': pre_assessment.unit_id,
                        'child_val': {'label': 'Pre Assessment'}}],
                    'l': [],
                    'label': 'Unit 1'}}],
            'label': 'UNTITLED COURSE'}
        assert_equals(
            expected, progress_stats.compute_entity_dict('course', []))

        # Only post
        unit1.pre_assessment = None
        unit1.post_assessment = post_assessment.unit_id
        progress_stats = ProgressStats(course)
        expected = {
            's': [{
                'child_id': pre_assessment.unit_id,
                'child_val': {'label': 'Pre Assessment'}}],
            'u': [{
                'child_id': unit1.unit_id,
                'child_val': {
                    's': [{
                        'child_id': post_assessment.unit_id,
                        'child_val': {
                            'label': 'Post Assessment'}}],
                    'l': [],
                    'label': 'Unit 1'}}],
             'label': 'UNTITLED COURSE'}
        assert_equals(
            expected, progress_stats.compute_entity_dict('course', []))

        # Pre and post assessment set.
        unit1.pre_assessment = pre_assessment.unit_id
        unit1.post_assessment = post_assessment.unit_id
        progress_stats = ProgressStats(course)
        expected = {
            's': [],
            'u': [{
                'child_id': unit1.unit_id,
                'child_val': {
                    's': [
                        {
                            'child_id': pre_assessment.unit_id,
                            'child_val': {
                                'label': 'Pre Assessment'}
                        }, {
                            'child_id': post_assessment.unit_id,
                            'child_val': {
                                'label': 'Post Assessment'}
                        }],
                    'l': [],
                    'label': 'Unit 1'}}],
             'label': 'UNTITLED COURSE'}
        assert_equals(
            expected, progress_stats.compute_entity_dict('course', []))



class QuestionAnalyticsTest(actions.TestBase):
    """Tests the question analytics page from Course Author dashboard."""

    def _get_sample_v15_course(self):
        """Creates a course with different types of questions and returns it."""
        sites.setup_courses('course:/test::ns_test, course:/:/')
        course = courses.Course(None, app_context=sites.get_all_courses()[0])
        unit1 = course.add_unit()
        lesson1 = course.add_lesson(unit1)
        assessment_old = course.add_assessment()
        assessment_old.title = 'Old assessment'
        assessment_new = course.add_assessment()
        assessment_new.title = 'New assessment'
        assessment_peer = course.add_assessment()
        assessment_peer.title = 'Peer review assessment'

        # Create a multiple choice question.
        mcq_new_dict = {
            'description': 'mcq_new',
            'type': 0,  # Multiple choice question.
            'choices': [{
                'text': 'answer',
                'score': 1.0
            }],
            'version': '1.5'
        }
        mcq_new_dto = models.QuestionDTO(None, mcq_new_dict)
        mcq_new_id = models.QuestionDAO.save(mcq_new_dto)

        # Create a short answer question.
        frq_new_dict = {
            'defaultFeedback': '',
            'rows': 1,
            'description': 'short answer',
            'hint': '',
            'graders': [{
                'matcher': 'case_insensitive',
                'score': '1.0',
                'response': 'hi',
                'feedback': ''
            }],
            'question': 'short answer question',
            'version': '1.5',
            'type': 1,  # Short answer question.
            'columns': 100
        }
        frq_new_dto = models.QuestionDTO(None, frq_new_dict)
        frq_new_id = models.QuestionDAO.save(frq_new_dto)

        # Create a question group.
        question_group_dict = {
            'description': 'question_group',
            'items': [
                {'question': str(mcq_new_id)},
                {'question': str(frq_new_id)},
                {'question': str(mcq_new_id)}
            ],
            'version': '1.5',
            'introduction': ''
        }
        question_group_dto = models.QuestionGroupDTO(None, question_group_dict)
        question_group_id = models.QuestionGroupDAO.save(question_group_dto)

        # Add a MC question and a question group to leesson1.
        lesson1.objectives = """
            <question quid="%s" weight="1" instanceid="QN"></question>
            random_text
            <gcb-youtube videoid="Kdg2drcUjYI" instanceid="VD"></gcb-youtube>
            more_random_text
            <question-group qgid="%s" instanceid="QG"></question-group>
        """ % (mcq_new_id, question_group_id)

        # Add a MC question, a short answer question, and a question group to
        # new style assessment.
        assessment_new.html_content = """
            <question quid="%s" weight="1" instanceid="QN2"></question>
            <question quid="%s" weight="1" instanceid="FRQ2"></question>
            random_text
            <gcb-youtube videoid="Kdg2drcUjYI" instanceid="VD"></gcb-youtube>
            more_random_text
            <question-group qgid="%s" instanceid="QG2"></question-group>
        """ % (mcq_new_id, frq_new_id, question_group_id)

        return course

    def test_get_summarized_question_list_from_event(self):
        """Tests the transform functions per event type."""
        sites.setup_courses('course:/test::ns_test, course:/:/')
        course = courses.Course(None, app_context=sites.get_all_courses()[0])

        question_aggregator = (synchronous_providers.QuestionStatsGenerator
                               .MultipleChoiceQuestionAggregator(course))

        event_payloads = open(os.path.join(
            appengine_config.BUNDLE_ROOT,
            'tests/unit/common/event_payloads.json')).read()

        event_payload_dict = transforms.loads(event_payloads)
        for event_info in event_payload_dict.values():
            questions = question_aggregator._process_event(
                event_info['event_source'], event_info['event_data'])
            assert_equals(questions, event_info['transformed_dict_list'])

    def test_compute_question_stats_on_empty_course_returns_empty_dicts(self):

        sites.setup_courses('course:/test::ns_test, course:/:/')
        app_context = sites.get_all_courses()[0]

        question_stats_computer = (
            synchronous_providers.QuestionStatsGenerator(app_context))
        id_to_questions, id_to_assessments = question_stats_computer.run()
        assert_equals({}, id_to_questions)
        assert_equals({}, id_to_assessments)

    def test_id_to_question_dict_constructed_correctly(self):
        """Tests id_to_question dicts are constructed correctly."""
        course = self._get_sample_v15_course()
        tracker = UnitLessonCompletionTracker(course)
        assert_equals(
            tracker.get_id_to_questions_dict(),
            {
                'u.1.l.2.c.QN': {
                    'answer_counts': [0],
                    'label': 'Unit 1 Lesson 1, Question mcq_new',
                    'location': 'unit?unit=1&lesson=2',
                    'num_attempts': 0,
                    'score': 0
                },
                'u.1.l.2.c.QG.i.0': {
                    'answer_counts': [0],
                    'label': ('Unit 1 Lesson 1, Question Group question_group '
                              'Question mcq_new'),
                    'location': 'unit?unit=1&lesson=2',
                    'num_attempts': 0,
                    'score': 0
                },
                'u.1.l.2.c.QG.i.2': {
                    'answer_counts': [0],
                    'label': ('Unit 1 Lesson 1, Question Group question_group '
                              'Question mcq_new'),
                    'location': 'unit?unit=1&lesson=2',
                    'num_attempts': 0,
                    'score': 0
                }
            }
        )
        assert_equals(
            tracker.get_id_to_assessments_dict(),
            {
                's.4.c.QN2': {
                    'answer_counts': [0],
                    'label': 'New assessment, Question mcq_new',
                    'location': 'assessment?name=4',
                    'num_attempts': 0,
                    'score': 0
                },
                's.4.c.QG2.i.0': {
                    'answer_counts': [0],
                    'label': ('New assessment, Question Group question_group '
                              'Question mcq_new'),
                    'location': 'assessment?name=4',
                    'num_attempts': 0,
                    'score': 0
                },
                's.4.c.QG2.i.2': {
                    'answer_counts': [0],
                    'label': ('New assessment, Question Group question_group '
                              'Question mcq_new'),
                    'location': 'assessment?name=4',
                    'num_attempts': 0,
                    'score': 0
                }
            }
        )


COURSE_ONE = 'course_one'
COURSE_TWO = 'course_two'


class CronCleanupTest(actions.TestBase):

    def setUp(self):
        super(CronCleanupTest, self).setUp()
        admin_email = 'admin@foo.com'
        self.course_one = actions.simple_add_course(
            COURSE_ONE, admin_email, 'Course One')
        self.course_two = actions.simple_add_course(
            COURSE_TWO, admin_email, 'Course Two')

        actions.login(admin_email, True)
        actions.register(self, admin_email, COURSE_ONE)
        actions.register(self, admin_email, COURSE_TWO)

        self.save_tz = os.environ.get('TZ')
        os.environ['TZ'] = 'GMT'
        time.tzset()

    def tearDown(self):
        if self.save_tz:
            os.environ['TZ'] = self.save_tz
        else:
            del os.environ['TZ']
        time.tzset()

    def _clean_jobs(self, max_age):
        return mapreduce_module.CronMapreduceCleanupHandler._clean_mapreduce(
            max_age)

    def _get_num_root_jobs(self, course_name):
        with common_utils.Namespace('ns_' + course_name):
            return len(pipeline.get_root_list()['pipelines'])

    def _get_cloudstore_paths(self, course_name):
        ret = set()
        with common_utils.Namespace('ns_' + course_name):
            for state in pipeline.get_root_list()['pipelines']:
                root_key = db.Key.from_path(
                    pipeline_models._PipelineRecord.kind(), state['pipelineId'])
                paths = (mapreduce_module.CronMapreduceCleanupHandler
                         ._collect_cloudstore_paths(root_key))
                ret = ret.union(paths)
        return ret

    def _assert_cloudstore_paths_removed(self, course_name, paths):
        with common_utils.Namespace('ns_' + course_name):
            for path in paths:
                with self.assertRaises(cloudstorage.NotFoundError):
                    cloudstorage.open(path)

    def _force_finalize(self, job):
        # For reasons that I do not grok, running the deferred task list
        # until it empties out in test mode does not wind up marking the
        # root job as 'done'.  (Whereas when running the actual service,
        # the job does get marked 'done'.)  This has already cost me most
        # of two hours of debugging, and I'm no closer to figuring out why,
        # much less having a monkey-patch into the Map/Reduce or Pipeline
        # libraries that would correct this.  Cleaner to just transition
        # the job into a completed state manually.
        root_pipeline_id = jobs.MapReduceJob.get_root_pipeline_id(job.load())
        with common_utils.Namespace(job._namespace):
            p = pipeline.Pipeline.from_id(root_pipeline_id)
            context = pipeline._PipelineContext('', 'default', '')
            context.transition_complete(p._pipeline_key)

    def test_non_admin_cannot_cleanup(self):
        actions.login('joe_user@foo.com')
        response = self.get('/cron/mapreduce/cleanup', expect_errors=True)
        self.assertEquals(400, response.status_int)

    def test_admin_cleanup_gets_200_ok(self):
        response = self.get('/cron/mapreduce/cleanup', expect_errors=True,
                            headers={'X-AppEngine-Cron': 'True'})
        self.assertEquals(200, response.status_int)

    def test_no_jobs_no_cleanup(self):
        self.assertEquals(0, self._clean_jobs(datetime.timedelta(seconds=0)))

    def test_unstarted_job_not_cleaned(self):
        mapper = rest_providers.LabelsOnStudentsGenerator(self.course_one)
        mapper.submit()

        self.assertEquals(1, self._get_num_root_jobs(COURSE_ONE))
        self.assertEquals(0, self._clean_jobs(datetime.timedelta(minutes=1)))

    def test_active_job_not_cleaned(self):
        mapper = rest_providers.LabelsOnStudentsGenerator(self.course_one)
        mapper.submit()
        self.execute_all_deferred_tasks(iteration_limit=1)

        self.assertEquals(1, self._get_num_root_jobs(COURSE_ONE))
        self.assertEquals(0, self._clean_jobs(datetime.timedelta(minutes=1)))

    def test_completed_job_is_not_cleaned(self):
        mapper = rest_providers.LabelsOnStudentsGenerator(self.course_one)
        mapper.submit()
        self.execute_all_deferred_tasks()
        self._force_finalize(mapper)

        self.assertEquals(1, self._get_num_root_jobs(COURSE_ONE))
        self.assertEquals(0, self._clean_jobs(datetime.timedelta(minutes=1)))

    def test_terminated_job_with_no_start_time_is_cleaned(self):
        mapper = rest_providers.LabelsOnStudentsGenerator(self.course_one)
        mapper.submit()
        self.execute_all_deferred_tasks(iteration_limit=1)
        mapper.cancel()
        self.execute_all_deferred_tasks()

        self.assertEquals(1, self._get_num_root_jobs(COURSE_ONE))
        self.assertEquals(1, self._clean_jobs(datetime.timedelta(minutes=1)))

        self.execute_all_deferred_tasks(iteration_limit=1)
        self.assertEquals(0, self._get_num_root_jobs(COURSE_ONE))

    def test_incomplete_job_cleaned_if_time_expired(self):
        mapper = rest_providers.LabelsOnStudentsGenerator(self.course_one)
        mapper.submit()
        self.execute_all_deferred_tasks(iteration_limit=1)

        self.assertEquals(1, self._get_num_root_jobs(COURSE_ONE))
        self.assertEquals(1, self._clean_jobs(datetime.timedelta(seconds=0)))

        self.execute_all_deferred_tasks()  # Run deferred deletion task.
        self.assertEquals(0, self._get_num_root_jobs(COURSE_ONE))

    def test_completed_job_cleaned_if_time_expired(self):
        mapper = rest_providers.LabelsOnStudentsGenerator(self.course_one)
        mapper.submit()
        self.execute_all_deferred_tasks()

        self.assertEquals(1, self._get_num_root_jobs(COURSE_ONE))
        self.assertEquals(1, self._clean_jobs(datetime.timedelta(seconds=0)))
        paths = self._get_cloudstore_paths(COURSE_ONE)
        self.assertTrue(len(paths) == 6 or len(paths) == 3)

        self.execute_all_deferred_tasks()  # Run deferred deletion task.
        self.assertEquals(0, self._get_num_root_jobs(COURSE_ONE))
        self._assert_cloudstore_paths_removed(COURSE_ONE, paths)

    def test_multiple_runs_cleaned(self):
        mapper = rest_providers.LabelsOnStudentsGenerator(self.course_one)
        for _ in range(0, 3):
            mapper.submit()
            self.execute_all_deferred_tasks()

        self.assertEquals(3, self._get_num_root_jobs(COURSE_ONE))
        self.assertEquals(3, self._clean_jobs(datetime.timedelta(seconds=0)))
        paths = self._get_cloudstore_paths(COURSE_ONE)
        self.assertTrue(len(paths) == 18 or len(paths) == 9)

        self.execute_all_deferred_tasks()  # Run deferred deletion task.
        self.assertEquals(0, self._get_num_root_jobs(COURSE_ONE))
        self._assert_cloudstore_paths_removed(COURSE_ONE, paths)

    def test_cleanup_modifies_incomplete_status(self):
        mapper = rest_providers.LabelsOnStudentsGenerator(self.course_one)
        mapper.submit()
        self.execute_all_deferred_tasks(iteration_limit=1)

        self.assertEquals(jobs.STATUS_CODE_STARTED, mapper.load().status_code)

        self.assertEquals(1, self._clean_jobs(datetime.timedelta(seconds=0)))
        self.assertEquals(jobs.STATUS_CODE_FAILED, mapper.load().status_code)
        self.assertIn('assumed to have failed', mapper.load().output)

    def test_cleanup_does_not_modify_completed_status(self):
        mapper = rest_providers.LabelsOnStudentsGenerator(self.course_one)
        mapper.submit()
        self.execute_all_deferred_tasks()

        self.assertEquals(jobs.STATUS_CODE_COMPLETED, mapper.load().status_code)

        self.assertEquals(1, self._clean_jobs(datetime.timedelta(seconds=0)))
        self.assertEquals(jobs.STATUS_CODE_COMPLETED, mapper.load().status_code)

    def test_cleanup_in_multiple_namespaces(self):
        mapper_one = rest_providers.LabelsOnStudentsGenerator(self.course_one)
        mapper_two = rest_providers.LabelsOnStudentsGenerator(self.course_two)
        for _ in range(0, 2):
            mapper_one.submit()
            mapper_two.submit()
            self.execute_all_deferred_tasks()

        self.assertEquals(2, self._get_num_root_jobs(COURSE_ONE))
        course_one_paths = self._get_cloudstore_paths(COURSE_ONE)
        self.assertTrue(len(course_one_paths) == 12 or
                        len(course_one_paths) == 6)
        self.assertEquals(2, self._get_num_root_jobs(COURSE_TWO))
        course_two_paths = self._get_cloudstore_paths(COURSE_TWO)
        self.assertTrue(len(course_two_paths) == 12 or
                        len(course_two_paths) == 6)

        self.assertEquals(4, self._clean_jobs(datetime.timedelta(seconds=0)))

        self.execute_all_deferred_tasks()  # Run deferred deletion task.
        self.assertEquals(0, self._get_num_root_jobs(COURSE_ONE))
        self.assertEquals(0, self._get_num_root_jobs(COURSE_TWO))
        self._assert_cloudstore_paths_removed(COURSE_ONE, course_one_paths)
        self._assert_cloudstore_paths_removed(COURSE_TWO, course_two_paths)

    def test_cleanup_handler(self):
        mapper = rest_providers.LabelsOnStudentsGenerator(self.course_one)
        mapper.submit()
        self.execute_all_deferred_tasks(iteration_limit=1)
        mapper.cancel()
        self.execute_all_deferred_tasks()

        self.assertEquals(1, self._get_num_root_jobs(COURSE_ONE))

        # Check that hitting the cron handler via GET works as well.
        # Note that since the actual handler uses a max time limit of
        # a few days, we need to set up a canceled job which, having
        # no defined start-time will be cleaned up immediately.
        self.get('/cron/mapreduce/cleanup',
                 headers={'X-AppEngine-Cron': 'True'})

        self.execute_all_deferred_tasks(iteration_limit=1)
        self.assertEquals(0, self._get_num_root_jobs(COURSE_ONE))


class DummyEntity(entities.BaseEntity):

    NUM_ENTITIES = 1000

    data = db.TextProperty(indexed=False)


class DummyDTO(object):

    def __init__(self, the_id, the_dict):
        self.id = the_id
        self.dict = the_dict

class DummyDAO(models.BaseJsonDao):
    DTO = DummyDTO
    ENTITY = DummyEntity
    ENTITY_KEY_TYPE = models.BaseJsonDao.EntityKeyTypeId
    CURRENT_VERSION = '1.0'

    @classmethod
    def upsert(cls, the_id, the_dict):
        dto = cls.load(the_id)
        if not dto:
            dto = DummyDTO(the_id, the_dict)
            cls.save(dto)


class DummyMapReduceJob(jobs.MapReduceJob):

    NUM_SHARDS = 10
    BOGUS_VALUE_ADDED_IN_COMBINE_STEP = 3
    TOTAL_AGGREGATION_KEY = 'total'

    def entity_class(self):
        return DummyEntity

    @staticmethod
    def map(item):
        # Count up by 1 for this shard.
        yield item.key().id() % DummyMapReduceJob.NUM_SHARDS, 1

        # Count up by 1 for the total number of items processed by M/R job.
        yield DummyMapReduceJob.TOTAL_AGGREGATION_KEY, 1

    @staticmethod
    def combine(key, values, prev_combine_results=None):
        if key != DummyMapReduceJob.TOTAL_AGGREGATION_KEY:
            # Here, we are pretending that the individual key/values
            # other than 'total' are not combine-able.  We thus pass
            # through the individual values for each item unchanged.
            # Note that this verifies that it is supported that
            # combine() may yield multiple values for a single key.
            for value in values:
                yield value
            if prev_combine_results:
                for value in prev_combine_results:
                    yield value
        else:
            # Aggregate values for 'total' here in combine step.
            ret = 0
            for value in values:
                ret += int(value)
            if prev_combine_results:
                for value in prev_combine_results:
                    ret += int(value)

            # Add a weird value to prove that combine() has been called.
            ret += DummyMapReduceJob.BOGUS_VALUE_ADDED_IN_COMBINE_STEP
            yield ret

    @staticmethod
    def reduce(key, values):
        ret = 0
        for value in values:
            ret += int(value)
        yield key, ret


class MapReduceSimpleTest(actions.TestBase):

    # Reserve a bunch of IDs; it appears that when module registration creates
    # objects, some ID counts are reserved, globally, such that we cannot
    # re-use those IDs, even when explicitly set on a different entity type.
    ID_FUDGE = 50

    def setUp(self):
        super(MapReduceSimpleTest, self).setUp()
        admin_email = 'admin@foo.com'
        self.context = actions.simple_add_course('mr_test', admin_email, 'Test')
        actions.login(admin_email, is_admin=True)
        with common_utils.Namespace('ns_mr_test'):
            # Start range after zero, because of reserved/consumed IDs.
            for key in range(self.ID_FUDGE,
                             DummyEntity.NUM_ENTITIES + self.ID_FUDGE):
                DummyDAO.upsert(key, {})

    def test_basic_operation(self):
        job = DummyMapReduceJob(self.context)
        job.submit()
        self.execute_all_deferred_tasks()
        results = jobs.MapReduceJob.get_results(job.load())

        # Expect to see a quantity of results equal to the number of shards,
        # plus one for the 'total' result.
        self.assertEquals(DummyMapReduceJob.NUM_SHARDS + 1, len(results))
        for key, value in results:
            if key == DummyMapReduceJob.TOTAL_AGGREGATION_KEY:
                # Here, we are making the entirely unwarranted assumption that
                # combine() will be called exactly once.  However, given that
                # the entire m/r is being done on a chunk of values that's
                # within the library's single-chunk size, and given that it's
                # running all on one host, etc., it turns out to be reliably
                # true that combine() is called exactly once.
                self.assertEquals(
                    DummyEntity.NUM_ENTITIES +
                    DummyMapReduceJob.BOGUS_VALUE_ADDED_IN_COMBINE_STEP,
                    value)
            else:
                # Here, check that each shard has been correctly aggregated by
                # the reduce step (and implicitly that the values for the
                # indivdual shards made it through the combine() step
                # unchanged)
                self.assertEquals(
                    DummyEntity.NUM_ENTITIES / DummyMapReduceJob.NUM_SHARDS,
                    value)
