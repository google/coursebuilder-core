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
from common import schema_fields
from extensions import tags
from lxml import etree
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

    def render(self, unused_node):
        """Receive a node and return a node."""
        return etree.XML('[Unimplemented custom tag]')

    def get_icon_url(self):
        """Provide an icon for the visual editor."""
        return """
data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAADAAAAAwCAYAAABXAvmHAAAAAXNSR0IArs
4c6QAAAAZiS0dEAP8A/wD/oL2nkwAAAAlwSFlzAAALEwAACxMBAJqcGAAAAAd0SU1FB90EGgAIFHpT6h
8AAAAZdEVYdENvbW1lbnQAQ3JlYXRlZCB3aXRoIEdJTVBXgQ4XAAAC30lEQVRo3u1ZP2sqQRCfVVGUXC
FqoZAmbSBYxFikMojBD2ErkgdC/AxpAn4A2wRMKptgCrWwSApBEG2DCidcI0gIxogXnXnFI5I87y6Jd6
seOHDN7LL7+83u/Nk5hoh/wMTCEJHMTMDGGDMzfrCAyWVL4DdCZLy72YwCxhgDIoKXlxcQRREeHx9BFE
WYTqfg9XohGAxCKBSCnZ0dcDqdhlrFEKlWq8QYIwD49ovFYjQajYiICBF17auLACLSbDaj3d3dObizsz
Nqt9v09PRE8Xhck0gul9NtONADnojI7XbPAXW73YV55XJZk8TFxcX6TuDk5GQORBAE1StxeXmpSaJery
99lWBZ69dqtQUgpVJJcW6/39cksL+/v/oTiEajC0DsdjvNZjPF+Q6HQ5PEsrJ0Huj1egs6WZbh+flZcX
4kEtFcr1KprDaRybKsqL++vlbU+/1+zfVEUVwtAZ/Pp6h/f39X1COi5nqBQGC1iaxUKine5eFwqDg/Fo
tx8QFdYfTm5uYLiPv7e0JExZD4OV/8/+3t7a0vkcmyTJIk0Xg8Vs0Dr6+vmta/vb1dbR74rTw8PKiCPz
09XV8m/qmEQiFF8IeHh7oLOq4EEJGazaam5ddajf5ElKJPNps1BDxXAohIjUbjC3CPx0OTycTQfbiewO
f3QDKZ5LIHVwIf4PP5vGFXZmUErq6uCAAok8lw9TFuBFKp1LxE4GF53eX0d10KSZLg+Pj4X/+SY/ePCw
HGGIzHYzg6OuLfG+W18MHBAYTDYf7daeLRLtv2RrcE9DdvC4UC5PN5mE6n3DvGhtU+RETn5+cLxVsikT
BHIru7u1N9uKTTaS4EDItCiAhWq1V13OVywWg02lwfGA6HmuNvb2+b7cQWi8XcUUgQBPB6varjWmMbE0
Y7nY5q4VYsFs0RRvv9PgmCMI8+VquVWq0WtzBqaC308bMPAGAwGAAiqvZQt8XcthbaELGZ/AbBX0kdVa
SPB+uxAAAAAElFTkSuQmCC
"""

    def get_schema(self):
        """Get the schema for the tag's attributes using schema_fields."""
        reg = schema_fields.FieldRegistry('Unimplemented Custom Tag')
        return reg


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
    if elt_list and isinstance(elt_list[0], basestring):
        node_list.append(safe_dom.Text(elt_list[0]))
        elt_list = elt_list[1:]
    for elt in elt_list:
        node_list.append(_process_html_tree(elt))
    return node_list
