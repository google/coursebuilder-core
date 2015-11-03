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

"""Classes to build sanitized HTML."""

__author__ = 'John Orr (jorr@google.com)'

import cgi
import re


def escape(strg):
    return cgi.escape(strg, quote=1).replace("'", '&#39;').replace('`', '&#96;')


class SafeDom(object):
    """Base class for the sanitizing module."""

    def __init__(self):
        self._parent = None

    def _set_parent(self, parent):
        assert self != parent
        self._parent = parent

    @property
    def parent(self):
        return self._parent

    @property
    def sanitized(self):
        raise NotImplementedError()

    def __str__(self):
        return self.sanitized


class Node(SafeDom):
    """Represents a single node in the DOM."""


# pylint: disable=incomplete-protocol
class NodeList(SafeDom):
    """Holds a list of Nodes and can bulk sanitize them."""

    def __init__(self):
        self.list = []
        super(NodeList, self).__init__()

    def __len__(self):
        return len(self.list)

    def append(self, node):
        assert node is not None, 'Cannot add an empty value to the node list'
        self.list.append(node)
        node._set_parent(self)  # pylint: disable=protected-access
        return self

    @property
    def children(self):
        return [] + self.list

    def empty(self):
        self.list = []
        return self

    def delete(self, node):
        _list = []
        for child in self.list:
            if child != node:
                _list.append(child)
        self.list = _list

    def insert(self, index, node):
        assert node is not None, 'Cannot add an empty value to the node list'
        self.list.insert(index, node)
        node._set_parent(self)  # pylint: disable=protected-access
        return self

    @property
    def sanitized(self):
        sanitized_list = []
        for node in self.list:
            sanitized_list.append(node.sanitized)
        return ''.join(sanitized_list)


class Text(Node):
    """Holds untrusted text which will be sanitized when accessed."""

    def __init__(self, unsafe_string):
        super(Text, self).__init__()
        self._value = unicode(unsafe_string)

    @property
    def sanitized(self):
        return escape(self._value)


class Comment(Node):
    """An HTML comment."""

    def __init__(self, unsafe_string=''):
        super(Comment, self).__init__()
        self._value = unicode(unsafe_string)

    def get_value(self):
        return self._value

    @property
    def sanitized(self):
        return '<!--%s-->' % escape(self._value)

    def add_attribute(self, **attr):
        pass

    def add_text(self, unsafe_string):
        self._value += unicode(unsafe_string)


class Element(Node):
    """Embodies an HTML element which will be sanitized when accessed."""

    _ALLOWED_NAME_PATTERN = re.compile(r'^[a-zA-Z][_\-a-zA-Z0-9]*$')

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
        super(Element, self).__init__()
        self._tag_name = tag_name
        self._children = []
        self._attr = {}
        for _name, _value in attr.items():
            self._attr[_name.lower()] = _value

    def has_attribute(self, name):
        return name.lower() in self._attr

    @property
    def attributes(self):
        return self._attr.keys()

    def set_attribute(self, name, value):
        self._attr[name.lower()] = value
        return self

    def get_escaped_attribute(self, name):
        return escape(self._attr[name.lower()])

    def add_attribute(self, **attr):
        for attr_name, value in attr.items():
            assert Element._ALLOWED_NAME_PATTERN.match(attr_name), (
                'attribute name %s is not allowed' % attr_name)
            self._attr[attr_name.lower()] = value
        return self

    def add_child(self, node):
        node._set_parent(self)  # pylint: disable=protected-access
        self._children.append(node)
        return self

    def append(self, node):
        return self.add_child(node)

    def add_children(self, node_list):
        for child in node_list.list:
            self.add_child(child)
        return self

    def empty(self):
        self._children = []
        return self

    def add_text(self, text):
        return self.add_child(Text(text))

    def can_have_children(self):
        return True

    @property
    def children(self):
        return [] + self._children

    @property
    def tag_name(self):
        return self._tag_name

    @property
    def sanitized(self):
        """Santize the element and its descendants."""
        assert Element._ALLOWED_NAME_PATTERN.match(self._tag_name), (
            'tag name %s is not allowed' % self._tag_name)
        buff = '<' + self._tag_name
        for attr_name, value in sorted(self._attr.items()):
            if attr_name == 'classname':
                attr_name = 'class'
            elif attr_name.startswith('data_'):
                attr_name = attr_name.replace('_', '-')
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


class A(Element):
    """Embodies an 'a' tag.  Just a conveniece wrapper on Element."""

    def __init__(self, href, **attr):
        """Initialize an 'a' tag to a given target.

        Args:
            href: The value to put in the 'href' tag of the 'a' element.
            **attr: the names and value of the attributes. Names must match
                _ALLOWED_NAME_PATTERN and values will be quote-escaped.
        """

        super(A, self).__init__('a', **attr)
        self.add_attribute(href=href)


class ScriptElement(Element):
    """Represents an HTML <script> element."""

    def __init__(self, **attr):
        super(ScriptElement, self).__init__('script', **attr)

    def can_have_children(self):
        return False

    def add_child(self, unused_node):
        raise ValueError()

    def add_children(self, unused_nodes):
        raise ValueError()

    def empty(self):
        raise ValueError()

    def add_text(self, text):
        """Add the script body."""

        class Script(Text):

            def __init__(self, script):
                # Pylint is just plain wrong about warning here; suppressing.
                # pylint: disable=bad-super-call
                super(Script, self).__init__(None)
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
        super(Entity, self).__init__()
        self._entity = entity

    @property
    def sanitized(self):
        assert Entity.ENTITY_PATTERN.match(self._entity)
        return self._entity


def _assemble_link_element(uri, text, **attr):
    attr['href'] = uri
    return Element('a', **attr).add_text(text)


def assemble_text_message(text, link):
    node_list = NodeList()
    if text:
        node_list.append(Text(text))
        node_list.append(Entity('&nbsp;'))
    if link:
        node_list.append(
            _assemble_link_element(link, 'Learn more...', target='_blank'))
    return node_list


def assemble_link(uri, text, **attr):
    node_list = NodeList()
    node_list.append(_assemble_link_element(uri, text, **attr))
    return node_list


class Template(Node):
    """Enables a Jinja template to be included in a safe_dom.NodeList."""

    def __init__(self, template, **kwargs):
        self.template = template
        self.kwargs = kwargs
        super(Template, self).__init__()

    @property
    def sanitized(self):
        return self.template.render(**self.kwargs)
