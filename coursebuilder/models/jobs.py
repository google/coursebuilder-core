# Copyright 2012 Google Inc. All Rights Reserved.
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

"""Common classes and methods for managing long running jobs."""

__author__ = 'Pavel Simakov (psimakov@google.com)'

import ast
from datetime import datetime
import logging
import time
import traceback
import urllib

import entities
from mapreduce import base_handler
from mapreduce import input_readers
from mapreduce import mapreduce_pipeline
import transforms

from common.utils import Namespace

from google.appengine import runtime
from google.appengine.ext import db
from google.appengine.ext import deferred

# A job can be in one of these states.
STATUS_CODE_QUEUED = 0
STATUS_CODE_STARTED = 1
STATUS_CODE_COMPLETED = 2
STATUS_CODE_FAILED = 3

# The methods in DurableJobEntity are module-level protected
# pylint: disable=protected-access


class DurableJobBase(object):
    """A class that represents a deferred durable job at runtime."""

    def __init__(self, app_context):
        self._namespace = app_context.get_namespace_name()
        self._job_name = 'job-%s-%s' % (
            self.__class__.__name__, self._namespace)

    def submit(self):
        with Namespace(self._namespace):
            db.run_in_transaction(self.non_transactional_submit)

    def non_transactional_submit(self):
        with Namespace(self._namespace):
            DurableJobEntity._create_job(self._job_name)

    def load(self):
        """Loads the last known state of this job from the datastore."""
        with Namespace(self._namespace):
            return DurableJobEntity._get_by_name(self._job_name)

    def is_active(self):
        job = self.load()
        return job and not job.has_finished


class DurableJob(DurableJobBase):

    def run(self):
        """Override this method to provide actual business logic."""

    def main(self):
        """Main method of the deferred task."""

        with Namespace(self._namespace):
            logging.info('Job started: %s', self._job_name)

            time_started = time.time()
            try:
                db.run_in_transaction(DurableJobEntity._start_job,
                                      self._job_name)
                result = self.run()
                db.run_in_transaction(DurableJobEntity._complete_job,
                                      self._job_name, transforms.dumps(result),
                                      long(time.time() - time_started))
                logging.info('Job completed: %s', self._job_name)
            except (Exception, runtime.DeadlineExceededError) as e:
                logging.error(traceback.format_exc())
                logging.error('Job failed: %s\n%s', self._job_name, e)
                db.run_in_transaction(DurableJobEntity._fail_job,
                                      self._job_name, traceback.format_exc(),
                                      long(time.time() - time_started))
                raise deferred.PermanentTaskFailure(e)

    def non_transactional_submit(self):
        super(DurableJob, self).non_transactional_submit()
        with Namespace(self._namespace):
            deferred.defer(self.main)


class MapReduceJobPipeline(base_handler.PipelineBase):
    def run(self, job_name, kwargs, namespace):
        time_started = time.time()

        with Namespace(namespace):
            db.run_in_transaction(DurableJobEntity._start_job, job_name,
                                  MapReduceJob.build_output(
                                      self.root_pipeline_id, []))
        output = yield mapreduce_pipeline.MapreducePipeline(**kwargs)
        yield StoreMapReduceResults(job_name, time_started, namespace, output)

    def finalized(self):
        pass  # Suppress default Pipeline behavior of sending email.


class StoreMapReduceResults(base_handler.PipelineBase):
    def run(self, job_name, time_started, namespace, output):
        results = []

        # TODO(mgainer): Notice errors earlier in pipeline, and mark job
        # as failed in that case as well.
        try:
            iterator = input_readers.RecordsReader(output, 0)
            for item in iterator:
                # Map/reduce puts reducer output into blobstore files as a
                # string obtained via "str(result)".  Use AST as a safe
                # alternative to eval() to get the Python object back.
                results.append(ast.literal_eval(item))
            time_completed = time.time()
            with Namespace(namespace):
                db.run_in_transaction(DurableJobEntity._complete_job, job_name,
                                      MapReduceJob.build_output(
                                          self.root_pipeline_id, results),
                                      long(time_completed - time_started))
        # Don't know what exceptions are currently, or will be in future,
        # thrown from Map/Reduce or Pipeline libraries; these are under
        # active development.
        #
        # pylint: disable=broad-except
        except Exception, ex:
            time_completed = time.time()
            with Namespace(namespace):
                db.run_in_transaction(DurableJobEntity._fail_job, job_name,
                                      MapReduceJob.build_output(
                                          self.root_pipeline_id,
                                          results,
                                          str(ex)),
                                      long(time_completed - time_started))


class MapReduceJob(DurableJobBase):

    # The 'output' field in the DurableJobEntity representing a MapReduceJob
    # is a map with the following keys:
    #
    # _OUTPUT_KEY_ROOT_PIPELINE_ID
    # Holds a string representing the ID of the MapReduceJobPipeline
    # as known to the mapreduce/lib/pipeline internals.  This is used
    # to generate URLs pointing at the pipeline support UI for detailed
    # inspection of pipeline action.
    #
    # _OUTPUT_KEY_RESULTS
    # Holds a list of individual results.  The result items will be of
    # whatever type is 'yield'-ed from the 'reduce' method (see below).
    #
    # _OUTPUT_KEY_ERROR
    # Stringified error message in the event that something has gone wrong
    # with the job.  Present and relevant only if job status is
    # STATUS_CODE_FAILED.
    _OUTPUT_KEY_ROOT_PIPELINE_ID = 'root_pipeline_id'
    _OUTPUT_KEY_RESULTS = 'results'
    _OUTPUT_KEY_ERROR = 'error'

    @staticmethod
    def build_output(root_pipeline_id, results_list, error=None):
        return transforms.dumps({
            MapReduceJob._OUTPUT_KEY_ROOT_PIPELINE_ID: root_pipeline_id,
            MapReduceJob._OUTPUT_KEY_RESULTS: results_list,
            MapReduceJob._OUTPUT_KEY_ERROR: error,
            })

    @staticmethod
    def get_status_url(job, namespace, xsrf_token):
        if not job.output:
            return None
        content = transforms.loads(job.output)
        pipeline_id = content[MapReduceJob._OUTPUT_KEY_ROOT_PIPELINE_ID]
        return ('/mapreduce/ui/pipeline/status?' +
                urllib.urlencode({'root': pipeline_id,
                                  'namespace': namespace,
                                  'xsrf_token': xsrf_token}))

    @staticmethod
    def has_status_url(job):
        if not job.output:
            return False
        return MapReduceJob._OUTPUT_KEY_ROOT_PIPELINE_ID in job.output

    @staticmethod
    def get_results(job):
        if not job.output:
            return None
        content = transforms.loads(job.output)
        return content[MapReduceJob._OUTPUT_KEY_RESULTS]

    @staticmethod
    def get_error_message(job):
        if not job.output:
            return None
        content = transforms.loads(job.output)
        return content[MapReduceJob._OUTPUT_KEY_ERROR]

    def entity_type_name(self):
        """Gives the fully-qualified name of the DB/NDB type to map over."""
        raise NotImplementedError('Classes derived from MapReduceJob must '
                                  'implement entity_type_name()')

    @staticmethod
    def map(item):
        """Implements the map function.  Must be declared @staticmethod.

        Args:
          item: The parameter passed to this function is a single element of the
          type given by entity_type_name().  This function may <em>yield</em> as
          many times as appropriate (including zero) to return key/value
          2-tuples.  E.g., for calculating student scores from a packed block of
          course events, this function would take as input the packed block.  It
          would iterate over the events, 'yield'-ing for those events that
          respresent items counting towards the grade.  E.g., yield
          (event.student, event.data['score'])
        """
        raise NotImplementedError('Classes derived from MapReduceJob must '
                                  'implement map as a @staticmethod.')

    @staticmethod
    def reduce(key, values):
        """Implements the reduce function.  Must be declared @staticmethod.

        This function should <em>yield</em> whatever it likes; the recommended
        thing to do is emit entities.  All emitted outputs from all
        reducers will be collected in an array and set into the output
        value for the job, so don't pick anything humongous.  If you
        need humongous, instead persist out your humongous stuff and return
        a reference (and deal with doing the dereference to load content
        in the FooHandler class in analytics.py)

        Args:
          key: A key value as emitted from the map() function, above.
          values: A list of all values from all mappers that were tagged with
          the given key.  This code can assume that it is the only process
          handling values for this key.  AFAICT, it can also assume that
          it will be called exactly once for each key with all of the output,
          but this may not be a safe assumption; needs to be verified.

        """
        raise NotImplementedError('Classes derived from MapReduceJob must '
                                  'implement map as a @staticmethod.')

    def non_transactional_submit(self):
        if self.is_active():
            return
        super(MapReduceJob, self).non_transactional_submit()
        kwargs = {
            'job_name': self._job_name,
            'mapper_spec': '%s.%s.map' % (
                self.__class__.__module__, self.__class__.__name__),
            'reducer_spec': '%s.%s.reduce' % (
                self.__class__.__module__, self.__class__.__name__),
            'input_reader_spec':
                'mapreduce.input_readers.DatastoreInputReader',
            'output_writer_spec':
                'mapreduce.output_writers.BlobstoreRecordsOutputWriter',
            'mapper_params': {
                'entity_kind': self.entity_type_name(),
                'namespace': self._namespace,
            },
        }
        mr_pipeline = MapReduceJobPipeline(self._job_name, kwargs,
                                           self._namespace)
        mr_pipeline.start(base_path='/mapreduce/worker/pipeline')


class DurableJobEntity(entities.BaseEntity):
    """A class that represents a persistent database entity of durable job."""

    updated_on = db.DateTimeProperty(indexed=True)
    execution_time_sec = db.IntegerProperty(indexed=False)
    status_code = db.IntegerProperty(indexed=False)
    output = db.TextProperty(indexed=False)

    @classmethod
    def _get_by_name(cls, name):
        return DurableJobEntity.get_by_key_name(name)

    @classmethod
    def _update(cls, name, status_code, output, execution_time_sec):
        """Updates job state in a datastore."""
        assert db.is_in_transaction()

        job = DurableJobEntity._get_by_name(name)
        if not job:
            logging.error('Job was not started or was deleted: %s', name)
            return
        job.updated_on = datetime.now()
        job.execution_time_sec = execution_time_sec
        job.status_code = status_code
        job.output = output
        job.put()

    @classmethod
    def _create_job(cls, name):
        """Creates new or reset a state of existing job in a datastore."""
        assert db.is_in_transaction()

        job = DurableJobEntity._get_by_name(name)
        if not job:
            job = DurableJobEntity(key_name=name)
        job.updated_on = datetime.now()
        job.execution_time_sec = 0
        job.status_code = STATUS_CODE_QUEUED
        job.output = None
        job.put()

    @classmethod
    def _start_job(cls, name, output=None):
        return cls._update(name, STATUS_CODE_STARTED, output, 0)

    @classmethod
    def _complete_job(cls, name, output, execution_time_sec):
        return cls._update(
            name, STATUS_CODE_COMPLETED, output, execution_time_sec)

    @classmethod
    def _fail_job(cls, name, output, execution_time_sec):
        return cls._update(name, STATUS_CODE_FAILED, output, execution_time_sec)

    @property
    def has_finished(self):
        return self.status_code in [STATUS_CODE_COMPLETED, STATUS_CODE_FAILED]
