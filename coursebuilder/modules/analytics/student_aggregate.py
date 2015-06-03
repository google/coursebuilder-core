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

"""Support for analytics on course dashboard pages."""

__author__ = ['Michael Gainer (mgainer@google.com)']

import collections
import logging
import zlib

from mapreduce import context

from common import schema_fields
from common import utils as common_utils
from controllers import sites
from models import courses
from models import data_sources
from models import entities
from models import jobs
from models import models
from models import transforms

from google.appengine.api import datastore_types
from google.appengine.ext import db

class AbstractStudentAggregationComponent(object):
    """Allows modules to contribute to map/reduce on EventEntity by Student.

    Extension modules that generate events data relating to students may wish
    to make this information available via the data pump to BigQuery.  This
    can be done by having the individual module produce its own data source,
    or by contributing to the Student aggregate .

    Adding to the aggregate is slightly preferred, as that removes the need for
    course administrators to separately push those data sources and to write
    BigQuery SQL to do joins.  Further, adding functionality here will gain some
    cost savings by reducing the number of passes over the EventEntity table.

    Note that any of the functions below can be provided either as
    @classmethod or instance method.  If using @classmethod, all functions
    must be overridden to keep Python happy.

    """

    def get_name(self):
        """Get short name for component.

        Note that while we could use __name__ to get a usable name to
        ensure registered components are unique, having get_name()
        explicitly in the interface permits this interface to be
        implemented as an instance.
        """
        raise NotImplementedError()

    def get_event_sources_wanted(self):
        """Give the matches to "source" in EventEntity this component wants.

        E.g, "enter-page", "attempt-lesson" and so on.
        Returns:
          list of strings for event types we can handle.
        """
        return []

    # pylint: disable=unused-argument
    def build_static_params(self, app_context):
        """Build any expensive-to-calculate items at course level.

        This function is called once at the start of the map/reduce job so
        that implementers can pre-calculate any facts that would be expensive
        to regenerate on each call to process_event().  If no such facts are
        required, return None.  Any type of object may be returned.

        Args:
          app_context: A standard CB application context object.
        Returns:
          Any.
        """
        return None

    # pylint: disable=unused-argument
    def process_event(self, event, static_params):
        """Handle one EventEntity.  Called from map phase of map/reduce job.

        This method is called once for each Event which has a "source" field
        matching one of the strings returned from get_event_sources_wanted().
        This function should produce a record that will be used below in
        produce_aggregate().  The list of all items returned from this
        function for each Student are provided to produce_aggregate().

        Args:
          event: an EventEntity.
          static_params: the value from build_static_params(), if any.
        Returns:
          Any object that can be converted to a string via transforms.dumps(),
          or None.
        """
        return None

    def produce_aggregate(self, course, student, static_params, event_items):
        """Aggregate event-item outputs.  Called from reduce phase of M/R job.

        For each Student in the course for which there were any EventEntity
        recorded, this function is called with the accumulated return values
        produced by process_event(), above.  Note that since even the act of
        registration generates events, every registered student will be
        handled.  Also note that this function will be called even for Student
        entries for which no output was produced by process_event().

        This method must produce a dict corresponding to the schema returned
        from get_schema(), or return None.

        Args:
          course: The Course in which the student and the events are found.
          student: the Student for which the events occurred.
          static_params: the value from build_static_params(), if any.
          event_items: a list of all the items produced by process_event()
              for the given Student.
        Returns:
          A dict corresponding to the declared schema.
        """
        raise NotImplementedError()

    def get_schema(self):
        """Provide the partial schema for results produced.

        This function may return a SchemaField, FieldArray or FieldRegistry.
        This schema element will appear as a top-level component in the master
        schema in the aggregate data source.
        """
        raise NotImplementedError()


class StudentAggregateEntity(entities.BaseEntity):
    """Holds data aggregated from Event entites for a single Student.

    As we run the registered sub-aggregators for the various event types,
    the reduce step of our master map/reduce job will be presented with
    summarized data for all events pertaining to a single Student.  Rather
    than write this large volume of data out to, say, BlobStore, we instead
    prefer to write each Student's aggregated data to one record in the DB.
    Doing this permits us to use existing paginated-rest-data-source logic
    to provide the aggregated student data as a feed to the data pump."""

    data = db.BlobProperty()

    @classmethod
    def safe_key(cls, db_key, transform_fn):
        return db.Key.from_path(cls.kind(), transform_fn(db_key.id_or_name()))


class StudentAggregateGenerator(jobs.MapReduceJob):
    """M/R job to aggregate data by student using registered plug-ins.

    This class coordinates the work of plugin classes registered with
    StudentAggregateComponentRegistry and combines their work into a single
    StudentAggregateEntity record in the datastore.  Plugin classes are
    insulated from one another, and are permitted to fail individually without
    compromising the results contributed for a Student by other plugins.

    """

    @staticmethod
    def get_description():
        return 'student_aggregate'

    @staticmethod
    def entity_class():
        return models.EventEntity

    def build_additional_mapper_params(self, app_context):
        schemas = {}
        schema_names = {}
        ret = {
            'course_namespace': app_context.get_namespace_name(),
            'schemas': schemas,
            'schema_names': schema_names,
            }
        for component in StudentAggregateComponentRegistry.get_components():
            component_name = component.get_name()
            static_value = component.build_static_params(app_context)
            if static_value:
                ret[component_name] = static_value
            schema = component.get_schema()
            if hasattr(schema, 'title'):
                schema_name = schema.title
            else:
                schema_name = schema.name
            schema_names[component_name] = schema_name
            schemas[component_name] = schema.get_json_schema_dict()
        return ret

    @staticmethod
    def map(event):
        for component in (StudentAggregateComponentRegistry.
                          get_components_for_event_source(event.source)):
            component_name = component.get_name()
            params = context.get().mapreduce_spec.mapper.params
            static_data = params.get(component_name)
            value = None
            try:
                value = component.process_event(event, static_data)
            # pylint: disable=broad-except
            except Exception, ex:
                common_utils.log_exception_origin()
                logging.critical('Student aggregation map function '
                                 'component handler %s failed: %s',
                                 component_name, str(ex))
            if value:
                value_str = '%s:%s' % (component_name, transforms.dumps(value))
                yield event.user_id, value_str

    @staticmethod
    def reduce(user_id, values):

        # Convenience for collections: Pre-load Student and Course objects.
        student = None
        try:
            student = models.Student.get_by_user_id(user_id)
        # pylint: disable=broad-except
        except Exception:
            common_utils.log_exception_origin()
        if not student:
            logging.warning(
                'Student for student aggregation with user ID %s '
                'was not loaded.  Ignoring records for this student.', user_id)
            return

        params = context.get().mapreduce_spec.mapper.params
        ns = params['course_namespace']
        app_context = sites.get_course_index().get_app_context_for_namespace(ns)
        course = courses.Course(None, app_context=app_context)

        # Bundle items together into lists by collection name
        event_items = collections.defaultdict(list)
        for value in values:
            component_name, payload = value.split(':', 1)
            event_items[component_name].append(transforms.loads(payload))

        # Build up per-Student aggregate by calling each component.  Note that
        # we call each component whether or not its mapper produced any
        # output.
        aggregate = {}
        for component in StudentAggregateComponentRegistry.get_components():
            component_name = component.get_name()
            static_value = params.get(component_name)
            value = {}
            try:
                value = component.produce_aggregate(
                    course, student, static_value,
                    event_items.get(component_name, []))
                if not value:
                    continue
            # pylint: disable=broad-except
            except Exception, ex:
                common_utils.log_exception_origin()
                logging.critical('Student aggregation reduce function '
                                 'component handler %s failed: %s',
                                 component_name, str(ex))
                continue

            schema_name = params['schema_names'][component_name]
            if schema_name not in value:
                logging.critical(
                    'Student aggregation reduce handler %s produced '
                    'a dict which does not contain the top-level '
                    'name (%s) from its registered schema.',
                    component_name, schema_name)
                continue

            variances = transforms.validate_object_matches_json_schema(
                value[schema_name], params['schemas'][component_name])
            if variances:
                logging.critical(
                    'Student aggregation reduce handler %s produced '
                    'a value which does not match its schema: %s',
                    component_name, ' '.join(variances))
                continue

            aggregate.update(value)

        # Overwrite any previous value.
        # TODO(mgainer): Consider putting records into blobstore.  Some
        # light activity manually producing test data is about 10K unzipped
        # and 1K zipped.  Unlikely that we'd see 1000x this amount of
        # activity, but possible eventually.
        data = zlib.compress(transforms.dumps(aggregate))
        # pylint: disable=protected-access
        if len(data) > datastore_types._MAX_RAW_PROPERTY_BYTES:
            # TODO(mgainer): Add injection and collection of counters to
            # map/reduce job.  Have overridable method to verify no issues
            # occurred when job completes.  If critical issues, mark job
            # as failed, even though M/R completed.
            logging.critical(
                'Aggregated compressed student data is over %d bytes; '
                'cannot store this in one field; ignoring this record!')
        else:
            StudentAggregateEntity(key_name=user_id, data=data).put()


class StudentAggregateComponentRegistry(
    data_sources.AbstractDbTableRestDataSource):

    _components = []
    _components_by_name = {}
    _components_by_schema = {}
    _components_for_event_source = collections.defaultdict(list)

    @classmethod
    def get_name(cls):
        return 'student_aggregate'

    @classmethod
    def get_title(cls):
        return 'Student Aggregate'

    @classmethod
    def get_entity_class(cls):
        return StudentAggregateEntity

    @classmethod
    def required_generators(cls):
        return [StudentAggregateGenerator]

    @classmethod
    def exportable(cls):
        return True

    @classmethod
    def get_default_chunk_size(cls):
        return 100

    @classmethod
    def get_schema(cls, app_context, log, data_source_context):
        ret = schema_fields.FieldRegistry('student_aggregation')
        for component in cls._components:
            ret.add_property(component.get_schema())
        if data_source_context.send_uncensored_pii_data:
            obfuscation = 'Un-Obfuscated'
        else:
            obfuscation = 'Obfuscated'
        description = (obfuscation + ' version of user ID.  Usable to join '
                       'to other tables also keyed on obfuscated user ID.')

        ret.add_property(schema_fields.SchemaField(
            'user_id', 'User ID', 'string', description=description))
        return ret.get_json_schema_dict()['properties']

    @classmethod
    def _postprocess_rows(cls, app_context, data_source_context, schema,
                          log, page_number, rows):
        if data_source_context.send_uncensored_pii_data:
            transform_fn = lambda x: x
        else:
            transform_fn = cls._build_transform_fn(data_source_context)
        ret = []
        for row in rows:
            item = transforms.loads(zlib.decompress(row.data))
            item['user_id'] = transform_fn(row.key().id_or_name())
            ret.append(item)
        return ret

    @classmethod
    def get_schema_name(cls, component):
        schema = component.get_schema()
        if hasattr(schema, 'name'):
            return schema.name
        return schema.title

    @classmethod
    def register_component(cls, component):
        component_name = component.get_name()
        if ':' in component_name:
            raise ValueError('Component names may not contain colons.')
        if component_name in cls._components_by_name:
            raise ValueError(
                'There is already a student aggregation component '
                'named "%s" registered. ' % component_name)
        schema_name = cls.get_schema_name(component)
        if schema_name in cls._components_by_schema:
            raise ValueError(
                'There is already a student aggregation component schema '
                'member named "%s" registered by %s.' % (
                    schema_name,
                    cls._components_by_schema[schema_name].get_name()))
        cls._components.append(component)
        cls._components_by_name[component_name] = component
        cls._components_by_schema[schema_name] = component
        for event_source in component.get_event_sources_wanted():
            cls._components_for_event_source[event_source].append(component)

    @classmethod
    def get_components_for_event_source(cls, source):
        return cls._components_for_event_source.get(source, [])

    @classmethod
    def get_components(cls):
        return cls._components
