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

"""Manages dynamic properties of an application and/or its modules.

An application must explicitly declare properties and provide a type, doc string
and default value for each. The default property values are overridden by
the new values found in the environment variable with the same name. Those are
further overridden by the values found in the datastore. We also try to do all
of this with performance in mind.
"""

__author__ = 'Pavel Simakov (psimakov@google.com)'

import logging
import os
import time
import appengine_config
import entities
import transforms
from google.appengine.api import namespace_manager
from google.appengine.ext import db


# The default update interval supported.
DEFAULT_UPDATE_INTERVAL = 60

# The longest update interval supported.
MAX_UPDATE_INTERVAL = 60 * 5


# Allowed property types.
TYPE_INT = int
TYPE_STR = str
TYPE_BOOL = bool
ALLOWED_TYPES = frozenset([TYPE_INT, TYPE_STR, TYPE_BOOL])


class ConfigProperty(object):
    """A property with name, type, doc_string and a default value."""

    def __init__(
        self, name, value_type, doc_string,
        default_value=None, multiline=False):

        if not value_type in ALLOWED_TYPES:
            raise Exception('Bad value type: %s' % value_type)

        self._multiline = multiline
        self._name = name
        self._type = value_type
        self._doc_string = doc_string
        self._default_value = value_type(default_value)
        self._value = None

        Registry.registered[name] = self

    @property
    def multiline(self):
        return self._multiline

    @property
    def name(self):
        return self._name

    @property
    def value_type(self):
        return self._type

    @property
    def doc_string(self):
        return self._doc_string

    @property
    def default_value(self):
        return self._default_value

    def get_environ_value(self):
        """Tries to get value from the environment variables."""

        # Look for a name in lower or upper case.
        name = None
        if self._name.lower() in os.environ:
            name = self._name.lower()
        else:
            if self._name.upper() in os.environ:
                name = self._name.upper()

        if name:
            try:
                return True, transforms.string_to_value(
                    os.environ[name], self.value_type)
            except Exception:  # pylint: disable-msg=broad-except
                logging.error(
                    'Property %s failed to cast to type %s; removing.',
                    self._name, self._type)
                del os.environ[name]
        return False, None

    @property
    def value(self):
        """Get the latest value from datastore, environment or use default."""

        # Try datastore overrides first.
        overrides = Registry.get_overrides()
        if overrides and self.name in overrides:
            return overrides[self.name]

        # Try environment variable overrides second.
        has_value, environ_value = self.get_environ_value()
        if has_value:
            return environ_value

        # Use default value last.
        return self._default_value


class Registry(object):
    """Holds all registered properties."""
    registered = {}
    db_overrides = {}
    update_interval = DEFAULT_UPDATE_INTERVAL
    last_update_time = 0
    update_index = 0

    @classmethod
    def get_overrides(cls, force_update=False):
        """Returns current property overrides, maybe cached."""

        # Check if datastore property overrides are enabled at all.
        has_value, environ_value = UPDATE_INTERVAL_SEC.get_environ_value()
        if (has_value and environ_value == 0) or (
                UPDATE_INTERVAL_SEC.default_value == 0):
            return

        # Check if cached values are still fresh.
        now = long(time.time())
        age = now - cls.last_update_time
        if force_update or age < 0 or age >= cls.update_interval:
            try:
                old_namespace = namespace_manager.get_namespace()
                try:
                    namespace_manager.set_namespace(
                        appengine_config.DEFAULT_NAMESPACE_NAME)

                    cls.load_from_db()
                finally:
                    namespace_manager.set_namespace(old_namespace)
            except Exception as e:  # pylint: disable-msg=broad-except
                logging.error(
                    'Failed to load properties from a database: %s.', str(e))
            finally:
                # Avoid overload and update timestamp even if we failed.
                cls.last_update_time = now
                cls.update_index += 1

        return cls.db_overrides

    @classmethod
    def load_from_db(cls):
        """Loads dynamic properties from db."""
        logging.info('Reloading properties.')
        overrides = {}
        for item in ConfigPropertyEntity.all().fetch(1000):
            name = item.key().name()

            if not name in cls.registered:
                logging.error(
                    'Property is not registered (skipped): %s', name)
                continue

            target = cls.registered[name]
            if target and not item.is_draft:
                # Enforce value type.
                try:
                    value = transforms.string_to_value(
                        item.value, target.value_type)
                except Exception:  # pylint: disable-msg=broad-except
                    logging.error(
                        'Property %s failed to cast to a type %s; removing.',
                        target.name, target.value_type)
                    continue

                # Don't allow disabling of update interval from a database.
                if name == UPDATE_INTERVAL_SEC.name:
                    if value == 0 or value < 0 or value > MAX_UPDATE_INTERVAL:
                        logging.error(
                            'Bad value %s for %s; discarded.', name, value)
                        continue
                    else:
                        cls.update_interval = value

                overrides[name] = value

        cls.db_overrides = overrides


class ConfigPropertyEntity(entities.BaseEntity):
    """A class that represents a named configuration property."""
    value = db.TextProperty(indexed=False)
    is_draft = db.BooleanProperty(indexed=False)


def run_all_unit_tests():
    """Runs all unit tests for this modules."""
    str_prop = ConfigProperty('gcb-str-prop', str, ('doc for str_prop'), 'foo')
    int_prop = ConfigProperty('gcb-int-prop', int, ('doc for int_prop'), 123)

    assert str_prop.default_value == 'foo'
    assert str_prop.value == 'foo'
    assert int_prop.default_value == 123
    assert int_prop.value == 123

    # Check os.environ override works.
    os.environ[str_prop.name] = 'bar'
    assert str_prop.value == 'bar'
    del os.environ[str_prop.name]
    assert str_prop.value == 'foo'

    # Check os.environ override with type casting.
    os.environ[int_prop.name] = '12345'
    assert int_prop.value == 12345

    # Check setting of value is disallowed.
    try:
        str_prop.value = 'foo'
        raise Exception()
    except AttributeError:
        pass

    # Check value of bad type is disregarded.
    os.environ[int_prop.name] = 'foo bar'
    assert int_prop.value == int_prop.default_value


UPDATE_INTERVAL_SEC = ConfigProperty(
    'gcb_config_update_interval_sec', int, (
        'An update interval (in seconds) for reloading runtime properties '
        'from a datastore. Using this editor, you can set this value to an '
        'integer between 1 and 300. To completely disable  reloading '
        'properties from a datastore, you must set the value to 0. However, '
        'you can only set the value to 0 by directly modifying the app.yaml '
        'file. Maximum value is "%s".' % MAX_UPDATE_INTERVAL),
    DEFAULT_UPDATE_INTERVAL)

if __name__ == '__main__':
    run_all_unit_tests()
