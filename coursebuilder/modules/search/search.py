# Copyright 2013 Google Inc. All Rights Reserved.
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

"""Search module that uses Google App Engine's full text search."""

__author__ = 'Ellis Michael (emichael@google.com)'

import collections
import gettext
import logging
import math
import mimetypes
import os
import time
import traceback

import jinja2
import resources
import webapp2

import appengine_config
from common import safe_dom
from controllers import sites
from controllers import utils
from models import config
from models import counters
from models import courses
from models import custom_modules
from models import jobs
from models import transforms

from google.appengine.api import namespace_manager
from google.appengine.api import search
from google.appengine.ext import db

MODULE_NAME = 'Full Text Search'

CAN_INDEX_ALL_COURSES_IN_CRON = config.ConfigProperty(
    'gcb_can_index_automatically', bool, safe_dom.Text(
        'Whether the search module can automatically index the course daily '
        'using a cron job. If enabled, this job would index the course '
        'incrementally so that only new items or items which have not been '
        'recently indexed are indexed.'),
    default_value=False)
SEARCH_QUERIES_MADE = counters.PerfCounter(
    'gcb-search-queries-made',
    'The number of student queries made to the search module.')
SEARCH_RESULTS_RETURNED = counters.PerfCounter(
    'gcb-search-results-returned',
    'The number of search results returned across all student queries.')
SEARCH_FAILURES = counters.PerfCounter(
    'gcb-search-failures',
    'The number of search failure messages returned across all student '
    'queries.')

INDEX_NAME = 'gcb_search_index'
RESULTS_LIMIT = 10
GCB_SEARCH_FOLDER_NAME = os.path.normpath('/modules/search/')

MAX_RETRIES = 5

# I18N: Message displayed on search results page when error occurs.
SEARCH_ERROR_TEXT = gettext.gettext('Search is currently unavailable.')


class ModuleDisabledException(Exception):
    """Exception thrown when the search module is disabled."""
    pass


def get_index(course):
    return search.Index(name=INDEX_NAME,
                        namespace=course.app_context.get_namespace_name())


def index_all_docs(course, incremental):
    """Index all of the docs for a given models.Course object.

    Args:
        course: models.courses.Course. the course to index.
        incremental: boolean. whether or not to index only new or out-of-date
            items.
    Returns:
        A dict with three keys.
        'num_indexed_docs' maps to an int, the number of documents added to the
            index.
        'doc_type' maps to a counter with resource types as keys mapping to the
            number of that resource added to the index.
        'indexing_time_secs' maps to a float representing the number of seconds
            the indexing job took.
    Raises:
        ModuleDisabledException: The search module is currently disabled.
    """

    if not custom_module.enabled:
        raise ModuleDisabledException('The search module is disabled.')

    start_time = time.time()
    index = get_index(course)
    timestamps, doc_types = (_get_index_metadata(index) if incremental
                             else ({}, {}))
    for doc in resources.generate_all_documents(course, timestamps):
        retry_count = 0
        while retry_count < MAX_RETRIES:
            try:
                index.put(doc)
                timestamps[doc.doc_id] = doc['date'][0].value
                doc_types[doc.doc_id] = doc['type'][0].value
                break
            except search.Error, e:
                if e.results[0].code == search.OperationResult.TRANSIENT_ERROR:
                    retry_count += 1
                    if retry_count >= MAX_RETRIES:
                        logging.error(
                            'Multiple transient errors indexing doc_id: %s',
                            doc.doc_id)
                else:
                    logging.error('Failed to index doc_id: %s', doc.doc_id)
                    break

    total_time = '%.2f' % (time.time() - start_time)
    indexed_doc_types = collections.Counter()
    for type_name in doc_types.values():
        indexed_doc_types[type_name] += 1
    return {'num_indexed_docs': len(timestamps),
            'doc_types': indexed_doc_types,
            'indexing_time_secs': total_time}


def clear_index(course):
    """Delete all docs in the index for a given models.Course object."""

    if not custom_module.enabled:
        raise ModuleDisabledException('The search module is disabled.')

    index = get_index(course)
    doc_ids = [document.doc_id for document in index.get_range(ids_only=True)]
    total_docs = len(doc_ids)
    while doc_ids:
        index.delete(doc_ids)
        doc_ids = [document.doc_id
                   for document in index.get_range(ids_only=True)]
    return {'deleted_docs': total_docs}


def _get_index_metadata(index):
    """Returns dict from doc_id to timestamp and one from doc_id to doc_type."""

    timestamps = []
    doc_types = []
    cursor = search.Cursor()
    while cursor:
        options = search.QueryOptions(
            limit=1000,
            cursor=cursor,
            returned_fields=['date', 'type'])
        query = search.Query(query_string='', options=options)
        current_docs = index.search(query)
        cursor = current_docs.cursor
        for doc in current_docs:
            timestamps.append((doc.doc_id, doc['date'][0].value))
            doc_types.append((doc.doc_id, doc['type'][0].value))
    return dict(timestamps), dict(doc_types)


def fetch(course, query_string, offset=0, limit=RESULTS_LIMIT):
    """Return an HTML fragment with the results of a search for query_string.

    Args:
        course: models.courses.Course. the course to search.
        query_string: str. the user's specified query.
        offset: int. the number of results to skip.
        limit: int. the number of results to return.
    Returns:
        A dict with two keys.
        'results' maps to an ordered list of resources.Result objects.
        'total_found' maps to the total number of results in the index which
            match query_string.
    Raises:
        ModuleDisabledException: The search module is currently disabled.
    """

    if not custom_module.enabled:
        raise ModuleDisabledException('The search module is disabled.')

    index = get_index(course)

    try:
        # TODO(emichael): Don't compute these for every query
        returned_fields = resources.get_returned_fields()
        snippeted_fields = resources.get_snippeted_fields()
        options = search.QueryOptions(
            limit=limit,
            offset=offset,
            returned_fields=returned_fields,
            number_found_accuracy=100,
            snippeted_fields=snippeted_fields)
        query = search.Query(query_string=query_string, options=options)
        results = index.search(query)
    except search.Error:
        logging.info('Failed searching for: %s', query_string)
        return {'results': None, 'total_found': 0}

    processed_results = resources.process_results(results)
    return {'results': processed_results, 'total_found': results.number_found}


class SearchHandler(utils.BaseHandler):
    """Handler for generating the search results page."""

    def get(self):
        """Process GET request."""
        # TODO(emichael): move timing to Javascript

        if not custom_module.enabled:
            self.error(404)
            return

        student = self.personalize_page_and_get_enrolled(
            supports_transient_student=True)
        if not student:
            return

        try:
            start = time.time()
            # TODO(emichael): Don't use get because it can't handle utf-8
            query = self.request.get('query')
            offset = self.request.get('offset')

            self.template_value['navbar'] = {}
            if query:
                try:
                    offset = int(offset)
                except (ValueError, TypeError):
                    offset = 0
                self.template_value['query'] = query
                SEARCH_QUERIES_MADE.inc()
                response = fetch(self.get_course(), query, offset=offset)
                response = self.filter(response, student)

                self.template_value['time'] = '%.2f' % (time.time() - start)
                self.template_value['search_results'] = response['results']

                total_found = response['total_found']
                if offset + RESULTS_LIMIT < total_found:
                    self.template_value['next_link'] = (
                        'search?query=%s&offset=%d' %
                        (query, offset + RESULTS_LIMIT))
                if offset - RESULTS_LIMIT >= 0:
                    self.template_value['previous_link'] = (
                        'search?query=%s&offset=%d' %
                        (query, offset - RESULTS_LIMIT))
                self.template_value['page_number'] = offset / RESULTS_LIMIT + 1
                self.template_value['total_pages'] = int(math.ceil(
                    float(total_found) / RESULTS_LIMIT))

                if response['results']:
                    SEARCH_RESULTS_RETURNED.inc(len(response['results']))

        # TODO(emichael): Remove this check when the unicode issue is fixed in
        # dev_appserver.
        except UnicodeEncodeError as e:
            SEARCH_FAILURES.inc()
            if not appengine_config.PRODUCTION_MODE:
                # This message will only be displayed to the course author in
                # dev, so it does not need to be I18N'd
                self.template_value['search_error'] = (
                    'There is a known issue in App Engine\'s SDK '
                    '(code.google.com/p/googleappengine/issues/detail?id=9335) '
                    'which causes an error when generating search snippets '
                    'which contain non-ASCII characters. This error does not '
                    'occur in the production environment, so you can safely '
                    'run your course with unicode characters on appspot.com.')
                logging.error('[Unicode/Dev server issue] Error rendering the '
                              'search page: %s.', e)
            else:
                self.template_value['search_error'] = SEARCH_ERROR_TEXT
                logging.error('Error rendering the search page: %s. %s',
                              e, traceback.format_exc())
        except Exception as e:  # pylint: disable-msg=broad-except
            SEARCH_FAILURES.inc()
            self.template_value['search_error'] = SEARCH_ERROR_TEXT
            logging.error('Error rendering the search page: %s. %s',
                          e, traceback.format_exc())
        finally:
            path = sites.abspath(self.app_context.get_home_folder(),
                                 GCB_SEARCH_FOLDER_NAME)
            template = self.get_template('search.html', additional_dirs=[path])
            self.template_value['navbar'] = {}
            self.response.out.write(template.render(self.template_value))

    def filter(self, response, student):
        if not response['results']:
            return response

        filtered_results = []
        available_unit_ids = set(
            str(unit.unit_id) for unit in
            self.get_course().get_track_matching_student(student))
        for result in response['results']:
            if not result.unit_id or str(result.unit_id) in available_unit_ids:
                filtered_results.append(result)
        return {
            'results': filtered_results,
            'total_found': len(filtered_results)
        }


class AssetsHandler(webapp2.RequestHandler):
    """Content handler for assets associated with search."""

    def get(self):
        """Respond to HTTP GET methods."""

        if not custom_module.enabled:
            self.error(404)
            return

        path = self.request.path
        if path.startswith('/'):
            path = path[1:]
        path = os.path.normpath(path)

        if os.path.basename(os.path.dirname(path)) != 'assets':
            self.error(404)

        resource_file = os.path.join(appengine_config.BUNDLE_ROOT, path)

        mimetype = mimetypes.guess_type(resource_file)[0]
        if mimetype is None:
            mimetype = 'application/octet-stream'

        try:
            sites.set_static_resource_cache_control(self)
            self.response.status = 200
            self.response.headers['Content-Type'] = mimetype
            stream = open(resource_file)
            self.response.write(stream.read())
        except IOError:
            self.error(404)


class SearchDashboardHandler(object):
    """Should only be inherited by DashboardHandler, not instantiated."""

    def get_search(self):
        """Renders course indexing view."""
        template_values = {'page_title': self.format_title('Search')}
        mc_template_value = {}
        mc_template_value['module_enabled'] = custom_module.enabled
        indexing_job = IndexCourse(self.app_context).load()
        clearing_job = ClearIndex(self.app_context).load()
        if indexing_job and (not clearing_job or
                             indexing_job.updated_on > clearing_job.updated_on):
            if indexing_job.status_code in [jobs.STATUS_CODE_STARTED,
                                            jobs.STATUS_CODE_QUEUED]:
                mc_template_value['status_message'] = 'Indexing in progress.'
                mc_template_value['job_in_progress'] = True
            elif indexing_job.status_code == jobs.STATUS_CODE_COMPLETED:
                mc_template_value['indexed'] = True
                mc_template_value['last_updated'] = (
                    indexing_job.updated_on.strftime(
                        utils.HUMAN_READABLE_DATETIME_FORMAT))
                mc_template_value['index_info'] = transforms.loads(
                    indexing_job.output)
            elif indexing_job.status_code == jobs.STATUS_CODE_FAILED:
                mc_template_value['status_message'] = (
                    'Indexing job failed with error: %s' % indexing_job.output)
        elif clearing_job:
            if clearing_job.status_code in [jobs.STATUS_CODE_STARTED,
                                            jobs.STATUS_CODE_QUEUED]:
                mc_template_value['status_message'] = 'Clearing in progress.'
                mc_template_value['job_in_progress'] = True
            elif clearing_job.status_code == jobs.STATUS_CODE_COMPLETED:
                mc_template_value['status_message'] = (
                    'The index has been cleared.')
            elif clearing_job.status_code == jobs.STATUS_CODE_FAILED:
                mc_template_value['status_message'] = (
                    'Clearing job failed with error: %s' % clearing_job.output)
        else:
            mc_template_value['status_message'] = (
                'No indexing job has been run yet.')

        mc_template_value['index_course_xsrf_token'] = self.create_xsrf_token(
            'index_course')
        mc_template_value['clear_index_xsrf_token'] = self.create_xsrf_token(
            'clear_index')

        template_values['main_content'] = jinja2.Markup(self.get_template(
            'search_dashboard.html', [os.path.dirname(__file__)]
            ).render(mc_template_value, autoescape=True))

        self.render_page(template_values)

    def post_index_course(self):
        """Submits a new indexing operation."""
        try:
            incremental = self.request.get('incremental') == 'true'
            check_jobs_and_submit(IndexCourse(self.app_context, incremental),
                                  self.app_context)
        except db.TransactionFailedError:
            # Double submission from multiple browsers, just pass
            pass
        self.redirect('/dashboard?action=search')

    def post_clear_index(self):
        """Submits a new indexing operation."""
        try:
            check_jobs_and_submit(ClearIndex(self.app_context),
                                  self.app_context)
        except db.TransactionFailedError:
            # Double submission from multiple browsers, just pass
            pass
        self.redirect('/dashboard?action=search')


class CronHandler(utils.BaseHandler):
    """Iterates through all courses and starts an indexing job for each one.

    All jobs should be submitted through the transactional check_jobs_and_submit
    method to prevent multiple index operations from running at the same time.
    If an index job is currently running when this cron job attempts to start
    one, this operation will be a noop for that course.
    """

    def get(self):
        """Start an index job for each course."""
        cron_logger = logging.getLogger('modules.search.cron')
        self.response.headers['Content-Type'] = 'text/plain'

        if CAN_INDEX_ALL_COURSES_IN_CRON.value:
            counter = 0
            for context in sites.get_all_courses():
                namespace = context.get_namespace_name()
                counter += 1
                try:
                    check_jobs_and_submit(IndexCourse(context), context)
                except db.TransactionFailedError as e:
                    cron_logger.info(
                        'Failed to submit job #%s in namespace %s: %s',
                        counter, namespace, e)
                else:
                    cron_logger.info(
                        'Index job #%s submitted for namespace %s.',
                        counter, namespace)
            cron_logger.info('All %s indexing jobs started; cron job complete.',
                             counter)
        else:
            cron_logger.info('Automatic indexing disabled. Cron job halting.')
        self.response.write('OK\n')


@db.transactional(xg=True)
def check_jobs_and_submit(job, app_context):
    """Determines whether an indexing job is running and submits if not."""
    indexing_job = IndexCourse(app_context).load()
    clearing_job = ClearIndex(app_context).load()

    bad_status_codes = [jobs.STATUS_CODE_STARTED, jobs.STATUS_CODE_QUEUED]
    if ((indexing_job and indexing_job.status_code in bad_status_codes) or
        (clearing_job and clearing_job.status_code in bad_status_codes)):
        raise db.TransactionFailedError('Index job is currently running.')
    else:
        job.non_transactional_submit()


class IndexCourse(jobs.DurableJob):
    """A job that indexes the course."""

    @staticmethod
    def get_description():
        return 'course index'

    def __init__(self, app_context, incremental=True):
        super(IndexCourse, self).__init__(app_context)
        self.incremental = incremental

    def run(self):
        """Index the course."""
        namespace = namespace_manager.get_namespace()
        logging.info('Running indexing job for namespace %s. Incremental: %s',
                     namespace_manager.get_namespace(), self.incremental)
        app_context = sites.get_app_context_for_namespace(namespace)
        course = courses.Course(None, app_context=app_context)
        return index_all_docs(course, self.incremental)


class ClearIndex(jobs.DurableJob):
    """A job that clears the index for a course."""

    @staticmethod
    def get_description():
        return 'clear course index'

    def run(self):
        """Clear the index."""
        namespace = namespace_manager.get_namespace()
        logging.info('Running clearing job for namespace %s.', namespace)
        app_context = sites.get_app_context_for_namespace(namespace)
        course = courses.Course(None, app_context=app_context)
        return clear_index(course)


# Module registration
custom_module = None


def register_module():
    """Registers this module in the registry."""

    global_routes = [
        ('/modules/search/assets/.*', AssetsHandler),
        ('/cron/search/index_courses', CronHandler)
    ]
    namespaced_routes = [
        ('/search', SearchHandler)
    ]

    global custom_module
    custom_module = custom_modules.Module(
        MODULE_NAME,
        'Provides search capabilities for courses',
        global_routes, namespaced_routes)
    return custom_module
