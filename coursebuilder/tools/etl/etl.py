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

There are four features:

1. Download and upload of Course Builder 1.3+ data:

$ python etl.py download course /cs101 myapp server.appspot.com archive.zip

This will result in a file called archive.zip that contains the files that make
up the Course Builder 1.3+ course found at the URL /cs101 on the application
with id myapp running on the server named server.appspot.com. archive.zip will
contain assets and data files from the course along with a manifest.json
enumerating them. The format of archive.zip will change and should not be relied
upon.

For upload,

$ python etl.py upload course /cs101 myapp server.appspot.com \
    --archive_path archive.zip

2. Download of datastore entities. This feature is experimental and upload is
   not supported:

$ python etl.py download datastore /cs101 myapp server.appspot.com \
    --archive_path archive.zip --datastore_types model1,model2

This will result in a file called archive.zip that contains a dump of all model1
and model2 instances found in the specified course, identified as above. The
archive will contain serialized data along with a manifest. The format of
archive.zip will change and should not be relied upon.

3. Deletion of all datastore entities in a single course. Delete of the course
   itself not supported. To run:

$ python etl.py delete datastore /cs101 myapp server.appspot.com

Before delete commences, you will be told what entity kinds will be deleted and
you will be prompted for confirmation. Note that this process is irreversible,
and, if interrupted, may leave the course in an invalid state. Note also that it
races with writes against your datastore unless you first disable writes.

Finally, note that only the datastore entities of the kinds listed will be
deleted, and those will only be deleted from the namespace corresponding to the
target course. Custom entities you added to base Course Builder may or may not
be processed. Entities in the global namespace and those created by App Engine
will not be processed.

Deleting a course flushes caches. Because memcache does not support namespaced
flush all operations, all caches for all courses will be flushed.

4. Execution of custom jobs.

$ python etl.py run path.to.my.Job /cs101 myapp server.appspot.com \
    --job_args='more_args --delegated_to my.Job'

This requires that you have written a custom class named Job found in the
directory path/to/my, relative to the Course Builder root. Job's main method
will be executed against the specified course, identified as above. See
etl_lib.Job for more information.

In order to run this script, you must add the following to the head of sys.path:

  1. The absolute path of your Course Builder installation.
  2. The absolute path of your App Engine SDK.
  3. The absolute paths of third party libraries from the SDK used by Course
     Builder:

     fancy_urllib
     jinja2
     webapp2
     webob

     Their locations in the supported 1.8.2 App Engine SDK are

     <sdk_path>/lib/fancy_urllib
     <sdk_path>/lib/jinja2-2.6
     <sdk_path>/lib/webapp2-2.5.2
     <sdk_path>/lib/webob-1.2.3

     where <sdk_path> is the absolute path of the 1.8.2 App Engine SDK.
  4. If you are running a custom job, the absolute paths of all code required
     by your custom job, unless covered above.

When running etl.py against a remote endpoint you will be prompted for a
username and password. If the remote endpoint is a development server, you may
enter any username and password. If the remote endpoint is in production, enter
your username and an application-specific password. See
http://support.google.com/accounts/bin/answer.py?hl=en&answer=185833 for help on
application-specific passwords.

Pass --help for additional usage information.
"""

__author__ = [
    'johncox@google.com (John Cox)',
]

import argparse
import functools
import hashlib
import hmac
import logging
import os
import random
import re
import sys
import traceback
import zipfile
import yaml


# Placeholders for modules we'll import after setting up sys.path. This allows
# us to avoid lint suppressions at every callsite.
appengine_config = None
config = None
courses = None
db = None
etl_lib = None
memcache = None
metadata = None
namespace_manager = None
remote = None
transforms = None
vfs = None


# String. Prefix for files stored in an archive.
_ARCHIVE_PATH_PREFIX = 'files'
# String. End of the path to course.json in an archive.
_COURSE_JSON_PATH_SUFFIX = 'data/course.json'
# String. End of the path to course.yaml in an archive.
_COURSE_YAML_PATH_SUFFIX = 'course.yaml'
# String. Message the user must type to confirm datastore deletion.
_DELETE_DATASTORE_CONFIRMATION_INPUT = 'YES, DELETE'
# Function that takes one arg and returns it.
_IDENTITY_TRANSFORM = lambda x: x
# Regex. Format of __internal_names__ used by datastore kinds.
_INTERNAL_DATASTORE_KIND_REGEX = re.compile(r'^__.*__$')
# Path prefix strings from local disk that will be included in the archive.
_LOCAL_WHITELIST = frozenset([_COURSE_YAML_PATH_SUFFIX, 'assets', 'data'])
# Path prefix strings that are subdirectories of the whitelist that we actually
# want to exclude because they aren't userland code and will cause conflicts.
_LOCAL_WHITELIST_EXCLUDES = frozenset(['assets/lib'])
# logging.Logger. Module logger.
_LOG = logging.getLogger('coursebuilder.tools.etl')
logging.basicConfig()
# List of string. Valid values for --log_level.
_LOG_LEVEL_CHOICES = ['DEBUG', 'ERROR', 'INFO', 'WARNING']
# String. Name of the manifest file.
_MANIFEST_FILENAME = 'manifest.json'
# String. Identifier for delete mode.
_MODE_DELETE = 'delete'
# String. Identifier for download mode.
_MODE_DOWNLOAD = 'download'
# String. Identifier for custom run mode.
_MODE_RUN = 'run'
# String. Identifier for upload mode.
_MODE_UPLOAD = 'upload'
# List of all modes.
_MODES = [_MODE_DELETE, _MODE_DOWNLOAD, _MODE_RUN, _MODE_UPLOAD]
# Int. The number of times to retry remote_api calls.
_RETRIES = 3
# String. Identifier for type corresponding to course definition data.
_TYPE_COURSE = 'course'
# String. Identifier for type corresponding to datastore entities.
_TYPE_DATASTORE = 'datastore'

# Command-line argument configuration.
PARSER = argparse.ArgumentParser()
PARSER.add_argument(
    'mode', choices=_MODES,
    help='Indicates the kind of operation we are performing', type=str)
PARSER.add_argument(
    'type',
    help=(
        'Type of entity to process. If mode is %s or %s, should be one of '
        '%s or %s. If mode is %s, should be an importable dotted path to your '
        'etl_lib.Job subclass') % (
            _MODE_DOWNLOAD, _MODE_UPLOAD, _TYPE_COURSE, _TYPE_DATASTORE,
            _MODE_RUN),
    type=str)
PARSER.add_argument(
    'course_url_prefix',
    help=(
        "URL prefix of the course you want to download (e.g. '/foo' in "
        "'course:/foo:/directory:namespace'"), type=str)
PARSER.add_argument(
    'application_id',
    help="The id of the application to read from (e.g. 'myapp')", type=str)
PARSER.add_argument(
    'server',
    help=(
        'The full name of the source application to read from (e.g. '
        'myapp.appspot.com)'), type=str)
PARSER.add_argument(
    '--archive_path',
    help=(
        'Absolute path of the archive file to read or write; required if mode '
        'is %s or %s' % (_MODE_DOWNLOAD, _MODE_UPLOAD)), type=str)
PARSER.add_argument(
    '--batch_size',
    help='Number of results to attempt to retrieve per batch',
    default=20, type=int)
PARSER.add_argument(
    '--datastore_types',
    help=(
        "When type is '%s', comma-separated list of datastore model types to "
        'process; all models are processed by default' % _TYPE_DATASTORE),
    type=lambda s: s.split(','))
PARSER.add_argument(
    '--disable_remote', action='store_true',
    help=(
        'If mode is %s, pass this flag to skip authentication and remote '
        'environment setup. Should only pass for jobs that run entirely '
        'locally and do not require RPCs') % _MODE_RUN)
PARSER.add_argument(
    '--force_overwrite', action='store_true',
    help=(
        'If mode is download and type is course, forces overwrite of entities '
        'on the target system that are also present in the archive. Note that '
        'this operation is dangerous and may result in data loss'))
PARSER.add_argument(
    '--job_args', default=[],
    help=(
        'If mode is %s, string containing args delegated to etl_lib.Job '
        'subclass') % _MODE_RUN, type=lambda s: s.split())
PARSER.add_argument(
    '--log_level', choices=_LOG_LEVEL_CHOICES,
    help='Level of logging messages to emit', default='INFO',
    type=lambda s: s.upper())
PARSER.add_argument(
    '--privacy', action='store_true',
    help=(
        "When mode is '%s' and type is '%s', passing this flag will strip or "
        "obfuscate information that can identify a single user" % (
            _MODE_DOWNLOAD, _TYPE_DATASTORE)))
PARSER.add_argument(
    '--privacy_secret',
    help=(
        "When mode is '%s', type is '%s', and --privacy is passed,  pass this "
        "secret to have user ids transformed with it rather than with random "
        "bits") % (_MODE_DOWNLOAD, _TYPE_DATASTORE), type=str)


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

    def add_local_file(self, local_filename, internal_filename):
        """Adds a file from local disk to the archive.

        Args:
            local_filename: string. Path on disk of file to add.
            internal_filename: string. Internal archive path to write to.
        """
        self._zipfile.write(local_filename, arcname=internal_filename)

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


def _confirm_delete_datastore_or_die(kind_names, namespace, title):
    context = {
        'confirmation_message': _DELETE_DATASTORE_CONFIRMATION_INPUT,
        'kinds': ', '.join(kind_names),
        'linebreak': os.linesep,
        'namespace': namespace,
        'title': title,
    }
    response = _raw_input(
        ('You are about to delete all entities of the kinds "%(kinds)s" from '
         'the course %(title)s in namespace %(namespace)s.%(linebreak)sYou are '
         'also about to flush all caches for all courses on your production '
         'instance.%(linebreak)sYou cannot undo this operation.%(linebreak)sTo '
         'confirm, type "%(confirmation_message)s": ') % context)
    if response != _DELETE_DATASTORE_CONFIRMATION_INPUT:
        _die('Delete not confirmed. Aborting')


def _delete(course_url_prefix, delete_type, batch_size):
    context = _get_context_or_die(course_url_prefix)
    if delete_type == _TYPE_COURSE:
        _delete_course()
    elif delete_type == _TYPE_DATASTORE:
        old_namespace = namespace_manager.get_namespace()
        try:
            namespace_manager.set_namespace(context.get_namespace_name())
            _delete_datastore(context, batch_size)
        finally:
            namespace_manager.set_namespace(old_namespace)


def _delete_course():
    """Stub for possible future course deleter."""
    raise NotImplementedError


def _delete_datastore(context, batch_size):
    kind_names = _get_datastore_kinds()
    _confirm_delete_datastore_or_die(
        kind_names, context.get_namespace_name(), context.get_title())
    # Fetch all classes before the loop so we cannot hit an import error partway
    # through issuing delete RPCs.
    model_classes = [db.class_for_kind(kind_name) for kind_name in kind_names]
    _LOG.info('Beginning datastore delete')

    for model_class in model_classes:
        _LOG.info('Deleting entities of kind %s', model_class.kind())
        _process_models(model_class, batch_size, delete=True)

    _LOG.info('Flushing all caches')
    memcache.flush_all()
    _LOG.info('Done')


def _die(message, with_trace=False):
    if with_trace:  # Also logs most recent traceback.
        info = sys.exc_info()
        message = '%s%s%s%s%s%s%s' % (
            message, os.linesep,
            info[0], os.linesep,  # exception class name
            info[1], os.linesep,  # exception message
            ''.join(traceback.format_tb(info[2])))  # exception stack
    _LOG.critical(message)
    sys.exit(1)


def _download(
    download_type, archive_path, course_url_prefix, datastore_types,
    batch_size, privacy_transform_fn):
    """Validates and dispatches to a specific download method."""
    archive_path = os.path.abspath(archive_path)
    context = _get_context_or_die(course_url_prefix)
    course = _get_course_from(context)
    if download_type == _TYPE_COURSE:
        _download_course(context, course, archive_path, course_url_prefix)
    elif download_type == _TYPE_DATASTORE:
        old_namespace = namespace_manager.get_namespace()
        try:
            namespace_manager.set_namespace(context.get_namespace_name())
            _download_datastore(
                context, course, archive_path, datastore_types, batch_size,
                privacy_transform_fn)
        finally:
            namespace_manager.set_namespace(old_namespace)


def _download_course(context, course, archive_path, course_url_prefix):
    if course.version < courses.COURSE_MODEL_VERSION_1_3:
        _die(
            'Cannot export course made with Course Builder version < %s' % (
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
        is_draft = False
        if stream.metadata and hasattr(stream.metadata, 'is_draft'):
            is_draft = stream.metadata.is_draft
        entity = _ManifestEntity(internal_path, is_draft)
        archive.add(internal_path, stream.read())
        manifest.add(entity)
    _LOG.info('Adding files from filesystem')
    for external_path in filesystem_files:
        with open(external_path) as f:
            internal_path = _Archive.get_internal_path(external_path)
            archive.add(internal_path, f.read())
            manifest.add(_ManifestEntity(internal_path, False))
    _finalize_download(archive, manifest)


def _download_datastore(
    context, course, archive_path, datastore_types, batch_size,
    privacy_transform_fn):
    available_types = set(_get_datastore_kinds())
    if not datastore_types:
        datastore_types = available_types
    requested_types = set(datastore_types)
    missing_types = requested_types - available_types
    if missing_types:
        _die(
            'Requested types not found: %s%sAvailable types are: %s' % (
                ', '.join(missing_types), os.linesep,
                ', '.join(available_types)))
    found_types = requested_types & available_types
    archive = _Archive(archive_path)
    archive.open('w')
    manifest = _Manifest(context.raw, course.version)
    for found_type in found_types:
        json_path = os.path.join(
            os.path.dirname(archive_path), '%s.json' % found_type)
        _LOG.info(
            'Adding entities of type %s to temporary file %s',
            found_type, json_path)
        json_file = transforms.JsonFile(json_path)
        json_file.open('w')
        model_map_fn = functools.partial(
            _write_model_to_json_file, json_file, privacy_transform_fn)
        _process_models(
            db.class_for_kind(found_type), batch_size,
            model_map_fn=model_map_fn)
        json_file.close()
        internal_path = _Archive.get_internal_path(
            os.path.basename(json_file.name))
        _LOG.info('Adding %s to archive', internal_path)
        archive.add_local_file(json_file.name, internal_path)
        manifest.add(_ManifestEntity(internal_path, False))
        _LOG.info('Removing temporary file ' + json_file.name)
        os.remove(json_file.name)
    _finalize_download(archive, manifest)


def _filter_filesystem_files(files):
    """Filters out unnecessary files from a local filesystem.

    If we just read from disk, we'll pick up and archive lots of files that we
    don't need to upload later, plus non-userland code that on reupload will
    shadow the system versions (views, assets/lib, etc.).

    Args:
        files: list of string. Absolute file paths.

    Returns:
        List of string. Absolute filepaths we want to archive.
    """
    filtered_files = []
    for path in files:
        relative_name = _remove_bundle_root(path)
        not_in_excludes = not any(
            [relative_name.startswith(e) for e in _LOCAL_WHITELIST_EXCLUDES])
        head_directory = relative_name.split(os.path.sep)[0]
        if not_in_excludes and head_directory in _LOCAL_WHITELIST:
            filtered_files.append(path)
    return filtered_files


def _finalize_download(archive, manifest):
    _LOG.info('Adding manifest')
    archive.add(_MANIFEST_FILENAME, str(manifest))
    archive.close()
    _LOG.info('Done; archive saved to ' + archive.path)


def _force_config_reload():
    # For some reason config properties aren't being automatically pulled from
    # the datastore with the remote environment. Force an update of all of them.
    config.Registry.get_overrides(force_update=True)


def _get_context_or_die(course_url_prefix):
    context = etl_lib.get_context(course_url_prefix)
    if not context:
        _die('No course found with course_url_prefix %s' % course_url_prefix)
    return context


def _get_privacy_transform_fn(privacy, privacy_secret):
    """Returns a transform function to use for export."""

    assert privacy_secret is not None

    if not privacy:
        return _IDENTITY_TRANSFORM
    else:
        return functools.partial(_hmac_sha_2_256, privacy_secret)


def _get_privacy_secret(privacy_secret):
    """Gets the passed privacy secret (or 128 random bits if None)."""
    secret = privacy_secret
    if secret is None:
        secret = random.getrandbits(128)
    return secret


def _get_course_from(app_context):
    """Gets a courses.Course from the given sites.ApplicationContext."""

    class _Adapter(object):
        def __init__(self, app_context):
            self.app_context = app_context

    return courses.Course(_Adapter(app_context))


def _hmac_sha_2_256(privacy_secret, value):
    """HMAC-SHA-2-256 for use as a privacy transformation function."""
    return hmac.new(
        str(privacy_secret), msg=str(value), digestmod=hashlib.sha256
    ).hexdigest()


def _import_entity_modules():
    """Import all entity type classes.

    We need to import main.py to make sure all known entity types are imported
    by the time the ETL code runs. If a transitive closure of main.py imports
    does not import all required classes, import them here explicitly.
    """
    # pylint: disable-msg=g-import-not-at-top,global-variable-not-assigned,
    # pylint: disable-msg=redefined-outer-name,unused-variable
    try:
        import main
    except ImportError, e:
        _die((
            'Unable to import required modules; see tools/etl/etl.py for '
            'docs.'), with_trace=True)


def _import_modules_into_global_scope():
    """Import helper; run after _set_up_sys_path() for imports to resolve."""
    # pylint: disable-msg=g-import-not-at-top,global-variable-not-assigned,
    # pylint: disable-msg=redefined-outer-name,unused-variable
    global appengine_config
    global memcache
    global namespace_manager
    global db
    global metadata
    global config
    global courses
    global transforms
    global vfs
    global etl_lib
    global remote
    try:
        import appengine_config
        from google.appengine.api import memcache
        from google.appengine.api import namespace_manager
        from google.appengine.ext import db
        from google.appengine.ext.db import metadata
        from models import config
        from models import courses
        from models import transforms
        from models import vfs
        from tools.etl import etl_lib
        from tools.etl import remote
    except ImportError, e:
        _die((
            'Unable to import required modules; see tools/etl/etl.py for '
            'docs.'), with_trace=True)


def _remove_bundle_root(path):
    """Removes BUNDLE_ROOT prefix from a path."""
    if path.startswith(appengine_config.BUNDLE_ROOT):
        path = path.split(appengine_config.BUNDLE_ROOT)[1]
    # Path must not start with path separator so it is os.path.join()able.
    if path.startswith(os.path.sep):
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
                except Exception as e:
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


@_retry(message='Checking if the specified course is empty failed; retrying')
def _context_is_for_empty_course(context):
    # True if course is entirely empty or contains only a course.yaml.
    current_course_files = context.fs.impl.list(
        appengine_config.BUNDLE_ROOT)
    empty_course_files = [os.path.join(
        appengine_config.BUNDLE_ROOT, _COURSE_YAML_PATH_SUFFIX)]
    return (
        (not current_course_files) or
        current_course_files == empty_course_files)


@_retry(message='Getting list of datastore_types failed; retrying')
def _get_datastore_kinds():
    # Return only user-defined names, not __internal_appengine_names__.
    return [
        k for k in metadata.get_kinds()
        if not _INTERNAL_DATASTORE_KIND_REGEX.match(k)]


@_retry(message='Getting contents for entity failed; retrying')
def _get_stream(context, path):
    return context.fs.impl.get(path)


@_retry(message='Fetching asset list failed; retrying')
def _list_all(context, include_inherited=False):
    return context.fs.impl.list(
        appengine_config.BUNDLE_ROOT, include_inherited=include_inherited)


def _process_models(model_class, batch_size, delete=False, model_map_fn=None):
    """Fetch all rows in batches."""
    assert (delete or model_map_fn) or (not delete and model_map_fn)
    reportable_chunk = batch_size * 10
    total_count = 0
    cursor = None
    while True:
        batch_count, cursor = _process_models_batch(
            model_class, cursor, batch_size, delete, model_map_fn)
        if not batch_count:
            break
        if not cursor:
            break
        total_count += batch_count
        if not total_count % reportable_chunk:
            _LOG.info('Processed records: %s', total_count)


@_retry(message='Processing datastore entity batch failed; retrying')
def _process_models_batch(
    model_class, cursor, batch_size, delete, model_map_fn):
    """Processes or deletes models in batches."""
    query = model_class.all(keys_only=delete)
    if cursor:
        query.with_cursor(start_cursor=cursor)

    count = 0
    empty = True
    results = query.fetch(limit=batch_size)

    if results:
        empty = False
        if delete:
            key_count = len(results)
            db.delete(results)
            count += key_count
        else:
            for result in results:
                model_map_fn(result)
                count += 1

    cursor = None
    if not empty:
        cursor = query.cursor()
    return count, cursor


def _get_entity_dict(model, privacy_transform_fn):
    key = model.safe_key(model.key(), privacy_transform_fn)

    if privacy_transform_fn is not _IDENTITY_TRANSFORM:
        model = model.for_export(privacy_transform_fn)

    entity_dict = transforms.entity_to_dict(model, force_utf_8_encoding=True)
    entity_dict['key.name'] = unicode(key.name())

    return entity_dict


@_retry(message='Upload failed; retrying')
def _put(context, content, path, is_draft, force_overwrite):
    path = os.path.join(appengine_config.BUNDLE_ROOT, path)
    if force_overwrite and context.fs.impl.isfile(path):
        _LOG.info('File %s found on target system; forcing overwrite', path)
        context.fs.impl.delete(path)
    context.fs.impl.non_transactional_put(
        os.path.join(appengine_config.BUNDLE_ROOT, path), content,
        is_draft=is_draft)


def _raw_input(message):
    """raw_input wrapper scoped to the module for swapping during tests."""
    return raw_input(message)


def _run_custom(parsed_args):
    try:
        module_name, job_class_name = parsed_args.type.rsplit('.', 1)
        module = __import__(module_name, globals(), locals(), [job_class_name])
        job_class = getattr(module, job_class_name)
        assert issubclass(job_class, etl_lib.Job)
        job = job_class(parsed_args)
    except:  # Any error means death. pylint: disable-msg=bare-except
        _die(
            'Unable to import and instantiate %s, or not of type %s' % (
                parsed_args.type, etl_lib.Job.__name__),
            with_trace=True)
    job.run()


def _upload(upload_type, archive_path, course_url_prefix, force_overwrite):
    _LOG.info(
        'Processing course with URL prefix %s from archive path %s',
        course_url_prefix, archive_path)
    context = _get_context_or_die(course_url_prefix)
    if upload_type == _TYPE_COURSE:
        _upload_course(
            context, archive_path, course_url_prefix, force_overwrite)
    elif upload_type == _TYPE_DATASTORE:
        _upload_datastore()


def _upload_course(context, archive_path, course_url_prefix, force_overwrite):
    if not _context_is_for_empty_course(context) and not force_overwrite:
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
            entity.is_draft, force_overwrite)
        count += 1
        _LOG.info('Uploaded ' + external_path)
    _clear_course_cache(context)
    _LOG.info(
        'Done; %s entit%s uploaded', count, 'y' if count == 1 else 'ies')


def _upload_datastore():
    """Stub for possible future datastore entity uploader."""
    raise NotImplementedError


def _validate_arguments(parsed_args):
    """Validate parsed args for additional constraints."""
    if (parsed_args.mode in {_MODE_DOWNLOAD, _MODE_UPLOAD}
        and not parsed_args.archive_path):
        _die('--archive_path missing')
    if parsed_args.batch_size < 1:
        _die('--batch_size must be a positive value')
    if (parsed_args.mode == _MODE_DOWNLOAD and
        os.path.exists(parsed_args.archive_path)):
        _die(
            'Cannot download to archive path %s; file already exists' % (
                parsed_args.archive_path))
    if parsed_args.disable_remote and parsed_args.mode != _MODE_RUN:
        _die('--disable_remote supported only if mode is ' + _MODE_RUN)
    if parsed_args.force_overwrite and not (
            parsed_args.mode == _MODE_UPLOAD and
            parsed_args.type == _TYPE_COURSE):
        _die(
            '--force_overwrite supported only if mode is %s and type is %s' % (
                _MODE_UPLOAD, _TYPE_COURSE))
    if parsed_args.privacy and not (
            parsed_args.mode == _MODE_DOWNLOAD and
            parsed_args.type == _TYPE_DATASTORE):
        _die(
            '--privacy supported only if mode is %s and type is %s' % (
                _MODE_DOWNLOAD, _TYPE_DATASTORE))
    if parsed_args.privacy_secret and not (
            parsed_args.mode == _MODE_DOWNLOAD and
            parsed_args.type == _TYPE_DATASTORE and parsed_args.privacy):
        _die(
            '--privacy_secret supported only if mode is %s, type is %s, and '
            '--privacy is passed' % (_MODE_DOWNLOAD, _TYPE_DATASTORE))


def _write_model_to_json_file(json_file, privacy_transform_fn, model):
    entity_dict = _get_entity_dict(model, privacy_transform_fn)
    json_file.write(transforms.dict_to_json(entity_dict, None))


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
    _import_entity_modules()

    if not environment_class:
        environment_class = remote.Environment

    privacy_secret = _get_privacy_secret(parsed_args.privacy_secret)
    privacy_transform_fn = _get_privacy_transform_fn(
        parsed_args.privacy, privacy_secret)

    _LOG.info('Mode is %s', parsed_args.mode)
    _LOG.info(
        'Target is url %s from application_id %s on server %s',
        parsed_args.course_url_prefix, parsed_args.application_id,
        parsed_args.server)

    if not parsed_args.disable_remote:
        environment_class(
            parsed_args.application_id, parsed_args.server).establish()

    _force_config_reload()

    if parsed_args.mode == _MODE_DELETE:
        _delete(
            parsed_args.course_url_prefix, parsed_args.type,
            parsed_args.batch_size)
    elif parsed_args.mode == _MODE_DOWNLOAD:
        _download(
            parsed_args.type, parsed_args.archive_path,
            parsed_args.course_url_prefix, parsed_args.datastore_types,
            parsed_args.batch_size, privacy_transform_fn)
    elif parsed_args.mode == _MODE_RUN:
        _run_custom(parsed_args)
    elif parsed_args.mode == _MODE_UPLOAD:
        _upload(
            parsed_args.type, parsed_args.archive_path,
            parsed_args.course_url_prefix, parsed_args.force_overwrite)


if __name__ == '__main__':
    main(PARSER.parse_args())
