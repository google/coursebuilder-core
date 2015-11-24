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


# TODO(johncox): remove _DefaultSuffix and _LegacyUrl once _ALL is fully
# populated.
class _DefaultSuffix(object):
    pass


_DEFAULT_SUFFIX = _DefaultSuffix()


class _LegacyUrl(object):
    """A legacy URL, where the value is taken verbatim instead of calculated."""

    def __init__(self, value):
        self.value = value


# Mappings. Each row is a (topic_id, url_suffix), where topic_id is a string
# containing the unique identifier of the help topic, and url_suffix is a string
# giving the suffix of the help URL. Neither may be missing or empty. url_suffix
# is relative to the version component of the URL.
# TODO(rim): replace the 2nd column below with the correct URLs and validate. If
# you have a URL of the form
#
#   https://www.google.com/edu/openonline/course-builder/docs/1.10/something,
#
# the value to put here is '/something'.
_ALL = [
    ('certificate:certificate_criteria', _DEFAULT_SUFFIX),
    ('core_tags:google_drive:unavailable', _DEFAULT_SUFFIX),
    ('core_tags:google_group:name', _DEFAULT_SUFFIX),
    ('core_tags:markdown:markdown', _DEFAULT_SUFFIX),
    ('course:advanced:description', _LegacyUrl(
        'https://code.google.com/p/course-builder/wiki/CourseSettings')),
    ('course:assessment:content', _LegacyUrl(
        'https://code.google.com/p/course-builder/wiki/CreateAssessments')),
    ('course:assessment:datetime', _LegacyUrl(
        'https://code.google.com/p/course-builder/wiki/PeerReview')),
    ('course:assessment:html_content', _LegacyUrl(
        'https://code.google.com/p/course-builder/wiki/CreateAssessments')),
    ('course:assessment:review_form', _LegacyUrl(
        'https://code.google.com/p/course-builder/wiki/PeerReview')),
    ('course:assessment:review_opts', _LegacyUrl(
        'https://code.google.com/p/course-builder/wiki/PeerReview')),
    ('course:assessment:snippet', _DEFAULT_SUFFIX),
    ('course:assessment:workflow:grader', _DEFAULT_SUFFIX),
    ('course:auto_index', _DEFAULT_SUFFIX),
    ('course:can_record_student_events', _DEFAULT_SUFFIX),
    ('course:can_student_change_locale', _DEFAULT_SUFFIX),
    ('course:google:api_key', _DEFAULT_SUFFIX),
    ('course:google:client_id', _DEFAULT_SUFFIX),
    ('course:google_analytics_id', _DEFAULT_SUFFIX),
    ('course:google_tag_manager_id', _DEFAULT_SUFFIX),
    ('course:lesson:activity', _LegacyUrl(
        'https://code.google.com/p/course-builder/wiki/CreateActivities'
        '#Writing_activities')),
    ('course:lesson:manual_progress', _DEFAULT_SUFFIX),
    ('course:main_image:url', _DEFAULT_SUFFIX),
    ('course:unit:manual_progress', _DEFAULT_SUFFIX),
    ('course:welcome_notifications_sender', _DEFAULT_SUFFIX),
    ('dashboard:gift_questions:questions', _DEFAULT_SUFFIX),
    ('data_pump:json_key', _DEFAULT_SUFFIX),
    ('data_pump:pii_encryption_token', _DEFAULT_SUFFIX),
    ('data_pump:project_id', _DEFAULT_SUFFIX),
    ('data_pump:table_lifetime', _DEFAULT_SUFFIX),
    ('data_removal:removal_policy', _DEFAULT_SUFFIX),
    ('math:math:input_type', _DEFAULT_SUFFIX),
    ('questionnaire:questionnaire:disabled', _DEFAULT_SUFFIX),
    ('questionnaire:questionnaire:form_id', _DEFAULT_SUFFIX),
    ('reg_form:additonal_registration_fields', _DEFAULT_SUFFIX),
    ('settings:debugging:show_hooks', _DEFAULT_SUFFIX),
    ('settings:debugging:show_jinja_context', _DEFAULT_SUFFIX),
    ('workflow:review_due_date', _LegacyUrl(
        'https://code.google.com/p/course-builder/wiki/PeerReview')),
    ('workflow:review_min_count', _LegacyUrl(
        'https://code.google.com/p/course-builder/wiki/PeerReview')),
    ('workflow:review_window_mins', _LegacyUrl(
        'https://code.google.com/p/course-builder/wiki/PeerReview'))
]
