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

import appengine_config

from common import schema_fields
from models import courses
from models import services
from modules.courses import settings
from modules.drive import errors
from modules.drive import messages
from modules.drive import constants


def validate_secrets(secrets):
    try:
        assert isinstance(secrets, dict)
        client_email = secrets.get('client_email')
        assert isinstance(client_email, basestring)
        assert '@' in client_email
        private_key = secrets.get('private_key')
        assert isinstance(private_key, basestring)
        assert private_key.startswith('-----BEGIN PRIVATE KEY-----\n')
        assert private_key.endswith('\n-----END PRIVATE KEY-----\n')
    except AssertionError as error:
        raise errors.Misconfigured(error)


def validate_secrets_text(text, validation_errors):
    if text:
        try:
            validate_secrets(json.loads(text))
        except (ValueError, TypeError):
            validation_errors.append(
                messages.SERVICE_ACCOUNT_JSON_PARSE_FAILURE)
        except errors.Misconfigured:
            validation_errors.append(
                messages.SERVICE_ACCOUNT_JSON_MISSING_FIELDS)


def drive_settings_schema_provider(unused_course):
    field = '{}:{}'.format(constants.MODULE_NAME,
        constants.SERVICE_ACCOUNT_JSON_FIELD_NAME)
    return schema_fields.SchemaField(
        field, 'Service Account JSON', 'text',
        description=services.help_urls.make_learn_more_message(
            messages.SERVICE_ACCOUNT_JSON_DESCRIPTION,
            'modules:{}'.format(field)),
        i18n=False, optional=True, validator=validate_secrets_text)


def make_drive_settings_section():
    settings.CourseSettingsHandler.register_settings_section(
        constants.MODULE_NAME, title=constants.MODULE_TITLE,
        schema_provider=drive_settings_schema_provider)


def get_secrets(app_context):
    try:
        secrets = json.loads(app_context.get_environ()[constants.MODULE_NAME][
            constants.SERVICE_ACCOUNT_JSON_FIELD_NAME])
        validate_secrets(secrets)
        return secrets
    except (KeyError, ValueError, TypeError):
        raise errors.NotConfigured


def get_client_email(app_context):
    # Can raise errors.NotConfigured
    if appengine_config.gcb_test_mode():
        return 'service-account@example.com'
    return get_secrets(app_context)['client_email']


def get_setting_value(app_context, constant):
    obj = app_context.get_environ()
    try:
        for segment in constant.split(':'):
            obj = obj[segment]
        return obj
    except KeyError:
        return None


def get_google_client_secret(app_context):
    return get_setting_value(
        app_context, courses.CONFIG_KEY_GOOGLE_CLIENT_SECRET)


def get_google_client_id(app_context):
    return get_setting_value(
        app_context, courses.CONFIG_KEY_GOOGLE_CLIENT_ID)


def get_google_api_key(app_context):
    return get_setting_value(
        app_context, courses.CONFIG_KEY_GOOGLE_API_KEY)


def automatic_sharing_is_available(app_context):
    return (
        get_google_client_secret(app_context) and
        get_google_client_id(app_context) and
        get_google_api_key(app_context))
