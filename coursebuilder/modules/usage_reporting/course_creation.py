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

"""Reporting of anonymized CourseBuilder usage statistics: welcome page."""

__author__ = [
    'Michael Gainer (mgainer@google.com)',
]

import jinja2

from common import jinja_utils
from modules.admin import admin
from modules.usage_reporting import config
from modules.usage_reporting import messaging
from modules.usage_reporting import constants

USAGE_REPORTING_CONSENT_CHECKBOX_NAME = 'usage_reporting_consent'
USAGE_REPORTING_CONSENT_CHECKBOX_VALUE = 'accepted'


def _welcome_form_submitted(handler):
    """Note value of reporting consent checkbox submitted with Welcome form."""

    consent_val = handler.request.get(USAGE_REPORTING_CONSENT_CHECKBOX_NAME)
    is_allowed = (consent_val == USAGE_REPORTING_CONSENT_CHECKBOX_VALUE)
    config.set_report_allowed(is_allowed)
    messaging.Message.send_instance_message(
        messaging.Message.METRIC_REPORT_ALLOWED, is_allowed,
        source=messaging.Message.WELCOME_SOURCE)


def _make_welcome_form_content():
    """Add content to welcome page to get user's consent for stat collection."""
    if messaging.is_disabled():
        return None

    checked = config.REPORT_ALLOWED.value or not config.is_consent_set()

    return jinja2.Markup(
        jinja_utils.get_template(
            'course_creation.html', [constants.TEMPLATES_DIR]).render(
        name=USAGE_REPORTING_CONSENT_CHECKBOX_NAME,
        value=USAGE_REPORTING_CONSENT_CHECKBOX_VALUE,
        checked=checked))


def notify_module_enabled():
    admin.WelcomeHandler.WELCOME_FORM_HOOKS.append(_make_welcome_form_content)
    admin.WelcomeHandler.POST_HOOKS.append(_welcome_form_submitted)
