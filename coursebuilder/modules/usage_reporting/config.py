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

"""Reporting of anonymized CourseBuilder usage statistics: configuration."""

__author__ = [
    'Michael Gainer (mgainer@google.com)',
]

import appengine_config
from common import jinja_utils
from common import safe_dom
from common import schema_fields
from common import utils as common_utils
from models import config
from models import courses
from modules.usage_reporting import messaging
from modules.usage_reporting import constants


def _on_change_report_allowed(config_property, unused_old_value):
    """Callback to report externally when value of REPORT_ALLOWED changes."""
    messaging.Message.send_instance_message(
        messaging.Message.METRIC_REPORT_ALLOWED, config_property.value,
        source=messaging.Message.ADMIN_SOURCE)


REPORT_ALLOWED = config.ConfigProperty(
    'gcb_report_usage_permitted', bool,
    safe_dom.Template(jinja_utils.get_template(
        'message.html', [constants.TEMPLATES_DIR], default_locale=None)),
    after_change=_on_change_report_allowed, default_value=False,
    label='Usage reporting')


def set_report_allowed(value):
    with common_utils.Namespace(appengine_config.DEFAULT_NAMESPACE_NAME):
        entity = config.ConfigPropertyEntity.get_by_key_name(
            REPORT_ALLOWED.name)
        if not entity:
            entity = config.ConfigPropertyEntity(key_name=REPORT_ALLOWED.name)
        entity.value = str(value)
        entity.is_draft = False
        entity.put()


def is_consent_set():
    with common_utils.Namespace(appengine_config.DEFAULT_NAMESPACE_NAME):
        return (
            config.ConfigPropertyEntity.get_by_key_name(REPORT_ALLOWED.name)
            is not None)


def notify_module_enabled():
    course_random_id = schema_fields.SchemaField(
        'course:{}'.format(messaging.USAGE_REPORTING_FIELD_ID),
        'Usage Reporting ID', 'string',
        optional=True, editable=False, i18n=False, hidden=True,
        description='When usage reporting for CourseBuilder is enabled, this '
        'string is used to identify data from this course.  The value is '
        'randomly selected when the first report is sent.')
    course_settings_fields = (
        lambda c: course_random_id,
        )
    courses.Course.OPTIONS_SCHEMA_PROVIDERS[
        courses.Course.SCHEMA_SECTION_COURSE] += course_settings_fields
