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
import time
import yaml

# all test classes with a total count of tests in each
ALL_TEST_CLASSES = {
    'tests.functional.admin_settings.AdminSettingsTests': 2,
    'tests.functional.admin_settings.HtmlHookTest': 11,
    'tests.functional.admin_settings.JinjaContextTest': 2,
    'tests.functional.admin_settings.WelcomePageTests': 5,
    'tests.functional.assets_rest.AssetsRestTest': 13,
    'tests.functional.common_crypto.EncryptionManagerTests': 5,
    'tests.functional.common_crypto.XsrfTokenManagerTests': 3,
    'tests.functional.common_crypto.PiiObfuscationHmac': 2,
    'tests.functional.common_crypto.GenCryptoKeyFromHmac': 2,
    'tests.functional.common_crypto.GetExternalUserIdTests': 4,
    'tests.functional.explorer_module.CourseExplorerTest': 3,
    'tests.functional.explorer_module.CourseExplorerDisabledTest': 2,
    'tests.functional.explorer_module.GlobalProfileTest': 1,
    'tests.functional.controllers_review.PeerReviewControllerTest': 7,
    'tests.functional.controllers_review.PeerReviewDashboardAdminTest': 1,
    'tests.functional.controllers_review.PeerReviewDashboardStudentTest': 2,
    'tests.functional.i18n.I18NCourseSettingsTests': 6,
    'tests.functional.i18n.I18NMultipleChoiceQuestionTests': 6,
    'tests.functional.model_analytics.AnalyticsTabsWithNoJobs': 8,
    'tests.functional.model_analytics.CronCleanupTest': 14,
    'tests.functional.model_analytics.ProgressAnalyticsTest': 8,
    'tests.functional.model_analytics.QuestionAnalyticsTest': 3,
    'tests.functional.model_data_sources.PaginatedTableTest': 17,
    'tests.functional.model_entities.BaseEntityTestCase': 3,
    'tests.functional.model_entities.ExportEntityTestCase': 2,
    'tests.functional.model_entities.EntityTransformsTest': 4,
    'tests.functional.model_jobs.JobOperationsTest': 15,
    'tests.functional.model_models.BaseJsonDaoTestCase': 1,
    'tests.functional.model_models.ContentChunkTestCase': 15,
    'tests.functional.model_models.EventEntityTestCase': 1,
    'tests.functional.model_models.MemcacheManagerTestCase': 4,
    'tests.functional.model_models.PersonalProfileTestCase': 1,
    'tests.functional.model_models.QuestionDAOTestCase': 3,
    'tests.functional.model_models.StudentAnswersEntityTestCase': 1,
    'tests.functional.model_models.StudentProfileDAOTestCase': 6,
    'tests.functional.model_models.StudentPropertyEntityTestCase': 1,
    'tests.functional.model_models.StudentTestCase': 3,
    'tests.functional.model_student_work.KeyPropertyTest': 4,
    'tests.functional.model_student_work.ReviewTest': 3,
    'tests.functional.model_student_work.SubmissionTest': 3,
    'tests.functional.model_utils.QueryMapperTest': 4,
    'tests.functional.module_config_test.ManipulateAppYamlFileTest': 8,
    'tests.functional.module_config_test.ModuleIncorporationTest': 8,
    'tests.functional.module_config_test.ModuleManifestTest': 7,
    'tests.functional.modules_certificate.CertificateHandlerTestCase': 4,
    'tests.functional.modules_certificate.CertificateCriteriaTestCase': 5,
    'tests.functional.modules_core_tags.GoogleDriveRESTHandlerTest': 8,
    'tests.functional.modules_core_tags.GoogleDriveTagRendererTest': 6,
    'tests.functional.modules_core_tags.RuntimeTest': 13,
    'tests.functional.modules_core_tags.TagsInclude': 8,
    'tests.functional.modules_core_tags.TagsMarkdown': 1,
    'tests.functional.modules_courses.AccessDraftsTestCase': 2,
    'tests.functional.modules_dashboard.QuestionDashboardTestCase': 9,
    'tests.functional.modules_dashboard.CourseOutlineTestCase': 1,
    'tests.functional.modules_dashboard.DashboardAccessTestCase': 3,
    'tests.functional.modules_dashboard.RoleEditorTestCase': 3,
    'tests.functional.modules_data_source_providers.CourseElementsTest': 11,
    'tests.functional.modules_data_source_providers.StudentScoresTest': 6,
    'tests.functional.modules_data_source_providers.StudentsTest': 5,
    'tests.functional.modules_i18n_dashboard.CourseContentTranslationTests': 15,
    'tests.functional.modules_i18n_dashboard.IsTranslatableRestHandlerTests': 3,
    'tests.functional.modules_i18n_dashboard.I18nDashboardHandlerTests': 4,
    'tests.functional.modules_i18n_dashboard'
        '.I18nProgressDeferredUpdaterTests': 5,
    'tests.functional.modules_i18n_dashboard.LazyTranslatorTests': 5,
    'tests.functional.modules_i18n_dashboard.ResourceKeyTests': 3,
    'tests.functional.modules_i18n_dashboard.ResourceBundleKeyTests': 2,
    'tests.functional.modules_i18n_dashboard.ResourceRowTests': 6,
    'tests.functional.modules_i18n_dashboard'
        '.TranslationConsoleRestHandlerTests': 7,
    'tests.functional.modules_i18n_dashboard'
        '.TranslationConsoleValidationTests': 4,
    'tests.functional.modules_i18n_dashboard.TranslationImportExportTests': 53,
    'tests.functional.modules_i18n_dashboard.TranslatorRoleTests': 2,
    'tests.functional.modules_i18n_dashboard.SampleCourseLocalizationTest': 16,
    'tests.functional.modules_i18n_dashboard_jobs.BaseJobTest': 9,
    'tests.functional.modules_i18n_dashboard_jobs.DeleteTranslationsTest': 3,
    'tests.functional.modules_i18n_dashboard_jobs.DownloadTranslationsTest': 5,
    'tests.functional.modules_i18n_dashboard_jobs.RoundTripTest': 1,
    'tests.functional.modules_i18n_dashboard_jobs'
        '.TranslateToReversedCaseTest': 1,
    'tests.functional.modules_i18n_dashboard_jobs.UploadTranslationsTest': 5,
    'tests.functional.modules_invitation.InvitationHandlerTests': 16,
    'tests.functional.modules_invitation.ProfileViewInvitationTests': 5,
    'tests.functional.modules_manual_progress.ManualProgressTest': 24,
    'tests.functional.modules_math.MathTagTests': 3,
    'tests.functional.modules_notifications.CronTest': 9,
    'tests.functional.modules_notifications.DatetimeConversionTest': 1,
    'tests.functional.modules_notifications.ManagerTest': 31,
    'tests.functional.modules_notifications.NotificationTest': 8,
    'tests.functional.modules_notifications.PayloadTest': 6,
    'tests.functional.modules_notifications.StatsTest': 2,
    'tests.functional.modules_oeditor.ObjectEditorTest': 4,
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
    'tests.functional.roles.RolesTest': 24,
    'tests.functional.upload_module.TextFileUploadHandlerTestCase': 8,
    'tests.functional.test_classes.ActivityTest': 2,
    'tests.functional.test_classes.AdminAspectTest': 8,
    'tests.functional.test_classes.AssessmentTest': 2,
    'tests.functional.test_classes.CourseAuthorAspectTest': 4,
    'tests.functional.test_classes.CourseAuthorCourseCreationTest': 2,
    'tests.functional.test_classes.CourseUrlRewritingTest': 44,
    'tests.functional.test_classes.DatastoreBackedCustomCourseTest': 6,
    'tests.functional.test_classes.DatastoreBackedSampleCourseTest': 44,
    'tests.functional.test_classes.EtlMainTestCase': 42,
    'tests.functional.test_classes.EtlRemoteEnvironmentTestCase': 0,
    'tests.functional.test_classes.InfrastructureTest': 18,
    'tests.functional.test_classes.I18NTest': 2,
    'tests.functional.test_classes.LessonComponentsTest': 2,
    'tests.functional.test_classes.MemcacheTest': 62,
    'tests.functional.test_classes.MultipleCoursesTest': 1,
    'tests.functional.test_classes.NamespaceTest': 2,
    'tests.functional.test_classes.StaticHandlerTest': 2,
    'tests.functional.test_classes.StudentAspectTest': 19,
    'tests.functional.test_classes.StudentUnifiedProfileTest': 19,
    'tests.functional.test_classes.TransformsEntitySchema': 1,
    'tests.functional.test_classes.TransformsJsonFileTestCase': 3,
    'tests.functional.test_classes.VirtualFileSystemTest': 44,
    'tests.functional.test_classes.ImportActivityTests': 7,
    'tests.functional.test_classes.ImportAssessmentTests': 3,
    'tests.functional.unit_assessment.UnitPrePostAssessmentTest': 17,
    'tests.functional.unit_description.UnitDescriptionsTest': 1,
    'tests.functional.unit_header_footer.UnitHeaderFooterTest': 11,
    'tests.functional.unit_on_one_page.UnitOnOnePageTest': 3,
    'tests.functional.whitelist.WhitelistTest': 12,
    'tests.integration.test_classes': 18,
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
    'tests.unit.common_utils.ZipAwareOpenTests': 2,
    'tests.unit.javascript_tests.AllJavaScriptTests': 7,
    'tests.unit.models_analytics.AnalyticsTests': 5,
    'tests.unit.models_courses.WorkflowValidationTests': 13,
    'tests.unit.models_transforms.JsonToDictTests': 13,
    'tests.unit.models_transforms.JsonParsingTests': 3,
    'tests.unit.models_transforms.StringValueConversionTests': 2,
    'tests.unit.modules_search.ParserTests': 10,
    'tests.unit.test_classes.DeepDictionaryMergeTest': 5,
    'tests.unit.test_classes.EtlRetryTest': 3,
    'tests.unit.test_classes.InvokeExistingUnitTest': 5,
    'tests.unit.test_classes.ReviewModuleDomainTests': 1,
    'tests.unit.test_classes.SuiteTestCaseTest': 3,
}
EXPENSIVE_TESTS = ['tests.integration.test_classes']

LOG_LINES = []
LOG_LOCK = threading.Lock()


def log(message):
    with LOG_LOCK:
        line = '%s\t%s' % (
            datetime.datetime.now().strftime('%Y/%m/%d %H:%M:%S'), message)
        LOG_LINES.append(line)
        print line


def all_third_party_tests():
    yaml_path = os.path.join(os.path.dirname(__file__),
                             'third_party_tests.yaml')
    if os.path.exists(yaml_path):
        with open(yaml_path) as fp:
            data = yaml.load(fp)
        return data['tests']
    else:
        return {}


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
    def execute_task_list(
        cls, tasks,
        chunk_size=None, runtimes_sec=None, fail_on_first_error=False):

        if chunk_size is None:
            chunk_size = len(tasks)
        assert chunk_size > 0
        assert chunk_size < 256

        if runtimes_sec is None:
          runtimes_sec = []

        errors = []

        todo = [] + tasks
        running = set()
        task_to_runtime_sec = {}

        def on_error(error, task):
            errors.append(error)
            log(Exception(error))
            log('Failed task: %s.' % task.name)
            if fail_on_first_error:
                raise Exception(error)

        def update_progress():
            log(
                'Progress so far: '
                '%s failed, %s completed, %s running, %s pending.' % (
                    len(errors), len(tasks) - len(todo) - len(running),
                    len(running), len(todo)))

        last_update_on = 0
        while todo or running:

            # update progress
            now = time.time()
            update_frequency_sec = 15
            if now - last_update_on > update_frequency_sec:
                last_update_on = now
                update_progress()

            # check status of running jobs
            if running:
                for task in list(running):
                    task.join(1)
                    if task.isAlive():
                        start, end = task_to_runtime_sec[task]
                        now = time.time()
                        if now - end > 60:
                            log('Waiting over %ss for: %s' % (
                                int(now - start), task.name))
                            task_to_runtime_sec[task] = (start, now)
                        continue
                    if task.exception:
                        on_error(task.exception, task)
                    start, _ = task_to_runtime_sec[task]
                    now = time.time()
                    task_to_runtime_sec[task] = (start, now)
                    running.remove(task)

            # submit new work
            while len(running) < chunk_size and todo:
                task = todo.pop(0)
                running.add(task)
                now = time.time()
                task_to_runtime_sec[task] = (now, now)
                task.start()

        update_progress()

        if errors:
            raise Exception('There were %s errors' % len(errors))

        # format runtimes
        for task in tasks:
            start, end = task_to_runtime_sec[task]
            runtimes_sec.append(end - start)

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
        if self.verbose:
            log('Running all tests in: %s.' % (self.test_class_name))
        test_sh = os.path.join(os.path.dirname(__file__), 'test.sh')
        result, self.output = run(
            ['sh', test_sh, self.test_class_name],
            verbose=self.verbose)
        if result != 0:
            raise Exception()


def setup_all_dependencies():
    """Setup all third party Python packages."""

    common_sh = os.path.join(os.path.dirname(__file__), 'common.sh')
    result, output = run(['sh', common_sh], strict=True)
    if result != 0:
        raise Exception()
    for line in output.split('\n'):
        if not line:
            continue
        # ignore garbage produced by the script; it proven impossible to fix the
        # script to avoid garbage from being produced
        if 'grep: write error' in line or 'grep: writing output' in line:
            continue
        log(line)


def chunk_list(l, n):
    """Yield successive n-sized chunks from l."""
    for i in xrange(0, len(l), n):
        yield l[i:i + n]


def run_all_tests(skip_expensive_tests, verbose, setup_deps=True):
    """Runs all functional tests concurrently."""

    start = time.time()

    # Prepare tasks.
    task_to_test = {}
    tasks = []
    test_classes = {}
    test_classes.update(ALL_TEST_CLASSES)
    test_classes.update(all_third_party_tests())

    for test_class_name in test_classes:
        if skip_expensive_tests and test_class_name in EXPENSIVE_TESTS:
            continue
        test = FunctionalTestTask(test_class_name, verbose)
        task = TaskThread(test.run, name='testing %s' % test_class_name)
        task_to_test[task] = test
        tasks.append(task)

    # order tests by their size largest to smallest
    tasks = sorted(
        tasks,
        key=lambda task: test_classes.get(task_to_test[task].test_class_name),
        reverse=True)

    # setup dependencies
    if setup_deps:
        setup_all_dependencies()

    # execute all tasks
    log('Executing all %s test suites' % len(tasks))
    runtimes_sec = []
    TaskThread.execute_task_list(
        tasks, chunk_size=16, runtimes_sec=runtimes_sec)

    # map durations to names
    name_durations = []
    for index, duration in enumerate(runtimes_sec):
        name_durations.append((
            round(duration, 2), task_to_test[tasks[index]].test_class_name))

    # report all longest first
    log('Reporting execution times for 10 longest tests')
    for duration, name in sorted(
        name_durations, key=lambda name_duration: name_duration[0],
        reverse=True)[:10]:
        log('Took %ss for %s' % (int(duration), name))

    # Check we ran all tests as expected.
    total_count = 0
    for task in tasks:
        test = task_to_test[task]
        # Check that no unexpected tests were picked up via automatic discovery,
        # and that the number of tests run in a particular suite.py invocation
        # matches the expected number of tests.
        test_count = test_classes.get(test.test_class_name, None)
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

    log('Ran %s tests in %s test classes; took %ss' % (
        total_count, len(tasks), int(time.time() - start)))


def main():
    run_all_tests(False, True)


if __name__ == '__main__':
    main()
