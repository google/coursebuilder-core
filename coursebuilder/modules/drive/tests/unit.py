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

"""Unit tests for the Drive module."""

__author__ = [
    'nretallack@google.com (Nick Retallack)',
]

import os
import json

import appengine_config

from tests import suite
from modules.drive import drive_api_client
from modules.drive import errors


def read_fixture(name):
    with open(os.path.join(appengine_config.BUNDLE_ROOT, 'modules', 'drive',
            'tests', 'fixtures', name), 'r') as fixture:
        return fixture.read()


class ApiClientTests(suite.TestBase):

    FAKE_KEY = (
        '-----BEGIN PRIVATE KEY-----\n'
        'secret\n'
        '-----END PRIVATE KEY-----\n'
    )

    def setUp(self):
        super(ApiClientTests, self).setUp()
        def mock_http_request(self, url):
            # pylint: disable=line-too-long
            return read_fixture({
                'https://spreadsheets.google.com/feeds/worksheets/1184RD90Yf9YhzFUWGVzF0_0-u9bm5COKEwRmBsvVFhA/private/full?alt=json':
                    'sheet_meta.json',
                'https://spreadsheets.google.com/feeds/cells/1184RD90Yf9YhzFUWGVzF0_0-u9bm5COKEwRmBsvVFhA/od6/private/full?alt=json':
                    'worksheet1.json',
                'https://spreadsheets.google.com/feeds/cells/1184RD90Yf9YhzFUWGVzF0_0-u9bm5COKEwRmBsvVFhA/o2ompgt/private/full?alt=json':
                    'worksheet2.json',
            }[url])

        self.swap(
            drive_api_client._APIClientWrapper, '_http_request',
            mock_http_request)

        fake_secrets = {
            'client_email': 'example@example.com',
            'private_key': self.FAKE_KEY,
        }

        self.client = drive_api_client._APIClientWrapper(fake_secrets)

    def test_spreadsheet_parser(self):
        self.assertEqual(
            self.client.get_sheet_data(
                '1184RD90Yf9YhzFUWGVzF0_0-u9bm5COKEwRmBsvVFhA').to_json(),
            json.loads(read_fixture('sheet_data.json')))

    def test_bad_secrets(self):
        with self.assertRaises(errors.Misconfigured):
            # empty strings
            drive_api_client.validate_secrets({
                'client_email': '',
                'private_key': '',
            })

        with self.assertRaises(errors.Misconfigured):
            # good email but bad key
            drive_api_client.validate_secrets({
                'client_email': 'example@example.com',
                'private_key': 'example',
            })

        with self.assertRaises(errors.Misconfigured):
            # bad email but good key
            drive_api_client.validate_secrets({
                'client_email': 'example',
                'private_key': self.FAKE_KEY,
            })
