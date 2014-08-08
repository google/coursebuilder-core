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

"""Tests that verify asset handling via REST."""

__author__ = 'Mike Gainer (mgainer@google.com)'

import cgi

from common import crypto
from models import transforms
from modules.dashboard import filer
from tests.functional import actions

COURSE_NAME = 'test_course'
COURSE_TITLE = 'Test Course'
NAMESPACE = 'ns_%s' % COURSE_NAME
ADMIN_EMAIL = 'admin@foo.com'
TEXT_ASSET_URL = '/%s%s' % (COURSE_NAME, filer.TextAssetRESTHandler.URI)
ITEM_ASSET_URL = '/%s%s' % (COURSE_NAME, filer.AssetItemRESTHandler.URI)


class AssetsRestTest(actions.TestBase):

    def setUp(self):
        super(AssetsRestTest, self).setUp()
        actions.simple_add_course(COURSE_NAME, ADMIN_EMAIL, COURSE_TITLE)
        actions.login(ADMIN_EMAIL)

    def test_add_file_in_unsupported_dir(self):

        # Upload file via REST POST
        xsrf_token = crypto.XsrfTokenManager.create_xsrf_token(
            filer.TextAssetRESTHandler.XSRF_TOKEN_NAME)
        key = 'assets/unsupported/foo.js'
        contents = 'alert("Hello, world");'
        response = self.put(TEXT_ASSET_URL, {'request': transforms.dumps({
            'xsrf_token': cgi.escape(xsrf_token),
            'key': key,
            'payload': transforms.dumps({'contents': contents})})})
        payload = transforms.loads(response.body)
        self.assertEquals(400, payload['status'])

    def test_add_file_in_subdir(self):

        # Upload file via REST POST
        xsrf_token = crypto.XsrfTokenManager.create_xsrf_token(
            filer.TextAssetRESTHandler.XSRF_TOKEN_NAME)
        key = 'assets/lib/my_project/foo.js'
        contents = 'alert("Hello, world");'
        response = self.put(TEXT_ASSET_URL, {'request': transforms.dumps({
            'xsrf_token': cgi.escape(xsrf_token),
            'key': key,
            'payload': transforms.dumps({'contents': contents})})})
        payload = transforms.loads(response.body)
        self.assertEquals(200, payload['status'])

        # Verify that content is available via REST GET.
        response = self.get(TEXT_ASSET_URL + '?key=%s' % cgi.escape(key))
        payload = transforms.loads(response.body)
        self.assertEquals(200, payload['status'])
        payload = transforms.loads(payload['payload'])
        self.assertEquals(contents, payload['contents'])

        # Verify that file uploaded to subdir is available via HTTP server
        response = self.get('/%s/%s' % (COURSE_NAME, key))
        self.assertEquals(contents, response.body)

    def test_add_item_in_subdir(self):

        # Upload file via REST POST
        xsrf_token = crypto.XsrfTokenManager.create_xsrf_token(
            filer.AssetItemRESTHandler.XSRF_TOKEN_NAME)
        base = 'assets/lib/my_project'
        filename = 'foo.js'
        contents = 'alert("Hello, world");'
        response = self.post(
            ITEM_ASSET_URL,
            {'request': transforms.dumps({
                'xsrf_token': cgi.escape(xsrf_token),
                'payload': transforms.dumps({
                    'base': base})})},
            upload_files=[('file', filename, contents)])
        self.assertIn('<status>200</status>', response.body)
        self.assertIn('<message>Saved.</message>', response.body)

        # Verify that file uploaded to subdir is available via HTTP server
        response = self.get('/%s/%s/%s' % (COURSE_NAME, base, filename))
        self.assertEquals(contents, response.body)

    def test_get_item_asset_url_in_subdir(self):
        response = self.get(ITEM_ASSET_URL +
                            '?key=assets/lib/my_project')
        payload = transforms.loads(response.body)
        self.assertEquals(200, payload['status'])
