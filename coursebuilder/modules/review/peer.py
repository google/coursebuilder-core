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

"""Internal implementation details of the peer review subsystem.

Public classes, including domain objects, can be found in models/review.py.
Entities declared here should not be used by external clients.
"""

__author__ = [
    'johncox@google.com (John Cox)',
]

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
        if not isinstance(value, db.Key):
            raise db.BadValueError(
                'Value must be of type db.Key; got %s' % type(value))
        if self._kind and value.kind() != self._kind:
            raise db.BadValueError(
                'Key must be of kind %s; was %s' % (self._kind, value.kind()))
        return value
