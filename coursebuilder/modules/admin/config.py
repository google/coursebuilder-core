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

"""Classes supporting configuration property editor and REST operations."""

__author__ = 'Pavel Simakov (psimakov@google.com)'

import cgi
import json
from models import config
from models import transforms
from modules.oeditor.oeditor import ObjectEditor
import webapp2
from google.appengine.ext import db


class ConfigPropertyEditor(object):
    """An editor for any configuration property."""

    # Map of configuration property type into inputex type.
    type_map = {str: 'string', int: 'integer', bool: 'boolean'}

    # This is a template because the value type is not yet known.
    schema_json_template = """
        {
            "id": "Configuration Property",
            "type": "object",
            "description": "Configuration Property",
            "properties": {
                "name" : {"type": "string"},
                "value": {"optional": true, "type": "%s"},
                "is_draft": {"type": "boolean"}
                }
        }
        """

    # This is a template because the doc_string is not yet known.
    schema_annotations = [
        (['title'], 'Configuration Property'),
        (['properties', 'name', '_inputex'], {
            'label': 'Name', '_type': 'uneditable'}),
        (['properties', 'is_draft', '_inputex'], {'label': 'Is Draft'})]

    @classmethod
    def get_schema_annotations(cls, config_property):
        """Gets editor specific schema annotations."""
        doc_string = '%s Default: \'%s\'.' % (
            config_property.doc_string, config_property.default_value)
        item_dict = [] + cls.schema_annotations
        item_dict.append((
            ['properties', 'value', '_inputex'], {
                'label': 'Value', '_type': '%s' % cls.get_value_type(
                    config_property),
                'description': doc_string}))
        return item_dict

    @classmethod
    def get_value_type(cls, config_property):
        """Gets an editor specific type for the property."""
        value_type = cls.type_map[config_property.value_type]
        if not value_type:
            raise Exception('Unknown type: %s', config_property.value_type)
        if config_property.value_type == str and config_property.multiline:
            return 'text'
        return value_type

    @classmethod
    def get_schema_json(cls, config_property):
        """Gets JSON schema for configuration property."""
        return cls.schema_json_template % cls.get_value_type(config_property)

    def get_config_edit(self):
        """Handles 'edit' property action."""

        key = self.request.get('name')
        if not key:
            self.redirect('/admin?action=settings')

        item = config.Registry.registered[key]
        if not item:
            self.redirect('/admin?action=settings')

        template_values = {}
        template_values[
            'page_title'] = 'Course Builder - Editing \'%s\'' % cgi.escape(key)

        exit_url = '/admin?action=settings#%s' % cgi.escape(key)
        rest_url = '/rest/config/item'
        template_values['main_content'] = ObjectEditor.get_html_for(
            self, ConfigPropertyEditor.get_schema_json(item),
            ConfigPropertyEditor.get_schema_annotations(item),
            key, rest_url, exit_url)

        self.render_page(template_values)

    def get_config_override(self):
        """Handles 'override' property action."""
        # TODO(psimakov): incomplete


class ItemRESTHandler(webapp2.RequestHandler):
    """Provides REST API for a configuration property."""

    def get(self):
        """Handles REST GET verb and returns an object as JSON payload."""
        key = self.request.get('key')
        item = config.Registry.registered[key]
        if not item:
            self.redirect('/admin?action=settings')

        try:
            entity = config.ConfigPropertyEntity.get_by_key_name(key)
        except db.BadKeyError:
            entity = None

        if not entity:
            transforms.send_json_response(
                self, 404, 'Object not found.', {'key': key})
        else:
            entity_dict = transforms.entity_to_dict(entity)
            entity_dict['name'] = key
            json_payload = transforms.dict_to_json(
                entity_dict,
                json.loads(ConfigPropertyEditor.get_schema_json(item)))
            transforms.send_json_response(self, 200, 'Success.', json_payload)

    def put(self):
        """Handles REST PUT verb with JSON payload."""
        # TODO(psimakov): incomplete
