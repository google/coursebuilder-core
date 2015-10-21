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
import logging
import urllib

import appengine_config
from common import crypto
from common import users
from common import utils as common_utils
from controllers import sites
from controllers import utils
from models import config
from models import courses
from models import entities
from models import models
from models import roles
from models import transforms
from modules.oeditor import oeditor

from google.appengine.api import namespace_manager
from google.appengine.ext import db
from google.appengine.ext import deferred
from google.appengine.ext.db import metadata

# This is a template because the value type is not yet known.
SCHEMA_JSON_TEMPLATE = """
    {
        "id": "Configuration Property",
        "type": "object",
        "description": "Configuration Property Override",
        "properties": {
            "label" : {"optional": true, "type": "string"},
            "name" : {"optional": true, "type": "string"},
            "value": {"optional": true, "type": "%s"},
            "is_draft": {"optional": true, "type": "boolean"}
        }
    }
    """

# This is a template because the doc_string is not yet known.
SCHEMA_ANNOTATIONS_TEMPLATE = [
    (['title'], 'Configuration Property Override'),
    (['properties', 'label', '_inputex'], {
        'label': 'Setting Name', '_type': 'uneditable'}),
    (['properties', 'name', '_inputex'], {
        'label': 'Internal Name', '_type': 'uneditable'}),
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

    def get_config_edit(self):
        """Handles 'edit' property action."""

        key = self.request.get('name')
        if not key:
            self.redirect('%s?action=settings' % self.URL)

        item = config.Registry.registered[key]
        if not item:
            self.redirect('%s?action=settings' % self.URL)

        template_values = {}
        template_values['page_title'] = self.format_title('Edit Settings')

        exit_url = '%s?action=settings#%s' % (
            self.LINK_URL, cgi.escape(key))
        rest_url = '/rest/config/item'
        delete_url = '%s?%s' % (
            self.LINK_URL,
            urllib.urlencode({
                'action': 'config_reset',
                'name': key,
                'xsrf_token': cgi.escape
                    (self.create_xsrf_token('config_reset'))}))

        template_values['main_content'] = oeditor.ObjectEditor.get_html_for(
            self, ConfigPropertyEditor.get_schema_json(item),
            ConfigPropertyEditor.get_schema_annotations(item),
            key, rest_url, exit_url, delete_url=delete_url)

        self.render_page(template_values, in_action='settings')

    def post_config_override(self):
        """Handles 'override' property action."""
        name = self.request.get('name')

        # Find item in registry.
        item = None
        if name and name in config.Registry.registered.keys():
            item = config.Registry.registered[name]
        if not item:
            self.redirect('?action=settings' % self.LINK_URL)

        with common_utils.Namespace(appengine_config.DEFAULT_NAMESPACE_NAME):
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
                'override-property', users.get_current_user(),
                transforms.dumps({
                    'name': name, 'value': str(entity.value)}))

        self.redirect('%s?%s' % (self.URL, urllib.urlencode(
            {'action': 'config_edit', 'name': name})))

    def post_config_reset(self):
        """Handles 'reset' property action."""
        name = self.request.get('name')

        # Find item in registry.
        item = None
        if name and name in config.Registry.registered.keys():
            item = config.Registry.registered[name]
        if not item:
            self.redirect('%s?action=settings' % self.LINK_URL)

        with common_utils.Namespace(appengine_config.DEFAULT_NAMESPACE_NAME):
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

        self.redirect('%s?action=settings' % self.URL)


class CoursesPropertyRights(object):
    """Manages view/edit rights for configuration properties."""

    @classmethod
    def can_add(cls):
        if roles.Roles.is_super_admin():
            return True
        for course_context in sites.get_all_courses():
            if roles.Roles.is_course_admin(course_context):
                return True
        return False


class CoursesItemRESTHandler(utils.BaseRESTHandler):
    """Provides REST API for course entries."""

    # Enable other modules to make changes to sample course import.
    # Each member must be a function of the form:
    #     callback(course, errors)
    COPY_SAMPLE_COURSE_HOOKS = []

    URI = '/rest/courses/item'
    XSRF_ACTION = 'add-course-put'

    def put(self):
        """Handles HTTP PUT verb."""
        request = transforms.loads(self.request.get('request'))
        if not self.assert_xsrf_token_or_fail(
                request, self.XSRF_ACTION, {}):
            return

        if not CoursesPropertyRights.can_add():
            transforms.send_json_response(
                self, 401, 'Access denied.')
            return

        payload = request.get('payload')
        json_object = transforms.loads(payload)
        name = json_object.get('name')
        title = json_object.get('title')
        admin_email = json_object.get('admin_email')
        template_course = json_object.get('template_course')

        # Add the new course entry.
        errors = []
        entry = sites.add_new_course_entry(name, title, admin_email, errors)
        if not entry and not errors:
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

        if template_course:
            if template_course != 'sample':
                transforms.send_json_response(
                    self, 412,
                    'Unknown template course: %s' % template_course)
                return
            errors = []
            src_app_context = sites.get_all_courses('course:/:/:')[0]
            new_course.import_from(src_app_context, errors)
            new_course.save()
            if not errors:
                common_utils.run_hooks(
                    self.COPY_SAMPLE_COURSE_HOOKS, app_context, errors)
            if errors:
                transforms.send_json_response(self, 412, '\n'.join(errors))
                return

        transforms.send_json_response(
            self, 200, 'Added.', {'entry': entry})


class Model(object):
    """Mock of App Engine db.Model class; helps build keys-only .all() queries.

    CourseDeletionHandler, below, needs to delete all entries for all model
    types in the datastore.  In theory, we could call db.class_for_kind(),
    but it turns out that in practice, a) the entity type may be an old
    leftover and the code for that class is gone, b) the entity type is for
    a Course Builder module that is not currently enabled, or c) it's in
    some module that overrides the .kind() method to return some other name
    than the class name (I'm looking at _you_, MapReduce), and we just can't
    get the class.

    Lucky us, though - it turns out that queries that are only interested in
    fetching keys only need the db.Model to respond to .kind(), and so an
    instance of this class can be used in place of an actual class derived
    from db.Model when building such a query.
    """

    def __init__(self, kind):
        self._kind = kind

    def kind(self):
        return self._kind


class CourseDeleteHandler(utils.BaseHandler):

    URI = '/course/delete'
    XSRF_ACTION = 'course_delete'
    DELETE_BATCH_SIZE = 1000

    def post(self):
        user = users.get_current_user()
        if not roles.Roles.is_course_admin(self.app_context):
            self.error(401)
            return
        if not self.assert_xsrf_token_or_fail(self.request, self.XSRF_ACTION):
            return
        if namespace_manager.get_namespace() == '':
            self.error(400)
            return

        sites.remove_course(self.app_context)
        deferred.defer(self.delete_course)

        if self.request.get('is_selected_course') == 'True':
            # If we are deleting the course the UI is currently selected for,
            # redirect to the global handler.
            self.redirect('/modules/admin?action=courses', normalize=False)
        else:
            self.redirect(self.request.referer)

    @classmethod
    def delete_course(cls):
        """Called back repeatedly from deferred queue dispatcher."""
        try:
            kind = metadata.Kind.all().get()
            if not kind:
                logging.info(
                    'CourseDeleteHandler found no entity types to delete for '
                    'namespace %s; deletion complete.',
                    namespace_manager.get_namespace())
                return

            kind_name = kind.kind_name
            model = Model(kind_name)
            keys = list(db.Query(Model(kind_name), keys_only=True).run(
                batch_size=cls.DELETE_BATCH_SIZE))
            entities.delete(keys)
            logging.info(
                'CourseDeleteHandler deleted %d entities of type %s from '
                'namespace %s', len(keys), kind_name,
                namespace_manager.get_namespace())
            deferred.defer(cls.delete_course)
        except Exception:
            logging.critical(
                'Failed when attempting to delete course for namespace %s',
                namespace_manager.get_namespace())
            common_utils.log_exception_origin()
            raise


class ConfigPropertyItemRESTHandler(utils.BaseRESTHandler):
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
            entity_dict = {'name': key, 'label': item.label,
                'is_draft': entity.is_draft}
            entity_dict['value'] = transforms.string_to_value(
                entity.value, item.value_type)
            json_payload = transforms.dict_to_json(entity_dict)
            transforms.send_json_response(
                self, 200, 'Success.',
                payload_dict=json_payload,
                xsrf_token=crypto.XsrfTokenManager.create_xsrf_token(
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
        if item.after_change:
            item.after_change(item, old_value)

        models.EventEntity.record(
            'put-property', users.get_current_user(), transforms.dumps({
                'name': key,
                'before': str(old_value), 'after': str(entity.value)}))

        transforms.send_json_response(self, 200, 'Saved.')
