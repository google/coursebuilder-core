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
