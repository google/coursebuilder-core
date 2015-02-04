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

"""Support for analytics on course dashboard pages."""

__author__ = ['Michael Gainer (mgainer@google.com)']

import collections

from common import schema_fields
from models import transforms
from modules.analytics import student_aggregate


class UserAgentAggregator(
    student_aggregate.AbstractStudentAggregationComponent):

    @classmethod
    def get_name(cls):
        return 'user_agent'

    @classmethod
    def get_event_sources_wanted(cls):
        return ['enter-page', 'exit-page']

    @classmethod
    def build_static_params(cls, app_context):
        return None

    @classmethod
    def process_event(cls, event, static_params):
        content = transforms.loads(event.data)
        return content.get('user_agent')

    @classmethod
    def produce_aggregate(cls, course, student, static_params, event_items):
        user_agents = collections.defaultdict(int)
        for user_agent in event_items:
            user_agents[user_agent] += 1

        ret = []
        for user_agent, count in user_agents.iteritems():
            ret.append({
                'user_agent': user_agent,
                'frequency': float(count) / len(event_items),
                })
        return {'user_agent_frequencies': ret}

    @classmethod
    def get_schema(cls):
        user_agent_frequency = schema_fields.FieldRegistry(
            'user_agent_frequency')
        user_agent_frequency.add_property(schema_fields.SchemaField(
            'user_agent', 'User Agent', 'string',
            description='User-Agent string as reported by a browser.'))
        user_agent_frequency.add_property(schema_fields.SchemaField(
            'frequency', 'Frequency', 'number',
            description='A floating point number greater than zero and less '
            'than or equal to 1.0.  Indicates the relative frequency of the '
            'user_agent in responses from this user.  The sum of all the '
            'frequency values should add up to 1.0.  The most-frequent '
            'user_agent is listed first in the array.'))
        return schema_fields.FieldArray(
          'user_agent_frequencies', 'User Agent Frequencies',
          item_type=user_agent_frequency,
          description='List of all User-Agents for this user, in '
          'descending order by proportion of responses.')
