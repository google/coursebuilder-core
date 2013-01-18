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


"""Enables hosting of multiple courses in one application instance.

We used to allow hosting of only one course in one Google App Engine instance.
Now we allow hosting of many courses simultaneously. To configure multiple
courses one must set an environment variable in app.yaml file, for example:

  ...
  env_variables:
    GCB_COURSES_CONFIG: 'course:/coursea:/courses/a, course:/courseb:/courses/b'
  ...

This variable holds a ',' separated list of rewrite rules. Each rewrite rule
has three ':' separated parts: the word 'course', the URL prefix, and the file
system location for the site files. The fourth, optional part, is a course
namespace name.

The URL prefix specifies, how will the course URL appear in the browser. In the
example above, the courses will be mapped to http://www.example.com[/coursea]
and http://www.example.com[/courseb].

The file system location of the files specifies, which files to serve for the
course. For each course we expect three sub-folders: 'assets', 'views', and
'data'. The 'data' folder must contain the CSV files that define the course
layout, the 'assets' and 'views' should contain the course specific files and
jinja2 templates respectively. In the example above, the course files are
expected to be placed into folders '/courses/a' and '/courses/b' of your Google
App Engine installation respectively.

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
example '/courses/mycourse'. Third, change your bulkloader commands to use the
new CSV data file locations and add a 'namespace' parameter, here is an
example:

  ...
  echo Uploading units.csv
  $GOOGLE_APP_ENGINE_HOME/appcfg.py upload_data \
  --url=http://localhost:8080/_ah/remote_api \
  --config_file=experimental/coursebuilder/bulkloader.yaml \
  --filename=experimental/coursebuilder/courses/a/data/unit.csv \
  --kind=Unit \
  --namespace=gcb-courses-a

  echo Uploading lessons.csv
  $GOOGLE_APP_ENGINE_HOME/appcfg.py upload_data \
  --url=http://localhost:8080/_ah/remote_api \
  --config_file=experimental/coursebuilder/bulkloader.yaml \
  --filename=experimental/coursebuilder/courses/a/data/lesson.csv \
  --kind=Lesson \
  --namespace=gcb-courses-a
  ...

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
import threading

import appengine_config
import webapp2

from google.appengine.api import namespace_manager


# the name of environment variable that holds rewrite rule definitions
GCB_COURSES_CONFIG_ENV_VAR_NAME = 'GCB_COURSES_CONFIG'

# base name for all course namespaces
GCB_BASE_COURSE_NAMESPACE = 'gcb-course'

# these folder and file names are reserved
GCB_ASSETS_FOLDER_NAME = os.path.normpath('/assets/')
GCB_VIEWS_FOLDER_NAME = os.path.normpath('/views/')
GCB_CONFIG_FILENAME = os.path.normpath('/course.yaml')

# supported site types
SITE_TYPE_COURSE = 'course'

# default 'Cache-Control' HTTP header for static files
DEFAULT_CACHE_CONTROL_HEADER_VALUE = 'public, max-age=600'

# enable debug output
DEBUG_INFO = False

# thread local storage for current request PATH_INFO
PATH_INFO_THREAD_LOCAL = threading.local()


def has_path_info():
    """Checks if PATH_INFO is defined for the thread local."""
    return hasattr(PATH_INFO_THREAD_LOCAL, 'path')


def set_path_info(path):
    """Stores PATH_INFO in thread local."""
    if not path:
        raise Exception('Use \'unset()\' instead.')
    if has_path_info():
        raise Exception('Expected no path set.')
    PATH_INFO_THREAD_LOCAL.path = path


def get_path_info():
    """Gets PATH_INFO from thread local."""
    return PATH_INFO_THREAD_LOCAL.path


def unset_path_info():
    """Removed PATH_INFO from thread local."""
    if not has_path_info():
        raise Exception('Expected valid path already set.')
    del PATH_INFO_THREAD_LOCAL.path


def debug(message):
    if DEBUG_INFO:
        logging.info(message)


def make_default_rule():
    # The default is: one course in the root folder of the None namespace.
    return ApplicationContext('course', '/', '/', None)


def get_all_rules():
    """Reads all rewrite rule definitions from environment variable."""
    default = make_default_rule()

    if not GCB_COURSES_CONFIG_ENV_VAR_NAME in os.environ:
        return [default]
    var_string = os.environ[GCB_COURSES_CONFIG_ENV_VAR_NAME]
    if not var_string:
        return [default]

    slugs = {}
    namespaces = {}
    all_contexts = []
    for rule in var_string.split(','):
        rule = rule.strip()
        if not rule:
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
        if parts[1] in slugs:
            raise Exception('Slug already defined: %s.' % parts[1])
        slugs[parts[1]] = True
        slug = parts[1]

        # validate folder name
        folder = parts[2]

        # validate or derive namespace
        namespace = None
        if len(parts) == 4:
            namespace = parts[3]
        else:
            if folder and folder != '/':
                namespace = '%s%s' % (GCB_BASE_COURSE_NAMESPACE,
                                      folder.replace('/', '-'))
            if namespace in namespaces:
                raise Exception('Namespace already defined: %s.' % namespace)
        namespaces[namespace] = True

        all_contexts.append(ApplicationContext(
            site_type, slug, folder, namespace))
    return all_contexts


def get_rule_for_current_request():
    """Chooses rule that matches current request context path."""

    # get path if defined
    if not has_path_info():
        return None
    path = get_path_info()

    # Get all rules.
    rules = get_all_rules()

    # Match a path to a rule.
    # TODO(psimakov): linear search is unacceptable
    for rule in rules:
        if path == rule.get_slug() or path.startswith(
                '%s/' % rule.get_slug()) or rule.get_slug() == '/':
            return rule

    debug('No mapping for: %s' % path)
    return None


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
    return os.path.join(base, path)


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


def namespace_manager_default_namespace_for_request():
    """Set a namespace appropriate for this request."""
    return ApplicationContext.get_namespace_name()


class AssetHandler(webapp2.RequestHandler):
    """Handles serving of static resources located on the file system."""

    def __init__(self, filename):
        self.filename = filename

    def get_mime_type(self, filename, default='application/octet-stream'):
        guess = mimetypes.guess_type(filename)[0]
        if guess is None:
            return default
        return guess

    def get(self):
        """Handles GET requests."""
        debug('File: %s' % self.filename)

        if not os.path.isfile(self.filename):
            self.error(404)

        self.response.headers['Cache-Control'] = (
            DEFAULT_CACHE_CONTROL_HEADER_VALUE)
        self.response.headers['Content-Type'] = self.get_mime_type(
            self.filename)
        self.response.write(open(self.filename, 'r').read())


class ApplicationContext(object):
    """An application context for a request/response."""

    @classmethod
    def get_namespace_name(cls):
        """Gets the name of the namespace to use for this request.

        (Examples of such namespaces are NDB and memcache.)

        Returns:
            The namespace for the current request, or None if no rule matches
            the current request context path.
        """
        rule = get_rule_for_current_request()
        if rule:
            return rule.namespace
        return None

    def __init__(self, site_type, slug, homefolder, namespace):
        # TODO(psimakov): Document these parameters.
        self.type = site_type
        # A common context path for all URLs in this context
        # ('/courses/mycourse').
        self.slug = slug
        # A folder with the assets belonging to this context.
        self.homefolder = homefolder
        self.namespace = namespace

    def get_home_folder(self):
        return self.homefolder

    def get_slug(self):
        return self.slug

    def get_config_filename(self):
        """Returns absolute location of a course configuration file."""
        filename = abspath(self.get_home_folder(), GCB_CONFIG_FILENAME)
        debug('Config file: %s' % filename)
        return filename

    def get_template_home(self):
        """Returns absolute location of a course template folder."""
        path = abspath(self.get_home_folder(), GCB_VIEWS_FOLDER_NAME)
        debug('Template home: %s' % path)
        return path


class ApplicationRequestHandler(webapp2.RequestHandler):
    """Handles dispatching of all URL's to proper handlers."""

    @classmethod
    def bind(cls, urls):
        urls_map = {}
        ApplicationRequestHandler.urls = {}
        for url in urls:
            urls_map[url[0]] = url[1]
        ApplicationRequestHandler.urls_map = urls_map

    def get_handler(self):
        """Finds a routing rule suitable for this request."""
        rule = get_rule_for_current_request()
        if not rule:
            return None

        path = get_path_info()
        if not path:
            return None

        return self.get_handler_for_course_type(
            rule, unprefix(path, rule.get_slug()))

    def get_handler_for_course_type(self, context, path):
        """Gets the right handler for the given context and path."""
        # TODO(psimakov): Add docs (including args and returns).
        norm_path = os.path.normpath(path)

        # Handle static assets here.
        if norm_path.startswith(GCB_ASSETS_FOLDER_NAME):
            abs_file = abspath(context.get_home_folder(), norm_path)
            debug('Course asset: %s' % abs_file)

            handler = AssetHandler(abs_file)
            handler.request = self.request
            handler.response = self.response
            handler.app_context = context

            return handler

        # Handle all dynamic handlers here.
        if path in ApplicationRequestHandler.urls_map:
            factory = ApplicationRequestHandler.urls_map[path]
            handler = factory()
            handler.app_context = context
            handler.request = self.request
            handler.response = self.response

            debug('Handler: %s > %s' % (path, handler.__class__.__name__))
            return handler

        return None

    def get(self, path):
        try:
            set_path_info(path)
            debug('Namespace: %s' % namespace_manager.get_namespace())
            handler = self.get_handler()
            if not handler:
                self.error(404)
            else:
                handler.get()
        finally:
            unset_path_info()

    def post(self, path):
        try:
            set_path_info(path)
            debug('Namespace: %s' % namespace_manager.get_namespace())
            handler = self.get_handler()
            if not handler:
                self.error(404)
            else:
                handler.post()
        finally:
            unset_path_info()


def assert_mapped(src, dest):
    try:
        set_path_info(src)
        rule = get_rule_for_current_request()
        if not dest:
            assert rule is None
        else:
            assert rule.get_slug() == dest
    finally:
        unset_path_info()


def assert_handled(src, target_handler):
    try:
        set_path_info(src)
        handler = ApplicationRequestHandler().get_handler()
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
        raise Exception()


def test_unprefix():
    assert unprefix('/', '/') == '/'
    assert unprefix('/a/b/c', '/a/b') == '/c'
    assert unprefix('/a/b/index.html', '/a/b') == '/index.html'
    assert unprefix('/a/b', '/a/b') == '/'


def test_rule_definitions():
    """Test various rewrite rule definitions."""
    os.environ = {}

    # Check that the default site is created when no rules are specified.
    assert len(get_all_rules()) == 1

    # Test that empty definition is ok.
    os.environ[GCB_COURSES_CONFIG_ENV_VAR_NAME] = ''
    assert len(get_all_rules()) == 1

    # Test one rule parsing.
    os.environ[GCB_COURSES_CONFIG_ENV_VAR_NAME] = (
        'course:/google/pswg:/sites/pswg')
    rules = get_all_rules()
    assert len(get_all_rules()) == 1
    rule = rules[0]
    assert rule.get_slug() == '/google/pswg'
    assert rule.get_home_folder() == '/sites/pswg'

    # Test two rule parsing.
    os.environ[GCB_COURSES_CONFIG_ENV_VAR_NAME] = (
        'course:/a/b:/c/d, course:/e/f:/g/h')
    assert len(get_all_rules()) == 2

    # Test that two of the same slugs are not allowed.
    os.environ[GCB_COURSES_CONFIG_ENV_VAR_NAME] = (
        'foo:/a/b:/c/d, bar:/a/b:/c/d')
    assert_fails(get_all_rules)

    # Test that only 'course' is supported.
    os.environ[GCB_COURSES_CONFIG_ENV_VAR_NAME] = (
        'foo:/a/b:/c/d, bar:/e/f:/g/h')
    assert_fails(get_all_rules)

    # Test namespaces.
    set_path_info('/')

    os.environ[GCB_COURSES_CONFIG_ENV_VAR_NAME] = 'course:/:/c/d'
    assert ApplicationContext.get_namespace_name() == 'gcb-course-c-d'

    unset_path_info()


def test_url_to_rule_mapping():
    """Tests mapping of a URL to a rule."""
    os.environ = {}

    # default mapping
    assert_mapped('/favicon.ico', '/')
    assert_mapped('/assets/img/foo.png', '/')

    # explicit mapping
    os.environ[GCB_COURSES_CONFIG_ENV_VAR_NAME] = (
        'course:/a/b:/c/d, course:/e/f:/g/h')

    assert_mapped('/a/b', '/a/b')
    assert_mapped('/a/b/', '/a/b')
    assert_mapped('/a/b/c', '/a/b')
    assert_mapped('/a/b/c', '/a/b')

    assert_mapped('/e/f', '/e/f')
    assert_mapped('/e/f/assets', '/e/f')
    assert_mapped('/e/f/views', '/e/f')

    assert_mapped('e/f', None)
    assert_mapped('foo', None)


def test_url_to_handler_mapping_for_course_type():
    """Tests mapping of a URL to a handler for course type."""
    os.environ = {}

    # setup rules
    os.environ[GCB_COURSES_CONFIG_ENV_VAR_NAME] = (
        'course:/a/b:/c/d, course:/e/f:/g/h')

    # setup helper classes
    class FakeHandler0(object):
        def __init__(self):
            self.app_context = None

    class FakeHandler1(object):
        def __init__(self):
            self.app_context = None

    class FakeHandler2(object):
        def __init__(self):
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

    # Test assets mapping.
    handler = assert_handled('/a/b/assets/img/foo.png', AssetHandler)
    assert os.path.normpath(handler.app_context.get_template_home()).endswith(
        os.path.normpath('/coursebuilder/c/d/views'))

    # This is allowed as we don't go out of /assets/...
    handler = assert_handled(
        '/a/b/assets/foo/../models/models.py', AssetHandler)
    assert os.path.normpath(handler.filename).endswith(
        os.path.normpath('/coursebuilder/c/d/assets/models/models.py'))

    # This is not allowed as we do go out of /assets/...
    assert_handled('/a/b/assets/foo/../../models/models.py', None)

    # Test negative cases
    assert_handled('/foo', None)
    assert_handled('/baz', None)

    # Site 'views' and 'data' are not accessible
    assert_handled('/a/b/view/base.html', None)
    assert_handled('/a/b/data/units.csv', None)

    # Default mapping
    os.environ = {}
    urls = [('/', handler0), ('/foo', handler1), ('/bar', handler2)]

    # Positive cases
    assert_handled('/', FakeHandler0)
    assert_handled('/foo', FakeHandler1)
    assert_handled('/bar', FakeHandler2)
    handler = assert_handled('/assets/js/main.js', AssetHandler)
    assert os.path.normpath(handler.app_context.get_template_home()).endswith(
        os.path.normpath('/coursebuilder/views'))

    # Negative cases
    assert_handled('/favicon.ico', None)
    assert_handled('/e/f/index.html', None)
    assert_handled('/foo/foo.css', None)

    # Clean up
    ApplicationRequestHandler.bind([])


def test_special_chars():
    os.environ = {}

    # Test that namespace collisions are detected and are not allowed.
    os.environ[GCB_COURSES_CONFIG_ENV_VAR_NAME] = (
        'foo:/a/b:/c/d, bar:/a/b:/c-d')
    assert_fails(get_all_rules)


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


def run_all_unit_tests():
    test_special_chars()
    test_unprefix()
    test_rule_definitions()
    test_url_to_rule_mapping()
    test_url_to_handler_mapping_for_course_type()
    test_path_construction()

if __name__ == '__main__':
    DEBUG_INFO = True
    run_all_unit_tests()
