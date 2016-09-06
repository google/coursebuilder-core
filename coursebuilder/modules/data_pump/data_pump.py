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

"""Enable periodic transmission of DB and job-produced content to BigQuery."""

__author__ = [
  'Michael Gainer (mgainer@google.com)',
  ]

import base64
import collections
import copy
import datetime
import logging
import os
import random
import re
import time
import urllib

import apiclient
import apiclient.discovery
import httplib2
import oauth2client
import oauth2client.client

from common import catch_and_log
from common import crypto
from common import schema_fields
from common import utils as common_utils
from controllers import sites
from controllers import utils
from models import analytics
from models import courses
from models import custom_modules
from models import data_sources
from models import jobs
from models import services
from models import transforms
from modules.courses import settings
from modules.dashboard import dashboard
from modules.data_pump import messages

from google.appengine.ext import db
from google.appengine.ext import deferred

# CourseBuilder setup strings
MODULE_NAME = 'data_pump'
XSRF_ACTION_NAME = MODULE_NAME
DASHBOARD_ACTION = MODULE_NAME
MODULE_TITLE = 'Data pump'

# Connection parameters for discovering and auth to BigQuery.
BIGQUERY_RW_SCOPE = 'https://www.googleapis.com/auth/bigquery'
BIGQUERY_API_NAME = 'bigquery'
BIGQUERY_API_VERSION = 'v2'

# API endpoint for initiating a retryable upload.
BIGQUERY_API_UPLOAD_URL_PREFIX = (
    'https://www.googleapis.com/upload/bigquery/v2/projects/')

# UI for BigQuery interactive queries
BIGQUERY_UI_URL_PREFIX = 'https://bigquery.cloud.google.com/table/'

# Max of about 20 min of retries (random exponential backoff from 2^1...2^MAX)
MAX_CONSECUTIVE_FAILURES = 10
MAX_RETRY_BACKOFF_SECONDS = 600

# Config for secret
PII_SECRET_LENGTH = 20
PII_SECRET_DEFAULT_LIFETIME = '30 days'

# Constants for accessing job context settings map
UPLOAD_URL = 'upload_url'
LAST_START_OFFSET = 'last_start_offset'
LAST_END_OFFSET = 'last_end_offset'
LAST_PAGE_SENT = 'last_page_sent'
LAST_PAGE_NUM_ITEMS = 'last_page_num_items'
CONSECUTIVE_FAILURES = 'consecutive_failures'
FAILURE_REASON = 'failure_reason'
ITEMS_UPLOADED = 'items_uploaded'
PII_SECRET = 'pii_secret'

# Constants for items within course settings schema
DATA_PUMP_SETTINGS_SCHEMA_SECTION = MODULE_NAME
PROJECT_ID = 'project_id'
DATASET_NAME = 'dataset_name'
JSON_KEY = 'json_key'
TABLE_LIFETIME = 'table_lifetime'
PII_ENCRYPTION_TOKEN = 'pii_encryption_token'

# Discovery service lookup retries constants
DISCOVERY_SERVICE_MAX_ATTEMPTS = 10
DISCOVERY_SERVICE_RETRY_SECONDS = 2

def _get_data_source_class_by_name(name):
    source_classes = data_sources.Registry.get_rest_data_source_classes()
    for source_class in source_classes:
        if source_class.__name__ == name and source_class.exportable():
            return source_class

    names = [source_class.__name__ for source_class in source_classes]
    logging.critical(
        'No entry found for data source class with name "%s".  '
        'Available names are: %s', name, ' '.join(names))
    return None


class DataPumpJob(jobs.DurableJobBase):

    @staticmethod
    def get_description():
        """Job to push data from CourseBuilder to BigQuery.

        The job operates from the deferred queue, and takes advantage of the
        underlying TaskQueue retry and backoff support.  One job is created
        for each DataSource (see models/data_source).  This job moves data
        from the paginated data source up to Google BigQuery via the
        retryable POST method.

        Jobs here run on the TaskQueue named "default along with all other
        CB deferred tasks because that queue has a reasonable set of config
        parameters.  However, there is nothing about these jobs that
        requires interleaving with others if queue parameters need to be
        tuned.  Functional tests will need to be changed to have
        execute_all_deferred_tasks() pass the name of the new queue.
        """

    def __init__(self, app_context, data_source_class_name,
                 no_expiration_date=False, send_uncensored_pii_data=False):
        if not _get_data_source_class_by_name(data_source_class_name):
            raise ValueError(
              'No such data source "%s", or data source is not marked '
              'as exportable.' % data_source_class_name)

        super(DataPumpJob, self).__init__(app_context)
        self._data_source_class_name = data_source_class_name
        self._job_name = 'job-datapump-%s-%s' % (self._data_source_class_name,
                                                 self._namespace)
        self._no_expiration_date = no_expiration_date
        self._send_uncensored_pii_data = send_uncensored_pii_data

    def non_transactional_submit(self):
        """Callback used when UI gesture indicates this job should start."""

        sequence_num = super(DataPumpJob, self).non_transactional_submit()
        deferred.defer(self.main, sequence_num)
        return sequence_num

    def _mark_job_canceled(self, job, message):
        """Override default behavior of setting job.output to error string."""

        if job.output:
            job_context, data_source_context = self._load_state(
                job, job.sequence_num)
        else:
            job_context = self._build_job_context(None, None)
            data_source_context = self._build_data_source_context()
        job_context[FAILURE_REASON] = message
        self._save_state(jobs.STATUS_CODE_FAILED, job, job.sequence_num,
                         job_context, data_source_context,
                         use_transaction=False)

    def _build_data_source_context(self):
        """Set up context class specific to data source type we pull from."""
        data_source_class = _get_data_source_class_by_name(
            self._data_source_class_name)
        context_class = data_source_class.get_context_class()

        # TODO(mgainer): if we start getting timeout failures, perhaps learn
        # proper chunk size from history, rather than using default.
        default_chunk_size = data_source_class.get_default_chunk_size()
        ret = context_class.build_blank_default({}, default_chunk_size)
        if hasattr(ret, 'send_uncensored_pii_data'):
            ret.send_uncensored_pii_data = self._send_uncensored_pii_data
        return ret

    def _build_job_context(self, upload_url, pii_secret):
        """Set up context object used to maintain this job's internal state."""
        job_context = {
            UPLOAD_URL: upload_url,
            LAST_START_OFFSET: 0,
            LAST_END_OFFSET: -1,
            LAST_PAGE_SENT: -1,
            LAST_PAGE_NUM_ITEMS: 0,
            CONSECUTIVE_FAILURES: [],
            FAILURE_REASON: '',
            ITEMS_UPLOADED: 0,
            PII_SECRET: pii_secret,
            }
        return job_context

    def _load_state(self, job, sequence_num):
        if job.sequence_num != sequence_num:
            raise ValueError(
                'Abandoning stale job with sequence %d; '
                'there is a new job with sequence %d running.' % (
                    sequence_num, job.sequence_num))

        data_source_class = _get_data_source_class_by_name(
            self._data_source_class_name)
        content = transforms.loads(job.output)
        job_context = content['job_context']

        data_source_context_class = data_source_class.get_context_class()
        data_source_context = data_source_context_class.build_from_dict(
            content['data_source_context'])
        return job_context, data_source_context

    def _save_state(self, state, job, sequence_num, job_context,
                    data_source_context, use_transaction=True):

        # Job context may have been made with blank values for these two items.
        # Recover them from the previous context if they are not set (and if
        # the previous context is present enough to have them)
        try:
            prev_job_context, _ = self._load_state(job, sequence_num)
            if not job_context[PII_SECRET]:
                job_context[PII_SECRET] = prev_job_context[PII_SECRET]
            if not job_context[UPLOAD_URL]:
                job_context[UPLOAD_URL] = prev_job_context[UPLOAD_URL]
        except (ValueError, AttributeError):
            pass

        # Convert data source context object to plain dict.
        data_source_class = _get_data_source_class_by_name(
            self._data_source_class_name)
        context_class = data_source_class.get_context_class()
        data_source_context_dict = context_class.save_to_dict(
            data_source_context)

        # Set job object state variables.
        now = datetime.datetime.utcnow()
        job.output = transforms.dumps({
            'job_context': job_context,
            'data_source_context': data_source_context_dict,
            })
        job.status_code = state
        job.execution_time_sec += int((now - job.updated_on).total_seconds())
        job.updated_on = now

        logging.info('Data pump job %s saving contexts: %s %s',
                     self._job_name, str(job_context), str(data_source_context))

        # Using _update in DurableJobEntity
        # pylint: disable=protected-access
        if use_transaction:
            xg_on = db.create_transaction_options(xg=True)
            db.run_in_transaction_options(
                xg_on, jobs.DurableJobEntity._update, self._job_name,
                sequence_num, job.status_code, job.output)
        else:
            jobs.DurableJobEntity._update(self._job_name, sequence_num,
                                          job.status_code, job.output)

    @classmethod
    def _parse_pii_encryption_token(cls, token):
        parts = token.split('/')
        return (parts[0],
                datetime.datetime(year=1970, month=1, day=1) +
                datetime.timedelta(seconds=int(parts[1])))

    @classmethod
    def _is_pii_encryption_token_valid(cls, token):
        try:
            _, valid_until_date = cls._parse_pii_encryption_token(token)
            return valid_until_date > datetime.datetime.utcnow()
        except ValueError:
            return False

    @classmethod
    def _build_new_pii_encryption_token(cls, timedelta_string):
        hmac_secret = base64.urlsafe_b64encode(
            os.urandom(int(PII_SECRET_LENGTH * 0.75)))
        table_lifetime_seconds = common_utils.parse_timedelta_string(
            timedelta_string).total_seconds()
        unix_epoch = datetime.datetime(year=1970, month=1, day=1)
        now = datetime.datetime.utcnow()
        table_lifetime_timedelta = datetime.timedelta(
            seconds=table_lifetime_seconds)
        valid_until_timestamp = int(
            (now - unix_epoch + table_lifetime_timedelta).total_seconds())
        pii_encryption_token = '%s/%d' % (hmac_secret,
                                          valid_until_timestamp)
        return pii_encryption_token

    @classmethod
    def _get_pii_token(cls, app_context):
        """Retrieve or generate and save a secret used to encrypt exported PII.

        All PII data in objects exported to BigQuery is either suppressed
        or transformed via a one-way hash using a secret value.  The point
        of the transformation is so that exported data cannot trivially be
        correlated to any individual's data in CourseBuilder, but records
        in exported data encoded using the same key can.  (E.g., a user_id
        is the key for students; this key should be usable to correlate a
        user's language preference with his test scores.)

        Once data has been exported from CourseBuilder to BigQuery, the
        internal permissions from CourseBuilder no longer apply.  To minimize
        the ability of those with access to the data to perform long-term
        correlations that might identify individuals, the secret used to
        encode PII is automatically rotated on a period determined by the
        course settings.  We re-use the expiration period for tables, or
        default to 30 days if no period is selected.

        The format for the stored setting is a string composed of:
        - A randomly-generated secret encoded as a base-64 string
        - A slash character ('/')
        - A Unix timestamp indicating the expiration date of the token.

        The expiration date approach is chosen so that within the expiration
        period, different data sources can be re-exported multiple times, but
        still correlated with one another in BigQuery.  Upon expiration, a
        new token is generated and used.  Data exported before and after the
        changeover cannot be directly correlated.  (It may be possible to
        force a correlation if old versions of the data tables were downloaded
        by comparing non-key fields in the old/new versions, if the non-key
        fields are sufficiently discriminative)

        Args:
          app_context: Standard CB application context object.
        Returns:
          Secret string used for encoding PII data upon export.
        """
        course_settings = app_context.get_environ()
        pump_settings = course_settings.get(DATA_PUMP_SETTINGS_SCHEMA_SECTION,
                                            {})
        pii_encryption_token = pump_settings.get(PII_ENCRYPTION_TOKEN)
        if (not pii_encryption_token or
            not cls._is_pii_encryption_token_valid(pii_encryption_token)):
            # If table_lifetime is missing OR is set to the empty string,
            # prefer the default value.
            lifetime = (pump_settings.get(TABLE_LIFETIME) or
                        PII_SECRET_DEFAULT_LIFETIME)
            pii_encryption_token = cls._build_new_pii_encryption_token(lifetime)
            pump_settings[PII_ENCRYPTION_TOKEN] = pii_encryption_token
            course = courses.Course(None, app_context=app_context)
            course.save_settings(course_settings)
        return pii_encryption_token

    @classmethod
    def _get_pii_secret(cls, app_context):
        secret, _ = cls._parse_pii_encryption_token(
            cls._get_pii_token(app_context))
        return secret

    def _get_bigquery_settings(self, app_context):
        """Pull settings necessary for using BigQuery from DB.

        This is nice and verbose and paranoid, so that if there is any
        misconfiguration, the end-user gets a nice message that's specific
        about the particular problem, rather than just a KeyError or
        ValueError.

        Args:
          app_context: The standard app context for the course in question.
        Returns:
          A namedtuple containing private_key, client_email, project_id
          and dataset_id members.  The first three are required to connect
          to BigQuery, and the last is the dataset within BigQuery to
          which the data pump will restrict itself for insert/write/delete
          operations.
        Raises:
          ValueError: if any expected element is missing or malformed.
        """

        pump_settings = app_context.get_environ().get(
            DATA_PUMP_SETTINGS_SCHEMA_SECTION, {})
        dataset_id = (
            pump_settings.get(DATASET_NAME) or
            re.sub('[^0-9a-z_:-]', '', app_context.get_slug().lower()) or
            'course')
        project_id = pump_settings.get(PROJECT_ID)
        if not project_id:
            raise ValueError('Cannot pump data without a course settings value '
                             'for the target Google BigQuery project ID')

        json_key = pump_settings.get(JSON_KEY)
        if not json_key:
            raise ValueError('Cannot pump data without a JSON client key '
                             'allowing access to the target Google BigQuery '
                             'project')
        try:
            json_key = transforms.loads(json_key)
        except ValueError:
            raise ValueError('Cannot decode JSON client key for the target '
                             'Google BigQuery project.')
        if 'private_key' not in json_key or 'client_email' not in json_key:
            raise ValueError('The JSON client key for the target Google '
                             'BigQuery project does not seem to be well '
                             'formed; either the "private_key" or '
                             '"client_email" field is missing.')
        # If table_lifetime setting is missing OR is set to the empty string,
        # prefer the default value.
        table_lifetime_seconds = common_utils.parse_timedelta_string(
            pump_settings.get(TABLE_LIFETIME) or PII_SECRET_DEFAULT_LIFETIME
            ).total_seconds()
        Settings = collections.namedtuple('Settings', [
            'private_key', 'client_email', PROJECT_ID, 'dataset_id',
            'table_lifetime_seconds'])
        return Settings(json_key['private_key'], json_key['client_email'],
                        project_id, dataset_id, table_lifetime_seconds)

    def _get_bigquery_service(self, bigquery_settings):
        """Get BigQuery API client plus HTTP client with auth credentials."""
        credentials = oauth2client.client.SignedJwtAssertionCredentials(
            bigquery_settings.client_email, bigquery_settings.private_key,
            BIGQUERY_RW_SCOPE)
        http = httplib2.Http()
        http = credentials.authorize(http)

        # Discovery.build has a timeout that's a little too aggressive.  Since
        # this happens before we even have our job_context built, any errors
        # returned from here will be fatal.  Since that's the case, add some
        # extra forgiveness here by retrying several times, with a little bit
        # of wait thrown in to allow the discovery service to recover, in case
        # it really is just having a bad few moments.
        attempts = 0
        while True:
            try:
                return apiclient.discovery.build(
                    BIGQUERY_API_NAME, BIGQUERY_API_VERSION, http=http), http
            # pylint: disable=broad-except
            except Exception, ex:
                attempts += 1
                if attempts >= DISCOVERY_SERVICE_MAX_ATTEMPTS:
                    raise
                logging.warning(
                    'Ignoring HTTP connection timeout %d of %d',
                    attempts, DISCOVERY_SERVICE_MAX_ATTEMPTS)
                time.sleep(DISCOVERY_SERVICE_RETRY_SECONDS)

    def _maybe_create_course_dataset(self, service, bigquery_settings):
        """Create dataset within BigQuery if it's not already there."""
        datasets = service.datasets()
        try:
            datasets.get(projectId=bigquery_settings.project_id,
                         datasetId=bigquery_settings.dataset_id).execute()
        except apiclient.errors.HttpError, ex:
            if ex.resp.status != 404:
                raise
            datasets.insert(projectId=bigquery_settings.project_id,
                            body={
                                'datasetReference': {
                                    'projectId': bigquery_settings.project_id,
                                    'datasetId': bigquery_settings.dataset_id
                                    }}).execute()

    def _maybe_delete_previous_table(self, tables, bigquery_settings,
                                     data_source_class):
        """Delete previous version of table for data source, if it exists."""

        # TODO(mgainer): Make clobbering old table and replacing optional.
        # For now, we assume people will be writing queries in terms of
        # a single table name, and will be irritated at having to change
        # their queries all the time if we add a timestamp to the table
        # name.  And no, AFAICT, the BigQuery API does not permit renaming
        # of tables, just creation and deletion.
        table_name = data_source_class.get_name()
        try:
            tables.delete(projectId=bigquery_settings.project_id,
                          datasetId=bigquery_settings.dataset_id,
                          tableId=table_name).execute()
        except apiclient.errors.HttpError, ex:
            if ex.resp.status != 404:
                raise

    def _json_schema_member_to_bigquery_schema(self, name, structure):
        item = {'name': name}
        if 'description' in structure:
            item['description'] = structure['description']

        if 'properties' in structure:  # It's a sub-registry.
            item['type'] = 'RECORD'
            item['mode'] = 'NULLABLE'
            item['fields'] = self._json_schema_to_bigquery_schema(
                structure['properties'])
        elif 'items' in structure:  # It's an array
            if 'items' in structure['items']:
                raise ValueError(
                    'BigQuery schema descriptions do not support nesting '
                    'arrays directly in other arrays.  Instead, nest '
                    'structures in arrays; those structures may contain '
                    'sub-arrays.  Problem arises trying to pump data for %s' %
                    self._data_source_class_name)
            item = self._json_schema_member_to_bigquery_schema(
                name, structure['items'])
            item['mode'] = 'REPEATED'
        else:
            item['mode'] = ('NULLABLE' if structure.get('optional')
                            else 'REQUIRED')
            if structure['type'] in ('string', 'text', 'html', 'url', 'file'):
                item['type'] = 'STRING'
            elif structure['type'] in 'integer':
                item['type'] = 'INTEGER'
            elif structure['type'] in 'number':
                item['type'] = 'FLOAT'
            elif structure['type'] in 'boolean':
                item['type'] = 'BOOLEAN'
            elif structure['type'] in ('date', 'datetime', 'timestamp'):
                # BigQuery will accept ISO-formatted datetimes as well as
                # integer seconds-since-epoch as timestamps.
                item['type'] = 'TIMESTAMP'
            else:
                raise ValueError(
                    'Unrecognized schema scalar type "%s" '
                    'when trying to make schema for data-pumping %s' % (
                        structure['type'], self._data_source_class_name))
        return item

    def _json_schema_to_bigquery_schema(self, json_schema_dict):
        fields = []
        for name, structure in json_schema_dict.iteritems():
            fields.append(self._json_schema_member_to_bigquery_schema(
                name, structure))
        return fields

    def _create_data_table(self, tables, bigquery_settings, schema,
                           data_source_class):
        """Instantiate and provide schema for new BigQuery table."""

        table_name = data_source_class.get_name()
        request = {
            'kind': 'bigquery#table',
            'tableReference': {
                'projectId': bigquery_settings.project_id,
                'datasetId': bigquery_settings.dataset_id,
                'tableId': table_name,
                },
            'schema': {'fields': schema}
            }

        # If user has requested it, set the time at which table should be
        # reclaimed (as milliseconds since Unix epoch).
        if (bigquery_settings.table_lifetime_seconds and
            not self._no_expiration_date):

            now = datetime.datetime.utcnow()
            expiration_delta = datetime.timedelta(
                seconds=bigquery_settings.table_lifetime_seconds)
            unix_epoch = datetime.datetime(year=1970, month=1, day=1)
            expiration_ms = int(
                (now + expiration_delta - unix_epoch).total_seconds()) * 1000
            request['expirationTime'] = expiration_ms

        # Allow exceptions from here to propagate; we don't expect any problems,
        # so if we have any, the upload should abort.
        tables.insert(
            projectId=bigquery_settings.project_id,
            datasetId=bigquery_settings.dataset_id,
            body=request).execute()

    def _create_upload_job(self, http, bigquery_settings, data_source_class):
        """Before uploading, we must create a job to handle the upload.

        Args:
          http: An HTTP client object configured to send our auth token
          bigquery_settings: Configs for talking to bigquery.
        Returns:
          URL specific to this upload job.  Subsequent PUT requests to send
          pages of data must be sent to this URL.
        Raises:
          Exception: on unexpected responses from BigQuery API.
        """

        uri = '%s%s/jobs?uploadType=resumable' % (
            BIGQUERY_API_UPLOAD_URL_PREFIX, bigquery_settings.project_id)
        headers = {
            'Content-Type': 'application/json',
            'X-Upload-Content-Type': 'application/octet-stream',
            }
        table_name = data_source_class.get_name()
        body = transforms.dumps({
            'kind': 'bigquery#job',
            'configuration': {
                'load': {
                    'createDisposition': 'CREATE_NEVER',  # Already exists.
                    'destinationTable': {
                        'projectId': bigquery_settings.project_id,
                        'datasetId': bigquery_settings.dataset_id,
                        'tableId': table_name,
                        },
                    'ignoreUnknownValues': False,
                    'sourceFormat': 'NEWLINE_DELIMITED_JSON',
                    }
                }
            })
        response, content = http.request(uri, method='POST',
                                         body=body, headers=headers)
        if int(response.get('status', 0)) != 200:
            raise Exception('Got non-200 response when trying to create a '
                            'new upload job.  Reponse was: "%s"; content '
                            'was "%s"' % (str(response), str(content)))
        location = response.get('location')
        if not location:
            raise Exception('Expected response to contain a "location" item '
                            'giving a URL to send subsequent content to, but '
                            'instead got "%s"' % str(response))
        return location

    def _initiate_upload_job(self, bigquery_service, bigquery_settings, http,
                             app_context, data_source_context):
        """Coordinate table cleanup, setup, and initiation of upload job."""
        data_source_class = _get_data_source_class_by_name(
            self._data_source_class_name)
        catch_and_log_ = catch_and_log.CatchAndLog()
        table_schema = data_source_class.get_schema(app_context, catch_and_log_,
                                                    data_source_context)
        schema = self._json_schema_to_bigquery_schema(table_schema)
        tables = bigquery_service.tables()

        self._maybe_create_course_dataset(bigquery_service, bigquery_settings)
        self._maybe_delete_previous_table(tables, bigquery_settings,
                                          data_source_class)
        self._create_data_table(tables, bigquery_settings, schema,
                                data_source_class)
        upload_url = self._create_upload_job(http, bigquery_settings,
                                             data_source_class)
        return upload_url

    def _note_retryable_failure(self, message, job_context):
        """Log a timestamped message into the job context object."""
        timestamp = datetime.datetime.utcnow().strftime(
            utils.HUMAN_READABLE_DATETIME_FORMAT)
        job_context[CONSECUTIVE_FAILURES].append(timestamp + ' ' + message)

    def _randomized_backoff_timeout(self, job_context):
        num_failures = len(job_context[CONSECUTIVE_FAILURES])
        if not num_failures:
            return 0
        return min(MAX_RETRY_BACKOFF_SECONDS,
                   random.randrange(2 ** num_failures, 2 ** (num_failures + 1)))

    def _check_upload_state(self, http, job_context):
        """Check with the BigQuery upload server to get state of our upload.

        Due to various communication failure cases, we may not be aware of
        the actual state of the upload as known to the server.  Issue a blank
        PUT request to evoke a response that will indicate:
        - How far along we are in the upload
        - Whether the upload has already completed
        - Whether the upload job has taken too long and expired

        Args:
          http: An HTTP client object configured to send our auth token
          job_context: Hash containing configuration for this upload job.
        Returns:
          A 2-tuple of next page to load (or None if no page should be
          loaded), and the next jobs.STATUS_CODE_<X> to transition to.
        """

        response, _ = http.request(job_context[UPLOAD_URL], method='PUT',
                                   headers={'Content-Range': 'bytes */*'})
        return self._handle_put_response(response, job_context, is_upload=False)

    def _send_data_page_to_bigquery(self, data, is_last_chunk, next_page,
                                    http, job, sequence_num, job_context,
                                    data_source_context):
        if next_page == 0 and is_last_chunk and not data:
            return jobs.STATUS_CODE_COMPLETED

        # BigQuery expects one JSON object per newline-delimed record,
        # not a JSON array containing objects, so convert them individually.
        # Less efficient, but less hacky than converting and then string
        # manipulation.
        lines = []
        total_len = 0
        for item in data:
            line = transforms.dumps(item)
            line += '\n'
            total_len += len(line)
            lines.append(line)

        # Round data size up to next multiple of 256K, per
        # https://cloud.google.com/bigquery/loading-data-post-request#chunking
        padding_amount = 0
        if not is_last_chunk:
            round_to = 256 * 1024
            if total_len % round_to:
                padding_amount = round_to - (total_len % round_to)
                lines.append(' ' * padding_amount)
        payload = ''.join(lines)

        # We are either re-attempting to send a page, or sending a new page.
        # Adjust the job_context's last-sent state to reflect this.
        job_context[LAST_PAGE_NUM_ITEMS] = len(data)
        if next_page == job_context[LAST_PAGE_SENT]:
            job_context[LAST_END_OFFSET] = (
                job_context[LAST_START_OFFSET] + len(payload) - 1)
        elif next_page == job_context[LAST_PAGE_SENT] + 1:
            job_context[LAST_PAGE_SENT] = next_page
            job_context[LAST_START_OFFSET] = (
                job_context[LAST_END_OFFSET] + 1)
            job_context[LAST_END_OFFSET] = (
                job_context[LAST_START_OFFSET] + len(payload) - 1)
        else:
            raise Exception(
                'Internal error - unexpected condition in sending page.  '
                'next_page=%d last_page=%d, num_items=%d' % (
                    next_page, job_context[LAST_PAGE_SENT], len(data)))

        logging.info(
            'Sending to BigQuery.  %d items; %d padding bytes; is-last: %s',
            len(data), padding_amount, str(is_last_chunk))
        headers = {
            'Content-Range': 'bytes %d-%d/%s' % (
                job_context[LAST_START_OFFSET],
                job_context[LAST_END_OFFSET],
                (job_context[LAST_END_OFFSET] + 1) if is_last_chunk else '*')
            }

        response, _ = http.request(job_context[UPLOAD_URL], method='PUT',
                                   body=payload, headers=headers)
        _, next_state = self._handle_put_response(response, job_context,
                                                  is_upload=True)
        return next_state

    def _handle_put_response(self, response, job_context, is_upload=True):
        """Update job_context state depending on response from BigQuery."""
        status = int(response['status'])
        logging.info('Response from bigquery: %d; %s', status, str(response))
        next_page = None
        next_status = jobs.STATUS_CODE_STARTED
        if status == 308:
            # Google's push-partial-data usurps the usual meaning of 308 to
            # instead mean "partial request incomplete"; here, it's telling
            # us that the request has partially completed, and it will give
            # us a Range: header to indicate how far it thinks we've gone.
            # We only care about the upper end of the range.
            if 'range' not in response:
                last_offset_received = -1
            else:
                last_offset_received = int(response['range'].split('-')[1])

            if last_offset_received == job_context[LAST_END_OFFSET]:
                # The nominal case; the reported index of the last byte
                # received exactly matches what we think we sent.  Tell our
                # caller we are ready to try the next page, and count up
                # the total number of items sent only now that we have seen
                # the receiving side's acknowledgement.
                next_page = job_context[LAST_PAGE_SENT] + 1
                job_context[ITEMS_UPLOADED] += job_context[LAST_PAGE_NUM_ITEMS]
                job_context[LAST_PAGE_NUM_ITEMS] = 0

                # Don't clear the list of failures if this is handling the
                # pre-check done before uploading.  Experiments show that
                # persistent problems with our requests result in 503's on
                # upload, but 308's (reporting no progress made) on check.
                # We want to eventually fail out if we're constantly getting
                # errors, so ignore the "success" on checking status.
                if is_upload:
                    job_context[CONSECUTIVE_FAILURES] = []

            elif (last_offset_received >= job_context[LAST_START_OFFSET] - 1 and
                  last_offset_received < job_context[LAST_END_OFFSET]):
                # If the last offset received is not the same as the last offset
                # sent, that's possibly OK; verify that the last offset received
                # is sane.  Here, "sane" means that we accept seeing the
                # last offset of the previous page sent (last_start_offset-1)
                # up to, but not including the last_end_offset (for the page
                # we just sent).  Anything lower means that our algorithm
                # mistakenly skipped past a failure.  Anything higher means
                # that we have somehow become confused and decided to step
                # backward (or BigQuery is lying to us).
                prev_page_size = (job_context[LAST_END_OFFSET] -
                                  job_context[LAST_START_OFFSET] + 1)
                bytes_received = (last_offset_received -
                                  job_context[LAST_START_OFFSET] + 1)
                self._note_retryable_failure(
                    'Incomplete upload detected - %d of %d bytes received '
                    'for page %d' %
                    (bytes_received, prev_page_size,
                     job_context[LAST_PAGE_SENT]), job_context)
                next_page = job_context[LAST_PAGE_SENT]

            else:
                raise ValueError(
                    'Uploaded byte count of %d does not fall in the range '
                    '%d to %d, the start/end range for previously-sent page '
                    'number %d.  Abandoning upload.' % (
                        last_offset_received, job_context[LAST_START_OFFSET],
                        job_context[LAST_END_OFFSET],
                        job_context[LAST_PAGE_SENT]))

        elif status in (200, 201):
            # BigQuery confirms that it has seen the upload complete.  (Note
            # that this is *not* a promise that the upload has parsed
            # correctly; there doesn't seem to be a clean way to ask about
            # that other than to probe the table for number of rows uploaded
            # until we see the desired number or time out.  Ick.)
            job_context[ITEMS_UPLOADED] += job_context[LAST_PAGE_NUM_ITEMS]
            job_context[LAST_PAGE_NUM_ITEMS] = 0
            next_status = jobs.STATUS_CODE_COMPLETED

        elif status == 404:
            # Unlikely, but possible.  For whatever reason, BigQuery has
            # decided that our upload URL is no longer valid.  (Docs say that
            # we are allowed up to a day to get an upload done, but do not
            # promise that this is the only reason a job may become invalid.)
            # We need to start again from scratch.  To start over, we will
            # just skip uploading a data page this round, and set ourselves up
            # to be called back again from the deferred-tasks queue.  When the
            # callback happens, STATUS_CODE_QUEUED will indicate we need to
            # re-init everything from scratch.
            next_status = jobs.STATUS_CODE_QUEUED

        elif status in (500, 502, 503, 504):
            # Server Error, Bad Gateway, Service Unavailable or Gateway Timeout.
            # In all of these cases, we do a randomized exponential delay before
            # retrying.
            self._note_retryable_failure('Retryable server error %d' % status,
                                         job_context)
        else:
            raise ValueError(
                'Got unexpected status code %d from BigQuery in response %s' %
                (status, str(response)))
        return next_page, next_status

    def _fetch_page_data(self, app_context, data_source_context, next_page):
        """Get the next page of data from the data source."""

        data_source_class = _get_data_source_class_by_name(
            self._data_source_class_name)
        catch_and_log_ = catch_and_log.CatchAndLog()
        is_last_page = False
        with catch_and_log_.propagate_exceptions('Loading page of data'):
            schema = data_source_class.get_schema(app_context, catch_and_log_,
                                                  data_source_context)
            required_jobs = data_sources.utils.get_required_jobs(
                data_source_class, app_context, catch_and_log_)
            data, _ = data_source_class.fetch_values(
                app_context, data_source_context, schema, catch_and_log_,
                next_page, *required_jobs)

            # BigQuery has a somewhat unfortunate design: It does not attempt
            # to parse/validate the data we send until all data has been
            # uploaded and the upload has been declared a "success".  Rather
            # than having to poll for an indefinite amount of time until the
            # upload is parsed, we validate that the sent items exactly match
            # the declared schema.  Somewhat expensive, but better than having
            # completely unreported hidden failures.
            for index, item in enumerate(data):
                complaints = transforms.validate_object_matches_json_schema(
                    item, schema)
                if complaints:
                    raise ValueError(
                        'Data in item to pump does not match schema!  ' +
                        'Item is item number %d ' % index +
                        'on data page %d. ' % next_page +
                        'Problems for this item are:\n' +
                        '\n'.join(complaints))

            if (data_source_class.get_default_chunk_size() == 0 or
                not hasattr(data_source_context, 'chunk_size') or
                len(data) < data_source_context.chunk_size):
                is_last_page = True
            else:
                # Here, we may have read to the end of the table and just
                # happened to end up on an even chunk boundary.  Attempt to
                # read one more row so that we can discern whether we really
                # are at the end.

                # Don't use the normal data_source_context; we don't want it
                # to cache a cursor for the next page that will only retrieve
                # one row.
                throwaway_context = copy.deepcopy(data_source_context)
                throwaway_context.chunk_size = 1
                next_data, actual_page = data_source_class.fetch_values(
                    app_context, throwaway_context, schema, catch_and_log_,
                    next_page + 1, *required_jobs)
                if not next_data or actual_page == next_page:
                    is_last_page = True
            return data, is_last_page

    def _send_next_page(self, sequence_num, job):
        """Coordinate table setup, job setup, sending pages of data."""

        # Gather necessary resources
        app_context = sites.get_course_index().get_app_context_for_namespace(
            self._namespace)
        pii_secret = self._get_pii_secret(app_context)
        bigquery_settings = self._get_bigquery_settings(app_context)
        bigquery_service, http = self._get_bigquery_service(bigquery_settings)

        # If this is our first call after job start (or we have determined
        # that we need to start over from scratch), do initial setup.
        # Otherwise, re-load context objects from saved version in job.output
        if job.status_code == jobs.STATUS_CODE_QUEUED:
            data_source_context = self._build_data_source_context()
            upload_url = self._initiate_upload_job(
                bigquery_service, bigquery_settings, http, app_context,
                data_source_context)
            job_context = self._build_job_context(upload_url, pii_secret)
        else:
            job_context, data_source_context = self._load_state(
                job, sequence_num)
        if hasattr(data_source_context, 'pii_secret'):
            data_source_context.pii_secret = pii_secret
        if self._send_uncensored_pii_data:
            data_source_context.send_uncensored_pii_data = True
        logging.info('Data pump job %s loaded contexts: %s %s',
                     self._job_name, str(job_context), str(data_source_context))

        # Check BigQuery's state.  Based on that, choose the next page of data
        # to push.  Depending on BigQuery's response, we may or may not be
        # able to send a page now.
        next_page, next_state = self._check_upload_state(http, job_context)
        if next_page is not None:
            data, is_last_chunk = self._fetch_page_data(
                app_context, data_source_context, next_page)
            next_state = self._send_data_page_to_bigquery(
                data, is_last_chunk, next_page,
                http, job, sequence_num, job_context, data_source_context)
        self._save_state(next_state, job, sequence_num, job_context,
                         data_source_context)

        # If we are not done, enqueue another to-do item on the deferred queue.
        if len(job_context[CONSECUTIVE_FAILURES]) >= MAX_CONSECUTIVE_FAILURES:
            raise Exception('Too many consecutive failures; abandoning job.')
        elif not job.has_finished:
            backoff_seconds = self._randomized_backoff_timeout(job_context)
            logging.info('%s re-queueing for subsequent work', self._job_name)
            deferred.defer(self.main, sequence_num, _countdown=backoff_seconds)
        else:
            logging.info('%s complete', self._job_name)

    def main(self, sequence_num):
        """Callback entry point.  Manage namespaces, failures; send data."""
        logging.info('%s de-queued and starting work.', self._job_name)
        job = self.load()
        if not job:
            raise deferred.PermanentTaskFailure(
                'Job object for %s not found!' % self._job_name)
        if job.has_finished:
            return  # We have been canceled; bail out immediately.
        with common_utils.Namespace(self._namespace):
            try:
                self._send_next_page(sequence_num, job)
            except Exception, ex:
                common_utils.log_exception_origin()
                logging.critical('%s: job abandoned due to fatal error %s',
                                 self._job_name, str(ex))

                # Log failure in job object as well.
                if job.output:
                    job_context, data_source_context = self._load_state(
                        job, sequence_num)
                else:
                    job_context = self._build_job_context(None, None)
                    data_source_context = (self._build_data_source_context())
                job_context[FAILURE_REASON] = str(ex)
                self._save_state(jobs.STATUS_CODE_FAILED, job, sequence_num,
                                 job_context, data_source_context)

                # PermanentTaskFailure tells deferred queue to give up on us.
                raise deferred.PermanentTaskFailure('Job %s failed: %s' % (
                    self._job_name, str(ex)))

    def get_display_dict(self, app_context):
        """Set up dict for Jinja rendering on data_pump.html."""
        data_source_context = self._build_data_source_context()
        data_source_class = _get_data_source_class_by_name(
            self._data_source_class_name)
        ret = {
            'name': self._data_source_class_name,
            'title': data_source_class.get_title(),
            'status': 'Has Never Run',
            'active': False,
            }

        job = self.load()
        if job:
            ret['status'] = jobs.STATUS_CODE_DESCRIPTION[job.status_code]
            ret['active'] = not job.has_finished
            ret['sequence_number'] = job.sequence_num
            ret['updated_on'] = job.updated_on.strftime(
                utils.HUMAN_READABLE_TIME_FORMAT)
            if job.has_finished:
                duration = job.execution_time_sec
            else:
                duration = int((datetime.datetime.utcnow() -
                                job.updated_on) .total_seconds())
            ret['duration'] = datetime.timedelta(days=0, seconds=duration)
            ret['last_updated'] = job.updated_on.strftime(
                utils.HUMAN_READABLE_DATETIME_FORMAT)
            bigquery_settings = self._get_bigquery_settings(app_context)
            ret['bigquery_url'] = '%s%s:%s.%s' % (
                BIGQUERY_UI_URL_PREFIX, bigquery_settings.project_id,
                bigquery_settings.dataset_id, data_source_class.get_name())
            try:
                job_context, data_source_context = self._load_state(
                    job, job.sequence_num)
                ret['job_context'] = job_context
                current_secret = DataPumpJob._get_pii_secret(app_context)
                if job_context[PII_SECRET] != current_secret:
                    ret['pii_secret_is_out_of_date'] = True
                del job_context[PII_SECRET]

            except (ValueError, AttributeError):
                # When jobs framework catches a failure, it overwrites the
                # job.output with the failure message as a string.  We will
                # get here if we fail to parse job.output as a JSON-packed
                # object.
                ret['message'] = job.output

        ret['source_url'] = '%s/rest/data/%s/items?chunk_size=10' % (
            app_context.get_slug(), data_source_class.get_name())
        catch_and_log_ = catch_and_log.CatchAndLog()
        ret['schema'] = data_source_class.get_schema(
            app_context, catch_and_log_, data_source_context)
        ret['generator_statuses'] = []
        ret['available'] = True
        ret['any_generator_running'] = False
        required_generators = data_source_class.required_generators()
        if not required_generators:
            ret['generator_statuses'].append(
                {'message': '(No dependencies)', 'link': None})
            ret['has_any_generators'] = False
        else:
            ret['has_any_generators'] = True

        for generator_class in required_generators:
            generator = generator_class(app_context)
            job = generator.load()
            message = analytics.display.get_generator_status_message(
                generator_class, job)
            link = analytics.display.get_pipeline_link(
                crypto.XsrfTokenManager, app_context, generator_class, job)
            ret['generator_statuses'].append({'message': message, 'link': link})
            if not job or job.status_code != jobs.STATUS_CODE_COMPLETED:
                ret['available'] = False
            if job and not job.has_finished:
                ret['any_generator_running'] = True
        return ret


class DataPumpJobsDataSource(data_sources.SynchronousQuery):
    """Present DataPump job status as an analytic generated at page-render time.

    This is a very mild hack.  Since the data pump job controls show up as a
    sub-tab under Dashboard -> Analytics, the easiest way to generate tab
    content is to act as though we are an analytic.  And we are, in a sense -
    this analytic just happens to generate a table of data-pump job statuses,
    rather than analytics about student performance.  This also conveniently
    re-uses all the mechanics for authorization, dispatch, page-painting, etc.
    """

    @staticmethod
    def required_generators():
        return []

    @staticmethod
    def fill_values(app_context, template_values):
        template_values['xsrf_token'] = (
            crypto.XsrfTokenManager.create_xsrf_token(XSRF_ACTION_NAME))
        template_values['exit_url'] = urllib.urlencode({
            'exit_url': 'dashboard?%s' % urllib.urlencode({
                'action': DASHBOARD_ACTION})})
        source_classes = [
          ds for ds in data_sources.Registry.get_rest_data_source_classes()
          if ds.exportable()]
        source_classes.sort(key=lambda c: c.get_title())
        # pylint: disable=protected-access
        template_values['pumps'] = []
        for source_class in source_classes:
            job = DataPumpJob(app_context, source_class.__name__)
            template_values['pumps'].append(job.get_display_dict(app_context))

        pump_settings = app_context.get_environ().get(
            DATA_PUMP_SETTINGS_SCHEMA_SECTION, {})
        template_values['need_settings'] = (
            not pump_settings.has_key(PROJECT_ID) or
            not pump_settings.has_key(JSON_KEY))
        # If table_lifetime setting is missing OR is set to the empty string,
        # prefer the default value.
        template_values['default_lifetime'] = (
            pump_settings.get(TABLE_LIFETIME) or PII_SECRET_DEFAULT_LIFETIME)
        template_values[DATASET_NAME] = (
            pump_settings.get(DATASET_NAME) or
            re.sub('[^0-9a-z_:-]', '', app_context.get_slug().lower()) or
            'course')


custom_module = None


class DashboardExtension(object):
    """Respond to UI run/cancel commands for individual data pump jobs."""

    @classmethod
    def register(cls):
        # Register a new Analytics sub-tab for showing data pump status and
        # start/stop buttons.
        data_pump_visualization = analytics.Visualization(
            MODULE_NAME, MODULE_TITLE, 'data_pump.html',
            data_source_classes=[DataPumpJobsDataSource])
        dashboard.DashboardHandler.add_sub_nav_mapping(
            'analytics', MODULE_NAME, MODULE_TITLE,
            action=DASHBOARD_ACTION,
            contents=analytics.TabRenderer([data_pump_visualization]),
            placement=1000, sub_group_name=MODULE_NAME)

        def post_action(handler):
            cls(handler).post_data_pump()
        dashboard.DashboardHandler.post_actions.append(DASHBOARD_ACTION)
        setattr(dashboard.DashboardHandler, 'post_%s' % DASHBOARD_ACTION,
                post_action)

    @classmethod
    def unregister(cls):
        dashboard.DashboardHandler.post_actions.remove(DASHBOARD_ACTION)
        setattr(dashboard.DashboardHandler, 'post_%s' % DASHBOARD_ACTION, None)

    def post_data_pump(self):
        source_name = self.handler.request.get('data_source')
        data_source_class = _get_data_source_class_by_name(source_name)
        if data_source_class:
            action = self.handler.request.get('pump_action')
            data_pump_job = DataPumpJob(
                self.handler.app_context, source_name,
                self.handler.request.get('no_expiration_date') == 'True',
                self.handler.request.get('send_uncensored_pii_data') == 'True')
            if action == 'start_pump':
                data_pump_job.submit()
            elif action == 'cancel_pump':
                data_pump_job.cancel()
            elif action == 'run_generators':
                for generator_class in data_source_class.required_generators():
                    generator_class(self.handler.app_context).submit()
            elif action == 'cancel_generators':
                for generator_class in data_source_class.required_generators():
                    generator_class(self.handler.app_context).cancel()
        self.handler.redirect(self.handler.get_action_url(
            DASHBOARD_ACTION, fragment=source_name))

    def __init__(self, handler):
        self.handler = handler


def register_module():
    """Adds this module to the registry.  Called once at startup."""

    def validate_project_id(value, errors):
        if not value:
            return
        if not re.match('^[a-z][-a-z0-9]{4,61}[a-z0-9]$', value):
            errors.append(
                'Project IDs must contain 6-63 lowercase letters, digits, '
                'or dashes. IDs must start with a letter and may not end '
                'with a dash.')

    _project_id_name = DATA_PUMP_SETTINGS_SCHEMA_SECTION + ':' + PROJECT_ID
    project_id = schema_fields.SchemaField(
        _project_id_name, 'Project ID', 'string',
        description=services.help_urls.make_learn_more_message(
            messages.PROJECT_ID, _project_id_name), i18n=False,
        validator=validate_project_id)
    dataset_name = schema_fields.SchemaField(
        DATA_PUMP_SETTINGS_SCHEMA_SECTION + ':' + DATASET_NAME,
        'Dataset Name', 'string', description=messages.DATASET_NAME,
        optional=True, i18n=False)

    def validate_json_key(json_key, errors):
        if not json_key:
            return
        try:
            json_key = transforms.loads(json_key or '')
            if 'private_key' not in json_key or 'client_email' not in json_key:
                errors.append(
                    'The JSON client key for allowing access to push data '
                    'to BigQuery is missing either the "private_key" or '
                    '"client_email" field (or both).  Please check that you '
                    'have copied the entire contents of the JSON key file '
                    'you downloaded using the Credentials screen in the '
                    'Google Developers Console.')
        except ValueError, ex:
            errors.append(
                'The JSON key field doesn\'t seem to contain valid JSON.  '
                'Please check that you have copied all of the content of the '
                'JSON file you downloaded using the Credentials screen in the '
                'Google Developers Console.  Also, be sure that you are '
                'pasting in the JSON version, not the .p12 (PKCS12) file.' +
                str(ex))

    _json_key_name = DATA_PUMP_SETTINGS_SCHEMA_SECTION + ':' + JSON_KEY
    json_key = schema_fields.SchemaField(
        _json_key_name, 'JSON Key', 'text',
        description=services.help_urls.make_learn_more_message(
            messages.JSON_KEY, _json_key_name), i18n=False,
        validator=validate_json_key)

    def validate_table_lifetime(value, errors):
        if not value:
            return
        seconds = common_utils.parse_timedelta_string(value).total_seconds()
        if not seconds:
            errors.append(
                'The string "%s" ' % value +
                'has some problems; please check the instructions below '
                'the field for instructions on accepted formats.')

    _table_lifetime_name = (
        DATA_PUMP_SETTINGS_SCHEMA_SECTION + ':' + TABLE_LIFETIME)
    table_lifetime = schema_fields.SchemaField(
        _table_lifetime_name, 'Table Lifetime', 'string', optional=True,
        i18n=False, validator=validate_table_lifetime,
        description=services.help_urls.make_learn_more_message(
            messages.TABLE_LIFETIME, _table_lifetime_name))

    _pii_encryption_token_name = (
        DATA_PUMP_SETTINGS_SCHEMA_SECTION + ':' + PII_ENCRYPTION_TOKEN)
    pii_encryption_token = schema_fields.SchemaField(
        _pii_encryption_token_name, 'PII Encryption Token', 'string',
        optional=True, i18n=False, editable=False,
        description=services.help_urls.make_learn_more_message(
            messages.PII_ENCRYPTION_TOKEN, _pii_encryption_token_name))

    course_settings_fields = (
        lambda c: project_id,
        lambda c: json_key,
        lambda c: dataset_name,
        lambda c: table_lifetime,
        lambda c: pii_encryption_token,
        )

    def on_module_enabled():
        data_sources.Registry.register(DataPumpJobsDataSource)
        courses.Course.OPTIONS_SCHEMA_PROVIDERS[
            DATA_PUMP_SETTINGS_SCHEMA_SECTION] += course_settings_fields
        settings.CourseSettingsHandler.register_settings_section(
            DATA_PUMP_SETTINGS_SCHEMA_SECTION)
        DashboardExtension.register()

    def on_module_disabled():
        for field in course_settings_fields:
            courses.Course.OPTIONS_SCHEMA_PROVIDERS[
                DATA_PUMP_SETTINGS_SCHEMA_SECTION].remove(field)
        DashboardExtension.unregister()

    global custom_module  # pylint: disable=global-statement
    custom_module = custom_modules.Module(
        MODULE_TITLE, 'Pushes DB and generated content to a BigQuery project',
        [], [],
        notify_module_enabled=on_module_enabled,
        notify_module_disabled=on_module_disabled)
    return custom_module


# Since this module contains a registry which may be populated from other
# modules, we here import 'main' so that we are ensured that by the time this
# module is loaded, the global code in 'main' has been run (either by this
# import, or prior).  Note that we must do this import strictly after we
# declare register_module(): If this import actually runs the code in main,
# this module must have declared its own register_module() method so that the
# the registration code can see it.
# pylint: disable=unused-import
import main
