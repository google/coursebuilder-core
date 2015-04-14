# Copyright 2013 Google Inc. All Rights Reserved.
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

"""Messages used in the dashboard."""

__author__ = 'John Orr (jorr@google.com)'

from common import safe_dom


ASSESSMENT_EDITOR_DESCRIPTION = safe_dom.assemble_text_message(
    None, 'https://code.google.com/p/course-builder/wiki/CreateAssessments')

COURSE_ADMIN_DESCRIPTION = safe_dom.assemble_text_message("""
Admin settings for users who are course authors but not
site administrators.
""", None)

EDIT_SETTINGS_DESCRIPTION = safe_dom.assemble_text_message("""
The course.yaml file contains many course settings.
""", 'https://code.google.com/p/course-builder/wiki/CourseSettings')

IMPORT_COURSE_DESCRIPTION = safe_dom.assemble_text_message("""
Import the contents of another course into this course. Both courses must be on
the same Google App Engine instance.
""", None)

LINK_EDITOR_DESCRIPTION = safe_dom.assemble_text_message("""
Links will appear in your outline and will take students directly to the URL.
""", None)

ROLES_DESCRIPTION = """
Manage the different roles associated with your course.
A role binds a set of permissions to a set of users. The role editor allows you
to assign any of the permissions currently registered by the enabled modules.
"""

UNIT_EDITOR_DESCRIPTION = safe_dom.assemble_text_message("""
Units contain lessons and acitivities.
""", 'https://code.google.com/p/course-builder/wiki/Dashboard#Outline')

UPLOAD_ASSET_DESCRIPTION = safe_dom.assemble_text_message("""
Choose a file to upload to this Google App Engine instance. Learn more about
file storage and hosting.
""", 'https://code.google.com/p/course-builder/wiki/Dashboard#Assets')
