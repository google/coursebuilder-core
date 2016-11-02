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
from modules.courses import constants
from modules.courses import triggers
from modules.gql import gql


def resolve_start_date(gql_course, args, info):
    """Get course card start date as a UTC ISO-8601 Zulu string.

    Student group overrides for the current user are injected into the
    gql_course.course_environ property when it is accessed. The original
    Course 'start_date' setting value is overwritten if the current user is
    in a student group having a corresponding start_date property value.

    The course_environ property calls courses.Course.get_environ(), passing
    it gql_course.app_context. The COURSE_ENV_POST_COPY_HOOKS are then run
    when get_environ() calls _run_env_post_copy_hooks(). One of those hooks
    is student_groups.modify_course_environment(). That hook calls the
    apply_overrides_to_environ() function in student_groups.graphql, which
    overwrites 'course:start_date' with the value of the start_date property
    in the StudentGroupDTO if that property has a value.

    Returns:
      The 'course:start_date' (constants.START_DATE_SETTING) string, if it
      exists in the 'course' settings of the gql_course.course_environ.
      Otherwise, None is returned.
    """
    return courses.Course.get_named_course_setting_from_environ(
        constants.START_DATE_SETTING, gql_course.course_environ)


def resolve_end_date(gql_course, args, info):
    """Get course card end date as a UTC ISO-8601 Zulu string.

    Student group overrides are injected similarly to resolve_start_date().

    Returns:
      The 'course:end_date' (constants.END_DATE_SETTING) string, if it exists
      in the 'course' settings of the gql_course.course_environ. Otherwise,
      None is returned.
    """
    return courses.Course.get_named_course_setting_from_environ(
        constants.END_DATE_SETTING, gql_course.course_environ)


def register_resolvers():
    gql.Course.add_to_class(constants.START_DATE_SETTING,
        graphene.String(resolver=resolve_start_date))
    gql.Course.add_to_class(constants.END_DATE_SETTING,
        graphene.String(resolver=resolve_end_date))


def update_start_date_from_course_start_when(start_trigger, unused_changed,
                                             course, env):
    if not start_trigger:
        return

    iso8601_when = start_trigger.encoded_when
    if not iso8601_when:
        return

    start_trigger.set_corresponding_setting(
        start_trigger.milestone, iso8601_when, env, course=course)


def update_end_date_from_course_end_when(end_trigger, unused_changed,
                                         course, env):
    if not end_trigger:
        return

    iso8601_when = end_trigger.encoded_when
    if not iso8601_when:
        return

    end_trigger.set_corresponding_setting(
        end_trigger.milestone, iso8601_when, env, course=course)


def register_callbacks():
    # Callbacks that will (eventually) make it possible for the GraphQL
    # resolvers to *only* examine course:start_date and course:end_date and
    # not be concerned with the course_start and course_end triggers at all.
    # (See TODOs above, and update this comment when they are addressed.)
    triggers.MilestoneTrigger.ACT_HOOKS[constants.START_DATE_MILESTONE][
        constants.MODULE_NAME] = update_start_date_from_course_start_when
    triggers.MilestoneTrigger.ACT_HOOKS[constants.END_DATE_MILESTONE][
        constants.MODULE_NAME] = update_end_date_from_course_end_when


def notify_module_enabled():
    register_resolvers()
    register_callbacks()
