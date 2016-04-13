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

"""Support for analytics on course dashboard pages."""

__author__ = ['Michael Gainer (mgainer@google.com)']

import messages
from common import schema_fields
from models import analytics
from models import courses
from models import custom_modules
from models import data_sources
from models import data_removal
from models import models
from models import services
from modules.analytics import answers_aggregator
from modules.analytics import click_link_aggregator
from modules.analytics import clustering
from modules.analytics import gradebook
from modules.analytics import location_aggregator
from modules.analytics import page_event_aggregator
from modules.analytics import rest_providers
from modules.analytics import student_aggregate
from modules.analytics import student_answers
from modules.analytics import synchronous_providers
from modules.analytics import user_agent_aggregator
from modules.analytics import youtube_event_aggregator
from modules.dashboard import dashboard

ANALYTICS = 'analytics'

# Name for a course level setting: whether to record events for student
# interaction with course: page views, widget interactions, question answers.
CAN_RECORD_STUDENT_EVENTS = 'can_record_student_events'

custom_module = None

def register_tabs():
    multiple_choice_question = analytics.Visualization(
        'multiple_choice_question',
        'Multiple Choice Question',
        'multiple_choice_question.html',
        data_source_classes=[
            synchronous_providers.QuestionStatsSource])
    student_progress = analytics.Visualization(
        'student_progress',
        'Student Progress',
        'student_progress.html',
        data_source_classes=[
            synchronous_providers.StudentProgressStatsSource])
    enrollment_assessment = analytics.Visualization(
        'enrollment_assessment',
        'Enrollment/Assessment',
        'enrollment_assessment.html',
        data_source_classes=[
            synchronous_providers.StudentEnrollmentAndScoresSource])
    assessment_difficulty = analytics.Visualization(
        'assessment_difficulty',
        'Assessment Difficulty',
        'assessment_difficulty.html',
        data_source_classes=[
            rest_providers.StudentAssessmentScoresDataSource])
    labels_on_students = analytics.Visualization(
        'labels_on_students',
        'Students by Track',
        'labels_on_students.html',
        data_source_classes=[rest_providers.LabelsOnStudentsDataSource])
    question_answers = analytics.Visualization(
        'question_answers',
        'Question Answers',
        'question_answers.html',
        data_source_classes=[
            student_answers.QuestionAnswersDataSource,
            student_answers.CourseQuestionsDataSource,
            student_answers.CourseUnitsDataSource])
    gradebook_visualization = analytics.Visualization(
        'gradebook',
        'Gradebook',
        'gradebook.html',
        data_source_classes=[
            gradebook.RawAnswersDataSource,
            gradebook.OrderedQuestionsDataSource])
    clusters_visualization = analytics.Visualization(
        'clusters',
        'Cluster Manager',
        'clustering.html',
        data_source_classes=[clustering.ClusterDataSource])
    student_vectors_visualization = analytics.Visualization(
        'student_vectors',
        'Student Vectors',
        'student_vectors.html',
        data_source_classes=[clustering.TentpoleStudentVectorDataSource])
    stats_visualization = analytics.Visualization(
        'clustering_stats',
        'Clustering Statistics',
        'cluster_stats.html',
        data_source_classes=[clustering.ClusterStatisticsDataSource])

    dashboard.DashboardHandler.add_sub_nav_mapping(
        ANALYTICS, 'students', 'Students', action='analytics_students',
        contents=analytics.TabRenderer([
            labels_on_students,
            student_progress,
            enrollment_assessment]))
    dashboard.DashboardHandler.add_sub_nav_mapping(
        ANALYTICS, 'questions', 'Questions', action='analytics_questions',
        contents=analytics.TabRenderer([
            multiple_choice_question,
            question_answers]))
    dashboard.DashboardHandler.add_sub_nav_mapping(
        ANALYTICS, 'assessments', 'Assessments', action='analytics_assessments',
        contents=analytics.TabRenderer([assessment_difficulty]))
    dashboard.DashboardHandler.add_sub_nav_mapping(
        ANALYTICS, 'gradebook', 'Gradebook', action='analytics_gradebook',
        contents=analytics.TabRenderer([gradebook_visualization]))
    dashboard.DashboardHandler.add_sub_nav_mapping(
        ANALYTICS, 'clustering', 'Clustering', action='analytics_clustering',
        contents=analytics.TabRenderer([
            clusters_visualization,
            student_vectors_visualization,
            stats_visualization]))


def add_actions():
    def cluster_prepare_template(dashboard_instance):
        if not clustering.ClusterDataSource.any_clusterable_objects_exist(
            dashboard_instance.app_context):
            dashboard_instance.redirect(
                dashboard_instance.get_action_url('analytics_clustering'))
            return

        key = dashboard_instance.request.get('key')
        template_values = {}
        template_values['page_title'] = dashboard_instance.format_title(
            'Edit Cluster')
        template_values['main_content'] = dashboard_instance.get_form(
            clustering.ClusterRESTHandler, key,
            '/dashboard?action=analytics_clustering',
            auto_return=True, app_context=dashboard_instance.app_context)
        dashboard_instance.render_page(
            template_values, in_action='analytics_clustering')

    dashboard.DashboardHandler.add_custom_get_action(
        'add_cluster', cluster_prepare_template)
    dashboard.DashboardHandler.add_custom_get_action(
        'edit_cluster', cluster_prepare_template)


def get_namespaced_handlers():
    return [
        (clustering.ClusterRESTHandler.URI, clustering.ClusterRESTHandler),
        (gradebook.CsvDownloadHandler.URI, gradebook.CsvDownloadHandler),
        ]


def register_module():

    can_record_student_events_name = 'course:' + CAN_RECORD_STUDENT_EVENTS
    can_record_student_events = schema_fields.SchemaField(
        can_record_student_events_name, 'Enable Student Analytics',
        'boolean', i18n=False, optional=True,
        description=services.help_urls.make_learn_more_message(
            messages.ANALYTICS_ENABLE_STUDENT_DESCRIPTION,
            can_record_student_events_name))
    course_settings_fields = [
        lambda course: can_record_student_events
    ]

    def on_module_enabled():
        page_event_aggregator.register_base_course_matchers()
        student_aggregate.StudentAggregateComponentRegistry.register_component(
            location_aggregator.LocationAggregator)
        student_aggregate.StudentAggregateComponentRegistry.register_component(
            location_aggregator.LocaleAggregator)
        student_aggregate.StudentAggregateComponentRegistry.register_component(
            user_agent_aggregator.UserAgentAggregator)
        student_aggregate.StudentAggregateComponentRegistry.register_component(
            answers_aggregator.AnswersAggregator)
        student_aggregate.StudentAggregateComponentRegistry.register_component(
            page_event_aggregator.PageEventAggregator)
        student_aggregate.StudentAggregateComponentRegistry.register_component(
            youtube_event_aggregator.YouTubeEventAggregator)
        student_aggregate.StudentAggregateComponentRegistry.register_component(
            click_link_aggregator.ClickLinkAggregator)

        data_sources.Registry.register(
            student_aggregate.StudentAggregateComponentRegistry)
        data_sources.Registry.register(clustering.ClusterDataSource)
        data_sources.Registry.register(clustering.ClusterStatisticsDataSource)
        data_sources.Registry.register(
            clustering.TentpoleStudentVectorDataSource)
        data_sources.Registry.register(
            student_answers.QuestionAnswersDataSource)
        data_sources.Registry.register(
            student_answers.CourseQuestionsDataSource)
        data_sources.Registry.register(student_answers.CourseUnitsDataSource)
        data_sources.Registry.register(gradebook.AnswersDataSource)
        data_sources.Registry.register(gradebook.RawAnswersDataSource)
        data_sources.Registry.register(gradebook.OrderedQuestionsDataSource)

        data_sources.Registry.register(
            synchronous_providers.QuestionStatsSource)
        data_sources.Registry.register(
            synchronous_providers.StudentEnrollmentAndScoresSource)
        data_sources.Registry.register(
            synchronous_providers.StudentProgressStatsSource)
        data_sources.Registry.register(rest_providers.AssessmentsDataSource)
        data_sources.Registry.register(rest_providers.UnitsDataSource)
        data_sources.Registry.register(rest_providers.LessonsDataSource)
        data_sources.Registry.register(
            rest_providers.StudentAssessmentScoresDataSource)
        data_sources.Registry.register(rest_providers.LabelsDataSource)
        data_sources.Registry.register(rest_providers.StudentsDataSource)
        data_sources.Registry.register(
            rest_providers.LabelsOnStudentsDataSource)

        data_removal.Registry.register_indexed_by_user_id_remover(
            clustering.StudentVector.delete_by_key)
        data_removal.Registry.register_indexed_by_user_id_remover(
            clustering.StudentClusters.delete_by_key)
        data_removal.Registry.register_indexed_by_user_id_remover(
            student_aggregate.StudentAggregateEntity.delete_by_key)
        data_removal.Registry.register_indexed_by_user_id_remover(
            gradebook.QuestionAnswersEntity.delete_by_primary_id)

        courses.Course.OPTIONS_SCHEMA_PROVIDERS[
            courses.Course.SCHEMA_SECTION_COURSE] += course_settings_fields

        models.StudentLifecycleObserver.EVENT_CALLBACKS[
            models.StudentLifecycleObserver.EVENT_ADD][ANALYTICS] = (
                rest_providers.AdditionalFieldNamesDAO.user_added_callback)

        register_tabs()
        add_actions()

    global custom_module  # pylint: disable=global-statement
    custom_module = custom_modules.Module(
        'Analytics', 'Data sources and dashboard analytics pages',
        [], get_namespaced_handlers(),
        notify_module_enabled=on_module_enabled)
    return custom_module
