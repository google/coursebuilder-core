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

"""Common classes and methods for managing persistent entities."""

__author__ = 'Pavel Simakov (psimakov@google.com)'


from counters import PerfCounter
from google.appengine.ext import db


# datastore performance counters
DB_QUERY = PerfCounter(
    'gcb-models-db-query',
    'A number of times a query()/all() was executed on a datastore.')
DB_GET = PerfCounter(
    'gcb-models-db-get',
    'A number of times an object was fetched from datastore.')
DB_PUT = PerfCounter(
    'gcb-models-db-put',
    'A number of times an object was put into datastore.')
DB_DELETE = PerfCounter(
    'gcb-models-db-delete',
    'A number of times an object was deleted from datastore.')


class BaseEntity(db.Model):
    """A common class to all datastore entities."""

    @classmethod
    def all(cls, **kwds):
        DB_QUERY.inc()
        return super(BaseEntity, cls).all(**kwds)

    @classmethod
    def get(cls, keys):
        DB_GET.inc()
        return super(BaseEntity, cls).get(keys)

    @classmethod
    def get_by_key_name(cls, key_names):
        DB_GET.inc()
        return super(BaseEntity, cls).get_by_key_name(key_names)

    def put(self):
        DB_PUT.inc()
        return super(BaseEntity, self).put()

    def delete(self):
        DB_DELETE.inc()
        super(BaseEntity, self).delete()
