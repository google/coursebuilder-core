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

"""Test news module functionality."""

__author__ = [
    'mgainer@google.com (Mike Gainer)',
]

import time

from controllers import sites
from common import utc
from common import utils as common_utils
from models import models
from modules.news import news
from modules.news import news_tests_lib
from tests.functional import actions

from google.appengine.api import namespace_manager


class NewsTestBase(actions.TestBase):

    ADMIN_EMAIL = 'admin@foo.com'
    STUDENT_EMAIL = 'student@foo.com'
    COURSE_NAME = 'news_test'
    NAMESPACE = 'ns_%s' % COURSE_NAME

    def setUp(self):
        super(NewsTestBase, self).setUp()
        self.base = '/' + self.COURSE_NAME
        self.app_context = actions.simple_add_course(
            self.COURSE_NAME, self.ADMIN_EMAIL, 'Title')
        self.maxDiff = None  # Show full text expansion of expect mismatches.

        # Simplify equivalence checks by supplying a deep comparator, rather
        # than getting object instance equality comparison.
        def news_items_are_equal(thing_one, thing_two):
            return (thing_one.resource_key == thing_two.resource_key and
                    thing_one.when == thing_two.when and
                    thing_one.url == thing_two.url and
                    thing_one.labels == thing_two.labels)
        news.NewsItem.__eq__ = news_items_are_equal
        news.NewsItem.__repr__ = lambda x: x.__dict__.__repr__()
        def seen_items_are_equal(thing_one, thing_two):
            return (thing_one.resource_key == thing_two.resource_key and
                    abs((thing_one.when - thing_two.when).total_seconds()) < 2)
        news.SeenItem.__eq__ = seen_items_are_equal
        news.SeenItem.__repr__ = lambda x: x.__dict__.__repr__()
        news.I18nTitleRegistry.register(
            'test', lambda x: 'Test Item ' + x.split(':', 1)[1])

        self.old_namespace = namespace_manager.get_namespace()
        namespace_manager.set_namespace(self.NAMESPACE)

        # News is always enabled during own-module tests so that we do not
        # accumulate any regressions within ourselves.  Other modules are
        # free to simply disable if they wish.
        self.save_is_enabled = news.is_enabled
        news.is_enabled = lambda: True
        if not news.custom_module.enabled:
            news.custom_module.enable()

    def tearDown(self):
        news.is_enabled = self.save_is_enabled
        del news.NewsItem.__eq__
        del news.NewsItem.__repr__
        del news.SeenItem.__eq__
        del news.SeenItem.__repr__
        news.I18nTitleRegistry.unregister('test')
        sites.reset_courses()
        namespace_manager.set_namespace(self.old_namespace)
        super(NewsTestBase, self).tearDown()


class NewsEntityTests(NewsTestBase):

    def test_get_course_news_with_no_entity(self):
        self.assertEquals([], news.CourseNewsDao.get_news_items())

    def test_get_student_news_with_no_user(self):
        with self.assertRaises(ValueError):
            news.StudentNewsDao.get_news_items()

    def test_get_student_news_with_no_student(self):
        actions.login(self.STUDENT_EMAIL)
        with self.assertRaises(ValueError):
            self.assertEquals([], news.StudentNewsDao.get_news_items())

    def test_get_student_news_with_no_entity(self):
        actions.login(self.STUDENT_EMAIL)
        actions.register(self, 'John Smith')
        self.assertEquals([], news.StudentNewsDao.get_news_items())

    def _test_add_news_item(self, dao_class):
        now = utc.now_as_datetime()
        news_item = news.NewsItem('test:key', 'test:url', when=now)
        dao_class.add_news_item(news_item)
        self.assertEquals([news_item], dao_class.get_news_items())

    def test_add_course_news_item(self):
        self._test_add_news_item(news.CourseNewsDao)

    def test_add_student_news_item(self):
        actions.login(self.STUDENT_EMAIL)
        actions.register(self, 'John Smith')
        self._test_add_news_item(news.StudentNewsDao)

    def _test_remove_news_item(self, dao_class):
        # Just need to see no explosions.
        dao_class.remove_news_item('no_such_item_key')

        # Add an item so that we can remove it next.
        now = utc.now_as_datetime()
        news_item = news.NewsItem('test:key', 'test:url', when=now)
        dao_class.add_news_item(news_item)
        self.assertEquals([news_item], dao_class.get_news_items())

        # Remove the item; verify empty set of items.
        dao_class.remove_news_item(news_item.resource_key)
        self.assertEquals([], dao_class.get_news_items())

        # Remove again an item that had existed; just want no explosions.
        dao_class.remove_news_item(news_item.resource_key)
        self.assertEquals([], dao_class.get_news_items())

    def test_remove_course_news_item(self):
        self._test_remove_news_item(news.CourseNewsDao)

    def test_remove_student_news_item(self):
        actions.login(self.STUDENT_EMAIL)
        actions.register(self, 'John Smith')
        self._test_remove_news_item(news.StudentNewsDao)

    def _test_add_duplicate_news_item(self, dao_class):
        now = utc.now_as_datetime()
        news_item = news.NewsItem('test:key', 'test:url', when=now)
        dao_class.add_news_item(news_item)
        dao_class.add_news_item(news_item)
        dao_class.add_news_item(news_item)
        dao_class.add_news_item(news_item)
        self.assertEquals([news_item], dao_class.get_news_items())

    def test_add_duplicate_course_news_item(self):
        self._test_add_duplicate_news_item(news.CourseNewsDao)

    def test_add_duplicate_student_news_item(self):
        actions.login(self.STUDENT_EMAIL)
        actions.register(self, 'John Smith')
        self._test_add_duplicate_news_item(news.StudentNewsDao)

    def _test_add_newer_and_older_news_item(self, dao_class):
        now_ts = utc.now_as_timestamp()

        older = news.NewsItem('test:key', 'test:url',
                              when=utc.timestamp_to_datetime(now_ts))
        newer = news.NewsItem('test:key', 'test:url',
                              when=utc.timestamp_to_datetime(now_ts + 1))

        dao_class.add_news_item(older)
        self.assertEquals([older], dao_class.get_news_items())

        # Newer items added with no-overwrite flag do not displace older item.
        dao_class.add_news_item(newer, overwrite_existing=False)
        self.assertEquals([older], dao_class.get_news_items())

        # Newer items displace older items with the same key.
        dao_class.add_news_item(newer)
        self.assertEquals([newer], dao_class.get_news_items())

        # But older items w/ same key do not displace newer ones.
        dao_class.add_news_item(older)
        self.assertEquals([newer], dao_class.get_news_items())

    def test_add_newer_and_older_course_news_item(self):
        self._test_add_newer_and_older_news_item(news.CourseNewsDao)

    def test_add_newer_and_older_student_news_item(self):
        actions.login(self.STUDENT_EMAIL)
        actions.register(self, 'John Smith')
        self._test_add_newer_and_older_news_item(news.StudentNewsDao)

    def _test_add_multiple_news_items(self, dao_class):
        NUM_ITEMS = 10
        expected_items = []
        for x in xrange(NUM_ITEMS):
            news_item = news.NewsItem('test:key_%d' % x, 'test:url')
            expected_items.append(news_item)
            dao_class.add_news_item(news_item)
        actual_items = dao_class.get_news_items()
        self.assertEquals(expected_items, actual_items)

    def test_add_multiple_course_news_items(self):
        self._test_add_multiple_news_items(news.CourseNewsDao)

    def test_add_multiple_student_news_items(self):
        actions.login(self.STUDENT_EMAIL)
        actions.register(self, 'John Smith')
        self._test_add_multiple_news_items(news.StudentNewsDao)

    def _test_mark_item_seen(self, dao_class):
        actions.login(self.STUDENT_EMAIL)
        actions.register(self, 'John Smith')

        now = utc.now_as_datetime()
        news_item = news.NewsItem('test:key', 'test:url', when=now)
        dao_class.add_news_item(news_item)
        self.assertEquals([news_item], dao_class.get_news_items())
        news.StudentNewsDao.mark_item_seen(news_item.resource_key)

        seen_item = news.SeenItem(news_item.resource_key, now)
        self.assertEquals([seen_item], news.StudentNewsDao.get_seen_items())

        # Move time forward one tick, and verify that the timestamp *does*
        # move forward on the 'seen' record.
        time.sleep(1)
        seen_item.when = utc.now_as_datetime()
        news.StudentNewsDao.mark_item_seen(news_item.resource_key)
        self.assertEquals([seen_item], news.StudentNewsDao.get_seen_items())

    def test_mark_course_item_seen(self):
        self._test_mark_item_seen(news.CourseNewsDao)

    def test_mark_student_item_seen(self):
        self._test_mark_item_seen(news.StudentNewsDao)

    def test_old_student_news_removed_when_seen_far_in_the_past(self):
        actions.login(self.STUDENT_EMAIL)
        actions.register(self, 'John Smith')
        now = utc.now_as_datetime()
        item_one = news.NewsItem('key_one', 'test:url', when=now)
        item_two = news.NewsItem('key_two', 'test:url', when=now)
        news.StudentNewsDao.add_news_item(item_one)
        news.StudentNewsDao.add_news_item(item_two)

        # Nothing seen; should have both news items still.
        news_items = news.StudentNewsDao.get_news_items()
        self.assertEquals(2, len(news_items))
        self.assertIn(item_one, news_items)
        self.assertIn(item_two, news_items)

        # Now we mark item_one as visited.  Still should retain both items,
        # since we're within the newsworthiness time limit.
        news.StudentNewsDao.mark_item_seen(item_one.resource_key)
        seen_one = news.SeenItem(item_one.resource_key, now)
        self.assertEquals([seen_one], news.StudentNewsDao.get_seen_items())
        news_items = news.StudentNewsDao.get_news_items()
        self.assertEquals(2, len(news_items))
        self.assertIn(item_one, news_items)
        self.assertIn(item_two, news_items)

        # Set the newsworthiness timeout to one second so we can get this
        # done in a sane amount of time.
        try:
            save_newsworthiness_seconds = news.NEWSWORTHINESS_SECONDS
            news.NEWSWORTHINESS_SECONDS = 1
            time.sleep(2)
            now = utc.now_as_datetime()

            # Marking item two as seen should have the side effect of
            # removing the seen and news items for 'key_one'.
            news.StudentNewsDao.mark_item_seen(item_two.resource_key)
            self.assertEquals([item_two], news.StudentNewsDao.get_news_items())
            seen_two = news.SeenItem(item_two.resource_key, now)
            self.assertEquals([seen_two], news.StudentNewsDao.get_seen_items())

        finally:
            news.NEWSWORTHINESS_SECONDS = save_newsworthiness_seconds



class NewsHttpTests(NewsTestBase):

    def _set_student_enroll_date(self, user, when):
        # Move student enroll date back to when news item appears, so
        # news item is considered to be newsworthy for this student.
        student = models.Student.get_enrolled_student_by_user(user)
        student.enrolled_on = when
        student.put()

    def test_get_news_no_user(self):
        response = news.course_page_navbar_callback(self.app_context)
        self.assertEquals([], response)

    def test_get_news_no_student(self):
        actions.login(self.STUDENT_EMAIL)
        response = news.course_page_navbar_callback(self.app_context)
        self.assertEquals([], response)

    def _get_news_title_styles(self, soup):
        title = soup.find(id='gcb_news_titlebar_text')
        return title.get('class')

    def test_get_news_no_news(self):
        actions.login(self.STUDENT_EMAIL)
        actions.register(self, 'John Smith')
        response = self.get('course')
        soup = self.parse_html_string_to_soup(response.body)
        self.assertEquals(['has_only_old_news'],
                          self._get_news_title_styles(soup))
        self.assertEquals([], news_tests_lib.extract_news_items_from_soup(soup))

    def test_get_news_unseen(self):
        user = actions.login(self.STUDENT_EMAIL)
        actions.register(self, 'John Smith')

        # Added item is older than newsworthiness cutoff, but student has
        # not been marked as having seen it, so it's new news.
        then_ts = utc.now_as_timestamp() - news.NEWSWORTHINESS_SECONDS - 1
        then = utc.timestamp_to_datetime(then_ts)
        self._set_student_enroll_date(user, then)
        news_item = news.NewsItem('test:key', 'test:url', then)
        news.CourseNewsDao.add_news_item(news_item)

        response = self.get('course')
        soup = self.parse_html_string_to_soup(response.body)
        self.assertEquals(['has_new_news'],
                          self._get_news_title_styles(soup))
        self.assertEquals(
            [news_tests_lib.NewsItem('Test Item key', 'test:url', True)],
            news_tests_lib.extract_news_items_from_soup(soup))

    def test_get_news_recently_seen(self):
        user = actions.login(self.STUDENT_EMAIL)
        actions.register(self, 'John Smith')

        # Newsworthy thing happened beyond newsworthy time limit,
        then_ts = utc.now_as_timestamp() - news.NEWSWORTHINESS_SECONDS - 1
        then = utc.timestamp_to_datetime(then_ts)
        self._set_student_enroll_date(user, then)
        news_item = news.NewsItem('test:key', 'test:url', then)
        news.CourseNewsDao.add_news_item(news_item)
        # But student has seen the thing, so it's marked as non-new.
        news.StudentNewsDao.mark_item_seen('test:key')

        response = self.get('course')
        soup = self.parse_html_string_to_soup(response.body)
        self.assertEquals(['has_only_old_news'],
                          self._get_news_title_styles(soup))
        self.assertEquals(
            [news_tests_lib.NewsItem('Test Item key', 'test:url', False)],
            news_tests_lib.extract_news_items_from_soup(soup))


    def test_get_news_some_old_some_new(self):
        user = actions.login(self.STUDENT_EMAIL)
        actions.register(self, 'John Smith')

        # Newsworthy thing happened beyond newsworthy time limit,
        then_ts = utc.now_as_timestamp() - news.NEWSWORTHINESS_SECONDS - 1
        then = utc.timestamp_to_datetime(then_ts)
        self._set_student_enroll_date(user, then)
        news_item = news.NewsItem('test:one', 'url_one', then)
        news.CourseNewsDao.add_news_item(news_item)
        news_item = news.NewsItem('test:two', 'url_two', then)
        news.CourseNewsDao.add_news_item(news_item)
        # But student has seen the thing, so it's marked as non-new.
        news.StudentNewsDao.mark_item_seen('test:one')

        response = self.get('course')
        soup = self.parse_html_string_to_soup(response.body)
        self.assertEquals(['has_new_news'],
                          self._get_news_title_styles(soup))
        self.assertEquals(
            [
                news_tests_lib.NewsItem('Test Item two', 'url_two', True),
                news_tests_lib.NewsItem('Test Item one', 'url_one', False),
            ],
            news_tests_lib.extract_news_items_from_soup(soup))

    def test_student_and_course_news(self):
        user = actions.login(self.STUDENT_EMAIL)
        actions.register(self, 'John Smith')

        then_ts = utc.now_as_timestamp() - news.NEWSWORTHINESS_SECONDS - 1
        then = utc.timestamp_to_datetime(then_ts)
        self._set_student_enroll_date(user, then)
        news_item = news.NewsItem('test:one', 'url_one', then)
        news.CourseNewsDao.add_news_item(news_item)
        news_item = news.NewsItem('test:two', 'url_two', then)
        news.StudentNewsDao.add_news_item(news_item)

        response = self.get('course')
        soup = self.parse_html_string_to_soup(response.body)
        self.assertEquals(['has_new_news'],
                          self._get_news_title_styles(soup))
        self.assertEquals(
            [
                news_tests_lib.NewsItem('Test Item two', 'url_two', True),
                news_tests_lib.NewsItem('Test Item one', 'url_one', True),
            ],
            news_tests_lib.extract_news_items_from_soup(soup))

    def test_old_news_excluded_by_new_news(self):
        NUM_OLD_ITEMS = news.MIN_NEWS_ITEMS_TO_DISPLAY * 2
        NUM_NEW_ITEMS = news.MIN_NEWS_ITEMS_TO_DISPLAY * 2

        user = actions.login(self.STUDENT_EMAIL)
        actions.register(self, 'John Smith')
        then_ts = (
            utc.now_as_timestamp() - news.NEWSWORTHINESS_SECONDS -
            NUM_OLD_ITEMS - 1)
        self._set_student_enroll_date(user, utc.timestamp_to_datetime(then_ts))

        # Add many old items - twice as many as we're willing to show.
        expected_old_items = []
        for i in xrange(NUM_OLD_ITEMS):
            expected_old_items.append(news_tests_lib.NewsItem(
                'Test Item %i' % i, 'u%i' % i, False))

            then = utc.timestamp_to_datetime(then_ts + i)
            item = news.NewsItem('test:%d' % i, 'u%d' % i, then)
            news.CourseNewsDao.add_news_item(item)
            news.StudentNewsDao.mark_item_seen('test:%d' % i)

        # Force everything we just did to be old news.
        try:
            save_newsworthiness_seconds = news.NEWSWORTHINESS_SECONDS
            news.NEWSWORTHINESS_SECONDS = 1
            time.sleep(2)

            # Expect that we see old items in newest-first order.
            expected_old_items.reverse()

            # Verify that we are only shown half of the old-news items before
            # we add any new ones.
            response = self.get('course')
            soup = self.parse_html_string_to_soup(response.body)
            self.assertEquals(
                expected_old_items[0:NUM_OLD_ITEMS / 2],
                news_tests_lib.extract_news_items_from_soup(soup))

            # Start adding new news items, one at a time.
            expected_new_items = []
            for i in xrange(NUM_NEW_ITEMS):
                j = NUM_OLD_ITEMS + i
                expected_new_items.append(news_tests_lib.NewsItem(
                    'Test Item %i' % j, 'u%i' % j, True))
                then = utc.timestamp_to_datetime(then_ts + j)
                item = news.NewsItem('test:%d' % j, 'u%d' % j, then)
                news.CourseNewsDao.add_news_item(item)

                # Expect to see all new items, and maybe some old items,
                # as long as the new ones are not crowding them out.
                # New items should appear strictly first.
                expected_items = list(reversed(expected_new_items))
                if i < news.MIN_NEWS_ITEMS_TO_DISPLAY:
                    expected_items += expected_old_items[
                        :news.MIN_NEWS_ITEMS_TO_DISPLAY - i - 1]

                response = self.get('course')
                soup = self.parse_html_string_to_soup(response.body)
                actual_items = news_tests_lib.extract_news_items_from_soup(soup)
                self.assertEquals(expected_items, actual_items)

        finally:
            news.NEWSWORTHINESS_SECONDS = save_newsworthiness_seconds

    def test_news_disabled_ui(self):
        with actions.OverriddenEnvironment({
                news.NEWS_SETTINGS_SECTION: {
                    news.IS_NEWS_ENABLED_SETTING: False,
                }}):
            response = self.get('course')
            soup = self.parse_html_string_to_soup(response.body)
            title = soup.find(id='gcb_news_titlebar_text')
            self.assertIsNone(title)

    def test_news_before_user_registration_is_not_news(self):
        news_item = news.NewsItem(
            'test:before', 'before_url', utc.now_as_datetime())
        news.CourseNewsDao.add_news_item(news_item)
        time.sleep(1)
        user = actions.login(self.STUDENT_EMAIL)
        actions.register(self, 'John Smith')
        now = utc.now_as_datetime()
        news_item = news.NewsItem('test:at', 'at_url', now)
        self._set_student_enroll_date(user, now)
        news.CourseNewsDao.add_news_item(news_item)
        time.sleep(1)
        news_item = news.NewsItem(
            'test:after', 'after_url', utc.now_as_datetime())
        news.CourseNewsDao.add_news_item(news_item)

        # Expect to not see news item from before student registration.
        response = self.get('course')
        soup = self.parse_html_string_to_soup(response.body)
        self.assertEquals(
            [news_tests_lib.NewsItem('Test Item after', 'after_url', True),
             news_tests_lib.NewsItem('Test Item at', 'at_url', True)],
            news_tests_lib.extract_news_items_from_soup(soup))

    def test_news_label_filtering(self):
        actions.login(self.STUDENT_EMAIL)
        actions.register(self, 'John Smith')

        label_foo = models.LabelDAO.save(models.LabelDTO(
            None, {'title': 'Foo',
                   'descripton': 'foo',
                   'type': models.LabelDTO.LABEL_TYPE_COURSE_TRACK}))
        label_bar = models.LabelDAO.save(models.LabelDTO(
            None, {'title': 'Bar',
                   'descripton': 'bar',
                   'type': models.LabelDTO.LABEL_TYPE_COURSE_TRACK}))

        now_ts = utc.now_as_timestamp() + 3  # Avoid filtering in-past items
        news.CourseNewsDao.add_news_item(news.NewsItem(
            'test:no_labels', 'url_no_labels',
            when=utc.timestamp_to_datetime(now_ts)))
        news.CourseNewsDao.add_news_item(news.NewsItem(
            'test:with_labels', 'url_with_labels',
            labels=common_utils.list_to_text([label_foo]),
            when=utc.timestamp_to_datetime(now_ts - 1)))

        # Student starts life with no labels, so should match both items.
        response = self.get('course')
        soup = self.parse_html_string_to_soup(response.body)
        self.assertEquals(
            [news_tests_lib.NewsItem(
                'Test Item no_labels', 'url_no_labels', True),
             news_tests_lib.NewsItem(
                 'Test Item with_labels', 'url_with_labels', True)],
            news_tests_lib.extract_news_items_from_soup(soup))

        # Apply non-matching label to Student; should not see labeled news.
        models.Student.set_labels_for_current(
            common_utils.list_to_text([label_bar]))
        response = self.get('course')
        soup = self.parse_html_string_to_soup(response.body)
        self.assertEquals(
            [news_tests_lib.NewsItem(
                'Test Item no_labels', 'url_no_labels', True)],
            news_tests_lib.extract_news_items_from_soup(soup))

        # Apply matching label to Student; should again see labeled news.
        models.Student.set_labels_for_current(
            common_utils.list_to_text([label_foo, label_bar]))
        response = self.get('course')
        soup = self.parse_html_string_to_soup(response.body)
        self.assertEquals(
            [news_tests_lib.NewsItem(
                'Test Item no_labels', 'url_no_labels', True),
             news_tests_lib.NewsItem(
                 'Test Item with_labels', 'url_with_labels', True)],
            news_tests_lib.extract_news_items_from_soup(soup))
