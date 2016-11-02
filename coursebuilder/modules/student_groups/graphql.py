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

"""Hooks for keeping info used by GraphQL and Course Explorer up-to-date."""


from models import courses
from modules.courses import constants


def apply_overrides_to_environ(student_group, env):
    """Overrides course start/end dates displayed in the course explorer.

    If student_group has a value for the start_date property, that value
    overwrites env['course']['start_date']. The 'course:end_date' is
    similarly overwritten if end_date has a value.

    Args:
        student_group: a StudentGroupDTO.
        env: a Course get_environ() dict containing settings (some of which
           are displayed on course cards in the course explorer) that are
           modified *in place* by student group specific overrides.
    """
    if not student_group:
        return  # The current user was not a member of a student group.

    start_date = student_group.start_date
    if start_date:
        # A start_date override was obtained from the student_group, so
        # overwrite any existing value in the Course get_environ() dict.
        courses.Course.set_named_course_setting_in_environ(
            constants.START_DATE_SETTING, env, start_date)

    end_date = student_group.end_date
    if end_date:
        # An end_date override was obtained from the student_group, so
        # overwrite any existing value in the Course get_environ() dict.
        courses.Course.set_named_course_setting_in_environ(
            constants.END_DATE_SETTING, env, end_date)


def update_start_date_from_start_override_when(start_trigger, unused_changed,
                                               unused_course, student_group):
    if not start_trigger:
        return

    iso8601_when = start_trigger.encoded_when
    if not iso8601_when:
        return

    start_trigger.set_corresponding_setting(
        start_trigger.milestone, iso8601_when, student_group)


def update_end_date_from_end_override_when(end_trigger, unused_changed,
                                           unused_course, student_group):
    if not end_trigger:
        return

    iso8601_when = end_trigger.encoded_when
    if not iso8601_when:
        return

    end_trigger.set_corresponding_setting(
        end_trigger.milestone, iso8601_when, student_group)


def register_callbacks(cls, module_name):
    """Registers callbacks that update StudentGroupDTO start/end dates.

    The registered callbacks make student group specific start_date and
    end_date values available for overriding course:start_date and
    course:end_date when modify_course_environment() is called.

    Args:
        cls: typically CourseOverrideTrigger, only parameterized to avoid
            circular import dependencies with the student_groups module.
        module_name: typically student_groups.MODULE_NAME, again only
            parameterized to avoid circular import dependencies.
    """
    cls.ACT_HOOKS[constants.START_DATE_MILESTONE][
        module_name] = update_start_date_from_start_override_when
    cls.ACT_HOOKS[constants.END_DATE_MILESTONE][
        module_name] = update_end_date_from_end_override_when


def notify_module_enabled(cls, module_name):
    """Performs initialization that alters course explorer course cards.

    Args:
        cls, module_name: see register_callbacks
    """
    register_callbacks(cls, module_name)
