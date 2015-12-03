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

LESSON_ACTIVITY_DESCRIPTION = """
Note: Activities defined in the "Activity" area are deprecated, please use the
"Lesson Body" area instead. Old-style activities are automatically
converted during "Import Course".
"""

LESSON_ALLOW_PROGRESS_OVERRIDE_DESCRIPTION = """
If checked, the manual progress REST API permits users to manually mark a
unit or lesson as complete, overriding the automatic progress tracking.
"""

LESSON_AVAILABILITY_DESCRIPTION = """
If this lesson is "%s", only admins can see it. If it is "%s", then anyone
who has access to the course can see it.
""" % (DRAFT_TEXT, PUBLISHED_TEXT)

QUESTION_DESCRIPTION = 'This is the description of this question.'

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

ASSESSMENT_CONTENT_DESCRIPTION = "Assessment questions and answers."

ASSESSMENT_CONTENT_JAVASCRIPT_DESCRIPTION = (
    "%s (JavaScript format)." % ASSESSMENT_CONTENT_DESCRIPTION)

ASSESSMENT_POINTS_DESCRIPTION = """
This is the number of points to assign to this assessment.
"""

ASSESSMENT_SHOW_CORRECT_ANSWER_DESCRIPTION = """
If checked, students will see "Check Answers" buttons which indicate if the
correct answer is given when pressed.
"""

ASSESSMENT_SINGLE_SUBMISSION_DESCRIPTION = """
If checked, students may only submit their answers once.
"""

ASSESSMENT_DUE_DATE_FORMAT_DESCRIPTION = """
If specified, students will not be able to submit answers after this date.
"""

ASSESSMENT_SHOW_FEEDBACK_DESCRIPTION = """Show students their total score and
the feedback for their answers after the due date is passed.  If no due date is
set, this has no effect.
"""

ASSESSMENT_FAILING_TEXT = """
This text is shown to a student upon receiving a failing result on the final
assessment. Use "%s%%" to insert the student's score.
"""

ASSESSMENT_PASSING_TEXT = """
This text is shown to a student upon receiving a passing result on the final
assessment. Use "%s%%" to insert the student's score.
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

ASSESSMENT_GRADING_METHOD_DESCRIPTION = """
If this is set to "Peer review", this assessment will use the Peer Review
module. Otherwise, it will be graded automatically.
"""

ASSESSMENT_DETAILS_DESCRIPTION = """
Properties and restrictions of your assessment.
"""

ASSESSMENT_REVIEWER_FEEDBACK_FORM_DESCRIPTION = """
Review form questions and answers (JavaScript format).
"""

ASSESSMENT_REVIEWER_FEEDBACK_FORM_HTML_DESCRIPTION = """
Add the content that reviewers of a Peer Review assignment see.
"""

ASSESSMENT_REVIEW_DUE_DATE_FORMAT_DESCRIPTION = """
Reviews must be completed by this date. Must be after the actual assessment due
date.
"""

ASSESSMENT_REVIEW_MIN_COUNT_DESCRIPTION = """
This is the minimum number of reviews a student must complete to get credit for
the assessment.
"""

ASSESSMENT_REVIEW_TIMEOUT_IN_MINUTES = """
How long a reviewer has to review an assignment once the reviewer accepts the
assignment.  This value should be specified in minutes.
"""

UNIT_TITLE_DESCRIPTION = """
The unit title is displayed to students on the syllabus page.
"""

UNIT_DESCRIPTION_DESCRIPTION = """
The unit description is displayed to students on the syllabus page.
"""

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

UNIT_ALLOW_PROGRESS_OVERRIDE_DESCRIPTION = """
If checked, the manual progress REST API permits users to manually mark a
unit or lesson as complete, overriding the automatic progress tracking.
"""

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

COURSE_GOOGLE_ANALYTICS_ID_DESCRIPTION = """
This ID is used to add Google Analytics functionality to this course.
"""

COURSE_GOOGLE_TAG_MANAGER_ID_DESCRIPTION = """
This ID is used to add Google Tag Manager functionality to this course.
"""

COURSE_GOOGLE_API_KEY_DESCRIPTION = """
The Google API Key is required to enable certain functionality.
"""

COURSE_GOOGLE_CLIENT_ID_DESCRIPTION = """
The Google Client ID is required to enable certain functionality.
"""

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

SHORT_ANSWER_TYPE_DESCRIPTION = """
This indicates the type of answer.
"""

SHORT_ANSWER_ANSWER_DESCRIPTION = """
The correct answer for this question.
"""

SHORT_ANSWER_FEEDBACK_DESCRIPTION = """
Shown when the student response does not match any of the possible answers.
"""

SHORT_ANSWER_DESCRIPTION_DESCRIPTION = """
This is the description of this question.
"""

SHORT_ANSWER_HINT_DESCRIPTION = """
This provides a hint to the answer.
"""

MULTIPLE_CHOICE_FEEDBACK_DESCRIPTION = """
This provides feedback to the student for this entire question.
"""

MULTIPLE_CHOICE_CHOICE_FEEDBACK_DESCRIPTION = """
This text provides feedback to the student for this particular answer choice.
"""

MULTIPLE_CHOICE_RANDOMIZE_CHOICES_DESCRIPTION = """
If checked, the answer choices will be presented to each student in a random
order.
"""

TRANSLATIONS_BASE_LANGUAGE = """
This is the base language of the course; other languages represent translations
of the default content in this language.
"""

TRANSLATIONS_OTHER_LANGUAGES = """
The course is available in the languages listed here which are marked as
available.
"""

TRANSLATIONS_PREVENT_EDITS = """
If checked, translations cannot be edited. This can be set to prevent accidental
or undesired edits to translated content.
"""

TRANSLATIONS_SHOW_LANGUAGE_PICKER = """
If checked, students can select among the available languages at any time via a
language picker. Otherwise, the desire language must be assigned during
registration.
"""

REGISTRATION_EMAIL_BODY = """
This is the body for welcome emails. Use the string {{student_name}} to include
the name of the student and {{course_title}} to include the course title. To
avoid spamming, you should always include {{unsubscribe_url}} in your message to
add a link which the recipient can use to unsubscribe from future mailings.
"""

REGISTRATION_EMAIL_SENDER = """
This is the "from" email address for welcome emails. It must be set to a valid
value for App Engine email.
"""

REGISTRATION_EMAIL_SUBJECT = """
This is the subject line for welcome emails. Use the string {{student_name}} to
include the name of the student and {{course_title}} to include the course
title.
"""

REGISTRATION_INTRODUCTION = """
This introduction text is shown to students at the top of the registration page.
"""

REGISTRATION_REGISTRATION_FORM = """
This text or question is shown below the default registration question.
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

SITE_SETTINGS_AGGREGATE_COUNTERS = """
If "True", counter values are aggregated across all frontend application
instances and recorded in memcache. This slightly increases latency of all
requests, but improves the quality of performance metrics. Otherwise, you will
only see counter values for the one frontend instance you are connected to right
now.
"""

SITE_SETTINGS_CACHE_CONTENT = """
If "True", course content is cached. During course development you should turn
this setting to "False" so you can see your changes instantaneously. Otherwise,
keep this setting at "True" to maximize performance.
"""

SITE_SETTINGS_COURSE_URLS = safe_dom.NodeList().append(
    safe_dom.Element('div').add_text("""
Specify the URLs for your course(s). Specify only one course per line.""")
    ).append(safe_dom.Element('br')).append(
        safe_dom.Element('span').add_text("""
The syntax has four parts, separated by colons (':'). The four parts are:""")
    ).append(
        safe_dom.Element('ol').add_child(
            safe_dom.Element('li').add_text(
                'The word \'course\', which is a required element.')
        ).add_child(
            safe_dom.Element('li').add_text("""
A unique course URL prefix. Examples could be '/cs101' or '/art'.
Default: '/'""")
        ).add_child(
            safe_dom.Element('li').add_text("""
A file system location of course asset files. If location is left empty,
the course assets are stored in a datastore instead of the file system. A course
with assets in a datastore can be edited online. A course with assets on file
system must be re-deployed to Google App Engine manually.""")
        ).add_child(
            safe_dom.Element('li').add_text("""
A course datastore namespace where course data is stored in App Engine.
Note: this value cannot be changed after the course is created."""))
    ).append(
        safe_dom.Text(
            'For example, consider the following two course entries:')
    ).append(safe_dom.Element('br')).append(
        safe_dom.Element('div', className='gcb-message').add_text(
            'course:/cs101::ns_cs101'
        ).add_child(
            safe_dom.Element('br')
        ).add_text('course:/:/')
    ).append(
        safe_dom.Element('div').add_text("""
Assuming you are hosting Course Builder on http://www.example.com, the first
entry defines a course on a http://www.example.com/cs101 and both its assets
and student data are stored in the datastore namespace 'ns_cs101'. The second
entry defines a course hosted on http://www.example.com/, with its assets
stored in the '/' folder of the installation and its data stored in the default
empty datastore namespace.""")
    ).append(safe_dom.Element('br')).append(
        safe_dom.Element('div').add_text("""
A line that starts with '#' is ignored. Course entries are applied in the
order they are defined.""")
)

SITE_SETTINGS_GOOGLE_APIS = """
If "True", courses can use Google APIs. You must still configure the relevant
APIs in the Cloud Console to successfully make API calls.
"""

SITE_SETTINGS_MEMCACHE = """
If "True", various objects are cached in memcache. During course development you
should turn this setting to "False" so you can see your changes instantaneously.
Otherwise, keep this setting at "True" to maximize performance.
"""

SITE_SETTINGS_QUEUE_NOTIFICATION = safe_dom.NodeList().append(
    safe_dom.Element('div').add_text("""
Specify the number of queue failures before Course Builder sends a notification
email to the course administrator(s)."""
).append(
    safe_dom.Element('br')
).append(
    safe_dom.Element('br')
).append(
    safe_dom.Element('div').add_text("""
Course Builder uses a work queue to notify modules of changes in the status of
students (enrollment, unenrollment, etc.). Since some of the work done from this
queue is potentially sensitive (e.g., privacy concerns), the queue will re-try
failed work indefinitely. If the failures persist for the specified number of
attempts, an email is sent to all the course administrators to alert them of the
problem. Retries are done with increasingly large delays 0:15, 0:30, 1:00, 2:00,
4:00, 8:00, 32:00, 1:04:00 and every two hours thereafter.""")))

SITE_SETTINGS_REFRESH_INTERVAL_TEMPLATE = """
An update interval (in seconds) for reloading runtime properties from the
datastore. Specify an integer value between 1 and %s, inclusive. To completely
disable reloading properties set the value to 0 in the app.yaml file.
"""

SITE_SETTINGS_SHARE_STUDENT_PROFILE = """
If "True", the student's profile information is shared among all the different
courses for which she registered. This setting is only relevant if you have
multiple courses on this instance.
"""

SITE_SETTINGS_SITE_ADMIN_EMAILS = """
This list of email addresses represents the super-administrators for the whole
site. Super-admin users have the highest level of access to your Google App
Engine istance and to all data about all courses and students within that
instance. Separate addresses with a comma, space, or newline.
"""

SITE_SETTINGS_WHITELIST = """
Specify a list of email addresses of users who are allowed to access courses.
Separate the email addresses with commas. If this field is blank, site-wide user
whitelisting is disabled. Access to courses is implicitly granted to Google App
Engine admins and course admins, so don't repeat them here. Course-specific
whitelists supercede this list: if a course has a non-blank whitelist, this list
is ignored.
"""

ORGANIZATION_NAME_DESCRIPTION = """
The organization name appears in the footer of every page, but only when the
Organization URL is also provided.
"""

ORGANIZATION_URL_DESCRIPTION = """
When the Organization Name is provided, it is displayed in the footer of every
page linked to the Organization URL. Links to other sites must start with "http"
or "https".
"""

IMAGE_OR_VIDEO_DESCRIPTION = """
URL for the preview image or YouTube video shown on the course homepage. Videos
must use the YouTube embed URL.
"""

IMAGE_DESCRIPTION_DESCRIPTION = """
This is the alt text for the preview image on the course syllabus page (useful
for screen readers).
"""

SITE_NAME_DESCRIPTION = """
This is the name of the site header of every page, next to the Site Logo. It
links to the root (default) of this deployment.
"""

SITE_LOGO_DESCRIPTION = """
This logo is displayed in the upper left corner of every student facing page,
next to the Site Name. It links to the root (default) of this deployment. Links
to other sites must start with "http" or "https".
"""

SITE_LOGO_DESCRIPTION_DESCRIPTION = """
This is the alt text for the Site Logo (useful for screen readers).
"""

COURSE_URL_COMPONENT_DESCRIPTION = """
This is the basename of your course in the URL.
"""

COURSE_NAMESPACE_DESCRIPTION = """
This is the namespace for your course.
"""
