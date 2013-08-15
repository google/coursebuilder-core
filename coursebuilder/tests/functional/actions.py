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

import cgi
import functools
import logging
import os
import re
import urllib

import appengine_config
from controllers import sites
from controllers import utils
import main
from models import config
from models import custom_modules
from models import transforms
from tests import suite
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


class ShouldHaveFailedByNow(Exception):
    """Special exception raised when a prior method did not raise."""
    pass


class TestBase(suite.AppEngineTestBase):
    """Contains methods common to all functional tests."""

    last_request_url = None

    def getApp(self):  # pylint: disable-msg=g-bad-name
        main.debug = True
        sites.ApplicationRequestHandler.bind(main.namespaced_routes)
        return main.app

    def assert_default_namespace(self):
        ns = namespace_manager.get_namespace()
        if ns != appengine_config.DEFAULT_NAMESPACE_NAME:
            raise Exception('Expected default namespace, found: %s' % ns)

    def setUp(self):  # pylint: disable-msg=g-bad-name
        super(TestBase, self).setUp()

        self.supports_editing = False
        self.assert_default_namespace()
        self.namespace = ''
        self.base = '/'

        # Reload all properties now to flush the values modified in other tests.
        config.Registry.get_overrides(True)

    def tearDown(self):  # pylint: disable-msg=g-bad-name
        self.assert_default_namespace()
        super(TestBase, self).tearDown()

    def canonicalize(self, href, response=None):
        """Create absolute URL using <base> if defined, self.base otherwise."""
        if href.startswith('/') or utils.ApplicationHandler.is_absolute(href):
            pass
        else:
            base = self.base
            if response:
                match = re.search(
                    r'<base href=[\'"]?([^\'" >]+)', response.body)
                if match and not href.startswith('/'):
                    base = match.groups()[0]
            if not base.endswith('/'):
                base += '/'
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

        self.last_request_url = self.canonicalize(response.request.path)

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
                allowed = self.url_allowed(url)

                if not (absolute or root or canonical or allowed):
                    raise Exception('Invalid reference \'%s\' in:\n%s' % (
                        url, response.body))

            self.audit_url(self.canonicalize(url, response=response))

    def url_allowed(self, url):
        """Check whether a URL should be allowed as a href in the response."""
        if url.startswith('/_ah/'):
            return True
        global_routes = []
        for module in custom_modules.Registry.registered_modules.values():
            for route, unused_handler in module.global_routes:
                global_routes.append(route)
        if any(re.match(route, url) for route in global_routes):
            return True

        return False

    def get(self, url, **kwargs):
        url = self.canonicalize(url)
        logging.info('HTTP Get: %s', url)
        response = self.testapp.get(url, **kwargs)
        return self.hook_response(response)

    def post(self, url, params, expect_errors=False):
        url = self.canonicalize(url)
        logging.info('HTTP Post: %s', url)
        response = self.testapp.post(url, params, expect_errors=expect_errors)
        return self.hook_response(response)

    def put(self, url, params, expect_errors=False):
        url = self.canonicalize(url)
        logging.info('HTTP Put: %s', url)
        response = self.testapp.put(url, params, expect_errors=expect_errors)
        return self.hook_response(response)

    def click(self, response, name):
        logging.info('Link click: %s', name)
        response = response.click(name)
        return self.hook_response(response)

    def submit(self, form):
        logging.info('Form submit: %s', form)
        response = form.submit()
        return self.hook_response(response)


class ExportTestBase(TestBase):
    """Base test class for classes that implement export functionality.

    If your entities.BaseEntity class implements a custom for_export or
    safe_key, you probably want to test them with this TestCase.
    """

    def assert_blacklisted_properties_removed(self, original_model, exported):
        # Treating as module-protected. pylint: disable-msg=protected-access
        for prop in original_model._get_export_blacklist():
            self.assertFalse(hasattr(exported, prop.name))

    def transform(self, value):
        return 'transformed_' + value


def assert_equals(actual, expected):
    if expected != actual:
        raise Exception('Expected \'%s\', does not match actual \'%s\'.' %
                        (expected, actual))


def to_unicode(text):
    """Converts text to Unicode if is not Unicode already."""
    if not isinstance(text, unicode):
        return unicode(text, 'utf-8')
    return text


def assert_contains(needle, haystack, collapse_whitespace=False):
    needle = to_unicode(needle)
    haystack = to_unicode(haystack)
    if collapse_whitespace:
        haystack = ' '.join(haystack.replace('\n', ' ').split())
    if needle not in haystack:
        raise Exception('Can\'t find \'%s\' in \'%s\'.' % (needle, haystack))


def assert_contains_all_of(needles, haystack):
    haystack = to_unicode(haystack)
    for needle in needles:
        needle = to_unicode(needle)
        if needle not in haystack:
            raise Exception(
                'Can\'t find \'%s\' in \'%s\'.' % (needle, haystack))


def assert_does_not_contain(needle, haystack, collapse_whitespace=False):
    needle = to_unicode(needle)
    haystack = to_unicode(haystack)
    if collapse_whitespace:
        haystack = ' '.join(haystack.replace('\n', ' ').split())
    if needle in haystack:
        raise Exception('Found \'%s\' in \'%s\'.' % (needle, haystack))


def assert_contains_none_of(needles, haystack):
    haystack = to_unicode(haystack)
    for needle in needles:
        needle = to_unicode(needle)
        if needle in haystack:
            raise Exception('Found \'%s\' in \'%s\'.' % (needle, haystack))


def assert_none_fail(browser, callbacks):
    """Invokes all callbacks and expects each one not to fail."""
    for callback in callbacks:
        callback(browser)


def assert_at_least_one_succeeds(callbacks):
    """Invokes all callbacks and expects at least one to succeed."""
    for callback in callbacks:
        try:
            callback()
            return True
        except Exception:  # pylint: disable-msg=broad-except
            pass
    raise Exception('All callbacks failed.')


def assert_all_fail(browser, callbacks):
    """Invokes all callbacks and expects each one to fail."""

    for callback in callbacks:
        try:
            callback(browser)
            raise ShouldHaveFailedByNow(
                'Expected to fail: %s().' % callback.__name__)
        except ShouldHaveFailedByNow as e:
            raise e
        except Exception:
            pass


def get_form_by_action(response, action):
    """Gets a form give an action string or returns None."""
    form = None
    try:
        form = next(
            form for form in response.forms.values() if form.action == action)
    except StopIteration:
        pass
    return form


def login(email, is_admin=False):
    os.environ['USER_EMAIL'] = email
    os.environ['USER_ID'] = email

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

    response = view_registration(browser)

    register_form = get_form_by_action(response, 'register')
    register_form.set('form01', name)
    response = browser.submit(register_form)

    assert_equals(response.status_int, 302)
    assert_contains(
        'course#registration_confirmation', response.headers['location'])
    check_profile(browser, name)
    return response


def check_profile(browser, name):
    response = view_my_profile(browser)
    assert_contains('Email', response.body)
    assert_contains(cgi.escape(name), response.body)
    assert_contains(get_current_user_email(), response.body)
    return response


def view_registration(browser):
    response = browser.get('register')
    check_personalization(browser, response)
    assert_contains('What is your name?', response.body)
    assert_contains_all_of([
        '<!-- reg_form.additional_registration_fields -->'], response.body)
    return response


def register_with_additional_fields(browser, name, data2, data3):
    """Registers a new student with customized registration form."""

    response = browser.get('/')
    assert_equals(response.status_int, 302)

    response = view_registration(browser)

    register_form = get_form_by_action(response, 'register')
    register_form.set('form01', name)
    register_form.set('form02', data2)
    register_form.set('form03', data3)
    response = browser.submit(register_form)

    assert_equals(response.status_int, 302)
    assert_contains(
        'course#registration_confirmation', response.headers['location'])
    check_profile(browser, name)


def check_logout_link(response_body):
    assert_contains(get_current_user_email(), response_body)


def check_login_link(response_body):
    assert_contains('Login', response_body)


def check_personalization(browser, response):
    """Checks that the login/logout text is correct."""
    sites.set_path_info(browser.last_request_url)
    app_context = sites.get_course_for_current_request()
    sites.unset_path_info()

    browsable = app_context.get_environ()['course']['browsable']

    if browsable:
        callbacks = [
            functools.partial(check_login_link, response.body),
            functools.partial(check_logout_link, response.body)
        ]
        assert_at_least_one_succeeds(callbacks)
    else:
        check_logout_link(response.body)


def view_preview(browser):
    """Views /preview page."""
    response = browser.get('preview')
    assert_contains(' the stakes are high.', response.body)
    assert_contains(
        '<li><p class="gcb-top-content">Pre-course assessment</p></li>',
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
    check_personalization(browser, response)

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
    assert_contains('https://www.youtube.com/embed/1ppwmxidyIE', response.body)
    check_personalization(browser, response)

    assert_contains_all_of(BASE_HOOK_POINTS, response.body)
    assert_contains_all_of(UNIT_HOOK_POINTS, response.body)
    assert_contains_none_of(PREVIEW_HOOK_POINTS, response.body)

    return response


def view_activity(browser):
    response = browser.get('activity?unit=1&lesson=2')
    assert_contains('<script src="assets/js/activity-1.2.js"></script>',
                    response.body)
    check_personalization(browser, response)
    return response


def get_activity(browser, unit_id, lesson_id, args):
    """Retrieve the activity page for a given unit and lesson id."""

    response = browser.get('activity?unit=%s&lesson=%s' % (unit_id, lesson_id))
    assert_equals(response.status_int, 200)
    assert_contains(
        '<script src="assets/js/activity-%s.%s.js"></script>' %
        (unit_id, lesson_id), response.body)
    assert_contains('assets/lib/activity-generic-1.3.js', response.body)

    js_response = browser.get('assets/lib/activity-generic-1.3.js')
    assert_equals(js_response.status_int, 200)

    # Extract XSRF token from the page.
    match = re.search(r'eventXsrfToken = [\']([^\']+)', response.body)
    assert match
    xsrf_token = match.group(1)
    args['xsrf_token'] = xsrf_token

    return response, args


def attempt_activity(browser, unit_id, lesson_id, index, answer, correct):
    """Attempts an activity in a given unit and lesson."""
    response, args = get_activity(browser, unit_id, lesson_id, {})

    # Prepare activity submission event.
    args['source'] = 'attempt-activity'
    args['payload'] = {
        'index': index,
        'type': 'activity-choice',
        'value': answer,
        'correct': correct
    }
    args['payload']['location'] = (
        'http://localhost:8080/activity?unit=%s&lesson=%s' %
        (unit_id, lesson_id))
    args['payload'] = transforms.dumps(args['payload'])

    # Submit the request to the backend.
    response = browser.post('rest/events?%s' % urllib.urlencode(
        {'request': transforms.dumps(args)}), {})
    assert_equals(response.status_int, 200)
    assert not response.body


def view_announcements(browser):
    response = browser.get('announcements')
    assert_equals(response.status_int, 200)
    return response


def view_my_profile(browser):
    response = browser.get('student/home')
    assert_contains('Date enrolled', response.body)
    check_personalization(browser, response)
    return response


def view_forum(browser):
    response = browser.get('forum')
    assert_contains('document.getElementById("forum_embed").src =',
                    response.body)
    check_personalization(browser, response)
    return response


def view_assessments(browser):
    for name in ['Pre', 'Mid', 'Fin']:
        response = browser.get('assessment?name=%s' % name)
        assert 'assets/js/assessment-%s.js' % name in response.body
        assert_equals(response.status_int, 200)
        check_personalization(browser, response)


def submit_assessment(browser, unit_id, args, presubmit_checks=True):
    """Submits an assessment."""
    response = browser.get('assessment?name=%s' % unit_id)

    if presubmit_checks:
        assert_contains(
            '<script src="assets/js/assessment-%s.js"></script>' % unit_id,
            response.body)
        js_response = browser.get('assets/js/assessment-%s.js' % unit_id)
        assert_equals(js_response.status_int, 200)

    # Extract XSRF token from the page.
    match = re.search(r'assessmentXsrfToken = [\']([^\']+)', response.body)
    assert match
    xsrf_token = match.group(1)
    args['xsrf_token'] = xsrf_token

    response = browser.post('answer', args)
    assert_equals(response.status_int, 200)
    return response


def request_new_review(browser, unit_id, expected_status_code=302):
    """Requests a new assignment to review."""
    response = browser.get('reviewdashboard?unit=%s' % unit_id)
    assert_contains('Assignments for your review', response.body)

    # Extract XSRF token from the page.
    match = re.search(
        r'<input type="hidden" name="xsrf_token"\s* value="([^"]*)">',
        response.body)
    assert match
    xsrf_token = match.group(1)
    args = {'xsrf_token': xsrf_token}

    expect_errors = (expected_status_code not in [200, 302])

    response = browser.post(
        'reviewdashboard?unit=%s' % unit_id, args, expect_errors=expect_errors)
    assert_equals(response.status_int, expected_status_code)

    if expected_status_code == 302:
        assert_equals(response.status_int, expected_status_code)
        assert_contains(
            'review?unit=%s' % unit_id, response.location)
        response = browser.get(response.location)
        assert_contains('Assignment to review', response.body)

    return response


def view_review(browser, unit_id, review_step_key, expected_status_code=200):
    """View a review page."""
    response = browser.get(
        'review?unit=%s&key=%s' % (unit_id, review_step_key),
        expect_errors=(expected_status_code != 200))
    assert_equals(response.status_int, expected_status_code)
    if expected_status_code == 200:
        assert_contains('Assignment to review', response.body)
    return response


def submit_review(
    browser, unit_id, review_step_key, args, presubmit_checks=True):
    """Submits a review."""
    response = browser.get(
        'review?unit=%s&key=%s' % (unit_id, review_step_key))

    if presubmit_checks:
        assert_contains(
            '<script src="assets/js/review-%s.js"></script>' % unit_id,
            response.body)
        js_response = browser.get('assets/js/review-%s.js' % unit_id)
        assert_equals(js_response.status_int, 200)

    # Extract XSRF token from the page.
    match = re.search(r'assessmentXsrfToken = [\']([^\']+)', response.body)
    assert match
    xsrf_token = match.group(1)
    args['xsrf_token'] = xsrf_token

    args['key'] = review_step_key
    args['unit_id'] = unit_id

    response = browser.post('review', args)
    assert_equals(response.status_int, 200)
    return response


def add_reviewer(browser, unit_id, reviewee_email, reviewer_email):
    """Adds a reviewer to a submission."""
    url_params = {
        'action': 'edit_assignment',
        'reviewee_id': reviewee_email,
        'unit_id': unit_id,
    }

    response = browser.get('/dashboard?%s' % urllib.urlencode(url_params))

    # Extract XSRF token from the page.
    match = re.search(
        r'<input type="hidden" name="xsrf_token"\s* value="([^"]*)">',
        response.body)
    assert match
    xsrf_token = match.group(1)
    args = {
        'xsrf_token': xsrf_token,
        'reviewer_id': reviewer_email,
        'reviewee_id': reviewee_email,
        'unit_id': unit_id,
    }
    response = browser.post('/dashboard?action=add_reviewer', args)
    return response


def change_name(browser, new_name):
    """Change the name of a student."""
    response = browser.get('student/home')

    edit_form = get_form_by_action(response, 'student/editstudent')
    edit_form.set('name', new_name)
    response = browser.submit(edit_form)

    assert_equals(response.status_int, 302)
    check_profile(browser, new_name)


def unregister(browser):
    """Unregister a student."""
    response = browser.get('student/home')
    response = browser.click(response, 'Unenroll')

    assert_contains('to unenroll from', response.body)
    unregister_form = get_form_by_action(response, 'student/unenroll')
    browser.submit(unregister_form)


class Permissions(object):
    """Defines who can see what."""

    @classmethod
    def get_browsable_pages(cls):
        """Returns all pages that can be accessed by a logged-out user."""
        return [view_announcements, view_forum, view_course, view_unit,
                view_assessments, view_activity]

    @classmethod
    def get_nonbrowsable_pages(cls):
        """Returns all non-browsable pages."""
        return [view_preview, view_my_profile, view_registration]

    @classmethod
    def get_logged_out_allowed_pages(cls):
        """Returns all pages that a logged-out user can see."""
        return [view_announcements, view_preview]

    @classmethod
    def get_logged_out_denied_pages(cls):
        """Returns all pages that a logged-out user can't see."""
        return [view_forum, view_course, view_assessments,
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
        return [view_announcements, view_registration, view_preview]

    @classmethod
    def get_unenrolled_student_denied_pages(cls):
        """Returns all pages that a logged-in, unenrolled student can't see."""
        pages = Permissions.get_enrolled_student_allowed_pages()
        for allowed in Permissions.get_unenrolled_student_allowed_pages():
            if allowed in pages:
                pages.remove(allowed)
        return pages

    @classmethod
    def assert_can_browse(cls, browser):
        """Check that pages for a browsing user are visible."""
        assert_none_fail(browser, Permissions.get_browsable_pages())
        assert_all_fail(browser, Permissions.get_nonbrowsable_pages())

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
