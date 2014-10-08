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

"""Page objects used in functional tests for Course Builder."""

__author__ = [
    'John Orr (jorr@google.com)'
]

import re
import time

from selenium.common import exceptions
from selenium.webdriver.common import action_chains
from selenium.webdriver.common import by
from selenium.webdriver.common import keys
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.support import select
from selenium.webdriver.support import wait


DEFAULT_TIMEOUT = 15


def get_parent_element(web_element):
    return web_element.find_element_by_xpath('..')


class PageObject(object):
    """Superclass to hold shared logic used by page objects."""

    def __init__(self, tester):
        self._tester = tester

    def get(self, url, can_retry=True):
        if can_retry:
            tries = 10
        else:
            tries = 1
        while tries > 0:
            tries -= 1
            self._tester.driver.get(url)
            if 'The website may be down' in self._tester.driver.page_source:
                time.sleep(5)
                continue
            return
        raise exceptions.TimeoutException(
            'Timeout waiting for %s page to load', url)

    def wait(self, timeout=None):
        if timeout is None:
            timeout = DEFAULT_TIMEOUT
        return wait.WebDriverWait(self._tester.driver, timeout)

    def find_element_by_css_selector(self, selector, index=None):
        if index is None:
            return self._tester.driver.find_element_by_css_selector(selector)
        else:
            return self._tester.driver.find_elements_by_css_selector(
                selector)[index]

    def find_element_by_id(self, elt_id):
        return self._tester.driver.find_element_by_id(elt_id)

    def find_element_by_link_text(self, text, index=None):
        if index is None:
            return self._tester.driver.find_element_by_link_text(text)
        else:
            return self._tester.driver.find_elements_by_link_text(text)[index]

    def find_element_by_name(self, name):
        return self._tester.driver.find_element_by_name(name)

    def expect_status_message_to_be(self, value):
        self.wait().until(
            ec.text_to_be_present_in_element(
                (by.By.ID, 'gcb-butterbar-message'), value))

    def wait_until_status_message_hidden(self):
        self.wait().until(
            ec.invisibility_of_element_located(
                (by.By.ID, 'gcb-butterbar-message')))
        return self


class EditorPageObject(PageObject):
    """Page object for pages which wait for the editor to finish loading."""

    def __init__(self, tester):
        super(EditorPageObject, self).__init__(tester)

        def successful_butter_bar(unused_driver):
            butter_bar_message = self.find_element_by_id(
                'gcb-butterbar-message')
            return 'Success' in butter_bar_message.text or (
                not butter_bar_message.is_displayed())

        self.wait().until(successful_butter_bar)

    def set_status(self, status):
        select.Select(self.find_element_by_name(
            'is_draft')).select_by_visible_text(status)
        return self

    def click_save(self, link_text='Save', status_message='Saved'):
        self.find_element_by_link_text(link_text).click()
        self.expect_status_message_to_be(status_message)
        return self

    def _close_and_return_to(self, continue_page):
        self.find_element_by_link_text('Close').click()
        return continue_page(self._tester)


class DashboardEditor(EditorPageObject):
    """A base class for the editors accessed from the Dashboard."""

    def click_close(self):
        return self._close_and_return_to(DashboardPage)


class RootPage(PageObject):
    """Page object to model the interactions with the root page."""

    def _add_default_course_if_needed(self, base_url):
        """Setup default read-only course if not yet setup."""

        # check default course is deployed
        self.get(base_url + '/')
        if 'Power Searching with Google' in self._tester.driver.page_source:
            return

        # deploy it
        LoginPage(self._tester).login('test@example.com', admin=True)
        self.get(base_url + '/admin?action=settings')
        AdminSettingsPage(self._tester).click_override(
            'gcb_courses_config'
        ).set_status('Active').click_save()
        self.get(base_url + '/admin?action=courses')
        self.find_element_by_link_text('Logout').click()

    def load(self, base_url):
        self._add_default_course_if_needed(base_url)
        self.get(base_url + '/')
        return self

    def load_welcome_page(self, base_url):
        self.click_login(
        ).login(
            'test@example.com', admin=True
        )
        self.get(base_url + '/admin?action=welcome')
        return WelcomePage(self._tester)

    def click_login(self):
        self.find_element_by_link_text('Login').click()
        return LoginPage(self._tester)

    def click_dashboard(self):
        self.find_element_by_link_text('Dashboard').click()
        return DashboardPage(self._tester)

    def click_admin(self):
        self.find_element_by_link_text('Admin').click()
        return AdminPage(self._tester)

    def click_announcements(self):
        self.find_element_by_link_text('Announcements').click()
        return AnnouncementsPage(self._tester)

    def click_register(self):
        self.find_element_by_link_text('Register').click()
        return RegisterPage(self._tester)


class WelcomePage(PageObject):

    def click_explore_sample_course(self):
        self.find_element_by_id('explore').click()
        return DashboardPage(self._tester)


class RegisterPage(PageObject):
    """Page object to model the registration page."""

    def enroll(self, name):
        enroll = self.find_element_by_name('form01')
        enroll.send_keys(name)
        enroll.submit()
        return self

    def verify_enrollment(self):
        self._tester.assertTrue(
            'Thank you for registering' in self.find_element_by_css_selector(
                '.gcb-top-content').text)
        return self

    def click_course(self):
        self.find_element_by_link_text('Course').click()
        return RootPage(self._tester)


class AnnouncementsPage(PageObject):
    """Page object to model the announcements page."""

    def click_add_new(self):
        self.find_element_by_css_selector(
            '#gcb-add-announcement > button').click()
        return AnnouncementsEditorPage(self._tester)

    def verify_announcement(self, title=None, date=None, body=None):
        """Verify that the announcement has the given fields."""
        if title:
            self._tester.assertEquals(
                title, self._tester.driver.find_elements_by_css_selector(
                    'div.gcb-aside h2')[0].text)
        if date:
            self._tester.assertEquals(
                date, self._tester.driver.find_elements_by_css_selector(
                    'div.gcb-aside p')[0].text)
        if body:
            self._tester.assertEquals(
                body, self._tester.driver.find_elements_by_css_selector(
                    'div.gcb-aside p')[1].text)
        return self


class AnnouncementsEditorPage(EditorPageObject):
    """Page to model the announcements editor."""

    def enter_fields(self, title=None, date=None, body=None):
        """Enter title, date, and body into the announcement form."""
        if title:
            title_el = self.find_element_by_name('title')
            title_el.clear()
            title_el.send_keys(title)
        if date:
            date_el = self.find_element_by_name('date')
            date_el.clear()
            date_el.send_keys(date)
        if body:
            body_el = self.find_element_by_name('html')
            body_el.clear()
            body_el.send_keys(body)
        return self

    def click_close(self):
        return self._close_and_return_to(AnnouncementsPage)


class LoginPage(PageObject):
    """Page object to model the interactions with the login page."""

    def login(self, login, admin=False):
        email = self.find_element_by_id('email')
        email.clear()
        email.send_keys(login)
        if admin:
            self.find_element_by_id('admin').click()
        self.find_element_by_id('submit-login').click()
        return RootPage(self._tester)


class DashboardPage(PageObject):
    """Page object to model the interactions with the dashboard landing page."""

    def load(self, base_url, name):
        self.get('/'.join([base_url, name, 'dashboard']))
        return self

    def verify_read_only_course(self):
        self._tester.assertEquals(
            'Read-only course.',
            self.find_element_by_id('gcb-butterbar-message').text)
        return self

    def verify_selected_tab(self, tab_text):
        tab = self.find_element_by_link_text(tab_text)
        self._tester.assertEquals('selected', tab.get_attribute('class'))

    def verify_not_publicly_available(self):
        self._tester.assertEquals(
            'The course is not publicly available.',
            self.find_element_by_id('gcb-butterbar-message').text)
        return self

    def click_import(self):
        self.find_element_by_css_selector('#import_course').click()
        return Import(self._tester)

    def click_add_unit(self):
        self.find_element_by_css_selector('#add_unit > button').click()
        return AddUnit(self._tester, AddUnit.CREATION_MESSAGE)

    def click_edit_unit(self, unit_title):
        self.find_element_by_link_text(unit_title).click()
        self.find_element_by_link_text('Edit Unit').click()
        return AddUnit(self._tester, AddUnit.LOADED_MESSAGE)

    def click_add_assessment(self):
        self.find_element_by_css_selector('#add_assessment > button').click()
        return AddAssessment(self._tester)

    def click_add_link(self):
        self.find_element_by_css_selector('#add_link > button').click()
        return AddLink(self._tester)

    def click_add_lesson(self):
        self.find_element_by_css_selector('#add_lesson > button').click()
        return AddLesson(self._tester)

    def click_organize(self):
        self.find_element_by_css_selector('#edit_unit_lesson').click()
        return Organize(self._tester)

    def click_assets(self):
        self.find_element_by_link_text('Assets').click()
        return AssetsPage(self._tester)

    def click_settings(self):
        self.find_element_by_link_text('Settings').click()
        self.find_element_by_link_text('Homepage').click()
        return SettingsPage(self._tester)

    def verify_course_outline_contains_unit(self, unit_title):
        self.find_element_by_link_text(unit_title)
        return self

    def click_on_course_outline_components(self, title):
        self.find_element_by_link_text(title).click()
        return LessonPage(self._tester)

    def click_analytics(self, name):
        self.find_element_by_link_text('Analytics').click()
        self.find_element_by_link_text(name).click()
        return AnalyticsPage(self._tester)

    def click_course(self):
        self.find_element_by_link_text('Course').click()
        return RootPage(self._tester)

    def click_i18n(self):
        self.find_element_by_link_text('I18N').click()
        return self


class CourseContentPage(RootPage):
    """Page object for viewing course content."""

    def _find_question(self, question_batch_id, question_text):
        questions = self._tester.driver.find_elements_by_css_selector(
            '[data-question-batch-id="%s"] .qt-mc-question.qt-standalone' %
            question_batch_id)
        if not questions:
            raise AssertionError('No questions in batch "%s" found' %
                                 question_batch_id)

        for question in questions:
            if (question.find_element_by_css_selector('.qt-question').text ==
                question_text):
                return question
        raise AssertionError('No questions in batch "%s" ' % question_batch_id +
                             'matched "%s"' % question_text)

    def set_answer_for_mc_question(self, question_batch_id,
                                   question_text, answer):
        question = self._find_question(question_batch_id, question_text)
        choices = question.find_elements_by_css_selector(
            '.qt-choices > *')
        for choice in choices:
            if choice.text == answer:
                choice.find_element_by_css_selector(
                    'input[type="radio"]').click()
                return self

        raise AssertionError(
            'No answer to question "%s" ' % question_text +
            'in batch "%s" ' + question_batch_id +
            'had an answer matching "%s"' % answer)

    def submit_question_batch(self, question_batch_id, button_text):
        buttons = self._tester.driver.find_elements_by_css_selector(
            'div[data-question-batch-id="%s"] .qt-check-answer-button' %
            question_batch_id)
        for button in buttons:
            if button_text in button.text:
                button.click()
                if question_batch_id.startswith('L'):
                    return self
                else:
                    return AssessmentConfirmationPage(self._tester)
        raise AssertionError('No button found matching "%s"' % button_text)


class LessonPage(CourseContentPage):
    """Object specific to Lesson behavior."""

    def verify_correct_submission(self, question_batch_id, question_text):
        question = self._find_question(question_batch_id, question_text)
        text = question.find_element_by_css_selector('.qt-feedback').text
        if text == 'Yes, the answer is correct.':
            return self
        raise Exception('Incorrect answer submitted')

    def verify_incorrect_submission(self, question_batch_id, question_text):
        question = self._find_question(question_batch_id, question_text)
        text = question.find_element_by_css_selector('.qt-feedback').text
        if text == 'No, the answer is incorrect.':
            return self
        raise Exception('Correct answer submitted')

    def verify_correct_grading(self, question_batch_id):
        report = self.find_element_by_css_selector(
            '.qt-grade-report[data-question-batch-id="%s"]' % question_batch_id)
        if report.text == 'Your score is: 1/1':
            return self
        raise Exception('Incorrect answer submitted')

    def verify_incorrect_grading(self, question_batch_id):
        report = self.find_element_by_css_selector(
            '.qt-grade-report[data-question-batch-id="%s"]' % question_batch_id)
        if report.text == 'Your score is: 0/1':
            return self
        raise Exception('Correct answer submitted')

    def play_video(self, instanceid):
        self._tester.driver.execute_script(
            'document.getElementById("%s").play();' % instanceid)
        time.sleep(1)  # Let the video get started before we do anything else.
        return self

    def pause_video(self, instanceid):
        self._tester.driver.execute_script(
            'document.getElementById("%s").pause();' % instanceid)
        return self

    def wait_for_video_state(self, instanceid, attribute, desired_state,
                             max_patience):
        def in_desired_state(driver):
            state = driver.execute_script(
                'return document.getElementById("%s").%s' % (
                    instanceid, attribute))
            return state == desired_state
        self.wait(timeout=max_patience).until(in_desired_state)
        return self


class AssessmentConfirmationPage(RootPage):

    def verify_correct_submission(self):
        completion_p = self.find_element_by_css_selector(
            '.gcb-top-content[role="heading"]')
        if 'Your score for this assessment is 100%' not in completion_p.text:
            raise AssertionError('Success indication not found in "%s"' %
                                 completion_p.text)
        return self

    def verify_incorrect_submission(self):
        completion_p = self.find_element_by_css_selector(
            '.gcb-top-content[role="heading"]')
        if 'Your score for this assessment is 0%' not in completion_p.text:
            raise AssertionError('Failure indication not found in "%s"' %
                                 completion_p.text)
        return self

    def return_to_unit(self):
        self.find_element_by_link_text('Return to Unit').click()
        return LessonPage(self._tester)


class SettingsPage(PageObject):
    """Page object for the dashboard's course settings tab."""

    def __init__(self, tester):
        super(SettingsPage, self).__init__(tester)

        def successful_load(unused_driver):
            tab = self.find_element_by_link_text('Homepage')
            print tab, tab.get_attribute('class'), tab.get_attribute('href')
            return 'selected' == tab.get_attribute('class')

        self.wait().until(successful_load)

    def click_course_options(self):
        self.find_element_by_css_selector(
            '#edit_course_settings > button').click()
        return CourseOptionsEditorPage(self._tester)


class CourseOptionsEditorPage(EditorPageObject):
    """Page object for the dashboard's course ioptions sub tab."""

    def click_close(self):
        return self._close_and_return_to(SettingsPage)

    def click_close_and_confirm(self):
        self.find_element_by_link_text('Close').click()
        self._tester.driver.switch_to_alert().accept()
        time.sleep(0.2)
        return SettingsPage(self._tester)

    def set_course_name(self, name):
        course_title_input = self.find_element_by_name('course:title')
        course_title_input.clear()
        course_title_input.send_keys(name)
        return self


class AssetsPage(PageObject):
    """Page object for the dashboard's assets tab."""

    def click_sub_tab(self, text):
        self.find_element_by_link_text(text).click()
        return self

    def click_upload(self):
        self.find_element_by_link_text('Upload to assets/img').click()
        return AssetsEditorPage(self._tester)

    def verify_image_file_by_name(self, name):
        self.find_element_by_link_text(name)  # throw exception if not found
        return self

    def verify_no_image_file_by_name(self, name):
        self.wait().until(ec.visibility_of_element_located((
            by.By.XPATH, '//h3[starts-with(.,\'Images & Documents\')]')))
        try:
            self.find_element_by_link_text(name)  # throw exception if not found
            raise AssertionError('Found file %s which should be absent' % name)
        except exceptions.NoSuchElementException:
            pass
        return self

    def click_edit_image(self, name):
        get_parent_element(
            self.find_element_by_link_text(name)
        ).find_element_by_css_selector('a.icon-edit').click()
        return ImageEditorPage(self._tester)

    def click_add_short_answer(self):
        self.find_element_by_link_text('Add Short Answer').click()
        return ShortAnswerEditorPage(self._tester)

    def click_add_multiple_choice(self):
        self.find_element_by_link_text('Add Multiple Choice').click()
        return MultipleChoiceEditorPage(self._tester)

    def click_add_question_group(self):
        self.find_element_by_link_text('Add Question Group').click()
        return QuestionEditorPage(self._tester)

    def click_edit_short_answer(self, name):
        raise NotImplementedError

    def click_edit_mc_question(self):
        raise NotImplementedError

    def verify_question_exists(self, description):
        """Verifies question description exists on list of question banks."""
        tds = self._tester.driver.find_elements_by_css_selector(
            '#gcb-main-content tbody td')
        for td in tds:
            try:
                self._tester.assertEquals(description, td.text)
                return self
            except AssertionError:
                continue
        raise AssertionError(description + ' not found')

    def click_question_preview(self):
        self.find_element_by_css_selector(
            '#gcb-main-content tbody td .icon-preview').click()
        return self

    def verify_question_preview(self, question_text):
        """Verifies contents of question preview."""
        def load_modal_iframe(driver):
            try:
                driver.switch_to_frame(
                    driver.find_element_by_css_selector('#modal-window iframe'))
            except exceptions.NoSuchFrameException:
                return False
            else:
                return True

        self.wait().until(load_modal_iframe)
        question = self._tester.driver.find_element_by_css_selector(
            '.qt-question')
        self._tester.assertEquals(question_text, question.text)
        self._tester.driver.switch_to_default_content()
        self._tester.driver.find_element_by_css_selector(
            '#modal-window .close-button').click()
        return self

    def click_add_label(self):
        self.find_element_by_link_text('Add Label').click()
        return LabelEditorPage(self._tester)

    def verify_label_present(self, title):
        self.find_element_by_id('label_' + title)  # Exception if not found.
        return self

    def verify_label_not_present(self, title):
        try:
            self.find_element_by_id('label_' + title)  # Exception if not found.
            raise AssertionError('Unexpectedly found label %s' % title)
        except exceptions.NoSuchElementException:
            pass
        return self

    def click_edit_label(self, title):
        self.find_element_by_id('label_' + title).click()
        return LabelEditorPage(self._tester)

    def click_outline(self):
        self.find_element_by_link_text('Outline').click()
        return DashboardPage(self._tester)


class AssetsEditorPage(DashboardEditor):
    """Page object for upload image page."""

    def select_file(self, path):
        self.find_element_by_name('file').send_keys(path)
        return self

    def click_upload_and_expect_saved(self):
        self.find_element_by_link_text('Upload').click()
        self.expect_status_message_to_be('Saved.')

        # Page automatically redirects after successful save.
        self.wait().until(ec.title_contains('Assets'))

        return AssetsPage(self._tester)


class QuestionEditorPage(EditorPageObject):
    """Abstract superclass for page objects for add/edit questions pages."""

    def set_question(self, question):
        question_el = self.find_element_by_name('question')
        question_el.clear()
        question_el.send_keys(question)
        return self

    def set_description(self, description):
        question_el = self.find_element_by_name('description')
        question_el.clear()
        question_el.send_keys(description)
        return self

    def click_close(self):
        return self._close_and_return_to(AssetsPage)


class MultipleChoiceEditorPage(QuestionEditorPage):
    """Page object for editing multiple choice questions."""

    def click_add_a_choice(self):
        self.find_element_by_link_text('Add a choice').click()
        return self

    def set_answer(self, n, answer):
        answer_el = self.find_element_by_id('gcbRteField-' + str(2 * n + 1))
        answer_el.clear()
        answer_el.send_keys(answer)
        return self

    def click_allow_only_one_selection(self):
        raise NotImplementedError

    def click_allow_multiple_selections(self):
        raise NotImplementedError


class ShortAnswerEditorPage(QuestionEditorPage):
    """Page object for editing short answer questions."""

    def click_add_an_answer(self):
        self.find_element_by_link_text('Add an answer').click()
        return self

    def set_score(self, n, score):
        score_el = self.find_element_by_name('graders[%d]score' % n)
        score_el.clear()
        score_el.send_key(score)

    def set_response(self, n, response):
        response_el = self.find_element_by_name('graders[%d]response' % n)
        response_el.clear()
        response_el.send_key(response)

    def click_delete_this_answer(self, n):
        raise NotImplementedError


class LabelEditorPage(EditorPageObject):

    def set_title(self, text):
        title_el = self.find_element_by_name('title')
        title_el.clear()
        title_el.send_keys(text)
        return self

    def verify_title(self, text):
        title_el = self.find_element_by_name('title')
        self._tester.assertEqual(text, title_el.get_attribute('value'))
        return self

    def set_description(self, description):
        description_el = self.find_element_by_name('description')
        description_el.clear()
        description_el.send_keys(description)
        return self

    def verify_description(self, description):
        description_el = self.find_element_by_name('description')
        self._tester.assertEqual(description,
                                 description_el.get_attribute('value'))
        return self

    def set_type(self, type_num):
        type_el = self.find_element_by_id('_inputex_radioId%d' % type_num)
        type_el.click()
        return self

    def verify_type(self, type_num):
        type_el = self.find_element_by_id('_inputex_radioId%d' % type_num)
        self._tester.assertEqual('true', type_el.get_attribute('checked'))
        return self

    def click_delete(self):
        self.find_element_by_link_text('Delete').click()
        return self

    def confirm_delete(self):
        self._tester.driver.switch_to_alert().accept()
        return AssetsPage(self._tester)

    def click_close(self):
        return self._close_and_return_to(AssetsPage)


class ImageEditorPage(EditorPageObject):
    """Page object for the dashboard's view/delete image page."""

    def click_delete(self):
        self.find_element_by_link_text('Delete').click()
        return self

    def confirm_delete(self):
        self._tester.driver.switch_to_alert().accept()
        return AssetsPage(self._tester)


class Import(DashboardEditor):
    """Page object to model the dashboard's unit/lesson organizer."""
    pass


class AddLink(DashboardEditor):
    """Page object to model the dashboard's link editor."""

    def __init__(self, tester):
        super(AddLink, self).__init__(tester)
        self.expect_status_message_to_be(
            'New link has been created and saved.')


class CourseContentElement(DashboardEditor):
    RTE_EDITOR_FORMAT = 'gcbRteField-%d_editor'
    RTE_TEXTAREA_ID = 'gcbRteField-0'

    def set_title(self, title):
        title_el = self.find_element_by_name('title')
        title_el.clear()
        title_el.send_keys(title)
        return self

    def click_rich_text(self, index=0):
        self.wait_until_status_message_hidden()
        el = self.find_element_by_css_selector('div.rte-control', index)
        self._tester.assertEqual('Rich Text', el.text)
        el.click()
        self.wait().until(ec.element_to_be_clickable(
            (by.By.ID, CourseContentElement.RTE_EDITOR_FORMAT % index)))
        return self

    def click_plain_text(self, index=None):
        el = self.find_element_by_css_selector('div.rte-control', index)
        self._tester.assertEqual('<HTML>', el.text)
        el.click()
        return self

    def click_rte_add_custom_tag(self, index=0):
        self.find_element_by_link_text(
            'Insert Google Course Builder component', index).click()
        return self

    def select_rte_custom_tag_type(self, option_text):
        """Select the given option from the custom content type selector."""
        self._ensure_rte_iframe_ready_and_switch_to_it()
        select_tag = self.find_element_by_name('tag')
        for option in select_tag.find_elements_by_tag_name('option'):
            if option.text == option_text:
                option.click()
                break
        else:
            self._tester.fail('No option "%s" found' % option_text)
        self.wait().until(ec.element_to_be_clickable(
                (by.By.PARTIAL_LINK_TEXT, 'Close')))
        self._tester.driver.switch_to_default_content()
        return self

    def _ensure_rte_iframe_ready_and_switch_to_it(self):
        self.wait().until(
            ec.frame_to_be_available_and_switch_to_it('modal-editor-iframe'))
        # Ensure inputEx has initialized too
        self.wait().until(
            ec.element_to_be_clickable(
                (by.By.PARTIAL_LINK_TEXT, 'Close')))

    def set_rte_lightbox_field(self, field_css_selector, value):
        self._ensure_rte_iframe_ready_and_switch_to_it()
        field = self.find_element_by_css_selector(field_css_selector)
        field.clear()
        field.send_keys(value)
        self._tester.driver.switch_to_default_content()
        return self

    def click_rte_save(self):
        self._ensure_rte_iframe_ready_and_switch_to_it()
        self.find_element_by_link_text('Save').click()
        self._tester.driver.switch_to_default_content()
        return self

    def send_rte_text(self, text):
        # Work around Selenium bug: If focus is in another window
        # and in a text area, send_keys won't work.  Steal focus
        # immediately before sending keys.
        # https://code.google.com/p/selenium/issues/detail?id=2977
        self._tester.driver.execute_script('window.focus();')
        textarea = self.find_element_by_id('gcbRteField-0_editor')
        textarea.click()
        textarea.send_keys(keys.Keys.HOME)

        textarea.send_keys(text)
        return self

    def doubleclick_rte_element(self, elt_css_selector, index=0):
        self._tester.driver.switch_to_frame(
            CourseContentElement.RTE_EDITOR_FORMAT % index)
        target = self.find_element_by_css_selector(elt_css_selector)
        action_chains.ActionChains(
            self._tester.driver).double_click(target).perform()
        self._tester.driver.switch_to_default_content()
        return self

    def ensure_rte_lightbox_field_has_value(self, field_css_selector, value):
        self._ensure_rte_iframe_ready_and_switch_to_it()
        self._tester.assertEqual(
            value,
            self.find_element_by_css_selector(
                field_css_selector).get_attribute('value'))
        self._tester.driver.switch_to_default_content()
        return self

    def _get_rte_contents(self):
        return self.find_element_by_id(
            CourseContentElement.RTE_TEXTAREA_ID).get_attribute('value')

    def _get_instanceid_list(self):
        """Returns a list of the instanceid attrs in the lesson body."""
        html = self._get_rte_contents()
        html_list = html.split(' instanceid="')
        instanceid_list = []
        for item in html_list[1:]:
            closing_quote_ind = item.find('"')
            instanceid_list.append(item[:closing_quote_ind])
        return instanceid_list

    def ensure_instanceid_count_equals(self, value):
        self._tester.assertEqual(value, len(self._get_instanceid_list()))
        return self

    def take_snapshot_of_instanceid_list(self, list_to_fill=None):
        self.instanceid_list_snapshot = self._get_instanceid_list()
        if list_to_fill is not None:
            list_to_fill.extend(self.instanceid_list_snapshot)
        return self

    def ensure_instanceid_list_matches_last_snapshot(self):
        self._tester.assertEqual(
            self.instanceid_list_snapshot, self._get_instanceid_list())
        return self

    def _codemirror_is_ready_builder(self, nth_instance):
        def codemirror_is_ready(unused_driver):
            return self._tester.driver.execute_script(
                "return $('.CodeMirror')[%s]"
                ".CodeMirror.gcbCodeMirrorMonitor.cmReady;" % nth_instance)

        return codemirror_is_ready

    def setvalue_codemirror(self, nth_instance, code_body):
        self.wait().until(self._codemirror_is_ready_builder(nth_instance))

        self._tester.driver.execute_script(
            "$('.CodeMirror')[%s].CodeMirror.setValue('%s');" % (
                nth_instance, code_body))
        return self

    def assert_equal_codemirror(self, nth_instance, expected_code_body):
        self.wait().until(self._codemirror_is_ready_builder(nth_instance))

        actual_code_body = self._tester.driver.execute_script(
            "return $('.CodeMirror')[%s].CodeMirror.getValue();" % nth_instance)
        self._tester.assertEqual(expected_code_body, actual_code_body)
        return self


class AddUnit(CourseContentElement):
    """Page object to model the dashboard's add unit editor."""

    CREATION_MESSAGE = 'New unit has been created and saved.'
    LOADED_MESSAGE = 'Success.'

    INDEX_UNIT_HEADER = 0
    INDEX_UNIT_FOOTER = 1

    def __init__(self, tester, expected_message):
        super(AddUnit, self).__init__(tester)
        self.expect_status_message_to_be(expected_message)

    def set_pre_assessment(self, assessment_name):
        select.Select(self.find_element_by_name(
            'pre_assessment')).select_by_visible_text(assessment_name)
        return self

    def set_post_assessment(self, assessment_name):
        select.Select(self.find_element_by_name(
            'post_assessment')).select_by_visible_text(assessment_name)
        return self

    def set_contents_on_one_page(self, setting):
        print
        labels = self._tester.driver.find_elements_by_tag_name('label')
        one_page_label = None
        for label in labels:
            if label.text == 'Show Contents on One Page':
                one_page_label = label
                break
        label_div = one_page_label.find_element_by_xpath('..')
        checkbox_div = label_div.find_element_by_xpath('..')
        checkbox = checkbox_div.find_element_by_css_selector(
            'input[type="checkbox"]')
        if checkbox.is_selected() != setting:
            checkbox.click()
        return self


class AddAssessment(CourseContentElement):
    """Page object to model the dashboard's assessment editor."""

    INDEX_CONTENT = 0
    INDEX_REVIEWER_FEEDBACK = 1

    def __init__(self, tester):
        super(AddAssessment, self).__init__(tester)
        self.expect_status_message_to_be(
            'New assessment has been created and saved.')


class AddLesson(CourseContentElement):
    """Page object to model the dashboard's lesson editor."""

    def __init__(self, tester):
        super(AddLesson, self).__init__(tester)
        self.instanceid_list_snapshot = []
        self.expect_status_message_to_be(
            'New lesson has been created and saved.')

    def ensure_lesson_body_textarea_matches_regex(self, regex):
        rte_contents = self._get_rte_contents()
        self._tester.assertRegexpMatches(rte_contents, regex)
        return self

    def set_questions_are_scored(self):
        select.Select(self.find_element_by_name(
            'scored')).select_by_visible_text('Questions are scored')
        return self

    def set_questions_give_feedback(self):
        select.Select(self.find_element_by_name(
            'scored')).select_by_visible_text('Questions only give feedback')
        return self


class Organize(DashboardEditor):
    """Page object to model the dashboard's unit/lesson organizer."""
    pass


class AdminPage(PageObject):
    """Page object to model the interactions with the admimn landing page."""

    def click_add_course(self):
        self.find_element_by_id('add_course').click()
        return AddCourseEditorPage(self._tester)

    def click_settings(self):
        self.find_element_by_link_text('Settings').click()
        return AdminSettingsPage(self._tester)


class AdminSettingsPage(PageObject):
    """Page object for the admin settings."""

    def click_override_admin_user_emails(self):
        self._tester.driver.find_elements_by_css_selector(
            'button.gcb-button')[0].click()
        return ConfigPropertyOverridePage(self._tester)

    def click_override(self, setting_name):
        self.find_element_by_id(setting_name).click()
        return ConfigPropertyOverridePage(self._tester)

    def verify_admin_user_emails_contains(self, email):
        self._tester.assertTrue(
            email in self._tester.driver.find_elements_by_css_selector(
                'table.gcb-config tr')[1].find_elements_by_css_selector(
                    'td')[1].text)


class ConfigPropertyOverridePage(EditorPageObject):
    """Page object for the admin property override editor."""

    def clear_value(self):
        element = self.find_element_by_name('value')
        element.clear()
        return self

    def set_value(self, value):
        element = self.find_element_by_name('value')
        if type(value) is bool:
            current_value = element.get_attribute('value').lower()
            if str(value).lower() != current_value:
                checkbox = get_parent_element(
                    element).find_element_by_css_selector('[type="checkbox"]')
                checkbox.send_keys(' ')  # Toggle, iff necessary.
        else:
            element.send_keys(value)
        return self

    def click_close(self):
        return self._close_and_return_to(AdminSettingsPage)


class AddCourseEditorPage(EditorPageObject):
    """Page object for the dashboards' add course page."""

    def set_fields(self, name=None, title=None, email=None):
        """Populate the fields in the add course page."""
        name_el = self.find_element_by_name('name')
        title_el = self.find_element_by_name('title')
        email_el = self.find_element_by_name('admin_email')

        name_el.clear()
        title_el.clear()
        email_el.clear()

        if name:
            name_el.send_keys(name)
        if title:
            title_el.send_keys(title)
        if email:
            email_el.send_keys(email)

        return self

    def click_close(self):
        return self._close_and_return_to(AdminPage)


class AnalyticsPage(PageObject):
    """Page object for analytics sub-tab."""

    def wait_until_logs_not_empty(self, data_source):
        def data_source_logs_not_empty(unused_driver):
            return self.get_data_source_logs(data_source)

        self.wait().until(data_source_logs_not_empty)
        return self

    def get_data_page_number(self, data_source):
        # When there is a chart on the page, the chart-drawing animation
        # takes ~1 sec to complete, which blocks the JS to unpack and paint
        # the data page numbers.
        max_wait = time.time() + 10
        text = self.find_element_by_id('model_visualizations_dump').text
        while not text and time.time() < max_wait:
            time.sleep(0.1)
            text = self.find_element_by_id('model_visualizations_dump').text

        numbers = {}
        for line in text.split('\n'):
            name, value = line.split('=')
            numbers[name] = int(value)
        return numbers[data_source]

    def get_displayed_page_number(self, data_source):
        return self.find_element_by_id('gcb_rest_source_page_number_' +
                                       data_source).text

    def get_data_source_logs(self, data_source):
        return self.find_element_by_id(
            'gcb_log_rest_source_' + data_source).text

    def get_page_level_logs(self):
        return self.find_element_by_id('gcb_rest_source_errors').text

    def click(self, data_source, button):
        name = 'gcb_rest_source_page_request_' + button + '_' + data_source
        self.find_element_by_id(name).click()

    def buttons_present(self, data_source):
        try:
            self.find_element_by_id('gcb_rest_source_request_zero_' +
                                    data_source)
            return True
        except exceptions.NoSuchElementException:
            return False

    def set_chunk_size(self, data_source, chunk_size):
        field = self.find_element_by_id(
            'gcb_rest_source_chunk_size_' + data_source)
        field.clear()
        field.send_keys(str(chunk_size))

    def answers_pie_chart_present(self):
        div = self.find_element_by_id('answers_pie_chart')
        svgs = div.find_elements_by_tag_name('svg')
        # pylint: disable-msg=g-explicit-length-test
        return len(svgs) > 0


class AppengineAdminPage(PageObject):

    def __init__(self, tester, base_url, course_name):
        super(AppengineAdminPage, self).__init__(tester)
        self._base_url = base_url
        self._course_name = course_name

    def get_datastore(self, entity_kind):
        self.get(
            self._base_url + '/datastore' +
            '?namespace=ns_%s' % self._course_name +
            '&kind=%s' % entity_kind)
        return DatastorePage(self._tester)


class DatastorePage(PageObject):

    def get_items(self):
        data_table = self._tester.driver.find_element_by_css_selector(
            'table.ae-table')

        title_elements = data_table.find_elements_by_css_selector(
            'table.ae-table th')
        for index, element in enumerate(title_elements):
            if element.text.strip() == 'Key':
                key_index = index

        rows = data_table.find_elements_by_css_selector('tr')
        data_urls = []
        for row in rows:
            cells = row.find_elements_by_css_selector('td')
            if len(cells) > key_index:
                url = cells[key_index].find_elements_by_tag_name(
                    'a')[0].get_attribute('href')
                data_urls.append(url)

        data = []
        for data_url in data_urls:
            self.get(data_url)
            rows = self._tester.driver.find_elements_by_css_selector(
                'div.ae-settings-block')
            item = {}
            data.append(item)
            for row in rows:
                labels = row.find_elements_by_tag_name('label')
                if labels:
                    name = re.sub(r'\(.*\)', '', labels[0].text).strip()
                    value_blocks = row.find_elements_by_tag_name('div')
                    if value_blocks:
                        inputs = value_blocks[0].find_elements_by_tag_name(
                            'input')
                        if inputs:
                            value = inputs[0].get_attribute('value').strip()
                        else:
                            value = value_blocks[0].text.strip()
                        item[name] = value
            self._tester.driver.back()

        return data
