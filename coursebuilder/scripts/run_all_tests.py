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


import argparse
import datetime
import logging
import multiprocessing
import os
import re
import signal
import socket
import stat
import subprocess
import sys
import threading
import time
import yaml


# WARNING !!!
#
# by convention, all entries in the ALL_*_TEST_CLASSES dicts, including
# integration test entries, are executed in separate threads concurrently;
# be very careful with it; use it when you are confident that the tests do
# not interfere with each other at runtime; they do interfere in a couple of
# ways, for example: due to edits to a shared course content, due to changes
# to the shared configuration properties or course settings and so on;
#
# when needed, force groups of tests to execute serially; simply don't list
# them here individually, but do create a new empty test class that inherits
# the individual tests from all desired test classes via multiple inheritance;
# list each bundle class below individually and all tests within it will run
# serially, while all the entries themselves continue to run concurrently
#
# WARNING !!!

# here we list all integration tests that require an integration server
ALL_INTEGRATION_TEST_CLASSES = {
    'tests.integration.test_classes.IntegrationTestBundle1': 15,
    'tests.integration.test_classes.VisualizationsTest': 5,
    'tests.integration.test_classes.EmbedModuleTest': 3,
}

# here we list all functional and unit tests that run in-process
ALL_TEST_CLASSES = {
    'tests.functional.admin_settings.AdminSettingsTests': 1,
    'tests.functional.admin_settings.ExitUrlTest': 1,
    'tests.functional.admin_settings.HtmlHookTest': 17,
    'tests.functional.admin_settings.JinjaContextTest': 2,
    'tests.functional.admin_settings.WelcomePageTests': 6,
    'tests.functional.assets_rest.AssetsRestTest': 13,
    'tests.functional.common_crypto.EncryptionManagerTests': 5,
    'tests.functional.common_crypto.XsrfTokenManagerTests': 3,
    'tests.functional.common_crypto.PiiObfuscationHmac': 2,
    'tests.functional.common_crypto.GenCryptoKeyFromHmac': 2,
    'tests.functional.common_crypto.GetExternalUserIdTests': 4,
    'tests.functional.common_users.AppEnginePassthroughUsersServiceTest': 10,
    'tests.functional.common_users.AuthInterceptorAndRequestHooksTest': 2,
    'tests.functional.common_users.PublicExceptionsAndClassesIdentityTests': 2,
    'tests.functional.explorer_module.CourseExplorerTest': 5,
    'tests.functional.explorer_module.CourseExplorerDisabledTest': 3,
    'tests.functional.explorer_module.GlobalProfileTest': 1,
    'tests.functional.controllers_review.PeerReviewControllerTest': 7,
    'tests.functional.controllers_review.PeerReviewDashboardAdminTest': 1,
    'tests.functional.controllers_review.PeerReviewDashboardStudentTest': 2,
    'tests.functional.i18n.I18NCourseSettingsTests': 7,
    'tests.functional.i18n.I18NMultipleChoiceQuestionTests': 6,
    'tests.functional.model_analytics.AnalyticsTabsWithNoJobs': 8,
    'tests.functional.model_analytics.CronCleanupTest': 14,
    'tests.functional.model_analytics.MapReduceSimpleTest': 1,
    'tests.functional.model_analytics.ProgressAnalyticsTest': 9,
    'tests.functional.model_analytics.QuestionAnalyticsTest': 3,
    'tests.functional.model_config.ValueLoadingTests': 2,
    'tests.functional.model_courses.CourseCachingTest': 5,
    'tests.functional.model_data_sources.PaginatedTableTest': 17,
    'tests.functional.model_data_sources.PiiExportTest': 4,
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
    'tests.functional.model_models.StudentLifecycleObserverTestCase': 13,
    'tests.functional.model_models.StudentProfileDAOTestCase': 6,
    'tests.functional.model_models.StudentPropertyEntityTestCase': 1,
    'tests.functional.model_models.StudentTestCase': 11,
    'tests.functional.model_student_work.KeyPropertyTest': 4,
    'tests.functional.model_student_work.ReviewTest': 3,
    'tests.functional.model_student_work.SubmissionTest': 3,
    'tests.functional.model_utils.QueryMapperTest': 4,
    'tests.functional.model_vfs.VfsLargeFileSupportTest': 6,
    'tests.functional.module_config_test.ManipulateAppYamlFileTest': 8,
    'tests.functional.module_config_test.ModuleIncorporationTest': 12,
    'tests.functional.module_config_test.ModuleManifestTest': 7,
    'tests.functional.modules_admin.AdminDashboardTabTests': 4,
    'tests.functional.modules_analytics.ClusterRESTHandlerTest': 29,
    'tests.functional.modules_analytics.ClusteringGeneratorTests': 6,
    'tests.functional.modules_analytics.ClusteringTabTests': 7,
    'tests.functional.modules_analytics.StudentAggregateTest': 6,
    'tests.functional.modules_analytics.StudentVectorGeneratorProgressTests': 2,
    'tests.functional.modules_analytics.StudentVectorGeneratorTests': 12,
    'tests.functional.modules_analytics.TestClusterStatisticsDataSource': 2,
    'tests.functional.modules_balancer.ExternalTaskTest': 3,
    'tests.functional.modules_balancer.ManagerTest': 10,
    'tests.functional.modules_balancer.ProjectRestHandlerTest': 5,
    'tests.functional.modules_balancer.TaskRestHandlerTest': 20,
    'tests.functional.modules_balancer.WorkerPoolTest': 2,
    'tests.functional.modules_certificate.CertificateHandlerTestCase': 5,
    'tests.functional.modules_certificate.CertificateCriteriaTestCase': 6,
    'tests.functional.modules_code_tags.CodeTagTests': 3,
    'tests.functional.modules_core_tags.GoogleDriveRESTHandlerTest': 8,
    'tests.functional.modules_core_tags.GoogleDriveTagRendererTest': 8,
    'tests.functional.modules_core_tags.RuntimeTest': 13,
    'tests.functional.modules_core_tags.TagsInclude': 8,
    'tests.functional.modules_core_tags.TagsMarkdown': 1,
    'tests.functional.modules_courses.AccessDraftsTestCase': 2,
    'tests.functional.modules_dashboard.CourseOutlineTestCase': 3,
    'tests.functional.modules_dashboard.DashboardAccessTestCase': 3,
    'tests.functional.modules_dashboard.TestLessonSchema': 2,
    'tests.functional.modules_dashboard.QuestionDashboardTestCase': 10,
    'tests.functional.modules_dashboard.RoleEditorTestCase': 3,
    'tests.functional.modules_data_pump.SchemaConversionTests': 1,
    'tests.functional.modules_data_pump.StudentSchemaValidationTests': 2,
    'tests.functional.modules_data_pump.PiiTests': 7,
    'tests.functional.modules_data_pump.BigQueryInteractionTests': 36,
    'tests.functional.modules_data_pump.UserInteractionTests': 4,
    'tests.functional.modules_data_removal.DataRemovalTests': 8,
    'tests.functional.modules_data_removal.UserInteractionTests': 16,
    'tests.functional.modules_data_source_providers.CourseElementsTest': 11,
    'tests.functional.modules_data_source_providers.StudentScoresTest': 6,
    'tests.functional.modules_data_source_providers.StudentsTest': 5,
    'tests.functional.modules_embed.DemoHandlerTest': 2,
    'tests.functional.modules_embed.ExampleEmbedAndHandlerV1Test': 3,
    'tests.functional.modules_embed.FinishAuthHandlerTest': 1,
    'tests.functional.modules_embed.GlobalErrorsDemoHandlerTest': 2,
    'tests.functional.modules_embed.Handlers404ByDefaultTest': 2,
    'tests.functional.modules_embed.JsHandlersTest': 3,
    'tests.functional.modules_embed.LocalErrorsDemoHandlerTest': 2,
    'tests.functional.modules_embed.RegistryTest': 3,
    'tests.functional.modules_embed.StaticResourcesTest': 1,
    'tests.functional.modules_embed.UrlParserTest': 12,
    'tests.functional.modules_extra_tabs.ExtraTabsTests': 7,
    'tests.functional.modules_gitkit'
        '.AccountChooserCustomizationHandlersTest': 2,
    'tests.functional.modules_gitkit.BaseHandlerTest': 3,
    'tests.functional.modules_gitkit.EmailMappingTest': 6,
    'tests.functional.modules_gitkit.EmailRestHandlerTest': 5,
    'tests.functional.modules_gitkit.RuntimeAndRuntimeConfigTest': 12,
    'tests.functional.modules_gitkit.GitkitServiceTest': 9,
    'tests.functional.modules_gitkit.OobChangeEmailResponseTest': 7,
    'tests.functional.modules_gitkit.OobFailureResponseTest': 6,
    'tests.functional.modules_gitkit.OobResetPasswordResponseTest': 7,
    'tests.functional.modules_gitkit.SignInContinueHandlerTest': 4,
    'tests.functional.modules_gitkit.SignInHandlerTest': 11,
    'tests.functional.modules_gitkit.SignOutContinueHandlerTest': 5,
    'tests.functional.modules_gitkit.SignOutHandlerTest': 2,
    'tests.functional.modules_gitkit.StudentFederatedEmailTest': 2,
    'tests.functional.modules_gitkit.WidgetHandlerTest': 2,
    'tests.functional.modules_gitkit.UsersServiceTest': 16,
    'tests.functional.modules_i18n_dashboard.CourseContentTranslationTests': 15,
    'tests.functional.modules_i18n_dashboard.IsTranslatableRestHandlerTests': 3,
    'tests.functional.modules_i18n_dashboard.I18nDashboardHandlerTests': 4,
    'tests.functional.modules_i18n_dashboard'
        '.I18nProgressDeferredUpdaterTests': 5,
    'tests.functional.modules_i18n_dashboard.LazyTranslatorTests': 5,
    'tests.functional.modules_i18n_dashboard.ResourceBundleKeyTests': 2,
    'tests.functional.modules_i18n_dashboard.ResourceRowTests': 6,
    'tests.functional.modules_i18n_dashboard'
        '.TranslationConsoleRestHandlerTests': 8,
    'tests.functional.modules_i18n_dashboard'
        '.TranslationConsoleValidationTests': 5,
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
    'tests.functional.modules_invitation.SantitationTests': 1,
    'tests.functional.modules_manual_progress.ManualProgressTest': 24,
    'tests.functional.modules_math.MathTagTests': 3,
    'tests.functional.modules_notifications.CronTest': 9,
    'tests.functional.modules_notifications.DatetimeConversionTest': 1,
    'tests.functional.modules_notifications.ManagerTest': 31,
    'tests.functional.modules_notifications.NotificationTest': 8,
    'tests.functional.modules_notifications.PayloadTest': 6,
    'tests.functional.modules_notifications.SerializedPropertyTest': 2,
    'tests.functional.modules_notifications.StatsTest': 2,
    'tests.functional.modules_oeditor.ButtonbarCssHandlerTests': 2,
    'tests.functional.modules_oeditor.ObjectEditorTest': 4,
    'tests.functional.modules_oeditor.EditorPrefsTests': 6,
    'tests.functional.modules_questionnaire.QuestionnaireDataSourceTests': 2,
    'tests.functional.modules_questionnaire.QuestionnaireTagTests': 3,
    'tests.functional.modules_questionnaire.QuestionnaireRESTHandlerTests': 5,
    'tests.functional.modules_rating.ExtraContentProvideTests': 4,
    'tests.functional.modules_rating.RatingHandlerTests': 15,
    'tests.functional.modules_search.SearchTest': 12,
    'tests.functional.modules_skill_map.CompetencyMeasureTests': 4,
    'tests.functional.modules_skill_map.CountSkillCompletionsTests': 3,
    'tests.functional.modules_skill_map.GenerateCompetencyHistogramsTests': 1,
    'tests.functional.modules_skill_map.EventListenerTests': 4,
    'tests.functional.modules_skill_map.LocationListRestHandlerTests': 2,
    'tests.functional.modules_skill_map.SkillAggregateRestHandlerTests': 6,
    'tests.functional.modules_skill_map.SkillCompletionTrackerTests': 6,
    'tests.functional.modules_skill_map.SkillGraphTests': 11,
    'tests.functional.modules_skill_map.SkillI18nTests': 5,
    'tests.functional.modules_skill_map.SkillMapAnalyticsTabTests': 2,
    'tests.functional.modules_skill_map.SkillMapHandlerTests': 3,
    'tests.functional.modules_skill_map.SkillMapMetricTests': 10,
    'tests.functional.modules_skill_map.SkillMapTests': 7,
    'tests.functional.modules_skill_map.SkillRestHandlerTests': 18,
    'tests.functional.modules_skill_map.StudentSkillViewWidgetTests': 6,
    'tests.functional.modules_unsubscribe.GetUnsubscribeUrlTests': 1,
    'tests.functional.modules_unsubscribe.SubscribeAndUnsubscribeTests': 4,
    'tests.functional.modules_unsubscribe.UnsubscribeHandlerTests': 4,
    'tests.functional.modules_usage_reporting.ConsentBannerTests': 4,
    'tests.functional.modules_usage_reporting.ConsentBannerRestHandlerTests': 3,
    'tests.functional.modules_usage_reporting.ConfigTests': 3,
    'tests.functional.modules_usage_reporting.CourseCreationTests': 4,
    'tests.functional.modules_usage_reporting.DevServerTests': 2,
    'tests.functional.modules_usage_reporting.EnrollmentTests': 3,
    'tests.functional.modules_usage_reporting.MessagingTests': 8,
    'tests.functional.modules_usage_reporting.UsageReportingTests': 4,
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
    'tests.functional.test_classes.AdminAspectTest': 9,
    'tests.functional.test_classes.AssessmentTest': 2,
    'tests.functional.test_classes.CourseAuthorAspectTest': 4,
    'tests.functional.test_classes.CourseAuthorCourseCreationTest': 1,
    'tests.functional.test_classes.CourseUrlRewritingTest': 44,
    'tests.functional.test_classes.DatastoreBackedCustomCourseTest': 6,
    'tests.functional.test_classes.DatastoreBackedSampleCourseTest': 44,
    'tests.functional.test_classes.EtlMainTestCase': 42,
    'tests.functional.test_classes.EtlRemoteEnvironmentTestCase': 0,
    'tests.functional.test_classes.ExtensionSwitcherTests': 2,
    'tests.functional.test_classes.InfrastructureTest': 21,
    'tests.functional.test_classes.I18NTest': 2,
    'tests.functional.test_classes.LegacyEMailAsKeyNameTest': 44,
    'tests.functional.test_classes.LessonComponentsTest': 3,
    'tests.functional.test_classes.MemcacheTest': 65,
    'tests.functional.test_classes.MultipleCoursesTest': 1,
    'tests.functional.test_classes.NamespaceTest': 2,
    'tests.functional.test_classes.StaticHandlerTest': 1,
    'tests.functional.test_classes.StudentAspectTest': 19,
    'tests.functional.test_classes.StudentKeyNameTest': 8,
    'tests.functional.test_classes.StudentUnifiedProfileTest': 19,
    'tests.functional.test_classes.TransformsEntitySchema': 1,
    'tests.functional.test_classes.TransformsJsonFileTestCase': 3,
    'tests.functional.test_classes.VirtualFileSystemTest': 44,
    'tests.functional.test_classes.ImportActivityTests': 7,
    'tests.functional.test_classes.ImportAssessmentTests': 3,
    'tests.functional.test_classes.ImportGiftQuestionsTests': 1,
    'tests.functional.test_classes.WSGIRoutingTest': 3,
    'tests.functional.unit_assessment.UnitPrePostAssessmentTest': 18,
    'tests.functional.unit_description.UnitDescriptionsTest': 1,
    'tests.functional.unit_header_footer.UnitHeaderFooterTest': 11,
    'tests.functional.unit_on_one_page.UnitOnOnePageTest': 4,
    'tests.functional.whitelist.WhitelistTest': 12,
    'tests.unit.etl_mapreduce.HistogramTests': 5,
    'tests.unit.etl_mapreduce.FlattenJsonTests': 4,
    'tests.unit.common_catch_and_log.CatchAndLogTests': 6,
    'tests.unit.common_locales.LocalesTests': 2,
    'tests.unit.common_locales.ParseAcceptLanguageTests': 6,
    'tests.unit.common_menus.MenuTests': 6,
    'tests.unit.common_resource.ResourceKeyTests': 3,
    'tests.unit.common_schema_fields.SchemaFieldTests': 4,
    'tests.unit.common_schema_fields.FieldArrayTests': 3,
    'tests.unit.common_schema_fields.FieldRegistryTests': 7,
    'tests.unit.common_safe_dom.NodeListTests': 4,
    'tests.unit.common_safe_dom.TextTests': 2,
    'tests.unit.common_safe_dom.ElementTests': 17,
    'tests.unit.common_safe_dom.ScriptElementTests': 3,
    'tests.unit.common_safe_dom.EntityTests': 11,
    'tests.unit.common_tags.CustomTagTests': 13,
    'tests.unit.common_utils.CommonUnitTests': 11,
    'tests.unit.common_utils.ParseTimedeltaTests': 8,
    'tests.unit.common_utils.ValidateTimedeltaTests': 6,
    'tests.unit.common_utils.ZipAwareOpenTests': 2,
    'tests.unit.javascript_tests.AllJavaScriptTests': 9,
    'tests.unit.models_analytics.AnalyticsTests': 5,
    'tests.unit.models_config.ValidateIntegerRangeTests': 3,
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
    'tests.unit.gift_parser_tests.SampleQuestionsTest': 1,
    'tests.unit.gift_parser_tests.TestEssayAndNumericQuestion': 4,
    'tests.unit.gift_parser_tests.TestMatchQuestion': 3,
    'tests.unit.gift_parser_tests.TestMissingWordQuestion': 2,
    'tests.unit.gift_parser_tests.TestShortAnswerQuestion': 3,
    'tests.unit.gift_parser_tests.TestTrueFalseQuestion': 2,
    'tests.unit.gift_parser_tests.TestMultiChoiceMultipleSelectionQuestion': 3,
    'tests.unit.gift_parser_tests.TestHead': 2,
    'tests.unit.gift_parser_tests.TestMultiChoiceQuestion': 5,
    'tests.unit.gift_parser_tests.TestCreateManyGiftQuestion': 1
}

INTEGRATION_SERVER_BASE_URL = 'http://localhost:8081'

LOG_LINES = []
LOG_LOCK = threading.Lock()


def make_default_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--test_class_name',
        help='required dotted module name of the test(s) to run',
        type=str, default=None)
    parser.add_argument(
        '--skip_integration', help='Whether to run integration tests',
        action='store_true')
    parser.add_argument(
        '--skip_non_integration',
        help='Whether to run functional and unit tests',
        action='store_true')
    parser.add_argument(
        '--skip_pylint', help='Whether to run pylint tests',
        action='store_true')
    parser.add_argument(
        '--ignore_pylint_failures',
        help='Whether to ignore pylint test failures',
        action='store_true')
    parser.add_argument(
        '--verbose',
        help='Print more verbose output to help diagnose problems',
        action='store_true')
    return parser



def _parse_test_name(name):
    """Attempts to convert the argument to a dotted test name.

    If the test name is provided in the format output by unittest error
    messages (e.g., "my_test (tests.functional.modules_my.MyModuleTest)")
    then it is converted to a dotted test name
    (e.g., "tests.functional.modules_my.MyModuleTest.my_test"). Otherwise
    it is returned unmodified.
    """

    if not name:
        return name

    match = re.match(r"\s*(?P<method_name>\S+)\s+\((?P<class_name>\S+)\)\s*",
        name)
    if match:
        return "{class_name}.{method_name}".format(
            class_name=match.group('class_name'),
            method_name=match.group('method_name'),
        )
    else:
        return name


def ensure_port_available(port_number):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind(('localhost', port_number))
    except socket.error, ex:
        logging.error('''
            ==========================================================
            Failed to bind to port %d.
            This probably means another CourseBuilder server is
            already running.  Be sure to shut down any manually
            started servers before running tests.
            ==========================================================''',
            port_number)
        raise ex
    s.close()


def start_integration_server():
    ensure_port_available(8081)
    ensure_port_available(8000)
    server_cmd = os.path.join(
        os.path.dirname(__file__), 'start_in_shell.sh')
    server = start_integration_server_process(
        server_cmd,
        set(['tests.integration.fake_visualizations']))
    return server


def start_integration_server_process(integration_server_start_cmd, modules):
    if modules:
        _fn = os.path.join(os.path.dirname(__file__), '..', 'custom.yaml')
        _st = os.stat(_fn)
        os.chmod(_fn, _st.st_mode | stat.S_IWUSR)
        fp = open(_fn, 'w')
        fp.writelines([
            'env_variables:\n',
            '  GCB_REGISTERED_MODULES_CUSTOM:\n'])
        fp.writelines(['    %s\n' % module for module in modules])
        fp.close()

    logging.info('Starting external server: %s', integration_server_start_cmd)
    devnull = open(os.devnull, 'w')
    server = subprocess.Popen(
        integration_server_start_cmd, stdout=devnull, stderr=devnull)
    time.sleep(3)  # Wait for server to start up

    return server


def stop_integration_server(server, modules):
    server.kill()  # dev_appserver.py itself.

    # The new dev appserver starts a _python_runtime.py process that isn't
    # captured by start_integration_server and so doesn't get killed. Until it's
    # done, our tests will never complete so we kill it manually.
    (stdout, unused_stderr) = subprocess.Popen(
        ['pgrep', '-f', '_python_runtime.py'], stdout=subprocess.PIPE
    ).communicate()

    # If tests are killed partway through, runtimes can build up; send kill
    # signals to all of them, JIC.
    pids = [int(pid.strip()) for pid in stdout.split('\n') if pid.strip()]
    for pid in pids:
        os.kill(pid, signal.SIGKILL)

    if modules:
        fp = open(
            os.path.join(os.path.dirname(__file__), '..', 'custom.yaml'), 'w')
        fp.writelines([
            '# Add configuration for your application here to avoid\n'
            '# potential merge conflicts with new releases of the main\n'
            '# app.yaml file.  Modules registered here should support the\n'
            '# standard CourseBuilder module config.  (Specifically, the\n'
            '# imported Python module should provide a method\n'
            '# "register_module()", taking no parameters and returning a\n'
            '# models.custom_modules.Module instance.\n'
            '#\n'
            'env_variables:\n'
            '#  GCB_REGISTERED_MODULES_CUSTOM:\n'
            '#    modules.my_extension_module\n'
            '#    my_extension.modules.widgets\n'
            '#    my_extension.modules.blivets\n'
            ])
        fp.close()


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
            update_frequency_sec = 30
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
        except Exception as e:  # pylint: disable=broad-except
            self.exception = e


class FunctionalTestTask(object):
    """Executes a set of tests given a test class name."""

    def __init__(self, test_class_name, verbose):
        self.test_class_name = test_class_name
        self.verbose = verbose

    def run(self):
        if self.verbose:
            log('Running all tests in: %s.' % (self.test_class_name))

        suite_sh = os.path.join(os.path.dirname(__file__), 'suite.sh')
        result, self.output = run(
            ['sh', suite_sh, self.test_class_name], stdout=None,
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


def is_a_member_of(test_class_name, set_of_tests):
    for name in set_of_tests.keys():

        # try matching on the class name
        if name.find(test_class_name) == 0:
            return True

        # try matching on the method name
        if test_class_name.find(name) == 0:
            return True

    return False


def select_tests_to_run(test_class_name):
    test_classes = {}
    test_classes.update(ALL_TEST_CLASSES)
    test_classes.update(ALL_INTEGRATION_TEST_CLASSES)
    test_classes.update(all_third_party_tests())

    if test_class_name:
        _test_classes = {}

        for name in test_classes.keys():
            # try matching on the class name
            if name.find(test_class_name) == 0:
                _test_classes.update({name: test_classes[name]})
                continue

            # try matching on the method name
            if test_class_name.find(name) == 0:
                _test_classes.update({test_class_name: 1})
                continue

        if not _test_classes:
            raise Exception('No tests found for "%s".' % test_class_name)
        test_classes = _test_classes

        sorted_names = sorted(test_classes, key=lambda key: test_classes[key])

    return test_classes


def run_all_tests(parsed_args, setup_deps=True):
    # get all applicable tests
    test_classes = select_tests_to_run(
        _parse_test_name(parsed_args.test_class_name))

    # separate out integration and non-integration tests
    integration_tests = {}
    non_integration_tests = {}
    for test_class_name in test_classes.keys():
        if is_a_member_of(
            test_class_name, ALL_INTEGRATION_TEST_CLASSES):
            target = integration_tests
        else:
            target = non_integration_tests
        target.update(
                {test_class_name: test_classes[test_class_name]})

    if parsed_args.skip_non_integration:
        log('Skipping non-integration tests at user request')
        non_integration_tests = {}
    if parsed_args.skip_integration:
        log('Skipping integration test at user request')
        integration_tests = {}

    all_tests = {}
    all_tests.update(non_integration_tests)
    all_tests.update(integration_tests)

    server = None
    if integration_tests:
        server = start_integration_server()
        run_tests({
            'tests.integration.test_classes.'
            'IntegrationServerInitializationTask': 1},
            False, setup_deps=False, chunk_size=1, hint='setup')
    try:
        if all_tests:
            try:
                chunk_size = 2 * multiprocessing.cpu_count()
            except:  # pylint: disable=bare-except
                chunk_size = 8
            run_tests(
                all_tests, parsed_args.verbose,
                setup_deps=setup_deps, chunk_size=chunk_size)
    finally:
        if server:
            stop_integration_server(
                server,
                set(['tests.integration.fake_visualizations']))


def run_tests(
    test_classes, verbose, setup_deps=True, chunk_size=16, hint='generic'):
    start = time.time()
    task_to_test = {}
    tasks = []
    integration_tasks = []

    # Prepare tasks
    for test_class_name in test_classes:
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
    log('Executing %s "%s" test suites' % (len(tasks), hint))
    runtimes_sec = []
    TaskThread.execute_task_list(
        tasks, chunk_size=chunk_size, runtimes_sec=runtimes_sec)

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


def run_lint():
    # Wire outputs to our own stdout/stderr so messages appear immediately,
    # rather than batching up and waiting for the end (linting takes a while)
    path = os.path.join(os.path.dirname(__file__), 'pylint.sh')
    status = subprocess.call(path, stdin=None, stdout=sys.stdout,
                             stderr=sys.stderr)
    return status == 0


def main():
    parser = make_default_parser()
    parsed_args = parser.parse_args()

    if parsed_args.skip_pylint:
        log('Skipping pylint at user request')
    else:
        if not run_lint():
            if parsed_args.ignore_pylint_failures:
                log('Ignoring pylint test errors.')
            else:
                raise RuntimeError('Pylint tests failed.')

    run_all_tests(parsed_args)


if __name__ == '__main__':
    main()
