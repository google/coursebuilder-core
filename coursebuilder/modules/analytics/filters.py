# Copyright 2016 Google Inc. All Rights Reserved.
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

"""Module providing common base types for analytics."""

__author__ = 'Mike Gainer (mgainer@google.com)'

import ast
import itertools

from mapreduce import base_handler
from mapreduce import mapper_pipeline

from common import schema_fields
from common import utils as common_utils
from models import data_sources
from models import entities
from models import jobs
from models import models
from models import transforms

from google.appengine.ext import db


class AbstractFilteredEntity(entities.BaseEntity):
    """Common base class providing support for filtering/ordering for analytics.

    Some analytics need to be filtered on multiple different dimensions.  This
    and peer classes provide a common framework to accomplish this while
    minimizing the amount of incremental work needed to add new analytics or
    filter dimensions.

    When adding a new analytic, you must derive from this class so that
    entities for your new feature's use case are separate.

    Derived classes should add an indexed field for each filter that is to be
    applied in that specific case.  Be certain to name the field identically
    to the value returned from the corresponding filter class' get_name().

    Also, if your type uses user_id as the key_name for these entities, be
    sure to remember to register your class with models.data_removal.Registry.
    """

    # Common data.  Stored as JSON blob.
    data = db.TextProperty(indexed=False)

    # All types will want to have this, so it's here in the common base.
    primary_id = db.StringProperty(indexed=True)

    @classmethod
    def get_filters(cls):
        """Provide the set of filters applicable to results from this job.

        These filters are applied to determine filter key values and field
        names when storing results in entities.

        NOTE: This should return the same iterable of filters as from the
        AbstractFilterableRestDataSource used to access the result entities.
        Hint: You may wish to implement that class' get_filters() by just
        forwarding to this function.
        """
        raise NotImplementedError()

    @classmethod
    def delete_by_primary_id(cls, primary_id):
        entity = cls.all().filter('primary_id=', primary_id).get()
        if entity:
            entity.delete()


class PreCleanMapReduceJobPipeline(base_handler.PipelineBase):
    """Map/Reduce pipeline that pre-cleans results from prior run of job.

    We need to delete our previous results since the set of values for each
    filter produced on this run may be a subset of filter values from a
    previous run.  Since we don't want to indadvertently find leftover results
    from a previous run when displaying analytics, we must first get rid of
    existing records.  Doing that as a map/reduce may sometimes be gross
    overkill, but it's idiot-proof, reliable, and leaves the generator job
    marked as running while it happens, which prevents some nasty races.
    """

    def run(self, namespace, job_name, sequence_num, cleanup_params,
            job_runner_args):
        self._started(namespace, job_name, sequence_num)
        yield mapper_pipeline.MapperPipeline(
            job_name=job_name,
            handler_spec=
                'modules.analytics.filters.PreCleanMapReduceJobPipeline.map',
            input_reader_spec='mapreduce.input_readers.DatastoreInputReader',
            params=cleanup_params
        )
        yield jobs.MapReduceJobRunner(**job_runner_args)

    def _started(self, namespace, job_name, sequence_num):
        with common_utils.Namespace(namespace):
            # pylint: disable=protected-access
            db.run_in_transaction(
                jobs.DurableJobEntity._start_job, job_name, sequence_num,
                jobs.MapReduceJob.build_output(self.root_pipeline_id, []))

    @staticmethod
    def map(entity):
        entities.delete(entity)


class AbstractFilteredMapReduceJob(jobs.MapReduceJob):

    """Base functionality for map/reduce jobs generating filterable results.

    See analytics_tests.FilteredAssessmentScores{Entity,Generator,DataSource}
    for an example implementation of an entity, generator job, and data source
    class that collaborate to filter on student group and student course
    track.
    """

    # Override default pipeline in base class; we need to clean old results.
    MAP_REDUCE_PIPELINE_CLASS = PreCleanMapReduceJobPipeline

    @classmethod
    def result_class(cls):
        """Identify the dervied AbstractFilteredEntity type saved by this job.

        This is used by other functions in the abstract implementation to
        discover the entity type that should be created to store job results.
        """
        raise NotImplementedError()

    @classmethod
    def map(cls, entity):
        """Standard map function in map/reduce paradigm.

        Concrete classes should impelement map functionality as normal, but
        when it is time to yield results, map functions must use exactly
        the syntax below.  It'd be nice if we could abstract this away, but
        the semantics of 'yield' means that the map function must be the
        place where the 'yield' statement occurs; this cannot be factored
        into a common function that a map() implementation can call.

        @classmethod
        def map(cls, an_entity):
            # code to process 'entity' in whatever way is appropriate.
            # Here, we assume that there are variables:
            # primary_id: Holds the ID on which aggregation should be
            #     performed.  E.g., if aggregating by Student, the user_id.
            #     If by course element, the unit_id, or similar.
            # result: One result which will be passed in to the reducer
            #     in a list of all results having the same key.  May be
            #     a simple scalar or complex, as long as it's serializable
            #     via str() and recoverable via ast.literal_eval().
            #

            # Example----------------(This will vary depending on your use case)
            #
            # Convert processor cycles used in each Android emulator test
            # case run to an amount in the app.  Set the primary key to the
            # user ID, so that the reduce step can aggregate our cost on
            # a per-student basis.
            #
            primary_id = an_enity.user_id
            result = {
                 'currency_code': entity.currency_code,
                 'amount': modules.payment.payment.processor_time_to_amount(
                     entity.currency_code, entity.processor_time_used)
            }

            # Boilerplate----------------------------(always write exactly this)
            #
            # generate_keys() generates all combinations of keys and None
            # we want to be able to filter by for processor use cost.
            # reduce() will aggregate and store these for each combination.
            #
            for key in cls._generate_keys(element, primary_id):
                yield key, result

        Args:
          entity: One instance of whatever type this class returns from the
              entity_class() method.
        """
        raise NotImplementedError()

    @classmethod
    def reduce(cls, keys, values):
        """Standard reduce function in map/reduce paradigm.

        You should perform whatever aggregation is required (if any), and
        then call _write_entity, as in the example code below.  You may
        also use 'yield' to generate output that will be stored in the
        DurableJobEntity result row for this job run, but this is neither
        required nor is it expected to be a common use case.

        @classmethod
        def reduce(cls, keys, values):
            # code to perform aggregation or any other required processing
            # on the list of values.  Here, we assume that a variable named
            # 'result' has been filled in with some simple or complex
            # structure.

            # Example----------------(This will vary depending on your use case)
            #
            # Unpack values; collect all currency codes and get conversion
            # rates to USD.  For all results, aggregate amounts in USD.
            # These will be stored by write_entity() for this particular
            # set of keys.
            #
            values = [ast.literal_eval(v) for v in values]
            currency_codes = set([v['currency_code'] for v in values])
            conversion = modules.payment.payment.conversions_to_usd(
                currency_codes)
            result = sum([v['amount'] * conversions[v['currency_code']]
                for v in values])

            # Boilerplate----------------------------(always write exactly this)
            #
            # Stores one row with the supplied keys and our aggregated result.
            cls._write_entity(keys, result)

        Args:
            keys: A tuple of key fields packed as a string.  The first
                item in the tuple will be the value of 'primary_id' as passed
                to generate_keys.  The other items are generated by the
                filters for this class, and should be treated as opaque data.
            values: A tuple of values; these will be _all_ the values, and
                _only_ the values yielded by map() for this specific list
                of keys.
        """
        raise NotImplementedError()

    @classmethod
    def _generate_keys(cls, element, primary_id):
        """Generates lists of combinations of keys for writing FilteredEntities

        Derived classes should not implement this function, but they will
        call it from their map() implementations.

        Args:
          element: The same element passed in to the map() function.
          primary_id: Names the particular element for which the reduce()
              is an aggregate.  E.g., if your are mapping over EventElement
              and aggregating results by Student, this will be the user_id
              for the relevant Student.  Similarly, if mapping over
              EventEntity assessment answers, and aggregating by question
              instance, this would be the ID of the instance of a question.
        """

        filter_key_lists = []
        filter_key_lists.append([primary_id])  # Always at index 0
        for _filter in cls._get_sorted_filters():
            key_list = _filter.get_keys_for_element(element)
            if key_list is None:
                key_list = []
            else:
                key_list = list(key_list)  # Convert set/tuple/generator to list

            # Note that we always add 'None' to the list of keys before we
            # generate the explosion of all possible key combinations.  We
            # do this to support the admin UI wanting to see results that are
            # not filtered on some axis.  Note that this consideration applies
            # for *all* filters, even for filters that will always have a
            # well-defined value for every item (e.g., display language for
            # page views)
            if None not in key_list:
                key_list.append(None)

            key_list.sort()
            filter_key_lists.append(key_list)
        for item in itertools.product(*filter_key_lists):
            yield item

    @classmethod
    def _write_entity(cls, keys, data):
        """Save a result entity initialized w/ primary_id and filter values."""

        if not isinstance(data, basestring):
            data = transforms.dumps(data)
        keys = ast.literal_eval(keys)
        constructor_args = {}
        constructor_args['primary_id'] = keys[0]  # Always at index 0
        constructor_args['data'] = data
        for key, _filter in zip(keys[1:], cls._get_sorted_filters()):
            if key is not None:
                constructor_args[_filter.get_name()] = key
        cls.result_class()(**constructor_args).put()

    @classmethod
    def _get_sorted_filters(cls):
        """Provides a single source of truth for ordering of filter key values.

        Note that map() produces a list of keys rather than a dict of field
        name -> value for efficiency.  We recover the filter names by
        ensuring that the reduce() function uses the exact same ordering,
        since both map() and reduce() use this function.
        """

        filters = list(cls.result_class().get_filters())
        filters.sort(key=lambda _filter: _filter.get_name())
        return filters

    def _create_toplevel_pipeline(self, sequence_num):
        job_runner_args = self._create_job_runner_args(sequence_num)

        result_class = self.result_class()
        cleanup_params = {
            'entity_kind': '%s.%s' % (
                result_class.__module__, result_class.__name__),
            'namespace': self._namespace,
        }
        return PreCleanMapReduceJobPipeline(
            self._namespace, self._job_name, sequence_num, cleanup_params,
            job_runner_args)


class AbstractFilteredSummingMapReduceJob(AbstractFilteredMapReduceJob):
    """Convenience for filterables having a simple numeric total as result."""

    RESULT_KEY = 'sum'

    @classmethod
    def reduce(cls, keys, values):
        _sum = sum(int(value) for value in values)
        cls._write_entity(keys, {cls.RESULT_KEY: _sum})


class AbstractFilteredAveragingMapReduceJob(AbstractFilteredMapReduceJob):
    """Convenience for filterables having a simple numeric average as result."""

    RESULT_KEY = 'average'

    @classmethod
    def reduce(cls, keys, values):
        average = sum(int(value) for value in values) / len(values)
        cls._write_entity(keys, {cls.RESULT_KEY: average})


class StudentTrackFilter(data_sources.AbstractEnumFilter):
    """Reference implementation of a filter class for core functionality."""

    @classmethod
    def get_title(cls):
        return 'Student Track'

    @classmethod
    def get_name(cls):
        return 'student_track'

    @classmethod
    def get_schema(cls):
        reg = schema_fields.FieldRegistry('student_track')
        reg.add_property(schema_fields.SchemaField(
            'student_track', 'Course Track ID', 'integer',
            optional=True, i18n=False))
        return reg.get_json_schema_dict()['properties']

    @classmethod
    def get_choices(cls):
        labels = models.LabelDAO.get_all_of_type(
            models.LabelDTO.LABEL_TYPE_COURSE_TRACK)
        return [
            data_sources.EnumFilterChoice(
                label.title, 'student_track=%s' % label.id)
            for label in labels]

    @classmethod
    def get_keys_for_element(cls, student):
        return [
            int(label_id) for label_id in
            student.get_labels_of_type(models.LabelDTO.LABEL_TYPE_COURSE_TRACK)]
