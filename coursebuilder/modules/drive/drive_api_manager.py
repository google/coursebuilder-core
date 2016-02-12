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

"""A wrapper for the wrapper.

It interacts with the datastore, where the wrapper it wraps does not.
"""

__author__ = [
    'nretallack@google.com (Nick Retallack)',
]

import json

import appengine_config
from google.appengine.ext import db

from models import models
from modules.drive import drive_api_client
from modules.drive import drive_api_client_mock
from modules.drive import drive_models
from modules.drive import drive_settings
from modules.drive import errors


class _DriveManager(object):
    def __init__(self, client):
        self.client = client

    @classmethod
    def from_app_context(cls, app_context):
        # pylint: disable=protected-access
        # for integration tests which can't use swap
        if appengine_config.gcb_test_mode():
            client = drive_api_client_mock._APIClientWrapperMock()

        else:
            client = drive_api_client._APIClientWrapper(
                drive_settings.get_secrets(app_context))

        return cls(client)

    @property
    def client_email(self):
        return self.client.client_email

    def list_file_meta(self, **kwargs):
        # add caching here if needed
        return self.client.list_file_meta(**kwargs)

    def get_file_meta(self, file_id):
        # add caching here if needed
        return self.client.get_file_meta(file_id)

    def download_file(self, dto):
        """Downloads a representation of the file into the datastore.

        For docs, it uses HTML.
        For sheets, it uses JSON.

        This method does not check for other concurrent actors.  Races can occur
        between the job and the manual sync handler.  However, documents are
        stored atomically in a single record, so the only consequences of a race
        are spending slightly more time and possibly temporarily regressing
        to a previous version if the document is being actively modified.
        Nothing another sync won't fix.
        """

        # Determine if the type is supported before messign with the database.
        # This will raise KeyError if you mess up.
        fetch_method = {
            drive_api_client.SHEET_TYPE: self.client.get_sheet_data,
            drive_api_client.DOC_TYPE: self.client.get_doc_as_html,
        }[dto.type]

        self._start_sync(dto.id)

        try:
            meta = self.client.get_file_meta(dto.id)
            if meta.version != dto.version:
                content = fetch_method(dto.id)
                content_chunk = models.ContentChunkDAO.get_one_by_uid(
                    models.ContentChunkDAO.make_uid(dto.type, dto.id))
                content_chunk_id = content_chunk.id if content_chunk else None
                self._save_content(meta, content, content_chunk_id)
            else:
                self._save_content_unchanged(meta)

        except errors.Error as error:
            self._save_failure(dto.id, error)
            raise error

    @db.transactional
    def _start_sync(self, file_id):
        dto = drive_models.DriveSyncDAO.load(file_id)
        dto.sync_started()
        drive_models.DriveSyncDAO.save(dto)

    @db.transactional
    def _save_failure(self, file_id, error):
        dto = drive_models.DriveSyncDAO.load(file_id)
        dto.sync_failed(error)
        drive_models.DriveSyncDAO.save(dto)

    @db.transactional
    def _save_content_unchanged(self, meta):
        dto = drive_models.DriveSyncDAO.load(meta.file_id)
        dto.dict['title'] = meta.title
        dto.sync_succeeded()
        drive_models.DriveSyncDAO.save(dto)

    @db.transactional(xg=True)
    def _save_content(self, meta, content, content_chunk_id):
        # load both
        dto = drive_models.DriveSyncDAO.load(meta.file_id)
        content_chunk = models.ContentChunkDAO.get(content_chunk_id)

        # update sync entity
        dto.dict['title'] = meta.title
        dto.version = meta.version
        dto.sync_succeeded()

        # instantiate new content chunk if necessary
        if not content_chunk:
            content_chunk = models.ContentChunkDTO({
                'type_id': meta.type,
                'resource_id': meta.file_id,
            })

        # populate content
        {
            drive_api_client.SHEET_TYPE: self._save_sheet_content,
            drive_api_client.DOC_TYPE: self._save_doc_content,
        }[dto.type](content_chunk, content)

        # Save both
        models.ContentChunkDAO.save(content_chunk)
        drive_models.DriveSyncDAO.save(dto)

    def _save_sheet_content(self, content_chunk, content):
        content_chunk.contents = json.dumps(content.to_json())
        content_chunk.content_type = 'application/json'

    def _save_doc_content(self, content_chunk, content):
        content_chunk.contents = content
        content_chunk.content_type = 'text/html'
