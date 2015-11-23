# Copyright 2014 Google Inc. All Rights Reserved.
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


"""Enables hosting of multiple courses in one application instance.

We used to allow hosting of only one course in one Google App Engine instance.
Now we allow hosting of many courses simultaneously. To configure multiple
courses one must set an environment variable in app.yaml file, for example:

  ...
  env_variables:
    GCB_COURSES_CONFIG: 'course:/coursea:/courses/a, course:/courseb:/courses/b'
  ...

This variable holds a ',' or newline separated list of course entries. Each
course entry has four ':' separated parts: the word 'course', the URL prefix,
and the file system location for the site files. If the third part is empty,
the course assets are stored in a datastore instead of the file system. The
fourth, optional part, is the name of the course namespace.

The URL prefix specifies, how will the course URL appear in the browser. In the
example above, the courses will be mapped to http://www.example.com[/coursea]
and http://www.example.com[/courseb].

The file system location of the files specifies, which files to serve for the
course. For each course we expect three sub-folders: 'assets', 'views', and
'data'. The 'data' folder must contain the CSV files that define the course
layout, the 'assets' and 'views' should contain the course specific files and
jinja2 templates respectively. In the example above, the course files are
expected to be placed into folders '/courses/a' and '/courses/b' of your Google
App Engine installation respectively. If this value is absent a datastore is
used to store course assets, not the file system.

By default Course Builder handles static '/assets' files using a custom
handler. You may choose to handle '/assets' files of your course as 'static'
files using Google App Engine handler. You can do so by creating a new static
file handler entry in your app.yaml and placing it before our main course
handler.

If you have an existing course developed using Course Builder and do NOT want
to host multiple courses, there is nothing for you to do. A following default
rule is silently created for you:

  ...
  env_variables:
    GCB_COURSES_CONFIG: 'course:/:/'
  ...

It sets the '/' as the base URL for the course, uses root folder of your Google
App Engine installation to look for course /assets/..., /data/..., and
/views/... and uses blank datastore and memcache namespace. All in all,
everything behaves just as it did in the prior version of Course Builder when
only one course was supported.

If you have existing course developed using Course Builder and DO want to start
hosting multiple courses here are the steps. First, define the courses
configuration environment variable as described above. Second, copy existing
'assets', 'data' and 'views' folders of your course into the new location, for
example '/courses/mycourse'.

If you have an existing course built on a previous version of Course Builder
and you now decided to use new URL prefix, which is not '/', you will need
to update your old course html template and JavaScript files. You typically
would have to make two modifications. First, replace all absolute URLs with
the relative URLs. For example, if you had <a href='/forum'>..</a>, you will
need to replace it with <a href='forum'>..</a>. Second, you need to add <base>
tag at the top of you course 'base.html' and 'base_registration.html' files,
like this:

  ...
  <head>
    <base href="{{ gcb_course_base }}" />
  ...

Current Course Builder release already has all these modifications.

Note, that each 'course' runs in a separate Google App Engine namespace. The
name of the namespace is derived from the course files location. In the example
above, the course files are stored in the folder '/courses/a', which be mapped
to the namespace name 'gcb-courses-a'. The namespaces can't contain '/', so we
replace them with '-' and prefix the namespace with the project abbreviation
'gcb'. Remember these namespace names, you will need to use them if/when
accessing server administration panel, viewing objects in the datastore, etc.
Don't move the files to another folder after your course starts as a new folder
name will create a new namespace name and old data will no longer be used. You
are free to rename the course URL prefix at any time. Once again, if you are
not hosting multiple courses, your course will run in a default namespace
(None).

Good luck!
"""

import logging
import mimetypes
import os
import posixpath
import re
import threading
import traceback
import urlparse
import zipfile

import utils
import webapp2
from webapp2_extras import i18n

import appengine_config
from common import caching
from common import users
from common import utils as common_utils
from models import messages
from models import models
from models import custom_modules
from models import transforms
from models.config import ConfigProperty
from models.config import ConfigPropertyEntity
from models.config import Registry
from models.counters import PerfCounter
from models.courses import Course
from models.roles import Roles
from models.vfs import AbstractFileSystem
from models.vfs import DatastoreBackedFileSystem
from models.vfs import LocalReadOnlyFileSystem

from google.appengine.api import namespace_manager
from google.appengine.ext import db
from google.appengine.ext.db import metadata
from google.appengine.ext import zipserve


# base name for all course namespaces
GCB_BASE_COURSE_NAMESPACE = 'gcb-course'

# these folder and file names are reserved
GCB_ASSETS_FOLDER_NAME = os.path.normpath('/assets/')
GCB_VIEWS_FOLDER_NAME = os.path.normpath('/views/')
GCB_DATA_FOLDER_NAME = os.path.normpath('/data/')
GCB_CONFIG_FILENAME = os.path.normpath('/course.yaml')

# modules do have files that must be inheritable, like oeditor.html
GCB_MODULES_FOLDER_NAME = os.path.normpath('/modules/')

# Files in these folders are inheritable between file systems.
GCB_INHERITABLE_FOLDER_NAMES = [
    os.path.join(GCB_ASSETS_FOLDER_NAME, 'css/'),
    os.path.join(GCB_ASSETS_FOLDER_NAME, 'img/'),
    os.path.join(GCB_ASSETS_FOLDER_NAME, 'lib/'),
    os.path.join(GCB_ASSETS_FOLDER_NAME, 'html/'),
    GCB_VIEWS_FOLDER_NAME,
    GCB_MODULES_FOLDER_NAME]

# supported site types
SITE_TYPE_COURSE = 'course'

# default 'Cache-Control' HTTP header for static files
DEFAULT_CACHE_CONTROL_MAX_AGE = 600
DEFAULT_CACHE_CONTROL_PUBLIC = 'public'

# default HTTP headers for dynamic responses
DEFAULT_EXPIRY_DATE = 'Mon, 01 Jan 1990 00:00:00 GMT'
DEFAULT_PRAGMA = 'no-cache'

# thread local storage for current request PATH_INFO
PATH_INFO_THREAD_LOCAL = threading.local()

# performance counters
STATIC_HANDLER_COUNT = PerfCounter(
    'gcb-sites-handler-static',
    'A number of times request was served via static handler.')
DYNAMIC_HANDLER_COUNT = PerfCounter(
    'gcb-sites-handler-dynamic',
    'A number of times request was served via dynamic handler.')
ZIP_HANDLER_COUNT = PerfCounter(
    'gcb-sites-handler-zip',
    'A number of times request was served via zip handler.')
NO_HANDLER_COUNT = PerfCounter(
    'gcb-sites-handler-none',
    'A number of times request was not matched to any handler.')

HTTP_BYTES_IN = PerfCounter(
    'gcb-sites-bytes-in',
    'A number of bytes received from clients by the handler.')
HTTP_BYTES_OUT = PerfCounter(
    'gcb-sites-bytes-out',
    'A number of bytes sent out from the handler to clients.')

HTTP_STATUS_200 = PerfCounter(
    'gcb-sites-http-20x',
    'A number of times HTTP status code 20x was returned.')
HTTP_STATUS_300 = PerfCounter(
    'gcb-sites-http-30x',
    'A number of times HTTP status code 30x was returned.')
HTTP_STATUS_400 = PerfCounter(
    'gcb-sites-http-40x',
    'A number of times HTTP status code 40x was returned.')
HTTP_STATUS_500 = PerfCounter(
    'gcb-sites-http-50x',
    'A number of times HTTP status code 50x was returned.')
COUNTER_BY_HTTP_CODE = {
    200: HTTP_STATUS_200, 300: HTTP_STATUS_300, 400: HTTP_STATUS_400,
    500: HTTP_STATUS_500}

_NAMESPACE_MAX_LENGTH = 100

# name of the response header used to transmit handler class name
GCB_HANDLER_CLASS_HEADER_NAME = 'gcb-handler-class'


class BaseZipHandler(zipserve.ZipHandler, utils.StarRouteHandlerMixin):
    """Base class for zip handlers."""
    pass


def count_stats(handler):
    """Records statistics about the request and the response."""
    try:
        # Record request bytes in.
        if handler.request and handler.request.content_length:
            HTTP_BYTES_IN.inc(handler.request.content_length)

        # Record response HTTP status code.
        if handler.response and handler.response.status_int:
            rounded_status_code = (handler.response.status_int / 100) * 100
            counter = COUNTER_BY_HTTP_CODE[rounded_status_code]
            if not counter:
                logging.error(
                    'Unknown HTTP status code: %s.',
                    handler.response.status_code)
            else:
                counter.inc()

        # Record response bytes out.
        if handler.response and handler.response.content_length:
            HTTP_BYTES_OUT.inc(handler.response.content_length)
    except Exception as e:  # pylint: disable=broad-except
        logging.error(
            'Failed to count_stats(): %s\n%s', e, traceback.format_exc())


def _validate_appcontext_list(contexts, strict=False):
    """Validates a list of application contexts."""

    # Check rule order is enforced. If we allowed any order and '/a' was before
    # '/aa', the '/aa' would never match.
    for i in range(len(contexts)):
        for j in range(i + 1, len(contexts)):
            above = contexts[i]
            below = contexts[j]
            if below.get_slug().startswith(above.get_slug()):
                raise Exception(
                    'Please reorder course entries to have '
                    '\'%s\' before \'%s\'.' % (
                        below.get_slug(), above.get_slug()))

    # Make sure '/' is mapped.
    if strict:
        is_root_mapped = False
        for context in contexts:
            if context.slug == '/':
                is_root_mapped = True
                break
        if not is_root_mapped:
            raise Exception(
                'Please add an entry with \'/\' as course URL prefix.')


def path_join(base, path):
    """Joins 'base' and 'path' ('path' is interpreted as a relative path).

    This method is like os.path.join(), but 'path' is interpreted relatively.
    E.g., os.path.join('/a/b', '/c') yields '/c', but this function yields
    '/a/b/c'.

    Args:
        base: The base path.
        path: The path to append to base; this is treated as a relative path.

    Returns:
        The path obtaining by appending 'path' to 'base'.
    """
    if os.path.isabs(path):
        # Remove drive letter (if we are on Windows).
        unused_drive, path_no_drive = os.path.splitdrive(path)
        # Remove leading path separator.
        path = path_no_drive[1:]
    return AbstractFileSystem.normpath(os.path.join(base, path))


def abspath(home_folder, filename):
    """Creates an absolute URL for a filename in a home folder."""
    return path_join(appengine_config.BUNDLE_ROOT,
                     path_join(home_folder, filename))


def unprefix(path, prefix):
    """Remove the prefix from path. Append '/' if an empty string results."""
    if not path.startswith(prefix):
        raise Exception('Not prefixed.')

    if prefix != '/':
        path = path[len(prefix):]
    if not path:
        path = '/'
    return path


def _add_handler_to_headers(handler):
    if users.is_current_user_admin() or not appengine_config.PRODUCTION_MODE:
        handler.response.headers[
            GCB_HANDLER_CLASS_HEADER_NAME] = handler.__class__.__name__


def set_static_resource_cache_control(handler):
    """Properly sets Cache-Control for a WebOb/webapp2 response."""
    _add_handler_to_headers(handler)
    handler.response.cache_control.no_cache = None
    handler.response.cache_control.public = DEFAULT_CACHE_CONTROL_PUBLIC
    handler.response.cache_control.max_age = DEFAULT_CACHE_CONTROL_MAX_AGE


def set_default_response_headers(handler):
    """Sets the default headers for outgoing responses."""
    _add_handler_to_headers(handler)

    # This conditional is needed for the unit tests to pass, since their
    # handlers do not have a response attribute.
    if handler.response:
        # Only set the headers for dynamic responses. This happens precisely
        # when the handler is an instance of utils.ApplicationHandler and not
        # AssetsHandler
        if isinstance(handler, AssetHandler):
            return
        if not isinstance(handler, utils.ApplicationHandler):
            return

        handler.response.cache_control.no_cache = True
        handler.response.cache_control.must_revalidate = True
        handler.response.expires = DEFAULT_EXPIRY_DATE
        handler.response.pragma = DEFAULT_PRAGMA


def make_zip_handler(zipfilename):
    """Creates a handler that serves files from a zip file."""

    class CustomZipHandler(BaseZipHandler):
        """Custom ZipHandler that properly controls caching."""

        def get(self, *args):
            """Handles GET request."""

            path = None

            # try to use path passed explicitly
            if args and len(args) >= 1:
                path = args[0]

            # use path_translated if no name was passed explicitly
            if not path:
                path = self.path_translated

                # we need to remove leading slash and all filenames inside zip
                # file must be relative
                if path and path.startswith('/') and len(path) > 1:
                    path = path[1:]

            if not path:
                self.error(404)
                return

            ZIP_HANDLER_COUNT.inc()
            self.ServeFromZipFile(zipfilename, path)
            count_stats(self)

        def SetCachingHeaders(self):  # pylint: disable=C6409
            """Properly controls caching."""
            set_static_resource_cache_control(self)

    return CustomZipHandler


class CssComboZipHandler(BaseZipHandler):
    """A handler which combines a files served from a zip file.

    The paths for the files within the zip file are presented
    as query parameters.
    """

    zipfile_cache = {}

    def get(self):
        raise NotImplementedError()

    def SetCachingHeaders(self):  # pylint: disable=C6409
        """Properly controls caching."""
        set_static_resource_cache_control(self)

    def serve_from_zip_file(self, zipfilename, static_file_handler):
        """Assemble the download by reading file from zip file."""
        zipfile_object = self.zipfile_cache.get(zipfilename)
        if zipfile_object is None:
            try:
                zipfile_object = zipfile.ZipFile(zipfilename)
            except (IOError, RuntimeError, zipfile.BadZipfile), err:
                # If the zipfile can't be opened, that's probably a
                # configuration error in the app, so it's logged as an error.
                logging.error('Can\'t open zipfile %s: %s', zipfilename, err)
                zipfile_object = ''  # Special value to cache negative results.
            self.zipfile_cache[zipfilename] = zipfile_object
        if not zipfile_object:
            self.error(404)
            return

        all_content_types = set()
        for name in self.request.GET:
            all_content_types.add(mimetypes.guess_type(name))
        if len(all_content_types) == 1:
            content_type = all_content_types.pop()[0]
        else:
            content_type = 'text/plain'
        self.response.headers['Content-Type'] = content_type

        self.SetCachingHeaders()

        for name in self.request.GET:
            try:
                content = zipfile_object.read(name)
                if content_type == 'text/css':
                    content = self.fix_css_paths(
                        name, content, static_file_handler)
                self.response.out.write(content)
            except (KeyError, RuntimeError), err:
                logging.error('Not found %s in %s', name, zipfilename)

    @classmethod
    def fix_css_paths(cls, path, css, static_file_handler):
        """Transform relative url() settings in CSS to absolute.

        This is necessary because a url setting, e.g., url(foo.png), is
        interpreted as relative to the location of the CSS file. However
        in the case of a bundled CSS file, obtained from a URL such as
            http://place.com/cb/combo?a/b/c/foo.css
        the browser would believe that the location for foo.png was
            http://place.com/cb/foo.png
        and not
            http://place.com/cb/a/b/c/foo.png
        Thus we transform the url from
            url(foo.png)
        to
            url(/static_file_service/a/b/c/foo.png)

        Args:
            path: the path to the CSS file within the ZIP file
            css: the content of the CSS file
            static_file_handler: the base handler to serve the referenced file

        Returns:
            The CSS with all relative URIs rewritten to absolute URIs.
        """
        base = static_file_handler + posixpath.split(path)[0] + '/'
        css = css.decode('utf-8')
        css = re.sub(
            r'url\(((?!(http:|https:|data:))\S+)\)', r'url(%s\1)' % base, css)
        return css


def make_css_combo_zip_handler(zipfilename, static_file_handler):

    class CustomCssComboZipHandler(CssComboZipHandler):

        def get(self):
            self.serve_from_zip_file(zipfilename, static_file_handler)

    return CustomCssComboZipHandler


class AssetHandler(utils.BaseHandler):
    """Handles serving of static resources located on the file system."""

    def __init__(self, app_context, filename):
        super(AssetHandler, self).__init__()
        self.app_context = app_context
        self.filename = filename

    def get_mime_type(self, filename, default='application/octet-stream'):
        guess = mimetypes.guess_type(filename)[0]
        if guess is None:
            return default
        return guess

    def _can_view(self, fs, stream):
        """Checks if current user can view stream."""
        public = not fs.is_draft(stream)
        return public or Roles.is_course_admin(self.app_context)

    def get(self):
        """Handles GET requests."""
        models.MemcacheManager.begin_readonly()
        try:
            stream = self.app_context.fs.open(self.filename)
            if not stream:
                self.error(404)
                return
            if not self._can_view(self.app_context.fs, stream):
                self.error(403)
                return
            set_static_resource_cache_control(self)
            self.response.headers['Content-Type'] = self.get_mime_type(
               self.filename)
            self.response.write(stream.read())
        finally:
            models.MemcacheManager.end_readonly()


class CourseIndex(object):
    """A list of all application contexts."""

    CAN_USE_INDEXED_GETTER = True

    @appengine_config.timeandlog('CourseIndex.init', duration_only=True)
    def __init__(self, all_contexts):
        self._all_contexts = all_contexts
        self._namespace2app_context = {}
        self._slug_parts2app_context = {}
        self._reindex()

    @classmethod
    def _slug_to_parts(cls, path):
        """Split slug into parts; slug parts are '/' separated."""
        if path in ['/', '']:
            return None
        _parts = path.split('/')
        assert _parts[0] == ''
        _parts.pop(0)
        return _parts

    @classmethod
    def _validate_and_split_path_to_parts(cls, path):
        """Split path into parts; path parts are '/' separated."""
        if path in ['/', '']:
            return True, None
        _parts = path.split('/')
        if _parts[0] != '':
            return False, None
        _parts.pop(0)
        return True, _parts

    def _update_slug_parts_index(self, app_context):
        """An index is a tree keyed by slug part."""
        _parts = self._slug_to_parts(app_context.get_slug())
        _parent = self._slug_parts2app_context
        while True:
            if not _parts:
                _parent[None] = app_context
                break
            _part = _parts.pop(0)
            _node = _parent.get(_part)
            if not _node:
                _node = {_part: {}}
                _parent.update(_node)
            _parent = _parent[_part]

    def _get_course_for_path_via_index(self, path):
        _result = None
        _valid, _parts = self._validate_and_split_path_to_parts(path)
        if not _valid:
            return None
        _parent = self._slug_parts2app_context
        while True:
            if not _parts:
                if _parent:
                    _result = _parent.get(None)
                break
            _part = _parts.pop(0)
            _node = _parent.get(_part)
            if not _node:
                if _parent:
                    _result = _parent.get(None)
                break
            _parent = _node
        if not _result:
            debug('No mapping for: %s' % path)
        return _result

    def _reindex(self):
        for app_context in self._all_contexts:
            self._update_slug_parts_index(app_context)
            self._namespace2app_context[app_context.get_namespace_name()] = (
                app_context)

    def get_all_courses(self):
        return self._all_contexts

    def _get_course_for_path_linear(self, path):
        for app_context in self._all_contexts:
            if (path == app_context.get_slug() or
                path.startswith('%s/' % app_context.get_slug()) or
                app_context.get_slug() == '/'):
                return app_context
        debug('No mapping for: %s' % path)
        return None

    def get_app_context_for_namespace(self, namespace):
        return self._namespace2app_context.get(namespace)

    def get_course_for_path(self, path):
        if CourseIndex.CAN_USE_INDEXED_GETTER:
            return self._get_course_for_path_via_index(path)
        else:
            return self._get_course_for_path_linear(path)


def debug(message):
    if ApplicationContext.DEBUG_INFO:
        logging.info(message)


class ApplicationContext(object):
    """An application context for a request/response."""

    # if True we auto-deploy filesystem-based default course
    AUTO_DEPLOY_DEFAULT_COURSE = False

    # enabled debug info output
    DEBUG_INFO = False

    # Here we store a map of a text definition of the courses to be parsed, and
    # a corresponding CourseIndex.
    _COURSE_INDEX_CACHE = {}

    @classmethod
    def get_namespace_name_for_request(cls):
        """Gets the name of the namespace to use for this request.

        (Examples of such namespaces are NDB and memcache.)

        Returns:
            The namespace for the current request, or None if no course matches
            the current request context path.
        """
        course = get_course_for_current_request()
        if course:
            return course.namespace
        return appengine_config.DEFAULT_NAMESPACE_NAME

    @classmethod
    def after_create(cls, instance):
        """Override this method to manipulate freshly created instance."""
        pass

    def __init__(self, site_type, slug, homefolder, namespace, fs, raw=None):
        """Creates new application context.

        Args:
            site_type: Specifies the type of context. Must be 'course' for now.
            slug: A common context path prefix for all URLs in the context.
            homefolder: A folder with the assets belonging to this context.
            namespace: A name of a datastore namespace for use by this context.
            fs: A file system object to be used for accessing homefolder.
            raw: A raw representation of this course rule (course:/:/).

        Returns:
            The new instance of namespace object.
        """
        self.type = site_type
        self.slug = slug
        self.homefolder = homefolder
        self.namespace = namespace
        self._fs = fs
        self._raw = raw
        self._cached_environ = None

        self._locale_threadlocal = threading.local()

        self.clear_per_request_cache()
        self.after_create(self)

    def __ne__(self, other):
        return not self.__eq__(other)

    def __eq__(self, other):
        """Two ApplicationContexts are the same if: same slug and namespace."""
        if not isinstance(other, ApplicationContext):
            return False

        app_context_1 = self
        app_context_2 = other
        if app_context_1 is app_context_2:
            return True
        if app_context_1 and app_context_2:
            same_ns = (
                app_context_1.get_namespace_name() ==
                app_context_2.get_namespace_name())
            same_slug = app_context_1.get_slug() == app_context_2.get_slug()
            return same_ns and same_slug
        return False

    @classmethod
    def clear_per_process_cache(cls):
        """Clears all objects from global in-process cache."""
        cls._COURSE_INDEX_CACHE = {}
        caching.ProcessScopedSingleton.clear_all()

    def clear_per_request_cache(self):
        """Clears all objects cached per request."""
        self._cached_environ = None
        caching.RequestScopedSingleton.clear_all()

    @ property
    def raw(self):
        return self._raw

    @ property
    def fs(self):
        return self._fs

    @property
    def now_available(self):
        return Course.is_course_available(self)

    @property
    def whitelist(self):
        return Course.get_whitelist(self)

    def set_current_locale(self, locale):
        old_locale = self.get_current_locale()
        if locale != old_locale:
            self._locale_threadlocal.locale = locale
            self.clear_per_request_cache()

    def get_current_locale(self):
        # we cache instances of this object between requests; it's possible
        # that new thread reuses the object and has no threadlocal initialized
        if not hasattr(self._locale_threadlocal, 'locale'):
            self._locale_threadlocal.locale = None
        return self._locale_threadlocal.locale

    @property
    def default_locale(self):
        course_settings = self.get_environ().get('course')
        if not course_settings:
            return None
        return course_settings.get('locale')

    def get_title(self):
        try:
            return self.get_environ()['course']['title']
        except KeyError:
            return 'UNTITLED'

    def get_namespace_name(self):
        return self.namespace

    def get_home_folder(self):
        return self.homefolder

    def get_slug(self):
        return self.slug

    def get_config_filename(self):
        """Returns absolute location of a course configuration file."""
        filename = abspath(self.get_home_folder(), GCB_CONFIG_FILENAME)
        debug('Config file: %s' % filename)
        return filename

    def get_environ(self):
        return Course.get_environ(self)

    def get_home(self):
        """Returns absolute location of a course folder."""
        path = abspath(self.get_home_folder(), '')
        return path

    def get_template_home(self):
        """Returns absolute location of a course template folder."""
        path = abspath(self.get_home_folder(), GCB_VIEWS_FOLDER_NAME)
        return path

    def get_data_home(self):
        """Returns absolute location of a course data folder."""
        path = abspath(self.get_home_folder(), GCB_DATA_FOLDER_NAME)
        return path

    def gettext(self, text):
        """Render localized text in the default locale.

        This method should be used in place of gettext.gettext, as it will
        set the locale correctly.

        Args:
            text: str. The text to be localized.

        Returns:
            Localized text, or the original string, if no localization exists.
        """
        try:
            translator = i18n.get_i18n()
            translator.set_locale(self.get_current_locale())
            return translator.gettext(text)
        except Exception:  # pylint: disable=broad-except
            logging.exception('Unable to translate %s', text)
            return text

    def get_template_environ(self, locale, additional_dirs):
        """Create and configure jinja template evaluation environment."""
        template_dir = self.get_template_home()
        dirs = [template_dir]
        if additional_dirs:
            dirs += additional_dirs
        jinja_environment = self.fs.get_jinja_environ(dirs)

        i18n.get_i18n().set_locale(locale)
        jinja_environment.install_gettext_translations(i18n)
        return jinja_environment

    def is_editable_fs(self):
        return self._fs.impl.__class__ == DatastoreBackedFileSystem

    def can_pick_all_locales(self):
        return custom_modules.can_pick_all_locales(self)

    def get_allowed_locales(self):
        environ = self.get_environ()
        default_locale = environ['course'].get('locale')
        extra_locales = environ.get('extra_locales', [])
        return [default_locale] + [
            loc['locale'] for loc in extra_locales
            if loc['locale'] != default_locale and (
                loc[Course.SCHEMA_LOCALE_AVAILABILITY] == (
                    Course.SCHEMA_LOCALE_AVAILABILITY_AVAILABLE)
                or self.can_pick_all_locales())]

    def get_all_locales(self):
        """Returns _all_ locales, whether enabled or not.  Dashboard only."""

        environ = self.get_environ()
        default_locale = self.default_locale
        extra_locales = environ.get('extra_locales', [])
        return [default_locale] + [loc['locale'] for loc in extra_locales]

    @classmethod
    def is_absolute_url(cls, url):
        return bool(urlparse.urlparse(url).scheme)

    def canonicalize_url(self, location):
        """Adds the current namespace URL prefix to the relative 'location'."""
        is_relative = (
            not self.is_absolute_url(location) and
            not location.startswith(self.get_slug()))
        has_slug = (
            self.get_slug() and self.get_slug() != '/')
        if is_relative and has_slug:
            location = '%s%s' % (self.get_slug(), location)
        return location


def has_path_info():
    """Checks if PATH_INFO is defined for the thread local."""
    return hasattr(PATH_INFO_THREAD_LOCAL, 'path')


def set_path_info(path):
    """Stores PATH_INFO in thread local."""
    if not path:
        raise Exception('Use \'unset()\' instead.')
    if has_path_info():
        raise Exception('Expected no path set.')
    try:
        PATH_INFO_THREAD_LOCAL.path = path
        PATH_INFO_THREAD_LOCAL.old_namespace = namespace_manager.get_namespace()
        namespace_manager.set_namespace(
            ApplicationContext.get_namespace_name_for_request())
    finally:
        try:
            caching.RequestScopedSingleton.clear_all()
        finally:
            models.MemcacheManager.clear_readonly_cache()


def get_path_info():
    """Gets PATH_INFO from thread local."""
    return PATH_INFO_THREAD_LOCAL.path


def unset_path_info():
    """Removed PATH_INFO from thread local."""
    if not has_path_info():
        raise Exception('Expected valid path already set.')
    try:
        models.MemcacheManager.clear_readonly_cache()
    finally:
        try:
            caching.RequestScopedSingleton.clear_all()
        finally:
            try:
                app_context = get_course_for_current_request()
                if app_context:
                    app_context.clear_per_request_cache()
            finally:
                namespace_manager.set_namespace(
                    PATH_INFO_THREAD_LOCAL.old_namespace)
                del PATH_INFO_THREAD_LOCAL.old_namespace
                del PATH_INFO_THREAD_LOCAL.path


def _build_course_list_from(rules_text, create_vfs=True):
    """Compute the list of contexts from the text rules."""
    if not rules_text:
        return []

    rules_text = rules_text.replace(',', '\n')
    rules = rules_text.split('\n')
    slugs = {}
    namespaces = {}
    all_contexts = []
    folder = None
    for rule in rules:
        rule = rule.strip()
        if not rule or rule.startswith('#'):
            continue
        parts = rule.split(':')

        # validate length
        if len(parts) < 3:
            raise Exception('Expected rule definition of the form '
                            ' \'type:slug:folder[:ns]\', got %s: ' % rule)

        # validate type
        if parts[0] != SITE_TYPE_COURSE:
            raise Exception('Expected \'%s\', found: \'%s\'.'
                            % (SITE_TYPE_COURSE, parts[0]))
        site_type = parts[0]

        # validate slug
        slug = parts[1]
        slug_parts = urlparse.urlparse(slug)
        if slug != slug_parts[2]:
            raise Exception(
                'Bad rule: \'%s\'. '
                'Course URL prefix \'%s\' must be a simple URL fragment.' % (
                    rule, slug))
        if slug in slugs:
            raise Exception(
                'Bad rule: \'%s\'. '
                'Course URL prefix \'%s\' is already defined.' % (rule, slug))
        slugs[slug] = True

        # validate folder name
        if parts[2]:
            folder = parts[2]
            create_fs = lambda unused_ns: LocalReadOnlyFileSystem(
                logical_home_folder=folder)
        else:
            folder = '/'
            create_fs = lambda ns: DatastoreBackedFileSystem(
                ns=ns,
                logical_home_folder=appengine_config.BUNDLE_ROOT,
                inherits_from=LocalReadOnlyFileSystem(logical_home_folder='/'),
                inheritable_folders=GCB_INHERITABLE_FOLDER_NAMES)

        # validate or derive namespace
        namespace = appengine_config.DEFAULT_NAMESPACE_NAME
        if len(parts) == 4:
            namespace = parts[3]
        else:
            if folder and folder != '/':
                namespace = '%s%s' % (GCB_BASE_COURSE_NAMESPACE,
                                      folder.replace('/', '-'))
        try:
            namespace_manager.validate_namespace(namespace)
        except Exception as e:
            raise Exception(
                'Error validating namespace "%s" in rule "%s"; %s.' % (
                    namespace, rule, e))

        if namespace in namespaces:
            raise Exception(
                'Bad rule \'%s\'. '
                'Namespace \'%s\' is already defined.' % (rule, namespace))
        namespaces[namespace] = True

        vfs = None
        if create_vfs:
            vfs = AbstractFileSystem(create_fs(namespace))

        all_contexts.append(ApplicationContext(
            site_type, slug, folder, namespace, vfs, raw=rule))

    _validate_appcontext_list(all_contexts)
    return all_contexts


def get_course_index(rules_text=None):
    """Build course index given a text of course definition rules."""

    if not rules_text:
        rules_text = GCB_COURSES_CONFIG.value
        if not ApplicationContext.AUTO_DEPLOY_DEFAULT_COURSE and (
            rules_text == GCB_COURSES_CONFIG.default_value) and (
            not Registry.get_overrides().get(GCB_COURSES_CONFIG.name)):
            return CourseIndex([])

    rules_text = rules_text.replace(',', '\n')

    # pylint: disable=protected-access
    course_index = ApplicationContext._COURSE_INDEX_CACHE.get(rules_text)
    if course_index:
        return course_index

    course_index = CourseIndex(_build_course_list_from(rules_text))

    # pylint: disable=protected-access
    ApplicationContext._COURSE_INDEX_CACHE = {rules_text: course_index}
    return course_index


def get_app_context_for_namespace(namespace):
    """Chooses the app_context that matches a namespace."""
    app_context = get_course_index().get_app_context_for_namespace(namespace)
    if not app_context:
        debug('No app_context in namespace: %s' % namespace)
    return app_context


def get_app_context_for_current_request():
    return get_course_index().get_app_context_for_namespace(
        namespace_manager.get_namespace())


def get_course_for_path(path):
    """Chooses app_context that matches a context path."""
    return get_course_index().get_course_for_path(path)


def get_course_for_current_request():
    """Chooses app_context that matches current request context path."""
    if not has_path_info():
        return None
    return get_course_for_path(get_path_info())


def get_all_courses(rules_text=None):
    course_index = get_course_index(rules_text)
    return course_index.get_all_courses()


def _courses_config_validator(rules_text, errors, expect_failures=True):
    """Validates a textual definition of courses entries."""
    try:
        _validate_appcontext_list(
            _build_course_list_from(rules_text, create_vfs=False))
        return True
    except Exception as e:  # pylint: disable=broad-except
        if not expect_failures:
            logging.error('%s\n%s', e, traceback.format_exc())
        errors.append(str(e))
        return False


def validate_new_course_entry_attributes(name, title, admin_email, errors):
    """Validates new course attributes."""
    if not name or len(name) < 3:
        errors.append(
            'The URL component must be at least three characters long.')

    if not re.match('[_a-z0-9]+$', name):
        errors.append(
            'The URL component should contain only '
            'lowercase letters, numbers, or underscores.')

    if len(name) >= _NAMESPACE_MAX_LENGTH:
        errors.append(
            'The URL component cannot be longer than 99 characters.')

    if not title or len(title) < 3:
        errors.append('The title is too short.')

    if not admin_email or '@' not in admin_email:
        errors.append('Please enter a valid email address.')


@db.transactional()
def _add_new_course_entry_to_persistent_configuration(raw):
    """Adds new raw course entry definition to the datastore settings.

    This loads all current datastore course entries and adds a new one. It
    also find the best place to add the new entry at the further down the list
    the better, because entries are applied in the order of declaration.

    Args:
        raw: The course entry rule: 'course:/foo::ns_foo'.

    Returns:
        True if added, False if not. False almost always means a duplicate rule.
    """

    # Get all current entries from a datastore.
    entity = ConfigPropertyEntity.get_by_key_name(GCB_COURSES_CONFIG.name)
    if not entity:
        entity = ConfigPropertyEntity(key_name=GCB_COURSES_CONFIG.name)
        entity.is_draft = False
    if not entity.value:
        entity.value = GCB_COURSES_CONFIG.value
        if entity.value == GCB_COURSES_CONFIG.default_value:
            entity.value = ''

    lines = entity.value.splitlines()

    # Add new entry to the rest of the entries. Since entries are matched
    # in the order of declaration, try to find insertion point further down.
    final_lines_text = None
    for index in reversed(range(0, len(lines) + 1)):
        # Create new rule list putting new item at index position.
        new_lines = lines[:]
        new_lines.insert(index, raw)
        new_lines_text = '\n'.join(new_lines)

        # Validate the rule list definition.
        if _courses_config_validator(new_lines_text, [], expect_failures=True):
            final_lines_text = new_lines_text
            break

    # Save updated course entries.
    if final_lines_text:
        entity.value = final_lines_text
        entity.put()
        return True
    return False


def add_new_course_entry(unique_name, title, admin_email, errors):
    """Validates course attributes and adds the course."""

    # Validate.
    validate_new_course_entry_attributes(
        unique_name, title, admin_email, errors)
    if errors:
        return

    # Create new entry and check it is valid.
    slug = '/%s' % unique_name
    namespace = 'ns_%s' % unique_name
    raw = 'course:%s::%s' % (slug, namespace)
    try:
        get_all_courses(rules_text=raw)
    except Exception as e:  # pylint: disable=broad-except
        errors.append('Failed to add entry: %s.\n%s' % (raw, e))
    if errors:
        return

    with common_utils.Namespace(namespace):
        if metadata.Kind.all().get():
            errors.append(
                'Unable to add new entry "%s": the corresponding namespace, '
                '"%s" is not empty.  If you are certain it should be, you '
                'can use the App Engine Dashboard to manually remove all '
                'database entities from it.' % (unique_name, namespace))
            return

    # Add new entry to persistence.
    if not _add_new_course_entry_to_persistent_configuration(raw):
        errors.append(
            'Unable to add new entry \'%s\'. Entry with the '
            'same name \'%s\' already exists.' % (raw, unique_name))
        return
    return raw


@db.transactional()
def _remove_course_from_persistent_configuration(app_context):
    entity = ConfigPropertyEntity.get_by_key_name(GCB_COURSES_CONFIG.name)
    if not entity:
        return
    if not entity.value:
        return

    match = 'course:%s::%s' % (app_context.get_slug(),
                               app_context.get_namespace_name())
    value = entity.value
    entity.value = '\n'.join([l for l in value.splitlines() if l != match])
    if value != entity.value:
        entity.put()
        return True
    return False


def remove_course(app_context):
    with common_utils.Namespace(appengine_config.DEFAULT_NAMESPACE_NAME):
        if _remove_course_from_persistent_configuration(app_context):
            # Force rebuild of the cached course index in this App Engine
            # instance: when we draw the page showing available courses, we
            # want to have the one we just deleted be gone.
            get_course_index()


GCB_COURSES_CONFIG = ConfigProperty(
    'gcb_courses_config', str, messages.SITE_SETTINGS_COURSE_URLS,
    'course:/:/:', label='Course URLs', multiline=True,
    validator=_courses_config_validator)


class _Route(object):

    def __init__(self, handler_method):
        self.handler_method = handler_method


class ApplicationRequestHandler(webapp2.RequestHandler):
    """Handles dispatching of all URL's to proper handlers."""

    # WARNING! never set this value to True, unless for the production load
    # tests; setting this value to True will allow any anonymous third party to
    # act as a Course Builder superuser
    CAN_IMPERSONATE = False

    # the name of the impersonation header
    IMPERSONATE_HEADER_NAME = 'Gcb-Impersonate'

    # custom global and namespaced error handlers; specify your methods here
    GLOBAL_ERROR_HANDLER = None
    NAMESPACED_ERROR_HANDLER = None

    def dispatch(self):
        if self.CAN_IMPERSONATE:
            self.impersonate_and_dispatch()
        else:
            super(ApplicationRequestHandler, self).dispatch()

    def impersonate_and_dispatch(self):
        """Dispatches request with user impersonation."""
        impersonate_info = self.request.headers.get(
            self.IMPERSONATE_HEADER_NAME)
        if not impersonate_info:
            super(ApplicationRequestHandler, self).dispatch()
            return

        impersonate_info = transforms.loads(impersonate_info)
        email = impersonate_info.get('email')
        user_id = impersonate_info.get('user_id')

        def get_impersonated_user():
            """A method that returns impersonated user."""
            try:
                return users.User(email=email, _user_id=user_id)
            except users.UserNotFoundError:
                return None

        old_get_current_user = users.get_current_user
        try:
            logging.info('Impersonating %s.', email)
            users.get_current_user = get_impersonated_user
            super(ApplicationRequestHandler, self).dispatch()
            return
        finally:
            users.get_current_user = old_get_current_user

    @classmethod
    def bind_to(cls, urls, urls_map):
        """Recursively builds a map from a list of (URL, Handler) tuples."""
        for url in urls:
            path_prefix = url[0]
            handler_class = url[1]
            if path_prefix in urls_map and (
                    handler_class != urls_map[path_prefix]):
                raise Exception(
                    'Path prefix %s defined by %s is being redefined by %s' % (
                        path_prefix, urls_map[path_prefix], handler_class))
            urls_map[path_prefix] = handler_class
            # add child handlers
            if hasattr(handler_class, 'get_child_routes'):
                cls.bind_to(handler_class.get_child_routes(), urls_map)

    @classmethod
    def bind(cls, urls):
        urls_map = {}
        cls.bind_to(urls, urls_map)
        cls.urls_map = urls_map

    def get_handler(self, verb, path):
        """Finds a course suitable for handling this request."""
        course = get_course_for_current_request()
        if not course:
            return None

        path = get_path_info()
        if not path:
            return None
        path = unprefix(path, course.get_slug())

        handler = self.get_handler_for_course_type(course, path)
        if handler:
            handler.route = _Route(verb)
            handler.request = self.request
            handler.response = self.response
            handler.app_context = course

            # This variable represents the path after the namespace prefix is
            # removed. The full path is still stored in self.request.path. For
            # example, if self.request.path is '/new_course/foo/bar/baz/...',
            # the path_translated would be '/foo/bar/baz/...'.
            handler.path_translated = path

        return handler

    def can_handle_course_requests(self, context):
        """Reject all, but authors requests, to an unpublished course."""
        return ((context.now_available and Roles.is_user_whitelisted(context))
                or Roles.is_course_admin(context)
                or Roles.in_any_role(context))

    def is_star_route(self, handler):
        return isinstance(handler, utils.StarRouteHandlerMixin) or (
            issubclass(handler, utils.StarRouteHandlerMixin))

    def _get_handler_factory_for_path(self, path):
        """Picks a handler to handle the path."""
        # Checks if path maps in its entirety.
        if path in ApplicationRequestHandler.urls_map:
            return ApplicationRequestHandler.urls_map[path]

        # Check if partial path maps. For now, let only classes of type
        # utils.StarRouteHandlerMixin handle partial matches. We want to find
        # the longest possible match if alternatives exist.
        parts = path.split('/')
        candidate = None
        partial_path = ''
        for part in parts:
            if part:
                partial_path += '/' + part
                if partial_path in ApplicationRequestHandler.urls_map:
                    handler = ApplicationRequestHandler.urls_map[partial_path]
                    if self.is_star_route(handler):
                        candidate = handler

        # check if root handler exists; it will not be matched above as it's
        # the least specific of all
        if not candidate:
            handler = ApplicationRequestHandler.urls_map.get('/')
            if handler and self.is_star_route(handler):
                candidate = handler

        return candidate

    def get_handler_for_course_type(self, context, path):
        """Gets the right handler for the given context and path."""
        if not self.can_handle_course_requests(context):
            return None

        # Handle static assets here.
        norm_path = os.path.normpath(path)
        if norm_path.startswith(GCB_ASSETS_FOLDER_NAME):
            abs_file = abspath(context.get_home_folder(), norm_path)
            handler = AssetHandler(self, abs_file)
            STATIC_HANDLER_COUNT.inc()
            return handler

        # Handle all dynamic handlers here.
        handler_factory = self._get_handler_factory_for_path(path)
        if handler_factory:
            handler = handler_factory()
            DYNAMIC_HANDLER_COUNT.inc()
            return handler

        NO_HANDLER_COUNT.inc()
        return None

    def before_method(self, handler, verb, path):
        if hasattr(handler, 'before_method'):
            handler.before_method(verb, path)

    def after_method(self, handler, verb, path):
        if hasattr(handler, 'after_method'):
            handler.after_method(verb, path)

    @appengine_config.timeandlog('invoke_http_verb')
    def invoke_http_verb(self, verb, path, no_handler):
        """Set up environment, find appropriate handler and dispatch to it."""

        # make sure this response has not been dispatched yet
        if self.response.status_code != 200 or self.response.body:
            self.finalize_response(
                self.request, self.response, self.response.status_code)
            return

        # setup context and dispatch
        try:
            set_path_info(path)
            handler = self.get_handler(verb.lower(), path)
            if handler:
                self._dispatch(handler, verb, path)
            else:
                no_handler(path)
        finally:
            count_stats(self)
            unset_path_info()

    @classmethod
    def get_status_code_from_dispatch_exception(cls, verb, path, e):
        if isinstance(e, webapp2.HTTPException):
            status_code = e.code
        else:
            status_code = 500
        if status_code >= 500:
            logging.error(
                'Error dispatching %s to %s: %s\n%s',
                verb, path, e, traceback.format_exc())
        return status_code

    def _dispatch(self, handler, verb, path):
        """Dispatch the verb, path to a given handler."""
        # these need to be empty, or dispatch() will attempt to use them; we
        # don't want them to be set or used because routing phase if over by now
        self.request.route_args = []
        self.request.route_kwargs = {}
        set_default_response_headers(handler)

        self.before_method(handler, verb, path)
        try:
            status_code = None
            try:
                handler.dispatch()
                status_code = handler.response.status_code
            except Exception as e:  # pylint: disable=broad-except
                status_code = self.get_status_code_from_dispatch_exception(
                    verb, path, e)
            self._finalize_namespaced_response(
                handler.app_context,
                handler.request, handler.response, status_code)
        finally:
            self.after_method(handler, verb, path)

    @classmethod
    def _needs_error_handler(cls, request, response, status_code):
        """Checks if response has an error, which need to be handled."""
        is_rest_handler = issubclass(cls, utils.RESTHandlerMixin)
        has_pending_content = response and len(response.body) > 0
        is_suitable_error_code = status_code >= 400
        return (
            is_suitable_error_code and
            not has_pending_content and
            not is_rest_handler)

    @classmethod
    def finalize_response(cls, request, response, status_code):
        if cls._needs_error_handler(request, response, status_code):
            error_handler = cls.GLOBAL_ERROR_HANDLER
            if not error_handler:
                error_handler = cls._default_error_hander
            error_handler(request, response, status_code)

    @classmethod
    def _finalize_namespaced_response(
        cls, app_context, request, response, status_code):
        assert app_context
        if cls._needs_error_handler(request, response, status_code):
            error_handler = cls.NAMESPACED_ERROR_HANDLER
            if not error_handler:
                error_handler = cls._default_namespaced_error_hander
            error_handler(app_context, request, response, status_code)

    @classmethod
    def _default_error_hander(cls, request, response, status_code):
        """Render default global error page."""
        response.status_code = status_code
        if status_code < 500:
            response.out.write(
                'Unable to access requested page. '
                'HTTP status code: %s.' % status_code)
        else:
            msg = 'Server error. HTTP status code: %s.' % status_code
            logging.error(msg)
            response.out.write(msg)

    @classmethod
    def _default_namespaced_error_hander(
        cls, app_context, request, response, status_code):
        """Render default namespaced error page."""
        response.status_code = status_code
        if status_code < 500:
            response.out.write(
                'Unable to access requested page in the course %s. '
                'HTTP status code: '
                '%s.' % (app_context.slug, status_code))
        else:
            msg = (
                'Server error accessing the course %s. '
                'HTTP status code: '
                '%s.' % (app_context.slug, status_code))
            logging.error(msg)
            response.out.write(msg)

    def _error_404(self, path):
        """Fail with 404."""
        self.error(404)
        self.finalize_response(self.request, self.response, 404)

    def get(self, path):
        self.invoke_http_verb('GET', path, self._error_404)

    def post(self, path):
        self.invoke_http_verb('POST', path, self._error_404)

    def put(self, path):
        self.invoke_http_verb('PUT', path, self._error_404)

    def delete(self, path):
        self.invoke_http_verb('DELETE', path, self._error_404)


def handle_exception(request, response, e):
    method = None
    path = None
    if request:
        method = request.method.lower()
        path = request.path
    status_code = (
        ApplicationRequestHandler.get_status_code_from_dispatch_exception(
            method, path, e))
    if status_code >= 500:
        logging.error(e)
    ApplicationRequestHandler.finalize_response(
        request, response, status_code)


class SmartRoute(webapp2.SimpleRoute):
    """A route that can dynamically choose whether it's active or not."""

    def is_active(self, handler, route, method, path):
        try:
            if callable(handler.can_handle_route_method_path_now):
                return handler.can_handle_route_method_path_now(
                    route, method, path)
        except AttributeError:
            pass
        return True

    def match(self, request):
        candidate = super(SmartRoute, self).match(request)
        if not candidate:
            return None
        elif self.is_active(
                self.handler, self.template, request.method, request.path):
            return candidate
        else:
            return None

class WSGIRouter(webapp2.Router):
    """Router that provides finalizaton."""

    def __init__(self, routes):
        assert routes and isinstance(routes, list), 'Expected a list'
        self.route_class = SmartRoute
        super(WSGIRouter, self).__init__(routes)

    def dispatch(self, request, response):
        result = super(WSGIRouter, self).dispatch(request, response)
        if result:
            response = result

        # pylint: disable=protected-access
        ApplicationRequestHandler.finalize_response(
            request, response, response.status_code)

        return response


def assert_mapped(src, dest):
    try:
        set_path_info(src)
        course = get_course_for_current_request()
        if not dest:
            assert course is None
        else:
            assert course.get_slug() == dest
    finally:
        unset_path_info()


def assert_handled(src, target_handler):
    try:
        set_path_info(src)
        app_handler = ApplicationRequestHandler()

        # For unit tests to work we want all requests to be handled regardless
        # of course.now_available flag value. Here we patch for that.
        app_handler.can_handle_course_requests = lambda context: True

        handler = app_handler.get_handler(None, None)
        if handler is None and target_handler is None:
            return None
        assert isinstance(handler, target_handler)
        return handler
    finally:
        unset_path_info()


def assert_fails(func):
    success = False
    try:
        func()
        success = True
    except Exception:  # pylint: disable=W0703
        pass
    if success:
        raise Exception('Function \'%s\' was expected to fail.' % func)


def setup_courses(course_config):
    """Helper method that allows a test to setup courses on the fly."""
    Registry.test_overrides[GCB_COURSES_CONFIG.name] = course_config


def reset_courses():
    """Cleanup method to complement setup_courses()."""
    Registry.test_overrides[
        GCB_COURSES_CONFIG.name] = GCB_COURSES_CONFIG.default_value


def test_unprefix():
    assert unprefix('/', '/') == '/'
    assert unprefix('/a/b/c', '/a/b') == '/c'
    assert unprefix('/a/b/index.html', '/a/b') == '/index.html'
    assert unprefix('/a/b', '/a/b') == '/'


def test_rule_validations():
    """Test rules validator."""
    courses = get_all_courses(rules_text='course:/:/')
    assert 1 == len(courses)

    # Check comments.
    setup_courses('course:/a:/nsa, course:/b:/nsb')
    assert 2 == len(get_all_courses())
    setup_courses('course:/a:/nsa, # course:/a:/nsb')
    assert 1 == len(get_all_courses())

    # Check slug collisions are not allowed.
    setup_courses('course:/a:/nsa, course:/a:/nsb')
    assert_fails(get_all_courses)

    # Check namespace collisions are not allowed.
    setup_courses('course:/a:/nsx, course:/b:/nsx')
    assert_fails(get_all_courses)

    # Check rule order is enforced. If we allowed any order and '/a' was before
    # '/aa', the '/aa' would never match.
    setup_courses('course:/a:/nsa, course:/aa:/nsaa, course:/aaa:/nsaaa')
    assert_fails(get_all_courses)

    # Check namespace names.
    setup_courses('course:/a::/nsx')
    assert_fails(get_all_courses)

    # Check slug validity.
    setup_courses('course:/a /b::nsa')
    get_all_courses()
    setup_courses('course:/a?/b::nsa')
    assert_fails(get_all_courses)

    # Cleanup.
    reset_courses()


def test_rule_definitions():
    """Test various rewrite rule definitions."""

    # Check that the default site is created when no rules are specified.
    assert len(get_all_courses()) == 1

    # Test one rule parsing.
    setup_courses('course:/google/pswg:/sites/pswg')
    rules = get_all_courses()
    assert len(get_all_courses()) == 1
    rule = rules[0]
    assert rule.get_slug() == '/google/pswg'
    assert rule.get_home_folder() == '/sites/pswg'

    # Test two rule parsing.
    setup_courses('course:/a/b:/c/d, course:/e/f:/g/h')
    assert len(get_all_courses()) == 2

    # Test that two of the same slugs are not allowed.
    setup_courses('foo:/a/b:/c/d, bar:/a/b:/c/d')
    assert_fails(get_all_courses)

    # Test that only 'course' is supported.
    setup_courses('foo:/a/b:/c/d, bar:/e/f:/g/h')
    assert_fails(get_all_courses)

    # Cleanup.
    reset_courses()

    # Test namespaces.
    set_path_info('/')
    try:
        setup_courses('course:/:/c/d')
        assert ApplicationContext.get_namespace_name_for_request() == (
            'gcb-course-c-d')
    finally:
        unset_path_info()

    # Cleanup.
    reset_courses()


def test_url_to_rule_mapping():
    """Tests mapping of a URL to a rule."""

    # default mapping
    assert_mapped('/favicon.ico', '/')
    assert_mapped('/assets/img/foo.png', '/')

    # explicit mapping
    setup_courses('course:/a/b:/c/d, course:/e/f:/g/h')

    assert_mapped('/a/b', '/a/b')
    assert_mapped('/a/b/', '/a/b')
    assert_mapped('/a/b/c', '/a/b')
    assert_mapped('/a/b/c', '/a/b')

    assert_mapped('/e/f', '/e/f')
    assert_mapped('/e/f/assets', '/e/f')
    assert_mapped('/e/f/views', '/e/f')

    assert_mapped('e/f', None)
    assert_mapped('foo', None)

    # Cleanup.
    reset_courses()


def build_index_for_rules_text(rules_text):
    Registry.test_overrides[GCB_COURSES_CONFIG.name] = rules_text
    courses = get_all_courses()
    index = get_course_index()
    return courses, index


def test_get_course_for_path_impl():
    # pylint: disable=protected-access
    courses, index = build_index_for_rules_text('course:/::ns_x')
    expected = {None: courses[0]}
    assert expected == index._slug_parts2app_context
    for path in ['', '/course', '/a/b']:
        assert courses[0] == get_course_for_path(path)

    courses, index = build_index_for_rules_text('course:/a::ns_x')
    expected = {'a': {None: courses[0]}}
    assert expected == index._slug_parts2app_context
    for path in ['/a', '/a/course', '/a/b/c']:
        assert courses[0] == get_course_for_path(path)
    for path in ['', '/', '/course']:
        assert not get_course_for_path(path)

    courses, index = build_index_for_rules_text(
        'course:/a::ns_x\ncourse:/b::ns_y')
    expected = {'a': {None: courses[0]}, 'b': {None: courses[1]}}
    assert expected == index._slug_parts2app_context
    for path in ['/a', '/a/course', '/a/b/c']:
        assert courses[0] == get_course_for_path(path)
    for path in ['/b', '/b/course', '/b/a/c']:
        assert courses[1] == get_course_for_path(path)
    for path in ['', '/', '/course']:
        assert not get_course_for_path(path)

    courses, index = build_index_for_rules_text('course:/a/b::ns_x')
    expected = {'a': {'b': {None: courses[0]}}}
    assert expected == index._slug_parts2app_context
    for path in ['/a/b', '/a/b/course', '/a/b/c']:
        assert courses[0] == get_course_for_path(path)
    for path in ['', '/a', '/a/course', '/a/c']:
        assert not get_course_for_path(path)

    courses, index = build_index_for_rules_text(
        'course:/a/c::ns_x\ncourse:/b/d::ns_y')
    expected = {'a': {'c': {None: courses[0]}}, 'b': {'d': {None: courses[1]}}}
    assert expected == index._slug_parts2app_context
    for path in ['/a/c', '/a/c/course', '/a/c/d']:
        assert courses[0] == get_course_for_path(path)
    for path in ['/b/d', '/b/d/course', '/b/d/c']:
        assert courses[1] == get_course_for_path(path)
    for path in ['', '/', '/course', '/a', '/b']:
        assert not get_course_for_path(path)

    try:
        courses, index = build_index_for_rules_text(
            'course:/a::ns_x\ncourse:/a/b::ns_y')
    except Exception as e:  # pylint: disable=broad-except
        assert 'reorder course entries' in e.message

    courses, index = build_index_for_rules_text(
        'course:/a/b::ns_x\ncourse:/a::ns_y')
    expected = {'a': {'b': {None: courses[0]}, None: courses[1]}}
    assert expected == index._slug_parts2app_context
    for path in ['/a/b', '/a/b/c', '/a/b/c/course', '/a/b/c/d']:
        assert courses[0] == get_course_for_path(path)
    for path in ['/a', '/a/c', '/a/course', '/a/c/d']:
        assert courses[1] == get_course_for_path(path)
    for path in ['/', '/course', '/b']:
        assert not get_course_for_path(path)
    # pylint: enable=protected-access


def test_get_course_for_path():
    """Tests linear and indexed search to make sure both work the same way."""
    CourseIndex.CAN_USE_INDEXED_GETTER = False
    test_get_course_for_path_impl()
    CourseIndex.CAN_USE_INDEXED_GETTER = True
    test_get_course_for_path_impl()


def test_url_to_handler_mapping_for_course_type():
    """Tests mapping of a URL to a handler for course type."""

    # setup rules
    setup_courses('course:/a/b:/c/d, course:/e/f:/g/h')

    # setup helper classes
    class FakeHandler0(object):

        def __init__(self):
            self.app_context = None

    class FakeHandler1(object):

        def __init__(self):
            self.app_context = None

    class FakeHandler2(BaseZipHandler):

        def __init__(self):
            super(FakeHandler2, self).__init__()
            self.app_context = None

    class FakeHandler3(BaseZipHandler):

        def __init__(self):
            super(FakeHandler3, self).__init__()
            self.app_context = None

    class FakeHandler4(BaseZipHandler):

        def __init__(self):
            super(FakeHandler4, self).__init__()
            self.app_context = None

    # Setup handler.
    handler0 = FakeHandler0
    handler1 = FakeHandler1
    handler2 = FakeHandler2
    urls = [('/', handler0), ('/foo', handler1), ('/bar', handler2)]
    ApplicationRequestHandler.bind(urls)

    # Test proper handler mappings.
    assert_handled('/a/b', FakeHandler0)
    assert_handled('/a/b/', FakeHandler0)
    assert_handled('/a/b/foo', FakeHandler1)
    assert_handled('/a/b/bar', FakeHandler2)

    # Test partial path match.
    assert_handled('/a/b/foo/bee', None)
    assert_handled('/a/b/bar/bee', FakeHandler2)

    # Test assets mapping.
    handler = assert_handled('/a/b/assets/img/foo.png', AssetHandler)
    assert AbstractFileSystem.normpath(
        handler.app_context.get_template_home()).endswith(
            AbstractFileSystem.normpath('/c/d/views'))

    # This is allowed as we don't go out of /assets/...
    handler = assert_handled(
        '/a/b/assets/foo/../models/models.py', AssetHandler)
    assert AbstractFileSystem.normpath(handler.filename).endswith(
        AbstractFileSystem.normpath('/c/d/assets/models/models.py'))

    # This is not allowed as we do go out of /assets/...
    assert_handled('/a/b/assets/foo/../../models/models.py', None)

    # Test negative cases
    assert_handled('/foo', None)
    assert_handled('/baz', None)

    # Site 'views' and 'data' are not accessible
    assert_handled('/a/b/view/base.html', None)
    assert_handled('/a/b/data/units.csv', None)

    # Default mapping
    reset_courses()
    handler3 = FakeHandler3
    handler4 = FakeHandler4
    urls = [
        ('/', handler0),
        ('/foo', handler1),
        ('/bar', handler2),
        ('/zip', handler3),
        ('/zip/a/b', handler4)]
    ApplicationRequestHandler.bind(urls)

    # Positive cases
    assert_handled('/', FakeHandler0)
    assert_handled('/foo', FakeHandler1)
    assert_handled('/bar', FakeHandler2)
    handler = assert_handled('/assets/js/main.js', AssetHandler)
    assert AbstractFileSystem.normpath(
        handler.app_context.get_template_home()).endswith(
            AbstractFileSystem.normpath('/views'))

    # Partial URL matching cases test that the most specific match is found.
    assert_handled('/zip', FakeHandler3)
    assert_handled('/zip/a', FakeHandler3)
    assert_handled('/zip/a/b', FakeHandler4)
    assert_handled('/zip/a/b/c', FakeHandler4)

    # Negative cases
    assert_handled('/baz', None)
    assert_handled('/favicon.ico', None)
    assert_handled('/e/f/index.html', None)
    assert_handled('/foo/foo.css', None)

    # Clean up.
    ApplicationRequestHandler.bind([])


def test_namespace_collisions_are_detected():
    """Test that namespace collisions are detected and are not allowed."""
    setup_courses('foo:/a/b:/c/d, bar:/a/b:/c-d')
    assert_fails(get_all_courses)
    reset_courses()


def test_path_construction():
    """Checks that path_join() works correctly."""

    # Test cases common to all platforms.
    assert (os.path.normpath(path_join('/a/b', '/c')) ==
            os.path.normpath('/a/b/c'))
    assert (os.path.normpath(path_join('/a/b/', '/c')) ==
            os.path.normpath('/a/b/c'))
    assert (os.path.normpath(path_join('/a/b', 'c')) ==
            os.path.normpath('/a/b/c'))
    assert (os.path.normpath(path_join('/a/b/', 'c')) ==
            os.path.normpath('/a/b/c'))

    # Windows-specific test cases.
    drive, unused_path = os.path.splitdrive('c:\\windows')
    if drive:
        assert (os.path.normpath(path_join('/a/b', 'c:/d')) ==
                os.path.normpath('/a/b/d'))
        assert (os.path.normpath(path_join('/a/b/', 'c:/d')) ==
                os.path.normpath('/a/b/d'))


def test_star_handler():
    """Tests a handler that is mapped to a route with '*'."""

    class FakeHandler0(object):

        def __init__(self):
            self.app_context = None

    class FakeHandler1(utils.StarRouteHandlerMixin):

        def __init__(self):
            super(FakeHandler1, self).__init__()
            self.app_context = None

    class FakeHandler2(object):

        def __init__(self):
            super(FakeHandler2, self).__init__()
            self.app_context = None

    handler0 = FakeHandler0
    handler1 = FakeHandler1
    handler2 = FakeHandler2
    urls = [('/', handler0), ('/1', handler1), ('/2', handler2)]
    ApplicationRequestHandler.bind(urls)

    setup_courses('course:/a/b:/c/d, course:/e/f:/g/h')

    assert_handled('/a/b/1', FakeHandler1)
    assert_handled('/a/b/1/', FakeHandler1)
    assert_handled('/a/b/1/bar', FakeHandler1)
    assert_handled('/a/b/1/bar/', FakeHandler1)
    assert_handled('/a/b/1/bar/baz', FakeHandler1)
    assert_handled('/a/b/1/bar/baz/', FakeHandler1)
    assert_handled('/a/b/1/bar/baz?alive=1&john=2', FakeHandler1)

    assert_handled('/a/b/2', FakeHandler2)
    assert_handled('/a/b/2/', None)
    assert_handled('/a/b/2/bar', None)
    assert_handled('/a/b/2/bar/', None)
    assert_handled('/a/b/2/bar/baz', None)
    assert_handled('/a/b/2/bar/baz/', None)
    assert_handled('/a/b/2/bar/baz?alive=1&john=2', None)


def test_css_combo_fix_css_paths():
    def assert_fixed_css(expected_css, orig_css):
        assert (
            expected_css
            == CssComboZipHandler.fix_css_paths(
                'a/b/c/foo.css', orig_css, '/yui/'))

    assert_fixed_css('url(/yui/a/b/c/foo.png)', 'url(foo.png)')
    assert_fixed_css('url(/yui/a/b/c/d/e/foo.png)', 'url(d/e/foo.png)')
    assert_fixed_css('url(http://x.org/foo.png)', 'url(http://x.org/foo.png)')
    assert_fixed_css('url(https://x.org/foo.png)', 'url(https://x.org/foo.png)')
    assert_fixed_css('url(data:00001111)', 'url(data:00001111)')


def run_all_unit_tests():
    assert not ApplicationRequestHandler.CAN_IMPERSONATE

    ApplicationContext.DEBUG_INFO = True
    ApplicationContext.AUTO_DEPLOY_DEFAULT_COURSE = True

    test_get_course_for_path()
    test_namespace_collisions_are_detected()
    test_unprefix()
    test_rule_definitions()
    test_url_to_rule_mapping()
    test_url_to_handler_mapping_for_course_type()
    test_path_construction()
    test_rule_validations()
    test_star_handler()
    test_css_combo_fix_css_paths()

if __name__ == '__main__':
    run_all_unit_tests()
