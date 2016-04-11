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

"""Student aggregate collection for (mostly outbound) link clicks."""

__author__ = ['Nick Retallack (nretallack@google.com)']

from common import schema_fields
from models import transforms
from modules.analytics import student_aggregate


class ClickLinkAggregator(
    student_aggregate.AbstractStudentAggregationComponent):

    @classmethod
    def get_name(cls):
        return 'click_link'

    @classmethod
    def get_event_sources_wanted(cls):
        return ['click-link']

    @classmethod
    def build_static_params(cls, unused_app_context):
        return None

    @classmethod
    def process_event(cls, event, static_params):
        data = transforms.loads(event.data)
        return {
            "timestamp": cls._fix_timestamp(event.recorded_on),
            "href": data['href'],
        }

    @classmethod
    def produce_aggregate(cls, course, student, static_params, event_items):
        return {'click_link':
            list(sorted(event_items, key=lambda event: event["timestamp"]))}

    @classmethod
    def get_schema(cls):
        event = schema_fields.FieldRegistry('event')
        event.add_property(schema_fields.SchemaField(
            'href', 'URL', 'string',
            description='URL the link points to.'))
        event.add_property(schema_fields.SchemaField(
            'timestamp', 'Timestamp', 'timestamp',
            description='When it was clicked.'))

        field = schema_fields.FieldArray(
            'click_link', 'Clicked Links', item_type=event,
            description='A list of external links the student has clicked,'
            'sorted by time.  The same link will appear once for each click.')
        return field
