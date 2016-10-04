# Copyright 2016 Google Inc. All Rights Reserved.
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

from models import courses
from common import schema_fields
from modules.explorer import constants
from modules.explorer import messages


def register():
    courses.Course.OPTIONS_SCHEMA_PROVIDERS[
        courses.Course.SCHEMA_SECTION_COURSE] += [
            lambda _: schema_fields.SchemaField(
                'course:estimated_workload', 'Estimated Workload', 'string',
                description=messages.COURSE_ESTIMATED_WORKLOAD_DESCRIPTION,
                optional=True, i18n=False,
            ),
            lambda _: schema_fields.SchemaField(
                'course:category_name', 'Category', 'string',
                description=messages.COURSE_CATEGORY_DESCRIPTION,
                optional=True, i18n=False,
            ),
            lambda _: schema_fields.SchemaField(
                'course:' + constants.SHOW_IN_EXPLORER, 'Show in Explorer',
                'boolean',
                description=messages.COURSE_INCLUDE_IN_EXPLORER_DESCRIPTION,
                optional=True, i18n=False, default_value=True,
            ),
        ]
