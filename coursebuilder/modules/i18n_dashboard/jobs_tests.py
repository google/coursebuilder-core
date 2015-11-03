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

"""Functional tests for modules/i18n_dashboard/jobs.py."""

__author__ = [
    'johncox@google.com (John Cox)',
]

import os
import zipfile
from modules.i18n_dashboard import jobs
from modules.i18n_dashboard import i18n_dashboard_tests
from tools.etl import etl
from tools.etl import testing

# Allow access to code under test. pylint: disable=protected-access


class _JobTestBase(
        testing.EtlTestBase, i18n_dashboard_tests.CourseLocalizationTestBase):

    def setUp(self):
        super(_JobTestBase, self).setUp()
        self.filename = os.path.join(self.test_tempdir, 'filename')
        self.zipfile_name = self.filename + '.zip'

    def assert_dies_if_cannot_get_app_context_for_course_url_prefix(
            self, job_name, job_args=None):
        bad_course_url_prefix = '/bad' + self.url_prefix
        args = [
            'run', 'modules.i18n_dashboard.jobs.' + job_name,
            bad_course_url_prefix, 'localhost']

        if job_args:
            args.append(job_args)

        with self.assertRaises(SystemExit):
            etl.main(etl.create_args_parser().parse_args(args), testing=True)

        self.assertIn(
            'Unable to find course with url prefix ' + bad_course_url_prefix,
            self.get_log())

    def assert_ln_locale_in_course(self, response):
        self.assertEqual(200, response.status_int)
        self.assertIn('>ln</th>', response.body)

    def assert_ln_locale_not_in_course(self, response):
        self.assertEqual(200, response.status_int)
        self.assertNotIn('>ln</th>', response.body)

    def assert_zipfile_contains_only_ln_locale(self, filename):
        with zipfile.ZipFile(filename) as zf:
            files = zf.infolist()
            self.assertEqual(
                ['locale/ln/LC_MESSAGES/messages.po'],
                [f.filename for f in files])

    def create_file(self, contents):
        with open(self.filename, 'w') as f:
            f.write(contents)

    def run_job(self, name, job_args=None):
        # Requires course at /first; use self._import_course().
        args = ['run', name, '/first', 'localhost']

        if job_args:
            args.append(job_args)

        etl.main(etl.create_args_parser().parse_args(args), testing=True)

    def run_delete_job(self, job_args=None):
        self.run_job(
            'modules.i18n_dashboard.jobs.DeleteTranslations', job_args=job_args)

    def run_download_job(self, job_args=None):
        if not job_args:
            job_args = '--job_args=' + self.zipfile_name

        self.run_job(
            'modules.i18n_dashboard.jobs.DownloadTranslations',
            job_args=job_args)

    def run_translate_job(self, job_args=None):
        self.run_job(
            'modules.i18n_dashboard.jobs.TranslateToReversedCase',
            job_args=job_args)

    def run_upload_job(self, job_args=None):
        if not job_args:
            job_args = '--job_args=' + self.zipfile_name

        self.run_job(
            'modules.i18n_dashboard.jobs.UploadTranslations', job_args=job_args)


class BaseJobTest(_JobTestBase):

    def test_file_does_not_exist_when_file_does_not_exist(self):
        jobs._BaseJob._check_file_does_not_exist(self.filename)

    def test_file_does_not_exist_dies_when_file_exists(self):
        with open(self.filename, 'w') as f:
            f.write('contents')

        with self.assertRaises(SystemExit):
            jobs._BaseJob._check_file_does_not_exist(self.filename)

        self.assertIn('File already exists', self.get_log())

    def test_file_exists_when_file_exists(self):
        self.create_file('contents')
        jobs._BaseJob._check_file_exists(self.filename)

    def test_file_exists_dies_when_file_does_not_exist(self):
        with self.assertRaises(SystemExit):
            jobs._BaseJob._check_file_exists(self.filename)

        self.assertIn('File does not exist', self.get_log())

    def test_get_app_context_or_die_gets_existing_app_context(self):
        self.assertEqual(
            self.url_prefix,
            jobs._BaseJob._get_app_context_or_die(self.url_prefix).slug)

    def test_get_app_context_or_die_dies_if_context_missing(self):
        with self.assertRaises(SystemExit):
            jobs._BaseJob._get_app_context_or_die('missing')

        self.assertIn(
            'Unable to find course with url prefix missing', self.get_log())

    def get_get_locales_returns_all_locales_if_no_requested_locales(self):
        self.assertEqual(
            ['all'],
            jobs._BaseJob._get_locales([], ['requested'], 'strip', 'prefix'))

    def test_get_locales_strips_default_locale(self):
        self.assertEqual(
            ['keep'],
            jobs._BaseJob._get_locales(
                [], ['strip', 'keep'], 'strip', 'prefix'))

    def test_get_locales_returns_sorted_locales_when_no_locales_missing(self):
        self.assertEqual(
            ['a', 'b'],
            jobs._BaseJob._get_locales(
                ['b', 'a'], ['b', 'a', 'strip'], 'strip', 'prefix'))

    def test_get_locales_dies_if_requested_locales_missing(self):
        with self.assertRaises(SystemExit):
            jobs._BaseJob._get_locales(
                ['missing'], ['first', 'second', 'strip'], 'strip', 'prefix')

        self.assertIn(
            'Requested locale missing not found for course at prefix. Choices '
            'are: first, second', self.get_log())


class DeleteTranslationsTest(_JobTestBase):

    def test_dies_if_cannot_get_app_context_for_course_url_prefix(self):
        self.assert_dies_if_cannot_get_app_context_for_course_url_prefix(
            'DeleteTranslations')

    def test_delete_all_locales(self):
        self._import_course()

        self.run_translate_job()
        response = self.get('first/dashboard?action=i18n_dashboard')
        self.assert_ln_locale_in_course(response)

        self.run_delete_job()
        response = self.get('first/dashboard?action=i18n_dashboard')
        self.assert_ln_locale_not_in_course(response)

    def test_delete_specific_locales(self):
        self._import_course()

        self.run_translate_job()
        response = self.get('first/dashboard?action=i18n_dashboard')
        self.assert_ln_locale_in_course(response)

        self.run_delete_job(job_args='--job_args=--locales=ln')
        response = self.get('first/dashboard?action=i18n_dashboard')
        self.assert_ln_locale_not_in_course(response)


class DownloadTranslationsTest(_JobTestBase):

    def test_dies_if_cannot_get_app_context_for_course_url_prefix(self):
        self.assert_dies_if_cannot_get_app_context_for_course_url_prefix(
            'DownloadTranslations', '--job_args=path')

    def test_dies_if_path_already_exists(self):
        self.create_file('contents')
        args = [
            'run', 'modules.i18n_dashboard.jobs.DownloadTranslations',
            self.url_prefix, 'localhost', '--job_args=%s' % self.filename]

        with self.assertRaises(SystemExit):
            etl.main(etl.create_args_parser().parse_args(args), testing=True)

        self.assertIn('File already exists', self.get_log())

    def test_download_of_course_with_no_translations_dies(self):
        args = [
            'run', 'modules.i18n_dashboard.jobs.DownloadTranslations',
            self.url_prefix, 'localhost', '--job_args=%s' % self.zipfile_name]

        with self.assertRaises(SystemExit):
            etl.main(etl.create_args_parser().parse_args(args), testing=True)

        self.assertIn(
            'No translations found for course at %s; exiting' % self.url_prefix,
            self.get_log())

    def test_download_all_locales(self):
        self._import_course()

        self.run_translate_job()
        response = self.get('first/dashboard?action=i18n_dashboard')
        self.assert_ln_locale_in_course(response)

        self.run_download_job()
        self.assert_zipfile_contains_only_ln_locale(self.zipfile_name)

    def test_download_specific_locales(self):
        self._import_course()

        self.run_translate_job()
        response = self.get('first/dashboard?action=i18n_dashboard')
        self.assert_ln_locale_in_course(response)

        self.run_download_job('--job_args=%s --locales=ln' % self.zipfile_name)
        self.assert_zipfile_contains_only_ln_locale(self.zipfile_name)


class TranslateToReversedCaseTest(_JobTestBase):

    def test_dies_if_cannot_get_app_context_for_course_url_prefix(self):
        self.assert_dies_if_cannot_get_app_context_for_course_url_prefix(
            'TranslateToReversedCase')


class UploadTranslationsTest(_JobTestBase):

    def create_zip_file(self, contents):
        with zipfile.ZipFile(self.zipfile_name, 'w') as zf:
            zf.writestr('filename', contents)

    def extract_zipfile(self):
        extracted = []
        with zipfile.ZipFile(self.zipfile_name) as zf:
            for zipinfo in zf.infolist():
                path = os.path.join(self.test_tempdir, zipinfo.filename)
                os.makedirs(os.path.dirname(path))
                with open(path, 'w') as f:
                    fromzip = zf.open(zipinfo.filename)
                    f.write(fromzip.read())
                    extracted.append(path)

        return extracted

    def test_dies_if_path_does_not_exist(self):
        args = [
            'run', 'modules.i18n_dashboard.jobs.UploadTranslations',
            self.url_prefix, 'localhost', '--job_args=%s' % self.zipfile_name]

        with self.assertRaises(SystemExit):
            etl.main(etl.create_args_parser().parse_args(args), testing=True)

        self.assertIn('File does not exist', self.get_log())

    def test_dies_if_path_has_bad_file_extension(self):
        args = [
            'run', 'modules.i18n_dashboard.jobs.UploadTranslations',
            self.url_prefix, 'localhost',
            '--job_args=%s' % self.zipfile_name + '.bad']

        with self.assertRaises(SystemExit):
            etl.main(etl.create_args_parser().parse_args(args), testing=True)

        self.assertIn('Invalid file extension: ".bad"', self.get_log())

    def test_dies_if_cannot_get_app_context_for_course_url_prefix(self):
        self.create_zip_file('contents')
        args = [
            'run', 'modules.i18n_dashboard.jobs.UploadTranslations',
            '/bad' + self.url_prefix, 'localhost',
            '--job_args=%s' % self.zipfile_name]

        with self.assertRaises(SystemExit):
            etl.main(etl.create_args_parser().parse_args(args), testing=True)

        self.assertIn(
            'Unable to find course with url prefix', self.get_log())

    def test_processes_pofile(self):
        self._import_course()

        self.run_translate_job()
        response = self.get('first/dashboard?action=i18n_dashboard')
        self.assert_ln_locale_in_course(response)

        self.run_download_job()
        self.assert_zipfile_contains_only_ln_locale(self.zipfile_name)

        self.run_delete_job()
        response = self.get('first/dashboard?action=i18n_dashboard')
        self.assert_ln_locale_not_in_course(response)

        for po_file in self.extract_zipfile():
            self.run_upload_job('--job_args=' + po_file)
            response = self.get('first/dashboard?action=i18n_dashboard')
            self.assert_ln_locale_in_course(response)

    def test_processes_zipfile(self):
        self._import_course()

        self.run_translate_job()
        response = self.get('first/dashboard?action=i18n_dashboard')
        self.assert_ln_locale_in_course(response)

        self.run_download_job()
        self.assert_zipfile_contains_only_ln_locale(self.zipfile_name)

        self.run_delete_job()
        response = self.get('first/dashboard?action=i18n_dashboard')
        self.assert_ln_locale_not_in_course(response)

        self.run_upload_job()
        response = self.get('first/dashboard?action=i18n_dashboard')
        self.assert_ln_locale_in_course(response)


class RoundTripTest(_JobTestBase):
    """Tests translate -> download -> delete -> upload."""

    def test_round_trip(self):
        self._import_course()
        response = self.get('first/dashboard?action=i18n_dashboard')
        self.assert_ln_locale_not_in_course(response)

        self.run_translate_job()
        response = self.get('first/dashboard?action=i18n_dashboard')
        self.assert_ln_locale_in_course(response)

        self.run_download_job()
        self.assert_zipfile_contains_only_ln_locale(self.zipfile_name)

        self.run_delete_job()
        response = self.get('first/dashboard?action=i18n_dashboard')
        self.assert_ln_locale_not_in_course(response)

        self.run_upload_job()
        response = self.get('first/dashboard?action=i18n_dashboard')
        self.assert_ln_locale_in_course(response)
