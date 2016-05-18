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

import collections
import random
import time

from tests import suite
from tests.integration import pageobjects

from selenium import webdriver
from selenium.common import exceptions
from selenium.webdriver.chrome import options

from models import courses


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

    def load_root_page(self, suffix=pageobjects.PageObject.BASE_URL_SUFFIX):
        base_url = suite.TestBase.INTEGRATION_SERVER_BASE_URL
        ret = pageobjects.RootPage(self).load(base_url, suffix=suffix)
        tries = 10
        while tries and 'This webpage is not avail' in self.driver.page_source:
            tries -= 1
            time.sleep(1)
            ret = pageobjects.RootPage(self).load(base_url, suffix=suffix)
        return ret

    def load_course(self, name):
        return self.load_root_page(suffix='/' + name)

    def load_dashboard(self, name):
        return pageobjects.DashboardPage(self).load(
            suite.TestBase.INTEGRATION_SERVER_BASE_URL, name)

    def load_courses_list(self, cls=pageobjects.CoursesListPage):
        return cls(self).load(suite.TestBase.INTEGRATION_SERVER_BASE_URL)

    def load_appengine_admin(self, course_name):
        return pageobjects.AppengineAdminPage(
            self, suite.TestBase.ADMIN_SERVER_BASE_URL, course_name)

    def login(self, email, admin=True, logout_first=False):
        root_page = self.load_root_page()
        if logout_first:
            root_page.click_logout()
        return root_page.click_login().login(email, admin=admin)

    def logout(self):
        return self.load_root_page().click_logout()

    def load_sample_course(self):
        # Be careful using this method. The sample class is a singleton and
        # tests which use it will not be isolated. This can lead to a number of
        # subtle collisions between tests that do not manifest when the tests
        # are run individually, but *do* manifest when run en bloc. Prefer
        # create_new_course() whenever possible.
        name = 'sample'
        title = 'Power Searching with Google'

        page = self.login(
            self.LOGIN, admin=True
        ).click_dashboard(
        ).click_courses()

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
        self.create_course(title, name, login=login)
        return (name, title)

    def create_course(self, title, name, login=True):
        """Create a new course from title and name, using the admin tools."""
        if login:
            self.login(self.LOGIN, admin=True)

        self.load_courses_list(
        ).click_add_course(
        ).set_fields(
            name=name, title=title, email='admin@example.com'
        ).click_ok()

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

    def set_course_availability(self, course_name, avail):
        return self.load_dashboard(
            course_name
        ).click_availability(
        ).set_course_availability(
            avail
        )

    # Courses in one of the following Publish > Availability visibility
    # states will not display the [Register] button.
    AVAILABILITY_TITLES_WITHOUT_REGISTER = [
        courses.COURSE_AVAILABILITY_POLICIES[
            courses.COURSE_AVAILABILITY_PRIVATE]['title'],
        courses.COURSE_AVAILABILITY_POLICIES[
            courses.COURSE_AVAILABILITY_PUBLIC]['title'],
    ]

    # Courses in one of the following Publish > Availability visibility
    # states display the [Register] button.
    AVAILABILITY_TITLES_WITH_REGISTER = [
        courses.COURSE_AVAILABILITY_POLICIES[
            courses.COURSE_AVAILABILITY_REGISTRATION_OPTIONAL]['title'],
        courses.COURSE_AVAILABILITY_POLICIES[
            courses.COURSE_AVAILABILITY_REGISTRATION_REQUIRED]['title'],
    ]

    def init_availability_and_whitelist(self, course_name, avail, emails):
        if emails is None:
            emails = []
        else:
            # "Flatten" any generators into an actual list.
            emails = [e for e in emails]

        avail_page = self.set_course_availability(course_name, avail)

        if avail not in self.AVAILABILITY_TITLES_WITHOUT_REGISTER:
            avail_page.set_whitelisted_students(emails)
        else:
            # Apparently, the [Register] button no longer appears for
            # courses with an availability of 'Public - No Registration' or
            # 'Private', so expect the caller to *not* provide any email
            # email addresses to be whitelisted.
            self.assertEqual(0, len(emails))

        avail_page.click_save()

    Person = collections.namedtuple('Person', 'email name admin')

    # To obtain some randomly initialized Person tuples regardless of course
    # availability, supply this constant for the `avail` parameter.
    IGNORE_AVAILABILITY = AVAILABILITY_TITLES_WITH_REGISTER[0]

    def some_persons(self, qty, admins=False, pupils=False,
                     avail=IGNORE_AVAILABILITY):
        if not self._check_availability_vs_person_count(avail, qty):
            return

        if admins:
            if pupils:
                who = ['Admin', 'Pupil']  # Both wanted so, 50-50 chance.
            else:
                who = ['Admin']  # Just admins, no pupils at all.
        elif pupils:
            who = ['Pupil']  # Just pupils, no admins at all.
        else:
            # No preference, so produce a mix with more pupils than admins.
            who = ['Admin', 'Pupil', 'Pupil', 'Pupil']

        for count in xrange(1, qty + 1):
            name = random.choice(who)
            person_id = random.randint(1, (2 << 32) - 1)
            email = '{:08X}-{}@example.com'.format(person_id, name.lower())
            full_name = '{:08X} {}'.format(person_id, name)
            yield self.Person(email, full_name, name == 'Admin')

    def one_person(self, admin=True, pupil=True):
        one = [p for p in
               self.some_persons(1, admins=admin, pupils=pupil)]
        self.assertEquals(1, len(one))
        return one[0]

    def one_admin(self):
        return self.one_person(admin=True, pupil=False)

    def one_pupil(self):
        return self.one_person(admin=False, pupil=True)

    def enroll_persons(self, course_name, persons,
                       avail=IGNORE_AVAILABILITY):
        """Enrolls list of Persons (pupils, admins) in the course_name course.

        Expects someone to already be logged in when called. Last Person to be
        enrolled will remain logged in at end of call.
        """
        if not self._check_availability_vs_person_count(avail, len(persons)):
            return

        for p in persons:
            self.login(p.email, admin=p.admin, logout_first=True)
            self.load_course(
                course_name
            ).click_register(
            ).enroll(
                p.name
            )

    def _check_availability_vs_person_count(self, avail, count):
        if avail in self.AVAILABILITY_TITLES_WITHOUT_REGISTER:
            self.assertEquals(0, count)
            # No [Register] button on Public or Private course pages, so bail.
            return False  # Do *not* whitelist or attempt to enroll.
        # else:
        #   "Registration Required" or "Registration Optional", so keep going.
        return True
