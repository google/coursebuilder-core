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

"""Help URL topic mappings."""

__author__ = [
    'John Cox (johncox@google.com)',
]


class _LegacyUrl(object):
    """A legacy URL, where the value is taken verbatim instead of calculated."""

    def __init__(self, value):
        self.value = value


# Mappings. Each row is a (topic_id, url_suffix), where topic_id is a string
# containing the unique identifier of the help topic, and url_suffix is a string
# giving the suffix of the help URL. Neither may be missing or empty. url_suffix
# is relative to the version component of the URL. If you have a URL of the form
#
#   https://www.google.com/edu/openonline/course-builder/docs/1.10/something,
#
# the value to put here is '/something'.
_ALL = [
    ('certificate:certificate_criteria',
     '/prepare-for-students/certificates.html'),
    ('core_tags:google_drive:unavailable',
     '/create-a-course/add-content/google-drive.html'
     '#enable-apis'),
    ('core_tags:google_group:name',
     '/create-a-course/add-content/content-editor.html'
     '#google-group'),
    ('core_tags:markdown:markdown',
     '/create-a-course/add-content/content-editor.html'
     '#markdown'),
    ('course:advanced:description',
     '/create-a-course/course-settings.html'
     '#advanced-course-settings'),
    ('course:assessment:content',
     '/create-a-course/add-elements/assessments/assessments.html'),
    ('course:assessment:html_content',
     '/create-a-course/add-elements/assessments/assessments.html'),
    ('course:assessment:review_form',
     '/create-a-course/add-elements/assessments/peer-review.html'
     '#reviewer-feedback-form'),
    ('course:assessment:review_opts',
     '/create-a-course/add-elements/assessments/peer-review.html'
     '#peer-review-fields'),
    ('course:assessment:snippet',
     '/create-a-course/add-elements/assessments/assessments.html'
     '#embed-link'),
    ('course:assessment:workflow:grader',
     '/create-a-course/add-elements/assessments/assessments.html'
     '#grading-method'),
    ('course:auto_index',
     '/create-a-course/course-settings.html'
     '#auto-index-course'),
    ('course:availability:availability',
     '/publish-a-course/availability.html'
     '#content-availability'),
    ('course:availability:shown_when_unavailable',
     '/publish-a-course/availability.html'
     '#shown-when-private'),
    ('course:availability:triggers',
     '/publish-a-course/availability.html'
     '#calendar-triggers'),
    ('course:can_record_student_events',
     '/create-a-course/course-settings.html'
     '#enable-student-analytics'),
    ('course:can_student_change_locale',
     '/prepare-for-students/translations/set-up.html'
     '#show-language-picker'),
    ('course:google:api_key',
     '/create-a-course/add-content/google-drive.html'
     '#get-credentials'),
    ('course:google:client_id',
     '/create-a-course/add-content/google-drive.html'
     '#get-credentials'),
    ('course:google:client_secret',
     '/create-a-course/add-content/google-drive.html'
     '#get-credentials'),
    ('course:google_analytics_id',
     '/create-a-course/course-settings.html'
     '#analytics-id'),
    ('course:google_tag_manager_id',
     '/create-a-course/course-settings.html'
     '#tag-manager-id'),
    ('course:lesson:activity',
     '/create-a-course/add-elements/lessons/add-new.html'
     '#lesson-body'),
    ('course:lesson:manual_progress',
     '/create-a-course/add-elements/lessons/settings.html'
     '#allow-progress-override'),
    ('course:main_image:url',
     '/create-a-course/course-settings.html'
     '#image-or-video'),
    ('course:unit:manual_progress',
     '/create-a-course/add-elements/units/details-and-settings.html'
     '#allow-progress-override'),
    ('course:welcome_notifications_sender',
     '/prepare-for-students/registration.html'
     '#email-sender'),
    ('course:send_welcome_notifications',
     '/prepare-for-students/registration.html'
     '#welcome-emails'),
    ('dashboard:gift_questions:questions',
     '/create-a-course/add-elements/questions/formats.html'
     '#gift-questions'),
    ('dashboard:powered_by',
     '/index.html'),
    ('data_pump:json_key',
     '/analyze-data/custom-analytics.html'
     '#data-pump-values'),
    ('data_pump:pii_encryption_token',
     '/analyze-data/custom-analytics.html'
     '#data-pump-values'),
    ('data_pump:project_id',
     '/set-up-course-builder/create-a-cloud-project.html'
     '#set-project-id'),
    ('data_pump:table_lifetime',
     '/analyze-data/custom-analytics.html'
     '#data-pump-values'),
    ('data_removal:removal_policy',
     '/create-a-course/course-settings.html'
     '#removal-policy'),
    ('modules:drive:service_account_json',
     '/index.html'),
    ('help:documentation',
     '/index.html'),
    ('help:forum', _LegacyUrl(
        'https://groups.google.com/forum/?fromgroups#!categories/'
        'course-builder-forum/general-troubleshooting')),
    ('help:videos', _LegacyUrl(
        'https://www.youtube.com/playlist?list=PLFB_aGY5EfxeltJfJZwkjqDLAW'
        'dMfSpES')),
    ('labels:tracks',
     '/create-a-course/organize-elements/tracks.html'),
    ('math:math:input_type',
     '/create-a-course/add-content/content-editor.html'
     '#math-formula'),
    ('modules:guide:availability',
     '/administer-site/guides.html'
     '#availability'),
    ('modules:guide:enabled',
     '/administer-site/guides.html'
     '#enable-guides'),
    ('modules:webserv:availability',
     '/administer-site/web-server.html'
     '#availability'),
    ('modules:webserv:doc_root',
     '/administer-site/web-server.html'
     '#content-root'),
    ('modules:webserv:enabled',
     '/administer-site/web-server.html'
     '#enable-web-server'),
    ('questionnaire:questionnaire:disabled',
     '/create-a-course/add-content/content-editor.html'
     '#questionnaire'),
    ('questionnaire:questionnaire:form_id',
     '/create-a-course/add-content/content-editor.html'
     '#questionnaire'),
    ('reg_form:additional_registration_fields',
     '/prepare-for-students/registration.html'
     '#registration-questions'),
    ('settings:debugging:show_hooks',
     '/debug-course/debug-course.html'),
    ('settings:debugging:show_jinja_context',
     '/debug-course/debug-course.html'),
    ('workflow:review_window_mins',
     '/create-a-course/add-elements/assessments/peer-review.html'
     '#review-window-timeout'),
]
