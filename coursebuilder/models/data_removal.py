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

"""Registration of classes with data attributable to an individual user."""

__author__ = 'Mike gainer (mgainer@google.com)'

from google.appengine.ext import db


class Registry(object):
    """Register classes with data that can be linked to an individual user."""

    _remove_sitewide_by_user_id_functions = []
    _remove_by_user_id_functions = []
    _remove_by_email_functions = []
    _unindexed_entity_classes = {}

    @classmethod
    def register_sitewide_indexed_by_user_id_remover(cls, remover):
        """Register a remover for per-instance data indexed by user_id.

        Callbacks registered here are called only when the user has been
        removed from every individual course in the App Engine instance.
        This is useful for things that are not course-specific, such
        as StudentProfile.

        Args:
          remover: A function to remove DB instances that are indexable by
              user ID.  The function must take exactly one parameter: The
              string constituting the user_id.  (This is the string
              returned from users.get_current_user().user_id()).
        """
        cls._remove_sitewide_by_user_id_functions.append(remover)


    @classmethod
    def register_indexed_by_user_id_remover(cls, remover):
        """Register a function that can remove instances by user_id.

        These items are treated differently from un-indexed items, because we
        want to be able to very rapidly remove the bulk of the data for a
        given user.  Items that are keyed or indexed by user ID tend to
        contain more sensitive PII; non-indexed items will generally be more
        along the lines of user events, etc.

        Also, immediately removing the user record will prevent re-login, and
        that's important for giving users the strong feedback that on
        un-register they really have had their stuff removed.

        Args:
          remover: A function to remove DB instances that are indexable by
              user ID.  The function must take exactly one parameter: The
              string constituting the user_id.  (This is the string
              returned from users.get_current_user().user_id()).
        """
        cls._remove_by_user_id_functions.append(remover)

    @classmethod
    def register_indexed_by_email_remover(cls, remover):
        """Register a function that can remove instances by email address.

        Note that this is necessarily best-effort; while we have an email
        address for the unregistering user, it may not match some other email
        address that was used by that person at some other time.  If email
        is the only way to identify an instance, be careful to consider
        how sensitive the information in such records is.

        Args:
          Remover: A function to remove DB instances that are indexable by
              email address.  The function must take exactly one parameter:
              the email address.

        """
        cls._remove_by_email_functions.append(remover)

    @classmethod
    def register_unindexed_entity_class(cls, entity_class):
        """Register a class needing data removal which is not indexed by user.

        Cleaning user data from these classes launches a map/reduce job to
        inspect each item in the db table.

        Args:
          entity_class: The class representing the database table.  Probably
              derived from entities.BaseEntity; must be derived from db.Model.
              The entity_class must implement a function named get_user_ids(),
              which returns a list of all user_ids relevant for that record.
        """
        if not issubclass(entity_class, db.Model):
            raise ValueError('Registered class %s must extend db.Model' %
                             entity_class)
        getattr(entity_class, 'get_user_ids')  # AttributeError if not present.
        cls._unindexed_entity_classes[entity_class.kind()] = entity_class

    @classmethod
    def get_sitewide_user_id_removers(cls):
        return cls._remove_sitewide_by_user_id_functions

    @classmethod
    def get_user_id_removers(cls):
        return cls._remove_by_user_id_functions

    @classmethod
    def get_email_removers(cls):
        return cls._remove_by_email_functions

    @classmethod
    def get_unindexed_class_names(cls):
        return cls._unindexed_entity_classes.keys()

    @classmethod
    def get_unindexed_classes(cls):
        return cls._unindexed_entity_classes
