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

"""Unified method of referring to to heterogenous resources in courses"""

__author__ = 'Mike Gainer (mgainer@google.com)'


class AbstractResourceHandler(object):
    """Unified accessor for heterogenous resources within CourseBuilder.

    CourseBuilder contains a number of different resources, such as
    questions, units, lessons, course settings, etc.  There are a number
    of features that are concerned with acting on some or all of these
    types, and would like to do so polymorphically.  (E.g., I18N,
    skill mapping, and other 3rd-party modules).
    """

    # Derived classes must set TYPE to a short, globally-unique string.  This
    # string may only contain lowercase letters, numbers, and underscores.
    TYPE = None

    @classmethod
    def get_key(cls, instance):
        """Returns a key for the given instance.

        Args:
          instance: And instance of a Course Builder resource.
        Returns:
          A Key for that instance.
        """
        raise NotImplementedError('Derived classes must implement this.')

    @classmethod
    def get_resource(cls, course, key):
        """Returns an instance of the resource type.

        Args:
          course: A courses.Course instance
          key: A small fact (string or integer, typically) representing
              the primary key for the desired instance.
        Returns:
          A loaded instance of the type appropriate for the Handler subtype.
          Note that this can be very broadly interpreted.  For example,
          since it is so common to need the Unit corresponding to a Lesson,
          this function in ResourceLesson returns a 2-tuple of the unit
          and lesson, rather than just the lesson.
        """
        raise NotImplementedError('Derived classes must implement this.')

    @classmethod
    def get_resource_title(cls, resource):
        """Get a title for the resource.

        Args:
          resource: Whatever is returned from get_resource() (q.v.)
        Returns:
          A short human-friendly string for titling the resource.
          NOTE: This string is not I18N'd - it is the actual string
          from the resource, before translation.  This string is
          suitable for display in dashboard contexts, where it is
          OK to presume a reasonable working knowledge of English,
          but not on student-facing pages.
        """
        raise NotImplementedError('Derived classes must implement this.')

    @classmethod
    def get_schema(cls, course, key):
        """Return a schema describing the value returned from get_data_dict().

        Again, note that in theory, the specific identity of the item in
        question should not be required to get what should be a generic
        schema.  The difference between theory and practice....

        Args:
          course: A courses.Course instance.
          key: A small fact (string or integer, typically) representing
              the primary key for the desired instance.
        Returns:
          A schema_fields.FieldRegistry instance.
        """
        raise NotImplementedError('Derived classes must implement this.')

    @classmethod
    def get_data_dict(cls, course, key):
        """Return a simple dict expression of the object's data.

        This is typically used in REST editors and other similar import/
        export related scenarios.

        Args:
          course: A courses.Course instance.
          key: A small fact (string or integer, typically) representing
              the primary key for the desired instance.
        Returns:
          A dict corresponding to the schema from get_schema().
        """
        raise NotImplementedError('Derived classes must implement this.')

    @classmethod
    def get_view_url(cls, resource):
        """Return a URL that will show a student view of the item.

        Not all classes need to return a reasonable value here.  For
        example, Labels and Skills may just not have a simple student-visible
        representation.  It is fine in those cases to return None; the
        caller must deal with this situation appropriately.

          resource: Whatever is returned from get_resource() (q.v.)
        Returns:
          A *relative* URL.  E.g., dashboard?action=foo_bar Such a
          URL can be placed unmmodified on a page which has been set
          up with the default URL prefix pointing to the namespace for
          the current course.
        """
        raise NotImplementedError('Derived classes must implement this.')

    @classmethod
    def get_edit_url(cls, key):
        """Return a dashboard URL for editing the resource.

        All classes should implement this function.  If it is hard to
        implement this, then you may have made a poor selection as to
        the noun that you're trying to represent.

        Args:
          key: A small fact (string or integer, typically) representing
              the primary key for the desired instance.
        Returns:
          A *relative* URL.  E.g., dashboard?action=foo_bar Such a
          URL can be placed unmmodified on a page which has been set
          up with the default URL prefix pointing to the namespace for
          the current course.
        """
        raise NotImplementedError('Derived classes must implement this.')


class Registry(object):

    _RESOURCE_HANDLERS = {}

    @classmethod
    def register(cls, resource_handler):
        """Object types wishing to be generically handled register here.

        Args:
          resource_handler: A class that inherits from AbstractResourceHandler,
          above.
        """

        type_name = resource_handler.TYPE
        if type_name in cls._RESOURCE_HANDLERS:
            raise ValueError(
                'The type name "%s" is already registered as a resource.' %
                type_name)
        cls._RESOURCE_HANDLERS[type_name] = resource_handler

    @classmethod
    def unregister(cls, resource_handler):
        type_name = resource_handler.TYPE
        if type_name in cls._RESOURCE_HANDLERS:
            del cls._RESOURCE_HANDLERS[type_name]

    @classmethod
    def get(cls, name):
        if not cls.is_valid_name(name):
            raise ValueError('Unknown resource type: %s' % name)
        return cls._RESOURCE_HANDLERS[name]

    @classmethod
    def is_valid_name(cls, name):
        return name in cls._RESOURCE_HANDLERS


class Key(object):
    """Manages key for Course Builder resource.

    Every Course Builder resource can be identified by a type name and a
    type-contextual key. This class holds data related to this keying, and
    manages serialization/deserialization as strings.
    """

    SEPARATOR = ':'

    def __init__(self, type_str, key, course=None):
        self._type = type_str
        self._key = key
        self._course = course
        assert Registry.is_valid_name(self._type), (
            'Unknown resource type: %s' % type_str)

    def __str__(self):
        return '%s%s%s' % (self._type, self.SEPARATOR, self._key)

    def __repr__(self):
        return "<{} {}>".format(self.__class__.__name__, str(self))

    @property
    def type(self):
        return self._type

    @property
    def key(self):
        return self._key

    @classmethod
    def fromstring(cls, key_str):
        index = key_str.index(cls.SEPARATOR)
        return Key(key_str[:index], key_str[index + 1:])

    def get_resource(self, course):
        course = course or self._course
        return Registry.get(self._type).get_resource(course, self._key)

    def get_schema(self, course):
        return Registry.get(self._type).get_schema(course, self._key)

    def get_data_dict(self, course):
        return Registry.get(self._type).get_data_dict(course, self._key)
