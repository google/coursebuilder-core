# -*- coding: utf-8 -*-
# Copyright 2014 Google Inc. All Rights Reserved.
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

"""HTML content transformation and manipulation functions.

About

    This module performs complex HTML document transformations, which enable
    machine-assisted internationalization (I18N) of content.


Extracting a resource bundle from your HTML content

  This is done using extract_resource_bundle_from() function. Here is what
  happens behind the scenes.

  HTML content is received as text and parsed into an XML ElementTree tree with
  html5lib library. ElementTree is then converted into safe_dom tree. Already
  parsed tree can be provided as well.

  The HTML tags in the tree are inspected to extract all contiguous text chunks.
  For example: content of <p>...</p> tag is extracted as one chunk, with a
  simple markup (like <a>, <b>, <i> and <br>) left inline.

  Text chunks are returned as a list of strings. Each string contains plain
  text and an inline markup. The markup uses slightly modified original tag
  names with the unique index appended and with most attributes removed. For
  example:
    '<a href="foo" title="Bar">Foo</a><br/><b>Bar</b>'
  becomes
    '<a#1 title="Bar">Foo</a#1><br#2 /><b#3>Bar</b#3>'

  The list of strings, which we will call a 'resource bundle', is ready to be
  sent to translator, who must translate both plain text and the text between
  inline markup. Reorder of marked up terms is allowed.

  When I said 'plain text', I lied a little bit. The strings are expected to
  a) be HTML entity encoded and b) be of unicode type in Python. Each of the
  strings will be parsed using minidom XML parser. The translator must take care
  of the entity encoding, and you as a developer must take care of using proper
  charsets in the user interface given to the translator. During the XML parsing
  phase UTF-8 is used internally.


Putting translations into your HTML content

  This is done using merge_resource_bundle_into() function. Here is what
  happens behind the scenes.

  The list of strings is received along with the HTML content or an safe_dom
  tree of the content to be inserted into. The content is processed as described
  above and both the strings and the markup in the original language are
  removed.

  New strings are inserted one by one into the proper places of the content tree
  and inline markup is expanded to have the proper original tags names and the
  attributes. The values of attributes like 'alt' and 'title' can be provided in
  the translations, other attributes specified in the translations are ignored.

  No attempt is made to make sure new strings correspond to the original
  strings. Whatever strings are given, those are the ones we will try to weave
  into the content. Thus, when the original content changes, it's your
  responsibility to diff the resource bundles before and after the edit, send
  the delta to translator and compose new updated resource bundle.

  The final safe_dom tree with the translations put in is returned. You have
  many options how to render it out, including using functions provided
  ContentIO.tostring() function.


Common issues

    Where is my whitespace?
      Whitespace inside and around translation strings is removed intentionally.

    Why do I see 'UnicodeDecodeError: 'ascii' codec can't decode byte...'?
      you most like forgot the a letter 'u' in front of your Python unicode
      string


Resource String Disambiguation

    One may encounter two strings that have exact same text in English, but have
    to be translated differently due to the context of their use. Simply add a
    comment just before the text to be translated. The comment must start with
    the 'I18N:', otherwise it is not shown. For example, here a valid i18N
    comment: '<!-- I18N: "Android" means "a robot" in this context -->'.


Open Issues:

    - P0: complete map_source_to_target() for allow_list_reorder=True
    - P0: move all schemas out of dashboard into models; leave UX specific
      inputEx annotations of those schemas in dashboard
    - P0: clean up and streamline Registry/SchemaFields
    - P0: update about herein with details of object bind/map/diff
    - P0: get rid of minidom, use cElementTree to reduce parser dependency
    - P0: drop '#' and allow <a> and <b> while no disambiguation is required
    - P0: how shall safedom handle custom tag nodes that are not yet ready to
      be expanded; as proxy nodes?


Good luck!
"""

__author__ = 'Pavel Simakov (psimakov@google.com)'


import difflib
import htmlentitydefs
import re
import StringIO
import sys
import unittest
from xml.dom import minidom
import safe_dom
from tags import html_to_safe_dom


XML_ENCODING = 'utf-8'

# Comments having this prefix will be extracted into the resource bundle; for
# example: <!-- I18N: 'Android' here means 'robot', not 'operating system' -->
I18N_COMMENT_PREFIX = 'I18N:'

# These tags are rendered inline if the don't have any children;
# for example: <a#1>Foo!</a#1>
DEFAULT_INLINE_TAG_NAMES = [
    'A', 'B', 'I', 'SPAN', 'BR', 'STRONG', 'EM', 'SMALL']

# These tags are not inspected are rendered inline without any content;
# for example: <script#1 />
DEFAULT_OPAQUE_TAG_NAMES = ['SCRIPT', 'STYLE']

# These tags are inspected and are rendered inline without any content;
# for example: <ul#1 />; their children are extracted and for translation as
# independent items
DEFAULT_OPAQUE_DECOMPOSABLE_TAG_NAMES = [
    'UL', 'TABLE', 'IMG', 'INPUT', 'TEXTAREA']

# The key is an attribute name. The value is a set of tag names, for which
# this attribute can be recomposed from resource bundle. All other attributes
# are not recomposable.
DEFAULT_RECOMPOSABLE_ATTRIBUTES_MAP = {
    'ALT': set(['*']), 'TITLE': set(['*']), 'SRC': set(['IMG']),
    'PLACEHOLDER': set(['INPUT', 'TEXTAREA'])}

# Regex that matches HTML entities (& followed by anything other than a ;, up to
# a ;).
_ENTITY_REGEX = re.compile('(&[a-z]+;)')
# Items we don't want to change to codes when translating HTML entities in XML.
_XML_ENTITY_NAMES = frozenset(['quot', 'amp', 'lt', 'gt', 'apos'])

# pylint: disable=protected-access


def _get_entity_map():
    mappings = {}
    html_and_xml_entities = dict(htmlentitydefs.entitydefs)
    # Python is missing apos, which is part of XML.
    html_and_xml_entities['apos'] = None  # Set below.
    for name, code in html_and_xml_entities.iteritems():
        if name in _XML_ENTITY_NAMES:
            # In entitydefs, some codes are unicode chars and some are numeric
            # references. Standardize on all numeric references for minidom
            # compatibility.
            code = '&%s;' % name
        else:
            if not code.startswith('&'):
                code = '&#%s;' % str(ord(code))
        mappings[name] = code
    return mappings


# Map of HTML entity name string ('copy') to ASCII, decimal code string
# ('&#169;'). IMPORTANT: some entities are known to both HTML and XML (see
# _XML_ENTITY_NAMES). In that case, we do not translate to a code because we're
# processing XML. For those items, the value is the entity name (for example,
# for the key 'quot' the value is '&quot;').
_ENTITY_MAP = _get_entity_map()


class ContentIO(object):
    """Class that knows how to load and save HTML content to be translated."""

    @classmethod
    def _is_simple_text_content(cls, node):
        """Checks if node only has children of type Text."""
        simple_text_content = True
        children = cls._get_children(node)
        for child in children:
            if not isinstance(child, safe_dom.Text):
                simple_text_content = False
                break
        return simple_text_content

    @classmethod
    def _get_children(cls, node_list_or_element):
        if isinstance(node_list_or_element, safe_dom.NodeList):
            return node_list_or_element.list
        if isinstance(node_list_or_element, safe_dom.Element):
            return node_list_or_element.children
        raise TypeError(
            'Expected NodeList/Element, found: %s.' % node_list_or_element)

    @classmethod
    def _merge_node_lists(cls, node_list, node):
        """Combines sibling or nested node lists into one."""
        if isinstance(node, safe_dom.NodeList):
            cls._merge_node_list_chidren(node_list, node)
        elif isinstance(node, safe_dom.Element):
            root_node_list = safe_dom.NodeList()
            root_node_list.append(node)
            cls._merge_node_list_chidren(node_list, root_node_list)
        else:
            node_list.append(node)

    @classmethod
    def _merge_node_list_chidren(cls, target_node_list, node_list):
        """Inspects NodeList and merges its contents recursively."""
        _children = [] + node_list.children
        node_list.empty()
        for child in _children:
            if isinstance(child, safe_dom.NodeList):
                cls._merge_node_list_chidren(target_node_list, child)
            else:
                target_node_list.append(child)
                if isinstance(child, safe_dom.Element):
                    cls._merge_element_chidren(child)

    @classmethod
    def _merge_element_chidren(cls, element):
        """Inspects Element and merges its contents recursively."""
        if not element.can_have_children():
            return
        _children = [] + element.children
        element.empty()

        _last_node_list_child = None
        for child in _children:
            if isinstance(child, safe_dom.NodeList):
                if _last_node_list_child is None:
                    _last_node_list_child = safe_dom.NodeList()
                    cls._merge_node_list_chidren(_last_node_list_child, child)
                    if _last_node_list_child:
                        element.append(_last_node_list_child)
                    else:
                        _last_node_list_child = None
                else:
                    cls._merge_node_list_chidren(_last_node_list_child, child)
            else:
                _last_node_list_child = None
                element.append(child)
                if isinstance(child, safe_dom.Element):
                    cls._merge_element_chidren(child)

    @classmethod
    def _normalize_tree(cls, tree):
        """Combines sibling or nested node lists into one."""
        node_list = safe_dom.NodeList()
        cls._merge_node_lists(node_list, tree)
        return node_list

    @classmethod
    def fromstring(cls, content):
        """Converts HTML string content into an XML tree."""
        return (
            html_to_safe_dom(unicode(content), None, render_custom_tags=False))

    @classmethod
    def tostring(cls, tree):
        """Renders tree to as HTML text."""
        return tree.sanitized


class TranslationIO(object):
    """Class that knows how to load and save XML translations."""

    @classmethod
    def _is_indexable(cls, node):
        """Checks if node can have an index of style of <a#1 />."""
        return not (isinstance(node, safe_dom.Text) or isinstance(
            node, safe_dom.Comment))

    @classmethod
    def _is_ancestor(cls, descendant, ancestor):
        if descendant == ancestor or descendant.parent == ancestor:
            return True
        if not descendant.parent:
            return False
        return cls._is_ancestor(descendant.parent, ancestor)

    @classmethod
    def _set_children(cls, node, children):
        if isinstance(node, safe_dom.NodeList):
            node.list = children
        elif isinstance(node, safe_dom.Element):
            node._children = children
        else:
            raise TypeError('Unsupported node type: %s.' % node)

    @classmethod
    def _copy_node_content_from_minidom_to_safe_dom(
        cls, source_node, target_element):
        """Copies child nodes from source to target."""
        if not source_node.childNodes:
            return
        target_element._children = []
        for node in source_node.childNodes:
            if node.nodeType == minidom.Node.TEXT_NODE:
                target_element.add_child(safe_dom.Text(node.nodeValue))
                continue
            if node.nodeType == minidom.Node.COMMENT_NODE:
                target_element.add_child(safe_dom.Comment(node.nodeValue))
                continue
            raise TypeError('Unknown node type: %s.' % node)

    @classmethod
    def _find_replace_for_tag_open(cls, source_delimiter, target_delimiter):
        """Returns regex pattern for replacing delimiter in the open tag."""
        return (
            r'<([a-zA-Z0-9_\-]+)%s([0-9]+)' % source_delimiter,
            '<\\1%s\\2' % target_delimiter)

    @classmethod
    def _find_replace_for_tag_close(cls, source_delimiter, target_delimiter):
        """Returns regex pattern for replacing delimiter in the closing tag."""
        return (
            r'</([a-zA-Z0-9_\-]+)%s([0-9]+)>' % source_delimiter,
            '</\\1%s\\2>' % target_delimiter)

    @classmethod
    def _apply_regex(cls, find_replace, content):
        _find, _replace = find_replace
        return re.sub(_find, _replace, content)

    @classmethod
    def remove_whitespace(cls, content):
        """Removes whitespace from translation string."""
        _content = content
        _content = re.sub(r'[\r\n]+', ' ', _content)
        _content = re.sub(r'\s\s+', ' ', _content)
        return _content.strip()

    @classmethod
    def _decode_tag_names(cls, content):
        """Decode all tags from 'tag#index' into 'tag-index' style names."""
        return cls._apply_regex(
            cls._find_replace_for_tag_open('#', '-'), cls._apply_regex(
                cls._find_replace_for_tag_close('#', '-'), content))

    @classmethod
    def _encode_tag_names(cls, content):
        """Encode all tags from 'tag-index' into 'tag#-index' style names."""
        return cls._apply_regex(
            cls._find_replace_for_tag_open('-', '#'), cls._apply_regex(
                cls._find_replace_for_tag_close('-', '#'), content))

    @classmethod
    def _element_to_translation(cls, config, context, element):
        """Converts safe_dom Element into a resource bundle string."""
        lines = []
        index = context.index.get_node_index_in_collation(element)
        assert index
        tag_name = '%s#%s' % (element.tag_name.lower(), index)

        start_tag = tag_name
        _attributes = element.attributes
        if config.sort_attributes:
            _attributes = sorted(_attributes)
        for attr in _attributes:
            tag_name_set = config.recomposable_attributes_map.get(attr.upper())
            if tag_name_set and (
                element.tag_name.upper() in tag_name_set
                or '*' in tag_name_set
            ):
                start_tag += ' %s="%s"' % (
                    attr, element.get_escaped_attribute(attr))

        if element.tag_name.upper() in config.opaque_tag_names:
            return False, '<%s />' % start_tag

        if element.tag_name.upper() in config.opaque_decomposable_tag_names:
            content = None
            if element.tag_name.upper() in config.inline_tag_names:
                content = []
                if element.children:
                    for child in element.children:
                        if not isinstance(child, safe_dom.Text):
                            raise TypeError(
                                'Unsupported node type: %s.' % child)
                        value = child.sanitized
                        content.append(value)
                if content:
                    content = ''.join(content)
                else:
                    content = None
            has_content = content or not config.omit_empty_opaque_decomposable
            if content:
                return has_content, '<%s>%s</%s>' % (
                    start_tag, content, tag_name)
            else:
                return has_content, '<%s />' % start_tag

        has_content = False
        if element.children:
            lines.append('<%s>' % start_tag)
            for child in element.children:
                if not isinstance(child, safe_dom.Text):
                    raise TypeError('Unsupported node type: %s.' % child)
                value = child.sanitized
                if value.strip():
                    has_content = True
                lines.append(value)
            lines.append('</%s>' % tag_name)
        else:
            lines.append('<%s />' % start_tag)
        return has_content, ''.join(lines)

    @classmethod
    def _collation_to_translation(cls, config, context, collation):
        """Converts a list of safe_dom nodes into a resource bundle string."""
        lines = []
        has_content = False
        for node in collation:
            if isinstance(
                node, safe_dom.Comment) or isinstance(node, safe_dom.Text):
                value = node.sanitized
                if value.strip():
                    has_content = True
                lines.append(value)
                continue
            if isinstance(node, safe_dom.Element):
                _has_content, _value = cls._element_to_translation(
                    config, context, node)
                if _has_content:
                    has_content = True
                lines.append(_value)
                continue
            raise TypeError('Unsupported node type: %s.' % node)

        if not has_content:
            return None
        return ''.join(lines)

    def new_tree(self):
        """Creates new empty tree."""
        return minidom.Document()

    @classmethod
    def parse_indexed_tag_name(cls, node):
        try:
            # Split off the last component after a '-'. (Note that custom tags
            # may contain '-' in their tag names.)
            parts = node.tagName.split('-')
            index = parts.pop()
            tag_name = '-'.join(parts)
            return tag_name, int(index)
        except:
            raise SyntaxError(
                'Error extracting index form the tag <%s>. '
                'Tag name format is <tag_name#index>, '
                'like <a#1>.' % node.tagName)

    @classmethod
    def extract_line_column_from_parse_error(cls, error):
        """Try to extract line, column from the text of parsing error."""
        try:
            msg = error.message
            match = re.match(r'.*\: line ([0-9]+), column ([0-9]+).*', msg)
            if match is not None:
                return int(match.group(1)), int(match.group(2))
        except:  # pylint: disable=bare-except
            pass
        return None, None

    @classmethod
    def get_text_fragment(cls, text, line_num, col_num, clip_len=16):
        """Makes an clip_len long excerpt of the text using line and column.

        Args:
          text: text to make a fragment of
          line_num: one-based line number of excerpt start
          col_num: one-based column number of excerpt start
          clip_len: number of character to leave on both sides of start position
        Returns:
           tuple clipped text fragment of the entire text if clipping failed
        """
        assert clip_len > 0
        lines = text.split('\n')
        if (line_num is not None
            and col_num is not None
            and line_num > 0
            and line_num <= len(lines)):
            line = lines[line_num - 1]
            if col_num < 0 or col_num >= len(line):
                return text
            from_col_num = max(col_num - clip_len, 0)
            to_col_num = min(col_num + clip_len, len(line))

            result = ''
            if from_col_num < col_num:
                result += line[from_col_num:col_num]
            result += '[%s]' % line[col_num]
            if to_col_num > col_num:
                result += line[col_num + 1:to_col_num]
            return result
        return text

    @classmethod
    def fromstring(cls, content):
        """Converts XML string content of the translation into an XML tree."""
        translated_entities = _ENTITY_REGEX.sub(cls._match_to_code, content)
        xml_text = '<div>%s</div>' % cls._decode_tag_names(
            translated_entities).encode(XML_ENCODING)
        try:
            tree = minidom.parseString(xml_text)
        except Exception as e:  # pylint: disable=broad-except
            line_num, col_num = cls.extract_line_column_from_parse_error(e)
            raise Exception(
                e.message, cls.get_text_fragment(xml_text, line_num, col_num))
        return tree

    @classmethod
    def _match_to_code(cls, match):
        return _ENTITY_MAP[match.group()[1:-1]]

    @classmethod
    def toxml(cls, tree):
        """Renders tree as XML text without XML declaration and root node."""
        assert 'DIV' == tree.documentElement.tagName.upper()
        data = StringIO.StringIO()
        for child in  tree.documentElement.childNodes:
            child.writexml(data)
        return data.getvalue()

    @classmethod
    def tocollation(cls, tree):
        """Converts a tree into a list of nodes no more than one level deep."""
        collation = []
        for node in tree.documentElement.childNodes:
            if node.nodeType == minidom.Node.TEXT_NODE:
                collation.append(node)
                continue
            if node.nodeType == minidom.Node.COMMENT_NODE:
                collation.append(node)
                continue
            if node.nodeType == minidom.Node.ELEMENT_NODE:
                for child in node.childNodes:
                    if child.nodeType not in [
                        minidom.Node.TEXT_NODE, minidom.Node.COMMENT_NODE]:
                        raise TypeError(
                            'Unsupported node child type: %s.' % child.nodeType)
                collation.append(node)
                continue
            raise TypeError('Unsupported node type: %s.' % node.nodeType)
        return collation

    @classmethod
    def get_indexed_tag_name(cls, node, index):
        return '%s#%s' % (node.tag_name.lower(), index)

    @classmethod
    def tostring(cls, tree):
        """Renders tree as a string with <a#1 /> style markup."""
        return cls._encode_tag_names(cls.toxml(tree))


class ResourceBundleItemError(Exception):
    """An error related to a specific string in a resource bundle."""

    def __init__(self, exc_info, original_exception, index):
        Exception.__init__(self, 'Error in chunk %s. %s' % (
            index + 1, original_exception))
        self._exc_info = exc_info
        self._original_exception = original_exception
        self._index = index

    @property
    def exc_info(self):
        return self._exc_info

    @property
    def index(self):
        return self._index

    @property
    def original_exception(self):
        return self._original_exception

    def reraise(self):
        """Re-raises an exception preserving original stack trace."""
        raise self._exc_info[0], self, self._exc_info[2]


class Configuration(object):
    """Various options that control content transformation process."""

    def __init__(
        self,
        inline_tag_names=None,
        opaque_tag_names=None,
        opaque_decomposable_tag_names=None,
        recomposable_attributes_map=None,
        omit_empty_opaque_decomposable=True,
        sort_attributes=False):

        if inline_tag_names is not None:
            self.inline_tag_names = inline_tag_names
        else:
            self.inline_tag_names = DEFAULT_INLINE_TAG_NAMES

        if opaque_tag_names is not None:
            self.opaque_tag_names = opaque_tag_names
        else:
            self.opaque_tag_names = DEFAULT_OPAQUE_TAG_NAMES

        if opaque_decomposable_tag_names is not None:
            self.opaque_decomposable_tag_names = opaque_decomposable_tag_names
        else:
            self.opaque_decomposable_tag_names = (
                DEFAULT_OPAQUE_DECOMPOSABLE_TAG_NAMES)

        if recomposable_attributes_map is not None:
            self.recomposable_attributes_map = recomposable_attributes_map
        else:
            self.recomposable_attributes_map = (
                DEFAULT_RECOMPOSABLE_ATTRIBUTES_MAP)

        self.omit_empty_opaque_decomposable = omit_empty_opaque_decomposable
        self.sort_attributes = sort_attributes


class Context(object):
    """Runtime state of the transformation process."""

    def __init__(self, tree):
        self.tree = ContentIO._normalize_tree(tree)
        self.collations = None
        self.index = None
        self.resource_bundle = None
        self.resource_bundle_index_2_collation_index = None
        self.append_to_index = None
        self.is_dirty = False

    def _get_collation_index(self, resource_bundle_index):
        return self.resource_bundle_index_2_collation_index[
            resource_bundle_index]

    def _remove_empty_collations(self):
        _collations = []
        for collation in self.collations:
            if collation:
                _collations.append(collation)
        self.collations = _collations

    def _new_collation(self):
        assert self.collations is not None
        if not self.collations or self.collations[-1]:
            self.collations.append([])
        self.append_to_index = len(self.collations) - 1

    def _append_collation(self, node):
        if not self.collations:
            self._new_collation()
        self.collations[self.append_to_index].append(node)


class CollationIndex(object):
    """An in-order index of all indexable nodes in the collation."""

    def __init__(self):
        self._node_to_index = {}

    def rebuild(self, context):
        for collation in context.collations:
            counter = 1
            for node in collation:
                if TranslationIO._is_indexable(node):
                    self._node_to_index[node] = counter
                    counter += 1
                else:
                    self._node_to_index[node] = None

    def get_node_index_in_collation(self, node):
        return self._node_to_index[node]

    def find_node_in_collation(self, collation, node_index):
        """Finds node that has a specific index in the collation."""
        for node in collation:
            if node_index == self.get_node_index_in_collation(node):
                return node
        return None

    @classmethod
    def get_all_indexes_in_collation(cls, context, collation):
        """Returns a set of all possible indexes of nodes in the collation."""
        all_indexes = set()
        for node in collation:
            if TranslationIO._is_indexable(node):
                all_indexes.add(context.index.get_node_index_in_collation(node))
        return all_indexes


class ContentTransformer(object):
    """Main class that performs content transformation."""

    def __init__(self, config=None):
        if config is None:
            config = Configuration()
        self.config = config

    def _collate_action_append(self, context, node):
        context._append_collation(node)

    def _collate_action_inspect_children(self, context, node):
        for child in ContentIO._get_children(node):
            action = self._get_collate_action(child)
            if action:
                action(context, child)

    def _collate_action_inspect_inline(self, context, node):
        if ContentIO._is_simple_text_content(node):
            self._collate_action_append(context, node)
        else:
            self._collate_action_inspect_composite(context, node)

    def _collate_action_inspect_opaque(self, context, node):
        context._append_collation(node)

    def _collate_action_inspect_opaque_decomposable(self, context, node):
        context._append_collation(node)
        _append_to_index = context.append_to_index
        context._new_collation()
        self._collate_action_inspect_children(context, node)
        context.append_to_index = _append_to_index

    def _collate_action_inspect_composite(self, context, node):
        context._new_collation()
        self._collate_action_inspect_children(context, node)
        context._new_collation()

    def _get_collate_action(self, node):
        if isinstance(node, safe_dom.NodeList):
            return self._collate_action_inspect_children
        if isinstance(node, safe_dom.Comment):
            if node.get_value().strip().find(I18N_COMMENT_PREFIX) == 0:
                return self._collate_action_append
            else:
                return None
        if isinstance(node, safe_dom.Text):
            return self._collate_action_append
        if isinstance(node, safe_dom.Element):
            tag_name = node.tag_name
            if tag_name.upper() in self.config.inline_tag_names:
                return self._collate_action_inspect_inline
            if tag_name.upper() in self.config.opaque_tag_names:
                return self._collate_action_inspect_opaque
            if tag_name.upper() in self.config.opaque_decomposable_tag_names:
                return self._collate_action_inspect_opaque_decomposable
            return self._collate_action_inspect_composite
        raise TypeError(
            'Unsupported node type: %s.' % node.__class__.__name__)

    @classmethod
    def _assert_all_indexed_elements_are_consumed(
        cls, context, target_collation, consumed_indexes):
        """Asserts all indexed nodes in the collation were consumed."""
        all_indexes = context.index.get_all_indexes_in_collation(
            context, target_collation)
        if consumed_indexes != all_indexes:
            missing_indexes = set(list(all_indexes))
            missing_indexes.difference_update(consumed_indexes)
            missing_tags = []
            for index in missing_indexes:
                missing_node = context.index.find_node_in_collation(
                    target_collation, index)
                missing_tags.append(TranslationIO.get_indexed_tag_name(
                    missing_node, index))
            raise LookupError(
                'Expected to find the following tags: <%s>.' % (
                    '>, <'.join(missing_tags)))

    @classmethod
    def _get_node_index(cls, node, node_list):
        node_index = None
        index = 0
        for child in node_list:
            if node == child:
                node_index = index
                break
            index += 1
        assert node_index is not None
        return node_index

    def _replace_children(self, tree, collation, children):
        """Replaces all nodes in the collation with the new nodes."""
        first_node = collation[0]
        parent = first_node.parent
        if not parent:
            parent = tree

        first_node_index = self._get_node_index(
            first_node, ContentIO._get_children(parent))

        new_children = []
        old_children = ContentIO._get_children(parent)
        for index in range(0, len(old_children)):
            if index == first_node_index:
                for new_child in children:
                    new_children.append(new_child)
            child = old_children[index]
            ignore = False
            for _child in collation:
                if TranslationIO._is_ancestor(_child, child):
                    ignore = True
                    break
            if not ignore:
                new_children.append(child)

        TranslationIO._set_children(parent, new_children)

    @classmethod
    def _copy_selected_node_attributes(
        cls, config, source_node, target_element):
        """Copy selected attributes from source to target."""
        for key in source_node.attributes.keys():
            tag_name_set = config.recomposable_attributes_map.get(
                key.upper())
            eligible = tag_name_set and (
                (source_node.tagName.upper() in tag_name_set) or (
                    '*' in tag_name_set))
            if eligible:
                if target_element.has_attribute(key):
                    target_element.set_attribute(
                        key, source_node.attributes[key].nodeValue)

    def _recompose(self, context, translation, collation_index):
        """Applies translation to the collation."""
        _tree = TranslationIO.fromstring(translation)
        consumed_indexes = set()
        collation = []
        for node in TranslationIO.tocollation(_tree):
            if node.nodeType == minidom.Node.TEXT_NODE:
                collation.append(safe_dom.Text(node.nodeValue))
                continue
            if node.nodeType == minidom.Node.COMMENT_NODE:
                collation.append(safe_dom.Comment(node.nodeValue))
                continue
            if node.nodeType == minidom.Node.ELEMENT_NODE:
                tag_name, index = TranslationIO.parse_indexed_tag_name(node)
                node.tagName = tag_name
                target_node = context.index.find_node_in_collation(
                    context.collations[collation_index], index)
                if not target_node:
                    raise LookupError(
                        'Unexpected tag: <%s#%s>.' % (tag_name, index))
                TranslationIO._copy_node_content_from_minidom_to_safe_dom(
                    node, target_node)
                self._copy_selected_node_attributes(
                    self.config, node, target_node)
                consumed_indexes.add(index)
                collation.append(target_node)
                continue
            raise TypeError('Unknown node type: %s.' % node)

        self._assert_all_indexed_elements_are_consumed(
            context, context.collations[collation_index], consumed_indexes)
        self._replace_children(
            context.tree, context.collations[collation_index], collation)

    def _collate(self, context):
        """Collates XML tree into lists of nodes containing chunks of text."""

        self._collate_action_inspect_children(context, context.tree)
        context._remove_empty_collations()
        context.index.rebuild(context)

    def decompose(self, context):
        """Creates a resource bundle from the collations of nodes."""
        context.collations = []
        context.index = CollationIndex()
        self._collate(context)

        _index = 0
        _collation_index = 0
        context.resource_bundle = []
        context.resource_bundle_index_2_collation_index = {}
        context.append_to_index = None
        for collation in context.collations:
            value = TranslationIO._collation_to_translation(
                self.config, context, collation)
            if value:
                context.resource_bundle.append(value)
                context.resource_bundle_index_2_collation_index[
                    _index] = _collation_index
                _index += 1
            _collation_index += 1

    def recompose(self, context, resource_bundle, errors=None):
        """Pushes string translations from resource bundle into the tree."""

        if context.is_dirty:
            raise AssertionError(
                'Please create new context; this context is not reusable.')

        if context.resource_bundle is None:
            raise Exception('Please call decompose() first.')

        if len(context.resource_bundle) != len(resource_bundle):
            raise IndexError(
                'The lists of translations must have the same number of items '
                '(%s) as extracted from the original content (%s).' % (
                        len(resource_bundle), len(context.resource_bundle)))

        if errors is None:
            errors = []

        context.is_dirty = True
        for index, item in enumerate(resource_bundle):
            try:
                self._recompose(
                    context, item,
                    context._get_collation_index(index))
            except Exception as e:  # pylint: disable=broad-except
                _error = ResourceBundleItemError(sys.exc_info(), e, index)
                errors.append(_error)

        if errors:
            errors[-1].reraise()


class SourceToTargetMapping(object):
    """Class that maps source to target."""

    def __init__(self, name, label, type_name, source_value, target_value):
        self._name = name
        self._label = label
        self._type = type_name
        self._source = source_value
        self._target = target_value

    def __str__(self):
        return '%s (%s): %s == %s' % (
            self._name, self._type, self._source, self._target)

    @property
    def name(self):
        return self._name

    @property
    def label(self):
        return self._label

    @property
    def source_value(self):
        return self._source

    @property
    def target_value(self):
        return self._target

    @property
    def type(self):
        return self._type

    @classmethod
    def find_mapping(cls, mappings, name):
        for mapping in mappings:
            if name == mapping.name:
                return mapping
        return None


class SourceToTargetDiffMapping(SourceToTargetMapping):
    """Class that maps source to target with diff."""

    VERB_NEW = 1  # new source value added, no mapping to target exists
    VERB_CHANGED = 2  # source value changed, mapping to target likely invalid
    VERB_CURRENT = 3  # source value is mapped to valid target value
    ALLOWED_VERBS = [VERB_NEW, VERB_CHANGED, VERB_CURRENT]

    SIMILARITY_CUTOFF = 0.5

    def __init__(
            self, name, label, type_name,
            source_value, target_value, verb,
            source_value_index, target_value_index):
        assert verb in self.ALLOWED_VERBS
        super(SourceToTargetDiffMapping, self).__init__(
            name, label, type_name, source_value, target_value)
        self._verb = verb
        self._source_value_index = source_value_index
        self._target_value_index = target_value_index

    def __str__(self):
        return '%s (%s, %s): %s | %s' % (
            self._name, self._type, self._verb, self._source, self._target)

    @property
    def verb(self):
        return self._verb

    @property
    def source_value_index(self):
        return self._source_value_index

    @property
    def target_value_index(self):
        return self._target_value_index

    @classmethod
    def _create_value_mapping(
            cls, field_value, source_value, target_value, verb,
            source_value_index, target_value_index):
        _name = None
        _label = None
        _type = None
        if field_value is not None:
            _name = field_value.name
            _label = field_value.field.label
            _type = field_value.field.type
        return SourceToTargetDiffMapping(
            _name, _label, _type,
            source_value, target_value, verb,
            source_value_index, target_value_index)

    @classmethod
    def map_lists_source_to_target(cls, a, b, allow_reorder=False):
        """Maps items from the source list to a target list."""
        return cls._map_lists_source_to_target_with_reorder(a, b) if (
            allow_reorder) else cls._map_lists_source_to_target_no_reorder(a, b)

    @classmethod
    def _map_lists_source_to_target_no_reorder(cls, a, b):
        mappings = []
        matcher = difflib.SequenceMatcher(None, a, b)
        for optcode in matcher.get_opcodes():
            tag, i1, i2, j1, j2 = optcode
            if 'insert' == tag:
                continue
            if 'replace' == tag:
                changed_len = min(i2 - i1, j2 - j1)
                for index in range(i1, i1 + changed_len):
                    entry = cls._create_value_mapping(
                        None, a[index], b[j1 + (index - i1)], cls.VERB_CHANGED,
                        index, j1 + (index - i1))
                    mappings.append(entry)
                for index in range(i1 + changed_len, i2):
                    entry = cls._create_value_mapping(
                        None, a[index], None, cls.VERB_NEW, index, None)
                    mappings.append(entry)
                continue
            for index in range(i1, i2):
                entry = None
                if 'equal' == tag:
                    assert (i2 - i1) == (j2 - j1)
                    entry = cls._create_value_mapping(
                        None, a[index], b[j1 + (index - i1)], cls.VERB_CURRENT,
                        index, j1 + (index - i1))
                elif 'delete' == tag:
                    entry = cls._create_value_mapping(
                        None, a[index], None, cls.VERB_NEW,
                        index, None)
                else:
                    raise KeyError()
                assert entry is not None
                mappings.append(entry)
        return mappings

    @classmethod
    def _map_lists_source_to_target_with_reorder(cls, a, b):
        mappings = []
        for new_index, _new in enumerate(a):
            best_match_index = None
            best_score = -1
            entry = None
            for old_index, _old in enumerate(b):
                if _new == _old:
                    entry = cls._create_value_mapping(
                        None,
                        a[new_index], b[old_index], cls.VERB_CURRENT,
                        new_index, old_index)
                    break
                score = difflib.SequenceMatcher(None, _new, _old).quick_ratio()
                if score > best_score:
                    best_score = score
                    best_match_index = old_index
            if entry:
                mappings.append(entry)
                continue
            if best_score > cls.SIMILARITY_CUTOFF:
                entry = cls._create_value_mapping(
                    None, a[new_index], b[best_match_index], cls.VERB_CHANGED,
                    new_index, best_match_index)
            else:
                entry = cls._create_value_mapping(
                    None, a[new_index], None, cls.VERB_NEW,
                    new_index, None)
            assert entry is not None
            mappings.append(entry)
        return mappings

    @classmethod
    def map_source_to_target(
        cls, binding,
        existing_mappings=None, allowed_names=None, allow_list_reorder=False,
        errors=None):
        """Maps binding field value to the existing SourceToTargetMapping.

        Args:
            binding: an instance of ValueToTypeBinding object
            existing_mappings: an array of SourceToTargetMapping holding
              existing translations
            allowed_names: field names that are subject to mapping
            allow_list_reorder: controls whether list items can be reordered
              while looking for better matching
            errors: an array to receive errors found during mapping process
        Returns:
            an array of SourceToTargetDiffMapping objects, one per each field
            value in the binding passed in
        """
        name_to_mapping = {}
        if existing_mappings is not None:
            for mapping in existing_mappings:
                name_to_mapping[mapping.name] = mapping
        mapping = []
        if allow_list_reorder:
            raise NotImplementedError()
        for index, field_value in enumerate(binding.value_list):
            if allowed_names is not None and (
                field_value.name not in allowed_names):
                continue
            target_value = None
            verb = cls.VERB_NEW
            translation = name_to_mapping.get(field_value.name)
            if translation:
                if translation.type != field_value.field.type:
                    _error = AssertionError(
                        'Source and target types don\'t match: %s, %s.' % (
                            field_value.field.type, translation.type))
                    if errors is not None:
                        _error = ResourceBundleItemError(
                            sys.exc_info(), _error, index)
                        errors.append(_error)
                        continue
                    else:
                        raise _error
                target_value = translation.target_value
                if translation.source_value != field_value.value:
                    verb = cls.VERB_CHANGED
                else:
                    verb = cls.VERB_CURRENT
            source_value = field_value.value
            entry = cls._create_value_mapping(
                field_value, source_value, target_value, verb, None, None)
            mapping.append(entry)
        return mapping


def extract_resource_bundle_from(
    tree=None, html=None, context=None, config=None):
    """Extracts resource bundle from the HTML string of tree.

    Args:
        tree: an XML tree of HTML content to use; required if content is None
        html: a string with HTML content to use; required if tree is None
        context: translation context
        config: configuration options
    Returns:
        a (context, transformer) tuple.
    """
    if config is None:
        config = Configuration()
    transformer = ContentTransformer(config=config)
    if tree is None and html is not None:
        tree = ContentIO.fromstring(html)

    context = Context(tree)
    transformer.decompose(context)
    return context, transformer


def merge_resource_bundle_into(
    tree=None, html=None, context=None, config=None, resource_bundle=None,
    errors=None):
    """Weaves strings from the resource bundle into the content.

    Args:
        tree: an XML tree of HTML content to use; required if content is None
        html: a string with HTML content to use; required if tree is None
        context: translation context
        config: configuration options
        resource_bundle: a list of strings containing translations in the same
          order and in the same quality that a list of strings in the resource
          bundle returned by extract_resource_bundle_from()
        errors: a list to receive errors
    Returns:
        a (context, transformer) tuple.
    """
    context, transformer = extract_resource_bundle_from(
        tree=tree, html=html, context=context, config=config)
    transformer.recompose(context, resource_bundle, errors=errors)
    return context, transformer


class ListsDifflibTests(unittest.TestCase):
    """Tests our understanding of difflib as applied to ordered lists."""

    def test_diff_two_string_lists_works(self):
        newest = ['The', 'sky', 'is', 'blue', '!']
        oldest = ['The', 'sky', 'was', 'blue', '!']
        matcher = difflib.SequenceMatcher(None, newest, oldest)
        expected_verbs = ['equal', 'replace', 'equal']
        for index, optcode in enumerate(matcher.get_opcodes()):
            tag, _, _, _, _ = optcode
            self.assertEqual(expected_verbs[index], tag)

    def test_diff_two_string_lists_no_reorder(self):
        newest = ['The', 'sky', 'is', 'blue', '!']
        oldest = ['The', 'is', 'sky', 'blue', '!']
        matcher = difflib.SequenceMatcher(None, newest, oldest)
        expected_verbs = ['equal', 'insert', 'equal', 'delete', 'equal']
        for index, optcode in enumerate(matcher.get_opcodes()):
            tag, _, _, _, _ = optcode
            self.assertEqual(expected_verbs[index], tag)

    def test_map_lists_source_to_target_identity(self):
        newest = ['The', 'sky', 'is', 'blue', '!']
        oldest = ['The', 'sky', 'is', 'blue', '!']
        mappings = SourceToTargetDiffMapping.map_lists_source_to_target(
            newest, oldest)
        expected_mappings = [
            ('The', 'The', SourceToTargetDiffMapping.VERB_CURRENT, 0, 0),
            ('sky', 'sky', SourceToTargetDiffMapping.VERB_CURRENT, 1, 1),
            ('is', 'is', SourceToTargetDiffMapping.VERB_CURRENT, 2, 2),
            ('blue', 'blue', SourceToTargetDiffMapping.VERB_CURRENT, 3, 3),
            ('!', '!', SourceToTargetDiffMapping.VERB_CURRENT, 4, 4)]
        self.assertEqual(
            expected_mappings, [(
                mapping.source_value, mapping.target_value,
                mapping.verb,
                mapping.source_value_index, mapping.target_value_index
            ) for mapping in mappings])

    def test_map_lists_source_to_target_no_reorder_but_changed(self):
        newest = ['The', 'sky', 'is', 'blue', '!']
        oldest = ['The', 'sky', 'was', 'blue', '!']
        mappings = SourceToTargetDiffMapping.map_lists_source_to_target(
            newest, oldest)
        expected_mappings = [
            ('The', 'The', SourceToTargetDiffMapping.VERB_CURRENT, 0, 0),
            ('sky', 'sky', SourceToTargetDiffMapping.VERB_CURRENT, 1, 1),
            ('is', 'was', SourceToTargetDiffMapping.VERB_CHANGED, 2, 2),
            ('blue', 'blue', SourceToTargetDiffMapping.VERB_CURRENT, 3, 3),
            ('!', '!', SourceToTargetDiffMapping.VERB_CURRENT, 4, 4)]
        self.assertEqual(
            expected_mappings, [(
                mapping.source_value, mapping.target_value,
                mapping.verb,
                mapping.source_value_index, mapping.target_value_index
            ) for mapping in mappings])

    def test_map_lists_source_to_target_no_reorder_and_remove_insert(self):
        newest = ['The', 'sky', 'is', 'blue', '!']
        oldest = ['The', 'is', 'sky', 'blue', '!']
        mappings = SourceToTargetDiffMapping.map_lists_source_to_target(
            newest, oldest)
        expected_mappings = [
            ('The', 'The', SourceToTargetDiffMapping.VERB_CURRENT, 0, 0),
            ('sky', 'sky', SourceToTargetDiffMapping.VERB_CURRENT, 1, 2),
            ('is', None, SourceToTargetDiffMapping.VERB_NEW, 2, None),
            ('blue', 'blue', SourceToTargetDiffMapping.VERB_CURRENT, 3, 3),
            ('!', '!', SourceToTargetDiffMapping.VERB_CURRENT, 4, 4)]
        self.assertEqual(
            expected_mappings, [(
                mapping.source_value, mapping.target_value,
                mapping.verb,
                mapping.source_value_index, mapping.target_value_index
            ) for mapping in mappings])

    def test_map_lists_source_to_target_no_reorder_and_new(self):
        newest = ['The', 'sky', 'is', 'blue', '!']
        oldest = ['The', 'sky', 'blue', '!']
        mappings = SourceToTargetDiffMapping.map_lists_source_to_target(
            newest, oldest)
        expected_mappings = [
            ('The', 'The', SourceToTargetDiffMapping.VERB_CURRENT, 0, 0),
            ('sky', 'sky', SourceToTargetDiffMapping.VERB_CURRENT, 1, 1),
            ('is', None, SourceToTargetDiffMapping.VERB_NEW, 2, None),
            ('blue', 'blue', SourceToTargetDiffMapping.VERB_CURRENT, 3, 2),
            ('!', '!', SourceToTargetDiffMapping.VERB_CURRENT, 4, 3)]
        self.assertEqual(
            expected_mappings, [(
                mapping.source_value, mapping.target_value,
                mapping.verb,
                mapping.source_value_index, mapping.target_value_index
            ) for mapping in mappings])

    def test_map_lists_source_to_target_no_reorder_change_and_new(self):
        newest = ['The', 'sky', 'is', 'blue', '!']
        oldest = ['The', 'sky', 'is', 'BLUE']
        mappings = SourceToTargetDiffMapping.map_lists_source_to_target(
            newest, oldest)
        expected_mappings = [
            ('The', 'The', SourceToTargetDiffMapping.VERB_CURRENT, 0, 0),
            ('sky', 'sky', SourceToTargetDiffMapping.VERB_CURRENT, 1, 1),
            ('is', 'is', SourceToTargetDiffMapping.VERB_CURRENT, 2, 2),
            ('blue', 'BLUE', SourceToTargetDiffMapping.VERB_CHANGED, 3, 3),
            ('!', None, SourceToTargetDiffMapping.VERB_NEW, 4, None)]
        self.assertEqual(
            expected_mappings, [(
                mapping.source_value, mapping.target_value,
                mapping.verb,
                mapping.source_value_index, mapping.target_value_index
            ) for mapping in mappings])


class SetsDifflibUtils(unittest.TestCase):
    """Tests our understanding of difflib as applied to lists and sets."""

    def test_diff_two_string_lists_with_reorder(self):
        newest = ['The', 'sky', 'is', 'blue', '!']
        oldest = ['The', 'is', 'sky', 'blue', '!']
        mappings = SourceToTargetDiffMapping.map_lists_source_to_target(
            newest, oldest, allow_reorder=True)
        expected_mappings = [
            ('The', 'The', SourceToTargetDiffMapping.VERB_CURRENT, 0, 0),
            ('sky', 'sky', SourceToTargetDiffMapping.VERB_CURRENT, 1, 2),
            ('is', 'is', SourceToTargetDiffMapping.VERB_CURRENT, 2, 1),
            ('blue', 'blue', SourceToTargetDiffMapping.VERB_CURRENT, 3, 3),
            ('!', '!', SourceToTargetDiffMapping.VERB_CURRENT, 4, 4)]
        self.assertEqual(
            expected_mappings, [(
                mapping.source_value, mapping.target_value,
                mapping.verb,
                mapping.source_value_index, mapping.target_value_index
            ) for mapping in mappings])

    def test_diff_two_string_lists_with_reorder_over_cutoff(self):
        newest = ['The', 'sky', 'is', 'blue', '!']
        oldest = ['The', 'sky', 'is', 'blUe', '!']
        mappings = SourceToTargetDiffMapping.map_lists_source_to_target(
            newest, oldest, allow_reorder=True)
        expected_mappings = [
            ('The', 'The', SourceToTargetDiffMapping.VERB_CURRENT, 0, 0),
            ('sky', 'sky', SourceToTargetDiffMapping.VERB_CURRENT, 1, 1),
            ('is', 'is', SourceToTargetDiffMapping.VERB_CURRENT, 2, 2),
            ('blue', 'blUe', SourceToTargetDiffMapping.VERB_CHANGED, 3, 3),
            ('!', '!', SourceToTargetDiffMapping.VERB_CURRENT, 4, 4)]
        self.assertEqual(
            expected_mappings, [(
                mapping.source_value, mapping.target_value,
                mapping.verb,
                mapping.source_value_index, mapping.target_value_index
            ) for mapping in mappings])

    def test_diff_two_string_lists_with_reorder_under_cutoff(self):
        newest = ['The', 'sky', 'is', 'blue', '!']
        oldest = ['The', 'sky', 'is', 'BLUE', '!']
        mappings = SourceToTargetDiffMapping.map_lists_source_to_target(
            newest, oldest, allow_reorder=True)
        expected_mappings = [
            ('The', 'The', SourceToTargetDiffMapping.VERB_CURRENT, 0, 0),
            ('sky', 'sky', SourceToTargetDiffMapping.VERB_CURRENT, 1, 1),
            ('is', 'is', SourceToTargetDiffMapping.VERB_CURRENT, 2, 2),
            ('blue', None, SourceToTargetDiffMapping.VERB_NEW, 3, None),
            ('!', '!', SourceToTargetDiffMapping.VERB_CURRENT, 4, 4)]
        self.assertEqual(
            expected_mappings, [(
                mapping.source_value, mapping.target_value,
                mapping.verb,
                mapping.source_value_index, mapping.target_value_index
            ) for mapping in mappings])


class TestCasesForIO(unittest.TestCase):
    """Tests for content/translation input/output."""

    def _containers(self):
        return [safe_dom.A('http://'), safe_dom.Element('div')]

    def _leafs(self):
        return [
            safe_dom.Comment('comment'),
            safe_dom.Entity('&gt;'),
            safe_dom.Text('text'),
            safe_dom.ScriptElement()]

    def _all(self):
        return [] + self._containers() + self._leafs()

    def test_merge_single_element(self):
        for _elem in self._all():
            _result = safe_dom.NodeList()
            ContentIO._merge_node_lists(_result, _elem)
            self.assertEqual(_result.list, [_elem])

    def test_merge_stack_of_node_lists_leaf_element(self):
        for _elem in self._all():
            _list1 = safe_dom.NodeList()
            _list2 = safe_dom.NodeList()
            _list3 = safe_dom.NodeList()

            _list1.append(_list2)
            _list2.append(_list3)
            _list3.append(_elem)
            self.assertEqual(_list1.list, [_list2])
            self.assertEqual(_list2.list, [_list3])
            self.assertEqual(_list3.list, [_elem])

            _result = safe_dom.NodeList()
            ContentIO._merge_node_lists(_result, _list1)
            self.assertEqual(_result.list, [_elem])

    def test_merge_stack_of_node_lists_non_leaf_element(self):
        for _bar in self._containers():
            for _foo in self._all():
                _bar.empty()

                _list1 = safe_dom.NodeList()
                _list2 = safe_dom.NodeList()
                _list3 = safe_dom.NodeList()

                _bar.add_child(_list1)
                _list1.append(_list2)
                _list2.append(_list3)
                _list3.append(_foo)
                self.assertEqual(_list1.list, [_list2])
                self.assertEqual(_list2.list, [_list3])
                self.assertEqual(_list3.list, [_foo])

                _result = safe_dom.NodeList()
                ContentIO._merge_node_lists(_result, _bar)
                self.assertEqual(_result.list, [_bar])
                self.assertEqual(
                    _bar.children[0].list, [_foo],
                    '%s >>> %s' % (_bar, _foo))

    def test_merge_sibling_node_lists_leaf_element(self):
        for _bar in self._all():
            for _foo in self._all():
                _list1 = safe_dom.NodeList()
                _list2 = safe_dom.NodeList()
                _list3 = safe_dom.NodeList()

                _list1.append(_list2)
                _list1.append(_list3)
                _list2.append(_foo)
                _list3.append(_bar)
                self.assertEqual(_list1.list, [_list2, _list3])
                self.assertEqual(_list2.list, [_foo])
                self.assertEqual(_list3.list, [_bar])

                _result = safe_dom.NodeList()
                ContentIO._merge_node_lists(_result, _list1)
                self.assertEqual(_result.list, [_foo, _bar])

    def test_merge_stack_and_sibling_lists(self):
        for _elem in self._containers():
            _list1 = safe_dom.NodeList()
            _list2 = safe_dom.NodeList()
            _list3 = safe_dom.NodeList()
            _list4 = safe_dom.NodeList()

            _list1.append(_list2)
            _list2.append(_elem)
            _elem.add_child(_list3)
            _list3.append(_list4)

            self.assertEqual(_elem.children, [_list3])
            self.assertEqual(_list3.list, [_list4])

            _result = safe_dom.NodeList()
            ContentIO._merge_node_lists(_result, _list1)
            self.assertEqual(_result.list, [_elem])
            self.assertEqual(_elem.children, [])

    def test_translation_to_minidom(self):
        translation = 'The <a#1 href="foo">skies</a#1> are <b#2>blue</b#2>.'
        tree_as_text = 'The <a-1 href="foo">skies</a-1> are <b-2>blue</b-2>.'
        dom = TranslationIO.fromstring(translation)
        self.assertEqual(tree_as_text, TranslationIO.toxml(dom))
        self.assertEqual(translation, TranslationIO.tostring(dom))

    def test_minidom_is_casesensitive(self):
        translation = 'The <SPAN#1>skies</SPAN#1>.'
        TranslationIO.fromstring(translation)

        translation = 'The <span#1>skies</SPAN#1>.'
        with self.assertRaises(Exception):
            TranslationIO.fromstring(translation)
        translation = 'The <SPAN#1>skies</span#1>.'
        with self.assertRaises(Exception):
            TranslationIO.fromstring(translation)

    def test_fromstring_translates_html_entities_for_minidom(self):
        original = u'The skies&reg; are &copy; copyrighted.'
        parsed = u'The skies\xae are \xa9 copyrighted.'
        dom = TranslationIO.fromstring(original)
        self.assertEqual(parsed, TranslationIO.toxml(dom))
        self.assertEqual(parsed, TranslationIO.tostring(dom))

    def test_fromstring_does_not_translate_xml_entities_for_minidom(self):
        original = u'Hello, &quot; &amp; &lt; &gt; &apos; world.'
        dom = TranslationIO.fromstring(original)
        # We leave &apos; as &apos, but minidom turns it to '.
        self.assertEqual(
            u"Hello, &quot; &amp; &lt; &gt; ' world.",
            TranslationIO.toxml(dom))
        self.assertEqual(
            u"Hello, &quot; &amp; &lt; &gt; ' world.",
            TranslationIO.tostring(dom))

    def test_entity_map_converts_all_html_codes_to_base_10_ascii(self):
        for name, code in _ENTITY_MAP.iteritems():
            if name not in _XML_ENTITY_NAMES:
                int(code[2:-1], base=10)
                self.assertTrue(code.startswith('&') and code.endswith(';'))

        # Spot check a few values.
        self.assertEqual('&#169;', _ENTITY_MAP.get('copy'))
        self.assertEqual('&#174;', _ENTITY_MAP.get('reg'))

    def test_entity_map_xml_entity_values_are_keynames_with_amp_and_semi(self):
        for xml_entity in _XML_ENTITY_NAMES:
            self.assertEqual('&%s;' % xml_entity, _ENTITY_MAP.get(xml_entity))

    def test_html_to_safedom(self):
        html = '''
            Let's start!
            <p>First!</>
            Some random <b>markup</b> text!
            <p>
                <!-- comment -->
                The <b>skies</b> are <a href="foo">blue</a>.
                The <b>roses</b> are <a href="bar">red</a>!
                <script>alert('Foo!');</script>
                <style>{ width: 100%; }</style>
            </p>
            <p>Last!</p>
            We are done!
            '''
        tree_as_text = '''
            Let&#39;s start!
            <p>First!
            Some random <b>markup</b> text!
            </p><p>
                <!-- comment -->
                The <b>skies</b> are <a href="foo">blue</a>.
                The <b>roses</b> are <a href="bar">red</a>!
                <script>alert('Foo!');</script>
                <style>{ width: 100%; }</style>
            </p>
            <p>Last!</p>
            We are done!
            '''
        self.assertEqual(
            tree_as_text,
            ContentIO.tostring(ContentIO.fromstring(html)))

    def test_parse_error_interpretation(self):
        # test expected error message
        error = Exception('not well-formed (invalid token): line 66, column 99')
        line_num, col_num = TranslationIO.extract_line_column_from_parse_error(
            error)
        self.assertEquals(66, line_num)
        self.assertEquals(99, col_num)

        # test text that does not have line & column
        self.assertEquals(
            (None, None),
            TranslationIO.extract_line_column_from_parse_error('Some text.'))

        # test clipping
        text = 'The sky is blue!'
        self.assertEquals(
            '[T]he s',
            TranslationIO.get_text_fragment(text, 1, 0, clip_len=5))
        self.assertEquals(
            'The s[k]y is',
            TranslationIO.get_text_fragment(text, 1, 5, clip_len=5))

        # text out of bounds conditions
        self.assertEquals(
            text,
            TranslationIO.get_text_fragment(text, 1, 16, clip_len=5))
        self.assertEquals(
            text, TranslationIO.get_text_fragment(text, 1, 99))
        self.assertEquals(
            text, TranslationIO.get_text_fragment(text, 1, -1))
        self.assertEquals(text, TranslationIO.get_text_fragment(text, -1, -1))


class TestCasesBase(unittest.TestCase):
    """Base class for testing translations."""

    def setUp(self):
        self.transformer = ContentTransformer()

    def tearDown(self):
        self.tree = None
        self.transformer = None
        self.context = None

    @classmethod
    def _remove_whitespace(cls, content):
        content = content.replace('\n', ' ').replace('\r', ' ')
        content = re.sub(r'\s+', ' ', content)
        content = re.sub(r'>\s+', '>', content)
        content = re.sub(r'\s+/>', '/>', content)
        content = re.sub(r'\s+<', '<', content)
        return content.strip()

    def _assert_collated_nodes_have_same_parent(self, collation):
        parent = None
        for node in collation:
            if parent is None:
                parent = node.parent
            assert parent == node.parent

    def _assert_decomposes(
        self, content, resource_bundle, ignore_whitespace=True):
        self.context = Context(ContentIO.fromstring(content))
        self.transformer.decompose(self.context)

        for collation in self.context.collations:
            self._assert_collated_nodes_have_same_parent(collation)

        if resource_bundle is not None:
            self.assertEqual(
                len(resource_bundle), len(self.context.resource_bundle))
            for index, _ in enumerate(resource_bundle):
                if ignore_whitespace:
                    self.assertEqual(
                        self._remove_whitespace(resource_bundle[index]),
                        self._remove_whitespace(
                            self.context.resource_bundle[index]))
                else:
                    self.assertEqual(
                        resource_bundle[index],
                        self.context.resource_bundle[index])

        if not self.context.resource_bundle:
            self.assertEqual(
                {},
                self.context.resource_bundle_index_2_collation_index)

    def _assert_recomposes(self, resource_bundle, result):
        self.transformer.recompose(self.context, resource_bundle)
        self.assertEqual(
            self._remove_whitespace(result),
            self._remove_whitespace(ContentIO.tostring(self.context.tree)))

    def _assert_recomposes_error(self, resource_bundle):
        failed = True
        result = None
        try:
            errors = []
            self.transformer.recompose(
                self.context, resource_bundle, errors=errors)
            failed = False
        except Exception as e:  # pylint: disable=broad-except
            if errors:
                return errors[0]
            return e
        if not failed:
            raise Exception('Expected to fail.' % ContentIO.tostring(
                result) if result else None)


class TestCasesForContentDecompose(TestCasesBase):
    """Tests for content decomposition phase."""

    def test_i18n_comment_is_preserved(self):
        original = 'Hello <!-- I18N: special comment -->world!'
        expected = ['Hello <!-- I18N: special comment -->world!']
        self._assert_decomposes(original, expected)
        return original

    def test_i18n_non_comment_is_removed(self):
        original = 'Hello <!-- just a comment -->world!'
        self._assert_decomposes(original, ['Hello world!'])

    def test_extract_simple_value_no_markup(self):
        original = 'The skies are blue.'
        expected = ['The skies are blue.']
        self._assert_decomposes(original, expected)

    def test_extract_simple_value_with_br(self):
        original = 'The skies are <br />blue.'
        expected = ['The skies are <br#1 />blue.']
        self._assert_decomposes(original, expected)

    def test_extract_value_with_inline(self):
        html = 'The <a href="foo">sky</a> is blue.'
        expected = ['The <a#1>sky</a#1> is blue.']
        self._assert_decomposes(html, expected)

    def test_extract_value_with_nested_inline(self):
        html = 'The <a href="foo"><b>ocean</b> liner</a> is blue.'
        expected = ['The', '<b#1>ocean</b#1> liner', 'is blue.']
        self._assert_decomposes(html, expected)

    def test_extract_simple_value_with_only_non_ascii_no_markup(self):
        original = u'<p>Трава зеленая.</p>'
        expected = [u'Трава зеленая.']
        self._assert_decomposes(original, expected)

    def test_extract_simple_value_with_only_non_ascii_and_markup(self):
        original = u'Трава <b>зеленая</b>.'
        expected = [u'Трава <b#1>зеленая</b#1>.']
        self._assert_decomposes(original, expected)

    def test_extract_simple_value_with_entity(self):
        original = 'The skies &lt; are blue.'
        expected = ['The skies &lt; are blue.']
        self._assert_decomposes(original, expected)

    def test_extract_simple_value_with_entity_2(self):
        original = '''Let's start!'''
        expected = ['Let&#39;s start!']
        self._assert_decomposes(original, expected)

    def test_extract_nothing_to_translate(self):
        original = '\n\n <script>alert("Foo!");</script>\n\n   '
        self._assert_decomposes(original, [])

    def test_extract_nothing_to_translate_2(self):
        original = '\n\n <a href="#foo" />\n\n   '
        self._assert_decomposes(original, [])

    def test_extract_script_value(self):
        original = 'The skies <script>alert("Foo!");</script> are blue.'
        expected = ['The skies <script#1 /> are blue.']
        self._assert_decomposes(original, expected)

        config = Configuration(opaque_tag_names=[])
        self.transformer = ContentTransformer(config=config)
        original = 'The skies <script>alert("Foo!");</script> are blue.'
        expected = ['The skies', 'alert("Foo!");', 'are blue.']
        self._assert_decomposes(original, expected)

    def test_extract_script_and_style_value(self):
        original = (
            'The skies <script>alert("Foo!");</script> are '
            '<style> { color: blue; } </style> blue.')
        expected = ['The skies <script#1 /> are <style#2 /> blue.']
        self._assert_decomposes(original, expected)

    def test_extract_one_complex_value(self):
        html = '''begin
            <p>
                The <a href='foo'>skies</a> are <a href="bar">blue</a>.
            </p>
            end'''
        expected = ['begin', 'The <a#1>skies</a#1> are <a#2>blue</a#2>.', 'end']
        self._assert_decomposes(html, expected)
        self.assertEqual(
            {0: 0, 1: 1, 2: 2},
            self.context.resource_bundle_index_2_collation_index)

    def test_resource_bundle_to_collation_mapping(self):
        html = '''


            <p>
                The <a href='foo'>skies</a> are <a href="bar">blue</a>.
            </p>


            '''
        expected = ['The <a#1>skies</a#1> are <a#2>blue</a#2>.']
        self._assert_decomposes(html, expected)
        self.assertEqual(3, len(self.context.collations))
        self.assertEqual(
            {0: 1},
            self.context.resource_bundle_index_2_collation_index)

    def test_extract_many_complex_values(self):
        html = '''begin
            <p>
                The <a href="foo">skies</a> are <a href="bar">blue</a>.
            </p>
            followed by more <a href="baz">text</a> with markup
            <p>
                The <span class="red">roses</span> are <a href="y">red</a>.
            </p>
            end'''
        expected = [
            'begin',
            'The <a#1>skies</a#1> are <a#2>blue</a#2>.',
            'followed by more <a#1>text</a#1> with markup',
            'The <span#1>roses</span#1> are <a#2>red</a#2>.',
            'end']
        self._assert_decomposes(html, expected)

    def test_extract_complex_value_with_unicode(self):
        original = u'''
            begin
            <p>
                The <b>skies</b> are <a href="foo">blue</a>.
                <p>Трава <b>зеленая</b>.</p>
                The <b>roses</b> are <a href="bar">red</a>!
            </p>
            end
            '''
        expected = [
            'begin',
            'The <b#1>skies</b#1> are <a#2>blue</a#2>.',
            u'Трава <b#1>зеленая</b#1>.',
            'The <b#1>roses</b#1> are <a#2>red</a#2>!',
            'end'
            ]
        self._assert_decomposes(original, expected)

    def test_extract_ul_value(self):
        original = '''
            Start!
            <ul>
                The skies are <li>blue</li> and <li>red</li>.
            </ul>
            Done!
            '''
        expected = [
            'Start!\n            <ul#1 />\n            Done!',
            'The skies are',
            'blue',
            'and',
            'red',
            '.']
        self._assert_decomposes(original, expected)

    def test_extract_nested_elements(self):
        original = '''
            <p>
                The skies can be:
                    <ul>
                        <li>red</li>
                        <li>blue</li>
                    </ul>
                in the fall.
            </p>
            '''
        # TODO(psimakov): undesirable, but the parser closes <p> before new <ul>
        expected = [
            'The skies can be:',
            '<ul#1 />\n                in the fall.',
            'red',
            'blue']
        self._assert_decomposes(original, expected)

    def test_extract_decompose_can_be_called_many_times(self):
        html = 'The <a href="foo">sky</a> is blue.'
        expected = ['The <a#1>sky</a#1> is blue.']
        self._assert_decomposes(html, expected)
        self._assert_decomposes(html, expected)
        self._assert_decomposes(html, expected)

    def test_extract_decompose_opaque_translatable(self):
        config = Configuration(
            omit_empty_opaque_decomposable=False,
            sort_attributes=True)
        self.transformer = ContentTransformer(config)
        html = '<img src="foo" />'
        expected = ['<img#1 src="foo" />']
        self._assert_decomposes(html, expected)

        html = '<img src="foo" alt="bar"/>'
        expected = ['<img#1 alt="bar" src="foo" />']
        self._assert_decomposes(html, expected)

        html = '<img alt="bar" src="foo" />'
        expected = ['<img#1 alt="bar" src="foo" />']
        self._assert_decomposes(html, expected)

        html = '<img alt="bar" src="foo" title="baz"/>'
        expected = ['<img#1 alt="bar" src="foo" title="baz" />']
        self._assert_decomposes(html, expected)

        html = '<img src="foo" alt="bar" title="baz"/>'
        expected = ['<img#1 alt="bar" src="foo" title="baz" />']
        self._assert_decomposes(html, expected)

    def test_extract_decompose_custom_tag_with_attribute(self):
        config = Configuration(
            inline_tag_names=['FOO'],
            opaque_decomposable_tag_names=['FOO'],
            omit_empty_opaque_decomposable=False)
        self.transformer = ContentTransformer(config)

        html = '<div><foo alt="bar"></foo></div>'
        expected = ['<foo#1 alt="bar" />']
        self._assert_decomposes(html, expected)

        html = '<div><foo alt="bar">baz</foo></div>'
        expected = ['<foo#1 alt="bar">baz</foo#1>']
        self._assert_decomposes(html, expected)

    def test_extract_large_sample_document(self):
        self.maxDiff = None
        original = ContentIO.tostring(ContentIO.fromstring(
            SAMPLE_HTML_DOC_CONTENT))
        self._assert_decomposes(original, SAMPLE_HTML_DOC_DECOMPOSE)

    def test_extract_resource_bundle_from(self):
        original = '<p>The <a href="foo">skies</a> are blue!</p>'
        expected = ['The <a#1>skies</a#1> are blue!']
        context, _ = extract_resource_bundle_from(html=original)
        self.assertEqual(expected, context.resource_bundle)


class TestCasesForContentRecompose(TestCasesBase):
    """Tests for content decomposition phase."""

    def test_recompose_i18n_comment_is_preserved(self):
        html = 'Hello <!-- I18N: special comment -->world!'
        self._assert_decomposes(html, None)
        translations = ['HELLO <!-- I18N: special comment -->WORLD!']
        result = 'HELLO <!-- I18N: special comment -->WORLD!'
        self._assert_recomposes(translations, result)

    def test_recompose_one_complex_value(self):
        html = '''begin
            <p>
                The <a href="foo">skies</a> are <a href="bar">blue</a>.
            </p>
            end'''
        self._assert_decomposes(html, None)
        translations = [
            'BEGIN', 'The <a#1>SKIES</a#1> ARE <a#2>BLUE</a#2>.', 'END']
        result = '''BEGIN
            <p>
                The <a href="foo">SKIES</a> ARE <a href="bar">BLUE</a>.
            </p>
            END'''
        self._assert_recomposes(translations, result)

    def test_recompose_complex_value_mixed_tags(self):
        html = '''
            Start!
            <p>
                The <b>skies</b> are <a href="foo">blue</a>.
                The <b>roses</b> are <a href="bar">red</a>!
            </p>
            Done!
            '''
        expected = [
            'Start!',
            '''The <b#1>skies</b#1> are <a#2>blue</a#2>.
                The <b#3>roses</b#3> are <a#4>red</a#4>!''',
            'Done!']
        self._assert_decomposes(html, expected)

        translations = [
            'START!',
            '''The <b#1>SKIES</b#1> ARE <a#2>BLUE</a#2>.
                The <b#3>roses</b#3> ARE <a#4>RED</a#4>!''',
            'DONE!']
        result = '''START!<p>The <b>SKIES</b> ARE <a href="foo">BLUE</a>.
                The <b>roses</b> ARE <a href="bar">RED</a>!</p>DONE!'''
        self._assert_recomposes(translations, result)

    def test_recompose_multiple_complex_values_with_mixed_tags(self):
        html = '''
            Start!
            <p>
                The <b>skies</b> are <a href="foo">blue</a>.
            </p>
            <p>
                The <b>roses</b> are <a href="bar">red</a>!
            </p>
            Done!
            '''
        expected = [
            'Start!',
            'The <b#1>skies</b#1> are <a#2>blue</a#2>.',
            'The <b#1>roses</b#1> are <a#2>red</a#2>!',
            'Done!']
        self._assert_decomposes(html, expected)

        translations = [
            'START!',
            'The <b#1>SKIES</b#1> ARE <a#2>blue</a#2>.',
            'THE <b#1>roses</b#1> are <a#2>RED</a#2>!',
            'DONE!']
        result = (
            'START!'
            '<p>The <b>SKIES</b> ARE <a href="foo">blue</a>.</p>'
            '<p>THE <b>roses</b> are <a href="bar">RED</a>!</p>'
            'DONE!')
        self._assert_recomposes(translations, result)

    def test_recompose_complex_value(self):
        html = """
              <h1>
                <a href="/">
                  <img alt="Google"
                    src="//www.google.com/images/logos/google_logo_41.png">
                Open Online Education</a>
              </h1>
              <a class="maia-teleport" href="#content">Skip to content</a>
            """
        expected = [
            '<img#1 src="//www.google.com/images/logos/google_logo_41.png" '
            'alt="Google" />\n                Open Online Education',
            '<a#1>Skip to content</a#1>']
        self._assert_decomposes(html, expected)
        translations = [
            '<img#1 src="//www.google.com/images/logos/google_logo_99.png" '
            'alt="Google+" />\n                Open ONLINE Education',
            '<a#1>SKIP to content</a#1>']
        result = """
              <h1>
                <a href="/">
                  <img alt="Google+"
                    src="//www.google.com/images/logos/google_logo_99.png" />
                Open ONLINE Education</a>
              </h1>
              <a class="maia-teleport" href="#content">SKIP to content</a>
            """
        self._assert_recomposes(translations, result)

    def test_recompose_complex_value_2(self):
        html = (
            'The <a class="foo">skies</a> '
            '<p>are <i>not</i></p>'
            ' always <a href="bar">blue</a>.')
        expected = [
            'The <a#1>skies</a#1>',
            'are <i#1>not</i#1>',
            'always <a#1>blue</a#1>.']
        self._assert_decomposes(html, expected)
        translations = [
            'The <a#1>SKIES</a#1> ',
            'ARE <i#1>NOT</i#1>',
            ' ALWAYS <a#1>blue</a#1>.']
        result = (
            'The <a class="foo">SKIES</a> '
            '<p>ARE <i>NOT</i></p>'
            ' ALWAYS <a href="bar">blue</a>.')
        self._assert_recomposes(translations, result)

    def test_textarea_self_closing_fails_parse(self):
        # TODO(psimakov): fix this
        html = 'foo <textarea name="bar"/> baz'
        expected = ['foo', 'baz']
        with self.assertRaises(AssertionError):
            self._assert_decomposes(html, expected)
        unexpected = ['foo <textarea#1 />', 'baz&lt;/div&gt;']
        self._assert_decomposes(html, unexpected)

    def test_placeholder(self):
        config = Configuration(omit_empty_opaque_decomposable=False)
        self.transformer = ContentTransformer(config)
        html = '<textarea class="foo" placeholder="bar">baz</textarea>'
        expected = ['<textarea#1 placeholder="bar" />', 'baz']
        self._assert_decomposes(html, expected)

    def test_recompose_complex_ul(self):
        config = Configuration(omit_empty_opaque_decomposable=False)
        self.transformer = ContentTransformer(config)
        html = '''
            <ul class="foo">
              <li>sss</li>
              <li index="bar">ttt</li>
              <li>xxx</li>
              <li>yyy</li>
              <li>zzz</li>
            </ul>
            '''
        expected = ['<ul#1 />', 'sss', 'ttt', 'xxx', 'yyy', 'zzz']
        self._assert_decomposes(html, expected)

        translations = ['<ul#1 />', 'SSS', 'TTT', 'XXX', 'YYY', 'ZZZ']
        result = '''
            <ul class="foo">
              <li>SSS</li>
              <li index="bar">TTT</li>
              <li>XXX</li>
              <li>YYY</li>
              <li>ZZZ</li>
            </ul>
            '''
        self._assert_recomposes(translations, result)

    def test_recompose_complex_with_opaque_docomposable(self):
        config = Configuration(omit_empty_opaque_decomposable=False)

        self.transformer = ContentTransformer(config)

        html = u"""
            <table border="2">
              <tbody>
                <tr>
                  <td>
                    <i>table</i>
                    <p></p>
                    <ul>
                      <li>a</li>
                      <li>b</li>
                    </ul>
                    <p></p>
                  </td>
                </tr>
              </tbody>
            </table>"""
        expected = [
          '<table#1 />', '<i#1>table</i#1>', '<ul#1 />', 'a', 'b']
        self._assert_decomposes(html, expected)
        translations = [
          '<table#1/>', '<i#1>TABLE</i#1>', '<ul#1/>', 'A', 'B']
        result = (
            '<table border="2">'
            '<tbody>'
            '<tr>'
            '<td>'
            '<i>TABLE</i>'
            '<p></p>'
            '<ul>'
            '<li>A</li>'
            '<li>B</li>'
            '</ul>'
            '<p></p>'
            '</td>'
            '</tr>'
            '</tbody>'
            '</table>')
        self._assert_recomposes(translations, result)

    def test_recompose_empty_p_is_roundtripped(self):
        html = 'The skies are blue.<p></p>The roses are red.'
        self._assert_decomposes(html, None)
        translation = ['The SKIES are blue. ', 'The roses are RED.']
        result = 'The SKIES are blue.<p></p>The roses are RED.'
        self._assert_recomposes(translation, result)

    def test_recompose_translation_with_no_significant_markup(self):
        html = 'The skies are blue.<p>Maybe...</p>The roses are red.'
        self._assert_decomposes(html, None)
        translation = ['The SKIES are blue.', 'MAYBE...', 'The roses are RED.']
        result = 'The SKIES are blue.<p>MAYBE...</p>The roses are RED.'
        self._assert_recomposes(translation, result)

    def test_no_new_tag_attributes_can_be_added_in_translations(self):
        html = 'The <a class="foo">skies</a> are blue.'
        self._assert_decomposes(html, None)
        translation = ['The <a#1 onclick="bar">SKIES</a#1> are blue.']
        result = 'The <a class="foo">SKIES</a> are blue.'
        self._assert_recomposes(translation, result)

    def test_whitespace_is_preserved(self):
        html = 'foo <b><i>bar</i></b>'

        expected_no_whitespace = ['foo', '<i#1>bar</i#1>']
        self._assert_decomposes(html, expected_no_whitespace)
        translation_no_whitespace = ['FOO', '<i#1>BAR</i#1>']
        result_no_whitespace = 'FOO<b><i>BAR</i></b>'
        self._assert_recomposes(translation_no_whitespace, result_no_whitespace)

        expected_with_whitespace = ['foo ', '<i#1>bar</i#1>']
        self._assert_decomposes(
            html, expected_with_whitespace, ignore_whitespace=False)
        translation_with_whitespace = ['FOO ', '<i#1>BAR</i#1>']
        result_with_whitespace = 'FOO <b><i>BAR</i></b>'
        self._assert_recomposes(
            translation_with_whitespace, result_with_whitespace)

    def test_no_new_tags_can_be_added_in_translations(self):
        original = 'The <a class="foo">skies</a> are blue.'
        self._assert_decomposes(original, None)
        translation = ['The <a#1>SKIES</a#1> are <b#2>blue</b#2>.']
        _error = self._assert_recomposes_error(translation)
        if not isinstance(_error.original_exception, LookupError):
            _error.reraise()
        self.assertEquals(
            'Unexpected tag: <b#2>.',
            _error.original_exception.message)
        self.assertEqual(0, _error.index)

    def test_all_tags_must_be_indexed_in_translations(self):
        original = 'The <a class="foo">skies</a> are blue.'
        self._assert_decomposes(original, None)
        translation = ['The <a#1>SKIES</a#1> are <b>blue</b>.']
        _error = self._assert_recomposes_error(translation)
        if not isinstance(_error.original_exception, SyntaxError):
            _error.reraise()
        self.assertEquals(
            'Error extracting index form the tag <b>. '
            'Tag name format is <tag_name#index>, like <a#1>.',
            _error.original_exception.message)
        self.assertEqual(0, _error.index)

    def test_all_tags_must_be_translated_in_translations(self):
        original = 'The <a class="foo">skies</a> are <a href="bar">blue</a>.'
        expected = ['The <a#1>skies</a#1> are <a#2>blue</a#2>.']
        self._assert_decomposes(original, expected)
        translation = ['The SKIES are blue.']
        _error = self._assert_recomposes_error(translation)
        if not isinstance(_error.original_exception, LookupError):
            _error.reraise()
        self.assertEquals(
            'Expected to find the following tags: <a#1>, <a#2>.',
            _error.original_exception.message)
        self.assertEqual(0, _error.index)

    def test_can_recompose_alphanum_tag_names(self):
        config = Configuration(
            inline_tag_names=['GCB-HTML5VIDEO'],
            omit_empty_opaque_decomposable=False)
        self.transformer = ContentTransformer(config)

        html = 'video <gcb-html5video url="woo.mp4"></gcb-html5video>'
        expected = ['video <gcb-html5video#1 />']
        self._assert_decomposes(html, expected)
        translation = ['VIDEO <gcb-html5video#1 />']
        result = 'VIDEO <gcb-html5video url="woo.mp4"></gcb-html5video>'
        self._assert_recomposes(translation, result)

    def test_recompose_called_multiple_times_fails(self):
        html = 'The <a class="foo">skies</a> are blue.'
        self._assert_decomposes(html, None)
        translation = ['The <a#1 onclick="bar">SKIES</a#1> are blue.']
        result = 'The <a class="foo">SKIES</a> are blue.'
        self._assert_recomposes(translation, result)
        _error = self._assert_recomposes_error(translation)
        if not isinstance(_error, AssertionError):
            raise Exception()
        self.assertEquals(
            'Please create new context; this context is not reusable.',
            _error.message)

    def test_recompose_large_sample_document(self):
        self.maxDiff = None
        original = ContentIO.tostring(ContentIO.fromstring(
            SAMPLE_HTML_DOC_CONTENT))
        self._assert_decomposes(original, None)
        translations = [] + SAMPLE_HTML_DOC_DECOMPOSE
        translations[2] = '<a#1>SKIP TO CONTENT</a#1>'
        result = original.replace('Skip to content', 'SKIP TO CONTENT')
        self._assert_recomposes(translations, result)

    def test_recompose_resource_bundle_into(self):
        original = '<p>The <a href="foo">skies</a> are blue!</p>'
        translation = [u'<a#1>Небо</a#1> синее!']
        expected = u'<p><a href="foo">Небо</a> синее!</p>'
        context, _ = merge_resource_bundle_into(
            html=original, resource_bundle=translation)
        self.assertEqual(expected, ContentIO.tostring(context.tree))


def run_all_unit_tests():
    """Runs all unit tests in this module."""
    suites_list = []
    for test_class in [
        ListsDifflibTests, SetsDifflibUtils,
        TestCasesForIO,
        TestCasesForContentDecompose, TestCasesForContentRecompose]:
        suite = unittest.TestLoader().loadTestsFromTestCase(test_class)
        suites_list.append(suite)
    result = unittest.TextTestRunner().run(unittest.TestSuite(suites_list))
    if not result.wasSuccessful() or result.errors:
        raise Exception(result)


# Below we keep content needed for test cases. We keep them here to allow this
# to be reused in any application and splitting test out into /tests/... would
# make this more difficult."""

# pylint: disable=line-too-long

# taken from http://www.google.com/edu/openonline/edukit/course-parts.html
SAMPLE_HTML_DOC_CONTENT = u'''

<!DOCTYPE html>
<html class="google" lang="en">
  <head>

    <script>
(function(H){H.className=H.className.replace(/\bgoogle\b/,'google-js')})(document.documentElement)
    </script>
    <meta charset="utf-8">
    <meta content="initial-scale=1, minimum-scale=1, width=device-width" name="viewport">
    <title>
      Google Open Online Education
    </title>
    <script src="//www.google.com/js/google.js">
</script>
    <script>
new gweb.analytics.AutoTrack({profile:"UA-12481063-1"});
    </script>
    <link href="//fonts.googleapis.com/css?family=Open+Sans:300,400,600,700&amp;lang=en" rel=
    "stylesheet">
    <link href=" /edu/openonline/css/edukit.css" rel="stylesheet">
  </head>
  <body>
    <div class="maia-header" id="maia-header" role="banner">
      <div class="maia-aux">
        <h1>
          <a href="/"><img alt="Google" src="//www.google.com/images/logos/google_logo_41.png">
          Open Online Education</a>
        </h1><a class="maia-teleport" href="#content">Skip to content</a>
      </div>
    </div>
    <div class="maia-nav" id="maia-nav-x" role="navigation">
      <div class="maia-aux">
        <ul>
          <li>
            <a data-g-action="Maia: Level 1" data-g-event="Maia: Site Nav" data-g-label="OOE_Home"
            href="/edu/openonline/index.html">Home</a>
          </li>
          <li>
            <a data-g-action="Maia: Level 1" data-g-event="Maia: Site Nav" data-g-label=
            "OOE_Insights" href="/edu/openonline/insights/index.html">Insights</a>
          </li>
          <li>
            <a class="active" data-g-action="Maia: Level 1" data-g-event="Maia: Site Nav"
            data-g-label="OOE_Edu_Kit" href="/edu/openonline/edukit/index.html">Online Course
            Kit</a>
          </li>
          <li>
            <a data-g-action="Maia: Level 1" data-g-event="Maia: Site Nav" data-g-label=
            "OOE_Open_edX" href="/edu/openonline/tech/index.html">Technologies</a>
          </li>
          <li>
            <a class="active" data-g-action="Maia: Level 1" data-g-event="Maia: Site Nav"
            data-g-label="GOOG_EDU_main" href="/edu/index.html">Google for Education</a>
          </li>
        </ul>
      </div>
    </div>
    <div id="maia-main" role="main">
      <div class="maia-nav-aux">
        <div class="edukit_nav">
          <ul>
            <li>
              <a data-g-action="Maia: Level 2" data-g-event="Maia: Site Nav" data-g-label=
              "Quick Start" href="/edu/openonline/edukit/quickstart.html">Quick Start</a>
            </li>
            <li>
              <a data-g-action="Maia: Level 2" data-g-event="Maia: Site Nav" data-g-label="Plan"
              href="/edu/openonline/edukit/plan.html">Plan</a>
            </li>
            <li>
              <a data-g-action="Maia: Level 2" data-g-event="Maia: Site Nav" data-g-label="Create"
              href="/edu/openonline/edukit/create.html">Create</a>
            </li>
            <li>
              <a data-g-action="Maia: Level 2" data-g-event="Maia: Site Nav" data-g-label=
              "Implement" href="/edu/openonline/edukit/implement.html">Implement</a>
            </li>
            <li>
              <a data-g-action="Maia: Level 2" data-g-event="Maia: Site Nav" data-g-label="Pilot"
              href="/edu/openonline/edukit/pilot.html">Pilot</a>
            </li>
            <li>
              <a data-g-action="Maia: Level 2" data-g-event="Maia: Site Nav" data-g-label=
              "Communicate" href="/edu/openonline/edukit/communicate.html">Communicate</a>
            </li>
            <li>
              <a data-g-action="Maia: Level 2" data-g-event="Maia: Site Nav" data-g-label=
              "Using Course Builder" href="/edu/openonline/edukit/course-parts.html">Using Course
              Builder</a>
            </li>
            <li>
              <a data-g-action="Maia: Level 2" data-g-event="Maia: Site Nav" data-g-label=
              "More Resources" href="/edu/openonline/edukit/resource.html">More Resources</a>
            </li>
          </ul>
        </div>
      </div>
      <div class="maia-teleport" id="content"></div>
      <div class="clearfix_nav"></div>
      <div class="ooe_content">
        <h1>
          Parts of a Course Builder Course
        </h1>
        <p>
          The primary parts of a course created with Course Builder are as follows:
        </p>
        <ul>
          <li>
            <a href="#course_content_and_delivery">Course content and delivery</a><br>
            The material that you formally convey to students. Formal content can be lessons
            recorded or written in advance. It can also be live question and answer sessions with
            course staff.
          </li>
          <li>
            <a href="#assessments_and_activities">Assessments and activities</a><br>
            Graded assessments with a fixed deadline to track student progress. You can also use
            ungraded assessments, called <strong>activities</strong>, to provide feedback and hints
            to students.
          </li>
          <li>
            <a href="#social_interactions">Social interactions</a><br>
            An important component of an online course is the interactions among the students
            themselves and the interactions between students and the course staff (the instructors
            or teaching assistants).
          </li>
          <li>
            <a href="#administrative_tasks">Administrative tasks</a><br>
            Of course, there are tasks such as registering students, setting up the course,
            tracking usage, and so on.
          </li>
        </ul>
        <p>
          A single course consists of a series of units with individual lessons and activities. The
          course can have any number of graded assessments scattered before, between, and after the
          units and lessons. It can also have one or more formally-set up avenues for social
          interaction for the students.
        </p>
        <p>
          For a quick description of the flow a student typically experiences in a course, see
          <a href="courseflow.html">Course Flow for Students</a>. For a description of the design
          process we think is effective, see <a href="design-process.html">Design Process</a>.
        </p>
        <p>
          The rest of this page discusses the four main parts of a course in more detail.
        </p><a id="course_content_and_delivery" name="course_content_and_delivery"></a>
        <h2>
          Course content and delivery
        </h2>
        <p>
          To make the content more digestible, consider grouping course material into a number of
          units. Each unit contains a series of lessons and possibly activities related to a
          particular topic within the content covered by the entire course.
        </p><input class="toggle-box-small" id="units1" type="checkbox"> <label for="units1">Units
        with lessons and activities</label>
        <div class="toggle-small maia-aside">
          <p>
            In the <a href="power-searching.html">Power Searching with Google</a> course, one unit
            is about interpreting search results; another is about checking the reliability of the
            content of those search results. Each of those units consists of about five lessons and
            about five activities. For these units, course staff creates and releases the lessons
            and activities ahead of time. While the material is available to students, course staff
            interacts with students through the <a href="forums.html">participant community
            mechanisms</a>.
          </p>
          <p>
            For a unit that consists of a series of lessons and activities, we found that around
            five lessons and four activities is a good length.
          </p>
          <p>
            A lesson is a coherent and relatively small chunk of information. In Power Searching
            with Google, we chose to create each lesson as one video and a text version of the same
            content. Your lessons do not have to have both parts. For more information, see
            <a href="https://www.google.com/edu/openonline/course-builder/docs/1.10/create-a-course/add-elements/lessons/lessons.html">Create Lessons</a>.
          </p>
          <p>
            An activity is an ungraded assessment, used to provide feedback to students on how well
            they understand the lesson. Activities typically contain optional hints. For more
            information, see <a href="#assessments_and_activities">Assessments and activities</a>.
          </p>
          <p>
            Tips:
          </p>
          <ul>
            <li>Make short videos, preferably 3-5 minutes.
            </li>
            <li>Include closed captions in your videos.
            </li>
            <li>For the text version, take the time to clean up the transcript.
            </li>
            <li>When deciding what content to include, design for the average student. To
            accommodate other students, consider including background or advanced material in forum
            posts (if you want discussion and maybe answers) or in Google+ or blog posts (if you
            just want to broadcast the information).
            </li>
          </ul>
        </div><input class="toggle-box-small" id="units2" type="checkbox"> <label for=
        "units2">Units using Hangouts on Air</label>
        <div class="toggle-small maia-aside">
          <p>
            A very different type of unit is online office hours where the students submit
            questions ahead of time and the course staff answers those questions in real-time using
            a <a href="http://www.google.com/+/learnmore/hangouts/onair.html">Hangout On Air</a>.
            Depending on your course, you may have some students interacting with the course staff
            over video for the Hangout On Air or you may have students submit all of their
            questions using <a href="https://www.google.com/moderator/">Google Moderator</a>.
          </p>
          <p>
            For online office hours you have a fixed date and time when the course staff broadcasts
            a session for students to watch and interact with.
          </p>
          <p>
            If you have a very small course (fewer than 10 people), you can use a Google Hangout
            for your session. If you have more than 10 people, you can use a combination of Google
            Hangouts on Air and Google Moderator instead.
          </p>
          <p>
            A <a href="//www.google.com/+/learnmore/hangouts/">Google Hangout</a> is a video chat
            that can have up to 10 participants. In a Google Hangout, all participants can share
            what\u2019s on each person's screen, collaborate in Google Docs, view presentations and
            diagrams together and speak to each other. If your course is small enough, this is a
            great way to go. If your course is large, you may still consider having your students
            break into small groups for interactive activities with each other over Hangouts.
          </p>
          <p>
            <strong>Tip:</strong> If you do a Hangout on Air, consider using a live captioning
            service to help students who are hearing impaired or whose primary language is not the
            language used in the Hangout on Air.
          </p>
        </div>
        <p>
          For all of these unit types, instructors make course content available to students at
          scheduled intervals throughout the course. Once available, the content continues to be
          available until the course ends. That is, lessons are not available for only a few days;
          students can go back and redo lessons at any time throughout the course. In <a href=
          "http://www.powersearchingwithgoogle.com/">Power Searching with Google</a>, soon after
          online office hours took place, the course staff posted a video of it. So even if
          students missed the office hours, that material was still available.
        </p>
        <p>
          Releasing course content at scheduled intervals has one perhaps unanticipated benefit.
          Many students tend to work on content relatively soon after the content becomes
          available. For that reason, questions about course material tend to cluster near the
          release of that material. Because other students are thinking about the same material,
          they are more likely to be interested in getting involved in discussions about the
          material or in answering questions.
        </p>
        <p>
          These are only some possibilities for how to model units. You may discover other ways to
          do things that suit your material better. For example, instead of all of the teaching
          being pushed from the course staff, you may decide to break your students into small
          cohorts and have those cohorts work on material together. You could provide them with
          lessons and activities to start from and then have them use Hangouts of their own for
          group study.
        </p><a id="assessments_and_activities" name="assessments_and_activities"></a>
        <h2>
          Assessments and activities
        </h2>
        <p>
          In Course Builder, an assessment is a test. Assessments can either be graded or ungraded.
          Ungraded assessments are also called activities.
        </p>
        <p>
          When you create your course using Course Builder, you supply the code with the
          information needed to grade assessments.
        </p><input class="toggle-box-small" id="question-types" type="checkbox"> <label for=
        "question-types">Question types</label>
        <div class="toggle-small maia-aside">
          <p>
            Graded and ungraded assessments essentially support the same types of questions:
          </p>
          <ul>
            <li>Multiple-choice with one correct answer
            </li>
            <li>Multiple-choice with more than one correct answer
            </li>
            <li>Fill-in-the blank
            </li>
            <li>Go and do something. These are questions that do not have prepared answers and
            instead invite the user to engage in some action. For example, in <a href=
            "//www.powersearchingwithgoogle.com/">Power Searching with Google</a> one of the
            questions was "When was the last historic earthquake in your area? Share your answer in
            the forum."
            </li>
          </ul>
          <p>
            Telling the experimental code how to grade multiple-choice questions is
            straightforward. Telling it how to grade fill-in-the-blank questions can be trickier.
            You need to be very careful both in your wording of the question and in what you
            include about the correct answer. \u201cGo and do something\u201d questions do not require an
            answer, so you don\u2019t have to include anything about the answer.
          </p>
        </div><input class="toggle-box-small" id="ungraded-activities" type="checkbox"> <label for=
        "ungraded-activities">Ungraded activities</label>
        <div class="toggle-small maia-aside">
          <p>
            An activity typically covers material only from the lesson that the activity
            immediately follows. You use them to let the students assess their own understanding of
            the material in that lesson. An activity does not affect a student\u2019s final score in the
            course.
          </p>
          <p>
            When you create a question for an activity, you can provide the following information:
          </p>
          <ul>
            <li>The correct answer to the question, so the code knows what to tell the student.
            </li>
            <li>A hint about why incorrect answers are incorrect. The hint should point the student
            to the correct answer.
            </li>
            <li>The correct answer and explanatory information.
            </li>
          </ul>
        </div><input class="toggle-box-small" id="graded-assessments" type="checkbox"> <label for=
        "graded-assessments">Graded assessments</label>
        <div class="toggle-small maia-aside">
          <p>
            Graded assessments typically cover material from several units and lessons. You use
            them to rate students\u2019 performance. Before and after assessments can also help you
            gauge the effectiveness of the course.
          </p>
          <p>
            With Course Builder's experimental code, you have control over how many graded
            assessments you provide and how each of those assessments counts in the final scoring
            for a student\u2019s grade.
          </p>
          <p>
            Because you use a graded assessment to rate performance and measure success, your
            practical choices are:
          </p>
          <ul>
            <li>Only let students take a graded assessment once. In this case, you can tell your
            students which of their answers are incorrect.
            </li>
            <li>Let students take a graded assessment multiple times. In this case, do not tell
            them which answers are incorrect. (If you do, then they'll have no difficulty getting
            100% when retaking the same assessment.)
            </li>
          </ul>
          <p>
            If you choose to allow your students to take the same graded assessment multiple times,
            consider still giving the students some feedback about what they did wrong. To do this,
            map each assessment question to the corresponding unit and lesson within the course.
            Then immediately after submission of the assessment, show students the score and list
            the lessons to review to improve their score.
          </p>
        </div>
        <h2>
          Social interactions
        </h2>
        <p>
          Another critical component of a successful course is student participation. Online office
          hours and asking questions of the experts are some examples to elicit participation.
        </p>
        <p>
          For large online courses, the size of the audience means that it is impractical for the
          course staff to answer all of the questions and to enter all of the discussions posed by
          all of the students. Instead, you can set up avenues in which the students can
          participate not just with the instructor but also with other students.
        </p>
        <p>
          The most common types of social interactions are:
        </p>
        <ul>
          <li>
            <a href="https://www.google.com/edu/openonline/course-builder/docs/1.10/prepare-for-students/forum.html">Google Groups or other web
            forum</a><br>
            A web forum is a great way to get your students to talk to each other. To facilitate
            discussion, you can set up your forum with appropriate categories, to guide students to
            likely places to read and to post questions on particular topics within your course.
            When designing the content of your course, consider creating activities requesting that
            students post answers to the forum. You can also use a forum to post material that you
            do not want in the main body of your course, either because it is background material
            for students who need a bit more help or more challenging questions for more advanced
            students.
          </li>
          <li>
            <a href="https://www.google.com/edu/openonline/course-builder/docs/1.10/meet-course-builder/student-facing-site.html#announcements-tab">Google+ page or
            blog</a><br>
            Use Google+ or your blog to share information that you want available to not just your
            students, but to other people as well. While students can comment on your posts, these
            formats are still primarily methods for instructors to push information out to the
            students.
          </li>
          <li>
            <a href="https://www.google.com/edu/openonline/course-builder/docs/1.10/create-a-course/add-elements/links.html#online-office-hours">Google Hangout</a><br>
            You may decide that you want your students to divide into smaller groups to work on
            projects together. Your students probably live in distributed areas. You can have them
            meet in a Google Hangout to collaborate on their project.
          </li>
          <li>
            <a href="https://www.google.com/edu/openonline/course-builder/docs/1.10/prepare-for-students/invitations.html">Announcements-only email alias</a><br>
            Throughout the course, you may want to send email to students, such as to remind them
            of upcoming events.
          </li>
        </ul>
        <p>
          In addition to these things that you set up, students may create additional interaction
          mechanisms, perhaps an email alias for students interested in a particular aspect of the
          course material or weekly in-person meetings for students living close to each other.
        </p><a id="administrivia" name="administrivia"></a>
        <h2>
          Administrative tasks
        </h2>
        <p>
          Of course, as with any class there are various administrative aspects to creating an
          online course. Two of the major ones are <a href=
          "https://www.google.com/edu/openonline/course-builder/docs/1.10/prepare-for-students/invitations.html">managing student
          registration</a> and <a href=
          "https://www.google.com/edu/openonline/course-builder/docs/1.10/prepare-for-students/registration.html">collecting and analyzing data
          to see how well your course does</a>.
        </p>
        <p>
          For a full list of tasks needed to create a course, see the <a href=
          "https://www.google.com/edu/openonline/course-builder/docs/1.10/create-a-course/create-a-course.html">Course Builder
          Checklist</a>.
        </p>
      </div>
    </div>
    <div id="maia-signature"></div>
    <div class="maia-footer" id="maia-footer">
      <div id="maia-footer-global">
        <div class="maia-aux">
          <ul>
            <li>
              <a href="/">Google</a>
            </li>
            <li>
              <a href="/intl/en/about/">About Google</a>
            </li>
            <li>
              <a href="/intl/en/policies/">Privacy &amp; Terms</a>
            </li>
          </ul>
        </div>
      </div>
    </div><script src="//www.google.com/js/maia.js">
</script>
  </body>
</html>
        '''

SAMPLE_HTML_DOC_DECOMPOSE = [
    'Google Open Online Education',
    '<img#1 src="//www.google.com/images/logos/google_logo_41.png" alt="Google" />\n          Open Online Education',
    '<a#1>Skip to content</a#1>',
    '<a#1>Home</a#1>',
    '<a#1>Insights</a#1>',
    '<a#1>Online Course\n            Kit</a#1>',
    '<a#1>Technologies</a#1>',
    '<a#1>Google for Education</a#1>',
    '<a#1>Quick Start</a#1>',
    '<a#1>Plan</a#1>',
    '<a#1>Create</a#1>',
    '<a#1>Implement</a#1>',
    '<a#1>Pilot</a#1>',
    '<a#1>Communicate</a#1>',
    '<a#1>Using Course\n              Builder</a#1>',
    '<a#1>More Resources</a#1>',
    'Parts of a Course Builder Course',
    'The primary parts of a course created with Course Builder are as follows:',
    '<a#1>Course content and delivery</a#1><br#2 />\n            The material that you formally convey to students. Formal content can be lessons\n            recorded or written in advance. It can also be live question and answer sessions with\n            course staff.',
    '<a#1>Assessments and activities</a#1><br#2 />\n            Graded assessments with a fixed deadline to track student progress. You can also use\n            ungraded assessments, called <strong#3>activities</strong#3>, to provide feedback and hints\n            to students.',
    '<a#1>Social interactions</a#1><br#2 />\n            An important component of an online course is the interactions among the students\n            themselves and the interactions between students and the course staff (the instructors\n            or teaching assistants).',
    '<a#1>Administrative tasks</a#1><br#2 />\n            Of course, there are tasks such as registering students, setting up the course,\n            tracking usage, and so on.',
    'A single course consists of a series of units with individual lessons and activities. The\n          course can have any number of graded assessments scattered before, between, and after the\n          units and lessons. It can also have one or more formally-set up avenues for social\n          interaction for the students.',
    'For a quick description of the flow a student typically experiences in a course, see\n          <a#1>Course Flow for Students</a#1>. For a description of the design\n          process we think is effective, see <a#2>Design Process</a#2>.',
    'The rest of this page discusses the four main parts of a course in more detail.',
    'Course content and delivery',
    'To make the content more digestible, consider grouping course material into a number of\n          units. Each unit contains a series of lessons and possibly activities related to a\n          particular topic within the content covered by the entire course.',
    'Units\n        with lessons and activities',
    'In the <a#1>Power Searching with Google</a#1> course, one unit\n            is about interpreting search results; another is about checking the reliability of the\n            content of those search results. Each of those units consists of about five lessons and\n            about five activities. For these units, course staff creates and releases the lessons\n            and activities ahead of time. While the material is available to students, course staff\n            interacts with students through the <a#2>participant community\n            mechanisms</a#2>.',
    'For a unit that consists of a series of lessons and activities, we found that around\n            five lessons and four activities is a good length.',
    'A lesson is a coherent and relatively small chunk of information. In Power Searching\n            with Google, we chose to create each lesson as one video and a text version of the same\n            content. Your lessons do not have to have both parts. For more information, see\n            <a#1>Create Lessons</a#1>.',
    'An activity is an ungraded assessment, used to provide feedback to students on how well\n            they understand the lesson. Activities typically contain optional hints. For more\n            information, see <a#1>Assessments and activities</a#1>.',
    'Tips:',
    'Make short videos, preferably 3-5 minutes.',
    'Include closed captions in your videos.',
    'For the text version, take the time to clean up the transcript.',
    'When deciding what content to include, design for the average student. To\n            accommodate other students, consider including background or advanced material in forum\n            posts (if you want discussion and maybe answers) or in Google+ or blog posts (if you\n            just want to broadcast the information).',
    'Units using Hangouts on Air',
    'A very different type of unit is online office hours where the students submit\n            questions ahead of time and the course staff answers those questions in real-time using\n            a <a#1>Hangout On Air</a#1>.\n            Depending on your course, you may have some students interacting with the course staff\n            over video for the Hangout On Air or you may have students submit all of their\n            questions using <a#2>Google Moderator</a#2>.',
    'For online office hours you have a fixed date and time when the course staff broadcasts\n            a session for students to watch and interact with.',
    'If you have a very small course (fewer than 10 people), you can use a Google Hangout\n            for your session. If you have more than 10 people, you can use a combination of Google\n            Hangouts on Air and Google Moderator instead.',
    u'A <a#1>Google Hangout</a#1> is a video chat\n            that can have up to 10 participants. In a Google Hangout, all participants can share\n            what\u2019s on each person&#39;s screen, collaborate in Google Docs, view presentations and\n            diagrams together and speak to each other. If your course is small enough, this is a\n            great way to go. If your course is large, you may still consider having your students\n            break into small groups for interactive activities with each other over Hangouts.',
    '<strong#1>Tip:</strong#1> If you do a Hangout on Air, consider using a live captioning\n            service to help students who are hearing impaired or whose primary language is not the\n            language used in the Hangout on Air.',
    'For all of these unit types, instructors make course content available to students at\n          scheduled intervals throughout the course. Once available, the content continues to be\n          available until the course ends. That is, lessons are not available for only a few days;\n          students can go back and redo lessons at any time throughout the course. In <a#1>Power Searching with Google</a#1>, soon after\n          online office hours took place, the course staff posted a video of it. So even if\n          students missed the office hours, that material was still available.',
    'Releasing course content at scheduled intervals has one perhaps unanticipated benefit.\n          Many students tend to work on content relatively soon after the content becomes\n          available. For that reason, questions about course material tend to cluster near the\n          release of that material. Because other students are thinking about the same material,\n          they are more likely to be interested in getting involved in discussions about the\n          material or in answering questions.',
    'These are only some possibilities for how to model units. You may discover other ways to\n          do things that suit your material better. For example, instead of all of the teaching\n          being pushed from the course staff, you may decide to break your students into small\n          cohorts and have those cohorts work on material together. You could provide them with\n          lessons and activities to start from and then have them use Hangouts of their own for\n          group study.',
    'Assessments and activities',
    'In Course Builder, an assessment is a test. Assessments can either be graded or ungraded.\n          Ungraded assessments are also called activities.',
    'When you create your course using Course Builder, you supply the code with the\n          information needed to grade assessments.',
    'Question types',
    'Graded and ungraded assessments essentially support the same types of questions:',
    'Multiple-choice with one correct answer',
    'Multiple-choice with more than one correct answer',
    'Fill-in-the blank',
    'Go and do something. These are questions that do not have prepared answers and\n            instead invite the user to engage in some action. For example, in <a#1>Power Searching with Google</a#1> one of the\n            questions was &quot;When was the last historic earthquake in your area? Share your answer in\n            the forum.&quot;',
    u'Telling the experimental code how to grade multiple-choice questions is\n            straightforward. Telling it how to grade fill-in-the-blank questions can be trickier.\n            You need to be very careful both in your wording of the question and in what you\n            include about the correct answer. \u201cGo and do something\u201d questions do not require an\n            answer, so you don\u2019t have to include anything about the answer.',
    'Ungraded activities',
    u'An activity typically covers material only from the lesson that the activity\n            immediately follows. You use them to let the students assess their own understanding of\n            the material in that lesson. An activity does not affect a student\u2019s final score in the\n            course.',
    'When you create a question for an activity, you can provide the following information:',
    'The correct answer to the question, so the code knows what to tell the student.',
    'A hint about why incorrect answers are incorrect. The hint should point the student\n            to the correct answer.',
    'The correct answer and explanatory information.',
    'Graded assessments',
    u'Graded assessments typically cover material from several units and lessons. You use\n            them to rate students\u2019 performance. Before and after assessments can also help you\n            gauge the effectiveness of the course.',
    u'With Course Builder&#39;s experimental code, you have control over how many graded\n            assessments you provide and how each of those assessments counts in the final scoring\n            for a student\u2019s grade.',
    'Because you use a graded assessment to rate performance and measure success, your\n            practical choices are:',
    'Only let students take a graded assessment once. In this case, you can tell your\n            students which of their answers are incorrect.',
    'Let students take a graded assessment multiple times. In this case, do not tell\n            them which answers are incorrect. (If you do, then they&#39;ll have no difficulty getting\n            100% when retaking the same assessment.)',
    'If you choose to allow your students to take the same graded assessment multiple times,\n            consider still giving the students some feedback about what they did wrong. To do this,\n            map each assessment question to the corresponding unit and lesson within the course.\n            Then immediately after submission of the assessment, show students the score and list\n            the lessons to review to improve their score.',
    'Social interactions',
    'Another critical component of a successful course is student participation. Online office\n          hours and asking questions of the experts are some examples to elicit participation.',
    'For large online courses, the size of the audience means that it is impractical for the\n          course staff to answer all of the questions and to enter all of the discussions posed by\n          all of the students. Instead, you can set up avenues in which the students can\n          participate not just with the instructor but also with other students.',
    'The most common types of social interactions are:',
    '<a#1>Google Groups or other web\n            forum</a#1><br#2 />\n            A web forum is a great way to get your students to talk to each other. To facilitate\n            discussion, you can set up your forum with appropriate categories, to guide students to\n            likely places to read and to post questions on particular topics within your course.\n            When designing the content of your course, consider creating activities requesting that\n            students post answers to the forum. You can also use a forum to post material that you\n            do not want in the main body of your course, either because it is background material\n            for students who need a bit more help or more challenging questions for more advanced\n            students.',
    '<a#1>Google+ page or\n            blog</a#1><br#2 />\n            Use Google+ or your blog to share information that you want available to not just your\n            students, but to other people as well. While students can comment on your posts, these\n            formats are still primarily methods for instructors to push information out to the\n            students.',
    '<a#1>Google Hangout</a#1><br#2 />\n            You may decide that you want your students to divide into smaller groups to work on\n            projects together. Your students probably live in distributed areas. You can have them\n            meet in a Google Hangout to collaborate on their project.',
    '<a#1>Announcements-only\n            email alias</a#1><br#2 />\n            Throughout the course, you may want to send email to students, such as to remind them\n            of upcoming events.',
    'In addition to these things that you set up, students may create additional interaction\n          mechanisms, perhaps an email alias for students interested in a particular aspect of the\n          course material or weekly in-person meetings for students living close to each other.',
    'Administrative tasks',
    'Of course, as with any class there are various administrative aspects to creating an\n          online course. Two of the major ones are <a#1>managing student\n          registration</a#1> and <a#2>collecting and analyzing data\n          to see how well your course does</a#2>.',
    'For a full list of tasks needed to create a course, see the <a#1>Course Builder\n          Checklist</a#1>.',
    '<a#1>Google</a#1>',
    '<a#1>About Google</a#1>',
    '<a#1>Privacy &amp; Terms</a#1>'
]
# pylint: enable=line-too-long


if __name__ == '__main__':
    run_all_unit_tests()
