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

"""Course and course content ("element") availability options."""

__author__ = 'Todd Larsen (tlarsen@google.com)'

from models import courses


def option_to_text(option):
    """Converts, for example, 'no_override' to 'no override'."""
    return option.replace('_', ' ')


def option_to_title(option):
    """Converts, for example, 'no_override' to 'No Override'."""
    return option_to_text(option).title()


def option_to_css(option):
    """Returns, for example, 'no_override' as 'no-override'."""
    return option_to_text(option).replace(' ', '-')


# Each valid <option> to <select> availability of course content items on
# the "Publish > Availability" page, in the "Element Settings" and
# "Change Course Content Availability at Date/Time" sections of that form
# (currently 'public', 'private', and 'course').
ELEMENT_SELECT_DATA = courses.AVAILABILITY_SELECT_DATA

# Just the values of each SELECT_DATA <option>, not the "title" text.
ELEMENT_VALUES = courses.AVAILABILITY_VALUES
ELEMENT_DEFAULT = courses.AVAILABILITY_UNAVAILABLE

# Each valid <option> to <select> overall availability of an entire course
# on the "Publish > Availability" page, in the "Course Availability" field
# on that form (currently 'public', 'private', 'registration_required',
# and 'registration_optional').
COURSE_SELECT_DATA = courses.COURSE_AVAILABILITY_SELECT_DATA

# Just the values of each SELECT_DATA <option>, not the "title" text.
COURSE_VALUES = courses.COURSE_AVAILABILITY_VALUES
COURSE_DEFAULT = courses.COURSE_AVAILABILITY_PRIVATE

AVAILABILITY_NONE_SELECTED = 'none'
NONE_SELECTED_TITLE = '--- change availability to ---'
NONE_SELECTED_OPTION = (AVAILABILITY_NONE_SELECTED, NONE_SELECTED_TITLE)

# Adds a '--- change availability to ---' choice to the existing "Course
# Availability" options on the "Publish > Availability" page (currently
# 'private', 'registration_required', 'registration_optional', and 'public').
COURSE_WITH_NONE_SELECT_DATA = [
    NONE_SELECTED_OPTION,
] + COURSE_SELECT_DATA
