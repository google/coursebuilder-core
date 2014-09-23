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

"""Classes and methods to create and manage Announcements."""

__author__ = 'Saifu Angto (saifu@google.com)'


import datetime
import urllib

from common import tags
from common import utils
from common.schema_fields import FieldArray
from common.schema_fields import FieldRegistry
from common.schema_fields import SchemaField
from controllers.utils import BaseHandler
from controllers.utils import BaseRESTHandler
from controllers.utils import ReflectiveRequestHandler
from controllers.utils import XsrfTokenManager
from models import custom_modules
from models import entities
from models import models
from models import notify
from models import roles
from models import transforms
from models.models import MemcacheManager
from models.models import Student
import modules.announcements.samples as samples
from modules.dashboard.label_editor import LabelGroupsHelper
from modules.oeditor import oeditor

from google.appengine.ext import db


class AnnouncementsRights(object):
    """Manages view/edit rights for announcements."""

    @classmethod
    def can_view(cls, unused_handler):
        return True

    @classmethod
    def can_edit(cls, handler):
        return roles.Roles.is_course_admin(handler.app_context)

    @classmethod
    def can_delete(cls, handler):
        return cls.can_edit(handler)

    @classmethod
    def can_add(cls, handler):
        return cls.can_edit(handler)

    @classmethod
    def apply_rights(cls, handler, items):
        """Filter out items that current user can't see."""
        if AnnouncementsRights.can_edit(handler):
            return items

        allowed = []
        for item in items:
            if not item.is_draft:
                allowed.append(item)

        return allowed


class AnnouncementsHandler(BaseHandler, ReflectiveRequestHandler):
    """Handler for announcements."""

    default_action = 'list'
    get_actions = [default_action, 'edit']
    post_actions = ['add', 'delete']

    @classmethod
    def get_child_routes(cls):
        """Add child handlers for REST."""
        return [('/rest/announcements/item', AnnouncementsItemRESTHandler)]

    def get_action_url(self, action, key=None):
        args = {'action': action}
        if key:
            args['key'] = key
        return self.canonicalize_url(
            '/announcements?%s' % urllib.urlencode(args))

    def format_items_for_template(self, items):
        """Formats a list of entities into template values."""
        template_items = []
        for item in items:
            item = transforms.entity_to_dict(item)

            # add 'edit' actions
            if AnnouncementsRights.can_edit(self):
                item['edit_action'] = self.get_action_url(
                    'edit', key=item['key'])

                item['delete_xsrf_token'] = self.create_xsrf_token('delete')
                item['delete_action'] = self.get_action_url(
                    'delete', key=item['key'])

            template_items.append(item)

        output = {}
        output['children'] = template_items

        # add 'add' action
        if AnnouncementsRights.can_edit(self):
            output['add_xsrf_token'] = self.create_xsrf_token('add')
            output['add_action'] = self.get_action_url('add')

        return output

    def put_sample_announcements(self):
        """Loads sample data into a database."""
        items = []
        for item in samples.SAMPLE_ANNOUNCEMENTS:
            entity = AnnouncementEntity()
            transforms.dict_to_entity(entity, item)
            entity.put()
            items.append(entity)
        return items

    def _render(self):
        self.template_value['navbar'] = {'announcements': True}
        self.render('announcements.html')

    def get_list(self):
        """Shows a list of announcements."""
        student = None
        user = self.personalize_page_and_get_user()
        transient_student = False
        if user is None:
            transient_student = True
        else:
            student = Student.get_enrolled_student_by_email(user.email())
            if not student:
                transient_student = True
        self.template_value['transient_student'] = transient_student

        items = AnnouncementEntity.get_announcements()
        if not items and AnnouncementsRights.can_edit(self):
            items = self.put_sample_announcements()

        items = AnnouncementsRights.apply_rights(self, items)
        if not roles.Roles.is_course_admin(self.get_course().app_context):
            items = models.LabelDAO.apply_course_track_labels_to_student_labels(
                self.get_course(), student, items)

        self.template_value['announcements'] = self.format_items_for_template(
            items)
        self._render()

    def get_edit(self):
        """Shows an editor for an announcement."""
        user = self.personalize_page_and_get_user()
        if not user or not AnnouncementsRights.can_edit(self):
            self.error(401)
            return

        key = self.request.get('key')

        schema = AnnouncementsItemRESTHandler.SCHEMA(
            'Announcement',
            self.get_course().get_course_announcement_list_email())

        exit_url = self.canonicalize_url(
            '/announcements#%s' % urllib.quote(key, safe=''))
        rest_url = self.canonicalize_url('/rest/announcements/item')
        form_html = oeditor.ObjectEditor.get_html_for(
            self,
            schema.get_json_schema(),
            schema.get_schema_dict(),
            key, rest_url, exit_url,
            required_modules=AnnouncementsItemRESTHandler.REQUIRED_MODULES)

        self.template_value['content'] = form_html
        self._render()

    def post_delete(self):
        """Deletes an announcement."""
        if not AnnouncementsRights.can_delete(self):
            self.error(401)
            return

        key = self.request.get('key')
        entity = AnnouncementEntity.get(key)
        if entity:
            entity.delete()
        self.redirect('/announcements')

    def post_add(self):
        """Adds a new announcement and redirects to an editor for it."""
        if not AnnouncementsRights.can_add(self):
            self.error(401)
            return

        entity = AnnouncementEntity()
        entity.title = 'Sample Announcement'
        entity.date = datetime.datetime.now().date()
        entity.html = 'Here is my announcement!'
        entity.is_draft = True
        entity.put()
        self.redirect(self.get_action_url('edit', key=entity.key()))


DRAFT_TEXT = 'Private'
PUBLISHED_TEXT = 'Public'


class AnnouncementsItemRESTHandler(BaseRESTHandler):
    """Provides REST API for an announcement."""

    REQUIRED_MODULES = [
        'inputex-date', 'gcb-rte', 'inputex-select', 'inputex-string',
        'inputex-uneditable', 'inputex-checkbox', 'inputex-list',
        'inputex-hidden']

    @classmethod
    def SCHEMA(cls, title, announcement_email):
        schema = FieldRegistry(title)
        schema.add_property(SchemaField(
            'key', 'ID', 'string', editable=False,
            extra_schema_dict_values={'className': 'inputEx-Field keyHolder'}))
        schema.add_property(SchemaField(
            'title', 'Title', 'string', optional=True))
        schema.add_property(SchemaField(
            'html', 'Body', 'html', optional=True,
            extra_schema_dict_values={
                'supportCustomTags': tags.CAN_USE_DYNAMIC_TAGS.value,
                'excludedCustomTags': tags.EditorBlacklists.COURSE_SCOPE}))
        schema.add_property(SchemaField(
            'date', 'Date', 'date',
            optional=True, extra_schema_dict_values={
                '_type': 'date', 'dateFormat': 'Y-m-d',
                'valueFormat': 'Y-m-d'}))
        schema.add_property(FieldArray(
            'label_groups', 'Labels',
             item_type=LabelGroupsHelper.make_labels_group_schema_field(),
             extra_schema_dict_values={
                 'className': 'inputEx-Field label-group-list'}))
        schema.add_property(SchemaField(
            'send_email', 'Send Email', 'boolean', optional=True,
            extra_schema_dict_values={
                'description':
                    AnnouncementsItemRESTHandler.get_send_email_description(
                        announcement_email)}))
        schema.add_property(SchemaField(
            'is_draft', 'Status', 'boolean',
            select_data=[(True, DRAFT_TEXT), (False, PUBLISHED_TEXT)],
            extra_schema_dict_values={'className': 'split-from-main-group'}))
        return schema

    @classmethod
    def get_send_email_description(cls, announcement_email):
        """Get the description for Send Email field."""
        if announcement_email:
            return 'Email will be sent to : ' + announcement_email
        return 'Announcement list not configured.'

    def get(self):
        """Handles REST GET verb and returns an object as JSON payload."""
        key = self.request.get('key')

        try:
            entity = AnnouncementEntity.get(key)
        except db.BadKeyError:
            entity = None

        if not entity:
            transforms.send_json_response(
                self, 404, 'Object not found.', {'key': key})
            return

        viewable = AnnouncementsRights.apply_rights(self, [entity])
        if not viewable:
            transforms.send_json_response(
                self, 401, 'Access denied.', {'key': key})
            return
        entity = viewable[0]

        schema = AnnouncementsItemRESTHandler.SCHEMA(
            'Announcement',
            self.get_course().get_course_announcement_list_email())

        entity_dict = transforms.entity_to_dict(entity)
        entity_dict['label_groups'] = (
            LabelGroupsHelper.announcement_labels_to_dict(entity))

        json_payload = transforms.dict_to_json(
            entity_dict, schema.get_json_schema_dict())
        transforms.send_json_response(
            self, 200, 'Success.',
            payload_dict=json_payload,
            xsrf_token=XsrfTokenManager.create_xsrf_token(
                'announcement-put'))

    def put(self):
        """Handles REST PUT verb with JSON payload."""
        request = transforms.loads(self.request.get('request'))
        key = request.get('key')

        if not self.assert_xsrf_token_or_fail(
                request, 'announcement-put', {'key': key}):
            return

        if not AnnouncementsRights.can_edit(self):
            transforms.send_json_response(
                self, 401, 'Access denied.', {'key': key})
            return

        entity = AnnouncementEntity.get(key)
        if not entity:
            transforms.send_json_response(
                self, 404, 'Object not found.', {'key': key})
            return

        schema = AnnouncementsItemRESTHandler.SCHEMA(
            'Announcement',
            self.get_course().get_course_announcement_list_email())

        payload = request.get('payload')
        update_dict = transforms.json_to_dict(
            transforms.loads(payload), schema.get_json_schema_dict())

        entity.labels = utils.list_to_text(
            LabelGroupsHelper.decode_labels_group(
                update_dict.get('label_groups')))

        transforms.dict_to_entity(entity, update_dict)

        entity.put()

        email_sent = False
        if entity.send_email:
            email_manager = notify.EmailManager(self.get_course())
            email_sent = email_manager.send_announcement(
                entity.title, entity.html)

        if entity.send_email and not email_sent:
            if not self.get_course().get_course_announcement_list_email():
                message = 'Saved. Announcement list not configured.'
            else:
                message = 'Saved, but there was an error sending email.'
        else:
            message = 'Saved.'
        transforms.send_json_response(self, 200, message)


class AnnouncementEntity(entities.BaseEntity):
    """A class that represents a persistent database entity of announcement."""
    title = db.StringProperty(indexed=False)
    date = db.DateProperty()
    html = db.TextProperty(indexed=False)
    labels = db.StringProperty(indexed=False)
    is_draft = db.BooleanProperty()
    send_email = db.BooleanProperty()

    memcache_key = 'announcements'

    @classmethod
    def get_announcements(cls, allow_cached=True):
        items = MemcacheManager.get(cls.memcache_key)
        if not allow_cached or items is None:
            items = AnnouncementEntity.all().order('-date').fetch(1000)

            # TODO(psimakov): prepare to exceed 1MB max item size
            # read more here: http://stackoverflow.com
            #   /questions/5081502/memcache-1-mb-limit-in-google-app-engine
            MemcacheManager.set(cls.memcache_key, items)
        return items

    def put(self):
        """Do the normal put() and also invalidate memcache."""
        result = super(AnnouncementEntity, self).put()
        MemcacheManager.delete(self.memcache_key)
        return result

    def delete(self):
        """Do the normal delete() and invalidate memcache."""
        super(AnnouncementEntity, self).delete()
        MemcacheManager.delete(self.memcache_key)


custom_module = None


def register_module():
    """Registers this module in the registry."""

    announcement_handlers = [('/announcements', AnnouncementsHandler)]

    global custom_module
    custom_module = custom_modules.Module(
        'Course Announcements',
        'A set of pages for managing course announcements.',
        [], announcement_handlers)
    return custom_module
