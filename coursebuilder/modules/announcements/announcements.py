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
import collections
import datetime
import os
import urllib

import jinja2

import appengine_config
from common import crypto
from common import tags
from common import utils as common_utils
from common import schema_fields
from common import resource
from common import utc
from controllers import sites
from controllers import utils
from models import resources_display
from models import courses
from models import custom_modules
from models import entities
from models import models
from models import roles
from models import transforms
from modules.announcements import messages
from modules.dashboard import dashboard
from modules.i18n_dashboard import i18n_dashboard
from modules.news import news
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
            student = models.Student.get_enrolled_student_by_user(user)
            if not student:
                transient_student = True
        self.template_value['transient_student'] = transient_student
        locale = self.app_context.get_current_locale()
        if locale == self.app_context.default_locale:
            locale = None
        items = AnnouncementEntity.get_announcements(locale=locale)
        items = AnnouncementsRights.apply_rights(self, items)
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
    DEFAULT_TITLE_TEXT = 'New Announcement'

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

        entity = AnnouncementEntity.make(self.DEFAULT_TITLE_TEXT, '', True)
        entity.put()

        self.redirect(self.get_announcement_action_url(
            self.EDIT_ACTION, key=entity.key()))


class AnnouncementsItemRESTHandler(utils.BaseRESTHandler):
    """Provides REST API for an announcement."""

    URL = '/rest/announcements/item'

    ACTION = 'announcement-put'
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

        json_payload = transforms.dict_to_json(entity_dict)
        transforms.send_json_response(
            self, 200, 'Success.',
            payload_dict=json_payload,
            xsrf_token=crypto.XsrfTokenManager.create_xsrf_token(self.ACTION))

    def put(self):
        """Handles REST PUT verb with JSON payload."""
        request = transforms.loads(self.request.get('request'))
        key = request.get('key')

        if not self.assert_xsrf_token_or_fail(
                request, self.ACTION, {'key': key}):
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
        if entity.is_draft and not update_dict.get('set_draft'):
            item = news.NewsItem(
                str(TranslatableResourceAnnouncement.key_for_entity(entity)),
                AnnouncementsStudentHandler.URL.lstrip('/'))
            news.CourseNewsDao.add_news_item(item)

        # The datetime widget returns a datetime object and we need a UTC date.
        update_dict['date'] = update_dict['date'].date()
        del update_dict['key']  # Don't overwrite key member method in entity.
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

        if entity.is_draft and not set_draft:
            item = news.NewsItem(
                str(TranslatableResourceAnnouncement.key_for_entity(entity)),
                AnnouncementsStudentHandler.URL.lstrip('/'))
            news.CourseNewsDao.add_news_item(item)

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
    """A class that represents a persistent database entity of announcements.

    Note that this class was added to Course Builder prior to the idioms
    introduced in models.models.BaseJsonDao and friends.  That being the
    case, this class is much more hand-coded and not well integrated into
    the structure of callbacks and hooks that have accumulated around
    entity caching, i18n, and the like.
    """

    title = db.StringProperty(indexed=False)
    date = db.DateProperty()
    html = db.TextProperty(indexed=False)
    is_draft = db.BooleanProperty()

    _MEMCACHE_KEY = 'announcements'

    @classmethod
    def get_announcements(cls, locale=None):
        memcache_key = cls._cache_key(locale)
        items = models.MemcacheManager.get(memcache_key)
        if items is None:
            items = list(common_utils.iter_all(AnnouncementEntity.all()))
            items.sort(key=lambda item: item.date, reverse=True)
            if locale:
                cls._translate_content(items)

            # TODO(psimakov): prepare to exceed 1MB max item size
            # read more here: http://stackoverflow.com
            #   /questions/5081502/memcache-1-mb-limit-in-google-app-engine
            models.MemcacheManager.set(memcache_key, items)
        return items

    @classmethod
    def _cache_key(cls, locale=None):
        if not locale:
            return cls._MEMCACHE_KEY
        return cls._MEMCACHE_KEY + ':' + locale

    @classmethod
    def purge_cache(cls, locale=None):
        models.MemcacheManager.delete(cls._cache_key(locale))

    @classmethod
    def make(cls, title, html, is_draft):
        entity = cls()
        entity.title = title
        entity.date = utc.now_as_datetime().date()
        entity.html = html
        entity.is_draft = is_draft
        return entity

    def put(self):
        """Do the normal put() and also invalidate memcache."""
        result = super(AnnouncementEntity, self).put()
        self.purge_cache()
        if i18n_dashboard.I18nProgressDeferredUpdater.is_translatable_course():
            i18n_dashboard.I18nProgressDeferredUpdater.update_resource_list(
                [TranslatableResourceAnnouncement.key_for_entity(self)])
        return result

    def delete(self):
        """Do the normal delete() and invalidate memcache."""
        news.CourseNewsDao.remove_news_item(
            str(TranslatableResourceAnnouncement.key_for_entity(self)))
        super(AnnouncementEntity, self).delete()
        self.purge_cache()

    @classmethod
    def _translate_content(cls, items):
        app_context = sites.get_course_for_current_request()
        course = courses.Course.get(app_context)
        key_list = [
            TranslatableResourceAnnouncement.key_for_entity(item)
            for item in items]
        FakeDto = collections.namedtuple('FakeDto', ['dict'])
        fake_items = [
            FakeDto({'title': item.title, 'html': item.html})
            for item in items]
        i18n_dashboard.translate_dto_list(course, fake_items, key_list)
        for item, fake_item in zip(items, fake_items):
            item.title = str(fake_item.dict['title'])
            item.html = str(fake_item.dict['html'])


class TranslatableResourceAnnouncement(
    i18n_dashboard.AbstractTranslatableResourceType):

    @classmethod
    def get_ordering(cls):
        return i18n_dashboard.TranslatableResourceRegistry.ORDERING_LAST

    @classmethod
    def get_title(cls):
        return MODULE_TITLE

    @classmethod
    def key_for_entity(cls, announcement, course=None):
        return resource.Key(ResourceHandlerAnnouncement.TYPE,
                            announcement.key().id(), course)

    @classmethod
    def get_resources_and_keys(cls, course):
        return [(announcement, cls.key_for_entity(announcement, course))
                for announcement in AnnouncementEntity.get_announcements()]

    @classmethod
    def get_resource_types(cls):
        return [ResourceHandlerAnnouncement.TYPE]

    @classmethod
    def notify_translations_changed(cls, resource_bundle_key):
        AnnouncementEntity.purge_cache(resource_bundle_key.locale)

    @classmethod
    def get_i18n_title(cls, resource_key):
        locale = None
        app_context = sites.get_course_for_current_request()
        if (app_context and
            app_context.default_locale != app_context.get_current_locale()):
            locale = app_context.get_current_locale()
        announcements = AnnouncementEntity.get_announcements(locale)
        item = common_utils.find(
            lambda a: a.key().id() == int(resource_key.key), announcements)
        return item.title if item else None


class ResourceHandlerAnnouncement(resource.AbstractResourceHandler):
    """Generic resoruce accessor for applying translations to announcements."""

    TYPE = 'announcement'

    @classmethod
    def _entity_key(cls, key):
        return db.Key.from_path(AnnouncementEntity.kind(), int(key))

    @classmethod
    def get_resource(cls, course, key):
        return AnnouncementEntity.get(cls._entity_key(key))

    @classmethod
    def get_resource_title(cls, rsrc):
        return rsrc.title

    @classmethod
    def get_schema(cls, course, key):
        return AnnouncementsItemRESTHandler.SCHEMA()

    @classmethod
    def get_data_dict(cls, course, key):
        entity = cls.get_resource(course, key)
        return transforms.entity_to_dict(entity)

    @classmethod
    def get_view_url(cls, rsrc):
        return AnnouncementsStudentHandler.URL.lstrip('/')

    @classmethod
    def get_edit_url(cls, key):
        return (AnnouncementsDashboardHandler.LINK_URL + '?' +
                urllib.urlencode({
                    'action': AnnouncementsDashboardHandler.EDIT_ACTION,
                    'key': cls._entity_key(key),
                }))


custom_module = None


def on_module_enabled():
    resource.Registry.register(ResourceHandlerAnnouncement)
    i18n_dashboard.TranslatableResourceRegistry.register(
        TranslatableResourceAnnouncement)


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
        [], handlers, notify_module_enabled=on_module_enabled)
    return custom_module
