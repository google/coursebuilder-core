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
from xml.etree import cElementTree

import bs4
import html5lib

import appengine_config
from common import users
from controllers import sites
from controllers import utils
import main
from models import config
from models import courses
from models import custom_modules
from models import permissions
from models import transforms
from models import vfs
from tests import suite

from google.appengine.api import memcache
from google.appengine.api import namespace_manager
from google.appengine.ext.testbed import datastore_stub_util

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


class MockAppContext(object):

    def __init__(self, environ=None, namespace=None, slug=None):
        self.environ = environ or {}
        self.namespace = namespace if namespace is not None else 'namespace'
        self.slug = slug if slug is not None else 'slug'
        self.fs = vfs.AbstractFileSystem(
            vfs.LocalReadOnlyFileSystem(logical_home_folder='/'))

    def get_environ(self):
        return self.environ

    def get_namespace_name(self):
        return self.namespace

    def get_slug(self):
        return self.slug


class MockHandler(object):

    def __init__(self, app_context=None, base_href=None):
        self.app_context = app_context or MockAppContext()
        self.base_href = base_href or 'http://mycourse.appspot.com/'

    def get_base_href(self, unused_handler):
        return self.base_href + self.app_context.slug + '/'


class ShouldHaveFailedByNow(Exception):
    """Special exception raised when a prior method did not raise."""
    pass


class OverriddenEnvironment(object):
    """Override the course environment from course.yaml with values in a dict.

    Usage:
        Use the class in a with statement as follows:
            with OverridenEnvironment({'course': {'browsable': True}}):
                # calls to Course.get_environ will return a dictionary
                # in which the original value of course/browsable has been
                # shadowed.
    """

    def __init__(self, new_env):
        self._old_get_environ = courses.Course.get_environ
        self._new_env = new_env

    def _get_environ(self, app_context):
        return courses.deep_dict_merge(
            self._new_env, self._old_get_environ(app_context))

    def __enter__(self):
        courses.Course.get_environ = self._get_environ
        return self

    def __exit__(self, *unused_exception_info):
        courses.Course.get_environ = self._old_get_environ
        return False


class OverriddenConfig(object):
    """Override a ConfigProperty value within a scope.

    Usage:

    def test_welcome_page(self):
        with OverriddenConfig(sites.GCB_COURSES_CONFIG.name, ''):
            .... test content needing to believe there are no courses....

    """

    def __init__(self, name, value):
        self._name = name
        self._value = value
        self._had_prev_value = False
        self._prev_value = None

    def __enter__(self):
        self._had_prev_value = self._name in config.Registry.test_overrides
        self._prev_value = config.Registry.test_overrides.get(self._name)
        config.Registry.test_overrides[self._name] = self._value
        return self

    def __exit__(self, *unused_exception_info):
        if not self._had_prev_value:
            del config.Registry.test_overrides[self._name]
        else:
            config.Registry.test_overrides[self._name] = self._prev_value


class OverriddenSchemaPermission(permissions.SimpleSchemaPermission):
    """Bind read/write permissions to a single email address for testing.

    Using this class does not require construction and registering
    permissions and roles, just an email address.  This is useful when what
    you're testing is not the permissions/roles setup, but page appearance due
    to presence/absence of read/edit authority on one or more properties.

    This class also supports Python's context-manager idiom, and so this
    class can be used in a "with" statement, as:

    def test_foo(self):
        with OverriddenSchemaPermission(
            'fake_course_perm', constants.SCOPE_COURSE_SETTINGS, 'foo@bar.com',
            editable_perms=['course/course:now_available']):

            actions.login('foo@bar.com')
            response = self.get('dashboard?action=outline')
            .... verify dashboard UI when user may edit course availability...

            actions.login('not-foo@bar.com')
            response = self.get('dashboard?action=outline')
            .... verify dashboard UI when course availability not editable...

    """

    def __init__(self, permission_name, scope, email_address,
                 readable_perms=None, editable_perms=None):
        super(OverriddenSchemaPermission, self).__init__(
            None, permission_name, readable_list=readable_perms,
            editable_list=editable_perms)
        self._scope = scope
        self._email_address = email_address

    def applies_to_current_user(self, unused_app_context):
        return users.get_current_user().email() == self._email_address

    def __enter__(self):
        permissions.SchemaPermissionRegistry.add(self._scope, self)
        return self

    def __exit__(self, *unused_exception_info):
        permissions.SchemaPermissionRegistry.remove(self._scope,
                                                    self._permission_name)
        return False


class PreserveUser(object):

    def __enter__(self):
        self._user_email = os.environ.get('USER_EMAIL')
        self._user_id = os.environ.get('USER_ID')
        self._user_is_admin = os.environ.get('USER_IS_ADMIN')
        return self

    def __exit__(self, *unused_exception_info):
        if self._user_email:
            os.environ['USER_EMAIL'] = self._user_email
        elif 'USER_EMAIL' in os.environ:
            del os.environ['USER_EMAIL']
        elif 'USER_ID' in os.environ:
            del os.environ['USER_ID']
        elif 'USER_IS_ADMIN' in os.environ:
            del os.environ['USER_IS_ADMIN']


class TestBase(suite.AppEngineTestBase):
    """Contains methods common to all functional tests."""

    last_request_url = None

    def getApp(self):
        main.debug = True
        sites.ApplicationRequestHandler.bind(main.namespaced_routes)
        return main.app

    def assert_default_namespace(self):
        ns = namespace_manager.get_namespace()
        if ns != appengine_config.DEFAULT_NAMESPACE_NAME:
            raise Exception('Expected default namespace, found: %s' % ns)

    def get_auto_deploy(self):
        return True

    def setUp(self):
        super(TestBase, self).setUp()

        self.test_mode_value = os.environ.get('GCB_TEST_MODE', None)
        os.environ['GCB_TEST_MODE'] = 'true'

        memcache.flush_all()
        sites.ApplicationContext.clear_per_process_cache()
        courses.Course.clear_current()

        self.auto_deploy = sites.ApplicationContext.AUTO_DEPLOY_DEFAULT_COURSE
        sites.ApplicationContext.AUTO_DEPLOY_DEFAULT_COURSE = (
            self.get_auto_deploy())

        self.supports_editing = False
        self.assert_default_namespace()
        self.namespace = ''
        self.base = '/'
        # Reload all properties now to flush the values modified in other tests.
        config.Registry.get_overrides(True)

    def tearDown(self):
        self.assert_default_namespace()
        sites.ApplicationContext.AUTO_DEPLOY_DEFAULT_COURSE = self.auto_deploy

        if self.test_mode_value is None:
            del os.environ['GCB_TEST_MODE']
        else:
            os.environ['GCB_TEST_MODE'] = self.test_mode_value

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

    @classmethod
    def parse_html_string(cls, html_str):
        """Parse the given HTML string to a XML DOM tree.

        Args:
          html_str: string. The HTML document to be parsed.

        Returns:
          An ElementTree representation of the DOM.
        """
        parser = html5lib.HTMLParser(
            tree=html5lib.treebuilders.getTreeBuilder('etree', cElementTree),
            namespaceHTMLElements=False)
        return parser.parse(html_str)

    @classmethod
    def parse_html_string_to_soup(cls, html_str):
        return bs4.BeautifulSoup(html_str)

    def execute_all_deferred_tasks(self, queue_name='default',
                                   iteration_limit=None):
        """Executes all pending deferred tasks."""

        # Outer loop here because some tasks (esp. map/reduce) will enqueue
        # more tasks as part of their operation.
        tasks_executed = 0
        while iteration_limit is None or iteration_limit > 0:
            tasks = self.taskq.GetTasks(queue_name)
            if not tasks:
                break
            for task in tasks:
                old_namespace = namespace_manager.get_namespace()
                try:
                    self.task_dispatcher.dispatch_task(task)
                    tasks_executed += 1
                finally:
                    if sites.has_path_info():
                        sites.unset_path_info()
                    namespace_manager.set_namespace(old_namespace)
            if iteration_limit:
                iteration_limit -= 1
        return tasks_executed

    def get(self, url, previous_response=None, **kwargs):
        url = self.canonicalize(url, response=previous_response)
        logging.info('HTTP Get: %s', url)
        response = self.testapp.get(url, **kwargs)
        return self.hook_response(response)

    def post(self, url, params, expect_errors=False, upload_files=None,
             **kwargs):
        url = self.canonicalize(url)
        logging.info('HTTP Post: %s', url)
        response = self.testapp.post(url, params, expect_errors=expect_errors,
                                     upload_files=upload_files, **kwargs)
        return self.hook_response(response)

    def put(self, url, params, expect_errors=False):
        url = self.canonicalize(url)
        logging.info('HTTP Put: %s', url)
        response = self.testapp.put(url, params, expect_errors=expect_errors)
        return self.hook_response(response)

    def delete(self, url, expect_errors=False):
        url = self.canonicalize(url)
        logging.info('HTTP Delete: %s', url)
        response = self.testapp.delete(url, expect_errors=expect_errors)
        return self.hook_response(response)

    def click(self, response, name, expect_errors=False):
        links = self.parse_html_string(response.body).findall('.//a')
        for link in links:
            if link.text and link.text.strip() == name:
                return self.get(link.get('href'), response,
                                expect_errors=expect_errors)
        complaint = 'No link with text "%s" found on page.\n' % name
        for link in links:
            if link.text:
                complaint += 'Possible link text: "%s"\n' % link.text.strip()
        raise ValueError(complaint)

    def submit(self, form, previous_response=None):
        logging.info('Form submit: %s', form)
        form.action = self.canonicalize(form.action, previous_response)
        response = form.submit()
        return self.hook_response(response)


class ExportTestBase(TestBase):
    """Base test class for classes that implement export functionality.

    If your entities.BaseEntity class implements a custom for_export or
    safe_key, you probably want to test them with this TestCase.
    """

    def assert_blacklisted_properties_removed(self, original_model, exported):
        for prop in original_model._get_export_blacklist():
            self.assertFalse(hasattr(exported, prop))

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
        except Exception:  # pylint: disable=broad-except
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
        except Exception:  # pylint: disable=broad-except
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
    assert email
    # Encode email to generate a bogus user ID using the same algorithm the
    # App Engine internals use for the dev server when creating fake IDs.
    user_id = datastore_stub_util.SynthesizeUserId(email)
    return login_with_specified_user_id(email, user_id, is_admin=is_admin)

def login_with_specified_user_id(email, user_id, is_admin=False):
    assert email
    assert user_id
    os.environ['USER_EMAIL'] = email
    os.environ['USER_ID'] = user_id
    os.environ['USER_IS_ADMIN'] = '1' if is_admin else '0'
    return users.get_current_user()

def get_current_user_email():
    email = os.environ['USER_EMAIL']
    if not email:
        raise Exception('No current user.')
    return email


def logout():
    if 'USER_EMAIL' in os.environ:
        del os.environ['USER_EMAIL']
    if 'USER_ID' in os.environ:
        del os.environ['USER_ID']
    if 'USER_IS_ADMIN' in os.environ:
        del os.environ['USER_IS_ADMIN']


def in_course(course, url):
    if not course:
        return url
    return '%s/%s' % (course, url)


def register(browser, name, course=None):
    """Registers a new student with the given name."""

    response = view_registration(browser, course)
    register_form = get_form_by_action(response, 'register')
    register_form.set('form01', name)
    response = browser.submit(register_form, response)

    assert_equals(response.status_int, 302)
    assert_contains(
        'course#registration_confirmation', response.headers['location'])
    check_profile(browser, name, course)
    return response


def check_profile(browser, name, course=None):
    response = view_my_profile(browser, course)
    assert_contains('Email', response.body)
    assert_contains(cgi.escape(name), response.body)
    assert_contains(get_current_user_email(), response.body)
    return response


def view_registration(browser, course=None):
    response = browser.get(in_course(course, 'register'))
    check_personalization(browser, response)
    assert_contains('What is your name?', response.body)
    assert_contains_all_of([
        '<!-- reg_form.additional_registration_fields -->'], response.body)
    return response


def register_with_additional_fields(browser, name, data2, data3):
    """Registers a new student with customized registration form."""

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


def view_course(browser):
    """Views /course page."""
    response = browser.get('course')

    assert_contains(' the stakes are high.', response.body)
    assert_contains('<a href="assessment?name=Pre"> Pre-course assessment </a>',
                    response.body, collapse_whitespace=True)
    check_personalization(browser, response)

    assert_contains_all_of(BASE_HOOK_POINTS, response.body)
    assert_contains_none_of(UNIT_HOOK_POINTS, response.body)

    return response


def view_unit(browser):
    """Views /unit page."""
    response = browser.get('unit?unit=1&lesson=1')

    assert_contains('Unit 1 - Introduction', response.body)
    assert_contains('1.3 How search works', response.body)
    assert_contains('1.6 Finding text on a web page', response.body)
    assert_contains(
        '<script>gcbTagYoutubeEnqueueVideo("1ppwmxidyIE", ', response.body)
    check_personalization(browser, response)

    assert_contains_all_of(BASE_HOOK_POINTS, response.body)
    assert_contains_all_of(UNIT_HOOK_POINTS, response.body)

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


def view_my_profile(browser, course=None):
    response = browser.get(in_course(course, 'student/home'))
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
    course = None

    for app_context in sites.get_all_courses():
        if app_context.get_slug() == browser.base:
            course = courses.Course(None, app_context=app_context)
            break

    assert course is not None, 'browser.base must match a course'

    if course.version == courses.COURSE_MODEL_VERSION_1_3:
        parent = course.get_parent_unit(unit_id)
        if parent is not None:
            response = browser.get(
                'unit?unit=%s&assessment=%s' % (parent.unit_id, unit_id))
        else:
            response = browser.get('assessment?name=%s' % unit_id)

    elif course.version == courses.COURSE_MODEL_VERSION_1_2:
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


def unregister(browser, course=None):
    """Unregister a student."""
    if course:
        response = browser.get('/%s/student/home' % course)
    else:
        response = browser.get('student/home')
    response = browser.click(response, 'Unenroll')

    assert_contains('to unenroll from', response.body)
    unregister_form = get_form_by_action(response, 'student/unenroll')
    browser.submit(unregister_form, response)


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
        return [view_my_profile, view_registration]

    @classmethod
    def get_logged_out_allowed_pages(cls):
        """Returns all pages that a logged-out user can see."""
        return [view_announcements]

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
        return [view_registration]

    @classmethod
    def get_unenrolled_student_allowed_pages(cls):
        """Returns all pages that a logged-in, unenrolled student can see."""
        return [view_announcements, view_registration]

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


def update_course_config(name, settings):
    """Merge settings into the saved course.yaml configuration.

    Args:
      name: Name of the course.  E.g., 'my_test_course'.
      settings: A nested dict of name/value settings.  Names for items here
          can be found in modules/dashboard/course_settings.py in
          create_course_registry.  See below in simple_add_course()
          for an example.
    Returns:
      Context object for the modified course.
    """
    site_type = 'course'
    namespace = 'ns_%s' % name
    slug = '/%s' % name
    rule = '%s:%s::%s' % (site_type, slug, namespace)

    context = sites.get_all_courses(rule)[0]
    environ = courses.deep_dict_merge(settings,
                                      courses.Course.get_environ(context))
    course = courses.Course(handler=None, app_context=context)
    course.save_settings(environ)
    course_config = config.Registry.test_overrides.get(
        sites.GCB_COURSES_CONFIG.name, 'course:/:/')
    if rule not in course_config:
        course_config = '%s, %s' % (rule, course_config)
        sites.setup_courses(course_config)
    return context


def update_course_config_as_admin(name, admin_email, settings):
    """Log in as admin and merge settings into course.yaml."""

    with PreserveUser():
        login(admin_email, is_admin=True)
        return update_course_config(name, settings)


def simple_add_course(name, admin_email, title):
    """Convenience wrapper to add an active course."""

    return update_course_config_as_admin(
        name, admin_email, {
            'course': {
                'title': title,
                'admin_user_emails': admin_email,
                'now_available': True,
                'browsable': True,
                },
            })


class CourseOutlineTest(TestBase):
    def assertAvailabilityState(self, element, available=None, active=None):
        """Check the state of a lock icon"""
        if available is True:
            self.assertIn('public', element.get('class'))
            self.assertNotIn('private', element.get('class'))
        elif available is False:
            self.assertNotIn('public', element.get('class'))
            self.assertIn('private', element.get('class'))

        if active is True:
            self.assertNotIn('inactive', element.get('class'))
        elif active is False:
            self.assertIn('inactive', element.get('class'))

    def assertEditabilityState(self, element, editable):
        self.assertIsNotNone(element)
        count = 1 if editable else 0
        self.assertEquals(len(element.select('a')), count)
