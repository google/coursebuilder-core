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

"""Defines the course-wide settings page for Drive."""

__author__ = [
    'nretallack@google.com (Nick Retallack)',
]

import json

from common import schema_fields
from modules.courses import settings
from modules.drive import errors
from modules.drive import messages
from modules.drive import constants
from modules.drive import drive_api_client


def validate_secrets_text(text, validation_errors):
    if text:
        try:
            drive_api_client.validate_secrets(json.loads(text))
        except (ValueError, TypeError):
            validation_errors.append(messages.DRIVE_SECRET_JSON_PARSE_FAILURE)
        except errors.Misconfigured:
            validation_errors.append(messages.DRIVE_SECRET_MISSING_FIELDS)


def drive_settings_schema_provider(unused_course):
    return schema_fields.SchemaField(
        '{}:{}'.format(constants.MODULE_NAME,
        constants.SERVICE_ACCOUNT_JSON_FIELD_NAME),
        'Service Account JSON', 'text',
        description=messages.SERVICE_ACCOUNT_JSON_DESCRIPTION,
        i18n=False, optional=True, validator=validate_secrets_text)


def make_drive_settings_section():
    settings.CourseSettingsHandler.register_settings_section(
        constants.MODULE_NAME, title=constants.MODULE_TITLE,
        schema_provider=drive_settings_schema_provider)


def get_secrets(app_context):
    try:
        return json.loads(app_context.get_environ().get(
            constants.MODULE_NAME, {}).get(
            constants.SERVICE_ACCOUNT_JSON_FIELD_NAME))
    except (KeyError, ValueError, TypeError):
        raise errors.NotConfigured
