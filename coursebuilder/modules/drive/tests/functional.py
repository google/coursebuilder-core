# Copyright 2015 Google Inc. All Rights Reserved.
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

"""Drive module tests"""

__author__ = [
    'nretallack@google.com (Nick Retallack)',
]

import json

from common import crypto
from common import utils
from models import models
from models import transforms
from modules.drive import drive_api_client_mock
from modules.drive import drive_models
from modules.drive import handlers
from tests.functional import actions


class DriveTestBase(actions.TestBase):

    ADMIN_EMAIL = 'admin@example.com'
    COURSE_NAME = 'drive-course'

    HANDLER_HOOKS = (
        (handlers.DriveListHandler, (
            'EXTRA_HEADER_CONTENT',
            'EXTRA_ROW_CONTENT',
        )),
        (handlers.DriveItemRESTHandler, (
            'SCHEMA_LOAD_HOOKS',
            'PRE_LOAD_HOOKS',
            'PRE_SAVE_HOOKS',
            'PRE_DELETE_HOOKS',
        )),
    )

    def setUp(self):
        super(DriveTestBase, self).setUp()
        actions.login(self.ADMIN_EMAIL, is_admin=True)
        self.app_context = actions.simple_add_course(
            self.COURSE_NAME, self.ADMIN_EMAIL, 'Drive Course')
        self.base = '/{}'.format(self.COURSE_NAME)

        # have a syncing policy in place already
        with utils.Namespace(self.app_context.namespace):
            self.setup_schedule_for_file('3')
            self.setup_schedule_for_file('5')
            self.setup_schedule_for_file('6', synced=True)

        # remove all hooks
        for handler, hooks in self.HANDLER_HOOKS:
            for hook in hooks:
                self.swap(handler, hook, [])

    def setup_schedule_for_file(
            self, file_id, availability='private', synced=False):
        # pylint: disable=protected-access
        client_mock = drive_api_client_mock._APIClientWrapperMock()
        meta = client_mock.get_file_meta(
            file_id)
        # pylint: enable=protected-access
        dto = drive_models.DriveSyncDAO.load_or_new(file_id)
        dto.dict.update({
            'id': meta.key,
            'title': meta.title,
            'type': meta.type,
            'sync_interval': 'hour',
            'availability': availability,
        })

        if synced:
            content_chunk = models.ContentChunkDTO({
                'type_id': meta.type,
                'resource_id': meta.file_id,
            })

            if meta.type == 'sheet':
                content_chunk.contents = json.dumps(client_mock.get_sheet_data(
                    file_id).to_json())
                content_chunk.content_type = 'application/json'
            else:
                content_chunk.contents = client_mock.get_doc_as_html(file_id)
                content_chunk.content_type = 'text/html'

            models.ContentChunkDAO.save(content_chunk)
            dto.sync_succeeded()

        drive_models.DriveSyncDAO.save(dto)

    def set_availability_for_file(self, file_id, availability):
        dto = drive_models.DriveSyncDAO.load_or_new(file_id)
        dto.dict.update({
            'availability': availability,
        })
        drive_models.DriveSyncDAO.save(dto)

    def get_page(self, url):
        return self.parse_html_string_to_soup(self.get(url).body)

    # assertions

    def assertRowCount(self, soup, count):
        self.assertEqual(
            len(soup.select('.gcb-list > table > tbody > tr')), count)

    def assertPresent(self, selection):
        self.assertEqual(len(selection), 1)

    def assertNotPresent(self, selection):
        self.assertEqual(len(selection), 0)

    def assertRestStatus(self, response, status):
        self.assertEqual(transforms.loads(response.body)['status'], status)


class DriveTests(DriveTestBase):

    def test_settings_page(self):
        self.get('dashboard?action=settings_drive')

    def test_list_page(self):
        soup = self.get_page('modules/drive')
        self.assertRowCount(soup, 3)
        self.assertPresent(soup.select('#file-3'))
        self.assertPresent(soup.select('#file-5'))
        self.assertPresent(soup.select('#file-6'))

    def test_add_page(self):
        soup = self.get_page('modules/drive/add')
        self.assertRowCount(soup, 3)

        # ensure items of unknown type don't get an add button
        unknown_item = soup.select('#file-4')[0]
        self.assertEqual(len(unknown_item.select('.add-button')), 0)

        # ensure items of known type do
        self.assertPresent(soup.select('#file-1 .add-button'))
        self.assertPresent(soup.select('#file-2 .add-button'))

    def test_item_pages_404_without_a_key(self):
        for url in [
                'modules/drive/item',
                'modules/drive/item/content']:
            response = self.get(url, expect_errors=True)
            self.assertEqual(response.status_code, 404)

        self.assertRestStatus(
            self.get('rest/modules/drive/item', expect_errors=True), 404)

    def test_adding_a_schedule(self):
        # Should be on the add page
        soup = self.get_page('modules/drive')
        self.assertNotPresent(soup.select('#file-2'))

        # but not the list page
        soup = self.get_page('modules/drive/add')
        self.assertPresent(soup.select('#file-2'))

        # rest handler should not return data
        self.assertRestStatus(
            self.get('rest/modules/drive/item?key=2'), 404)

        # add it
        self.post('modules/drive/add', {
            'xsrf_token_drive-add':
                crypto.XsrfTokenManager.create_xsrf_token('drive-add'),
            'key': '2',
        })

        # Should now be on the list page
        soup = self.get_page('modules/drive')
        self.assertPresent(soup.select('#file-2'))

        # but not the add page
        soup = self.get_page('modules/drive/add')
        self.assertNotPresent(soup.select('#file-2'))

        # rest handler should return success now
        self.assertRestStatus(self.get('rest/modules/drive/item?key=2'), 200)

    def test_saving_a_schedule(self):
        # form page should be visitable
        self.get('modules/drive/item?key=3')

        # update existing record
        self.assertRestStatus(self.put('rest/modules/drive/item', {
            'request': transforms.dumps({
                'xsrf_token':
                    crypto.XsrfTokenManager.create_xsrf_token(
                        'drive-item-rest'),
                'key': '3',
                'payload': transforms.dumps({
                    'sync_interval': 'hour',
                    'version': '1.0',
                    'availability': 'public',
                }),
            }),
        }), 200)

    def test_manual_sheet_sync_and_content(self):
        # ensure chunk doesn't exist
        response = self.get(
            'modules/drive/item/content?key=3', expect_errors=True)
        self.assertEqual(response.status_code, 404)

        # sync it
        soup = self.get_page('modules/drive')
        token = soup.select(
            'input[name=xsrf_token_drive-sync]')[0].attrs['value']
        response = self.post('modules/drive/sync', {
            'xsrf_token_drive-sync': token,
            'key': '3',
        })

        # now chunk should exist
        response = self.get('modules/drive/item/content?key=3')
        content = transforms.loads(response.body)
        payload = transforms.loads(content['payload'])
        self.assertIn('worksheets', payload)
        self.assertEqual(payload['id'], '3')

    def test_manual_doc_sync_and_content(self):
        # ensure chunk doesn't exist
        response = self.get(
            'modules/drive/item/content?key=5', expect_errors=True)
        self.assertEqual(response.status_code, 404)

        # sync it
        soup = self.get_page('modules/drive')
        token = soup.select(
            'input[name=xsrf_token_drive-sync]')[0].attrs['value']
        response = self.post('modules/drive/sync', {
            'xsrf_token_drive-sync': token,
            'key': '5',
        })

        # now chunk should exist
        response = self.get('modules/drive/item/content?key=5')
        self.assertEqual(
            response.headers['Content-Type'], 'text/html; charset=utf-8')
        self.assertEqual(response.body, '<p>Some HTML</p>')

    def test_content_permissions(self):
        # as admin, you can access this
        response = self.get('modules/drive/item/content?key=6')
        self.assertEqual(response.status_code, 200)

        # as nobody, you can't
        actions.logout()
        response = self.get(
            'modules/drive/item/content?key=6', expect_errors=True)
        self.assertEqual(response.status_code, 404)

        # unless it's public
        self.set_availability_for_file('6', 'public')
        response = self.get(
            'modules/drive/item/content?key=6', expect_errors=True)
        self.assertEqual(response.status_code, 404)

    def test_cron_job(self):
        # ensure chunks don't exist
        response = self.get(
            'modules/drive/item/content?key=3', expect_errors=True)
        self.assertEqual(response.status_code, 404)

        response = self.get(
            'modules/drive/item/content?key=5', expect_errors=True)
        self.assertEqual(response.status_code, 404)

        # sync
        response = self.get('/cron/drive/sync')
        self.assertEqual(response.status_code, 200)
        self.execute_all_deferred_tasks()

        # now chunks should exist
        response = self.get('modules/drive/item/content?key=3')
        content = transforms.loads(response.body)
        payload = transforms.loads(content['payload'])
        self.assertIn('worksheets', payload)
        self.assertEqual(payload['id'], '3')

        response = self.get('modules/drive/item/content?key=5')
        self.assertEqual(
            response.headers['Content-Type'], 'text/html; charset=utf-8')
        self.assertEqual(response.body, '<p>Some HTML</p>')

    def test_download_missing(self):
        soup = self.get_page('modules/drive')
        token = soup.select(
            'input[name=xsrf_token_drive-sync]')[0].attrs['value']
        response = self.post('modules/drive/sync', {
            'xsrf_token_drive-sync': token,
            'key': '1000',
        }, expect_errors=True)


