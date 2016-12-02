# coding: utf-8
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
import copy
import datetime
import logging
import os
import random
import time
import traceback

from common import utils as common_utils
from tests import suite
from tests.integration import pageobjects

from selenium import webdriver
from selenium.common import exceptions
from selenium.webdriver.common import desired_capabilities
from selenium.webdriver.chrome import options
from selenium.webdriver.remote import webelement
from selenium.webdriver.support import wait

from models import courses


BROWSER_WIDTH = 1600
BROWSER_HEIGHT = 1000


class TestBase(suite.TestBase):
    """Base class for all integration tests."""

    LOGIN = 'test@example.com'
    TEST_BUNDLE_ONE = 'tests.integration.test_classes.IntegrationTestBundle1.'

    def setUp(self):
        super(TestBase, self).setUp()
        chrome_options = options.Options()
        chrome_options.add_argument('--disable-extensions')
        capabilities = desired_capabilities.DesiredCapabilities.CHROME
        capabilities['loggingPrefs'] = {'browser':'ALL'}

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
                self.driver = webdriver.Chrome(
                    chrome_options=chrome_options,
                    desired_capabilities=capabilities)
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

        # Add names of flaky tests below to collect extra information to help
        # with debugging flaky tests.  Configure the WHAT_... items collected
        # for various WHEN_... events.  The list of items collected can be
        # modified to collect only enough data to reproduce a timing-sensitive
        # flake while (hopefully) not adding enough latency to prevent the
        # flake.
        #
        # If no WHAT_... items are specified for a WHEN_... event, the event
        # is not hooked for data collection and thus adds no delay or
        # alternate code execution paths.  As checked in, no items are
        # collected.
        #
        # Collected facts are stored in ./snapshots/<timestamp>_<test-name>.
        # Each event's data is stored in a sub-directory named for the
        # hour/minute/second/fraction for that step.  The WHAT_...  contents
        # are stored in appropriately-named files within that directory.
        #
        self._snapshot = None
        if self.id() in [
            # self.TEST_BUNDLE_ONE + 'test_admin_can_add_announcement',
        ]:
            self._snapshot = Snapshot(self.driver, self.id(), collect_what={
                Snapshot.WHEN_GET: [
                    Snapshot.WHAT_PAGE_SOURCE,
                    Snapshot.WHAT_URL,
                ],
                Snapshot.WHEN_CLICK: [
                    Snapshot.WHAT_PAGE_SOURCE,
                    Snapshot.WHAT_URL,
                ],
                Snapshot.WHEN_WAIT_TIMEOUT: Snapshot.WHAT_ALL,
            })

        # Records courses the test creates so they can be removed in teardown.
        self.course_namespaces = []

    def tearDown(self):
        if self.course_namespaces:
            self.force_admin_login(self.LOGIN)
            for namespace in copy.copy(self.course_namespaces):
                self.delete_course(namespace, login=False)
        time.sleep(1)  # avoid broken sockets on the server
        self.driver.quit()
        if self._snapshot:
            self._snapshot.tearDown()
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

    def load_appengine_cron(self):
        return pageobjects.AppengineCronPage(self).load(
            suite.TestBase.ADMIN_SERVER_BASE_URL, suffix='/cron')

    COURSE_LIST_LOGIN_URL = '/_ah/login?continue=/modules/admin'

    def _course_list_login_page(self):
        return pageobjects.LoginPage(
            self, continue_page=pageobjects.CoursesListPage).load(
                suite.TestBase.INTEGRATION_SERVER_BASE_URL,
                suffix=self.COURSE_LIST_LOGIN_URL)

    def _dismiss_alerts(self, action, tries=3):
        """Some pages have more than one alert when you try to leave."""
        for _ in xrange(tries):
            try:
                return action()
            except exceptions.UnexpectedAlertPresentException:
                self.driver.switch_to_alert().accept()
        raise Exception('Too many alerts.')

    def _try_to_navigate(self, action, expected_url, tries=3):
        """Sometimes webdriver decides not to navigate, so we try again."""
        failure_message = 'Failed to navigate to {}.'.format(expected_url)
        for _ in xrange(tries):
            result = self._dismiss_alerts(action)
            if self.driver.current_url.endswith(expected_url):
                return result
            logging.warn(failure_message)
            time.sleep(0.5)
        raise Exception(failure_message)

    def force_admin_login(self, email):
        return self._try_to_navigate(
            self._course_list_login_page, self.COURSE_LIST_LOGIN_URL).login(
                email, True)

    def login(self, email, admin=True, logout_first=False,
              login_page=None, logout_page=None):
        if logout_first:
            if not logout_page:
                logout_page = self.load_root_page()
                if login_page is None:
                    # Avoid loading the root page repeatedly.
                    login_page = logout_page
            logout_page.click_logout()

        if login_page is None:
            login_page = self.load_root_page()
        return login_page.click_login().login(email, admin=admin)

    def logout(self, logout_page=None):
        if not logout_page:
            logout_page = self.load_root_page()
        return logout_page.click_logout()

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
        title = u'Ţěṥŧ Ĉӧևɽṣḙ ({})'.format(uid)
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

        # Create a record of courses we have created so they can be deleted
        # in teardown.
        self.course_namespaces.append('ns_{}'.format(name))

    def delete_course(self, namespace, login=True):
        if login:
            self.login(self.LOGIN, admin=True)

        # Best effort, but don't block test if course removal fails.  Removing
        # courses is a cleanup step that helps reduce flakes.  Don't add to
        # flakiness by being fragile about cleanup failures.
        patience = 5
        while patience:
            patience -= 1

            page = self.load_courses_list()
            try:
                element = page.find_element_by_css_selector(
                    '[data-course-namespace={}] [delete_course] button'.format(
                        namespace))
                element.click()
                page.switch_to_alert().accept()
            except exceptions.TimeoutException:
                logging.info('Could not find course; assuming deleted.')
                common_utils.log_exception_origin()
                break
            except exceptions.UnexpectedAlertPresentException, ex1:
                logging.warning('Unexpected alert: %s', str(ex1))
                common_utils.log_exception_origin()
                page.switch_to_alert().accept()  # Previous alert?  Not ours?
                continue
            except exceptions.WebDriverException, ex2:
                logging.warning('WebDriverException: %s', str(ex2))
                common_utils.log_exception_origin()
                continue

            self.course_namespaces.remove(namespace)
            break

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

        course_page = None

        for p in persons:
            self.login(p.email, admin=p.admin, logout_first=True,
                       logout_page=course_page)  # Log out from current page.
            course_page = self.load_course(
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


class Snapshot(object):

    SNAPSHOTS_DIR = 'snapshots'
    IGNORE_IDS = [
        'tests.integration.test_classes.IntegrationServerInitializationTask'
        '.test_setup_default_course',
    ]

    WHAT_URL = 'url'
    WHAT_SCREENSHOT = 'screenshot'
    WHAT_TRACEBACK = 'traceback'
    WHAT_PAGE_SOURCE = 'page_source'
    WHAT_TITLE = 'title'
    WHAT_ALL = [
        WHAT_URL,
        WHAT_SCREENSHOT,
        WHAT_TRACEBACK,
        WHAT_PAGE_SOURCE,
        WHAT_TITLE]
    WHEN_GET = 'get'
    WHEN_CLICK = 'click'
    WHEN_WAIT_TIMEOUT = 'wait_timeout'

    def __init__(self, driver, test_id, collect_what):
        self._save_get = None
        self._save_click = None
        self._save_until = None

        if test_id in self.IGNORE_IDS or not collect_what:
            return

        self._active = True
        now = datetime.datetime.now().strftime('%Y-%m-%d_%H:%M:%S')
        dirname = os.path.join(self.SNAPSHOTS_DIR, '%s_%s' % (now, test_id))

        def collect_snapshot(collect_what):
            if not collect_what:
                return

            step_time = datetime.datetime.now().strftime('%H:%M:%S.%f')
            subdir_name = os.path.join(dirname, step_time)
            os.makedirs(subdir_name)

            if self.WHAT_SCREENSHOT in collect_what:
                screenshot_name = os.path.join(subdir_name, 'screenshot.png')
                try:
                    with open(screenshot_name, 'wb') as fp:
                        fp.write(driver.get_screenshot_as_png())
                except Exception:  # pylint: disable=broad-except
                    os.unlink(screenshot_name)

            if self.WHAT_TRACEBACK in collect_what:
                with open(os.path.join(subdir_name, 'traceback'), 'w') as fp:
                    fp.writelines(traceback.format_stack()[:-2])

            if self.WHAT_URL in collect_what:
                current_url_name = os.path.join(subdir_name, 'current_url')
                try:
                    with open(current_url_name, 'w') as fp:
                        fp.write(driver.current_url + '\n')
                except (exceptions.NoSuchWindowException,
                        exceptions.WebDriverException):
                    os.unlink(current_url_name)

            if self.WHAT_PAGE_SOURCE in collect_what:
                with open(os.path.join(subdir_name, 'page_source'), 'w') as fp:
                    fp.write((driver.page_source).encode('utf-8'))

            if self.WHAT_TITLE in collect_what:
                with open(os.path.join(subdir_name, 'title'), 'w') as fp:
                    fp.write(driver.title + '\n')

        if self.WHEN_GET in collect_what:
            save_get = webdriver.chrome.webdriver.WebDriver.get
            def wrap_get(self, url):
                ret = save_get(self, url)
                collect_snapshot(collect_what[Snapshot.WHEN_GET])
                return ret
            webdriver.chrome.webdriver.WebDriver.get = wrap_get
            self._save_get = save_get

        if self.WHEN_CLICK in collect_what:
            save_click = webelement.WebElement.click
            def wrap_click(self):
                ret = save_click(self)
                collect_snapshot(collect_what[Snapshot.WHEN_GET])
                return ret
            webelement.WebElement.click = wrap_click
            self._save_click = save_click

        if self.WHEN_WAIT_TIMEOUT in collect_what:
            save_until = wait.WebDriverWait.until
            def wrap_until(self, method, message=''):
                try:
                    return save_until(method, message)
                except exceptions.TimeoutException:
                    collect_snapshot(collect_what[Snapshot.WHEN_WAIT_TIMEOUT])
                    raise
            self._save_until = save_until

    def tearDown(self):
        if self._save_get:
            webdriver.chrome.webdriver.WebDriver.get = self._save_get
        if self._save_click:
            webelement.WebElement.click = self._save_click
        if self._save_until:
            wait.WebDriverWait.until = self._save_until
