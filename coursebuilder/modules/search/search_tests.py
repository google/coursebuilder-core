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

import logging
import re
import urllib

from common import utils as common_utils
from controllers import sites
from models import courses
from models import resources_display
from models import models
from models import transforms
from modules.announcements import announcements
from modules.i18n_dashboard import i18n_dashboard
from modules.search import search
from modules.search import search_unit_tests
from tests.functional import actions

from google.appengine.api import namespace_manager


class SearchTest(search_unit_tests.SearchTestBase):
    """Tests the search module."""

    @classmethod
    def get_xsrf_token(cls, body, form_name):
        match = re.search(form_name + r'.+[\n\r].+value="([^"]+)"', body)
        assert match
        return match.group(1)

    def index_test_course(self):
        email = 'admin@google.com'
        actions.login(email, is_admin=True)
        response = self.get('/test/dashboard?action=settings_search')
        index_token = self.get_xsrf_token(response.body, 'gcb-index-course')
        response = self.post('/test/dashboard?action=index_course',
                             {'xsrf_token': index_token})
        self.execute_all_deferred_tasks()

    def setUp(self):
        super(SearchTest, self).setUp()
        assert search.custom_module.enabled

        self.logged_error = ''
        def error_report(string, *args, **unused_kwargs):
            self.logged_error = string % args
        self.error_report = error_report

    def test_module_enabled(self):
        email = 'admin@google.com'
        actions.login(email, is_admin=True)

        response = self.get('course')
        self.assertIn('gcb-search-box', response.body)

        response = self.get('/search?query=lorem')
        self.assertEqual(response.status_code, 200)

        response = self.get('dashboard?action=settings_search')
        self.assertIn('Google &gt; Dashboard &gt; Search', response.body)
        self.assertIn('Index Course', response.body)

    def test_indexing_button(self):
        email = 'admin@google.com'
        actions.login(email, is_admin=True)

        response = self.get('dashboard?action=settings_search')

        index_token = self.get_xsrf_token(response.body, 'gcb-index-course')

        response = self.post('dashboard?action=index_course',
                             {'xsrf_token': index_token})
        self.assertEqual(response.status_int, 302)

        response = self.post('dashboard?action=index_course', {},
                             expect_errors=True)
        assert response.status_int == 403

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
        sites.setup_courses('course:/test::ns_test, course:/:/')
        course = courses.Course(None,
                                app_context=sites.get_all_courses()[0])
        unit = course.add_unit()
        unit.availability = courses.AVAILABILITY_AVAILABLE
        lesson_a = course.add_lesson(unit)
        lesson_a.notes = search_unit_tests.UNICODE_PAGE_URL
        lesson_a.availability = courses.AVAILABILITY_AVAILABLE
        course.update_unit(unit)
        course.save()

        self.index_test_course()

        self.swap(logging, 'error', self.error_report)
        response = self.get('/test/search?query=paradox')
        self.assertEqual('', self.logged_error)
        self.assertNotIn('unavailable', response.body)
        self.assertIn('gcb-search-result', response.body)

    def test_external_links(self):
        sites.setup_courses('course:/test::ns_test, course:/:/')
        course = courses.Course(None, app_context=sites.get_all_courses()[0])
        unit = course.add_unit()
        unit.availability = courses.AVAILABILITY_AVAILABLE
        lesson_a = course.add_lesson(unit)
        lesson_a.notes = search_unit_tests.VALID_PAGE_URL
        objectives_link = 'http://objectiveslink.null/'
        lesson_a.objectives = '<a href="%s"></a><a href="%s"></a>' % (
            search_unit_tests.LINKED_PAGE_URL, objectives_link)
        lesson_a.availability = courses.AVAILABILITY_AVAILABLE
        course.update_unit(unit)
        course.save()

        self.index_test_course()

        response = self.get('/test/search?query=What%20hath%20God%20wrought')
        self.assertIn('gcb-search-result', response.body)

        response = self.get('/test/search?query=Cogito')
        self.assertIn('gcb-search-result', response.body)
        self.assertIn(search_unit_tests.VALID_PAGE_URL, response.body)
        self.assertIn(objectives_link, response.body)
        self.assertNotIn(search_unit_tests.PDF_URL, response.body)

        # If this test fails, indexing will crawl the entire web
        response = self.get('/test/search?query=ABORT')
        self.assertNotIn('gcb-search-result', response.body)
        self.assertNotIn(search_unit_tests.SECOND_LINK_PAGE_URL, response.body)

    def test_youtube(self):
        sites.setup_courses('course:/test::ns_test, course:/:/')
        default_namespace = namespace_manager.get_namespace()
        try:
            namespace_manager.set_namespace('ns_test')

            course = courses.Course(None,
                                    app_context=sites.get_all_courses()[0])
            unit = course.add_unit()
            unit.availability = courses.AVAILABILITY_AVAILABLE
            lesson_a = course.add_lesson(unit)
            lesson_a.video = 'portal'
            lesson_a.availability = courses.AVAILABILITY_AVAILABLE
            lesson_b = course.add_lesson(unit)
            lesson_b.objectives = '<gcb-youtube videoid="glados">'
            lesson_b.availability = courses.AVAILABILITY_AVAILABLE
            course.update_unit(unit)
            course.save()

            entity = announcements.AnnouncementEntity.make(
                'New Announcement', '<gcb-youtube videoid="aperature">', False)
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
            self.assertIn('http://thumbnail.null', response.body)

            # Test to make sure empty notes field doesn't cause a urlfetch
            response = self.get('/test/search?query=cogito')
            self.assertNotIn('gcb-search-result', response.body)
        finally:
            namespace_manager.set_namespace(default_namespace)

    def _add_announcement(self, form_settings):
        response = actions.view_announcements(self)
        add_form = response.forms['gcb-add-announcement']
        response = self.submit(add_form).follow()
        match = re.search(r'\'([^\']+rest/announcements/item\?key=([^\']+))',
                          response.body)
        url = match.group(1)
        key = match.group(2)
        response = self.get(url)
        json_dict = transforms.loads(response.body)
        payload_dict = transforms.loads(json_dict['payload'])
        payload_dict.update(form_settings)
        request = {}
        request['key'] = key
        request['payload'] = transforms.dumps(payload_dict)
        request['xsrf_token'] = json_dict['xsrf_token']
        response = self.put('rest/announcements/item?%s' % urllib.urlencode(
            {'request': transforms.dumps(request)}), {})

    def test_announcements(self):
        email = 'admin@google.com'
        actions.login(email, is_admin=True)

        self._add_announcement({
            'title': 'My Test Title',
            'date': '2015-02-03 00:00',
            'is_draft': False,
            'html': 'Four score and seven years ago, our founding fathers'
            })
        self._add_announcement({
            'title': 'My Test Title',
            'date': '2015-02-03 00:00',
            'is_draft': True,
            'html': 'Standing beneath this serene sky, overlooking these',
            })

        response = self.get('dashboard?action=settings_search')
        index_token = self.get_xsrf_token(response.body, 'gcb-index-course')
        response = self.post('dashboard?action=index_course',
                             {'xsrf_token': index_token})
        self.execute_all_deferred_tasks()

        # This matches an announcement in the Power Searching course
        response = self.get(
            'search?query=Four%20score%20seven%20years')
        self.assertIn('gcb-search-result', response.body)
        self.assertIn('announcements#', response.body)

        # The draft announcement in Power Searching should not be indexed
        response = self.get('search?query=Standing%20beneath%20serene')
        self.assertNotIn('gcb-search-result', response.body)
        self.assertNotIn('announcements#', response.body)

    def test_private_units_and_lessons(self):
        sites.setup_courses('course:/test::ns_test, course:/:/')
        course = courses.Course(None, app_context=sites.get_all_courses()[0])

        unit1 = course.add_unit()
        lesson11 = course.add_lesson(unit1)
        lesson11.notes = search_unit_tests.VALID_PAGE_URL
        lesson11.objectives = search_unit_tests.VALID_PAGE
        lesson11.video = 'portal'
        unit2 = course.add_unit()
        lesson21 = course.add_lesson(unit2)
        lesson21.notes = search_unit_tests.VALID_PAGE_URL
        lesson21.objectives = search_unit_tests.VALID_PAGE
        lesson21.video = 'portal'

        unit1.availability = courses.AVAILABILITY_AVAILABLE
        lesson11.availability = courses.AVAILABILITY_UNAVAILABLE
        course.update_unit(unit1)

        unit2.availability = courses.AVAILABILITY_UNAVAILABLE
        lesson21.availability = courses.AVAILABILITY_AVAILABLE
        course.update_unit(unit2)

        course.save()
        self.index_test_course()

        response = self.get('/test/search?query=cogito%20ergo%20sum')
        self.assertNotIn('gcb-search-result', response.body)

        response = self.get('/test/search?query=apple')
        self.assertNotIn('gcb-search-result', response.body)
        self.assertNotIn('v=portal', response.body)

    def test_tracked_lessons(self):
        context = actions.simple_add_course('test', 'admin@google.com',
                                            'Test Course')
        course = courses.Course(None, context)
        actions.login('admin@google.com')
        actions.register(self, 'Some Admin', 'test')

        with common_utils.Namespace('ns_test'):
            foo_id = models.LabelDAO.save(models.LabelDTO(
                None, {'title': 'Foo',
                       'descripton': 'foo',
                       'type': models.LabelDTO.LABEL_TYPE_COURSE_TRACK}))
            bar_id = models.LabelDAO.save(models.LabelDTO(
                None, {'title': 'Bar',
                       'descripton': 'bar',
                       'type': models.LabelDTO.LABEL_TYPE_COURSE_TRACK}))

        unit1 = course.add_unit()
        unit1.availability = courses.AVAILABILITY_AVAILABLE
        unit1.labels = str(foo_id)
        lesson11 = course.add_lesson(unit1)
        lesson11.objectives = 'common plugh <gcb-youtube videoid="glados">'
        lesson11.availability = courses.AVAILABILITY_AVAILABLE
        lesson11.notes = search_unit_tests.VALID_PAGE_URL
        lesson11.video = 'portal'
        course.update_unit(unit1)
        unit2 = course.add_unit()
        unit2.availability = courses.AVAILABILITY_AVAILABLE
        unit1.labels = str(bar_id)
        lesson21 = course.add_lesson(unit2)
        lesson21.objectives = 'common plover'
        lesson21.availability = courses.AVAILABILITY_AVAILABLE
        course.update_unit(unit2)
        course.save()
        self.index_test_course()

        # Registered, un-tracked student sees all.
        response = self.get('/test/search?query=common')
        self.assertIn('common', response.body)
        self.assertIn('plugh', response.body)
        self.assertIn('plover', response.body)
        response = self.get('/test/search?query=link')  # Do see followed links
        self.assertIn('Partial', response.body)
        self.assertIn('Absolute', response.body)
        response = self.get('/test/search?query=lemon')  # Do see video refs
        self.assertIn('v=glados', response.body)

        # Student with tracks sees filtered view.
        with common_utils.Namespace('ns_test'):
            models.Student.set_labels_for_current(str(foo_id))
        response = self.get('/test/search?query=common')
        self.assertIn('common', response.body)
        self.assertNotIn('plugh', response.body)
        self.assertIn('plover', response.body)
        response = self.get('/test/search?query=link')  # Links are filtered
        self.assertNotIn('Partial', response.body)
        self.assertNotIn('Absolute', response.body)
        response = self.get('/test/search?query=lemon')  # Don't see video refs
        self.assertNotIn('v=glados', response.body)

    def test_localized_search(self):
        def _text(elt):
            return ''.join(elt.itertext())

        dogs_page = """
          <html>
            <body>
              A page about dogs.
            </body>
          </html>"""
        dogs_link = 'http://dogs.null/'
        self.pages[dogs_link + '$'] = (dogs_page, 'text/html')

        dogs_page_fr = """
          <html>
            <body>
              A page about French dogs.
            </body>
          </html>"""
        dogs_link_fr = 'http://dogs_fr.null/'
        self.pages[dogs_link_fr + '$'] = (dogs_page_fr, 'text/html')

        self.base = '/test'
        context = actions.simple_add_course(
            'test', 'admin@google.com', 'Test Course')
        course = courses.Course(None, context)
        actions.login('admin@google.com')
        actions.register(self, 'Some Admin')

        unit = course.add_unit()
        unit.availability = courses.AVAILABILITY_AVAILABLE
        lesson = course.add_lesson(unit)
        lesson.objectives = 'A lesson about <a href="%s">dogs</a>' % dogs_link
        lesson.availability = courses.AVAILABILITY_AVAILABLE
        course.save()

        lesson_bundle = {
            'objectives': {
                'type': 'html',
                'source_value': (
                    'A lesson about <a href="%s">dogs</a>' % dogs_link),
                'data': [{
                    'source_value': (
                        'A lesson about <a#1 href="%s">dogs</a#1>' % dogs_link),
                    'target_value': (
                        'A lesson about French <a#1 href="%s">'
                        'dogs</a#1>' % dogs_link_fr)}]
            }
        }
        lesson_key_fr = i18n_dashboard.ResourceBundleKey(
            resources_display.ResourceLesson.TYPE, lesson.lesson_id, 'fr')
        with common_utils.Namespace('ns_test'):
            i18n_dashboard.ResourceBundleDAO.save(
                i18n_dashboard.ResourceBundleDTO(
                    str(lesson_key_fr), lesson_bundle))

        extra_locales = [{'locale': 'fr', 'availability': 'available'}]
        with actions.OverriddenEnvironment({'extra_locales': extra_locales}):

            self.index_test_course()

            dom = self.parse_html_string(self.get('search?query=dogs').body)
            snippets = dom.findall('.//div[@class="gcb-search-result-snippet"]')
            self.assertEquals(2, len(snippets))  # Expect no French hits
            self.assertIn('page about dogs', _text(snippets[0]))
            self.assertIn('lesson about dogs', _text(snippets[1]))

            # Switch locale to 'fr'
            with common_utils.Namespace('ns_test'):
                prefs = models.StudentPreferencesDAO.load_or_default()
                prefs.locale = 'fr'
                models.StudentPreferencesDAO.save(prefs)

            dom = self.parse_html_string(self.get('search?query=dogs').body)
            snippets = dom.findall('.//div[@class="gcb-search-result-snippet"]')
            self.assertEquals(2, len(snippets))  # Expect no Engish hits
            self.assertIn('page about French dogs', _text(snippets[0]))
            self.assertIn('lesson about French dogs', _text(snippets[1]))

    def test_cron(self):
        app_context = sites.get_all_courses()[0]
        app_context.set_current_locale('en_US')
        course = courses.Course(None, app_context=app_context)
        actions.login('admin@google.com', is_admin=True)

        # Call cron URL without indexing enabled; expect 0 results found.
        self.get(search.CronIndexCourse.URL)
        self.execute_all_deferred_tasks()
        response = search.fetch(course, 'color')
        self.assertEquals(0, response['total_found'])

        # Call cron URL with indexing enabled; expect results.
        with actions.OverriddenEnvironment(
            {'course': {search.AUTO_INDEX_SETTING: 'True'}}):
            self.get(search.CronIndexCourse.URL)
        self.execute_all_deferred_tasks()
        response = search.fetch(course, 'color')
        self.assertEquals(1, response['total_found'])
