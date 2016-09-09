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

"""GraphQL schema extensions for the Course Explorer."""


import graphene
from models import courses
from modules.courses import triggers
from modules.gql import gql


def resolve_start_date(gql_course, args, info):
    """Get course card start date as a UTC ISO-8601 Zulu string.

    Returns:
      The "encoded" `when` string of the course_start MilestoneTrigger, if
      that milestone trigger exists in the 'publish' settings of the
      gql_course.course_environ.

      Otherwise, the 'start_date' string, if it exists in the 'course'
      settings of the gql_course.course_environ.

      As a last resort, None is returned.
    """
    # Dates should be returned in UTC ISO8601 Zulu format
    # (eg "2016-05-01T07:00:00.000Z")
    start_when = triggers.MilestoneTrigger.copy_milestone_from_environ(
        'course_start', gql_course.course_environ).get('when')
    if start_when:
        return start_when

    return courses.Course.get_named_course_setting_from_environ(
        'start_date', gql_course.course_environ)


def resolve_end_date(gql_course, args, info):
    """Get course card end date as a UTC ISO-8601 Zulu string.

    Returns:
      The "encoded" `when` string of the course_end MilestoneTrigger, if
      that milestone trigger exists in the 'publish' settings of the
      gql_course.course_environ.

      Otherwise, the 'end_date' string, if it exists in the 'course'
      settings of the gql_course.course_environ.

      As a last resort, None is returned.
    """
    # Dates should be returned in UTC ISO8601 Zulu format
    # (eg "2016-05-01T07:00:00.000Z")
    end_when = triggers.MilestoneTrigger.copy_milestone_from_environ(
        'course_end', gql_course.course_environ).get('when')
    if end_when:
        return end_when

    return courses.Course.get_named_course_setting_from_environ(
        'end_date', gql_course.course_environ)


def register():
    gql.Course.add_to_class(
        'start_date', graphene.String(resolver=resolve_start_date))
    gql.Course.add_to_class(
        'end_date', graphene.String(resolver=resolve_end_date))
