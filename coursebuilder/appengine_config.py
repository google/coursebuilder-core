# Copyright 2013 Google Inc. All Rights Reserved.
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

"""Custom configurations and functions for Google App Engine."""

__author__ = 'psimakov@google.com (Pavel Simakov)'

import datetime
import importlib
import logging
import os
import sys

from common import manifests

# configure Appstats
appstats_MAX_STACK = 20

# Whether we are running in the production environment.
PRODUCTION_MODE = not os.environ.get(
    'SERVER_SOFTWARE', 'Development').startswith('Development')

# Set this flag to true to enable bulk downloads of Javascript/CSS files in lib
BUNDLE_LIB_FILES = not os.environ.get(
    'GCB_STATIC_SERV_ENABLED', 'false').upper() == 'TRUE'

# Set this flag to true if you can generate flattened polymer import files
USE_FLATTENED_HTML_IMPORTS = os.environ.get(
    'GCB_STATIC_SERV_ENABLED', 'false').upper() == 'TRUE'

# this is the official location of this app for computing of all relative paths
BUNDLE_ROOT = os.path.dirname(__file__)

# make all Windows and Linux paths have the same separator '/'
BUNDLE_ROOT = BUNDLE_ROOT.replace('\\', '/')
CODE_ROOT = BUNDLE_ROOT

# Default namespace name is '' and not None.
DEFAULT_NAMESPACE_NAME = ''

# Flag to indicate whether module importation is in progress.  Some modules
# and core items may wish to be a little flexible about warnings and
# exceptions due to some, but not all, modules being imported yet at module
# registration time.
MODULE_REGISTRATION_IN_PROGRESS = False

# Name for the core module.  We don't actually have any code in modules/core,
# since having a core module is pretty well a contradiction in terms.  However,
# there are a few things that want module and module-like-things to register
# themselves by name, and so here we provide a name for the un-module that is
# the immutable core functionality.
CORE_MODULE_NAME = 'core'


class _Library(object):
    """DDO that represents a Python library contained in a .zip file."""

    def __init__(self, zipfile, relative_path=None):
        self._relative_path = relative_path
        self._zipfile = zipfile

    @property
    def file_path(self):
        """Path to the library's file on disk."""
        return os.path.join(BUNDLE_ROOT, 'lib', self._zipfile)

    @property
    def full_path(self):
        """Full path for imports, containing archive-relative paths if any."""
        path = self.file_path
        if self._relative_path:
            path = os.path.join(path, self._relative_path)
        return path

# Google-produced library zip files.
GOOGLE_LIBS = [
    _Library('google-api-python-client-1.4.0.zip'),
    _Library('GoogleAppEngineCloudStorageClient-1.9.15.0.zip',
             relative_path='GoogleAppEngineCloudStorageClient-1.9.15.0'),
    _Library('GoogleAppEnginePipeline-1.9.17.0.zip',
             relative_path='GoogleAppEnginePipeline-1.9.17.0'),
]

# Third-party library zip files.
THIRD_PARTY_LIBS = [
    _Library('Graphy-1.0.0.zip', relative_path='Graphy-1.0.0'),
    _Library('appengine-mapreduce-0.8.2.zip',
             relative_path='appengine-mapreduce-0.8.2/python/src'),
    _Library('babel-0.9.6.zip'),
    _Library('decorator-3.4.0.zip', relative_path='src'),
    _Library('gaepytz-2011h.zip'),
    _Library('graphene-0.7.3.zip'),
    _Library('graphql-core-0.4.12.1.zip'),
    _Library('graphql-relay-0.3.3.zip'),
    _Library('html5lib-0.95.zip'),
    _Library('identity-toolkit-python-client-0.1.6.zip'),
    _Library('markdown-2.5.zip', relative_path='Markdown-2.5'),
    _Library('mrs-mapreduce-0.9.zip', relative_path='mrs-mapreduce-0.9'),
    _Library('networkx-1.9.1.zip', relative_path='networkx-1.9.1'),
    _Library('oauth-1.0.1.zip', relative_path='oauth'),
    _Library('pyparsing-1.5.7.zip'),
    _Library('reportlab-3.1.8.zip'),
    _Library('simplejson-3.7.1.zip', relative_path='simplejson-3.7.1'),
    _Library('six-1.10.0.zip'),

    # rdflib and deps
    _Library('isodate-0.5.5.zip', relative_path='src'),
    _Library('rdflib-4.2.2-dev.zip', relative_path='rdflib'),
]

ALL_LIBS = GOOGLE_LIBS + THIRD_PARTY_LIBS


def gcb_force_default_encoding(encoding):
    """Force default encoding to a specific value."""

    # Eclipse silently sets default encoding to 'utf-8', while GAE forces
    # 'ascii'. We need to control this directly for consistency.
    if sys.getdefaultencoding() != encoding:
        reload(sys)
        sys.setdefaultencoding(encoding)


def _third_party_libs_from_env():
    ret = []
    for lib_config in os.environ.get('GCB_THIRD_PARTY_LIBRARIES', '').split():
        parts = lib_config.split(':')
        if len(parts) == 1:
            ret.append(_Library(parts[0]))
        else:
            ret.append(_Library(parts[0], relative_path=parts[1]))
    return ret


def gcb_init_third_party():
    """Add all third party libraries to system path."""
    for lib in ALL_LIBS + _third_party_libs_from_env():
        if not os.path.exists(lib.file_path):
            raise Exception('Library does not exist: %s' % lib.file_path)
        sys.path.insert(0, lib.full_path)


def gcb_appstats_enabled():
    return 'True' == os.environ.get('GCB_APPSTATS_ENABLED')


def gcb_test_mode():
    return  os.environ.get('GCB_TEST_MODE', 'false').upper() == 'TRUE'


def webapp_add_wsgi_middleware(app):
    """Enable AppStats if requested."""
    if gcb_appstats_enabled():
        logging.info('Enabling AppStats.')
        from google.appengine.ext.appstats import recording
        app = recording.appstats_wsgi_middleware(app)
    return app


def _import_and_enable_modules(env_var, reraise=False):
    for module_name in os.environ.get(env_var, '').split():
        enabled = True
        if module_name.count('='):
            module_name, option = module_name.split('=', 1)
            enabled = (option.lower() == 'enabled')
        _import_module_by_name(module_name, enabled, reraise=reraise)


def _import_module_by_name(module_name, enabled, reraise=False):
    try:
        operation = 'importing'
        module = importlib.import_module(module_name)
        operation = 'registering'
        custom_module = module.register_module()
        if enabled:
            operation = 'enabling'
            custom_module.enable()
    except Exception, ex:  # pylint: disable=broad-except
        logging.exception('Problem %s module "%s"', operation, module_name)
        if reraise:
            raise ex


def _import_and_enable_modules_by_manifest():
    modules = manifests.ModulesRepo(BUNDLE_ROOT)
    for module_name, manifest in sorted(modules.module_to_manifest.iteritems()):
        registration = manifest.get_registration()
        if registration.main_module:
            enabled = (
                registration.enabled or
                (registration.enabled_for_tests and gcb_test_mode()))
            _import_module_by_name(registration.main_module, enabled)


def import_and_enable_modules():
    global MODULE_REGISTRATION_IN_PROGRESS  # pylint: disable=global-statement
    MODULE_REGISTRATION_IN_PROGRESS = True
    _import_and_enable_modules('GCB_PRELOADED_MODULES')
    _import_and_enable_modules('GCB_REGISTERED_MODULES_CUSTOM')
    _import_and_enable_modules('GCB_THIRD_PARTY_MODULES')
    _import_and_enable_modules_by_manifest()
    MODULE_REGISTRATION_IN_PROGRESS = False


def time_delta_to_millis(delta):
    """Converts time delta into total number of milliseconds."""
    millis = delta.days * 24 * 60 * 60 * 1000
    millis += delta.seconds * 1000
    millis += delta.microseconds / 1000
    return millis


def timeandlog(name, duration_only=False):
    """Times and logs execution of decorated method."""

    def timed_1(func):

        def timed_2(*args, **kwargs):
            _name = name
            if args and isinstance(args[0], type):
                _name += '.' + str(args[0].__name__)

            before = datetime.datetime.utcnow()
            if not duration_only:
                log_appstats_event(_name + '.enter')

            result = func(*args, **kwargs)

            after = datetime.datetime.utcnow()
            millis = time_delta_to_millis(after - before)
            if duration_only:
                logging.info(_name + ': duration=%sms' % millis)
                log_appstats_event(_name, {'millis': millis})
            else:
                logging.info(_name + '.leave: duration=%sms' % millis)
                log_appstats_event(_name + '.leave', {'millis': millis})
            return result

        if gcb_appstats_enabled():
            return timed_2
        else:
            return func

    return timed_1


def log_appstats_event(label, data=None):
    if gcb_appstats_enabled():
        try:
            from google.appengine.ext.appstats.recording import recorder_proxy
            if recorder_proxy and (
                recorder_proxy.has_recorder_for_current_request()):
                recorder_proxy.record_custom_event(label=label, data=data)
        except Exception:  # pylint: disable=broad-except
            logging.exception('Failed to record Appstats event %s.', label)


gcb_init_third_party()
