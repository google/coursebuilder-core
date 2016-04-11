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

"""Student aggregate collection for detailed YouTube interaction logs."""

__author__ = ['Michael Gainer (mgainer@google.com)']

from common import schema_fields
from models import transforms
from modules.analytics import student_aggregate

# This is YouTube's mapping from their 'data' field in YT events to meaning.
ACTION_ID_TO_NAME = {
    -1: 'unstarted',
    0: 'ended',
    1: 'playing',
    2: 'paused',
    3: 'buffering',
    5: 'video cued'
}


class YouTubeEventAggregator(
    student_aggregate.AbstractStudentAggregationComponent):

    @classmethod
    def get_name(cls):
        return 'youtube_event'

    @classmethod
    def get_event_sources_wanted(cls):
        return ['tag-youtube-event']

    @classmethod
    def build_static_params(cls, unused_app_context):
        return None

    @classmethod
    def process_event(cls, event, static_params):
        data = transforms.loads(event.data)
        video_id = data['video_id']
        position = data['position']
        action = data['data']
        timestamp = cls._fix_timestamp(event.recorded_on)
        return (video_id, position, action, timestamp)

    @classmethod
    def produce_aggregate(cls, course, student, static_params, event_items):
        # Sort by timestamp, then video ID, then position.
        event_items.sort(key=lambda item: (item[3], item[0], item[1]))

        youtube_interactions = []
        prev_video_id = None
        prev_position = 0
        current_interaction = None
        for event_item in event_items:
            video_id, position, action, timestamp = event_item

            # If we are seeing events either for a different video ID than
            # last time, or we are on the same ID, but have rewound to 0,
            # then call that a new interaction.
            if video_id != prev_video_id or prev_position > 0 and position == 0:
                current_interaction = {
                    'video_id': video_id,
                    'events': [],
                }
                youtube_interactions.append(current_interaction)
            prev_video_id = video_id
            prev_position = position

            # And build the detail event, adding it to the current interaction.
            event = {
                'position': position,
                'timestamp': timestamp,
            }
            if action in ACTION_ID_TO_NAME:
                event['action'] = ACTION_ID_TO_NAME[action]
            else:
                event['action'] = str(action)
            current_interaction['events'].append(event)

        return {'youtube': youtube_interactions}

    @classmethod
    def get_schema(cls):
        youtube_event = schema_fields.FieldRegistry('event')
        youtube_event.add_property(schema_fields.SchemaField(
            'position', 'Position', 'integer',
            description='Offset from start of video, in seconds.'))
        youtube_event.add_property(schema_fields.SchemaField(
            'action', 'Action', 'string',
            description='Type of event that has occurred.  The types that '
            'are known are: unstarted, ended, playing, paused, buffering, '
            'and video cued.  If YouTube adds more types of events than '
            'these, they will be reported as a string version of the '
            'integer event code supplied by YouTube.  Please see YouTube '
            'documentation for interpretation of unknown codes.'))
        youtube_event.add_property(schema_fields.SchemaField(
            'timestamp', 'Timestamp', 'timestamp',
            description='Moment when event occurred.'))

        youtube_interaction = schema_fields.FieldRegistry('interaction')
        youtube_interaction.add_property(schema_fields.SchemaField(
            'video_id', 'Video ID', 'string',
            description='The ID of the YouTube video.  E.g., Kdg2drcUjYI '))
        youtube_interaction.add_property(schema_fields.FieldArray(
            'events', 'YouTube Events', item_type=youtube_event,
            description='A list of events describing an interaction with '
            'a video.  Note that these are grouped sequentially by '
            'video ID from the raw stream.  It is technically possible, '
            'though unlikely, to get confusing results if multiple '
            'videos are viewed simultaneously by one student.'))

        youtube_interactions = schema_fields.FieldArray(
            'youtube', 'YouTube Interactions', item_type=youtube_interaction,
            description='A list of interactions with individual YouTube '
            'video.  These are ordered by the first interaction with a '
            'given video ID, and group together multiple actions '
            'within the same interaction.')
        return youtube_interactions
