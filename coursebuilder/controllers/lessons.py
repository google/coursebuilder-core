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

import urlparse
from models import models
from models import transforms
from models.config import ConfigProperty
from models.counters import PerfCounter
from utils import BaseHandler
from utils import BaseRESTHandler
from utils import XsrfTokenManager

# Whether to record events in a database.
CAN_PERSIST_ACTIVITY_EVENTS = ConfigProperty(
    'gcb_can_persist_activity_events', bool, (
        'Whether or not to record student activity interactions in a '
        'datastore. Without event recording, you cannot analyze student '
        'activity interactions. On the other hand, no event recording reduces '
        'the number of datastore operations and minimizes the use of Google '
        'App Engine quota. Turn event recording on if you want to analyze '
        'this data.'),
    False)

COURSE_EVENTS_RECEIVED = PerfCounter(
    'gcb-course-events-received',
    'A number of activity/assessment events received by the server.')

COURSE_EVENTS_RECORDED = PerfCounter(
    'gcb-course-events-recorded',
    'A number of activity/assessment events recorded in a datastore.')


def extract_unit_and_lesson_id(handler):
    """Extracts unit and lesson ids from a request."""
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


def get_unit_and_lesson_id_from_url(url):
    """Extracts unit and lesson ids from a URL."""
    url_components = urlparse.urlparse(url)
    query_dict = urlparse.parse_qs(url_components.query)
    unit_id, lesson_id = query_dict['unit'][0], query_dict['lesson'][0]
    return unit_id, lesson_id


class CourseHandler(BaseHandler):
    """Handler for generating course page."""

    @classmethod
    def get_child_routes(cls):
        """Add child handlers for REST."""
        return [('/rest/events', EventsRESTHandler)]

    def get(self):
        """Handles GET requests."""
        user = self.personalize_page_and_get_user()
        if not user:
            self.redirect('/preview')
            return None

        student = self.personalize_page_and_get_enrolled()
        if not student:
            return

        self.template_value['units'] = self.get_units()
        self.template_value['progress'] = (
            self.get_progress_tracker().get_unit_progress(student))
        self.template_value['is_progress_recorded'] = (
            CAN_PERSIST_ACTIVITY_EVENTS.value)
        self.template_value['navbar'] = {'course': True}
        self.render('course.html')


class UnitHandler(BaseHandler):
    """Handler for generating unit page."""

    def get(self):
        """Handles GET requests."""
        student = self.personalize_page_and_get_enrolled()
        if not student:
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

        # Set template values for student progress
        self.template_value['is_progress_recorded'] = (
            CAN_PERSIST_ACTIVITY_EVENTS.value)
        if CAN_PERSIST_ACTIVITY_EVENTS.value:
            self.template_value['progress'] = (
                self.get_progress_tracker().get_lesson_progress(
                    student, unit_id))

        self.render('unit.html')


class ActivityHandler(BaseHandler):
    """Handler for generating activity page and receiving submissions."""

    def get(self):
        """Handles GET requests."""
        student = self.personalize_page_and_get_enrolled()
        if not student:
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

        # Set template value for event recording
        self.template_value['record_events'] = CAN_PERSIST_ACTIVITY_EVENTS.value

        # Set template values for student progress
        self.template_value['is_progress_recorded'] = (
            CAN_PERSIST_ACTIVITY_EVENTS.value)
        if CAN_PERSIST_ACTIVITY_EVENTS.value:
            self.template_value['progress'] = (
                self.get_progress_tracker().get_lesson_progress(
                    student, unit_id))

        self.template_value['event_xsrf_token'] = (
            XsrfTokenManager.create_xsrf_token('event-post'))

        # Mark this page as accessed. This is done after setting the student
        # progress template value, so that the mark only shows up after the
        # student visits the page for the first time.
        self.get_course().get_progress_tracker().put_activity_accessed(
            student, unit_id, lesson_id)

        self.render('activity.html')


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
        self.template_value['record_events'] = CAN_PERSIST_ACTIVITY_EVENTS.value
        self.template_value['assessment_xsrf_token'] = (
            XsrfTokenManager.create_xsrf_token('assessment-post'))
        self.template_value['event_xsrf_token'] = (
            XsrfTokenManager.create_xsrf_token('event-post'))

        self.render('assessment.html')


class EventsRESTHandler(BaseRESTHandler):
    """Provides REST API for an Event."""

    def post(self):
        """Receives event and puts it into datastore."""

        COURSE_EVENTS_RECEIVED.inc()
        if not CAN_PERSIST_ACTIVITY_EVENTS.value:
            return

        request = transforms.loads(self.request.get('request'))
        if not self.assert_xsrf_token_or_fail(request, 'event-post', {}):
            return

        user = self.get_user()
        if not user:
            return

        source = request.get('source')
        payload_json = request.get('payload')

        models.EventEntity.record(source, user, payload_json)
        COURSE_EVENTS_RECORDED.inc()

        self.process_event(user, source, payload_json)

    def process_event(self, user, source, payload_json):
        """Processes an event after it has been recorded in the event stream."""

        if source == 'attempt-activity':
            student = models.Student.get_enrolled_student_by_email(user.email())
            if not student:
                return
            payload = transforms.loads(payload_json)
            source_url = payload['location']
            unit_id, lesson_id = get_unit_and_lesson_id_from_url(source_url)
            if unit_id is not None and lesson_id is not None:
                self.get_course().get_progress_tracker().put_block_completed(
                    student, unit_id, lesson_id, payload['index'])
