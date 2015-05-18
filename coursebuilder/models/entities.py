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
import transforms

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

    # List of db.Property, or string.  This lists the properties on this
    # model that should be purged before export via tools/etl.py because they
    # contain private information about a user.  If a property is internally
    # structured, the name may identify sub-components to remove.  E.g.,
    # for a record of type Student, you might specify:
    # _PROPERTY_EXPORT_BLACKLIST = [
    #     name,                        # A db.Property in Student
    #     'additional_fields.gender',  # A named sub-element
    #     'additional_fields.age',     # ditto.
    #     ]
    # This syntax permits non-PII fields (e.g. 'additional_fields.course_goal')
    # to remain present.  It is harmless to name items that are not present;
    # this permits backward compatibility with older versions of DB entities.
    #
    # For fields that must be transformed rather than purged, see
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

    @classmethod
    def _get_export_blacklist(cls):
        """Collapses all _PROPERTY_EXPORT_BLACKLISTs in the class hierarchy."""
        blacklist = []
        for klass in cls.__mro__:
            if hasattr(klass, '_PROPERTY_EXPORT_BLACKLIST'):
                # Treat as module-protected.
                # pylint: disable=protected-access
                blacklist.extend(klass._PROPERTY_EXPORT_BLACKLIST)

        for index, item in enumerate(blacklist):
            if isinstance(item, db.Property):
                blacklist[index] = item.name
            elif isinstance(item, basestring):
                pass
            else:
                raise ValueError(
                    'Blacklist entries must be either a db.Property ' +
                    'or a string.  The entry "%s" is neither. ' % str(item))
        return sorted(set(blacklist))

    def put(self):
        DB_PUT.inc()
        return super(BaseEntity, self).put()

    def delete(self):
        DB_DELETE.inc()
        super(BaseEntity, self).delete()

    @classmethod
    def delete_by_key(cls, id_or_name):
        delete(db.Key.from_path(cls.kind(), id_or_name))

    @classmethod
    def delete_by_user_id_prefix(cls, user_id):
        """Delete items keyed by a prefix of user ID and some suffix.

        For example, StudentPropertyEntity is keyed with a name string
        composed of the user ID, a hyphen, and an property name.  Since
        we cannot simply look up items by user_id as a key, we do an
        index range scan starting from the user_id up to but not
        including the user_id incremented by one.

        Args:
          user_id: User ID as found in Student.user_id.
        """
        if user_id.isdigit():
            # Obfuscated IDs only ever contain characters in 0...9.
            next_user_id = str(int(user_id) + 1)
        else:
            # But this is not true in dev_appserver, which just re-uses the
            # email address.
            next_user_id = user_id[:-1] + unichr(ord(user_id[-1]) + 1)
        query = cls.all(keys_only=True)
        query.filter('__key__ >=', db.Key.from_path(cls.kind(), user_id))
        query.filter('__key__ <', db.Key.from_path(cls.kind(), next_user_id))
        delete(query.run())

    def _properties_for_export(self, transform_fn):
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

        Raises:
            ValueError: if the _PROPERTY_EXPORT_BLACKLIST contains anything
            other than db.Property references or strings.

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

        for name, prop in self.properties().items():
            if isinstance(prop, db.ReferenceProperty):
                referent = getattr(self, name)
                if referent:
                    unsafe_key = referent.key()
                    safe_key = referent.safe_key(unsafe_key, transform_fn)
                    properties[name] = str(safe_key)
            else:
                properties[name] = getattr(self, name)
        return properties

    def for_export(self, transform_fn):
        properties = self._properties_for_export(transform_fn)

        # Blacklist may contain db.Property, or names as strings.  If string,
        # the name may be a dotted list of containers.  This is useful for
        # redacting sub-items.  E.g., for the type Student,
        # specifying 'additional_items.name' would remove the PII item for
        # the student's name, but not affect additional_items['goal'],
        # (the student's goal for the course), which is not PII.
        for item in  self._get_export_blacklist():
            self._remove_named_component(item, properties)
        return ExportEntity(**properties)

    def for_export_unsafe(self):
        """Get properties for entity ignoring blacklist, and without encryption.

        Using this function is strongly discouraged.  The only situation in
        which this function is merited is for the export of data for analysis,
        where that analysis:

        - Requires PII (e.g., gender, age, detailed locale, income level, etc.)
        - Will be aggregated such that individuals' PII is not retained
        - Subject to a data retention policy with a maximum age.

        In particular, the Data Pump will not infrequently need to send
        per-Student data.  This will often contain user-supplied PII in the
        'additional_fields' member.  This function permits the use of BigQuery
        for analyses not shipped with base CourseBuilder.

        (Note that BigQuery permits specification of a maximum data retention
        period, and the Data Pump sets this age by default to 30 days.
        This is overridable, but only on individual requests)

        Returns:
          An ExportEntity (db.Expando) containing the entity's properties.
        """

        properties = self._properties_for_export(lambda x: x)
        return ExportEntity(**properties)

    @classmethod
    def _remove_named_component(cls, spec, container):
        name, tail = spec.split('.', 1) if '.' in spec else (spec, None)

        if isinstance(container, dict) and name in container:
            if tail:
                tmp_dict = transforms.nested_lists_as_string_to_dict(
                    container[name])
                if tmp_dict:
                    cls._remove_named_component(tail, tmp_dict)
                    container[name] = transforms.dict_to_nested_lists_as_string(
                        tmp_dict)
                else:
                    cls._remove_named_component(tail, container[name])
            else:
                del container[name]
