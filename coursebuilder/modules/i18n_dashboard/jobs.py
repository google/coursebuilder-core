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
import zipfile
from babel import localedata
from common import utils as common_utils
from models import courses
from modules.i18n_dashboard import i18n_dashboard
from tools.etl import etl_lib


def _die(message):
    logging.critical(message)
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
        self._add_locales_argument(self.parser)

    def main(self):
        app_context = self._get_app_context_or_die(
            self.etl_args.course_url_prefix)
        self._check_file_does_not_exist(self.args.path)

        locales = self._get_locales(
            self.args.locales, app_context.get_all_locales(),
            app_context.default_locale, self.etl_args.course_url_prefix)
        download_handler = i18n_dashboard.TranslationDownloadRestHandler
        translations = download_handler.build_translations(
            courses.Course.get(app_context), locales, 'all')

        if not translations.keys():
            _die(
                'No translations found for course at %s; exiting' % (
                    self.etl_args.course_url_prefix))

        with open(self.args.path, 'w') as f:
            i18n_dashboard.TranslationDownloadRestHandler.build_zip_file(
                courses.Course.get(app_context), f, translations, locales)

        logging.info('Translations saved to ' + self.args.path)


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

    _PO_EXTENSION = '.po'
    _ZIP_EXTENSION = '.zip'
    _EXTENSIONS = frozenset([
        _PO_EXTENSION,
        _ZIP_EXTENSION,
    ])

    _UPLOAD_HANDLER = i18n_dashboard.TranslationUploadRestHandler

    def _configure_parser(self):
        self.parser.add_argument(
            'path', type=str, help='.zip or .po file containing translations. '
            'If a .zip file is given, its internal structure is unimportant; '
            'all .po files it contains will be processed. We do no validation '
            'on file contents.')

    def main(self):
        self._check_file(self.args.path)
        app_context = self._get_app_context_or_die(
            self.etl_args.course_url_prefix)
        extension = self._get_file_extension(self.args.path)

        course = courses.Course.get(app_context)
        self._configure_babel(course)
        if extension == self._PO_EXTENSION:
            translations = self._process_po_file(self.args.path)
        elif extension == self._ZIP_EXTENSION:
            translations = self._process_zip_file(self.args.path)

        # Add the locales being uploaded to the UI.
        environ = course.get_environ(app_context)
        extra_locales = environ.setdefault('extra_locales', [])
        for locale in translations:
            if not any(
                    l[courses.Course.SCHEMA_LOCALE_LOCALE] == locale
                    for l in extra_locales):
                extra_locales.append({
                    courses.Course.SCHEMA_LOCALE_LOCALE: locale,
                    courses.Course.SCHEMA_LOCALE_AVAILABILITY: (
                        courses.Course.SCHEMA_LOCALE_AVAILABILITY_UNAVAILABLE)})
        course.save_settings(environ)

        # Make updates to the translations
        self._update_translations(course, translations)

    @classmethod
    def _check_file(cls, path):
        extension = cls._get_file_extension(path)
        if not extension or extension not in cls._EXTENSIONS:
            _die(
                'Invalid file extension: "%s". Choices are: %s' % (
                    extension, ', '.join(sorted(cls._EXTENSIONS))))

        cls._check_file_exists(path)

    @classmethod
    def _configure_babel(cls, course):
        with common_utils.ZipAwareOpen():
            # Internally, babel uses the 'en' locale, and we must configure it
            # before we make babel calls.
            localedata.load('en')
            # Also load the course's default language.
            localedata.load(course.default_locale)

    @classmethod
    def _get_file_extension(cls, path):
        return os.path.splitext(path)[-1]

    @classmethod
    def _process_po_file(cls, po_file_path):
        translations = cls._UPLOAD_HANDLER.build_translations_defaultdict()
        with open(po_file_path) as f:
            cls._UPLOAD_HANDLER.parse_po_file(translations, f.read())
        return translations

    @classmethod
    def _process_zip_file(cls, zip_file_path):
        zf = zipfile.ZipFile(zip_file_path, 'r', allowZip64=True)
        translations = cls._UPLOAD_HANDLER.build_translations_defaultdict()
        for zipinfo in zf.infolist():
            if cls._get_file_extension(zipinfo.filename) != cls._PO_EXTENSION:
                continue
            logging.info('Processing ' + zipinfo.filename)
            po_contents = zf.read(zipinfo.filename)
            cls._UPLOAD_HANDLER.parse_po_file(translations, po_contents)
        zf.close()
        return translations

    @classmethod
    def _update_translations(cls, course, translations):
        messages = []
        cls._UPLOAD_HANDLER.update_translations(course, translations, messages)
        for message in messages:
            logging.info(message)
