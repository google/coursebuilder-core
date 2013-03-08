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

"""Extract-transform-load utility.

In order to run this script, you must first ensure all third-party libraries
required by Course Builder are installed and importable.

Pass --help for usage.
"""

__author__ = [
    'johncox@google.com (John Cox)',
]

import argparse
import logging
import os
import sys
import yaml


# logging.Logger. Module logger.
_LOG = logging.getLogger('coursebuilder.tools.etl')
# String. Identifier for download mode.
_MODE_DOWNLOAD = 'download'
# String. Identifer for upload mode.
_MODE_UPLOAD = 'upload'
# List of all modes.
_MODES = [_MODE_DOWNLOAD, _MODE_UPLOAD]
# Frozenset of strings containing App Engine SDK versions we support.
_SUPPORTED_APP_ENGINE_SDK_VERSIONS = frozenset(['1.7.0'])

# Command-line argument configuration.
_PARSER = argparse.ArgumentParser()
_PARSER.add_argument(
    'mode', choices=_MODES,
    help='indicates whether we are downloading or uploading data', type=str)
_PARSER.add_argument(
    'application_id',
    help="the id of the application to read from (e.g. 'myapp')", type=str)
_PARSER.add_argument(
    '--log_level', help='Level of logging messages to emit', default='WARNING',
    type=lambda s: s.upper())
_PARSER.add_argument(
    '--sdk_path', help='absolute path of the App Engine SDK', required=True,
    type=str)
_PARSER.add_argument(
    'server',
    help=('the full name of the source application to read from (e.g. '
          'myapp.appspot.com)'), type=str)


def _check_sdk(sdk_path):
    """Ensure that the SDK exists; warn if the version is not supported."""
    version = None
    try:
        with open(os.path.join(sdk_path, 'VERSION')) as f:
            # Cannot import transforms wrapper yet; use plain yaml module.
            contents = yaml.load(f.read())
            version = contents.get('release')
            if not version:  # SDK is malformed somehow.
                raise IOError
    except IOError:
        sys.exit('Unable to find App Engine SDK at ' + sdk_path)
    if version not in _SUPPORTED_APP_ENGINE_SDK_VERSIONS:
        _LOG.warning(
            ('SDK version %s found at %s is not supported; behavior may be '
             'unpredictable') % (version, sdk_path))


def _get_root_path():
    """Finds absolute Course Builder root path."""
    path = os.path.abspath(__file__)
    while not path.endswith('coursebuilder'):
        path = os.path.split(path)[0]
    return path


def _set_up_sys_path(sdk_path):
    """Sets up sys.path so App Engine/Course Builder imports work."""
    for path in [
            _get_root_path(), sdk_path, os.path.join(sdk_path, 'lib/webapp2')]:
        if path not in sys.path:
            sys.path.insert(0, path)


def _download():
    """Stub for download method."""
    # TODO(johncox): implement downloading.
    raise NotImplementedError('download not implemented')


def _upload():
    """Stub for upload method."""
    # TODO(johncox): implement uploading.
    raise NotImplementedError('upload not implemented')


def main(parsed_args):
    _set_up_sys_path(parsed_args.sdk_path)
    logging.basicConfig()
    _LOG.setLevel(parsed_args.log_level.upper())
    _check_sdk(parsed_args.sdk_path)
    # Must do Course Builder/App Engine imports after _set_up_sys_path().
    # pylint: disable-msg=g-import-not-at-top
    from tools.etl import remote
    _LOG.info('Mode is %s' % parsed_args.mode)
    _LOG.info(
        'Target is application_id %s on server %s' % (
            parsed_args.application_id, parsed_args.server))
    remote.Environment(
        parsed_args.application_id, parsed_args.server).establish()
    if parsed_args.mode == _MODE_DOWNLOAD:
        _download()
    elif parsed_args.mode == _MODE_UPLOAD:
        _upload()


if __name__ == '__main__':
    main(_PARSER.parse_args())
