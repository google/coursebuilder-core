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

"""Module providing base types for analytics."""

__author__ = 'Mike Gainer (mgainer@google.com)'

import re


class _DataSource(object):
    """Common base class for all kinds of data sources."""

    @staticmethod
    def required_generators():
        """Tell what long-running jobs (if any) are required for this source.

        Return an array of classes.  The empty array is allowed if
        your data source does not depend on any data sources.  All
        data sources named must derive from DurableJobBase.  When the
        framework calls to the display content generator function, the
        jobs will be provided singly as parameters.  E.g., if you
        return [FooGenerator, BarGenerator] here, your fill_values
        method should be declared:

        @staticmethod
        def fill_values(app_context, template_values, foo_generator_job,
                        bar_generator_job)
            foo_results = transforms.loads(foo_generator_job.load().output)
            template_values['foo_widgets'] = foo_results['widgets']
            template_values['foo_frammis'] = foo_results['frammis']
            ... and similarly for bar_generator_job. ...
        Returns:
          Array of types derived from DurableJobBase.  May be empty list.
        """

        return []

    @classmethod
    def verify_on_registration(cls):
        """Override to perform sanity-checking at registration time."""
        pass


class _SynchronousQuery(_DataSource):
    """Inherit from this class to indicate your data source is synchronous.

    By synchronous, we mean that when the dashboard display is
    created, we directly generate HTML from a template and parameters,
    as opposed to asynchronously fetching data up to the page (via
    JavaScript) after the page has loaded.

    It is OK for a data source to inherit both from SynchronousQuery
    and from _AbstractRestDataSource.  In this situation, fill_values() will
    be called synchronously, and fetch_values asynchronously when
    the JavaScript on the page makes a JSON request.
    """

    @staticmethod
    def fill_values(app_context, template_values, required_generator_job_1,
                    required_generator_job_2, required_generator_job_N):
        """Set key/value strings for use in HTML template expansion.

        Args:
            app_context: the context taking the request.  This can be used to
                identify the namespace for the request.
            template_values: A hash to be filled in by fill_values.  Its
                contents are provided to the template interpreter.  All
                sources used by a single analytic contribute to the same
                template_values dict; be careful to avoid name collisions.
            required_generator_job_1: Your class may declare that it it needs
                one or more generators from which to obtain data values.  You
                do this by overriding _DataSource.required_generators() to
                name the class definitions.  When this function is called, the
                Job objects corresponding to those generators are passed in to
                this function (in the same order in which they were specified
                in the return value from required_generators().  Your class
                should then extract the results from the job and return them
                from this function.
            required_generator_job_2: as required_generator_job_1
            required_generator_job_N: as required_generator_job_1
        Returns:
            Return value is ignored.
        """

        raise NotImplementedError(
            'Classes which synchronously provide parameters for '
            'expansion into their HTML templates must implement the '
            'fill_values method.')


class _AbstractFilter(object):
    """Describes a filterable field in a REST data source."""

    KIND_ENUM = 'enum'
    KIND_RANGE = 'range'

    @classmethod
    def get_title(cls):
        """Human-friendly English display title for this filter."""
        raise NotImplementedError()

    @classmethod
    def get_name(cls):
        """JavaScript-friendly identifier.  Only lowercase and underscores.

        Also used to match filters to field names when constructiong
        AbstractFilteredEntity instances.
        """
        raise NotImplementedError()

    @classmethod
    def get_kind(cls):
        """Tell UI generator what kind of filter we implement.

        Returns one of the KIND_ defintions.
        """
        raise NotImplementedError()

    @classmethod
    def get_schema(cls):
        """Extend provided schema with additional filterable fields.

        These additional fields are added so that sanity checks on filtered
        fields bing part of the schema for the entity class for the data
        source.

        Implementations should construct a schema_fields.FieldRegistry object,
        and return: my_registry.get_json_schema_dict['properties'] for
        commonality with the schemas returned by data source implementations.
        """
        raise NotImplementedError()

    @classmethod
    def get_keys_for_element(cls, element):
        """Return a list of all filter-match values for this element.

        If there are no matches, None, an empty list, or a list containing
        None are all acceptable ways of expressing that.

        Args:
          element: The element passed in to the map() function of your map/
              reduce job.

        Return:
          None, [None], [] imply no matching keys.
          If there are matching keys, return an iterable of those.  You may
          optionally include None on that list.
        """
        raise NotImplementedError()


class _EnumFilterChoice(object):

    def __init__(self, label, value, selected=False):
        """Constructor.

        Args:
          label: Displayed name for enum selection.
          value: A filter expression.  See PaginatedDataSource.  E.g,
              'student_group=1234'
        """
        self.label = label
        self.value = value


class _AbstractEnumFilter(_AbstractFilter):

    @classmethod
    def get_kind(cls):
        return _AbstractFilter.KIND_ENUM

    @classmethod
    def get_choices(cls):
        """Return a list of EnumFilterChoice instances."""
        raise NotImplementedError()


class _AbstractRangeFilter(_AbstractFilter):

    @classmethod
    def get_kind(cls):
        return _AbstractFilter.KIND_RANGE

    @classmethod
    def get_min_value(cls):
        """Return min value (inclusive) that the filterable item may take."""
        raise NotImplementedError()

    @classmethod
    def get_max_value(cls):
        """Return max value (exclusive) that the filterable item may take."""
        raise NotImplementedError()


class _AbstractRestDataSource(_DataSource):
    """Provide paginated data supplied to clients via a REST API.

    This data source will be served from a REST-style URL.  The
    canonical use of this data is to provide raw input to JavaScript
    charting/graphing libraries on the dashboard's analytics page.
    However, the source is available for any authorized user to make
    use of however he sees fit.

    It is OK for a data source to inherit both from SynchronousQuery
    and from _AbstractRestDataSource.  In this situation, fill_values() will
    be called synchronously, and fetch_values asynchronously when
    the JavaScript on the page makes a JSON request.
    """

    # This limit is based on manual experiments with CourseBuilder and
    # simulated randomized student data.  10,000 is plenty fast,
    # and 400,000 items causes a several-second delay in repainting of
    # graphs.  Picking 10,000 for safety against larger object sizes.
    RECOMMENDED_MAX_DATA_ITEMS = 10000

    # Mantain registry of sources by name so that we can guarantee that
    # names will be unique.
    _rest_data_sources_by_name = {}

    @classmethod
    def get_name(cls):
        raise NotImplementedError(
            'Classes derived from _AbstractRestDataSource must provide a name '
            'by which they are known.  This name must be composed only '
            'of lowercase alphabetics, numerics and underscores.  (This'
            'name will, among other uses, be employed to create '
            'JavaScript identifiers.)  Also, this name must be globally '
            'unique within a CourseBuilder installation.')

    @classmethod
    def get_title(cls):
        raise NotImplementedError(
            'Classes derived from _AbstractRestDataSource must provide a '
            'title string for display on web pages.  This is used in the '
            'context of controls to select a particular page.')

    @classmethod
    def get_filters(cls):
        """Return list of filters for this type.

        These should correspond to access patterns that permit filtering
        on the declared fields, and which are stable (returning the same
        results on repeated queries).  E.g., for data sources pulling from
        DB tables, these would correspond to indexed fields.  Note that it
        is not required that all indexed fields be declared here, but
        rather only those that should be publicly available.

        Implementing classes should return an iterable of AbstractFilter
        classes.
        """
        return ()

    @classmethod
    def exportable(cls):
        return False

    @classmethod
    def get_default_chunk_size(cls):
        """Tell what the recommended number of items per page is.

        This will vary based on the sizes of the items returned.  Note that
        this is not an absolute maximum; the UI may request more than this
        value (up to the absolute maximum imposed by App Engine overall
        response size limits).

        This value can be set to zero to indicate that the resource does not
        support or require paging.  This is useful for, e.g., course-level
        items (units, assessments) of which we expect to have never more than
        tens to hundreds.

        Returns:
            Recommended maximum items per page of data source items
        """
        return cls.RECOMMENDED_MAX_DATA_ITEMS

    @classmethod
    def get_context_class(cls):
        raise NotImplementedError(
            'Classes derived from _AbstractRestDataSource must provide a class '
            'inherited from _AbstractContextManager.  This class should handle '
            'building and maintaining a context used for storing '
            'parameters and optimizations for fetching values.  If '
            'no context is needed, the NullContextManager class may '
            'be returned from this function.')

    @classmethod
    def get_schema(cls, app_context, log, source_context):
        raise NotImplementedError(
            'Classes derived from _AbstractRestDataSource must be able to '
            'statically produce a JSON schema describing their typical '
            'contents.  This function must return a dict as produced by '
            'FieldRegistry.get_json_schema_dict().')

    @classmethod
    def fetch_values(cls, app_context, source_context, schema, log,
                     page_number, foo_job):
        """Provide data to be returned from this source.

        This function should return a plain Python array of dicts.  (The point
        here is that the data must not require any postprocessing before it is
        converted to a JSON string.)

        Args:
            app_context: The application context for the current request;
                useful for namespacing any datastore queries you may need to
                perform.
            source_context: A context instance/object as produced from a
                _AbstractContextManager.build_from_web_request() or
                build_from_dict() call.  This class specifies the exact
                sub-type of _AbstractContextManager that should be used with
                it, so the specific type of context object can be relied upon.
            schema: A schema, as returned from the get_schema() method.  It is
                possible that the schema may need to be modified as the result
                of a get_data operation -- e.g., to include fields that are
                present in the actual data even though not mentioned in the
                formal type definition, and so this field is provided to
                the fetch_values() operation, just-in-case.
            log: A Log instance; use this to remark on any problems or
                progress during processing.
            page_number: The number of the page of data items desired.
            foo_job: One parameter for each of the job classes returned by
                required_generators() (if any), in that same order.  These are
                passed as separate parameters for convenience of naming in
                your code.
        """
        raise NotImplementedError(
            'Data sources which provide asynchronous feeds must '
            'implement the fetch_values() method.')

    @classmethod
    def verify_on_registration(cls):
        source_name = cls.get_name()
        if not re.match('^[_0-9a-z]+$', source_name):
            raise ValueError(
                'REST data source name "%s" ' % source_name +
                'must contain only lowercase letters, '
                'numbers or underscore characters')
        other_class = cls._rest_data_sources_by_name.get(
            source_name, None)
        if other_class:
            raise ValueError(
                'Error: the name "%s" ' % source_name +
                'is already registered to the class ' +
                '%s' % other_class.__module__ +
                '.%s' % other_class.__name__ +
                '; you cannot register '
                '%s' % cls.__module__ +
                '.%s' % cls.__name__ +
                'with the same name.')


class _AbstractContextManager(object):
    """Interface for managing contexts used by _AbstractRestDataSource types.

    When a REST request is made, a context is returned along with the data and
    other items.  Subsequent REST requests should provide the context object.
    This permits the data fetching class to retain state across operations.
    Generally, a _AbstractContextManager type will be quite specific to the
    type of _AbstractRestDataSource.  However, the responsibilities of context
    management are quite specific and thus these are separated into a distinct
    interface.

    Note that all the methods in this class are specifed as @classmethod.
    This is intentional: It permits this class to return either instances
    of itself, another type, or a simple dict.
    """

    @classmethod
    def build_from_web_request(cls, params, default_chunk_size):
        """Build a context instance given a set of URL parameters."""
        raise NotImplementedError(
            'Subclasses of _AbstractContextManager must implement a function '
            'to read URL parameters specific to a context/data-source '
            'and convert that into a context object.'
            ''
            'NOTE: If there are _no_ parameters, this method should '
            'return None.  This allows us callers to pass only the '
            'source_context parameter and not have to re-specify '
            'query parameters on each request.  (If this function returns '
            'a default context, it will likely mismatch with the previous '
            'version, and the old version will be discarded, losing '
            'an opportunity for optimizing queries.')

    @classmethod
    def save_to_dict(cls, context):
        """Convert a context into a simple Python dict."""
        raise NotImplementedError(
            'Subclasses of _AbstractContextManager must provide a method to '
            'convert a context into a simple dict to permit serialization of '
            'the context so that it may be encrypted and returned along with '
            'the rest of the REST response.')

    @classmethod
    def build_from_dict(cls, prev_dict):
        """Build a context from a dict previously returned by save_to_dict()."""
        raise NotImplementedError(
            'When a REST call returns, the save_to_dict() method is called to '
            'convert the context object into a simple Python dict to permit '
            'serialization.  This is then serialized, encrypted, and '
            'returned to the caller.  On subsequent calls, the caller '
            'provides the returned context parameter.  This is decrypted '
            'and reified into a dict.  This method should convert '
            'that dict back into a context.')

    @classmethod
    def build_blank_default(cls, params, default_chunk_size):
        """Build a default version of the context."""
        raise NotImplementedError(
            'When build_from_web_request() returns None, this function is used '
            'to build a default version of a context.')

    @classmethod
    def get_public_params_for_display(cls, context):
        """Provide a human-readable version of the context."""
        raise NotImplementedError(
            'Subclasses of _AbstractContextManager must provide a method to '
            'render a context\'s main features as a simple Python type '
            '(usually a dict of name/value pairs).  This is returned in the '
            'body of REST responses so that humans can manually inspect and '
            'verify operation during development.')

    @classmethod
    def equivalent(cls, context_one, context_two):
        """Tell whether two contexts are equivalent."""
        raise NotImplementedError(
            'Subclasses of _AbstractContextManager must provide a method to '
            'tell whether two contexts are equivalent.  REST requests may '
            'contain a previously-saved context as well as HTML parameters.  '
            'If the context built from one does not match the context built '
            'from the other, the old context must be discarded.  Note that '
            'not all fields need to match for contexts to be equivalent; '
            'only the fields that define the data return need to be '
            'identical.  Any saved state used for optimization need not be '
            '(and will probably not be) present in the HTML parameters.')


class _NullContextManager(_AbstractContextManager):
    """An _AbstractContextManager used when a real context is not required."""

    @classmethod
    def build_from_web_request(cls, params, default_chunk_size):
        return {'null_context': 'null_context'}

    @classmethod
    def build_from_dict(cls, prev_dict):
        return {'null_context': 'null_context'}

    @classmethod
    def save_to_dict(cls, context):
        return context

    @classmethod
    def build_blank_default(cls, params, default_chunk_size):
        return {'null_context': 'null_context'}

    @classmethod
    def get_public_params_for_display(cls, context):
        return context

    @classmethod
    def equivalent(cls, context_one, context_two):
        return context_one == context_two


class _AbstractSmallRestDataSource(_AbstractRestDataSource):
    """Default methods for data source classes not requiring a context.

    This is most commonly the case when a REST data source is based on
    a resource that is always going to be small enough to be sent in
    a single page.  E.g., items based on course items.  There will at
    most be hundreds, or possibly thousands of units, questions, etc.
    This is well within the recommended limit of 10,000.
    """

    @classmethod
    def get_context_class(cls):
        # Expect at most hundreds of course elements; no need for pagination,
        # so null context is fine.
        return _NullContextManager

    @classmethod
    def get_default_chunk_size(cls):
        return 0  # Meaning we don't require or support paginated access.
