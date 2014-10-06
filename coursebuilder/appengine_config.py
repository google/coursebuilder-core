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

# configure Appstats
appstats_MAX_STACK = 20

# Whether we are running in the production environment.
PRODUCTION_MODE = not os.environ.get(
    'SERVER_SOFTWARE', 'Development').startswith('Development')

# Set this flag to true to enable bulk downloads of Javascript/CSS files in lib
BUNDLE_LIB_FILES = True

# this is the official location of this app for computing of all relative paths
BUNDLE_ROOT = os.path.dirname(__file__)

# make all Windows and Linux paths have the same separator '/'
BUNDLE_ROOT = BUNDLE_ROOT.replace('\\', '/')
CODE_ROOT = BUNDLE_ROOT

# Default namespace name is '' and not None.
DEFAULT_NAMESPACE_NAME = ''


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


# Third-party library zip files.
THIRD_PARTY_LIBS = [
    _Library('babel-0.9.6.zip'),
    _Library('html5lib-0.95.zip'),
    _Library('httplib2-0.8.zip', relative_path='httplib2-0.8/python2'),
    _Library('gaepytz-2011h.zip'),
    _Library(
        'google-api-python-client-1.1.zip',
        relative_path='google-api-python-client-1.1'),
    _Library('mapreduce-r645.zip'),
    _Library('markdown-2.5.zip', relative_path='Markdown-2.5'),
    _Library('mrs-mapreduce-0.9.zip', relative_path='mrs-mapreduce-0.9'),
    _Library('python-gflags-2.0.zip', relative_path='python-gflags-2.0'),
    _Library('oauth-1.0.1.zip', relative_path='oauth'),
    _Library('pyparsing-1.5.7.zip'),
]


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
    for lib in THIRD_PARTY_LIBS + _third_party_libs_from_env():
        if not os.path.exists(lib.file_path):
            raise Exception('Library does not exist: %s' % lib.file_path)
        sys.path.insert(0, lib.full_path)


def gcb_appstats_enabled():
    return 'True' == os.environ.get('GCB_APPSTATS_ENABLED')


def webapp_add_wsgi_middleware(app):
    """Enable AppStats if requested."""
    if gcb_appstats_enabled():
        logging.info('Enabling AppStats.')
        # pylint: disable-msg=g-import-not-at-top
        from google.appengine.ext.appstats import recording
        # pylint: enable-msg=g-import-not-at-top
        app = recording.appstats_wsgi_middleware(app)
    return app


def _import_and_enable_modules(env_var, reraise=False):
    for module_name in os.environ.get(env_var, '').split():
        option = 'enabled'
        if module_name.count('='):
            module_name, option = module_name.split('=', 1)
        try:
            operation = 'importing'
            module = importlib.import_module(module_name)
            operation = 'registering'
            custom_module = module.register_module()
            if option is 'enabled':
                operation = 'enabling'
                custom_module.enable()
        except Exception, ex:  # pylint: disable-msg=broad-except
            logging.exception('Problem %s module "%s"', operation, module_name)
            if reraise:
                raise ex


def import_and_enable_modules():
    _import_and_enable_modules('GCB_REGISTERED_MODULES')
    _import_and_enable_modules('GCB_REGISTERED_MODULES_CUSTOM')
    _import_and_enable_modules('GCB_THIRD_PARTY_MODULES')


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
            # pylint: disable-msg=g-import-not-at-top
            from google.appengine.ext.appstats.recording import recorder_proxy
            # pylint: enable-msg=g-import-not-at-top
            if recorder_proxy and (
                recorder_proxy.has_recorder_for_current_request()):
                recorder_proxy.record_custom_event(label=label, data=data)
        except Exception:  # pylint: disable-msg=broad-except
            logging.exception('Failed to record Appstats event %s.', label)


gcb_init_third_party()
