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

"""Stats generation for the notifications module."""

__author__ = [
    'johncox@google.com (John Cox)',
]

import ast
import datetime

from common import schema_fields
from models import analytics
from models import data_sources
from models import jobs
from modules.dashboard import dashboard
from modules.notifications import notifications


class NotificationCountsGenerator(jobs.AbstractCountingMapReduceJob):

    @staticmethod
    def get_description():
        return 'notifications'

    def entity_class(self):
        return notifications.Notification

    @staticmethod
    def map(notification):
        yield (
            notifications.Status.from_notification(notification).state,
            # Treating as module-protected. pylint: disable=protected-access
            notification._enqueue_date.date().toordinal()
            ), 1


class NotificationsDataSource(
    data_sources.AbstractSmallRestDataSource,
    data_sources.SynchronousQuery):

    @classmethod
    def get_name(cls):
        return 'notifications'

    @classmethod
    def get_title(cls):
        return 'Notifications'

    @staticmethod
    def required_generators():
        return [NotificationCountsGenerator]

    @classmethod
    def get_schema(cls, app_context, log, source_context):
        ret = schema_fields.FieldRegistry('notifications')
        ret.add_property(schema_fields.SchemaField(
            'timestamp_millis', 'Millisceonds Since Epoch', 'integer'))
        ret.add_property(schema_fields.SchemaField(
            'status', 'Status', 'string'))
        ret.add_property(schema_fields.SchemaField(
            'count', 'Count', 'integer'))
        return ret.get_json_schema_dict()['properties']

    @classmethod
    def fetch_values(cls, app_context, source_context, schema, log, page_number,
                     job):
        epoch = datetime.date(year=1970, month=1, day=1)
        ret = []
        for key, count in jobs.MapReduceJob.get_results(job):
            status, date_ordinal = ast.literal_eval(key)
            date = datetime.date.fromordinal(date_ordinal)
            timestamp_millis = int((date - epoch).total_seconds()) * 1000
            ret.append({
                'timestamp_millis': timestamp_millis,
                'status': status,
                'count': count,
            })
        return ret, page_number

    @staticmethod
    def fill_values(app_context, template_values, job):
        template_values['any_notifications'] = bool(
            jobs.MapReduceJob.get_results(job))


def register_analytic():
    data_sources.Registry.register(NotificationsDataSource)
    name = 'notifications'
    title = 'Notifications'
    visualization = analytics.Visualization(
        name, title, 'stats.html',
        data_source_classes=[NotificationsDataSource])
    dashboard.DashboardHandler.add_sub_nav_mapping(
        'analytics', name, title, action='analytics_notifications',
        contents=analytics.TabRenderer([visualization]))
