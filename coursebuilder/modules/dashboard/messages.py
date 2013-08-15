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


def assemble_sanitized_message(text, link):
    node_list = safe_dom.NodeList()
    if text:
        node_list.append(safe_dom.Text(text))
        node_list.append(safe_dom.Entity('&nbsp;'))
    if link:
        node_list.append(safe_dom.Element(
            'a', href=link, target='_blank').add_text('Learn more...'))
    return node_list


ABOUT_THE_COURSE_DESCRIPTION = assemble_sanitized_message("""
This information is configured by an administrator from the Admin pages.
""", None)

ASSESSMENT_CONTENT_DESCRIPTION = assemble_sanitized_message("""
Assessment questions and answers (JavaScript format).
""", 'https://code.google.com/p/course-builder/wiki/CreateAssessments')

ASSESSMENT_DETAILS_DESCRIPTION = assemble_sanitized_message("""
Properties and restrictions of your assessment.
""", 'https://code.google.com/p/course-builder/wiki/PeerReview')

ASSESSMENT_EDITOR_DESCRIPTION = assemble_sanitized_message(
    None, 'https://code.google.com/p/course-builder/wiki/CreateAssessments')

ASSETS_DESCRIPTION = assemble_sanitized_message("""
These are all the assets for your course. You can upload new images and
documents here, after which you can use them in your lessons and activities.
You may create, edit, and delete activities and assessments from the Outline
page. All other assets must be edited by an administrator.
""", None)

ASSIGNMENTS_MENU_DESCRIPTION = assemble_sanitized_message("""
Select a peer-reviewed assignment and enter a student's email address to view
their assignment submission and any associated reviews.
""", None)

CONTENTS_OF_THE_COURSE_DESCRIPTION = assemble_sanitized_message("""
The course.yaml file contains many course settings.  Edit it using the buttons
at the right.
""", 'https://code.google.com/p/course-builder/wiki/CourseSettings')

COURSE_OUTLINE_DESCRIPTION = assemble_sanitized_message(
    'Build, organize and preview your course here.',
    'https://code.google.com/p/course-builder/wiki/Dashboard#Outline')

COURSE_OUTLINE_EDITOR_DESCRIPTION = assemble_sanitized_message("""
Click up/down arrows to re-order units, or lessons within units.  To move a
lesson between units, edit that lesson from the outline page and change its
parent unit.
""", None)

COURSE_TEMPLATE_DESCRIPTION = assemble_sanitized_message("""
The course_template.yaml file contains the common template settings
for all courses. You can override the template settings for this
course by editing your course.yaml file.
""", None)

DATA_FILES_DESCRIPTION = assemble_sanitized_message("""
The lesson.csv file contains the contents of your lesson. The unit.csv file
contains the course related content shown on the homepage. These files are
located in your Course Builder installation. Edit them directly with an editor
like Notepad++. Be careful, some editors will add extra characters, which may
prevent the uploading of these files.
""", 'https://code.google.com/p/course-builder/wiki/Dashboard#Outline')

EDIT_SETTINGS_DESCRIPTION = assemble_sanitized_message("""
The course.yaml file contains many course settings.
""", 'https://code.google.com/p/course-builder/wiki/CourseSettings')

IMPORT_COURSE_DESCRIPTION = assemble_sanitized_message("""
Import the contents of another course into this course. Both courses must be on
the same Google App Engine instance.
""", None)

INCORRECT_ANSWER_FEEDBACK = """
Shown when the student response does not match any of the possible answers.
"""

INPUT_FIELD_HEIGHT_DESCRIPTION = """
Height of the input field, measured in rows.
"""

INPUT_FIELD_WIDTH_DESCRIPTION = """
Width of the input field, measured in columns.
"""

LESSON_ACTIVITY_DESCRIPTION = assemble_sanitized_message("""
Create an activity by entering the correct syntax above.
""", ('https://code.google.com/p/course-builder/wiki/CreateActivities'
      '#Writing_activities'))

LESSON_ACTIVITY_LISTED_DESCRIPTION = """
Whether the activity should be viewable as a stand-alone item in the unit index.
"""

LESSON_ACTIVITY_TITLE_DESCRIPTION = """
This appears above your activity.
"""

LESSON_OBJECTIVES_DESCRIPTION = """
The lesson body is displayed to students above the video in the default
template.
"""

LESSON_SCORED_DESCRIPTION = """
Whether questions in this lesson will be scored (summative) or only
provide textual feedback (formative).
"""

LESSON_VIDEO_ID_DESCRIPTION = """
Provide a YouTube video ID to embed a video.
"""

LESSON_NOTES_DESCRIPTION = """
Provide a URL that points to the notes for this lesson (if applicable). These
notes can be accessed by clicking on the 'Text Version' button on the lesson
page.
"""

LINK_EDITOR_DESCRIPTION = assemble_sanitized_message("""
Links will appear in your outline and will take students directly to the URL.
""", None)

LINK_EDITOR_URL_DESCRIPTION = """
Links to external sites must start with 'http' or https'.
"""

PAGES_DESCRIPTION = assemble_sanitized_message(
    None, 'https://code.google.com/p/course-builder/wiki/Dashboard#Outline')

QUESTION_DESCRIPTION = 'Shown when selecting questions for quizzes, etc.'

REVIEWER_FEEDBACK_FORM_DESCRIPTION = assemble_sanitized_message("""
Review form questions and answers (JavaScript format).
""", 'https://code.google.com/p/course-builder/wiki/PeerReview')

SETTINGS_DESCRIPTION = assemble_sanitized_message(
    None, 'https://code.google.com/p/course-builder/wiki/Dashboard#Settings')

UNIT_EDITOR_DESCRIPTION = assemble_sanitized_message("""
Units contain lessons and acitivities.
""", 'https://code.google.com/p/course-builder/wiki/Dashboard#Outline')

UPLOAD_ASSET_DESCRIPTION = assemble_sanitized_message("""
Choose a file to upload to this Google App Engine instance. Learn more about
file storage and hosting.
""", 'https://code.google.com/p/course-builder/wiki/Dashboard#Assets')

DUE_DATE_FORMAT_DESCRIPTION = assemble_sanitized_message("""
Should be formatted as YYYY-MM-DD hh:mm (e.g. 1997-07-16 19:20) and be specified
in the UTC timezone.""", None)

REVIEW_DUE_DATE_FORMAT_DESCRIPTION = assemble_sanitized_message("""
Should be formatted as YYYY-MM-DD hh:mm (e.g. 1997-07-16 19:20) and be specified
in the UTC timezone.
""", 'https://code.google.com/p/course-builder/wiki/PeerReview')

REVIEW_TIMEOUT_IN_MINUTES = assemble_sanitized_message("""
This value should be specified in minutes.
""", 'https://code.google.com/p/course-builder/wiki/PeerReview')

REVIEW_MIN_COUNT_DESCRIPTION = assemble_sanitized_message(
    None, 'https://code.google.com/p/course-builder/wiki/PeerReview')

AUTO_GRADER_NAME = 'Automatic Grading'

HUMAN_GRADER_NAME = 'Peer Review'

PEER_MATCHER_NAME = 'Peer'
