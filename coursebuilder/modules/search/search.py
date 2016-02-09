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
import messages
import resources
import webapp2

import appengine_config
from common import crypto
from common import safe_dom
from common import schema_fields
from controllers import sites
from controllers import utils
from models import config
from models import counters
from models import courses
from models import custom_modules
from models import jobs
from models import services
from models import transforms
from modules.dashboard import dashboard

from google.appengine.api import namespace_manager
from google.appengine.api import search
from google.appengine.ext import db

MODULE_NAME = 'Full Text Search'

DEPRECATED = config.ConfigProperty(
    'gcb_can_index_automatically', bool, safe_dom.Text(
        'This property has been deprecated; it is retained so that we '
        'will not generate no-such-variable error messages for existing '
        'installations that have this property set.'),
    default_value=False, label='Automatically index search', deprecated=True)
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

INDEX_NAME = 'gcb_search_index_loc_%s'
RESULTS_LIMIT = 10
GCB_SEARCH_FOLDER_NAME = os.path.normpath('/modules/search/')

MAX_RETRIES = 5

# Name of a per-course setting determining whether automatic indexing is enabled
AUTO_INDEX_SETTING = 'auto_index'

# I18N: Message displayed on search results page when error occurs.
SEARCH_ERROR_TEXT = gettext.gettext('Search is currently unavailable.')


class ModuleDisabledException(Exception):
    """Exception thrown when the search module is disabled."""
    pass


def get_index(namespace, locale):
    assert locale, 'Must have a non-null locale'
    return search.Index(name=INDEX_NAME % locale, namespace=namespace)


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
    index = get_index(
        course.app_context.get_namespace_name(),
        course.app_context.get_current_locale())
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

    indexed_doc_types = collections.Counter()
    for type_name in doc_types.values():
        indexed_doc_types[type_name] += 1
    return {'num_indexed_docs': len(timestamps),
            'doc_types': indexed_doc_types,
            'indexing_time_secs': time.time() - start_time}


def clear_index(namespace, locale):
    """Delete all docs in the index for a given models.Course object."""

    if not custom_module.enabled:
        raise ModuleDisabledException('The search module is disabled.')

    index = get_index(namespace, locale)
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

    index = get_index(
        course.app_context.get_namespace_name(),
        course.app_context.get_current_locale())

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
        except Exception as e:  # pylint: disable=broad-except
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
        units, lessons = self.get_course().get_track_matching_student(student)
        available_unit_ids = set(str(unit.unit_id) for unit in units)
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
            return

        resource_file = os.path.join(appengine_config.BUNDLE_ROOT, path)

        mimetype = mimetypes.guess_type(resource_file)[0]
        if mimetype is None:
            mimetype = 'application/octet-stream'

        try:
            sites.set_static_resource_cache_control(self)
            self.response.status = 200
            stream = open(resource_file)
            content = stream.read()
            self.response.headers['Content-Type'] = mimetype
            self.response.write(content)
        except IOError:
            self.error(404)


def _get_search(handler):
    """Renders course indexing view."""
    template_values = {'page_title': handler.format_title('Search')}
    mc_template_value = {}
    mc_template_value['module_enabled'] = custom_module.enabled
    indexing_job = IndexCourse(handler.app_context).load()
    if indexing_job:
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
    else:
        mc_template_value['status_message'] = (
            'No indexing job has been run yet.')

    mc_template_value['index_course_xsrf_token'] = (
        crypto.XsrfTokenManager.create_xsrf_token('index_course'))

    template_values['main_content'] = jinja2.Markup(handler.get_template(
        'search_dashboard.html', [os.path.dirname(__file__)]
        ).render(mc_template_value, autoescape=True))

    return template_values

def _post_index_course(handler):
    """Submits a new indexing operation."""
    try:
        check_job_and_submit(handler.app_context, incremental=False)
    except db.TransactionFailedError:
        # Double submission from multiple browsers, just pass
        pass
    handler.redirect('/dashboard?action=settings_search')


class CronIndexCourse(utils.AbstractAllCoursesCronHandler):
    """Index courses where auto-indexing is enabled.

    All jobs should be submitted through the transactional check_job_and_submit
    method to prevent multiple index operations from running at the same time.
    If an index job is currently running when this cron job attempts to start
    one, this operation will be a noop for that course.
    """
    URL = '/cron/search/index_courses'

    @classmethod
    def is_globally_enabled(cls):
        return True

    @classmethod
    def is_enabled_for_course(cls, app_context):
        course_settings = app_context.get_environ().get('course')
        return course_settings and course_settings.get(AUTO_INDEX_SETTING)

    def cron_action(self, app_context, unused_global_state):
        try:
            check_job_and_submit(app_context, incremental=True)
            logging.info('Index submitted for namespace %s.',
                        app_context.get_namespace_name())
        except db.TransactionFailedError as e:
            logging.info(
                'Failed to submit re-index job in namespace %s: %s',
                app_context.get_namespace_name(), e)


@db.transactional(xg=True)
def check_job_and_submit(app_context, incremental=True):
    """Determines whether an indexing job is running and submits if not."""
    indexing_job = IndexCourse(app_context, incremental=False)
    job_entity = IndexCourse(app_context).load()

    bad_status_codes = [jobs.STATUS_CODE_STARTED, jobs.STATUS_CODE_QUEUED]
    if job_entity and job_entity.status_code in bad_status_codes:
        raise db.TransactionFailedError('Index job is currently running.')

    indexing_job.non_transactional_submit()


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

        # Make a request URL to make sites.get_course_for_current_request work
        sites.set_path_info(app_context.slug)

        indexing_stats = {
            'deleted_docs': 0,
            'num_indexed_docs': 0,
            'doc_types': collections.Counter(),
            'indexing_time_secs': 0,
            'locales': []
        }
        for locale in app_context.get_allowed_locales():
            stats = clear_index(namespace, locale)
            indexing_stats['deleted_docs'] += stats['deleted_docs']
        for locale in app_context.get_allowed_locales():
            app_context.set_current_locale(locale)
            course = courses.Course(None, app_context=app_context)
            stats = index_all_docs(course, self.incremental)
            indexing_stats['num_indexed_docs'] += stats['num_indexed_docs']
            indexing_stats['doc_types'] += stats['doc_types']
            indexing_stats['indexing_time_secs'] += stats['indexing_time_secs']
            indexing_stats['locales'].append(locale)
        return indexing_stats


# Module registration
custom_module = None


def register_module():
    """Registers this module in the registry."""

    global_routes = [
        ('/modules/search/assets/.*', AssetsHandler),
        (CronIndexCourse.URL, CronIndexCourse)
    ]
    namespaced_routes = [
        ('/search', SearchHandler)
    ]

    auto_index_enabled = schema_fields.SchemaField(
        'course:' + AUTO_INDEX_SETTING, 'Auto-Index', 'boolean',
        description=services.help_urls.make_learn_more_message(
            messages.SEARCH_AUTO_INDEX_DESCRIPTION, 'course:auto_index'),
        i18n=False, optional=True)
    course_settings_fields = [
        lambda course: auto_index_enabled
        ]

    def notify_module_enabled():
        dashboard.DashboardHandler.add_sub_nav_mapping(
            'publish', 'search', 'Search', action='settings_search',
            contents=_get_search, placement=1000)
        dashboard.DashboardHandler.add_custom_post_action(
            'index_course', _post_index_course)
        courses.Course.OPTIONS_SCHEMA_PROVIDERS[
            courses.Course.SCHEMA_SECTION_COURSE] += course_settings_fields

    global custom_module  # pylint: disable=global-statement
    custom_module = custom_modules.Module(
        MODULE_NAME,
        'Provides search capabilities for courses',
        global_routes, namespaced_routes,
        notify_module_enabled=notify_module_enabled)
    return custom_module
