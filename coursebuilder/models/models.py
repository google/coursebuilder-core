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

import logging
import appengine_config
from config import ConfigProperty
import counters
from counters import PerfCounter
from entities import BaseEntity
import transforms
from google.appengine.api import memcache
from google.appengine.api import namespace_manager
from google.appengine.api import users
from google.appengine.ext import db


# We want to use memcache for both objects that exist and do not exist in the
# datastore. If object exists we cache its instance, if object does not exist
# we cache this object below.
NO_OBJECT = {}

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
    def get_namespace(cls):
        """Look up namespace from namespace_manager or use default."""
        namespace = namespace_manager.get_namespace()
        if namespace:
            return namespace
        return appengine_config.DEFAULT_NAMESPACE_NAME

    @classmethod
    def _get_namespace(cls, namespace):
        if namespace is not None:
            return namespace
        return cls.get_namespace()

    @classmethod
    def get(cls, key, namespace=None):
        """Gets an item from memcache if memcache is enabled."""
        if not CAN_USE_MEMCACHE.value:
            return None
        value = memcache.get(key, namespace=cls._get_namespace(namespace))

        # We store some objects in memcache that don't evaluate to True, but are
        # real objects, '{}' for example. Count a cache miss only in a case when
        # an object is None.
        if value != None:  # pylint: disable-msg=g-equals-none
            CACHE_HIT.inc()
        else:
            logging.info('Cache miss, key: %s. %s', key, Exception())
            CACHE_MISS.inc(context=key)
        return value

    @classmethod
    def set(cls, key, value, ttl=DEFAULT_CACHE_TTL_SECS, namespace=None):
        """Sets an item in memcache if memcache is enabled."""
        if CAN_USE_MEMCACHE.value:
            CACHE_PUT.inc()
            memcache.set(
                key, value, ttl, namespace=cls._get_namespace(namespace))

    @classmethod
    def delete(cls, key, namespace=None):
        """Deletes an item from memcache if memcache is enabled."""
        if CAN_USE_MEMCACHE.value:
            CACHE_DELETE.inc()
            memcache.delete(key, namespace=cls._get_namespace(namespace))

    @classmethod
    def incr(cls, key, delta, namespace=None):
        """Incr an item in memcache if memcache is enabled."""
        if CAN_USE_MEMCACHE.value:
            memcache.incr(
                key, delta,
                namespace=cls._get_namespace(namespace), initial_value=0)


CAN_AGGREGATE_COUNTERS = ConfigProperty(
    'gcb_can_aggregate_counters', bool,
    'Whether or not to aggregate and record counter values in memcache. '
    'This allows you to see counter values aggregated across all frontend '
    'application instances. Without recording, you only see counter values '
    'for one frontend instance you are connected to right now. Enabling '
    'aggregation improves quality of performance metrics, but adds a small '
    'amount of latency to all your requests.',
    default_value=False)


def incr_counter_global_value(name, delta):
    if CAN_AGGREGATE_COUNTERS.value:
        MemcacheManager.incr(
            'counter:' + name, delta,
            namespace=appengine_config.DEFAULT_NAMESPACE_NAME)


def get_counter_global_value(name):
    if CAN_AGGREGATE_COUNTERS.value:
        return MemcacheManager.get(
            'counter:' + name,
            namespace=appengine_config.DEFAULT_NAMESPACE_NAME)
    else:
        return None

counters.get_counter_global_value = get_counter_global_value
counters.incr_counter_global_value = incr_counter_global_value


# Whether to record tag events in a database.
CAN_SHARE_STUDENT_PROFILE = ConfigProperty(
    'gcb_can_share_student_profile', bool, (
        'Whether or not to share student profile between different courses.'),
    False)


class PersonalProfile(BaseEntity):
    """Personal information not specific to any course instance."""

    email = db.StringProperty(indexed=False)
    legal_name = db.StringProperty(indexed=False)
    nick_name = db.StringProperty(indexed=False)
    date_of_birth = db.DateProperty(indexed=False)
    enrollment_info = db.TextProperty()
    course_info = db.TextProperty()

    _PROPERTY_EXPORT_BLACKLIST = [email, legal_name, nick_name, date_of_birth]

    @property
    def user_id(self):
        return self.key().name()

    @classmethod
    def safe_key(cls, db_key, transform_fn):
        return db.Key.from_path(cls.kind(), transform_fn(db_key.name()))


class PersonalProfileDTO(object):
    """DTO for PersonalProfile."""

    def __init__(self, personal_profile=None):
        self.enrollment_info = '{}'
        self.course_info = '{}'
        if personal_profile:
            self.user_id = personal_profile.user_id
            self.email = personal_profile.email
            self.legal_name = personal_profile.legal_name
            self.nick_name = personal_profile.nick_name
            self.date_of_birth = personal_profile.date_of_birth
            self.enrollment_info = personal_profile.enrollment_info
            self.course_info = personal_profile.course_info


class StudentProfileDAO(object):
    """All access and mutation methods for PersonalProfile and Student."""

    TARGET_NAMESPACE = appengine_config.DEFAULT_NAMESPACE_NAME

    @classmethod
    def _memcache_key(cls, key):
        """Makes a memcache key from primary key."""
        return 'entity:personal-profile:%s' % key

    @classmethod
    def _get_profile_by_user_id(cls, user_id):
        """Loads profile given a user_id and returns Entity object."""
        old_namespace = namespace_manager.get_namespace()
        try:
            namespace_manager.set_namespace(cls.TARGET_NAMESPACE)

            profile = MemcacheManager.get(
                cls._memcache_key(user_id), namespace=cls.TARGET_NAMESPACE)
            if profile == NO_OBJECT:
                return None
            if profile:
                return profile
            profile = PersonalProfile.get_by_key_name(user_id)
            MemcacheManager.set(
                cls._memcache_key(user_id), profile if profile else NO_OBJECT,
                namespace=cls.TARGET_NAMESPACE)
            return profile
        finally:
            namespace_manager.set_namespace(old_namespace)

    @classmethod
    def _add_new_profile(cls, user_id, email):
        """Adds new profile for a user_id and returns Entity object."""
        if not CAN_SHARE_STUDENT_PROFILE.value:
            return None

        old_namespace = namespace_manager.get_namespace()
        try:
            namespace_manager.set_namespace(cls.TARGET_NAMESPACE)

            profile = PersonalProfile(key_name=user_id)
            profile.email = email
            profile.enrollment_info = '{}'
            profile.put()
            return profile
        finally:
            namespace_manager.set_namespace(old_namespace)

    @classmethod
    def _update_global_profile_attributes(
        cls, profile,
        email=None, legal_name=None, nick_name=None,
        date_of_birth=None, is_enrolled=None, final_grade=None,
        course_info=None):
        """Modifies various attributes of Student's Global Profile."""
        # TODO(psimakov): update of email does not work for student
        if email is not None:
            profile.email = email

        if legal_name is not None:
            profile.legal_name = legal_name

        if nick_name is not None:
            profile.nick_name = nick_name

        if date_of_birth is not None:
            profile.date_of_birth = date_of_birth

        if not (is_enrolled is None and final_grade is None and
                course_info is None):

            # Defer to avoid circular import.
            # pylint: disable-msg=g-import-not-at-top
            from controllers import sites
            course = sites.get_course_for_current_request()
            course_namespace = course.get_namespace_name()

            if is_enrolled is not None:
                enrollment_dict = transforms.loads(profile.enrollment_info)
                enrollment_dict[course_namespace] = is_enrolled
                profile.enrollment_info = transforms.dumps(enrollment_dict)

            if final_grade is not None or course_info is not None:
                course_info_dict = {}
                if profile.course_info:
                    course_info_dict = transforms.loads(profile.course_info)
                if course_namespace in course_info_dict.keys():
                    info = course_info_dict[course_namespace]
                else:
                    info = {}
                if final_grade:
                    info['final_grade'] = final_grade
                if course_info:
                    info['info'] = course_info
                course_info_dict[course_namespace] = info
                profile.course_info = transforms.dumps(course_info_dict)

    @classmethod
    def _update_course_profile_attributes(
        cls, student, nick_name=None, is_enrolled=None):
        """Modifies various attributes of Student's Course Profile."""

        if nick_name is not None:
            student.name = nick_name

        if is_enrolled is not None:
            student.is_enrolled = is_enrolled

    @classmethod
    def _update_attributes(
        cls, profile, student,
        email=None, legal_name=None, nick_name=None,
        date_of_birth=None, is_enrolled=None, final_grade=None,
        course_info=None):
        """Modifies various attributes of Student and Profile."""

        if profile:
            cls._update_global_profile_attributes(
                profile, email=email, legal_name=legal_name,
                nick_name=nick_name, date_of_birth=date_of_birth,
                is_enrolled=is_enrolled, final_grade=final_grade,
                course_info=course_info)

        if student:
            cls._update_course_profile_attributes(
                student, nick_name=nick_name, is_enrolled=is_enrolled)

    @classmethod
    def _put_profile(cls, profile):
        """Does a put() on profile objects."""
        if not profile:
            return
        profile.put()
        MemcacheManager.delete(
            cls._memcache_key(profile.user_id),
            namespace=cls.TARGET_NAMESPACE)

    @classmethod
    def get_profile_by_user_id(cls, user_id):
        """Loads profile given a user_id and returns DTO object."""
        profile = cls._get_profile_by_user_id(user_id)
        if profile:
            return PersonalProfileDTO(personal_profile=profile)
        return None

    @classmethod
    def add_new_profile(cls, user_id, email):
        return cls._add_new_profile(user_id, email)

    @classmethod
    def add_new_student_for_current_user(cls, nick_name, additional_fields):
        user = users.get_current_user()

        student_by_uid = Student.get_student_by_user_id(user.user_id())
        is_valid_student = (student_by_uid is None or
                            student_by_uid.user_id == user.user_id())
        assert is_valid_student, (
            'Student\'s email and user id do not match.')

        cls._add_new_student_for_current_user(
            user.user_id(), user.email(), nick_name, additional_fields)

    @classmethod
    @db.transactional(xg=True)
    def _add_new_student_for_current_user(
        cls, user_id, email, nick_name, additional_fields):
        """Create new or re-enroll old student."""

        # create profile if does not exist
        profile = cls._get_profile_by_user_id(user_id)
        if not profile:
            profile = cls._add_new_profile(user_id, email)

        # create new student or re-enroll existing
        student = Student.get_by_email(email)
        if not student:
            # TODO(psimakov): we must move to user_id as a key
            student = Student(key_name=email)

        # update profile
        cls._update_attributes(
            profile, student, nick_name=nick_name, is_enrolled=True)

        # update student
        student.user_id = user_id
        student.additional_fields = additional_fields

        # put both
        cls._put_profile(profile)
        student.put()

    @classmethod
    def get_enrolled_student_by_email_for(cls, email, app_context):
        """Returns student for a specific course."""
        old_namespace = namespace_manager.get_namespace()
        try:
            namespace_manager.set_namespace(app_context.get_namespace_name())
            return Student.get_enrolled_student_by_email(email)
        finally:
            namespace_manager.set_namespace(old_namespace)

    @classmethod
    @db.transactional(xg=True)
    def update(
        cls, user_id, email, legal_name=None, nick_name=None,
        date_of_birth=None, is_enrolled=None, final_grade=None,
        course_info=None, profile_only=False):
        """Updates a student and/or their global profile."""
        student = None
        if not profile_only:
            student = Student.get_by_email(email)
            if not student:
                raise Exception('Unable to find student for: %s' % user_id)

        profile = cls._get_profile_by_user_id(user_id)
        if not profile:
            profile = cls.add_new_profile(user_id, email)

        cls._update_attributes(
            profile, student, email=email, legal_name=legal_name,
            nick_name=nick_name, date_of_birth=date_of_birth,
            is_enrolled=is_enrolled, final_grade=final_grade,
            course_info=course_info)

        cls._put_profile(profile)
        if not profile_only:
            student.put()


class Student(BaseEntity):
    """Student data specific to a course instance."""
    enrolled_on = db.DateTimeProperty(auto_now_add=True, indexed=True)
    user_id = db.StringProperty(indexed=True)
    name = db.StringProperty(indexed=False)
    additional_fields = db.TextProperty(indexed=False)
    is_enrolled = db.BooleanProperty(indexed=False)

    # Each of the following is a string representation of a JSON dict.
    scores = db.TextProperty(indexed=False)

    _PROPERTY_EXPORT_BLACKLIST = [additional_fields, name]

    @classmethod
    def safe_key(cls, db_key, transform_fn):
        return db.Key.from_path(cls.kind(), transform_fn(db_key.id_or_name()))

    def for_export(self, transform_fn):
        """Creates an ExportEntity populated from this entity instance."""
        assert not hasattr(self, 'key_by_user_id')
        model = super(Student, self).for_export(transform_fn)
        model.user_id = transform_fn(self.user_id)
        # Add a version of the key that always uses the user_id for the name
        # component. This can be used to establish relationships between objects
        # where the student key used was created via get_key(). In general,
        # this means clients will join exports on this field, not the field made
        # from safe_key().
        model.key_by_user_id = self.get_key(transform_fn=transform_fn)
        return model

    @property
    def is_transient(self):
        return False

    @property
    def email(self):
        return self.key().name()

    @property
    def profile(self):
        return StudentProfileDAO.get_profile_by_user_id(self.user_id)

    @classmethod
    def _memcache_key(cls, key):
        """Makes a memcache key from primary key."""
        return 'entity:student:%s' % key

    def put(self):
        """Do the normal put() and also add the object to memcache."""
        result = super(Student, self).put()
        MemcacheManager.set(self._memcache_key(self.key().name()), self)
        return result

    def delete(self):
        """Do the normal delete() and also remove the object from memcache."""
        super(Student, self).delete()
        MemcacheManager.delete(self._memcache_key(self.key().name()))

    @classmethod
    def add_new_student_for_current_user(cls, nick_name, additional_fields):
        StudentProfileDAO.add_new_student_for_current_user(
            nick_name, additional_fields)

    @classmethod
    def get_by_email(cls, email):
        return Student.get_by_key_name(email.encode('utf8'))

    @classmethod
    def get_enrolled_student_by_email(cls, email):
        """Returns enrolled student or None."""
        student = MemcacheManager.get(cls._memcache_key(email))
        if NO_OBJECT == student:
            return None
        if not student:
            student = Student.get_by_email(email)
            if student:
                MemcacheManager.set(cls._memcache_key(email), student)
            else:
                MemcacheManager.set(cls._memcache_key(email), NO_OBJECT)
        if student and student.is_enrolled:
            return student
        else:
            return None

    @classmethod
    def _get_user_and_student(cls):
        """Loads user and student and asserts both are present."""
        user = users.get_current_user()
        if not user:
            raise Exception('No current user.')
        student = Student.get_by_email(user.email())
        if not student:
            raise Exception('Student instance corresponding to user %s not '
                            'found.' % user.email())
        return user, student

    @classmethod
    def rename_current(cls, new_name):
        """Gives student a new name."""
        _, student = cls._get_user_and_student()
        StudentProfileDAO.update(
            student.user_id, student.email, nick_name=new_name)

    @classmethod
    def set_enrollment_status_for_current(cls, is_enrolled):
        """Changes student enrollment status."""
        _, student = cls._get_user_and_student()
        StudentProfileDAO.update(
            student.user_id, student.email, is_enrolled=is_enrolled)

    def get_key(self, transform_fn=None):
        """Gets a version of the key that uses user_id for the key name."""
        if not self.user_id:
            raise Exception('Student instance has no user_id set.')
        user_id = transform_fn(self.user_id) if transform_fn else self.user_id
        return db.Key.from_path(Student.kind(), user_id)

    @classmethod
    def get_student_by_user_id(cls, user_id):
        students = cls.all().filter(cls.user_id.name, user_id).fetch(limit=2)
        if len(students) == 2:
            raise Exception(
                'There is more than one student with user_id %s' % user_id)
        return students[0] if students else None

    def has_same_key_as(self, key):
        """Checks if the key of the student and the given key are equal."""
        return key == self.get_key()


class TransientStudent(object):
    """A transient student (i.e. a user who hasn't logged in or registered)."""

    @property
    def is_transient(self):
        return True


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

    def for_export(self, transform_fn):
        model = super(EventEntity, self).for_export(transform_fn)
        model.user_id = transform_fn(self.user_id)
        return model


class StudentAnswersEntity(BaseEntity):
    """Student answers to the assessments."""

    updated_on = db.DateTimeProperty(indexed=True)

    # Each of the following is a string representation of a JSON dict.
    data = db.TextProperty(indexed=False)

    @classmethod
    def safe_key(cls, db_key, transform_fn):
        return db.Key.from_path(cls.kind(), transform_fn(db_key.id_or_name()))


class StudentPropertyEntity(BaseEntity):
    """A property of a student, keyed by the string STUDENT_ID-PROPERTY_NAME."""

    updated_on = db.DateTimeProperty(indexed=True)

    name = db.StringProperty()
    # Each of the following is a string representation of a JSON dict.
    value = db.TextProperty()

    @classmethod
    def _memcache_key(cls, key):
        """Makes a memcache key from primary key."""
        return 'entity:student_property:%s' % key

    @classmethod
    def create_key(cls, student_id, property_name):
        return '%s-%s' % (student_id, property_name)

    @classmethod
    def create(cls, student, property_name):
        return StudentPropertyEntity(
            key_name=cls.create_key(student.user_id, property_name),
            name=property_name)

    @classmethod
    def safe_key(cls, db_key, transform_fn):
        user_id, name = db_key.name().split('-', 1)
        return db.Key.from_path(
            cls.kind(), '%s-%s' % (transform_fn(user_id), name))

    def put(self):
        """Do the normal put() and also add the object to memcache."""
        result = super(StudentPropertyEntity, self).put()
        MemcacheManager.set(self._memcache_key(self.key().name()), self)
        return result

    def delete(self):
        """Do the normal delete() and also remove the object from memcache."""
        super(Student, self).delete()
        MemcacheManager.delete(self._memcache_key(self.key().name()))

    @classmethod
    def get(cls, student, property_name):
        """Loads student property."""
        key = cls.create_key(student.user_id, property_name)
        value = MemcacheManager.get(cls._memcache_key(key))
        if NO_OBJECT == value:
            return None
        if not value:
            value = cls.get_by_key_name(key)
            if value:
                MemcacheManager.set(cls._memcache_key(key), value)
            else:
                MemcacheManager.set(cls._memcache_key(key), NO_OBJECT)
        return value


class BaseJsonDao(object):
    """Base DAO class for entities storing their data in a single JSON blob."""

    @classmethod
    def _memcache_key(cls, obj_id):
        """Makes a memcache key from datastore id."""
        # Keeping case-sensitivity in kind() because Foo(object) != foo(object).
        return '(entity:%s:%s)' % (cls.ENTITY.kind(), obj_id)

    @classmethod
    def get_all(cls):
        entities = cls.ENTITY.all().fetch(1000)
        return [
            cls.DTO(e.key().id(), transforms.loads(e.data)) for e in entities]

    @classmethod
    def _load_entity(cls, obj_id):
        if not obj_id:
            return None
        memcache_key = cls._memcache_key(obj_id)
        entity = MemcacheManager.get(memcache_key)
        if NO_OBJECT == entity:
            return None
        if not entity:
            entity = cls.ENTITY.get_by_id(int(obj_id))
            if entity:
                MemcacheManager.set(memcache_key, entity)
            else:
                MemcacheManager.set(memcache_key, NO_OBJECT)
        return entity

    @classmethod
    def load(cls, obj_id):
        entity = cls._load_entity(obj_id)
        if entity:
            return cls.DTO(obj_id, transforms.loads(entity.data))
        else:
            return None

    @classmethod
    def save(cls, dto):
        entity = cls._load_entity(dto.id)
        if not entity:
            entity = cls.ENTITY()
        entity.data = transforms.dumps(dto.dict)
        entity.put()
        MemcacheManager.set(cls._memcache_key(entity.key().id()), entity)
        return entity.key().id()

    @classmethod
    def save_all(cls, dtos):
        """Performs a block persist of a list of DTO's."""
        entities = []
        for dto in dtos:
            entity = cls._load_entity(dto.id)
            if not entity:
                entity = cls.ENTITY()
            entity.data = transforms.dumps(dto.dict)
            entities.append(entity)

        keys = db.put(entities)
        for key, entity in zip(keys, entities):
            MemcacheManager.set(cls._memcache_key(key.id()), entity)
        return [key.id() for key in keys]

    @classmethod
    def delete(cls, dto):
        entity = cls._load_entity(dto.id)
        entity.delete()
        MemcacheManager.delete(cls._memcache_key(entity.key().id()))


class QuestionEntity(BaseEntity):
    """An object representing a top-level question."""
    data = db.TextProperty(indexed=False)


class QuestionDTO(object):
    """DTO for question entities."""
    MULTIPLE_CHOICE = 0
    SHORT_ANSWER = 1

    def __init__(self, the_id, the_dict):
        self.id = the_id
        self.dict = the_dict

    @property
    def type(self):
        return self.dict.get('type')

    @type.setter
    def type(self, value):
        self.dict['type'] = value

    @property
    def description(self):
        return self.dict.get('description') or ''


class QuestionDAO(BaseJsonDao):
    DTO = QuestionDTO
    ENTITY = QuestionEntity

    @classmethod
    def used_by(cls, question_dto_id):
        """Returns descriptions of the question groups using a question.

        Args:
            question_dto_id: int. Identifier of the question we're testing.

        Returns:
            List of unicode. The lexicographically-sorted list of the
            descriptions of all question groups that use the given question.
        """
        # O(num_question_groups), but deserialization of 1 large group takes
        # ~1ms so practically speaking latency is OK for the admin console.
        matches = []
        for group in QuestionGroupDAO.get_all():
            if long(question_dto_id) in [long(x) for x in group.question_ids]:
                matches.append(group.description)

        return sorted(matches)


class SaQuestionConstants(object):
    DEFAULT_WIDTH_COLUMNS = 100
    DEFAULT_HEIGHT_ROWS = 1


class QuestionGroupEntity(BaseEntity):
    """An object representing a question group in the datastore."""
    data = db.TextProperty(indexed=False)


class QuestionGroupDTO(object):
    """Data transfer object for question groups."""

    def __init__(self, the_id, the_dict):
        self.id = the_id
        self.dict = the_dict

    @property
    def description(self):
        return self.dict.get('description') or ''

    @property
    def introduction(self):
        return self.dict.get('introduction') or ''

    @property
    def question_ids(self):
        return [item['question'] for item in self.dict.get('items', [])]


class QuestionGroupDAO(BaseJsonDao):
    DTO = QuestionGroupDTO
    ENTITY = QuestionGroupEntity
