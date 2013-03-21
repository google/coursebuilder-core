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

Currently only download and upload of Course Builder 1.3 data is implemented.
Example use:

$ python etl.py download course /cs101 myapp server.appspot.com archive.zip

This will result in a file called archive.zip that contains the contents of
the Course Builder 1.3 course found at the URL /cs101 on the application with id
myapp running on the server named server.appspot.com.  archive.zip will contain
assets and data from the course along with a manifest.json enumerating them.
The format of archive.zip will change and should not be relied upon.

For upload,

$ python etl.py upload course /cs101 myapp server.appspot.com archive.zip

In order to run this script, you must add the following to the head of sys.path:

1. The absolute path of your Course Builder installation.
2. The absolute path of your App Engine SDK.
3. The absolute paths of third party libraries from the SDK used by Course
   Builder:

   fancy_urllib
   jinja2
   webapp2
   webob

   Their locations in the supported 1.7.0 App Engine SDK are

   <sdk_path>/lib/fancy_urllib
   <sdk_path>/lib/jinja2
   <sdk_path>/lib/webapp2
   <sdk_path>/lib/webob_1_1_1

where <sdk_path> is the absolute path of the 1.7.0 App Engine SDK.

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

# String. Prefix for files stored in an archive.
_ARCHIVE_PATH_PREFIX = 'files'
# String. End of the path to course.json in an archive.
_COURSE_JSON_PATH_SUFFIX = 'data/course.json'
# String. End of the path to course.yaml in an archive.
_COURSE_YAML_PATH_SUFFIX = 'course.yaml'
# Path prefix strings from local disk that will be included in the archive.
_LOCAL_WHITELIST = frozenset([_COURSE_YAML_PATH_SUFFIX, 'assets', 'data'])
# logging.Logger. Module logger.
_LOG = logging.getLogger('coursebuilder.tools.etl')
logging.basicConfig()
# List of string. Valid values for --log_level.
_LOG_LEVEL_CHOICES = ['DEBUG', 'ERROR', 'INFO', 'WARNING']
# String. Name of the manifest file.
_MANIFEST_FILENAME = 'manifest.json'
# String. Identifier for download mode.
_MODE_DOWNLOAD = 'download'
# String. Identifer for upload mode.
_MODE_UPLOAD = 'upload'
# List of all modes.
_MODES = [_MODE_DOWNLOAD, _MODE_UPLOAD]
# Int. The number of times to retry remote_api calls.
_RETRIES = 3
# String. Identifier for type course.
_TYPE_COURSE = 'course'
# List of all types.
_TYPES = [_TYPE_COURSE]

# Command-line argument configuration.
PARSER = argparse.ArgumentParser()
PARSER.add_argument(
    'mode', choices=_MODES,
    help='indicates whether we are downloading or uploading data', type=str)
PARSER.add_argument(
    'type', choices=_TYPES, help='type of entity to download', type=str)
PARSER.add_argument(
    'course_url_prefix',
    help=(
        "URL prefix of the course you want to download (e.g. '/foo' in "
        "'course:/foo:/directory:namespace'"), type=str)
PARSER.add_argument(
    'application_id',
    help="the id of the application to read from (e.g. 'myapp')", type=str)
PARSER.add_argument(
    'server',
    help=('the full name of the source application to read from (e.g. '
          'myapp.appspot.com)'), type=str)
PARSER.add_argument(
    'archive_path',
    help='absolute path of the archive file to read or write', type=str)
PARSER.add_argument(
    '--log_level', choices=_LOG_LEVEL_CHOICES,
    help='Level of logging messages to emit', default='INFO',
    type=lambda s: s.upper())


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

    @classmethod
    def get_external_path(cls, internal_path):
        """Gets external path string from results of cls.get_internal_path."""
        prefix = _ARCHIVE_PATH_PREFIX + os.sep
        assert internal_path.startswith(prefix)
        return internal_path.split(prefix)[1]

    @classmethod
    def get_internal_path(cls, external_path):
        """Get path string used in the archive from an external path string.

        Generates the path used within an archive for an asset. All assets
        (meaning all archive contents except the manifest file) must have
        their paths generated this way, and those paths must be re-translated to
        external paths via cls.get_external_path before use with systems
        external to the archive file.

        Args:
            external_path: string. Path to generate an internal archive path
                from.

        Returns:
            String. Internal archive path.
        """
        assert not external_path.startswith(_ARCHIVE_PATH_PREFIX)
        return os.path.join(
            _ARCHIVE_PATH_PREFIX, _remove_bundle_root(external_path))

    def add(self, filename, contents):
        """Adds contents to the archive.

        Args:
            filename: string. Path of the contents to add.
            contents: bytes. Contents to add.
        """
        self._zipfile.writestr(filename, contents)

    def close(self):
        """Closes archive and test for integrity; must close before read."""
        self._zipfile.testzip()
        self._zipfile.close()

    def get(self, path):
        """Return the raw bytes of the archive entity found at path.

        Returns None if path is not in the archive.

        Args:
            path: string. Path of file to retrieve from the archive.

        Returns:
            Bytes of file contents.
        """
        assert self._zipfile
        try:
            return self._zipfile.read(path)
        except KeyError:
            pass

    def open(self, mode):
        """Opens archive in the mode given by mode string ('r', 'w', 'a')."""
        assert not self._zipfile
        self._zipfile = zipfile.ZipFile(self._path, mode)

    @property
    def manifest(self):
        """Returns the archive's manifest."""
        return _Manifest.from_json(self.get(_MANIFEST_FILENAME))

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

    @classmethod
    def from_json(cls, json):
        """Returns a manifest for the given JSON string."""
        parsed = transforms.loads(json)
        instance = cls(parsed['raw'], parsed['version'])
        for entity in parsed['entities']:
            instance.add(_ManifestEntity(entity['path'], entity['is_draft']))
        return instance

    def add(self, entity):
        self._entities.append(entity)

    def get(self, path):
        """Gets _Entity by path string; returns None if not found."""
        for entity in self._entities:
            if entity.path == path:
                return entity

    @property
    def entities(self):
        return sorted(self._entities, key=lambda e: e.path)

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
        self.path = path


class _ReadWrapper(object):
    """Wrapper for raw bytes that supports read()."""

    def __init__(self, data):
        """Constructs a new read wrapper.

        Args:
            data: bytes. The bytes to return on read().
        """
        self._data = data

    def read(self):
        return self._data


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
    archive.open('w')
    manifest = _Manifest(context.raw, course.version)
    _LOG.info('Processing course with URL prefix ' + course_url_prefix)
    datastore_files = set(_list_all(context))
    all_files = set(_filter_filesystem_files(_list_all(
        context, include_inherited=True)))
    filesystem_files = all_files - datastore_files
    _LOG.info('Adding files from datastore')
    for external_path in datastore_files:
        internal_path = _Archive.get_internal_path(external_path)
        stream = _get_stream(context, external_path)
        entity = _ManifestEntity(internal_path, stream.metadata.is_draft)
        archive.add(internal_path, stream.read())
        manifest.add(entity)
    _LOG.info('Adding files from filesystem')
    for external_path in filesystem_files:
        with open(external_path) as f:
            internal_path = _Archive.get_internal_path(external_path)
            archive.add(internal_path, f.read())
            manifest.add(_ManifestEntity(internal_path, False))
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
    try:
        import appengine_config
        from controllers import sites
        from models import courses
        from models import transforms
        from models import vfs
        from tools.etl import remote
    except ImportError, e:
        _die((
            'Unable to import required modules; see tools/etl/etl.py for docs. '
            'Error was: ' + str(e)))


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


def _retry(message=None, times=_RETRIES):
    """Returns a decorator that automatically retries functions on error.

    Args:
        message: string or None. The optional message to log on retry.
        times: int. Number of times to retry.

    Returns:
        Function wrapper.
    """
    assert times > 0
    def decorator(fn):
        """Real decorator."""
        def wrapped(*args, **kwargs):
            failures = 0
            while failures < times:
                try:
                    return fn(*args, **kwargs)
                # We can't be more specific by default.
                # pylint: disable-msg=broad-except
                except Exception, e:
                    if message:
                        _LOG.info(message)
                    failures += 1
                    if failures == times:
                        raise e
        return wrapped
    return decorator


@_retry(message='Clearing course cache failed; retrying')
def _clear_course_cache(context):
    courses.CachedCourse13.delete(context)  # Force update in UI.


@_retry(message='Getting contents for entity failed; retrying')
def _get_stream(context, path):
    return context.fs.impl.get(path)


@_retry(message='Fetching asset list failed; retrying')
def _list_all(context, include_inherited=False):
    return context.fs.impl.list(
        appengine_config.BUNDLE_ROOT, include_inherited=include_inherited)


@_retry(message='Upload failed; retrying')
def _put(context, content, path, is_draft):
    context.fs.impl.non_transactional_put(
        os.path.join(appengine_config.BUNDLE_ROOT, path), content,
        is_draft=is_draft)


def _upload(archive_path, course_url_prefix):
    _LOG.info((
        'Processing course with URL prefix %s from archive path %s' % (
            course_url_prefix, archive_path)))
    context = _get_requested_context(sites.get_all_courses(), course_url_prefix)
    if not context:
        _die('No course found with course_url_prefix %s' % course_url_prefix)
    course = _get_course_from(context)
    if course.get_units():
        _die(
            'Cannot upload to non-empty course with course_url_prefix %s' % (
                course_url_prefix))
    archive = _Archive(archive_path)
    try:
        archive.open('r')
    except IOError:
        _die('Cannot open archive_path ' + archive_path)
    course_json = archive.get(
        _Archive.get_internal_path(_COURSE_JSON_PATH_SUFFIX))
    if course_json:
        try:
            courses.PersistentCourse13().deserialize(course_json)
        except (AttributeError, ValueError):
            _die((
                'Cannot upload archive at %s containing malformed '
                'course.json') % archive_path)
    course_yaml = archive.get(
        _Archive.get_internal_path(_COURSE_YAML_PATH_SUFFIX))
    if course_yaml:
        try:
            yaml.safe_load(course_yaml)
        except Exception:  # pylint: disable-msg=broad-except
            _die((
                'Cannot upload archive at %s containing malformed '
                'course.yaml') % archive_path)
    _LOG.info('Validation passed; beginning upload')
    count = 0
    for entity in archive.manifest.entities:
        external_path = _Archive.get_external_path(entity.path)
        _put(
            context, _ReadWrapper(archive.get(entity.path)), external_path,
            entity.is_draft)
        count += 1
        _LOG.info('Uploaded ' + external_path)
    _clear_course_cache(context)
    _LOG.info(
        'Done; %s entit%s uploaded' % (count, 'y' if count == 1 else 'ies'))


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
    _LOG.setLevel(parsed_args.log_level.upper())
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
        _upload(parsed_args.archive_path, parsed_args.course_url_prefix)


if __name__ == '__main__':
    main(PARSER.parse_args())
