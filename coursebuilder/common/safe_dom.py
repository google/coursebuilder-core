"""Classes to build sanitized HTML."""

__author__ = 'John Orr (jorr@google.com)'

import cgi
import re


def escape(strg):
    return cgi.escape(strg, quote=1).replace("'", '&#39;').replace('`', '&#96;')


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

    def __len__(self):
        return len(self.list)

    def append(self, node):
        assert node is not None, 'Cannot add an empty value to the node list'
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
        return escape(self._value)


class Element(Node):
    """Embodies an HTML element which will be sanitized when accessed."""

    _ALLOWED_NAME_PATTERN = re.compile('^[a-zA-Z][a-zA-Z0-9]*$')

    _VOID_ELEMENTS = frozenset([
        'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'keygen',
        'link', 'menuitem', 'meta', 'param', 'source', 'track', 'wbr'])

    def __init__(self, tag_name, **attr):
        """Initializes an element with given tag name and attributes.

        Tag name will be restricted to alpha chars, attribute names
        will be quote-escaped.

        Args:
            tag_name: the name of the element, which must match
                _ALLOWED_NAME_PATTERN.
            **attr: the names and value of the attributes. Names must match
                _ALLOWED_NAME_PATTERN and values will be quote-escaped.
        """
        assert Element._ALLOWED_NAME_PATTERN.match(tag_name), (
            'tag name %s is not allowed' % tag_name)
        for attr_name in attr:
            assert Element._ALLOWED_NAME_PATTERN.match(attr_name), (
                'attribute name %s is not allowed' % attr_name)

        self._tag_name = tag_name
        self._attr = attr
        self._children = []

    def add_attribute(self, **attr):
        for attr_name, value in attr.items():
            assert Element._ALLOWED_NAME_PATTERN.match(attr_name), (
                'attribute name %s is not allowed' % attr_name)
            self._attr[attr_name] = value
        return self

    def add_child(self, node):
        self._children.append(node)
        return self

    def add_children(self, node_list):
        self._children += node_list.list
        return self

    def add_text(self, text):
        return self.add_child(Text(text))

    @property
    def sanitized(self):
        """Santize the element and its descendants."""
        assert Element._ALLOWED_NAME_PATTERN.match(self._tag_name), (
            'tag name %s is not allowed' % self._tag_name)
        buff = '<' + self._tag_name
        for attr_name, value in sorted(self._attr.items()):
            if attr_name == 'className':
                attr_name = 'class'
            if value is None:
                value = ''
            buff += ' %s="%s"' % (
                attr_name, escape(value))

        if self._children:
            buff += '>'
            for child in self._children:
                buff += child.sanitized
            buff += '</%s>' % self._tag_name
        elif self._tag_name.lower() in Element._VOID_ELEMENTS:
            buff += '/>'
        else:
            buff += '></%s>' % self._tag_name

        return buff


class ScriptElement(Element):
    """Represents an HTML <script> element."""

    def __init__(self, **attr):
        super(ScriptElement, self).__init__('script', **attr)

    def add_child(self, unused_node):
        raise ValueError()

    def add_children(self, unused_nodes):
        raise ValueError()

    def add_text(self, text):
        """Add the script body."""

        class Script(Node):
            def __init__(self, script):
                self._script = script

            @property
            def sanitized(self):
                if '</script>' in self._script:
                    raise ValueError('End script tag forbidden')
                return self._script

        self._children.append(Script(text))


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
