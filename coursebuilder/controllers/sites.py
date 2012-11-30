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


"""Enables hosting of multiple courses in one application instance."""

import appengine_config, logging, mimetypes, os, threading, webapp2
from google.appengine.api import namespace_manager


# the name of environment variable that holds rewrite rule definitions
GCB_COURSES_CONFIG_ENV_VAR_NAME = 'GCB_COURSES_CONFIG'

# base name for all course namespaces
GCB_BASE_COURSE_NAMESPACE = 'gcb-course'

# these folder names are reserved
GCB_ASSETS_FOLDER_NAME = '/assets'
GCB_VIEWS_FOLDER_NAME = '/views'

# supported site types
SITE_TYPE_COURSE = 'course'

# enable debug output
DEBUG_INFO = False

# thread local storage for current request PATH_INFO
PATH_INFO_THREAD_LOCAL = threading.local()

def hasPathInfo():
  """Checks if PATH_INFO is defined for the thread local."""
  return hasattr(PATH_INFO_THREAD_LOCAL, 'path')

def setPathInfo(path):
  """Stores PATH_INFO in thread local."""
  if not path:
    raise Exception('Use \'unset()\ instead.')
  if hasPathInfo():
    raise Exception("Expected no path set.")
  PATH_INFO_THREAD_LOCAL.path = path

def getPathInfo():
  """Gets PATH_INFO from thread local."""
  return PATH_INFO_THREAD_LOCAL.path

def unsetPathInfo():
  """Removed PATH_INFO from thread local."""
  if not hasPathInfo():
    raise Exception("Expected valid path already set.")
  del PATH_INFO_THREAD_LOCAL.path

def debug(message):
  if DEBUG_INFO:
    logging.info(message)

def makeDefaultRule():
  """By default, we support one course in the root folder in the None namespace."""
  return ApplicationContext('course', '/', '/', None)

def getAllRules():
  """Reads all rewrite rule definitions from environment variable."""
  default = makeDefaultRule()

  if not GCB_COURSES_CONFIG_ENV_VAR_NAME in os.environ:
    return [default]
  var_string = os.environ[GCB_COURSES_CONFIG_ENV_VAR_NAME]
  if not var_string:
    return [default]

  slugs = {}
  namespaces = {}
  all = []
  for rule in var_string.split(','):
    rule = rule.strip()
    if len(rule) == 0:
      continue
    parts = rule.split(':')
    
    # validate length
    if len(parts) < 3:
      raise Exception(
          'Expected rule definition in a form of \'type:slug:folder[:ns]\', got %s: ' % rule)

    # validate type
    if parts[0] != SITE_TYPE_COURSE:
      raise Exception('Expected \'%s\', found: \'%s\'.' % (SITE_TYPE_COURSE, parts[0]))
    type = parts[0]

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
      if folder == '/':
        namespace = GCB_BASE_COURSE_NAMESPACE
      else:
        namespace = '%s%s' % (GCB_BASE_COURSE_NAMESPACE, folder.replace('/', '-'))
      if namespace in namespaces:
        raise Exception('Namespace already defined: %s.' % namespace)
    namespaces[namespace] = True

    all.append(ApplicationContext(type, slug, folder, namespace))
  return all


def getRuleForCurrentRequest():
  """Chooses rule that matches current request context path."""

  # get path if defined
  if not hasPathInfo():
    return None
  path = getPathInfo()

  # get all rules
  rules = getAllRules()

  # match a path to a rule
  # TODO(psimakov): linear search is unacceptable
  for rule in rules:
    if path == rule.getSlug() or path.startswith(
        '%s/' % rule.getSlug()) or rule.getSlug() == '/':
      return rule

  debug('No mapping for: %s' % path)
  return None


def unprefix(path, prefix):
  """Removed the prefix from path, appends '/' if empty string results."""
  if not path.startswith(prefix):
    raise Exception('Not prefixed.')

  if prefix != '/':
    path = path[len(prefix):]
  if path == '':
    path = '/'
  return path


def namespace_manager_default_namespace_for_request():
  """Set a namespace appropriate for this request."""
  return ApplicationContext.getNamespaceName()


"""A class that handles serving of static resources located on the file system."""
class AssetHandler(webapp2.RequestHandler):
  def __init__(self, filename):
    filename = os.path.abspath(filename).replace('//', '/')
    if not filename.startswith('/'):
      raise Exception('Expected absolute path.')
    filename = filename[1:]
    self.filename = os.path.join(appengine_config.BUNDLE_ROOT, filename)

  def getMimeType(self, filename, default='application/octet-stream'):
    guess = mimetypes.guess_type(filename)[0]
    if guess is None:
      return default
    return guess

  def get(self):
    debug('File: %s' % self.filename)

    if not os.path.isfile(self.filename):
      self.error(404)

    self.response.headers['Content-Type'] = self.getMimeType(self.filename)
    self.response.write(open(self.filename, 'r').read())


"""A class that contains an application context for request/response."""
class ApplicationContext(object):
  @classmethod
  def getNamespaceName(cls):
    """A name of the namespace (NDB, memcache, etc.) to use for this request."""
    rule = getRuleForCurrentRequest()
    if rule:
      return rule.namespace
    return None

  def __init__(self, type, slug, homefolder, namespace):
    self.slug = slug
    self.homefolder = homefolder
    self.type = type
    self.namespace = namespace

  def getHomeFolder(self):
    """A folder with the assets belonging to this context."""
    return self.homefolder

  def getSlug(self):
    """A common context path for all URLs in this context ('/courses/mycourse')."""
    return self.slug

  def getTemplateHome(self):
    if self.getHomeFolder() == '/':
      template_home = GCB_VIEWS_FOLDER_NAME
    else:
      template_home = '%s%s' % (self.getHomeFolder(), GCB_VIEWS_FOLDER_NAME)
    template_home = os.path.abspath(template_home)
    if not template_home.startswith('/'):
      raise Exception('Expected absolute path.')
    template_home = template_home[1:]

    debug('Template home: %s' % template_home)
    return os.path.join(appengine_config.BUNDLE_ROOT, template_home)


"""A class that handles dispatching of all URL's to proper handlers."""
class ApplicationRequestHandler(webapp2.RequestHandler):

  @classmethod
  def bind(cls, urls):
    urls_map = {}
    ApplicationRequestHandler.urls = {}
    for url in urls:
      urls_map[url[0]] = url[1]
    ApplicationRequestHandler.urls_map = urls_map

  def getHandler(self):
    """Finds a routing rule suitable for this request."""
    rule = getRuleForCurrentRequest()
    if not rule:
      return None

    path = getPathInfo()
    if not path:
      return None

    return self.getHandlerForCourseType(rule, unprefix(path, rule.getSlug()))

  def getHandlerForCourseType(self, context, path):
    # handle static assets here    
    absolute_path = os.path.abspath(path)
    if absolute_path.startswith('%s/' % GCB_ASSETS_FOLDER_NAME):
      handler = AssetHandler('%s%s' % (context.getHomeFolder(), absolute_path))
      handler.request = self.request
      handler.response = self.response
      handler.app_context = context

      debug('Course asset: %s' % absolute_path)
      return handler

    # handle all dynamic handlers here
    if path in ApplicationRequestHandler.urls_map:
      factory = ApplicationRequestHandler.urls_map[path]
      handler = factory()
      handler.app_context = context
      handler.request = self.request
      handler.response = self.response

      debug('Handler: %s > %s'  %(path, handler.__class__.__name__))
      return handler

    return None

  def get(self, path):
    try:
      setPathInfo(path)
      debug('Namespace: %s' % namespace_manager.get_namespace())
      handler = self.getHandler()
      if not handler:
        self.error(404)
      else:
        handler.get()
    finally:
      unsetPathInfo()

  def post(self, path):
    try:
      setPathInfo(path)
      debug('Namespace: %s' % namespace_manager.get_namespace())
      handler = self.getHandler()
      if not handler:
        self.error(404)
      else:
        handler.post()
    finally:
      unsetPathInfo()


def AssertMapped(src, dest):
  try:
    setPathInfo(src)
    rule = getRuleForCurrentRequest()
    if not dest:
      assert rule == None
    else:
      assert rule.getSlug() == dest
  finally:
    unsetPathInfo()

def AssertHandled(src, targetHandler):
  try:
    setPathInfo(src)
    handler = ApplicationRequestHandler().getHandler()
    if handler == None and targetHandler == None:
      return None
    assert isinstance(handler, targetHandler)
    return handler
  finally:
    unsetPathInfo()

def AssertFails(func):
  success = False
  try:
    func()
    success = True
  except Exception:
    pass
  if success: raise Exception()

def TestUnprefix():
  assert unprefix('/', '/') == '/'
  assert unprefix('/a/b/c', '/a/b') == '/c'
  assert unprefix('/a/b/index.html', '/a/b') == '/index.html'
  assert unprefix('/a/b', '/a/b') == '/'

def TestRuleDefinitions():
  """Test various rewrite rule definitions."""
  os.environ = {}

  # check default site is created when none specified explicitly
  assert len(getAllRules()) == 1

  # test empty definition is ok
  os.environ[GCB_COURSES_CONFIG_ENV_VAR_NAME] = ''
  assert len(getAllRules()) == 1

  # test one rule parsing
  os.environ[GCB_COURSES_CONFIG_ENV_VAR_NAME] = 'course:/google/pswg:/sites/pswg'
  rules = getAllRules()
  assert len(getAllRules()) == 1
  rule = rules[0]
  assert rule.getSlug() == '/google/pswg'
  assert rule.getHomeFolder() == '/sites/pswg'

  # test two rule parsing
  os.environ[GCB_COURSES_CONFIG_ENV_VAR_NAME] = 'course:/a/b:/c/d, course:/e/f:/g/h'
  assert len(getAllRules()) == 2

  # test two of the same slugs are not allowed
  os.environ[GCB_COURSES_CONFIG_ENV_VAR_NAME] = 'foo:/a/b:/c/d, bar:/a/b:/c/d'
  AssertFails(getAllRules)

  # test only course|static is supported
  os.environ[GCB_COURSES_CONFIG_ENV_VAR_NAME] = 'foo:/a/b:/c/d, bar:/e/f:/g/h'
  AssertFails(getAllRules)

  # test namespaces
  setPathInfo('/')

  os.environ[GCB_COURSES_CONFIG_ENV_VAR_NAME] = 'course:/:/c/d'
  assert ApplicationContext.getNamespaceName() == 'gcb-course-c-d'

  unsetPathInfo()

def TestUrlToRuleMapping():
  """Tests mapping of a URL to a rule."""
  os.environ = {}

  # default mapping
  AssertMapped('/favicon.ico', '/')
  AssertMapped('/assets/img/foo.png', '/')

  # explicit mapping
  os.environ[GCB_COURSES_CONFIG_ENV_VAR_NAME] = 'course:/a/b:/c/d, course:/e/f:/g/h'

  AssertMapped('/a/b', '/a/b')
  AssertMapped('/a/b/', '/a/b')
  AssertMapped('/a/b/c', '/a/b')
  AssertMapped('/a/b/c', '/a/b')

  AssertMapped('/e/f', '/e/f')
  AssertMapped('/e/f/assets', '/e/f')
  AssertMapped('/e/f/views', '/e/f')

  AssertMapped('e/f', None)
  AssertMapped('foo', None)

def TestUrlToHandlerMappingForCourseType():
  """Tests mapping of a URL to a handler for course type."""
  os.environ = {}

  # setup rules
  os.environ[GCB_COURSES_CONFIG_ENV_VAR_NAME] = 'course:/a/b:/c/d, course:/e/f:/g/h'

  # setup helper classes
  class FakeHandler0():
    def __init__(self):
      self.app_context = None

  class FakeHandler1():
    def __init__(self):
      self.app_context = None

  class FakeHandler2():
    def __init__(self):
      self.app_context = None

  # setup handler
  handler0 = FakeHandler0
  handler1 = FakeHandler1
  handler2 = FakeHandler2
  urls = [('/', handler0), ('/foo', handler1), ('/bar', handler2)]
  ApplicationRequestHandler.bind(urls)

  # test proper handler mappings
  AssertHandled('/a/b', FakeHandler0)
  AssertHandled('/a/b/', FakeHandler0)
  AssertHandled('/a/b/foo', FakeHandler1)
  AssertHandled('/a/b/bar', FakeHandler2)

  # test assets mapping
  handler = AssertHandled('/a/b/assets/img/foo.png', AssetHandler)
  assert handler.app_context.getTemplateHome().endswith(
      'experimental/coursebuilder/c/d/views')

  # this is allowed as we don't go out of /assets/...
  handler = AssertHandled('/a/b/assets/foo/../models/models.py', AssetHandler)
  assert handler.filename.endswith(
      'experimental/coursebuilder/c/d/assets/models/models.py')

  # this is not allowed as we do go out of /assets/...
  AssertHandled('/a/b/assets/foo/../../models/models.py', None)

  # test negative cases
  AssertHandled('/foo', None)
  AssertHandled('/baz', None)

  # site 'views' and 'data' are not accessible
  AssertHandled('/a/b/view/base.html', None)
  AssertHandled('/a/b/data/units.csv', None)

  # default mapping
  os.environ = {}
  urls = [('/', handler0), ('/foo', handler1), ('/bar', handler2)]

  # positive cases
  AssertHandled('/', FakeHandler0)
  AssertHandled('/foo', FakeHandler1)
  AssertHandled('/bar', FakeHandler2)
  handler = AssertHandled('/assets/js/main.js', AssetHandler)
  assert handler.app_context.getTemplateHome().endswith(
      'experimental/coursebuilder/views')

  # negative cases
  AssertHandled('/favicon.ico', None)
  AssertHandled('/e/f/index.html', None)
  AssertHandled('/foo/foo.css', None)

  # clean up
  ApplicationRequestHandler.bind([])

def TestSpecialChars():
  os.environ = {}

  # test namespace collisions are detected and is not allowed
  os.environ[GCB_COURSES_CONFIG_ENV_VAR_NAME] = 'foo:/a/b:/c/d, bar:/a/b:/c-d'
  AssertFails(getAllRules)

def RunAllUnitTests():
  TestSpecialChars()
  TestUnprefix()
  TestRuleDefinitions()
  TestUrlToRuleMapping()
  TestUrlToHandlerMappingForCourseType()

if __name__ == '__main__':
  DEBUG_INFO = True
  RunAllUnitTests()
