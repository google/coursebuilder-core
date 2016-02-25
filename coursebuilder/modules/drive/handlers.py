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

"""Request handlers for the Drive module."""

__author__ = 'Nick Retallack (nretallack@google.com)'

import json
import logging

from common import utils as common_utils
from controllers import utils
from models import courses
from models import models
from models import transforms
from modules.dashboard import dto_editor
from modules.drive import constants
from modules.drive import cron
from modules.drive import dashboard_handler
from modules.drive import drive_api_client
from modules.drive import drive_api_manager
from modules.drive import drive_models
from modules.drive import drive_settings
from modules.drive import errors
from modules.drive import jobs


def _sorted_drive_items(items):
    return list(sorted(items, key=lambda item: item.title))


class AbstractDriveDashboardHandler(dashboard_handler.AbstractDashboardHandler):
    TEMPLATE_DIRS = [constants.TEMPLATE_DIR]

    def setup_drive(self):
        try:
            # pylint: disable=protected-access
            self.drive_manager = (
                drive_api_manager._DriveManager.from_app_context(
                    self.app_context))
            # pylint: enable=protected-access
        except errors.NotConfigured:
            self.redirect('/' + DriveNotConfiguredHandler.URL, abort=True)

    def before_method(self, method, path):
        super(AbstractDriveDashboardHandler, self).before_method(method, path)
        self.setup_drive()

    def handle_error(self, error):
        if isinstance(error, errors.TimeoutError):
            logging.error('Google Drive Timed Out')
            self.response.set_status(504)
            self.render_other('drive-timeout.html')
        else:
            logging.error('Google Drive Error: %s', error)
            self.response.set_status(502)
            self.render_other('drive-failed.html')

    def create_sync_schedule(self, key, data):
        dto = drive_models.DriveSyncDAO.DTO(key, {
            'title': data.title,
            'type': data.type,
            'sync_interval': drive_models.SYNC_INTERVAL_MANUAL,
            'availability': courses.AVAILABILITY_COURSE,
            'version': '1.0',
        })
        drive_models.DriveSyncDAO.save(dto)

        # Attempt to sync now.  If it fails, that's ok.  The error will be
        # visible in the list view.
        try:
            self.drive_manager.download_file(dto)
        except errors.Error as error:
            logging.error('Google Drive Error: %s', error)

        return dto


class DriveListHandler(AbstractDriveDashboardHandler):
    PAGE_TITLE = 'Drive'
    URL = 'modules/drive'
    TEMPLATE = 'drive-list.html'
    ACTION = 'drive-list'
    EXTRA_JS_URLS = [
        '/modules/drive/_static/script.js',
        'https://apis.google.com/js/client:platform.js?onload=onGoogleApiLoaded'
    ]
    EXTRA_CSS_URLS = ['/modules/drive/_static/style.css']

    # hooks
    EXTRA_HEADER_CONTENT = []
    EXTRA_ROW_CONTENT = []

    def get(self):
        super(DriveListHandler, self).get()
        items = _sorted_drive_items(drive_models.DriveSyncDAO.get_all())

        self.render_this(
            items=items,
            automatic_sharing_is_available=
                drive_settings.automatic_sharing_is_available(self.app_context),
            google_api_key=drive_settings.get_google_api_key(self.app_context),
            google_client_id=
                drive_settings.get_google_client_id(self.app_context),
            add_rest_xsrf_token=
                self.create_xsrf_token(DriveAddRESTHandler.ACTION),
            add_rest_url=DriveAddRESTHandler.URL,

            # pylint: disable=protected-access
            job_status_url=self.app_context.canonicalize_url(
                '/rest/core/jobs/status?name={}'.format(
                    jobs.DriveSyncJob(self.app_context)._job_name)),
            # pylint: enable=protected-access

            sync_url=DriveSyncHandler.URL,
            sync_xsrf_token=self.create_xsrf_token(DriveSyncHandler.ACTION),
            sync_xsrf_action=DriveSyncHandler.ACTION,

            job_url=DriveSyncJobHandler.URL,
            job_xsrf_token=self.create_xsrf_token(
                DriveSyncJobHandler.ACTION),
            job_xsrf_action=DriveSyncJobHandler.ACTION,

            header_hooks=self.EXTRA_HEADER_CONTENT,
            row_hooks=self.EXTRA_ROW_CONTENT,
            app_context=self.app_context,

            # urls
            this_url=self.URL,
            add_url=DriveAddListHandler.URL,
            item_url=DriveItemHandler.URL,
            content_url=DriveContentHandler.URL,
            sheets_to_site_url=(
                '/modules/sheets_to_site/_static/index.html?course={}'.format(
                    self.app_context.get_slug())),
        )


class DriveSyncHandler(AbstractDriveDashboardHandler):
    URL = 'modules/drive/sync'
    ACTION = 'drive-sync'

    def post(self):
        """Sync one item."""
        super(DriveSyncHandler, self).post()

        key = self.request.get('key')
        dto = drive_models.DriveSyncDAO.load(key)
        if dto is None:
            self.abort(400)

        # Redirect browsers regardless of errors, return empty responses with
        # status codes to XHRs.
        is_xhr = 'text/html' not in self.request.headers.get('Accept', '')

        try:
            self.drive_manager.download_file(dto)
        except errors.Error as error:
            if is_xhr:
                status = 504 if isinstance(error, errors.TimeoutError) else 502
                self.response.set_status(status)
                self.response.write('')
                return

        if is_xhr:
            self.response.set_status(204)
            self.response.write('')
        else:
            self.redirect(self.app_context.canonicalize_url(
                '/' + DriveListHandler.URL))


class DriveSyncJobHandler(AbstractDriveDashboardHandler):
    URL = 'modules/drive/job'
    ACTION = 'drive-job'

    def post(self):
        super(DriveSyncJobHandler, self).post()

        job = jobs.DriveSyncJob(self.app_context)
        action = self.request.get('action')
        if action == 'cancel':
            job.cancel()
        else:
            self.abort(400)

        self.redirect(self.app_context.canonicalize_url('/{}'.format(
            DriveListHandler.URL)))


class DriveNotConfiguredHandler(dashboard_handler.AbstractDashboardHandler):
    PAGE_TITLE = 'Drive Not Configured'
    URL = 'modules/drive/error'
    TEMPLATE = 'drive-not-configured.html'
    ACTION = 'drive-not-configured'
    IN_ACTION = DriveListHandler.ACTION
    TEMPLATE_DIRS = [constants.TEMPLATE_DIR]

    def get(self):
        self.render_this()


class DriveAddListHandler(AbstractDriveDashboardHandler):
    PAGE_TITLE = 'Add from Drive'
    URL = 'modules/drive/add'
    TEMPLATE = 'drive-add.html'
    ACTION = 'drive-add'
    IN_ACTION = DriveListHandler.ACTION
    EXTRA_CSS_URLS = ['/modules/drive/_static/style.css']

    def get(self):
        super(DriveAddListHandler, self).get()

        existing_item_keys = set(item.key
            for item in drive_models.DriveSyncDAO.get_all())

        try:
            data = self.drive_manager.list_file_meta()
        except errors.Error as error:
            self.handle_error(error)
            return

        new_items = [item
            for item in data.items
            if item.key not in existing_item_keys]

        self.render_this(
            items=new_items,
            service_account_email=
                drive_settings.get_client_email(self.app_context),

            add_url=self.URL,
            add_action=self.ACTION,
            add_xsrf_token=self.create_xsrf_token(self.ACTION),
        )

    def post(self):
        super(DriveAddListHandler, self).post()
        key = self.request.get('key')

        try:
            data = self.drive_manager.get_file_meta(key)
        except errors.Error as error:
            self.handle_error(error)
            return

        if data.type not in drive_api_client.KNOWN_MIME_TYPES.values():
            self.abort(404)

        self.create_sync_schedule(key, data)

        self.redirect(self.app_context.canonicalize_url(
            '/{}?key={}'.format(DriveItemHandler.URL, key)))


class DriveAddRESTHandler(AbstractDriveDashboardHandler):
    URL = 'rest/modules/drive/add'
    ACTION = 'drive-add-rest'

    def post(self):
        super(DriveAddRESTHandler, self).post()
        code = self.request.get('code')
        file_id = self.request.get('file_id')

        # attempt to share
        try:
            # pylint: disable=protected-access
            current_user_drive_manager = (
                drive_api_manager._DriveManager.from_code(
                    self.app_context, code))
            # pylint: enable=protected-access
            current_user_drive_manager.share_file(
                file_id, drive_settings.get_client_email(self.app_context))

        except errors.Error as error:
            if isinstance(error, errors.SharingPermissionError):
                message = 'You do not have permission to share this file.'
            else:
                message = (
                    'An unknown error occurred when sharing this file.  Check '
                    'your Drive or Google API configuration or try again.')

            transforms.send_json_response(
                self, 502, 'error', payload_dict={
                    'status': 'error',
                    'message': message,
            })
            return

        try:
            data = self.drive_manager.get_file_meta(file_id)
        except errors.Error as error:
            transforms.send_json_response(
                self, 502, 'error', payload_dict={
                    'status': 'error',
                    'message':
                        'File shared, but Drive API failed to fetch metadata.  '
                        'Please try again or check your Drive configuration.',
            })
            return

        # Generally this should create a new record, but if one already exists
        # that's ok.  Just don't want to clobber it.
        dto = drive_models.DriveSyncDAO.load(file_id)
        if dto is None:
            self.create_sync_schedule(file_id, data)

        transforms.send_json_response(
            self, 200, 'ok', payload_dict={
                'status': 'success',
                'message': 'Shared.',
        })


class DriveItemHandler(
        AbstractDriveDashboardHandler, dto_editor.BaseDatastoreAssetEditor):
    PAGE_TITLE = 'Drive Document'
    URL = 'modules/drive/item'
    TEMPLATE = 'drive-item.html'
    ACTION = 'drive-item'
    IN_ACTION = DriveListHandler.ACTION

    def get(self):
        super(DriveItemHandler, self).get()

        key = self.request.get('key')
        if not key:
            self.abort(404)

        self.render_content(self.get_form(
            DriveItemRESTHandler, key, '/' + DriveListHandler.URL))


class DriveItemRESTHandler(dto_editor.BaseDatastoreRestHandler):
    URL = 'rest/modules/drive/item'
    URI = '/' + URL
    XSRF_TOKEN = 'drive-item-rest'
    DAO = drive_models.DriveSyncDAO

    # Allow hooks
    SCHEMA_LOAD_HOOKS = []
    PRE_LOAD_HOOKS = []
    PRE_SAVE_HOOKS = []
    PRE_DELETE_HOOKS = []
    VALIDATE_HOOKS = []

    CAN_CREATE = False

    @classmethod
    def get_schema(cls):
        schema = drive_models.get_drive_sync_entity_schema()
        common_utils.run_hooks(cls.SCHEMA_LOAD_HOOKS, schema)
        return schema

    @classmethod
    def get_and_populate_dto(cls, key, python_dict):
        dto = cls.DAO.load(key)
        dto.dict.update(python_dict)
        return dto


class DriveContentHandler(utils.CourseHandler):
    URL = 'modules/drive/item/content'

    def get(self):
        key = self.request.get('key')
        if not key:
            self.abort(404)

        # check availability
        item = drive_models.DriveSyncDAO.load(key)
        if item is None or not self.check_availability(item.availability):
            self.abort(404)

        # find the synced content
        chunk = models.ContentChunkDAO.get_one_by_uid(
            models.ContentChunkDAO.make_uid(item.type, key))
        if chunk is None:
            self.abort(404)

        self.response.headers['Last-Modified'] = str(item.last_synced)
        # TODO(nretallack): implement if-modified-since check here

        if chunk.content_type == 'application/json':
            transforms.send_json_response(
                self, 200, 'ok', payload_dict=json.loads(chunk.contents))
        else:
            self.response.headers['Content-Type'] = str(chunk.content_type)
            self.response.write(chunk.contents)


global_routes = utils.map_handler_urls([
    cron.DriveCronHandler,
])

namespaced_routes = utils.map_handler_urls([
    DriveListHandler,
    DriveAddListHandler,
    DriveAddRESTHandler,
    DriveSyncHandler,
    DriveItemHandler,
    DriveItemRESTHandler,
    DriveContentHandler,
    DriveNotConfiguredHandler,
    DriveSyncJobHandler,
])
