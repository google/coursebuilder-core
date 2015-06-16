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

"""Messages used in the dashboard."""

__author__ = 'Mike Gainer (mgainer@google.com)'

from common import safe_dom


ABOUT_THE_COURSE_DESCRIPTION = safe_dom.assemble_text_message("""
This information is configured by an administrator from the Admin pages.
""", None)

DATA_FILES_DESCRIPTION = safe_dom.assemble_text_message("""
The lesson.csv file contains the contents of your lesson. The unit.csv file
contains the course related content shown on the homepage. These files are
located in your Course Builder installation. Edit them directly with an editor
like Notepad++. Be careful, some editors will add extra characters, which may
prevent the uploading of these files.
""", 'https://code.google.com/p/course-builder/wiki/Dashboard#Outline')

CONTENTS_OF_THE_COURSE_DESCRIPTION = safe_dom.assemble_text_message("""
The course.yaml file contains all course-level settings.  It can be
modified from other settings sub-tabs, or directly edited in its
raw form here.
""", 'https://code.google.com/p/course-builder/wiki/CourseSettings')

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

SETTINGS_DESCRIPTION = safe_dom.assemble_text_message(
    None, 'https://code.google.com/p/course-builder/wiki/Dashboard#Settings')
