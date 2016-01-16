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

"""Page objects for integration tests for modules/embed."""

__author__ = [
    'John Cox (johncox@google.com)',
]

from models import transforms
from tests.integration import pageobjects

from selenium.common import exceptions
from selenium.webdriver.common import by
from selenium.webdriver.support import expected_conditions


class StateError(object):
    """Type for embeds rendering an error."""


class StateEmbed(object):
    """Type for embeds rendering embed content."""


class StateSignIn(object):
    """Type for embeds rendering the sign-in control."""


class AbstractIframePageObject(pageobjects.PageObject):
    """Base class for pages that have or are in iframes."""

    def is_embed_page(self):
        try:
            ps = self._tester.driver.find_elements_by_tag_name('p')
            return bool(ps and 'Greetings' in ps[-1].text)
        except exceptions.NoSuchElementException:
            return False

    def is_error_page(self):
        try:
            header = self._tester.driver.find_element_by_tag_name('h1')
            return 'Embed misconfigured' in header.text
        except exceptions.NoSuchElementException:
            return False

    def is_sign_in_page(self):
        try:
            return bool(self._tester.driver.find_element_by_class_name(
                'cb-embed-sign-in-button'))
        except exceptions.NoSuchElementException:
            return False

    def switch_from_iframe(self):
        self._tester.driver.switch_to_default_content()

    def switch_to_iframe(self, iframe):
        self._tester.driver.switch_to_frame(iframe)


class AbstractIframeContentsPageObject(AbstractIframePageObject):
    """Base page object for pages contained in iframes."""

    def __init__(self, tester, iframe):
        super(AbstractIframeContentsPageObject, self).__init__(tester)
        self._iframe = iframe

    def switch_to_iframe(self):
        self._tester.driver.switch_to_frame(self._iframe)


class DemoPage(AbstractIframePageObject):

    _STATES = [
        StateError,
        StateEmbed,
        StateSignIn,
    ]

    def get_cb_embed_elements(self):
        self.wait().until(expected_conditions.visibility_of_element_located(
            (by.By.TAG_NAME, 'cb-embed')))
        return self._tester.driver.find_elements_by_tag_name('cb-embed')

    def get_iframe(self, cb_embed):
        def iframe_present(_):
            return bool(cb_embed.find_element_by_tag_name('iframe'))

        self.wait().until(iframe_present)
        return cb_embed.find_element_by_tag_name('iframe')

    def get_page(self, iframe):
        if self.is_embed_page():
            return ExampleEmbedPage(self._tester, iframe)
        elif self.is_error_page():
            return ErrorPage(self._tester, iframe)
        elif self.is_sign_in_page():
            return SignInPage(self._tester, iframe)
        else:
            raise TypeError('No matching page object found')

    def is_state_valid(self, state):
        return state in self._STATES

    def load(self, url):
        self.get(url)
        return self

    def load_embed(self, cb_embed, wait_for=StateEmbed):
        if not self.is_state_valid(wait_for):
            raise ValueError('Invalid state: %s' % wait_for)

        iframe = self.get_iframe(cb_embed)
        self.switch_to_iframe(iframe)

        def iframe_populated(_):
            # Must always block until embed is in the state the caller requires.
            # Otherwise, timing issues could cause (for example) tests to run
            # against the widget in the sign-in state that expect the widget to
            # be displaying content immediately after sign-in. Note that this
            # does not replace asserts against embed contents in any particular
            # state -- it merely ensures the widget is displaying the right
            # state for the assert to run. All checks against widget contents
            # must come after these blocking calls.
            if wait_for is StateEmbed:
                return self.is_embed_page()
            elif wait_for is StateError:
                return self.is_error_page()
            elif wait_for is StateSignIn:
                return self.is_sign_in_page()

        self.wait().until(iframe_populated)
        page = self.get_page(iframe)
        self.switch_from_iframe()
        return page

    def login(self, email):
        cb_embed = self.get_cb_embed_elements()[0]
        sign_in_page = self.load_embed(
            cb_embed, wait_for=StateSignIn)
        sign_in_page.click().login(email)


class ErrorPage(AbstractIframeContentsPageObject):

    def has_error(self, text):
        self.switch_to_iframe()

        def loaded(_):
            return self.is_error_page()

        self.wait().until(loaded)

        found = False
        for li in self._tester.driver.find_elements_by_tag_name('li'):
            if text in li.text:
                found = True
                break

        self.switch_from_iframe()
        return found


class ExampleEmbedPage(AbstractIframeContentsPageObject):

    def get_text(self):
        self.switch_to_iframe()

        def loaded(_):
            return self.is_embed_page()

        self.wait().until(loaded)
        text = self._tester.driver.find_elements_by_tag_name('p')[-1].text
        self.switch_from_iframe()
        return text


class SignInPage(AbstractIframeContentsPageObject):

    def click(self):
        self.switch_to_iframe()
        self._tester.driver.find_element_by_css_selector(
            '.cb-embed-sign-in-button').click()
        self.switch_from_iframe()
        return self

    def login(self, email):
        last_window_handle = self._tester.driver.current_window_handle
        self.switch_to_login_window(last_window_handle)

        login_page = pageobjects.LoginPage(self._tester)
        login_page.login(email, post_wait=False)

        self._tester.driver.switch_to_window(last_window_handle)

    def get_text(self):
        self.switch_to_iframe()
        text = self._tester.driver.find_element_by_css_selector(
            '.cb-embed-sign-in-button').text
        self.switch_from_iframe()
        return text

    def switch_to_login_window(self, from_handle):
        # Switch to the login window, which cannot be the current window. To
        # avoid interleaving with other tests, do not rely on window order.
        # Instead, cycle through candidates and pick the first with the correct
        # title. We make no attempt to guard against the test executor
        # running multiple tests in the same browser that hit login > 1 times
        # concurrently.
        get_other_handles = lambda: [
            h for h in self._tester.driver.window_handles if h != from_handle]

        def other_windows_exist(_):
            return bool(get_other_handles())

        self.wait().until(other_windows_exist)

        for candidate_handle in get_other_handles():
            self._tester.driver.switch_to_window(candidate_handle)
            if self._tester.driver.title != 'Login':
                self._tester.driver.switch_to_window(from_handle)
            else:
                return

        raise exceptions.InvalidSwitchToTargetException(
            'Unable to find login window')


class EnsureSessionExamplePage(pageobjects.PageObject):
    URL = 'modules/embed/ext/ensure-session-example.html'

    def load(
            self, static_server_base_url, course_builder_base_url,
            redirect=False):

        config = {}
        config['cbHost'] = course_builder_base_url
        if redirect:
            config['redirect'] = True

        self.get('%s/%s#%s' % (
            static_server_base_url, self.URL, transforms.dumps(config)))

        if redirect:
            return pageobjects.LoginPage(
                self._tester, continue_page=EnsureSessionExamplePage)
        else:
            return self

    def _get_start_button(self, pre_wait=True):
        # Check that the page is visible
        self._tester.assertIsNotNone(
            self.find_element_by_id('ensure-session-example-para-1'))

        buttons = self.find_elements_by_css_selector(
            '.cb-embed-sign-in-button', pre_wait=pre_wait)
        if buttons:
            return buttons[0]
        else:
            return None

    def assert_start_button_is_visible(self):
        self._tester.assertIsNotNone(self._get_start_button())
        return self

    def assert_start_button_is_not_visible(self):
        self._tester.assertIsNone(self._get_start_button(pre_wait=False))
        return self

    def click_start_button(self):
        self._get_start_button().click()
        return pageobjects.LoginPage(
            self._tester, continue_page=EnsureSessionExamplePage)
