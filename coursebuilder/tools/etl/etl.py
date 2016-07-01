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

"""Extract-transform-load utility.

There are four features:

1. Download and upload of Course Builder 1.3+ data:

$ python etl.py download course /cs101 server.appspot.com archive.zip

This will result in a file called archive.zip that contains the files that make
up the Course Builder 1.3+ course found at the URL /cs101 on the deployment
running on the server named server.appspot.com. archive.zip will contain assets
and data files from the course along with a manifest.json enumerating them. The
format of archive.zip will change and should not be relied upon.

For upload of course and related data

$ python etl.py upload course /cs101 server.appspot.com \
    --archive_path archive.zip

2. Download of datastore entities. This feature is experimental.

$ python etl.py download datastore /cs101 server.appspot.com \
    --archive_path archive.zip --datastore_types model1,model2

This will result in a file called archive.zip that contains a dump of all model1
and model2 instances found in the specified course, identified as above. The
archive will contain serialized data along with a manifest. The format of
archive.zip will change and should not be relied upon.

By default, all data types are downloaded.  You can specifically select or
skip specific types using the --datastore_types and --exclude_types flags,
respectively.

3. Upload of datastore entities.  This feature is experimental.

$ python etl.py upload datastore /cs101 server.apppot.com \
    --archive_path archive.zip

Uploads should ideally be (but are not required to be) done to courses that
are not available to students and which are not actively being edited by
admins.  To upload to a course, it must first exist.  You can create a blank
new course using the administrator UI.  Note that keys and fields that use PII
are obscured during download if --privacy_secret is used, and not obscured if
not.  Uploading of multiple downloads to the same course is supported, but
for encoded references to work, all uploads must have been created with
the same --privacy_secret (or all with no secret).

Other flags for uploading are recommended:
    --resume:  Use this flag to permit an upload to resume where it left off.
    --force_overwrite:  Unless this flag is specified, every entity to be
      uploaded is checked to see whether an entity with this key already
      exists in the datastore.  This takes substantial additional time.
      If you are sure that there will not be any overlap between existing data
      and uploaded data, use of this flag is strongly recommended.
    --batch_size=<NNN>:  Set this to larger values to group uploaded entities
      together for efficiency.  Higher values help, but give diminishing
      returns.  Start at around 100.
    --datastore_types:  and/or --exclude_types   By default, all types in the
      specified .zip file are uploaded.  You may select or ignore specific types
      with these flags, respectively.

      Data extracted from courses running an older version of CourseBuilder
      may contain entities of types that no longer exist in the code base of a
      more-recent CourseBuilder installation.  Depending on the nature of the
      change, this extra data may simply be no longer needed.  Conversely, the
      data may be crucial to the correct operation of an older, un-upgraded
      installation, and will simply not work with a newer version of code.
      Using a specific set of types can permit upload of the entities that are
      still recognized.  Operation of CourseBuilder with the partial data may
      well be compromised for some or all functionality; it is safest to
      upload the data to a blank course and experiment before uploading
      incomplete data to a production instance.

For example, you may wish to upload to a local instance to test things out
before uploading to a production installation:

./scripts/etl.sh --force_overwrite --batch_size=100 --resume \
  --exclude_types=RootUsageEntity,KeyValueEntity,DefinitionEntity,UsageEntity \
  --archive_path my_archive_file.zip \
  upload datastore /new_course localhost

4. Deletion of all datastore entities in a single course. Delete of the course
   itself not supported. To run:

$ python etl.py delete datastore /cs101 server.appspot.com

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

5. Execution of custom jobs.

$ python etl.py run path.to.my.Job /cs101 server.appspot.com \
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

     Their locations in the supported App Engine SDK are

     <sdk_path>/lib/fancy_urllib
     <sdk_path>/lib/jinja2-2.6
     <sdk_path>/lib/webapp2-2.5.2
     <sdk_path>/lib/webob-1.2.3

     where <sdk_path> is the absolute path of the App Engine SDK installed by
     scripts/common.sh.
  4. If you are running a custom job, the absolute paths of all code required
     by your custom job, unless covered above.

When running etl.py against a remote endpoint, you must authenticate via OAuth2.
If you have not authenticated, you will get an error with instructions on how to
authenticate.

Pass --help for additional usage information.
"""

__author__ = [
    'johncox@google.com (John Cox)',
]

import argparse
import functools
import logging
import os
import random
import re
import shutil
import sys
import time
import traceback
import zipfile
import yaml


# Placeholders for modules we'll import after setting up sys.path. This allows
# us to avoid lint suppressions at every callsite.
appengine_config = None
common_utils = None
config = None
courses = None
crypto = None
datastore_types = None
db = None
entity_transforms = None
etl_lib = None
memcache = None
metadata = None
remote = None
sites = None
transforms = None
vfs = None


# String. Prefix for files stored in an archive.
_ARCHIVE_PATH_PREFIX = 'files'
# String. Prefix for models stored in an archive.
_ARCHIVE_PATH_PREFIX_MODELS = 'models'
# String. End of the path to course.json in an archive.
_COURSE_JSON_PATH_SUFFIX = 'data/course.json'
# String. End of the path to course.yaml in an archive.
_COURSE_YAML_PATH_SUFFIX = 'course.yaml'
# String. Message the user must type to confirm datastore deletion.
_DELETE_DATASTORE_CONFIRMATION_INPUT = 'YES, DELETE'
# Default value of --port passed to the dev appserver. Keep this in sync
# with the value in scripts/parse_start_args.sh's CB_PORT.
_DEV_APPSERVER_DEFAULT_PORT = 8081
# List of types which are not to be downloaded.  These are types which
# are either known to be transient, disposable state classes (e.g.,
# map/reduce's "_AE_... classes), or legacy types no longer required.
_EXCLUDE_TYPES = set([
    # Map/reduce internal types:
    '_AE_Barrier_Index',
    '_AE_MR_MapreduceState',
    '_AE_MR_OutputFile',
    '_AE_MR_ShardState',
    '_AE_MR_TaskPayload',
    '_AE_Pipeline_Barrier',
    '_AE_Pipeline_Record',
    '_AE_Pipeline_Slot',
    '_AE_Pipeline_Status',
    '_AE_TokenStorage_',
    # AppEngine internal background jobs queue
    '_DeferredTaskEntity',
    ])
# Function that takes one arg and returns it.
_IDENTITY_TRANSFORM = lambda x: x
# Regex. Format of __internal_names__ used by datastore kinds.
_INTERNAL_DATASTORE_KIND_REGEX = re.compile(r'^__.*__$')
# Names of fields in row which should be ignored when importing datastore.
_KEY_FIELDS = set(['key.id', 'key.name', 'key'])
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
# List of modes where --force_overwrite is supported:
_FORCE_OVERWRITE_MODES = [_MODE_DOWNLOAD, _MODE_UPLOAD]
# Int. The number of times to retry remote_api calls.
_RETRIES = 3
# String. Identifier for type corresponding to course definition data.
_TYPE_COURSE = 'course'
# String. Identifier for type corresponding to datastore entities.
_TYPE_DATASTORE = 'datastore'
# Number of items upon which to emit upload rate statistics.
_UPLOAD_CHUNK_SIZE = 1000
# We support .zip files as one archive format.
ARCHIVE_TYPE_ZIP = 'zip'
# We support plain UNIX directory structure as an archive format
ARCHIVE_TYPE_DIRECTORY = 'directory'
# The list of all supported archive formats
_ARCHIVE_TYPES = [
    ARCHIVE_TYPE_ZIP,
    ARCHIVE_TYPE_DIRECTORY,
]
# Name of flag used to gate access to less-generally-useful features.
INTERNAL_FLAG_NAME = '--internal'


def create_args_parser():
    # Command-line argument configuration.
    parser = argparse.ArgumentParser()
    parser.add_argument(
        'mode', choices=_MODES,
        help='Indicates the kind of operation we are performing', type=str)
    parser.add_argument(
        'type',
        help=(
            'Type of entity to process. If mode is %s or %s, should be one of '
            '%s or %s. If mode is %s, should be an importable dotted path to '
            'your etl_lib.Job subclass') % (
                _MODE_DOWNLOAD, _MODE_UPLOAD, _TYPE_COURSE, _TYPE_DATASTORE,
                _MODE_RUN),
        type=str)
    parser.add_argument(
        'course_url_prefix',
        help=(
            "URL prefix of the course you want to download (e.g. '/foo' in "
            "'course:/foo:/directory:namespace'"), type=str)
    parser.add_argument(
        'server',
        help=(
            'The full name of the source application to read from (e.g. '
            'myapp.appspot.com)'), type=str)
    parser.add_argument(
        '--archive_path',
        help=(
            'Absolute path of the archive file to read or write; required if '
            'mode is %s or %s' % (_MODE_DOWNLOAD, _MODE_UPLOAD)), type=str)
    parser.add_argument(
        '--batch_size',
        help='Number of results to attempt to retrieve per batch',
        default=20, type=int)
    parser.add_argument(
        '--datastore_types', default=[],
        help=(
            'When type is "%s", comma-separated list of datastore model types '
            'to process; all models are processed by default' %
            _TYPE_DATASTORE),
        type=lambda s: s.split(','))
    parser.add_argument(
        '--exclude_types', default=[],
        help=(
            'When type is "%s", comma-separated list of datastore model types '
            'to exclude from processing' % _TYPE_DATASTORE),
        type=lambda s: s.split(','))
    parser.add_argument(
        '--disable_remote', action='store_true',
        help=(
            'If mode is %s, pass this flag to skip authentication and remote '
            'environment setup. Should only pass for jobs that run entirely '
            'locally and do not require RPCs') % _MODE_RUN)
    parser.add_argument(
        '--force_overwrite', action='store_true',
        help=(
            'If mode is download, overwriting of local .zip files is permitted.'
            'If mode is upload,  forces overwrite of entities '
            'on the target system that are also present in the archive. Note '
            'that this operation is dangerous and may result in data loss.'))
    parser.add_argument(
        '--port', default=_DEV_APPSERVER_DEFAULT_PORT,
        help=(
            'If running against localhost, this is the port remote API '
            'requests are sent to. Default is %s. Ignored if running against '
            'non-localhost deployments. Must be the value passed to '
            'dev_appserver.py via --port.' % (_DEV_APPSERVER_DEFAULT_PORT)))
    parser.add_argument(
        '--resume', action='store_true',
        help=(
            'Setting this flag indicates that you are starting or resuming '
            'an upload or download.  If uploading, only use this flag when you '
            'are uploading to a course that had no prior data, or conflicts '
            'may occur.  When downloading, don\'t change the set of types '
            'being downloaded when re-trying after a partial failure.  '))
    parser.add_argument(
        '--job_args', default=[],
        help=(
            'If mode is %s, string containing args delegated to etl_lib.Job '
            'subclass') % _MODE_RUN, type=lambda s: s.split())
    parser.add_argument(
        '--log_level', choices=_LOG_LEVEL_CHOICES,
        help='Level of logging messages to emit', default='INFO',
        type=lambda s: s.upper())
    parser.add_argument(
        '--privacy', action='store_true',
        help=(
            "When mode is '%s' and type is '%s', passing this flag will strip "
            "or obfuscate information that can identify a single user" % (
                _MODE_DOWNLOAD, _TYPE_DATASTORE)))
    parser.add_argument(
        '--privacy_secret',
        help=(
            "When mode is '%s', type is '%s', and --privacy is passed,  pass "
            "this secret to have user ids transformed with it rather than with "
            "random bits") % (_MODE_DOWNLOAD, _TYPE_DATASTORE), type=str)
    parser.add_argument(
        '--verbose', action='store_true',
        help='Tell about each item uploaded/downloaded.')
    parser.add_argument(
        INTERNAL_FLAG_NAME, action='store_true',
        help=('Enable control flags needed only by developers.  '
              'Use %s --help to see documentation on these extra flags.' %
              INTERNAL_FLAG_NAME))
    return parser


def add_internal_args_support(parser):
    """Enable features only suitable for CourseBuilder developers.

    This is present as a public function so that functional tests and utilities
    that are only for developers to enable internal-only features from Python
    code directly.
    """

    parser.add_argument(
        '--archive_type', default='zip', choices=_ARCHIVE_TYPES,
        help=(
            'By default, uploads and downloads are done using a single .zip '
            'for the archived form of the data.  This is convenient, as only '
            'that single file needs to be retained and protected.  When making '
            'functional tests that depend on a constellation of several entity '
            'types in complex relationships, it is often much more convenient '
            'to create the entities by direct interaction with CourseBuilder, '
            'rather than writing code to achieve the same effect.  Saving this '
            'data out for later use in unit tests is easily accomplished via '
            'ETL.  However, as code changes, modifications to the stored test '
            'values is occasionally necessary.  Rather than store the test '
            'values as a monolithic opaque binary blob (hard to edit), '
            'one may specify --archive_type=directory. This treats the '
            '--archive_path argument as a directory, and stores individual '
            'files in that directory.'))
    parser.add_argument(
        '--no_static_files', action='store_true',
        help=(
            'Do not upload/download static file content, except for special '
            'files %s and %s containing the course.  Useful for saving space '
            'when generating test-case data.' % (
                _COURSE_YAML_PATH_SUFFIX, _COURSE_JSON_PATH_SUFFIX)))


def create_configured_args_parser(argv):
    """Creates a parser and configures it for internal use if needed."""
    parser = create_args_parser()
    if INTERNAL_FLAG_NAME in argv:
        add_internal_args_support(parser)

    return parser


def _init_archive(path, archive_type=ARCHIVE_TYPE_ZIP):
    if archive_type == ARCHIVE_TYPE_ZIP:
        return _ZipArchive(path)
    elif archive_type == ARCHIVE_TYPE_DIRECTORY:
        return _DirectoryArchive(path)
    else:
        raise ValueError('Archive type "%s" not one of "zip", "directory".' %
                         archive_type)


class _AbstractArchive(object):
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

    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception_value, exception_traceback):
        pass

    @classmethod
    def get_external_path(cls, internal_path, prefix=_ARCHIVE_PATH_PREFIX):
        """Gets external path string from results of cls.get_internal_path."""
        _prefix = prefix + os.sep
        assert internal_path.startswith(_prefix)
        return internal_path.split(_prefix)[1]

    @classmethod
    def get_internal_path(cls, external_path, prefix=_ARCHIVE_PATH_PREFIX):
        """Get path string used in the archive from an external path string.

        Generates the path used within an archive for an asset. All assets
        (meaning all archive contents except the manifest file) must have
        their paths generated this way, and those paths must be re-translated to
        external paths via cls.get_external_path before use with systems
        external to the archive file.

        Args:
            external_path: string. Path to generate an internal archive path
                from.
            prefix: string. Prefix to base the path on.

        Returns:
            String. Internal archive path.
        """
        assert not external_path.startswith(prefix)
        return os.path.join(
            prefix, _remove_bundle_root(external_path))

    def add(self, filename, contents):
        """Adds contents to the archive.

        Args:
            filename: string. Path of the contents to add.
            contents: bytes. Contents to add.
        """
        raise NotImplementedError()

    def add_local_file(self, local_filename, internal_filename):
        """Adds a file from local disk to the archive.

        Args:
            local_filename: string. Path on disk of file to add.
            internal_filename: string. Internal archive path to write to.
        """
        raise NotImplementedError()

    def close(self):
        """Closes archive and test for integrity; must close before read."""
        raise NotImplementedError()

    def get(self, path):
        """Return the raw bytes of the archive entity found at path.

        Returns None if path is not in the archive.

        Args:
            path: string. Path of file to retrieve from the archive.

        Returns:
            Bytes of file contents.
        """
        raise NotImplementedError()

    def open(self, mode):
        """Opens archive in the mode given by mode string ('r', 'w', 'a')."""
        raise NotImplementedError()

    @property
    def manifest(self):
        """Returns the archive's manifest."""
        content = self.get(_MANIFEST_FILENAME)
        return _Manifest.from_json(content) if content else None

    @property
    def path(self):
        return self._path

    def listdir(self, path):
        """Returns a list of names in a directory, excluding . and .."""
        raise NotImplementedError()


class _ZipArchive(_AbstractArchive):

    def __init__(self, path):
        super(_ZipArchive, self).__init__(path)
        self._zipfile = None

    def __exit__(self, exception_type, exception_value, exception_traceback):
        if self._zipfile:
            self.close()

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
        self._zipfile = zipfile.ZipFile(self._path, mode, allowZip64=True)

    def listdir(self, path):
        ret = []
        names = self._zipfile.namelist()
        for name in names:
            if name.startswith(path):
                name = name.replace(path, '', 1)
                name = name.lstrip('/')
                name = name.split('/')[0]
                ret.append(name)
        return ret


class _DirectoryArchive(_AbstractArchive):

    def _ensure_directory(self, filename):
        dir_path = os.path.join(self.path, os.path.dirname(filename))
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)

    def add(self, filename, contents):
        self._ensure_directory(filename)
        with open(os.path.join(self.path, filename), 'wb') as fp:
            fp.write(contents)

    def add_local_file(self, local_filename, filename):
        self._ensure_directory(filename)
        shutil.copyfile(local_filename, os.path.join(self.path, filename))

    def close(self):
        pass

    def get(self, filename):
        path = os.path.join(self.path, filename)
        if not os.path.exists(path):
            return None
        with open(path, 'rb') as fp:
            return fp.read()

    def open(self, mode):
        if mode in ('w', 'a'):
            if not os.path.exists(self.path):
                os.makedirs(self.path)
        elif not os.path.isdir(self.path):
            raise ValueError('"%s" is not a directory.' % self.path)

    def listdir(self, path):
        path = os.path.join(self.path, path)
        return os.listdir(path) if os.path.exists(path) else []



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
    """Asks user to confirm action."""
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


def _delete(params):
    """Deletes desired object."""
    context = _get_context_or_die(params.course_url_prefix)
    with common_utils.Namespace(context.get_namespace_name()):
        if params.type == _TYPE_COURSE:
            _delete_course()
        elif params.type == _TYPE_DATASTORE:
            _delete_datastore(context, params.batch_size)


def _delete_course():
    """Stub for possible future course deleter."""
    raise NotImplementedError


def _delete_datastore(context, batch_size):
    """Deletes datastore content."""
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


def _download(params):
    """Validates and dispatches to a specific download method."""
    archive_path = os.path.abspath(params.archive_path)
    context = _get_context_or_die(params.course_url_prefix)
    course = etl_lib.get_course(context)
    archive, already_done_names, manifest = _open_archive_for_write(
        context, course, archive_path, params)
    with archive:
        with common_utils.Namespace(context.get_namespace_name()):
            if params.type == _TYPE_COURSE:
                _download_course(context, course, params, archive,
                                 already_done_names, manifest)
            elif params.type == _TYPE_DATASTORE:
                _download_datastore(context, course, params, archive,
                                    already_done_names, manifest)
    _LOG.info('Done; archive saved to ' + archive.path)


def _open_archive_for_write(context, course, archive_path, params):
    archive = _init_archive(
        archive_path, vars(params).get('archive_type', ARCHIVE_TYPE_ZIP))
    already_done_names = set()
    manifest = None
    if params.resume:
        archive.open('a')
        model_names = archive.listdir('models')
        already_done_names.update([n.replace('.json', '') for n in model_names])
        manifest = archive.manifest
    else:
        archive.open('w')

    if not manifest:
        manifest = _Manifest(context.raw, course.version)
    return archive, already_done_names, manifest


def _download_course(context, course, params, archive, already_done_names,
                     manifest):
    """Downloads course content."""
    if course.version < courses.COURSE_MODEL_VERSION_1_3:
        _die(
            'Cannot export course made with Course Builder version < %s' % (
                courses.COURSE_MODEL_VERSION_1_3))

    _LOG.info('Processing course with URL prefix ' + params.course_url_prefix)
    datastore_files = set(_list_all(context))
    all_files = set(_filter_filesystem_files(_list_all(
        context, include_inherited=True)))
    filesystem_files = all_files - datastore_files

    if vars(params).get('no_static_files', False):
        # pylint: disable=protected-access
        always_allowed_files = set([
            context.fs.impl._physical_to_logical(_COURSE_JSON_PATH_SUFFIX),
            context.fs.impl._physical_to_logical(_COURSE_YAML_PATH_SUFFIX)])
        filesystem_files.intersection_update(always_allowed_files)
        datastore_files.intersection_update(always_allowed_files)

    _LOG.info('Adding files from datastore')
    for external_path in datastore_files:
        internal_path = _AbstractArchive.get_internal_path(external_path)
        if params.verbose:
            _LOG.info('Adding ' + internal_path)
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
            internal_path = _AbstractArchive.get_internal_path(external_path)
            if params.verbose:
                _LOG.info('Adding ' + internal_path)
            archive.add(internal_path, f.read())
            manifest.add(_ManifestEntity(internal_path, False))

    _LOG.info('Adding dependencies from datastore')
    all_entities = list(courses.COURSE_CONTENT_ENTITIES) + list(
        courses.ADDITIONAL_ENTITIES_FOR_COURSE_IMPORT)
    type_names = set([entity.__name__ for entity in all_entities])
    _download_types(archive, manifest, type_names, already_done_names,
                    params.batch_size, _IDENTITY_TRANSFORM)

def _download_datastore(context, course, params, archive, already_done_types,
                        manifest):
    """Downloads datastore content."""
    available_types = set(_get_datastore_kinds())
    type_names = params.datastore_types
    if not type_names:
        type_names = available_types
    requested_types = (
        set(type_names) - set(params.exclude_types) - set(_EXCLUDE_TYPES))
    missing_types = requested_types - available_types
    if missing_types:
        _die(
            'Requested types not found: %s%sAvailable types are: %s' % (
                ', '.join(missing_types), os.linesep,
                ', '.join(available_types)))

    privacy_secret = _get_privacy_secret(params.privacy_secret)
    privacy_transform_fn = _get_privacy_transform_fn(
        params.privacy, privacy_secret)
    found_types = (requested_types & available_types)
    _download_types(archive, manifest, found_types, already_done_types,
                    params.batch_size, privacy_transform_fn)


def _download_types(archive, manifest, type_names, already_done_names,
                    batch_size, transform):
    for type_name in type_names & already_done_names:
        _LOG.info('Skipping already-downloaded type %s', type_name)
    type_names -= already_done_names
    _verify_downloadability(type_names)
    _finalize_manifest(type_names, manifest, archive)
    for type_name in sorted(type_names):
        _download_type(archive, manifest, type_name, batch_size, transform)


def _verify_downloadability(type_names):
    problems = []
    for type_name in type_names:
        try:
            cls = db.class_for_kind(type_name)
            if not hasattr(cls, 'safe_key'):
                problems.append(
                    'Class %s has no safe_key method.  This probably means '
                    'it is non-permanent (e.g., job control for map/reduce), '
                    'or similar internal state.  Consider adding this type '
                    'to the permanent exclusions list in tools/etl/etl.py. ' %
                    type_name)
        except Exception:  # pylint: disable=broad-except
            problems.append(
                'Could not locate the Python code for the type %s.' % type_name)

        if problems:
            for problem in problems:
                logging.critical(problem)
            _die('Remove these types from the --datastore_types list, '
                 'or add them to the --exclude_types list.')


def _finalize_manifest(type_names, manifest, archive):
    if archive.manifest:
        return  # We are resuming; manifest has already been written.

    for type_name in type_names:
        json_name = type_name + '.json'
        internal_path = _AbstractArchive.get_internal_path(
            json_name, prefix=_ARCHIVE_PATH_PREFIX_MODELS)
        manifest.add(_ManifestEntity(internal_path, False))
    archive.add(_MANIFEST_FILENAME, str(manifest))


def _download_type(
    archive, manifest, model_class, batch_size, privacy_transform_fn):
    """Downloads a set of files and adds them to the archive."""

    json_path = os.path.join(
        os.path.dirname(archive.path), '%s.json' % model_class)

    _LOG.info(
        'Adding entities of type %s to temporary file %s',
        model_class, json_path)
    json_file = transforms.JsonFile(json_path)
    json_file.open('w')
    model_map_fn = functools.partial(
        _write_model_to_json_file, json_file, privacy_transform_fn)
    _process_models(
        db.class_for_kind(model_class), batch_size,
        model_map_fn=model_map_fn)
    json_file.close()
    internal_path = _AbstractArchive.get_internal_path(
        os.path.basename(json_file.name), prefix=_ARCHIVE_PATH_PREFIX_MODELS)

    _LOG.info('Adding %s to archive', internal_path)
    archive.add_local_file(json_file.name, internal_path)

    _LOG.info('Removing temporary file ' + json_file.name)
    os.remove(json_file.name)


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
        return functools.partial(crypto.hmac_sha_2_256_transform,
                                 privacy_secret)


def _get_privacy_secret(privacy_secret):
    """Gets the passed privacy secret (or 128 random bits if None)."""
    secret = privacy_secret
    if secret is None:
        secret = random.getrandbits(128)
    return secret


def _set_env_vars_from_app_yaml():
    """Read and set environment from app.yaml.

    This is to set up the GCB_REGISTERED_MODULES and
    GCB_REGISTERED_MODULES_CUSTOM vars so that main's call to
    appengine_config.import_and_enable_modules() will work properly.
    """

    from google.appengine.api import appinfo_includes
    import appengine_config  # pylint: disable=redefined-outer-name
    cb_home = os.environ.get(
        'COURSEBUILDER_HOME', appengine_config.BUNDLE_ROOT)
    app_yaml = appinfo_includes.Parse(
        open(os.path.join(cb_home, 'app.yaml')), open)
    for name, value in app_yaml.env_variables.items():
        os.environ[name] = value


def _import_entity_modules():
    """Import all entity type classes.

    We need to import main.py to make sure all known entity types are imported
    by the time the ETL code runs. If a transitive closure of main.py imports
    does not import all required classes, import them here explicitly.
    """

    # pylint: disable=global-variable-not-assigned,
    # pylint: disable=redefined-outer-name,unused-variable
    try:
        import main
    except ImportError, e:
        _die((
            'Unable to import required modules; see tools/etl/etl.py for '
            'docs.'), with_trace=True)


def _import_modules_into_global_scope():
    """Import helper; run after _set_up_sys_path() for imports to resolve."""
    # pylint: disable=global-variable-not-assigned,
    # pylint: disable=redefined-outer-name,unused-variable
    global appengine_config
    global memcache
    global datastore_types
    global db
    global entities
    global entity_transforms
    global metadata
    global common_utils
    global config
    global courses
    global crypto
    global models
    global sites
    global transforms
    global vfs
    global etl_lib
    global remote
    try:
        import appengine_config
        from google.appengine.api import memcache
        from google.appengine.api import datastore_types
        from google.appengine.ext import db
        from google.appengine.ext.db import metadata
        from common import crypto
        from common import utils as common_utils
        from models import config
        from controllers import sites
        from models import courses
        from models import entities
        from models import entity_transforms
        from models import models
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
                # pylint: disable=broad-except
                except Exception as e:
                    if message:
                        _LOG.info(message)
                    failures += 1
                    if failures == times:
                        traceback.print_exc()  # Show origin of failure
                        raise e

        return wrapped
    return decorator


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
    entity_dict['key.id'] = key.id()

    return entity_dict


@_retry(message='Upload failed; retrying')
def _put(context, content, path, is_draft, force_overwrite, verbose):
    path = os.path.join(appengine_config.BUNDLE_ROOT, path)
    description = _remove_bundle_root(path)
    do_put = False
    if context.fs.impl.isfile(path) and not path.endswith('/course.yaml'):
        if force_overwrite:
            _LOG.info('Overriding file %s', description)
            context.fs.impl.delete(path)
            do_put = True
        elif verbose:
            _LOG.info('Not replacing existing file %s', description)
    else:
        do_put = True
        if verbose:
            _LOG.info('Uploading file %s', description)

    if do_put:
        context.fs.impl.non_transactional_put(
            os.path.join(appengine_config.BUNDLE_ROOT, path), content.read(),
            is_draft=is_draft)


def _raw_input(message):
    """raw_input wrapper scoped to the module for swapping during tests."""
    return raw_input(message)


def _run_custom(parsed_args):
    """Runs desired command."""
    try:
        module_name, job_class_name = parsed_args.type.rsplit('.', 1)
        module = __import__(module_name, globals(), locals(), [job_class_name])
        job_class = getattr(module, job_class_name)
        assert issubclass(job_class, etl_lib.Job)
        job = job_class(parsed_args)
    except:  # Any error means death. pylint: disable=bare-except
        _die(
            'Unable to import and instantiate %s, or not of type %s' % (
                parsed_args.type, etl_lib.Job.__name__),
            with_trace=True)
    job.run()
    _LOG.info('Completed job %s', job_class.__name__)


def _upload(params):
    _LOG.info('Processing course with URL prefix %s from archive path %s',
              params.course_url_prefix, params.archive_path)
    context = _get_context_or_die(params.course_url_prefix)
    all_entities = list(courses.COURSE_CONTENT_ENTITIES) + list(
        courses.ADDITIONAL_ENTITIES_FOR_COURSE_IMPORT)
    with common_utils.Namespace(context.get_namespace_name()):
        if params.type == _TYPE_COURSE:
            _upload_course(context, params)
            type_names = [x.__name__ for x in all_entities]
            _upload_datastore(params, type_names)
        elif params.type == _TYPE_DATASTORE:
            _upload_datastore(params, params.datastore_types)
        sites.ApplicationContext.clear_per_process_cache()


def _can_upload_entity_to_course(entity):
    """Checks if a file can be uploaded to course."""
    head, tail = os.path.split(entity.path)
    if head == _ARCHIVE_PATH_PREFIX_MODELS and tail == _COURSE_YAML_PATH_SUFFIX:
        return True
    return head != _ARCHIVE_PATH_PREFIX_MODELS


def _upload_course(context, params):
    """Uploads course data."""
    if not _context_is_for_empty_course(context) and not params.force_overwrite:
        _die('Cannot upload to non-empty course with course_url_prefix %s.  '
             'You can override this behavior via the --force_overwrite flag.' %
             params.course_url_prefix)

    archive = _init_archive(params.archive_path,
                            vars(params).get('archive_type', ARCHIVE_TYPE_ZIP))
    try:
        archive.open('r')
    except IOError:
        _die('Cannot open archive_path ' + params.archive_path)
    course_json = archive.get(
        _AbstractArchive.get_internal_path(_COURSE_JSON_PATH_SUFFIX))

    if course_json:
        try:
            courses.PersistentCourse13().deserialize(course_json)
        except (AttributeError, ValueError):
            _die((
                'Cannot upload archive at %s containing malformed '
                'course.json') % params.archive_path)

    course_yaml = archive.get(
        _AbstractArchive.get_internal_path(_COURSE_YAML_PATH_SUFFIX))
    if course_yaml:
        try:
            yaml.safe_load(course_yaml)
        except Exception:  # pylint: disable=broad-except
            _die((
                'Cannot upload archive at %s containing malformed '
                'course.yaml') % params.archive_path)

    files_filter = set()
    if vars(params).get('no_static_files', False):
        files_filter.add(_COURSE_JSON_PATH_SUFFIX)
        files_filter.add(_COURSE_YAML_PATH_SUFFIX)

    _LOG.info('Uploading files')
    count = 0
    for entity in archive.manifest.entities:
        if not _can_upload_entity_to_course(entity):
            _LOG.info('Skipping file ' + entity.path)
            continue
        if files_filter and entity.path in files_filter and params.verbose:
            _LOG.info('Skipping file ' + entity.path +
                      ' due to --no_static_files')
            continue
        external_path = _AbstractArchive.get_external_path(entity.path)
        _put(
            context, _ReadWrapper(archive.get(entity.path)), external_path,
            entity.is_draft, params.force_overwrite, params.verbose)
        count += 1
    _LOG.info('Uploaded %d files.', count)


def _get_classes_for_type_names(type_names):
    entity_classes = []
    any_problems = False
    for type_name in type_names:
        # TODO(johncox): Add class-method to troublesome types so they can be
        # regenerated from serialized ETL data.
        if type_name in ('Submission', 'Review', 'Notification', 'Payload'):
            any_problems = True
            _LOG.critical(
                'Cannot upload entities of type "%s". '
                'This type has a nontrivial constructor, and simply '
                'setting properties into the DB base object type is '
                'insufficient to correctly construct this type.', type_name)
            continue

        try:
            entity_class = db.class_for_kind(type_name)
            entity_classes.append(entity_class)
        except db.KindError:
            any_problems = True
            _LOG.critical(
                'Cannot upload entities of type "%s". '
                'The corresponding Python class for this entity type '
                'was not found in CourseBuilder.  This indicates a '
                'substantial incompatiblity in versions; some or all '
                'functionality may be affected.  Use the --exclude_types '
                'flag to skip entities of this type.', type_name)

        for field_name, prop in entity_class.properties().iteritems():
            if prop.data_type == datastore_types.Blob:
                _LOG.critical(
                    'Cannot upload entities of type %s, since the field '
                    '"%s" is a Blob field; this is not currently supported.',
                    type_name, field_name)
                any_problems = True
                break

    if any_problems:
        _die('Cannot proceed with upload in the face of these problems.')
    return entity_classes


def _determine_type_names(params, included_type_names, archive):
    included_type_names = set(included_type_names)
    excluded_type_names = set(params.exclude_types)
    zipfile_type_names = set()
    for entity in archive.manifest.entities:
        head, tail = os.path.split(entity.path)
        if head == _ARCHIVE_PATH_PREFIX_MODELS:
            zipfile_type_names.add(tail.replace('.json', ''))
    if not zipfile_type_names:
        _die('No entity types to upload found in archive file "%s"' %
             params.archive_path)
    if not included_type_names:
        included_type_names = zipfile_type_names

    for type_name in included_type_names - zipfile_type_names:
        _LOG.error('Included type "%s" not found in archive.', type_name)
    included_type_names &= zipfile_type_names
    for type_name in excluded_type_names - zipfile_type_names:
        _LOG.warning('Excluded type "%s" not found in archive.', type_name)
    excluded_type_names &= zipfile_type_names
    for type_name in excluded_type_names - included_type_names:
        _LOG.info('Redundant exclusion of type "%s" by mention in '
                  '--excluded_types and non-mention in '
                  'the --datastore_types list.', type_name)
    for type_name in included_type_names & excluded_type_names:
        _LOG.info('Excluding type "%s" from upload.', type_name)
    ret = included_type_names - excluded_type_names
    if not ret:
        _die('Command line flags specify that no entity types are '
             'eligible to be uploaded.  Available types are: %s' %
             ' '.join(sorted(zipfile_type_names)))
    return ret


def _upload_datastore(params, included_type_names):
    archive = _init_archive(params.archive_path,
                            vars(params).get('archive_type', ARCHIVE_TYPE_ZIP))
    try:
        archive.open('r')
    except IOError:
        _die('Cannot open archive path ' + params.archive_path)

    type_names = _determine_type_names(params, included_type_names, archive)
    entity_classes = _get_classes_for_type_names(type_names)
    total_count = 0
    total_start = time.time()
    for entity_class in entity_classes:
        _LOG.info('-------------------------------------------------------')
        _LOG.info('Adding entities of type %s', entity_class.__name__)

        # Get JSON contents from .zip file
        json_path = _AbstractArchive.get_internal_path(
            '%s.json' % entity_class.__name__,
            prefix=_ARCHIVE_PATH_PREFIX_MODELS)
        _LOG.info('Fetching data from .zip archive')
        json_text = archive.get(json_path)
        if not json_text:
            _LOG.info(
                'Unable to find data file %s for entity %s; skipping',
                json_path, entity_class.__name__)
            continue
        _LOG.info('Parsing data into JSON')
        json_object = transforms.loads(json_text)
        schema = (entity_transforms
                  .get_schema_for_entity(entity_class)
                  .get_json_schema_dict())
        total_count += _upload_entities_for_class(
            entity_class, schema, json_object['rows'], params)
    _LOG.info('Flushing all caches')
    memcache.flush_all()
    total_end = time.time()

    _LOG.info(
        'Done; %s entit%s uploaded in %d seconds', total_count,
        'y' if total_count == 1 else 'ies', int(total_end - total_start))


def _upload_entities_for_class(entity_class, schema, entities, params):
    num_entities = len(entities)
    i = 0
    is_first_batch_after_resume = False

    # Binary search to find first un-uploaded entity.
    if params.resume:
        _LOG.info('Resuming upload; searching for first non-uploaded entry.')
        start = 0
        end = num_entities
        while start < end:
            guess = (start + end) / 2
            if params.verbose:
                _LOG.info('Checking whether instance %d exists', guess)
            key, _ = _get_entity_key(entity_class, entities[guess])
            if db.get(key):
                start = guess + 1
            else:
                end = guess
        i = start

        # If we are doing things in batches, it is possible that the previous
        # batch only partially completed.  Experiments on a dev instance show
        # that partial writes do not proceed in the order the items are
        # supplied.  I see no reason to trust that production will be any
        # friendlier.  Check that there are no missed entities up to one
        # chunk back from where we are planning on restarting the upload.
        if params.batch_size > 1 and i > 0:
            start = max(0, i - params.batch_size)
            end = min(start + params.batch_size, len(entities))
            is_first_batch_after_resume = True
            existing = _find_existing_items(entity_class, entities, start, end)
            if None in existing:
                if start > 0:
                    _LOG.info('Previous chunk only partially completed; '
                              'backing up from found location by one full '
                              'chunk just in case.')
                i = start

        if i < num_entities:
            _LOG.info('Resuming upload at item number %d of %d.', i,
                      num_entities)
        else:
            _LOG.info('All %d entities already uploaded; skipping.',
                      num_entities)

    # Proceed to end of entities (starting from 0 if not resuming)
    # pylint: disable=protected-access
    progress = etl_lib._ProgressReporter(
        _LOG, 'Uploaded', entity_class.__name__, _UPLOAD_CHUNK_SIZE,
        len(entities) - i)
    if i < num_entities:
        _LOG.info('Starting upload of entities')
        while i < num_entities:
            quantity = _upload_batch(entity_class, schema, entities, i,
                                     is_first_batch_after_resume, params)
            progress.count(quantity)
            i += quantity
            is_first_batch_after_resume = False

        progress.report()
        _LOG.info('Upload of %s complete', entity_class.__name__)
    return progress.get_count()


def _find_existing_items(entity_class, entities, start, end):
    keys = []
    for i in xrange(start, end):
        key, _ = _get_entity_key(entity_class, entities[i])
        keys.append(key)
    return db.get(keys)


@_retry(message='Uploading batch of entities failed; retrying')
def _upload_batch(entity_class, schema, entities, start,
                  is_first_batch_after_resume, params):
    end = min(start + params.batch_size, len(entities))

    # See what elements we want to upload already exist in the datastore.
    if params.force_overwrite:
        existing = []
    else:
        existing = _find_existing_items(entity_class, entities, start, end)

    # Build up array of things to batch-put to DB.
    to_put = []
    for i in xrange(start, end):
        key, id_or_name = _get_entity_key(entity_class, entities[i])
        if params.force_overwrite:
            if params.verbose:
                _LOG.info('Forcing write of object #%d with key %s',
                          i, id_or_name)
        elif existing[i - start]:
            if is_first_batch_after_resume:
                if params.verbose:
                    _LOG.info('Not overwriting object #%d with key %s '
                              'written in previous batch which we are '
                              'now recovering.', i, id_or_name)
                continue
            else:
                _die('Object #%d of class %s with key %s already exists.' % (
                    i, entity_class.__name__, id_or_name))
        else:
            if params.verbose:
                _LOG.info('Adding new object #%d with key %s', i, id_or_name)
        to_put.append(_build_entity(entity_class, schema, entities[i], key))
    if params.verbose:
        _LOG.info('Sending batch of %d objects to DB', end - start)
    db.put(to_put)
    return end - start


def _get_entity_key(entity_class, entity):
    id_or_name = entity['key.id'] or entity['key.name']
    return db.Key.from_path(entity_class.__name__, id_or_name), id_or_name


def _build_entity(entity_class, schema, entity, key):
    kwargs = transforms.json_to_dict(entity, schema, permit_none_values=True)
    current_properties = entity_class.properties()
    for name in list(kwargs.keys()):
        if name not in current_properties:
            # Remove args for fields that used to be present (and were exported
            # when those fields were current), but are no longer supported.
            kwargs.pop(name)
        elif (isinstance(current_properties[name], db.ReferenceProperty) and
              isinstance(kwargs[name], basestring)):
            # Reference args need to be passed in as actual reference keys,
            # not stringified versions.
            kwargs[name] = entity_transforms.string_to_key(kwargs[name])
        # else:
        #     All other field types in kwargs do not need conversion beyond
        #     that already done by transforms.json_to_dict().
    return entity_class(key=key, **kwargs)


def _validate_arguments(parsed_args):
    """Validate parsed args for additional constraints."""
    if (parsed_args.mode in {_MODE_DOWNLOAD, _MODE_UPLOAD}
        and not parsed_args.archive_path):
        _die('--archive_path missing')
    if parsed_args.batch_size < 1:
        _die('--batch_size must be a positive value')
    if (parsed_args.mode == _MODE_DOWNLOAD and
        os.path.exists(parsed_args.archive_path) and
        not parsed_args.force_overwrite and
        not parsed_args.resume):
        _die(
            'Cannot download to archive path %s; file already exists' % (
                parsed_args.archive_path))
    if (parsed_args.disable_remote and
        parsed_args.mode != _MODE_RUN
        and not parsed_args.internal):
        _die('--disable_remote supported only if mode is ' + _MODE_RUN)
    if (parsed_args.force_overwrite and
        parsed_args.mode not in _FORCE_OVERWRITE_MODES):
        _die(
            '--force_overwrite supported only if mode is one of %s' % (
                ', '.join(_FORCE_OVERWRITE_MODES)))
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
    if parsed_args.resume and parsed_args.mode not in (_MODE_UPLOAD,
                                                       _MODE_DOWNLOAD):
        _die('--resume flag is only supported for uploading.')


def _write_model_to_json_file(json_file, privacy_transform_fn, model):
    entity_dict = _get_entity_dict(model, privacy_transform_fn)
    json_file.write(transforms.dict_to_json(entity_dict))


def main(parsed_args, testing=False):
    """Performs the requested ETL operation.

    Args:
        parsed_args: argparse.Namespace. Parsed command-line arguments.
    """
    _validate_arguments(parsed_args)
    _LOG.setLevel(parsed_args.log_level.upper())
    _import_modules_into_global_scope()
    _set_env_vars_from_app_yaml()
    _import_entity_modules()

    environment = remote.Environment(
        parsed_args.server, port=parsed_args.port, testing=testing)
    _LOG.info('Mode is %s', parsed_args.mode)
    _LOG.info('Target is: %s', environment.get_info())

    if not parsed_args.disable_remote:
        environment.establish()

    _force_config_reload()

    if parsed_args.mode == _MODE_DELETE:
        _delete(parsed_args)
    elif parsed_args.mode == _MODE_DOWNLOAD:
        _download(parsed_args)
    elif parsed_args.mode == _MODE_RUN:
        _run_custom(parsed_args)
    elif parsed_args.mode == _MODE_UPLOAD:
        _upload(parsed_args)


if __name__ == '__main__':
    main(create_configured_args_parser(sys.argv).parse_args())
