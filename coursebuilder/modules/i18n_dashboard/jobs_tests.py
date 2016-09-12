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

from common import utils as common_utils
from models import courses
from modules.i18n_dashboard import jobs
from modules.i18n_dashboard import i18n_dashboard
from modules.i18n_dashboard import i18n_dashboard_tests
from tests.functional import actions
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

    def extract_zipfile(self):
        extracted = []
        with zipfile.ZipFile(self.zipfile_name) as zf:
            for zipinfo in zf.infolist():
                path = os.path.join(self.test_tempdir, zipinfo.filename)
                dirname = os.path.dirname(path)
                if not os.path.exists(dirname):
                    os.makedirs(dirname)
                with open(path, 'w') as f:
                    fromzip = zf.open(zipinfo.filename)
                    f.write(fromzip.read())
                    extracted.append(path)
        return extracted


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

    def test_dies_if_path_does_not_exist(self):
        args = [
            'run', 'modules.i18n_dashboard.jobs.UploadTranslations',
            self.url_prefix, 'localhost', '--job_args=%s' % self.zipfile_name]

        with self.assertRaises(IOError):
            etl.main(etl.create_args_parser().parse_args(args), testing=True)

    def test_dies_if_path_has_bad_file_extension(self):
        args = [
            'run', 'modules.i18n_dashboard.jobs.UploadTranslations',
            self.url_prefix, 'localhost',
            '--job_args=%s' % self.zipfile_name + '.bad']

        with self.assertRaises(IOError):
            etl.main(etl.create_args_parser().parse_args(args), testing=True)

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

    def test_separate_files(self):
        app_context = self._import_course()
        course = courses.Course(None, app_context=app_context)
        unit = course.add_unit()
        lesson = course.add_lesson(unit)
        lesson.objectives = 'some text'
        course.save()

        self.run_translate_job()
        self.run_download_job('--job_args=%s --separate_files_by_type' %
                              self.zipfile_name)
        paths = self.extract_zipfile()
        actual = sorted([os.path.basename(path) for path in paths])
        expected = [
            'course_settings.po',
            'html_hook.po',
            'lesson_2.po',
            'unit_1.po'
            ]
        self.assertEquals(expected, actual)

    def test_max_entries(self):
        app_context = self._import_course()
        course = courses.Course(None, app_context=app_context)
        unit = course.add_unit()
        lesson = course.add_lesson(unit)
        lesson.objectives = 'some text'
        course.save()

        self.run_translate_job()
        self.run_download_job('--job_args=%s --max_entries_per_file=3' %
                              self.zipfile_name)
        paths = self.extract_zipfile()
        actual = sorted([os.path.basename(path) for path in paths])
        expected = [
            'messages_001.po',
            'messages_002.po',
            ]
        self.assertEquals(expected, actual)

    def test_max_entries_and_separate_files(self):
        app_context = self._import_course()
        course = courses.Course(None, app_context=app_context)
        unit = course.add_unit()
        lesson = course.add_lesson(unit)
        lesson.objectives = 'some text'
        course.save()

        self.run_translate_job()
        self.run_download_job(
            '--job_args=%s --separate_files_by_type --max_entries_per_file=1' %
            self.zipfile_name)
        paths = self.extract_zipfile()
        actual = sorted([os.path.basename(path) for path in paths])
        expected = [
            'course_settings_001.po',
            'html_hook_001.po',
            'lesson_2_001.po',
            'lesson_2_002.po',
            'unit_1_001.po']
        self.assertEquals(expected, actual)

    def test_square_brackets(self):
        app_context = self._import_course()
        course = courses.Course(None, app_context=app_context)
        assessment = course.add_assessment()
        assessment.html_content = '<b>[in [square] brackets]</b>'
        course.save()
        self.run_translate_job()
        self.run_download_job('--job_args=%s --encoded_angle_brackets' %
                             self.zipfile_name)

        # Open the downloaded .zip file; check the contents of the .po file
        # to ensure we have an HTML tag converted to square brackets, and
        # that the literal square brackets in the text were escaped.
        with zipfile.ZipFile(self.zipfile_name) as zf:
            data = zf.read('locale/ln/LC_MESSAGES/messages.po')
        lines = data.split('\n')
        index = lines.index(
            'msgid "[b#1]\\\\[in \\\\[square\\\\] brackets\\\\][/b#1]"')
        self.assertGreater(index, -1)

        # Overwrite the .zip file with a new .po file that contains a
        # translated version of the text w/ square brackets, and upload.
        lines[index + 1] = (
            'msgstr "[b#1]\\\\[IN \\\\[ROUND\\\\] BRACKETS\\\\][/b#1]"')
        data = '\n'.join(lines)
        with zipfile.ZipFile(self.zipfile_name, 'w') as zf:
            zf.writestr('locale/ln/LC_MESSAGES/messages.po', data)
            zf.close()
        self.run_upload_job('--job_args=%s --encoded_angle_brackets' %
                            self.zipfile_name)

        # Verify that the translated version is visible in the page.
        actions.login('admin@foo.com', is_admin=True)
        response = self.get('first/assessment?name=%s&hl=ln' %
                            assessment.unit_id)
        self.assertIn('<b>[IN [ROUND] BRACKETS]</b>', response.body)

    def test_locale_agnostic_lifecycle(self):
        app_context = self._import_course()
        course = courses.Course(None, app_context=app_context)
        unit = course.add_unit()
        unit.title = 'Title in base language'
        course.save()
        extra_env = {
            'extra_locales': [
                {'locale': 'de', 'availability': 'available'},
                {'locale': 'fr', 'availability': 'available'},
            ]
        }
        bundle_key_de = str(i18n_dashboard.ResourceBundleKey(
            'unit', str(unit.unit_id), 'de'))
        bundle_key_fr = str(i18n_dashboard.ResourceBundleKey(
            'unit', str(unit.unit_id), 'fr'))

        # Do language-agnostic export; should get locale 'gv'.
        with actions.OverriddenEnvironment(extra_env):
            self.run_download_job(
                '--job_args=%s '
                '--locale_agnostic '
                '--export=all' %
                self.zipfile_name)

        with zipfile.ZipFile(self.zipfile_name) as zf:
            data = zf.read('locale/%s/LC_MESSAGES/messages.po' %
                           jobs.AGNOSTIC_EXPORT_LOCALE)
        lines = data.split('\n')
        index = lines.index('msgid "Title in base language"')
        self.assertGreater(index, -1)

        # Provide 'translation' for unit title to 'German'.
        lines[index + 1] = 'msgstr "Title in German"'
        data = '\n'.join(lines)
        with zipfile.ZipFile(self.zipfile_name, 'w') as zf:
            zf.writestr('locale/%s/LC_MESSAGES/messages.po' %
                        jobs.AGNOSTIC_EXPORT_LOCALE, data)
            zf.close()

        # Run upload, forcing locale to German.
        self.run_upload_job('--job_args=%s --force_locale=de' %
                            self.zipfile_name)

        # Verify that we now have DE translation bundle.
        with common_utils.Namespace(self.NAMESPACE):
            bundle = i18n_dashboard.ResourceBundleDAO.load(bundle_key_de)
            self.assertEquals(
                'Title in German',
                bundle.dict['title']['data'][0]['target_value'])

        # Also upload to 'fr', which will give us the wrong content, but
        # the user said "--force", so we force it.
        self.run_upload_job('--job_args=%s --force_locale=fr' %
                            self.zipfile_name)

        # Verify that we now have FR translation bundle.
        with common_utils.Namespace(self.NAMESPACE):
            bundle = i18n_dashboard.ResourceBundleDAO.load(bundle_key_fr)
            self.assertEquals(
                'Title in German',
                bundle.dict['title']['data'][0]['target_value'])

        # Do a locale-agnostic download, specifying all content.
        # Since it's --export=all, we should get the unit title, but
        # since it's locale agnostic, we should get no translated text.
        os.unlink(self.zipfile_name)
        with actions.OverriddenEnvironment(extra_env):
            self.run_download_job(
                '--job_args=%s '
                '--locale_agnostic '
                '--export=all' %
                self.zipfile_name)

        with zipfile.ZipFile(self.zipfile_name) as zf:
            data = zf.read('locale/%s/LC_MESSAGES/messages.po' %
                           jobs.AGNOSTIC_EXPORT_LOCALE)
        lines = data.split('\n')
        index = lines.index('msgid "Title in base language"')
        self.assertGreater(index, -1)
        self.assertEquals('msgstr ""', lines[index + 1])

        # Do locale-agnostic download, specifying only new content.
        # We don't specificy locale, which means we should consider
        # 'de' and 'fr'.  But since both of those are up-to-date,
        # we shouldn't see the translation for the unit title even
        # appear in the output file.
        os.unlink(self.zipfile_name)
        with actions.OverriddenEnvironment(extra_env):
            self.run_download_job(
                '--job_args=%s '
                '--locale_agnostic '
                '--export=new' %
                self.zipfile_name)

        with zipfile.ZipFile(self.zipfile_name) as zf:
            data = zf.read('locale/%s/LC_MESSAGES/messages.po' %
                           jobs.AGNOSTIC_EXPORT_LOCALE)
        lines = data.split('\n')
        self.assertEquals(0, lines.count('msgid "Title in base language"'))

        # Modify unit title.
        unit = course.find_unit_by_id(unit.unit_id)
        unit.title = 'New and improved title in the base language'
        course.save()

        # Submit a new translation of the changed title, but only for DE.
        os.unlink(self.zipfile_name)
        with actions.OverriddenEnvironment(extra_env):
            self.run_download_job(
                '--job_args=%s '
                '--locale_agnostic '
                '--locales=de '
                '--export=new' %
                self.zipfile_name)

        with zipfile.ZipFile(self.zipfile_name) as zf:
            data = zf.read('locale/%s/LC_MESSAGES/messages.po' %
                           jobs.AGNOSTIC_EXPORT_LOCALE)
        lines = data.split('\n')
        index = lines.index(
            'msgid "New and improved title in the base language"')
        self.assertGreater(index, -1)
        lines[index + 1] = 'msgstr = "New and improved German title"'
        data = '\n'.join(lines)
        with zipfile.ZipFile(self.zipfile_name, 'w') as zf:
            zf.writestr('locale/%s/LC_MESSAGES/messages.po' %
                        jobs.AGNOSTIC_EXPORT_LOCALE, data)
            zf.close()

        # Run upload, forcing locale to German.
        self.run_upload_job('--job_args=%s --force_locale=de' %
                            self.zipfile_name)

        # Locale-agnostic download, for DE only, and only for 'new'
        # items.  Since we've updated the translation bundle since
        # the time we updated the course, we don't expect to see the
        # unit title exported to the .po file.
        os.unlink(self.zipfile_name)
        with actions.OverriddenEnvironment(extra_env):
            self.run_download_job(
                '--job_args=%s '
                '--locales=de '
                '--locale_agnostic '
                '--export=new' %
                self.zipfile_name)

        with zipfile.ZipFile(self.zipfile_name) as zf:
            data = zf.read('locale/%s/LC_MESSAGES/messages.po' %
                           jobs.AGNOSTIC_EXPORT_LOCALE)
        lines = data.split('\n')
        self.assertEquals(
            0,
            lines.count('msgid "New and improved title in the base language"'))

        # Exact same download, but change 'de' to 'fr'.  Since the FR
        # translation was not updated, we should see that item in the
        # export.
        os.unlink(self.zipfile_name)
        with actions.OverriddenEnvironment(extra_env):
            self.run_download_job(
                '--job_args=%s '
                '--locales=fr '
                '--locale_agnostic '
                '--export=new' %
                self.zipfile_name)

        with zipfile.ZipFile(self.zipfile_name) as zf:
            data = zf.read('locale/%s/LC_MESSAGES/messages.po' %
                           jobs.AGNOSTIC_EXPORT_LOCALE)
        lines = data.split('\n')
        self.assertEquals(
            1,
            lines.count('msgid "New and improved title in the base language"'))

        # Download again, leaving off the locales argument.  This should
        # find both locales, and in this case, since at least one of the
        # locales has not been updated, we should, again, see that item.
        os.unlink(self.zipfile_name)
        with actions.OverriddenEnvironment(extra_env):
            self.run_download_job(
                '--job_args=%s '
                '--locale_agnostic '
                '--export=new' %
                self.zipfile_name)

        with zipfile.ZipFile(self.zipfile_name) as zf:
            data = zf.read('locale/%s/LC_MESSAGES/messages.po' %
                           jobs.AGNOSTIC_EXPORT_LOCALE)
        lines = data.split('\n')
        self.assertEquals(
            1,
            lines.count('msgid "New and improved title in the base language"'))
