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

"""Handlers that are not directly related to course content."""

__author__ = 'Saifu Angto (saifu@google.com)'

import datetime
import gettext
import HTMLParser
import os
import re
import urlparse

import jinja2
import sites
import webapp2

import appengine_config
from common import jinja_utils
from common import locales
from common import safe_dom
from common import tags
from common import utils as common_utils
from common.crypto import XsrfTokenManager
from models import courses
from models import models
from models import transforms
from models.config import ConfigProperty
from models.courses import Course
from models.models import Student
from models.models import StudentProfileDAO
from models.models import TransientStudent
from models.roles import Roles
from modules import courses as courses_module

from google.appengine.api import users

# The name of the template dict key that stores a course's base location.
COURSE_BASE_KEY = 'gcb_course_base'

# The name of the template dict key that stores data from course.yaml.
COURSE_INFO_KEY = 'course_info'

# The name of the cookie used to store the locale prefs for users out of session
GUEST_LOCALE_COOKIE = 'cb-user-locale'
GUEST_LOCALE_COOKIE_MAX_AGE_SEC = 48 * 60 * 60  # 48 hours

TRANSIENT_STUDENT = TransientStudent()

# Whether to output debug info into the page.
CAN_PUT_DEBUG_INFO_INTO_PAGES = ConfigProperty(
    'gcb_can_put_debug_info_into_pages', bool, (
        'Whether or not to put debugging information into the web pages. '
        'This may be useful for debugging purposes if you develop custom '
        'Course Builder features or extensions.'), False)

# Whether to record page load/unload events in a database.
CAN_PERSIST_PAGE_EVENTS = ConfigProperty(
    'gcb_can_persist_page_events', bool, (
        'Whether or not to record student page interactions in a '
        'datastore. Without event recording, you cannot analyze student '
        'page interactions. On the other hand, no event recording reduces '
        'the number of datastore operations and minimizes the use of Google '
        'App Engine quota. Turn event recording on if you want to analyze '
        'this data.'),
    False)


# Whether to record tag events in a database.
CAN_PERSIST_TAG_EVENTS = ConfigProperty(
    'gcb_can_persist_tag_events', bool, (
        'Whether or not to record student tag interactions in a '
        'datastore. Without event recording, you cannot analyze student '
        'tag interactions. On the other hand, no event recording reduces '
        'the number of datastore operations and minimizes the use of Google '
        'App Engine quota. Turn event recording on if you want to analyze '
        'this data.'),
    False)


# Whether to record events in a database.
CAN_PERSIST_ACTIVITY_EVENTS = ConfigProperty(
    'gcb_can_persist_activity_events', bool, (
        'Whether or not to record student activity interactions in a '
        'datastore. Without event recording, you cannot analyze student '
        'activity interactions. On the other hand, no event recording reduces '
        'the number of datastore operations and minimizes the use of Google '
        'App Engine quota. Turn event recording on if you want to analyze '
        'this data.'),
    False)


# Date format string for displaying datetimes in UTC.
# Example: 2013-03-21 13:00 UTC
HUMAN_READABLE_DATETIME_FORMAT = '%Y-%m-%d, %H:%M UTC'

# Date format string for displaying dates. Example: 2013-03-21
HUMAN_READABLE_DATE_FORMAT = '%Y-%m-%d'

# Time format string for displaying times. Example: 01:16:40 UTC.
HUMAN_READABLE_TIME_FORMAT = '%H:%M:%S UTC'


class PageInitializer(object):
    """Abstract class that defines an interface to initialize page headers."""

    @classmethod
    def initialize(cls, template_value):
        raise NotImplementedError


class DefaultPageInitializer(PageInitializer):
    """Implements default page initializer."""

    @classmethod
    def initialize(cls, template_value):
        pass


class PageInitializerService(object):
    """Installs the appropriate PageInitializer."""
    _page_initializer = DefaultPageInitializer

    @classmethod
    def get(cls):
        return cls._page_initializer

    @classmethod
    def set(cls, page_initializer):
        cls._page_initializer = page_initializer


class ReflectiveRequestHandler(object):
    """Uses reflection to handle custom get() and post() requests.

    Use this class as a mix-in with any webapp2.RequestHandler to allow request
    dispatching to multiple get() and post() methods based on the 'action'
    parameter.

    Open your existing webapp2.RequestHandler, add this class as a mix-in.
    Define the following class variables:

        default_action = 'list'
        get_actions = ['default_action', 'edit']
        post_actions = ['save']

    Add instance methods named get_list(self), get_edit(self), post_save(self).
    These methods will now be called automatically based on the 'action'
    GET/POST parameter.
    """

    def create_xsrf_token(self, action):
        return XsrfTokenManager.create_xsrf_token(action)

    def get(self):
        """Handles GET."""
        action = self.request.get('action')
        if not action:
            action = self.default_action

        if action not in self.get_actions:
            self.error(404)
            return

        handler = getattr(self, 'get_%s' % action)
        if not handler:
            self.error(404)
            return

        return handler()

    def post(self):
        """Handles POST."""
        action = self.request.get('action')
        if not action or action not in self.post_actions:
            self.error(404)
            return

        handler = getattr(self, 'post_%s' % action)
        if not handler:
            self.error(404)
            return

        # Each POST request must have valid XSRF token.
        xsrf_token = self.request.get('xsrf_token')
        if not XsrfTokenManager.is_xsrf_token_valid(xsrf_token, action):
            self.error(403)
            return

        return handler()


def _get_course_properties():
    return Course.get_environ(sites.get_course_for_current_request())


def display_unit_title(unit, course_properties=None):
    """Prepare an internationalized display for the unit title."""
    if not course_properties:
        course_properties = _get_course_properties()
    if course_properties['course'].get('display_unit_title_without_index'):
        return unit.title
    else:
        # I18N: Message displayed as title for unit within a course.
        return gettext.gettext('Unit %s - %s' % (unit.index, unit.title))


def display_short_unit_title(unit, course_properties=None):
    """Prepare a short unit title."""
    if not course_properties:
        course_properties = _get_course_properties()
    if course_properties['course'].get('display_unit_title_without_index'):
        return unit.title
    if unit.type != 'U':
        return unit.title
    # I18N: Message displayed as title for unit within a course.
    return '%s %s' % (gettext.gettext('Unit'), unit.index)


def display_lesson_title(unit, lesson, course_properties=None):
    """Prepare an internationalized display for the unit title."""
    if not course_properties:
        course_properties = _get_course_properties()

    content = safe_dom.NodeList()
    span = safe_dom.Element('span')
    content.append(span)

    if lesson.auto_index:
        prefix = ''
        if course_properties['course'].get('display_unit_title_without_index'):
            prefix = '%s ' % lesson.index
        else:
            prefix = '%s.%s ' % (unit.index, lesson.index)
        span.add_text(prefix)
        _class = ''
    else:
        _class = 'no-index'

    span.add_text(lesson.title)
    span.set_attribute('className', _class)
    return content


class HtmlHooks(object):

    def __init__(self, course, prefs=None):
        self.course = course
        self.prefs = prefs
        if self.prefs is None:
            self.prefs = models.StudentPreferencesDAO.load_or_create()

    def _has_visible_content(self, html_text):

        class VisibleHtmlParser(HTMLParser.HTMLParser):

            def __init__(self, *args, **kwargs):
                HTMLParser.HTMLParser.__init__(self, *args, **kwargs)
                self._has_visible_content = False

            def handle_starttag(self, unused_tag, unused_attrs):
                # Not 100% guaranteed; e.g., <p> does not guarantee content,
                # but <button> does -- even if the <button> does not contain
                # data/entity/char.  I don't want to spend a lot of logic
                # looking for specific cases, and this behavior is enough.
                self._has_visible_content = True

            def handle_data(self, data):
                if data.strip():
                    self._has_visible_content = True

            def handle_entityref(self, unused_data):
                self._has_visible_content = True

            def handle_charref(self, unused_data):
                self._has_visible_content = True

            def has_visible_content(self):
                return self._has_visible_content

        parser = VisibleHtmlParser()
        parser.feed(html_text)
        parser.close()
        return parser.has_visible_content()

    def insert(self, name):
        # Do we want page markup to permit course admins to edit hooks?
        show_admin_content = False
        if (self.prefs and self.prefs.show_hooks and
            Roles.is_course_admin(self.course.app_context)):
            show_admin_content = True
        if self.course.version == courses.CourseModel12.VERSION:
            show_admin_content = False

        # Look up desired content chunk in course.yaml dict/sub-dict.
        content = ''
        environ = self.course.app_context.get_environ()
        for part in name.split(':'):
            if part in environ:
                item = environ[part]
                if type(item) == str:
                    content = item
                else:
                    environ = item
        if show_admin_content and not self._has_visible_content(content):
            content += name

        # Add the content to the page in response to the hook call.
        hook_div = safe_dom.Element('div', className='gcb-html-hook',
                                    id=re.sub('[^a-zA-Z-]', '-', name))
        hook_div.add_child(tags.html_to_safe_dom(content, self))

        # Mark up content to enable edit controls
        if show_admin_content:
            hook_div.add_attribute(onclick='gcb_edit_hook_point("%s")' % name)
            hook_div.add_attribute(className='gcb-html-hook-edit')
        return jinja2.Markup(hook_div.sanitized)


class ApplicationHandler(webapp2.RequestHandler):
    """A handler that is aware of the application context."""

    RIGHT_LINKS = []
    EXTRA_GLOBAL_CSS_URLS = []
    EXTRA_GLOBAL_JS_URLS = []

    @classmethod
    def is_absolute(cls, url):
        return bool(urlparse.urlparse(url).scheme)

    @classmethod
    def get_base_href(cls, handler):
        """Computes current course <base> href."""
        base = handler.app_context.get_slug()
        if not base.endswith('/'):
            base = '%s/' % base

        # For IE to work with the <base> tag, its href must be an absolute URL.
        if not cls.is_absolute(base):
            parts = urlparse.urlparse(handler.request.url)
            base = urlparse.urlunparse(
                (parts.scheme, parts.netloc, base, None, None, None))
        return base

    def render_template_to_html(self, template_values, template_file,
                                additional_dirs=None):
        courses.Course.set_current(self.get_course())
        models.MemcacheManager.begin_readonly()
        try:
            template = self.get_template(template_file, additional_dirs)
            return jinja2.utils.Markup(
                template.render(template_values, autoescape=True))
        finally:
            models.MemcacheManager.end_readonly()
            courses.Course.clear_current()

    def get_template(self, template_file, additional_dirs=None, prefs=None):
        raise NotImplementedError()

    @classmethod
    def canonicalize_url_for(cls, app_context, location):
        """Adds the current namespace URL prefix to the relative 'location'."""
        is_relative = (
            not cls.is_absolute(location) and
            not location.startswith(app_context.get_slug()))
        has_slug = (
            app_context.get_slug() and app_context.get_slug() != '/')
        if is_relative and has_slug:
            location = '%s%s' % (app_context.get_slug(), location)
        return location

    def canonicalize_url(self, location):
        if hasattr(self, 'app_context'):
            return self.canonicalize_url_for(self.app_context, location)
        else:
            return location

    def redirect(self, location, normalize=True):
        if normalize:
            location = self.canonicalize_url(location)
        super(ApplicationHandler, self).redirect(location)


class CourseHandler(ApplicationHandler):
    """Base handler that is aware of the current course."""

    def __init__(self, *args, **kwargs):
        super(CourseHandler, self).__init__(*args, **kwargs)
        self.course = None
        self.template_value = {}

    def get_user(self):
        """Get the current user."""
        return users.get_current_user()

    def get_student(self):
        """Get the current student."""
        user = self.get_user()
        if user is None:
            return None
        return Student.get_by_email(user.email())

    def _pick_first_valid_locale_from_list(self, desired_locales):
        available_locales = self.app_context.get_allowed_locales()
        for lang in desired_locales:
            for available_locale in available_locales:
                if lang.lower() == available_locale.lower():
                    return lang
        return None

    def get_locale_for(self, request, app_context, student=None, prefs=None):
        """Returns a locale that should be used by this request."""

        if self.get_user():
            # check if student has any locale labels assigned
            if student is None:
                student = self.get_student()
            if student and student.is_enrolled and not student.is_transient:
                student_label_ids = student.get_labels_of_type(
                    models.LabelDTO.LABEL_TYPE_LOCALE)
                if student_label_ids:
                    all_labels = models.LabelDAO.get_all_of_type(
                        models.LabelDTO.LABEL_TYPE_LOCALE)
                    student_locales = []
                    for label in all_labels:
                        if label.type != models.LabelDTO.LABEL_TYPE_LOCALE:
                            continue
                        if label.id in student_label_ids:
                            student_locales.append(label.title)
                    locale = self._pick_first_valid_locale_from_list(
                        student_locales)
                    if locale:
                        return locale

            # check if user preferences have been set
            if prefs is None:
                prefs = models.StudentPreferencesDAO.load_or_create()
            if prefs is not None and prefs.locale is not None:
                return prefs.locale

        locale_cookie = self.request.cookies.get(GUEST_LOCALE_COOKIE)
        if locale_cookie and (
                locale_cookie in self.app_context.get_allowed_locales()):
            return locale_cookie

        # check if accept language has been set
        accept_langs = request.headers.get('Accept-Language')
        locale = self._pick_first_valid_locale_from_list(
            [lang for lang, _ in locales.parse_accept_language(accept_langs)])
        if locale:
            return locale

        return app_context.default_locale

    def get_course(self):
        """Get current course."""
        if not self.course:
            self.course = Course(self)
        return self.course

    def get_track_matching_student(self, student):
        """Gets units whose labels match those on the student."""
        return self.get_course().get_track_matching_student(student)

    def get_progress_tracker(self):
        """Gets the progress tracker for the course."""
        return self.get_course().get_progress_tracker()

    def find_unit_by_id(self, unit_id):
        """Gets a unit with a specific id or fails with an exception."""
        return self.get_course().find_unit_by_id(unit_id)

    def get_units(self):
        """Gets all units in the course."""
        return self.get_course().get_units()

    def get_lessons(self, unit_id):
        """Gets all lessons (in order) in the specific course unit."""
        return self.get_course().get_lessons(unit_id)

    @classmethod
    def _cache_debug_info(cls, cache):
        items = []
        for key, entry in cache.items.iteritems():
            updated_on = None
            if entry:
                updated_on = entry.updated_on()
            items.append('entry: %s, %s' % (key, updated_on))
        return items

    @classmethod
    def debug_info(cls):
        """Generates a debug info for this request."""

        # we only want to run import if this method is called; most of the
        # it is not; we also have circular import dependencies if we were to
        # put them at the top...
        # pylint: disable-msg=g-import-not-at-top
        from models import vfs
        from modules.i18n_dashboard import i18n_dashboard
        vfs_items = cls._cache_debug_info(
            vfs.ProcessScopedVfsCache.instance().cache)
        rb_items = cls._cache_debug_info(
            i18n_dashboard.ProcessScopedResourceBundleCache.instance().cache)
        return ''.join([
              '\nDebug Info: %s' % datetime.datetime.utcnow(),
              '\n\nServer Environment Variables: %s' % '\n'.join([
                  'item: %s, %s'% (key, value)
                  for key, value in os.environ.iteritems()]),
              '\n\nVfsCacheKeys:\n%s' % '\n'.join(vfs_items),
              '\n\nResourceBundlesCache:\n%s' % '\n'.join(rb_items),
              ])

    def init_template_values(self, environ, prefs=None):
        """Initializes template variables with common values."""
        self.template_value[COURSE_INFO_KEY] = environ
        self.template_value[
            'page_locale'] = self.app_context.get_current_locale()
        self.template_value['html_hooks'] = HtmlHooks(
            self.get_course(), prefs=prefs)
        self.template_value['is_course_admin'] = Roles.is_course_admin(
            self.app_context)
        self.template_value['can_see_drafts'] = (
            courses_module.courses.can_see_drafts(self.app_context))
        self.template_value[
            'is_read_write_course'] = self.app_context.fs.is_read_write()
        self.template_value['is_super_admin'] = Roles.is_super_admin()
        self.template_value[COURSE_BASE_KEY] = self.get_base_href(self)
        self.template_value['right_links'] = (
            [('/admin', 'Admin')] if Roles.is_super_admin() else [])
        for func in self.RIGHT_LINKS:
            self.template_value['right_links'].extend(func(self.app_context))

        if not prefs:
            prefs = models.StudentPreferencesDAO.load_or_create()
        self.template_value['student_preferences'] = prefs

        if (Roles.is_course_admin(self.app_context) and
            not appengine_config.PRODUCTION_MODE and
            prefs and prefs.show_jinja_context):
                @jinja2.contextfunction
                def get_context(context):
                    return context
                self.template_value['context'] = get_context

        if CAN_PUT_DEBUG_INFO_INTO_PAGES.value:
            self.template_value['debug_info'] = self.debug_info()

        self.template_value[
            'extra_global_css_urls'] = self.EXTRA_GLOBAL_CSS_URLS
        self.template_value[
            'extra_global_js_urls'] = self.EXTRA_GLOBAL_JS_URLS

        # Common template information for the locale picker (only shown for
        # user in session)
        can_student_change_locale = (
            self.get_course().get_course_setting('can_student_change_locale')
            or self.get_course().app_context.can_pick_all_locales())
        if can_student_change_locale:
            self.template_value['available_locales'] = [
                {
                    'name': locales.get_locale_display_name(loc),
                    'value': loc
                } for loc in self.app_context.get_allowed_locales()]
            self.template_value['locale_xsrf_token'] = (
                XsrfTokenManager.create_xsrf_token(
                    StudentLocaleRESTHandler.XSRF_TOKEN_NAME))
            self.template_value['selected_locale'] = self.get_locale_for(
                self.request, self.app_context, prefs=prefs)

    def get_template(self, template_file, additional_dirs=None, prefs=None):
        """Computes location of template files for the current namespace."""

        _p = self.app_context.get_environ()
        self.init_template_values(_p, prefs=prefs)
        template_environ = self.app_context.get_template_environ(
            self.app_context.get_current_locale(), additional_dirs)
        template_environ.filters[
            'gcb_tags'] = jinja_utils.get_gcb_tags_filter(self)
        template_environ.globals.update({
            'display_unit_title': (
                lambda unit: display_unit_title(unit, _p)),
            'display_short_unit_title': (
                lambda unit: display_short_unit_title(unit, _p)),
            'display_lesson_title': (
                lambda unit, lesson: display_lesson_title(unit, lesson, _p))})

        return template_environ.get_template(template_file)


class BaseHandler(CourseHandler):
    """Base handler."""

    def __init__(self, *args, **kwargs):
        super(BaseHandler, self).__init__(*args, **kwargs)
        self._old_locale = None

    def before_method(self, verb, path):
        """Modify global locale value for the duration of this handler."""
        self._old_locale = self.app_context.get_current_locale()
        new_locale = self.get_locale_for(self.request, self.app_context)
        self.app_context.set_current_locale(new_locale)

    def after_method(self, verb, path):
        """Restore original global locale value."""
        self.app_context.set_current_locale(self._old_locale)

    def personalize_page_and_get_user(self):
        """If the user exists, add personalized fields to the navbar."""
        user = self.get_user()
        PageInitializerService.get().initialize(self.template_value)

        if hasattr(self, 'app_context'):
            self.template_value['can_register'] = self.app_context.get_environ(
                )['reg_form']['can_register']

        if user:
            email = user.email()
            self.template_value['email_no_domain_name'] = (
                email[:email.find('@')] if '@' in email else email)
            self.template_value['email'] = email
            self.template_value['logoutUrl'] = (
                users.create_logout_url(self.request.uri))
            self.template_value['transient_student'] = False

            # configure page events
            self.template_value['record_tag_events'] = (
                CAN_PERSIST_TAG_EVENTS.value)
            self.template_value['record_page_events'] = (
                CAN_PERSIST_PAGE_EVENTS.value)
            self.template_value['record_events'] = (
                CAN_PERSIST_ACTIVITY_EVENTS.value)
            self.template_value['event_xsrf_token'] = (
                XsrfTokenManager.create_xsrf_token('event-post'))
        else:
            self.template_value['loginUrl'] = users.create_login_url(
                self.request.uri)
            self.template_value['transient_student'] = True
            return None

        return user

    def personalize_page_and_get_enrolled(
        self, supports_transient_student=False):
        """If the user is enrolled, add personalized fields to the navbar."""
        user = self.personalize_page_and_get_user()
        if user is None:
            student = TRANSIENT_STUDENT
        else:
            student = Student.get_enrolled_student_by_email(user.email())
            if not student:
                self.template_value['transient_student'] = True
                student = TRANSIENT_STUDENT

        if student.is_transient:
            if supports_transient_student and (
                    self.app_context.get_environ()['course']['browsable']):
                return TRANSIENT_STUDENT
            elif user is None:
                self.redirect(
                    users.create_login_url(self.request.uri), normalize=False
                )
                return None
            else:
                self.redirect('/preview')
                return None

        # Patch Student models which (for legacy reasons) do not have a user_id
        # attribute set.
        if not student.user_id:
            student.user_id = user.user_id()
            student.put()

        return student

    def assert_xsrf_token_or_fail(self, request, action):
        """Asserts the current request has proper XSRF token or fails."""
        token = request.get('xsrf_token')
        if not token or not XsrfTokenManager.is_xsrf_token_valid(token, action):
            self.error(403)
            return False
        return True

    @appengine_config.timeandlog('BaseHandler.render')
    def render(self, template_file):
        """Renders a template."""
        prefs = models.StudentPreferencesDAO.load_or_create()

        courses.Course.set_current(self.get_course())
        models.MemcacheManager.begin_readonly()
        try:
            template = self.get_template(template_file, prefs=prefs)
            self.response.out.write(template.render(self.template_value))
        finally:
            models.MemcacheManager.end_readonly()
            courses.Course.clear_current()

        # If the page displayed successfully, save the location for registered
        # students so future visits to the course's base URL sends the student
        # to the most-recently-visited page.
        # TODO(psimakov): method called render() must not have mutations
        user = self.get_user()
        if user:
            student = models.Student.get_enrolled_student_by_email(
                user.email())
            if student:
                prefs.last_location = self.request.path_qs
                models.StudentPreferencesDAO.save(prefs)

    def get_redirect_location(self, student):
        if (not student.is_transient and
            (self.request.path == self.app_context.get_slug() or
             self.request.path == self.app_context.get_slug() + '/' or
             self.request.get('use_last_location'))):  # happens on '/' page
            prefs = models.StudentPreferencesDAO.load_or_create()
            # Belt-and-suspenders: prevent infinite self-redirects
            if (prefs.last_location and
                prefs.last_location != self.request.path_qs):
                return prefs.last_location
        return None


class BaseRESTHandler(CourseHandler):
    """Base REST handler."""

    def __init__(self, *args, **kwargs):
        super(BaseRESTHandler, self).__init__(*args, **kwargs)

    def assert_xsrf_token_or_fail(self, token_dict, action, args_dict):
        """Asserts that current request has proper XSRF token or fails."""
        token = token_dict.get('xsrf_token')
        if not token or not XsrfTokenManager.is_xsrf_token_valid(token, action):
            transforms.send_json_response(
                self, 403,
                'Bad XSRF token. Please reload the page and try again',
                args_dict)
            return False
        return True

    def validation_error(self, message, key=None):
        """Deliver a validation message."""
        if key:
            transforms.send_json_response(
                self, 412, message, payload_dict={'key': key})
        else:
            transforms.send_json_response(self, 412, message)


class PreviewHandler(BaseHandler):
    """Handler for viewing course preview."""

    def get(self):
        """Handles GET requests."""
        user = self.personalize_page_and_get_user()
        if user is None:
            student = TRANSIENT_STUDENT
        else:
            student = Student.get_enrolled_student_by_email(user.email())
            if not student:
                student = TRANSIENT_STUDENT

        # If the course is browsable, or the student is logged in and
        # registered, redirect to the main course page.
        if ((student and not student.is_transient) or
            self.app_context.get_environ()['course']['browsable']):
            self.redirect('/course')
            return

        self.template_value['transient_student'] = True
        self.template_value['can_register'] = self.app_context.get_environ(
            )['reg_form']['can_register']
        self.template_value['navbar'] = {'course': True}
        self.template_value['units'] = self.get_units()
        self.template_value['show_registration_page'] = True

        course = self.app_context.get_environ()['course']
        self.template_value['video_exists'] = bool(
            'main_video' in course and
            'url' in course['main_video'] and
            course['main_video']['url'])
        self.template_value['image_exists'] = bool(
            'main_image' in course and
            'url' in course['main_image'] and
            course['main_image']['url'])

        if user:
            profile = StudentProfileDAO.get_profile_by_user_id(user.user_id())
            additional_registration_fields = self.app_context.get_environ(
                )['reg_form']['additional_registration_fields']
            if profile is not None and not additional_registration_fields:
                self.template_value['show_registration_page'] = False
                self.template_value['register_xsrf_token'] = (
                    XsrfTokenManager.create_xsrf_token('register-post'))
        self.render('preview.html')


class RegisterHandler(BaseHandler):
    """Handler for course registration."""

    def get(self):
        """Handles GET request."""
        user = self.personalize_page_and_get_user()
        if not user:
            self.redirect(
                users.create_login_url(self.request.uri), normalize=False)
            return

        student = Student.get_enrolled_student_by_email(user.email())
        if student:
            self.redirect('/course')
            return

        can_register = self.app_context.get_environ(
            )['reg_form']['can_register']
        if not can_register:
            self.redirect('/course#registration_closed')
            return

        # pre-fill nick name from the profile if available
        self.template_value['current_name'] = ''
        profile = StudentProfileDAO.get_profile_by_user_id(user.user_id())
        if profile and profile.nick_name:
            self.template_value['current_name'] = profile.nick_name

        self.template_value['navbar'] = {}
        self.template_value['transient_student'] = True
        self.template_value['register_xsrf_token'] = (
            XsrfTokenManager.create_xsrf_token('register-post'))

        self.render('register.html')

    def post(self):
        """Handles POST requests."""
        user = self.personalize_page_and_get_user()
        if not user:
            self.redirect(
                users.create_login_url(self.request.uri), normalize=False)
            return

        if not self.assert_xsrf_token_or_fail(self.request, 'register-post'):
            return

        can_register = self.app_context.get_environ(
            )['reg_form']['can_register']
        if not can_register:
            self.redirect('/course#registration_closed')
            return

        if 'name_from_profile' in self.request.POST.keys():
            profile = StudentProfileDAO.get_profile_by_user_id(user.user_id())
            name = profile.nick_name
        else:
            name = self.request.get('form01')

        Student.add_new_student_for_current_user(
            name, transforms.dumps(self.request.POST.items()), self,
            labels=self.request.get('labels'))

        # Render registration confirmation page
        self.redirect('/course#registration_confirmation')


class ForumHandler(BaseHandler):
    """Handler for forum page."""

    def get(self):
        """Handles GET requests."""
        student = self.personalize_page_and_get_enrolled(
            supports_transient_student=True)
        if not student:
            return

        self.template_value['navbar'] = {'forum': True}
        self.render('forum.html')


class StudentProfileHandler(BaseHandler):
    """Handles the click to 'Progress' link in the nav bar."""

    # A list of functions which will provide extra rows in the Student Progress
    # table. Each function will be passed the current handler, student,  and
    # course object and should return a pair of strings; the first being the
    # title of the data and the second the value to display.
    EXTRA_STUDENT_DATA_PROVIDERS = []

    def get(self):
        """Handles GET requests."""
        student = self.personalize_page_and_get_enrolled()
        if not student:
            return

        track_labels = models.LabelDAO.get_all_of_type(
            models.LabelDTO.LABEL_TYPE_COURSE_TRACK)

        course = self.get_course()
        units = []
        for unit in course.get_units():
            # Don't show assessments that are part of units.
            if course.get_parent_unit(unit.unit_id):
                continue
            units.append({
                'unit_id': unit.unit_id,
                'title': unit.title,
                'labels': list(course.get_unit_track_labels(unit)),
                })

        name = student.name
        profile = student.profile
        if profile:
            name = profile.nick_name
        student_labels = student.get_labels_of_type(
            models.LabelDTO.LABEL_TYPE_COURSE_TRACK)
        self.template_value['navbar'] = {'progress': True}
        self.template_value['student'] = student
        self.template_value['student_name'] = name
        self.template_value['date_enrolled'] = student.enrolled_on.strftime(
            HUMAN_READABLE_DATE_FORMAT)
        self.template_value['score_list'] = course.get_all_scores(student)
        self.template_value['overall_score'] = course.get_overall_score(student)
        self.template_value['student_edit_xsrf_token'] = (
            XsrfTokenManager.create_xsrf_token('student-edit'))
        self.template_value['can_edit_name'] = (
            not models.CAN_SHARE_STUDENT_PROFILE.value)
        self.template_value['track_labels'] = track_labels
        self.template_value['student_labels'] = student_labels
        self.template_value['units'] = units
        self.template_value['track_env'] = transforms.dumps({
            'label_ids': [label.id for label in track_labels],
            'units': units
            })

        # Append any extra data which is provided by modules
        extra_student_data = []
        for data_provider in self.EXTRA_STUDENT_DATA_PROVIDERS:
            extra_student_data.append(data_provider(self, student, course))
        self.template_value['extra_student_data'] = extra_student_data

        self.render('student_profile.html')


class StudentEditStudentHandler(BaseHandler):
    """Handles edits to student records by students."""

    def post(self):
        """Handles POST requests."""
        student = self.personalize_page_and_get_enrolled()
        if not student:
            return

        if not self.assert_xsrf_token_or_fail(self.request, 'student-edit'):
            return

        Student.rename_current(self.request.get('name'))

        self.redirect('/student/home')


class StudentSetTracksHandler(BaseHandler):
    """Handles submission of student tracks selections."""

    def post(self):
        student = self.personalize_page_and_get_enrolled()
        if not student:
            return
        if not self.assert_xsrf_token_or_fail(self.request, 'student-edit'):
            return

        all_track_label_ids = models.LabelDAO.get_set_of_ids_of_type(
            models.LabelDTO.LABEL_TYPE_COURSE_TRACK)
        new_track_label_ids = set(
            [int(label_id)
             for label_id in self.request.get_all('labels')
             if label_id and int(label_id) in all_track_label_ids])
        student_label_ids = set(
            [int(label_id)
             for label_id in common_utils.text_to_list(student.labels)
             if label_id])

        # Remove all existing track (and only track) labels from student,
        # then merge in selected set from form.
        student_label_ids = student_label_ids.difference(all_track_label_ids)
        student_label_ids = student_label_ids.union(new_track_label_ids)
        models.Student.set_labels_for_current(
            common_utils.list_to_text(list(student_label_ids)))

        self.redirect('/student/home')


class StudentUnenrollHandler(BaseHandler):
    """Handler for students to unenroll themselves."""

    def get(self):
        """Handles GET requests."""
        student = self.personalize_page_and_get_enrolled()
        if not student:
            return

        self.template_value['student'] = student
        self.template_value['navbar'] = {}
        self.template_value['student_unenroll_xsrf_token'] = (
            XsrfTokenManager.create_xsrf_token('student-unenroll'))
        self.render('unenroll_confirmation_check.html')

    def post(self):
        """Handles POST requests."""
        student = self.personalize_page_and_get_enrolled()
        if not student:
            return

        if not self.assert_xsrf_token_or_fail(self.request, 'student-unenroll'):
            return

        Student.set_enrollment_status_for_current(False)

        self.template_value['navbar'] = {}
        self.template_value['transient_student'] = True
        self.render('unenroll_confirmation.html')


class StudentLocaleRESTHandler(BaseRESTHandler):
    """REST handler to manage student setting their preferred locale."""

    XSRF_TOKEN_NAME = 'locales'

    def post(self):
        request = transforms.loads(self.request.get('request'))
        if not self.assert_xsrf_token_or_fail(
                request, self.XSRF_TOKEN_NAME, {}):
            return

        selected = request['payload']['selected']
        if selected not in self.app_context.get_allowed_locales():
            transforms.send_json_response(self, 401, 'Bad locale')
            return

        prefs = models.StudentPreferencesDAO.load_or_create()
        if prefs:
            # Store locale in StudentPreferences for logged-in users
            prefs.locale = selected
            models.StudentPreferencesDAO.save(prefs)
        else:
            # Store locale in cookie for out-of-session users
            self.response.set_cookie(
                GUEST_LOCALE_COOKIE, selected,
                max_age=GUEST_LOCALE_COOKIE_MAX_AGE_SEC)

        transforms.send_json_response(self, 200, 'OK')
