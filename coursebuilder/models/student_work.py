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

"""Models and helper utilities for the review workflow."""

__author__ = [
    'johncox@google.com (John Cox)',
    'sll@google.com (Sean Lip)',
]

import datetime

import data_removal
import entities
import transforms

import models

from google.appengine.ext import db


class KeyProperty(db.StringProperty):
    """A property that stores a datastore key.

    App Engine's db.ReferenceProperty is dangerous because accessing a
    ReferenceProperty on a model instance implicitly causes an RPC. We always
    want to know about and be in control of our RPCs, so we use this property
    instead, store a key, and manually make datastore calls when necessary.
    This is analogous to the approach ndb takes, and it also allows us to do
    validation against a key's kind (see __init__).

    Keys are stored as indexed strings internally. Usage:

        class Foo(db.Model):
            pass

        class Bar(db.Model):
            foo_key = KeyProperty(kind=Foo)  # Validates key is of kind 'Foo'.

        foo_key = Foo().put()
        bar = Bar(foo_key=foo_key)
        bar_key = bar.put()
        foo = db.get(bar.foo_key)
    """

    def __init__(self, *args, **kwargs):
        """Constructs a new KeyProperty.

        Args:
            *args: positional arguments passed to superclass.
            **kwargs: keyword arguments passed to superclass. Additionally may
                contain kind, which if passed will be a string used to validate
                key kind. If omitted, any kind is considered valid.
        """
        kind = kwargs.pop('kind', None)
        super(KeyProperty, self).__init__(*args, **kwargs)
        self._kind = kind

    def validate(self, value):
        """Validates passed db.Key value, validating kind passed to ctor."""
        super(KeyProperty, self).validate(str(value))
        if value is None:  # Nones are valid iff they pass the parent validator.
            return value
        if not isinstance(value, db.Key):
            raise db.BadValueError(
                'Value must be of type db.Key; got %s' % type(value))
        if self._kind and value.kind() != self._kind:
            raise db.BadValueError(
                'Key must be of kind %s; was %s' % (self._kind, value.kind()))
        return value


# For many classes we define both a _DomainObject subclass and a db.Model.
# When possible it is best to use the domain object, since db.Model carries with
# it the datastore API and allows clients to bypass business logic by making
# direct datastore calls.


class BaseEntity(entities.BaseEntity):
    """Abstract base entity for models related to reviews."""

    @classmethod
    def key_name(cls):
        """Returns a key_name for use with cls's constructor."""
        raise NotImplementedError

    @classmethod
    def _split_key(cls, key_name):
        """Takes a key_name and returns its components."""
        # '(a:b:(c:d:(e:f:g)):h)' -> ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'].
        return key_name.replace('(', '').replace(')', '').split(':')


class Review(BaseEntity):
    """Datastore model for a student review of a Submission."""

    # Contents of the student's review. Max size is 1MB.
    contents = db.TextProperty()

    # Key of the student whose work is being reviewed.
    reviewee_key = KeyProperty(kind=models.Student.kind())
    # Key of the Student who wrote this review.
    reviewer_key = KeyProperty(kind=models.Student.kind())
    # Identifier of the unit this review is a part of.
    unit_id = db.StringProperty(required=True)

    def __init__(self, *args, **kwargs):
        """Constructs a new Review."""
        assert not kwargs.get('key_name'), (
            'Setting key_name manually is not supported')
        reviewee_key = kwargs.get('reviewee_key')
        reviewer_key = kwargs.get('reviewer_key')
        unit_id = kwargs.get('unit_id')
        assert reviewee_key, 'Missing required property: reviewee_key'
        assert reviewer_key, 'Missing required property: reviewer_key'
        assert unit_id, 'Missing required_property: unit_id'
        kwargs['key_name'] = self.key_name(unit_id, reviewee_key, reviewer_key)
        super(Review, self).__init__(*args, **kwargs)

    @classmethod
    def key_name(cls, unit_id, reviewee_key, reviewer_key):
        """Creates a key_name string for datastore operations.

        In order to work with the review subsystem, entities must have a key
        name populated from this method.

        Args:
            unit_id: string. The id of the unit this review belongs to.
            reviewee_key: db.Key of models.models.Student. The student whose
                work is being reviewed.
            reviewer_key: db.Key of models.models.Student. The author of this
                the review.

        Returns:
            String.
        """
        return '(review:%s:%s:%s)' % (unit_id, reviewee_key, reviewer_key)

    @classmethod
    def safe_key(cls, db_key, transform_fn):
        _, unit_id, reviewee_key_str, reviewer_key_str = cls._split_key(
            db_key.name())
        reviewee_key = db.Key(encoded=reviewee_key_str)
        reviewer_key = db.Key(encoded=reviewer_key_str)
        safe_reviewee_key = models.Student.safe_key(reviewee_key, transform_fn)
        safe_reviewer_key = models.Student.safe_key(reviewer_key, transform_fn)
        return db.Key.from_path(
            cls.kind(),
            cls.key_name(unit_id, safe_reviewee_key, safe_reviewer_key))

    def for_export(self, transform_fn):
        model = super(Review, self).for_export(transform_fn)
        model.reviewee_key = models.Student.safe_key(
            model.reviewee_key, transform_fn)
        model.reviewer_key = models.Student.safe_key(
            model.reviewer_key, transform_fn)
        return model

    @classmethod
    def _get_student_key(cls, value):
        return db.Key.from_path(models.Student.kind(), value)

    @classmethod
    def delete_by_reviewee_id(cls, user_id):
        student_key = cls._get_student_key(user_id)
        query = Review.all(keys_only=True).filter('reviewee_key =', student_key)
        db.delete(query.run())


class Submission(BaseEntity):
    """Datastore model for a student work submission."""

    # Contents of the student submission. Max size is 1MB.
    contents = db.TextProperty()

    # Submission date
    updated_on = db.DateTimeProperty(indexed=True)

    # Key of the Student who wrote this submission.
    reviewee_key = KeyProperty(kind=models.Student.kind())
    # Identifier of the unit this review is a part of.
    unit_id = db.StringProperty(required=True)
    # Optional identifier of the component which submitted this data
    instance_id = db.StringProperty(required=False)

    def __init__(self, *args, **kwargs):
        """Constructs a new Submission."""
        assert not kwargs.get('key_name'), (
            'Setting key_name manually is not supported')
        reviewee_key = kwargs.get('reviewee_key')
        unit_id = kwargs.get('unit_id')
        instance_id = kwargs.get('instance_id')
        assert reviewee_key, 'Missing required property: reviewee_key'
        assert unit_id, 'Missing required_property: unit_id'
        kwargs['key_name'] = self.key_name(
            unit_id, reviewee_key, instance_id=instance_id)
        super(Submission, self).__init__(*args, **kwargs)

    @classmethod
    def _get_student_key(cls, value):
        return db.Key.from_path(models.Student.kind(), value)

    @classmethod
    def delete_by_reviewee_id(cls, user_id):
        student_key = cls._get_student_key(user_id)
        query = Submission.all(keys_only=True).filter('reviewee_key =',
                                                      student_key)
        db.delete(query.run())

    @classmethod
    def key_name(cls, unit_id, reviewee_key, instance_id=None):
        """Creates a key_name string for datastore operations.

        In order to work with the review subsystem, entities must have a key
        name populated from this method.

        Args:
            unit_id: string. The id of the unit this submission belongs to.
            reviewee_key: db.Key of models.models.Student. The author of the
                the submission.
            instance_id: string. The instance id of a component (e.g., file
                upload) which submitted the content.

        Returns:
            String.
        """
        if instance_id:
            return '(submission:%s:%s:%s)' % (
                unit_id, instance_id, reviewee_key.id_or_name())
        else:
            return '(submission:%s:%s)' % (unit_id, reviewee_key.id_or_name())

    @classmethod
    def get_key(cls, unit_id, reviewee_key, instance_id=None):
        """Returns a db.Key for a submission."""
        return db.Key.from_path(cls.kind(), cls.key_name(
            unit_id, reviewee_key, instance_id=instance_id))

    @classmethod
    def safe_key(cls, db_key, transform_fn):
        split_key = cls._split_key(db_key.name())
        if len(split_key) == 3:
            _, unit_id, student_key_str = split_key
            instance_id = None
        else:
            _, unit_id, instance_id, student_key_str = split_key

        student_key = db.Key.from_path(models.Student.kind(), student_key_str)
        safe_student_key = models.Student.safe_key(student_key, transform_fn)
        return db.Key.from_path(cls.kind(), cls.key_name(
            unit_id, safe_student_key, instance_id=instance_id))

    @classmethod
    def write(cls, unit_id, reviewee_key, contents, instance_id=None):
        """Updates or creates a student submission, and returns the key.

        Args:
            unit_id: string. The id of the unit this submission belongs to.
            reviewee_key: db.Key of models.models.Student. The author of the
                submission.
            contents: object. The contents of the submission, as a Python
                object. This will be JSON-transformed before it is stored.
            instance_id: string. The instance id of a component (e.g., file
                upload) which submitted the content.

        Returns:
            db.Key of Submission.
        """
        return cls(
            unit_id=str(unit_id), reviewee_key=reviewee_key,
            contents=transforms.dumps(contents),
            instance_id=instance_id,
            updated_on=datetime.datetime.utcnow()
        ).put()

    @classmethod
    def get(cls, unit_id, reviewee_key, instance_id=None):
        submission_key = cls.get_key(
            unit_id, reviewee_key, instance_id=instance_id)
        submission = entities.get(submission_key)
        # For backward compatibility, if no entry is found with the instance_id
        # in the key, also look for an entry with no instance_id used.
        if submission is None and instance_id:
            submission = entities.get(cls.get_key(unit_id, reviewee_key))
        return submission

    @classmethod
    def get_contents(cls, unit_id, reviewee_key, instance_id=None):
        """Returns the de-JSONified contents of a submission."""
        submission_key = cls.get_key(
            unit_id, reviewee_key, instance_id=instance_id)
        contents = cls.get_contents_by_key(submission_key)
        # For backward compatibility, if no entry is found with the instance_id
        # in the key, also look for an entry with no instance_id used.
        if contents is None and instance_id:
            contents = cls.get_contents_by_key(
                cls.get_key(unit_id, reviewee_key))
        return contents

    @classmethod
    def get_contents_by_key(cls, submission_key):
        """Returns the contents of a submission, given a db.Key."""
        submission = entities.get(submission_key)
        return transforms.loads(submission.contents) if submission else None

    def for_export(self, transform_fn):
        model = super(Submission, self).for_export(transform_fn)
        model.reviewee_key = models.Student.safe_key(
            model.reviewee_key, transform_fn)
        return model


class StudentWorkUtils(object):
    """A utility class for processing student work objects."""

    @classmethod
    def get_answer_list(cls, submission):
        """Compiles a list of the student's answers from a submission."""
        if not submission:
            return []

        answer_list = []
        for item in submission:
            # Check that the indices within the submission are valid.
            assert item['index'] == len(answer_list)
            answer_list.append(item['value'])
        return answer_list


def register_for_data_removal():
    data_removal.Registry.register_indexed_by_user_id_remover(
        Review.delete_by_reviewee_id)
    data_removal.Registry.register_indexed_by_user_id_remover(
        Submission.delete_by_reviewee_id)
