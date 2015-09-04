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


class LocationAggregator(student_aggregate.AbstractStudentAggregationComponent):

    @classmethod
    def get_name(cls):
        return 'location'

    @classmethod
    def get_event_sources_wanted(cls):
        return ['enter-page', 'exit-page']

    @classmethod
    def build_static_params(cls, app_context):
        return None

    @classmethod
    def process_event(cls, event, static_params):
        content = transforms.loads(event.data)
        if 'loc' not in content:
            return None
        loc = content['loc']
        return loc.get('country'), loc.get('region'), loc.get('city')

    @classmethod
    def produce_aggregate(cls, course, student, static_params, event_items):
        locations = collections.defaultdict(int)
        for location in event_items:
            locations[tuple(location)] += 1

        ret = []
        for location, count in locations.iteritems():
            country, region, city = location
            item = {
                'frequency': float(count) / len(event_items),
                }
            if country:
                item['country'] = country
            if region:
                item['region'] = region
            if city:
                item['city'] = city
            ret.append(item)
        return {'location_frequencies': ret}

    @classmethod
    def get_schema(cls):
        location_frequency = schema_fields.FieldRegistry('location_frequency')
        location_frequency.add_property(schema_fields.SchemaField(
            'country', 'Country', 'string', optional=True,
            description='An ISO-3166-1 two-character country code.'))
        location_frequency.add_property(schema_fields.SchemaField(
            'region', 'Region', 'string', optional=True,
            description='A string describing a region within a country.  '
            'The format and content of this string may vary widely depending '
            'on the specific country\'s customs, but this will generally '
            'correspond to a top-level political division within the country.'))
        location_frequency.add_property(schema_fields.SchemaField(
            'city', 'City', 'string', optional=True,
            description='A string describing a town or city.  As with region, '
            'local usage and custom will dictate the values here.  This is '
            'not necessarily the lowest-level political division - e.g., '
            'this would be "New York", rather than "The Bronx"'))
        location_frequency.add_property(schema_fields.SchemaField(
            'frequency', 'Frequency', 'number',
            description='A floating point number greater than zero and less '
            'than or equal to 1.0.  Indicates the relative frequency of the '
            'location in responses from this user.  The sum of all the '
            'frequency values should add up to 1.0.  The most-frequent '
            'location is listed first in the array.'))
        return schema_fields.FieldArray(
          'location_frequencies', 'Location Frequencies',
          item_type=location_frequency,
          description='List of all locations seen for this user, in '
          'descending order by proportion of responses.')


class LocaleAggregator(student_aggregate.AbstractStudentAggregationComponent):

    @classmethod
    def get_name(cls):
        return 'locale'

    @classmethod
    def get_event_sources_wanted(cls):
        return ['enter-page', 'exit-page']

    @classmethod
    def build_static_params(cls, app_context):
        return None

    @classmethod
    def process_event(cls, event, static_params):
        content = transforms.loads(event.data)
        if 'loc' not in content:
            return None
        loc = content['loc']
        locale = (loc.get('locale') or
                  loc.get('page_locale') or
                  loc.get('language', 'UNKNOWN').split(',')[0])
        return locale

    @classmethod
    def produce_aggregate(cls, course, student, static_params, event_items):
        locales = collections.defaultdict(int)
        for locale in event_items:
            locales[locale] += 1

        ret = []
        for locale, count in locales.iteritems():
            ret.append({
                'locale': locale,
                'frequency': float(count) / len(event_items)
                })
        return {'locale_frequencies': ret}

    @classmethod
    def get_schema(cls):
        """Provide schema; override default schema generated from DB type."""

        locale_frequency = schema_fields.FieldRegistry('locale_frequency')
        locale_frequency.add_property(schema_fields.SchemaField(
            'locale', 'Language', 'string',
            description='A string indicating language and possibly regional '
            'variation.  Always starts with an ISO-639-1 two-character '
            'lanaguage code.  If the language is used in multiple countries, '
            'this is followed with an underscore ("_") character, and then '
            'an ISO-3166-1 two-character country code.  E.g., "en_US"'))
        locale_frequency.add_property(schema_fields.SchemaField(
            'frequency', 'Frequency', 'number',
            description='A floating point number greater than zero and less '
            'than or equal to 1.0.  Indicates the relative frequency of the '
            'locale in responses from this user.  The sum of all the '
            'frequency values should add up to 1.0.  The most-frequent '
            'locale is listed first in the array.'))
        return schema_fields.FieldArray(
            'locale_frequencies', 'Language Frequencies',
            item_type=locale_frequency,
            description='List of all languages seen for this user, in '
            'descending order by proportion of responses.')
