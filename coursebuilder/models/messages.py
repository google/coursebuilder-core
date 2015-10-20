# Copyright 2014 Google Inc. All Rights Reserved.
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

"""Messages used in the models."""

__author__ = 'Boris Roussev (borislavr@google.com)'

from common import safe_dom

DRAFT_TEXT = 'Private'
PUBLISHED_TEXT = 'Public'
PEER_MATCHER_NAME = 'Peer'

LESSON_TITLE_DESCRIPTION = """
The lesson title is displayed to students on the unit page.
"""

LESSON_PARENT_UNIT_DESCRIPTION = """
This lesson is part of this unit.
"""

LESSON_VIDEO_ID_DESCRIPTION = """
Provide a YouTube video ID to embed a video.
"""

LESSON_SCORED_DESCRIPTION = """
If this is set to "Questions are scored", the questions in this lesson will
be scored (summative). Otherwise, they will only provide textual feedback
(formative).
"""

LESSON_TEXT_VERSION_URL_DESCRIPTION = """
This is the URL to the text version of this lesson's content. If present, it is
accessed by clicking on the "Text Version" button on the lesson page. Links to
other sites must start with "http" or "https".
"""

LESSON_AUTO_NUMBER_DESCRIPTION = """
If checked, this lesson will be numbered in sequence in the list of lessons
in this unit.
"""

LESSON_ACTIVITY_TITLE_DESCRIPTION = """
This appears above your activity.
"""

LESSON_ACTIVITY_LISTED_DESCRIPTION = """
Whether the activity should be viewable as a stand-alone item in the unit index.
"""

LESSON_ACTIVITY_DESCRIPTION = safe_dom.assemble_text_message("""
Note: Activities defined in the "Activity" area are deprecated, please use the
"Lesson Body" area instead. Old-style activities are automatically
converted during "Import Course".
""", ('https://code.google.com/p/course-builder/wiki/CreateActivities'
      '#Writing_activities'))

# TODO(johncox): replace placeholder URL once target link is determined.
LESSON_ALLOW_PROGRESS_OVERRIDE_DESCRIPTION = safe_dom.assemble_text_message("""
If checked, the manual progress REST API permits users to manually mark a
unit or lesson as complete, overriding the automatic progress tracking.
""", 'https://code.google.com/p/course-builder/wiki/Dashboard')

LESSON_AVAILABILITY_DESCRIPTION = """
If this lesson is "%s", only admins can see it. If it is "%s", then anyone
who has access to the course can see it.
""" % (DRAFT_TEXT, PUBLISHED_TEXT)

QUESTION_DESCRIPTION = 'Shown when selecting questions for quizzes, etc.'

INCORRECT_ANSWER_FEEDBACK = """
Shown when the student response does not match any of the possible answers.
"""

INPUT_FIELD_HEIGHT_DESCRIPTION = """
Height of the input field, measured in rows.
"""

INPUT_FIELD_WIDTH_DESCRIPTION = """
Width of the input field, measured in columns.
"""

LINK_TITLE_DESCRIPTION = """
The link title is displayed to students on the syllabus page.
"""

LINK_DESCRIPTION_DESCRIPTION = """
The link description is displayed to students on the syllabus page.
"""

LINK_AVAILABILITY_DESCRIPTION = """
If this link is "%s", only admins can see it. If it is "%s", then
anyone who has access to the course can see it.
""" % (DRAFT_TEXT, PUBLISHED_TEXT)

LINK_SYLLABUS_VISIBILITY_DESCRIPTION = """
If this link is "%s", this controls whether or not its title is still
shown to students on the syllabus page.
""" % DRAFT_TEXT

LINK_URL_DESCRIPTION = """
This is the URL to which this link goes. Links to other sites must start
with "http" or "https".
"""

ASSESSMENT_TITLE_DESCRIPTION = """
The assessment title is displayed to students on the syllabus page.
"""

ASSESSMENT_DESCRIPTION_DESCRIPTION = """
The assessment description is displayed to students on the syllabus page.
"""

ASSESSMENT_AVAILABILITY_DESCRIPTION = """
If this assessment is "%s", only admins can see it. If it is "%s",
then anyone who has access to the course can see it.
""" % (DRAFT_TEXT, PUBLISHED_TEXT)

ASSESSMENT_SYLLABUS_VISIBILITY_DESCRIPTION = """
If this assessment is "%s", this controls whether or not its title is
still shown to students on the syllabus page.
""" % DRAFT_TEXT

ASSESSMENT_CONTENT_DESCRIPTION_TEXT = "Assessment questions and answers."

ASSESSMENT_CONTENT_DESCRIPTION = safe_dom.assemble_text_message(
    ASSESSMENT_CONTENT_DESCRIPTION_TEXT,
    'https://code.google.com/p/course-builder/wiki/CreateAssessments')

ASSESSMENT_CONTENT_JAVASCRIPT_DESCRIPTION = safe_dom.assemble_text_message(
    "%s (JavaScript format)." % ASSESSMENT_CONTENT_DESCRIPTION_TEXT,
    'https://code.google.com/p/course-builder/wiki/CreateAssessments')

ASSESSMENT_POINTS_DESCRIPTION = """
This is the number of points to assign to this assessment.
"""

ASSESSMENT_SHOW_CORRECT_ANSWER_DESCRIPTION = """
If checked, students will see "Check Answers" buttons which indicate if the
correct answer is given when pressed.
"""

ASSESSMENT_SINGLE_SUBMISSION_DESCRIPTION = """
Allow students only one opportunity to submit the answers.
"""

ASSESSMENT_DUE_DATE_FORMAT_DESCRIPTION = safe_dom.assemble_text_message("""
Should be formatted as YYYY-MM-DD hh:mm (e.g. 2013-07-16 19:20) and be specified
in the UTC timezone.""", None)


ASSESSMENT_SHOW_FEEDBACK_DESCRIPTION = """
Show students the feedback on their answers after the due date is passed.
If no due date is set, this flag has no effect.
"""

ASSESSMENT_SHOW_SCORE_DESCRIPTION = """
Show students the total score on the assignment after the due date is passed.
If no due date is set, this flag has no effect.
"""

ASSESSMENT_FAILING_TEXT = """
This text is shown to a student upon receiving a failing result.
"""

ASSESSMENT_PASSING_TEXT = """
This text is shown to a student upon receiving a passing result.
"""

HOMEPAGE_PRIVACY_URL_DESCRIPTION = """
This link to your terms of service and privacy policy is displayed in the
footer of every page. If blank, the link will be omitted. Links to other
sites must start with "http" or "https".
"""

HOMEPAGE_TITLE_DESCRIPTION = """
The course title is the name of the course.
"""

HOMEPAGE_ABSTRACT_DESCRIPTION = """
The course abstract is displayed to students on the course homepage and
should describe the course.
"""

HOMEPAGE_INSTRUCTOR_DETAILS_DESCRIPTION = """
The instructor details are displayed to students on the course homepage.
"""

HOMEPAGE_SHOW_GPLUS_BUTTON_DESCRIPTION = """
If checked, a G+ button will be displayed in the header of all pages.
"""
# TODO(johncox): replace placeholder URL once target link is determined.
ASSESSMENT_GRADING_METHOD_DESCRIPTION = safe_dom.assemble_text_message("""
If this is set to "Peer review", this assessment will use the Peer Review
module. Otherwise, it will be graded automatically.
""", 'https://code.google.com/p/course-builder/wiki/Dashboard')

ASSESSMENT_DETAILS_DESCRIPTION = safe_dom.assemble_text_message("""
Properties and restrictions of your assessment.
""", 'https://code.google.com/p/course-builder/wiki/PeerReview')

ASSESSMENT_REVIEWER_FEEDBACK_FORM_DESCRIPTION = safe_dom.assemble_text_message(
"""
Review form questions and answers (JavaScript format).
""", 'https://code.google.com/p/course-builder/wiki/PeerReview')

ASSESSMENT_REVIEWER_FEEDBACK_FORM_HTML_DESCRIPTION = """
Add the content that reviewers of a Peer Review assignment see.
"""

ASSESSMENT_REVIEW_DUE_DATE_FORMAT_DESCRIPTION = safe_dom.assemble_text_message(
"""
The review date must be later than the Submission Date.
Should be formatted as YYYY-MM-DD hh:mm (e.g. 1997-07-16 19:20) and be specified
in the UTC timezone.
""", 'https://code.google.com/p/course-builder/wiki/PeerReview')

ASSESSMENT_REVIEW_MIN_COUNT_DESCRIPTION = safe_dom.assemble_text_message(
    None, 'https://code.google.com/p/course-builder/wiki/PeerReview')

ASSESSMENT_REVIEW_TIMEOUT_IN_MINUTES = safe_dom.assemble_text_message("""
How long a reviewer has to review an assignment once the reviewer accepts the
assignment.  This value should be specified in minutes.
""", 'https://code.google.com/p/course-builder/wiki/PeerReview')

UNIT_TITLE_DESCRIPTION = """
The unit title is displayed to students on the syllabus page.
"""

UNIT_DESCRIPTION_DESCRIPTION = """
The unit description is displayed to students on the syllabus page.
"""

UNIT_AVAILABILITY_DESCRIPTION = """
If this unit is "%s", only admins can see it. If it is "%s", then
anyone who has access to the course can see it.
""" % (DRAFT_TEXT, PUBLISHED_TEXT)

UNIT_SYLLABUS_VISIBILITY_DESCRIPTION = """
If this unit is "%s", this controls whether or not its title is still
shown to students on the syllabus page.
""" % DRAFT_TEXT

UNIT_PRE_ASSESSMENT_DESCRIPTION = """
This assessment is given to students at the start of this unit.
"""

UNIT_POST_ASSESSMENT_DESCRIPTION = """
This assessment is given to students at the end of this unit.
"""

UNIT_SHOW_ON_ONE_PAGE_DESCRIPTION = """
If checked, all assessments, lessons, and activties in this unit are shown on
one page. Otherwise, each is shown on its own page.
"""

# TODO(johncox): replace placeholder URL once target link is determined.
UNIT_ALLOW_PROGRESS_OVERRIDE_DESCRIPTION = safe_dom.assemble_text_message("""
If checked, the manual progress REST API permits users to manually mark a
unit or lesson as complete, overriding the automatic progress tracking.
""", 'https://code.google.com/p/course-builder/wiki/Dashboard')

UNIT_HIDE_ASSESSMENT_NAV = """
If checked, the "Previous Page" and "Next Page" buttons will be omitted from
pre- and post-assessments within units.
"""

UNIT_HIDE_LESSON_NAV = """
If checked, the "Previous Page" and "Next Page" buttons will be omitted from
lesson and activity pages.
"""

UNIT_HIDE_UNIT_NUMBERS = """
If checked, numbers will be omitted when displaying unit titles.
"""

UNIT_SHOW_UNIT_LINK = """
If checked, unit links will be displayed in the side navigation bar.
"""

COURSE_ADMIN_EMAILS_DESCRIPTION = """
This list of email addresses represents the administrators for this course.
Separate addresses with a comma, space, or newline.
"""

# TODO(johncox): replace placeholder URL once target link is determined.
COURSE_GOOGLE_ANALYTICS_ID_DESCRIPTION = safe_dom.assemble_text_message("""
This ID is used to add Google Analytics functionality to this course.
""", 'https://code.google.com/p/course-builder/wiki/Dashboard')

# TODO(johncox): replace placeholder URL once target link is determined.
COURSE_GOOGLE_TAG_MANAGER_ID_DESCRIPTION = safe_dom.assemble_text_message("""
This ID is used to add Google Tag Manager functionality to this course.
""", 'https://code.google.com/p/course-builder/wiki/Dashboard')

UNIT_HEADER_DESCRIPTION = """
This content appears at the top of the unit page.
"""

UNIT_FOOTER_DESCRIPTION = """
This content appears at the bottom of the unit page.
"""

SHORT_ANSWER_SCORE_DESCRIPTION = """
Points a student receives for answering this question correctly. 1.0 indicates
full credit.
"""

ALLOW_LANGUAGE_SWITCHING_DESCRIPTION = """
Allow students to switch languages at any time using a menu on the bottom of
the page.
"""

BASE_LANGUAGE_DESCRIPTION = """
The language your original course content is written in.
"""

PREVENT_TRANSLATION_EDITS_DESCRIPTION = """
Enable this to boost performance if you are finished translating your course.
"""

REGISTRATION_EMAIL_BODY = """
This is the body for welcome emails. Use the string {{student_name}} to include
the name of the student and {{course_title}} to include the course title. To
avoid spamming, you should always include {{unsubscribe_url}} in your message to
add a link which the recipient can use to unsubscribe from future mailings.
"""

# TODO(johncox): replace placeholder URL once target link is determined.
REGISTRATION_EMAIL_SENDER = safe_dom.assemble_text_message("""
This is the "from" email address for welcome emails. It must be set to a valid
value for App Engine email.
""", 'https://code.google.com/p/course-builder/wiki/Dashboard')

REGISTRATION_EMAIL_SUBJECT = """
This is the subject line for welcome emails. Use the string {{student_name}} to
include the name of the student and {{course_title}} to include the course
title.
"""

REGISTRATION_INTRODUCTION = """
This introduction text is shown to students at the top of the registration page.
"""

REGISTRATION_SEND_WELCOME_EMAIL = """
If checked, welcome emails will be sent when new students register for the
course. You must also leave notifications and unsubscribe modules active (this
is the default). An email sender must also be specified.
"""

ROLES_PERMISSION_ALL_LOCALES_DESCRIPTION = """
Can pick all languages, including unavailable ones.
"""

ROLES_PERMISSION_SEE_DRAFTS_DESCRIPTION = """
Can see lessons and assessments with draft status.
"""
