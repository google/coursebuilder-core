# Copyright 2015 Google Inc. All Rights Reserved.
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

"""Integration tests for modules/embed."""

__author__ = [
    'John Cox (johncox@google.com)',
]

import os

import SimpleHTTPServer
import SocketServer
import socket
import threading

from modules.embed import embed
from modules.embed import embed_pageobjects
from modules.student_groups import student_groups_pageobjects
from tests import suite
from tests.integration import integration
from tests.integration import pageobjects


class EmbedModuleTest(integration.TestBase):

    # Ideally we'd fetch this programmatically, but the integration tests can't
    # see app contexts, and we don't want to refactor the DOM to make it
    # accessible.
    SAMPLE_COURSE_TITLE = 'Power Searching with Google'

    def setUp(self):
        super(EmbedModuleTest, self).setUp()
        self.email = 'test@example.com'

    def assert_embed_has_error(self, page, error):
        self.assertIsNotNone(page)
        self.assertTrue(page.has_error(error))

    def assert_is_embed_page(self, page, embedded_course_title):
        self.assertIsNotNone(page)
        page_text = page.get_text()
        self.assertIn('Greetings, %s.' % self.email, page_text)
        self.assertIn(embedded_course_title, page_text)

    def assert_is_sign_in_page(self, page):
        self.assertIsNotNone(page)
        self.assertIn('start', page.get_text().lower())

    def get_demo_child_url(self, name):
        # Treat as module-protected. pylint: disable=protected-access
        return (
            integration.TestBase.INTEGRATION_SERVER_BASE_URL +
            embed._DEMO_CHILD_URL + '?slug=' + name)

    def get_demo_url(self):
        # Treat as module-protected. pylint: disable=protected-access
        return (
            integration.TestBase.INTEGRATION_SERVER_BASE_URL + embed._DEMO_URL)

    def get_global_errors_url(self):
        # Treat as module-protected. pylint: disable=protected-access
        return (
            integration.TestBase.INTEGRATION_SERVER_BASE_URL +
            embed._GLOBAL_ERRORS_DEMO_URL)

    def get_local_errors_url(self):
        # Treat as module-protected. pylint: disable=protected-access
        return (
            integration.TestBase.INTEGRATION_SERVER_BASE_URL +
            embed._LOCAL_ERRORS_DEMO_URL)

    def make_course_enrollable(self, name):
        self.load_dashboard(
            name
        ).click_leftnav_item_by_link_text(
            'publish', 'Availability',
            student_groups_pageobjects.CourseAvailabilityPage
        ).set_course_availability('Registration Required'
        ).set_whitelisted_students(
            [self.email]
        ).click_save()

    def set_child_courses_and_make_course_available(
            self, parent_name, child_name):
        self.load_dashboard(parent_name
        ).click_leftnav_item_by_link_text(
            'publish', 'Availability',
            student_groups_pageobjects.CourseAvailabilityPage
        ).set_course_availability('Registration Required'
        ).click_save()

        self.load_dashboard(parent_name
        ).click_advanced_settings(
        ).click_advanced_edit(
        ).set_child_courses(
            [child_name]
        )

    def test_embed_global_errors(self):
        self.load_sample_course()
        pageobjects.RootPage(self).load(
            integration.TestBase.INTEGRATION_SERVER_BASE_URL).click_logout()

        global_error_page = embed_pageobjects.DemoPage(self).load(
            self.get_global_errors_url())

        # Because both widgets have configuration errors, the embeds are both in
        # state error and no sign-in widget is shown.
        cb_embeds = global_error_page.get_cb_embed_elements()

        self.assertEquals(2, len(cb_embeds))

        first_error_page = global_error_page.load_embed(
            cb_embeds[0], wait_for=embed_pageobjects.StateError)
        global_error_message = (
            'Embed src '
            '"http://other:8081/sample/modules/embed/v1/resource/example/1" '
            'does not match origin "http://localhost:8081"')

        self.assert_embed_has_error(first_error_page, global_error_message)

        second_error_page = global_error_page.load_embed(
            cb_embeds[1], wait_for=embed_pageobjects.StateError)
        global_error_message = (
            'Embed src '
            '"http://localhost:8082/sample/modules/embed/v1/resource/example/'
            '2" does not match origin "http://localhost:8081"')
        local_error_message = (
            'Embed src '
            '"http://localhost:8082/sample/modules/embed/v1/resource/example/'
            '2" does not match first cb-embed src found, which is from the '
            'deployment at "http://other:8081/sample/modules/embed/v1". '
            'All cb-embeds in a single page must be from the same Course '
            'Builder deployment.')

        self.assert_embed_has_error(second_error_page, global_error_message)
        self.assert_embed_has_error(second_error_page, local_error_message)

    def test_embed_local_errors(self):
        self.load_sample_course()
        pageobjects.RootPage(self).load(
            integration.TestBase.INTEGRATION_SERVER_BASE_URL).click_logout()

        local_error_page = embed_pageobjects.DemoPage(self).load(
            self.get_local_errors_url())

        # Before signing in, the first embed shows the sign-in widget, and the
        # second shows both a global and a local error.
        cb_embeds = local_error_page.get_cb_embed_elements()

        self.assertEquals(2, len(cb_embeds))
        self.assert_is_sign_in_page(
            local_error_page.load_embed(
                cb_embeds[0], wait_for=embed_pageobjects.StateSignIn))

        second_embed_page = local_error_page.load_embed(
            cb_embeds[1], wait_for=embed_pageobjects.StateError)
        global_error_message = (
            'Embed src '
            '"http://localhost:8082/sample/modules/embed/v1/resource/example/'
            '2" does not match origin "http://localhost:8081"')
        local_error_message = (
            'Embed src '
            '"http://localhost:8082/sample/modules/embed/v1/resource/example/'
            '2" does not match first cb-embed src found, which is from the '
            'deployment at "http://localhost:8081/sample/modules/embed/v1". '
            'All cb-embeds in a single page must be from the same Course '
            'Builder deployment.')

        self.assert_embed_has_error(second_embed_page, global_error_message)
        self.assert_embed_has_error(second_embed_page, local_error_message)

        # After signing in, the first embed shows content and the second embed
        # shows both a global and a local error.
        local_error_page.login(self.email)

        cb_embeds = local_error_page.get_cb_embed_elements()

        self.assertEquals(2, len(cb_embeds))

        first_embed_page = local_error_page.load_embed(cb_embeds[0])
        second_embed_page = local_error_page.load_embed(
            cb_embeds[1], wait_for=embed_pageobjects.StateError)

        self.assert_is_embed_page(first_embed_page, self.SAMPLE_COURSE_TITLE)
        self.assert_embed_has_error(second_embed_page, global_error_message)
        self.assert_embed_has_error(second_embed_page, local_error_message)

    def test_embed_render_lifecycle_for_child_course(self):
        child_name, child_title = self.create_new_course()
        self.make_course_enrollable(child_name)
        parent_name = self.create_new_course(login=False)[0]
        self.set_child_courses_and_make_course_available(
            parent_name, child_name)
        pageobjects.RootPage(self).load(
            integration.TestBase.INTEGRATION_SERVER_BASE_URL).click_logout()
        demo_page = embed_pageobjects.DemoPage(self).load(
            self.get_demo_child_url(parent_name))
        embeds = demo_page.get_cb_embed_elements()

        self.assertTrue(len(embeds) == 1)

        for cb_embed in embeds:
            page = demo_page.load_embed(
                cb_embed, wait_for=embed_pageobjects.StateSignIn)
            self.assert_is_sign_in_page(page)

        demo_page.login(self.email)

        # Force refetch of embeds because login state changed.
        for cb_embed in demo_page.get_cb_embed_elements():
            page = demo_page.load_embed(cb_embed)
            self.assert_is_embed_page(page, child_title)

    def test_embed_render_lifecycle_for_single_course(self):
        dashboard_page = self.load_sample_course()
        pageobjects.RootPage(self).load(
            integration.TestBase.INTEGRATION_SERVER_BASE_URL).click_logout()
        demo_page = embed_pageobjects.DemoPage(self).load(
            self.get_demo_url())
        embeds = demo_page.get_cb_embed_elements()

        self.assertTrue(len(embeds) == 3)

        for cb_embed in embeds:
            page = demo_page.load_embed(
                cb_embed, wait_for=embed_pageobjects.StateSignIn)
            self.assert_is_sign_in_page(page)

        demo_page.login(self.email)

        # Force refetch of embeds because login state changed.
        for cb_embed in demo_page.get_cb_embed_elements():
            page = demo_page.load_embed(cb_embed)
            self.assert_is_embed_page(page, self.SAMPLE_COURSE_TITLE)


class EnsureSessionTest(integration.TestBase):
    PORT = 3123

    def setUp(self):
        self._original_directory = os.getcwd()
        os.chdir(os.environ['COURSEBUILDER_HOME'])
        super(EnsureSessionTest, self).setUp()

        class TestServer(SocketServer.TCPServer):
            # Don't want to wait for TIME_WAIT for shutdown
            allow_reuse_address = True

        try:
            self._server = TestServer(
                ("", self.PORT), SimpleHTTPServer.SimpleHTTPRequestHandler)
        except socket.error, ex:
            print """
                ==========================================================
                Failed to bind to port %d.
                This may mean you have another server running on that
                port, or you may have a hung test process.

                Kill running server from command line via:
                lsof -i tcp:%d -Fp | tr -d p | xargs kill -9
                ==========================================================
            """ % (self.PORT, self.PORT)
            raise ex

        server_thread = threading.Thread(target=self._server.serve_forever)
        server_thread.start()

    def tearDown(self):
        self.driver.close()
        self._server.shutdown()
        self._server.server_close()
        os.chdir(self._original_directory)
        super(EnsureSessionTest, self).tearDown()

    def test_ensure_session_with_button(self):
        example_page = embed_pageobjects.EnsureSessionExamplePage(self).load(
            'http://localhost:%s' % self.PORT,
            suite.TestBase.INTEGRATION_SERVER_BASE_URL,
            redirect=False
        ).assert_start_button_is_visible(
        ).click_start_button(
        ).login(
            'user@example.com'
        ).assert_start_button_is_not_visible()

    def test_ensure_session_with_auto_redirect(self):
        example_page = embed_pageobjects.EnsureSessionExamplePage(self).load(
            'http://localhost:%s' % self.PORT,
            suite.TestBase.INTEGRATION_SERVER_BASE_URL,
            redirect=True
        ).login(
            'user@example.com'
        ).assert_start_button_is_not_visible()
