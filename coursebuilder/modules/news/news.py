# Copyright 2016 Google Inc. All Rights Reserved.
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

"""Notify students of items new or changed since their last visit.

News consists of course-level news and per-student news.  Course-level news
consists of things such as a unit becoming available or a new annnouncement.
Student-level news is things like earning a course certificate based on
assessment scores.

We keep one per-course singleton to keep track of course news.  This is only
ever appended to.  We also keep a per-student record, which tracks both news
items and what items (both course and student level) a student has seen.

When a student views a course page, the news that are still actually new to
that student are calculated and used to populate the News tab in the title
bar.  Note that merely having visited a new news item once is not sufficient
to exclude the news item; we only consider news items to be "old news" after a
few hours.  This permits students to re-find the same item using the same UI
affordance for a little while.

"""

__author__ = [
    'mgainer@google.com (Mike Gainer)',
]

import collections
import os

import jinja2

import appengine_config
from common import resource
from common import schema_fields
from common import users
from common import utc
from common import utils as common_utils
from controllers import sites
from controllers import utils
from models import courses
from models import custom_modules
from models import data_removal
from models import models
from models import services
from models import transforms
from modules.i18n_dashboard import i18n_dashboard
from modules.news import messages

from google.appengine.ext import db

MODULE_NAME = 'news'
NEWS_SETTINGS_SECTION = 'news'
TEMPLATES_DIR = os.path.join(
    appengine_config.BUNDLE_ROOT, 'modules', 'news', 'templates')

# Course-level setting field name for enabling News module functionality.
IS_NEWS_ENABLED_SETTING = 'is_news_enabled'

# News items that have been seen more recently than this are still newsworthy.
# Older items may be excluded from the UI and/or removed from the per-Student
# news record for space savings.
NEWSWORTHINESS_SECONDS = 6 * 60 * 60

# Try to show at least this many news items in the News tab, even if that
# means pulling in news that was seen more than NEWSWORTHINESS_SECONDS ago.
MIN_NEWS_ITEMS_TO_DISPLAY = 5

custom_module = None


def is_enabled():
    # TODO(mgainer): Add tests to verify that this does the right thing
    # when this module is re-enabled in manifest.yaml.

    # Enabled/disabled in manifest.yaml
    if not custom_module.enabled:
        return False

    # If we don't have a course, we can't reasonably expect to have course news.
    app_context = sites.get_app_context_for_current_request()
    if not app_context:
        return False

    # Enabled at course level?
    settings = app_context.get_environ()
    news_settings = settings.get(NEWS_SETTINGS_SECTION, {})
    return news_settings.get(IS_NEWS_ENABLED_SETTING, True)  # True if unset.

class SerializableList(object):
    """Convenience functions to marshal/unmarshal objects from JSON."""

    @classmethod
    def json_to_list(cls, json_str):
        if not json_str:
            return []
        json_dicts = transforms.loads(json_str)
        parsed_dicts = [
            transforms.json_to_dict(d, cls.SCHEMA.get_json_schema_dict())
            for d in json_dicts]
        return [cls(**kwargs) for kwargs in parsed_dicts]

    @classmethod
    def list_to_json(cls, items):
        json_dicts = [
            transforms.dict_to_json(transforms.instance_to_dict(item))
            for item in items]
        return transforms.dumps(json_dicts)


class NewsItem(SerializableList):
    """Behaviorless struct, plus marshal/unmarshal convenience functions."""

    FIELD_KEY = 'resource_key'
    FIELD_WHEN = 'when'
    FIELD_URL = 'url'
    FIELD_LABELS = 'labels'

    SCHEMA = schema_fields.FieldRegistry('NewsItem')
    SCHEMA.add_property(schema_fields.SchemaField(
        FIELD_KEY, 'Key', 'string'))
    SCHEMA.add_property(schema_fields.SchemaField(
        FIELD_WHEN, 'When', 'datetime'))
    SCHEMA.add_property(schema_fields.SchemaField(
        FIELD_URL, 'URL', 'string'))
    SCHEMA.add_property(schema_fields.SchemaField(
        FIELD_LABELS, 'Labels', 'string'))

    def __init__(self, resource_key, url, when=None, labels=None):
        # String version of common.resource.Key
        self.resource_key = resource_key

        # The time when this item became news.
        self.when = when or utc.now_as_datetime()

        # URL to the page showing the item.
        self.url = url

        # Single string giving IDs of labels, whitespace separated.  Same as
        # labels field on Student, Announcement, Unit and so on.  Used to
        # restrict news on items that are labelled to only students with
        # matching labels.  Follows usual label-match rules: if either Student
        # or NewsItem does not have labels in a category, category does not
        # filter.  If both have labels, at least one label must exist in
        # common for match.
        self.labels = labels or ''

        # --------------------------------------------------------------------
        # Below here is transient data - not persisted.  Overwritten only for
        # UX display.  Note that since the serialization library ignores
        # transient items based on leading-underscore, we also provide
        # getter/setter properties to avoid warnings about touching private
        # members.

        # Distinguish news items that are likely interesting versus items that
        # are likely old news for the student.
        self._is_new_news = None

        # Title, suitably i18n'd for the current display locale.
        self._i18n_title = None

    @property
    def is_new_news(self):
        return self._is_new_news

    @is_new_news.setter
    def is_new_news(self, value):
        self._is_new_news = value

    @property
    def i18n_title(self):
        return self._i18n_title

    @i18n_title.setter
    def i18n_title(self, value):
        self._i18n_title = value


class SeenItem(SerializableList):
    """Behaviorless struct, plus marshal/unmarshal convenience functions."""

    FIELD_KEY = 'resource_key'
    FIELD_WHEN = 'when'

    SCHEMA = schema_fields.FieldRegistry('SeenItem')
    SCHEMA.add_property(schema_fields.SchemaField(
        FIELD_KEY, 'Key', 'string'))
    SCHEMA.add_property(schema_fields.SchemaField(
        FIELD_WHEN, 'When', 'datetime'))

    def __init__(self, resource_key, when):
        # String version of common.resource.Key
        self.resource_key = resource_key

        # The time when this item became news.
        self.when = when


class BaseNewsDto(object):
    """Common base for CourseNewsDao, StudentNewsDao."""
    NEWS_ITEMS = 'news_items'  # JSON array of NewsItem contents

    def __init__(self, the_id, the_dict):
        self.id = the_id
        self.dict = the_dict

    def get_news_items(self):
        return NewsItem.json_to_list(self.dict.get(self.NEWS_ITEMS))

    def _set_news_items(self, news_items):
        self.dict[self.NEWS_ITEMS] = NewsItem.list_to_json(news_items)

    def add_news_item(self, news_item, overwrite_existing):
        news_items = self.get_news_items()
        # Only one News item per course object.  If user has not seen older
        # alert, no point retaining it.
        old_item = common_utils.find(
            lambda i: i.resource_key == news_item.resource_key, news_items)
        if old_item:
            if overwrite_existing and old_item.when < news_item.when:
                news_items.remove(old_item)
                news_items.append(news_item)
        else:
            news_items.append(news_item)
        self._set_news_items(news_items)

    def remove_news_item(self, resource_key):
        news_items = self.get_news_items()
        item = common_utils.find(
            lambda i: i.resource_key == resource_key, news_items)
        if not item:
            return False
        news_items.remove(item)
        self._set_news_items(news_items)
        return True


class BaseNewsDao(models.BaseJsonDao):

    @classmethod
    def add_news_item(cls, news_item, overwrite_existing=True):
        """Convenience method when only one operation is needed on DTO."""
        if not is_enabled():
            return

        dto = cls.load_or_default()
        dto.add_news_item(news_item, overwrite_existing)
        cls.save(dto)

    @classmethod
    def remove_news_item(cls, resource_key):
        if not is_enabled():
            return

        dto = cls.load_or_default()
        if dto.remove_news_item(resource_key):
            cls.save(dto)

    @classmethod
    def get_news_items(cls):
        """Convenience method when only one operation is needed on DTO."""
        if not is_enabled():
            return []

        dto = cls.load_or_default()
        return dto.get_news_items()


class CourseNewsEntity(models.BaseEntity):
    """Singleton: coursewide news.  E.g., new announcements, units, lessons."""
    SINGLETON_KEY_NAME = 'singleton'

    data = db.TextProperty(indexed=False)


class CourseNewsDto(BaseNewsDto):
    """No extra behavior, just here for naming convenience/commonality."""
    pass


class CourseNewsDao(BaseNewsDao):
    DTO = CourseNewsDto
    ENTITY = CourseNewsEntity
    ENTITY_KEY_TYPE = models.BaseJsonDao.EntityKeyTypeName

    @classmethod
    def load_or_default(cls):
        dto = cls.load(CourseNewsEntity.SINGLETON_KEY_NAME)
        if not dto:
            dto = CourseNewsDto(CourseNewsEntity.SINGLETON_KEY_NAME, {})
        return dto


class StudentNewsEntity(models.BaseEntity):
    """Per-Student: Global news items already seen, plus per-student News.

    Keyed by student obfuscated user ID.
    """
    data = db.TextProperty(indexed=False)


class StudentNewsDto(BaseNewsDto):
    SEEN_ITEMS = 'seen'

    def get_seen_items(self):
        return SeenItem.json_to_list(self.dict.get(self.SEEN_ITEMS))

    def _set_seen_items(self, seen_items):
        self.dict[self.SEEN_ITEMS] = SeenItem.list_to_json(seen_items)

    def mark_item_seen(self, resource_key):
        now = utc.now_as_datetime()

        # First, add/update a record to indicate that the student has just now
        # seen the newsworthy thing.
        # Note: Using OrderedDict's here because they permit deletion during
        # iteration.
        seen_items = collections.OrderedDict(
            {i.resource_key: i for i in self.get_seen_items()})
        seen_items[resource_key] = SeenItem(resource_key, now)

        # As long as we're here, also take this opportunity to clean up:
        # Remove pairs of items where we have a 'seen' record and a 'news'
        # record for the same key and where the item was seen more than
        # NEWSWORTHINESS_SECONDS ago.  We retain things that are only
        # slightly-old so that students can still use the News feature to
        # re-find stuff they've already seen but may still want to re-visit.
        news_items = collections.OrderedDict(
            {n.resource_key: n for n in self.get_news_items()})
        for resource_key, seen_item in seen_items.iteritems():
            if (now - seen_item.when).total_seconds() > NEWSWORTHINESS_SECONDS:
                if resource_key in news_items:
                    del news_items[resource_key]
                    del seen_items[resource_key]
                    break

        self._set_seen_items(seen_items.values())
        self._set_news_items(news_items.values())


class StudentNewsDao(BaseNewsDao):
    DTO = StudentNewsDto
    ENTITY = StudentNewsEntity
    ENTITY_KEY_TYPE = models.BaseJsonDao.EntityKeyTypeName

    @classmethod
    def load_or_default(cls):
        # Sanity check: Re-verify that we have a Student.  Calling handlers
        # should be either checking first or watching for these exceptions and
        # converting to reasonable HTML responses.
        user = users.get_current_user()
        if not user:
            raise ValueError('No current user.')
        student = models.Student.get_enrolled_student_by_user(user)
        if not student:
            raise ValueError('No Student found for current user.')
        dto = cls.load(user.user_id())
        if not dto:
            dto = StudentNewsDto(user.user_id(), {})
        return dto

    @classmethod
    def mark_item_seen(cls, resource_key):
        """Convenience method when only one operation is needed on DTO."""
        dto = cls.load_or_default()
        dto.mark_item_seen(resource_key)
        cls.save(dto)

    @classmethod
    def get_seen_items(cls):
        """Convenience method when only one operation is needed on DTO."""
        dto = cls.load_or_default()
        return dto.get_seen_items()


def course_page_navbar_callback(app_context):
    """Generate HTML for inclusion on tabs bar.

    Thankfully, this function gets called pretty late during page generation,
    so StudentNewsDao should already have been notified when we're on a page
    that was newsworthy, but now is not because the student has seen it.
    """

    # If we don't have a registered student in session, no news for you!
    user = users.get_current_user()
    if not user:
        return []
    student = models.Student.get_enrolled_student_by_user(user)
    if not student or student.is_transient:
        return []
    student_dao = StudentNewsDao.load_or_default()

    # Combine all news items for consideration.
    news = student_dao.get_news_items() + CourseNewsDao.get_news_items()
    seen_times = {s.resource_key: s.when
                  for s in student_dao.get_seen_items()}

    # Filter out items that student can't see due to label matching.  Do
    # this before reducing number of items displayed to a fixed maximum.
    course = courses.Course.get(app_context)
    models.LabelDAO.apply_course_track_labels_to_student_labels(
        course, student, news)

    # Run through news items, categorizing 'new' and 'old' news for display.
    # news is everything else.
    new_news = []
    old_news = []
    now = utc.now_as_datetime()
    enrolled_on = student.enrolled_on.replace(microsecond=0)
    for item in news:
        seen_when = seen_times.get(item.resource_key)
        if seen_when is None:
            # Items not yet seen at all get marked for CSS highlighting.
            # Items prior to student enrollment are not incremental new stuff;
            # we assume that on enroll, the student is on notice that all
            # course content is "new", and we don't need to redundantly bring
            # it to their attention.
            if item.when >= enrolled_on:
                item.is_new_news = True
                new_news.append(item)
        elif (now - seen_when).total_seconds() < NEWSWORTHINESS_SECONDS:
            # Items seen recently are always shown, but with CSS dimming.
            item.is_new_news = False
            new_news.append(item)
        else:
            # Items seen and not recently are put on seprate list for
            # inclusion only if there are few new items.
            item.is_new_news = False
            old_news.append(item)

    # Display setup: Order by time within new, old set.  Show all new
    # news, and if there are few of those, some old news as well.
    new_news.sort(key=lambda n: (n.is_new_news, n.when), reverse=True)
    old_news.sort(key=lambda n: n.when, reverse=True)
    news = new_news + old_news[
        0:max(0, MIN_NEWS_ITEMS_TO_DISPLAY - len(new_news))]

    for item in news:
        try:
            key = resource.Key.fromstring(item.resource_key)
            resource_handler = (
                i18n_dashboard.TranslatableResourceRegistry.get_by_type(
                    key.type))
            item.i18n_title = resource_handler.get_i18n_title(key)
        except AssertionError:
            # Not all news things are backed by AbstractResourceHandler types.
            # Fall back to news-specific registry for these.
            resource_handler = I18nTitleRegistry
            key_type, _ = item.resource_key.split(resource.Key.SEPARATOR, 1)
            item.i18n_title = resource_handler.get_i18n_title(
                key_type, item.resource_key)

    # Fill template
    template_environ = app_context.get_template_environ(
        app_context.get_current_locale(), [TEMPLATES_DIR])
    template = template_environ.get_template('news.html', [TEMPLATES_DIR])
    return [
        jinja2.utils.Markup(template.render({'news': news}, autoescape=True))]


class I18nTitleRegistry(object):

    _REGISTRY = {}

    @classmethod
    def register(cls, type_str, i18n_title_provider):
        """Register a resource handler for news items.

        If your newsworthy thing has already implemented a class inheriting
        from common.resource.AbstractResourceHandler, you need not register
        here; that class will be detected from its registration with
        common.resource.Registry and used directly.  This registry is only for
        things that are newsworthy but do not represent actual resource
        entities.  This primarily includes less tangible notions, such as
        course completion indications.

        Args:
          i18n_title_provider: A callback that can provide i18n'd title string
              for a news item.  The callback is provided with one argument:
              key: Whatever was set as the news item's key string when it
              was added.  If the current course or locale are required, use
              the various get_current_X functions in controllers.sites.
        """
        if type_str in cls._REGISTRY:
            raise ValueError('Resource type %s is already registered.' %
                             type_str)
        cls._REGISTRY[type_str] = i18n_title_provider

    @classmethod
    def unregister(cls, type_str):
        if type_str in cls._REGISTRY:
            del cls._REGISTRY[type_str]

    @classmethod
    def get_i18n_title(cls, key_type, key):
        return cls._REGISTRY[key_type](key)


def register_module():

    name = NEWS_SETTINGS_SECTION + ':' + IS_NEWS_ENABLED_SETTING
    news_enabled = schema_fields.SchemaField(
        name, 'News', 'boolean',
        optional=True, i18n=False, default_value=True,
        description=services.help_urls.make_learn_more_message(
            messages.IS_NEWS_ENABLED_MESSAGE, name))

    course_settings_fields = (
        lambda c: news_enabled,
    )

    def on_module_enabled():
        courses.Course.OPTIONS_SCHEMA_PROVIDERS[
            courses.Course.SCHEMA_SECTION_COURSE].extend(course_settings_fields)

        # Register "News" element on navbar.
        utils.CourseHandler.LEFT_LINKS.append(course_page_navbar_callback)

        # Register StudentNewsEntity for removal when student requests their
        # data be purged.
        data_removal.Registry.register_indexed_by_user_id_remover(
            StudentNewsEntity.delete_by_key)

    # pylint: disable=global-statement
    global custom_module
    custom_module = custom_modules.Module(
        'News', messages.MODULE_DESCRIPTION,
        global_routes=[],
        namespaced_routes=[],
        notify_module_enabled=on_module_enabled)
    return custom_module
