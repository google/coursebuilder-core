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

from selenium.webdriver.common import action_chains
from selenium.webdriver.common import by
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.support import select
from selenium.webdriver.support import wait


class PageObject(object):
    """Superclass to hold shared logic used by page objects."""

    def __init__(self, tester):
        self._tester = tester

    def find_element_by_css_selector(self, selector):
        return self._tester.driver.find_element_by_css_selector(selector)

    def find_element_by_id(self, elt_id):
        return self._tester.driver.find_element_by_id(elt_id)

    def find_element_by_link_text(self, text):
        return self._tester.driver.find_element_by_link_text(text)

    def find_element_by_name(self, name):
        return self._tester.driver.find_element_by_name(name)

    def expect_status_message_to_be(self, value):
        wait.WebDriverWait(self._tester.driver, 15).until(
            ec.text_to_be_present_in_element(
                (by.By.ID, 'gcb-butterbar-message'), value))


class EditorPageObject(PageObject):
    """Page object for pages which wait for the editor to finish loading."""

    def __init__(self, tester):
        super(EditorPageObject, self).__init__(tester)

        def successful_butter_bar(driver):
            butter_bar_message = driver.find_element_by_id(
                'gcb-butterbar-message')
            return 'Success.' in butter_bar_message.text or (
                not butter_bar_message.is_displayed())

        wait.WebDriverWait(self._tester.driver, 15).until(successful_butter_bar)

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

    def load(self, base_url):
        self._tester.driver.get(base_url + '/')
        return self

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


class RegisterPage(PageObject):
    """Page object to model the registration page."""

    def enroll(self, name):
        enroll = self.find_element_by_name('form01')
        enroll.send_keys(name)
        enroll.submit()
        return RegisterPage(self._tester)

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
        email = self._tester.driver.find_element_by_id('email')
        email.clear()
        email.send_keys(login)
        if admin:
            self.find_element_by_id('admin').click()
        self.find_element_by_id('submit-login').click()
        return RootPage(self._tester)


class DashboardPage(PageObject):
    """Page object to model the interactions with the dashboard landing page."""

    def load(self, base_url, name):
        self._tester.driver.get('/'.join([base_url, name, 'dashboard']))
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
        return AddUnit(self._tester)

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

    def verify_course_outline_contains_unit(self, unit_title):
        self.find_element_by_link_text(unit_title)
        return self

    def click_on_course_outline_components(self, title):
        self.find_element_by_link_text(title).click()
        return LessonPage(self._tester)


class LessonPage(RootPage):
    """Page object for viewing course content."""

    def submit_answer_for_mc_question_and_verify(self, question_text, answer):
        questions = self._tester.driver.find_elements_by_css_selector(
            '.qt-mc-question.qt-standalone')
        for question in questions:
            if (question.find_element_by_css_selector('.qt-question').text ==
                question_text):
                choices = question.find_elements_by_css_selector(
                    '.qt-choices > *')
                for choice in choices:
                    if choice.text == answer:
                        choice.find_element_by_css_selector(
                            'input[type="radio"]').click()
                        question.find_element_by_css_selector(
                            '.qt-check-answer').click()
                        if (question.find_element_by_css_selector(
                                '.qt-feedback').text ==
                            'Yes, the answer is correct.'):
                            return self
                        else:
                            raise Exception('Incorrect answer submitted')


class AssetsPage(PageObject):
    """Page object for the dashboard's assets tab."""

    def click_upload(self):
        self.find_element_by_link_text('Upload to assets/img').click()
        return AssetsEditorPage(self._tester)

    def verify_image_file_by_name(self, name):
        self.find_element_by_link_text(name)  # throw exception if not found
        return self

    def verify_no_image_file_by_name(self, name):
        self.find_element_by_link_text(name)  # throw exception if not found
        return self

    def click_edit_image(self, name):
        self.find_element_by_link_text(
            name).parent.find_element_by_link_text('[Edit]').click()
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
        lis = self._tester.driver.find_elements_by_css_selector(
            '#gcb-main-content > ol > li')
        for li in lis:
            try:
                self._tester.assertEquals(
                    description + ' [Edit]', li.text)
                return self
            except AssertionError:
                continue
        raise AssertionError(description + ' not found')

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
        wait.WebDriverWait(self._tester.driver, 15).until(
            ec.title_contains('Assets'))

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
        score_el = self.find_element_by_name('graders[%d]score' %n)
        score_el.clear()
        score_el.send_key(score)

    def set_response(self, n, response):
        response_el = self.find_element_by_name('graders[%d]response' %n)
        response_el.clear()
        response_el.send_key(response)

    def click_delete_this_answer(self, n):
        raise NotImplementedError


class ImageEditorPage(EditorPageObject):
    """Page object for the dashboard's view/delete image page."""

    def click_delete(self):
        self.find_element_by_link_text('Delete').click()
        return self

    def confirm_delete(self):
        self._tester.driver.switch_to_alert().accept()
        return AssetsPage(self._tester)


class AddUnit(DashboardEditor):
    """Page object to model the dashboard's add unit editor."""

    def __init__(self, tester):
        super(AddUnit, self).__init__(tester)
        self.expect_status_message_to_be('New unit has been created and saved.')

    def set_title(self, title):
        title_el = self.find_element_by_name('title')
        title_el.clear()
        title_el.send_keys(title)
        return self


class Import(DashboardEditor):
    """Page object to model the dashboard's unit/lesson organizer."""
    pass


class AddAssessment(DashboardEditor):
    """Page object to model the dashboard's assessment editor."""

    def __init__(self, tester):
        super(AddAssessment, self).__init__(tester)
        self.expect_status_message_to_be(
            'New assessment has been created and saved.')


class AddLink(DashboardEditor):
    """Page object to model the dashboard's link editor."""

    def __init__(self, tester):
        super(AddLink, self).__init__(tester)
        self.expect_status_message_to_be(
            'New link has been created and saved.')


class AddLesson(DashboardEditor):
    """Page object to model the dashboard's lesson editor."""
    RTE_EDITOR_ID = 'gcbRteField-0_editor'
    RTE_TEXTAREA_ID = 'gcbRteField-0'

    def __init__(self, tester):
        super(AddLesson, self).__init__(tester)
        self.instanceid_list_snapshot = []
        self.expect_status_message_to_be(
            'New lesson has been created and saved.')

    def click_rich_text(self):
        el = self.find_element_by_css_selector('div.rte-control')
        self._tester.assertEqual('Rich Text', el.text)
        el.click()
        wait.WebDriverWait(self._tester.driver, 15).until(
            ec.element_to_be_clickable((by.By.ID, AddLesson.RTE_EDITOR_ID)))
        return self

    def click_plain_text(self):
        el = self.find_element_by_css_selector('div.rte-control')
        self._tester.assertEqual('<HTML>', el.text)
        el.click()
        return self

    def send_rte_text(self, text):
        self.find_element_by_id('gcbRteField-0_editor').send_keys(text)
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
        wait.WebDriverWait(self._tester.driver, 15).until(
            ec.element_to_be_clickable(
                (by.By.PARTIAL_LINK_TEXT, 'Close')))
        self._tester.driver.switch_to_default_content()
        return self

    def click_rte_add_custom_tag(self):
        self.find_element_by_link_text(
            'Insert Google Course Builder component').click()
        return self

    def set_lesson_title(self, lesson_title):
        title_el = self.find_element_by_name('title')
        title_el.clear()
        title_el.send_keys(lesson_title)
        return self

    def doubleclick_rte_element(self, elt_css_selector):
        self._tester.driver.switch_to_frame(AddLesson.RTE_EDITOR_ID)
        target = self.find_element_by_css_selector(elt_css_selector)
        action_chains.ActionChains(
            self._tester.driver).double_click(target).perform()
        self._tester.driver.switch_to_default_content()
        return self

    def _ensure_rte_iframe_ready_and_switch_to_it(self):
        wait.WebDriverWait(self._tester.driver, 15).until(
            ec.frame_to_be_available_and_switch_to_it('modal-editor-iframe'))
        # Ensure inputEx has initialized too
        wait.WebDriverWait(self._tester.driver, 15).until(
            ec.element_to_be_clickable(
                (by.By.PARTIAL_LINK_TEXT, 'Close')))

    def set_rte_lightbox_field(self, field_css_selector, value):
        self._ensure_rte_iframe_ready_and_switch_to_it()
        field = self.find_element_by_css_selector(field_css_selector)
        field.clear()
        field.send_keys(value)
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

    def click_rte_save(self):
        self._ensure_rte_iframe_ready_and_switch_to_it()
        self.find_element_by_link_text('Save').click()
        self._tester.driver.switch_to_default_content()
        return self

    def _get_rte_contents(self):
        return self.find_element_by_id(
            AddLesson.RTE_TEXTAREA_ID).get_attribute('value')

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

    def take_snapshot_of_instanceid_list(self):
        self.instanceid_list_snapshot = self._get_instanceid_list()
        return self

    def ensure_instanceid_list_matches_last_snapshot(self):
        self._tester.assertEqual(
            self.instanceid_list_snapshot, self._get_instanceid_list())
        return self

    def ensure_lesson_body_textarea_matches_regex(self, regex):
        rte_contents = self._get_rte_contents()
        self._tester.assertRegexpMatches(rte_contents, regex)
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

    def verify_admin_user_emails_contains(self, email):
        self._tester.assertTrue(
            email in self._tester.driver.find_elements_by_css_selector(
                'table.gcb-config tr')[1].find_elements_by_css_selector(
                    'td')[1].text)


class ConfigPropertyOverridePage(EditorPageObject):
    """Page object for the admin property override editor."""

    def set_value(self, value):
        self.find_element_by_name('value').send_keys(value)
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
