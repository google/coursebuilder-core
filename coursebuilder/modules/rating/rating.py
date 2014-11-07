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

"""Provide a widget to record user satisfaction with course content."""

__author__ = 'John Orr (jorr@google.com)'

import os

import jinja2

import appengine_config
from common import schema_fields
from common import tags
from controllers import lessons
from controllers import utils
from models import courses
from models import custom_modules
from models import models
from models import transforms

from google.appengine.api import users

RESOURCES_PATH = '/modules/rating/resources'

# The token to namespace the XSRF token to this module
XSRF_TOKEN_NAME = 'rating'

# The "source" field to identify events recorded by this module
EVENT_SRC = 'rating-event'

TEMPLATES_DIR = os.path.join(
    appengine_config.BUNDLE_ROOT, 'modules', 'rating', 'templates')

rating_module = None


class StudentRatingProperty(models.StudentPropertyEntity):
    """Entity to store the student's current rating of each component."""

    PROPERTY_NAME = 'student-rating-property'

    @classmethod
    def load_or_create(cls, student):
        entity = cls.get(student, cls.PROPERTY_NAME)
        if entity is None:
            entity = cls.create(student, cls.PROPERTY_NAME)
            entity.value = '{}'
            entity.put()
        return entity

    def get_rating(self, key):
        value_dict = transforms.loads(self.value)
        return value_dict.get(key)

    def set_rating(self, key, value):
        value_dict = transforms.loads(self.value)
        value_dict[key] = value
        self.value = transforms.dumps(value_dict)


class StudentRatingEvent(models.EventEntity):

    def for_export(self, transform_fn):
        model = super(StudentRatingEvent, self).for_export(transform_fn)

        data_dict = transforms.loads(model.data)
        model.data = transforms.dumps({
            'key': data_dict['key'],
            'rating': data_dict['rating']})

        return model


class RatingHandler(utils.BaseRESTHandler):
    """REST handler for recording and displaying rating scores."""

    URL = '/rest/modules/rating'

    def _get_payload_and_student(self):
        # I18N: Message displayed to non-logged in user
        access_denied_msg = self.gettext('Access denied.')

        if not _rating__is_enabled_in_course_settings(self.app_context):
            transforms.send_json_response(self, 401, access_denied_msg, {})
            return (None, None)

        request = transforms.loads(self.request.get('request'))

        if not self.assert_xsrf_token_or_fail(request, XSRF_TOKEN_NAME, {}):
            return (None, None)

        user = users.get_current_user()
        if user is None:
            transforms.send_json_response(self, 401, access_denied_msg, {})
            return (None, None)

        student = models.Student.get_enrolled_student_by_email(user.email())
        if student is None:
            transforms.send_json_response(self, 401, access_denied_msg, {})
            return (None, None)

        return (transforms.loads(request.get('payload')), student)

    def get(self):
        payload, student = self._get_payload_and_student()
        if payload is None and student is None:
            return

        key = payload.get('key')
        prop = StudentRatingProperty.load_or_create(student)
        rating = prop.get_rating(key)

        payload_dict = {
            'key': key,
            'rating': rating
        }
        transforms.send_json_response(
            self, 200, None, payload_dict=payload_dict)

    def post(self):
        payload, student = self._get_payload_and_student()
        if payload is None and student is None:
            return

        key = payload.get('key')
        rating = payload.get('rating')
        additional_comments = payload.get('additional_comments')

        if rating is not None:
            prop = StudentRatingProperty.load_or_create(student)
            prop.set_rating(key, rating)
            prop.put()

        StudentRatingEvent.record(EVENT_SRC, self.get_user(), transforms.dumps({
            'key': key,
            'rating': rating,
            'additional_comments': additional_comments
        }))

        # I18N: Message displayed when user submits written comments
        thank_you_msg = self.gettext('Thank you for your feedback.')

        transforms.send_json_response(self, 200, thank_you_msg, {})


def _rating__is_enabled_in_course_settings(app_context):
    env = app_context.get_environ()
    return env .get('unit', {}).get('ratings_module', {}).get('enabled')


def extra_content(app_context):
    if not _rating__is_enabled_in_course_settings(app_context):
        return None

    user = users.get_current_user()
    if user is None or (
        models.Student.get_enrolled_student_by_email(user.email()) is None
    ):
        return None

    template_data = {
        'xsrf_token': utils.XsrfTokenManager.create_xsrf_token(XSRF_TOKEN_NAME)
    }
    template_environ = app_context.get_template_environ(
        app_context.get_current_locale(), [TEMPLATES_DIR])
    return jinja2.Markup(
        template_environ.get_template('widget.html').render(template_data))


def get_course_settings_fields(unused_course):
    return schema_fields.SchemaField(
        'unit:ratings_module:enabled', 'Ratings widget', 'boolean',
        description='Whether to show user rating widget at the bottom of '
        'each unit and lesson.')


def register_module():

    def on_module_enabled():
        courses.Course.OPTIONS_SCHEMA_PROVIDERS[
            courses.Course.SCHEMA_SECTION_UNITS_AND_LESSONS
        ].append(get_course_settings_fields)
        lessons.UnitHandler.EXTRA_CONTENT.append(extra_content)

    def on_module_disabled():
        courses.Course.OPTIONS_SCHEMA_PROVIDERS[
            courses.Course.SCHEMA_SECTION_UNITS_AND_LESSONS
        ].remove(get_course_settings_fields)
        lessons.UnitHandler.EXTRA_CONTENT.remove(extra_content)

    global_routes = [
        (os.path.join(RESOURCES_PATH, 'js', '.*'), tags.JQueryHandler),
        (os.path.join(RESOURCES_PATH, '.*'), tags.ResourcesHandler)]

    namespaced_routes = [(RatingHandler.URL, RatingHandler)]

    global rating_module
    rating_module = custom_modules.Module(
        'Student rating widget',
        'Provide a widget to record user satisfaction with course content.',
        global_routes, namespaced_routes,
        notify_module_enabled=on_module_enabled,
        notify_module_disabled=on_module_disabled)

    return rating_module
