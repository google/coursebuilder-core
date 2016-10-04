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

"""Messages used in the course_explorer module."""

__author__ = [
    'johncox@google.com (John Cox)',
]


SITE_SETTINGS_COURSE_EXPLORER = """
If "True", the root directory ("/" after the hostname) redirects to the course
explorer page. Otherwise, it redirects to the preview page for the default
course.
"""

COURSE_ESTIMATED_WORKLOAD_DESCRIPTION = """
This is displayed on the course explorer page and can be an indication of
the length of the course (e.g., 10 hours).
"""

COURSE_CATEGORY_DESCRIPTION = """
Students may filter courses by category on the course explorer page
(e.g., Biology).
"""

SITE_LOGO_DESCRIPTION = """
This logo is displayed in the upper left corner of the Course Explorer and
every page of all courses.
"""

COURSE_INCLUDE_IN_EXPLORER_DESCRIPTION = """
When checked, the course is eligible to be included in the Course Explorer,
subject to the course's availability settings.  When unchecked, the course
is never shown in the Course Explorer, regardless of availability.
"""

EXTRA_CONTENT_DESCRIPTION = """
This HTML content is displayed at the top of the course explorer page.
"""
