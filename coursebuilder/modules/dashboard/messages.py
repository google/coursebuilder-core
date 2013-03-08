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

from modules.admin import messages as admin_messages


ABOUT_THE_COURSE_DESCRIPTION = """
This information is configured by an administrator from the Admin pages.
"""

ASSESSMENT_EDITOR_DESCRIPTION = admin_messages.format_msg(
    None, 'https://code.google.com/p/course-builder/wiki/CreateAssessments')

ASSETS_DESCRIPTION = """
These are all the assets for your course. You can upload new images and
documents here, after which you can use them in your lessons and activities.
You may create, edit, and delete activities and assessments from the Outline
page. All other assets must be edited by an administrator.
"""

CONTENTS_OF_THE_COURSE_DESCRIPTION = admin_messages.format_msg("""
The course.yaml file contains many course settings.  Edit it using the button at
right.
""", 'https://code.google.com/p/course-builder/wiki/CourseSettings')

COURSE_OUTLINE_DESCRIPTION = admin_messages.format_msg("""
Build, organize and preview your course here.
""", 'https://code.google.com/p/course-builder/wiki/Dashboard#Outline')

COURSE_OUTLINE_EDITOR_DESCRIPTION = """
Click up/down arrows to re-order units, or lessons within units.  To move a
lesson between units, edit that lesson from the outline page and change its
parent unit.
"""

DATA_FILES_DESCRIPTION = admin_messages.format_msg("""
The lesson.csv file contains the contents of your lesson. The unit.csv file
contains the course related content shown on the homepage. These files are
located in your Course Builder installation. Edit them directly with an editor
like Notepad++. Be careful, some editors will add extra characters, which may
prevent the uploading of these files.
""", 'https://code.google.com/p/course-builder/wiki/Dashboard#Outline')

EDIT_SETTINGS_DESCRIPTION = admin_messages.format_msg("""
The course.yaml file contains many course settings.
""", 'https://code.google.com/p/course-builder/wiki/CourseSettings')

IMPORT_COURSE_DESCRIPTION = admin_messages.format_msg("""
Import the contents of another course into this course. Both courses must be on
the same Google App Engine instance.
<strong>This will only import into an empty course</strong>.
""", None)

LESSON_ACTIVITY_DESCRIPTION = """
Create an activity by entering the correct syntax above.
"""

LESSON_ACTIVITY_TITLE_DESCRIPTION = """
This appears above your activity.
"""

LESSON_OBJECTIVES_DESCRIPTION = """
Objectives are displayed to students under the video in the default template.
"""

LESSON_VIDEO_ID_DESCRIPTION = """
Provide a YouTube video ID to embed a video.
"""

LESSON_NOTES_DESCRIPTION = """
Notes are displayed under the objects in the default template.
"""

LINK_EDITOR_DESCRIPTION = """
Links will appear in your outline and will take students directly to the URL.
"""

LINK_EDITOR_URL_DESCRIPTION = """
Links to external sites must start with 'http' or https'.
"""

PAGES_DESCRIPTION = admin_messages.format_msg(
    None, 'https://code.google.com/p/course-builder/wiki/Dashboard#Outline')

SETTINGS_DESCRIPTION = admin_messages.format_msg(
    None, 'https://code.google.com/p/course-builder/wiki/Dashboard#Settings')

UNIT_EDITOR_DESCRIPTION = admin_messages.format_msg("""
Units contain lessons and acitivities.
""", 'https://code.google.com/p/course-builder/wiki/Dashboard#Outline')

UPLOAD_ASSET_DESCRIPTION = admin_messages.format_msg("""
Choose a file to upload to this Google App Engine instance. Learn more about
file storage and hosting.
""", 'https://code.google.com/p/course-builder/wiki/Dashboard#Assets')
