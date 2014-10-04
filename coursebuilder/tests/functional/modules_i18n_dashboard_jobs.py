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
from tools.etl import etl
from tools.etl import testing

# Allow access to code under test. pylint: disable-msg=protected-access


class _JobTestBase(testing.EtlTestBase):

    def setUp(self):
        super(_JobTestBase, self).setUp()
        self.filename = os.path.join(self.test_tempdir, 'filename')

    def assert_dies_if_cannot_get_app_context_for_course_url_prefix(
            self, job_name, job_args=None):
        bad_course_url_prefix = '/bad' + self.url_prefix
        args = [
            'run', 'modules.i18n_dashboard.jobs.' + job_name,
            bad_course_url_prefix, 'myapp', 'localhost:8080']

        if job_args:
            args.append(job_args)

        with self.assertRaises(SystemExit):
            etl.main(
                etl.PARSER.parse_args(args),
                environment_class=testing.FakeEnvironment)

        self.assertIn(
            'Unable to find course with url prefix ' + bad_course_url_prefix,
            self.get_log())

    def create_file(self, contents):
        with open(self.filename, 'w') as f:
            f.write(contents)


class BaseJobTest(_JobTestBase):

    def setUp(self):
        super(BaseJobTest, self).setUp()

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

    # TODO(johncox): strengthen with tests of one locale, multiple locales.


class DownloadTranslationsTest(_JobTestBase):

    def test_dies_if_cannot_get_app_context_for_course_url_prefix(self):
        self.assert_dies_if_cannot_get_app_context_for_course_url_prefix(
            'DownloadTranslations', '--job_args=path')

    def test_dies_if_path_already_exists(self):
        self.create_file('contents')
        args = [
            'run', 'modules.i18n_dashboard.jobs.DownloadTranslations',
            self.url_prefix, 'myapp', 'localhost:8080',
            '--job_args=%s' % self.filename]

        with self.assertRaises(SystemExit):
            etl.main(
                etl.PARSER.parse_args(args),
                environment_class=testing.FakeEnvironment)

        self.assertIn('File already exists', self.get_log())

    def test_download_of_course_with_no_translations_dies(self):
        filename = self.filename + '.zip'
        args = [
            'run', 'modules.i18n_dashboard.jobs.DownloadTranslations',
            self.url_prefix, 'myapp', 'localhost:8080',
            '--job_args=%s' % filename]

        with self.assertRaises(SystemExit):
            etl.main(
                etl.PARSER.parse_args(args),
                environment_class=testing.FakeEnvironment)

        self.assertIn(
            'No translations found for course at %s; exiting' % self.url_prefix,
            self.get_log())

    # TODO(johncox): strengthen with test of one locale, multiple locales,
    # and downloading all vs. new.


class TranslateToReversedCaseTest(_JobTestBase):

    def test_dies_if_cannot_get_app_context_for_course_url_prefix(self):
        self.assert_dies_if_cannot_get_app_context_for_course_url_prefix(
            'TranslateToReversedCase')


class UploadTranslationsTest(_JobTestBase):

    def setUp(self):
        super(UploadTranslationsTest, self).setUp()
        self.filename += '.zip'

    def create_zip_file(self, contents):
        with zipfile.ZipFile(self.filename, 'w') as zf:
            zf.writestr('filename', contents)

    def test_dies_if_path_does_not_exist(self):
        args = [
            'run', 'modules.i18n_dashboard.jobs.UploadTranslations',
            self.url_prefix, 'myapp', 'localhost:8080',
            '--job_args=%s' % self.filename]

        with self.assertRaises(SystemExit):
            etl.main(
                etl.PARSER.parse_args(args),
                environment_class=testing.FakeEnvironment)

        self.assertIn('File does not exist', self.get_log())

    def test_dies_if_path_has_bad_file_extension(self):
        args = [
            'run', 'modules.i18n_dashboard.jobs.UploadTranslations',
            self.url_prefix, 'myapp', 'localhost:8080',
            '--job_args=%s' % self.filename + '.bad']

        with self.assertRaises(SystemExit):
            etl.main(
                etl.PARSER.parse_args(args),
                environment_class=testing.FakeEnvironment)

        self.assertIn('Invalid file extension: ".bad"', self.get_log())

    def test_dies_if_cannot_get_app_context_for_course_url_prefix(self):
        self.create_zip_file('contents')
        args = [
            'run', 'modules.i18n_dashboard.jobs.UploadTranslations',
            '/bad' + self.url_prefix, 'myapp', 'localhost:8080',
            '--job_args=%s' % self.filename]

        with self.assertRaises(SystemExit):
            etl.main(
                etl.PARSER.parse_args(args),
                environment_class=testing.FakeEnvironment)

        self.assertIn(
            'Unable to find course with url prefix', self.get_log())

    # TODO(johncox): strengthen with tests of a .po file and a .zip containing
    # both .po files and other files to ensure other files are filtered. Also,
    # verify we've done the work to make the change show in the UI wihout adding
    # locales that match the new locales uploaded.


class RoundTripTest(_JobTestBase):
    """Tests translate -> download -> delete -> upload."""

    def test_round_trip(self):
        filename = self.filename + '.zip'

        # Translate to create something to download.
        translate_args = [
            'run', 'modules.i18n_dashboard.jobs.TranslateToReversedCase',
            self.url_prefix, 'myapp', 'localhost:8080']
        etl.main(
            etl.PARSER.parse_args(translate_args),
            environment_class=testing.FakeEnvironment)
        # TODO(johncox): strengthen by checking that the 'ln' locale is now
        # present in the course.

        # Download into .zip.
        download_args = [
            'run', 'modules.i18n_dashboard.jobs.DownloadTranslations',
            self.url_prefix, 'myapp', 'localhost:8080',
            '--job_args=' + filename]
        etl.main(
            etl.PARSER.parse_args(download_args),
            environment_class=testing.FakeEnvironment)
        # TODO(johncox): strengthen by spot-checking .zip for .po containing
        # 'ln' locale translations.

        # Delete translations so we can verify upload.
        delete_args = [
            'run', 'modules.i18n_dashboard.jobs.DeleteTranslations',
            self.url_prefix, 'myapp', 'localhost:8080']
        etl.main(
            etl.PARSER.parse_args(delete_args),
            environment_class=testing.FakeEnvironment)
        # TODO(johncox): strengthen by checking that the 'ln' locale is no
        # longer present in the course.

        # Upload from .zip.
        upload_args = [
            'run', 'modules.i18n_dashboard.jobs.UploadTranslations',
            self.url_prefix, 'myapp', 'localhost:8080',
            '--job_args=' + filename]
        etl.main(
            etl.PARSER.parse_args(upload_args),
            environment_class=testing.FakeEnvironment)
        # TODO(johncox): strengthen by inspecting course contents to verify that
        # the 'ln' locale is once again present.
        self.assertIn(
            'Processing locale/ln/LC_MESSAGES/messages.po', self.get_log())
