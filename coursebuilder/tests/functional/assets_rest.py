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
import os
import urllib

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
FILES_HANDLER_URL = '/%s%s' % (COURSE_NAME, filer.FilesItemRESTHandler.URI)


def _post_asset(test, base, key_name, file_name, content,
                locale=None):
    xsrf_token = crypto.XsrfTokenManager.create_xsrf_token(
        filer.AssetItemRESTHandler.XSRF_TOKEN_NAME)
    if key_name:
        key = os.path.join(base, key_name)
    else:
        key = base
    if locale:
        key = '/locale/%s/%s' % (locale, key)
    response = test.post(
        '/%s%s' % (test.COURSE_NAME, filer.AssetItemRESTHandler.URI),
        {'request': transforms.dumps({
            'xsrf_token': cgi.escape(xsrf_token),
            'payload': transforms.dumps({'key': key, 'base': base})})},
        upload_files=[('file', file_name, content)])
    return response


class AssetsRestTest(actions.TestBase):

    def setUp(self):
        super(AssetsRestTest, self).setUp()
        actions.simple_add_course(COURSE_NAME, ADMIN_EMAIL, COURSE_TITLE)
        actions.login(ADMIN_EMAIL, is_admin=True)
        actions.update_course_config(COURSE_NAME, {
            'extra_locales': [
                {'locale': 'de_DE', 'availability': 'available'}]})
        self.COURSE_NAME = COURSE_NAME

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

    def test_add_new_asset(self):
        base = 'assets/lib'
        name = 'foo.js'
        content = 'alert("Hello, world");'
        response = _post_asset(self, base, None, name, content)
        self.assertIn('<status>200</status>', response)
        self.assertIn('<message>Saved.</message>', response)

        # Verify asset available via AssetHandler
        response = self.get('/%s/%s/%s' % (COURSE_NAME, base, name))
        self.assertEquals(content, response.body)

    def test_add_new_asset_with_key(self):
        base = 'assets/lib'
        name = 'foo.js'
        content = 'alert("Hello, world");'
        response = _post_asset(self, base, name, name, content)
        self.assertIn('<status>200</status>', response)
        self.assertIn('<message>Saved.</message>', response)

        # Verify asset available via AssetHandler
        response = self.get('/%s/%s/%s' % (COURSE_NAME, base, name))
        self.assertEquals(content, response.body)

    def test_add_asset_in_subdir(self):
        base = 'assets/lib'
        key_name = 'a/b/c/foo.js'
        file_name = 'foo.js'
        content = 'alert("Hello, world");'
        response = _post_asset(self, base, key_name, file_name, content)
        self.assertIn('<status>200</status>', response.body)
        self.assertIn('<message>Saved.</message>', response.body)

        # Verify asset available via AssetHandler
        response = self.get('/%s/%s/%s' % (COURSE_NAME, base, key_name))
        self.assertEquals(content, response.body)

    def test_add_asset_in_bad_dir(self):
        base = 'assets/not_a_supported_asset_directory'
        name = 'foo.js'
        content = 'alert("Hello, world");'
        response = _post_asset(self, base, name, name, content)
        self.assertIn('<status>400</status>', response.body)
        self.assertIn('<message>Malformed request.</message>', response.body)

    def test_get_item_asset_url_in_subdir(self):
        response = self.get(ITEM_ASSET_URL + '?key=assets/lib/my_project')
        payload = transforms.loads(response.body)
        self.assertEquals(200, payload['status'])

    def test_get_asset_directory(self):
        response = self.get(ITEM_ASSET_URL + '?key=assets/img')
        payload = transforms.loads(transforms.loads(response.body)['payload'])
        self.assertEquals('assets/img', payload['key'])
        self.assertEquals('/assets/img/', payload['base'])
        self.assertEquals('assets/img/', payload['asset_url'])

    def test_get_nonexistent_asset(self):
        response = self.get(ITEM_ASSET_URL + '?key=assets/img/foo.jpg')
        payload = transforms.loads(transforms.loads(response.body)['payload'])
        self.assertEquals('assets/img/foo.jpg', payload['key'])
        self.assertEquals('/assets/img/', payload['base'])
        self.assertEquals('assets/img/', payload['asset_url'])

    def test_cannot_overwrite_existing_file_without_key(self):
        def add_asset():
            base = 'assets/lib'
            name = 'foo.js'
            content = 'alert("Hello, world");'
            return _post_asset(self, base, None, name, content)
        response = add_asset()
        self.assertIn('<message>Saved.</message>', response.body)
        response = add_asset()
        self.assertIn('<status>403</status>', response.body)
        self.assertIn('<message>Cannot overwrite existing file.</message>',
                      response.body)

    def test_can_overwrite_existing_file_with_key(self):
        def add_asset():
            base = 'assets/lib'
            name = 'foo.js'
            content = 'alert("Hello, world");'
            return _post_asset(self, base, name, name, content)
        response = add_asset()
        self.assertIn('<message>Saved.</message>', response.body)
        response = add_asset()
        self.assertIn('<message>Saved.</message>', response.body)

    def test_overwrite_ignores_file_name(self):
        base = 'assets/lib'
        key_name = 'foo.js'
        file_name = 'bar.js'
        content = 'alert("Hello, world");'
        _post_asset(self, base, key_name, file_name, content)

        response = self.get('/%s/%s/%s' % (COURSE_NAME, base, key_name))
        self.assertEquals(200, response.status_int)
        response = self.get('/%s/%s/%s' % (COURSE_NAME, base, file_name),
                            expect_errors=True)
        self.assertEquals(404, response.status_int)

    def test_deleting(self):
        base = 'assets/img'
        name = 'foo.jpg'
        en_content = 'xyzzy'
        _post_asset(self, base, name, name, en_content)

        xsrf_token = crypto.XsrfTokenManager.create_xsrf_token('delete-asset')
        key = os.path.join(base, name)
        delete_url = '%s?%s' % (
            FILES_HANDLER_URL,
            urllib.urlencode({
                'key': key,
                'xsrf_token': cgi.escape(xsrf_token)
            }))
        self.delete(delete_url)

        asset_url = '/%s/%s/%s' % (COURSE_NAME, base, name)
        response = self.get(asset_url, expect_errors=True)
        self.assertEquals(404, response.status_int)
