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
import appengine_config
from common import jinja_filters
from common import tags
from controllers import utils
import jinja2
from models import transforms
import webapp2

# a set of YUI and inputex modules required by the editor
COMMON_REQUIRED_MODULES = [
    'inputex-group', 'inputex-form', 'inputex-jsonschema']

ALL_MODULES = [
    'querystring-stringify-simple', 'inputex-select', 'inputex-string',
    'inputex-radio', 'inputex-date', 'inputex-datepicker', 'inputex-checkbox',
    'inputex-list', 'inputex-color', 'gcb-rte', 'inputex-textarea',
    'inputex-url', 'inputex-uneditable', 'inputex-integer', 'inputex-hidden',
    'inputex-file', 'io-upload-iframe']


class ObjectEditor(object):
    """Generic object editor powered by jsonschema."""

    @classmethod
    def get_html_for(
        cls, handler, schema_json, annotations, object_key,
        rest_url, exit_url,
        extra_args=None,
        save_method='put',
        delete_url=None, delete_method='post',
        auto_return=False, read_only=False,
        required_modules=None, save_button_caption='Save',
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
            delete_method: optional HTTP method for delete operation
            auto_return: whether to return to the exit_url on successful save
            read_only: optional flag; if set, removes Save and Delete operations
            required_modules: list of inputex modules required for this editor
            save_button_caption: a caption for the 'Save' button
            exit_button_caption: a caption for the 'Close' button

        Returns:
            The HTML, JS and CSS text that will instantiate an object editor.
        """
        required_modules = required_modules or ALL_MODULES

        # extract label
        type_label = transforms.loads(schema_json).get('description')
        if not type_label:
            type_label = 'Generic Object'

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

        template_values = {
            'schema': schema_json,
            'type_label': type_label,
            'get_url': '%s?%s' % (get_url, urllib.urlencode(get_args, True)),
            'save_url': post_url,
            'save_args': transforms.dumps(post_args),
            'exit_button_caption': exit_button_caption,
            'exit_url': exit_url,
            'required_modules': COMMON_REQUIRED_MODULES + required_modules,
            'schema_annotations': [
                (item[0], transforms.dumps(item[1])) for item in annotations],
            'save_method': save_method,
            'auto_return': auto_return,
            'save_button_caption': save_button_caption,
            'custom_rte_tag_icons': transforms.dumps(custom_rte_tag_icons)
            }

        if delete_url and not read_only:
            template_values['delete_url'] = delete_url
        if delete_method:
            template_values['delete_method'] = delete_method
        if appengine_config.BUNDLE_LIB_FILES:
            template_values['bundle_lib_files'] = True

        return jinja2.utils.Markup(handler.get_template(
            'oeditor.html', [os.path.dirname(__file__)]
        ).render(template_values))


class PopupHandler(webapp2.RequestHandler, utils.ReflectiveRequestHandler):
    """A handler to serve the content of the popup subeditor."""

    default_action = 'custom_tag'
    get_actions = ['custom_tag']
    post_actions = []

    def get_template(self, template_name, dirs):
        """Sets up an environment and Gets jinja template."""

        jinja_environment = jinja2.Environment(
            autoescape=True, finalize=jinja_filters.finalize,
            loader=jinja2.FileSystemLoader(dirs + [os.path.dirname(__file__)]))
        jinja_environment.filters['js_string'] = jinja_filters.js_string

        return jinja_environment.get_template(template_name)

    def get_custom_tag(self):
        """Return the the page used to edit a custom HTML tag in a popup."""
        tag_name = self.request.get('tag_name')
        tag_bindings = tags.get_tag_bindings()
        tag_class = tag_bindings[tag_name]
        schema = tag_class().get_schema()
        if schema.has_subregistries():
            raise NotImplementedError()

        template_values = {}
        template_values['form_html'] = ObjectEditor.get_html_for(
            self, schema.get_json_schema(), schema.get_schema_dict(), None,
            None, None)
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
