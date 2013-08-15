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
import logging
import math
import mimetypes
import os
import time
import traceback

import appengine_config
from controllers import sites
from controllers import utils
import jinja2
from models import courses
from models import custom_modules
from models import jobs
from models import transforms
import webapp2

import resources

from google.appengine.api import namespace_manager
from google.appengine.api import search
from google.appengine.ext import db


MODULE_NAME = 'Full Text Search'

INDEX_NAME = 'gcb_search_index'
RESULTS_LIMIT = 10
GCB_SEARCH_FOLDER_NAME = os.path.normpath('/modules/search/')

MAX_RETRIES = 5


class ModuleDisabledException(Exception):
    """Exception thrown when the search module is disabled."""
    pass


def get_index(course):
    return search.Index(name=INDEX_NAME,
                        namespace=course.app_context.get_namespace_name())


def index_all_docs(course):
    """Index all of the docs for a given models.Course object.

    Args:
        course: models.courses.Course. the course to index.
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
    counter = 0
    indexed_doc_types = collections.Counter()
    for doc in resources.generate_all_documents(course):
        retry_count = 0
        while retry_count < MAX_RETRIES:
            try:
                index.put(doc)
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
            else:
                counter += 1
                try:
                    doc_type = doc['type'][0].value
                except (AttributeError, KeyError, IndexError):
                    doc_type = 'Unknown'
                indexed_doc_types[doc_type] += 1
                break
    total_time = '%.2f' % (time.time() - start_time)
    return {'num_indexed_docs': counter,
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
                response = fetch(self.get_course(), query, offset=offset)
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
        except Exception as e:  # pylint: disable-msg=broad-except
            self.template_value['search_error'] = True
            logging.error(
                'Error rendering the search page: %s. %s',
                e, traceback.format_exc)
        finally:
            path = sites.abspath(self.app_context.get_home_folder(),
                                 GCB_SEARCH_FOLDER_NAME)
            template = self.get_template('search.html', additional_dirs=[path])
            self.template_value['navbar'] = {}
            self.response.out.write(template.render(self.template_value))


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
        template_values = {}
        template_values['page_title'] = self.format_title('Search')

        mc_template_value = {}
        mc_template_value['module_enabled'] = custom_module.enabled
        indexing_job = IndexCourse(self.app_context).load()
        clearing_job = ClearIndex(self.app_context).load()
        if (indexing_job and
            indexing_job.status_code == jobs.STATUS_CODE_COMPLETED):
            if (clearing_job and
                clearing_job.updated_on > indexing_job.updated_on):
                mc_template_value['status'] = 'clearing'
            else:
                mc_template_value['status'] = 'indexed'
                mc_template_value['last_updated'] = indexing_job.updated_on
                mc_template_value['index_status'] = transforms.loads(
                    indexing_job.output)
        elif (indexing_job and
              indexing_job.status_code == jobs.STATUS_CODE_STARTED):
            mc_template_value['status'] = 'indexing_in_progress'

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
            check_jobs_and_submit(IndexCourse(self.app_context),
                                  self.app_context)
            transforms.send_json_response(
                self, 202, 'Indexing operation queued.')
        except db.TransactionFailedError:
            transforms.send_json_response(
                self, 409, 'Index currently busy.')

    def post_clear_index(self):
        """Submits a new indexing operation."""
        try:
            check_jobs_and_submit(ClearIndex(self.app_context),
                                  self.app_context)
            transforms.send_json_response(
                self, 202, 'Clearing operation queued.')
        except db.TransactionFailedError:
            transforms.send_json_response(
                self, 409, 'Index currently busy.')


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

    def run(self):
        """Index the course."""
        app_context = sites.get_app_context_for_namespace(
            namespace_manager.get_namespace())
        course = courses.Course(None, app_context=app_context)
        return index_all_docs(course)


class ClearIndex(jobs.DurableJob):
    """A job that clears the index for a course."""

    def run(self):
        """Clear the index."""
        app_context = sites.get_app_context_for_namespace(
            namespace_manager.get_namespace())
        course = courses.Course(None, app_context=app_context)
        return clear_index(course)


# Module registration
custom_module = None


def register_module():
    """Registers this module in the registry."""

    global_routes = [
        ('/modules/search/assets/.*', AssetsHandler)
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
