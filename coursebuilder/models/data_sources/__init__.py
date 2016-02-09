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

"""Module providing data source contents via REST interface."""

__author__ = 'Mike Gainer (mgainer@google.com)'

from models.data_sources import base_types
from models.data_sources import source_handler
from models.data_sources import paginated_table
from models.data_sources import registry

# Make these types available at models.data_sources so that client
# code does not have to know about our internal structure.
# pylint: disable=protected-access
AbstractDbTableRestDataSource = paginated_table._AbstractDbTableRestDataSource
AbstractFilter = base_types._AbstractFilter
AbstractEnumFilter = base_types._AbstractEnumFilter
AbstractRangeFilter = base_types._AbstractRangeFilter
AbstractRestDataSource = base_types._AbstractRestDataSource
AbstractSmallRestDataSource = base_types._AbstractSmallRestDataSource
AbstractContextManager = base_types._AbstractContextManager
DbTableContext = paginated_table._DbTableContext
EnumFilterChoice = base_types._EnumFilterChoice
NullContextManager = base_types._NullContextManager
Registry = registry._Registry
SynchronousQuery = base_types._SynchronousQuery
# pylint: enable=protected-access


def _generate_rest_handler(rest_data_source_class):

    # (Package protected) pylint: disable=protected-access
    class CurriedRestHandler(source_handler._AbstractRestDataSourceHandler):
        """Web handler class curried with class of rest data source."""

        @classmethod
        def get_data_source_class(cls):
            return rest_data_source_class

    return CurriedRestHandler


def get_namespaced_handlers():
    """Create URLs + handler classes customized to REST data source types.

    Other modules must register their analytics with this module before
    this module is registered.  This function produces a list of handlers
    for all REST data source URLs in all analytics.

    Returns:
        A (URL, handler) 2-tuple for each rest data source class mentioned
        in any analytic.
    """

    ret = []

    # Convert set into sorted list so WebApp always sees items in the same
    # order.  In theory, this shouldn't matter.  In practice, the difference
    # between theory and practice may be nonzero, so doing this JIC.
    for clazz in sorted(Registry.get_rest_data_source_classes()):
        ret.append(('/rest/data/%s/items' % clazz.get_name(),
                    _generate_rest_handler(clazz)))
    return ret
