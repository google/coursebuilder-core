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

"""Setup for tests exercising visualization displays."""

__author__ = 'Mike Gainer (mgainer@google.com)'

from common import schema_fields
from controllers import utils
from models import analytics
from models import custom_modules
from models import data_sources
from modules.dashboard import dashboard


class FakeDataSource(data_sources.AbstractRestDataSource):

    _exception = None
    _log_critical = None
    _page_number = None

    @classmethod
    def get_context_class(cls):
        return data_sources.DbTableContext

    @classmethod
    def get_schema(cls, *args, **kwargs):
        reg = schema_fields.FieldRegistry(
            'Bogus', description='bogus')
        reg.add_property(schema_fields.SchemaField(
            'bogus', 'Bogus', 'integer', description='Fake schema'))
        return reg.get_json_schema_dict()['properties']

    @classmethod
    def set_fetch_values_page_number(cls, page_number=None):
        """For testing.  Force fetch_values to return a specific page number."""
        cls._page_number = page_number

    @classmethod
    def set_fetch_values_exception(cls):
        """For testing.  Force fetch_values to raise an exception."""
        cls._exception = True

    @classmethod
    def set_fetch_values_log_critical(cls):
        """For testing.  Force fetch_values to log an error message."""
        cls._log_critical = True

    @classmethod
    def fetch_values(cls, _app_context, _source_context, _schema, log,
                     page_number):
        if cls._exception:
            cls._exception = None
            raise ValueError('Error for testing')

        if cls._log_critical:
            cls._log_critical = None
            log.critical('Error for testing')

        if cls._page_number is not None:
            if cls._page_number != page_number:
                log.warning('Stopping at last page %d' % cls._page_number)
            page_number = cls._page_number
            cls._page_number = None

        return [
            {'name': 'Snoopy', 'score': 10, 'page_number': page_number},
            {'name': 'Linus', 'score': 8},
            {'name': 'Lucy', 'score': 3},
            {'name': 'Schroeder', 'score': 5},
            ], page_number


class ExamsDataSource(FakeDataSource):

    @classmethod
    def get_name(cls):
        return 'exams'

    @classmethod
    def get_title(cls):
        return 'Exams'

    @classmethod
    def get_default_chunk_size(cls):
        return 0  # Not paginated


class PupilsDataSource(FakeDataSource):

    @classmethod
    def get_name(cls):
        return 'pupils'

    @classmethod
    def get_title(cls):
        return 'Pupils'


class AnswersDataSource(FakeDataSource):

    @classmethod
    def get_name(cls):
        return 'fake_answers'

    @classmethod
    def get_title(cls):
        return 'Fake Answers'


class ForceResponseHandler(utils.ApplicationHandler):
    """REST service to allow tests to affect the behavior of FakeDataSource."""

    URL = '/fake_data_source_response'

    PARAM_DATA_SOURCE = 'data_source'
    PARAM_ACTION = 'action'
    PARAM_PAGE_NUMBER = 'page_number'

    ACTION_PAGE_NUMBER = 'page_number'
    ACTION_LOG_CRITICAL = 'log_critical'
    ACTION_EXCEPTION = 'exception'

    def post(self):
        data_source_classes = {
            'exams': ExamsDataSource,
            'pupils': PupilsDataSource,
            'fake_answers': AnswersDataSource,
        }

        data_source = data_source_classes[
            self.request.get(ForceResponseHandler.PARAM_DATA_SOURCE)]
        action = self.request.get(ForceResponseHandler.PARAM_ACTION)
        if action == ForceResponseHandler.ACTION_PAGE_NUMBER:
            data_source.set_fetch_values_page_number(
                int(self.request.get(ForceResponseHandler.PARAM_PAGE_NUMBER)))
        elif action == ForceResponseHandler.ACTION_LOG_CRITICAL:
            data_source.set_fetch_values_log_critical()
        elif action == ForceResponseHandler.ACTION_EXCEPTION:
            data_source.set_fetch_values_exception()
        else:
            self.response.set_status(400)
            self.response.write('Malformed Request')
            return


def register_on_enable():
    data_sources.Registry.register(ExamsDataSource)
    data_sources.Registry.register(PupilsDataSource)
    data_sources.Registry.register(AnswersDataSource)

    exams = analytics.Visualization(
        'exams', 'Exams', 'fake_visualizations.html',
        [ExamsDataSource])
    pupils = analytics.Visualization(
        'pupils', 'Pupils', 'fake_visualizations.html',
        [PupilsDataSource])
    scoring = analytics.Visualization(
        'scoring', 'Scoring', 'fake_visualizations.html',
        [ExamsDataSource, PupilsDataSource, AnswersDataSource])

    dashboard.DashboardHandler.add_sub_nav_mapping(
        'analytics', 'exams', 'Exams', action='analytics_exams',
        contents=analytics.TabRenderer([exams]))
    dashboard.DashboardHandler.add_sub_nav_mapping(
        'analytics', 'pupils', 'Pupils', action='analytics_pupils',
        contents=analytics.TabRenderer([pupils]))
    dashboard.DashboardHandler.add_sub_nav_mapping(
        'analytics', 'scoring', 'Scoring', action='analytics_scoring',
        contents=analytics.TabRenderer([scoring]))


def register_module():
    """Dynamically registered module providing fake analytics for testing."""

    namespaced_handlers = [(ForceResponseHandler.URL, ForceResponseHandler)]
    return custom_modules.Module(
        'FakeVisualizations', 'Provide visualizations requiring simple, '
        'paginated, and multiple data streams for testing.',
        [], namespaced_handlers, register_on_enable, None)
