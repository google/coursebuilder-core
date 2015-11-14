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

"""List of all tests.

    WARNING !!!

    by convention, all entries in the ALL_*_TEST_CLASSES dicts, including
    integration test entries, are executed in separate threads concurrently;
    be very careful with it; use it when you are confident that the tests do
    not interfere with each other at runtime; they do interfere in a couple of
    ways, for example: due to edits to a shared course content, due to changes
    to the shared configuration properties or course settings and so on;

    when needed, force groups of tests to execute serially; simply don't list
    them here individually, but do create a new empty test class that inherits
    the individual tests from all desired test classes via multiple inheritance;
    list each bundle class below individually and all tests within it will run
    serially, while all the entries themselves continue to run concurrently

    WARNING !!!

"""

__author__ = 'Pavel Simakov (psimakov@google.com)'


# here we list all integration tests that require an integration server
ALL_INTEGRATION_TEST_CLASSES = {
    'tests.integration.test_classes.IntegrationTestBundle1': 15,
    'tests.integration.test_classes.VisualizationsTest': 5,
}

# here we list all functional and unit tests that run in-process
ALL_TEST_CLASSES = {
    'tests.functional.admin_settings.AdminSettingsTests': 1,
    'tests.functional.admin_settings.ExitUrlTest': 1,
    'tests.functional.admin_settings.HtmlHookTest': 17,
    'tests.functional.admin_settings.JinjaContextTest': 2,
    'tests.functional.admin_settings.WelcomePageTests': 2,
    'tests.functional.assets_rest.AssetsRestTest': 13,
    'tests.functional.common_crypto.EncryptionManagerTests': 5,
    'tests.functional.common_crypto.XsrfTokenManagerTests': 3,
    'tests.functional.common_crypto.PiiObfuscationHmac': 2,
    'tests.functional.common_crypto.GenCryptoKeyFromHmac': 2,
    'tests.functional.common_crypto.GetExternalUserIdTests': 4,
    'tests.functional.common_users.AppEnginePassthroughUsersServiceTest': 10,
    'tests.functional.common_users.AuthInterceptorAndRequestHooksTest': 2,
    'tests.functional.common_users.PublicExceptionsAndClassesIdentityTests': 2,
    'tests.functional.controllers_utils.LocalizedGlobalHandlersTest': 4,
    'tests.functional.i18n.I18NCourseSettingsTests': 7,
    'tests.functional.i18n.I18NMultipleChoiceQuestionTests': 6,
    'tests.functional.model_analytics.AnalyticsTabsWithNoJobs': 8,
    'tests.functional.model_analytics.CronCleanupTest': 14,
    'tests.functional.model_analytics.MapReduceSimpleTest': 1,
    'tests.functional.model_analytics.ProgressAnalyticsTest': 9,
    'tests.functional.model_analytics.QuestionAnalyticsTest': 3,
    'tests.functional.model_config.ValueLoadingTests': 2,
    'tests.functional.model_courses.CourseCachingTest': 5,
    'tests.functional.model_courses.PermissionsTest': 4,
    'tests.functional.model_data_sources.PaginatedTableTest': 17,
    'tests.functional.model_data_sources.PiiExportTest': 4,
    'tests.functional.model_entities.BaseEntityTestCase': 3,
    'tests.functional.model_entities.ExportEntityTestCase': 2,
    'tests.functional.model_entities.EntityTransformsTest': 4,
    'tests.functional.model_jobs.JobOperationsTest': 15,
    'tests.functional.model_models.BaseJsonDaoTestCase': 1,
    'tests.functional.model_models.ContentChunkTestCase': 16,
    'tests.functional.model_models.EventEntityTestCase': 1,
    'tests.functional.model_models.MemcacheManagerTestCase': 4,
    'tests.functional.model_models.PersonalProfileTestCase': 1,
    'tests.functional.model_models.QuestionDAOTestCase': 3,
    'tests.functional.model_models.StudentAnswersEntityTestCase': 1,
    'tests.functional.model_models.StudentLifecycleObserverTestCase': 13,
    'tests.functional.model_models.StudentProfileDAOTestCase': 6,
    'tests.functional.model_models.StudentPropertyEntityTestCase': 1,
    'tests.functional.model_models.StudentTestCase': 11,
    'tests.functional.model_permissions.PermissionsTests': 4,
    'tests.functional.model_permissions.SimpleSchemaPermissionTests': 16,
    'tests.functional.model_student_work.KeyPropertyTest': 4,
    'tests.functional.model_student_work.ReviewTest': 3,
    'tests.functional.model_student_work.SubmissionTest': 3,
    'tests.functional.model_utils.QueryMapperTest': 4,
    'tests.functional.model_vfs.VfsLargeFileSupportTest': 6,
    'tests.functional.module_config_test.ManipulateAppYamlFileTest': 8,
    'tests.functional.module_config_test.ModuleIncorporationTest': 12,
    'tests.functional.module_config_test.ModuleManifestTest': 7,
    'tests.functional.modules_data_source_providers.CourseElementsTest': 11,
    'tests.functional.modules_data_source_providers.StudentScoresTest': 6,
    'tests.functional.modules_data_source_providers.StudentsTest': 5,
    'tests.functional.progress_percent.ProgressPercent': 4,
    'tests.functional.student_answers.StudentAnswersAnalyticsTest': 1,
    'tests.functional.student_labels.StudentLabelsTest': 32,
    'tests.functional.student_last_location.NonRootCourse': 9,
    'tests.functional.student_last_location.RootCourse': 3,
    'tests.functional.student_tracks.StudentTracksTest': 10,
    'tests.functional.roles.RolesTest': 24,
    'tests.functional.test_classes.ActivityTest': 1,
    'tests.functional.test_classes.AdminAspectTest': 10,
    'tests.functional.test_classes.AssessmentPolicyTests': 6,
    'tests.functional.test_classes.AssessmentTest': 2,
    'tests.functional.test_classes.CourseAuthorAspectTest': 4,
    'tests.functional.test_classes.CourseAuthorCourseCreationTest': 1,
    'tests.functional.test_classes.CourseAuthorCourseDeletionTest': 7,
    'tests.functional.test_classes.CourseUrlRewritingTest': 47,
    'tests.functional.test_classes.DatastoreBackedCustomCourseTest': 6,
    'tests.functional.test_classes.DatastoreBackedSampleCourseTest': 47,
    'tests.functional.test_classes.EtlMainTestCase': 46,
    'tests.functional.test_classes.EtlTranslationRoundTripTest': 1,
    'tests.functional.test_classes.ExtensionSwitcherTests': 2,
    'tests.functional.test_classes.InfrastructureTest': 21,
    'tests.functional.test_classes.I18NTest': 2,
    'tests.functional.test_classes.LegacyEMailAsKeyNameTest': 47,
    'tests.functional.test_classes.LessonComponentsTest': 3,
    'tests.functional.test_classes.MemcacheTest': 68,
    'tests.functional.test_classes.MultipleCoursesTest': 1,
    'tests.functional.test_classes.NamespaceTest': 2,
    'tests.functional.test_classes.StaticHandlerTest': 3,
    'tests.functional.test_classes.StudentAspectTest': 19,
    'tests.functional.test_classes.StudentKeyNameTest': 8,
    'tests.functional.test_classes.StudentUnifiedProfileTest': 19,
    'tests.functional.test_classes.TransformsEntitySchema': 1,
    'tests.functional.test_classes.TransformsJsonFileTestCase': 3,
    'tests.functional.test_classes.VirtualFileSystemTest': 47,
    'tests.functional.test_classes.ImportActivityTests': 7,
    'tests.functional.test_classes.ImportAssessmentTests': 3,
    'tests.functional.test_classes.ImportGiftQuestionsTests': 1,
    'tests.functional.test_classes.WSGIRoutingTest': 5,
    'tests.functional.unit_assessment.UnitPartialUpdateTests': 5,
    'tests.functional.unit_assessment.UnitPrePostAssessmentTest': 18,
    'tests.functional.unit_description.UnitDescriptionsTest': 1,
    'tests.functional.unit_header_footer.UnitHeaderFooterTest': 11,
    'tests.functional.unit_on_one_page.UnitOnOnePageTest': 4,
    'tests.functional.whitelist.WhitelistTest': 13,
    'tests.unit.etl_mapreduce.HistogramTests': 5,
    'tests.unit.etl_mapreduce.FlattenJsonTests': 4,
    'tests.unit.etl_remote.EnvironmentTests': 3,
    'tests.unit.common_catch_and_log.CatchAndLogTests': 6,
    'tests.unit.common_locales.LocalesTests': 2,
    'tests.unit.common_locales.ParseAcceptLanguageTests': 6,
    'tests.unit.common_menus.MenuTests': 6,
    'tests.unit.common_resource.ResourceKeyTests': 3,
    'tests.unit.common_schema_fields.CloneItemsNamedTests': 10,
    'tests.unit.common_schema_fields.ComplexDisplayTypeTests': 1,
    'tests.unit.common_schema_fields.DisplayTypeTests': 6,
    'tests.unit.common_schema_fields.FieldArrayTests': 3,
    'tests.unit.common_schema_fields.FieldRegistryTests': 7,
    'tests.unit.common_schema_fields.RedactEntityTests': 11,
    'tests.unit.common_schema_fields.SchemaFieldTests': 4,
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
    'tests.unit.javascript_tests.AllJavaScriptTests': 2,
    'tests.unit.models_analytics.AnalyticsTests': 6,
    'tests.unit.models_config.ValidateIntegerRangeTests': 3,
    'tests.unit.models_courses.WorkflowValidationTests': 13,
    'tests.unit.models_transforms.JsonToDictTests': 13,
    'tests.unit.models_transforms.JsonParsingTests': 3,
    'tests.unit.models_transforms.SchemaValidationTests': 21,
    'tests.unit.models_transforms.StringValueConversionTests': 2,
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
    'tests.unit.gift_parser_tests.TestCreateManyGiftQuestion': 1,
}

INTERNAL_TEST_CLASSES = {}
