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
import json
import urllib
from controllers.utils import BaseHandler
from controllers.utils import BaseRESTHandler
from controllers.utils import ReflectiveRequestHandler
from controllers.utils import XsrfTokenManager
from models import entities
from models import roles
from models.models import MemcacheManager
import models.transforms as transforms
import modules.announcements.samples as samples
from modules.oeditor import oeditor
from google.appengine.ext import db


# TODO(psimakov): we should really use an ordered dictionary, not plain text; it
# can't be just a normal dict because a dict iterates its items in undefined
# order;  thus when we render a dict to JSON an order of fields will not match
# what we specify here; the final editor will also show the fields in an
# undefined order; for now we use the raw JSON, rather than the dict, but will
# move to an ordered dict later
SCHEMA_JSON = """
    {
        "id": "Announcement Entity",
        "type": "object",
        "description": "Announcement",
        "properties": {
            "key" : {"type": "string"},
            "title": {"optional": true, "type": "string"},
            "date": {"optional": true, "type": "date"},
            "html": {"optional": true, "type": "text"},
            "is_draft": {"type": "boolean"}
            }
    }
    """

SCHEMA_DICT = json.loads(SCHEMA_JSON)

# inputex specific schema annotations to control editor look and feel
SCHEMA_ANNOTATIONS_DICT = [
    (['title'], 'Announcement'),
    (['properties', 'key', '_inputex'], {
        'label': 'ID', '_type': 'uneditable'}),
    (['properties', 'date', '_inputex'], {
        'label': 'Date', '_type': 'date', 'dateFormat': 'Y/m/d',
        'valueFormat': 'Y/m/d'}),
    (['properties', 'title', '_inputex'], {'label': 'Title'}),
    (['properties', 'html', '_inputex'], {'label': 'Body', '_type': 'text'}),
    oeditor.create_bool_select_annotation(
        ['properties', 'is_draft'], 'Status', 'Draft', 'Published')]


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
                item['edit_action'] = self.get_action_url('edit', item['key'])

                item['delete_xsrf_token'] = self.create_xsrf_token('delete')
                item['delete_action'] = self.get_action_url(
                    'delete', item['key'])

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

    def get_list(self):
        """Shows a list of announcements."""
        if not self.personalize_page_and_get_enrolled():
            return

        items = AnnouncementEntity.get_announcements()
        if not items and AnnouncementsRights.can_edit(self):
            items = self.put_sample_announcements()

        items = AnnouncementsRights.apply_rights(self, items)

        self.template_value['announcements'] = self.format_items_for_template(
            items)
        self.template_value['navbar'] = {'announcements': True}
        self.render('announcements.html')

    def get_edit(self):
        """Shows an editor for an announcement."""
        if not AnnouncementsRights.can_edit(self):
            self.error(401)
            return

        key = self.request.get('key')

        exit_url = self.canonicalize_url(
            '/announcements#%s' % urllib.quote(key, safe=''))
        rest_url = self.canonicalize_url('/rest/announcements/item')
        form_html = oeditor.ObjectEditor.get_html_for(
            self, SCHEMA_JSON, SCHEMA_ANNOTATIONS_DICT,
            key, rest_url, exit_url)
        self.template_value['navbar'] = {'announcements': True}
        self.template_value['content'] = form_html
        self.render('bare.html')

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
        self.redirect(self.get_action_url('edit', entity.key()))


class AnnouncementsItemRESTHandler(BaseRESTHandler):
    """Provides REST API for an announcement."""

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

        json_payload = transforms.dict_to_json(transforms.entity_to_dict(
            entity), SCHEMA_DICT)
        transforms.send_json_response(
            self, 200, 'Success.',
            payload_dict=json_payload,
            xsrf_token=XsrfTokenManager.create_xsrf_token(
                'announcement-put'))

    def put(self):
        """Handles REST PUT verb with JSON payload."""
        request = json.loads(self.request.get('request'))
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

        payload = request.get('payload')
        transforms.dict_to_entity(entity, transforms.json_to_dict(
            json.loads(payload), SCHEMA_DICT))
        entity.put()

        transforms.send_json_response(self, 200, 'Saved.')


class AnnouncementEntity(entities.BaseEntity):
    """A class that represents a persistent database entity of announcement."""
    title = db.StringProperty(indexed=False)
    date = db.DateProperty()
    html = db.TextProperty(indexed=False)
    is_draft = db.BooleanProperty()

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
