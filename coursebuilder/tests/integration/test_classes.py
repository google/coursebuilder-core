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

"""Functional tests for Course Builder."""

__author__ = [
    'John Orr (jorr@google.com)'
]

import collections
import os
import random
import subprocess
import time
import urllib
import urllib2
import zipfile

import pageobjects
from selenium import webdriver
from selenium.common import exceptions
from selenium.webdriver.chrome import options

from models import models
from models import transforms
from tests import suite
from tests.integration import fake_visualizations

BROWSER_WIDTH = 1000
BROWSER_HEIGHT = 1000


class BaseIntegrationTest(suite.TestBase):
    """Base class for all integration tests."""

    TAGS = {
        suite.TestBase.REQUIRES_INTEGRATION_SERVER: True,
        suite.TestBase.REQUIRES_TESTING_MODULES: set([fake_visualizations]),
        }

    LOGIN = 'test@example.com'

    def setUp(self):  # pylint: disable=g-bad-name
        super(BaseIntegrationTest, self).setUp()
        chrome_options = options.Options()
        chrome_options.add_argument('--disable-extensions')

        # Sadly, the max wait for the driver to become ready is hard-coded at
        # 30 seconds.  However, that seems like it'd be enough for our
        # purposes, so retrying the whole shebang seems like a better bet for
        # getting rid of the flakiness due to occasional failure to connect to
        # the Chrome driver.
        self.driver = None
        tries = 10
        while not self.driver:
            tries -= 1
            try:
                self.driver = webdriver.Chrome(chrome_options=chrome_options)
            except exceptions.WebDriverException, ex:
                print ex
                if tries:
                    print 'Retrying Chrome connection up to %d more times' % (
                        tries)
                else:
                    raise ex

        # Set a large enough window size independent of screen size so that all
        # click actions can be performed correctly.
        self.driver.set_window_size(BROWSER_WIDTH, BROWSER_HEIGHT)

    def tearDown(self):  # pylint: disable=g-bad-name
        time.sleep(1)  # avoid broken sockets on the server
        self.driver.quit()
        super(BaseIntegrationTest, self).tearDown()

    def load_root_page(self):
        ret = pageobjects.RootPage(self).load(
            suite.TestBase.INTEGRATION_SERVER_BASE_URL)
        tries = 10
        while tries and 'This webpage is not avail' in self.driver.page_source:
            tries -= 1
            time.sleep(1)
            ret = pageobjects.RootPage(self).load(
                suite.TestBase.INTEGRATION_SERVER_BASE_URL)
        return ret

    def load_dashboard(self, name):
        return pageobjects.DashboardPage(self).load(
            suite.TestBase.INTEGRATION_SERVER_BASE_URL, name)

    def load_appengine_admin(self, course_name):
        return pageobjects.AppengineAdminPage(
            self, suite.TestBase.ADMIN_SERVER_BASE_URL, course_name)

    def get_uid(self):
        """Generate a unique id string."""
        uid = ''
        for i in range(10):  # pylint: disable=unused-variable
            j = random.randint(0, 61)
            if j < 26:
                uid += chr(65 + j)  # ascii capital letters
            elif j < 52:
                uid += chr(97 + j - 26)  # ascii lower case letters
            else:
                uid += chr(48 + j - 52)  # ascii digits
        return uid

    def create_new_course(self):
        """Create a new course with a unique name, using the admin tools."""
        uid = self.get_uid()
        name = 'ns_%s' % uid
        title = 'Test Course (%s)' % uid

        self.load_root_page(
        ).click_login(
        ).login(
            self.LOGIN, admin=True
        ).click_admin(
        ).click_add_course(
        ).set_fields(
            name=name, title=title, email='a@bb.com'
        ).click_save(
            link_text='Add New Course', status_message='Added.'
        ).click_close()

        return (name, title)

    def set_admin_setting(self, setting_name, state):
        """Configure a property on Admin setting page."""

        self.load_root_page(
        ).click_admin(
        ).click_settings(
        ).click_override(
            setting_name
        ).set_value(
            state
        ).set_status(
            'Active'
        ).click_save(
        ).click_close()


class EtlTranslationRoundTripTest(BaseIntegrationTest):

    def setUp(self):
        super(EtlTranslationRoundTripTest, self).setUp()
        self.archive_path = self._get_archive_path('translations.zip')

    def _delete_archive_file(self):
        os.remove(self.archive_path)

    def _get_archive_path(self, name):
        return os.path.join(self.test_tempdir, name)

    def _get_etl_sh_abspath(self):
        cb_home = os.environ.get('COURSEBUILDER_HOME')
        if not cb_home:
            raise Exception('Could not find COURSEBUILDER_HOME')

        return os.path.join(cb_home, 'scripts/etl.sh')

    def _get_ln_locale_element(self, page):
        try:
            return page.find_element_by_css_selector(
                'thead > tr > th:nth-child(3)')
        except exceptions.NoSuchElementException:
            return None

    def _load_sample_course(self):
        return self.load_root_page(
        ).load_welcome_page(
            self.INTEGRATION_SERVER_BASE_URL
        ).click_explore_sample_course()

    def _run_download_course(self):
        etl_command = [
            'download', 'course', '/sample', 'mycourse', 'localhost:8081',
            '--archive_path', self.archive_path]
        self._run_etl_command(etl_command)

    def _run_download_datastore(self):
        etl_command = [
            'download', 'datastore', '/sample', 'mycourse', 'localhost:8081',
            '--archive_path', self.archive_path]
        self._run_etl_command(etl_command)

    def _run_delete_job(self):
        etl_command = [
            'run', 'modules.i18n_dashboard.jobs.DeleteTranslations', '/sample',
            'mycourse', 'localhost:8081']
        self._run_etl_command(etl_command)

    def _run_download_job(self):
        etl_command = [
            'run', 'modules.i18n_dashboard.jobs.DownloadTranslations',
            '/sample', 'mycourse', 'localhost:8081',
            '--job_args=' + self.archive_path]
        self._run_etl_command(etl_command)

    def _run_translate_job(self):
        etl_command = [
            'run', 'modules.i18n_dashboard.jobs.TranslateToReversedCase',
            '/sample', 'mycourse', 'localhost:8081']
        self._run_etl_command(etl_command)

    def _run_upload_job(self):
        etl_command = [
            'run', 'modules.i18n_dashboard.jobs.UploadTranslations', '/sample',
            'mycourse', 'localhost:8081', '--job_args=' + self.archive_path]
        self._run_etl_command(etl_command)

    def _run_etl_command(self, etl_command):
        etl_command = (['sh', self._get_etl_sh_abspath()] + etl_command)
        process = subprocess.Popen(
            etl_command, stdin=subprocess.PIPE, stderr=subprocess.PIPE,
            stdout=subprocess.PIPE)
        process.stdin.write('anything@example.com\nany_password\n')
        process.stdin.flush()
        _, stderr = process.communicate()

        if process.returncode:
            raise Exception(
                'Unable to run etl command "%s", stderr was %s' % (
                    ' '.join(etl_command), stderr))

    def assert_archive_file_exists(self):
        self.assertTrue(os.path.exists(self.archive_path))

    def assert_ln_locale_in_course(self, page):
        self.assertTrue(self._get_ln_locale_element(page))

    def assert_ln_locale_not_in_course(self, page):
        self.assertFalse(self._get_ln_locale_element(page))

    def assert_zipfile_contains_only_ln_locale(self):
        self.assert_archive_file_exists()

        with zipfile.ZipFile(self.archive_path) as zf:
            files = zf.infolist()
            self.assertEqual(
                ['locale/ln/LC_MESSAGES/messages.po'],
                [f.filename for f in files])

    def test_full_round_trip_of_data_via_i18n_dashboard_module_jobs(self):
        page = self._load_sample_course().click_i18n()
        self.assert_ln_locale_not_in_course(page)

        self._run_translate_job()
        page.click_i18n()
        self.assert_ln_locale_in_course(page)

        self._run_download_job()
        self.assert_zipfile_contains_only_ln_locale()

        self._run_delete_job()
        page.click_i18n()
        self.assert_ln_locale_not_in_course(page)

        self._run_upload_job()
        page.click_i18n()
        self.assert_ln_locale_in_course(page)

        # As an additional sanity check, make sure we can download the course
        # definitions and datastore data for a course with translations.

        self._delete_archive_file()
        self._run_download_course()
        self.assert_archive_file_exists()

        self._delete_archive_file()
        self._run_download_datastore()
        self.assert_archive_file_exists()


class SampleCourseTests(BaseIntegrationTest):
    """Integration tests on the sample course installed with Course Builder."""

    def test_admin_can_add_announcement(self):
        uid = self.get_uid()
        login = 'test-%s@example.com' % uid
        title = 'Test announcement (%s)' % uid

        self.load_root_page(
        ).click_login(
        ).login(login, admin=True)

        self.set_admin_setting('gcb_can_highlight_code', False)

        self.load_root_page(
        ).click_announcements(
        ).click_add_new(
        ).enter_fields(
            title=title,
            date='2013-03-01',
            body='The new announcement'
        ).click_save(
        ).click_close(
        ).verify_announcement(
            title=title + ' (Draft)', date='2013-03-01',
            body='The new announcement')

    def test_admin_can_change_admin_user_emails(self):
        uid = self.get_uid()
        login = 'test-%s@example.com' % uid
        email = 'new-admin-%s@foo.com' % uid

        self.load_root_page(
        ).click_login(
        ).login(
            login, admin=True
        ).click_admin(
        ).click_settings(
        ).click_override_admin_user_emails(
        ).set_value(
            email
        ).set_status(
            'Active'
        ).click_save(
        ).click_close(
        ).verify_admin_user_emails_contains(email)


class AdminTests(BaseIntegrationTest):
    """Tests for the administrator interface."""

    LOGIN = 'test@example.com'

    def test_default_course_is_read_only(self):
        self.load_root_page(
        ).click_login(
        ).login(
            self.LOGIN, admin=True
        ).click_dashboard(
        ).verify_read_only_course()

    def test_create_new_course(self):
        self.create_new_course()

    def test_add_unit(self):
        name = self.create_new_course()[0]

        self.load_dashboard(
            name
        ).verify_not_publicly_available(
        ).click_add_unit(
        ).set_title(
            'Test Unit 1'
        ).set_status(
            'Public'
        ).click_save(
        ).click_close(
        ).verify_course_outline_contains_unit('Unit 1 - Test Unit 1')

    def test_rte_codemirror(self):
        """Test that CodeMirror is working properly with rte."""

        name = self.create_new_course()[0]

        unit_title = 'Test Unit 1'
        unit_header_html = '<h1> header </h1> <p> paragraph </p>'

        self.load_dashboard(
            name
        ).click_add_unit(
        ).set_title(
            unit_title
        ).set_status(
            'Public'
        ).setvalue_codemirror(
            0, unit_header_html
        ).assert_equal_codemirror(
            0, unit_header_html
        ).click_save(
        ).click_close(
        ).click_edit_unit(
            'Unit 1 - ' + unit_title
        ).assert_equal_codemirror(
        # recheck that the data is really on the server
            0, unit_header_html
        ).click_close()

    def test_cancel_add_with_no_changes_should_not_need_confirm(self):
        """Test entering editors and clicking close without making changes."""

        name = self.create_new_course()[0]

        # Test Import
        self.load_dashboard(name).click_import(
        ).click_close(
        ).verify_not_publicly_available()  # confirm that we're on the dashboard

        # Test Add Link
        self.load_dashboard(name).click_add_link(
        ).click_close(
        ).verify_not_publicly_available()  # confirm that we're on the dashboard

        # Test Add Unit
        self.load_dashboard(name).click_add_unit(
        ).click_close(
        ).verify_not_publicly_available()  # confirm that we're on the dashboard

        # Test Add Lesson
        self.load_dashboard(name).click_add_lesson(
        ).click_close(
        ).verify_not_publicly_available()  # confirm that we're on the dashboard

        # Test Organize Units and Lessons
        self.load_dashboard(name).click_organize(
        ).click_close(
        ).verify_not_publicly_available()  # confirm that we're on the dashboard

        # Test Upload asset
        self.load_dashboard(name).click_assets(
        ).click_sub_tab(
            'Images & Documents'
        ).click_upload(
        ).click_close(
        ).verify_selected_tab('Assets')

        # Confirm that changes to the course name get alert, but no changes
        # get no alert.
        self.load_dashboard(name).click_settings(
        ).click_course_options(
        ).set_course_name(
            ''
        ).click_close_and_confirm(
        ).click_course_options(
        ).click_close()

    def test_upload_and_delete_image(self):
        """Admin should be able to upload an image and then delete it."""
        image_file = os.path.join(
            os.path.dirname(__file__), 'assets', 'img', 'test.png')

        name = self.create_new_course()[0]

        self.load_dashboard(
            name
        ).click_assets(
        ).click_sub_tab(
            'Images & Documents'
        ).click_upload(
        ).select_file(
            image_file
        ).click_upload_and_expect_saved(
        ).verify_image_file_by_name(
            'assets/img/test.png'
        ).click_edit_image(
            'assets/img/test.png'
        ).click_delete(
        ).confirm_delete(
        ).verify_no_image_file_by_name('assets/img/test.png')

    def test_add_and_edit_custom_tags(self):
        name = self.create_new_course()[0]
        instanceid_regex = 'instanceid="[A-Za-z0-9]{12}"'

        self.load_dashboard(
            name
        ).click_add_unit(
        ).set_title(
            'First Unit'
        ).click_save(
        ).click_close(
        ).click_add_lesson(
        ).click_rich_text(
        ).send_rte_text(
            'YouTube:'
        ).click_rte_add_custom_tag(
        ).select_rte_custom_tag_type(
            'gcb: YouTube Video'
        ).set_rte_lightbox_field(
            'input[name=videoid]', '123'
        ).click_rte_save(
        ).click_plain_text(
        ).ensure_instanceid_count_equals(
            1
        ).take_snapshot_of_instanceid_list(
        ).click_rich_text(
        ).doubleclick_rte_element(
            'img.gcbMarker'
        ).ensure_rte_lightbox_field_has_value(
            'input[name=videoid]', '123'
        ).set_rte_lightbox_field(
            'input[name=videoid]', '321'
        ).click_rte_save(
        ).click_plain_text(
        ).ensure_lesson_body_textarea_matches_regex(
            'YouTube:<gcb-youtube videoid="321" %s>'
            '</gcb-youtube>' % instanceid_regex
        ).ensure_instanceid_list_matches_last_snapshot(
        ).click_rich_text(
        ).send_rte_text(
            'Google Group:'
        ).click_rte_add_custom_tag(
        ).select_rte_custom_tag_type(
            'gcb: Google Group'
        ).set_rte_lightbox_field(
            'input[name=group]', 'abc'
        ).set_rte_lightbox_field(
            'input[name=category]', 'def'
        ).click_rte_save(
        ).click_plain_text(
        ).ensure_lesson_body_textarea_matches_regex(
            'Google Group:'
            '<gcb-googlegroup group="abc" category="def" %s></gcb-googlegroup>'
            'YouTube:<gcb-youtube videoid="321" %s></gcb-youtube>' % (
                instanceid_regex, instanceid_regex
            )
        )

    def test_add_edit_delete_label(self):
        name = self.create_new_course()[0]

        self.load_dashboard(
            name
        ).click_assets(
        ).click_sub_tab(
            'Labels'
        ).click_add_label(
        ).set_title(
            'Liver'
        ).set_description(
            'Exercise and diet to support healthy hepatic function'
        ).set_type(
            models.LabelDTO.LABEL_TYPE_COURSE_TRACK
        ).click_save(
        ).click_close(
        ).verify_label_present(
            'Liver'
        ).click_edit_label(
            'Liver'
        ).verify_title(
            'Liver'
        ).verify_description(
            'Exercise and diet to support healthy hepatic function'
        ).verify_type(
            models.LabelDTO.LABEL_TYPE_COURSE_TRACK
        ).set_title(
            'Kidney'
        ).click_save(
        ).click_close(
        ).verify_label_present(
            'Kidney'
        ).click_edit_label(
            'Kidney'
        ).click_delete(
        ).confirm_delete(
        ).verify_label_not_present(
            'Kidney'
        ).verify_label_not_present(
            'Liver'
        )


class QuestionsTest(BaseIntegrationTest):

    def test_add_question_and_solve_it(self):
        name = self.create_new_course()[0]

        self.set_admin_setting('gcb_can_highlight_code', False)

        self.load_dashboard(
            name
        ).click_course(
        ).click_register(
        ).enroll(
            'John Smith'
        ).click_course(
        ).click_dashboard(

        #---------------------------------------------- Question
        ).click_assets(
        ).click_sub_tab(
            'Questions'
        ).click_add_multiple_choice(
        ).set_question(
            'What is your favorite color?'
        ).set_description(
            'Multiple choice question'
        ).set_answer(
            0, 'Red'
        ).set_answer(
            1, 'Blue'
        ).set_answer(
            2, 'Yellow'
        ).set_answer(
            3, 'Pink'
        ).click_save(
        ).click_close(
        ).verify_question_exists(
            'Multiple choice question'
        ).click_question_preview(
        ).verify_question_preview(
            'What is your favorite color?'
        ).click_outline(
        ).verify_not_publicly_available(
        #---------------------------------------------- Unit
        ).click_add_unit(
        ).set_title(
            'Test Unit 1'
        ).set_status(
            'Public'
        ).set_contents_on_one_page(
            True
        ).click_save(
        ).click_close(
        ).verify_course_outline_contains_unit(
            'Unit 1 - Test Unit 1'
        #---------------------------------------------- Lesson 1 (graded)
        ).click_add_lesson(
        ).set_title(
            'Question lesson - Graded'
        ).set_status(
            'Public'
        ).set_questions_are_scored(
        ).click_rich_text(
        ).click_rte_add_custom_tag(
        ).select_rte_custom_tag_type(
            'gcb: Question'
        ).set_rte_lightbox_field(
            'input[name=weight]', 1
        ).click_rte_save(
        ).click_save(
        ).click_close(
        #---------------------------------------------- Lesson 2 (ungraded)
        ).click_add_lesson(
        ).set_title(
            'Question lesson - UnGraded'
        ).set_status(
            'Public'
        ).click_rich_text(
        ).click_rte_add_custom_tag(
        ).select_rte_custom_tag_type(
            'gcb: Question'
        ).set_rte_lightbox_field(
            'input[name=weight]', 1
        ).click_rte_save(
        ).click_save(
        ).click_close(
        #---------------------------------------------- Assessment pre (ID 4)
        ).click_add_assessment(
        ).set_title(
            'Pre-Assessment'
        ).set_status(
            'Public'
        ).click_rich_text(
            pageobjects.AddAssessment.INDEX_CONTENT
        ).click_rte_add_custom_tag(
            pageobjects.AddAssessment.INDEX_CONTENT
        ).select_rte_custom_tag_type(
            'gcb: Question'
        ).set_rte_lightbox_field(
            'input[name=weight]', 1
        ).click_rte_save(
        ).click_save(
        ).click_close(
        #---------------------------------------------- Assessment post (ID 5)
        ).click_add_assessment(
        ).set_title(
            'Post-Assessment'
        ).set_status(
            'Public'
        ).click_rich_text(
            pageobjects.AddAssessment.INDEX_CONTENT
        ).click_rte_add_custom_tag(
            pageobjects.AddAssessment.INDEX_CONTENT
        ).select_rte_custom_tag_type(
            'gcb: Question'
        ).set_rte_lightbox_field(
            'input[name=weight]', 1
        ).click_rte_save(
        ).click_save(
        ).click_close(
        #---------------------------------------------- Add assessments to unit
        ).click_edit_unit(
            'Unit 1 - Test Unit 1'
        ).set_pre_assessment(
            'Pre-Assessment'
        ).set_post_assessment(
            'Post-Assessment'
        ).click_save(
        ).click_close(
        ).click_on_course_outline_components(
            'Question lesson - UnGraded'
        #---------------------------------------------- Verify pre-assessment
        ).set_answer_for_mc_question(
            'A4', 'What is your favorite color?', 'Red'
        ).submit_question_batch(
            'A4', 'Submit Answers'
        ).verify_correct_submission(
        ).return_to_unit(
        #---------------------------------------------- Verify non-graded
        ).set_answer_for_mc_question(
            'L3', 'What is your favorite color?', 'Yellow'
        ).submit_question_batch(
            'L3', 'Check Answer'
        ).verify_incorrect_submission(
            'L3', 'What is your favorite color?'
        ).set_answer_for_mc_question(
            'L3', 'What is your favorite color?', 'Red'
        ).submit_question_batch(
            'L3', 'Check Answer'
        ).verify_correct_submission(
            'L3', 'What is your favorite color?'
        #---------------------------------------------- Verify graded
        ).set_answer_for_mc_question(
            'L2', 'What is your favorite color?', 'Red'
        ).submit_question_batch(
            'L2', 'Grade Questions'
        ).verify_correct_grading(
            'L2'
        ).set_answer_for_mc_question(
            'L2', 'What is your favorite color?', 'Pink'
        ).submit_question_batch(
            'L2', 'Grade Questions'
        ).verify_incorrect_grading(
            'L2'
        #---------------------------------------------- Verify post-assessment
        ).set_answer_for_mc_question(
            'A5', 'What is your favorite color?', 'Blue'
        ).submit_question_batch(
            'A5', 'Submit Answers'
        ).verify_incorrect_submission(
        ).return_to_unit()


class VisualizationsTest(BaseIntegrationTest):

    def setUp(self):
        super(VisualizationsTest, self).setUp()
        self._name = self.create_new_course()[0]

    def _have_page_number(self, page, data_source, page_number):
        return (page.get_data_page_number(data_source) == page_number and
                page.get_displayed_page_number(data_source) == str(page_number))

    def _assert_have_page_number(self, page, data_source, page_number):
        self.assertEquals(page_number, page.get_data_page_number(data_source))
        self.assertEquals(str(page_number), page.get_displayed_page_number(
            data_source))

    def _wait_for_page_number(self, page, data_source, page_number):
        max_time = time.time() + 10
        while (time.time() < max_time and
               not self._have_page_number(page, data_source, page_number)):
            time.sleep(0.1)
        self._assert_have_page_number(page, data_source, page_number)

    def _force_response_common(self, data_source, action, page_number=0):
        url = (suite.TestBase.INTEGRATION_SERVER_BASE_URL +
               fake_visualizations.ForceResponseHandler.URL)
        fp = urllib2.urlopen(url, urllib.urlencode({
            fake_visualizations.ForceResponseHandler.PARAM_DATA_SOURCE:
                data_source,
            fake_visualizations.ForceResponseHandler.PARAM_ACTION:
                action,
            fake_visualizations.ForceResponseHandler.PARAM_PAGE_NUMBER:
                page_number,
            }))
        fp.read()
        fp.close()

    def _force_response_exception(self, data_source):
        self._force_response_common(
            data_source,
            fake_visualizations.ForceResponseHandler.ACTION_EXCEPTION)

    def _force_response_log_critical(self, data_source):
        self._force_response_common(
            data_source,
            fake_visualizations.ForceResponseHandler.ACTION_LOG_CRITICAL)

    def _force_response_page_number(self, data_source, page_number):
        self._force_response_common(
            data_source,
            fake_visualizations.ForceResponseHandler.ACTION_PAGE_NUMBER,
            page_number)

    def test_exams_simple(self):
        page = self.load_dashboard(self._name).click_analytics('Exams')

        # Seeing this zero proves we have really loaded data to page via REST.
        self.assertEquals(0, page.get_data_page_number('exams'))

        # Verify that page controls and page number are not displayed.
        self.assertEquals('', page.get_displayed_page_number('exams'))
        self.assertFalse(page.buttons_present('exams'))

        self._force_response_log_critical('exams')
        page = self.load_dashboard(self._name).click_analytics(
            'Exams').wait_until_logs_not_empty('exams')
        self.assertEquals('critical: Error for testing',
                          page.get_data_source_logs('exams'))

        self._force_response_exception('exams')
        page = self.load_dashboard(self._name).click_analytics(
            'Exams').wait_until_logs_not_empty('exams')

        self.assertRegexpMatches(
            page.get_data_source_logs('exams'),
            'critical: Fetching results data: ValueError: Error for testing')

    def test_pupils_page_navigation(self):
        page = self.load_dashboard(self._name).click_analytics('Pupils')

        # Initial load of page shoud use data page zero
        self._assert_have_page_number(page, 'pupils', 0)

        # Click forward to data page 1
        page.click('pupils', 'plusone')
        self._wait_for_page_number(page, 'pupils', 1)

        # Pretend that page 1 is the last with data; click forward.
        self._force_response_page_number('pupils', 1)
        page.click('pupils', 'plusone')
        self._wait_for_page_number(page, 'pupils', 1)
        self.assertEquals('warning: Stopping at last page 1',
                          page.get_data_source_logs('pupils'))
        page.click('pupils', 'minusone')
        self._wait_for_page_number(page, 'pupils', 0)

        page.click('pupils', 'plusten')
        self._wait_for_page_number(page, 'pupils', 10)
        page.click('pupils', 'plusone')
        self._wait_for_page_number(page, 'pupils', 11)
        page.click('pupils', 'plusten')
        self._wait_for_page_number(page, 'pupils', 21)
        page.click('pupils', 'plusone')
        self._wait_for_page_number(page, 'pupils', 22)

        self._force_response_page_number('pupils', 22)
        page.click('pupils', 'plusten')
        self._wait_for_page_number(page, 'pupils', 22)
        self.assertEquals('warning: Stopping at last page 22',
                          page.get_data_source_logs('pupils'))

        page.click('pupils', 'minusone')
        self._wait_for_page_number(page, 'pupils', 21)
        page.click('pupils', 'minusone')
        self._wait_for_page_number(page, 'pupils', 20)
        page.click('pupils', 'minusone')
        self._wait_for_page_number(page, 'pupils', 19)
        page.click('pupils', 'minusten')
        self._wait_for_page_number(page, 'pupils', 9)
        page.click('pupils', 'minusten')
        self._wait_for_page_number(page, 'pupils', 0)
        page.click('pupils', 'minusone')
        self._wait_for_page_number(page, 'pupils', 0)
        page.click('pupils', 'minusten')
        self._wait_for_page_number(page, 'pupils', 0)

    def test_pupils_caching(self):
        page = self.load_dashboard(self._name).click_analytics('Pupils')
        self._assert_have_page_number(page, 'pupils', 0)
        page.click('pupils', 'plusone')
        self._wait_for_page_number(page, 'pupils', 1)
        page.click('pupils', 'plusone')
        self._wait_for_page_number(page, 'pupils', 2)

        # Pretend page one now has a problem on the server side;
        # click back to page one.  We expect to _not_ see that
        # exception, since we've cached page one.
        self._force_response_log_critical('pupils')
        page.click('pupils', 'minusone')
        self._wait_for_page_number(page, 'pupils', 1)
        self.assertEquals('', page.get_page_level_logs())

        # Now change the number of items in a data page; click back
        # to page zero.  We _do_ expect to now see that exception,
        # since we should drop our cached pages since the parameters
        # to the page selection have changed.
        page.set_chunk_size('pupils', 3)
        page.click('pupils', 'minusone')
        self._wait_for_page_number(page, 'pupils', 0)
        self.assertEquals('critical: Error for testing',
                          page.get_data_source_logs('pupils'))

    def test_dimension_gc(self):
        page = self.load_dashboard(self._name).click_analytics('Scoring')
        self._wait_for_page_number(page, 'answers', 0)

        # Scoring page has a pie chart.
        self.assertTrue(page.answers_pie_chart_present())

        # If we haven't been cleaning up crossfilter dimensions, when
        # we hit 32, crossfilter will pitch a fit and the chart won't
        # display.
        for _ in range(32):
            page.click('answers', 'minusone')
        self.assertTrue(page.answers_pie_chart_present())

    def test_data_sources_independent(self):
        page = self.load_dashboard(self._name).click_analytics('Scoring')
        self._wait_for_page_number(page, 'pupils', 0)
        self._wait_for_page_number(page, 'answers', 0)

        self._force_response_log_critical('answers')
        self._force_response_exception('pupils')

        page.click('pupils', 'plusone')
        self._wait_for_page_number(page, 'pupils', 0)
        self._wait_for_page_number(page, 'answers', 0)
        self.assertRegexpMatches(
            page.get_data_source_logs('pupils'),
            'critical: Fetching results data: ValueError: Error for testing')
        self.assertEquals('', page.get_data_source_logs('answers'))

        page.click('pupils', 'plusone')
        self._wait_for_page_number(page, 'pupils', 1)
        self._wait_for_page_number(page, 'answers', 0)
        self.assertEquals('', page.get_data_source_logs('pupils'))
        self.assertEquals('', page.get_data_source_logs('answers'))

        page.click('answers', 'plusone')
        self._wait_for_page_number(page, 'pupils', 1)
        self._wait_for_page_number(page, 'answers', 1)
        self.assertEquals('', page.get_data_source_logs('pupils'))
        self.assertEquals('critical: Error for testing',
                          page.get_data_source_logs('answers'))


class EventsTest(BaseIntegrationTest):

    def test_html5_video_events(self):
        name = self.create_new_course()[0]

        # Set gcb_can_persist_tag_events so we will track video events.
        self.load_root_page(
        ).click_admin(
        ).click_settings(
        ).click_override(
            'gcb_can_persist_tag_events'
        ).set_value(
            True
        ).set_status(
            'Active'
        ).click_save()

        # Add a unit with a video.
        instanceid_list = []
        self.load_dashboard(
            name
        ).click_add_unit(
        ).set_title(
            'First Unit'
        ).set_status(
            'Public'
        ).click_rich_text(
            pageobjects.AddUnit.INDEX_UNIT_HEADER
        ).click_rte_add_custom_tag(
        ).select_rte_custom_tag_type(
            'gcb: HTML5 Video'
        ).set_rte_lightbox_field(
            'input[name=url]',
            'http://techslides.com/demos/sample-videos/small.mp4'
        ).click_rte_save(
        ).click_plain_text(
        ).take_snapshot_of_instanceid_list(
            instanceid_list
        ).click_save(
        )
        instanceid = instanceid_list[0]

        # Load the unit with the video and fiddle with the controls.
        self.load_dashboard(
            name
        ).click_on_course_outline_components(
            'Unit 1 - First Unit'
        ).wait_for_video_state(
            instanceid, 'readyState', 4, 10
        ).play_video(
            instanceid
        ).wait_for_video_state(
            instanceid, 'paused', False, 10
        ).pause_video(
            instanceid
        ).wait_for_video_state(
            instanceid, 'paused', True, 10
        ).play_video(
            instanceid
        ).wait_for_video_state(
            instanceid, 'ended', True, 10
        )

        # Verify that we have two events logged: load-start, and error.
        data = self.load_appengine_admin(
            name
        ).get_datastore(
            'EventEntity'
        ).get_items(
        )

        events = []
        for datum in data:
            events.append(transforms.loads(datum['data']))
        events.sort(key=lambda event: event['event_id'])

        # Sometimes get this, sometimes don't.  Don't check for this to
        # avoid flakiness.
        if events[0]['event_type'] == 'loadstart':
            del events[0]

        ExpectedEvent = collections.namedtuple(
            'ExpectedEvent', ['event_type', 'position'])
        expected_events = [
            ExpectedEvent('loadeddata', 'zero'),
            ExpectedEvent('play', 'zero'),
            ExpectedEvent('playing', 'zero'),
            ExpectedEvent('pause', 'middle'),
            ExpectedEvent('play', 'middle'),
            ExpectedEvent('playing', 'middle'),
            ExpectedEvent('pause', 'end'),
            ExpectedEvent('ended', 'end'),
            ]

        end_position = 5.568
        for event, expected in zip(events, expected_events):
            self.assertEquals(instanceid, event['instance_id'])
            self.assertEquals(1, event['rate'])
            self.assertEquals(1, event['default_rate'])
            self.assertEquals(expected.event_type, event['event_type'])
            if expected.position == 'zero':
                self.assertEquals(0, event['position'])
            elif expected.position == 'middle':
                self.assertNotEquals(0, event['position'])
                self.assertNotEquals(end_position, event['position'])
            elif expected.position == 'end':
                self.assertEquals(end_position, event['position'])
