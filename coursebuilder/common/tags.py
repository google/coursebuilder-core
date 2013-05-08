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

"""Handlers for custom HTML tags."""

__author__ = 'John Orr (jorr@google.com)'

import inspect
import pkgutil
from extensions import tags
from lxml import html
from models import config
import safe_dom


CAN_USE_DYNAMIC_TAGS = config.ConfigProperty(
    'gcb_can_use_dynamic_tags', bool, (
        'Whether lesson content can make use of custom HTML tags such as '
        '<gcb-youtube videoid="...">. If this is enabled some legacy content '
        'may be rendered differently. '),
    default_value=True)


class BaseTag(object):
    """Base class for the custom HTML tags."""

    def render(self, node):
        """Receive a node and return a node."""
        raise NotImplementedError()

    def get_icon_url(self):
        """Provide an icon for the visual editor."""
        raise NotImplementedError()


def get_tag_bindings():
    """Return the bindings of tag names to implementing classes.

    Tag bindings work by looking for classes which extend BaseTag and which
    belong to packages inside extensions/tags. The tag name is then composed
    from the package name and the class name, after lower-casing and separated
    with a dash. E.g., the class
        extensions.tags.gcb.YouTube
    is bound to the tag name gcb-youtube.

    Returns:
        the bindings of tag names to implementing classes.
    """

    bindings = {}
    for loader, name, ispkg in pkgutil.walk_packages(tags.__path__):
        if ispkg:
            mod = loader.find_module(name).load_module(name)
            for name, clazz in inspect.getmembers(mod, inspect.isclass):
                if issubclass(clazz, BaseTag):
                    tag_name = ('%s-%s' % (mod.__name__, name)).lower()
                    bindings[tag_name] = clazz
    return bindings


def html_to_safe_dom(html_string):
    """Render HTML text as a tree of safe_dom elements."""
    tag_bindings = get_tag_bindings()

    def _process_html_tree(elt):
        node_list = safe_dom.NodeList()

        tail = elt.tail

        if elt.tag in tag_bindings:
            elt = tag_bindings[elt.tag]().render(elt)

        out_elt = safe_dom.Element(elt.tag)
        out_elt.add_attribute(**elt.attrib)
        if elt.text:
            out_elt.add_text(elt.text)
        for child in elt:
            out_elt.add_children(_process_html_tree(child))
        node_list.append(out_elt)
        if tail:
            node_list.append(safe_dom.Text(tail))
        return node_list

    elt_list = html.fragments_fromstring(html_string)
    node_list = safe_dom.NodeList()
    if elt_list and isinstance(elt_list[0], str):
        node_list.append(safe_dom.Text(elt_list[0]))
        elt_list = elt_list[1:]
    for elt in elt_list:
        node_list.append(_process_html_tree(elt))
    return node_list
