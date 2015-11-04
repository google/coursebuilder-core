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


import logging
import mimetypes
import os
import re
from xml.etree import cElementTree

import html5lib
import safe_dom
import webapp2

import appengine_config

from common import messages
from common import schema_fields
from models import config

_LXML_AVAILABLE = False
try:
    import lxml.html
    _LXML_AVAILABLE = True
except ImportError:
    if appengine_config.PRODUCTION_MODE:
        raise


CAN_USE_DYNAMIC_TAGS = config.ConfigProperty(
    'gcb_can_use_dynamic_tags', bool, messages.SITE_SETTINGS_DYNAMIC_TAGS,
    default_value=True, label='Dynamic Tags')


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

    @classmethod
    def extra_js_files(cls):
        """Returns a list of JS files to be loaded in the editor lightbox."""
        return []

    @classmethod
    def extra_css_files(cls):
        """Returns a list of CSS files to be loaded in the editor lightbox."""
        return []

    @classmethod
    def additional_dirs(cls):
        """Returns a list of directories searched for files used by the editor.

        These folders will be searched for files to be loaded as Jinja
        templates by the editor, e.g., the files referenced by extra_js_files
        and extra_css_files.

        Returns:
            List of strings.
        """
        return []

    def render(self, node, handler):  # pylint: disable=W0613
        """Receive a node and return a node.

        Args:
            node: cElementTree.Element. The DOM node for the tag which should be
                rendered.
            handler: controllers.utils.BaseHandler. The server runtime.

        Returns:
            A cElementTree.Element holding the rendered DOM.
        """
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

        The schema field type of "text" plays a special role: a tag is allowed
        to have at most one field of type "text", and this is stored in the body
        of the tag, not as an attribute.

        Args:
          unused_handler: a request handler; if None is received, the request
            is being made by the system and there is no user in session; the
            minimal schema must be returned in this case; don't attempt to
            access course, app_context, file system, datastore, etc. in this
            case;  if a valid handler object is received, the request is being
            made by a real user and schema can have additional data binding in
            it; for example: 'select_data' can be computed and set by accessing
            course, app_context, filesyste, datastore, etc.

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
                    'value': str(message),
                    'visu': {
                        'visuType': 'funcName',
                        'funcName': 'disableSave'}}))
        return reg


class ContextAwareTag(BaseTag):
    """A tag which shares a context with other tags of the same type."""

    class Context(object):
        """Carries the environment and other data used by the tag."""

        def __init__(self, handler, env):
            """Initialize the context.

            Args:
                handler: controllers.utils.BaseHandler. The server runtime.
                env: dict. A dict of values shared shared between instances of
                    the tag on the same page. Values stored in this dict will be
                    available to subsequent calls to render() on the same page,
                    and to the call to rollup_header_footer() made at the end of
                    the page. Use this to store things like JS library refs
                    which can be de-dup'd and put in the header or footer.
            """
            self.handler = handler
            self.env = env

    def render(self, node, context):  # pylint: disable=W0613
        """Receive a node and return a node.

        Args:
            node: cElementTree.Element. The DOM node for the tag which should be
                rendered.
            context: Context. The context shared between instances of the tag.

        Returns:
            A cElementTree.Element holding the rendered DOM.
        """
        return super(ContextAwareTag, self).render(node, context.handler)

    def rollup_header_footer(self, context):
        """Roll up header and footer from data stored in the tag environment.

        This method is called once at the end of page processing. It receives
        the context object, which has been passed to all rendering methods for
        this tag on the page, and which accumulates data stored by the
        renderers.

        Args:
            context: Context. Holds data set in an environment dict by previous
                calls to render, containing, e.g., URLs of CSS or JS resources.

        Returns:
            A pair of cElementTree.Element's (header, footer).
        """
        pass


class ResourcesHandler(webapp2.RequestHandler):
    """Content handler for resources associated with custom tags."""

    def rebase_path(self, path):
        """Override this method to rebase the path to a different root."""
        return path

    def transform_resource(self, resource_str):
        """Override this method to apply a transforation to the resource."""
        return resource_str

    def get(self):
        """Respond to HTTP GET methods."""
        path = self.rebase_path(self.request.path)
        if path.startswith('/'):
            path = path[1:]
        path = os.path.normpath(path)

        resource_file = os.path.join(appengine_config.BUNDLE_ROOT, path)

        mimetype = mimetypes.guess_type(resource_file)[0]
        if mimetype is None:
            mimetype = 'application/octet-stream'

        try:
            self.response.status = 200
            self.response.cache_control.no_cache = None
            self.response.cache_control.public = 'public'
            self.response.cache_control.max_age = 600
            stream = open(resource_file)
            content = self.transform_resource(stream.read())
            self.response.headers['Content-Type'] = mimetype
            self.response.write(content)
        except IOError:
            self.error(404)


class DeprecatedResourcesHandler(ResourcesHandler):
    """Points "resources" urls at the new "_static" directory."""
    URL_PATTERN = re.compile(
        r'^/modules/(?P<module_name>[^/]*)/resources/(?P<asset>.*)$')
    PATH_TEMPLATE = '/modules/{module_name}/_static/{prefix}{asset}'
    WARNING_TEMPLATE = ('This URL is deprecated: %s.  Please use the new URL '
        'instead: %s')
    PREFIX = ''

    def rebase_path(self, path):
        match = self.URL_PATTERN.match(path)
        assert match
        new_path = self.PATH_TEMPLATE.format(
            module_name=match.group('module_name'),
            asset=match.group('asset'),
            prefix=self.PREFIX)
        logging.warning(self.WARNING_TEMPLATE, path, new_path)
        return new_path


def make_deprecated_resources_handler(prefix):
    class CustomDeprecatedResourcesHandler(DeprecatedResourcesHandler):
        PREFIX = prefix

    return CustomDeprecatedResourcesHandler


class JQueryHandler(ResourcesHandler):
    """A content handler which serves jQuery scripts wrapped in $.ready()."""

    def transform_resource(self, resource_str):
        return '$(function() {%s});' % resource_str


class IifeHandler(ResourcesHandler):
    """A content handler which serves JavaScript wrapped in an immediately
    invoked function expression (IIFE).
    """

    def transform_resource(self, resource_str):
        return '(function() {%s})();' % resource_str


class EditorBlacklists(object):
    """Lists tags which should not be supported by various editors."""

    COURSE_SCOPE = set()
    ASSESSMENT_SCOPE = set()
    DESCRIPTIVE_SCOPE = set()

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
    return dict(Registry.get_all_tags().items())


def html_string_to_element_tree(html_string, is_fragment=True):
    parser = html5lib.HTMLParser(
        tree=html5lib.treebuilders.getTreeBuilder('etree', cElementTree),
        namespaceHTMLElements=False)
    if is_fragment:
        # This returns the <div> element we wrap around the content.
        return parser.parseFragment('<div>%s</div>' % html_string)[0]
    else:
        # This returns the <html> element.
        return parser.parse(html_string)


def html_to_safe_dom(html_string, handler, render_custom_tags=True):
    """Render HTML text as a tree of safe_dom elements."""

    tag_bindings = get_tag_bindings()

    node_list = safe_dom.NodeList()
    if not html_string:
        return node_list

    # Set of all instance id's used in this dom tree, used to detect duplication
    used_instance_ids = set([])
    # A dictionary of environments, one for each tag type which appears in the
    # page
    tag_contexts = {}

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

    def _remove_namespace(tag_name):
        # Remove any namespacing which html5lib may have introduced. Html5lib
        # namespacing is of the form, e.g.,
        #     {http://www.w3.org/2000/svg}svg
        return re.sub(r'^\{[^\}]+\}', '', tag_name, count=1)

    def _process_html_tree(elt):
        """Recursively parses an HTML tree into a safe_dom.NodeList()."""
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
            if render_custom_tags and elt.tag in tag_bindings:
                tag = tag_bindings[elt.tag]()
                if isinstance(tag, ContextAwareTag):
                    # Get or initialize a environment dict for this type of tag.
                    # Each tag type gets a separate environment shared by all
                    # instances of that tag.
                    context = tag_contexts.get(elt.tag)
                    if context is None:
                        context = ContextAwareTag.Context(handler, {})
                        tag_contexts[elt.tag] = context
                    # Render the tag
                    elt = tag.render(elt, context)
                else:
                    # Render the tag
                    elt = tag.render(elt, handler)

            if elt.tag == cElementTree.Comment:
                out_elt = safe_dom.Comment()
            elif elt.tag.lower() == 'script':
                out_elt = safe_dom.ScriptElement()
            else:
                out_elt = safe_dom.Element(_remove_namespace(elt.tag))
            out_elt.add_attribute(**elt.attrib)

            if elt.text:
                out_elt.add_text(elt.text)
            for child in elt:
                out_elt.add_children(
                    _process_html_tree(child))

            node_list = safe_dom.NodeList()
            node_list.append(out_elt)
            if original_elt.tail:
                node_list.append(safe_dom.Text(original_elt.tail))
            return node_list

        except Exception as e:  # pylint: disable=broad-except
            logging.exception('Error handling tag: %s', elt.tag)
            return _generate_error_message_node_list(
                original_elt, '%s: %s' % (INVALID_HTML_TAG_MESSAGE, e))

    root = html_string_to_element_tree(html_string)
    if root.text:
        node_list.append(safe_dom.Text(root.text))

    for child_elt in root:
        node_list.append(_process_html_tree(child_elt))

    # After the page is processed, rollup any global header/footer data which
    # the environment-aware tags have accumulated in their env's
    for tag_name, context in tag_contexts.items():
        header, footer = tag_bindings[tag_name]().rollup_header_footer(context)
        node_list.insert(0, _process_html_tree(header))
        node_list.append(_process_html_tree(footer))

    return node_list


def get_components_from_html(html, use_lxml=_LXML_AVAILABLE):
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
    if use_lxml:
        return get_components_using_lxml(html)
    else:
        return get_components_using_html5lib(html)


def get_components_using_html5lib(html):
    """Find lesson components using the pure python html5lib library."""

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


def get_components_using_lxml(html):
    """Find lesson components using the fast C-binding lxml library."""

    content = lxml.html.fromstring('<div>%s</div>' % html)
    components = []
    for component in content.xpath('.//*[@instanceid]'):
        component_dict = {'cpt_name': component.tag}
        component_dict.update(component.attrib)
        components.append(component_dict)
    return components
