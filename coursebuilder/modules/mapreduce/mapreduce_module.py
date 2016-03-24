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

"""Module providing handlers for URLs related to map/reduce and pipelines."""

__author__ = 'Mike Gainer (mgainer@google.com)'

import datetime
import logging
import types
import urllib

import cloudstorage
from mapreduce import main as mapreduce_main
from mapreduce import parameters as mapreduce_parameters
from mapreduce import util as mapreduce_util
from pipeline import models as pipeline_models
from pipeline import pipeline

import messages

from common import users
from common.utils import Namespace
from controllers import sites
from controllers import utils
from models import custom_modules
from models import data_sources
from models import jobs
from models.config import ConfigProperty

from google.appengine.ext import db

# Module registration
custom_module = None
MODULE_NAME = 'Map/Reduce'
XSRF_ACTION_NAME = 'view-mapreduce-ui'
MAX_MAPREDUCE_METADATA_RETENTION_DAYS = 3

GCB_ENABLE_MAPREDUCE_DETAIL_ACCESS = ConfigProperty(
    'gcb_enable_mapreduce_detail_access', bool,
    messages.SITE_SETTINGS_MAPREDUCE, default_value=False, label='MapReduce',
    multiline=False, validator=None)


def authorization_wrapper(self, *args, **kwargs):
    # developers.google.com/appengine/docs/python/taskqueue/overview-push
    # promises that this header cannot be set by external callers.  If this
    # is present, we can be certain that the request is internal and from
    # the task queue worker.  (This is belt-and-suspenders with the admin
    # restriction on /mapreduce/worker*)
    if 'X-AppEngine-TaskName' not in self.request.headers:
        self.response.out.write('Forbidden')
        self.response.set_status(403)
        return
    self.real_dispatch(*args, **kwargs)


def ui_access_wrapper(self, *args, **kwargs):
    content_is_static = (
        self.request.path.startswith('/mapreduce/ui/') and
        (self.request.path.endswith('.css') or
         self.request.path.endswith('.js')))
    xsrf_token = self.request.get('xsrf_token')
    user_is_course_admin = utils.XsrfTokenManager.is_xsrf_token_valid(
        xsrf_token, XSRF_ACTION_NAME)
    ui_enabled = GCB_ENABLE_MAPREDUCE_DETAIL_ACCESS.value

    if ui_enabled and (content_is_static or
                       user_is_course_admin or
                       users.is_current_user_admin()):
        namespace = self.request.get('namespace')
        with Namespace(namespace):
            self.real_dispatch(*args, **kwargs)

        # Some places in the pipeline UI are good about passing the
        # URL's search string along to RPC calls back to Ajax RPCs,
        # which automatically picks up our extra namespace and xsrf
        # tokens.  However, some do not, and so we patch it
        # here, rather than trying to keep up-to-date with the library.
        params = {}
        if namespace:
            params['namespace'] = namespace
        if xsrf_token:
            params['xsrf_token'] = xsrf_token
        extra_url_params = urllib.urlencode(params)
        if self.request.path == '/mapreduce/ui/pipeline/status.js':
            self.response.body = self.response.body.replace(
                'rpc/tree?',
                'rpc/tree\' + window.location.search + \'&')

        elif self.request.path == '/mapreduce/ui/pipeline/rpc/tree':
            self.response.body = self.response.body.replace(
                '/mapreduce/worker/detail?',
                '/mapreduce/ui/detail?' + extra_url_params + '&')

        elif self.request.path == '/mapreduce/ui/detail':
            self.response.body = self.response.body.replace(
                'src="status.js"',
                'src="status.js?%s"' % extra_url_params)

        elif self.request.path == '/mapreduce/ui/status.js':
            replacement = (
                '\'namespace\': \'%s\', '
                '\'xsrf_token\': \'%s\', '
                '\'mapreduce_id\':' % (
                    namespace if namespace else '',
                    xsrf_token if xsrf_token else ''))
            self.response.charset = 'utf8'
            self.response.text = self.response.body.replace(
                '\'mapreduce_id\':', replacement)
    else:
        self.response.out.write('Forbidden')
        self.response.set_status(403)


class CronMapreduceCleanupHandler(utils.BaseHandler):

    def get(self):
        """Clean up intermediate data items for completed or failed M/R jobs.

        Map/reduce runs leave around a large number of rows in several
        tables.  This data is useful to have around for a while:
        - it helps diagnose any problems with jobs that may be occurring
        - it shows where resource usage is occurring
        However, after a few days, this information is less relevant, and
        should be cleaned up.

        The algorithm here is: for each namespace, find all the expired
        map/reduce jobs and clean them up.  If this happens to be touching
        the M/R job that a MapReduceJob instance is pointing at, buff up
        the description of that job to reflect the cleanup.  However, since
        DurableJobBase-derived things don't keep track of all runs, we
        cannot simply use the data_sources.Registry to list MapReduceJobs
        and iterate that way; we must iterate over the actual elements
        listed in the database.
        """

        # Belt and suspenders.  The app.yaml settings should ensure that
        # only admins can use this URL, but check anyhow.
        if 'X-AppEngine-Cron' not in self.request.headers:
            self.error(400)
            return

        self._clean_mapreduce(
            datetime.timedelta(days=MAX_MAPREDUCE_METADATA_RETENTION_DAYS))

    @classmethod
    def _collect_cloudstore_paths(cls, root_key):
        paths = set()
        # pylint: disable=protected-access
        for model, field_name in ((pipeline_models._SlotRecord, 'value'),
                                  (pipeline_models._PipelineRecord, 'params')):
            prev_cursor = None
            any_records = True
            while any_records:
                any_records = False
                query = (model
                         .all()
                         .filter('root_pipeline =', root_key)
                         .with_cursor(prev_cursor))
                for record in query.run():
                    any_records = True
                    # The data parameters in SlotRecord and PipelineRecord
                    # vary widely, but all are provided via this interface as
                    # some combination of Python scalar, list, tuple, and
                    # dict.  Rather than depend on specifics of the map/reduce
                    # internals, manually rummage around.  Experiment shows
                    # this to be sufficient.
                    try:
                        data_object = getattr(record, field_name)
                    except TypeError:
                        data_object = None
                    if (data_object and
                        isinstance(data_object, list) and
                        all(isinstance(x, basestring) for x in data_object) and
                        all(x[0] == '/' for x in data_object)
                    ):
                        paths.update(data_object)
                prev_cursor = query.cursor()
        return paths

    @classmethod
    def _clean_cloudstore_paths_for_key(cls, root_key, min_start_time_millis):
        for path in cls._collect_cloudstore_paths(root_key):
            try:
                cloudstorage.delete(path)
                logging.info('Deleted cloud storage file %s', path)
            except cloudstorage.NotFoundError:
                logging.info('Cloud storage file %s already deleted', path)

    @classmethod
    def _clean_mapreduce(cls, max_age):
        """Separated as internal function to permit tests to pass max_age."""
        num_cleaned = 0

        # If job has a start time before this, it has been running too long.
        min_start_time_datetime = datetime.datetime.utcnow() - max_age
        min_start_time_millis = int(
            (min_start_time_datetime - datetime.datetime(1970, 1, 1))
            .total_seconds() * 1000)

        # Iterate over all namespaces in the installation
        for course_context in sites.get_all_courses():
            with Namespace(course_context.get_namespace_name()):

                # Index map/reduce jobs in this namespace by pipeline ID.
                jobs_by_pipeline_id = {}
                for job_class in data_sources.Registry.get_generator_classes():
                    if issubclass(job_class, jobs.MapReduceJob):
                        job = job_class(course_context)
                        pipe_id = jobs.MapReduceJob.get_root_pipeline_id(
                            job.load())
                        jobs_by_pipeline_id[pipe_id] = job

                # Clean up pipelines
                for state in pipeline.get_root_list()['pipelines']:
                    pipeline_id = state['pipelineId']
                    job_definitely_terminated = (
                        state['status'] == 'done' or
                        state['status'] == 'aborted' or
                        state['currentAttempt'] > state['maxAttempts'])
                    have_start_time = 'startTimeMs' in state
                    job_started_too_long_ago = (
                        have_start_time and
                        state['startTimeMs'] < min_start_time_millis)

                    if (job_started_too_long_ago or
                        (not have_start_time and job_definitely_terminated)):
                        # At this point, the map/reduce pipeline is
                        # either in a terminal state, or has taken so long
                        # that there's no realistic possibility that there
                        # might be a race condition between this and the
                        # job actually completing.
                        if pipeline_id in jobs_by_pipeline_id:
                            jobs_by_pipeline_id[pipeline_id].mark_cleaned_up()

                        p = pipeline.Pipeline.from_id(pipeline_id)
                        if p:
                            # Pipeline cleanup, oddly, does not go clean up
                            # relevant blobstore items.  They have a TODO,
                            # but it has not been addressed as of Sep 2014.
                            # pylint: disable=protected-access
                            root_key = db.Key.from_path(
                                pipeline_models._PipelineRecord.kind(),
                                pipeline_id)
                            cls._clean_cloudstore_paths_for_key(
                                root_key, min_start_time_millis)

                            # This only enqueues a deferred cleanup item, so
                            # transactionality with marking the job cleaned is
                            # not terribly important.
                            p.cleanup()
                        num_cleaned += 1
        return num_cleaned


def handler_for_name(fq_name):
    """Resolves and instantiates handler by fully qualified name.

    NOTE: This is a clone of a function in the map/reduce module which has
    also been taught that map and reduce functions may be marked with
    @classmethod, as opposed to only member functions of default-constructable
    classes or @staticmethod.  It is applied as a monkey-patch to fix the base
    library.

    First resolves the name using for_name call. Then if it resolves to a
    class, instantiates a class, if it resolves to a method - instantiates the
    class and binds method to the instance.

    Args:
      fq_name: fully qualified name of something to find.

    Returns:
      handler instance which is ready to be called.

    """
    resolved_name = mapreduce_util.for_name(fq_name)
    if isinstance(resolved_name, (type, types.ClassType)):
        # create new instance if this is type
        return resolved_name()
    elif (isinstance(resolved_name, types.MethodType) and
          resolved_name.im_self is None):
        # bind the method
        return getattr(resolved_name.im_class(), resolved_name.__name__)
    else:
        # Already bound -- classmethod or staticmethod.
        return resolved_name


def register_module():
    """Registers this module in the registry."""

    global_handlers = [
        ('/cron/mapreduce/cleanup', CronMapreduceCleanupHandler),
    ]

    def notify_module_enabled():
        for path, handler_class in mapreduce_main.create_handlers_map():
            # The mapreduce and pipeline libraries are pretty casual about
            # mixing up their UI support in with their functional paths.
            # Here, we separate things and give them different prefixes
            # so that the only-admin-access patterns we define in app.yaml
            # can be reasonably clean.
            if path.startswith('.*/pipeline'):
                if 'pipeline/rpc/' in path or path == '.*/pipeline(/.+)':
                    path = path.replace('.*/pipeline', '/mapreduce/ui/pipeline')
                else:
                    path = path.replace('.*/pipeline',
                                        '/mapreduce/worker/pipeline')
            else:
                if '_callback' in path:
                    path = path.replace('.*', '/mapreduce/worker', 1)
                elif '/list_configs' in path:
                    # This needs mapreduce.yaml, which we don't distribute.  Not
                    # having this prevents part of the mapreduce UI front page
                    # from loading, but we don't care, because we don't want
                    # people using the M/R front page to relaunch jobs anyhow.
                    continue
                else:
                    path = path.replace('.*', '/mapreduce/ui', 1)

            # The UI needs to be guarded by a config so that casual users aren't
            # exposed to the internals, but advanced users can
            # investigate issues.
            if '/ui/' in path or path.endswith('/ui'):
                if (hasattr(handler_class, 'dispatch') and
                    not hasattr(handler_class, 'real_dispatch')):
                    handler_class.real_dispatch = handler_class.dispatch
                    handler_class.dispatch = ui_access_wrapper
                global_handlers.append((path, handler_class))

            # Wrap worker handlers with check that request really is coming
            # from task queue.
            else:
                if (hasattr(handler_class, 'dispatch') and
                    not hasattr(handler_class, 'real_dispatch')):
                    handler_class.real_dispatch = handler_class.dispatch
                    handler_class.dispatch = authorization_wrapper
                global_handlers.append((path, handler_class))

        # Tell map/reduce internals that this is now the base path to use.
        mapreduce_parameters.config.BASE_PATH = '/mapreduce/worker'

        # Monkey-patch handler_for_name in mapreduce; the implementation does
        # not correctly handle map, reduce methods marked as @classmethod.
        mapreduce_util.handler_for_name = handler_for_name

    global custom_module  # pylint: disable=global-statement
    custom_module = custom_modules.Module(
        MODULE_NAME,
        'Provides support for analysis jobs based on map/reduce',
        global_handlers, [], notify_module_enabled=notify_module_enabled)
    return custom_module
