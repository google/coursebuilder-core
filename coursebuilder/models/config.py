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
import threading
import time

import entities
import messages
import transforms

import appengine_config

from google.appengine.api import namespace_manager
from google.appengine.ext import db


# The default update interval supported.
DEFAULT_UPDATE_INTERVAL_SEC = 60

# The longest update interval supported.
MAX_UPDATE_INTERVAL_SEC = 60 * 5


# Allowed property types.
TYPE_INT = int
TYPE_STR = str
TYPE_BOOL = bool
ALLOWED_TYPES = frozenset([TYPE_INT, TYPE_STR, TYPE_BOOL])


class ConfigProperty(object):
    """A property with name, type, doc_string and a default value."""

    def __init__(
        self, name, value_type, doc_string,
        default_value=None, multiline=False, validator=None,
        after_change=None, label=None, deprecated=False):
        """Create a new global config property.

        These properties are persisted as ConfigPropertyEntity in the default
        namespace.  As such, these properties apply to the installation as
        a whole, rather than individual courses.

        Args:
          name: A name, by convention starting with "gcb_" for Google
              Course Builder, and something else for third-party extensions.
          value_type: A Python type, one of {bool, str, int}
          doc_string: A brief description displayed on the admin page listing
              all the config variables
          default_value: The value used when no override has been set by the
              site admin.
          multiline: Whether the value, if value_type is str, can be
              expected to extend to multiple lines of text.
          validator: A function taking two parameters:
              value: The value to validate
              errors: A list of strings indicating problems.  If the value
                  is acceptable, 'errors' must not be appended to, and
                  conversely.
          after_change: This is a function which is called only when the
              value is changed by the site administrator via the UI.
              (It is not called when the underlying ConfigPropertyEntity is
              directly modified).  This function takes two one parameters:
              the ConfigProperty instance, and the previous value.
          label: A friendly display name.
          deprecated: True/False.  When a property is logically removed,
              it should be marked as deprecated.  This will leave the name
              known to the system so that we do not issue spurious warnings
              about unknown properties (once per minute, on property refresh)
        """

        if value_type not in ALLOWED_TYPES:
            raise Exception('Bad value type: %s' % value_type)

        self._validator = validator
        self._multiline = multiline
        self._name = name
        self._label = label
        self._type = value_type
        self._doc_string = doc_string
        self._default_value = value_type(default_value)
        self._after_change = after_change
        self._deprecated = deprecated

        errors = []
        if self._validator and self._default_value:
            self._validator(self._default_value, errors)
        if errors:
            raise Exception('Default value is invalid: %s.' % errors)

        Registry.registered[name] = self
        if name in Registry.db_items:
            item = Registry.db_items[name]
            del Registry.db_items[name]
            # pylint: disable=protected-access
            Registry._config_property_entity_changed(item)

    @property
    def validator(self):
        return self._validator

    @property
    def after_change(self):
        """Properties may register callbacks to notice changes to value."""
        return self._after_change

    @property
    def multiline(self):
        return self._multiline

    @property
    def name(self):
        return self._name

    @property
    def label(self):
        return self._label or self._name

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
            except Exception:  # pylint: disable=broad-except
                logging.error(
                    'Property %s failed to cast to type %s; removing.',
                    self._name, self._type)
                del os.environ[name]
        return False, None

    def get_value(self, db_overrides=None):
        """Gets value from overrides (datastore, environment) or default."""

        # Try testing overrides.
        overrides = Registry.test_overrides
        if overrides and self.name in overrides:
            return overrides[self.name]

        # Try datastore overrides.
        if db_overrides and self.name in db_overrides:
            return db_overrides[self.name]

        # Try environment variable overrides.
        has_value, environ_value = self.get_environ_value()
        if has_value:
            return environ_value

        # Use default value as last resort.
        return self._default_value

    @property
    def value(self):
        return self.get_value(db_overrides=Registry.get_overrides())

    @property
    def deprecated(self):
        return self._deprecated

class ValidateLength(object):

    def __init__(self, length):
        self._length = length

    def validator(self, value, errors):
        if len(value) != self._length:
            errors.append(
                'The length of this field must be exactly %d, ' % self._length +
                'but the value "%s" is of length %d.' % (value, len(value)))


class ValidateIntegerRange(object):

    def __init__(self,
                 lower_bound_inclusive=None,
                 upper_bound_inclusive=None,
                 lower_bound_exclusive=None,
                 upper_bound_exclusive=None):
        if (lower_bound_exclusive is not None and
            lower_bound_inclusive is not None):
            raise ValueError('Please specify only one lower bound.')
        if (upper_bound_exclusive is not None and
            upper_bound_inclusive is not None):
            raise ValueError('Please specify only one upper bound.')
        if (lower_bound_inclusive is None and
            lower_bound_exclusive is None and
            upper_bound_inclusive is None and
            upper_bound_exclusive is None):
            raise ValueError('Please specify at least one bound.')

        # Convert to integers before checking ranges for sanity.
        self._lower_bound_inclusive = None
        self._lower_bound_exclusive = None
        self._upper_bound_inclusive = None
        self._upper_bound_exclusive = None
        if lower_bound_inclusive != None:
            self._lower_bound_inclusive = int(lower_bound_inclusive)
        if lower_bound_exclusive != None:
            self._lower_bound_exclusive = int(lower_bound_exclusive)
        if upper_bound_inclusive != None:
            self._upper_bound_inclusive = int(upper_bound_inclusive)
        if upper_bound_exclusive != None:
            self._upper_bound_exclusive = int(upper_bound_exclusive)

        if (lower_bound_exclusive is not None and
            upper_bound_exclusive is not None and
            lower_bound_exclusive + 1 >= upper_bound_exclusive):
            raise ValueError('Bounds do not permit any valid values.')
        if (lower_bound_inclusive is not None and
            upper_bound_exclusive is not None and
            lower_bound_inclusive >= upper_bound_exclusive):
            raise ValueError('Bounds do not permit any valid values.')
        if (lower_bound_exclusive is not None and
            upper_bound_inclusive is not None and
            lower_bound_exclusive >= upper_bound_inclusive):
            raise ValueError('Bounds do not permit any valid values.')
        if (lower_bound_inclusive is not None and
            upper_bound_inclusive is not None and
            lower_bound_inclusive > upper_bound_inclusive):
            raise ValueError('Bounds do not permit any valid values.')

    def validate(self, value, errors):
        try:
            value = int(value)
        except ValueError:
            errors.append('"%s" is not an integer' % value)
            return

        if (self._lower_bound_inclusive is not None and
            value < self._lower_bound_inclusive):
            errors.append('This value must be greater than or equal to %d' %
                          self._lower_bound_inclusive)
        if (self._lower_bound_exclusive is not None and
            value <= self._lower_bound_exclusive):
            errors.append('This value must be greater than %d' %
                          self._lower_bound_exclusive)
        if (self._upper_bound_inclusive is not None and
            value > self._upper_bound_inclusive):
            errors.append('This value must be less than or equal to %d' %
                          self._upper_bound_inclusive)
        if (self._upper_bound_exclusive is not None and
            value >= self._upper_bound_exclusive):
            errors.append('This value must be less than %d' %
                          self._upper_bound_exclusive)


class Registry(object):
    """Holds all registered properties and their various overrides."""
    registered = {}
    test_overrides = {}
    db_items = {}
    db_overrides = {}
    names_with_draft = {}
    last_update_time = 0
    update_index = 0
    threadlocal = threading.local()
    REENTRY_ATTR_NAME = 'busy'

    @classmethod
    def get_overrides(cls, force_update=False):
        """Returns current property overrides, maybe cached."""

        now = long(time.time())
        age = now - cls.last_update_time
        max_age = UPDATE_INTERVAL_SEC.get_value(db_overrides=cls.db_overrides)

        # do not update if call is reentrant or outer db transaction exists
        busy = hasattr(cls.threadlocal, cls.REENTRY_ATTR_NAME) or (
            db.is_in_transaction())

        if (not busy) and (force_update or age < 0 or age >= max_age):
            # Value of '0' disables all datastore overrides.
            if UPDATE_INTERVAL_SEC.get_value() == 0:
                cls.db_overrides = {}
                return cls.db_overrides

            # Load overrides from a datastore.
            setattr(cls.threadlocal, cls.REENTRY_ATTR_NAME, True)
            try:
                old_namespace = namespace_manager.get_namespace()
                try:
                    namespace_manager.set_namespace(
                        appengine_config.DEFAULT_NAMESPACE_NAME)
                    cls._load_from_db()
                finally:
                    namespace_manager.set_namespace(old_namespace)
            except Exception as e:  # pylint: disable=broad-except
                logging.error(
                    'Failed to load properties from a database: %s.', str(e))
            finally:
                delattr(cls.threadlocal, cls.REENTRY_ATTR_NAME)

                # Avoid overload and update timestamp even if we failed.
                cls.last_update_time = now
                cls.update_index += 1

        return cls.db_overrides

    @classmethod
    def _load_from_db(cls):
        """Loads dynamic properties from db."""
        items = {}
        overrides = {}
        drafts = set()
        for item in ConfigPropertyEntity.all().fetch(1000):
            items[item.key().name()] = item
            cls._set_value(item, overrides, drafts)
        cls.db_items = items
        cls.db_overrides = overrides
        cls.names_with_draft = drafts

    @classmethod
    def _config_property_entity_changed(cls, item):
        cls._set_value(item, cls.db_overrides, cls.names_with_draft)

    @classmethod
    def _set_value(cls, item, overrides, drafts):
        name = item.key().name()
        target = cls.registered.get(name, None)
        if not target:
            if appengine_config.MODULE_REGISTRATION_IN_PROGRESS:
                log_level = logging.INFO
            else:
                log_level = logging.WARNING
            logging.log(log_level, 'Property is not registered (skipped): %s',
                        name)
            return

        if item.is_draft:
            if name in overrides:
                del overrides[name]
            drafts.add(name)
        else:
            if name in drafts:
                drafts.remove(name)

            # Enforce value type.
            try:
                value = transforms.string_to_value(
                    item.value, target.value_type)
            except Exception:  # pylint: disable=broad-except
                logging.error(
                    'Property %s failed to cast to a type %s; removing.',
                    target.name, target.value_type)
                return

            # Enforce value validator.
            if target.validator:
                errors = []
                try:
                    target.validator(value, errors)
                except Exception as e:  # pylint: disable=broad-except
                    errors.append(
                        'Error validating property %s.\n%s',
                        (target.name, e))
                if errors:
                    logging.error(
                        'Property %s has invalid value:\n%s',
                        target.name, '\n'.join(errors))
                    return

            overrides[name] = value


class ConfigPropertyEntity(entities.BaseEntity):
    """A class that represents a named configuration property."""
    value = db.TextProperty(indexed=False)
    is_draft = db.BooleanProperty(indexed=False)

    def put(self):
        # Persist to DB.
        super(ConfigPropertyEntity, self).put()

        # And tell local registry.  Do this by direct call and synchronously
        # so that this setting will be internally consistent within the
        # remainder of this server's path of execution.  (Note that the
        # setting is _not_ going to be immediately available at all other
        # instances; they will pick it up in due course after
        # UPDATE_INTERVAL_SEC has elapsed.

        # pylint: disable=protected-access
        Registry._config_property_entity_changed(self)


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
    'gcb_config_update_interval_sec', int,
    messages.SITE_SETTINGS_REFRESH_INTERVAL_TEMPLATE % MAX_UPDATE_INTERVAL_SEC,
    default_value=DEFAULT_UPDATE_INTERVAL_SEC, label='Refresh Interval',
    validator=ValidateIntegerRange(
        lower_bound_inclusive=0,
        upper_bound_inclusive=MAX_UPDATE_INTERVAL_SEC).validate)

if __name__ == '__main__':
    run_all_unit_tests()
