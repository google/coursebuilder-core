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

"""Tests for modules/courses/."""

__author__ = 'Mike Gainer (mgainer@google.com)'

import datetime
import time

import apiclient
from common import catch_and_log
from common import schema_fields
from common import utils as common_utils
from models import courses
from models import data_sources
from models import jobs
from models import models
from models import transforms
from modules.data_pump import data_pump
from modules.analytics import rest_providers
from tests.functional import actions

from google.appengine.ext import deferred

COURSE_NAME = 'data_pump'
ADMIN_EMAIL = 'admin@foo.com'
USER_EMAIL = 'user@foo.com'
USER_NAME = 'Some User'

# pylint: disable=protected-access


class TrivialDataSource(data_sources.AbstractRestDataSource):

    @classmethod
    def get_name(cls):
        return 'trivial_data_source'

    @classmethod
    def get_title(cls):
        return 'Trivial Data Source'

    @classmethod
    def exportable(cls):
        return True

    @classmethod
    def get_schema(cls, unused_app_context, unused_log, data_source_context):
        reg = schema_fields.FieldRegistry('Trivial')
        reg.add_property(schema_fields.SchemaField(
            'thing', 'Thing', 'integer',
            description='stuff'))
        if data_source_context.send_uncensored_pii_data:
            reg.add_property(schema_fields.SchemaField(
                'ssn', 'SSN', 'string',
                description='Social Security Number'))
        return reg.get_json_schema_dict()['properties']

    @classmethod
    def get_default_chunk_size(cls):
        return 3

    @classmethod
    def get_context_class(cls):
        return TrivialDataSourceContext

    @classmethod
    def _make_item(cls, value, source_context):
        item = {'thing': value}
        if source_context.send_uncensored_pii_data:
            ssn = '%d%d%d-%d%d-%d%d%d%d' % ([value] * 9)
        return item

    @classmethod
    def fetch_values(cls, app_context, source_context, schema, log, page):
        if page in (0, 1, 2):
            ret = []
            for count in range(0, 3):
                ret.append(cls._make_item(page * 3 + count, source_context))
            return ret, page
        else:
            return [cls._make_item(9, source_context)], 3


class TrivialDataSourceContext(data_sources.AbstractContextManager):

    def __init__(self):
        self.chunk_size = 3
        self.send_uncensored_pii_data = False

    @classmethod
    def build_from_web_request(cls, *unused_args, **unused_kwargs):
        return TrivialDataSourceContext()

    @classmethod
    def build_from_dict(cls, context_dict):
        return TrivialDataSourceContext()

    @classmethod
    def build_blank_default(cls, *unused_args, **unused_kwargs):
        return TrivialDataSourceContext()

    @classmethod
    def save_to_dict(cls, context):
        return {'chunk_size': 3}

    @classmethod
    def get_public_params_for_display(cls, context):
        return {'chunk_size': 3}

    @classmethod
    def equivalent(cls, a, b):
        return True

    @classmethod
    def _build_secret(cls, params):
        return None


class ComplexDataSource(data_sources.AbstractRestDataSource):

    @classmethod
    def get_name(cls):
        return 'complex_data_source'

    @classmethod
    def get_title(cls):
        return 'Complex Data Source'

    @classmethod
    def exportable(cls):
        return True

    @classmethod
    def get_schema(cls, unused_app_context, unused_log, data_source_context):
        ret = schema_fields.FieldRegistry('Complex')

        # Directly contained scalars.
        ret.add_property(schema_fields.SchemaField(
            'an_int', 'An Integer', 'integer', description='integer desc'))
        ret.add_property(schema_fields.SchemaField(
            'a_string', 'A String', 'string', description='string desc'))

        # Array of complex type
        array_subtype = schema_fields.FieldRegistry('Array Subtype')
        array_subtype.add_property(schema_fields.SchemaField(
            'sub_int', 'Sub Integer', 'integer', description='sub int desc'))
        array_subtype.add_property(schema_fields.SchemaField(
            'sub_str', 'Sub String', 'string', description='sub str desc'))
        ret.add_property(schema_fields.FieldArray(
            'sub_array', 'Sub Array', description='sub arr desc',
            item_type=array_subtype))

        # Array of scalar type.
        ret.add_property(schema_fields.FieldArray(
            'scalar_array', 'Scalar Array', description='scalar arr desc',
            item_type=schema_fields.SchemaField(
                'arr_int', 'Array Integer', 'integer', description='arr int')))

        # Sub object.  Contains scalars and an array of scalar.
        sub_obj_type = schema_fields.FieldRegistry('Sub-Object')
        sub_obj_type.add_property(schema_fields.SchemaField(
            'sub_date', 'Sub Date', 'datetime', description='sub date desc'))
        sub_obj_type.add_property(schema_fields.SchemaField(
            'sub_bool', 'Sub Boolean', 'bool', description='sub bool desc'))
        sub_obj_type.add_property(schema_fields.FieldArray(
            'sub_obj_array', 'Sub Obj Array', description='subobj array desc',
            item_type=schema_fields.SchemaField(
                'arr_text', 'Array Text', 'text', description='arr text desc')))
        ret.add_sub_registry('sub_registry', registry=sub_obj_type)
        return ret.get_json_schema_dict()['properties']

    @classmethod
    def get_default_chunk_size(cls):
        return 0

    @classmethod
    def get_context_class(cls):
        return TrivialDataSourceContext

    @classmethod
    def fetch_values(cls, app_context, source_context, schema, log, page):
        return []


class StudentSchemaValidationTests(actions.TestBase):
    """Verify that Student schema (with/without PII) is correctly validated."""

    def setUp(self):
        super(StudentSchemaValidationTests, self).setUp()
        self.app_context = actions.simple_add_course(
            COURSE_NAME, ADMIN_EMAIL, 'Data pump')
        actions.login(USER_EMAIL, is_admin=False)
        actions.register(self, USER_NAME, COURSE_NAME)
        actions.login(ADMIN_EMAIL, is_admin=True)

    def _build_student_fetch_params(self, with_pii):
        ctx_class = rest_providers.StudentsDataSource.get_context_class()
        data_source_context = ctx_class.build_blank_default(
            params={'data_source_token': 'xyzzy'},
            default_chunk_size=1)
        data_source_context.send_uncensored_pii_data = with_pii
        catch_and_log_ = catch_and_log.CatchAndLog()
        schema = rest_providers.StudentsDataSource.get_schema(
            self.app_context, catch_and_log_, data_source_context)
        return data_source_context, schema, catch_and_log_

    def _test_student_schema(self, with_pii):
        source_ctx, schema, log_ = self._build_student_fetch_params(with_pii)
        values, _ = rest_providers.StudentsDataSource.fetch_values(
            self.app_context, source_ctx, schema, log_, 0)
        self.assertEquals(1, len(values))
        complaints = transforms.validate_object_matches_json_schema(
            values[0], schema)
        self.assertEquals(0, len(complaints))

    def test_student_schema_without_pii(self):
        self._test_student_schema(with_pii=False)

    def test_student_schema_including_pii(self):
        self._test_student_schema(with_pii=True)


class SchemaConversionTests(actions.TestBase):

    def setUp(self):
        super(SchemaConversionTests, self).setUp()
        actions.login(ADMIN_EMAIL, is_admin=True)
        self.app_context = actions.simple_add_course(
            COURSE_NAME, ADMIN_EMAIL, 'Data pump')
        data_sources.Registry.register(TrivialDataSource)
        self.job = data_pump.DataPumpJob(self.app_context,
                                         TrivialDataSource.__name__)

    def tearDown(self):
        data_sources.Registry.unregister(TrivialDataSource)

    def test_complex_conversion(self):
        reg = schema_fields.FieldRegistry('Complex')
        reg.add_property(schema_fields.SchemaField(
            'an_integer', 'An Integer', 'integer',
            optional=True, description='an integer'))
        reg.add_property(schema_fields.SchemaField(
            'a_string', 'A String', 'string', description='a string'))
        reg.add_property(schema_fields.SchemaField(
            'some text', 'Some Text', 'text', description='some text'))
        reg.add_property(schema_fields.SchemaField(
            'some html', 'Some HTML', 'html', description='some html'))
        reg.add_property(schema_fields.SchemaField(
            'a url', 'A URL', 'url', description='a url'))
        reg.add_property(schema_fields.SchemaField(
            'a file', 'A File', 'file', description='a file'))
        reg.add_property(schema_fields.SchemaField(
            'a number', 'A Number', 'number', description='a number'))
        reg.add_property(schema_fields.SchemaField(
            'a boolean', 'A Boolean', 'boolean', description='a boolean'))
        reg.add_property(schema_fields.SchemaField(
            'a date', 'A Date', 'date', description='a date'))
        reg.add_property(schema_fields.SchemaField(
            'a datetime', 'A DateTime', 'datetime', description='a datetime'))

        sub_registry = schema_fields.FieldRegistry('subregistry')
        sub_registry.add_property(schema_fields.SchemaField(
            'name', 'Name', 'string', description='user name'))
        sub_registry.add_property(schema_fields.SchemaField(
            'city', 'City', 'string', description='city name'))
        reg.add_sub_registry('sub_registry', title='Sub Registry',
                             description='a sub-registry',
                             registry=sub_registry)

        reg.add_property(schema_fields.FieldArray(
            'simple_array', 'Simple Array', description='a simple array',
            item_type=schema_fields.SchemaField(
                'array_int', 'Array Int', 'integer', description='array int')))

        complex_array_type = schema_fields.FieldRegistry('complex_array_type')
        complex_array_type.add_property(schema_fields.SchemaField(
            'this', 'This', 'string', description='the this'))
        complex_array_type.add_property(schema_fields.SchemaField(
            'that', 'That', 'number', description='the that'))
        complex_array_type.add_property(schema_fields.SchemaField(
            'these', 'These', 'datetime', description='the these'))
        reg.add_property(schema_fields.FieldArray(
            'complex_array', 'Complex Array', description='complex array',
            item_type=complex_array_type))
        actual_schema = self.job._json_schema_to_bigquery_schema(
            reg.get_json_schema_dict()['properties'])

        expected_schema = [
            {'mode': 'NULLABLE',
             'type': 'INTEGER',
             'name': 'an_integer',
             'description': 'an integer'},
            {'mode': 'REQUIRED',
             'type': 'STRING',
             'name': 'a_string',
             'description': 'a string'},
            {'mode': 'REQUIRED',
             'type': 'STRING',
             'name': 'some text',
             'description': 'some text'},
            {'mode': 'REQUIRED',
             'type': 'STRING',
             'name': 'some html',
             'description': 'some html'},
            {'mode': 'REQUIRED',
             'type': 'STRING',
             'name': 'a url',
             'description': 'a url'},
            {'mode': 'REQUIRED',
             'type': 'STRING',
             'name': 'a file',
             'description': 'a file'},
            {'mode': 'REQUIRED',
             'type': 'FLOAT',
             'name': 'a number',
             'description': 'a number'},
            {'mode': 'REQUIRED',
             'type': 'BOOLEAN',
             'name': 'a boolean',
             'description': 'a boolean'},
            {'mode': 'REQUIRED',
             'type': 'TIMESTAMP',
             'name': 'a date',
             'description': 'a date'},
            {'mode': 'REQUIRED',
             'type': 'TIMESTAMP',
             'name': 'a datetime',
             'description': 'a datetime'},
            {'mode': 'REPEATED',
             'type': 'INTEGER',
             'name': 'simple_array',
             'description': 'array int'},
            {'fields': [
                {'mode': 'REQUIRED',
                 'type': 'STRING',
                 'name': 'this',
                 'description': 'the this'},
                {'mode': 'REQUIRED',
                 'type': 'FLOAT',
                 'name': 'that',
                 'description': 'the that'},
                {'mode': 'REQUIRED',
                 'type': 'TIMESTAMP',
                 'name': 'these',
                 'description': 'the these'}],
             'type': 'RECORD',
             'name': 'complex_array',
             'mode': 'REPEATED'},
            {'fields': [
                {'mode': 'REQUIRED',
                 'type': 'STRING',
                 'name': 'name',
                 'description': 'user name'},
                {'mode': 'REQUIRED',
                 'type': 'STRING',
                 'name': 'city',
                 'description': 'city name'}],
             'type': 'RECORD',
             'name': 'sub_registry',
             'mode': 'NULLABLE'}
            ]
        self.assertEqual(expected_schema, actual_schema)


class PiiTests(actions.TestBase):

    def setUp(self):
        super(PiiTests, self).setUp()
        actions.login(ADMIN_EMAIL, is_admin=True)
        self.app_context = actions.simple_add_course(
            COURSE_NAME, ADMIN_EMAIL, 'Data pump')
        data_sources.Registry.register(TrivialDataSource)
        self.job = data_pump.DataPumpJob(self.app_context,
                                         TrivialDataSource.__name__)

    def tearDown(self):
        data_sources.Registry.unregister(TrivialDataSource)

    def test_cannot_push_unregistered_class(self):
        class NotRegistered(data_sources.AbstractSmallRestDataSource):
            pass
        with self.assertRaises(ValueError):
            data_pump.DataPumpJob(self.app_context, NotRegistered.__name__)

    def test_cannot_push_unexportable_class(self):
        """Ensure classes not marked as exportable cannot be exported.

        Verify that this is enforced deeper in the code than simply not
        displaying visual UI elements on a web page, so that we are certain
        that feeds with PII (RawQuestionAnswers, I'm looking at you)
        are suppressed for export.
        """

        class NotExportable(data_sources.AbstractSmallRestDataSource):

            @classmethod
            def get_name(cls):
                return 'not_exportable'

        data_sources.Registry.register(NotExportable)
        with self.assertRaises(ValueError):
            data_pump.DataPumpJob(self.app_context, NotExportable.__name__)
        data_sources.Registry.unregister(NotExportable)

    def test_get_pii_secret_with_blank_settings(self):
        secret, end_date = data_pump.DataPumpJob._parse_pii_encryption_token(
            data_pump.DataPumpJob._get_pii_token(self.app_context))
        self.assertEqual(len(secret), data_pump.PII_SECRET_LENGTH)
        expected_end_date = (
            datetime.datetime.now() + common_utils.parse_timedelta_string(
                data_pump.PII_SECRET_DEFAULT_LIFETIME))
        unix_epoch = datetime.datetime(year=1970, month=1, day=1)
        expected_sec = (expected_end_date - unix_epoch).total_seconds()
        actual_sec = (end_date - unix_epoch).total_seconds()
        self.assertLessEqual(expected_sec - actual_sec, 2.0)

    def test_pii_secret_expiration(self):
        token = data_pump.DataPumpJob._build_new_pii_encryption_token('1s')
        self.assertTrue(
            data_pump.DataPumpJob._is_pii_encryption_token_valid(token))
        time.sleep(1)
        self.assertFalse(
            data_pump.DataPumpJob._is_pii_encryption_token_valid(token))

    def test_course_settings_used(self):
        course_settings = self.app_context.get_environ()
        pump_settings = {}
        course_settings[data_pump.DATA_PUMP_SETTINGS_SCHEMA_SECTION] = (
            pump_settings)
        pump_settings[data_pump.TABLE_LIFETIME] = '2 s'
        course = courses.Course(None, app_context=self.app_context)
        course.save_settings(course_settings)

        old_token = data_pump.DataPumpJob._get_pii_token(self.app_context)
        time.sleep(2)
        new_token = data_pump.DataPumpJob._get_pii_token(self.app_context)
        self.assertNotEqual(old_token, new_token)
        self.assertFalse(data_pump.DataPumpJob._is_pii_encryption_token_valid(
            old_token))
        self.assertTrue(data_pump.DataPumpJob._is_pii_encryption_token_valid(
            new_token))

    def _get_student_data(self, send_uncensored_pii_data):
        with common_utils.Namespace('ns_' + COURSE_NAME):
            job = data_pump.DataPumpJob(
                self.app_context, rest_providers.StudentsDataSource.__name__)
            data_source_context = job._build_data_source_context()
            data_source_context.pii_secret = job._get_pii_secret(
                self.app_context)
            data_source_context.send_uncensored_pii_data = (
                send_uncensored_pii_data)
            data, is_last_page = job._fetch_page_data(self.app_context,
                                                      data_source_context, 0)
        self.assertTrue(is_last_page)
        self.assertEqual(len(data), 1)
        return data[0]

    def test_student_pii_data_obscured(self):
        user = actions.login(USER_EMAIL)
        actions.register(self, USER_EMAIL, COURSE_NAME)
        actions.logout()

        actions.login(ADMIN_EMAIL)
        student_record = self._get_student_data(send_uncensored_pii_data=False)
        with common_utils.Namespace('ns_' + COURSE_NAME):
            student = models.Student.get_by_user(user)
            self.assertIsNotNone(student.user_id)
            self.assertIsNotNone(student_record['user_id'])
            self.assertNotEqual(student.user_id, student_record['user_id'])
            self.assertNotIn('email', student_record)
            self.assertNotIn('name', student_record)
            self.assertNotIn('additional_fields', student_record)

    def test_student_pii_data_sent_when_commanded(self):
        user = actions.login(USER_EMAIL)
        actions.register(self, USER_EMAIL, COURSE_NAME)
        actions.logout()

        actions.login(ADMIN_EMAIL)
        student_record = self._get_student_data(send_uncensored_pii_data=True)
        with common_utils.Namespace('ns_' + COURSE_NAME):
            student = models.Student.get_by_user(user)
            self.assertIsNotNone(student.user_id)
            self.assertIsNotNone(student_record['user_id'])
            self.assertEqual(student.user_id, student_record['user_id'])
            self.assertEqual(student.email, student_record['email'])
            self.assertEquals('user@foo.com', student_record['name'])
            self.assertEquals(
              'user@foo.com',
              common_utils.find(lambda x: x['name'] == 'form01',
                                student_record['additional_fields'])['value'])

    def _setup_for_additional_fields(self):
        user_name = 'John Smith, from back East'
        user_phone = '1.212.555.1212'
        user_ssn = '123-45-6789'

        environ = {
            'reg_form': {
                'additional_registration_fields': (
                    '\'<!-- reg_form.additional_registration_fields -->'
                    '<input name="form02" type="text">'
                    '<input name="form03" type="text">')
            }
        }
        with actions.OverriddenEnvironment(environ):
            user = actions.login(USER_EMAIL)
            self.base = '/' + COURSE_NAME
            actions.register_with_additional_fields(
                self, user_name, user_phone, user_ssn)

        # Additional fields propagate and list of add'l fields is updated in DB.
        self.execute_all_deferred_tasks(
            models.StudentLifecycleObserver.QUEUE_NAME)
        return user

    def test_additional_fields_as_columns(self):
        user = self._setup_for_additional_fields()
        actions.login(ADMIN_EMAIL)
        student_record = self._get_student_data(send_uncensored_pii_data=True)
        self.assertEquals(
            student_record['registration_fields']['form01'],
            'John Smith, from back East')
        self.assertEquals(
            student_record['registration_fields']['form02'], '1.212.555.1212')
        self.assertEquals(
            student_record['registration_fields']['form03'], '123-45-6789')

    def test_additional_fields_mismatch_known_fields(self):
        user = self._setup_for_additional_fields()
        with common_utils.Namespace('ns_' + COURSE_NAME):
            student = models.Student.get_by_user(user)
            student.additional_fields = transforms.dumps(
                [['form02', '1.212.555.1212'],
                 ['unknown_field', 'unknown_value']])
            student.put()

        actions.login(ADMIN_EMAIL)
        student_record = self._get_student_data(send_uncensored_pii_data=True)
        self.assertFalse(
            'form01' in student_record['registration_fields'])
        self.assertEquals(
            student_record['registration_fields']['form02'], '1.212.555.1212')
        self.assertFalse(
            'form03' in student_record['registration_fields'])
        self.assertFalse(
            'unknown_field' in student_record['registration_fields'])


class MockResponse(object):

    def __init__(self, the_dict):
        self._the_dict = the_dict

    def get(self, name, default=None):
        if name in self._the_dict:
            return self._the_dict[name]
        return default

    def __getattr__(self, name):
        return self._the_dict[name]

    def __getitem__(self, name):
        return self._the_dict[name]

    def __contains__(self, name):
        return name in self._the_dict


class MockHttp(object):

    def __init__(self):
        self.responses = []
        self.request_args = None
        self.request_kwargs = None

    def add_response(self, headers_dict):
        self.responses.append(headers_dict)

    def request(self, *args, **kwargs):
        self.request_args = args
        self.request_kwargs = kwargs
        item = self.responses[0]
        del self.responses[0]
        if isinstance(item, Exception):
            raise item
        else:
            return MockResponse(item), ''


class MockServiceClient(object):

    def __init__(self, mock_http):
        self.mock_http = mock_http
        self.calls = []
        self.insert_args = None
        self.insert_kwargs = None

    def datasets(self, *unused_args, **unused_kwargs):
        self.calls.append('datasets')
        return self

    def tables(self, *unused_args, **unused_kwargs):
        self.calls.append('tables')
        return self

    def get(self, *unused_args, **unused_kwargs):
        self.calls.append('get')
        return self

    def insert(self, *args, **kwargs):
        self.calls.append('insert')
        self.insert_args = args
        self.insert_kwargs = kwargs
        return self

    def delete(self, *unused_args, **unused_kwargs):
        self.calls.append('delete')
        return self

    def execute(self, *unused_args, **unused_kwargs):
        self.calls.append('execute')
        return self.mock_http.request()


class InteractionTests(actions.TestBase):

    def setUp(self):
        super(InteractionTests, self).setUp()
        actions.login(ADMIN_EMAIL, is_admin=True)
        self.app_context = actions.simple_add_course(
            COURSE_NAME, ADMIN_EMAIL, 'Data pump')

        # Configure data pump settings.
        course_settings = self.app_context.get_environ()
        pump_settings = {}
        course_settings[data_pump.DATA_PUMP_SETTINGS_SCHEMA_SECTION] = (
            pump_settings)
        pump_settings['project_id'] = 'foo'
        pump_settings['json_key'] = '{"private_key": "X", "client_email": "Y"}'
        course = courses.Course(None, app_context=self.app_context)
        course.save_settings(course_settings)

        # Remove all other data sources; ensure that we are the only source
        # causing text to appear on the UI page.  Note: must do this by
        # affecting the array's contents; replacing the array itself will not
        # affect the references already held by compiled @classmethod
        # functions.
        self.save_registered_sources = []
        self.save_registered_sources.extend(
            data_sources.Registry._data_source_classes)
        del data_sources.Registry._data_source_classes[:]
        data_sources.Registry.register(TrivialDataSource)

        # Build mocks for comms to BigQuery
        self.mock_http = MockHttp()
        self.mock_service_client = MockServiceClient(self.mock_http)
        self.save_bigquery_service_function = (
            data_pump.DataPumpJob._get_bigquery_service)
        data_pump.DataPumpJob._get_bigquery_service = (
            lambda slf, set: (self.mock_service_client, self.mock_http))
        self._set_up_job(no_expiration_date=False,
                         send_uncensored_pii_data=False)

    def _set_up_job(self, no_expiration_date=False,
                    send_uncensored_pii_data=False):
        self.job = data_pump.DataPumpJob(
            self.app_context, TrivialDataSource.__name__,
            no_expiration_date, send_uncensored_pii_data)
        self.bigquery_settings = self.job._get_bigquery_settings(
            self.app_context)

    def tearDown(self):
        super(InteractionTests, self).tearDown()
        data_sources.Registry.unregister(TrivialDataSource)
        data_pump.DataPumpJob._get_bigquery_service = (
            self.save_bigquery_service_function)
        del data_sources.Registry._data_source_classes[:]
        data_sources.Registry._data_source_classes.extend(
            self.save_registered_sources)


class BigQueryInteractionTests(InteractionTests):

    def test_does_not_create_dataset_when_already_exists(self):
        self.mock_http.add_response({'status': 200})
        self.job._maybe_create_course_dataset(self.mock_service_client,
                                              self.bigquery_settings)
        self.assertEqual(
            ['datasets', 'get', 'execute'],
            self.mock_service_client.calls)

    def test_does_create_dataset_when_none_exists(self):
        self.mock_http.add_response(apiclient.errors.HttpError(
            MockResponse({'status': 404}), ''))
        self.mock_http.add_response({'status': 200})
        self.job._maybe_create_course_dataset(self.mock_service_client,
                                              self.bigquery_settings)
        self.assertEqual(
            ['datasets', 'get', 'execute', 'insert', 'execute'],
            self.mock_service_client.calls)

    def test_create_dataset_raises_500(self):
        self.mock_http.add_response(apiclient.errors.HttpError(
            MockResponse({'status': 500}), ''))
        with self.assertRaises(apiclient.errors.HttpError):
            self.job._maybe_create_course_dataset(self.mock_service_client,
                                                  self.bigquery_settings)

    def test_delete_table_ignores_404(self):
        self.mock_http.add_response(apiclient.errors.HttpError(
            MockResponse({'status': 404}), ''))
        self.job._maybe_delete_previous_table(
            self.mock_service_client, self.bigquery_settings, TrivialDataSource)
        self.assertEqual(
            ['delete', 'execute'],
            self.mock_service_client.calls)

    def test_delete_table_accepts_200(self):
        self.mock_http.add_response({'status': 200})
        self.job._maybe_delete_previous_table(
            self.mock_service_client, self.bigquery_settings, TrivialDataSource)
        self.assertEqual(
            ['delete', 'execute'],
            self.mock_service_client.calls)

    def test_delete_table_raises_500(self):
        self.mock_http.add_response(apiclient.errors.HttpError(
            MockResponse({'status': 500}), ''))
        with self.assertRaises(apiclient.errors.HttpError):
            self.job._maybe_delete_previous_table(
                self.mock_service_client, self.bigquery_settings,
                TrivialDataSource)

    def test_create_data_table_accepts_200(self):
        self.mock_http.add_response({'status': 200})
        self.job._create_data_table(
            self.mock_service_client, self.bigquery_settings, None,
            TrivialDataSource)

    def test_create_data_table_raises_404(self):
        self.mock_http.add_response(apiclient.errors.HttpError(
            MockResponse({'status': 404}), ''))
        with self.assertRaises(apiclient.errors.HttpError):
            self.job._create_data_table(
                self.mock_service_client, self.bigquery_settings, None,
                TrivialDataSource)

    def test_create_upload_job_accepts_200(self):
        self.mock_http.add_response({'status': 200, 'location': 'there'})
        location = self.job._create_upload_job(
            self.mock_http, self.bigquery_settings, TrivialDataSource)
        self.assertEqual(location, 'there')

    def test_create_upload_receiving_response_without_location_is_error(self):
        self.mock_http.add_response({'status': 200})
        with self.assertRaises(Exception):
            self.job._create_upload_job(
                self.mock_http, self.bigquery_settings, TrivialDataSource)

    def test_create_upload_receiving_non_200_response_is_error(self):
        self.mock_http.add_response({'status': 204, 'location': 'there'})
        with self.assertRaises(Exception):
            self.job._create_upload_job(
                self.mock_http, self.bigquery_settings, TrivialDataSource)

    def _initiate_upload_job(self):
        self.mock_http.add_response({'status': 200})
        self.mock_http.add_response({'status': 200})
        self.mock_http.add_response({'status': 200})
        self.mock_http.add_response({'status': 200, 'location': 'there'})
        return self.job._initiate_upload_job(
            self.mock_service_client, self.bigquery_settings, self.mock_http,
            self.app_context, self.job._build_data_source_context())

    def test_create_data_table_makes_non_pii_schema(self):
        self._initiate_upload_job()
        fields = (
            self.mock_service_client.insert_kwargs['body']['schema']['fields'])
        self.assertIsNotNone(
            common_utils.find(lambda f: f['name'] == 'thing', fields))
        self.assertIsNone(
            common_utils.find(lambda f: f['name'] == 'ssn', fields))

    def test_create_data_table_makes_pii_schema(self):
        self._set_up_job(no_expiration_date=False,
                         send_uncensored_pii_data=True)
        self._initiate_upload_job()
        fields = (
            self.mock_service_client.insert_kwargs['body']['schema']['fields'])
        self.assertIsNotNone(
            common_utils.find(lambda f: f['name'] == 'thing', fields))
        self.assertIsNotNone(
            common_utils.find(lambda f: f['name'] == 'ssn', fields))

    def test_create_data_table_sends_default_expiration(self):
        self._initiate_upload_job()
        utc_now = datetime.datetime.utcnow()
        utc_epoch = datetime.datetime.utcfromtimestamp(0)
        expected = ((utc_now - utc_epoch).total_seconds() +
                    self.bigquery_settings.table_lifetime_seconds) * 1000

        # Ensure we have default value (not zero)
        self.assertEquals(30 * 24 * 60 *60,
                          self.bigquery_settings.table_lifetime_seconds)
        # Ensure table expiration timestamp sent to BigQuery matches setting.
        actual = (
            self.mock_service_client.insert_kwargs['body']['expirationTime'])
        self.assertAlmostEqual(expected, actual, delta=2000)

    def test_create_data_table_sends_configured_expiration(self):
        course_settings = self.app_context.get_environ()
        course_settings[data_pump.DATA_PUMP_SETTINGS_SCHEMA_SECTION][
            data_pump.TABLE_LIFETIME] = '10 s'
        course = courses.Course(None, app_context=self.app_context)
        course.save_settings(course_settings)
        self._set_up_job(no_expiration_date=False,
                         send_uncensored_pii_data=False)
        self._initiate_upload_job()
        utc_now = datetime.datetime.utcnow()
        utc_epoch = datetime.datetime.utcfromtimestamp(0)
        expected = ((utc_now - utc_epoch).total_seconds() +
                    self.bigquery_settings.table_lifetime_seconds) * 1000

        # Ensure we have override from default value.
        self.assertEquals(10, self.bigquery_settings.table_lifetime_seconds)
        # Ensure table expiration timestamp sent to BigQuery matches setting.
        actual = (
            self.mock_service_client.insert_kwargs['body']['expirationTime'])
        self.assertAlmostEqual(expected, actual, delta=2000)

    def test_table_expiration_suppressed(self):
        self._set_up_job(no_expiration_date=True,
                         send_uncensored_pii_data=False)
        self._initiate_upload_job()
        self.assertNotIn('expirationTime',
                         self.mock_service_client.insert_kwargs['body'])

    def test_initiate_upload_job(self):
        location = self._initiate_upload_job()
        self.assertEqual(location, 'there')

    def test_check_state_just_started(self):
        self.job.submit()  # Saves state, but does not run queued item.
        job_context = self.job._build_job_context('unused', 'unused')
        self.mock_http.add_response({'status': 308})
        next_page, next_status = self.job._check_upload_state(
            self.mock_http, job_context)
        self.assertEqual(next_page, 0)
        self.assertEqual(next_status, jobs.STATUS_CODE_STARTED)
        self.assertEqual(len(job_context[data_pump.CONSECUTIVE_FAILURES]), 0)

    def test_check_state_last_page_not_recieved(self):
        self.job.submit()  # Saves state, but does not run queued item.
        job_context = self.job._build_job_context('unused', 'unused')
        job_context[data_pump.LAST_PAGE_SENT] = 6
        job_context[data_pump.LAST_START_OFFSET] = 5
        job_context[data_pump.LAST_END_OFFSET] = 6
        self.mock_http.add_response({'status': 308, 'range': '0-5'})
        next_page, next_status = self.job._check_upload_state(
            self.mock_http, job_context)
        self.assertEqual(next_page, 6)
        self.assertEqual(next_status, jobs.STATUS_CODE_STARTED)
        self.assertEqual(len(job_context[data_pump.CONSECUTIVE_FAILURES]), 1)

    def test_check_state_last_page_received(self):
        self.job.submit()  # Saves state, but does not run queued item.
        job_context = self.job._build_job_context('unused', 'unused')
        job_context[data_pump.LAST_PAGE_SENT] = 6
        job_context[data_pump.LAST_START_OFFSET] = 5
        job_context[data_pump.LAST_END_OFFSET] = 6
        self.mock_http.add_response({'status': 308, 'range': '0-6'})
        next_page, next_status = self.job._check_upload_state(
            self.mock_http, job_context)
        self.assertEqual(next_page, 7)
        self.assertEqual(next_status, jobs.STATUS_CODE_STARTED)
        self.assertEqual(len(job_context[data_pump.CONSECUTIVE_FAILURES]), 0)

    def test_check_state_last_page_has_bad_range_too_low(self):
        self.job.submit()  # Saves state, but does not run queued item.
        job_context = self.job._build_job_context('unused', 'unused')
        job_context[data_pump.LAST_PAGE_SENT] = 6
        job_context[data_pump.LAST_START_OFFSET] = 5
        job_context[data_pump.LAST_END_OFFSET] = 6
        self.mock_http.add_response({'status': 308, 'range': '0-3'})
        with self.assertRaises(ValueError):
            self.job._check_upload_state(self.mock_http, job_context)

    def test_check_state_last_page_has_bad_range_too_high(self):
        self.job.submit()  # Saves state, but does not run queued item.
        job_context = self.job._build_job_context('unused', 'unused')
        job_context[data_pump.LAST_PAGE_SENT] = 6
        job_context[data_pump.LAST_START_OFFSET] = 5
        job_context[data_pump.LAST_END_OFFSET] = 6
        self.mock_http.add_response({'status': 308, 'range': '0-7'})
        with self.assertRaises(ValueError):
            self.job._check_upload_state(self.mock_http, job_context)

    def test_check_state_completed(self):
        self.job.submit()  # Saves state, but does not run queued item.
        job_context = self.job._build_job_context('unused', 'unused')
        self.mock_http.add_response({'status': 200})
        next_page, next_status = self.job._check_upload_state(
            self.mock_http, job_context)
        self.assertEqual(next_page, None)
        self.assertEqual(next_status, jobs.STATUS_CODE_COMPLETED)
        self.assertEqual(len(job_context[data_pump.CONSECUTIVE_FAILURES]), 0)

    def test_check_state_disappeared(self):
        self.job.submit()  # Saves state, but does not run queued item.
        job_context = self.job._build_job_context('unused', 'unused')
        self.mock_http.add_response({'status': 404})
        next_page, next_status = self.job._check_upload_state(
            self.mock_http, job_context)
        self.assertEqual(next_page, None)
        self.assertEqual(next_status, jobs.STATUS_CODE_QUEUED)
        self.assertEqual(len(job_context[data_pump.CONSECUTIVE_FAILURES]), 0)

    def test_check_state_server_error(self):
        self.job.submit()  # Saves state, but does not run queued item.
        job_context = self.job._build_job_context('unused', 'unused')
        self.mock_http.add_response({'status': 503})
        next_page, next_status = self.job._check_upload_state(
            self.mock_http, job_context)
        self.assertEqual(next_page, None)
        self.assertEqual(next_status, jobs.STATUS_CODE_STARTED)
        self.assertEqual(len(job_context[data_pump.CONSECUTIVE_FAILURES]), 1)

    def test_check_state_unexpected_code(self):
        self.job.submit()  # Saves state, but does not run queued item.
        job_context = self.job._build_job_context('unused', 'unused')
        self.mock_http.add_response({'status': 400})
        with self.assertRaises(ValueError):
            self.job._check_upload_state(self.mock_http, job_context)

    def test_check_state_recoverable_failure_then_success(self):
        self.job.submit()  # Saves state, but does not run queued item.
        job_context = self.job._build_job_context('unused', 'unused')
        job_context[data_pump.LAST_PAGE_SENT] = 6
        job_context[data_pump.LAST_START_OFFSET] = 5
        job_context[data_pump.LAST_END_OFFSET] = 6
        self.mock_http.add_response({'status': 308, 'range': '0-5'})
        self.job._check_upload_state(self.mock_http, job_context)
        self.assertEqual(len(job_context[data_pump.CONSECUTIVE_FAILURES]), 1)

        # We want to _not_ see the error clear if we're just checking on
        # upload.
        self.mock_http.add_response({'status': 308, 'range': '0-6'})
        self.job._check_upload_state(self.mock_http, job_context)
        self.assertEqual(len(job_context[data_pump.CONSECUTIVE_FAILURES]), 1)

    def test_send_first_page_as_last_page(self):
        self.job.submit()  # Saves state, but does not run queued item.
        job_status_object = self.job.load()
        job_context = self.job._build_job_context('unused', 'unused')
        data_source_context = self.job._build_data_source_context()
        self.mock_http.add_response({'status': 308, 'range': '0-1'})
        next_state = self.job._send_data_page_to_bigquery(
            data=[1], is_last_chunk=True, next_page=0,
            http=self.mock_http, job=job_status_object,
            sequence_num=job_status_object.sequence_num,
            job_context=job_context, data_source_context=data_source_context)
        self.assertEqual(next_state, jobs.STATUS_CODE_STARTED)
        self.assertEqual(
            self.mock_http.request_kwargs['headers']['Content-Range'],
            'bytes 0-1/2')

    def test_send_first_page_as_non_last_page(self):
        self.job.submit()  # Saves state, but does not run queued item.
        job_status_object = self.job.load()
        job_context = self.job._build_job_context('unused', 'unused')
        data_source_context = self.job._build_data_source_context()
        self.mock_http.add_response({'status': 308, 'range': '0-1'})
        next_state = self.job._send_data_page_to_bigquery(
            data=[1], is_last_chunk=False, next_page=0,
            http=self.mock_http, job=job_status_object,
            sequence_num=job_status_object.sequence_num,
            job_context=job_context, data_source_context=data_source_context)
        self.assertEqual(next_state, jobs.STATUS_CODE_STARTED)
        self.assertEqual(
            self.mock_http.request_kwargs['headers']['Content-Range'],
            'bytes 0-262143/*')

    def test_resend_first_page_as_last_page(self):
        self.job.submit()  # Saves state, but does not run queued item.
        job_status_object = self.job.load()
        job_context = self.job._build_job_context('unused', 'unused')
        job_context[data_pump.LAST_PAGE_SENT] = 0
        job_context[data_pump.LAST_START_OFFSET] = 0
        job_context[data_pump.LAST_END_OFFSET] = 1
        data_source_context = self.job._build_data_source_context()
        self.mock_http.add_response({'status': 308, 'range': '0-1'})
        next_state = self.job._send_data_page_to_bigquery(
            data=[1], is_last_chunk=True, next_page=0,
            http=self.mock_http, job=job_status_object,
            sequence_num=job_status_object.sequence_num,
            job_context=job_context, data_source_context=data_source_context)
        self.assertEqual(next_state, jobs.STATUS_CODE_STARTED)
        self.assertEqual(
            self.mock_http.request_kwargs['headers']['Content-Range'],
            'bytes 0-1/2')

    def test_send_subsequent_page_as_last_page(self):
        self.job.submit()  # Saves state, but does not run queued item.
        job_status_object = self.job.load()
        job_context = self.job._build_job_context('unused', 'unused')
        job_context[data_pump.LAST_PAGE_SENT] = 0
        job_context[data_pump.LAST_START_OFFSET] = 0
        job_context[data_pump.LAST_END_OFFSET] = 262143
        data_source_context = self.job._build_data_source_context()
        self.mock_http.add_response({'status': 308, 'range': '0-262145'})
        next_state = self.job._send_data_page_to_bigquery(
            data=[1], is_last_chunk=True, next_page=1,
            http=self.mock_http, job=job_status_object,
            sequence_num=job_status_object.sequence_num,
            job_context=job_context, data_source_context=data_source_context)
        self.assertEqual(next_state, jobs.STATUS_CODE_STARTED)
        self.assertEqual(
            self.mock_http.request_kwargs['headers']['Content-Range'],
            'bytes 262144-262145/262146')

    def test_send_failure_then_success(self):
        self.job.submit()  # Saves state, but does not run queued item.
        job_status_object = self.job.load()
        job_context = self.job._build_job_context('unused', 'unused')
        data_source_context = self.job._build_data_source_context()

        # Here, we have the server respond without a 'Range' header,
        # indicating that it has not seen _any_ data at all from us,
        # so we incur a transient failure.
        self.mock_http.add_response({'status': 308})
        self.job._send_data_page_to_bigquery(
            data=[1], is_last_chunk=True, next_page=0,
            http=self.mock_http, job=job_status_object,
            sequence_num=job_status_object.sequence_num,
            job_context=job_context, data_source_context=data_source_context)
        self.assertEqual(len(job_context[data_pump.CONSECUTIVE_FAILURES]), 1)

        # And here, we claim the server has seen everything we need to send,
        # and so we should also see the consecutive failures list clear out.
        self.mock_http.add_response({'status': 308, 'range': '0-1'})
        self.job._send_data_page_to_bigquery(
            data=[1], is_last_chunk=True, next_page=0,
            http=self.mock_http, job=job_status_object,
            sequence_num=job_status_object.sequence_num,
            job_context=job_context, data_source_context=data_source_context)
        self.assertEqual(len(job_context[data_pump.CONSECUTIVE_FAILURES]), 0)

    def test_excessive_retries_causes_failure(self):
        self.job.submit()
        job_object = self.job.load()

        # Dataset exists; table deletion, table creation, job initiation.
        self.mock_http.add_response({'status': 200})
        self.mock_http.add_response({'status': 200})
        self.mock_http.add_response({'status': 200})
        self.mock_http.add_response({'status': 200, 'location': 'there'})

        # Fail on status check, even before sending data N-1 times.
        for _ in range(0, data_pump.MAX_CONSECUTIVE_FAILURES - 1):
            self.mock_http.add_response({'status': 500})
            self.execute_all_deferred_tasks(iteration_limit=1)
            job_object = self.job.load()
            job_context, _ = self.job._load_state(job_object,
                                                  job_object.sequence_num)
            self.assertEqual(job_object.status_code, jobs.STATUS_CODE_STARTED)
            self.assertEqual(0, job_context[data_pump.ITEMS_UPLOADED])
            self.assertEqual(-1, job_context[data_pump.LAST_PAGE_SENT])
            self.assertEqual(0, job_context[data_pump.LAST_START_OFFSET])
            self.assertEqual(-1, job_context[data_pump.LAST_END_OFFSET])

        # Last failure pops exception to notify queue to abandon this job.
        self.mock_http.add_response({'status': 500})
        with self.assertRaises(deferred.PermanentTaskFailure):
            self.execute_all_deferred_tasks(iteration_limit=1)
        job_object = self.job.load()
        self.assertEqual(job_object.status_code, jobs.STATUS_CODE_FAILED)

        # Verify job did not re-queue itself after declaring failure
        num_tasks = self.execute_all_deferred_tasks(iteration_limit=1)
        self.assertEqual(0, num_tasks)

    def test_cancellation(self):
        self.job.submit()
        job_object = self.job.load()

        # Dataset exists; table deletion, table creation, job initiation.
        self.mock_http.add_response({'status': 200})
        self.mock_http.add_response({'status': 200})
        self.mock_http.add_response({'status': 200})
        self.mock_http.add_response({'status': 200, 'location': 'there'})

        # Initial page check - no 'range' header when no data sent.
        # Initial page send; response indicates full recipt of page #0
        self.mock_http.add_response({'status': 308})
        self.mock_http.add_response({'status': 308, 'range': '0-262143'})
        self.execute_all_deferred_tasks(iteration_limit=1)
        job_object = self.job.load()
        self.assertEqual(job_object.status_code, jobs.STATUS_CODE_STARTED)

        # Cancel job.  Set mock server to pretend upload completed;
        # cancellation should take priority.
        self.job.cancel()
        self.mock_http.add_response({'status': 200})
        num_tasks = self.execute_all_deferred_tasks(iteration_limit=1)
        job_object = self.job.load()
        self.assertEqual(1, num_tasks)
        self.assertEqual(job_object.status_code, jobs.STATUS_CODE_FAILED)

        # Verify job did not re-queue itself after declaring failure
        num_tasks = self.execute_all_deferred_tasks(iteration_limit=1)
        self.assertEqual(0, num_tasks)

    def test_upload_job_expiration(self):
        self.job.submit()
        job_object = self.job.load()

        # Dataset exists; table deletion, table creation, job initiation.
        self.mock_http.add_response({'status': 200})
        self.mock_http.add_response({'status': 200})
        self.mock_http.add_response({'status': 200})
        self.mock_http.add_response({'status': 200, 'location': 'there'})

        # Initial page check - no 'range' header when no data sent.
        # Initial page send; response indicates full recipt of page #0
        self.mock_http.add_response({'status': 308})
        self.mock_http.add_response({'status': 308, 'range': '0-262143'})
        self.execute_all_deferred_tasks(iteration_limit=1)
        job_object = self.job.load()
        job_context, _ = self.job._load_state(job_object,
                                              job_object.sequence_num)
        self.assertEqual(job_object.status_code, jobs.STATUS_CODE_STARTED)
        self.assertEqual(3, job_context[data_pump.ITEMS_UPLOADED])
        self.assertEqual(0, job_context[data_pump.LAST_PAGE_SENT])
        self.assertEqual(0, job_context[data_pump.LAST_START_OFFSET])
        self.assertEqual(262143, job_context[data_pump.LAST_END_OFFSET])

        # Server acepts page #1 correctly as well.  Here, we're doing
        # one more page so that when we check lower down to see where
        # we are, we will appear to have gone backwards as to how far
        # the upload has proceeded.  This is to verify the full reset
        # of internal state on upload timeout.
        self.mock_http.add_response({'status': 308, 'range': '0-262143'})
        self.mock_http.add_response({'status': 308, 'range': '262144-524287'})
        self.execute_all_deferred_tasks(iteration_limit=1)
        job_object = self.job.load()
        job_context, _ = self.job._load_state(job_object,
                                              job_object.sequence_num)
        self.assertEqual(job_object.status_code, jobs.STATUS_CODE_STARTED)
        self.assertEqual(6, job_context[data_pump.ITEMS_UPLOADED])
        self.assertEqual(1, job_context[data_pump.LAST_PAGE_SENT])
        self.assertEqual(262144, job_context[data_pump.LAST_START_OFFSET])
        self.assertEqual(524287, job_context[data_pump.LAST_END_OFFSET])
        self.assertEqual(0, len(job_context[data_pump.CONSECUTIVE_FAILURES]))

        # Here, we have a job status object claiming we've made some progress.
        # Now set mock server to claim upload job has been reclaimed due to
        # long inactivity (return 404)
        self.mock_http.add_response({'status': 404})
        num_tasks = self.execute_all_deferred_tasks(iteration_limit=1)
        job_object = self.job.load()
        job_context, _ = self.job._load_state(job_object,
                                              job_object.sequence_num)
        self.assertEqual(job_object.status_code, jobs.STATUS_CODE_QUEUED)

        # Since we claimed to be queued, logic should start over and
        # attempt to re-push content.  Verify that we have started over
        # from scratch.
        self.mock_http.add_response({'status': 200})
        self.mock_http.add_response({'status': 200})
        self.mock_http.add_response({'status': 200})
        self.mock_http.add_response({'status': 200, 'location': 'there'})
        self.mock_http.add_response({'status': 308})
        self.mock_http.add_response({'status': 308, 'range': '0-262143'})
        self.execute_all_deferred_tasks(iteration_limit=1)
        job_object = self.job.load()
        job_context, _ = self.job._load_state(job_object,
                                              job_object.sequence_num)
        self.assertEqual(job_object.status_code, jobs.STATUS_CODE_STARTED)
        self.assertEqual(3, job_context[data_pump.ITEMS_UPLOADED])
        self.assertEqual(0, job_context[data_pump.LAST_PAGE_SENT])
        self.assertEqual(0, job_context[data_pump.LAST_START_OFFSET])
        self.assertEqual(262143, job_context[data_pump.LAST_END_OFFSET])

        # Here, we have tested everything we need to.  Now lie to the
        # uploader so it will think it has completed.  Next, verify that
        # no items are on the queue (so we don't screw up sibling tests)
        self.mock_http.add_response({'status': 200})
        self.execute_all_deferred_tasks(iteration_limit=1)
        num_tasks = self.execute_all_deferred_tasks(iteration_limit=1)
        self.assertEqual(0, num_tasks)

    def test_full_job_lifecycle(self):
        self.job.submit()
        job_object = self.job.load()
        self.assertEqual(job_object.status_code, jobs.STATUS_CODE_QUEUED)

        # Dataset exists; table deletion, table creation, job initiation.
        self.mock_http.add_response({'status': 200})
        self.mock_http.add_response({'status': 200})
        self.mock_http.add_response({'status': 200})
        self.mock_http.add_response({'status': 200, 'location': 'there'})

        # Initial page check - no 'range' header when no data sent.
        # Initial page send; response indicates full recipt of page #0
        self.mock_http.add_response({'status': 308})
        self.mock_http.add_response({'status': 308, 'range': '0-262143'})
        self.execute_all_deferred_tasks(iteration_limit=1)
        job_object = self.job.load()
        job_context, _ = self.job._load_state(job_object,
                                              job_object.sequence_num)
        self.assertEqual(job_object.status_code, jobs.STATUS_CODE_STARTED)
        self.assertEqual(3, job_context[data_pump.ITEMS_UPLOADED])
        self.assertEqual(0, job_context[data_pump.LAST_PAGE_SENT])
        self.assertEqual(0, job_context[data_pump.LAST_START_OFFSET])
        self.assertEqual(262143, job_context[data_pump.LAST_END_OFFSET])

        # Re-check on re-entry to main function; still have bytes [0..38]
        # On send of 2nd page, pretend to not have heard, staying at [0..38]
        self.mock_http.add_response({'status': 308, 'range': '0-262143'})
        self.mock_http.add_response({'status': 308, 'range': '0-262143'})
        self.execute_all_deferred_tasks(iteration_limit=1)
        job_object = self.job.load()
        job_context, _ = self.job._load_state(job_object,
                                              job_object.sequence_num)
        self.assertEqual(job_object.status_code, jobs.STATUS_CODE_STARTED)
        self.assertEqual(3, job_context[data_pump.ITEMS_UPLOADED])
        self.assertEqual(1, job_context[data_pump.LAST_PAGE_SENT])
        self.assertEqual(262144, job_context[data_pump.LAST_START_OFFSET])
        self.assertEqual(524287, job_context[data_pump.LAST_END_OFFSET])
        self.assertEqual(1, len(job_context[data_pump.CONSECUTIVE_FAILURES]))

        # Pretend server is having trouble and is returning 500's.
        # Only the status-check call will run; we should not attempt to
        # upload data to a server that's having trouble.
        # We expect to see one more item in the consecutive failures
        # list.  We also expect at least 4 seconds to elapse.
        self.mock_http.add_response({'status': 500})
        self.execute_all_deferred_tasks(iteration_limit=1)
        job_object = self.job.load()
        job_context, _ = self.job._load_state(job_object,
                                              job_object.sequence_num)
        self.assertEqual(job_object.status_code, jobs.STATUS_CODE_STARTED)
        self.assertEqual(3, job_context[data_pump.ITEMS_UPLOADED])
        self.assertEqual(1, job_context[data_pump.LAST_PAGE_SENT])
        self.assertEqual(262144, job_context[data_pump.LAST_START_OFFSET])
        self.assertEqual(524287, job_context[data_pump.LAST_END_OFFSET])
        self.assertEqual(2, len(job_context[data_pump.CONSECUTIVE_FAILURES]))

        # OK, server is now well, and accepts page #1 successfully.
        self.mock_http.add_response({'status': 308, 'range': '0-262143'})
        self.mock_http.add_response({'status': 308, 'range': '262144-524287'})
        self.execute_all_deferred_tasks(iteration_limit=1)
        job_object = self.job.load()
        job_context, _ = self.job._load_state(job_object,
                                              job_object.sequence_num)
        self.assertEqual(job_object.status_code, jobs.STATUS_CODE_STARTED)
        self.assertEqual(6, job_context[data_pump.ITEMS_UPLOADED])
        self.assertEqual(1, job_context[data_pump.LAST_PAGE_SENT])
        self.assertEqual(262144, job_context[data_pump.LAST_START_OFFSET])
        self.assertEqual(524287, job_context[data_pump.LAST_END_OFFSET])
        self.assertEqual(0, len(job_context[data_pump.CONSECUTIVE_FAILURES]))

        # OK, server is now well, and accepts page #2 successfully.
        self.mock_http.add_response({'status': 308, 'range': '262144-524287'})
        self.mock_http.add_response({'status': 308, 'range': '524288-786431'})
        self.execute_all_deferred_tasks(iteration_limit=1)
        job_object = self.job.load()
        job_context, _ = self.job._load_state(job_object,
                                              job_object.sequence_num)
        self.assertEqual(job_object.status_code, jobs.STATUS_CODE_STARTED)
        self.assertEqual(9, job_context[data_pump.ITEMS_UPLOADED])
        self.assertEqual(2, job_context[data_pump.LAST_PAGE_SENT])
        self.assertEqual(524288, job_context[data_pump.LAST_START_OFFSET])
        self.assertEqual(786431, job_context[data_pump.LAST_END_OFFSET])
        self.assertEqual(0, len(job_context[data_pump.CONSECUTIVE_FAILURES]))

        # OK, server is now well, and accepts page #3 successfully.  Here,
        # server acknowledges receipt of last page w/ a 200 rather than a 308;
        # we should notice that and mark ourselves complete.
        self.mock_http.add_response({'status': 308, 'range': '524288-786431'})
        self.mock_http.add_response({'status': 200, 'range': '786432-786444'})
        self.execute_all_deferred_tasks(iteration_limit=1)
        job_object = self.job.load()
        job_context, _ = self.job._load_state(job_object,
                                              job_object.sequence_num)
        self.assertEqual(job_object.status_code, jobs.STATUS_CODE_COMPLETED)
        self.assertEqual(10, job_context[data_pump.ITEMS_UPLOADED])
        self.assertEqual(3, job_context[data_pump.LAST_PAGE_SENT])
        self.assertEqual(786432, job_context[data_pump.LAST_START_OFFSET])
        self.assertEqual(786444, job_context[data_pump.LAST_END_OFFSET])
        self.assertEqual(0, len(job_context[data_pump.CONSECUTIVE_FAILURES]))

        # And verify job did not re-queue itself after declaring success.
        num_tasks = self.execute_all_deferred_tasks(iteration_limit=1)
        self.assertEqual(0, num_tasks)


class UserInteractionTests(InteractionTests):

    URL = '/data_pump/dashboard?action=data_pump'

    def test_no_data_pump_settings(self):
        course_settings = self.app_context.get_environ()
        del course_settings[data_pump.DATA_PUMP_SETTINGS_SCHEMA_SECTION]
        course = courses.Course(None, app_context=self.app_context)
        course.save_settings(course_settings)

        response = self.get(self.URL)
        self.assertIn(
            'Data pump functionality is not currently enabled', response.body)

    def _get_status_text(self):
        dom = self.parse_html_string(self.get(self.URL).body)
        row = dom.find('.//tr[@id="TrivialDataSource"]')
        cell = row.find('.//td[@class="status-column"]')
        # Convert all whitespace sequences to single spaces.
        text = ' '.join(''.join(cell.itertext()).strip().split())
        return text

    def test_full_job_lifecycle(self):
        self.assertEquals(
            'Trivial Data Source '
            'Pump status: Has Never Run '
            'Do not encrypt PII data for this upload '
            'Uploaded data never expires (default expiration is 30 days)',
            self._get_status_text())

        response = self.get(self.URL)
        self.submit(response.forms['data_pump_form_TrivialDataSource'],
                     response)
        # Dataset exists; table deletion, table creation, job initiation.
        self.mock_http.add_response({'status': 200})
        self.mock_http.add_response({'status': 200})
        self.mock_http.add_response({'status': 200})
        self.mock_http.add_response({'status': 200, 'location': 'there'})

        # Initial page check - no 'range' header when no data sent.
        # Initial page send; response indicates full recipt of page #0
        self.mock_http.add_response({'status': 308})
        self.mock_http.add_response({'status': 308, 'range': '0-262143'})
        self.execute_all_deferred_tasks(iteration_limit=1)
        self.assertEqual('Trivial Data Source '
                         'Pump status: Started '
                         'Uploaded 3 items.',
                         self._get_status_text())

        # Re-check on re-entry to main function; still have bytes [0..38]
        # On send of 2nd page, pretend to not have heard, staying at [0..38]
        self.mock_http.add_response({'status': 308, 'range': '0-262143'})
        self.mock_http.add_response({'status': 308, 'range': '0-262143'})
        self.execute_all_deferred_tasks(iteration_limit=1)
        status_text = self._get_status_text()
        self.assertIn('Trivial Data Source', status_text)
        self.assertIn('Pump status: Started', status_text)
        self.assertIn('Uploaded 3 items.', status_text)
        self.assertIn('Incomplete upload detected - 0 of 262144 bytes '
                      'received for page 1', status_text)

        # Pretend server is having trouble and is returning 500's.
        # Only the status-check call will run; we should not attempt to
        # upload data to a server that's having trouble.
        # We expect to see one more item in the consecutive failures
        # list.  We also expect at least 4 seconds to elapse.
        self.mock_http.add_response({'status': 500})
        self.execute_all_deferred_tasks(iteration_limit=1)
        status_text = self._get_status_text()
        self.assertIn('Trivial Data Source', status_text)
        self.assertIn('Pump status: Started', status_text)
        self.assertIn('Uploaded 3 items.', status_text)
        self.assertIn('Incomplete upload detected - 0 of 262144 bytes '
                      'received for page 1', status_text)
        self.assertIn('Retryable server error 500', status_text)

        # OK, server is now well, and accepts page #1 successfully.
        self.mock_http.add_response({'status': 308, 'range': '0-262143'})
        self.mock_http.add_response({'status': 308, 'range': '262144-524287'})
        self.execute_all_deferred_tasks(iteration_limit=1)
        status_text = self._get_status_text()
        # Here note that transient failure messages are now gone.
        self.assertEquals('Trivial Data Source '
                          'Pump status: Started '
                          'Uploaded 6 items.', status_text)

        # OK, server is now well, and accepts page #2 successfully.
        self.mock_http.add_response({'status': 308, 'range': '262144-524287'})
        self.mock_http.add_response({'status': 308, 'range': '524288-786431'})
        self.execute_all_deferred_tasks(iteration_limit=1)
        status_text = self._get_status_text()
        self.assertEquals('Trivial Data Source '
                          'Pump status: Started '
                          'Uploaded 9 items.', status_text)

        # OK, server is now well, and accepts page #3 successfully.  Here,
        # server acknowledges receipt of last page w/ a 200 rather than a 308;
        # we should notice that and mark ourselves complete.
        self.mock_http.add_response({'status': 308, 'range': '524288-786431'})
        self.mock_http.add_response({'status': 200, 'range': '786432-786444'})
        self.execute_all_deferred_tasks(iteration_limit=1)
        status_text = self._get_status_text()
        self.assertEquals(
            'Trivial Data Source '
            'Pump status: Completed '
            'Uploaded 10 items. '
            'Do not encrypt PII data for this upload '
            'Uploaded data never expires (default expiration is 30 days)',
            status_text)

    def test_cancellation(self):
        self.assertEquals(
            'Trivial Data Source '
            'Pump status: Has Never Run '
            'Do not encrypt PII data for this upload '
            'Uploaded data never expires (default expiration is 30 days)',
            self._get_status_text())

        response = self.get(self.URL)
        self.submit(response.forms['data_pump_form_TrivialDataSource'],
                    response)

        # Dataset exists; table deletion, table creation, job initiation.
        self.mock_http.add_response({'status': 200})
        self.mock_http.add_response({'status': 200})
        self.mock_http.add_response({'status': 200})
        self.mock_http.add_response({'status': 200, 'location': 'there'})

        # Initial page check - no 'range' header when no data sent.
        # Initial page send; response indicates full recipt of page #0
        self.mock_http.add_response({'status': 308})
        self.mock_http.add_response({'status': 308, 'range': '0-262143'})
        self.execute_all_deferred_tasks(iteration_limit=1)
        self.assertEqual('Trivial Data Source '
                         'Pump status: Started '
                         'Uploaded 3 items.',
                         self._get_status_text())

        response = self.get(self.URL)
        self.submit(response.forms['data_pump_form_TrivialDataSource'],
                    response)

        self.execute_all_deferred_tasks()
        self.assertIn('Trivial Data Source '
                      'Pump status: Failed '
                      'Canceled by admin@foo.com',
                      self._get_status_text())

    def test_pii_expiration_warning(self):
        course_settings = self.app_context.get_environ()
        pump_settings = (
          course_settings[data_pump.DATA_PUMP_SETTINGS_SCHEMA_SECTION])
        pump_settings[data_pump.TABLE_LIFETIME] = '1 s'
        course = courses.Course(None, app_context=self.app_context)
        course.save_settings(course_settings)

        # Push full content of TrivialDataSource to BigQuery
        response = self.get(self.URL)
        self.submit(response.forms['data_pump_form_TrivialDataSource'],
                    response)
        self.mock_http.add_response({'status': 200})
        self.mock_http.add_response({'status': 200})
        self.mock_http.add_response({'status': 200})
        self.mock_http.add_response({'status': 200, 'location': 'there'})
        self.mock_http.add_response({'status': 308})
        self.mock_http.add_response({'status': 308, 'range': '0-262143'})
        self.mock_http.add_response({'status': 308, 'range': '0-262143'})
        self.mock_http.add_response({'status': 308, 'range': '262144-524287'})
        self.mock_http.add_response({'status': 308, 'range': '262144-524287'})
        self.mock_http.add_response({'status': 308, 'range': '524288-786431'})
        self.mock_http.add_response({'status': 308, 'range': '524288-786431'})
        self.mock_http.add_response({'status': 200, 'range': '786432-786444'})
        self.execute_all_deferred_tasks()

        time.sleep(1)
        self.assertEquals(
            'Trivial Data Source '
            'Pump status: Completed '
            'WARNING: This data source was last uploaded when a different '
            'secret for encoding personal data was in use. Data from this '
            'source will not be correlatable with other data sources '
            'uploaded using the latest secret. You may wish to re-upload '
            'this data. '
            'Uploaded 10 items. '
            'Do not encrypt PII data for this upload '
            'Uploaded data never expires (default expiration is 1 s)',
            self._get_status_text())

    def test_schema_rendering(self):
        del data_sources.Registry._data_source_classes[:]
        data_sources.Registry.register(ComplexDataSource)

        response = self.get(self.URL)
        soup = self.parse_html_string_to_soup(response.body)
        rows = soup.select('.schema-column > table > tr')
        schema_text = []
        for row in rows:
            schema_text.append([td.text for td in row.select('td')])
        expected = [
            ['an_int', 'integer', 'integer desc'],
            ['a_string', 'string', 'string desc'],
            ['sub_array', 'array', 'sub arr desc'],
              ['sub_int', 'integer', 'sub int desc'],
              ['sub_str', 'string', 'sub str desc'],
            ['scalar_array', 'array', 'scalar arr desc'],
              [u'', u'integer', u'arr int'],
            ['sub_registry', 'object', ''],
              ['sub_date', 'datetime', 'sub date desc'],
              ['sub_bool', 'bool', 'sub bool desc'],
              ['sub_obj_array', 'array', 'subobj array desc'],
                ['', 'text', 'arr text desc'],
        ]
        self.assertEquals(expected, schema_text)
