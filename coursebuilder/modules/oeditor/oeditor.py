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


class ObjectEditor(object):
    """Generic object editor powered by jsonschema."""

    @classmethod
    def get_html_for(cls, handler, schema, object_key, rest_provider_url):
        """Creates an HTML code needed to embed and operate this form.

        This method creates an HTML, JS and CSS  required to embed JSON
        schema-based object editor into a view.

        Args:
            handler: a BaseHandler class, which will host this HTML, JS and CSS
            schema: a JSON schema dictionary for the object being edited
            object_key: a key of an object being edited
            rest_provider_url: a REST endpoint for object GET/PUT operation

        Returns:
            The HTML, JS and CSS text that will instantiate an object editor.
        """

        type_label = schema['description']

        get_url = rest_provider_url
        get_args = {'key': object_key}
        post_url = rest_provider_url
        post_args = {'key': object_key}

        template_values = {
            'schema': json.dumps(schema),
            'type_label': type_label,
            'get_url': '%s?%s' % (get_url, urllib.urlencode(get_args, True)),
            'post_url': post_url,
            'post_args': json.dumps(post_args)
        }

        return handler.get_template(
            'oeditor.html', [os.path.dirname(__file__)]).render(template_values)
