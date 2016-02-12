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

"""A thin wrapper around the Drive and Sheets API."""

__author__ = [
    'nretallack@google.com (Nick Retallack)',
]

import httplib2
import itertools
import json

from google.appengine.api import urlfetch
from google.appengine.api import urlfetch_errors

from apiclient import discovery
from apiclient import errors as apiclient_errors
import oauth2client

from modules.drive import errors

_DRIVE_SCOPE = 'https://www.googleapis.com/auth/drive'
_SHEETS_SCOPE = 'https://spreadsheets.google.com/feeds'
_ALL_SCOPES = " ".join((_DRIVE_SCOPE, _SHEETS_SCOPE))

SHEET_MIME_TYPE = 'application/vnd.google-apps.spreadsheet'
DOC_MIME_TYPE = 'application/vnd.google-apps.document'
SHEET_TYPE = 'sheet'
DOC_TYPE = 'doc'
KNOWN_MIME_TYPES = {
    SHEET_MIME_TYPE: SHEET_TYPE,
    DOC_MIME_TYPE: DOC_TYPE,
}

_URLFETCH_DEADLINE_SECONDS = 20


class _APIClientWrapper(object):
    """Facade for accessing Google Drive, Docs, and Sheets APIs.

    Raises Error when accessing missing data.

    This class is lazy.  It will accept client secrets at construction time,
    but it will not perform OAuth until it has to do a web request.
    """

    def __init__(self, secrets, scope=_ALL_SCOPES):
        validate_secrets(secrets)
        self._secrets = secrets
        self._scope = scope
        self._drive_client_instance = None
        urlfetch.set_default_fetch_deadline(_URLFETCH_DEADLINE_SECONDS)

    @property
    def client_email(self):
        """Email address of the service account.

        You may need to share resources with this email in order to access them.
        """
        return self._secrets['client_email']

    def _make_drive_client(self):
        try:
            credentials = oauth2client.client.SignedJwtAssertionCredentials(
                self._secrets['client_email'], self._secrets['private_key'],
                self._scope)
            http_auth = credentials.authorize(httplib2.Http())
            return discovery.build('drive', 'v2', http=http_auth)
        except Exception as error:
            # pylint: disable=protected-access
            raise errors._WrappedError(error)
            # pylint: enable=protected-access

    @property
    def _drive_client(self):
        if self._drive_client_instance is None:
            self._drive_client_instance = self._make_drive_client()
        return self._drive_client_instance

    def _http_request(self, url):
        """Perform an arbitrary HTTP request using the Python API client.

        This uses the OAuth credentials that are already set up.
        Based on the example code found at:
        https://developers.google.com/drive/web/manage-downloads
        """
        # pylint: disable=protected-access
        try:
            response, content = self._drive_client._http.request(url)
            if response.status == 200:
                return content
            else:
                raise errors._HttpError(url, response, content)
        except urlfetch_errors.DeadlineExceededError as error:
            raise errors.TimeoutError(error)

    def list_file_meta(self, max_results=100, page_token=None):
        """Returns a DriveItemList"""
        # TODO(nretallack): It's possible that this could time out.
        # Stress-test and tune the max_results number.
        try:
            return DriveItemList.from_api_list(self._drive_client.files().list(
                maxResults=max_results,
                pageToken=page_token,
            ).execute())

        except apiclient_errors.Error as error:
            # pylint: disable=protected-access
            raise errors._WrappedError(error)
            # pylint: enable=protected-access
        except urlfetch_errors.DeadlineExceededError as error:
            raise errors.TimeoutError(error)

    def get_file_meta(self, file_id):
        """Returns a single DriveItem"""
        return DriveItem.from_api_item(self._get_file_meta(file_id))

    def _get_file_meta(self, file_id):
        """Returns the raw un-wrapped metadata"""
        try:
            return self._drive_client.files().get(fileId=file_id).execute()
        except apiclient_errors.Error as error:
            # pylint: disable=protected-access
            raise errors._WrappedError(error)
            # pylint: enable=protected-access
        except urlfetch_errors.DeadlineExceededError as error:
            raise errors.TimeoutError(error)

    def get_doc_as_html(self, file_id):
        """Returns the HTML export of a google doc."""
        meta = self._get_file_meta(file_id)
        try:
            return self._http_request(meta['exportLinks']['text/html'])
        except KeyError:
            raise errors.Error

    def get_sheet_data(self, file_id):
        """Download a spreadsheet and all its worksheets."""
        meta = json.loads(self._http_request(self._make_sheets_url(
            'worksheets/{}'.format(file_id))))['feed']

        return Sheet(
            file_id=file_id,
            title=meta['title']['$t'],
            worksheets=[
                self._get_worksheet_data(file_id, worksheet)
                for worksheet in meta['entry']
            ],
        )

    def _get_worksheet_data(self, file_id, worksheet_meta):
        worksheet_id = worksheet_meta['id']['$t'].rsplit('/', 1)[1]

        return Worksheet(
            cells=self._get_worksheet_rows(file_id, worksheet_id),
            title=worksheet_meta['title']['$t'],
            worksheet_id=worksheet_id,
        )

    def _get_worksheet_rows(self, file_id, worksheet_id):
        def row_keyfunc(cell_data):
            return int(cell_data['gs$cell']['row'])

        def cell_keyfunc(cell_data):
            return (
                int(cell_data['gs$cell']['row']),
                int(cell_data['gs$cell']['col']))

        def format_row(cells):
            """Blank cells are not present in the feed.

            To make things line up, we will fill them in with empty strings.
            We don't fill in trailing blanks."""

            result = []
            for cell in cells:
                while len(result) < int(cell['gs$cell']['col']):
                    result.append('')
                result.append(cell['gs$cell']['$t'])
            return result

        result = [
            format_row(cells)
            for row_index, cells in itertools.groupby(
                sorted(
                    self._get_worksheet_meta(file_id, worksheet_id)['entry'],
                    key=cell_keyfunc,
                ),
                key=row_keyfunc,
            )
        ]

        return result

    def _get_worksheet_meta(self, file_id, worksheet_id):
        return json.loads(self._http_request(self._make_sheets_url(
            'cells/{}/{}'.format(file_id, worksheet_id))))['feed']

    def _make_sheets_url(self, path):
        return ('https://spreadsheets.google.com/feeds/{}/private/full?alt=json'
            ).format(path)


class Sheet(object):
    def __init__(self, file_id=None, title=None, worksheets=None):
        self.file_id = file_id
        self.title = title
        self.worksheets = worksheets or []

    def to_json(self):
        return {
            'id': self.file_id,
            'title': self.title,
            'worksheets': [worksheet.to_json() for worksheet in self.worksheets]
        }

    @property
    def key(self):
        return self.file_id


class Worksheet(object):
    def __init__(self, cells=None, file_id=None, title=None, worksheet_id=None):
        self.file_id = file_id
        self.worksheet_id = worksheet_id
        self.title = title
        self.cells = cells or []

    def to_json(self):
        return {
            'id': self.worksheet_id,
            'title': self.title,
            'cells': self.cells,
        }

    @property
    def key(self):
        return self.worksheet_id


class DriveItem(object):
    def __init__(self, file_id, file_type, title, version):
        self.file_id = file_id
        self.type = file_type
        self.title = title
        self.version = version

    @classmethod
    def from_api_item(cls, data):
        return cls(
            data['id'],
            KNOWN_MIME_TYPES.get(data['mimeType'], 'unknown'),
            data['title'],
            data['version'],
        )

    @property
    def can_sync(self):
        return self.type in [SHEET_TYPE, DOC_TYPE]

    @property
    def key(self):
        return self.file_id


class DriveItemList(object):
    def __init__(self, items, next_page_token=None):
        self.items = items
        self.next_page_token = next_page_token

    @classmethod
    def from_api_list(cls, data):
        return cls([DriveItem.from_api_item(item) for item in data['items']],
            next_page_token=data.get('nextPageToken'))


def validate_secrets(secrets):
    try:
        assert isinstance(secrets, dict)
        client_email = secrets.get('client_email')
        assert isinstance(client_email, basestring)
        assert '@' in client_email
        private_key = secrets.get('private_key')
        assert isinstance(private_key, basestring)
        assert private_key.startswith('-----BEGIN PRIVATE KEY-----\n')
        assert private_key.endswith('\n-----END PRIVATE KEY-----\n')
    except AssertionError as error:
        raise errors.Misconfigured(error)
