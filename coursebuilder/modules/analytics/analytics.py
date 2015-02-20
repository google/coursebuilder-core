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

from models import analytics
from models import custom_modules
from models import data_sources
from modules.analytics import answers_aggregator
from modules.analytics import clustering
from modules.analytics import location_aggregator
from modules.analytics import page_event_aggregator
from modules.analytics import student_aggregate
from modules.analytics import user_agent_aggregator
from modules.analytics import youtube_event_aggregator
from modules.dashboard import tabs
from modules.dashboard.dashboard import DashboardHandler

custom_module = None


def register_tabs():
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

    tabs.Registry.register('analytics', 'clustering', 'Clustering',
                           [clusters_visualization,
                            student_vectors_visualization,
                            stats_visualization])


def add_actions():
    def cluster_prepare_template(dashboard_instance):
        key = dashboard_instance.request.get('key')
        template_values = {}
        template_values['page_title'] = dashboard_instance.format_title(
            'Edit Cluster')
        template_values['main_content'] = dashboard_instance.get_form(
            clustering.ClusterRESTHandler, key,
            '/dashboard?action=analytics&tab=clustering',
            auto_return=True, app_context=dashboard_instance.app_context)
        dashboard_instance.render_page(template_values, 'clusters')

    DashboardHandler.add_custom_get_action('add_cluster',
                                           cluster_prepare_template)
    DashboardHandler.add_custom_get_action('edit_cluster',
                                           cluster_prepare_template)


def get_namespaced_handlers():
    return [(clustering.ClusterRESTHandler.URI, clustering.ClusterRESTHandler)]


def register_module():

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
        data_sources.Registry.register(
            student_aggregate.StudentAggregateComponentRegistry)
        data_sources.Registry.register(clustering.ClusterDataSource)
        data_sources.Registry.register(clustering.ClusterStatisticsDataSource)
        data_sources.Registry.register(
            clustering.TentpoleStudentVectorDataSource)
        register_tabs()
        add_actions()

    global custom_module  # pylint: disable=global-statement
    custom_module = custom_modules.Module(
        'Analytics', 'Data sources and dashboard analytics pages',
        [], get_namespaced_handlers(),
        notify_module_enabled=on_module_enabled)
    return custom_module
