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

""" Models and forms for Drive file metadata and content. """

__author__ = [
    'nretallack@google.com (Nick Retallack)',
]

import time
import datetime

from google.appengine.ext import db

from models import courses
from models import models
from common import schema_fields
from modules.drive import messages


class DriveSyncEntity(models.BaseEntity):
    data = db.TextProperty(indexed=False)


SYNC_STATUS_NEVER = None
SYNC_STATUS_OK = 'ok'
SYNC_STATUS_FAILED = 'failed'
SYNC_STATUS_WORKING = 'working'
SYNC_STATUS_TIMED_OUT = 'timed out'

SYNC_STATUS_MESSAGES = {
    SYNC_STATUS_NEVER: 'not synced',
    SYNC_STATUS_OK: 'synced',
    SYNC_STATUS_FAILED: 'failed',
    SYNC_STATUS_WORKING: 'syncing...',
    SYNC_STATUS_TIMED_OUT: 'timed out'
}

# Assume the fetch was interrupted if it takes this long.
SYNC_TIMEOUT_SECONDS = 60 * 10


class DriveSyncDTO(object):
    def __init__(self, the_id, the_dict):
        self.id = the_id
        self.dict = the_dict

    # constant fields

    @property
    def key(self):
        return self.id

    @property
    def title(self):
        return self.dict['title']

    @property
    def type(self):
        return self.dict['type']

    # editable fields

    @property
    def sync_interval(self):
        return self.dict['sync_interval']

    @property
    def sync_interval_human(self):
        return next(human for code, human in SYNC_INTERVAL_OPTIONS
            if code == self.sync_interval)

    @property
    def availability(self):
        return self.dict.get('availability', 'private')

    # content version

    @property
    def version(self):
        return self.dict.get('file_version')

    @version.setter
    def version(self, version):
        self.dict['file_version'] = version

    # status checks

    @property
    def sync_status(self):
        if self.sync_timed_out:
            return SYNC_STATUS_TIMED_OUT
        else:
            return self.dict.get('sync_status', SYNC_STATUS_NEVER)

    @property
    def sync_status_human(self):
        return SYNC_STATUS_MESSAGES[self.sync_status]

    @property
    def sync_timed_out(self):
        if (self.dict.get('sync_status') == SYNC_STATUS_WORKING
                and time.time() - self.dict['sync_start_time'] >
                SYNC_TIMEOUT_SECONDS):
            return True

    @property
    def last_synced(self):
        return self.dict.get('last_synced')

    # status updates

    def sync_started(self):
        self.dict['sync_status'] = SYNC_STATUS_WORKING
        self.dict['sync_start_time'] = time.time()

    def sync_failed(self, error):
        self.dict['sync_status'] = SYNC_STATUS_FAILED
        self.dict['sync_fail_time'] = time.time()
        self.dict['manual_sync_requested'] = False
        self.dict['last_error'] = str(error)

    def sync_succeeded(self):
        self.dict['sync_status'] = SYNC_STATUS_OK
        self.dict['last_synced'] = time.time()
        self.dict['manual_sync_requested'] = False

    # priority checks

    @property
    def needs_sync(self):
        return (self.manual_sync_requested
            or (self.sync_interval == SYNC_INTERVAL_HOUR
                and not self.synced_this_hour)
            or (self.sync_interval == SYNC_INTERVAL_DAY
                and not self.synced_today))

    @property
    def sync_priority(self):
        return (self.manual_sync_requested, -(self.last_synced or 0))

    @property
    def synced_today(self):
        return (
            datetime.datetime.fromtimestamp(self.dict.get('sync_start_time', 0)
            ).day == datetime.datetime.utcnow().day)

    @property
    def synced_this_hour(self):
        SECONDS_IN_AN_HOUR = 60 * 60
        return (time.time() - self.dict.get('sync_start_time', 0)
            < SECONDS_IN_AN_HOUR)

    @property
    def last_sync_attempt(self):
        return max(
            self.dict.get('last_synced', 0),
            self.dict.get('sync_fail_time', 0)) or None

    # priority overrides

    def request_manual_sync(self):
        self.dict['manual_sync_requested'] = True

    @property
    def manual_sync_requested(self):
        return self.dict.get('manual_sync_requested', False)



class DriveSyncDAO(models.BaseJsonDao):
    DTO = DriveSyncDTO
    ENTITY = DriveSyncEntity
    ENTITY_KEY_TYPE = models.BaseJsonDao.EntityKeyTypeName

    @classmethod
    def load_or_new(cls, key, defaults=None):
        dto = cls.load(key)
        if dto is None:
            if defaults is None:
                defaults = {}
            dto = cls.DTO(key, defaults)
        return dto


def get_drive_sync_entity_schema():
    schema = schema_fields.FieldRegistry(
        'Google Drive Sync Item',
        description='sync',
        extra_schema_dict_values={
            'className': 'inputEx-Group new-form-layout',
        })

    schema.add_property(schema_fields.SchemaField(
        'title', 'Title', 'string', editable=False, i18n=False, optional=True))

    schema.add_property(schema_fields.SchemaField(
        'type', 'Type', 'string', editable=False, i18n=False, optional=True))

    schema.add_property(schema_fields.SchemaField(
        'id', 'ID', 'string', editable=False, i18n=False, optional=True))

    schema.add_property(schema_fields.SchemaField(
        'sync_interval', 'Sync Frequency', 'string',
        description=messages.SYNC_FREQUENCY_DESCRIPTION,
        i18n=False,
        select_data=SYNC_INTERVAL_OPTIONS,
    ))

    schema.add_property(schema_fields.SchemaField(
        'availability', 'Availability', 'string',
        description=messages.AVAILABILITY_DESCRIPTION,
        default_value=courses.AVAILABILITY_COURSE,
        i18n=False,
        select_data=courses.AVAILABILITY_SELECT_DATA,
    ))

    # DTO editor wants this.
    schema.add_property(schema_fields.SchemaField(
        'version', '', 'string', hidden=True))
    return schema


SYNC_INTERVAL_MANUAL = 'manual'
SYNC_INTERVAL_DAY = 'day'
SYNC_INTERVAL_HOUR = 'hour'

SYNC_INTERVAL_OPTIONS = (
    (SYNC_INTERVAL_MANUAL, 'Manual only'),
    (SYNC_INTERVAL_DAY, 'Daily'),
    (SYNC_INTERVAL_HOUR, 'Hourly'),
)
