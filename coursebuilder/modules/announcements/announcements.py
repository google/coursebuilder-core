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


import cgi
import datetime
import os
import urllib

import jinja2

import appengine_config
from common import tags
from common import utils as common_utils
from common import schema_fields
from controllers import utils
from models import resources_display
from models import custom_modules
from models import entities
from models import models
from models import roles
from models import transforms
from models.models import MemcacheManager
from models.models import Student
from modules.announcements import messages
from modules.dashboard import dashboard
from modules.oeditor import oeditor

from google.appengine.ext import db

MODULE_NAME = 'announcements'
MODULE_TITLE = 'Announcements'
TEMPLATE_DIR = os.path.join(
    appengine_config.BUNDLE_ROOT, 'modules', MODULE_NAME, 'templates')


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


class AnnouncementsHandlerMixin(object):
    def get_announcement_action_url(self, action, key=None):
        args = {'action': action}
        if key:
            args['key'] = key
        return self.canonicalize_url(
            '{}?{}'.format(
                AnnouncementsDashboardHandler.URL, urllib.urlencode(args)))

    def format_items_for_template(self, items):
        """Formats a list of entities into template values."""
        template_items = []
        for item in items:
            item = transforms.entity_to_dict(item)
            date = item.get('date')
            if date:
                date = datetime.datetime.combine(
                    date, datetime.time(0, 0, 0, 0))
                item['date'] = (
                    date - datetime.datetime(1970, 1, 1)).total_seconds() * 1000

            # add 'edit' actions
            if AnnouncementsRights.can_edit(self):
                item['edit_action'] = self.get_announcement_action_url(
                    AnnouncementsDashboardHandler.EDIT_ACTION, key=item['key'])

                item['delete_xsrf_token'] = self.create_xsrf_token(
                    AnnouncementsDashboardHandler.DELETE_ACTION)
                item['delete_action'] = self.get_announcement_action_url(
                    AnnouncementsDashboardHandler.DELETE_ACTION,
                    key=item['key'])

            template_items.append(item)

        output = {}
        output['children'] = template_items

        # add 'add' action
        if AnnouncementsRights.can_edit(self):
            output['add_xsrf_token'] = self.create_xsrf_token(
                AnnouncementsDashboardHandler.ADD_ACTION)
            output['add_action'] = self.get_announcement_action_url(
                AnnouncementsDashboardHandler.ADD_ACTION)

        return output


class AnnouncementsStudentHandler(
        AnnouncementsHandlerMixin, utils.BaseHandler,
        utils.ReflectiveRequestHandler):
    URL = '/announcements'
    default_action = 'list'
    get_actions = [default_action]
    post_actions = []

    def get_list(self):
        """Shows a list of announcements."""
        student = None
        user = self.personalize_page_and_get_user()
        transient_student = False
        if user is None:
            transient_student = True
        else:
            student = Student.get_enrolled_student_by_user(user)
            if not student:
                transient_student = True
        self.template_value['transient_student'] = transient_student
        items = AnnouncementEntity.get_announcements()
        items = AnnouncementsRights.apply_rights(self, items)
        if not roles.Roles.is_course_admin(self.get_course().app_context):
            items = models.LabelDAO.apply_course_track_labels_to_student_labels(
                self.get_course(), student, items)

        self.template_value['announcements'] = self.format_items_for_template(
            items)
        self._render()

    def _render(self):
        self.template_value['navbar'] = {'announcements': True}
        self.render('announcements.html')


class AnnouncementsDashboardHandler(
        AnnouncementsHandlerMixin, dashboard.DashboardHandler):
    """Handler for announcements."""

    LIST_ACTION = 'edit_announcements'
    EDIT_ACTION = 'edit_announcement'
    DELETE_ACTION = 'delete_announcement'
    ADD_ACTION = 'add_announcement'

    get_actions = [LIST_ACTION, EDIT_ACTION]
    post_actions = [ADD_ACTION, DELETE_ACTION]

    LINK_URL = 'edit_announcements'
    URL = '/{}'.format(LINK_URL)
    LIST_URL = '{}?action={}'.format(LINK_URL, LIST_ACTION)

    @classmethod
    def get_child_routes(cls):
        """Add child handlers for REST."""
        return [
            (AnnouncementsItemRESTHandler.URL, AnnouncementsItemRESTHandler)]

    def get_edit_announcements(self):
        """Shows a list of announcements."""
        items = AnnouncementEntity.get_announcements()
        items = AnnouncementsRights.apply_rights(self, items)

        main_content = self.get_template(
            'announcement_list.html', [TEMPLATE_DIR]).render({
                'announcements': self.format_items_for_template(items),
                'status_xsrf_token': self.create_xsrf_token(
                    AnnouncementsItemRESTHandler.STATUS_ACTION)
            })

        self.render_page({
            'page_title': self.format_title('Announcements'),
            'main_content': jinja2.utils.Markup(main_content)})

    def get_edit_announcement(self):
        """Shows an editor for an announcement."""

        key = self.request.get('key')

        schema = AnnouncementsItemRESTHandler.SCHEMA()

        exit_url = self.canonicalize_url('/{}'.format(self.LIST_URL))
        rest_url = self.canonicalize_url('/rest/announcements/item')
        form_html = oeditor.ObjectEditor.get_html_for(
            self,
            schema.get_json_schema(),
            schema.get_schema_dict(),
            key, rest_url, exit_url,
            delete_method='delete',
            delete_message='Are you sure you want to delete this announcement?',
            delete_url=self._get_delete_url(
                AnnouncementsItemRESTHandler.URL, key, 'announcement-delete'),
            display_types=schema.get_display_types())

        self.render_page({
            'main_content': form_html,
            'page_title': 'Edit Announcements',
        }, in_action=self.LIST_ACTION)

    def _get_delete_url(self, base_url, key, xsrf_token_name):
        return '%s?%s' % (
            self.canonicalize_url(base_url),
            urllib.urlencode({
                'key': key,
                'xsrf_token': cgi.escape(
                    self.create_xsrf_token(xsrf_token_name)),
            }))

    def post_delete_announcement(self):
        """Deletes an announcement."""
        if not AnnouncementsRights.can_delete(self):
            self.error(401)
            return

        key = self.request.get('key')
        entity = AnnouncementEntity.get(key)
        if entity:
            entity.delete()
        self.redirect('/{}'.format(self.LIST_URL))

    def post_add_announcement(self):
        """Adds a new announcement and redirects to an editor for it."""
        if not AnnouncementsRights.can_add(self):
            self.error(401)
            return

        entity = AnnouncementEntity.make('New Announcement', '', True)
        entity.put()

        self.redirect(self.get_announcement_action_url(
            self.EDIT_ACTION, key=entity.key()))


class AnnouncementsItemRESTHandler(utils.BaseRESTHandler):
    """Provides REST API for an announcement."""

    URL = '/rest/announcements/item'

    STATUS_ACTION = 'set_draft_status_announcement'

    @classmethod
    def SCHEMA(cls):
        schema = schema_fields.FieldRegistry('Announcement',
            extra_schema_dict_values={
                'className': 'inputEx-Group new-form-layout'})
        schema.add_property(schema_fields.SchemaField(
            'key', 'ID', 'string', editable=False, hidden=True))
        schema.add_property(schema_fields.SchemaField(
            'title', 'Title', 'string',
            description=messages.ANNOUNCEMENT_TITLE_DESCRIPTION))
        schema.add_property(schema_fields.SchemaField(
            'html', 'Body', 'html',
            description=messages.ANNOUNCEMENT_BODY_DESCRIPTION,
            extra_schema_dict_values={
                'supportCustomTags': tags.CAN_USE_DYNAMIC_TAGS.value,
                'excludedCustomTags': tags.EditorBlacklists.COURSE_SCOPE},
            optional=True))
        schema.add_property(schema_fields.SchemaField(
            'date', 'Date', 'datetime',
            description=messages.ANNOUNCEMENT_DATE_DESCRIPTION,
            extra_schema_dict_values={
                '_type': 'datetime',
                'className': 'inputEx-CombineField gcb-datetime '
                'inputEx-fieldWrapper date-only inputEx-required'}))
        resources_display.LabelGroupsHelper.add_labels_schema_fields(
            schema, 'announcement')
        schema.add_property(schema_fields.SchemaField(
            'is_draft', 'Status', 'boolean',
            description=messages.ANNOUNCEMENT_STATUS_DESCRIPTION,
            extra_schema_dict_values={'className': 'split-from-main-group'},
            optional=True,
            select_data=[
                (True, resources_display.DRAFT_TEXT),
                (False, resources_display.PUBLISHED_TEXT)]))
        return schema

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

        schema = AnnouncementsItemRESTHandler.SCHEMA()

        entity_dict = transforms.entity_to_dict(entity)

        # Format the internal date object as ISO 8601 datetime, with time
        # defaulting to 00:00:00
        date = entity_dict['date']
        date = datetime.datetime(date.year, date.month, date.day)
        entity_dict['date'] = date

        entity_dict.update(
            resources_display.LabelGroupsHelper.labels_to_field_data(
                common_utils.text_to_list(entity.labels)))

        json_payload = transforms.dict_to_json(entity_dict)
        transforms.send_json_response(
            self, 200, 'Success.',
            payload_dict=json_payload,
            xsrf_token=utils.XsrfTokenManager.create_xsrf_token(
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

        schema = AnnouncementsItemRESTHandler.SCHEMA()

        payload = request.get('payload')
        update_dict = transforms.json_to_dict(
            transforms.loads(payload), schema.get_json_schema_dict())

        # The datetime widget returns a datetime object and we need a UTC date.
        update_dict['date'] = update_dict['date'].date()

        entity.labels = common_utils.list_to_text(
            resources_display.LabelGroupsHelper.field_data_to_labels(
                update_dict))
        resources_display.LabelGroupsHelper.remove_label_field_data(update_dict)

        transforms.dict_to_entity(entity, update_dict)

        entity.put()

        transforms.send_json_response(self, 200, 'Saved.')

    def delete(self):
        """Deletes an announcement."""
        key = self.request.get('key')

        if not self.assert_xsrf_token_or_fail(
                self.request, 'announcement-delete', {'key': key}):
            return

        if not AnnouncementsRights.can_delete(self):
            self.error(401)
            return

        entity = AnnouncementEntity.get(key)
        if not entity:
            transforms.send_json_response(
                self, 404, 'Object not found.', {'key': key})
            return

        entity.delete()

        transforms.send_json_response(self, 200, 'Deleted.')

    @classmethod
    def post_set_draft_status(cls, handler):
        """Sets the draft status of a course component.

        Only works with CourseModel13 courses, but the REST handler
        is only called with this type of courses.

        XSRF is checked in the dashboard.
        """
        key = handler.request.get('key')

        if not AnnouncementsRights.can_edit(handler):
            transforms.send_json_response(
                handler, 401, 'Access denied.', {'key': key})
            return

        entity = AnnouncementEntity.get(key)
        if not entity:
            transforms.send_json_response(
                handler, 404, 'Object not found.', {'key': key})
            return

        set_draft = handler.request.get('set_draft')
        if set_draft == '1':
            set_draft = True
        elif set_draft == '0':
            set_draft = False
        else:
            transforms.send_json_response(
                handler, 401, 'Invalid set_draft value, expected 0 or 1.',
                {'set_draft': set_draft}
            )
            return

        entity.is_draft = set_draft
        entity.put()

        transforms.send_json_response(
            handler,
            200,
            'Draft status set to %s.' % (
                resources_display.DRAFT_TEXT if set_draft else
                resources_display.PUBLISHED_TEXT
            ), {
                'is_draft': set_draft
            }
        )
        return


class AnnouncementEntity(entities.BaseEntity):
    """A class that represents a persistent database entity of announcement."""
    title = db.StringProperty(indexed=False)
    date = db.DateProperty()
    html = db.TextProperty(indexed=False)
    labels = db.StringProperty(indexed=False)
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

    @classmethod
    def make(cls, title, html, is_draft):
        entity = cls()
        entity.title = title
        entity.date = datetime.datetime.now().date()
        entity.html = html
        entity.is_draft = is_draft
        return entity

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

    handlers = [
        (handler.URL, handler) for handler in
        [AnnouncementsStudentHandler, AnnouncementsDashboardHandler]]

    dashboard.DashboardHandler.add_sub_nav_mapping(
        'analytics', MODULE_NAME, MODULE_TITLE,
        action=AnnouncementsDashboardHandler.LIST_ACTION,
        href=AnnouncementsDashboardHandler.LIST_URL,
        placement=1000, sub_group_name='pinned')

    dashboard.DashboardHandler.add_custom_post_action(
        AnnouncementsItemRESTHandler.STATUS_ACTION,
        AnnouncementsItemRESTHandler.post_set_draft_status)

    global custom_module  # pylint: disable=global-statement
    custom_module = custom_modules.Module(
        MODULE_TITLE,
        'A set of pages for managing course announcements.',
        [], handlers)
    return custom_module
