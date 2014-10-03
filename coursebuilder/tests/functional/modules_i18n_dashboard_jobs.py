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

    # TODO(johncox): right now etl_lib.get_context isn't honoring
    # OverriddenEnvironment. Find out why and add tests for _get_locales.


class DeleteTranslationsTest(_JobTestBase):

    def test_dies_if_cannot_get_app_context_for_course_url_prefix(self):
        self.assert_dies_if_cannot_get_app_context_for_course_url_prefix(
            'DeleteTranslations')

    def test_raises_not_implemented_error_if_args_passed_successfully(self):
        # TODO(johncox): remove once delete is implemented in i18n_dashboard.
        args = [
            'run', 'modules.i18n_dashboard.jobs.DeleteTranslations',
            self.url_prefix, 'myapp', 'localhost:8080']

        with self.assertRaises(NotImplementedError):
            etl.main(
                etl.PARSER.parse_args(args),
                environment_class=testing.FakeEnvironment)

    # TODO(johncox): once delete is implemented, add a test for deleting all
    # locales.

    # TODO(johncox): once delete is implemented, add a test for deleting
    # specific locales.


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

    # TODO(johncox): finish tests.


class TranslateToReversedCapsTest(_JobTestBase):

    def test_dies_if_cannot_get_app_context_for_course_url_prefix(self):
        self.assert_dies_if_cannot_get_app_context_for_course_url_prefix(
            'TranslateToReversedCaps')

    def test_raises_not_implemented_error_if_args_passed_successfully(self):
        # TODO(johncox): remove once i18n_dashboard implements translate.
        args = [
            'run', 'modules.i18n_dashboard.jobs.TranslateToReversedCaps',
            self.url_prefix, 'myapp', 'localhost:8080']

        with self.assertRaises(NotImplementedError):
            etl.main(
                etl.PARSER.parse_args(args),
                environment_class=testing.FakeEnvironment)

    # TODO(johncox): once translate is implemented, add a test that calls and
    # verifies the delete.


class UploadTranslationsTest(_JobTestBase):

    def test_something(self):
        # TODO(johncox): tests.
        self.assertTrue(True)
