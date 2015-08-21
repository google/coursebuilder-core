# Copyright 2015 Google Inc. All Rights Reserved.
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

"""DB Model types used for tracking data removal."""

import collections

# DO NOT import any modules from Course Builder here; this module is used in
# common with a Google-specific tool for Google-provided courses.  That tool
# doesn't need the extra work of picking up any dependencies (besides this
# file) from CB.

from google.appengine.ext import db


class ImmediateRemovalState(db.Model):
    """Removal state for a given student.

    This needs to be separate from Student so as to track the condition where
    records indexable by user ID/email have been removed, but other records
    have not.
    """

    STATE_REGISTERED = 1
    STATE_DELETION_PENDING = 2
    # There is no STATE_DELETED - having one would mean we were holding
    # per-user data for a user for whom all data should be removed.
    state = db.IntegerProperty(indexed=False)
    last_modified = db.DateTimeProperty(auto_now=True, indexed=False)

    @classmethod
    def get_by_user_id(cls, user_id):
        return cls.get_by_key_name(user_id)

    @classmethod
    def delete_by_user_id(cls, user_id):
        db.delete(db.Key.from_path(cls.kind(), user_id))

    @classmethod
    def create(cls, user_id):
        # We would like to be able use cls.get_or_insert() here, but that
        # function uses a transaction internally, and we are already in a
        # transaction due to user account creation (for atomically adding
        # Student and StudentPreferences), so we need to re-invent that wheel
        # here.  :-(
        instance = cls.get_by_key_name(user_id)
        if not instance:
            instance = cls(key_name=user_id, state=cls.STATE_REGISTERED)
            instance.put()
        return instance

    @classmethod
    def is_deletion_pending(cls, user_id):
        """Can't re-register while deletion of old records is pending."""
        item = cls.get_by_key_name(user_id)
        return item is not None and item.state == cls.STATE_DELETION_PENDING

    @classmethod
    def set_deletion_pending(cls, user_id):
        instance = cls.create(user_id)
        instance.state = cls.STATE_DELETION_PENDING
        instance.put()

    @classmethod
    def safe_key(cls, db_key, transform_fn):
        return db.Key.from_path(cls.kind(), transform_fn(db_key.id_or_name()))


class BatchRemovalState(db.Model):
    """Represents intent to perform removal for entities not indexed by user_id.

    Datastore resources that contain user data, but which are not indexed
    by user id must also be wiped out.  This is done on a periodic basis
    by a cron task which starts map/reduce or similar jobs to clean out
    datastore tables.

    This record type is keyed by user id, and contains the names of resource
    kinds which have not yet been deleted.  On creation, the list of resource
    names will be initialized from the list of registered un-indexed entity
    classes; see models.data_removal.Registry.
    """

    resource_types = db.StringListProperty(indexed=False)
    DONE_WITH_REMOVAL_HOOKS = []

    @classmethod
    def create(cls, user_id, resource_types):
        instance = cls.get_or_insert(user_id)
        instance.resource_types = resource_types
        instance.put()

    @classmethod
    def delete_by_user_id(cls, user_id):
        db.delete(db.Key.from_path(cls.kind(), user_id))

    @classmethod
    def get_all_work(cls):
        """Gets pending work organized as dict of entity name -> user_ids."""

        items = cls.all().run()
        ret = collections.defaultdict(list)
        for item in items:
            user_id = item.key().name()

            # Note user as needing batch work for all batch items that have
            # not yet marked themselves as completed by removing their names
            # from this list of resource_types needing cleanup.
            for resource_type in item.resource_types:
                ret[resource_type].append(user_id)

            # Save users with no more batch work to do in a special list.
            if not item.resource_types:
                ret[None].append(user_id)
        return ret

    @classmethod
    def get_by_user_ids(cls, user_ids):
        keys = [db.Key.from_path(cls.kind(), user_id) for user_id in user_ids]
        return db.get(keys)

    @classmethod
    def get_by_user_id(cls, user_id):
        return db.get(db.Key.from_path(cls.kind(), user_id))

    @classmethod
    def safe_key(cls, db_key, transform_fn):
        return db.Key.from_path(cls.kind(), transform_fn(db_key.id_or_name()))
