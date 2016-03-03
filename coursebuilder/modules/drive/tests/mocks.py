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

"""A fake version of the API client wrapper that won't use the network."""

__author__ = [
    'nretallack@google.com (Nick Retallack)',
]

from modules.drive import drive_api_client
from modules.drive import drive_api_manager
from modules.drive import errors


class _APIClientWrapperMock(object):
    """Mimicks _APIClientWrapper but returns test data."""
    MOCK_FILES = [
        drive_api_client.DriveItem(
            '1', drive_api_client.DOC_TYPE, '1 Test Doc', 1),
        drive_api_client.DriveItem(
            '2', drive_api_client.SHEET_TYPE, '2 Test Sheet', 1),
        drive_api_client.DriveItem(
            '3', drive_api_client.SHEET_TYPE, '3 Another Test Sheet', 1),
        drive_api_client.DriveItem(
            '4', 'unknown', '4 Some Unknown File', 1),
        drive_api_client.DriveItem(
            '5', drive_api_client.DOC_TYPE, '5 Another Test Doc', 1),
        drive_api_client.DriveItem(
            '6', drive_api_client.SHEET_TYPE, '6 Synced Sheet', 1)
    ]

    SHARABLE_FILE = drive_api_client.DriveItem(
        '7', drive_api_client.DOC_TYPE, '7 Sharable Doc', 1)

    def list_file_meta(self):
        return drive_api_client.DriveItemList(self.MOCK_FILES)

    def get_file_meta(self, file_id):
        for item in self.MOCK_FILES:
            if item.key == file_id:
                return item

        raise errors.Error


    def get_sheet_data(self, file_id):
        meta = self.get_file_meta(file_id)
        if meta is None or meta.type != drive_api_client.SHEET_TYPE:
            raise errors.Error()
        return drive_api_client.Sheet(
            file_id=meta.key,
            title=meta.title,
            worksheets=[
                drive_api_client.Worksheet(
                    worksheet_id='1',
                    title='Main Worksheet',
                    cells=[
                        ['a', 'b', 'c'],
                        ['1', '2', '3'],
                    ]
                )
            ]
        )

    def get_doc_as_html(self, file_id):
        meta = self.get_file_meta(file_id)
        if meta is None or meta.type != drive_api_client.DOC_TYPE:
            raise errors.Error()

        return '<p>Some HTML</p>'

    def share_file(self, file_id, email):
        if self.SHARABLE_FILE not in self.MOCK_FILES:
            self.MOCK_FILES = self.MOCK_FILES.append(self.SHARABLE_FILE)

    @classmethod
    def create(cls, *args, **kwargs):
        return cls()

    from_service_account_secrets = from_client_secrets_and_code = create



def raise_error(*args, **kwargs):
    raise errors.Error(Exception())


def raise_timeout(*args, **kwargs):
    raise errors.TimeoutError(Exception())


def raise_sharing_permission_error(*args, **kwargs):
    raise errors.SharingPermissionError(errors.Error)


def manager_from_mock(cls, *args, **kwargs):
    return cls(_APIClientWrapperMock())


def setup_drive(self):
    self.drive_manager = manager_from_mock(drive_api_manager._DriveManager)


def get_secrets(*args):
    return {
        'client_email': 'service-account@example.com',
        'private_key': TESTING_KEY,
    }


def install_integration_mocks():
    drive_api_client._APIClientWrapper = _APIClientWrapperMock


# This key is not a real credential for anything.
TESTING_KEY = """-----BEGIN PRIVATE KEY-----
MIIEowIBAAKCAQEA5J9Lc+Hny6pBkl4bkWaz4piOzYvNHTemydKohWROPiJtuzO4
AbQ+b+C2sQXImiPeUJ2+uwrCxegrBokwhYqQvVCRNf4kxRdOWgDnA40qfJiUBh+9
FNogY6q6xTPk8W9gxYLsba6/A9AIi//8UDG4Ggr0wjGJrOoyabq4fmJQOSx1utq1
omDD040NMjI/VGqo3Wo0dxeBhK6j2uXGagFNcQsRbEtE5nT5sZSNJ7RD3vrYzUPq
ygXGfHCtr440nowqiRTkNkbWnoM4d2et/MH5Gvhf10I1DEdfSdbLPodc0WqhLdLp
utVXpTYJKjUqOk+QTuSFxnrjH4ZDwbhsomx3DwIDAQABAoIBAAyqorSN7JjFGxLv
8dkRdp/0Ud0jhL68qZn++OVDFG6u26OGjwhRIzBxo82VA3M+z39p7fpQ80+huFiJ
W03ayoAiqZjzNrhQvT+RUztII/V5QqJAOeqg1zCOcgChCmsx/4uR4GWHS//7E64m
BaWvy4Jt3vevZPBWnWpsNPKTodw49pAeslb1Bh64Ot0tJyumcOPpjP/IaLwVa0WV
VMpd7TeAgG3/y6zbag/ar3ePY574AmNcsNgtgF68Cd2CbQy2e+nNCHJUXKh9PsvY
7Jyr2AEPnQsiQTKrrLaZbKDZjaTRYykWaPMgicj1jfIHQXEuhZ4usmRsI+Xbud9a
1RYlXQECgYEA9+YN2R4H4KfNo7kf743bQoFEQ/VedDpwXTsYHa+mC+1x3HONya+a
7AWSpUKA/Rl6z6Wk2+Qf6RHbKOkaz+jO5ALvE2XQTkNDzCYxNOcChR1nxt69jdns
VKqHaaX/6zAXEUHcbFYdn+4jbZxUINc1WB7Qo2Z+3rF0wfvc5vAYGoECgYEA7Bf4
5Nxhjc8CobTbk3kslezcnx8hJlrNBXp216JnsafbfElPcpEXL6LKC0VgvR9ZKbOQ
8V269bk82lQSn1wFSVL3MfF47j7FXE5pjlXNyczxrJa1RwjWd4gaxOqnRuDrN8Id
H5XTFFKCkx+GsBklcZlRZMyF5olPN4bG+Xc3KY8CgYEA2d1wnDk9WR6Apvwi6gj1
AuzSjxtNCL73U6iE2Eovl1n18HYJzZAsinOXXvAkpsvG2ElOqwZBWTedMcY0Dzce
5NsDPDwFp1KMehWytzizSUP/mZLWap10izBX0+zVDuBz1XHZg8jnPlAvCL0UXsxk
kG58lK6Wn6a742Qzzy6BMIECgYAYS385TdRcG2lR6qKN0nJcGzu4xCNNJxrh7XA9
UGELTxKu/3xFddjE9iOEdWc3DvrF58yKifKrRpyUewJPk9CXcwotAYRIP/1fOlJy
azH6CjT0Za3R2X74XfEjQmJkUNDjs/37Ohe2h6cYLK5XgL7xqa1Oih1dU9PrCtt+
4F200QKBgCS6THFlSSrQfk24HDG7Qd+Ka6Ju9+lIG9x3X4voa7JJKc72Fo626l15
GDd7+xDI1Z3o5rzrsN8XpUaNHwfILKkcg2cCzjA4iTywc4N7CA7yrcyw6l5tkAQd
9DwacpIhxkbKvMISCfv5Ysa7kP/32Pd6d8G5OVWxIbdmuHOuEcc+
-----END PRIVATE KEY-----
"""
