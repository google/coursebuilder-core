# Copyright 2015 Google Inc. All Rights Reserved.
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

"""Tests for modules/analytics/*."""

__author__ = 'Mike Gainer (mgainer@google.com)'

import appengine_config
import datetime
import json
import os
import pprint
import tempfile
import urllib
import zlib

from common import users
from common import utils as common_utils
from models import courses
from models import jobs
from models import models
from models import transforms
from models.progress import UnitLessonCompletionTracker
from modules.analytics import clustering
from modules.analytics import gradebook
from modules.analytics import student_aggregate
from modules.analytics import student_answers
from tests.functional import actions
from tools.etl import etl

from google.appengine.api import namespace_manager


# Note to those extending this set of tests in the future:
# - Make a new course named "test_course".
# - Use the admin user to set up whatever test situation you need.
# - In an incognito window, log in as 'foo@bar.com' and register.
# - Perform relevant user actions to generate EventEntity items.
# - Download test data via:
#
#   echo "a@b.c" | \
#   ./scripts/etl.sh download course /test_course localhost \
#   --archive_path=tests/functional/modules_analytics/TEST_NAME_HERE/course \
#   --internal --archive_type=directory --force_overwrite --no_static_files
#
#   echo "a@b.c" | \
#   ./scripts/etl.sh download datastore /test_course localhost \
#   --archive_path=tests/functional/modules_analytics/TEST_NAME_HERE/datastore \
#   --internal --archive_type=directory --force_overwrite --no_static_files
#
# - Run the following script to dump out the actual values from the
#   map/reduce analytic run.
#
#   ./scripts/test.sh \
#   tests.functional.modules_analytics.NotReallyTest.test_dump_results
#
# - Verify that the JSON result is as-expected.  This is also a good time to
#   edit the dumped events to change fields to manufacture test conditions
#   for malformed data, or to set up cases that are not easy to configure
#   by manual interaction.  (E.g., location and locale for localhost dev
#   environments are not easily changed, but the events are easily edited.)
#
# - Write your test to verify expected vs. actual output.  C.f.
#   StudentAggregateTest.test_page_views

class AbstractModulesAnalyticsTest(actions.TestBase):

    COURSE_NAME = 'test_course'
    ADMIN_EMAIL = 'admin@foo.com'

    def setUp(self):
        super(AbstractModulesAnalyticsTest, self).setUp()
        self.app_context = actions.simple_add_course(
            self.COURSE_NAME, self.ADMIN_EMAIL, 'Analytics Test')
        self.course = courses.Course(None, app_context=self.app_context)
        self.maxDiff = None

    def _get_data_path(self, path):
        return os.path.join(appengine_config.BUNDLE_ROOT, 'modules',
                            'analytics', 'test_courses', path)

    def load_course(self, path):
        data_path = self._get_data_path(path)
        course_data = os.path.join(data_path, 'course')
        datastore_data = os.path.join(data_path, 'datastore')

        # Load the course to the VFS, and populate the DB w/ entities
        parser = etl.create_args_parser()
        etl.add_internal_args_support(parser)
        etl.main(parser.parse_args([
            'upload', 'course', '/' + self.COURSE_NAME, 'localhost',
            '--archive_path', course_data, '--internal', '--archive_type',
            'directory', '--disable_remote', '--force_overwrite', '--log_level',
            'WARNING']))

    def load_datastore(self, path):
        data_path = self._get_data_path(path)
        course_data = os.path.join(data_path, 'course')
        datastore_data = os.path.join(data_path, 'datastore')

        parser = etl.create_args_parser()
        etl.add_internal_args_support(parser)
        etl.main(parser.parse_args([
            'upload', 'datastore', '/' + self.COURSE_NAME, 'localhost',
            '--archive_path', datastore_data, '--internal', '--archive_type',
            'directory', '--disable_remote', '--force_overwrite', '--log_level',
            'WARNING', '--exclude_types',
            ','.join([
                'Submission', 'FileDataEntity', 'FileMetadataEntity'])]))

    def get_aggregated_data_by_email(self, email):
        # email and user_id must match the values listed in Student.json file
        user = users.User('foo@bar.com', _user_id='124317316405206137111')

        with common_utils.Namespace('ns_' + self.COURSE_NAME):
            student = models.Student.get_by_user(user)
            aggregate_entity = (
                student_aggregate.StudentAggregateEntity.get_by_key_name(
                    student.user_id))
            return transforms.loads(zlib.decompress(aggregate_entity.data))

    def load_expected_data(self, path, item):
        data_path = self._get_data_path(path)
        expected_path = os.path.join(data_path, 'expected', item)
        with open(expected_path) as fs:
            data = fs.read()
            return transforms.loads(data)

    def run_aggregator_job(self):
        job = student_aggregate.StudentAggregateGenerator(self.app_context)
        job.submit()
        self.execute_all_deferred_tasks()


class NotReallyTest(AbstractModulesAnalyticsTest):

    def test_dump_results(self):
        """Convenience "test" to run analytic job and dump results to stdout."""
        # Change these values as appropriate to match the test case for which
        # you wish to dump output.
        test_data_subdir = 'multiple'
        test_student_email = 'foo@bar.com'

        self.load_course('simple_questions')
        self.load_datastore(test_data_subdir)
        self.run_aggregator_job()
        actual = self.get_aggregated_data_by_email(test_student_email)
        print '############################### Pretty-printed version:'
        pprint.pprint(actual)
        print '############################### JSON version:'
        print transforms.dumps(actual)


class StudentAggregateTest(AbstractModulesAnalyticsTest):

    def test_page_views(self):
        self.load_course('simple_questions')
        self.load_datastore('page_views')
        self.run_aggregator_job()
        actual = self.get_aggregated_data_by_email('foo@bar.com')

        # This verifies the following cases:
        # - Only /course is submitted in URL; correct unit/lesson is found.
        # - Only /unit is submitted in URL; correct unit/lesson is found
        # - Full /unit?unit=X&lesson=Y ; correct unit/lesson logged.
        # - Page enter but not exit
        # - Page exit but not enter
        # - YouTube events
        # - Events are present (and reported on in output) for unit, lesson,
        #   and assessment that have been deleted after events were recorded.
        expected = self.load_expected_data('page_views', 'page_views.json')
        expected.sort(key=lambda x: (x['name'], x.get('id'), x.get('start')))
        actual['page_views'].sort(
            key=lambda x: (x['name'], x.get('id'), x.get('start')))
        self.assertEqual(expected, actual['page_views'])

    def test_location_locale_user_agent(self):
        self.load_course('simple_questions')
        self.load_datastore('location_locale')
        self.run_aggregator_job()
        actual = self.get_aggregated_data_by_email('foo@bar.com')

        # This verifies the following cases:
        # - Multiple different countries (4 US, 2 AR, 1 DE, 1 ES) and that
        #   these are reported with their correct fractional weights.
        expected = self.load_expected_data('location_locale',
                                           'location_frequencies.json')
        expected.sort(key=lambda x: (x['country'], x['frequency']))
        actual['location_frequencies'].sort(
            key=lambda x: (x['country'], x['frequency']))
        self.assertEqual(expected, actual['location_frequencies'])

        # This verifies the following cases:
        # - Multiple different locales (4 en_US, 2 es_AR, 1 de_DE, 1 es_ES)
        #   and that these are reported with their correct fractional weights.
        expected = self.load_expected_data('location_locale',
                                           'locale_frequencies.json')
        expected.sort(key=lambda x: (x['locale'], x['frequency']))
        actual['locale_frequencies'].sort(
            key=lambda x: (x['locale'], x['frequency']))
        self.assertEqual(expected, actual['locale_frequencies'])

        # This verifies the following cases:
        # - Multiple different user agents at 50%, 25%, 12.5%, 12.5%
        #   and that these are reported with their correct fractional weights.
        expected = self.load_expected_data('location_locale',
                                           'user_agent_frequencies.json')
        expected.sort(key=lambda x: (x['user_agent'], x['frequency']))
        actual['user_agent_frequencies'].sort(
            key=lambda x: (x['user_agent'], x['frequency']))
        self.assertEqual(expected, actual['user_agent_frequencies'])

    def test_scoring(self):
        self.load_course('simple_questions')
        self.load_datastore('scoring')
        self.run_aggregator_job()
        actual = self.get_aggregated_data_by_email('foo@bar.com')

        # This verifies the following cases:
        # - All combinations of:
        #   {Short-Answer, Multiple-Choice} x
        #   {unscored lesson, scored lesson, assessment} x
        #   {bare question, questions in question-group}
        # - Scoring with weights for:
        #   * different answers within a question
        #   * usage of question within scored lesson
        #   * usage of question within question group
        # - Answers of various degrees of correctness
        # - Different usages of the same question on different pages
        expected = self.load_expected_data('scoring', 'assessments.json')
        expected.sort(key=lambda x: (x['unit_id'], x['lesson_id']))
        actual['assessments'].sort(key=lambda x: (x['unit_id'], x['lesson_id']))
        self.assertEqual(expected, actual['assessments'])

    def test_bad_references_in_assessments(self):
        self.load_course('bad_references')
        self.load_datastore('bad_references')
        self.run_aggregator_job()
        actual = self.get_aggregated_data_by_email('foo@bar.com')

        # This verifies the following cases:
        # - For all below, submission on: lesson, scored-lesson, assessment
        # - Question, group, and container still present and valid.
        # - Question and question-group removed, but still referenced
        # - Question group modified: remove one member (but don't delete member)
        # - Question group modified: delete referenced question.
        # - Containers removed.
        expected = self.load_expected_data('bad_references', 'assessments.json')
        expected.sort(key=lambda x: (x['unit_id'], x['lesson_id']))
        actual['assessments'].sort(key=lambda x: (x['unit_id'], x['lesson_id']))
        self.assertEqual(expected, actual['assessments'])

    def test_multiple_submissions(self):
        self.load_course('simple_questions')
        self.load_datastore('multiple')
        self.run_aggregator_job()
        actual = self.get_aggregated_data_by_email('foo@bar.com')

        # This verifies the following items for multiple submissions on the
        # same assessment:
        # - min/max/first/last scores
        # - that multiple submission actually works
        # - Having gotten 100% on assessment means certificate earned
        expected = self.load_expected_data('multiple', 'assessments.json')
        expected.sort(key=lambda x: (x['unit_id'], x['lesson_id']))
        actual['assessments'].sort(key=lambda x: (x['unit_id'], x['lesson_id']))
        self.assertEqual(expected, actual['assessments'])
        self.assertTrue(actual['earned_certificate'])

    def test_youtube_events(self):
        self.load_course('simple_questions')
        self.load_datastore('youtube_events')
        self.run_aggregator_job()
        actual = self.get_aggregated_data_by_email('foo@bar.com')

        # This verifies the following items:
        # - Play video XJk8ijAUCiI from start to finish.
        # - Play video Kdg2drcUjYI for a couple of seconds, then pause.
        # - Rewind that video to 0 seconds, and re-start (makes new entry)
        # - Play video XJk8ijAUCiI for a few seconds, and pause.
        # - While other is paused, play Kdg2drcUjYI start-to-end
        # - Resume video XJk8ijAUCiI and play to end.
        expected = self.load_expected_data('youtube_events', 'youtube.json')
        # No sorting - items should be presented in order by time, video, etc.
        self.assertEqual(expected, actual['youtube'])


class ClusteringTabTests(actions.TestBase):
    """Test for the clustering subtab of analytics tab."""
    COURSE_NAME = 'clustering_course'
    ADMIN_EMAIL = 'test@example.com'
    NON_ADMIN_EMAIL = 'test2@example.com'
    CLUSTER_TAB_URL = (
        '/{}/dashboard?action=analytics_clustering'.format(COURSE_NAME))

    def setUp(self):
        super(ClusteringTabTests, self).setUp()
        self.base = '/' + self.COURSE_NAME
        self.context = actions.simple_add_course(
            self.COURSE_NAME, self.ADMIN_EMAIL, 'Clustering Course')

        self.old_namespace = namespace_manager.get_namespace()
        namespace_manager.set_namespace('ns_%s' % self.COURSE_NAME)

        actions.login(self.ADMIN_EMAIL, is_admin=True)

    def tearDown(self):
        # Clean up app_context.
        namespace_manager.set_namespace(self.old_namespace)
        super(ClusteringTabTests, self).tearDown()

    def test_non_admin_access(self):
        """With no admin registration expect redirection."""
        actions.logout()
        actions.login(self.NON_ADMIN_EMAIL, is_admin=False)
        response = self.get(self.CLUSTER_TAB_URL, expect_errors=True)
        self.assertEquals(302, response.status_int)

    def _add_clusters(self, clusters_number):
        """Adds the given clusters_number clusters to the db and saves the keys.
        """
        self.clusters_keys = []
        self.description_str = ('This is a fairly good description of the'
                                ' cluster{}')
        self.name_str = 'strange cluster name{}'
        for index in range(clusters_number):
            new_cluster = clustering.ClusterDTO(None,
                {'name': self.name_str.format(index),
                 'description': self.description_str.format(index),
                 'vector': []})
            self.clusters_keys.append(clustering.ClusterDAO.save(new_cluster))

    def _add_unit_to_course(self):
        course = courses.Course(None, self.context)
        course.add_unit()
        course.save()

    def test_all_clusters_listed(self):
        """All the clusters in the db are listed in the page."""
        self._add_unit_to_course()
        clusters_number = 100
        self._add_clusters(clusters_number)
        response = self.get(self.CLUSTER_TAB_URL)
        self.assertEquals(200, response.status_code,
            msg='Cluster tab not found. Code {}'.format(response.status_code))
        dom = self.parse_html_string(response.body)
        table = dom.find('.//table[@id="gcb-clustering"]')
        self.assertIsNotNone(table)
        rows = table.findall('.//tr')
        self.assertEqual(len(rows), clusters_number + 1)  # Title first

        # Check the names
        for index in range(clusters_number):
            self.assertIn(self.name_str.format(index), response.body,
                msg='Cluster name not present in page')
            self.assertIn(self.description_str.format(index), response.body,
                msg='Cluster description not present in page')

    def test_no_add_cluster_button_when_no_course_elements(self):
        url = 'dashboard?action=add_cluster'
        response = self.get(self.CLUSTER_TAB_URL)
        self.assertNotIn(url, response.body,
                         msg='Url for add cluster unexpectedly found.')

    def test_add_cluster_button(self):
        """There is a new cluster button in the page"""
        self._add_unit_to_course()
        url = 'dashboard?action=add_cluster'
        response = self.get(self.CLUSTER_TAB_URL)
        self.assertIn(url, response.body, msg='No url for add cluster found.')

    def test_edit_correct_url_present(self):
        """There is a correct update link for each cluster."""
        self._add_unit_to_course()
        clusters_number = 10
        url = 'dashboard?action=edit_cluster&amp;key={}'
        self._add_clusters(clusters_number)
        response = self.get(self.CLUSTER_TAB_URL)
        for cluster_key in self.clusters_keys:
            self.assertIn(url.format(cluster_key), response.body)

    def test_add_cluster_redirects_when_no_clusterables(self):
        response = self.get('/%s/dashboard?action=add_cluster' %
                            self.COURSE_NAME)
        self.assertEquals(302, response.status_int)
        self.assertEquals(
            'http://localhost/%s/dashboard?action=analytics_clustering' %
            self.COURSE_NAME, response.location)

    def test_edit_cluster_redirects_when_no_clusterables(self):
        response = self.get('/%s/dashboard?action=edit_cluster' %
                            self.COURSE_NAME)
        self.assertEquals(302, response.status_int)
        self.assertEquals(
            'http://localhost/%s/dashboard?action=analytics_clustering' %
            self.COURSE_NAME, response.location)

class ClusterRESTHandlerTest(actions.TestBase):
    """Tests for the add_cluster handler and page."""

    COURSE_NAME = 'clustering_course'
    ADMIN_EMAIL = 'test@example.com'
    NON_ADMIN_EMAIL = 'test2@example.com'
    CLUSTER_GET_URL = ('/{}/rest/cluster?key='.format(COURSE_NAME))
    CLUSTER_PUT_URL = ('/{}/rest/cluster'.format(COURSE_NAME))
    CLUSTER_ADD_URL = ('/{}/dashboard?action=add_cluster'.format(COURSE_NAME))

    def setUp(self):
        super(ClusterRESTHandlerTest, self).setUp()
        self.base = '/' + self.COURSE_NAME
        self.app_context = actions.simple_add_course(
            self.COURSE_NAME, self.ADMIN_EMAIL, 'Clustering Course')

        self.old_namespace = namespace_manager.get_namespace()
        namespace_manager.set_namespace('ns_%s' % self.COURSE_NAME)

        self.course = courses.Course(None, self.app_context)

        actions.login(self.ADMIN_EMAIL, is_admin=True)
        self._q_usage_counter = 1000  # To not confuse usage id with ids.
        self._add_contents()

    def tearDown(self):
        namespace_manager.set_namespace(self.old_namespace)
        super(ClusterRESTHandlerTest, self).tearDown()

    def _add_unit(self, u_index):
        """Adds a unit to the course and records the u_index and unit_id."""
        unit = self.course.add_unit()
        unit.title = self.unit_name_str.format(u_index)
        unit.availability = courses.AVAILABILITY_AVAILABLE
        self.unit_keys.append((u_index, unit.unit_id))
        return unit

    def _add_lesson(self, u_index, unit):
        """Adds a lesson to the course and records the u_index and lesson_id."""
        lesson = self.course.add_lesson(unit)
        lesson.title = self.lesson_name_str.format(u_index)
        lesson.availability = courses.AVAILABILITY_AVAILABLE
        lesson.scored = True
        lesson.objectives = ''
        self.lesson_keys.append((u_index, lesson.lesson_id))
        return lesson

    def _add_question(self, q_index, target, target_attr):
        """Adds a questions in db and in the content of target. Saves the key.
        """
        self._q_usage_counter += 1
        question_dto = models.QuestionDTO(None, {
            'description': self.descript_str.format(target.unit_id, q_index),
            'type': 1})
        question_id = models.QuestionDAO.save(question_dto)
        new_attr = (getattr(target, target_attr) or '') + (
            '<question quid="{}" weight="1" instanceid="{}">'
            '</question>'.format(question_id, self._q_usage_counter))
        setattr(target, target_attr, new_attr)
        lesson_id = getattr(target, 'lesson_id', None)
        self.questions_keys.append(
            (target.unit_id, lesson_id, q_index, question_id))

    def _add_question_group(self, target, target_attr, items):
        """Adds a question group to the db and to the content of target."""
        self._q_usage_counter += 1
        question_group_dto = models.QuestionGroupDTO(None, {
            'description': 'Question group',
            'items': items,
            'version': '1.5'})
        question_group_id = models.QuestionGroupDAO.save(question_group_dto)
        qg_str = '<question-group qgid="{}" instanceid="{}"></question-group>'
        new_attr = (getattr(target, target_attr, '') +
                    qg_str.format(question_group_id, self._q_usage_counter))
        setattr(target, target_attr, new_attr)

    def _add_assessment(self, u_index):
        """Adds an assessment to the course and records the u_index and id."""
        assessment = self.course.add_assessment()
        assessment.title = self.assessment_name_str.format(u_index)
        assessment.availability = courses.AVAILABILITY_AVAILABLE
        self.assessment_keys.append((u_index, assessment.unit_id))
        return assessment

    def _add_contents(self):
        """Adds units, questions and lessons to the course."""
        self.units_number = 10
        self.question_numbers = 10
        self.unit_name_str = 'Very cool and unique unit name{}'
        self.descript_str = ('Description of a question that you hardly '
                             'see unless introduced by this test{}{}')
        self.lesson_name_str = 'This is a very very good lesson{}'
        self.assessment_name_str = 'This is the most hard assessment{}'
        self.unit_keys = []
        self.lesson_keys = []
        self.questions_keys = []
        self.assessment_keys = []
        for u_index in range(self.units_number):
            unit = self._add_unit(u_index)
            lesson = self._add_lesson(u_index, unit)
            for q_index in range(self.question_numbers):
                self._add_question(q_index, lesson, 'objectives')
            assessment = self._add_assessment(u_index)
            self._add_question(self.question_numbers+2, assessment,
                               'html_content')
            self.course.save()

    def _add_cluster(self):
        """Adds the given clusters_number clusters to the db and saves the keys.
        """
        cluster_description = 'This is a good description of the cluster'
        cluster_name = 'strange cluster name'
        vector = [{clustering.DIM_TYPE: clustering.DIM_TYPE_UNIT,
                   clustering.DIM_ID: 1,
                   clustering.DIM_LOW: 10,
                   clustering.DIM_HIGH: 50}]
        new_cluster = clustering.ClusterDTO(None,
            {'name': cluster_name,
             'description': cluster_description,
             'version': clustering.ClusterRESTHandler.SCHEMA_VERSIONS[0],
             'vector': vector})
        return clustering.ClusterDAO.save(new_cluster)

    def _send_put_resquest(self, key, cluster, xsrf_token):
        """Build and send a put request. Returns the response."""
        request = {}
        request['key'] = key
        request['payload'] = json.dumps(cluster)
        request['xsrf_token'] = xsrf_token
        return self.put(self.CLUSTER_PUT_URL + '?%s' % urllib.urlencode(
            {'request': transforms.dumps(request)}), {})

    def _dim_from_dict(self, vector, dimension_id, dimension_type):
        candidates = [dim for dim in vector
                      if dim[clustering.DIM_ID] == dimension_id and
                      dim[clustering.DIM_TYPE] == dimension_type]
        error_msg = 'Dimension type:{} id:{} not founded'
        self.assertEqual(len(candidates), 1,
                         msg=error_msg.format(dimension_type, dimension_id))
        return candidates[0]

    def _check_questions(self, vector):
        for unit_id, lesson_id, q_index, question_key in self.questions_keys:
            dimension_id = clustering.pack_question_dimid(
                unit_id, lesson_id, question_key)
            dim = self._dim_from_dict(vector, dimension_id,
                                      clustering.DIM_TYPE_QUESTION)
            self.assertEqual(dim['name'],
                self.descript_str.format(unit_id, q_index))

    def _check_lessons(self, vector):
        for l_index, lesson_key in self.lesson_keys:
            dim = self._dim_from_dict(vector, lesson_key,
                                      clustering.DIM_TYPE_LESSON)
            self.assertEqual(dim['name'],
                             self.lesson_name_str.format(l_index))

    def test_all_dimensions_units_scores(self):
        """All units are listed as dimensions in default content."""
        vector = clustering.get_possible_dimensions(self.app_context)
        for u_index, unit_key in self.unit_keys:
            dim = self._dim_from_dict(vector, unit_key,
                                      clustering.DIM_TYPE_UNIT)
            self.assertEqual(dim['name'],
                             self.unit_name_str.format(u_index))
            self.assertIn(clustering.DIM_EXTRA_INFO, dim)
            extra_info = json.loads(dim[clustering.DIM_EXTRA_INFO])
            self.assertEqual(extra_info['unit_scored_lessons'], 1)

    def test_all_dimensions_unit_visits(self):
        """All units must have a visits dimension."""
        self._add_unit(self.units_number + 10)
        self.course.save()
        u_index, unit_id = self.unit_keys[-1]
        vector = clustering.get_possible_dimensions(self.app_context)
        dim = self._dim_from_dict(vector, unit_id,
                                  clustering.DIM_TYPE_UNIT_VISIT)
        self.assertNotEqual(dim['name'], self.unit_name_str.format(u_index))
        self.assertIn('visits', dim['name'])

    def test_all_dimensions_unit_progress(self):
        """All units must have a progress dimension.

        This new unit will no be obtained using OrderedQuestionsDataSource.
        """
        self._add_unit(self.units_number + 10)
        self.course.save()
        u_index, unit_id = self.unit_keys[-1]
        vector = clustering.get_possible_dimensions(self.app_context)
        dim = self._dim_from_dict(vector, unit_id,
                                  clustering.DIM_TYPE_UNIT_PROGRESS)
        self.assertNotEqual(dim['name'], self.unit_name_str.format(u_index))
        self.assertIn('progress', dim['name'])

    def test_all_dimensions_lessons(self):
        """All lessons are listed as dimensions in default content."""
        vector = clustering.get_possible_dimensions(self.app_context)
        self._check_lessons(vector)

    def test_all_dimensions_lessons_progress(self):
        """All lessons must have a progress dimension.

        This new lesson will no be obtained using OrderedQuestionsDataSource.
        """
        unit = self._add_unit(self.units_number + 10)
        self._add_lesson(self.units_number + 12, unit)
        l_index, lesson_id = self.lesson_keys[-1]
        self.course.save()
        vector = clustering.get_possible_dimensions(self.app_context)
        dim = self._dim_from_dict(vector, lesson_id,
                                  clustering.DIM_TYPE_LESSON_PROGRESS)
        self.assertNotEqual(dim['name'], self.lesson_name_str.format(l_index))
        self.assertIn('progress', dim['name'])
        self.assertIn(clustering.DIM_EXTRA_INFO, dim)
        self.assertEqual(dim[clustering.DIM_EXTRA_INFO],
                         transforms.dumps({'unit_id': unit.unit_id}))

    def test_all_dimensions_questions(self):
        """All questions are listed as dimensions in default content."""
        vector = clustering.get_possible_dimensions(self.app_context)
        self._check_questions(vector)

    def test_all_dimensions_multiple_usage_id(self):
        """Questions with more than one usage id are listed as dimensions."""
        # Get a lesson
        unit = self.course.find_unit_by_id(self.unit_keys[0][1])
        lesson = self.course.find_lesson_by_id(unit, self.lesson_keys[0][1])
        question_id = 15
        lesson.objectives += (
            '<question quid="{}" weight="1" instanceid="{}">'
            '</question>'.format(question_id, self._q_usage_counter + 1))
        self.course.save()

        vector = clustering.get_possible_dimensions(self.app_context)
        dimension_id = clustering.pack_question_dimid(
            unit.unit_id, lesson.lesson_id, question_id)
        self._dim_from_dict(vector, dimension_id,
                            clustering.DIM_TYPE_QUESTION)

    def test_all_dimensions_question_group(self):
        """Questions added in a question group are listed as dimensions."""
        unit = self.course.find_unit_by_id(self.unit_keys[0][1])
        lesson = self.course.find_lesson_by_id(unit, self.lesson_keys[0][1])
        items = [{'question':self.questions_keys[-1][-1]}]
        self._add_question_group(lesson, 'objectives', items)
        self.course.save()
        dimension_id = clustering.pack_question_dimid(
            unit.unit_id, lesson.lesson_id, self.questions_keys[-1][-1])
        vector = clustering.get_possible_dimensions(self.app_context)
        self._dim_from_dict(vector, dimension_id,
                            clustering.DIM_TYPE_QUESTION)

    def test_all_dimensions_assessments(self):
        """All assessments are listed as dimensions in default content."""
        vector = clustering.get_possible_dimensions(self.app_context)
        for u_index, assessment_key in self.assessment_keys:
            dim = self._dim_from_dict(vector, assessment_key,
                                      clustering.DIM_TYPE_UNIT)
            self.assertEqual(dim['name'],
                             self.assessment_name_str.format(u_index))

    def test_no_scored_lesson(self):
        """Non scored lessons should not be included as possible dimensions.
        """
        unit = self.course.find_unit_by_id(self.unit_keys[0][1])
        lesson = self._add_lesson(1, unit)
        lesson.scored = False
        self._add_question(6, lesson, 'objectives')
        self.course.save()

        vector = clustering.get_possible_dimensions(self.app_context)
        for dim in vector:
            if (dim[clustering.DIM_ID] == lesson.lesson_id and
                dim[clustering.DIM_TYPE] == clustering.DIM_TYPE_LESSON):
                self.assertTrue(False,
                                msg='Not scored lesson listed as dimension')
            if (dim[clustering.DIM_ID] == unit.unit_id and
                dim[clustering.DIM_TYPE] == clustering.DIM_TYPE_UNIT):
                extra_info = json.loads(dim[clustering.DIM_EXTRA_INFO])
                self.assertEqual(extra_info['unit_scored_lessons'], 1,
                                 msg='Not scored lesson counted in unit')

    def test_all_dimensions_pre_assessment(self):
        """All units pre assessments and their questions as dimensions.
        """
        unit = self.course.find_unit_by_id(self.unit_keys[0][1])
        assessment = self._add_assessment(self.units_number + 10)
        self._add_question(self.question_numbers*self.units_number,
                           assessment, 'html_content')
        unit.pre_assessment = assessment.unit_id
        self.course.save()

        vector = clustering.get_possible_dimensions(self.app_context)

        # Check the assessment
        dim = self._dim_from_dict(vector, assessment.unit_id,
                                  clustering.DIM_TYPE_UNIT)
        self.assertIsNotNone(dim)
        # Check the question
        question_id = self.questions_keys[-1][-1]
        question_id = clustering.pack_question_dimid(assessment.unit_id,
                                                     None, question_id)
        dim = self._dim_from_dict(vector, question_id,
                                  clustering.DIM_TYPE_QUESTION)
        self.assertIsNotNone(dim)

    def test_save_name(self):
        """Save cluster with correct name."""
        # get a sample payload
        response = self.get(self.CLUSTER_GET_URL)
        transformed_response = transforms.loads(response.body)
        default_cluster = json.loads(transformed_response['payload'])
        cluster_name = 'Name for the cluster number one.'
        default_cluster['name'] = cluster_name

        response = self._send_put_resquest(None, default_cluster,
                                           transformed_response['xsrf_token'])

        # get the key
        cid = json.loads(transforms.loads(response.body)['payload'])['key']
        cluster = clustering.ClusterDAO.load(cid)
        self.assertIsNotNone(cluster, msg='Cluster not saved.')
        self.assertEqual(cluster.name, cluster_name, msg='Wrong name saved')

    def test_save_empty_name(self):
        """If the cluster has no name expect error."""
        # get a sample payload
        response = self.get(self.CLUSTER_GET_URL)
        transformed_response = transforms.loads(response.body)
        default_cluster = json.loads(transformed_response['payload'])

        response = self._send_put_resquest(None, default_cluster,
                                           transformed_response['xsrf_token'])

        self.assertIn('"status": 412', response.body)

    def test_save_description(self):
        """Save cluster with correct description."""
        # get a sample payload
        response = self.get(self.CLUSTER_GET_URL)
        transformed_response = transforms.loads(response.body)
        default_cluster = json.loads(transformed_response['payload'])
        cluster_description = 'Description for the cluster number one.'
        default_cluster['name'] = 'Name for the cluster number one.'
        default_cluster['description'] = cluster_description

        response = self._send_put_resquest(None, default_cluster,
                                           transformed_response['xsrf_token'])

        # get the key
        cid = json.loads(transforms.loads(response.body)['payload'])['key']
        cluster = clustering.ClusterDAO.load(cid)
        self.assertIsNotNone(cluster, msg='Cluster not saved.')

        self.assertEqual(cluster.description, cluster_description,
                         msg='Wrong description saved')

    def test_save_no_range(self):
        """The dimensions with no range are not saved"""
        # get a sample payload
        response = self.get(self.CLUSTER_GET_URL)
        transformed_response = transforms.loads(response.body)
        default_cluster = json.loads(transformed_response['payload'])
        vector = [{clustering.DIM_ID: clustering.ClusterRESTHandler.pack_id(
            '2', clustering.DIM_TYPE_LESSON)}]
        cluster_name = 'Name for the cluster number one.'
        default_cluster['name'] = cluster_name
        default_cluster['vector'] = vector

        response = self._send_put_resquest(None, default_cluster,
                                           transformed_response['xsrf_token'])

        # get the key
        cid = json.loads(transforms.loads(response.body)['payload'])['key']
        cluster = clustering.ClusterDAO.load(cid)
        self.assertIsNotNone(cluster, msg='Cluster not saved.')

        self.assertEqual(cluster.vector, [], msg='Empty dimension saved.')

    def test_xsrf_token(self):
        """Check XSRF is required"""
        response = self.get(self.CLUSTER_GET_URL)
        transformed_response = transforms.loads(response.body)
        default_cluster = json.loads(transformed_response['payload'])

        request = {}
        request['key'] = None
        request['payload'] = json.dumps(default_cluster)
        response = self.put(self.CLUSTER_PUT_URL + '?%s' % urllib.urlencode(
            {'request': transforms.dumps(request)}), {})
        self.assertEqual(response.status_int, 200)
        self.assertIn('"status": 403', response.body)

    def test_save_range0(self):
        """The dimensions with range (0, 0) are saved"""
        response = self.get(self.CLUSTER_GET_URL)
        transformed_response = transforms.loads(response.body)
        default_cluster = json.loads(transformed_response['payload'])
        default_cluster['name'] = 'ClusterName'
        dim_id = clustering.ClusterRESTHandler.pack_id(
            '2', clustering.DIM_TYPE_LESSON)
        vector = [{
            clustering.DIM_ID: dim_id,
            clustering.DIM_LOW: 0,
            clustering.DIM_HIGH: 0}]
        default_cluster['vector'] = vector

        response = self._send_put_resquest(None, default_cluster,
                                           transformed_response['xsrf_token'])

        # get the key
        cid = json.loads(transforms.loads(response.body)['payload'])['key']
        cluster = clustering.ClusterDAO.load(cid)

        self.assertEqual(len(cluster.vector), 1, msg='Wrong dimensions number')
        dimension = cluster.vector[0]
        self.assertEqual(dimension[clustering.DIM_LOW], 0,
            msg='Cluster saved with wrong dimension range')
        self.assertEqual(dimension[clustering.DIM_HIGH], 0,
            msg='Cluster saved with wrong dimension range')

    def test_save_range_incomplete_left(self):
        """One side ranges completed to None."""
        response = self.get(self.CLUSTER_GET_URL)
        transformed_response = transforms.loads(response.body)
        default_cluster = json.loads(transformed_response['payload'])
        default_cluster['name'] = 'ClusterName'
        dim_id = clustering.ClusterRESTHandler.pack_id(
            '2', clustering.DIM_TYPE_LESSON)
        vector = [{clustering.DIM_ID: dim_id, clustering.DIM_HIGH: '0'}]
        default_cluster['vector'] = vector

        response = self._send_put_resquest(None, default_cluster,
                                           transformed_response['xsrf_token'])

        # get the key
        cid = json.loads(transforms.loads(response.body)['payload'])['key']
        cluster = clustering.ClusterDAO.load(cid)
        self.assertEqual(len(cluster.vector), 1, msg='Wrong dimension number')
        dimension = cluster.vector[0]
        self.assertIn(clustering.DIM_LOW, dimension)
        self.assertIsNone(dimension[clustering.DIM_LOW],
            msg='Cluster saved with incomplete left side of dimension range')

    def test_save_range_incomplete_right(self):
        """One side ranges completed to None."""
        response = self.get(self.CLUSTER_GET_URL)
        transformed_response = transforms.loads(response.body)
        default_cluster = json.loads(transformed_response['payload'])
        default_cluster['name'] = 'ClusterName'
        dim_id = clustering.ClusterRESTHandler.pack_id(
            '2', clustering.DIM_TYPE_LESSON)
        vector = [{clustering.DIM_ID: dim_id, clustering.DIM_LOW: '0.55'}]
        default_cluster['vector'] = vector

        response = self._send_put_resquest(None, default_cluster,
                                           transformed_response['xsrf_token'])

        # get the key
        cid = json.loads(transforms.loads(response.body)['payload'])['key']
        cluster = clustering.ClusterDAO.load(cid)
        self.assertEqual(len(cluster.vector), 1, msg='Wrong dimension number')
        dimension = cluster.vector[0]
        self.assertIn(clustering.DIM_HIGH, dimension)
        self.assertIsNone(dimension[clustering.DIM_HIGH],
            msg='Cluster saved with incomplete right side of dimension range')

    def test_save_incosistent_range(self):
        """If left part of the range is greater than right expect error."""
        # get a sample payload
        response = self.get(self.CLUSTER_GET_URL)
        transformed_response = transforms.loads(response.body)
        default_cluster = json.loads(transformed_response['payload'])
        default_cluster['name'] = 'ClusterName'
        dim_id = clustering.ClusterRESTHandler.pack_id(
            '2', clustering.DIM_TYPE_LESSON)
        vector = [{
            clustering.DIM_ID: dim_id,
            clustering.DIM_HIGH: '0',
            clustering.DIM_LOW: '20'}]
        default_cluster['vector'] = vector

        response = self._send_put_resquest(None, default_cluster,
                                           transformed_response['xsrf_token'])

        self.assertIn('"status": 412', response.body)

    def test_save_non_numeric_range_left(self):
        """If range cant be converted to a number expect error response."""
        # get a sample payload
        response = self.get(self.CLUSTER_GET_URL)
        transformed_response = transforms.loads(response.body)
        default_cluster = json.loads(transformed_response['payload'])
        default_cluster['name'] = 'ClusterName'
        dim_id = clustering.ClusterRESTHandler.pack_id(
            '2', clustering.DIM_TYPE_LESSON)
        vector = [{
            clustering.DIM_ID: dim_id,
            clustering.DIM_HIGH: '0',
            clustering.DIM_LOW: 'Non numeric'}]
        default_cluster['vector'] = vector

        response = self._send_put_resquest(None, default_cluster,
                                           transformed_response['xsrf_token'])

        self.assertIn('"status": 412', response.body)

    def test_save_non_numeric_range_right(self):
        """If range cant be converted to a number expect error response."""
        # get a sample payload
        response = self.get(self.CLUSTER_GET_URL)
        transformed_response = transforms.loads(response.body)
        default_cluster = json.loads(transformed_response['payload'])
        default_cluster['name'] = 'ClusterName'
        dim_id = clustering.ClusterRESTHandler.pack_id(
            '2', clustering.DIM_TYPE_LESSON)
        vector = [{
            clustering.DIM_ID: dim_id,
            clustering.DIM_HIGH: 'Non numeric'}]
        default_cluster['vector'] = vector

        response = self._send_put_resquest(None, default_cluster,
                                           transformed_response['xsrf_token'])

        self.assertIn('"status": 412', response.body)

    def test_save_correct_url(self):
        """Test if the save button is posting to the correct url."""
        response = self.get(self.CLUSTER_ADD_URL)
        self.assertIn(self.CLUSTER_PUT_URL, response.body)

    def test_edit_correct_url(self):
        cluster_key = self._add_cluster()
        url = 'dashboard?action=edit_cluster&key={}'
        response = self.get(url.format(cluster_key))
        self.assertEqual(response.status_code, 200)

    def test_non_admin_get(self):
        """No admid users can't perform GET request."""
        actions.logout()
        actions.login(self.NON_ADMIN_EMAIL, is_admin=False)
        response = self.get(self.CLUSTER_GET_URL)
        self.assertEquals(200, response.status_code)
        self.assertIn('"status": 401', response.body)

    def test_non_admin_put(self):
        """No admid users can't perform PUT request."""
        actions.logout()
        actions.login(self.NON_ADMIN_EMAIL, is_admin=False)
        response = self.get(self.CLUSTER_PUT_URL)
        self.assertEquals(200, response.status_code)
        self.assertIn('"status": 401', response.body)

    def test_edit_fill_correct_data(self):
        """In the edit page the name, description and range must be present.
        """
        cluster_key = self._add_cluster()
        cluster = clustering.ClusterDAO.load(cluster_key)

        response = self.get(self.CLUSTER_GET_URL + str(cluster_key))
        self.assertEquals(200, response.status_code)
        transformed_response = transforms.loads(response.body)
        payload_cluster = json.loads(transformed_response['payload'])

        self.assertEqual(cluster.name, payload_cluster['name'])
        self.assertEqual(cluster.description, payload_cluster['description'])

    def test_save_name_after_edit(self):
        """The edited values are saved correctly."""
        cluster_key = self._add_cluster()
        old_cluster = clustering.ClusterDAO.load(cluster_key)
        response = self.get(self.CLUSTER_GET_URL + str(cluster_key))

        transformed_response = transforms.loads(response.body)
        new_cluster = json.loads(transformed_response['payload'])
        new_cluster_name = 'Name for the cluster number one.'
        new_cluster['name'] = new_cluster_name

        response = self._send_put_resquest(cluster_key, new_cluster,
                                           transformed_response['xsrf_token'])

        new_cluster = clustering.ClusterDAO.load(cluster_key)

        self.assertEqual(new_cluster.name, new_cluster_name)

    def test_save_dimension_after_edit(self):
        """The edited values are saved correctly."""
        cluster_key = self._add_cluster()
        old_cluster = clustering.ClusterDAO.load(cluster_key)
        response = self.get(self.CLUSTER_GET_URL + str(cluster_key))

        transformed_response = transforms.loads(response.body)
        new_cluster = json.loads(transformed_response['payload'])
        new_cluster['vector'][0][clustering.DIM_LOW] = 50
        new_cluster['vector'][0][clustering.DIM_HIGH] = 60
        packed_dimension_key = new_cluster['vector'][-1][clustering.DIM_ID]
        self.assertIsNotNone(packed_dimension_key)

        response = self._send_put_resquest(cluster_key, new_cluster,
                                           transformed_response['xsrf_token'])

        new_cluster = clustering.ClusterDAO.load(cluster_key)

        new_dimension = new_cluster.vector[0]
        dim_id, dim_type = clustering.ClusterRESTHandler.unpack_id(
            packed_dimension_key)
        self.assertEqual(new_dimension[clustering.DIM_ID], dim_id,
                         msg='Cluster saved with wrong dimension id.')
        self.assertEqual(new_dimension[clustering.DIM_TYPE], dim_type,
                         msg='Cluster saved with wrong dimension type.')
        self.assertEqual(new_dimension[clustering.DIM_LOW], 50,
                         msg='Cluster saved with wrong dimension low.')
        self.assertEqual(new_dimension[clustering.DIM_HIGH], 60,
                         msg='Cluster saved with wrong dimension high.')


class StudentVectorGeneratorTests(actions.TestBase):

    COURSE_NAME = 'test_course'
    ADMIN_EMAIL = 'admin@foo.com'

    def setUp(self):
        super(StudentVectorGeneratorTests, self).setUp()

        self.old_namespace = namespace_manager.get_namespace()
        namespace_manager.set_namespace('ns_%s' % self.COURSE_NAME)

        self.app_context = actions.simple_add_course(
            self.COURSE_NAME, self.ADMIN_EMAIL, 'Analytics Test')
        self.course = courses.Course(None, app_context=self.app_context)
        self._load_initial_data()

        self.dimensions = [  # Data obteined from assessments.json
            {clustering.DIM_TYPE: clustering.DIM_TYPE_UNIT,
             clustering.DIM_ID: '4',
             clustering.DIM_EXTRA_INFO: json.dumps({'unit_scored_lessons': 0}),
             'expected_value': 187.0},
            {clustering.DIM_TYPE: clustering.DIM_TYPE_UNIT,
             clustering.DIM_ID: '1',
             clustering.DIM_EXTRA_INFO: json.dumps({'unit_scored_lessons': 1}),
             'expected_value': 8.5},
            {clustering.DIM_TYPE: clustering.DIM_TYPE_LESSON,
             clustering.DIM_ID: '3',
             'expected_value': 8.5},
            {clustering.DIM_TYPE: clustering.DIM_TYPE_QUESTION,
             clustering.DIM_ID: clustering.pack_question_dimid('1', '2',
                                                  '5629499534213120'),
             'expected_value': 0.5},
            {clustering.DIM_TYPE: clustering.DIM_TYPE_QUESTION,
             clustering.DIM_ID: clustering.pack_question_dimid('1', '2',
                                                  '5066549580791808'),
             'expected_value': 0.75},  # Last weighted score
            {clustering.DIM_TYPE: clustering.DIM_TYPE_QUESTION,
             clustering.DIM_ID: clustering.pack_question_dimid('1', '3',
                                                  '5629499534213120'),
             'expected_value': (1.0 + 2.5) / 2},  # Average in submission.
            {clustering.DIM_TYPE: clustering.DIM_TYPE_QUESTION,
             clustering.DIM_ID: clustering.pack_question_dimid('1', '3',
                                                  '5066549580791808'),
             'expected_value': (3.5 + 1.5) / 2},
            {clustering.DIM_TYPE: clustering.DIM_TYPE_QUESTION,
             clustering.DIM_ID: clustering.pack_question_dimid('4', None,
                                                  '5629499534213120'),
             'expected_value': (55.0 + 22.0) / 2},
            {clustering.DIM_TYPE: clustering.DIM_TYPE_QUESTION,
             clustering.DIM_ID: clustering.pack_question_dimid('4', None,
                                                  '5066549580791808'),
             'expected_value': (77.0 + 33.0) / 2},
            {clustering.DIM_TYPE: clustering.DIM_TYPE_UNIT_VISIT,
             clustering.DIM_ID: '3',
             'expected_value': 2},
            {clustering.DIM_TYPE: clustering.DIM_TYPE_UNIT_VISIT,
             clustering.DIM_ID: '6',
             'expected_value': 2}
        ]

    def tearDown(self):
        # Clean up app_context.
        namespace_manager.set_namespace(self.old_namespace)
        super(StudentVectorGeneratorTests, self).tearDown()

    def _get_data_path(self, path):
        return os.path.join(appengine_config.BUNDLE_ROOT, 'modules',
                            'analytics', 'test_courses', path)

    def _load_initial_data(self):
        """Creates several StudentAggregateEntity based on the file item."""
        # email must match the value listed in Student.json file
        self.aggregate_entity = student_aggregate.StudentAggregateEntity(
            key_name='foo@bar.com')

        # Upload data from scoring
        data_path = self._get_data_path('scoring')
        expected_path = os.path.join(data_path, 'expected',
                                     'assessments.json')
        raw_assessment_data = None
        with open(expected_path) as fs:
            raw_assessment_data = transforms.loads(fs.read())
        raw_views_data = None
        data_path = self._get_data_path('page_views')
        expected_path = os.path.join(data_path, 'expected',
                                     'page_views.json')
        with open(expected_path) as fs:
            raw_views_data = transforms.loads(fs.read())

        self.aggregate_entity.data = zlib.compress(transforms.dumps({
                'assessments': raw_assessment_data,
                'page_views': raw_views_data}))

        self.aggregate_entity.put()
        self.raw_activities = raw_assessment_data
        self.raw_views_data = raw_views_data

    def test_inverse_submission_data(self):
        """inverse_submission_data returns a dictionary keys by dimension id.

        For every dimension of submissions the dictionary has a value with the
        same information as the original submission data. The value will
        be a list with all the submission relevant to that dimension.
        If an assessment is included inside a unit as pre or post assessment,
        the aggregator will put it in the first level as any other unit.
        """
        def get_questions(unit_id, lesson_id, question_id):
            result = []
            for activity in self.raw_activities:
                if not (activity.get('unit_id') == str(unit_id) and
                        activity.get('lesson_id') == str(lesson_id)):
                    continue
                for submission in activity['submissions']:
                    for question in submission['answers']:
                        if question.get('question_id') == question_id:
                            question['timestamp'] = submission['timestamp']
                            result.append(question)
                return result

        # Treat as module-protected. pylint: disable=protected-access
        result = clustering.StudentVectorGenerator._inverse_submission_data(
            self.dimensions, self.raw_activities)
        for dim in self.dimensions:
            dim_type = dim[clustering.DIM_TYPE]
            dim_id = dim[clustering.DIM_ID]
            entry = sorted(result[dim_type, dim_id])
            expected = None
            if dim_type == clustering.DIM_TYPE_UNIT:
                expected = [activity for activity in self.raw_activities
                            if activity['unit_id'] == dim_id]
            elif dim_type == clustering.DIM_TYPE_LESSON:
                expected = [activity for activity in self.raw_activities
                            if activity['lesson_id'] == dim_id]
            elif dim_type == clustering.DIM_TYPE_QUESTION:
                unit_id, lesson_id, q_id = clustering.unpack_question_dimid(
                    dim_id)
                expected = get_questions(unit_id, lesson_id, q_id)
            if not expected:
                continue
            expected.sort()
            self.assertEqual(entry, expected,
                             msg='Bad entry {} {}: {}. Expected: {}'.format(
                                dim_type, dim_id, entry, expected))

    def test_inverse_page_view_data(self):
        """inverse_page_view_data returns a dictionary keys by dimension id.
        """
        # Treat as module-protected. pylint: disable=protected-access
        result = clustering.StudentVectorGenerator._inverse_page_view_data(
            self.raw_views_data)
        for dim in self.dimensions:
            dim_type = dim[clustering.DIM_TYPE]
            dim_id = dim[clustering.DIM_ID]
            entry = sorted(result[dim_type, dim_id])
            if dim_type == clustering.DIM_TYPE_UNIT_VISIT:
                expected = [page_view for page_view in self.raw_views_data
                            if page_view['name'] in ['unit', 'assessment'] and
                            page_view['item_id'] == dim_id]
                expected.sort()
                self.assertEqual(entry, expected)

    def run_generator_job(self):
        def mock_mapper_params(unused_self, unused_app_context):
            return {'possible_dimensions': self.dimensions}
        mock_generator = clustering.StudentVectorGenerator
        mock_generator.build_additional_mapper_params = mock_mapper_params
        job = mock_generator(self.app_context)
        job.submit()
        self.execute_all_deferred_tasks()

    def test_map_reduce(self):
        """The generator is producing the expected output vector."""
        self.run_generator_job()
        self.assertEqual(clustering.StudentVector.all().count(), 1)
        student_vector = clustering.StudentVector.get_by_key_name(
            str(self.aggregate_entity.key().name()))
        for expected_dim in self.dimensions:
            obtained_value = clustering.StudentVector.get_dimension_value(
                transforms.loads(student_vector.vector),
                expected_dim[clustering.DIM_ID],
                expected_dim[clustering.DIM_TYPE])
            self.assertEqual(expected_dim['expected_value'], obtained_value)

    def test_map_reduce_no_assessment(self):
        self.aggregate_entity.data = zlib.compress(transforms.dumps({}))
        self.aggregate_entity.put()
        self.run_generator_job()
        student_vector = clustering.StudentVector.get_by_key_name(
            str(self.aggregate_entity.key().id()))
        self.assertIsNone(student_vector)

    def test_get_unit_score(self):
        """The score of a unit is the average score of its scored lessons.

        This is testing the following extra cases:
            - Submissions with no lesson_id
        """
        # Treat as module-protected. pylint: disable=protected-access
        data = clustering.StudentVectorGenerator._inverse_submission_data(
            self.dimensions, self.raw_activities)
        for dim in self.dimensions:
            if dim[clustering.DIM_TYPE] == clustering.DIM_TYPE_UNIT:
                # Treat as module-protected. pylint: disable=protected-access
                value = clustering.StudentVectorGenerator._get_unit_score(
                    data[dim[clustering.DIM_TYPE], dim[clustering.DIM_ID]], dim)
                self.assertEqual(value, dim['expected_value'])

    def test_get_lesson_score(self):
        """The score of a lesson is its last score.

        This is testing the following extra cases:
            - Submissions with no lesson_id
        """
        # Treat as module-protected. pylint: disable=protected-access
        data = clustering.StudentVectorGenerator._inverse_submission_data(
            self.dimensions, self.raw_activities)
        for dim in self.dimensions:
            if dim[clustering.DIM_TYPE] == clustering.DIM_TYPE_LESSON:
                value = clustering.StudentVectorGenerator._get_lesson_score(
                    data[dim[clustering.DIM_TYPE], dim[clustering.DIM_ID]], dim)
                self.assertEqual(value, dim['expected_value'])

    def test_get_question_score(self):
        """The score of a question is its last score.

        This is testing the following extra cases:
            - Multiple submissions of the same question.
            - Save question multiple times in the same submission.
            - Submissions to assesments (no lesson id).
        """
        # Treat as module-protected. pylint: disable=protected-access
        data = clustering.StudentVectorGenerator._inverse_submission_data(
            self.dimensions, self.raw_activities)
        for dim in self.dimensions:
            if dim[clustering.DIM_TYPE] == clustering.DIM_TYPE_QUESTION:
                value = clustering.StudentVectorGenerator._get_question_score(
                    data[dim[clustering.DIM_TYPE], dim[clustering.DIM_ID]], dim)
                self.assertEqual(value, dim['expected_value'])

    def test_get_unit_visits(self):
        """Count the number of visits for a unit or an assessment.
        """
        # Treat as module-protected. pylint: disable=protected-access
        data = clustering.StudentVectorGenerator._inverse_page_view_data(
            self.raw_views_data)
        for dim in self.dimensions:
            if dim[clustering.DIM_TYPE] == clustering.DIM_TYPE_UNIT_VISIT:
                value = clustering.StudentVectorGenerator._get_unit_visits(
                    data[dim[clustering.DIM_TYPE], dim[clustering.DIM_ID]],
                    dim)
                self.assertEqual(value, dim['expected_value'])

    def test_score_no_submitted_unit(self):
        """If there is no submission of a unit the value is 0."""
        extra_dimension = {
            clustering.DIM_TYPE: clustering.DIM_TYPE_UNIT,
            clustering.DIM_ID: '10'}
        # Treat as module-protected. pylint: disable=protected-access
        data = clustering.StudentVectorGenerator._inverse_submission_data(
            [extra_dimension], self.raw_activities)
        value = clustering.StudentVectorGenerator._get_unit_score(
            data[extra_dimension[clustering.DIM_TYPE], '10'], extra_dimension)
        self.assertEqual(value, 0)

    def test_score_no_submitted_lesson(self):
        """If there is no submission of a lesson the value is 0."""
        extra_dimension = {
            clustering.DIM_TYPE: clustering.DIM_TYPE_LESSON,
            clustering.DIM_ID: '10'
            }
        # Treat as module-protected. pylint: disable=protected-access
        data = clustering.StudentVectorGenerator._inverse_submission_data(
            [extra_dimension], self.raw_activities)
        value = clustering.StudentVectorGenerator._get_lesson_score(
            data[extra_dimension[clustering.DIM_TYPE], '10'], extra_dimension)
        self.assertEqual(value, 0)

    def test_score_no_submitted_question(self):
        """If there is no submission of a question the value is 0."""
        extra_dimension = {
            clustering.DIM_TYPE: clustering.DIM_TYPE_QUESTION,
            clustering.DIM_ID: clustering.pack_question_dimid('1', '3', '00000')
            }
        # Treat as module-protected. pylint: disable=protected-access
        data = clustering.StudentVectorGenerator._inverse_submission_data(
            [extra_dimension], self.raw_activities)
        value = clustering.StudentVectorGenerator._get_question_score(
            data[extra_dimension[clustering.DIM_TYPE], '10'], extra_dimension)
        self.assertEqual(value, 0)

    def test_get_unit_score_multiple_lessons(self):
        """The score of a unit is the average score of its scored lessons."""
        raw_assessment_data = self.raw_activities + [{
            'last_score':10.5,
            'unit_id':'1',
            'lesson_id':'5',
        }]
        dimension = {
            clustering.DIM_TYPE: clustering.DIM_TYPE_UNIT,
            clustering.DIM_ID: '1',
            clustering.DIM_EXTRA_INFO : json.dumps({
                'unit_scored_lessons': 2
            })
        }
        expected = (10.5 + 8.5) / 2
        # Treat as module-protected. pylint: disable=protected-access
        value = clustering.StudentVectorGenerator._get_unit_score(
            raw_assessment_data, dimension)
        self.assertEqual(value, expected,
                         msg='Wrong score for unit with multiple lessons. '
                         'Expected {}. Got {}'.format(expected, value))


class StudentVectorGeneratorProgressTests(actions.TestBase):
    """Tests the calculation of the progress dimensions."""

    COURSE_NAME = 'test_course'
    ADMIN_EMAIL = 'admin@foo.com'

    def setUp(self):
        super(StudentVectorGeneratorProgressTests, self).setUp()

        self.old_namespace = namespace_manager.get_namespace()
        namespace_manager.set_namespace('ns_%s' % self.COURSE_NAME)

        self.app_context = actions.simple_add_course(
            self.COURSE_NAME, self.ADMIN_EMAIL, 'Analytics Test')
        self.course = courses.Course(None, app_context=self.app_context)
        self._create_entities()

    def tearDown(self):
        # Clean up app_context.
        namespace_manager.set_namespace(self.old_namespace)
        super(StudentVectorGeneratorProgressTests, self).tearDown()

    def _create_entities(self):
        # Add course content
        unit = self.course.add_unit()
        unit.title = 'Unit number 1'
        unit.availability = courses.AVAILABILITY_AVAILABLE
        lesson = self.course.add_lesson(unit)
        lesson.title = 'Lesson'
        lesson.availability = courses.AVAILABILITY_AVAILABLE
        self.course.save()

        self.student_id = '1'
        self.student = models.Student(user_id=self.student_id)
        self.student.put()
        self.aggregate_entity = student_aggregate.StudentAggregateEntity(
            key_name=self.student_id,
            data=zlib.compress(transforms.dumps({})))
        self.aggregate_entity.put()
        self.progress = UnitLessonCompletionTracker.get_or_create_progress(
            self.student)
        self.progress.value = transforms.dumps(
            {"u.{}.l.{}".format(unit.unit_id, lesson.lesson_id): 2,
             "u.{}".format(unit.unit_id): 1})
        self.progress.put()

        self.dimensions = [
            {clustering.DIM_TYPE: clustering.DIM_TYPE_UNIT_PROGRESS,
             clustering.DIM_ID: unit.unit_id,
             'expected_value': 1},
            {clustering.DIM_TYPE: clustering.DIM_TYPE_LESSON_PROGRESS,
             clustering.DIM_ID: lesson.lesson_id,
             'expected_value': 2,
             clustering.DIM_EXTRA_INFO: transforms.dumps({'unit_id': 1})}
        ]

    def run_generator_job(self):
        def mock_mapper_params(unused_self, unused_app_context):
            return {'possible_dimensions': self.dimensions}
        mock_generator = clustering.StudentVectorGenerator
        mock_generator.build_additional_mapper_params = mock_mapper_params
        job = mock_generator(self.app_context)
        job.submit()
        self.execute_all_deferred_tasks()

    def test_map_reduce(self):
        """The generator is producing the expected output vector."""
        self.run_generator_job()
        self.assertEqual(clustering.StudentVector.all().count(), 1)
        student_vector = clustering.StudentVector.get_by_key_name(
            str(self.aggregate_entity.key().name()))
        for expected_dim in self.dimensions:
            obtained_value = clustering.StudentVector.get_dimension_value(
                transforms.loads(student_vector.vector),
                expected_dim[clustering.DIM_ID],
                expected_dim[clustering.DIM_TYPE])
            self.assertEqual(expected_dim['expected_value'], obtained_value)

    def test_map_reduce_no_progress(self):
        """The student has no progress."""
        self.progress.value = None
        self.progress.put()
        self.run_generator_job()
        self.assertEqual(clustering.StudentVector.all().count(), 0)


class ClusteringGeneratorTests(actions.TestBase):
    """Tests for the ClusteringGenerator job and auxiliary functions."""

    COURSE_NAME = 'test_course'
    ADMIN_EMAIL = 'admin@foo.com'

    def setUp(self):
        super(ClusteringGeneratorTests, self).setUp()

        self.old_namespace = namespace_manager.get_namespace()
        namespace_manager.set_namespace('ns_%s' % self.COURSE_NAME)

        self.app_context = actions.simple_add_course(
            self.COURSE_NAME, self.ADMIN_EMAIL, 'Analytics Test')
        self.course = courses.Course(None, app_context=self.app_context)
        self.dim_number = 10
        self.dimensions = [
            {clustering.DIM_TYPE: clustering.DIM_TYPE_QUESTION,
             clustering.DIM_ID: str(i)} for i in range(self.dim_number)]
        self.student_vector_keys = []

    def tearDown(self):
        # Clean up app_context.
        namespace_manager.set_namespace(self.old_namespace)
        super(ClusteringGeneratorTests, self).tearDown()

    def _add_student_vector(self, student_id, values):
        """Creates a StudentVector in the db using the given id and values.

        Values is a list of numbers, one for each dimension. It must not
        have more items than self.dimensions.
        """
        new_sv = clustering.StudentVector(key_name=student_id)
        for index, value in enumerate(values):
            self.dimensions[index][clustering.DIM_VALUE] = value
        new_sv.vector = transforms.dumps(self.dimensions)
        self.student_vector_keys.append(new_sv.put())

    def _add_cluster(self, values):
        """Creates a ClusterEntity in the db using the given id and values.

        Values is a list of 2-uples, one for each dimension. It must not
        have more items than self.dimensions."""
        for index, value in enumerate(values):
            self.dimensions[index][clustering.DIM_LOW] = value[0]
            self.dimensions[index][clustering.DIM_HIGH] = value[1]
        new_cluster = clustering.ClusterDTO(None,
            {'name': 'Cluster {}'.format(len(values) + 1),
             'vector': self.dimensions})
        return clustering.ClusterDAO.save(new_cluster)

    def run_generator_job(self):
        job = clustering.ClusteringGenerator(self.app_context)
        job.submit()
        self.execute_all_deferred_tasks()

    def _add_entities(self):
        """Creates the entities in the db needed to run the job."""
        self.sv_number = 20
        # Add StudentVectors
        for index in range(self.sv_number):
            values = range(index + 1, index + self.dim_number + 1)
            student = models.Student(user_id=str(index))
            student.put()
            self._add_student_vector(student.user_id, values)
        # Add extra student with no student vector
        models.Student(user_id=str(self.sv_number)).put()
        # Add cluster
        cluster_values = [(i, i*2) for i in range(1, self.dim_number+1)]
        cluster1_key = self._add_cluster(cluster_values)
        # expected distances vector 1: 0 0  1  2  3  4 ...
        cluster_values = [(i, i+1) for i in range(1, self.dim_number+1)]
        cluster2_key = self._add_cluster(cluster_values)
        # expected distances vector 2: 0 0 10 10 10 10 ...
        return cluster1_key, cluster2_key

    def test_mapreduce_clusters(self):
        """Tests clusters stored in StudentVector after map reduce job.

        The job must update the clusters attribute in each StudentVector
        with a dictionary where the keys are the clusters' ids and the
        values are the distances, as long as the distance is in the correct
        range.
        """
        cluster1_key, cluster2_key = self._add_entities()
        self.run_generator_job()

        # Check the StudentVector clusters
        expected_distances1 = [0, 0, 1, 2]
        expected_distances2 = [0, 0]
        for index, key in enumerate(self.student_vector_keys[:4]):
            student_clusters = clustering.StudentClusters.get_by_key_name(
                key.name())
            clusters = transforms.loads(student_clusters.clusters)
            self.assertIn(str(cluster1_key), clusters)
            self.assertEqual(clusters[str(cluster1_key)],
                             expected_distances1[index],
                             msg='Wrong distance vector {}'.format(index))
        for index, key in enumerate(self.student_vector_keys[:2]):
            student_clusters = clustering.StudentClusters.get_by_key_name(
                key.name())
            clusters = transforms.loads(student_clusters.clusters)
            self.assertIn(str(cluster2_key), clusters)
            self.assertEqual(clusters[str(cluster2_key)],
                             expected_distances2[index],
                             msg='Wrong distance vector {}'.format(index))

    def test_mapreduce_stats(self):
        """Tests clusters stats generated after map reduce job.

        The expected result of the job is a list of tuples. The first
        element of the tuple is going to be the metric name and the
        second a dictionary. The values of the dictionary are lists.
        [
            ('count', ['1', [2, 1, 1, ...]]),
            ('count', ['2', [2, 0, 0, ...]]),
            ('intersection', [('1', '2'), [2, 2, 2, ...]]),
            ('student_count', 20)
            ...
        ]
        """
        cluster1_key, cluster2_key = self._add_entities()
        self.run_generator_job()
        job = clustering.ClusteringGenerator(self.app_context).load()
        result = jobs.MapReduceJob.get_results(job)
        self.assertEqual(4, len(result), msg='Wrong response number')

        # All tuples are converted to lists after map reduce.
        self.assertIn(['count', [cluster1_key, [2, 1, 1]]], result)
        self.assertIn(['count', [cluster2_key, [2]]], result)
        self.assertIn(['intersection', [[cluster1_key, cluster2_key], [2]]],
                      result)
        self.assertIn(['student_count', self.sv_number + 1], result)

    def _check_hamming(self, cluster_vector, student_vector, value):
        self.assertEqual(clustering.hamming_distance(
            cluster_vector, student_vector), value)

    def test_hamming_distance(self):
        cluster_vector = [
            {clustering.DIM_TYPE: clustering.DIM_TYPE_UNIT,
             clustering.DIM_ID: '1',
             clustering.DIM_HIGH: 10,
             clustering.DIM_LOW: None},
            {clustering.DIM_TYPE: clustering.DIM_TYPE_UNIT,
             clustering.DIM_ID: '2',
             clustering.DIM_HIGH: 80,
             clustering.DIM_LOW: 60},
        ]
        student_vector = [
            {clustering.DIM_TYPE: clustering.DIM_TYPE_UNIT,
             clustering.DIM_ID: '1',
             clustering.DIM_VALUE: 7},  # Match
            {clustering.DIM_TYPE: clustering.DIM_TYPE_UNIT,
             clustering.DIM_ID: '2',
             clustering.DIM_VALUE: 100},  # Don't mach
            {clustering.DIM_TYPE: clustering.DIM_TYPE_UNIT,
             clustering.DIM_ID: '3',
             clustering.DIM_VALUE: 4}  # Match
        ]
        self._check_hamming(cluster_vector, student_vector, 1)

    def test_hamming_equal_left(self):
        """The limit of the dimension range must be considered."""
        cluster_vector = [
            {clustering.DIM_TYPE: clustering.DIM_TYPE_UNIT,
             clustering.DIM_ID: '4',
             clustering.DIM_HIGH: 7,
             clustering.DIM_LOW: 6},
        ]
        student_vector = [
            {clustering.DIM_TYPE: clustering.DIM_TYPE_UNIT,
             clustering.DIM_ID: '1',
             clustering.DIM_VALUE: 7},
        ]
        self._check_hamming(cluster_vector, student_vector, 1)

    def test_hamming_equal_right(self):
        """The limit of the dimension range must be considered."""
        cluster_vector = [
            {clustering.DIM_TYPE: clustering.DIM_TYPE_UNIT,
             clustering.DIM_ID: '4',
             clustering.DIM_HIGH: 9,
             clustering.DIM_LOW: 7},
        ]
        student_vector = [
            {clustering.DIM_TYPE: clustering.DIM_TYPE_UNIT,
             clustering.DIM_ID: '1',
             clustering.DIM_VALUE: 7},
        ]
        self._check_hamming(cluster_vector, student_vector, 1)

    def test_hamming_missing_dim_student(self):
        """If a student has no matching dimension assume the value 0."""
        cluster_vector = [
            {clustering.DIM_TYPE: clustering.DIM_TYPE_UNIT,
             clustering.DIM_ID: '4',
             clustering.DIM_HIGH: 7,
             clustering.DIM_LOW: 3},
        ]
        self._check_hamming(cluster_vector, [], 1)


class TestClusterStatisticsDataSource(actions.TestBase):

    def _add_clusters(self):
        self.clusters_map = {}
        n_clusters = 4
        dimension = {"type": "lp", "low": 1.0, "high": 1.0, "id": "8"}
        for index in range(n_clusters):
            name = 'Cluster {}'.format(index)
            new_cluster = clustering.ClusterDTO(None,
                {'name': name, 'vector': [dimension] * (index + 1)})
            key = clustering.ClusterDAO.save(new_cluster)
            self.clusters_map[key] = name

    def _add_student_vectors(self):
        self.n_students = 6
        for i in range(self.n_students):
            clustering.StudentVector().put()

    def test_fetch_values_count(self):
        """Tests the result of the count statistics"""
        self._add_clusters()
        keys = self.clusters_map.keys()
        job_result = [
            ('count', (keys[0], [1, 1])),
            ('count', (keys[1], [0])),
            ('count', (keys[2], [1, 1, 2])),
            ('student_count', 6)
        ]
        expected_result = [
            [self.clusters_map[keys[0]], 1, 0, 0, 5],  # one dimension
            [self.clusters_map[keys[1]], 0, 0, 0, 6],  # two dimensions
            [self.clusters_map[keys[2]], 1, 1, 2, 2],  # three dimensions
            [self.clusters_map[keys[3]], 0, 0, 0, 6],
        ]
        # Treat as module-protected. pylint: disable=protected-access
        result = clustering.ClusterStatisticsDataSource._process_job_result(
            job_result)
        self.assertEqual(expected_result, result[0])

    def test_fetch_values_intersection(self):
        """Tests the result of the count statistics"""
        self._add_clusters()
        self._add_student_vectors()
        keys = self.clusters_map.keys()
        job_result = [
            ('count', (keys[0], [1, 1, 2])),  # [1, 2, 4]
            ('count', (keys[1], [2])),  # [2, 2, 2]
            ('count', (keys[2], [2, 1])),  # [2, 3, 3]
            ('count', (keys[3], [1, 1])),  # [1, 2, 2]
            ('intersection', ((keys[0], keys[1]), [1, 1, 2])),
            ('intersection', ((keys[1], keys[2]), [1, 2])),
            ('intersection', ((keys[3], keys[2]), [0])),
            ('student_count', self.n_students)
        ]
        expected_mapping = [self.clusters_map[k] for k in keys]  # names
        expected0 = {
            'count': {0: {1: 1},
                      1: {2: 1},
                      3: {2: 0}},
            'percentage': {0: {1: 16.67},
                           1: {2: 16.67},
                           3: {2: 0.00}},
            'probability': {0: {1: 1.0}, 1: {0: 0.5, 2: 0.5},
                            2: {1: 0.5, 3: 0.0},
                            3: {2: 0.0}}
        }
        expected1 = {
            'count': {0: {1: 1},
                      1: {2: 2},
                      3: {2: 0}},
            'percentage': {0: {1: 16.67},
                           1: {2: 33.33},
                           3: {2: 0.00}},
            'probability': {0: {1: 0.5}, 1: {0: 0.5, 2: 1.0},
                            2: {1: 0.67, 3: 0},
                            3: {2: 0.0}}
        }
        expected2 = {
            'count': {0: {1: 2},
                      1: {2: 2},
                      3: {2: 0}},
            'percentage': {0: {1: 33.33},
                           1: {2: 33.33},
                           3: {2: 0.00}},
            'probability': {0: {1: 0.5}, 1: {0: 1.0, 2: 1.0},
                            2: {1: 0.67, 3: 0.0},
                            3: {2: 0.0}}
        }
        # Treat as module-protected. pylint: disable=protected-access
        result = clustering.ClusterStatisticsDataSource._process_job_result(
            job_result)
        self.assertEqual(result[1], [expected0, expected1, expected2])
        self.assertEqual(result[2], expected_mapping)


class GradebookCsvTests(actions.TestBase):
    """Plain vanilla test; does use ETL'd test content."""

    COURSE_NAME = 'gradebook_csv'
    NAMESPACE = 'ns_%s' % COURSE_NAME
    ADMIN_EMAIL = 'admin@foo.com'
    STUDENT_EMAIL = 'student@foo.com'


    def setUp(self):
        super(GradebookCsvTests, self).setUp()

        self.old_namespace = namespace_manager.get_namespace()
        namespace_manager.set_namespace(self.NAMESPACE)
        self.q_a_id = models.QuestionEntity(
            data=u'{"description": "\u9959", "question": "aa"}').put().id()
        self.q_b_id = models.QuestionEntity(
            data='{"description": "b", "question": "aa"}').put().id()
        self.q_c_id = models.QuestionEntity(
            data='{"description": "c", "question": "aa"}').put().id()
        self.q_d_id = models.QuestionEntity(
            data='{"description": "d", "question": "aa"}').put().id()
        self.q_e_id = models.QuestionEntity(
            data='{"description": "e", "question": "aa"}').put().id()
        self.q_f_id = models.QuestionEntity(
            data='{"description": "f", "question": "aa"}').put().id()
        self.q_g_id = models.QuestionEntity(
            data='{"description": "g", "question": "aa"}').put().id()

        self.app_context = actions.simple_add_course(
            self.COURSE_NAME, self.ADMIN_EMAIL, 'Gradebook CSV Course')
        course = courses.Course(None, app_context=self.app_context)
        self.unit_one = course.add_unit()  # No lessons
        self.unit_one.title = 'Unit One'
        self.unit_two = course.add_unit()  # One lesson
        self.unit_two.title = 'Unit Two'
        self.u2_l1 = course.add_lesson(self.unit_two)
        self.u2_l1.title = 'U2L1'
        self.u2_l1.objectives = (
            '<question quid="%s" instanceid="x">' % self.q_a_id)
        self.unit_three = course.add_unit()  # Pre, post assessment & lessons.
        self.unit_three.title = 'Unit Three'
        self.pre_assessment = course.add_assessment()
        self.pre_assessment.title = 'Pre Assessment'
        self.pre_assessment.html_content = (
            '<question quid="%s" instanceid="x">' % self.q_b_id)
        self.unit_three.pre_assessment = self.pre_assessment.unit_id
        self.u3_l1 = course.add_lesson(self.unit_three)
        self.u3_l1.title = 'U3L1'
        self.u3_l2 = course.add_lesson(self.unit_three)
        self.u3_l2.title = 'U3L2'
        self.u3_l2.objectives = (
            '<question quid="%s" instanceid="x">' % self.q_c_id +
            '<question quid="%s" instanceid="x">' % self.q_d_id +
            '<question quid="%s" instanceid="x">' % self.q_e_id)
        self.u3_l3 = course.add_lesson(self.unit_three)
        self.u3_l3.title = 'U3L3'
        self.post_assessment = course.add_assessment()
        self.post_assessment.title = 'Post Assessment'
        self.post_assessment.html_content = (
            '<question quid="%s" instanceid="x">' % self.q_b_id)
        self.unit_three.post_assessment = self.post_assessment.unit_id
        self.assessment = course.add_assessment()
        self.assessment.title = 'Top-Level Assessment'
        self.assessment.html_content = (
            '<question quid="%s" instanceid="x">' % self.q_f_id +
            '<question quid="%s" instanceid="x">' % self.q_g_id)
        course.save()

        self.expected_score_headers = ','.join([
            'Email',
            '%s: %s' % (self.unit_two.title, self.u2_l1.title),
            '%s: %s' % (self.unit_three.title, self.pre_assessment.title),
            '%s: %s' % (self.unit_three.title, self.u3_l1.title),
            '%s: %s' % (self.unit_three.title, self.u3_l2.title),
            '%s: %s' % (self.unit_three.title, self.u3_l3.title),
            '%s: %s' % (self.unit_three.title, self.post_assessment.title),
            self.assessment.title]) + '\r\n'

        self.expected_question_headers = ','.join([
            'Email',
            '\xe9\xa5\x99 answer', '\xe9\xa5\x99 score',
            'b answer', 'b score',
            'c answer', 'c score',
            'd answer', 'd score',
            'e answer', 'e score',
            'b answer', 'b score',
            'f answer', 'f score',
            'g answer', 'g score',
            ]) + '\r\n'

        fp, self.temp_file_name = tempfile.mkstemp(suffix='.zip')
        os.close(fp)
        actions.login(self.ADMIN_EMAIL)
        actions.register(self, 'John Smith', self.COURSE_NAME)

    def tearDown(self):
        os.unlink(self.temp_file_name)
        namespace_manager.set_namespace(self.old_namespace)
        super(GradebookCsvTests, self).tearDown()

    def _build_job(self, mode, course_name=None):
        etl_args = etl.create_args_parser().parse_args(
            ['run',
             'modules.analytics.gradebook.DownloadAsCsv',
             '/%s' % (course_name or self.COURSE_NAME),
             'unused_servername',
             '--job_args', '--mode=%s --save_as=%s' % (
                 mode, self.temp_file_name),
             ])
        return gradebook.DownloadAsCsv(etl_args)

    def _verify_output(self, expected):
        with open(self.temp_file_name) as fp:
            actual = fp.read()
            self.assertEquals(expected, actual)


    def _verify(self, expected_scores, expected_questions, course_name=None):
        course_name = course_name or self.COURSE_NAME

        # Treat as module-protected. pylint: disable=protected-access
        self._build_job(gradebook._MODE_SCORES, course_name).run()
        self._verify_output(expected_scores)

        self._build_job(gradebook._MODE_QUESTIONS, course_name).run()
        self._verify_output(expected_questions)

        scores_url = ('/%s%s?%s=%s' % (
            course_name, gradebook.CsvDownloadHandler.URI,
            gradebook._MODE_ARG_NAME, gradebook._MODE_SCORES))
        response = self.get(scores_url)
        self.assertEquals(expected_scores, response.body)

        questions_url = ('/%s%s?%s=%s' % (
            course_name, gradebook.CsvDownloadHandler.URI,
            gradebook._MODE_ARG_NAME, gradebook._MODE_QUESTIONS))
        response = self.get(questions_url)
        self.assertEquals(expected_questions, response.body)

    def test_no_data(self):
        self._verify(self.expected_score_headers,
                     self.expected_question_headers)

    def test_non_admin_url_access(self):
        actions.logout()
        actions.login(self.STUDENT_EMAIL)

        # Treat as module-protected. pylint: disable=protected-access
        scores_url = ('/%s%s?%s=%s' % (
            self.COURSE_NAME, gradebook.CsvDownloadHandler.URI,
            gradebook._MODE_ARG_NAME, gradebook._MODE_SCORES))
        response = self.get(scores_url, expect_errors=True)
        self.assertEquals(401, response.status_int)

        questions_url = ('/%s%s?%s=%s' % (
            self.COURSE_NAME, gradebook.CsvDownloadHandler.URI,
            gradebook._MODE_ARG_NAME, gradebook._MODE_QUESTIONS))
        response = self.get(questions_url, expect_errors=True)
        self.assertEquals(401, response.status_int)

    def test_one_answer(self):
        a1 = 'xxx\xe7\xb6\x92'
        s1 = 123.0
        w1 = 246.0
        answers = [[
            self.unit_two.unit_id, self.u2_l1.lesson_id, 0, self.q_a_id,
            None, None, a1, s1, w1, True]]
        user = users.get_current_user()
        student_answers.QuestionAnswersEntity(
            key_name=user.user_id(), data=transforms.dumps(answers)).put()

        expected_scores = self.expected_score_headers + ','.join(
            [str(x) for x in
             user.email(), w1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]) + '\r\n'

        expected_questions = self.expected_question_headers + ','.join(
            [str(x) for x in
             user.email(),
             a1, w1,
             '', 0.0,
             '', 0.0,
             '', 0.0,
             '', 0.0,
             '', 0.0,
             '', 0.0,
             '', 0.0]) + '\r\n'
        self._verify(expected_scores, expected_questions)

    def test_multiple_students(self):
        answers = [
            [self.unit_two.unit_id, self.u2_l1.lesson_id, 0, self.q_a_id,
             None, None, 'one', 1, 1, True],
            [self.pre_assessment.unit_id, None, 0, self.q_b_id,
             None, None, 'two', 2, 2, True],
            [self.unit_three.unit_id, self.u3_l2.lesson_id, 0, self.q_c_id,
             None, None, 'three', 3, 3, True],
            [self.unit_three.unit_id, self.u3_l2.lesson_id, 1, self.q_d_id,
             None, None, 'four', 4, 4, True],
            [self.unit_three.unit_id, self.u3_l2.lesson_id, 2, self.q_e_id,
             None, None, 'five', 5, 5, True],
            [self.post_assessment.unit_id, None, 0, self.q_b_id,
             None, None, 'six', 6, 6, True],
            [self.assessment.unit_id, None, 0, self.q_f_id,
             None, None, 'seven', 7, 7, True],
            [self.assessment.unit_id, None, 1, self.q_g_id,
             None, None, 'eight', 8, 8, True]]
        user = users.get_current_user()
        student_answers.QuestionAnswersEntity(
            key_name=user.user_id(), data=transforms.dumps(answers)).put()

        actions.login(self.STUDENT_EMAIL)
        actions.register(self, 'Jane Smith', self.COURSE_NAME)
        answers = [
            [self.unit_two.unit_id, self.u2_l1.lesson_id, 0, self.q_a_id,
             None, None, 'eleven', 11, 11, True],
            [self.pre_assessment.unit_id, None, 0, self.q_b_id,
             None, None, 'twelve', 12, 12, True],
            [self.unit_three.unit_id, self.u3_l2.lesson_id, 0, self.q_c_id,
             None, None, 'thirteen', 13, 13, True],
            [self.unit_three.unit_id, self.u3_l2.lesson_id, 1, self.q_d_id,
             None, None, 'fourteen', 14, 14, True],
            [self.unit_three.unit_id, self.u3_l2.lesson_id, 2, self.q_e_id,
             None, None, 'fifteen', 15, 15, True],
            [self.post_assessment.unit_id, None, 0, self.q_b_id,
             None, None, 'sixteen', 16, 16, True],
            [self.assessment.unit_id, None, 0, self.q_f_id,
             None, None, 'seventeen', 17, 17, True],
            [self.assessment.unit_id, None, 1, self.q_g_id,
             None, None, 'eighteen', 18, 18, True]]
        user = users.get_current_user()
        student_answers.QuestionAnswersEntity(
            key_name=user.user_id(), data=transforms.dumps(answers)).put()

        expected_scores = self.expected_score_headers
        expected_scores += ','.join(
            [str(x) for x in
             self.ADMIN_EMAIL, 1.0, 2.0, 0.0, 12.0, 0.0, 6.0, 15.0]) + '\r\n'
        expected_scores += ','.join(
            [str(x) for x in
             self.STUDENT_EMAIL, 11.0, 12.0, 0.0, 42.0, 0.0, 16.0, 35.0]
            ) + '\r\n'

        expected_questions = self.expected_question_headers
        expected_questions += ','.join(
            [str(x) for x in
             self.ADMIN_EMAIL,
             'one', 1.0,
             'two', 2.0,
             'three', 3.0,
             'four', 4.0,
             'five', 5.0,
             'six', 6.0,
             'seven', 7.0,
             'eight', 8.0]) + '\r\n'
        expected_questions += ','.join(
            [str(x) for x in
             self.STUDENT_EMAIL,
             'eleven', 11.0,
             'twelve', 12.0,
             'thirteen', 13.0,
             'fourteen', 14.0,
             'fifteen', 15.0,
             'sixteen', 16.0,
             'seventeen', 17.0,
             'eighteen', 18.0]) + '\r\n'

        actions.login(self.ADMIN_EMAIL)
        self._verify(expected_scores, expected_questions)

    def test_commas_are_stripped(self):
        course_name = 'commas'
        with common_utils.Namespace('ns_' + course_name):

            app_context = actions.simple_add_course(
                course_name, self.ADMIN_EMAIL, 'Commas')
            actions.register(self, 'John Smith', course_name)
            course = courses.Course(None, app_context=app_context)
            assessment = course.add_assessment()
            assessment.title = 'This, That, These, and Those'
            q_id = models.QuestionEntity(
                data='{"description": "a,b,c", "question": "c,b,a"}').put().id()
            assessment.html_content = (
                '<question quid="%s" instanceid="x">' % q_id)
            course.save()
            user = users.get_current_user()

            answers = [[
                assessment.unit_id, None, 0, q_id,
                None, None, 'to comma, or not to comma', 0, 1, True]]
            student_answers.QuestionAnswersEntity(
                key_name=user.user_id(), data=transforms.dumps(answers)).put()

            self._verify(
                'Email,"This, That, These, and Those"\r\nadmin@foo.com,1.0\r\n',
                'Email,"a,b,c answer","a,b,c score"\r\n'
                'admin@foo.com,"to comma, or not to comma",1.0\r\n',
                course_name)

    def test_interactive_downloads_only_for_courses_with_few_students(self):
        gradebook_url = ('/%s/dashboard?action=analytics_gradebook' %
                         self.COURSE_NAME)
        # Treat as module-protected. pylint: disable=protected-access
        job_name = student_answers.RawAnswersGenerator(
            self.app_context)._job_name

        # No results => No button and no too-much-data text
        response = self.get(gradebook_url)
        self.assertNotIn('Download Scores as CSV File', response.body)
        self.assertNotIn('For larger volumes of gradebook data', response.body)

        # Few results => Interactive download
        with common_utils.Namespace(self.NAMESPACE):
            jobs.DurableJobEntity(
                key_name=job_name,
                status_code=2,
                updated_on=datetime.datetime(1970, 1, 1),
                output='{"results": [["total_students", 1]]}').put()
        response = self.get(gradebook_url)
        self.assertIn('Download Scores as CSV File', response.body)
        self.assertNotIn('For larger volumes of gradebook data', response.body)

        # Many results => No interactive download
        with common_utils.Namespace(self.NAMESPACE):
            jobs.DurableJobEntity(
                key_name=job_name,
                status_code=2,
                updated_on=datetime.datetime(1970, 1, 1),
                output='{"results": [["total_students", 101]]}').put()
        response = self.get(gradebook_url)
        self.assertNotIn('Download Scores as CSV File', response.body)
        self.assertIn('For larger volumes of gradebook data', response.body)
