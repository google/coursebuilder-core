# Copyright 2016 Google Inc. All Rights Reserved.
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

"""Drive integration tests."""

__author__ = [
    'nretallack@google.com (Nick Retallack)',
]

import json

from tests.integration import pageobjects
from tests.integration import integration

from modules.drive.tests import mocks


WAIT_TIMEOUT = 10

class DriveIntegrationTests(integration.TestBase):
    def test_sync_new_file(self):
        name = self.create_new_course()[0]
        self.load_dashboard(
            name
        ).click_leftnav_item_by_id(
            'edit', 'menu-item__edit__drive', DriveNotConfiguredPage,
        ).click_leftnav_item_by_id(
            'settings', 'menu-item__settings__drive', DriveSettingsPage,
        ).configure_service_account(
        ).click_settings(
        ).set_text_field_by_name('course:google:api_key', 'x',
        ).set_text_field_by_name('course:google:client_id', 'y',
        ).set_text_field_by_name('course:google:client_secret', 'z',
        ).click_save(
        ).click_leftnav_item_by_id(
            'edit', 'menu-item__edit__drive', DriveListPage,
        ).add_something(
        ).click_save(
        ).click_close(
        ).sync_something(
        )


class PageWaitMixin(object):
    def __init__(self, tester):
        super(PageWaitMixin, self).__init__(tester)
        self.wait(WAIT_TIMEOUT).until(lambda x: self.is_the_right_page())


class DriveNotConfiguredPage(pageobjects.DashboardPage, PageWaitMixin):
    def is_the_right_page(self):
        return self.find_element_by_id('drive-not-configured-page')


class DriveSettingsPage(
        pageobjects.EditorPageObject, pageobjects.DashboardPage, PageWaitMixin):
    def is_the_right_page(self):
        return self.find_element_by_id('drive-list')

    def configure_service_account(self):
        self.set_text_field_by_name(
            'drive:service_account_json', json.dumps(mocks.get_secrets()))
        self.click_save()
        return self


class DriveListPage(pageobjects.DashboardPage, PageWaitMixin):
    def is_the_right_page(self):
        return self.find_element_by_id('drive-list')

    def add_something(self):
        self._tester.driver.execute_script("""shareDriveItem('1', 'code')""")
        return DriveDTOPage(self._tester)

    def sync_something(self):
        self.find_element_by_css_selector('.sync-button').click()
        return DriveListPage(self._tester)

    def edit_something(self):
        self.find_element_by_css_selector('.title a').click()
        return pageobjects.EditorPageObject(self._tester)

class DriveDTOPage(
        pageobjects.EditorPageObject, pageobjects.DashboardPage, PageWaitMixin):

    def click_close(self):
        return self._close_and_return_to(DriveListPage)
