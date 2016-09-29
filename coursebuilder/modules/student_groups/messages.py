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

"""Static text messages relating to student groups."""

from common import safe_dom


__author__ = 'Mike Gainer (mgainer@google.com)'


STUDENT_GROUPS_DESCRIPTION = safe_dom.NodeList(
    ).append(safe_dom.Element('p').add_text(
        """Manage groups of students. Group level settings can override
course level settings, and apply only to students in that
group. Events recorded for students are marked with their current
group. Certain analytics can be filtered to show only results relating
to individual groups.""")
    ).append(safe_dom.Element('span').add_text(
        """This page allows you to create your student groups. You can then
        manage membership and content access on the
        """)
    ).append(safe_dom.assemble_link(
        'dashboard?action=availability', 'availability page'))

GROUP_MEMBERS_DESCRIPTION = """
The email addresses of students in this group.
Student emails may be assigned to groups before they are registered for the
course.  Separate email addresses with any combination of commas, spaces,
tabs or newlines.
Each student may only be in one group.
"""

EDIT_STUDENT_GROUPS_PERMISSION_DESCRIPTION = """
Allows creation, deletion, and modification of membership in groups of students.
Other permissions may be required to configure group-level settings to
override course-level settings -- e.g., to modify course/unit/lesson
availability.
"""

STUDENT_GROUP_ID_DESCRIPTION = """
Numeric ID of the group to which the student belongs, or null if the student
has not been assigned to any group.  This can be used directly for
grouping/aggregating data.
"""

STUDENT_GROUP_NAME_DESCRIPTION = """
Name of the group to which the student has been assigned, or null.  Note that
since student groups can be given the same name, you should not rely on this
field for aggregation, unless you are sure that no groups share a name.
"""

AVAILABILITY_DEFAULT_AVAILABILITY_DESCRIPTION = """
This is the current availability setting for this item at the course level.
"""

AVAILABILITY_OVERRIDDEN_AVAILABILITY_DESCRIPTION = """
Availability of course items can be overridden for students in this group,
or can default to using whatever the course-level setting is.
"""

GROUP_COURSE_AVAILABILITY = """
This sets the availability of the course for registered and unregistered
students in this group.
"""

ENABLE_GROUP_CACHING = """
If 'True', student groups are cached, with a one-hour refresh rate.
If you plan to change multiple student groups, or you otherwise need
your student group changes to take effect rapidly, this can be set to
'False'.  Otherwise, keep this setting at 'True' to maximize performance.
"""

AVAILABILITY_FOR_PICKER_MESSAGE = (
'Availability can be set for the course as a whole and overridden for '
) + str(safe_dom.assemble_link(
  "dashboard?action=edit_student_groups", "specific groups of students."))

MILESTONE_TRIGGER_DESC_FMT = """
This is the course {milestone} date used in the course explorer.

If you specify an availability in the dropdown, the course will be
scheduled to update to that availability at this date and hour (UTC).

To cancel the scheduled update, click the "Clear" button and select the
first option in the dropdown.

This only impacts students who are members of the currently selected group.
"""

CONTENT_TRIGGERS_DESCRIPTION = """
Changes to availability that are triggered at a specified date and time for
students in this group.
"""

CONTENT_TRIGGER_RESOURCE_DESCRIPTION = """
The course content, such as unit or lesson, for which to change the
availability for students in this group.
"""

CONTENT_TRIGGER_WHEN_DESCRIPTION = """
The date and hour (UTC) when the availability of the resource will be changed
for students in this group.
"""

CONTENT_TRIGGER_AVAIL_DESCRIPTION = """
The availability of the course resource will change to this value after the
trigger date and time for students in this group.
"""
