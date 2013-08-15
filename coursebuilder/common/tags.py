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
import logging
import mimetypes
import os
import pkgutil
from xml.etree import cElementTree

import appengine_config
from common import schema_fields
from extensions import tags
import html5lib
from models import config
import webapp2

import safe_dom


CAN_USE_DYNAMIC_TAGS = config.ConfigProperty(
    'gcb_can_use_dynamic_tags', bool, safe_dom.Text(
        'Whether lesson content can make use of custom HTML tags such as '
        '<gcb-youtube videoid="...">. If this is enabled some legacy content '
        'may be rendered differently. '),
    default_value=True)


DUPLICATE_INSTANCE_ID_MESSAGE = (
    'Error processing custom HTML tag: duplicate tag id')
INVALID_HTML_TAG_MESSAGE = 'Invalid HTML tag'


class BaseTag(object):
    """Base class for the custom HTML tags."""

    @classmethod
    def name(cls):
        return cls.__name__

    @classmethod
    def vendor(cls):
        return cls.__module__

    @classmethod
    def required_modules(cls):
        """Lists the inputEx modules required by the editor."""
        return []

    def render(self, unused_node, unused_handler):
        """Receive a node and return a node."""
        return cElementTree.XML('<div>[Unimplemented custom tag]</div>')

    def get_icon_url(self):
        """Return the URL for the icon to be displayed in the rich text editor.

        Images should be placed in a folder called 'resources' inside the main
        package for the tag definitions.

        Returns:
          the URL for the icon to be displayed in the editor.
        """

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

    def get_schema(self, unused_handler):
        """Return the list of fields which will be displayed in the editor.

        This method assembles the list of fields which will be displayed in
        the rich text editor when a user double-clicks on the icon for the tag.
        The fields are a list of SchemaField objects in a FieldRegistry
        container. Each SchemaField has the actual attribute name as used in
        the tag, the display name for the form, and the type (usually
        string).

        Returns:
          the list of fields to be displayed in the editor.
        """

        reg = schema_fields.FieldRegistry('Unimplemented Custom Tag')
        return reg

    def unavailable_schema(self, message):
        """Utility to generate a schema for a "not available" message."""
        reg = schema_fields.FieldRegistry(self.name())
        reg.add_property(
            schema_fields.SchemaField(
                'unused_id', '', 'string', optional=True,
                editable=False, extra_schema_dict_values={
                    'value': message,
                    'visu': {
                        'visuType': 'funcName',
                        'funcName': 'disableSave'}}))
        return reg


class ResourcesHandler(webapp2.RequestHandler):
    """Content handler for resources associated with custom tags."""

    def get(self):
        """Respond to HTTP GET methods."""
        path = self.request.path
        if path.startswith('/'):
            path = path[1:]
        path = os.path.normpath(path)

        if os.path.basename(os.path.dirname(path)) != 'resources':
            self.error(404)

        resource_file = os.path.join(appengine_config.BUNDLE_ROOT, path)

        mimetype = mimetypes.guess_type(resource_file)[0]
        if mimetype is None:
            mimetype = 'application/octet-stream'

        try:
            self.response.status = 200
            self.response.headers['Content-Type'] = mimetype
            self.response.cache_control.no_cache = None
            self.response.cache_control.public = 'public'
            self.response.cache_control.max_age = 600
            stream = open(resource_file)
            self.response.write(stream.read())
        except IOError:
            self.error(404)


class EditorBlacklists(object):
    """Lists tags which should not be supported by various editors."""

    COURSE_SCOPE = set()
    ASSESSMENT_SCOPE = set()

    @classmethod
    def register(cls, tag_name, editor_set):
        editor_set.add(tag_name)

    @classmethod
    def unregister(cls, tag_name, editor_set):
        if tag_name in editor_set:
            editor_set.remove(tag_name)


class Registry(object):
    """A class that holds all dynamically registered tags."""

    _bindings = {}

    @classmethod
    def add_tag_binding(cls, tag_name, clazz):
        """Registers a tag name to class binding."""
        cls._bindings[tag_name] = clazz

    @classmethod
    def remove_tag_binding(cls, tag_name):
        """Unregisters a tag binding."""
        if tag_name in cls._bindings:
            del cls._bindings[tag_name]

    @classmethod
    def get_all_tags(cls):
        return dict(cls._bindings.items())


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
    return dict(bindings.items() + Registry.get_all_tags().items())


def html_string_to_element_tree(html_string):
    parser = html5lib.HTMLParser(
        tree=html5lib.treebuilders.getTreeBuilder('etree', cElementTree),
        namespaceHTMLElements=False)
    return parser.parseFragment('<div>%s</div>' % html_string)[0]


def html_to_safe_dom(html_string, handler):
    """Render HTML text as a tree of safe_dom elements."""

    tag_bindings = get_tag_bindings()

    node_list = safe_dom.NodeList()
    if not html_string:
        return node_list

    def _generate_error_message_node_list(elt, error_message):
        """Generates a node_list representing an error message."""
        logging.error(
            '[%s, %s]: %s.', elt.tag, dict(**elt.attrib), error_message)

        node_list = safe_dom.NodeList()
        node_list.append(safe_dom.Element(
            'span', className='gcb-error-tag'
        ).add_text(error_message))

        if elt.tail:
            node_list.append(safe_dom.Text(elt.tail))
        return node_list

    def _process_html_tree(elt, used_instance_ids):
        # Return immediately with an error message if a duplicate instanceid is
        # detected.
        if 'instanceid' in elt.attrib:
            if elt.attrib['instanceid'] in used_instance_ids:
                return _generate_error_message_node_list(
                    elt, DUPLICATE_INSTANCE_ID_MESSAGE)

            used_instance_ids.add(elt.attrib['instanceid'])

        # Otherwise, attempt to parse this tag and all its child tags.
        original_elt = elt
        try:
            if elt.tag in tag_bindings:
                elt = tag_bindings[elt.tag]().render(elt, handler)

            if elt.tag.lower() == 'script':
                out_elt = safe_dom.ScriptElement()
            else:
                out_elt = safe_dom.Element(elt.tag)
            out_elt.add_attribute(**elt.attrib)

            if elt.text:
                out_elt.add_text(elt.text)
            for child in elt:
                out_elt.add_children(
                    _process_html_tree(child, used_instance_ids))

            node_list = safe_dom.NodeList()
            node_list.append(out_elt)
            if original_elt.tail:
                node_list.append(safe_dom.Text(original_elt.tail))
            return node_list

        except Exception as e:  # pylint: disable-msg=broad-except
            return _generate_error_message_node_list(
                original_elt, '%s: %s' % (INVALID_HTML_TAG_MESSAGE, e))

    root = html_string_to_element_tree(html_string)
    if root.text:
        node_list.append(safe_dom.Text(root.text))

    used_instance_ids = set([])
    for elt in root:
        node_list.append(_process_html_tree(elt, used_instance_ids))

    return node_list


def get_components_from_html(html):
    """Returns a list of dicts representing the components in a lesson.

    Args:
        html: a block of html that may contain some HTML tags representing
          custom components.

    Returns:
        A list of dicts. Each dict represents one component and has two
        keys:
        - instanceid: the instance id of the component
        - cpt_name: the name of the component tag (e.g. gcb-googlegroup)
    """
    parser = html5lib.HTMLParser(
        tree=html5lib.treebuilders.getTreeBuilder('etree', cElementTree),
        namespaceHTMLElements=False)
    content = parser.parseFragment('<div>%s</div>' % html)[0]

    components = []
    for component in content.findall('.//*[@instanceid]'):
        component_dict = {'cpt_name': component.tag}
        component_dict.update(component.attrib)
        components.append(component_dict)
    return components

