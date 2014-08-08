#!/usr/bin/python

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

"""Runs all of the tests in parallel.

Execute this script from the Course Builder folder as:
    python scripts/run_all_tests.py
"""

__author__ = 'Pavel Simakov (psimakov@google.com)'


import datetime
import os
import subprocess
import threading


# all test classes with a total count of tests in each
ALL_TEST_CLASSES = {
    'tests.functional.admin_settings.AdminSettingsTests': 2,
    'tests.functional.admin_settings.HtmlHookTest': 11,
    'tests.functional.admin_settings.JinjaContextTest': 2,
    'tests.functional.assets_rest.AssetsRestTest': 4,
    'tests.functional.common_crypto.EncryptionManagerTests': 5,
    'tests.functional.common_crypto.XsrfTokenManagerTests': 3,
    'tests.functional.common_crypto.PiiObfuscationHmac': 2,
    'tests.functional.common_crypto.GenCryptoKeyFromHmac': 2,
    'tests.functional.common_crypto.GetExternalUserIdTests': 4,
    'tests.functional.explorer_module.CourseExplorerTest': 3,
    'tests.functional.explorer_module.CourseExplorerDisabledTest': 1,
    'tests.functional.explorer_module.GlobalProfileTest': 1,
    'tests.functional.controllers_review.PeerReviewControllerTest': 7,
    'tests.functional.controllers_review.PeerReviewDashboardAdminTest': 1,
    'tests.functional.controllers_review.PeerReviewDashboardStudentTest': 2,
    'tests.functional.model_analytics.AnalyticsTabsWithNoJobs': 8,
    'tests.functional.model_analytics.CronCleanupTest': 14,
    'tests.functional.model_analytics.ProgressAnalyticsTest': 8,
    'tests.functional.model_analytics.QuestionAnalyticsTest': 3,
    'tests.functional.model_data_sources.PaginatedTableTest': 17,
    'tests.functional.model_entities.BaseEntityTestCase': 3,
    'tests.functional.model_entities.ExportEntityTestCase': 2,
    'tests.functional.model_jobs.JobOperationsTest': 15,
    'tests.functional.model_models.EventEntityTestCase': 1,
    'tests.functional.model_models.PersonalProfileTestCase': 1,
    'tests.functional.model_models.QuestionDAOTestCase': 3,
    'tests.functional.model_models.StudentTestCase': 3,
    'tests.functional.model_models.StudentAnswersEntityTestCase': 1,
    'tests.functional.model_models.StudentProfileDAOTestCase': 6,
    'tests.functional.model_models.StudentPropertyEntityTestCase': 1,
    'tests.functional.model_student_work.KeyPropertyTest': 4,
    'tests.functional.model_student_work.ReviewTest': 3,
    'tests.functional.model_student_work.SubmissionTest': 3,
    'tests.functional.model_utils.QueryMapperTest': 4,
    'tests.functional.modules_certificate.CertificateHandlerTestCase': 4,
    'tests.functional.modules_certificate.CertificateCriteriaTestCase': 5,
    'tests.functional.modules_data_source_providers.CourseElementsTest': 11,
    'tests.functional.modules_data_source_providers.StudentScoresTest': 6,
    'tests.functional.modules_data_source_providers.StudentsTest': 5,
    'tests.functional.modules_manual_progress.ManualProgressTest': 24,
    'tests.functional.modules_notifications.CronTest': 9,
    'tests.functional.modules_notifications.DatetimeConversionTest': 1,
    'tests.functional.modules_notifications.ManagerTest': 31,
    'tests.functional.modules_notifications.NotificationTest': 8,
    'tests.functional.modules_notifications.PayloadTest': 6,
    'tests.functional.modules_notifications.StatsTest': 2,
    'tests.functional.modules_search.SearchTest': 12,
    'tests.functional.modules_unsubscribe.GetUnsubscribeUrlTests': 1,
    'tests.functional.modules_unsubscribe.SubscribeAndUnsubscribeTests': 4,
    'tests.functional.modules_unsubscribe.UnsubscribeHandlerTests': 2,
    'tests.functional.progress_percent.ProgressPercent': 4,
    'tests.functional.review_module.ManagerTest': 55,
    'tests.functional.review_peer.ReviewStepTest': 3,
    'tests.functional.review_peer.ReviewSummaryTest': 5,
    'tests.functional.student_answers.StudentAnswersAnalyticsTest': 1,
    'tests.functional.student_labels.StudentLabelsTest': 32,
    'tests.functional.student_last_location.NonRootCourse': 9,
    'tests.functional.student_last_location.RootCourse': 3,
    'tests.functional.student_tracks.StudentTracksTest': 10,
    'tests.functional.review_stats.PeerReviewAnalyticsTest': 1,
    'tests.functional.roles.RolesTest': 15,
    'tests.functional.upload_module.TextFileUploadHandlerTestCase': 8,
    'tests.functional.tags_include.TagsInclude': 8,
    'tests.functional.test_classes.ActivityTest': 2,
    'tests.functional.test_classes.AdminAspectTest': 8,
    'tests.functional.test_classes.AssessmentTest': 2,
    'tests.functional.test_classes.CourseAuthorAspectTest': 4,
    'tests.functional.test_classes.CourseAuthorCourseCreationTest': 2,
    'tests.functional.test_classes.CourseUrlRewritingTest': 42,
    'tests.functional.test_classes.DatastoreBackedCustomCourseTest': 5,
    'tests.functional.test_classes.DatastoreBackedSampleCourseTest': 42,
    'tests.functional.test_classes.EtlMainTestCase': 31,
    'tests.functional.test_classes.EtlRemoteEnvironmentTestCase': 0,
    'tests.functional.test_classes.InfrastructureTest': 13,
    'tests.functional.test_classes.I18NTest': 2,
    'tests.functional.test_classes.LessonComponentsTest': 2,
    'tests.functional.test_classes.MemcacheTest': 55,
    'tests.functional.test_classes.MultipleCoursesTest': 1,
    'tests.functional.test_classes.NamespaceTest': 2,
    'tests.functional.test_classes.StaticHandlerTest': 2,
    'tests.functional.test_classes.StudentAspectTest': 17,
    'tests.functional.test_classes.StudentUnifiedProfileTest': 17,
    'tests.functional.test_classes.TransformsEntitySchema': 1,
    'tests.functional.test_classes.TransformsJsonFileTestCase': 3,
    'tests.functional.test_classes.VirtualFileSystemTest': 42,
    'tests.functional.test_classes.ImportActivityTests': 6,
    'tests.functional.unit_assessment.UnitPrePostAssessmentTest': 17,
    'tests.functional.unit_description.UnitDescriptionsTest': 1,
    'tests.functional.unit_header_footer.UnitHeaderFooterTest': 11,
    'tests.functional.unit_on_one_page.UnitOnOnePageTest': 3,
    'tests.functional.whitelist.WhitelistTest': 12,
    'tests.integration.test_classes': 16,
    'tests.unit.etl_mapreduce.HistogramTests': 5,
    'tests.unit.etl_mapreduce.FlattenJsonTests': 4,
    'tests.unit.common_catch_and_log.CatchAndLogTests': 6,
    'tests.unit.common_locales.LocalesTests': 2,
    'tests.unit.common_locales.ParseAcceptLanguageTests': 3,
    'tests.unit.common_schema_fields.SchemaFieldTests': 4,
    'tests.unit.common_schema_fields.FieldArrayTests': 3,
    'tests.unit.common_schema_fields.FieldRegistryTests': 7,
    'tests.unit.common_safe_dom.NodeListTests': 4,
    'tests.unit.common_safe_dom.TextTests': 2,
    'tests.unit.common_safe_dom.ElementTests': 17,
    'tests.unit.common_safe_dom.ScriptElementTests': 3,
    'tests.unit.common_safe_dom.EntityTests': 11,
    'tests.unit.common_tags.CustomTagTests': 12,
    'tests.unit.common_utils.CommonUnitTests': 11,
    'tests.unit.javascript_tests.AllJavaScriptTests': 6,
    'tests.unit.models_analytics.AnalyticsTests': 5,
    'tests.unit.models_courses.WorkflowValidationTests': 13,
    'tests.unit.models_transforms.JsonToDictTests': 12,
    'tests.unit.models_transforms.JsonParsingTests': 3,
    'tests.unit.models_transforms.StringValueConversionTests': 2,
    'tests.unit.modules_search.ParserTests': 10,
    'tests.unit.test_classes.EtlRetryTest': 3,
    'tests.unit.test_classes.InvokeExistingUnitTest': 3,
    'tests.unit.test_classes.ReviewModuleDomainTests': 1,
    'tests.unit.test_classes.SuiteTestCaseTest': 3,
}
OMITTED_FROM_PRESUBMIT = ['tests.integration.test_classes']

LOG_LINES = []
LOG_LOCK = threading.Lock()


def log(message):
    with LOG_LOCK:
        line = '%s\t%s' % (
            datetime.datetime.now().strftime('%Y/%m/%d %H:%M:%S'), message)
        LOG_LINES.append(line)
        print line


def run(exe, strict=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        verbose=False):
    """Runs a shell command and captures the stdout and stderr output."""
    p = subprocess.Popen(exe, stdout=stdout, stderr=stderr)
    last_stdout, last_stderr = p.communicate()
    result = []
    if last_stdout:
        for line in last_stdout:
            result.append(line)
    if last_stderr:
        for line in last_stderr:
            result.append(line)
    result = ''.join(result)

    if p.returncode != 0 and verbose and 'KeyboardInterrupt' not in result:
        exe_string = ' '.join(exe)
        print '#########vvvvv########### Start of output from >>>%s<<< ' % (
            exe_string)
        print result
        print '#########^^^^^########### End of output from >>>%s<<<' % (
            exe_string)

    if p.returncode != 0 and strict:
        raise Exception('Error %s\n%s' % (p.returncode, result))
    return p.returncode, result


class TaskThread(threading.Thread):
    """Runs a task in a separate thread."""

    def __init__(self, func, name=None):
        super(TaskThread, self).__init__()
        self.func = func
        self.exception = None
        self.name = name

    @classmethod
    def start_all_tasks(cls, tasks):
        """Starts all tasks."""
        for task in tasks:
            task.start()

    @classmethod
    def check_all_tasks(cls, tasks):
        """Checks results of all tasks; fails on the first exception found."""
        first_error = None
        first_failed_task = None

        def fail_if_error_pending():
            if first_error:
                log(Exception(first_error))
                log('Failed task: %s.' % first_failed_task.name)
                raise Exception()

        for task in tasks:
            while True:
                # Timeouts should happen after 15 seconds.
                task.join(15)
                if task.isAlive():
                    log('Still waiting for: %s.' % task.name)
                    continue
                else:
                    break

            if task.exception:
                fail_if_error_pending()
                first_error = task.exception
                first_failed_task = task

        fail_if_error_pending()

    @classmethod
    def execute_task_list(cls, tasks):
        """Starts all tasks and checks the results."""
        cls.start_all_tasks(tasks)
        cls.check_all_tasks(tasks)

    def run(self):
        try:
            self.func()
        except Exception as e:  # pylint: disable-msg=broad-except
            self.exception = e


class FunctionalTestTask(object):
    """Executes a set of tests given a test class name."""

    def __init__(self, test_class_name, verbose):
        self.test_class_name = test_class_name
        self.verbose = verbose

    def run(self):
        log('Running all tests in: %s.' % (self.test_class_name))
        test_sh = os.path.join(os.path.dirname(__file__), 'test.sh')
        result, self.output = run(
            ['sh', test_sh, self.test_class_name],
            verbose=self.verbose)
        if result != 0:
            raise Exception()


def setup_all_dependencies():
    """Setup all third party Python packages."""

    log('Setup common environment.')
    common_sh = os.path.join(os.path.dirname(__file__), 'common.sh')
    run(['sh', common_sh], strict=True, stdout=None)


def run_all_tests(presubmit, verbose):
    """Runs all functional tests concurrently."""

    setup_all_dependencies()

    # Prepare tasks.
    task_to_test = {}
    tasks = []
    for test_class_name in ALL_TEST_CLASSES:
        if presubmit and test_class_name in OMITTED_FROM_PRESUBMIT:
            continue
        test = FunctionalTestTask(test_class_name, verbose)
        task = TaskThread(test.run, name='testing %s' % test_class_name)
        task_to_test[task] = test
        tasks.append(task)

    # Execute tasks.
    TaskThread.execute_task_list(tasks)

    # Check we ran all tests as expected.
    total_count = 0
    for task in tasks:
        test = task_to_test[task]
        # Check that no unexpected tests were picked up via automatic discovery,
        # and that the number of tests run in a particular suite.py invocation
        # matches the expected number of tests.
        test_count = ALL_TEST_CLASSES.get(test.test_class_name, None)
        expected_text = 'INFO: All %s tests PASSED!' % test_count
        if test_count is None:
            log('%s\n\nERROR: ran unexpected test class %s' % (
                test.output, test.test_class_name))
        if expected_text not in test.output:
            log('%s\n\nERROR: Expected %s tests to be run for the test class '
                '%s, but found some other number.' % (
                    test.output, test_count, test.test_class_name))
            raise Exception()
        total_count += test_count

    log('Ran %s tests in %s test classes.' % (total_count, len(tasks)))


def main():
    run_all_tests(False, True)


if __name__ == '__main__':
    main()
