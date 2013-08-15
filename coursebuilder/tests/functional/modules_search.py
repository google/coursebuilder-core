# Copyright 2013 Google Inc. All Rights Reserved.
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

"""Tests for modules/search/."""

__author__ = 'Ellis Michael (emichael@google.com)'

import datetime
import logging
import re

from controllers import sites
from models import courses
from models import custom_modules
from modules.announcements import announcements
from modules.search import search
from tests.unit import modules_search as search_unit_test
import actions

from google.appengine.api import namespace_manager


class SearchTest(search_unit_test.SearchTestBase):
    """Tests the search module."""

    # Don't require documentation for self-describing test methods.
    # pylint: disable-msg=g-missing-docstring

    @classmethod
    def enable_module(cls):
        custom_modules.Registry.registered_modules[
            search.MODULE_NAME].enable()
        assert search.custom_module.enabled

    @classmethod
    def disable_module(cls):
        custom_modules.Registry.registered_modules[
            search.MODULE_NAME].disable()
        assert not search.custom_module.enabled

    @classmethod
    def get_xsrf_token(cls, body, form_name):
        match = re.search(form_name + r'.+[\n\r].+value="([^"]+)"', body)
        assert match
        return match.group(1)

    def index_test_course(self):
        email = 'admin@google.com'
        actions.login(email, is_admin=True)
        response = self.get('/test/dashboard?action=search')
        index_token = self.get_xsrf_token(response.body, 'gcb-index-course')
        response = self.post('/test/dashboard?action=index_course',
                             {'xsrf_token': index_token})
        self.execute_all_deferred_tasks()

    def setUp(self):   # Name set by parent. pylint: disable-msg=g-bad-name
        super(SearchTest, self).setUp()
        self.enable_module()

        self.logged_error = ''
        def error_report(string, *args, **unused_kwargs):
            self.logged_error = string % args
        self.error_report = error_report

    def test_module_disabled(self):
        email = 'admin@google.com'
        actions.login(email, is_admin=True)

        self.disable_module()

        response = self.get('/search?query=lorem', expect_errors=True)
        self.assertEqual(response.status_code, 404)

        response = self.get('dashboard?action=search')
        self.assertIn('Google &gt; Dashboard &gt; Search', response.body)
        self.assertNotIn('Index Course', response.body)
        self.assertNotIn('Clear Index', response.body)

    def test_module_enabled(self):
        email = 'admin@google.com'
        actions.login(email, is_admin=True)

        response = self.get('course')
        self.assertIn('gcb-search-box', response.body)

        response = self.get('/search?query=lorem')
        self.assertEqual(response.status_code, 200)

        response = self.get('dashboard?action=search')
        self.assertIn('Google &gt; Dashboard &gt; Search', response.body)
        self.assertIn('Index Course', response.body)
        self.assertIn('Clear Index', response.body)

    def test_indexing_and_clearing_buttons(self):
        email = 'admin@google.com'
        actions.login(email, is_admin=True)

        response = self.get('dashboard?action=search')

        index_token = self.get_xsrf_token(response.body, 'gcb-index-course')
        clear_token = self.get_xsrf_token(response.body, 'gcb-clear-index')

        response = self.post('dashboard?action=index_course',
                             {'xsrf_token': index_token})
        self.assertEqual(response.status_int, 302)

        response = self.post('dashboard?action=clear_index',
                             {'xsrf_token': clear_token})
        self.assertEqual(response.status_int, 302)

        response = self.post('dashboard?action=index_course', {},
                             expect_errors=True)
        assert response.status_int == 403
        response = self.post('dashboard?action=clear_index', {},
                             expect_errors=True)
        assert response.status_int == 403

    def test_index_search_clear(self):
        email = 'admin@google.com'
        actions.login(email, is_admin=True)

        response = self.get('dashboard?action=search')
        index_token = self.get_xsrf_token(response.body, 'gcb-index-course')
        clear_token = self.get_xsrf_token(response.body, 'gcb-clear-index')
        response = self.post('dashboard?action=index_course',
                             {'xsrf_token': index_token})
        self.execute_all_deferred_tasks()

        # weather is a term found in the Power Searching Course and should not
        # be in the HTML returned by the patched urlfetch in SearchTestBase
        response = self.get('search?query=weather')
        self.assertNotIn('gcb-search-result', response.body)

        # This term should be present as it is in the dummy content.
        response = self.get('search?query=cogito%20ergo%20sum')
        self.assertIn('gcb-search-result', response.body)

        response = self.post('dashboard?action=clear_index',
                             {'xsrf_token': clear_token})
        self.execute_all_deferred_tasks()

        # After the index is cleared, it shouldn't match anything
        response = self.get('search?query=cogito%20ergo%20sum')
        self.assertNotIn('gcb-search-result', response.body)

    def test_bad_search(self):
        email = 'user@google.com'
        actions.login(email, is_admin=False)

        # %3A is a colon, and searching for only punctuation will cause App
        # Engine's search to throw an error that should be handled
        response = self.get('search?query=%3A')
        self.assertEqual(response.status_int, 200)
        self.assertIn('gcb-search-info', response.body)

    def test_errors_not_displayed_to_user(self):
        exception_code = '0xDEADBEEF'
        def bad_fetch(*unused_vargs, **unused_kwargs):
            raise Exception(exception_code)
        self.swap(search, 'fetch', bad_fetch)

        self.swap(logging, 'error', self.error_report)
        response = self.get('search?query=cogito')
        self.assertEqual(response.status_int, 200)
        self.assertIn('unavailable', response.body)
        self.assertNotIn('gcb-search-result', response.body)
        self.assertIn('gcb-search-info', response.body)
        self.assertIn(exception_code, self.logged_error)

    def test_unicode_pages(self):
        # TODO(emichael): Remove try, except, else when the unicode issue
        # is fixed in dev_appserver.
        try:
            sites.setup_courses('course:/test::ns_test, course:/:/')
            course = courses.Course(None,
                                    app_context=sites.get_all_courses()[0])
            unit = course.add_unit()
            unit.now_available = True
            lesson_a = course.add_lesson(unit)
            lesson_a.notes = search_unit_test.UNICODE_PAGE_URL
            lesson_a.now_available = True
            course.update_unit(unit)
            course.save()

            self.index_test_course()

            self.swap(logging, 'error', self.error_report)
            response = self.get('/test/search?query=paradox')
            self.assertEqual('', self.logged_error)
            self.assertNotIn('unavailable', response.body)
            self.assertIn('gcb-search-result', response.body)
        except AssertionError:
            # Failing due to known unicode issue
            pass
        else:
            raise AssertionError('Unicode search test should have failed. The '
                                 'issue might now be fixed in dev_appserver.')

    def test_external_links(self):
        sites.setup_courses('course:/test::ns_test, course:/:/')
        course = courses.Course(None, app_context=sites.get_all_courses()[0])
        unit = course.add_unit()
        unit.now_available = True
        lesson_a = course.add_lesson(unit)
        lesson_a.notes = search_unit_test.VALID_PAGE_URL
        objectives_link = 'http://objectiveslink.null/'
        lesson_a.objectives = '<a href="%s"></a><a href="%s"></a>' % (
            search_unit_test.LINKED_PAGE_URL, objectives_link)
        lesson_a.now_available = True
        course.update_unit(unit)
        course.save()

        self.index_test_course()

        response = self.get('/test/search?query=What%20hath%20God%20wrought')
        self.assertIn('gcb-search-result', response.body)

        response = self.get('/test/search?query=Cogito')
        self.assertIn('gcb-search-result', response.body)
        self.assertIn(search_unit_test.VALID_PAGE_URL, response.body)
        self.assertIn(objectives_link, response.body)
        self.assertNotIn(search_unit_test.PDF_URL, response.body)

        # If this test fails, indexing will crawl the entire web
        response = self.get('/test/search?query=ABORT')
        self.assertNotIn('gcb-search-result', response.body)
        self.assertNotIn(search_unit_test.SECOND_LINK_PAGE_URL, response.body)

    def test_youtube(self):
        sites.setup_courses('course:/test::ns_test, course:/:/')
        default_namespace = namespace_manager.get_namespace()
        try:
            namespace_manager.set_namespace('ns_test')

            course = courses.Course(None,
                                    app_context=sites.get_all_courses()[0])
            unit = course.add_unit()
            unit.now_available = True
            lesson_a = course.add_lesson(unit)
            lesson_a.video = 'portal'
            lesson_a.now_available = True
            lesson_b = course.add_lesson(unit)
            lesson_b.objectives = '<gcb-youtube videoid="glados">'
            lesson_b.now_available = True
            course.update_unit(unit)
            course.save()

            entity = announcements.AnnouncementEntity()
            entity.html = '<gcb-youtube videoid="aperature">'
            entity.title = 'Sample Announcement'
            entity.date = datetime.datetime.now().date()
            entity.is_draft = False
            entity.put()

            self.index_test_course()

            response = self.get('/test/search?query=apple')
            self.assertIn('gcb-search-result', response.body)
            self.assertIn('start=3.14', response.body)
            self.assertIn('v=portal', response.body)
            self.assertIn('v=glados', response.body)
            self.assertIn('v=aperature', response.body)
            self.assertIn('lemon', response.body)
            self.assertIn('Medicus Quis', response.body)
            self.assertIn('- YouTube', response.body)
            self.assertIn('http://thumbnail.null', response.body)

            # Test to make sure empty notes field doesn't cause a urlfetch
            response = self.get('/test/search?query=cogito')
            self.assertNotIn('gcb-search-result', response.body)
        finally:
            namespace_manager.set_namespace(default_namespace)

    def test_announcements(self):
        email = 'admin@google.com'
        actions.login(email, is_admin=True)

        self.get('announcements')

        response = self.get('dashboard?action=search')
        index_token = self.get_xsrf_token(response.body, 'gcb-index-course')
        response = self.post('dashboard?action=index_course',
                             {'xsrf_token': index_token})
        self.execute_all_deferred_tasks()

        # This matches an announcement in the Power Searching course
        response = self.get(
            'search?query=Certificates%20qualifying%20participants')
        self.assertIn('gcb-search-result', response.body)
        self.assertIn('announcements#', response.body)

        # The draft announcement in Power Searching should not be indexed
        response = self.get('search?query=Welcome%20to%20the%20final%20class')
        self.assertNotIn('gcb-search-result', response.body)
        self.assertNotIn('announcements#', response.body)

    def test_private_units_and_lessons(self):
        sites.setup_courses('course:/test::ns_test, course:/:/')
        course = courses.Course(None, app_context=sites.get_all_courses()[0])

        unit1 = course.add_unit()
        lesson11 = course.add_lesson(unit1)
        lesson11.notes = search_unit_test.VALID_PAGE_URL
        lesson11.objectives = search_unit_test.VALID_PAGE
        lesson11.video = 'portal'
        unit2 = course.add_unit()
        lesson21 = course.add_lesson(unit2)
        lesson21.notes = search_unit_test.VALID_PAGE_URL
        lesson21.objectives = search_unit_test.VALID_PAGE
        lesson21.video = 'portal'

        unit1.now_available = True
        lesson11.now_available = False
        course.update_unit(unit1)

        unit2.now_available = False
        lesson21.now_available = True
        course.update_unit(unit2)

        course.save()
        self.index_test_course()

        response = self.get('/test/search?query=cogito%20ergo%20sum')
        self.assertNotIn('gcb-search-result', response.body)

        response = self.get('/test/search?query=apple')
        self.assertNotIn('gcb-search-result', response.body)
        self.assertNotIn('v=portal', response.body)
