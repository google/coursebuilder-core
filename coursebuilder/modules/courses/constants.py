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

"""Common constants for courses module.  Kept here to avoid inclusion cycles."""

__author__ = 'Mike Gainer (mgainer@google.com)'


MODULE_NAME = 'Course'

# Name of permission allowing admin to modify order of course outline (but not
# add/delete units/assessments/links)
COURSE_OUTLINE_REORDER_PERMISSION = 'course_outline_reorder'

# Name for the permission for read-only access to all course settings.
VIEW_ALL_SETTINGS_PERMISSION = 'settings_viewer'

# Name of permission allowing modification of course, unit, lesson
# availability, visibility.  Also governs access to course whitelist.
MODIFY_AVAILABILITY_PERMISSION = 'modify_availability'

# Perm. to allow editing a few permissions in course, unit/lesson/assessment
# scopes suitable to adjusting a small run or re-run of a course to fix up
# dates, course order, and grading options.
TEACHING_ASSISTANT_PERMISSION = 'teaching_assistant'
TEACHING_ASSISTANT_ROLE_NAME = 'Teaching Assistant'
TEACHING_ASSISTANT_ROLE_PERMISSIONS = [
    TEACHING_ASSISTANT_PERMISSION,
    COURSE_OUTLINE_REORDER_PERMISSION,
]

# Permssions scope name for permissions relating to course settings
SCOPE_COURSE_SETTINGS = 'course_settings'

# Permissions scope for schema restrictions on Unit/Assessment/Link
SCOPE_UNIT = 'unit'
SCOPE_ASSESSMENT = 'assessment'
SCOPE_LINK = 'link'

# Names of Course settings (obtained via the get_course_setting() method or
# the get_named_course_setting_from_environ() classmethod) containing the
# course start and end datetime, as a UTC ISO-8601 encoded string.
#
# NOTE: Python "snake-cased" names like these, when used with GraphQL in
# Javascript, are automatically converted to camel case. For example:
#   Course.get_environ(app_context)['course']['end_date']
# is referred to as:
#   course.endDate
# in the Javascript code.
START_DATE_SETTING = 'start_date'
END_DATE_SETTING = 'end_date'

# These milestone strings are converted from Python "snake-case" into
# separate words, title case (e.g. "Course Start"), etc., and used in the
# UI in various places, so changing them will have user-visible impact.
START_DATE_MILESTONE = 'course_start'
END_DATE_MILESTONE = 'course_end'

# The 'course' dict settings names are different from the milestone strings
# above because changing, for example, start_date to course_start results
# in harder to read code elsewhere (e.g. course.courseStart instead of
# course.startDate in the Javascript code). So, a mapping from one to the
# other ends up being necessary.
MILESTONE_TO_SETTING = {
    START_DATE_MILESTONE: START_DATE_SETTING,
    END_DATE_MILESTONE: END_DATE_SETTING,
}
MILESTONE_TO_TITLE = {
    START_DATE_MILESTONE: 'Start',
    END_DATE_MILESTONE: 'End',
}
SETTING_TO_MILESTONE = {s: m for m, s in MILESTONE_TO_SETTING.iteritems()}

# MILESTONE_TO_SETTING.keys() is not simply used here because the order
# of "Course Start" and "Course End" matter when they appear in the UI.
COURSE_MILESTONES = [
    START_DATE_MILESTONE,
    END_DATE_MILESTONE,
]
