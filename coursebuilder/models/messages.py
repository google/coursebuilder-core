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


PEER_MATCHER_NAME = 'Peer'

ASSESSMENT_CONTENT_DESCRIPTION = safe_dom.assemble_text_message("""
Assessment questions and answers (JavaScript format).
""", 'https://code.google.com/p/course-builder/wiki/CreateAssessments')

ASSESSMENT_DETAILS_DESCRIPTION = safe_dom.assemble_text_message("""
Properties and restrictions of your assessment.
""", 'https://code.google.com/p/course-builder/wiki/PeerReview')

DUE_DATE_FORMAT_DESCRIPTION = safe_dom.assemble_text_message("""
Should be formatted as YYYY-MM-DD hh:mm (e.g. 1997-07-16 19:20) and be specified
in the UTC timezone.""", None)

REVIEWER_FEEDBACK_FORM_DESCRIPTION = safe_dom.assemble_text_message("""
Review form questions and answers (JavaScript format).
""", 'https://code.google.com/p/course-builder/wiki/PeerReview')

REVIEWER_FEEDBACK_FORM_HTML_DESCRIPTION = """
Add the content that reviewers of a Peer Review assignment see.
"""

REVIEW_DUE_DATE_FORMAT_DESCRIPTION = safe_dom.assemble_text_message("""
The review date must be later than the Submission Date.
Should be formatted as YYYY-MM-DD hh:mm (e.g. 1997-07-16 19:20) and be specified
in the UTC timezone.
""", 'https://code.google.com/p/course-builder/wiki/PeerReview')

REVIEW_MIN_COUNT_DESCRIPTION = safe_dom.assemble_text_message(
    None, 'https://code.google.com/p/course-builder/wiki/PeerReview')

REVIEW_TIMEOUT_IN_MINUTES = safe_dom.assemble_text_message("""
How long a reviewer has to review an assignment once the reviewer accepts the
assignment.  This value should be specified in minutes.
""", 'https://code.google.com/p/course-builder/wiki/PeerReview')

LESSON_VIDEO_ID_DESCRIPTION = """
Provide a YouTube video ID to embed a video.
"""

LESSON_SCORED_DESCRIPTION = """
Whether questions in this lesson will be scored (summative) or only
provide textual feedback (formative).
"""

LESSON_OBJECTIVES_DESCRIPTION = """
The lesson body is displayed to students above the video in the default
template.
"""

LESSON_NOTES_DESCRIPTION = """
Provide a URL that points to the notes for this lesson (if applicable). These
notes can be accessed by clicking on the 'Text Version' button on the lesson
page.
"""

LESSON_AUTO_INDEX_DESCRIPTION = """
Assign a sequential number to this lesson automatically.
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

LESSON_MANUAL_PROGRESS_DESCRIPTION = """
When set, the manual progress REST API permits
users to manually mark a unit or lesson as complete,
overriding the automatic progress tracking.
"""

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

LINK_EDITOR_URL_DESCRIPTION = """
Links to external sites must start with 'http' or https'.
"""

ASSESSMENT_WEIGHT_DESCRIPTION = """
Specify how many points to assign to this assessment.
"""

CHECK_ANSWERS_DESCRIPTION = """
Choose whether your students can get feedback on whether the answer is correct.
"""

UNIT_DESCRIPTION_DESCRIPTION = """
Students see this description on the syllabus page.
"""

SHORT_ANSWER_SCORE_DESCRIPTION = """
Points a student receives for answering this question correctly. 1.0 indicates
full credit.
"""
