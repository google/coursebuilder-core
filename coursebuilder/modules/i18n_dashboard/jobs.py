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
from models import courses
from modules.i18n_dashboard import i18n_dashboard
from tools.etl import etl_lib

_LOG = logging.getLogger('coursebuilder.modules.i18n_dashboard.jobs')
_LOG.setLevel(logging.INFO)


def _die(message):
    _LOG.critical(message)
    sys.exit(1)


class _BaseJob(etl_lib.CourseJob):

    @classmethod
    def _add_locales_argument(cls, parser):
        parser.add_argument(
            '--locales', default=[], type=lambda s: s.split(','),
            help='Comma-delimited list of locales (for example, "af") to '
            'export. If omitted, all locales except the default locale for the '
            'course will be exported. Passed locales must exist for the '
            'specified course.')

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
        /target_course appid servername

    To delete specific locales:

      sh scripts/etl.sh run modules.i18n_dashboard.jobs.DeleteTranslations \
        /target_course appid servername \
        --job_args='--locales=en_US,fr'
    """

    def _configure_parser(self):
        self._add_locales_argument(self.parser)

    def main(self):
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
        /target_course appid servername \
        --job_args='/tmp/download.zip'

    To download specific locales:

      sh scripts/etl.sh run modules.i18n_dashboard.jobs.DownloadTranslations \
        /target_course appid servername \
        --job_args='/tmp/download.zip --locales=en_US,fr'
    """

    _EXPORT_ALL = 'all'
    _EXPORT_NEW = 'new'
    _EXPORT_CHOICES = frozenset([
        _EXPORT_ALL,
        _EXPORT_NEW,
    ])

    def _configure_parser(self):
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
        self._add_locales_argument(self.parser)

    def main(self):
        app_context = self._get_app_context_or_die(
            self.etl_args.course_url_prefix)
        self._check_file_does_not_exist(self.args.path)

        locales = self._get_locales(
            self.args.locales, app_context.get_all_locales(),
            app_context.default_locale, self.etl_args.course_url_prefix)
        exporter = i18n_dashboard.TranslationContents(
            self.args.separate_files_by_type)
        download_handler = i18n_dashboard.TranslationDownloadRestHandler
        download_handler.build_translations(
            courses.Course.get(app_context), locales, self.args.export,
            exporter)
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
        /target_course appid servername
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
        /target_course appid servername \
        --job_args='/tmp/file.zip'
    """

    _UPLOAD_HANDLER = i18n_dashboard.TranslationUploadRestHandler

    def _configure_parser(self):
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

    def main(self):
        app_context = self._get_app_context_or_die(
            self.etl_args.course_url_prefix)

        # Parse content from .zip of .po files, or single .po file.
        with open(self.args.path) as fp:
            data = fp.read()
        importer = self._UPLOAD_HANDLER.load_file_content(app_context, data)
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
        messages = self._UPLOAD_HANDLER.update_translations(
            course, importer, self.args.warn_not_found, self.args.warn_not_used)
        for message in messages:
            _LOG.info(message)
