# Copyright 2012 Google Inc. All Rights Reserved.
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
#
# @author: psimakov@google.com (Pavel Simakov)

"""A collection of actions for testing Course Builder pages."""

import logging
import os
import re
import appengine_config
from controllers import sites
from controllers import utils
import main
import suite
from google.appengine.api import namespace_manager


# All URLs referred to from all the pages.
UNIQUE_URLS_FOUND = {}

BASE_HOOK_POINTS = [
    '<!-- base.before_head_tag_ends -->',
    '<!-- base.after_body_tag_begins -->',
    '<!-- base.after_navbar_begins -->',
    '<!-- base.before_navbar_ends -->',
    '<!-- base.after_top_content_ends -->',
    '<!-- base.after_main_content_ends -->',
    '<!-- base.before_body_tag_ends -->']

UNIT_HOOK_POINTS = [
    '<!-- unit.after_leftnav_begins -->',
    '<!-- unit.before_leftnav_ends -->',
    '<!-- unit.after_content_begins -->',
    '<!-- unit.before_content_ends -->']

PREVIEW_HOOK_POINTS = [
    '<!-- preview.after_top_content_ends -->',
    '<!-- preview.after_main_content_ends -->']


class MustFail(Exception):
    """Special exception raised when a prior method did not raise."""
    pass


class TestBase(suite.BaseTestClass):
    """Contains methods common to all tests."""

    def getApp(self):  # pylint: disable-msg=g-bad-name
        main.debug = True
        sites.ApplicationRequestHandler.bind(main.urls)
        return main.app

    def assert_default_namespace(self):
        ns = namespace_manager.get_namespace()
        if not ns == appengine_config.DEFAULT_NAMESPACE_NAME:
            raise Exception('Expected default namespace, found: %s' % ns)

    def setUp(self):  # pylint: disable-msg=g-bad-name
        super(TestBase, self).setUp()
        self.assert_default_namespace()
        self.namespace = ''
        self.base = '/'

    def tearDown(self):  # pylint: disable-msg=g-bad-name
        self.assert_default_namespace()
        super(TestBase, self).tearDown()

    def canonicalize(self, href, response=None):
        """Create absolute URL using <base> if defined, '/' otherwise."""
        if href.startswith('/') or utils.ApplicationHandler.is_absolute(href):
            pass
        else:
            base = '/'
            if response:
                match = re.search(
                    r'<base href=[\'"]?([^\'" >]+)', response.body)
                if match and not href.startswith('/'):
                    base = match.groups()[0]
            href = '%s%s' % (base, href)
        self.audit_url(href)
        return href

    def audit_url(self, url):
        """Record for audit purposes the URL we encountered."""
        UNIQUE_URLS_FOUND[url] = True

    def hook_response(self, response):
        """Modify response.goto() to compute URL using <base>, if defined."""
        if response.status_int == 200:
            self.check_response_hrefs(response)

        gotox = response.goto

        def new_goto(href, method='get', **args):
            return gotox(self.canonicalize(href), method, **args)

        response.goto = new_goto
        return response

    def check_response_hrefs(self, response):
        """Check response page URLs are properly formatted/canonicalized."""
        hrefs = re.findall(r'href=[\'"]?([^\'" >]+)', response.body)
        srcs = re.findall(r'src=[\'"]?([^\'" >]+)', response.body)
        for url in hrefs + srcs:
            # We expect all internal URLs to be relative: 'asset/css/main.css',
            # and use <base> tag. All others URLs must be whitelisted below.
            if url.startswith('/'):
                absolute = url.startswith('//')
                root = url == '/'
                canonical = url.startswith(self.base)
                allowed = url.startswith('/admin') or url.startswith('/_ah/')

                if not (absolute or root or canonical or allowed):
                    raise Exception('Invalid reference \'%s\' in:\n%s' % (
                        url, response.body))

            self.audit_url(self.canonicalize(url, response))

    def get(self, url):
        url = self.canonicalize(url)
        logging.info('HTTP Get: %s', url)
        response = self.testapp.get(url)
        return self.hook_response(response)

    def post(self, url, params):
        url = self.canonicalize(url)
        logging.info('HTTP Post: %s', url)
        response = self.testapp.post(url, params)
        return self.hook_response(response)

    def put(self, url, params):
        url = self.canonicalize(url)
        logging.info('HTTP Put: %s', url)
        response = self.testapp.put(url, params)
        return self.hook_response(response)

    def click(self, response, name):
        logging.info('Link click: %s', name)
        response = response.click(name)
        return self.hook_response(response)

    def submit(self, form):
        logging.info('Form submit: %s', form)
        response = form.submit()
        return self.hook_response(response)


def assert_equals(expected, actual):
    if not expected == actual:
        raise Exception('Expected \'%s\', does not match actual \'%s\'.' %
                        (expected, actual))


def assert_contains(needle, haystack):
    if not needle in haystack:
        raise Exception('Can\'t find \'%s\' in \'%s\'.' % (needle, haystack))


def assert_contains_all_of(needles, haystack):
    for needle in needles:
        if not needle in haystack:
            raise Exception(
                'Can\'t find \'%s\' in \'%s\'.' % (needle, haystack))


def assert_does_not_contain(needle, haystack):
    if needle in haystack:
        raise Exception('Found \'%s\' in \'%s\'.' % (needle, haystack))


def assert_contains_none_of(needles, haystack):
    for needle in needles:
        if needle in haystack:
            raise Exception('Found \'%s\' in \'%s\'.' % (needle, haystack))


def assert_none_fail(browser, callbacks):
    """Invokes all callbacks and expects each one not to fail."""
    for callback in callbacks:
        callback(browser)


def assert_all_fail(browser, callbacks):
    """Invokes all callbacks and expects each one to fail."""

    for callback in callbacks:
        try:
            callback(browser)
            raise MustFail('Expected to fail: %s().' % callback.__name__)
        except MustFail as e:
            raise e
        except Exception:
            pass


def login(email, is_admin=False):
    os.environ['USER_EMAIL'] = email
    os.environ['USER_ID'] = 'user1'

    is_admin_value = '0'
    if is_admin:
        is_admin_value = '1'
    os.environ['USER_IS_ADMIN'] = is_admin_value


def get_current_user_email():
    email = os.environ['USER_EMAIL']
    if not email:
        raise Exception('No current user.')
    return email


def logout():
    del os.environ['USER_EMAIL']
    del os.environ['USER_ID']
    del os.environ['USER_IS_ADMIN']


def register(browser, name):
    """Registers a new student with the given name."""

    response = browser.get('/')
    assert_equals(response.status_int, 302)

    response = view_registration(browser)

    response.form.set('form01', name)
    response = browser.submit(response.form)

    assert_contains('Thank you for registering for', response.body)
    check_profile(browser, name)


def check_profile(browser, name):
    response = view_my_profile(browser)
    assert_contains('Email', response.body)
    assert_contains(name, response.body)
    assert_contains(get_current_user_email(), response.body)
    return response


def view_registration(browser):
    response = browser.get('register')
    assert_contains('What is your name?', response.body)
    assert_contains_all_of([
        '<!-- reg_form.additional_registration_fields -->'], response.body)
    return response


def view_preview(browser):
    """Views /preview page."""
    response = browser.get('preview')
    assert_contains(' the stakes are high.', response.body)
    assert_contains(
        '<li><p class="top_content">Pre-course assessment</p></li>',
        response.body)

    assert_contains_none_of(UNIT_HOOK_POINTS, response.body)
    assert_contains_all_of(PREVIEW_HOOK_POINTS, response.body)

    return response


def view_course(browser):
    """Views /course page."""
    response = browser.get('course')

    assert_contains(' the stakes are high.', response.body)
    assert_contains('<a href="assessment?name=Pre">Pre-course assessment</a>',
                    response.body)
    assert_contains(get_current_user_email(), response.body)

    assert_contains_all_of(BASE_HOOK_POINTS, response.body)
    assert_contains_none_of(UNIT_HOOK_POINTS, response.body)
    assert_contains_none_of(PREVIEW_HOOK_POINTS, response.body)

    return response


def view_unit(browser):
    """Views /unit page."""
    response = browser.get('unit?unit=1&lesson=1')

    assert_contains('Unit 1 - Introduction', response.body)
    assert_contains('1.3 How search works', response.body)
    assert_contains('1.6 Finding text on a web page', response.body)
    assert_contains('http://www.youtube.com/embed/1ppwmxidyIE', response.body)
    assert_contains(get_current_user_email(), response.body)

    assert_contains_all_of(BASE_HOOK_POINTS, response.body)
    assert_contains_all_of(UNIT_HOOK_POINTS, response.body)
    assert_contains_none_of(PREVIEW_HOOK_POINTS, response.body)

    return response


def view_activity(browser):
    response = browser.get('activity?unit=1&lesson=2')
    assert_contains('<script src="assets/js/activity-1.2.js"></script>',
                    response.body)
    assert_contains(get_current_user_email(), response.body)
    return response


def view_announcements(browser):
    response = browser.get('announcements')
    assert_equals(response.status_int, 200)
    assert_contains(get_current_user_email(), response.body)
    return response


def view_my_profile(browser):
    response = browser.get('student/home')
    assert_contains('Date enrolled', response.body)
    assert_contains(get_current_user_email(), response.body)
    return response


def view_forum(browser):
    response = browser.get('forum')
    assert_contains('document.getElementById("forum_embed").src =',
                    response.body)
    assert_contains(get_current_user_email(), response.body)
    return response


def view_assessments(browser):
    for name in ['Pre', 'Mid', 'Fin']:
        response = browser.get('assessment?name=%s' % name)
        assert 'assets/js/assessment-%s.js' % name in response.body
        assert_equals(response.status_int, 200)
        assert_contains(get_current_user_email(), response.body)


def change_name(browser, new_name):
    response = browser.get('student/home')

    response.form.set('name', new_name)
    response = browser.submit(response.form)

    assert_equals(response.status_int, 302)
    check_profile(browser, new_name)


def unregister(browser):
    response = browser.get('student/home')
    response = browser.click(response, 'Unenroll')

    assert_contains('to unenroll from', response.body)
    browser.submit(response.form)


class Permissions(object):
    """Defines who can see what."""

    @classmethod
    def get_logged_out_allowed_pages(cls):
        """Returns all pages that a logged-out user can see."""
        return [view_preview]

    @classmethod
    def get_logged_out_denied_pages(cls):
        """Returns all pages that a logged-out user can't see."""
        return [view_announcements, view_forum, view_course, view_assessments,
                view_unit, view_activity, view_my_profile, view_registration]

    @classmethod
    def get_enrolled_student_allowed_pages(cls):
        """Returns all pages that a logged-in, enrolled student can see."""
        return [view_announcements, view_forum, view_course,
                view_assessments, view_unit, view_activity, view_my_profile]

    @classmethod
    def get_enrolled_student_denied_pages(cls):
        """Returns all pages that a logged-in, enrolled student can't see."""
        return [view_registration, view_preview]

    @classmethod
    def get_unenrolled_student_allowed_pages(cls):
        """Returns all pages that a logged-in, unenrolled student can see."""
        return [view_registration, view_preview]

    @classmethod
    def get_unenrolled_student_denied_pages(cls):
        """Returns all pages that a logged-in, unenrolled student can't see."""
        pages = Permissions.get_enrolled_student_allowed_pages()
        for allowed in Permissions.get_unenrolled_student_allowed_pages():
            if allowed in pages:
                pages.remove(allowed)
        return pages

    @classmethod
    def assert_logged_out(cls, browser):
        """Check that only pages for a logged-out user are visible."""
        assert_none_fail(browser, Permissions.get_logged_out_allowed_pages())
        assert_all_fail(browser, Permissions.get_logged_out_denied_pages())

    @classmethod
    def assert_enrolled(cls, browser):
        """Check that only pages for an enrolled student are visible."""
        assert_none_fail(
            browser, Permissions.get_enrolled_student_allowed_pages())
        assert_all_fail(
            browser, Permissions.get_enrolled_student_denied_pages())

    @classmethod
    def assert_unenrolled(cls, browser):
        """Check that only pages for an unenrolled student are visible."""
        assert_none_fail(
            browser, Permissions.get_unenrolled_student_allowed_pages())
        assert_all_fail(
            browser, Permissions.get_unenrolled_student_denied_pages())
