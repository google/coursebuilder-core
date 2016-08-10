# coding: utf-8
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

"""Tests for the internationalization (i18n) workflow."""

__author__ = [
    'Mike Gainer (mgainer@google.com)'
]

import re
import time
import urllib
import urlparse

from common import crypto
from common import resource
from common import utc
from controllers import sites
from models import models
from models import transforms
from modules.announcements import announcements
from modules.i18n_dashboard import i18n_dashboard
from modules.news import news
from modules.news import news_tests_lib
from tests.functional import actions

from google.appengine.api import namespace_manager
from google.appengine.ext import db


class AnnouncementsTests(actions.TestBase):

    COURSE = 'announcements_course'
    NAMESPACE = 'ns_%s' % COURSE
    ADMIN_EMAIL = 'admin@foo.com'

    def setUp(self):
        super(AnnouncementsTests, self).setUp()
        self.app_context = actions.simple_add_course(
            self.COURSE, self.ADMIN_EMAIL, 'Announcements')
        self.old_namespace = namespace_manager.get_namespace()
        self.base = '/' + self.COURSE
        namespace_manager.set_namespace('ns_%s' % self.COURSE)
        actions.login(self.ADMIN_EMAIL, is_admin=True)

    def tearDown(self):
        namespace_manager.set_namespace(self.old_namespace)
        sites.reset_courses()
        super(AnnouncementsTests, self).tearDown()

    def _add_announcement(self):
        request = {
            'action': announcements.AnnouncementsDashboardHandler.ADD_ACTION,
            'xsrf_token': crypto.XsrfTokenManager.create_xsrf_token(
                announcements.AnnouncementsDashboardHandler.ADD_ACTION)
        }
        response = self.post(
            announcements.AnnouncementsDashboardHandler.LINK_URL, request)
        self.assertEquals(302, response.status_int)

        url = urlparse.urlparse(response.location)
        params = urlparse.parse_qs(url.query)
        return params['key'][0]

    def _put_announcement(self, data, expect_errors=False, xsrf_token=None):
        if not xsrf_token:
            xsrf_token = crypto.XsrfTokenManager.create_xsrf_token(
                announcements.AnnouncementsItemRESTHandler.ACTION)
        request = {
            'key': data['key'],
            'xsrf_token': xsrf_token,
            'payload': transforms.dumps(data),
        }
        response = self.put(
            announcements.AnnouncementsItemRESTHandler.URL.lstrip('/'),
            {'request': transforms.dumps(request)})
        self.assertEquals(response.status_int, 200)
        payload = transforms.loads(response.body)
        if not expect_errors:
            self.assertEquals(200, payload['status'])
            self.assertEquals('Saved.', payload['message'])
        return payload

    def _get_announcement(self, key):
        response = self.get(
            announcements.AnnouncementsItemRESTHandler.URL.lstrip('/') + '?' +
            urllib.urlencode({'key': key}))
        self.assertEquals(200, response.status_int)
        payload = transforms.loads(response.body)
        if payload['status'] == 200:
            return transforms.loads(payload['payload'])
        else:
            return None

    def _delete_announcement(self, key):
        request = {
            'key': key,
            'action': announcements.AnnouncementsDashboardHandler.DELETE_ACTION,
            'xsrf_token': crypto.XsrfTokenManager.create_xsrf_token(
                announcements.AnnouncementsDashboardHandler.DELETE_ACTION),
        }
        response = self.post(
            announcements.AnnouncementsDashboardHandler.LINK_URL, request)
        self.assertEquals(302, response.status_int)

    def _verify_announcements(self, expected_titles, expected_contents):
        response = self.get(
            announcements.AnnouncementsStudentHandler.URL.lstrip('/'))
        soup = self.parse_html_string_to_soup(response.body)
        titles = soup.select('.gcb-announcement-title')
        titles = [title.text.strip() for title in titles]
        titles = [re.sub(r'\s+', ' ', title) for title in titles]
        contents = soup.select('.gcb-announcement-content')
        contents = [content.text.strip() for content in contents]
        contents = [re.sub(r'\s+', ' ', content) for content in contents]
        self.assertEquals(expected_titles, titles)
        self.assertEquals(expected_contents, contents)

    def test_dashboard_controls(self):
        """Test course author can manage announcements."""

        # add new
        response = self.get('edit_announcements?action=edit_announcements')
        add_form = response.forms['gcb-add-announcement']
        response = self.submit(add_form)
        self.assertEquals(response.status_int, 302)

        # check edit form rendering
        response = response.follow()
        self.assertEquals(response.status_int, 200)
        self.assertIn('/rest/announcements/item?key=', response.body)
        response = self.get('edit_announcements?action=edit_announcements')
        self.assertIn(
            announcements.AnnouncementsDashboardHandler.DEFAULT_TITLE_TEXT,
            response.body)

        # check added
        self._verify_announcements(
            [announcements.AnnouncementsDashboardHandler.DEFAULT_TITLE_TEXT +
             ' (Private)'], [''])

        # delete draft
        response = self.get('edit_announcements?action=edit_announcements')
        delete_form = response.forms['gcb-delete-announcement-0']
        response = self.submit(delete_form)
        self.assertEquals(response.status_int, 302)

        # check deleted
        response = self.get('edit_announcements?action=edit_announcements')
        self.assertNotIn(
            announcements.AnnouncementsDashboardHandler.DEFAULT_TITLE_TEXT,
            response.body)

    def test_announcements_page_admin_controls(self):
        response = self.get(
            announcements.AnnouncementsStudentHandler.URL.lstrip('/'))
        add_form = response.forms['gcb-add-announcement']
        response = self.submit(add_form)
        self.assertEquals(response.status_int, 302)

        # check edit form rendering
        response = response.follow()
        self.assertEquals(response.status_int, 200)
        self.assertIn('/rest/announcements/item?key=', response.body)

        response = self.get('edit_announcements?action=edit_announcements')
        self.assertIn(
            announcements.AnnouncementsDashboardHandler.DEFAULT_TITLE_TEXT,
            response.body)

    def test_announcements_page_no_admin_control_for_student(self):
        actions.login('student@example.com')
        response = self.get(
            announcements.AnnouncementsStudentHandler.URL.lstrip('/'))
        soup = self.parse_html_string_to_soup(response.body)
        add_forms = soup.select('#gcb-add-announcement')
        self.assertEquals(0, len(add_forms))

    def test_rest_get_not_found(self):
        response = self.get(
            announcements.AnnouncementsItemRESTHandler.URL.lstrip('/') + '?' +
            urllib.urlencode({'key': 'foozle'}), expect_errors=True)
        self.assertEquals(200, response.status_int)
        response = transforms.loads(response.body)
        self.assertEquals(404, response['status'])

    def test_create_announcement_defaults(self):
        key = self._add_announcement()
        data = self._get_announcement(key)

        expected_date = utc.to_text(
            seconds=utc.day_start(utc.now_as_timestamp()))
        self.assertEquals(data['date'], expected_date)
        expected_key = str(db.Key.from_path(
            announcements.AnnouncementEntity.kind(), 1))
        self.assertEquals(data['key'], expected_key)
        self.assertEquals(data['html'], '')
        self.assertEquals(data['is_draft'], True)
        self.assertEquals(
            data['title'],
            announcements.AnnouncementsDashboardHandler.DEFAULT_TITLE_TEXT)

    def test_rest_get_draft_not_permitted_for_students(self):
        key = self._add_announcement()
        actions.login('student@example.com')
        response = self.get(
            announcements.AnnouncementsItemRESTHandler.URL.lstrip('/') + '?' +
            urllib.urlencode({'key': key}), expect_errors=True)
        self.assertEquals(200, response.status_int)
        response = transforms.loads(response.body)
        self.assertEquals(401, response['status'])
        self.assertEquals('Access denied.', response['message'])

    def test_put_as_student(self):
        key = self._add_announcement()
        sent_data = {
            'key': key,
            'date': utc.to_text(seconds=0),
            'html': 'Twas brillig, and the slithy toves',
            'title': 'Jabberwocky',
            'is_draft': False,
        }
        actions.login('student@example.com')
        response = self._put_announcement(sent_data, expect_errors=True)
        self.assertEquals(401, response['status'])
        self.assertEquals('Access denied.', response['message'])

    def test_put_bad_xsrf(self):
        key = self._add_announcement()
        sent_data = {
            'key': key,
            'date': utc.to_text(seconds=0),
            'html': 'Twas brillig, and the slithy toves',
            'title': 'Jabberwocky',
            'is_draft': False,
        }
        response = self._put_announcement(sent_data, expect_errors=True,
                                          xsrf_token='gibberish')
        self.assertEquals(403, response['status'])
        self.assertEquals(
            'Bad XSRF token. Please reload the page and try again',
            response['message'])

    def test_put_unknown_key(self):
        key = str(db.Key.from_path(announcements.AnnouncementEntity.kind(), 1))
        sent_data = {
            'key': key,
            'date': utc.to_text(seconds=0),
            'html': 'Twas brillig, and the slithy toves',
            'title': 'Jabberwocky',
            'is_draft': False,
        }
        response = self._put_announcement(sent_data, expect_errors=True)
        self.assertEquals(404, response['status'])
        self.assertEquals('Object not found.', response['message'])

    def test_put_announcement(self):
        key = self._add_announcement()

        sent_data = {
            'key': key,
            'date': utc.to_text(seconds=0),
            'html': 'Twas brillig, and the slithy toves',
            'title': 'Jabberwocky',
            'is_draft': False,
        }
        self._put_announcement(sent_data)

        data = self._get_announcement(key)
        self.assertEquals(sent_data, data)

        self._verify_announcements([sent_data['title']], [sent_data['html']])

    def test_delete_announcement(self):
        key = self._add_announcement()
        self.assertIsNotNone(self._get_announcement(key))
        self._delete_announcement(key)
        data = self._get_announcement(key)
        self.assertIsNone(self._get_announcement(key))

    def test_no_announcements(self):
        self._verify_announcements(
            [],
            ['Currently, there are no announcements.'])

    def test_announcement_draft_status(self):
        key = self._add_announcement()
        data = {
            'key': key,
            'date': utc.to_text(seconds=0),
            'html': 'Twas brillig, and the slithy toves',
            'title': 'Jabberwocky',
            'is_draft': True,
        }
        self._put_announcement(data)

        # Admin sees announcement on course page
        self._verify_announcements([data['title'] + ' (Private)'],
                                   [data['html']])

        # Should appear to student as though there are no announcements.
        actions.login('student@example.com')
        self._verify_announcements([],
                                   ['Currently, there are no announcements.'])
        # Make announcement public
        actions.login(self.ADMIN_EMAIL)
        data['is_draft'] = False
        self._put_announcement(data)

        # Should now appear to both admin and student.
        self._verify_announcements([data['title']], [data['html']])
        actions.login('student@example.com')
        self._verify_announcements([data['title']], [data['html']])

    def test_announcement_ordering(self):
        items = []
        for x in xrange(5):
            key = self._add_announcement()
            data = {
                'key': key,
                'date': utc.to_text(seconds=86400 * x),
                'html': 'content %d' % x,
                'title': 'title %d' % x,
                'is_draft': False,
            }
            self._put_announcement(data)
            items.append(data)

        # Since we added items in increasing timestamp order, we now
        # reverse, since announcements are listed newest-first.
        items.reverse()
        self._verify_announcements(
            [i['title'] for i in items], [i['html'] for i in items])

    def _set_prefs_locale(self, locale):
        prefs = models.StudentPreferencesDAO.load_or_default()
        prefs.locale = locale
        models.StudentPreferencesDAO.save(prefs)

    def _assert_announcement_locale(self, announcements_title, locale):
        response = self.get('announcements')
        self.assertEquals(response.status_int, 200)
        self.assertIn(announcements_title, response.body)
        self.assertEquals(self.parse_html_string(
            response.body).get('lang'), locale)
        if locale == 'en_US':
            self._verify_announcements(['Test Announcement'],
                                       ['Announcement Content'])
        else:
            self._verify_announcements(['TEST ANNOUNCEMENT'],
                                       ['ANNOUNCEMENT CONTENT'])

    def _add_announcement_and_translation(self, locale, is_draft=False):
        announcement = announcements.AnnouncementEntity()
        announcement.title = 'Test Announcement'
        announcement.html = 'Announcement Content'
        announcement.is_draft = is_draft
        announcement.put()

        key = i18n_dashboard.ResourceBundleKey(
            announcements.ResourceHandlerAnnouncement.TYPE,
            announcement.key().id(), locale)
        dto = i18n_dashboard.ResourceBundleDTO(str(key), {
            'title': {
                'type': 'string',
                'source_value': '',
                'data': [
                    {'source_value': 'Test Announcement',
                     'target_value': 'TEST ANNOUNCEMENT'}]
            },
            'html': {
                'type': 'string',
                'source_value': '',
                'data': [
                    {'source_value': 'Announcement Content',
                     'target_value': 'ANNOUNCEMENT CONTENT'}]
            },
        })
        i18n_dashboard.ResourceBundleDAO.save(dto)
        return announcement

    def test_view_announcement_via_locale_picker(self):
        locale = 'ru_RU'
        self._add_announcement_and_translation(locale)
        actions.login('student@sample.com')
        actions.register(self, 'John Doe')

        with actions.OverriddenEnvironment({
            'course': {'locale': 'en_US'},
            'extra_locales': [{'locale': locale, 'availability': 'true'}]}):

            self._set_prefs_locale(None)
            self._assert_announcement_locale('Announcements', 'en_US')
            self._set_prefs_locale('ru_RU')
            self._assert_announcement_locale('Сообщения', 'ru_RU')

    def test_announcement_i18n_title(self):
        locale = 'de'
        announcement = self._add_announcement_and_translation(locale)
        actions.login('student@sample.com')
        actions.register(self, 'John Doe')

        # Verify that one-off title translation also works.
        try:
            sites.set_path_info('/' + self.COURSE)
            ctx = sites.get_course_for_current_request()
            save_locale = ctx.get_current_locale()
            key = announcements.TranslatableResourceAnnouncement.key_for_entity(
                announcement)

            # Untranslated
            ctx.set_current_locale(None)
            i18n_title = str(
                announcements.TranslatableResourceAnnouncement.get_i18n_title(
                    key))
            self.assertEquals('Test Announcement', i18n_title)

            # Translated
            ctx.set_current_locale(locale)
            i18n_title = str(
                announcements.TranslatableResourceAnnouncement.get_i18n_title(
                    key))
            self.assertEquals('TEST ANNOUNCEMENT', i18n_title)
        finally:
            ctx.set_current_locale(save_locale)
            sites.unset_path_info()

    @news_tests_lib.force_news_enabled
    def test_announcement_news(self):
        actions.login('student@sample.com')
        actions.register(self, 'John Doe')
        time.sleep(1)
        locale = 'de'
        announcement = self._add_announcement_and_translation(
            locale, is_draft=True)
        sent_data = {
            'key': str(announcement.key()),
            'title': 'Test Announcement',
            'date': utc.to_text(seconds=utc.now_as_timestamp()),
            'is_draft': False,
        }
        actions.login(self.ADMIN_EMAIL)
        response = self._put_announcement(sent_data)
        actions.login('student@sample.com')

        # Verify announcement news item using news API directly
        news_items = news.CourseNewsDao.get_news_items()
        self.assertEquals(1, len(news_items))
        item = news_items[0]
        now_timestamp = utc.now_as_timestamp()
        self.assertEquals(
            announcements.AnnouncementsStudentHandler.URL.lstrip('/'), item.url)
        self.assertEquals(
            str(announcements.TranslatableResourceAnnouncement.key_for_entity(
                announcement)),
            item.resource_key)
        self.assertAlmostEqual(
            now_timestamp, utc.datetime_to_timestamp(item.when), delta=10)

        # Verify announcement news item looking at HTTP response to /course
        response = self.get('course')
        soup = self.parse_html_string_to_soup(response.body)
        self.assertEquals(
            [news_tests_lib.NewsItem(
                'Test Announcement',
                announcements.AnnouncementsStudentHandler.URL.lstrip('/'),
                True)],
            news_tests_lib.extract_news_items_from_soup(soup))

        # Verify announcement news item translated title.
        self._set_prefs_locale(locale)
        response = self.get('course')
        soup = self.parse_html_string_to_soup(response.body)
        self.assertEquals(
            [news_tests_lib.NewsItem(
                'TEST ANNOUNCEMENT',
                announcements.AnnouncementsStudentHandler.URL.lstrip('/'),
                True)],
            news_tests_lib.extract_news_items_from_soup(soup))

        # Delete the announcement; news item should also go away.
        actions.login(self.ADMIN_EMAIL)
        self._delete_announcement(str(announcement.key()))
        actions.login('student@sample.com')
        response = self.get('course')
        soup = self.parse_html_string_to_soup(response.body)
        self.assertEquals([], news_tests_lib.extract_news_items_from_soup(soup))

    def test_announcement_caching(self):

        with actions.OverriddenConfig(models.CAN_USE_MEMCACHE.name, True):

            # Get the fact that there are no announcements into the cache.
            self._verify_announcements(
                [],
                ['Currently, there are no announcements.'])

            # Add an announcement
            key = self._add_announcement()
            data = {
                'key': key,
                'date': utc.to_text(seconds=0),
                'html': 'Twas brillig, and the slithy toves',
                'title': 'Jabberwocky',
                'is_draft': True,
            }
            self._put_announcement(data)

            # Admin sees announcement on course page.
            self._verify_announcements([data['title'] + ' (Private)'],
                                       [data['html']])

            # Capture cache content for later.
            cache_content = models.MemcacheManager.get(
                announcements.AnnouncementEntity._MEMCACHE_KEY)

            # Delete announcement.
            self._delete_announcement(key)

            # Check that we see no announcements.
            self._verify_announcements(
                [],
                ['Currently, there are no announcements.'])

            # Put cache content back and verify we see cache content on page.
            models.MemcacheManager.set(
                announcements.AnnouncementEntity._MEMCACHE_KEY, cache_content)
            self._verify_announcements([data['title'] + ' (Private)'],
                                       [data['html']])

    def _put_translation(self, data, locale, title, html):
        resource_key = str(i18n_dashboard.ResourceBundleKey(
            announcements.ResourceHandlerAnnouncement.TYPE,
            db.Key(encoded=data['key']).id(), locale))
        xsrf_token = crypto.XsrfTokenManager.create_xsrf_token(
            i18n_dashboard.TranslationConsoleRestHandler.XSRF_TOKEN_NAME)
        request = {
            'key': resource_key,
            'xsrf_token': xsrf_token,
            'validate': False,
            'payload': transforms.dumps({
                'title': 'Announcements',
                'key': resource_key,
                'source_locale': 'en_US',
                'target_locale': locale,
                'sections': [
                    {
                        'name': 'title',
                        'label': 'Title',
                        'type': 'string',
                        'source_value': '',
                        'data': [{
                            'source_value': data['title'],
                            'target_value': title,
                            'verb': 1,  # verb NEW
                            'old_source_value': '',
                            'changed': True
                        }]
                    },
                    {
                        'name': 'html',
                        'label': 'Body',
                        'type': 'html',
                        'source_value': '',
                        'data': [{
                            'source_value': data['html'],
                            'target_value': html,
                            'verb': 1,  # verb NEW
                            'old_source_value': '',
                            'changed': True
                        }]
                    }
                ]
            })
        }
        response = self.put(
            self.base +
            i18n_dashboard.TranslationConsoleRestHandler.URL.lstrip(),
            {'request': transforms.dumps(request)})
        self.assertEquals(200, response.status_int)
        response = transforms.loads(response.body)
        self.assertEquals(200, response['status'])

    def test_announcement_translation_caching(self):
        LOCALE = 'de'
        with actions.OverriddenConfig(models.CAN_USE_MEMCACHE.name, True):
            with actions.OverriddenEnvironment({
                'i18n': {
                    'course:locale': 'en_US',
                    'extra_locales': [
                        {'locale': LOCALE,
                         'availability': 'true'}]
                }}):

                key = self._add_announcement()
                data = {
                    'key': key,
                    'date': utc.to_text(seconds=0),
                    'html': 'Unsafe for operation',
                    'title': 'Attention',
                    'is_draft': False,
                }
                self._put_announcement(data)
                self._put_translation(data, LOCALE, 'Achtung', 'Gefahrlich!')

                actions.login('student@sample.com')
                actions.register(self, 'John Doe')
                self._set_prefs_locale(None)
                self._verify_announcements([data['title']], [data['html']])
                self._set_prefs_locale(LOCALE)
                self._verify_announcements(['Achtung'], ['Gefahrlich!'])

                # Verify that we have data added to the cache.
                cached = models.MemcacheManager.get(
                    announcements.AnnouncementEntity._cache_key(LOCALE))
                self.assertIsNotNone(cached)

                # Modify the translated version.
                actions.login(self.ADMIN_EMAIL)
                self._put_translation(data, LOCALE, 'Foo', 'Bar')

                # Verify that the cache has been purged
                cached = models.MemcacheManager.get(
                    announcements.AnnouncementEntity._cache_key(LOCALE))
                self.assertIsNone(cached)

                # And that the changed translations show up on the page.
                actions.login('student@sample.com')
                self._verify_announcements(['Foo'], ['Bar'])

    def test_change_base_announcment_updates_i18n_progress(self):
        LOCALE = 'de'
        with actions.OverriddenConfig(models.CAN_USE_MEMCACHE.name, True):
            with actions.OverriddenEnvironment({
                'course': {
                    'locale': 'en_US',
                },
                'extra_locales': [{'locale': LOCALE,
                                   'availability': 'true'}]
                }):

                key = self._add_announcement()
                data = {
                    'key': key,
                    'date': utc.to_text(seconds=0),
                    'html': 'Unsafe for operation',
                    'title': 'Attention',
                    'is_draft': False,
                }
                self._put_announcement(data)
                self._put_translation(data, LOCALE, 'Achtung', 'Gefahrlich!')

                # Verify that having saved the translation, we are in progress
                # state DONE.
                resource_key = str(resource.Key(
                    announcements.ResourceHandlerAnnouncement.TYPE,
                    db.Key(encoded=data['key']).id()))
                progress = i18n_dashboard.I18nProgressDAO.load(resource_key)
                self.assertEquals(progress.get_progress(LOCALE),
                                  i18n_dashboard.I18nProgressDTO.DONE)

                # Modify the announcement in the base language.
                data['title'] = 'Informational'
                data['html'] = 'Now safe for operation again'
                self._put_announcement(data)
                self.execute_all_deferred_tasks()

                # Verify that saving the base version of the announcement
                # moves the progress state back.
                progress = i18n_dashboard.I18nProgressDAO.load(resource_key)
                self.assertEquals(progress.get_progress(LOCALE),
                                  i18n_dashboard.I18nProgressDTO.IN_PROGRESS)

    def test_search_index_translated_announcements(self):
        LOCALE = 'de'
        with actions.OverriddenConfig(models.CAN_USE_MEMCACHE.name, True):
            with actions.OverriddenEnvironment({
                'course': {
                    'locale': 'en_US',
                },
                'extra_locales': [{'locale': LOCALE,
                                   'availability': 'true'}]
                }):

                key = self._add_announcement()
                data = {
                    'key': key,
                    'date': utc.to_text(seconds=0),
                    'html': 'Unsafe for operation',
                    'title': 'Attention',
                    'is_draft': False,
                }
                self._put_announcement(data)
                self._put_translation(data, LOCALE, 'Achtung', 'Gefahrlich!')

                response = self.post(
                    self.base + '/dashboard?action=index_course',
                    {'xsrf_token':
                     crypto.XsrfTokenManager.create_xsrf_token('index_course')})
                self.assertEquals(302, response.status_int)
                self.execute_all_deferred_tasks()

                actions.login('student@sample.com')
                actions.register(self, 'John Doe')
                self._set_prefs_locale(LOCALE)

                response = self.get('search?query=Achtung')
                soup = self.parse_html_string_to_soup(response.body)
                snippets = soup.select('.gcb-search-result-snippet')
                self.assertEquals(snippets[0].text.strip(), 'Gefahrlich!...')
