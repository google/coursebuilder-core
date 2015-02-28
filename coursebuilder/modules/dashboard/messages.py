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


ABOUT_THE_COURSE_DESCRIPTION = safe_dom.assemble_text_message("""
This information is configured by an administrator from the Admin pages.
""", None)

ADMIN_PREFERENCES_DESCRIPTION = safe_dom.assemble_text_message("""
Preferences settings for individual course admins.
""", None)

ADMINISTERED_COURSES_DESCRIPTION = safe_dom.assemble_text_message("""
Courses for which you have administrator privileges
""", None)

ASSESSMENT_EDITOR_DESCRIPTION = safe_dom.assemble_text_message(
    None, 'https://code.google.com/p/course-builder/wiki/CreateAssessments')

ASSETS_DESCRIPTION = safe_dom.assemble_text_message("""
These are all the assets for your course. You can upload new images and
documents here, after which you can use them in your lessons and activities.
You may create, edit, and delete activities and assessments from the Outline
page. All other assets must be edited by an administrator.
""", None)

ASSIGNMENTS_MENU_DESCRIPTION = safe_dom.assemble_text_message("""
Select a peer-reviewed assignment and enter a student's email address to view
their assignment submission and any associated reviews.
""", None)

CONTENTS_OF_THE_COURSE_DESCRIPTION = safe_dom.assemble_text_message("""
The course.yaml file contains all course-level settings.  It can be
modified from other settings sub-tabs, or directly edited in its
raw form here.
""", 'https://code.google.com/p/course-builder/wiki/CourseSettings')

COURSE_ADMIN_DESCRIPTION = safe_dom.assemble_text_message("""
Admin settings for users who are course authors but not
site administrators.
""", None)

COURSE_OUTLINE_DESCRIPTION = safe_dom.assemble_text_message(
    'Build, organize and preview your course here.',
    'https://code.google.com/p/course-builder/wiki/Dashboard#Outline')

COURSE_OUTLINE_EDITOR_DESCRIPTION = safe_dom.assemble_text_message("""
Click up/down arrows to re-order units, or lessons within units.  To move a
lesson between units, edit that lesson from the outline page and change its
parent unit.
""", None)

COURSE_TEMPLATE_DESCRIPTION = safe_dom.assemble_text_message("""
The course_template.yaml file provides default values for course settings.
These values are not dynamically editable, but you can override them
by editing your course.yaml file directly, or by changing settings in
the other Settings sub-tabs.

You can also change the default settings for all courses by editing
the course_template.yaml file on disk and re-pushing CourseBuilder to
AppEngine.  Changing the defaults in the file will not erase or
override any course-specific settings you may have made.
""", None)

DATA_FILES_DESCRIPTION = safe_dom.assemble_text_message("""
The lesson.csv file contains the contents of your lesson. The unit.csv file
contains the course related content shown on the homepage. These files are
located in your Course Builder installation. Edit them directly with an editor
like Notepad++. Be careful, some editors will add extra characters, which may
prevent the uploading of these files.
""", 'https://code.google.com/p/course-builder/wiki/Dashboard#Outline')

EDIT_SETTINGS_DESCRIPTION = safe_dom.assemble_text_message("""
The course.yaml file contains many course settings.
""", 'https://code.google.com/p/course-builder/wiki/CourseSettings')

EDIT_HTML_HOOK_DESCRIPTION = safe_dom.assemble_text_message("""
HTML hooks are snippets of HTML code that are inserted at different points on
the pages of a course.  Editing these snippets here permits you to make
global changes to these items.
""", 'https://code.google.com/p/course-builder/wiki/Dashboard#Outline')

IMPORT_COURSE_DESCRIPTION = safe_dom.assemble_text_message("""
Import the contents of another course into this course. Both courses must be on
the same Google App Engine instance.
""", None)

LINK_EDITOR_DESCRIPTION = safe_dom.assemble_text_message("""
Links will appear in your outline and will take students directly to the URL.
""", None)

PAGES_DESCRIPTION = safe_dom.assemble_text_message(
    None, 'https://code.google.com/p/course-builder/wiki/Dashboard#Outline')

ROLES_DESCRIPTION = """
Manage the different roles associated with your course.
A role binds a set of permissions to a set of users. The role editor allows you
to assign any of the permissions currently registered by the enabled modules.
"""

SETTINGS_DESCRIPTION = safe_dom.assemble_text_message(
    None, 'https://code.google.com/p/course-builder/wiki/Dashboard#Settings')

UNIT_EDITOR_DESCRIPTION = safe_dom.assemble_text_message("""
Units contain lessons and acitivities.
""", 'https://code.google.com/p/course-builder/wiki/Dashboard#Outline')

UPLOAD_ASSET_DESCRIPTION = safe_dom.assemble_text_message("""
Choose a file to upload to this Google App Engine instance. Learn more about
file storage and hosting.
""", 'https://code.google.com/p/course-builder/wiki/Dashboard#Assets')
