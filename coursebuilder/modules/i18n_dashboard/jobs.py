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

"""ETL jobs for the i18n dashboard."""

__author__ = [
    'johncox@google.com (John Cox)',
]

import logging
import os
import sys
from common import xcontent
from models import config
from models import courses
from models import models
from modules.i18n_dashboard import i18n_dashboard
from tools.etl import etl_lib

# Locale code for indicating that the locale in this file is not really
# the locale we should be using.  Instead, a locale to use must be
# provided via an ETL job flag or HTTP parameter.  Again, to keep Babel happy,
# this needs to be in Babel's supported set.  'gv' is for Manx, a Celtic
# locale, with somewhere between 100 and 1000 speakers, depending on when
# and how you ask, so pretty good odds we're not going to be actually using
# this for real courses.
AGNOSTIC_EXPORT_LOCALE = 'gv'

_LOG = logging.getLogger('coursebuilder.modules.i18n_dashboard.jobs')
_LOG.setLevel(logging.INFO)


def _die(message):
    _LOG.critical(message)
    sys.exit(1)


class _BaseJob(etl_lib.CourseJob):

    def _configure_parser(self):
        self.parser.add_argument(
            '--locales', default=[], type=lambda s: s.split(','),
            help='Comma-delimited list of locales (for example, "af") to '
            'export. If omitted, all locales except the default locale for the '
            'course will be exported. Passed locales must exist for the '
            'specified course.')
        self.parser.add_argument(
            '--suppress_nondefault_composable_tags', action='store_true',
            help='Use only very basic rules for composing/decomposing '
            'contents of HTML tags.  Not recommended for use, unless '
            'you know your translation bureau cannot support .po files '
            'exported without use of this flag.')
        self.parser.add_argument(
            '--suppress_memcache', type=bool, default=True,
            help='Suppress using memcache when looking up objects.  This '
            'is to work around a known issue with Memcache and DB relating '
            'to old-style protocol buffers.  '
            'It\'s also a good idea in general; since this job will touch '
            'many, many objects in an unusual pattern, it\'s worthwhile to '
            'not spam all of these objects into the memcache.'
            )

    def _apply_parsed_args(self):
        if self.args.suppress_memcache:
            config.Registry.test_overrides[models.CAN_USE_MEMCACHE.name] = False

    @classmethod
    def _build_translation_config(cls, args, app_context):
        cfg = i18n_dashboard.I18nTranslationContext.get(app_context)
        if args.suppress_nondefault_composable_tags:
            cfg.opaque_decomposable_tag_names = list(
                xcontent.DEFAULT_OPAQUE_DECOMPOSABLE_TAG_NAMES)
            cfg.RECOMPOSABLE_ATTRIBUTES_MAP = dict(
                xcontent.DEFAULT_RECOMPOSABLE_ATTRIBUTES_MAP)
        return cfg

    @classmethod
    def _check_file_exists(cls, path):
        if not os.path.exists(path):
            _die('File does not exist: ' + path)

    @classmethod
    def _check_file_does_not_exist(cls, path):
        if os.path.exists(path):
            _die('File already exists: ' + path)

    @classmethod
    def _get_locales(
            cls, requested_locales, all_locales, default_locale,
            course_url_prefix):
        # We do not want to include the base locale in this list, because
        # it is not something people can delete with this tool, and we do not
        # want it in the output .zipfile because we don't want users to upload
        # it.
        all_locales.remove(default_locale)
        all_locales = sorted(all_locales)
        if not requested_locales:
            return all_locales

        all_locales = set(all_locales)
        requested_locales = set(requested_locales)
        missing_locales = requested_locales - all_locales
        if missing_locales:
            _die(
                'Requested locale%s %s not found for course at %s. Choices '
                'are: %s' % (
                    's' if len(missing_locales) > 1 else '',
                    ', '.join(sorted(missing_locales)), course_url_prefix,
                    ', '.join(sorted(all_locales))))

        return sorted(requested_locales)


class DeleteTranslations(_BaseJob):
    """Deletes translations from a course based on locales.

    Usage for deleting all locales:

      sh scripts/etl.sh run modules.i18n_dashboard.jobs.DeleteTranslations \
        /target_course servername

    To delete specific locales:

      sh scripts/etl.sh run modules.i18n_dashboard.jobs.DeleteTranslations \
        /target_course servername \
        --job_args='--locales=en_US,fr'
    """

    def _configure_parser(self):
        super(DeleteTranslations, self)._configure_parser()

    def main(self):
        super(DeleteTranslations, self)._apply_parsed_args()
        app_context = self._get_app_context_or_die(
            self.etl_args.course_url_prefix)
        locales = self._get_locales(
            self.args.locales, app_context.get_all_locales(),
            app_context.default_locale, self.etl_args.course_url_prefix)
        i18n_dashboard.TranslationDeletionRestHandler.delete_locales(
            courses.Course.get(app_context), locales)


class DownloadTranslations(_BaseJob):
    """Downloads .zip of .po files of translations.

    Usage for downloading all locales:

      sh scripts/etl.sh run modules.i18n_dashboard.jobs.DownloadTranslations \
        /target_course servername \
        --job_args='/tmp/download.zip'

    To download specific locales:

      sh scripts/etl.sh run modules.i18n_dashboard.jobs.DownloadTranslations \
        /target_course servername \
        --job_args='/tmp/download.zip --locales=en_US,fr'
    """

    _EXPORT_ALL = 'all'
    _EXPORT_NEW = 'new'
    _EXPORT_CHOICES = frozenset([
        _EXPORT_ALL,
        _EXPORT_NEW,
    ])

    def _configure_parser(self):
        super(DownloadTranslations, self)._configure_parser()
        self.parser.add_argument(
            'path', type=str, help='Path of the file to save output to')
        self.parser.add_argument(
            '--export', choices=self._EXPORT_CHOICES, default=self._EXPORT_ALL,
            type=str, help='What translation strings to export. Choose '
            '"%(new)s" to get items that are new or have out-of-date '
            'translations; choose "%(all)s" to get all items. Default: '
            '"%(all)s"' % ({
                'all': self._EXPORT_ALL,
                'new': self._EXPORT_NEW,
            }))
        self.parser.add_argument(
            '--separate_files_by_type', action='store_true',
            help='Extract translatable content into separate files by type.  '
            'Configurations, questions and the contents of individual units '
            'and lessons are extracted into separate files, rather than one '
            'big file.  This can be helpful to reduce the size of individual '
            '.po files, as well as making the context more clear for short '
            'phrases that might otherwise get inappropriately combined into '
            'the same translation item if they were in one big file.')
        self.parser.add_argument(
            '--encoded_angle_brackets', action='store_true',
            help='Encode angle brackets as square brackets in downloaded .po '
            'file content.  This can be helpful for translation bureaus '
            'that cannot cope with embedded HTML markup in original or '
            'translated content.  Be sure to also supply this flag when '
            're-uploading translated content.')
        self.parser.add_argument(
            '--locale_agnostic', action='store_true',
            help='Download .po file(s) using a single locale of "gv".  '
            '"gv" locale.  When using this flag in combination with the '
            '--export=new setting, you may specify --locales=.... to restrict '
            'the locales you want to consider when establishing whether to '
            'export items for which the base-locale content is newer.  '
            'If --locales is not given, all locales are considered.  '
            'When using --export=all, you need not set --locales.')
        self.parser.add_argument(
            '--max_entries_per_file', type=int, default=None,
            help='Set maximum number of entries per translation file.  '
            'This is useful if your tranlation bureau has a maximum size '
            'limit on input files.')

    def main(self):
        super(DownloadTranslations, self)._apply_parsed_args()
        app_context = self._get_app_context_or_die(
            self.etl_args.course_url_prefix)
        self._check_file_does_not_exist(self.args.path)

        all_locales = app_context.get_all_locales()
        if self.args.locale_agnostic and self.args.export == self._EXPORT_ALL:
            # If we're locale-agnostic and exporting everything, just pick any
            # one locale.  Naming more locales would just force unnecessary
            # repetitive work.
            all_locales.remove(app_context.default_locale)
            if not all_locales:
                _die('Course must have at least one translatable locale '
                     'configured in the translation settings.')
            locales = all_locales[:1]
        else:
            locales = self._get_locales(
                self.args.locales, all_locales,
                app_context.default_locale, self.etl_args.course_url_prefix)

        if self.args.locale_agnostic:
            exporter = OverriddenLocaleTranslationContents(
                separate_files_by_type=self.args.separate_files_by_type,
                max_entries_per_file=self.args.max_entries_per_file,
                locale_to_use=AGNOSTIC_EXPORT_LOCALE)
        else:
            exporter = i18n_dashboard.TranslationContents(
                separate_files_by_type=self.args.separate_files_by_type,
                max_entries_per_file=self.args.max_entries_per_file)

        cfg = self._build_translation_config(self.args, app_context)
        i18n_dashboard.TranslationDownloadRestHandler.build_translations(
            courses.Course.get(app_context), locales, self.args.export,
            exporter, config=cfg)
        if self.args.encoded_angle_brackets:
            exporter.encode_angle_to_square_brackets()

        if exporter.is_empty():
            _die(
                'No translations found for course at %s; exiting' % (
                    self.etl_args.course_url_prefix))
        with open(self.args.path, 'w') as fp:
            exporter.write_zip_file(app_context, fp)
        _LOG.info('Translations saved to ' + self.args.path)


class TranslateToReversedCase(_BaseJob):
    """Translates a specified course to rEVERSED cASE.

    Usage.

      sh scripts/etl.sh run \
        modules.i18n_dashboard.jobs.TranslateToReversedCase \
        /target_course servername
    """

    def main(self):
        app_context = self._get_app_context_or_die(
            self.etl_args.course_url_prefix)
        i18n_dashboard.I18nReverseCaseHandler.translate_course(
            courses.Course.get(app_context))


class UploadTranslations(_BaseJob):
    """Uploads .po or .zip file containing translations.

    Usage:

      sh scripts/etl.sh run modules.i18n_dashboard.jobs.UploadTranslations \
        /target_course servername \
        --job_args='/tmp/file.zip'
    """

    _UPLOAD_HANDLER = i18n_dashboard.TranslationUploadRestHandler

    def _configure_parser(self):
        super(UploadTranslations, self)._configure_parser()
        self.parser.add_argument(
            'path', type=str, help='.zip or .po file containing translations. '
            'If a .zip file is given, its internal structure is unimportant; '
            'all .po files it contains will be processed.')
        self.parser.add_argument(
            '--encoded_angle_brackets', action='store_true',
            help='When uploading, convert angle brackets that were encoded '
            'as square brackets back to angle brackets.')
        self.parser.add_argument(
            '--warn_not_found', action='store_true',
            help='When uploading, warn about translatable items that exist '
            'in the course that had no matching item in the uploaded .po file. '
            'Do not use this when uploading partial .po files (as created '
            'when downloading with the --separate_files_by_type flag -- this '
            'will then warn about all the items not for that partial file.')
        self.parser.add_argument(
            '--warn_not_used', action='store_const', const=True, default=True,
            help='When uploading, warn about translation items found in the '
            '.po file that did not match current course content (and thus '
            'were not incorporated into the translations for the course)')
        self.parser.add_argument(
            '--force_locale',
            help='When uploading, force the upload to be done to the named '
            'locale, rather than the locale encoded in the location keys '
            'embedded in the file.  This is useful when you have previously '
            'done a file download that is locale-agnostic, and now you are '
            'uploading one of a number of returned translations.  '
            'NOTE: If you get this wrong, this will simply overwrite the '
            'incorrect locale\'s translations.  The only way to recover '
            'the overwritten items is by uploading a file with the correct '
            'content, or restoring from backups.')

    def main(self):
        super(UploadTranslations, self)._apply_parsed_args()
        app_context = self._get_app_context_or_die(
            self.etl_args.course_url_prefix)

        # Parse content from .zip of .po files, or single .po file.
        with open(self.args.path) as fp:
            data = fp.read()

        if self.args.force_locale:
            importer = OverriddenLocaleTranslationContents(
                locale_to_use=self.args.force_locale)
        else:
            importer = i18n_dashboard.TranslationContents()

        self._UPLOAD_HANDLER.load_file_content(app_context, data, importer)
        if self.args.encoded_angle_brackets:
            importer.decode_square_to_angle_brackets()

        # Add the locales being uploaded to the UI; these may not exist if we
        # are uploading to a clone of a course.
        course = courses.Course.get(app_context)
        environ = course.get_environ(app_context)
        extra_locales = environ.setdefault('extra_locales', [])
        for locale in importer.get_locales():
            if not any(
                    l[courses.Course.SCHEMA_LOCALE_LOCALE] == locale
                    for l in extra_locales):
                extra_locales.append({
                    courses.Course.SCHEMA_LOCALE_LOCALE: locale,
                    courses.Course.SCHEMA_LOCALE_AVAILABILITY: (
                        courses.Course.SCHEMA_LOCALE_AVAILABILITY_UNAVAILABLE)})
        course.save_settings(environ)

        # Make updates to the translations
        cfg = self._build_translation_config(self.args, app_context)
        messages = self._UPLOAD_HANDLER.update_translations(
            course, importer, warn_not_found=self.args.warn_not_found,
            warn_not_used=self.args.warn_not_used, config=cfg)
        for message in messages:
            _LOG.info(message)


class OverriddenLocaleTranslationContents(i18n_dashboard.TranslationContents):

    def __init__(self, separate_files_by_type=False,
                 max_entries_per_file=None,
                 locale_to_use=AGNOSTIC_EXPORT_LOCALE):
        super(OverriddenLocaleTranslationContents, self).__init__(
            separate_files_by_type=separate_files_by_type,
            max_entries_per_file=max_entries_per_file)
        self._locale_to_use = locale_to_use

    def get_message(self, resource_bundle_key, message_key):
        resource_key = resource_bundle_key.resource_key
        resource_bundle_key = i18n_dashboard.ResourceBundleKey(
            resource_key.type, resource_key.key, self._locale_to_use)
        return super(OverriddenLocaleTranslationContents, self).get_message(
            resource_bundle_key, message_key)

    def _get_file(self, resource_bundle_key, file_name):
        file_key = (self._locale_to_use, file_name)
        if file_key not in self._files:
            self._files[file_key] = OverriddenLocaleTranslationFile(
                self._locale_to_use, file_name)
        return self._files[file_key]


class OverriddenLocaleTranslationFile(i18n_dashboard.TranslationFile):

    def __init__(self, locale, file_name):
        super(OverriddenLocaleTranslationFile, self).__init__(
            locale, file_name)
        self._locale_to_use = locale

    def _get_message(self, key):
        if key not in self._translations:
            self._translations[key] = OverriddenLocaleTranslationMessage(
                self._locale_to_use)
        return self._translations[key]


class OverriddenLocaleTranslationMessage(i18n_dashboard.TranslationMessage):

    def __init__(self, locale_to_use):
        super(OverriddenLocaleTranslationMessage, self).__init__()
        self._locale_to_use = locale_to_use

    def add_location(self, resource_bundle_key, loc_name, loc_type):
        resource_key = resource_bundle_key.resource_key
        fixed_location_bundle_key = i18n_dashboard.ResourceBundleKey(
            resource_key.type, resource_key.key, self._locale_to_use)
        super(OverriddenLocaleTranslationMessage, self).add_location(
            fixed_location_bundle_key, loc_name, loc_type)

    def add_translation(self, translation):
        # Location-agnostic exports never send existing translations, since
        # their purpose is to combine work from multiple languages.
        if self._locale_to_use == AGNOSTIC_EXPORT_LOCALE:
            translation = ''
        super(OverriddenLocaleTranslationMessage, self).add_translation(
            translation)
