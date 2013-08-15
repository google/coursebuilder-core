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

# String. Name of the safe key property used for data export.
SAFE_KEY_NAME = 'safe_key'


def delete(keys):
    """Wrapper around db.delete that counts entities we attempted to get."""
    DB_DELETE.inc(increment=_count(keys))
    return db.delete(keys)


def get(keys):
    """Wrapper around db.get that counts entities we attempted to get."""
    DB_GET.inc(increment=_count(keys))
    return db.get(keys)


def put(keys):
    """Wrapper around db.put that counts entities we attempted to put."""
    DB_PUT.inc(increment=_count(keys))
    return db.put(keys)


def _count(keys):
    # App engine accepts key or list of key; count entities found.
    return len(keys) if isinstance(keys, (list, tuple)) else 1


class ExportEntity(db.Expando):
    """An entity instantiated, but never saved; for data export only.

    Will not work with the webapp.
    """

    def __init__(self, *args, **kwargs):
        assert kwargs.get(SAFE_KEY_NAME)
        super(ExportEntity, self).__init__(*args, **kwargs)

    def get(self):
        raise NotImplementedError

    def put(self):
        raise NotImplementedError


class BaseEntity(db.Model):
    """A common class to all datastore entities."""

    # List of db.Property. The properties on this model that should be purged
    # before export via tools/etl.py because they contain private information
    # about a user. For fields that must be transformed rather than purged, see
    # BaseEntity.for_export().
    _PROPERTY_EXPORT_BLACKLIST = []

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

    @classmethod
    def safe_key(cls, db_key, unused_transform_fn):
        """Creates a copy of db_key that is safe for export.

        Keys may contain sensitive user data, like the user_id of a users.User.
        This method takes a db_key for an entity that is the same kind as cls.
        It returns a new instance of a key for that same kind with any sensitive
        data irreversibly transformed.

        The suggested irreversible transformation is cls.hash. The
        transformation must take a value and a client-defined secret. It must be
        deterministic and nonreversible.

        Args:
            db_key: db.Key of the same kind as cls. Key containing original
                values.
            unused_transform_fn: function that takes a single argument castable
                to string and returns a transformed string of that user data
                that is safe for export. If no user data is sensitive, the
                identity transform should be used. Used in subclass
                implementations.

        Returns:
            db.Key of the same kind as cls with sensitive data irreversibly
            transformed.
        """
        assert cls.kind() == db_key.kind()
        return db_key

    def _get_export_blacklist(self):
        """Collapses all _PROPERTY_EXPORT_BLACKLISTs in the class hierarchy."""
        blacklist = []
        for klass in self.__class__.__mro__:
            if hasattr(klass, '_PROPERTY_EXPORT_BLACKLIST'):
                # Treat as module-protected.
                # pylint: disable-msg=protected-access
                blacklist.extend(klass._PROPERTY_EXPORT_BLACKLIST)
        return sorted(set(blacklist))

    def put(self):
        DB_PUT.inc()
        return super(BaseEntity, self).put()

    def delete(self):
        DB_DELETE.inc()
        super(BaseEntity, self).delete()

    def for_export(self, transform_fn):
        """Creates an ExportEntity populated from this entity instance.

        This method is called during export via tools/etl.py to make an entity
        instance safe for export via tools/etl.py when --privacy is passed. For
        this to obtain,

        1) Properties that need to be purged must be deleted from the instance.
           Subclasses can set these fields in _PROPERTY_EXPORT_BLACKLIST.
        2) Properties that need to be transformed should be modified in subclass
           implementations. In particular, properties with customizable JSON
           contents often need to be handled this way.

        Args:
            transform_fn: function that takes a single argument castable to
                string and returns a transformed string of that user data that
                is safe for export. If no user data is sensitive, the identity
                transform should be used.

        Returns:
            EventEntity populated with the fields from self, plus a new field
            called 'safe_key', containing a string representation of the value
            returned by cls.safe_key().
        """
        properties = {}

        # key is a reserved property and cannot be mutated; write to safe_key
        # instead, but refuse to handle entities that set safe_key themselves.
        # TODO(johncox): reserve safe_key so it cannot be used in the first
        # place?
        assert SAFE_KEY_NAME not in self.properties().iterkeys()
        properties[SAFE_KEY_NAME] = self.safe_key(self.key(), transform_fn)

        for name in self.properties():
            if name not in [prop.name for prop in self._get_export_blacklist()]:
                properties[name] = getattr(self, name)

        return ExportEntity(**properties)
