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
import urllib
from controllers import sites
from controllers.utils import BaseRESTHandler
from controllers.utils import XsrfTokenManager
from models import config
from models import courses
from models import models
from models import roles
from models import transforms
from modules.oeditor import oeditor
from google.appengine.api import users
from google.appengine.ext import db


# This is a template because the value type is not yet known.
SCHEMA_JSON_TEMPLATE = """
    {
        "id": "Configuration Property",
        "type": "object",
        "description": "Configuration Property Override",
        "properties": {
            "name" : {"type": "string"},
            "value": {"optional": true, "type": "%s"},
            "is_draft": {"type": "boolean"}
            }
    }
    """

# This is a template because the doc_string is not yet known.
SCHEMA_ANNOTATIONS_TEMPLATE = [
    (['title'], 'Configuration Property Override'),
    (['properties', 'name', '_inputex'], {
        'label': 'Name', '_type': 'uneditable'}),
    oeditor.create_bool_select_annotation(
        ['properties', 'is_draft'], 'Status', 'Pending', 'Active',
        description='<strong>Active</strong>: This value is active and '
        'overrides all other defaults.<br/><strong>Pending</strong>: This '
        'value is not active yet, and the default settings still apply.')]


class ConfigPropertyRights(object):
    """Manages view/edit rights for configuration properties."""

    @classmethod
    def can_view(cls):
        return cls.can_edit()

    @classmethod
    def can_edit(cls):
        return roles.Roles.is_super_admin()

    @classmethod
    def can_delete(cls):
        return cls.can_edit()

    @classmethod
    def can_add(cls):
        return cls.can_edit()


class ConfigPropertyEditor(object):
    """An editor for any configuration property."""

    # Map of configuration property type into inputex type.
    type_map = {str: 'string', int: 'integer', bool: 'boolean'}

    @classmethod
    def get_schema_annotations(cls, config_property):
        """Gets editor specific schema annotations."""
        doc_string = '%s Default: \'%s\'.' % (
            config_property.doc_string, config_property.default_value)
        item_dict = [] + SCHEMA_ANNOTATIONS_TEMPLATE
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
        return SCHEMA_JSON_TEMPLATE % cls.get_value_type(config_property)

    def get_add_course(self):
        """Handles 'add_course' action and renders new course entry editor."""

        exit_url = '/admin?action=courses'
        rest_url = CoursesItemRESTHandler.URI

        template_values = {}
        template_values[
            'page_title'] = 'Course Builder - Add Course'
        template_values['main_content'] = oeditor.ObjectEditor.get_html_for(
            self, CoursesItemRESTHandler.SCHEMA_JSON,
            CoursesItemRESTHandler.SCHEMA_ANNOTATIONS_DICT,
            None, rest_url, exit_url,
            auto_return=True,
            save_button_caption='Add New Course')

        self.render_page(template_values)

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
            'page_title'] = 'Course Builder - Edit Settings'

        exit_url = '/admin?action=settings#%s' % cgi.escape(key)
        rest_url = '/rest/config/item'
        delete_url = '/admin?%s' % urllib.urlencode({
            'action': 'config_reset',
            'name': key,
            'xsrf_token': cgi.escape(self.create_xsrf_token('config_reset'))})

        template_values['main_content'] = oeditor.ObjectEditor.get_html_for(
            self, ConfigPropertyEditor.get_schema_json(item),
            ConfigPropertyEditor.get_schema_annotations(item),
            key, rest_url, exit_url, delete_url=delete_url)

        self.render_page(template_values)

    def post_config_override(self):
        """Handles 'override' property action."""
        name = self.request.get('name')

        # Find item in registry.
        item = None
        if name and name in config.Registry.registered.keys():
            item = config.Registry.registered[name]
        if not item:
            self.redirect('/admin?action=settings')

        # Add new entity if does not exist.
        try:
            entity = config.ConfigPropertyEntity.get_by_key_name(name)
        except db.BadKeyError:
            entity = None
        if not entity:
            entity = config.ConfigPropertyEntity(key_name=name)
            entity.value = str(item.value)
            entity.is_draft = True
            entity.put()

        models.EventEntity.record(
            'override-property', users.get_current_user(), transforms.dumps({
                'name': name, 'value': str(entity.value)}))

        self.redirect('/admin?%s' % urllib.urlencode(
            {'action': 'config_edit', 'name': name}))

    def post_config_reset(self):
        """Handles 'reset' property action."""
        name = self.request.get('name')

        # Find item in registry.
        item = None
        if name and name in config.Registry.registered.keys():
            item = config.Registry.registered[name]
        if not item:
            self.redirect('/admin?action=settings')

        # Delete if exists.
        try:
            entity = config.ConfigPropertyEntity.get_by_key_name(name)
            if entity:
                old_value = entity.value
                entity.delete()

                models.EventEntity.record(
                    'delete-property', users.get_current_user(),
                    transforms.dumps({
                        'name': name, 'value': str(old_value)}))

        except db.BadKeyError:
            pass

        self.redirect('/admin?action=settings')


class CoursesItemRESTHandler(BaseRESTHandler):
    """Provides REST API for course entries."""

    URI = '/rest/courses/item'

    SCHEMA_JSON = """
        {
            "id": "Course Entry",
            "type": "object",
            "description": "Course Entry",
            "properties": {
                "name": {"type": "string"},
                "title": {"type": "string"},
                "admin_email": {"type": "string"}
                }
        }
        """

    SCHEMA_DICT = transforms.loads(SCHEMA_JSON)

    SCHEMA_ANNOTATIONS_DICT = [
        (['title'], 'New Course Entry'),
        (['properties', 'name', '_inputex'], {'label': 'Unique Name'}),
        (['properties', 'title', '_inputex'], {'label': 'Course Title'}),
        (['properties', 'admin_email', '_inputex'], {
            'label': 'Course Admin Email'})]

    def get(self):
        """Handles HTTP GET verb."""
        if not ConfigPropertyRights.can_view():
            transforms.send_json_response(
                self, 401, 'Access denied.')
            return

        transforms.send_json_response(
            self, 200, 'Success.',
            payload_dict={
                'name': 'new_course',
                'title': 'My New Course',
                'admin_email': self.get_user().email()},
            xsrf_token=XsrfTokenManager.create_xsrf_token(
                'add-course-put'))

    def put(self):
        """Handles HTTP PUT verb."""
        request = transforms.loads(self.request.get('request'))
        if not self.assert_xsrf_token_or_fail(
                request, 'add-course-put', {}):
            return

        if not ConfigPropertyRights.can_edit():
            transforms.send_json_response(
                self, 401, 'Access denied.')
            return

        payload = request.get('payload')
        json_object = transforms.loads(payload)
        name = json_object.get('name')
        title = json_object.get('title')
        admin_email = json_object.get('admin_email')

        # Add the new course entry.
        errors = []
        entry = sites.add_new_course_entry(name, title, admin_email, errors)
        if not entry:
            errors.append('Error adding a new course entry.')
        if errors:
            transforms.send_json_response(self, 412, '\n'.join(errors))
            return

        # We can't expect our new configuration being immediately available due
        # to datastore queries consistency limitations. So we will instantiate
        # our new course here and not use the normal sites.get_all_courses().
        app_context = sites.get_all_courses(entry)[0]

        # Update course with a new title and admin email.
        new_course = courses.Course(None, app_context=app_context)
        if not new_course.init_new_course_settings(title, admin_email):
            transforms.send_json_response(
                self, 412,
                'Added new course entry, but failed to update title and/or '
                'admin email. The course.yaml file already exists and must be '
                'updated manually.')
            return

        transforms.send_json_response(
            self, 200, 'Added.', {'entry': entry})


class ConfigPropertyItemRESTHandler(BaseRESTHandler):
    """Provides REST API for a configuration property."""

    def get(self):
        """Handles REST GET verb and returns an object as JSON payload."""
        key = self.request.get('key')
        if not ConfigPropertyRights.can_view():
            transforms.send_json_response(
                self, 401, 'Access denied.', {'key': key})
            return

        item = None
        if key and key in config.Registry.registered.keys():
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
            entity_dict = {'name': key, 'is_draft': entity.is_draft}
            entity_dict['value'] = transforms.string_to_value(
                entity.value, item.value_type)
            json_payload = transforms.dict_to_json(
                entity_dict,
                transforms.loads(
                    ConfigPropertyEditor.get_schema_json(item)))
            transforms.send_json_response(
                self, 200, 'Success.',
                payload_dict=json_payload,
                xsrf_token=XsrfTokenManager.create_xsrf_token(
                    'config-property-put'))

    def put(self):
        """Handles REST PUT verb with JSON payload."""
        request = transforms.loads(self.request.get('request'))
        key = request.get('key')

        if not self.assert_xsrf_token_or_fail(
                request, 'config-property-put', {'key': key}):
            return

        if not ConfigPropertyRights.can_edit():
            transforms.send_json_response(
                self, 401, 'Access denied.', {'key': key})
            return

        item = None
        if key and key in config.Registry.registered.keys():
            item = config.Registry.registered[key]
        if not item:
            self.redirect('/admin?action=settings')

        try:
            entity = config.ConfigPropertyEntity.get_by_key_name(key)
        except db.BadKeyError:
            transforms.send_json_response(
                self, 404, 'Object not found.', {'key': key})
            return

        payload = request.get('payload')
        json_object = transforms.loads(payload)
        new_value = item.value_type(json_object['value'])

        # Validate the value.
        errors = []
        if item.validator:
            item.validator(new_value, errors)
        if errors:
            transforms.send_json_response(self, 412, '\n'.join(errors))
            return

        # Update entity.
        old_value = entity.value
        entity.value = str(new_value)
        entity.is_draft = json_object['is_draft']
        entity.put()

        models.EventEntity.record(
            'put-property', users.get_current_user(), transforms.dumps({
                'name': key,
                'before': str(old_value), 'after': str(entity.value)}))

        transforms.send_json_response(self, 200, 'Saved.')
