"""Classes to build sanitized HTML."""

__author__ = 'John Orr (jorr@google.com)'

import cgi
import re
import urllib


class Node(object):
    """Base class for the sanitizing module."""

    @property
    def sanitized(self):
        raise NotImplementedError()

    def __str__(self):
        return self.sanitized


class NodeList(object):
    """Holds a list of Nodes and can bulk sanitize them."""

    def __init__(self):
        self.list = []

    def append(self, node):
        self.list.append(node)
        return self

    @property
    def sanitized(self):
        sanitized_list = []
        for node in self.list:
            sanitized_list.append(node.sanitized)
        return ''.join(sanitized_list)

    def __str__(self):
        return self.sanitized


class Text(Node):
    """Holds untrusted text which will be sanitized when accessed."""

    def __init__(self, unsafe_string):
        self._value = unsafe_string

    @property
    def sanitized(self):
        return cgi.escape(self._value)


class Element(Node):
    """Embodies an HTML element which will be sanitized when accessed."""

    _ALLOWED_NAME_PATTERN = re.compile('^[a-zA-Z]+$')

    def __init__(self, tag_name, **attr):
        """Initializes an element with given tag name and attributes.

        Tag name will be restricted to alpha chars, attribute names
        will be quote-escaped.

        Args:
            tag_name: the name of the element, which must match [a-zA-Z]+
            **attr: the names and value of the attributes. Names must match
                [a-zA-Z]+ and values will be quote-escaped.
        """
        assert Element._ALLOWED_NAME_PATTERN.match(tag_name), (
            'tag name %s is not allowed' % tag_name)
        for attr_name in attr:
            assert Element._ALLOWED_NAME_PATTERN.match(attr_name), (
                'attribute name %s is not allowed' % attr_name)

        self._tag_name = tag_name
        self._attr = attr
        self._children = []

    def add_child(self, node):
        self._children.append(node)
        return self

    def add_text(self, text):
        return self.add_child(Text(text))

    @property
    def sanitized(self):
        """Santize the element and its descendants."""
        assert Element._ALLOWED_NAME_PATTERN.match(self._tag_name), (
            'tag name %s is not allowed' % self._tag_name)
        buff = '<' + self._tag_name
        for attr_name, value in self._attr.items():
            if attr_name == 'className':
                attr_name = 'class'
            if value is None:
                value = ''
            buff += ' %s="%s"' % (
                attr_name, urllib.quote(value, safe='/()?&#=:'))
        buff += '>'
        for child in self._children:
            buff += child.sanitized
        buff += '</%s>' % self._tag_name
        return buff


class Entity(Node):
    """Holds an XML entity."""

    ENTITY_PATTERN = re.compile('^&([a-zA-Z]+|#[0-9]+|#x[0-9a-fA-F]+);$')

    def __init__(self, entity):
        assert Entity.ENTITY_PATTERN.match(entity)
        self._entity = entity

    @property
    def sanitized(self):
        assert Entity.ENTITY_PATTERN.match(self._entity)
        return self._entity
