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

"""Access AppEngine DB tables via AbstractRestDataSource interface."""

__author__ = 'Mike Gainer (mgainer@google.com)'

import copy
import functools
import re

from common import crypto
from common.utils import Namespace
from models import entity_transforms
from models import transforms
from models.data_sources import base_types
from models.data_sources import utils as data_sources_utils

from google.appengine.ext import db


# Package-protected pylint: disable=protected-access
class _AbstractDbTableRestDataSource(base_types._AbstractRestDataSource):
    """Implements a paged view against a single DB table."""

    @classmethod
    def get_entity_class(cls):
        raise NotImplementedError(
            'Do not use this class directly; call paginated_table_source() '
            'to build a curried version.')

    @classmethod
    def get_name(cls):
        raise NotImplementedError(
            'Do not use this class directly; call paginated_table_source() '
            'to build a curried version.')

    @classmethod
    def get_context_class(cls):
        return _DbTableContext

    @classmethod
    def get_schema(cls, app_context, log, source_context):
        clazz = cls.get_entity_class()
        if source_context.send_uncensored_pii_data:
            registry = entity_transforms.get_schema_for_entity_unsafe(clazz)
        else:
            registry = entity_transforms.get_schema_for_entity(clazz)
        return registry.get_json_schema_dict()['properties']

    @classmethod
    def fetch_values(cls, app_context, source_context, schema, log,
                     sought_page_number, *unused_jobs):
        with Namespace(app_context.get_namespace_name()):
            stopped_early = False
            while len(source_context.cursors) < sought_page_number:
                page_number = len(source_context.cursors)
                query = cls._build_query(source_context, schema, page_number,
                                         log)
                rows = cls._fetch_page(source_context, query, page_number, log)

                # Stop early if we notice we've hit the end of the table.
                if len(rows) < source_context.chunk_size:
                    log.warning('Fewer pages available than requested.  '
                                'Stopping at last page %d' % page_number)
                    stopped_early = True
                    break

            if not stopped_early:
                page_number = sought_page_number
                query = cls._build_query(source_context, schema, page_number,
                                         log)
                rows = cls._fetch_page(source_context, query, page_number, log)

                # While returning a page with _no_ items for the 'last' page
                # is technically correct, it tends to have unfortunate
                # consequences for dc/crossfilter/d3-based displays.
                if not rows:
                    page_number = sought_page_number - 1
                    log.warning('Fewer pages available than requested.  '
                                'Stopping at last page %d' % page_number)
                    query = cls._build_query(source_context, schema,
                                             page_number, log)
                    rows = cls._fetch_page(source_context, query,
                                           page_number, log)

            return cls._postprocess_rows(
                app_context, source_context, schema, log, page_number, rows
                ), page_number

    @classmethod
    def _postprocess_rows(cls, unused_app_context, source_context,
                          schema, unused_log, unused_page_number,
                          rows):
        transform_fn = cls._build_transform_fn(source_context)
        if source_context.send_uncensored_pii_data:
            entities = [row.for_export_unsafe() for row in rows]
        else:
            entities = [row.for_export(transform_fn) for row in rows]
        dicts = [transforms.entity_to_dict(entity) for entity in entities]
        return [transforms.dict_to_json(d) for d in dicts]

    @classmethod
    def _build_query(cls, source_context, schema, page_number, log):
        query = cls.get_entity_class().all()
        cls._add_query_filters(source_context, schema, page_number, query)
        cls._add_query_orderings(source_context, schema, page_number, query)
        cls._add_query_cursors(source_context, schema, page_number, query, log)
        return query

    FILTER_RE = re.compile('^([a-zA-Z0-9_]+)([<>=]+)(.*)$')
    SUPPORTED_OPERATIONS = ['=', '<', '>', '>=', '<=']

    @classmethod
    def _add_query_filters(cls, source_context, schema, page_number, query):
        for filter_spec in source_context.filters:
            parts = cls.FILTER_RE.match(filter_spec)
            if not parts:
                raise ValueError(
                    'Filter specification "%s" ' % filter_spec +
                    'is not of the form: <name><op><value>')
            name, op, value = parts.groups()
            if op not in cls.SUPPORTED_OPERATIONS:
                raise ValueError(
                    'Filter specification "%s" ' % filter_spec +
                    'uses an unsupported comparison operation "%s"' % op)

            if name not in schema:
                raise ValueError(
                    'Filter specification "%s" ' % filter_spec +
                    'calls for field "%s" ' % name +
                    'which is not in the schema for '
                    'type "%s"' % cls.get_entity_class().__name__)
            converted_value = transforms.json_to_dict(
                {name: value},
                {'properties': {name: schema[name]}})[name]
            query.filter('%s %s' % (name, op), converted_value)

    @classmethod
    def _add_query_orderings(cls, source_context, schema, page_number, query):
        for ordering in source_context.orderings:
            query.order(ordering)

    @classmethod
    def _add_query_cursors(cls, source_context, schema, page_number, query,
                           log):
        start_cursor = source_context.cursors.get(str(page_number), None)
        end_cursor = source_context.cursors.get(str(page_number + 1), None)
        log.info('fetch page %d start cursor %s; end cursor %s' %
                 (page_number,
                  'present' if start_cursor else 'missing',
                  'present' if end_cursor else 'missing'))
        query.with_cursor(start_cursor=start_cursor, end_cursor=end_cursor)

    @classmethod
    def _fetch_page(cls, source_context, query, page_number, log):
        limit = None
        if (str(page_number + 1)) not in source_context.cursors:
            limit = source_context.chunk_size
            log.info('fetch page %d using limit %d' % (page_number, limit))
        results = query.fetch(limit=limit, read_policy=db.EVENTUAL_CONSISTENCY)
        if (str(page_number + 1)) not in source_context.cursors:
            cursor = query.cursor()
            if cursor:
                if len(results) >= source_context.chunk_size:
                    source_context.cursors[str(page_number + 1)] = cursor
                    log.info('fetch page %d saving end cursor' % page_number)
                else:
                    log.info('fetch page %d is partial; not saving end cursor'
                             % page_number)
            else:
                log.info('fetch_page %d had no end cursor' % page_number)
        return results

    @classmethod
    def _build_transform_fn(cls, context):
        if not context.pii_secret:
            # This value is used in key generation in entities, and so
            # cannot be None or an empty string; the appengine DB internals
            # will complain.
            return lambda pii: 'None'
        return functools.partial(crypto.hmac_sha_2_256_transform,
                                 context.pii_secret)


# Package-protected pylint: disable=protected-access
class _DbTableContext(base_types._AbstractContextManager):
    """Save/restore interface for context specific to DbTableRestDataSource.

      chunk_size=<N>: Specify the number of data items desired per page.
          If not provided, the default value is
          base_types._AbstractRestDataSource.RECOMMENDED_MAX_DATA_ITEMS.
      filters=<filter>: May be specified zero or more times.  Each
          filter must be of the form: <name><comparator><literal>
          Here, <name> is the name of a field on which to filter.
          The <comparator> is one of "=", "<", ">", "<=", ">='
            with the obvious meaning.
          Lastly, <literal> is a literal value of a type matching the
            filtered field.
      orderings=<name>:  May be specified zero or more times.  This
          specifies a sort order based on a field.  The format is
          <field> or <field>.asc or <field>.desc, where <field> is
          the name of a field.  Note that if a less-than or greater-than
          filter is applied, these fields must also be ordered by before
          you specify any other order-by fields.
    """

    # Classes defining various versions of source_context used for
    # DbTableRestDataSource.
    class _TableContext1(object):

        def __init__(self, version, chunk_size, filters, orderings, cursors,
                     pii_secret, send_uncensored_pii_data=False):
            """Set up a context.

            Note: This plain-old-data class is being used in preference over a
            collections.namedtuple(), because for export to the JS on a page, we
            want to be able to "just get all the members", which is done using
            the __dict__ member.  This works fine for namedtuple proper, but
            when a namedtuple is serialized (pickled) and then unpickled, it
            appears to come out as some type that acts like a namedtuple
            w.r.t. the individual elements, but the __dict__ member is not
            present.  This situation never seems to come up in dev environments,
            but it does occur in production reliably enough to count as a bug.
            Thus we make this class by hand, the old fashioned way.

            Args:
              version: Always 1 to match TableContext1
              chunk_size: Goal number of items in each page.
              filters: List of strings of form <field>.<op>.<value>
              orderings: List of strings of form <field>.{asc|desc}
              cursors: List of opaque AppEngine DB cursor strings, one per page
              pii_secret: Session-specific encryption key for PII data.
            """
            self.version = version
            self.chunk_size = chunk_size
            self.filters = filters
            self.orderings = orderings
            self.cursors = cursors
            self.pii_secret = pii_secret

            # This field is present, but normally never set.  In one-off
            # requests from the Data Pump, where the administrator has checked
            # a checkbox, un-blacklisted data is available.  Note that setting
            # this flag will also almost certainly change the reported schema.
            self.send_uncensored_pii_data = False

    @classmethod
    def build_from_web_request(cls, params, default_chunk_size):
        chunk_size = params.get('chunk_size')
        filters = params.get_all('filter')
        orderings = params.get_all('ordering')
        if not chunk_size and not filters and not orderings:
            return None

        chunk_size = int(chunk_size or default_chunk_size)
        secret = cls._build_secret(params)
        return cls._TableContext1(1, chunk_size, filters, orderings, {}, secret)

    @classmethod
    def build_from_dict(cls, context_dict):
        version = context_dict.get('version', -1)
        if version == 1:
            return cls._TableContext1(**context_dict)
        else:
            raise NotImplementedError(
                'Source context version %d is not supported.' % version)

    @classmethod
    def build_blank_default(cls, params, default_chunk_size):
        secret = cls._build_secret(params)
        return cls._TableContext1(
            1,
            default_chunk_size,
            [],  # no filters
            [],  # no orderings
            {},  # no cursors
            secret)

    @classmethod
    def save_to_dict(cls, context):
        # convert namedtuple to regular Python dict
        return context.__dict__

    @classmethod
    def get_public_params_for_display(cls, context):
        ret = copy.copy(context.__dict__)
        del ret['version']
        del ret['cursors']
        del ret['pii_secret']
        del ret['send_uncensored_pii_data']
        return ret

    @classmethod
    def equivalent(cls, new_context, old_context):
        return (
            new_context.version == old_context.version and
            new_context.chunk_size == old_context.chunk_size and
            new_context.filters == old_context.filters and
            new_context.orderings == old_context.orderings)

    @classmethod
    def _build_secret(cls, params):
        data_source_token = params.get('data_source_token')
        return crypto.generate_transform_secret_from_xsrf_token(
            data_source_token,
            data_sources_utils.DATA_SOURCE_ACCESS_XSRF_ACTION)
