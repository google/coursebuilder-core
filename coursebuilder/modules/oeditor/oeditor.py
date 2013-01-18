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

import json
import os
import urllib

# a set of YUI and inputex modules required by the editor; need to be optimized
# to load what is needed for a specific schema; for now we use a static list
REQUIRED_MODULES = """
    "querystring-stringify-simple",
    "inputex-group", "inputex-select", "inputex-string", "inputex-form",
    "inputex-radio", "inputex-date", "inputex-datepicker", "inputex-jsonschema",
    "inputex-checkbox", "inputex-list", "inputex-color", "inputex-rte",
    "inputex-textarea", "inputex-uneditable", "inputex-integer"
    """


class ObjectEditor(object):
    """Generic object editor powered by jsonschema."""

    @classmethod
    def format_annotations(cls, annotations):
        """Formats annotations into JavaScript.

        An annotation is a tuple of two elements. The first element is a
        list of key names forming xpath of a target schema element. The second
        is a dictionary, items of which must be attached to the target element.

        Args:
            annotations: an array of annotations

        Returns:
            The JavaScript representation of the annotations.
        """
        annotations_lines = []
        for item in annotations:
            path = []
            for element in item[0]:
                path.append('[\'%s\']' % element)
            annotations_lines.append('schema.root%s = %s;' % (
                ''.join(path), json.dumps(item[1])))
        return '\n'.join(annotations_lines)

    @classmethod
    def get_html_for(
        cls, handler, schema_json, annotations, object_key, rest_url, exit_url,
        delete_url=None):
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
            delete_url: optional URL for delete POST operation

        Returns:
            The HTML, JS and CSS text that will instantiate an object editor.
        """

        # extract label
        type_label = json.loads(schema_json)['description']
        if not type_label:
            type_label = 'Generic Object'

        # construct parameters
        get_url = rest_url
        get_args = {'key': object_key}
        post_url = rest_url
        post_args = {'key': object_key}

        template_values = {
            'schema': schema_json,
            'type_label': type_label,
            'get_url': '%s?%s' % (get_url, urllib.urlencode(get_args, True)),
            'save_url': post_url,
            'save_args': json.dumps(post_args),
            'exit_url': exit_url,
            'required_modules': REQUIRED_MODULES,
            'schema_annotations': cls.format_annotations(annotations)
            }

        if delete_url:
            template_values['delete_url'] = delete_url

        return handler.get_template(
            'oeditor.html', [os.path.dirname(__file__)]).render(template_values)


def create_bool_select_annotation(
    keys_list, label, true_label, false_label, description=None):
    """Creates inputex annotation to display bool type as a select."""
    properties = {
        'label': label, 'choices': [
            {'value': True, 'label': true_label},
            {'value': False, 'label': false_label}]}
    if description:
        properties['description'] = description
    return (keys_list, {'type': 'select', '_inputex': properties})
