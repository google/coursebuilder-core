# Copyright 2013 Google Inc. All Rights Reserved.
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

"""Core data model classes."""

__author__ = 'Pavel Simakov (psimakov@google.com)'

import appengine_config
from config import ConfigProperty
from counters import PerfCounter
from entities import BaseEntity
from google.appengine.api import memcache
from google.appengine.api import namespace_manager
from google.appengine.api import users
from google.appengine.ext import db


# The default amount of time to cache the items for in memcache.
DEFAULT_CACHE_TTL_SECS = 60 * 5

# Global memcache controls.
CAN_USE_MEMCACHE = ConfigProperty(
    'gcb_can_use_memcache', bool, (
        'Whether or not to cache various objects in memcache. For production '
        'this value should be on to enable maximum performance. For '
        'development this value should be off so you can see your changes to '
        'course content instantaneously.'),
    appengine_config.PRODUCTION_MODE)

# performance counters
CACHE_PUT = PerfCounter(
    'gcb-models-cache-put',
    'A number of times an object was put into memcache.')
CACHE_HIT = PerfCounter(
    'gcb-models-cache-hit',
    'A number of times an object was found in memcache.')
CACHE_MISS = PerfCounter(
    'gcb-models-cache-miss',
    'A number of times an object was not found in memcache.')
CACHE_DELETE = PerfCounter(
    'gcb-models-cache-delete',
    'A number of times an object was deleted from memcache.')


class MemcacheManager(object):
    """Class that consolidates all memcache operations."""

    @classmethod
    def get(cls, key, namespace=None):
        """Gets an item from memcache if memcache is enabled."""
        if not CAN_USE_MEMCACHE.value:
            return None
        if not namespace:
            namespace = appengine_config.DEFAULT_NAMESPACE_NAME
        if namespace == namespace_manager.get_namespace():
            value = memcache.get(key)
        else:
            old_namespace = namespace_manager.get_namespace()
            namespace_manager.set_namespace(namespace)
            try:
                value = memcache.get(key)
            finally:
                namespace_manager.set_namespace(old_namespace)
        if value:
            CACHE_HIT.inc()
        else:
            CACHE_MISS.inc()
        return value

    @classmethod
    def set(cls, key, value, ttl=DEFAULT_CACHE_TTL_SECS, namespace=None):
        """Sets an item in memcache if memcache is enabled."""
        if CAN_USE_MEMCACHE.value:
            CACHE_PUT.inc()
            if not namespace:
                namespace = appengine_config.DEFAULT_NAMESPACE_NAME
            if namespace == namespace_manager.get_namespace():
                memcache.set(key, value, ttl)
            else:
                old_namespace = namespace_manager.get_namespace()
                namespace_manager.set_namespace(namespace)
                try:
                    memcache.set(key, value, ttl)
                finally:
                    namespace_manager.set_namespace(old_namespace)

    @classmethod
    def delete(cls, key, namespace=None):
        """Deletes an item from memcache if memcache is enabled."""
        if CAN_USE_MEMCACHE.value:
            CACHE_DELETE.inc()
            if not namespace:
                namespace = appengine_config.DEFAULT_NAMESPACE_NAME
            if namespace == namespace_manager.get_namespace():
                memcache.delete(key)
            else:
                old_namespace = namespace_manager.get_namespace()
                namespace_manager.set_namespace(namespace)
                try:
                    memcache.delete(key)
                finally:
                    namespace_manager.set_namespace(old_namespace)


class Student(BaseEntity):
    """Student profile."""
    enrolled_on = db.DateTimeProperty(auto_now_add=True, indexed=True)
    user_id = db.StringProperty(indexed=False)
    name = db.StringProperty(indexed=False)
    is_enrolled = db.BooleanProperty(indexed=False)

    # Each of the following is a string representation of a JSON dict.
    scores = db.TextProperty(indexed=False)

    def put(self):
        """Do the normal put() and also add the object to memcache."""
        result = super(Student, self).put()
        MemcacheManager.set(self.key().name(), self)
        return result

    def delete(self):
        """Do the normal delete() and also remove the object from memcache."""
        super(Student, self).delete()
        MemcacheManager.delete(self.key().name())

    @classmethod
    def get_by_email(cls, email):
        return Student.get_by_key_name(email.encode('utf8'))

    @classmethod
    def get_enrolled_student_by_email(cls, email):
        student = MemcacheManager.get(email)
        if not student:
            student = Student.get_by_email(email)
            MemcacheManager.set(email, student)
        if student and student.is_enrolled:
            return student
        else:
            return None

    @classmethod
    def rename_current(cls, new_name):
        """Gives student a new name."""
        user = users.get_current_user()
        if not user:
            raise Exception('No current user.')
        if new_name:
            student = Student.get_by_email(user.email())
            student.name = new_name
            student.put()

    @classmethod
    def set_enrollment_status_for_current(cls, is_enrolled):
        """Changes student enrollment status."""
        user = users.get_current_user()
        if not user:
            raise Exception('No current user.')
        student = Student.get_by_email(user.email())
        student.is_enrolled = is_enrolled
        student.put()


class EventEntity(BaseEntity):
    """Generic events.

    Each event has a 'source' that defines a place in a code where the event was
    recorded. Each event has a 'user_id' to represent an actor who triggered
    the event. The event 'data' is a JSON object, the format of which is defined
    elsewhere and depends on the type of the event.
    """
    recorded_on = db.DateTimeProperty(auto_now_add=True, indexed=True)
    source = db.StringProperty(indexed=False)
    user_id = db.StringProperty(indexed=False)

    # Each of the following is a string representation of a JSON dict.
    data = db.TextProperty(indexed=False)

    @classmethod
    def record(cls, source, user, data):
        """Records new event into a datastore."""

        event = EventEntity()
        event.source = source
        event.user_id = user.user_id()
        event.data = data
        event.put()


class StudentAnswersEntity(BaseEntity):
    """Student answers to the assessments."""

    updated_on = db.DateTimeProperty(indexed=True)

    # Each of the following is a string representation of a JSON dict.
    data = db.TextProperty(indexed=False)


class StudentPropertyEntity(BaseEntity):
    """A property of a student, keyed by the string STUDENT_ID-PROPERTY_NAME."""

    updated_on = db.DateTimeProperty(indexed=True)

    name = db.StringProperty()
    # Each of the following is a string representation of a JSON dict.
    value = db.TextProperty()

    @classmethod
    def create_key(cls, student_id, property_name):
        return '%s-%s' % (student_id, property_name)

    @classmethod
    def create(cls, student, property_name):
        return StudentPropertyEntity(
            key_name=cls.create_key(student.user_id, property_name),
            name=property_name)

    def put(self):
        """Do the normal put() and also add the object to memcache."""
        result = super(StudentPropertyEntity, self).put()
        MemcacheManager.set(self.key().name(), self)
        return result

    def delete(self):
        """Do the normal delete() and also remove the object from memcache."""
        super(Student, self).delete()
        MemcacheManager.delete(self.key().name())

    @classmethod
    def get(cls, student, property_name):
        key = cls.create_key(student.user_id, property_name)
        value = MemcacheManager.get(key)
        if not value:
            value = cls.get_by_key_name(key)
        return value
