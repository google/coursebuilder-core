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

import os
import pprint
import zlib

import appengine_config
from common import utils as common_utils
from models import courses
from models import models
from models import transforms
from modules.analytics import student_aggregate
from tests.functional import actions
from tools.etl import etl


# Note to those extending this set of tests in the future:
# - Make a new course named "test_course".
# - Use the admin user to set up whatever test situation you need.
# - In an incognito window, log in as 'foo@bar.com' and register.
# - Perform relevant user actions to generate EventEntity items.
# - Download test data via:
#
#   echo "a@b.c" | \
#   ./scripts/etl.sh download course /test_course mycourse localhost:8081 \
#   --archive_path=tests/functional/modules_analytics/TEST_NAME_HERE/course \
#   --internal --archive_type=directory --force_overwrite --no_static_files
#
#   echo "a@b.c" | \
#   ./scripts/etl.sh download datastore /test_course mycourse localhost:8081 \
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
        return os.path.join(appengine_config.BUNDLE_ROOT, 'tests', 'functional',
                            'modules_analytics', 'test_courses', path)

    def load_course(self, path):
        data_path = self._get_data_path(path)
        course_data = os.path.join(data_path, 'course')
        datastore_data = os.path.join(data_path, 'datastore')

        # Load the course to the VFS, and populate the DB w/ entities
        parser = etl.create_args_parser()
        etl.add_internal_args_support(parser)
        etl.main(parser.parse_args([
            'upload', 'course', '/' + self.COURSE_NAME, 'mycourse',
            'localhost:8081', '--archive_path', course_data,
            '--internal', '--archive_type', 'directory',
            '--disable_remote', '--force_overwrite', '--log_level', 'WARNING']))

    def load_datastore(self, path):
        data_path = self._get_data_path(path)
        course_data = os.path.join(data_path, 'course')
        datastore_data = os.path.join(data_path, 'datastore')

        parser = etl.create_args_parser()
        etl.add_internal_args_support(parser)
        etl.main(parser.parse_args([
            'upload', 'datastore', '/' + self.COURSE_NAME, 'mycourse',
            'localhost:8081', '--archive_path', datastore_data,
            '--internal', '--archive_type', 'directory',
            '--disable_remote', '--force_overwrite', '--log_level', 'WARNING',
            '--exclude_types',
            ','.join([
                'Submission', 'FileDataEntity', 'FileMetadataEntity'])]))

    def get_aggregated_data_by_email(self, email):
        with common_utils.Namespace('ns_' + self.COURSE_NAME):
            student = models.Student.get_by_email('foo@bar.com')
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
        # - Youtube events
        # - Events are present (and reported on in output) for unit, lesson,
        #   and assessment that have been deleted after events were recorded.
        expected = self.load_expected_data('page_views', 'page_views.json')
        expected.sort(key=lambda x: (x['name'], x.get('id'), x.get('start')))
        actual['page_views'].sort(
            key=lambda x: (x['name'], x.get('id'), x.get('start')))
        self.assertEqual(expected, actual['page_views'])

    def test_location_locale(self):
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
