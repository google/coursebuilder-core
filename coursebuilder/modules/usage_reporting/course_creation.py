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

from common import safe_dom
from modules.admin import admin
from modules.usage_reporting import config
from modules.usage_reporting import messaging

USAGE_REPORTING_CONSENT_CHECKBOX_NAME = 'usage_reporting_consent'
USAGE_REPORTING_CONSENT_CHECKBOX_VALUE = 'accepted'


def _welcome_form_submitted(app_context, handler):
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

    checkbox = safe_dom.Element(
        'input'
    ).set_attribute(
        'type', 'checkbox'
    ).set_attribute(
        'name', USAGE_REPORTING_CONSENT_CHECKBOX_NAME
    ).set_attribute(
        'value', USAGE_REPORTING_CONSENT_CHECKBOX_VALUE
    )
    if config.REPORT_ALLOWED.value or not config.is_consent_set():
        checkbox.set_attribute('checked', 'checked')

    return safe_dom.Element(
        'div'
        ).set_attribute(
            'style', 'width: 60%; margin: 0 auto; '
        ).append(
            safe_dom.Element(
                'div'
                ).set_attribute(
                    'style', 'float: left; width: 10%; '
                ).add_child(checkbox)
        ).append(
            safe_dom.Element(
                'div'
                ).set_attribute(
                    'style', 'float: left; width: 90%; text-align: left'
                ).add_text(
                    'I agree that Google may collect information about this '
                    'deployment of Course Builder to help improve Google\'s '
                    'products and services and for research purposes.  '
                    'Google will maintain this data in acccordance with '
                ).add_child(
                    safe_dom.A(
                        'http://www.google.com/policies/privacy/'
                        ).add_text(
                            'Google\'s privacy policy'
                        )
                ).add_text(
                    ' and will not associate the data it collects with '
                    'this course or a user.  Your response to this question '
                    'will be sent to Google.'
                )
        ).append(
            safe_dom.Element(
                'div'
                ).set_attribute(
                    'style', 'clear: both; '
                )
        )


def notify_module_enabled():
    admin.WelcomeHandler.WELCOME_FORM_HOOKS.append(_make_welcome_form_content)
    admin.WelcomeHandler.POST_HOOKS.append(_welcome_form_submitted)
