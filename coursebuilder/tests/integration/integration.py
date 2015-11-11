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

"""Core functionality for integration tests."""

__author__ = [
    'John Cox (johncox@google.com)',
    'John Orr (jorr@google.com)',
]

import random
import time

from tests import suite
from tests.integration import pageobjects

from selenium import webdriver
from selenium.common import exceptions
from selenium.webdriver.chrome import options


BROWSER_WIDTH = 1600
BROWSER_HEIGHT = 1000


class TestBase(suite.TestBase):
    """Base class for all integration tests."""

    LOGIN = 'test@example.com'

    def setUp(self):
        super(TestBase, self).setUp()
        chrome_options = options.Options()
        chrome_options.add_argument('--disable-extensions')

        # Sadly, the max wait for the driver to become ready is hard-coded at
        # 30 seconds.  However, that seems like it'd be enough for our
        # purposes, so retrying the whole shebang seems like a better bet for
        # getting rid of the flakiness due to occasional failure to connect to
        # the Chrome driver.
        self.driver = None
        tries = 10
        while not self.driver:
            tries -= 1
            try:
                self.driver = webdriver.Chrome(chrome_options=chrome_options)
            except exceptions.WebDriverException, ex:
                print ex
                if tries:
                    print 'Retrying Chrome connection up to %d more times' % (
                        tries)
                else:
                    raise ex

        # Set a large enough window size independent of screen size so that all
        # click actions can be performed correctly.
        self.driver.set_window_size(BROWSER_WIDTH, BROWSER_HEIGHT)

    def tearDown(self):
        time.sleep(1)  # avoid broken sockets on the server
        self.driver.quit()
        super(TestBase, self).tearDown()

    def load_root_page(self):
        ret = pageobjects.RootPage(self).load(
            suite.TestBase.INTEGRATION_SERVER_BASE_URL)
        tries = 10
        while tries and 'This webpage is not avail' in self.driver.page_source:
            tries -= 1
            time.sleep(1)
            ret = pageobjects.RootPage(self).load(
                suite.TestBase.INTEGRATION_SERVER_BASE_URL)
        return ret

    def load_dashboard(self, name):
        return pageobjects.DashboardPage(self).load(
            suite.TestBase.INTEGRATION_SERVER_BASE_URL, name)

    def load_appengine_admin(self, course_name):
        return pageobjects.AppengineAdminPage(
            self, suite.TestBase.ADMIN_SERVER_BASE_URL, course_name)

    def load_sample_course(self):
        # Be careful using this method. The sample class is a singleton and
        # tests which use it will not be isolated. This can lead to a number of
        # subtle collisions between tests that do not manifest when the tests
        # are run individually, but *do* manifest when run en bloc. Prefer
        # create_new_course() whenever possible.
        name = 'sample'
        title = 'Power Searching with Google'

        page = self.load_root_page(
        ).click_login(
        ).login(
            self.LOGIN, admin=True
        ).click_dashboard(
        ).click_admin()

        if not page.has_course(name):
            page.click_add_sample_course(
            ).set_fields(
                name=name, title=title, email=self.LOGIN
            ).click_ok()

        return self.load_dashboard(name)

    def get_slug_for_current_course(self):
        """Returns the slug for the current course based on the current URL."""
        return '/' + self.driver.current_url.split('/')[3]

    def get_uid(self):
        """Generate a unique id string."""
        possible_chars = 'abcdefghijklmnopqrstuvwxyz1234567890'
        return ''.join(random.choice(possible_chars) for _ in xrange(10))

    def create_new_course(self, login=True):
        """Create a new course with a unique name, using the admin tools."""
        uid = self.get_uid()
        name = 'ns_%s' % uid
        title = 'Test Course (%s)' % uid

        page = self.load_root_page()

        if login:
            page.click_login(
            ).login(
                self.LOGIN, admin=True
            )

        page.click_dashboard(
        ).click_admin(
        ).click_add_course(
        ).set_fields(
            name=name, title=title, email='a@bb.com'
        ).click_ok()

        return (name, title)

    def set_admin_setting(self, setting_name, state):
        """Configure a property on Admin setting page."""

        self.load_root_page(
        ).click_dashboard(
        ).click_admin(
        ).click_site_settings(
        ).click_override(
            setting_name
        ).set_value(
            state
        ).set_status(
            'Active'
        ).click_save(
        ).click_close()
