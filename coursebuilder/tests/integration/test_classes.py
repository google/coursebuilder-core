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
import time
import urllib
import urllib2

from models import transforms
from tests.integration import fake_visualizations
from tests.integration import integration
from tests.integration import pageobjects


class IntegrationServerInitializationTask(integration.TestBase):

    def test_setup_default_course(self):
        self.load_root_page()._add_default_course_if_needed(
            integration.TestBase.INTEGRATION_SERVER_BASE_URL)


class SampleCourseTests(integration.TestBase):
    """Integration tests on the sample course installed with Course Builder."""

    def test_admin_can_add_announcement(self):
        uid = self.get_uid()
        login = 'test-%s@example.com' % uid
        title = 'Test announcement (%s)' % uid

        self.login(login, admin=True)

        self.load_root_page(
        ).click_announcements(
        ).click_add_new(
        ).enter_fields(
            title=title,
            date='2013-03-01',
            body='The new announcement'
        ).click_save(
        ).click_close(
        ).click_view_item(
            0, pageobjects.AnnouncementsPage
        ).verify_announcement(
            title=title + ' (Private)', date='2013-03-01',
            body='The new announcement')

    def test_admin_can_change_admin_user_emails(self):
        uid = self.get_uid()
        login = 'test-%s@example.com' % uid
        email = 'new-admin-%s@foo.com' % uid

        self.login(
            login, admin=True
        ).click_dashboard(
        ).click_admin(
        ).click_site_settings(
        ).click_override_admin_user_emails(
        ).set_value(
            email
        ).click_save(
        ).click_close(
        ).verify_admin_user_emails_contains(email)


class AdminTests(integration.TestBase):
    """Tests for the administrator interface."""

    LOGIN = 'test@example.com'

    def test_default_course_is_read_only(self):
        self.login(
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
        ).click_plain_text(
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

    def test_in_place_lesson_editing(self):
        name = self.create_new_course()[0]
        self.load_dashboard(
            name
        ).click_add_unit(
        ).set_title(
            'Test Unit 1'
        ).click_save(
        ).click_close(
        ).verify_course_outline_contains_unit(
            'Unit 1 - Test Unit 1'
        ).click_add_lesson(
        ).set_title(
            'Test Lesson'
        ).select_settings(
        ).select_content(
        ).click_plain_text(
        ).setvalue_codemirror(
            0, 'Lorem ipsum'
        ).click_save(
        ).click_close(
        ).click_on_course_outline_components(
            '1. Test Lesson'
        ).click_edit_lesson(
        ).edit_lesson_iframe_assert_equal_codemirror(
            'Lorem ipsum'
        ).edit_lesson_iframe_setvalue_codemirror(
            'Lorem ipsum dolor sit amet'
        ).edit_lesson_iframe_click_save(
        ).assert_lesson_content_contains('Lorem ipsum dolor sit amet')

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

        # Test Upload asset
        self.load_dashboard(name).click_edit(
        ).click_sub_tab(
            'Images'
        ).click_upload(
        ).click_close(
        ).verify_selected_group('edit')

    def test_leave_page_with_changes_triggers_alert(self):
        """Opens an editor page, make changes and tries to leave.

        Expects an alert for confirmation.
        """
        name = self.create_new_course()[0]
        confirm_message = ('You have unsaved changes that will be lost if'
                           ' you leave.')
        # Test back arrow
        browser = self.load_dashboard(name).click_add_unit(
        ).set_contents_on_one_page(True).go_back(expect_exception=True)
        alert = browser.switch_to_alert()
        self.assertEqual(confirm_message, alert.text)
        alert.accept()
        self.assertEqual(browser.where_am_i(), 'dashboard')

        # Test click close button
        browser = self.load_dashboard(name).click_add_unit(
        ).set_contents_on_one_page(True).click_close()
        alert = browser.switch_to_alert()
        self.assertEqual(confirm_message, alert.text)
        alert.accept()
        self.assertEqual(browser.where_am_i(), 'dashboard')

        # Test click navigation bar button
        dashboard = self.load_dashboard(name)
        dashboard.click_add_unit().set_contents_on_one_page(True)
        dashboard.click_edit()
        alert = browser.switch_to_alert()
        self.assertEqual(confirm_message, alert.text)
        alert.accept()
        self.assertEqual(browser.where_am_i(), 'dashboard?action=outline')

        # Test cancel the alert
        browser = self.load_dashboard(name).click_add_unit(
        ).set_contents_on_one_page(True).go_back(expect_exception=True)
        browser.switch_to_alert().dismiss()
        self.assertNotEqual(browser.where_am_i(), 'dashboard')

    def test_upload_and_delete_image(self):
        """Admin should be able to upload an image and then delete it."""
        image_file = os.path.join(
            os.path.dirname(__file__), 'assets', 'img', 'test.png')

        name = self.create_new_course()[0]

        self.load_dashboard(
            name
        ).click_edit(
        ).click_sub_tab(
            'Images'
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
        video_id_1 = 'f1U4SAgy60c'
        video_id_2 = 'https://www.youtube.com/embed/sIE0mcOGnms'

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
            'YouTube Video'
        ).set_rte_lightbox_field(
            'input[name=videoid]', video_id_1
        ).click_rte_save(
        ).click_preview(
        ).ensure_preview_document_matches_text(
            '<script>gcbTagYoutubeEnqueueVideo("' + video_id_1 + '", '
        ).click_plain_text(
        ).ensure_instanceid_count_equals(
            1
        ).take_snapshot_of_instanceid_list(
        ).click_rich_text(
        ).doubleclick_rte_element(
            'img.gcbMarker'
        ).ensure_rte_lightbox_field_has_value(
            'input[name=videoid]', video_id_1
        ).set_rte_lightbox_field(
            'input[name=videoid]', video_id_2
        ).click_rte_save(
        ).click_plain_text(
        ).ensure_lesson_body_textarea_matches_regex(
            'YouTube:<gcb-youtube videoid="' + video_id_2 + '" %s>'
            '</gcb-youtube>' % instanceid_regex
        ).ensure_instanceid_list_matches_last_snapshot(
        ).click_rich_text(
        ).send_rte_text(
            'Google Group:'
        ).click_rte_add_custom_tag(
            'Google Group'
        ).set_rte_lightbox_field(
            'input[name=group]', 'abc'
        ).set_rte_lightbox_field(
            'input[name=category]', 'def'
        ).click_rte_save(
        ).click_plain_text(
        ).ensure_lesson_body_textarea_matches_regex(
            'YouTube:<gcb-youtube videoid="' + video_id_2 +
            '" %s></gcb-youtube>'
            'Google Group:'
            '<gcb-googlegroup group="abc" category="def" %s>'
            '</gcb-googlegroup>' % (instanceid_regex, instanceid_regex)
        ).click_save(
        #---------- Test editor state is saved ----------
        ).click_close(
        ).click_edit_lesson(
            '1. New Lesson'
        ).assert_editor_mode_is_html(
        ).click_rich_text(
        ).click_save(
        ).click_close(
        ).click_edit_lesson(
            '1. New Lesson'
        ).assert_editor_mode_is_rich_text()

    def test_add_edit_delete_label(self):
        name = self.create_new_course()[0]

        self.load_dashboard(
            name
        ).click_edit(
        ).click_sub_tab(
            'Tracks'
        ).click_add_label(
            'Add Track'
        ).set_title(
            'Liver'
        ).set_description(
            'Exercise and diet to support healthy hepatic function'
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


class QuestionsTest(integration.TestBase):

    def test_inline_question_creation(self):
        name = self.create_new_course()[0]

        self.load_dashboard(
            name
        ).click_add_unit(
        ).set_title(
            'Test Unit'
        ).click_save(
        ).click_close(
        ).click_add_lesson(
        ).set_title(
            'Test Lesson'
        ).click_rich_text(

        #---------------------------------------------- Add a MC question
        ).click_rte_add_custom_tag(
            'Question'
        ).click_rte_element(
            '#mc_tab'
        ).set_rte_lightbox_field(
            '.mc-container [name="description"]', 'mc question'
        ).set_rte_lightbox_field(
            '.question-weight [name="weight"]', '23'
        ).set_rte_lightbox_field(
            '.mc-container .yui-editor-editable', 'What color is the sky?',
            index=0, clear=False
        ).set_rte_lightbox_field(
            '.mc-container .yui-editor-editable', 'Blue',
            index=2, clear=False
        ).click_rte_link(
            'Add a choice'
        ).set_rte_lightbox_field(
            '.mc-container .yui-editor-editable', 'Red',
            index=4, clear=False
        ).click_rte_link(
            'Add a choice'
        ).set_rte_lightbox_field(
            '.mc-container .yui-editor-editable', 'Green',
            index=6, clear=False
        ).click_rte_link(
            'Add a choice'
        ).set_rte_lightbox_field(
            '.mc-container .yui-editor-editable', 'Yellow',
            index=8, clear=False
        ).click_rte_save(
        ).doubleclick_rte_element(
            'img'
        ).ensure_rte_lightbox_field_has_value(
            '.mc-container [name="description"]', 'mc question'
        ).ensure_rte_lightbox_field_has_value(
            '.question-weight [name="weight"]', '23'
        ).click_rte_close(
        ).click_preview(
        #---------------------------------------------- Confirm in preview
        ).ensure_preview_document_matches_text(
            '23 points'
        ).ensure_preview_document_matches_text(
            'What color is the sky?'
        ).click_rich_text(

        #---------------------------------------------- Add a SA questions
        ).click_rte_add_custom_tag(
            'Question'
        ).click_rte_element(
            '#sa_tab'
        ).set_rte_lightbox_field(
            '.sa-container [name="description"]', 'sa question',
        ).set_rte_lightbox_field(
            '.question-weight [name="weight"]', '24',
        ).set_rte_lightbox_field(
            '.sa-container .yui-editor-editable', 'Type "woof"',
            index=0, clear=False
        ).set_rte_lightbox_field(
            '.sa-container [name="graders[0]response"]', 'woof'
        ).click_rte_save(
        ).doubleclick_rte_element(
            'img:nth-of-type(2)', index=0
        ).ensure_rte_lightbox_field_has_value(
            '.sa-container [name="description"]', 'sa question'
        ).ensure_rte_lightbox_field_has_value(
            '.question-weight [name="weight"]', '24'
        ).click_rte_close(
        ).click_preview(
        #---------------------------------------------- Confirm in preview
        ).ensure_preview_document_matches_text(
            '24 points'
        ).ensure_preview_document_matches_text(
            'Type "woof"'
        ).ensure_preview_document_matches_text(
            '23 points'
        ).ensure_preview_document_matches_text(
            'What color is the sky?'
        )

    def test_add_question_and_solve_it(self):
        name = self.create_new_course()[0]
        root_page = self.load_root_page(
        ).register_for_course(
            name
        )

        # Note the occasional breaks in the fluent structure of the code in
        # this test are because Pylint has stack overflow problems with very
        # long chained expressions.

        page = root_page.click_dashboard(

        #---------------------------------------------- Question
        ).click_edit(
        ).click_sub_tab(
            'Questions'
        ).click_add_multiple_choice(
        ).set_question(
            'What is your favorite color?'
        ).set_description(
            'Multiple choice question'
        ).set_answer(
            0, 'Red'
        ).click_add_choice(
        ).set_answer(
            1, 'Blue'
        ).click_add_choice(
        ).set_answer(
            2, 'Yellow'
        ).click_add_choice(
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
        ).set_contents_on_one_page(
            True
        ).click_save(
        ).click_close(
        ).verify_course_outline_contains_unit(
            'Unit 1 - Test Unit 1'
        #---------------------------------------------- Lesson 1 (graded)
        )

        page = page.click_add_lesson(
        ).set_title(
            'Question lesson - Graded'
        ).select_settings(
        ).set_questions_are_scored(
        ).select_content(
        ).click_rich_text(
        ).click_rte_add_custom_tag(
            'Question'
        ).click_rte_element(
            '#select_tab'
        ).set_rte_lightbox_field(
            '.question-weight input[name=weight]', 1
        ).click_rte_element(
            '.select-container [name="quid"] option:nth-child(2)'
        ).click_rte_save(
        ).click_save(
        ).click_close(
        #---------------------------------------------- Lesson 2 (ungraded)
        ).click_add_lesson(
        ).set_title(
            'Question lesson - UnGraded'
        ).select_settings(
        ).select_content(
        ).click_rich_text(
        ).click_rte_add_custom_tag(
            'Question'
        ).click_rte_element(
            '#select_tab'
        ).set_rte_lightbox_field(
            '.question-weight input[name=weight]', 1
        ).click_rte_element(
            '.select-container [name="quid"] option:nth-child(2)'
        ).click_rte_save(
        ).click_save(
        ).click_close(
        #---------------------------------------------- Assessment pre (ID 4)
        )

        page = page.click_add_assessment(
        ).set_title(
            'Pre-Assessment'
        ).click_rich_text(
            pageobjects.AddAssessment.INDEX_CONTENT
        ).click_rte_add_custom_tag(
            'Question',
            pageobjects.AddAssessment.INDEX_CONTENT
        ).click_rte_element(
            '#select_tab'
        ).set_rte_lightbox_field(
            '.question-weight input[name=weight]', 1
        ).click_rte_element(
            '.select-container [name="quid"] option:nth-child(2)'
        ).click_rte_save(
        ).click_save(
        ).click_close(
        #---------------------------------------------- Assessment post (ID 5)
        )

        page = page.click_add_assessment(
        ).set_title(
            'Post-Assessment'
        ).click_rich_text(
            pageobjects.AddAssessment.INDEX_CONTENT
        ).click_rte_add_custom_tag(
            'Question',
            pageobjects.AddAssessment.INDEX_CONTENT
        ).click_rte_element(
            '#select_tab'
        ).set_rte_lightbox_field(
            '.question-weight input[name=weight]', 1
        ).click_rte_element(
            '.select-container [name="quid"] option:nth-child(2)'
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
            '2. Question lesson - UnGraded'
        #---------------------------------------------- Verify pre-assessment
        )

        page.set_answer_for_mc_question(
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


class VisualizationsTest(integration.TestBase):

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
        url = (integration.TestBase.INTEGRATION_SERVER_BASE_URL +
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
        self.assertEquals('', page.get_displayed_page_number(
            'exams', pre_wait=False))
        self.assertFalse(page.buttons_present('exams', pre_wait=False))

        self._force_response_log_critical('exams')
        page = self.load_dashboard(self._name).click_analytics(
            'Exams').wait_until_logs_not_empty('exams')
        page.wait_until_logs_not_empty('exams')
        self.assertEquals('critical: Error for testing',
                          page.get_data_source_logs('exams'))

        self._force_response_exception('exams')
        page = self.load_dashboard(self._name).click_analytics(
            'Exams').wait_until_logs_not_empty('exams')

        page.wait_until_logs_not_empty('exams')
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
        page.wait_until_logs_not_empty('pupils')
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
        page.wait_until_logs_not_empty('pupils')
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
        page.wait_until_logs_not_empty('pupils')
        self.assertEquals('critical: Error for testing',
                          page.get_data_source_logs('pupils'))

    def test_dimension_gc(self):
        page = self.load_dashboard(self._name).click_analytics('Scoring')
        self._wait_for_page_number(page, 'fake_answers', 0)

        # Scoring page has a pie chart.
        self.assertTrue(page.answers_pie_chart_present())

        # If we haven't been cleaning up crossfilter dimensions, when
        # we hit 32, crossfilter will pitch a fit and the chart won't
        # display.
        for _ in range(32):
            page.click('fake_answers', 'minusone')
        self.assertTrue(page.answers_pie_chart_present())

    def test_data_sources_independent(self):
        page = self.load_dashboard(self._name).click_analytics('Scoring')
        self._wait_for_page_number(page, 'pupils', 0)
        self._wait_for_page_number(page, 'fake_answers', 0)

        self._force_response_log_critical('fake_answers')
        self._force_response_exception('pupils')

        page.click('pupils', 'plusone')
        self._wait_for_page_number(page, 'pupils', 0)
        self._wait_for_page_number(page, 'fake_answers', 0)
        page.wait_until_logs_not_empty('pupils')
        self.assertRegexpMatches(
            page.get_data_source_logs('pupils'),
            'critical: Fetching results data: ValueError: Error for testing')
        self.assertEquals('', page.get_data_source_logs('fake_answers'))

        page.click('pupils', 'plusone')
        self._wait_for_page_number(page, 'pupils', 1)
        self._wait_for_page_number(page, 'fake_answers', 0)
        self.assertEquals('', page.get_data_source_logs('pupils'))
        self.assertEquals('', page.get_data_source_logs('fake_answers'))

        page.click('fake_answers', 'plusone')
        self._wait_for_page_number(page, 'pupils', 1)
        self._wait_for_page_number(page, 'fake_answers', 1)
        self.assertEquals('', page.get_data_source_logs('pupils'))
        page.wait_until_logs_not_empty('fake_answers')
        self.assertEquals('critical: Error for testing',
                          page.get_data_source_logs('fake_answers'))


class EventsTest(integration.TestBase):

    def test_html5_video_events(self):
        name = self.create_new_course()[0]

        # Set Enable Student Analytics so we will track video events.
        self.load_dashboard(name
        ).click_settings(
        ).set_checkbox_by_title(
            'Enable Student Analytics', True
        ).click_save()

        # Add a unit with a video.
        instanceid_list = []
        self.load_dashboard(
            name
        ).click_add_unit(
        ).set_title(
            'First Unit'
        ).click_rich_text(
            pageobjects.AddUnit.INDEX_UNIT_HEADER
        ).click_rte_add_custom_tag(
            'HTML5 Video'
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
            instanceid, 'paused', None, 10
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

        events = [transforms.loads(d['data']) for d in data]
        events = [e for e in events if 'event_id' in e]
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

        # Positions are in seconds since start of video
        end_position = 5.568
        for event, expected in zip(events, expected_events):
            self.assertEquals(instanceid, event['instance_id'])
            self.assertEquals(1, event['rate'])
            self.assertEquals(1, event['default_rate'])
            self.assertEquals(expected.event_type, event['event_type'])
            if expected.position == 'zero':
                self.assertAlmostEqual(0, event['position'], delta=0.03)
            elif expected.position == 'middle':
                self.assertNotAlmostEquals(0, event['position'], delta=0.03)
                self.assertNotAlmostEquals(
                    end_position, event['position'], delta=0.03)
            elif expected.position == 'end':
                self.assertAlmostEquals(
                    end_position, event['position'], delta=0.03)


class IntegrationTestBundle1(
        AdminTests, EventsTest, QuestionsTest, SampleCourseTests):
    """Test bundle that forces serial execution of all containing tests."""
    pass
