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

from models import custom_modules
from models import data_sources
from modules.analytics import answers_aggregator
from modules.analytics import location_aggregator
from modules.analytics import page_event_aggregator
from modules.analytics import student_aggregate

custom_module = None


def register_module():

    def on_module_enabled():
        page_event_aggregator.register_base_course_matchers()
        student_aggregate.StudentAggregateComponentRegistry.register_component(
            location_aggregator.LocationAggregator)
        student_aggregate.StudentAggregateComponentRegistry.register_component(
            location_aggregator.LocaleAggregator)
        student_aggregate.StudentAggregateComponentRegistry.register_component(
            answers_aggregator.AnswersAggregator)
        student_aggregate.StudentAggregateComponentRegistry.register_component(
            page_event_aggregator.PageEventAggregator)
        data_sources.Registry.register(
            student_aggregate.StudentAggregateComponentRegistry)

    global custom_module  # pylint: disable=global-statement
    custom_module = custom_modules.Module(
        'Analytics', 'Data sources and dashboard analytics pages',
        [], [],
        notify_module_enabled=on_module_enabled)
    return custom_module
