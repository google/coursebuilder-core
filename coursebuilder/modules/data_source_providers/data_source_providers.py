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

"""Provide data sources of common CourseBuilder items.

If you are adding an extension module to CourseBuilder and you wish to include
a data source as part of that extension, you should add that class in the
directory specific to your module, rather than registering it here.  That way,
if your module needs to be disabled, that can be done all at once.

This module provides data sources for common CourseBuilder entites using the
framework defined in models/data_sources.  The name of this module differs
both to reflect the concrete/abstract disctintion as well as to avoid module
naming conflicts.
"""

__author__ = 'Mike Gainer (mgainer@google.com)'

from models import custom_modules
from models import data_sources
from modules.data_source_providers import rest_providers
from modules.data_source_providers import synchronous_providers

custom_module = None
MODULE_NAME = 'Data Source Providers'


def _notify_module_enabled():
    data_sources.Registry.register(synchronous_providers.QuestionStatsSource)
    data_sources.Registry.register(
        synchronous_providers.StudentEnrollmentAndScoresSource)
    data_sources.Registry.register(
        synchronous_providers.StudentProgressStatsSource)
    data_sources.Registry.register(rest_providers.AssessmentsDataSource)
    data_sources.Registry.register(rest_providers.UnitsDataSource)
    data_sources.Registry.register(rest_providers.LessonsDataSource)
    data_sources.Registry.register(
        rest_providers.StudentAssessmentScoresDataSource)
    data_sources.Registry.register(rest_providers.StudentsDataSource)
    data_sources.Registry.register(rest_providers.LabelsOnStudentsDataSource)


def _notify_module_disabled():
    raise NotImplementedError(
        'Data sources may not be un-registered; disabling this module '
        'is not supported.')


def register_module():
    global custom_module
    custom_module = custom_modules.Module(
        MODULE_NAME,
        'Implementations of specific data sources.',
        [], [], _notify_module_enabled, _notify_module_disabled)
    return custom_module
