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

"""Messages used in the Guide module."""

__author__ = [
    'davyrisso@google.com (Davy Risso)',
]


MODULE_DESCRIPTION = """
Guide: A new learning experience module. An alternative to the default course
explorer and course experience.
"""

SITE_SETTINGS_GUIDE = """
If True, Guide will be accessible at /modules/guide.
"""

COURSE_SETTINGS_COLOR_DESCRIPTION = """
The color scheme for this course\'s guide. Must be expressed as a web color name
or hex triplet beginning with a "#".
If blank, Material Cyan 500 (#00bcd4) will be used.
"""

COURSE_SETTINGS_ENABLED_DESCRIPTION = """
If checked, this course will be included in the guides experience accessible at
/modules/guide. Course must not be Private.
"""

COURSE_SETTINGS_LESSON_DURATION_DESCRIPTION = """
Specify the average length of each lesson in the course in minutes and it will
be used to estimate the duration of each guide.
If blank or set to 0, duration will not be shown.
"""

