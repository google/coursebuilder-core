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

"""Generic object editor view that uses REST services."""

__author__ = 'Pavel Simakov (psimakov@google.com)'

import os
import urllib

import jinja2
import webapp2

import appengine_config
from common import jinja_utils
from common import schema_fields
from common import tags
from controllers import utils
from models import custom_modules
from models import transforms
from models.config import ConfigProperty

# a set of YUI and inputex modules required by the editor
COMMON_REQUIRED_MODULES = [
    'inputex-group', 'inputex-form', 'inputex-jsonschema']

ALL_MODULES = [
    'querystring-stringify-simple', 'inputex-select', 'inputex-string',
    'inputex-radio', 'inputex-date', 'inputex-datepicker', 'inputex-checkbox',
    'inputex-list', 'inputex-color', 'gcb-rte', 'inputex-textarea',
    'inputex-url', 'inputex-uneditable', 'inputex-integer', 'inputex-hidden',
    'inputex-file', 'io-upload-iframe']

RESOURCES_PATH = '/modules/oeditor/resources'

# Global code syntax highlighter controls.
CAN_HIGHLIGHT_CODE = ConfigProperty(
    'gcb_can_highlight_code', bool, (
        'Whether or not to highlight code syntax '
        'in Dashboard editors and displays.'),
    True)


class ObjectEditor(object):
    """Generic object editor powered by jsonschema."""

    # Modules can add extra script tags to the oeditor page by registering a
    # callback function here. The callback function will receive the app_context
    # as an argument, and should return an iterable of strings, each of which is
    # the URL of a script library.
    EXTRA_SCRIPT_TAG_URLS = []

    @classmethod
    def get_html_for(
        cls, handler, schema_json, annotations, object_key,
        rest_url, exit_url,
        extra_args=None,
        save_method='put',
        delete_url=None, delete_message=None, delete_method='post',
        auto_return=False, read_only=False,
        required_modules=None,
        extra_css_files=None,
        extra_js_files=None,
        additional_dirs=None,
        delete_button_caption='Delete',
        save_button_caption='Save',
        exit_button_caption='Close'):
        """Creates an HTML code needed to embed and operate this form.

        This method creates an HTML, JS and CSS  required to embed JSON
        schema-based object editor into a view.

        Args:
            handler: a BaseHandler class, which will host this HTML, JS and CSS
            schema_json: a text of JSON schema for the object being edited
            annotations: schema annotations dictionary
            object_key: a key of an object being edited
            rest_url: a REST endpoint for object GET/PUT operation
            exit_url: a URL to go to after the editor form is dismissed
            extra_args: extra request params passed back in GET and POST
            save_method: how the data should be saved to the server (put|upload)
            delete_url: optional URL for delete operation
            delete_message: string. Optional custom delete confirmation message
            delete_method: optional HTTP method for delete operation
            auto_return: whether to return to the exit_url on successful save
            read_only: optional flag; if set, removes Save and Delete operations
            required_modules: list of inputex modules required for this editor
            extra_css_files: list of extra CSS files to be included
            extra_js_files: list of extra JS files to be included
            additional_dirs: list of extra directories to look for
                Jinja template files, e.g., JS or CSS files included by modules.
            delete_button_caption: string. A caption for the 'Delete' button
            save_button_caption: a caption for the 'Save' button
            exit_button_caption: a caption for the 'Close' button

        Returns:
            The HTML, JS and CSS text that will instantiate an object editor.
        """
        required_modules = required_modules or ALL_MODULES

        if not delete_message:
            kind = transforms.loads(schema_json).get('description')
            if not kind:
                kind = 'Generic Object'
            delete_message = 'Are you sure you want to delete this %s?' % kind

        # construct parameters
        get_url = rest_url
        get_args = {'key': object_key}
        post_url = rest_url
        post_args = {'key': object_key}

        if extra_args:
            get_args.update(extra_args)
            post_args.update(extra_args)

        if read_only:
            post_url = ''
            post_args = ''

        custom_rte_tag_icons = []
        for tag, tag_class in tags.get_tag_bindings().items():
            custom_rte_tag_icons.append({
                'name': tag,
                'iconUrl': tag_class().get_icon_url()})

        extra_script_tag_urls = []
        for callback in cls.EXTRA_SCRIPT_TAG_URLS:
            for url in callback():
             extra_script_tag_urls.append(url)

        template_values = {
            'enabled': custom_module.enabled,
            'schema': schema_json,
            'get_url': '%s?%s' % (get_url, urllib.urlencode(get_args, True)),
            'save_url': post_url,
            'save_args': transforms.dumps(post_args),
            'exit_button_caption': exit_button_caption,
            'exit_url': jinja2.Markup(exit_url),  # suppress & -> &amp; in url
            'required_modules': COMMON_REQUIRED_MODULES + required_modules,
            'extra_css_files': extra_css_files or [],
            'extra_js_files': extra_js_files or [],
            'schema_annotations': [
                (item[0], transforms.dumps(item[1])) for item in annotations],
            'save_method': save_method,
            'auto_return': auto_return,
            'delete_button_caption': delete_button_caption,
            'save_button_caption': save_button_caption,
            'custom_rte_tag_icons': transforms.dumps(custom_rte_tag_icons),
            'delete_message': delete_message,
            'can_highlight_code': CAN_HIGHLIGHT_CODE.value,
            'extra_script_tag_urls': extra_script_tag_urls,
        }

        if delete_url and not read_only:
            template_values['delete_url'] = delete_url
        if delete_method:
            template_values['delete_method'] = delete_method
        if appengine_config.BUNDLE_LIB_FILES:
            template_values['bundle_lib_files'] = True

        return jinja2.utils.Markup(handler.get_template('oeditor.html', (
            [os.path.dirname(__file__)] + (additional_dirs or [])
        )).render(template_values))


class PopupHandler(webapp2.RequestHandler, utils.ReflectiveRequestHandler):
    """A handler to serve the content of the popup subeditor."""

    default_action = 'custom_tag'
    get_actions = ['edit_custom_tag', 'add_custom_tag']
    post_actions = []

    def get_template(self, template_name, dirs):
        """Sets up an environment and Gets jinja template."""
        return jinja_utils.get_template(
            template_name, dirs + [os.path.dirname(__file__)])

    def _validate_schema(self, tag, schema):
        if schema.has_subregistries():
            return tag.unavailable_schema(
                'This tag has an invalid schema and cannot be edited. '
                'Only simple field types are allowed.')

        text_field_count = 0
        index = schema_fields.FieldRegistryIndex(schema)
        index.rebuild()
        for name in index.names_in_order:
            if index.find(name).type == 'text':
                text_field_count += 1
        if text_field_count > 1:
            return tag.unavailable_schema(
                'This tag has an invalid schema and cannot be edited. '
                'Only one field of type "text" is allowed.')

        return schema

    def get_edit_custom_tag(self):
        """Return the the page used to edit a custom HTML tag in a popup."""
        tag_name = self.request.get('tag_name')
        tag_bindings = tags.get_tag_bindings()
        tag_class = tag_bindings[tag_name]
        tag = tag_class()
        schema = tag.get_schema(self)
        schema = self._validate_schema(tag, schema)

        template_values = {}
        template_values['form_html'] = ObjectEditor.get_html_for(
            self, schema.get_json_schema(), schema.get_schema_dict(), None,
            None, None,
            required_modules=tag_class.required_modules(),
            extra_js_files=tag_class.extra_js_files(),
            extra_css_files=tag_class.extra_css_files(),
            additional_dirs=tag_class.additional_dirs())
        self.response.out.write(
            self.get_template('popup.html', []).render(template_values))

    def get_add_custom_tag(self):
        """Return the page for the popup used to add a custom HTML tag."""
        tag_name = self.request.get('tag_name')
        excluded_tags = self.request.get_all('excluded_tags')

        tag_bindings = tags.get_tag_bindings()

        select_data = []
        for name in tag_bindings.keys():
            if name not in excluded_tags:
                clazz = tag_bindings[name]
                select_data.append((name, '%s: %s' % (
                    clazz.vendor(), clazz.name())))
        select_data = sorted(select_data, key=lambda pair: pair[1])

        if tag_name:
            tag_class = tag_bindings[tag_name]
        else:
            tag_class = tag_bindings[select_data[0][0]]
        tag = tag_class()
        tag_schema = tag.get_schema(self)
        tag_schema = self._validate_schema(tag, tag_schema)

        schema = schema_fields.FieldRegistry('Add a Component')
        type_select = schema.add_sub_registry('type', 'Component Type')
        type_select.add_property(schema_fields.SchemaField(
            'tag', 'Name', 'string', select_data=select_data))
        schema.add_sub_registry('attributes', registry=tag_schema)

        template_values = {}
        template_values['form_html'] = ObjectEditor.get_html_for(
            self, schema.get_json_schema(), schema.get_schema_dict(), None,
            None, None,
            required_modules=tag_class.required_modules(),
            extra_js_files=['add_custom_tag.js'] + tag_class.extra_js_files(),
            extra_css_files=tag_class.extra_css_files(),
            additional_dirs=tag_class.additional_dirs())
        self.response.out.write(
            self.get_template('popup.html', []).render(template_values))


def create_bool_select_annotation(
    keys_list, label, true_label, false_label, class_name=None,
    description=None):
    """Creates inputex annotation to display bool type as a select."""
    properties = {
        'label': label, 'choices': [
            {'value': True, 'label': true_label},
            {'value': False, 'label': false_label}]}
    if class_name:
        properties['className'] = class_name
    if description:
        properties['description'] = description
    return (keys_list, {'type': 'select', '_inputex': properties})


custom_module = None


def register_module():
    """Registers this module in the registry."""

    from controllers import sites  # pylint: disable-msg=g-import-not-at-top

    yui_handlers = [
        ('/static/inputex-3.1.0/(.*)', sites.make_zip_handler(
            os.path.join(
                appengine_config.BUNDLE_ROOT, 'lib/inputex-3.1.0.zip'))),
        ('/static/yui_3.6.0/(.*)', sites.make_zip_handler(
            os.path.join(
                appengine_config.BUNDLE_ROOT, 'lib/yui_3.6.0.zip'))),
        ('/static/2in3/(.*)', sites.make_zip_handler(
            os.path.join(
                appengine_config.BUNDLE_ROOT, 'lib/yui_2in3-2.9.0.zip')))]

    codemirror_handler = [
        ('/static/codemirror/(.*)', sites.make_zip_handler(
            os.path.join(
                appengine_config.BUNDLE_ROOT, 'lib/codemirror-4.5.0.zip')))]

    if appengine_config.BUNDLE_LIB_FILES:
        yui_handlers += [
            ('/static/combo/inputex', sites.make_css_combo_zip_handler(
                os.path.join(
                    appengine_config.BUNDLE_ROOT, 'lib/inputex-3.1.0.zip'),
                '/static/inputex-3.1.0/')),
            ('/static/combo/yui', sites.make_css_combo_zip_handler(
                os.path.join(appengine_config.BUNDLE_ROOT, 'lib/yui_3.6.0.zip'),
                '/yui/')),
            ('/static/combo/2in3', sites.make_css_combo_zip_handler(
                os.path.join(
                    appengine_config.BUNDLE_ROOT, 'lib/yui_2in3-2.9.0.zip'),
                '/static/2in3/'))]

    oeditor_handlers = [('/oeditorpopup', PopupHandler)]
    global_routes = yui_handlers + codemirror_handler + [
        (os.path.join(RESOURCES_PATH, '.*'), tags.ResourcesHandler)]

    global custom_module
    custom_module = custom_modules.Module(
        'Object Editor',
        'A visual editor for editing various types of objects.',
        global_routes, oeditor_handlers)
    return custom_module
