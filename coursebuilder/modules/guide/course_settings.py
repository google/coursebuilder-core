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

"""Course Settings for the Guide module."""

__author__ = 'Davy Risso (davyrisso@google.com)'

from common import schema_fields
from models import courses
from modules.courses import settings

from modules.guide import messages
from modules.guide import constants

GUIDE_SETTINGS_SCHEMA_SECTION = 'modules:guide'

GUIDE_COLOR = 'color'
GUIDE_COLOR_DEFAULT_VALUE = '#00bcd4'

GUIDE_ENABLED = 'enabled'
GUIDE_ENABLED_DEFAULT_VALUE = True

GUIDE_LESSON_DURATION = 'duration'
GUIDE_LESSON_DURATION_DEFAULT_VALUE = 0


def register():
    courses.Course.OPTIONS_SCHEMA_PROVIDERS[
        GUIDE_SETTINGS_SCHEMA_SECTION] += [
            lambda _: schema_fields.SchemaField(
                GUIDE_SETTINGS_SCHEMA_SECTION + ':' + GUIDE_ENABLED,
                'Enabled', 'boolean',
                optional=True, i18n=False, editable=True,
                default_value=GUIDE_ENABLED_DEFAULT_VALUE,
                description=messages.COURSE_SETTINGS_ENABLED_DESCRIPTION),
            lambda _: schema_fields.SchemaField(
                GUIDE_SETTINGS_SCHEMA_SECTION + ':' + GUIDE_COLOR,
                'Color', 'string',
                optional=True, i18n=False, editable=True,
                default_value=GUIDE_COLOR_DEFAULT_VALUE,
                description=messages.COURSE_SETTINGS_COLOR_DESCRIPTION),
            lambda _: schema_fields.SchemaField(
                GUIDE_SETTINGS_SCHEMA_SECTION + ':' + GUIDE_LESSON_DURATION,
                'Duration', 'integer',
                optional=True, i18n=False, editable=True,
                default_value=GUIDE_LESSON_DURATION_DEFAULT_VALUE,
                description=(
                    messages.COURSE_SETTINGS_LESSON_DURATION_DESCRIPTION))
            ]

    courses.Course.OPTIONS_SCHEMA_PROVIDER_TITLES[
        GUIDE_SETTINGS_SCHEMA_SECTION] = constants.MODULE_TITLE
    settings.CourseSettingsHandler.register_settings_section(
        GUIDE_SETTINGS_SCHEMA_SECTION)

