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
import datetime
import logging
import time
import traceback
import urllib

from common import utils as common_utils
import entities
from mapreduce import base_handler
from mapreduce import input_readers
from mapreduce import mapreduce_pipeline
from mapreduce import output_writers
from mapreduce import util
from pipeline import pipeline
import transforms
from common import users
from common.utils import Namespace

from google.appengine import runtime
from google.appengine.api import app_identity
from google.appengine.ext import db
from google.appengine.ext import deferred

# A job can be in one of these states.
STATUS_CODE_QUEUED = 0
STATUS_CODE_STARTED = 1
STATUS_CODE_COMPLETED = 2
STATUS_CODE_FAILED = 3

STATUS_CODE_DESCRIPTION = {
    STATUS_CODE_QUEUED: 'Queued',
    STATUS_CODE_STARTED: 'Started',
    STATUS_CODE_COMPLETED: 'Completed',
    STATUS_CODE_FAILED: 'Failed',
}

# The methods in DurableJobEntity are module-level protected
# pylint: disable=protected-access


class DurableJobBase(object):
    """A class that represents a deferred durable job at runtime."""

    xg_on = db.create_transaction_options(xg=True)

    @staticmethod
    def get_description():
        """Briefly describe the nature and purpose of your job type.

        This is used in the display code of analytics to complete
        sentences like "<description> statistics have not been
        calculated yet".  Don't capitalize; captialization will be
        automatically performed where <description> appears at the
        start of a sentence or in a section title.
        """
        raise NotImplementedError(
            'Leaf classes inheriting from DurableJobBase should provide a '
            'brief description of their nature and purpose.  E.g., '
            '"student ranking"')

    def __init__(self, app_context):
        self._app_context = app_context
        self._namespace = app_context.get_namespace_name()
        self._job_name = 'job-%s-%s' % (
            self.__class__.__name__, self._namespace)

    def submit(self):
        if self.is_active():
            return -1
        with Namespace(self._namespace):
            if not self._pre_transaction_setup():
                return -1
            return db.run_in_transaction_options(self.xg_on,
                                                 self.non_transactional_submit)

    def non_transactional_submit(self):
        with Namespace(self._namespace):
            return DurableJobEntity._create_job(self._job_name)

    def load(self):
        """Loads the last known state of this job from the datastore."""
        with Namespace(self._namespace):
            return DurableJobEntity._get_by_name(self._job_name)

    def cancel(self):
        job = self.load()
        if job and not job.has_finished:
            user = users.get_current_user()
            message = 'Canceled by %s at %s' % (
                user.nickname() if user else 'default',
                datetime.datetime.now().strftime('%Y-%m-%d, %H:%M UTC'))
            duration = int((datetime.datetime.now() - job.updated_on)
                           .total_seconds())

            with Namespace(self._namespace):
                # Do work specific to job type outside of our transaction
                self._cancel_queued_work(job, message)

                # Update our job record
                return db.run_in_transaction(self._mark_job_canceled,
                                             job, message, duration)
        return job

    def _cancel_queued_work(self, unused_job, unused_message):
        """Override in subclasses to do cancel work outside transaction."""
        pass

    def _mark_job_canceled(self, job, message, duration):
        DurableJobEntity._fail_job(
            self._job_name, job.sequence_num, message, duration)

    def is_active(self):
        job = self.load()
        return job and not job.has_finished

    def _pre_transaction_setup(self):
        return True  # All is well.

    @property
    def name(self):
        return self._job_name


class DurableJob(DurableJobBase):

    def run(self):
        """Override this method to provide actual business logic."""

    @db.transactional
    def _already_finished(self, sequence_num):
        current_status = self.load()
        return (sequence_num < current_status.sequence_num or
                (sequence_num == current_status.sequence_num and
                 current_status.has_finished))

    def main(self, sequence_num):
        """Main method of the deferred task."""

        with Namespace(self._namespace):
            logging.info('Job started: %s w/ sequence number %d',
                         self._job_name, sequence_num)

            time_started = time.time()
            try:
                # Check we haven't been canceled before we start.
                if self._already_finished(sequence_num):
                    logging.info(
                        'Job %s sequence %d already canceled or subsequent '
                        'run completed; not running this version.',
                        self._job_name, sequence_num)
                    return
                db.run_in_transaction(DurableJobEntity._start_job,
                                      self._job_name, sequence_num)
                result = self.run()
                db.run_in_transaction(DurableJobEntity._complete_job,
                                      self._job_name, sequence_num,
                                      transforms.dumps(result),
                                      long(time.time() - time_started))
                logging.info('Job completed: %s', self._job_name)
            except (Exception, runtime.DeadlineExceededError) as e:
                logging.error(traceback.format_exc())
                logging.error('Job failed: %s\n%s', self._job_name, e)
                db.run_in_transaction(DurableJobEntity._fail_job,
                                      self._job_name, sequence_num,
                                      traceback.format_exc(),
                                      long(time.time() - time_started))
                raise deferred.PermanentTaskFailure(e)

    def non_transactional_submit(self):
        sequence_num = super(DurableJob, self).non_transactional_submit()
        deferred.defer(self.main, sequence_num)
        return sequence_num


class MapReduceJobPipeline(base_handler.PipelineBase):

    def run(self, job_name, sequence_num, kwargs, namespace, complete_fn):
        time_started = time.time()

        with Namespace(namespace):
            db.run_in_transaction(
                DurableJobEntity._start_job, job_name, sequence_num,
                MapReduceJob.build_output(self.root_pipeline_id, []))
        output = yield mapreduce_pipeline.MapreducePipeline(**kwargs)
        yield StoreMapReduceResults(job_name, sequence_num, time_started,
                                    namespace, output, complete_fn, kwargs)

    def finalized(self):
        pass  # Suppress default Pipeline behavior of sending email.


class StoreMapReduceResults(base_handler.PipelineBase):

    def run(self, job_name, sequence_num, time_started, namespace, output,
            complete_fn, kwargs):
        results = []
        # TODO(mgainer): Notice errors earlier in pipeline, and mark job
        # as failed in that case as well.
        try:
            iterator = input_readers.GoogleCloudStorageInputReader(output, 0)
            for file_reader in iterator:
                for item in file_reader:
                    # Map/reduce puts reducer output into blobstore files as a
                    # string obtained via "str(result)".  Use AST as a safe
                    # alternative to eval() to get the Python object back.
                    results.append(ast.literal_eval(item))
            if complete_fn:
                util.for_name(complete_fn)(kwargs, results)
            time_completed = time.time()
            with Namespace(namespace):
                db.run_in_transaction(
                    DurableJobEntity._complete_job, job_name, sequence_num,
                    MapReduceJob.build_output(self.root_pipeline_id, results),
                    long(time_completed - time_started))
        # Don't know what exceptions are currently, or will be in future,
        # thrown from Map/Reduce or Pipeline libraries; these are under
        # active development.
        #
        # pylint: disable=broad-except
        except Exception, ex:
            logging.critical('Failed running map/reduce job %s: %s', job_name,
                             str(ex))
            common_utils.log_exception_origin()
            time_completed = time.time()
            with Namespace(namespace):
                db.run_in_transaction(
                    DurableJobEntity._fail_job, job_name, sequence_num,
                    MapReduceJob.build_output(self.root_pipeline_id, results,
                                              str(ex)),
                    long(time_completed - time_started))


class GoogleCloudStorageConsistentOutputReprWriter(
    output_writers.GoogleCloudStorageConsistentOutputWriter):

    def write(self, data):
        if isinstance(data, basestring):
            # Convert from unicode, as returned from transforms.dumps()
            data = str(data)
            if not data.endswith('\n'):
                data += '\n'
        else:
            data = repr(data) + '\n'
        super(GoogleCloudStorageConsistentOutputReprWriter, self).write(data)


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
    def get_root_pipeline_id(job):
        if not job or not job.output:
            return None
        content = transforms.loads(job.output)
        return content[MapReduceJob._OUTPUT_KEY_ROOT_PIPELINE_ID]

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

    def entity_class(self):
        """Return a reference to the class for the DB/NDB type to map over."""
        raise NotImplementedError('Classes derived from MapReduceJob must '
                                  'implement entity_class()')

    @staticmethod
    def map(item):
        """Implements the map function.  Must be declared @staticmethod.

        Args:
          item: The parameter passed to this function is a single element of the
          type given by entity_class().  This function may <em>yield</em> as
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

    @staticmethod
    def combine(unused_key, values, previously_combined_values):
        """Optional.  Performs reduce task on mappers to minimize shuffling.

        After the map() function, each job-host has a chunk of yield()-ed
        results, often for the same key.  Rather than send all of those
        separate results over to the appropriate reducer task, it would be
        nice to be able to pre-combine these items within the mapper job,
        so as to minimize the amount of data that needs to be shuffled and
        piped out to reducers.

        If your reduce step is strictly aggregative in nature (specifically,
        if the reduce:
        1.) does not need to have the entire universe of mapped-values for
            the same key in order to operate correctly
        2.) can meaningfully combine partial results into another partial
            result, which can itself later be combined (either in another
            collect() call, or in the final reduce() call)
        then you're OK to implement this function.

        NOTE that since this function can't make up any new keys, the framework
        expects the yield() from this function to yield only a single combined
        value, not a key/value pair.

        See the example below in AbstractCountingMapReduceJob.
        """
        raise NotImplementedError('Classes derived from MapReduceJob may '
                                  'optionally implement combine() as a static '
                                  'method.')

    @staticmethod
    def complete(kwargs, results):
        """Optional.  Called exactly once on successful job completion.

        When a job has completed successfully, this function is called.
        'kwargs' is a dict containing values provided to mappers/reducers,
        including any items produced from your
        build_additional_mapper_params() function, if impemented.  The
        'results' parameter contains the list of results for the job.  These
        are the same values as would be returned from get_results(job).

        This is called after the results from the m/r job have been extracted,
        but before logging success of the job in the DurableJobEntity row.
        Raising an exception here will cause the job to be marked as failed,
        despite the main m/r having succeeded.

        NOTE: Be sure to use kwargs['mapper_params'] to access values added by
        build_additional_mapper_params(), rather than using context.get() at
        complete() time.  This is because the same thread may be used for
        multiple job completions, and there's a race between setting the
        global context and this function.
        """
        raise NotImplementedError()

    def build_additional_mapper_params(self, unused_app_context):
        """Build a dict of additional parameters to make available to mappers.

        The map/reduce framework permits an arbitrary dict of plain-old-data
        items to be passed along and made available to mapper jobs.  This is
        very useful if you have a small-ish (10s of K) amount of data that
        is needed as a lookup table or similar when the mapper is running,
        and which is expensive to re-calculate within each mapper job.

        To make use of this, override this function and return a dict.
        This will be merged with the mapper_params.  Note that you cannot
        override the reserved items already in mapper_params:
        - 'entity_kind' - The name of the DB entity class mapped over
        - 'namespace' - The namespace in which mappers operate.

        To access this extra data, you need to:

        from mapreduce import context
        class MyMapReduceClass(jobs.MapReduceJob):

            def build_additional_mapper_params(self, app_context):
                .... set up values to be conveyed to mappers ...
                return {
                   'foo': foo,
                   ....
                   }

            @staticmethod
            def map(item):
                mapper_params = context.get().mapreduce_spec.mapper.params
                foo = mapper_params['foo']
                ....
                yield(...)

        Args:
          unused_app_context: Caller provides namespaced context for subclass
              implementation of this function.
        Returns:
          A dict of name/value pairs that should be made available to
          map jobs.
        """
        return {}

    def _pre_transaction_setup(self):
        """Hack to allow use of DB before we are formally in a txn."""

        self.mapper_params = self.build_additional_mapper_params(
            self._app_context)
        return True

    def non_transactional_submit(self):
        if self.is_active():
            return -1
        sequence_num = super(MapReduceJob, self).non_transactional_submit()
        entity_class_type = self.entity_class()
        entity_class_name = '%s.%s' % (entity_class_type.__module__,
                                       entity_class_type.__name__)

        # Build config parameters to make available to map framework
        # and individual mapper jobs.  Overwrite important parameters
        # so derived class cannot mistakenly set them.
        self.mapper_params.update({
            'entity_kind': entity_class_name,
            'namespace': self._namespace,
            })

        # Config parameters for reducer, output writer stages.  Copy from
        # mapper_params so that the implemented reducer function also gets
        # to see any parameters built by build_additional_mapper_params().
        reducer_params = {}
        reducer_params.update(self.mapper_params)
        bucket_name = app_identity.get_default_gcs_bucket_name()
        reducer_params.update({
            'output_writer': {
                output_writers.GoogleCloudStorageOutputWriter.BUCKET_NAME_PARAM:
                    bucket_name,
            }
        })

        kwargs = {
            'job_name': self._job_name,
            'mapper_spec': '%s.%s.map' % (
                self.__class__.__module__, self.__class__.__name__),
            'reducer_spec': '%s.%s.reduce' % (
                self.__class__.__module__, self.__class__.__name__),
            'input_reader_spec':
                'mapreduce.input_readers.DatastoreInputReader',
            'output_writer_spec':
                'models.jobs.GoogleCloudStorageConsistentOutputReprWriter',
            'mapper_params': self.mapper_params,
            'reducer_params': reducer_params,
        }
        if (getattr(self.__class__, 'combine') !=
            getattr(MapReduceJob, 'combine')):
            kwargs['combiner_spec'] = '%s.%s.combine' % (
                self.__class__.__module__, self.__class__.__name__)
        complete_fn = None
        if (getattr(self.__class__, 'complete') !=
            getattr(MapReduceJob, 'complete')):
            complete_fn = '%s.%s.complete' % (
                self.__class__.__module__, self.__class__.__name__)
        mr_pipeline = MapReduceJobPipeline(self._job_name, sequence_num,
                                           kwargs, self._namespace, complete_fn)
        mr_pipeline.start(base_path='/mapreduce/worker/pipeline')
        return sequence_num

    def _cancel_queued_work(self, job, message):
        root_pipeline_id = MapReduceJob.get_root_pipeline_id(job)
        if root_pipeline_id:
            p = pipeline.Pipeline.from_id(root_pipeline_id)
            if p:
                p.abort(message)

    def _mark_job_canceled(self, job, message, duration):
        DurableJobEntity._fail_job(
            self._job_name, job.sequence_num,
            MapReduceJob.build_output(None, None, message), duration)

    def mark_cleaned_up(self):
        job = self.load()

        # If the job has already finished, then the cleanup is a
        # no-op; we are just reclaiming transient state.  However, if
        # our DurableJobEntity still thinks the job is running and it
        # is actually not, then mark the status message to indicate
        # the cleanup.
        if job and not job.has_finished:
            duration = int((datetime.datetime.utcnow() - job.updated_on)
                           .total_seconds())
            with Namespace(self._namespace):
                return db.run_in_transaction(
                    self._mark_job_canceled, job,
                    'Job has not completed; assumed to have failed after %s' %
                    str(datetime.timedelta(seconds=duration)), duration)
        return job


class AbstractCountingMapReduceJob(MapReduceJob):
    """Provide common functionality for map/reduce jobs that just count.

    This class provides a common implementation of combine() and reduce()
    so that a map/reduce task that is only concerned with counting the
    number of occurrences of something can be more terse.  E.g., if we
    want to get a total of the number of students with the same first
    name, we only need to write:

    class NameCounter(jobs.AbstractCountingMapReduceJob):
        @staticmethod
        def get_description():
            return "count names"
        def entity_class():
            return models.Student
        @staticmethod
        def map(student):
            return (student.name.split()[0], 1)

    The output of this job will be an array of 2-tuples consisting of
    the name and the total number of students with that same first name.
    """

    @staticmethod
    def combine(unused_key, values, previously_combined_outputs=None):
        total = sum([int(value) for value in values])
        if previously_combined_outputs is not None:
            total += sum([int(value) for value in previously_combined_outputs])
        yield total

    @staticmethod
    def reduce(key, values):
        total = sum(int(value) for value in values)
        yield (key, total)


class DurableJobEntity(entities.BaseEntity):
    """A class that represents a persistent database entity of durable job."""

    updated_on = db.DateTimeProperty(indexed=True)
    execution_time_sec = db.IntegerProperty(indexed=False)
    status_code = db.IntegerProperty(indexed=False)
    output = db.TextProperty(indexed=False)
    sequence_num = db.IntegerProperty(indexed=False)

    @classmethod
    def _get_by_name(cls, name):
        return DurableJobEntity.get_by_key_name(name)

    @classmethod
    def _update(cls, name, sequence_num, status_code, output,
                execution_time_sec):
        """Updates job state in a datastore."""
        assert db.is_in_transaction()

        job = DurableJobEntity._get_by_name(name)
        if not job:
            logging.error('Job was not started or was deleted: %s', name)
            return
        if job.sequence_num != sequence_num:
            logging.warning(
                'Request to update status code to %d ' % status_code +
                'for sequence number %d ' % sequence_num +
                'but job is already on run %d' % job.sequence_num)
            return
        job.updated_on = datetime.datetime.now()
        job.execution_time_sec = execution_time_sec
        job.status_code = status_code
        if output:
            job.output = output
        job.put()

    @classmethod
    def _create_job(cls, name):
        """Creates new or reset a state of existing job in a datastore."""
        assert db.is_in_transaction()

        job = DurableJobEntity._get_by_name(name)
        if not job:
            job = DurableJobEntity(key_name=name)
        job.updated_on = datetime.datetime.now()
        job.execution_time_sec = 0
        job.status_code = STATUS_CODE_QUEUED
        job.output = None
        if not job.sequence_num:
            job.sequence_num = 1
        else:
            job.sequence_num += 1
        job.put()
        return job.sequence_num

    @classmethod
    def _start_job(cls, name, sequence_num, output=None):
        return cls._update(name, sequence_num, STATUS_CODE_STARTED, output, 0)

    @classmethod
    def _complete_job(cls, name, sequence_num, output, execution_time_sec):
        return cls._update(name, sequence_num, STATUS_CODE_COMPLETED,
                           output, execution_time_sec)

    @classmethod
    def _fail_job(cls, name, sequence_num, output, execution_time_sec):
        return cls._update(name, sequence_num, STATUS_CODE_FAILED,
                           output, execution_time_sec)

    @property
    def has_finished(self):
        return self.status_code in [STATUS_CODE_COMPLETED, STATUS_CODE_FAILED]
