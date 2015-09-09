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

import datetime

from models import analytics
from models import data_sources
from models import jobs
from modules.dashboard import dashboard
from modules.notifications import notifications


_SERIALIZED_DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S.%f'


class _Result(object):

    # Treating as module-protected. pylint: disable=protected-access

    def __init__(self, now):
        self.now = now
        self.last_day = _Bin('day', self.now - datetime.timedelta(days=1))
        self.last_hour = _Bin('hour', self.now - datetime.timedelta(hours=1))
        self.last_week = _Bin('week', self.now - datetime.timedelta(days=7))
        self.bins = [self.last_hour, self.last_day, self.last_week]
        self._totals = {'all': 0}
        self._totals.update(
            {state: 0 for state in notifications.Status._STATES})

    def add(self, state, dt):
        # Datastore values may no longer be found in code; silently
        # discard if so.
        if state in notifications.Status._STATES:
            self._totals['all'] += 1
            self._totals[state] += 1
            for selected in self.bins:
                if dt > selected.cutoff:
                    selected.add(state)

    def failed(self):
        return self._totals[notifications.Status.FAILED]

    def pending(self):
        return self._totals[notifications.Status.PENDING]

    def succeeded(self):
        return self._totals[notifications.Status.SUCCEEDED]

    def total(self):
        return self._totals['all']


class _Bin(object):

    def __init__(self, name, cutoff):
        # Treating as module-protected. pylint: disable=protected-access
        self._data = {state: 0 for state in notifications.Status._STATES}
        self.cutoff = cutoff
        self.name = name

    def add(self, state):
        self._data[state] += 1

    def failed(self):
        return self._data[notifications.Status.FAILED]

    def pending(self):
        return self._data[notifications.Status.PENDING]

    def succeeded(self):
        return self._data[notifications.Status.SUCCEEDED]

    def total(self):
        return sum(self._data.values())


class CountsGenerator(jobs.MapReduceJob):

    @staticmethod
    def get_description():
        return 'notification'

    def entity_class(self):
        return notifications.Notification

    @staticmethod
    def map(notification):
        yield (
            notifications.Status.from_notification(notification).state,
            # Treating as module-protected. pylint: disable=protected-access
            notification._enqueue_date
            )

    @staticmethod
    def reduce(key, values):
        yield key, values


class NotificationsDataSource(data_sources.SynchronousQuery):

    @staticmethod
    def fill_values(app_context, template_values, job):
        now = datetime.datetime.utcnow()
        result = _Result(now)

        for state_name, create_dates in jobs.MapReduceJob.get_results(job):
            for create_date in create_dates:
                result.add(
                    state_name, datetime.datetime.strptime(
                        create_date, _SERIALIZED_DATETIME_FORMAT))

        template_values.update({'result': result})

    @staticmethod
    def required_generators():
        return [CountsGenerator]


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
