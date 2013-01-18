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

"""Handlers for generating various frontend pages."""

__author__ = 'Saifu Angto (saifu@google.com)'

from models import models
from models.config import ConfigProperty
from models.counters import PerfCounter
from utils import BaseHandler

# Whether to record events in a database.
CAN_PERSIST_ACTIVITY_EVENTS = ConfigProperty(
    'gcb_can_persist_activity_events', bool, (
        'If "True", all student activity interactions are recorded in a '
        'datastore. Set to "False" to turn off event recording. Do so if you '
        'will not analyze the data, to reduce the number of datastore '
        'operations, or to minimize the use of Google App Engine quota.'),
    False)

ACTIVITY_EVENTS_RECEIVED = PerfCounter(
    'gcb-activity-events-received',
    'A number of activity events received by the server.')

ACTIVITY_EVENTS_RECORDED = PerfCounter(
    'gcb-activity-events-recorded',
    'A number of activity events recorded by the server in a datastore.')


def extract_unit_and_lesson_id(handler):
    """Extracts unit and lesson id from the request."""
    c = handler.request.get('unit')
    if not c:
        unit_id = 1
    else:
        unit_id = int(c)

    l = handler.request.get('lesson')
    if not l:
        lesson_id = 1
    else:
        lesson_id = int(l)

    return unit_id, lesson_id


class CourseHandler(BaseHandler):
    """Handler for generating course page."""

    def get(self):
        """Handles GET requests."""
        user = self.personalize_page_and_get_user()
        if not user:
            self.redirect('/preview')
            return None

        if not self.personalize_page_and_get_enrolled():
            return

        self.template_value['units'] = self.get_units()
        self.template_value['navbar'] = {'course': True}
        self.render('course.html')


class UnitHandler(BaseHandler):
    """Handler for generating unit page."""

    def get(self):
        """Handles GET requests."""
        if not self.personalize_page_and_get_enrolled():
            return

        # Extract incoming args
        unit_id, lesson_id = extract_unit_and_lesson_id(self)
        self.template_value['unit_id'] = unit_id
        self.template_value['lesson_id'] = lesson_id

        # Set template values for a unit and its lesson entities
        for unit in self.get_units():
            if unit.unit_id == str(unit_id):
                self.template_value['units'] = unit

        lessons = self.get_lessons(unit_id)
        self.template_value['lessons'] = lessons

        # Set template values for nav bar
        self.template_value['navbar'] = {'course': True}

        # Set template values for back and next nav buttons
        if lesson_id == 1:
            self.template_value['back_button_url'] = ''
        elif lessons[lesson_id - 2].activity:
            self.template_value['back_button_url'] = (
                'activity?unit=%s&lesson=%s' % (unit_id, lesson_id - 1))
        else:
            self.template_value['back_button_url'] = (
                'unit?unit=%s&lesson=%s' % (unit_id, lesson_id - 1))

        if lessons[lesson_id - 1].activity:
            self.template_value['next_button_url'] = (
                'activity?unit=%s&lesson=%s' % (unit_id, lesson_id))
        elif lesson_id == len(lessons):
            self.template_value['next_button_url'] = ''
        else:
            self.template_value['next_button_url'] = (
                'unit?unit=%s&lesson=%s' % (unit_id, lesson_id + 1))

        self.render('unit.html')


class ActivityHandler(BaseHandler):
    """Handler for generating activity page and receiving submissions."""

    def get(self):
        """Handles GET requests."""
        if not self.personalize_page_and_get_enrolled():
            return

        # Extract incoming args
        unit_id, lesson_id = extract_unit_and_lesson_id(self)
        self.template_value['unit_id'] = unit_id
        self.template_value['lesson_id'] = lesson_id

        # Set template values for a unit and its lesson entities
        for unit in self.get_units():
            if unit.unit_id == str(unit_id):
                self.template_value['units'] = unit

        lessons = self.get_lessons(unit_id)
        self.template_value['lessons'] = lessons

        # Set template values for nav bar
        self.template_value['navbar'] = {'course': True}

        # Set template values for back and next nav buttons
        self.template_value['back_button_url'] = (
            'unit?unit=%s&lesson=%s' % (unit_id, lesson_id))
        if lesson_id == len(lessons):
            self.template_value['next_button_url'] = ''
        else:
            self.template_value['next_button_url'] = (
                'unit?unit=%s&lesson=%s' % (unit_id, lesson_id + 1))

        self.template_value['record_events'] = str(
            CAN_PERSIST_ACTIVITY_EVENTS.value).lower()

        self.render('activity.html')

    def post(self):
        """Receives activity submissions and puts it into datastore."""

        ACTIVITY_EVENTS_RECEIVED.inc()
        if not CAN_PERSIST_ACTIVITY_EVENTS.value:
            return

        user = self.get_user()
        if not user:
            return

        student = models.Student.get_enrolled_student_by_email(user.email())
        if not student:
            return

        models.EventEntity.record('activity', user, self.request.get('request'))
        ACTIVITY_EVENTS_RECORDED.inc()


class AssessmentHandler(BaseHandler):
    """Handler for generating assessment page."""

    def get(self):
        """Handles GET requests."""
        if not self.personalize_page_and_get_enrolled():
            return

        # Extract incoming args
        n = self.request.get('name')
        if not n:
            n = 'Pre'
        self.template_value['name'] = n
        self.template_value['navbar'] = {'course': True}
        self.render('assessment.html')
