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

Currently only download of Course Builder 1.3 data is implemented. Example use:

$ python etl.py download course /cs101 myapp server.appspot.com \
    archive.zip --sdk_path=/path/to/my/appengine/sdk

This will result in a file called archive.zip that contains the contents of
the Course Builder 1.3 course found at the URL /cs101 on the application with id
myapp running on the server named server.appspot.com.  archive.zip will contain
assets and data from the course along with a manifest.json enumerating them.
The format of archive.zip will change and should not be relied upon.

In order to run this script, you must first ensure all third-party libraries
required by Course Builder are installed and importable.

Pass --help for additional usage information.
"""

__author__ = [
    'johncox@google.com (John Cox)',
]

import argparse
import logging
import os
import sys
import zipfile
import yaml

# Placeholders for modules we'll import after setting up sys.path. This allows
# us to avoid lint suppressions at every callsite.
appengine_config = None
courses = None
remote = None
sites = None
transforms = None
vfs = None

# Paths from local disk that will be included in the archive.
_LOCAL_WHITELIST = frozenset(['course.yaml', 'assets', 'data'])
# logging.Logger. Module logger.
_LOG = logging.getLogger('coursebuilder.tools.etl')
# String. Name of the manifest file.
_MANIFEST_FILENAME = 'manifest.json'
# String. Identifier for download mode.
_MODE_DOWNLOAD = 'download'
# String. Identifer for upload mode.
_MODE_UPLOAD = 'upload'
# List of all modes.
_MODES = [_MODE_DOWNLOAD, _MODE_UPLOAD]
# Frozenset of strings containing App Engine SDK versions we support.
_SUPPORTED_APP_ENGINE_SDK_VERSIONS = frozenset(['1.7.0'])
# String. Identifier for type course.
_TYPE_COURSE = 'course'
# List of all types.
_TYPES = [_TYPE_COURSE]

# Command-line argument configuration.
_PARSER = argparse.ArgumentParser()
_PARSER.add_argument(
    'mode', choices=_MODES,
    help='indicates whether we are downloading or uploading data', type=str)
_PARSER.add_argument(
    'type', choices=_TYPES, help='type of entity to download', type=str)
_PARSER.add_argument(
    'course_url_prefix',
    help=(
        "URL prefix of the course you want to download (e.g. '/foo' in "
        "'course:/foo:/directory:namespace'"), type=str)
_PARSER.add_argument(
    'application_id',
    help="the id of the application to read from (e.g. 'myapp')", type=str)
_PARSER.add_argument(
    'server',
    help=('the full name of the source application to read from (e.g. '
          'myapp.appspot.com)'), type=str)
_PARSER.add_argument(
    'archive_path',
    help='absolute path of the archive file to read or write', type=str)
_PARSER.add_argument(
    '--log_level', help='Level of logging messages to emit', default='WARNING',
    type=lambda s: s.upper())
_PARSER.add_argument(
    '--sdk_path', help='absolute path of the App Engine SDK', required=True,
    type=str)


class _Archive(object):
    """Manager for local archives of Course Builder data.

    The internal format of the archive may change from version to version; users
    must not depend on it.

    Archives contain assets and data from a single course, along with a manifest
    detailing the course's raw definition string, version of Course Builder the
    course is compatible with, and the list of course files contained within
    the archive.

    # TODO(johncox): possibly obfuscate this archive so it cannot be unzipped
    # outside etl.py. Add a command-line flag for creating a zip instead. For
    # uploads, require an obfuscated archive, not a zip.
    """

    def __init__(self, path):
        """Constructs a new archive.

        Args:
            path: string. Absolute path where the archive will be written.
        """
        self._path = path
        self._zipfile = None

    def add(self, filename, contents):
        """Adds contents to the archive.

        Args:
            filename: string. Path of the contents to add.
            contents: bytes. Contents to add.
        """
        self._zipfile.writestr(_remove_bundle_root(filename), contents)

    def close(self):
        """Closes archive and test for integrity; must close before read."""
        self._zipfile.testzip()
        self._zipfile.close()

    def open(self):
        assert not self._zipfile
        self._zipfile = zipfile.ZipFile(self._path, 'w')

    @property
    def path(self):
        return self._path


class _Manifest(object):
    """Manifest that lists the contents and version of an archive folder."""

    def __init__(self, raw, version):
        """Constructs a new manifest.

        Args:
            raw: string. Raw course definition string.
            version: string. Version of Course Builder course this manifest was
                generated from.
        """
        self._entities = []
        self._raw = raw
        self._version = version

    def add(self, entity):
        self._entities.append(entity)

    @property
    def entities(self):
        return sorted(self._entities)

    @property
    def raw(self):
        return self._raw

    @property
    def version(self):
        return self._version

    def __str__(self):
        """Returns JSON representation of the manifest."""
        manifest = {
            'entities': [e.__dict__ for e in self.entities],
            'raw': self.raw,
            'version': self.version,
        }
        return transforms.dumps(manifest, indent=2, sort_keys=2)


class _ManifestEntity(object):
    """Object that represents an entity in a manifest."""

    def __init__(self, path, is_draft):
        self.is_draft = is_draft
        self.path = _remove_bundle_root(path)


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
        _die('Unable to find App Engine SDK at ' + sdk_path)
    if version not in _SUPPORTED_APP_ENGINE_SDK_VERSIONS:
        _LOG.warning(
            ('SDK version %s found at %s is not supported; behavior may be '
             'unpredictable') % (version, sdk_path))


def _die(message):
    _LOG.critical(message)
    sys.exit(1)


def _download(archive_path, course_url_prefix):
    """Downloads one course to an archive."""
    context = _get_requested_context(sites.get_all_courses(), course_url_prefix)
    if not context:
        _die('No course found with course_url_prefix %s' % course_url_prefix)
    course = _get_course_from(context)
    if course.version < courses.COURSE_MODEL_VERSION_1_3:
        _die(
            'Cannot export course with version < %s' % (
                courses.COURSE_MODEL_VERSION_1_3))
    archive = _Archive(archive_path)
    archive.open()
    manifest = _Manifest(context.raw, course.version)
    _LOG.info('Processing course with URL prefix ' + course_url_prefix)
    datastore_files = set(
        context.fs.impl.list(appengine_config.BUNDLE_ROOT))
    all_files = set(_filter_filesystem_files(context.fs.impl.list(
        appengine_config.BUNDLE_ROOT, include_inherited=True)))
    filesystem_files = all_files - datastore_files
    _LOG.info('Adding files from datastore')
    for path in datastore_files:
        stream = context.fs.impl.get(path)
        entity = _ManifestEntity(path, stream.metadata.is_draft)
        archive.add(path, stream.read())
        manifest.add(entity)
    _LOG.info('Adding files from filesystem')
    for path in filesystem_files:
        with open(path) as f:
            archive.add(path, f.read())
            manifest.add(_ManifestEntity(path, False))
    _LOG.info('Adding manifest')
    archive.add(_MANIFEST_FILENAME, str(manifest))
    archive.close()
    _LOG.info('Done; archive saved to ' + archive.path)


def _filter_filesystem_files(files):
    """Filters out unnecessary files from a local filesystem.

    If we just read from disk, we'll pick up and archive lots of files that we
    don't need to upload later.

    Args:
        files: list of string. Absolute file paths.

    Returns:
        List of string. Absolute filepaths we want to archive.
    """
    return [
        f for f in files if _remove_bundle_root(f).split('/')[0]
        in _LOCAL_WHITELIST]


def _get_course_from(app_context):
    """Gets a courses.Course from the given sites.ApplicationContext."""

    class _Adapter(object):
        def __init__(self, app_context):
            self.app_context = app_context

    return courses.Course(_Adapter(app_context))


def _get_root_path():
    """Finds absolute Course Builder root path."""
    path = os.path.abspath(__file__)
    while not path.endswith('coursebuilder'):
        path = os.path.split(path)[0]
    return path


def _import_modules_into_global_scope():
    """Import helper; run after _set_up_sys_path() for imports to resolve."""
    # pylint: disable-msg=g-import-not-at-top,global-variable-not-assigned,
    # pylint: disable-msg=redefined-outer-name,unused-variable
    global appengine_config
    global sites
    global courses
    global transforms
    global vfs
    global remote
    import appengine_config
    from controllers import sites
    from models import courses
    from models import transforms
    from models import vfs
    from tools.etl import remote


def _get_requested_context(app_contexts, course_url_prefix):
    """Gets requested app_context from list based on course_url_prefix str."""
    found = None
    for context in app_contexts:
        if context.raw.startswith('course:%s:' % course_url_prefix):
            found = context
            break
    return found


def _remove_bundle_root(path):
    """Removes BUNDLE_ROOT prefix from a path."""
    if path.startswith(appengine_config.BUNDLE_ROOT):
        path = path.split(appengine_config.BUNDLE_ROOT)[1]
    # Path must not start with / so it is os.path.join()able.
    if path.startswith('/'):
        path = path[1:]
    return path


def _set_up_sys_path(sdk_path):
    """Sets up sys.path so App Engine/Course Builder imports work."""
    for path in [
            _get_root_path(), sdk_path, os.path.join(sdk_path, 'lib/webapp2')]:
        if path not in sys.path:
            sys.path.insert(0, path)


def _upload():
    """Stub for upload method."""
    # TODO(johncox): implement uploading.
    raise NotImplementedError('upload not implemented')


def _validate_arguments(parsed_args):
    """Validate parsed args for additional constraints."""
    if (parsed_args.mode == _MODE_DOWNLOAD and
        os.path.exists(parsed_args.archive_path)):
        _die(
            'Cannot download to archive path %s; file already exists.' % (
                parsed_args.archive_path))


def main(parsed_args, environment_class=None):
    """Performs the requested ETL operation.

    Args:
        parsed_args: argparse.Namespace. Parsed command-line arguments.
        environment_class: None or remote.Environment. Environment setup class
            used to configure the service stub map. Injectable for tests only;
            defaults to remote.Environment if not specified.
    """
    _validate_arguments(parsed_args)
    _set_up_sys_path(parsed_args.sdk_path)
    logging.basicConfig()
    _LOG.setLevel(parsed_args.log_level.upper())
    _check_sdk(parsed_args.sdk_path)
    _import_modules_into_global_scope()
    if not environment_class:
        environment_class = remote.Environment
    _LOG.info('Mode is %s' % parsed_args.mode)
    _LOG.info(
        'Target is url %s from application_id %s on server %s' % (
            parsed_args.course_url_prefix, parsed_args.application_id,
            parsed_args.server))
    environment_class(
        parsed_args.application_id, parsed_args.server).establish()
    if parsed_args.mode == _MODE_DOWNLOAD:
        _download(parsed_args.archive_path, parsed_args.course_url_prefix)
    elif parsed_args.mode == _MODE_UPLOAD:
        _upload()


if __name__ == '__main__':
    main(_PARSER.parse_args())
